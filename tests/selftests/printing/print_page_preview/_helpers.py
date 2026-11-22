# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

import time

NAME = "print_page_preview"
DEPENDS: list[str] = []
TITLE = "第四步打印效果预览"


def _tmp_png(path, w: int, h: int):
    """造一张纯白测试图（QPainter 随手画两笔，便于肉眼区分）。"""
    from PySide6.QtGui import QColor, QImage, QPainter

    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#f2f2f2"))
    painter = QPainter(img)
    painter.setPen(QColor("#333333"))
    painter.drawRect(10, 10, w - 20, h - 20)
    painter.end()
    img.save(str(path))
    return path


def _wait_new_image(widget, app, previous, timeout: float = 20.0):
    """等效果预览加载完成，返回新的 QPixmap（previous 用于区分旧图）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        pm = widget.view._pixmap
        if pm is not None and (
            previous is None or (pm.width(), pm.height()) != previous
        ):
            app.processEvents()
            return pm
        time.sleep(0.05)
    return widget.view._pixmap




def _hint_of(widget) -> str:
    """触发一次空选删除，捕获 hint 文案。

    ⚠️ 先清掉选中：删掉当前行后 Qt 会把下一行自动设成当前（单选模式下
    当前=选中），不清的话第二次 ``remove_selected`` 会真删下一张。
    """
    messages = []
    widget.hint.connect(messages.append)
    widget.strip.clearSelection()
    widget.remove_selected()
    return messages[0] if messages else ""


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
