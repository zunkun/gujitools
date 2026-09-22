# -*- coding: utf-8 -*-
"""第三步「改参数实时预览当前页」的计算与落盘。

与「生成预览」的分工
--------------------
- **「生成预览」**：全量正式产物，写 ``stages/rembgpreview``，会被「提交本次
  任务」读取。参数一变它就过期（见 ``services/submit_state`` 的 PREVIEW_STALE）。
- **本模块**：只算用户当前看着的**那一页**，落到系统临时目录，仅供预览区显示。
  **绝不碰 rembgpreview** —— 否则各页是不同参数下算出来的，提交时新旧混用，
  成品会不自洽。

计算入口统一走 ``utils.rembg_page``，与 CLI 产物逐像素同源（``functions.rembg``
用的是同一个函数）。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def live_dir(task_id: str) -> Path:
    """该任务的实时预览暂存目录（系统临时目录下，按 task_id 隔离）。"""
    return Path(tempfile.gettempdir()) / "guji_live_preview" / str(task_id)


def reset(task_id: str) -> None:
    """清空该任务的实时暂存（参数回到「生成预览」状态时调用）。"""
    target = live_dir(task_id)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def render_page(image_path: str, args: dict, out_dir: str | Path) -> str:
    """对单页执行去底色并写入 ``out_dir``，返回结果文件路径。

    ⚠️ 重依赖（numpy / PIL，以及 ``utils.image_utils`` 背后的 cv2）在这里
    **延迟导入**：GUI 主进程只有在用户真的动了参数时才付出这点加载成本，
    启动路径不受影响。

    PNG 用 ``compress_level=1``：这是**临时预览**，编码速度比压缩率重要
    （正式产物走 ``functions.rembg``，那里仍是 level=9）。
    """
    import numpy as np
    from PIL import Image

    import utils

    out_path_dir = Path(out_dir)
    out_path_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as img:
        img.load()
        # 与 functions.rembg 一致：RGBA 先合到白底，避免 alpha 干扰阈值
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img_arr = np.array(img)
        gray_arr = np.array(img.convert("L"))

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
