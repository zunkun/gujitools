# -*- coding: utf-8 -*-
"""第四步（print）图片列表的条目几何自测。

背景：用户反馈「area=2 border=None 时，列表里图片与下方文字距离偏大」。
根因不在 area/border 几何（`utils.box_geometry` 输出的画布尺寸是对的），
而在 `PrintPreviewWidget` 的列表项布局：

    ICON_SIZE = 180x240      # 图标框
    GRID_SIZE = 200x290      # 每个条目的固定网格
    textAlignment = AlignBottom

条目被强制成 200x290 的固定框，图标只占顶部 240px，而文字被
`AlignBottom` **钉在网格最底部** —— 于是图片下沿到文字之间恒定空出
GRID_H - ICON_H = 50px 死区，与图片宽高比无关。

为什么 `area=2 + border=None` 观感最差：该模式下输出的是**整页画布**
（如 2481x3508，ratio 1.414），缩到 180x240 图标框时几乎占满，
人眼看到「图片 → 50px 空白 → 文字」的对比最强烈；而 `area=1` 输出
900x2600（ratio 2.889）只占图标框中间约 83px 宽，同样的 50px 显得不刺眼。

本模块守住两条不变量：
1. 网格高 = 图标高 + 文件名区，**不在两者之间预留死区**；
2. 文字对齐不得用 AlignBottom（会把文字推出图标紧邻区）。
"""

NAME = "print_list_layout"
DEPENDS: list[str] = []
TITLE = "print 列表条目几何"


def run(ctx) -> None:
    from tests.selftests._context import ok

    from desktop.components.viewers.print_preview import PrintPreviewWidget

    # ---- 1. 网格高与图标高不再脱节 ----
    icon_h = PrintPreviewWidget.ICON_SIZE.height()
    grid_h = PrintPreviewWidget.GRID_SIZE.height()
    label_h = PrintPreviewWidget.LABEL_H
    ok("网格高 = 图标高 + 文件名区",
       grid_h == icon_h + label_h,
       f"ICON_H={icon_h} LABEL_H={label_h} GRID_H={grid_h}")
    ok("文件名区高度为正且克制（< 80px）",
       0 < label_h < 80, f"LABEL_H={label_h}")
    ok("网格宽度不小于图标宽度",
       PrintPreviewWidget.GRID_SIZE.width() >= PrintPreviewWidget.ICON_SIZE.width(),
       f"{PrintPreviewWidget.GRID_SIZE} vs {PrintPreviewWidget.ICON_SIZE}")

    # 曾出 bug 的旧值：GRID_H(290) - ICON_H(240) = 50px 死区
    dead_band = grid_h - icon_h - label_h
    ok("图标与文字之间无额外死区", dead_band == 0, f"死区 {dead_band}px")

    # ---- 2. 条目文字对齐不得是 AlignBottom ----
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QListWidgetItem

    widget = PrintPreviewWidget()
    try:
        widget.set_entries([{"file": __file__, "label": "82"}])
        item: QListWidgetItem = widget.list.item(0)
        align = item.textAlignment()
        ok("条目文字不使用 AlignBottom（否则会被钉到网格底部）",
           not (align & Qt.AlignBottom), f"align={int(align)}")
        ok("条目文字水平居中", bool(align & Qt.AlignHCenter), f"align={int(align)}")
        # SizeHint 与网格一致，避免文字被裁
        hint = item.sizeHint()
        ok("条目 SizeHint 与网格尺寸一致",
           hint.width() == PrintPreviewWidget.GRID_SIZE.width()
           and hint.height() == PrintPreviewWidget.GRID_SIZE.height(),
           f"hint={hint.width()}x{hint.height()}")
    finally:
        widget.deleteLater()

    # ---- 3. area=2 + border=None 的输出确实会占满图标框（回归语境）----
    from utils.box_geometry import build_output_layout

    boxes = [[300, 400, 1200, 3000], [1300, 400, 2200, 3000]]
    lay = build_output_layout(
        boxes, area=2, border_padding=None, image_size=(2481, 3508), dpi=300
    )
    canvas = lay.canvases[0]
    ok("area=2 双框 border=None 走整页画布", lay.full_page, str(lay))
    ok("整页画布尺寸 = 原图尺寸", canvas.size == (2481, 3508), str(canvas.size))
    # 该比例在 180x240 图标框内几乎占满 -> 死区会被看得一清二楚
    ratio = canvas.size[1] / canvas.size[0]
    icon_ratio = icon_h / PrintPreviewWidget.ICON_SIZE.width()
    ok("整页输出比例接近方形，确实会占满图标框",
       ratio < icon_ratio * 1.15,
       f"canvas_ratio={ratio:.3f} icon_ratio={icon_ratio:.3f}")
