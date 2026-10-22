# -*- coding: utf-8 -*-
"""去底色参数调整时的**单页实时预览**（只显示，不写正式产物）。

用户口径：改 offset/type/印章、翻页时当前页要立刻看到效果，而不是必须点
「执行去底色」全量跑一遍。

边界（2026-10-22 单步化之后）：

- **只看当前页**、只写系统临时目录 ``guji_live_preview/<task_id>/``；
  ``stages/rembg`` 是「执行去底色」的正式成品，实时预览**绝不**碰它。
- 参数与最近一次成功执行一致时，直接显示正式成品，不重复计算。
- 计算入口与 CLI / 正式阶段同源：``utils.rembg_page``。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def live_dir(task_id: str) -> Path:
    """该任务的实时预览暂存目录（系统临时目录下，按 task_id 隔离）。"""
    return Path(tempfile.gettempdir()) / "guji_live_preview" / str(task_id)


def reset(task_id: str) -> None:
    """清空该任务的实时暂存（参数回到正式成果、或切换任务时调用）。"""
    target = live_dir(task_id)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def render_page(image_path: str, args: dict, out_dir: str | Path) -> str:
    """对单页执行整图去底色并写入 ``out_dir``，返回结果文件路径。

    PNG 用 ``compress_level=1``：这是临时预览，编码速度比压缩率重要；
    正式产物走 ``desktop.stages.rembg_stage``（透明底 + level=6）。
    """
    from PIL import Image

    import utils
    from functions.rembg import load_rgb_and_gray

    out_path_dir = Path(out_dir)
    out_path_dir.mkdir(parents=True, exist_ok=True)

    img_arr, gray_arr = load_rgb_and_gray(Path(image_path))
    img_type = int(args.get("type", 1))
    final_arr = utils.rembg_page(
        img_arr,
        gray_arr,
        offset=int(args.get("offset", 0)),
        img_type=img_type,
        enable_seal=bool(args.get("seal", False)),
        seal_color=bool(args.get("sealcolor", False)),
        seal_area=int(args.get("sealarea", 80)),
        seal_min_sat=int(args.get("sealmin_sat", 50)),
    )

    out_path = out_path_dir / f"{Path(image_path).stem}.png"
    if final_arr.ndim == 3:
        Image.fromarray(final_arr, "RGB").save(
            out_path, format="PNG", compress_level=1
        )
    else:
        out_img = Image.fromarray(final_arr, "L")
        if img_type == 2:
            out_img = out_img.convert("1")  # 1bit 单色位图
        out_img.save(out_path, format="PNG", compress_level=1)
    return str(out_path)
