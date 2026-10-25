# -*- coding: utf-8 -*-
"""rembg 阶段执行器：**一步**完成整图去底色并直接落成品图。

用户 2026-10-22 口径：

> 「生成预览」改成「执行去底色」，直接去底色到 rembg，不再需要预览了，
> 图片直接全局 otsu……输入什么图片尺寸，输出就什么图片尺寸。

所以这里**只有一个动作**：读输入图 → ``utils.rembg_page``（所选阈值算法，
默认全局 Otsu）→ 白底转透明的 PNG 写进 ``stages/rembg[~节点]``。没有预览目录、
没有提交动作，也不按检测框裁剪（裁剪已在第二步「提交本次任务」完成）。

每页实际使用的算法会写进任务根目录的 ``rembg_methods[~节点].json``
（``{页名: 算法 key}``），供事后核对"这张图是按哪种方法去底色的"。

产物一律是**白底透明**的 PNG（规则与编码形态的唯一实现在
``utils/transparent_png.py``）：第四步 PDF 排版依赖透明底叠在纸上。
"""

from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import utils
from core.args import machine_worker_budget
from utils.rembg_algorithms import (
    ALGORITHMS,
    LOCAL_ALGORITHM_KEYS,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    get_algorithm,
)
from desktop.stages.events import emit
from desktop.utils.files import THUMBNAIL_EDGE
from utils.file_utils import write_bytes_atomic

#: 并行 worker 数。瓶颈在 **PNG 编码**（与旧提交阶段同一份实测：单张
#: 6000×5475 约 0.65s，占整页 85%；4 线程实测 3.47×）。每个 worker 同时持有
#: 整页位图 + 输出数组，峰值内存随线程数线性涨。
#: ⚠️ 上限与 ``core.args.machine_worker_budget()`` 保持一致；环境变量是用户的
#: 显式选择，可越过预算但受绝对封顶 8 约束。
REMBG_WORKERS = max(
    1,
    min(
        8,
        int(os.environ.get("GUJI_REMBG_WORKERS") or 0)
        or min(8, machine_worker_budget(), os.cpu_count() or 1),
    ),
)


def _qimage_rgb_array(image):
    """QImage → ``(H, W, 3)`` 的 RGB 数组（``uint8``，独立于 QImage 生命周期）。

    ⚠️ 三个坑，逐条都是踩过的：
    1. ``constBits()`` 的内存布局是 **B,G,R,A**（Format_RGB32），直接当 RGB 用
       会让整页偏色——必须反序取通道。
    2. **必须复制一份出来**（``np.ascontiguousarray``）。numpy 的 ``frombuffer``
       只是**引用** Qt 的缓冲区，而内存归 QImage 对象所有：一旦那个 QImage 被
       回收，数组就变成悬垂指针（产物里混进随机彩色像素，重则段错误）。
    3. ``convertToFormat`` 在格式已一致时会返回浅拷贝；这里只在格式不同时调用。

    除去底色的透明 PNG 编码外，检测提交阶段的 JPEG q95 裁图也用它——两处
    都需要「Qt 位图 → RGB 数组」这同一个安全转换。
    """
    import numpy as np
    from PySide6.QtGui import QImage

    if image.format() != QImage.Format.Format_RGB32:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    height, width = image.height(), image.width()
    stride = image.bytesPerLine()
    buffer = np.frombuffer(image.constBits(), np.uint8)
    rows = buffer[: stride * height].reshape(height, stride)
    # RGB32 每行 32 位对齐，stride 恒等于 width*4（这里仍取 width*4 切一刀，
    # 不依赖该前提）；切片后恒为连续视图，reshape 不会悄悄复制。
    pixels = rows[:, : width * 4].reshape(height, width, 4)
    return np.ascontiguousarray(pixels[:, :, 2::-1])


