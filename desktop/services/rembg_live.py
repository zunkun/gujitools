# -*- coding: utf-8 -*-
"""去底色参数实时调整的**单页重算**：直接覆盖正式成品。

用户口径（2026-10-22，任务 0014 报障）：

> 「在去底色步骤设置了 offset，没有能够传给下一步……图片任务目录下面要替换掉
>  rembg 下的图片」

所以这里**没有**"临时预览目录"：改 offset/type/印章或翻页时，当前页立刻按键入
参数重算，结果**覆盖** ``stages/rembg[~节点]/<页名>.png``（透明底 PNG，与
「执行去底色」的产物同规格），并顺带刷新第四步缩略图——不落进任务目录的话，
下一步「图片拼版 / PDF排版」拿到的还是旧图。

计算口径与正式阶段同源（``utils.rembg_page`` + ``utils.save_white_as_transparent``）。
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from desktop.utils.files import THUMBNAIL_EDGE
from utils.file_utils import write_bytes_atomic


def _rgb_of(final_arr):
    """去底结果 → ``(H, W, 3)`` RGB 数组（透明 PNG 编码的输入形状）。"""
    import numpy as np

    if final_arr.ndim == 3:
        return final_arr[:, :, :3]
    return np.repeat(final_arr[:, :, None], 3, axis=2)


def _save_thumb(rgb, name: str, thumb_dir: Path) -> None:
    """顺手刷新第四步缩略条用的小图（256px JPEG，白底）。

    与 ``desktop.stages.rembg_stage._save_thumb`` 同一规格（第四步的
    ``_print_thumb_provider`` 按 ``mtime 不旧于成品图`` 判有效，不刷新的话它
    会回落整幅解码）。失败**静默跳过**：缩略图是纯加速件。
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


def render_page(image_path: str, args: dict, out_dir: str | Path,
                thumb_dir: str | Path | None = None) -> str:
    """单页整图去底色 → **覆盖**正式成品（并刷新第四步缩略图），返回成品路径。

    ⚠️ 覆盖走「同目录 ``.part`` + ``os.replace``」：这份成品随时会被第四步查看器
    或拼版合成读到，直接 ``Image.save`` 会让人读到半截 PNG。``.part`` 后缀不在
    ``IMAGE_SUFFIXES`` 里，也不会被当成一页。
    """
    import utils
    from functions.rembg import load_rgb_and_gray

    out_path_dir = Path(out_dir)
    out_path_dir.mkdir(parents=True, exist_ok=True)

    img_arr, gray_arr = load_rgb_and_gray(Path(image_path))
    final_arr = utils.rembg_page(
        img_arr,
        gray_arr,
        offset=int(args.get("offset", 0)),
        img_type=int(args.get("type", 1)),
        enable_seal=bool(args.get("seal", False)),
        seal_color=bool(args.get("sealcolor", False)),
        seal_area=int(args.get("sealarea", 80)),
        seal_min_sat=int(args.get("sealmin_sat", 50)),
    )
    rgb = _rgb_of(final_arr)
    out_path = out_path_dir / f"{Path(image_path).stem}.png"
    part = out_path.with_name(out_path.name + ".part")
    utils.save_white_as_transparent(rgb, part)
    os.replace(part, out_path)
    if thumb_dir:
        _save_thumb(rgb, Path(image_path).stem, Path(thumb_dir))
    return str(out_path)
