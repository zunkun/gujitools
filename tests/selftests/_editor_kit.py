# -*- coding: utf-8 -*-
"""图片编辑器自测的共用小助手（**不是**用例模块，运行器按 ``_`` 前缀跳过）。

2026-10-14 拆分：``image_editor.py`` 原本 2793 行、一个巨型 ``run()``，
按主题拆成 8 个模块后，下面这些纯助手被多个模块共用，收在这里一份。
以前它们是 ``image_editor.py`` 的模块级函数，别的模块各自复制一份
（``image_editor_multi.py`` 至今仍有一份自己的 ``_make_image``）。
"""

from __future__ import annotations


def make_image(width: int, height: int):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    return image


def is_dark(color) -> bool:
    """足够深的像素（文字/黑笔刷落点，抗锯齿边缘不算）。"""
    return (color.red() < 100 and color.green() < 100
            and color.blue() < 100)


def plane_diff(a, b) -> float:
    """两张**同尺寸**图的平均通道差（隔点采样，够用又便宜）。

    用于"画布预览 == 烘焙结果"的像素级对照：同一条数学算出来的两张图，
    差别只该来自抗锯齿（实测 1–2），差到几十就是"内容落在别处/被裁掉"。
    """
    if a.size() != b.size():
        return 999.0
    total = 0
    count = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += (abs(ca.red() - cb.red()) + abs(ca.green() - cb.green())
                      + abs(ca.blue() - cb.blue()))
            count += 3
    return total / max(1, count)


def canvas_img(canvas):
    """取画布当前图（``canvas.image`` 声明为可空，但用例都在有图态访问）。"""
    img = canvas.image
    assert img is not None  # 编辑过程中画布必有图
    return img


def history_labels(dialog) -> str:
    """右侧「编辑历史」每一格的文案，拼成一行放进断言信息里。

    ⚠️ **不要写成 f-string 里的多行推导式**（``f"{[x.text() for x in
    lst\n ...]}"``）：替换字段里出现物理换行是 **Python 3.12+（PEP 701）
    才有的语法**，仓库跑 conda py310 ⇒ 那会让**整个自测模块 import 失败**
    （``gui_selftest.discover_modules`` 直接崩，整个套件都跑不了）。
    2026-10-08 那次布局调整就是这么把原 ``image_editor.py`` 写坏的，
    到 2026-10-10 才发现——搬进来的每份副本都带着这条警告。
    """
    return str([dialog.history_list.item(i).text()
                for i in range(dialog.history_list.count())])


def mouse_event(kind: str, view_pos, button=None):
    """合成一个画布用的 ``QMouseEvent``（视口坐标）。

    ``kind`` ∈ ``press`` / ``move`` / ``release``；``move`` 时按下的键
    必须是 NoButton（Qt 语义：拖动过程中 reports buttons 不含 press 键
    的写法在部分版本会被当成悬停）。不传 ``button`` 时默认左键。
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent

    types = {
        "press": QEvent.Type.MouseButtonPress,
        "move": QEvent.Type.MouseMove,
        "release": QEvent.Type.MouseButtonRelease,
    }
    button = Qt.MouseButton.LeftButton if button is None else button
    buttons = (Qt.MouseButton.NoButton if kind == "move" else button)
    return QMouseEvent(types[kind], view_pos, button, buttons,
                       Qt.KeyboardModifier.NoModifier)