# -*- coding: utf-8 -*-
"""rembg 阶段执行器：**一步**完成整图去底色并直接落成品图。

用户 2026-10-22 口径：

> 「生成预览」改成「执行去底色」，直接去底色到 rembg，不再需要预览了，
> 图片直接全局 otsu……输入什么图片尺寸，输出就什么图片尺寸。

所以这里**只有一个动作**：读输入图 → ``utils.rembg_page``（全局 Otsu）→
白底转透明的 PNG 写进 ``stages/rembg[~节点]``。没有预览目录、没有提交动作，
也不按检测框裁剪（裁剪已在第二步「提交本次任务」完成）。

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

    除去底色的透明 PNG 编码外，检测提交阶段的紧凑 PNG（``save_png_compact``）
    也用它——两处都需要「Qt 位图 → RGB 数组」这同一个安全转换。
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
    """面板/CLI 参数 → ``utils.rembg_page`` 的关键字参数。"""
    return {
        "offset": int(args.get("offset", 0)),
        "img_type": int(args.get("type", 1)),
        "enable_seal": bool(args.get("seal", False)),
        "seal_color": bool(args.get("sealcolor", False)),
        "seal_area": int(args.get("sealarea", 80)),
        "seal_min_sat": int(args.get("sealmin_sat", 50)),
    }


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
    - ``offset/type/seal/sealcolor/sealarea/sealmin_sat``：去底色参数。

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
        total = len(files)
        # 读图口径与 CLI 共用一份（函数内导入：本模块在 worker 子进程里跑，
        # 启动路径不需要 numpy/PIL）。
        from functions.rembg import load_rgb_and_gray

        def _process(image_path: Path) -> tuple[str, str]:
            """一张：全局 Otsu → 透明 PNG（+ 第四步缩略图）。"""
            name = f"{image_path.stem}.png"
            img_arr, gray_arr = load_rgb_and_gray(image_path)
            final_arr = utils.rembg_page(img_arr, gray_arr, **params)
            rgb = _rgb_of(final_arr)
            dst = out_dir / name
            try:
                utils.save_white_as_transparent(rgb, dst)
            except Exception as exc:  # noqa: BLE001 - 单张失败不许拖垮整批
                return "", f"写入失败: {dst}（{exc}）"
            _save_thumb(rgb, image_path.stem, thumb_dir)
            return name, ""

        done = 0
        saved = 0
        errors: list[str] = []
        # ⚠️ 并发时把 cv2 内部线程压成 1（与 functions/base 同一理由）：外层
        #    已经 N 路并行，再叠 cv2 的满核并行只会超订阅、互相抢缓存。
        import cv2

        prev_threads = cv2.getNumThreads()
        if REMBG_WORKERS > 1:
            cv2.setNumThreads(1)
        executor = ThreadPoolExecutor(max_workers=REMBG_WORKERS)
        try:
            jobs = {executor.submit(_process, path): path for path in files}
            for future in as_completed(jobs):
                source = jobs[future]
                try:
                    name, error = future.result()
                except Exception as exc:  # noqa: BLE001 - 单张异常不许拖垮整批
                    name, error = "", f"{source.name} 处理失败：{exc}"
                done += 1
                status = "success" if name else "error"
                if name:
                    saved += 1
                elif error:
                    errors.append(error)
                emit({
                    "type": "page_done", **context,
                    "source": str(source), "file": source.name,
                    "status": status,
                    "output": str(out_dir / name) if name else "",
                })
                emit({"type": "progress", **context, "done": done, "total": total})
                emit({
                    "type": "log", **context,
                    "message": f"去底色 {done}/{total}：{source.name} → "
                               + (name or "无输出"),
                })
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            cv2.setNumThreads(prev_threads)
        for message in errors:
            emit({"type": "log", **context, "message": message})
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