def _rembg_params(args: dict) -> dict:
    """面板/CLI 参数 → ``utils.rembg_page`` 的关键字参数。

    ⚠️ ``algorithm`` 是**全量执行的默认算法**：逐张表里单独记过的页优先用它
    自己的值（见 ``run_rembg_stage`` 的 ``algorithms``）。
    """
    return {
        "algorithm": str(args.get("algorithm", "otsu")),
        "offset": int(args.get("offset", 0)),
        "window": int(args.get("window", 25)),
        "k": float(args.get("k", 0.2)),
        "img_type": int(args.get("type", 1)),
        "enable_seal": bool(args.get("seal", False)),
        "seal_color": bool(args.get("sealcolor", False)),
        "seal_area": int(args.get("sealarea", 80)),
        "seal_min_sat": int(args.get("sealmin_sat", 50)),
    }


def _write_methods(out_dir: Path, methods: dict[str, str]) -> None:
    """把「每页实际使用的算法」写进任务根目录的侧车文件（保留未重跑页的记录）。

    失败静默：这是可追溯性记录，绝不能因为写不了就判定整批失败。
    """
    try:
        from desktop.steps.ports import rembg_methods_path
        from desktop.store.json_io import read_json, write_json

        path = rembg_methods_path(out_dir)
        if path is None:
            return
        existing = read_json(path, {})
        if not isinstance(existing, dict):
            existing = {}
        present = {item.stem for item in out_dir.glob("*.png")}
        merged = {
            str(key): str(value)
            for key, value in existing.items()
            if str(key) in present
        }
        merged.update(methods)
        if merged:
            write_json(path, merged)
    except Exception:  # noqa: BLE001 - 记录不是主流程
        pass


def _rgb_of(final_arr):
    """去底结果 → ``(H, W, 3)`` RGB 数组（透明 PNG 编码的输入形状）。"""
    import numpy as np

    if final_arr.ndim == 3:
        return final_arr[:, :, :3]
    return np.repeat(final_arr[:, :, None], 3, axis=2)


def _save_thumb(rgb, name: str, thumb_dir: Path) -> None:
    """顺手生成第四步缩略条用的小图（256px JPEG，白底）。

    失败**静默跳过**：缩略图是纯加速件，查看器对缺失的页回落原图解码，
    绝不能因为缩略图写失败把成功的页报成失败。原子写避免截断的缩略图被
    mtime 新鲜度判据永久当成有效缓存。
    """
    from PIL import Image

    try:
        small = Image.fromarray(rgb, "RGB")
        small.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
        buf = BytesIO()
        small.save(buf, format="JPEG", quality=80)
        write_bytes_atomic(thumb_dir / f"{name}.jpg", buf.getvalue())
    except Exception:  # noqa: BLE001 - 加速件不许拖垮主流程
        pass


