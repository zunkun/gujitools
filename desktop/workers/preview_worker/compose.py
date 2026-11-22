# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
"""效果区域合成：按 border 规则把检测框裁成多张预览图（纯 QImage 绘制）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from utils.box_geometry import build_output_layout, parse_border_mm


def region_canvas_specs(
    image_size: tuple[int, int], boxes: list, border_mm,
    dpi: int = 300,
) -> list:
    """compose_region_output 的**纯几何**部分：返回 ``[(画布尺寸, sources)]``。

    不碰位图——只依据图片**尺寸**（QImageReader 读文件头即可拿到）就能
    算出每张输出画布的大小与贴图来源。第三步提交据此**预先算好输出
    文件名**（张数 × 名称），再并行处理各页；规则仍然只有这一份。

    **每个检测框各自一张输出画布**（框 + border）；无框时整页原图一张。
    """
    W, H = image_size
    present = [list(b) for b in boxes if b]
    if not present:  # 无检测框：整页原图
        return [((W, H), [])]
    padding = parse_border_mm(border_mm, dpi)
    layout = build_output_layout(
        boxes=present,
        border_padding=padding,
        image_size=(W, H),
    )
    return [(canvas_spec.size, canvas_spec.sources) for canvas_spec in layout.canvases]


def compose_region_output(image: QImage, boxes: list, border_mm,
                          dpi: int = 300) -> list:
    """按 border 规则，把**每个检测框**裁成一张"效果预览图"。

    **几何规则来自 utils.box_geometry**（与 functions/text_region.py 的 CLI
    输出共用同一份实现），本函数只负责用 QImage 把布局画出来——这样规则
    不会因数像素后端不同而被复制成两份。几何部分见 `region_canvas_specs`。
    """
    W, H = image.width(), image.height()
    specs = region_canvas_specs((W, H), boxes, border_mm, dpi)
    result = []
    for size, sources in specs:
        canvas = QImage(max(size[0], 1), max(size[1], 1), QImage.Format.Format_RGB32)
        canvas.fill(Qt.GlobalColor.white)
        for source, ox, oy in sources:
            x1, y1, x2, y2 = source
            sx1, sy1 = max(0, x1), max(0, y1)
            sx2, sy2 = min(W, x2), min(H, y2)
            if sx2 > sx1 and sy2 > sy1:
                painter = QPainter(canvas)
                painter.drawImage(
                    ox + sx1 - x1,
                    oy + sy1 - y1,
                    image,
                    sx1,
                    sy1,
                    sx2 - sx1,
                    sy2 - sy1,
                )
                painter.end()
        result.append(canvas)
    return result


def compose_outputs_horizontal(outputs: list, gap: int = 12) -> QImage:
    """多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。"""
    if not outputs:
        return QImage()
    if len(outputs) == 1:
        return outputs[0]
    height = max(c.height() for c in outputs)
    total_w = sum(c.width() for c in outputs) + gap * (len(outputs) - 1)
    out = QImage(total_w, height, QImage.Format.Format_RGB32)
    out.fill(Qt.GlobalColor.darkGray)
    painter = QPainter(out)
    offset_x = 0
    for crop in outputs:
        painter.drawImage(offset_x, (height - crop.height()) // 2, crop)
        offset_x += crop.width() + gap
    painter.end()
    return out
