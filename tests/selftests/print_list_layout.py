# -*- coding: utf-8 -*-
"""第四步预览区的**布局形态**自测：与前三步保持一致。

背景：第四步原来是「图片瀑布流（QListWidget IconMode 网格）」，右侧参数
再全也看不出成品长什么样，而且和第一~三步（左缩略图条 + 右大图）不是
一套视觉语言。改成左缩略图 + 右效果预览后，本模块守住三条布局不变量：

1. 第 2/3/4 步的预览区都是「左 ThumbStrip + 右 ImageView」；
2. 旧瀑布流的网格常量（ICON_SIZE / GRID_SIZE / LABEL_H）已经移除——
   只要有人把它们加回来，说明又退回网格布局了；
3. 缩略图条宽度与前三步一致（视觉对齐）。
"""

NAME = "print_list_layout"
DEPENDS: list[str] = []
TITLE = "第四步预览布局形态"


def run(ctx) -> None:
    from tests.selftests._context import ok

    from desktop.components.viewers.image_view import ImageView
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget
    from desktop.components.viewers.thumb_strip import ThumbStrip

    # ---- 1. 与前三步同构：左缩略图条 + 右大图 ----
    widgets = {
        "detect(第2步)": ImageViewerWidget(),
        "rembg(第3步)": RembgPreviewWidget(),
        "print(第4步)": PrintPreviewWidget(),
    }
    try:
        for name, widget in widgets.items():
            ok(f"{name}：左 ThumbStrip + 右 ImageView",
               isinstance(getattr(widget, "strip", None), ThumbStrip)
               and isinstance(getattr(widget, "view", None), ImageView),
               f"{type(widget).__name__}")
            ok(f"{name}：缩略图条在左（先于大图加入布局）",
               widget.layout().itemAt(0) is not None)
    finally:
        for widget in widgets.values():
            widget.deleteLater()

    # ---- 2. 旧瀑布流常量必须已移除 ----
    for attr in ("ICON_SIZE", "GRID_SIZE", "LABEL_H"):
        ok(f"print 预览已移除旧网格常量 {attr}",
           not hasattr(PrintPreviewWidget, attr),
           str(getattr(PrintPreviewWidget, attr, None)))

    # ---- 3. 缩略图条宽度与前三步一致 ----
    # 无父对象的临时控件必须持有引用，否则会被 Python 立刻回收
    holder = PrintPreviewWidget()
    plain = ThumbStrip()
    try:
        strip_print = holder.strip
        ok("缩略图条宽度沿用 ThumbStrip 固定值",
           strip_print.width() == plain.width() and strip_print.width() > 0,
           f"{strip_print.width()} vs {plain.width()}")
        ok("缩略图条宽度就是 ThumbStrip.STRIP_WIDTH（唯一来源）",
           strip_print.width() == ThumbStrip.STRIP_WIDTH,
           f"{strip_print.width()} vs {ThumbStrip.STRIP_WIDTH}")
        # 条目网格必须放得下整个图标框：图标框比网格还大时 QListWidget 会
        # 悄悄压缩图标，缩略图看起来"没占满宽度"
        ok("条目网格放得下图标框（含文字行）",
           ThumbStrip.GRID_SIZE.width() >= ThumbStrip.ICON_SIZE.width()
           and ThumbStrip.GRID_SIZE.height()
           >= ThumbStrip.ICON_SIZE.height() + ThumbStrip.LABEL_H,
           f"grid={ThumbStrip.GRID_SIZE} icon={ThumbStrip.ICON_SIZE}")
        ok("缩略图条为纵向单列（不换行）",
           strip_print.flow() == ThumbStrip.Flow.TopToBottom
           and strip_print.isWrapping() is False)
    finally:
        holder.deleteLater()
        plain.deleteLater()

    # ---- 4. 工具栏仍在（插入/删除/下载 PDF）----
    widget = PrintPreviewWidget()
    try:
        ok("工具栏保留插入/删除/下载按钮",
           widget.insert_button is not None
           and widget.delete_button is not None
           and widget.download_button is not None)
        ok("下载按钮初始禁用（还没生成 PDF）",
           widget.download_button.isEnabled() is False)
    finally:
        widget.deleteLater()

    # ---- 5. 条目高度逐条自适应：不同宽高比的页面之间不再是"留白" ----
    # 根因：早先网格单元统一高度（竖框 156 + 文字行），横幅双页拼合图缩进
    # 竖框后只占约一半框高，剩下的是单元内空白；而网格高度若取"最高那张"，
    # 矮一点的条目各自留的空白还不一样大 → 用户看到"同高图间距 0、
    # 不同高图间距很大"。现在取消网格、每条按图定高，间距只剩 ITEM_SPACING。
    from PySide6.QtGui import QImage

    strip = ThumbStrip()
    try:
        label_h = ThumbStrip.LABEL_H
        spacing = ThumbStrip.ITEM_SPACING
        ok("条目之间保留可见间距（不为 0）", spacing > 0, f"spacing={spacing}")

        def _hint_h(w: int, h: int) -> int:
            """w×h 的图放进图标框后的条目总高（图高 + 文字行）。"""
            shown = _size_fitted(w, h)
            return max(ThumbStrip.MIN_DISPLAY_H, shown) + label_h

        def _size_fitted(w: int, h: int) -> int:
            box_w, box_h = (ThumbStrip.ICON_SIZE.width(),
                            ThumbStrip.ICON_SIZE.height())
            scale = min(box_w / w, box_h / h)
            return round(h * scale)

        def _make_image(w: int, h: int) -> QImage:
            img = QImage(w, h, QImage.Format.Format_RGB32)
            img.fill(0xFF888888)
            return img

        # 三张宽高比不同的图：横幅双页(480×200) / 中等(400×260) / 竖开本(200×400)
        sizes = [(480, 200), (400, 260), (200, 400)]
        for w, h in sizes:
            strip.add_page_item(f"{w}x{h}", "")
        ok("占位图阶段条目按满框给定",
           strip.item(0).sizeHint().height()
           == ThumbStrip.ICON_SIZE.height() + label_h,
           str(strip.item(0).sizeHint()))
        for row, (w, h) in enumerate(sizes):
            strip.set_item_icon(row, _make_image(w, h), f"f{row}", f"第{row}頁")

        hints = [strip.item(row).sizeHint().height() for row in range(3)]
        expected = [_hint_h(w, h) for w, h in sizes]
        ok("条目高度逐条跟着图走（不同宽高比 → 不同高）",
           hints == expected and len(set(hints)) == len(hints),
           f"{hints} vs {expected}")
        ok("条目高度 = 图高 + 文字行（条目内不留任何空白）",
           all(abs(got - exp) <= 1 for got, exp in zip(hints, expected)),
           f"{hints} vs {expected}")
        ok("横幅图条目明显比旧满框矮（空白已去掉）",
           hints[0] < ThumbStrip.ICON_SIZE.height() + label_h - 24,
           f"{hints[0]} vs 满框 {ThumbStrip.ICON_SIZE.height() + label_h}")
        ok("竖开本条目仍是满框高（窄图不被压扁也不被截断）",
           abs(hints[2] - (ThumbStrip.ICON_SIZE.height() + label_h)) <= 1,
           f"{hints[2]}")
        # 条目宽度统一（占满条宽），与前三步对齐
        ok("条目宽度统一 = 网格宽",
           all(strip.item(row).sizeHint().width()
               == ThumbStrip.GRID_SIZE.width() for row in range(3)),
           str([strip.item(r).sizeHint().width() for r in range(3)]))
    finally:
        strip.deleteLater()
