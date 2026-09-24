# -*- coding: utf-8 -*-
"""第四步「版面编辑器」交互守卫：拖拽/缩放 → 坐标 → 通知宿主。

背景：用户在 A4 纸上直接拖动/缩放图片，坐标（页面 mm）写回 print.json 的
pages[].rect，生成 PDF 时由 plan_print_page(image_rect=...) 原样采用。要守住：

1. **初始框来自自动排版**：没存过坐标的页，用当前参数算出的框作起点（老任务
   无缝兼容），且必须落在页面内、尺寸非零；
2. **拖动真的改坐标**：框内拖动 = 整体移动，四角拖动 = 缩放；松手才发信号；
3. **夹在页面内**：往页面外拖不会拖出去（否则成品 PDF 会出现越界图片）；
4. **通知宿主**：rect_changed → 条目 rect 更新 + layout_changed(index, rect)，
   宿主据此落盘并标脏。

坐标体系与 utils.page_layout.plan_print_page 的 plan.image 同源（页面 mm、
左上原点），此处用控件私有 _off_x/_px_per_mm 反算像素位置来模拟真实鼠标。
"""

NAME = "print_layout_editor"
DEPENDS: list[str] = []
TITLE = "第四步版面编辑器拖拽与坐标"

import time


def _tmp_png(path, w: int, h: int):
    from PySide6.QtGui import QColor, QImage, QPainter

    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#f2f2f2"))
    painter = QPainter(img)
    painter.setPen(QColor("#333333"))
    painter.drawRect(10, 10, w - 20, h - 20)
    painter.end()
    img.save(str(path))
    return path


