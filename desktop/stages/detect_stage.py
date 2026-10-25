# -*- coding: utf-8 -*-
"""detect 阶段执行器：单图检测 + 批量检测。

重依赖（torch/ultralytics）由**常驻 YOLO 服务**承担（见
`functions/yolo_service.py`）：本进程只发「图片路径」过去等结果，因此一个
worker 起来只需几百毫秒，模型全局只加载一次、多次检测共用。

日志按用户要求逐张留痕——「模型加载用时」+「每张 detect 了哪个文件、结果
如何、花了多久」+「总计用时」。没有这些，一次检测跑完日志里只有进度条在动，
用户根本不知道到底执行了什么。
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.args import default_workers, machine_worker_budget
from desktop.stages.events import ProgressStream, emit, _real_stdout


def _emit_log(message: str, context: dict | None = None) -> None:
    """发一条人读日志事件（有 context 就带上，便于 GUI 归位到任务/阶段）。"""
    payload: dict = {"type": "log"}
    if context:
        payload.update(context)
    payload["message"] = message
    emit(payload)


def run_detect(config: dict) -> int:
    """检测单张图片的内容框（半幅左右 / 整幅），返回像素坐标（重依赖由常驻服务承担）。"""
    image_path = config["image"]
    emit({"type": "detect_started", "image": image_path})
    # ⚠️ 单图模式同样要拦 stdout（2026-09-26 审计 #19，与批量模式同款）：
    #    YOLO/ultralytics 的模型摘要直接 print，不拦就混进 stdout JSON 流，
    #    GUI 侧解析失败的行只能静默丢弃——模型加载日志凭空消失。
    interceptor = ProgressStream(_real_stdout(), {"image": image_path})
    original_stdout = sys.stdout
    sys.stdout = interceptor
    try:
        # 跨层复用（登记在案，见 docs/dev/refactor-modularity.md §3.C）：
        # GUI 检测阶段必须跑与 CLI **完全相同**的检测算法，否则界面预览与
        # 命令行产物会对不上；下沉到 core 不合适（检测属业务层）。
        # 放在函数内是刻意的——避免主进程加载 YOLO。
        import utils
        from functions.detect import (  # noqa: PLC0415
            resolution_note,
            detect_page_content_by_path,
            format_box,
            warm_up_detect_model,
        )

        # 模型准备单独一步并单独计时：不这么做的话，加载那几秒会算进第一张图，
        # 看起来像"某张图特别慢"（用户提过这点）。
        load_line, _load_seconds = warm_up_detect_model()
        _emit_log(load_line)
        started = time.perf_counter()
        page = detect_page_content_by_path(image_path)
        elapsed = time.perf_counter() - started
        _emit_log(
            f"detect {Path(image_path).name}  "
            f"左={format_box(page.left)} 右={format_box(page.right)} "
            f"整幅={format_box(page.full)}  "
            f"({elapsed * 1000:.0f} ms)"
        )
        note = resolution_note(page)  # 互斥消解剔了框 → 日志里看得见
        if note:
            _emit_log(note)
        emit(
            {
                "type": "boxes",
                "image": image_path,
                "left": list(page.left) if page.left else None,
                "right": list(page.right) if page.right else None,
                "full": list(page.full) if page.full else None,
            }
        )
        return 0
    except Exception as exc:
        _emit_log(f"检测失败: {Path(image_path).name} —— {exc}")
        emit({"type": "detect_error", "image": image_path, "message": str(exc)})
        return 1
    finally:
        sys.stdout = original_stdout
        # 进程结束时缓冲里若有残留（无换行的最后一行），按日志转发掉
        if interceptor.buffer.strip():
            interceptor._consume(interceptor.buffer.strip())


def run_detect_pages(files: list[Path], *, workers: int, report) -> dict:
    """逐页检测（**全仓唯一实现**）：子进程阶段与 singletask 执行器都调这里。

    **每次执行都重新跑全部页**（用户 2026-10-26：不再复用上次结果）。

    参数:
        files: 全部待处理的图片（按页序）。
        workers: 并发线程数；<=0 时按 ``core.args.default_workers`` 自动取。
        report: ``(事件名, 负载)`` 回调，名字取 ``log`` / ``progress`` /
            ``page_boxes``（与 ``desktop.steps.kernel.Report`` 同形）。

    返回:
        统计字典：``done/left/right/full/failed/cost/elapsed/
        load_seconds/workers``。

    ⚠️ 为什么抽出来（用户 2026-10-20 的第二个问题）：singletask 与任务流程
    必须跑**完全相同**的检测循环（并发、逐页日志、槽位事件），各写一份必然
    漂移；这里只负责"怎么跑"，不关心产物落到哪个文件。
    """
    total = len(files)
    stat: dict = {
        "done": 0, "left": 0, "right": 0, "full": 0, "failed": 0,
        "cost": 0.0, "elapsed": 0.0, "load_seconds": 0.0,
        "workers": 0,
    }
    if not total:
        return stat

    # 同上：跨层复用检测入口是登记在案的有意依赖。
    from functions.detect import (  # noqa: PLC0415 - 延迟导入，避免主进程加载重依赖
        detect_page_content_by_path,
        format_box,
        resolution_note,
        warm_up_detect_model,
    )

    # ⚠️ 模型准备**放在计时之外**：先把它备好并单独报一次耗时，之后每一张的
    # 耗时才是纯检测耗时；否则第一张会背上 5 秒，看起来像那张图有问题。
    load_line, load_seconds = warm_up_detect_model()
    stat["load_seconds"] = load_seconds
    report("log", {"message": load_line})

    # 逐张并发跑：单线程一张一两百毫秒，81 页就要十几秒；并发后总时长
    # 主要取决于最慢的那张。上限与函数层共用一份（core.args.default_workers
    # 传入 command="detect" → min(8, CPU 核数, 张数)）：检测每张只在服务端
    # imread 一次，比去底/裁剪的 ~350MB/张轻得多，所以上限单独放宽到 8。
    # 具体数值只在 core/args.py 的 _COMMAND_WORKER_CAP 里写一次。
    workers = max(1, int(workers or 0) or default_workers(total, command="detect"))
    stat["workers"] = workers
    if workers > 1:
        report("log", {
            "message": f"并发处理：{workers} 个线程（共 {total} 张）"
        })

    started_all = time.perf_counter()
    lock = threading.Lock()

    def _detect_one(path: Path) -> None:
        """检测一张并立刻上报。**计数与上报都放在锁内**，保证
        「本张的 page_boxes → 本张的 progress」成对出现、计数不互相覆盖。"""
        started = time.perf_counter()
        failure = None
        page = None
        try:
            page = detect_page_content_by_path(path)
        except Exception as exc:  # noqa: BLE001 - 单张失败不该中断整批
            failure = str(exc)
        elapsed = time.perf_counter() - started
        with lock:
            stat["done"] += 1
            stat["cost"] += elapsed
            if failure or page is None:
                # ⚠️ ``page is None`` 与 failure 同一分支：检测没抛异常时
                # 一定给了结果对象，走到这儿拿不到就按失败记，别让它掉进
                # 下面的成功分支去读 page.left。
                stat["failed"] += 1
                report("log", {
                    "message": f"detect {path.name} 失败: {failure or '无检测结果'}"
                })
            else:
                if page.left:
                    stat["left"] += 1
                if page.right:
                    stat["right"] += 1
                if page.full:
                    stat["full"] += 1
                report("log", {
                    "message": (
                        f"detect {path.name}  "
                        f"左={format_box(page.left)} 右={format_box(page.right)} "
                        f"整幅={format_box(page.full)}  "
                        f"({elapsed * 1000:.0f} ms)"
                    )
                })
                note = resolution_note(page)  # 互斥消解剔了框 → 日志里看得见
                if note:
                    report("log", {"message": note})
                report("page_boxes", {
                    "image": path.stem,
                    "left": list(page.left) if page.left else None,
                    "right": list(page.right) if page.right else None,
                    "full": list(page.full) if page.full else None,
                })
            report("progress", {"done": stat["done"], "total": total})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_detect_one, path) for path in files]
        for future in as_completed(futures):
            # 单张的异常已在 _detect_one 内兜住；这里只是等全部跑完
            future.result()

    stat["elapsed"] = time.perf_counter() - started_all
    counted = max(stat["done"], 1)  # 防零除（total 已保证 > 0）
    summary = (
        f"总计用时 {stat['elapsed']:.1f} s（共 {total} 张："
        f"半幅 左{stat['left']}/右{stat['right']}、整幅 {stat['full']}、"
        f"失败 {stat['failed']}；"
        f"{workers} 线程，单张累计 {stat['cost']:.1f} s、"
        f"平均 {stat['cost'] / counted * 1000:.0f} ms/张）"
    )
    if load_seconds > 0:
        summary += f"，模型加载另计 {load_seconds:.1f} s"
    report("log", {"message": summary})
    return stat


def run_detect_stage(config: dict) -> int:
    """detect 阶段：逐图检测内容框（半幅左右 / 整幅）并上报坐标，不切割、不生成任何文件。

    检测算法复用 `functions.detect.detect_page_boxes_by_path`（内部即 CLI crop /
    cropremove 用的同一入口），最终裁剪框由 GUI 按同一套规则
    （`utils.box_geometry.compute_final_boxes`）从检测框实时推导，用于预览标注。

    ⚠️ 2026-10-22：本函数**只出框**。检测出几个框就裁几张图是
    :func:`run_detect_submit_stage`（「提交本次任务」）的事——第二步界面上
    就是「检测 → 提交」两步语义。

    ⚠️ 逐页循环本体在 :func:`run_detect_pages`（与 singletask 共用一份）；本函数
    只负责 stdout 拦截、任务上下文与事件协议（``{"type": name, **context, **payload}``）。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    # 拦截 stdout：YOLO/ultralytics 会直接 print，不拦住就会混进 stdout
    # 破坏 JSON Lines 协议（GUI 只能靠解析失败兜底当日志）。
    interceptor = ProgressStream(_real_stdout(), context)
    original_stdout = sys.stdout
    sys.stdout = interceptor
    try:
        # 同上：跨层复用检测入口是登记在案的有意依赖。
        import utils

        files = utils.collect_image_files(Path(args.get("input", ".")), is_file=False)
        total = len(files)
        if not total:
            emit({"type": "error", **context, "message": "输入目录中没有图片"})
            return 1

        def report(name: str, payload: dict) -> None:
            """把共用循环的事件翻成 stdout 协议行（带任务/阶段上下文）。"""
            emit({"type": name, **context, **payload})

        stat = run_detect_pages(
            files,
            workers=int(args.get("workers") or 0),
            report=report,
        )
        # ⚠️ 并发分支的真实进度在 `stat["done"]`（2026-09-26 审计：以前 finished
        #    里的 done 恒为 0）。GUI 现在靠 _last_progress 兜着看不出问题，但任何
        #    直接消费 finished 的旁路（e2e、将来的 UI）会拿到错误的完成数。
        emit(
            {
                "type": "finished",
                **context,
                "done": stat["done"],
                "total": total,
                "result": None,
                "output": None,
            }
        )
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
    finally:
        sys.stdout = original_stdout
        # 冲刷残留的库输出，避免最后一行被吞
        if interceptor.buffer.strip():
            interceptor._consume(interceptor.buffer.strip())


