# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-
from __future__ import annotations

NAME = "image_editor_multi"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·双图编辑（拼版编辑整图）"


def _make_image(width: int, height: int, color: str):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def _spread_dialog():
    """双图弹窗：左图 200×100 @ (0,0)，右图 150×80 @ (250,10)。均为不透明
    纯色图（入口收紧不触发，trim 恒 (0,0)，断言里不含收紧变量）。"""
    from desktop.components.viewers.image_editor import ImageEditorDialog

    left = _make_image(200, 100, "#ffffff")
    right = _make_image(150, 80, "#dddddd")
    items = [
        {"image": left, "file": "_left.png", "rect": (0, 0, 200, 100)},
        {"image": right, "file": "_right.png", "rect": (250, 10, 150, 80)},
    ]
    dialog = ImageEditorDialog(None, left, save_back=True)
    dialog.configure_multiple_images(items)
    return dialog, left, right


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