def run(ctx) -> None:
    from pathlib import Path

    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    from tests.selftests._context import ok, pump

    from desktop.components.viewers.print_preview import PrintPreviewWidget

    tmp = Path(ctx.tmp) / "print_layout_editor"
    tmp.mkdir(parents=True, exist_ok=True)
    app = ctx.app

    full = {
        "paper_size": "A4",
        "orientation": "landscape",
        "page_margins": [20, 20, 20, 20],
        "left_page_margins": [20, 20, 20, 20],
        "right_page_margins": [20, 20, 20, 20],
        "title_printing": False,
        "page_number": False,
    }
    png = _tmp_png(tmp / "0001.png", 800, 1200)

    widget = PrintPreviewWidget(params_provider=lambda: dict(full))
    widget.resize(1000, 700)
    widget.canvas.resize(600, 500)
    widget.show()
    pump(app, 6)

    seen_rect = []
    seen_layout = []
    widget.canvas.rect_changed.connect(lambda r: seen_rect.append(list(r)))
    widget.layout_changed.connect(
        lambda i, r: seen_layout.append((i, list(r)))
    )

    widget.set_entries([{"file": str(png), "label": "0001"}])
    pump(app, 6)

    # ---- 1. 初始框来自自动排版 ----
    rect0 = widget.canvas.current_rect()
    ok("初始框来自自动排版：尺寸非零且在页面内",
       len(rect0) == 4 and rect0[2] > 0 and rect0[3] > 0
       and rect0[0] >= 0 and rect0[1] >= 0
       and rect0[0] + rect0[2] <= widget.canvas._page_w_mm + 0.01
       and rect0[1] + rect0[3] <= widget.canvas._page_h_mm + 0.01,
       str(rect0))

    canvas = widget.canvas
    ppm = canvas._px_per_mm

    def _press(px, py):
        canvas.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(px, py),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))

    def _move(px, py):
        canvas.mouseMoveEvent(QMouseEvent(
            QEvent.Type.MouseMove, QPointF(px, py),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))

    def _release(px, py):
        canvas.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(px, py),
            Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

    # ---- 2. 框内拖动 = 整体移动 ----
    r = canvas._rect_px()
    cx, cy = r.x() + r.width() / 2, r.y() + r.height() / 2
    _press(cx, cy)
    _move(cx + 20 * ppm, cy + 10 * ppm)
    _release(cx + 20 * ppm, cy + 10 * ppm)
    rect1 = canvas.current_rect()
    ok("框内拖动整体移动（位移≈鼠标位移，尺寸不变）",
       abs(rect1[0] - rect0[0] - 20) < 1.0
       and abs(rect1[1] - rect0[1] - 10) < 1.0
       and abs(rect1[2] - rect0[2]) < 0.01
       and abs(rect1[3] - rect0[3]) < 0.01,
       f"{rect0} -> {rect1}")
    ok("移动后发了 rect_changed 且通知宿主 layout_changed",
       len(seen_rect) == 1 and len(seen_layout) == 1
       and seen_layout[0][0] == 0, str((seen_rect, seen_layout)))
    ok("坐标已写回条目 rect（供 print.json 落盘）",
       widget.entries()[0].get("rect") is not None
       and abs(widget.entries()[0]["rect"][0] - rect1[0]) < 0.01,
       str(widget.entries()[0].get("rect")))

    # ---- 3. 四角拖动 = 缩放 ----
    # ⚠️ 「原比例缩放」默认开启（keep_ratio=True，用户要求）：四角拖拽改为
    # **等比缩放**——鼠标给的宽高里取更受限的维度配对，所以宽高的增量不再
    # 各自 ≥5mm（这里竖开本受高度限制，宽只 +3.3mm），但**宽高比必须不变**、
    # 左上角不动、两个维度都变大。想自由拉伸请取消勾选（见第 7 节的边手柄）。
    r = canvas._rect_px()
    _press(r.x() + r.width(), r.y() + r.height())   # 右下角手柄
    _move(r.x() + r.width() + 15 * ppm, r.y() + r.height() + 5 * ppm)
    _release(r.x() + r.width() + 15 * ppm, r.y() + r.height() + 5 * ppm)
    rect2 = canvas.current_rect()
    ok("四角拖动缩放（默认原比例：等比变大，左上角不动）",
       rect2[2] > rect1[2] and rect2[3] > rect1[3]
       and abs(rect2[0] - rect1[0]) < 0.01
       and abs(rect2[1] - rect1[1]) < 0.01
       and abs(rect2[2] / rect2[3] - rect1[2] / rect1[3]) < 1e-6,
       f"{rect1} -> {rect2}")

    # ---- 4. 拖出页面会被夹住 ----
    r = canvas._rect_px()
    cx, cy = r.x() + r.width() / 2, r.y() + r.height() / 2
    _press(cx, cy)
    _move(cx - 5000, cy - 5000)
    _release(cx - 5000, cy - 5000)
    rect3 = canvas.current_rect()
    ok("往页面外拖会被夹在页面内（不越界）",
       rect3[0] >= -0.01 and rect3[1] >= -0.01
       and rect3[0] + rect3[2] <= canvas._page_w_mm + 0.01
       and rect3[1] + rect3[3] <= canvas._page_h_mm + 0.01,
       str(rect3))

    # ---- 5. 标题 / 页码必须在版面编辑器里画出来 ----
    # 曾误把「版面编辑」做成只画图片，用户以为标题页码被去掉了。它们是版面
    # 的一部分：不画就无从判断图片挪动后会不会压到字。
    def _ink_count() -> int:
        """画布上的深色像素数（标题/页码是黑字，画出来计数必增）。

        逐像素扫、不跳采样：版面编辑画布的密度只有 ~2 px/mm，12pt 的字
        换算下来不足 10px，跳采样会把字整个漏掉。
        """
        img = canvas.grab().toImage()
        if img.isNull():
            return -1
        return sum(
            1
            for y in range(img.height())
            for x in range(img.width())
            if img.pixelColor(x, y).red() < 120
            and img.pixelColor(x, y).green() < 120
            and img.pixelColor(x, y).blue() < 120
        )

    widget.set_entries([{"file": str(png), "label": "0001"}])
    pump(app, 6)
    ink_plain = _ink_count()
    ok("未开启标题/页码时画布只有图片（有基准可比对）",
       ink_plain >= 0 and canvas._plan is not None
       and canvas._plan.title is None and canvas._plan.page_number is None,
       f"ink={ink_plain}")

    widget._params_provider = lambda: dict(
        full, title_printing=True, title_text="測試古籍",
        page_number_printing=True, page_number_start_page=1,
    )
    widget.refresh_layout()
    pump(app, 6)
    ok("版面编辑的 plan 带标题与页码",
       canvas._plan.title is not None
       and canvas._plan.title.text == "測試古籍"
       and canvas._plan.page_number is not None,
       f"title={getattr(canvas._plan.title, 'text', None)}")
    ok("标题/页码真的画在画布上（深色像素增加）",
       _ink_count() > ink_plain, f"{ink_plain} -> {_ink_count()}")

    # 字号必须随画布密度换算（pt → mm → px），否则「字固定像素、逐字步进
    # 按 mm 缩放」两者口径不同，密度一变小字就叠在一起（真实踩过）。
    from desktop.workers.preview_worker import (
        MM_PER_PT, preview_text_font,
    )

    _spec_t = canvas._plan.title
    _font = preview_text_font(_spec_t, canvas._px_per_mm)
    _want_px = max(1, round(_spec_t.font_size_pt * MM_PER_PT
                            * canvas._px_per_mm))
    ok("标题字号按画布密度换算（pt → mm → px）",
       _font.pixelSize() == _want_px,
       f"pixelSize={_font.pixelSize()} want={_want_px}")
    ok("逐字步进与字号同源（字不会叠在一起）",
       abs(_spec_t.char_h_mm * canvas._px_per_mm - _font.pixelSize()) < 0.51,
       f"step={_spec_t.char_h_mm * canvas._px_per_mm:.2f} "
       f"font={_font.pixelSize()}")

    # ---- 6. 存过的坐标优先（重新进入第四步不丢） ----
    saved = [12.5, 8.5, 100.0, 60.0]
    widget.set_entries([{"file": str(png), "label": "0001",
                         "rect": list(saved)}])
    pump(app, 6)
    ok("已存坐标优先于自动排版（重进不丢）",
       all(abs(a - b) < 0.01
           for a, b in zip(canvas.current_rect(), saved)),
       f"{canvas.current_rect()} vs {saved}")

    widget.close()
    time.sleep(0)

    # ---- 7. 原比例缩放（keep_ratio）：手柄与拖拽手感 ----
    # 参数勾选「原比例缩放」（默认）→ 四角等比缩放、不给四边手柄；
    # 取消 → 铺满语义，另有上/下/左/右四个边手柄可单独拉伸改变比例。
    from PySide6.QtCore import QPointF  # noqa: F401（占位说明：命中走 mm 域）

    from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas

    ratio_canvas = PrintLayoutCanvas()
    try:
        ratio_canvas.resize(700, 560)
        ratio_canvas.show()
        pump(app, 4)
        ratio_canvas.set_page(297, 210, None, [100, 100, 200, 300])
        ok("四角 + 四边恒 8 个手柄（四边始终可用：拖边即单方向拉伸）",
           len(ratio_canvas._handle_positions()) == 8,
           str(len(ratio_canvas._handle_positions())))

        # 原比例：角拖拽保持宽高比（鼠标给的宽高里取更受限的维度配对；
        # 超出页面时整体等比缩回，不做单维度夹取——夹取会破坏比例）。
        ratio_canvas._keep_ratio = True
        ratio_canvas._rect_mm = [100, 100, 200, 300]     # w/h = 2/3
        ratio_canvas._grab_rect = list(ratio_canvas._rect_mm)
        ratio_canvas._corner = 0                          # 左上，锚点 = 右下
        rect = ratio_canvas._resize_from_handle(50, 50)
        ratio_src = 200 / 300
        ok("原比例角拖拽保持宽高比（超页时整体等比缩回）",
           abs(rect[2] / rect[3] - ratio_src) < 1e-6,
           f"{rect[2]:.1f}/{rect[3]:.1f} = {rect[2] / rect[3]:.3f} "
           f"vs 源 {ratio_src:.3f}")
        ok("…且仍在页面内",
           rect[0] >= 0 and rect[1] >= 0
           and rect[0] + rect[2] <= 297 + 1e-6
           and rect[1] + rect[3] <= 210 + 1e-6,
           str([round(v, 1) for v in rect]))

        # 非原比例：边手柄只改一个维度（这正是"可以上下左右拉伸"）
        ratio_canvas._keep_ratio = False
        ratio_canvas._rect_mm = [100, 100, 200, 100]
        ratio_canvas._corner = 4                          # 上边
        rect = ratio_canvas._resize_from_handle(150, 40)
        ok("上边手柄单独拉伸：高度变、宽度不动（比例随之改变）",
           abs(rect[2] - 200) < 1e-6 and abs(rect[3] - 160) < 1e-6,
           str([round(v, 1) for v in rect]))
        ratio_canvas._corner = 5                          # 右边
        rect = ratio_canvas._resize_from_handle(260, 150)
        ok("右边手柄单独拉伸：宽度变、高度不动",
           abs(rect[2] - 160) < 1e-6 and abs(rect[3] - 100) < 1e-6,
           str([round(v, 1) for v in rect]))
        # ⚠️ 边手柄**不看** keep_ratio：勾着「原比例缩放」也必须能单方向拉伸
        # （用户 16:58 报：「四边也可以拉伸调整，这样可以自由缩放宽高」）。
        ratio_canvas._keep_ratio = True
        ratio_canvas._rect_mm = [100, 100, 200, 100]
        ratio_canvas._corner = 4                          # 上边
        rect = ratio_canvas._resize_from_handle(150, 40)
        ok("勾着原比例时边手柄仍可单独拉伸（等比只约束四角）",
           abs(rect[2] - 200) < 1e-6 and abs(rect[3] - 160) < 1e-6,
           str([round(v, 1) for v in rect]))

        # 命中区：**整条边**都算（不限于边中点的小圆点）；角优先于边。
        # 用户 17:03 报「为何不把四边大部分区域做成可以改变宽度的功能」。
        rpx = ratio_canvas._rect_px()
        ok("上边整条都是命中区（偏离中点也能拖那条边）",
           ratio_canvas._hit_handle(
               QPointF(rpx.center().x() + 60, rpx.y())) == 4, "")
        ok("右边的非中点位置同样命中",
           ratio_canvas._hit_handle(
               QPointF(rpx.x() + rpx.width(), rpx.center().y() - 40)) == 5, "")
        ok("角部优先按对角缩放命中（不误判成边）",
           ratio_canvas._hit_handle(QPointF(rpx.x(), rpx.y())) == 0, "")
        ok("框内仍命中移动（不会被边带误判成缩放）",
           ratio_canvas._hit_handle(rpx.center()) is None
           and ratio_canvas._hit_rect(rpx.center()), "")
    finally:
        ratio_canvas.deleteLater()
