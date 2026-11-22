# -*- coding: utf-8 -*-
"""第四步「版面编辑器」交互画布：在 A4 纸上拖拽 / 缩放 / 旋转图片。

坐标体系与 ``utils.page_layout.plan_print_page`` 算出的 ``plan.image`` 完全一致
——**页面毫米，左上原点，x 向右、y 向下**。控件把页面等比缩放到可视区，
用 ``px_per_mm`` 在「页面 mm」与「控件像素」之间换算；用户拖拽/缩放得到的
``[x_mm, y_mm, w_mm, h_mm]`` 直接写回 ``print.json`` 的 ``pages[].rect``，
出 PDF 时由 ``plan_print_page(image_rect=...)`` 原样采用——所见即所得。

交互（与 detect/rembg 的裁剪框编辑同款手感）：
- 框内拖动 → 整体移动；**四角**手柄拖动 → 缩放（勾「原比例缩放」时等比）；
  **四条边整条都是命中带**（不限边中点的小圆点）→ 拖上/下边只改高度、
  拖左/右边只改宽度（自由拉伸改变比例）；松手 emit ``rect_changed``；
- **框外上方的旋转钮**（用户 2026-11-02：与「图片拼版」同款组件）→ 左键
  拖动绕框心旋转任意角度（按住 Shift 吸附 15°）；旋转后框按外接框重算，
  角度与框一起落盘 ``pages[].rotate``；
- 框始终被夹在页面内（夹到纸边即停），不会拖出页面；
- 悬停手柄/边/旋转钮/框时显示对应光标。

**标题与页码照画**：它们是「版面」的一部分，去掉就无从判断图片挪动后会不会
压到字（曾误判为「标题页码被去除」）。绘制复用 ``preview_worker`` 的
``_draw_print_text``——与成品 PDF 同源，只是多了画布自身的居中偏移。
标题/页码的落点只取决于 ``page_margins``，**不随图片框移动**，与 PDF 一致。

图片按目标矩形绘制（未旋转时**拉伸**，与成品 ``pdf.image(img, x, y, w, h)``
的拉伸规则一致）；旋转时先绕框心转、再按旋转后的外接框等比放进同一个框，
与 PDF / 效果预览共用 ``utils.page_layout.fit_rotated_rect``。

⚠️ 2026-11-22 起拆成子包（constants / _host / geometry / mouse / paint /
canvas）。本 ``__init__`` 只做重导出：既有
``from ...print_layout_canvas import X`` 全部不变。
"""

from __future__ import annotations

from .canvas import PrintLayoutCanvas
from .constants import (
    DISPLAY_IMAGE_EDGE,
    EDGE_HIT_PX,
    HANDLE_RADIUS,
    MIN_RECT_MM,
    PAGE_BORDER,
    PAGE_COLOR,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_HIT,
    ROTATE_KNOB_RADIUS,
    SNAP_DEGREES,
)

__all__ = [
    "DISPLAY_IMAGE_EDGE",
    "MIN_RECT_MM",
    "PrintLayoutCanvas",
    "SNAP_DEGREES",
]