# ---------------------------------------------------------------- 提交（裁图）
#: 提交裁图的 JPEG 画质。裁图只是下一步去底色的输入，不需要无损；q95 +
#: 4:4:4（subsampling=0）实测与源像素 PSNR≈47.8dB，二值化后差异 ≤0.1%，
#: 体积约为原 PNG 的三分之一，编码耗时只有 PNG 的 1/14。
SUBMIT_JPEG_QUALITY = 95

#: 提交裁图的并行 worker 数。瓶颈在 JPEG 编码，单个 worker 同时持有一整页
#: 位图 + 输出画布，峰值内存随线程数线性涨。
#: ⚠️ 预算只走 ``core.args.machine_worker_budget()``（与函数层同一份），
#: 这里**不自己调 ``os.cpu_count()``**——那等于第二份并发策略（护栏
#: ``defaults_single_source`` 会盯着）。
SUBMIT_WORKERS = max(
    1,
    min(
        8,
        int(os.environ.get("GUJI_SUBMIT_WORKERS") or 0)
        or machine_worker_budget(),
    ),
)


def run_detect_submit_stage(config: dict) -> int:
    """detect 提交：把**每个检测框**裁成一张图，写入 ``stages/detect``（JPG q95）。

    用户 2026-10-22 口径：

    > 检测文本框流程，提交时把检测到的文本框里面的内容裁剪出来。
    > 提交任务，本步骤才算是执行完毕，才能转入下一阶段。

    也就是说这一步是"CLI crop 的两步版"：检测出一组框（人工可改）→
    提交时真正按框裁图。**没提交 = 没产物**，下一步（去底色）的输入
    目录是空的，自然转不过去。

    几何/命名/张数（``plan_detect_submit_entries`` → ``entry_to_effect_spec``
    → ``plan_submit_job`` → ``compose_region_output``）：检测出几个框就裁几张
    图，``-l`` / ``-r`` 命名、单栏书归一化、用户指定左右这些既有约定不变。

    产物格式为 **JPEG q95（4:4:4）**：裁图只作为下一步去底色的输入，不需要
    无损；q95 在扫描件上与源像素 PSNR≈47.8dB，二值化后差异 ≤0.1%，体积
    约为旧 PNG 的 1/3、编码耗时约为 1/14（见 docs/dev/webp-format-benchmark.md
    的 3.2.1）。旧版本同页的 ``.png`` 会在写成功后删掉，避免下游把同一页
    的两个后缀当成两页。

    args["_effects"] = [
        {"file": 源页图, "label": 输出文件名(无扩展名),
         "effect": {"boxes": [[x1,y1,x2,y2]], "border": "0"}},
        …
    ]
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = dict(config["args"])
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        effects = args.pop("_effects", None) or []
        out_dir = Path(args["output"])
        if args.get("clean") and out_dir.exists():
            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)

        from PIL import Image
        from PySide6.QtGui import QImage, QImageReader

        from desktop.services.print_plan import plan_submit_job
        from desktop.stages.rembg_stage import _qimage_rgb_array
        from desktop.workers.preview_worker import compose_region_output
        from utils.file_utils import replace_with_retry

        # ---- 阶段一（主线程）：预计算每页的输出文件名 --------------------
        jobs: list[dict] = []
        for spec in effects:
            reader = QImageReader(str(spec["file"]))
            size = reader.size()
            px = None if size.isEmpty() else (size.width(), size.height())
            jobs.append(plan_submit_job(spec, px))
        total = sum(len(j["names"]) for j in jobs)  # 输出**张数**
        # 占位条目与真框走**同一条裁剪路径**（都从原图截对应区域），
        # ``placeholder`` 标记只用于日志/统计区分。
        placeholder_total = sum(1 for j in jobs if j.get("placeholder"))

        def _save(image, dst: Path) -> None:
            """JPEG q95 落盘（4:4:4）；原子写避免下游读到半截图。"""
            tmp = dst.with_name(dst.name + ".tmp")
            Image.fromarray(_qimage_rgb_array(image), "RGB").save(
                tmp, "JPEG",
                quality=SUBMIT_JPEG_QUALITY,
                subsampling=0,
                dpi=(300, 300),
            )
            replace_with_retry(tmp, dst)

        # ---- 阶段二（线程池）：并行 读图 → 逐框裁剪合成 → 写 JPG ----------
        # ⚠️ emit 只在主线程调（worker 线程往 stdout 写 JSON 行会交错）。
        def _process(job: dict):
            saved_names: list[str] = []
            errors: list[str] = []
            if not job["names"]:
                return saved_names, [f"无法读取图片: {job['file']}"]
            image = QImage(job["file"])
            if image.isNull():
                return saved_names, [f"无法读取图片: {job['file']}"]
            if job["compose"]:
                outputs = compose_region_output(
                    image, job["boxes"], job["border"],
                )
            else:
                outputs = [image]
            names = job["names"]
            if len(outputs) != len(names):
                # 几何结果与预计算不一致（理论上不可能）：按张数现算，
                # 命名规则不变，避免静默丢页
                names = (
                    [f"{job['label']}.jpg"]
                    if len(outputs) == 1
                    else [f"{job['label']}-{i + 1}.jpg"
                          for i in range(len(outputs))]
                )
            for out, name in zip(outputs, names):
                dst = out_dir / name
                try:
                    _save(out, dst)
                except Exception as exc:  # noqa: BLE001 - 单张失败不许拖垮整批
                    errors.append(f"写入失败: {dst}（{exc}）")
                    continue
                # 旧版本产物是 .png：同页两个后缀会被下游当成两页（重复裁图）。
                dst.with_suffix(".png").unlink(missing_ok=True)
                saved_names.append(name)
            return saved_names, errors

        done = 0
        saved = 0
        executor = ThreadPoolExecutor(max_workers=SUBMIT_WORKERS)
        try:
            future_jobs = {
                executor.submit(_process, job): job for job in jobs
            }
            for future in as_completed(future_jobs):
                job = future_jobs[future]
                saved_names, errors = future.result()
                saved += len(saved_names)
                done += len(saved_names) + len(errors)
                emit({"type": "progress", **context, "done": done, "total": total})
                emit({
                    "type": "log", **context,
                    "message": f"提交处理 {done}/{total}：{job['label']}"
                               + ("（原图占位）" if job.get("placeholder") else "")
                               + " → "
                               + ("、".join(saved_names) if saved_names else "无输出"),
                })
                for message in errors:
                    emit({"type": "log", **context, "message": message})
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        emit({"type": "progress", **context, "done": total, "total": total})
        emit(
            {"type": "log", **context,
             "message": (
                 f"检测结果已提交（按文本框裁图 {saved - placeholder_total} 张"
                 + (f"，原图占位 {placeholder_total} 张" if placeholder_total else "")
                 + f"）：{out_dir}"
             )}
        )
        if not saved:
            emit(
                {"type": "error", **context,
                 "message": "没有生成任何图片，请先执行「检测文本框」。"}
            )
            return 1
        emit(
            {
                "type": "finished", **context,
                "done": saved, "total": total,
                "result": None, "output": str(out_dir),
            }
        )
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