def run_rembg_stage(config: dict) -> int:
    """整图去底色：输入目录里的每张图 → ``stages/rembg[~节点]/<同页名>.png``。

    args 约定：

    - ``input``：输入图片目录（或单张图片）；
    - ``_outpath``：精确输出目录（调用方给节点作用域后的 ``stages/rembg``）；
    - ``clean``：开始前清空输出目录；
    - ``algorithm/window/k``：去底色算法与局部参数（``algorithm`` = 全量默认值）；
    - ``algorithms``：逐张算法覆盖表 ``{页名: 算法 key}``（用户单独调过的页）；
    - ``offset/type/seal/sealcolor/sealarea/sealmin_sat``：其他去底色参数。

    ``page_done`` 事件带 ``source``（输入图）与 ``output``（成品图），GUI 据此
    边跑边把该页刷成去底色结果。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = dict(config["args"])
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        input_path = Path(args["input"])
        out_text = args.get("_outpath") or args.get("output")
        if not out_text:
            raise ValueError("去底色没有指定输出目录")
        out_dir = Path(out_text)
        files = utils.collect_image_files(input_path, input_path.is_file())
        if not files:
            raise FileNotFoundError(
                f"未在 {input_path} 找到任何图片"
                "（若图片在子目录里，请指向该子目录）"
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.get("clean") and out_dir.exists():
            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()

        # 第四步缩略图缓存（与 ``store.rembg_thumbnails_dir`` 同一布局：
        # ``<task>/thumbnails/print[~<节点>]``）。worker 拿不到 store，按任务
        # 目录布局 + **产物目录名里的节点后缀**推导——同一步骤多个节点时各自的
        # 缩略图不许互相覆盖。本次是整目录重建，旧缩略图一并作废。
        from desktop.steps.ports import node_scope_from_output_dir

        thumb_dir = (
            out_dir.parent.parent
            / "thumbnails"
            / f"print{node_scope_from_output_dir(out_dir.name)}"
        )
        shutil.rmtree(thumb_dir, ignore_errors=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        params = _rembg_params(args)
        #: 逐张图片的 offset 覆盖（黑名单法：只有用户单独调过的图才有条目）。
        #: ⚠️ 只要调用方传了这张表（GUI 总会传，哪怕是空表），**没记录的图
        #:    就按 0 处理**——offset 是逐张参数，不能把当前页的值扩散给全批。
        raw_offsets = args.get("offsets")
        offsets = {
            str(key): int(value)
            for key, value in (raw_offsets or {}).items()
        }
        #: 逐张算法覆盖（白名单法：只有用户单独改过算法的页才有条目）。
        #: ⚠️ 没记录的页用**面板上的默认算法**（``params["algorithm"]``），
        #:    与 offset 的"没记录 = 0"不同——算法没有"0 表示未设置"的哨兵。
        algorithms = {
            str(key): str(value)
            for key, value in (args.get("algorithms") or {}).items()
        }
        total = len(files)
        # 读图口径与 CLI 共用一份（函数内导入：本模块在 worker 子进程里跑，
        # 启动路径不需要 numpy/PIL）。
        from functions.rembg import load_rgb_and_gray
        from desktop.services.rembg_groups import group_files

        def _algorithm_for(stem: str) -> str:
            """某张图最终用哪种算法（逐张覆盖优先，否则面板默认）。"""
            return str(algorithms.get(stem, params["algorithm"]))

        def _offset_for(stem: str) -> int:
            """某张图最终用哪个阈值偏移（逐张覆盖优先，否则面板默认）。"""
            if raw_offsets is None:
                return int(params["offset"])
            return int(offsets.get(stem, 0))

        def _shareable(members) -> bool:
            """这一组能否共享一个**全局**阈值。

            规则（用户 2026-10-25）：只有 YOLO **左右双栏都真实存在**时才合并；
            占位图不参与合并（它自己单独算阈值），所以只看非占位成员——必须是
            **同一个全局算法**。局部算法逐像素定阈值，不能跨图共享；算法不一致
            也不同步硬凑。
            """
            if len(members) < 2:
                return False
            real = [m for m in members if not m.placeholder]
            if not real:
                return False
            keys = {_algorithm_for(m.path.stem) for m in real}
            return len(keys) == 1 and next(iter(keys)) not in LOCAL_ALGORITHM_KEYS

        def _process_group(members) -> list[tuple[Path, str, str, str]]:
            """一组（通常同页 l/r 两张）→ 每张的结果列表。

            全局算法：用**非占位成员**的灰度合并算一个阈值，再应用到真实成员。
            **占位图不套用组阈值**（用户 2026-10-25：占位图自己单独计算阈值）；
            局部算法 / 组内算法不一致：也各算各的。
            """
            loaded = []
            results: list[tuple[Path, str, str, str]] = []
            for member in members:
                algorithm = _algorithm_for(member.path.stem)
                # 过滤异常小文件（下载不完整或占位符）
                if not utils.is_valid_image_size(member.path):
                    results.append((member.path, "", "file too small", algorithm))
                    continue
                try:
                    img_arr, gray_arr = load_rgb_and_gray(member.path)
                except Exception as exc:  # noqa: BLE001 - 单张失败不许拖垮整批
                    results.append((
                        member.path, "",
                        f"{member.path.name} 读取失败：{exc}", algorithm,
                    ))
                    continue
                loaded.append((member, img_arr, gray_arr))

            shared_algorithm = None
            shared_threshold = None
            if _shareable(members):
                real = [(m, gray) for m, _img, gray in loaded if not m.placeholder]
                keys = {_algorithm_for(m.path.stem) for m, _gray in real}
                if len(keys) == 1:
                    shared_algorithm = next(iter(keys))
                    try:
                        shared_threshold = get_algorithm(
                            shared_algorithm
                        ).shared_threshold([gray for _m, gray in real])
                    except Exception:  # noqa: BLE001 - 合并失败退回逐图
                        shared_threshold = None

            while loaded:
                member, img_arr, gray_arr = loaded.pop(0)
                stem = member.path.stem
                algorithm = _algorithm_for(stem)
                offset = _offset_for(stem)
                threshold = None
                if (
                    shared_threshold is not None
                    and not member.placeholder
                    and shared_algorithm == algorithm
                    and algorithm not in LOCAL_ALGORITHM_KEYS
                ):
                    # 共享的是**基础阈值**；offset 仍是逐张微调。
                    threshold = min(
                        max(int(shared_threshold) + offset, THRESHOLD_MIN),
                        THRESHOLD_MAX,
                    )
                page_params = dict(params)
                page_params["algorithm"] = algorithm
                page_params["offset"] = offset
                page_params["threshold"] = threshold
                name = f"{stem}.png"
                dst = out_dir / name
                try:
                    final_arr = utils.rembg_page(img_arr, gray_arr, **page_params)
                    rgb = _rgb_of(final_arr)
                    utils.save_white_as_transparent(rgb, dst)
                    _save_thumb(rgb, stem, thumb_dir)
                    results.append((member.path, name, "", algorithm))
                except Exception as exc:  # noqa: BLE001 - 单张失败不许拖垮整批
                    results.append((
                        member.path, "",
                        f"{member.path.name} 处理失败：{exc}", algorithm,
                    ))
            return results

        # 同页左右裁图合成一组（分组依据是上游 detect 的 boxes.json 提交计划）。
        # 不能共享阈值的组拆回逐张任务，保持原有并发度。
        groups = group_files(files, args.get("_boxes_path"))
        job_groups: list[list] = []
        for group in groups:
            if _shareable(group):
                job_groups.append(group)
            else:
                job_groups.extend([[member] for member in group])

        done = 0
        saved = 0
        errors: list[str] = []
        #: 每页实际使用的算法（写进任务根目录的 rembg_methods 侧车）。
        methods: dict[str, str] = {}
        # ⚠️ 并发时把 cv2 内部线程压成 1（与 functions/base 同一理由）：外层
        #    已经 N 路并行，再叠 cv2 的满核并行只会超订阅、互相抢缓存。
        import cv2

        prev_threads = cv2.getNumThreads()
        if REMBG_WORKERS > 1:
            cv2.setNumThreads(1)
        labels = {item.key: item.label for item in ALGORITHMS}
        executor = ThreadPoolExecutor(max_workers=REMBG_WORKERS)
        try:
            jobs = {
                executor.submit(_process_group, group): group
                for group in job_groups
            }
            for future in as_completed(jobs):
                group = jobs[future]
                try:
                    results = future.result()
                except Exception as exc:  # noqa: BLE001 - 单组异常不许拖垮整批
                    results = [
                        (m.path, "", f"{m.path.name} 处理失败：{exc}",
                         _algorithm_for(m.path.stem))
                        for m in group
                    ]
                for source, name, error, algorithm in results:
                    done += 1
                    status = "success" if name else "error"
                    if name:
                        saved += 1
                        methods[source.stem] = algorithm
                    elif error:
                        errors.append(error)
                    emit({
                        "type": "page_done", **context,
                        "source": str(source), "file": source.name,
                        "status": status,
                        "algorithm": algorithm,
                        "output": str(out_dir / name) if name else "",
                    })
                    emit({"type": "progress", **context,
                          "done": done, "total": total})
                    emit({
                        "type": "log", **context,
                        "message": f"去底色 {done}/{total}：{source.name} "
                                   f"[{labels.get(algorithm, algorithm)}] → "
                                   + (name or "无输出"),
                    })
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            cv2.setNumThreads(prev_threads)
        for message in errors:
            emit({"type": "log", **context, "message": message})
        # 每页用了哪种算法：任务根目录的侧车文件（执行记录的一部分）。
        _write_methods(out_dir, methods)
        emit({"type": "progress", **context, "done": total, "total": total})
        emit(
            {"type": "log", **context,
             "message": f"去底色完成（{saved} 张，白底已转透明）：{out_dir}"}
        )
        if not saved:
            emit({"type": "error", **context, "message": "没有生成任何图片。"})
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
