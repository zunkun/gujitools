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

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.args import default_workers
from core.command_spec import WHOLE_PAGE_AREA
from desktop.stages.events import ProgressStream, emit, _real_stdout


def _emit_log(message: str, context: dict | None = None) -> None:
    """发一条人读日志事件（有 context 就带上，便于 GUI 归位到任务/阶段）。"""
    payload: dict = {"type": "log"}
    if context:
        payload.update(context)
    payload["message"] = message
    emit(payload)


def run_detect(config: dict) -> int:
    """检测单张图片的左右文本框，返回像素坐标（重依赖由常驻服务承担）。"""
    image_path = config["image"]
    emit({"type": "detect_started", "image": image_path})
    try:
        # 跨层复用（登记在案，见 docs/dev/refactor-modularity.md §3.C）：
        # GUI 检测阶段必须跑与 CLI **完全相同**的检测算法，否则界面预览与
        # 命令行产物会对不上；下沉到 core 不合适（检测属业务层）。
        # 放在函数内是刻意的——避免主进程加载 YOLO。
        import utils
        from functions.detect import (  # noqa: PLC0415
            detect_page_boxes_by_path,
            format_box,
            warm_up_detect_model,
        )

        if int(config.get("area") or 1) == WHOLE_PAGE_AREA:
            # 整页模式：不加载 YOLO，整页即唯一文本框
            img = utils.imread(image_path)
            if img is None:
                raise ValueError(f"无法读取图片: {image_path}")
            h, w = img.shape[:2]
            _emit_log(f"整页模式：{Path(image_path).name} 整页作为一个文本框，未做检测")
            emit(
                {
                    "type": "boxes",
                    "image": image_path,
                    "left": [0, 0, int(w), int(h)],
                    "right": None,
                }
            )
            return 0

        # 模型准备单独一步并单独计时：不这么做的话，加载那几秒会算进第一张图，
        # 看起来像"某张图特别慢"（用户提过这点）。
        load_line, _load_seconds = warm_up_detect_model()
        _emit_log(load_line)
        started = time.perf_counter()
        left_box, right_box = detect_page_boxes_by_path(image_path)
        elapsed = time.perf_counter() - started
        _emit_log(
            f"detect {Path(image_path).name}  "
            f"左={format_box(left_box)} 右={format_box(right_box)}  "
            f"({elapsed * 1000:.0f} ms)"
        )
        emit(
            {
                "type": "boxes",
                "image": image_path,
                "left": list(left_box) if left_box else None,
                "right": list(right_box) if right_box else None,
            }
        )
        return 0
    except Exception as exc:
        _emit_log(f"检测失败: {Path(image_path).name} —— {exc}")
        emit({"type": "detect_error", "image": image_path, "message": str(exc)})
        return 1


