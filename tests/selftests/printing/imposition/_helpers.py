# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

NAME = "imposition"
DEPENDS: list[str] = []
TITLE = "图片拼版"

import shutil
import tempfile
from pathlib import Path
from typing import cast

from tests.selftests._context import make_pdf, ok, pump

RED = (220, 40, 40)
GREEN = (30, 160, 60)
BLUE = (40, 80, 220)
YELLOW = (230, 190, 30)

#: 选中框/手柄的颜色（与 imposition_canvas.FRAME_COLOR 一致），像素判据用
FRAME_RGB = (0x0E, 0x7C, 0x8B)
#: 红色对齐线（与 imposition_canvas.SPINE_COLOR 一致），像素判据用
SPINE_RGB = (0xE0, 0x20, 0x20)
#: 灰色成品截图范围框（与 imposition_canvas.CROP_COLOR 一致），像素判据用
CROP_RGB = (0x5F, 0x63, 0x68)


def _mk(path: Path, color, size=(400, 600)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


#: 编辑结果用的工作色：挑两个夹具色系里没有的颜色，像素断言不会被"本来就
#: 是这个颜色"糊弄过去
EDIT_ITEM_COLOR = (12, 200, 180)
EDIT_SPREAD_COLOR = (200, 30, 200)


def _solid_qimage(color, width: int = 64, height: int = 48):
    """纯色 QImage（编辑结果的替身）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(*color))
    return image


def _qimage_pixel(path: Path, x: int, y: int):
    """读文件里一个像素的 (r, g, b)；读不到返回 None。"""
    from PySide6.QtGui import QImage

    image = QImage(str(path))
    if image.isNull():
        return None
    c = image.pixelColor(x, y)
    return (c.red(), c.green(), c.blue())


def _names(paths) -> list[str]:
    return [Path(p).name for p in paths]


def _count_near(image, rgb, tol: int = 28, step: int = 2) -> int:
    """数一数画面上有多少像素接近 ``rgb``（隔点取样，够用且快）。"""
    total = 0
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            color = image.pixelColor(x, y)
            if (
                abs(color.red() - rgb[0]) <= tol
                and abs(color.green() - rgb[1]) <= tol
                and abs(color.blue() - rgb[2]) <= tol
            ):
                total += 1
    return total


def _count_non_white(image, tol: int = 12, step: int = 2) -> int:
    """数一数有多少像素不接近纯白（确认缩略图**真的画上了内容**）。"""
    total = 0
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            color = image.pixelColor(x, y)
            if (
                color.red() < 255 - tol
                or color.green() < 255 - tol
                or color.blue() < 255 - tol
            ):
                total += 1
    return total


def _px_near(image, x: int, y: int, rgb, tol: int = 24) -> bool:
    """图上 (x, y) 一个像素是否接近 ``rgb``（合成缩略图的左右半判色用）。"""
    if image is None or image.isNull():
        return False
    if not (0 <= x < image.width() and 0 <= y < image.height()):
        return False
    c = image.pixelColor(x, y)
    return (
        abs(c.red() - rgb[0]) <= tol
        and abs(c.green() - rgb[1]) <= tol
        and abs(c.blue() - rgb[2]) <= tol
    )


def _bar_of(page, step: str) -> int:
    """查某一步在步骤条里的格序；图里没有这一格就直接断（别静默切别的格）。"""
    index = page.bar_index_of_step(step)
    assert index is not None, f"流程图里没有「{step}」这一格"
    return index


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