def run_detect_stage(config: dict) -> int:
    """detect 阶段：逐图检测左右文本框并上报坐标，不切割、不生成任何文件。

    检测算法复用 `functions.detect.detect_page_boxes_by_path`（内部即 CLI crop /
    cropremove 用的同一入口），最终裁剪框由 GUI 按同一套规则
    （`utils.box_geometry.compute_final_boxes`）从检测框实时推导，用于预览标注。
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
        from functions.detect import (  # noqa: PLC0415
            detect_page_boxes_by_path,
            format_box,
            warm_up_detect_model,
        )

        files = utils.collect_image_files(Path(args.get("input", ".")), is_file=False)
        total = len(files)
        if not total:
            emit({"type": "error", **context, "message": "输入目录中没有图片"})
            return 1
        done = 0
        if int(args.get("area") or 1) == WHOLE_PAGE_AREA:
            # 整页模式：不加载 YOLO、不写 boxes.json（框由主进程按整页合成）。
            # 仍逐页报进度，界面上「本子任务」能正常走完，日志说明为何没有框。
            _emit_log("整页模式：跳过检测，整页作为一个文本框", context)
            for path in files:
                done += 1
                _emit_log(f"检测 {path.name}  整页（未做检测）", context)
                emit({"type": "progress", **context, "done": done, "total": total})
            emit(
                {
                    "type": "finished",
                    **context,
                    "done": done,
                    "total": total,
                    "result": None,
                    "output": None,
                }
            )
            return 0

        # ⚠️ 模型准备**放在计时之外**：先把它备好并单独报一次耗时，之后每一张的
        # 耗时才是纯检测耗时；否则第一张会背上 5 秒，看起来像那张图有问题。
        load_line, load_seconds = warm_up_detect_model()
        _emit_log(load_line, context)

        # 逐张并发跑：单线程一张一两百毫秒，81 页就要十几秒；并发后总时长
        # 主要取决于最慢的那张。上限与函数层共用一份（core.args.default_workers
        # 传入 command="detect" → min(8, CPU 核数, 张数)）：检测每张只在服务端
        # imread 一次，比去底/裁剪的 ~350MB/张轻得多，所以上限单独放宽到 8。
        # 具体数值只在 core/args.py 的 _COMMAND_DEFAULT_WORKER_CAP 里写一次。
        workers = max(
            1,
            int(args.get("workers") or 0) or default_workers(total, command="detect"),
        )
        if workers > 1:
            _emit_log(f"并发处理：{workers} 个线程（共 {total} 张）", context)

        started_all = time.perf_counter()
        lock = threading.Lock()
        stat = {"done": 0, "left": 0, "right": 0, "failed": 0, "cost": 0.0}

        def _detect_one(path: Path) -> None:
            """检测一张并立刻上报。**计数与上报都放在锁内**，保证
            「本张的 page_boxes → 本张的 progress」成对出现、计数不互相覆盖。"""
            started = time.perf_counter()
            failure = None
            try:
                left_box, right_box = detect_page_boxes_by_path(path)
            except Exception as exc:  # noqa: BLE001 - 单张失败不该中断整批
                left_box = right_box = None
                failure = str(exc)
            elapsed = time.perf_counter() - started
            with lock:
                stat["done"] += 1
                stat["cost"] += elapsed
                if failure:
                    stat["failed"] += 1
                    _emit_log(f"detect {path.name} 失败: {failure}", context)
                else:
                    if left_box:
                        stat["left"] += 1
                    if right_box:
                        stat["right"] += 1
                    _emit_log(
                        f"detect {path.name}  "
                        f"左={format_box(left_box)} 右={format_box(right_box)}  "
                        f"({elapsed * 1000:.0f} ms)",
                        context,
                    )
                    emit(
                        {
                            "type": "page_boxes",
                            **context,
                            "image": path.stem,
                            "left": list(left_box) if left_box else None,
                            "right": list(right_box) if right_box else None,
                        }
                    )
                emit(
                    {
                        "type": "progress",
                        **context,
                        "done": stat["done"],
                        "total": total,
                    }
                )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_detect_one, path) for path in files]
            for future in as_completed(futures):
                # 单张的异常已在 _detect_one 内兜住；这里只是等全部跑完
                future.result()

        # ---- 最后汇总：一次性给出总数、成败与耗时（含模型加载另计）----
        total_elapsed = time.perf_counter() - started_all
        counted = max(stat["done"], 1)  # 防零除（total 已保证 > 0）
        # ⚠️ 并发分支的真实进度在 `stat["done"]`，局部变量 `done` 从没自增过
        #    （2026-09-26 审计）→ 以前 finished 事件里的 done 恒为 0。GUI 现在
        #    靠 _last_progress 兜着看不出问题，但任何直接消费 finished 的旁路
        #    （e2e、将来的 UI）会拿到错误的完成数。
        done = stat["done"]
        summary = (
            f"总计用时 {total_elapsed:.1f} s（共 {total} 张："
            f"左框 {stat['left']}、右框 {stat['right']}、失败 {stat['failed']}；"
            f"{workers} 线程，单张累计 {stat['cost']:.1f} s、"
            f"平均 {stat['cost'] / counted * 1000:.0f} ms/张）"
        )
        if load_seconds > 0:
            summary += f"，模型加载另计 {load_seconds:.1f} s"
        _emit_log(summary, context)
        emit(
            {
                "type": "finished",
                **context,
                "done": done,
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
