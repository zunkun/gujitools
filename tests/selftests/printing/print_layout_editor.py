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

    img = QImage(w, h, QImage.Format.Format_RGB32)
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
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    def _move(px, py):
        canvas.mouseMoveEvent(QMouseEvent(
            QEvent.Type.MouseMove, QPointF(px, py),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    def _release(px, py):
        canvas.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(px, py),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

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

    # ---- 4. 可以拖出纸面（负边距 = 图片顶出纸边，需能挪裁切位置）----
    r = canvas._rect_px()
    cx, cy = r.x() + r.width() / 2, r.y() + r.height() / 2
    _press(cx, cy)
    _move(cx - 200 * ppm, cy - 200 * ppm)
    _release(cx - 200 * ppm, cy - 200 * ppm)
    rect3 = canvas.current_rect()
    ok("可以拖到纸面外（不再把框夹回纸内）",
       rect3[0] < -0.01 and rect3[1] < -0.01, str(rect3))

    # 拖出纸面的框必须原样带进预览/PDF 排版；之前 plan 把"越界"当坏值回落
    # 自动排版，双击放大预览时图又被铺满整张 A4（用户 2026-11-22）。
    from utils.page_layout import plan_print_page

    spec_out, _note = widget._print_spec(0, Path(str(png)))
    plan_out = plan_print_page(
        (800, 1200), spec_out["args"], 0, 1,
        image_name="0001", image_rect=spec_out["rect"],
    )
    ok("拖出纸面的坐标带进预览/PDF（不被自动排版覆盖）",
       all(abs(a - b) < 1e-9
           for a, b in zip(plan_out.image, spec_out["rect"]))
       and spec_out["rect"][0] < -0.01 and spec_out["rect"][1] < -0.01,
       f"{spec_out['rect']} -> {plan_out.image}")

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
    _plan = canvas._plan
    assert _plan is not None            # ⚠️ 上面刚 set_entries，必然排出版面
    ok("版面编辑的 plan 带标题与页码",
       _plan.title is not None
       and _plan.title.text == "測試古籍"
       and _plan.page_number is not None,
       f"title={getattr(_plan.title, 'text', None)}")
    ok("标题/页码真的画在画布上（深色像素增加）",
       _ink_count() > ink_plain, f"{ink_plain} -> {_ink_count()}")

    # 字号必须随画布密度换算（pt → mm → px），否则「字固定像素、逐字步进
    # 按 mm 缩放」两者口径不同，密度一变小字就叠在一起（真实踩过）。
    from desktop.workers.preview_worker import (
        MM_PER_PT, preview_text_font,
    )

    _spec_t = _plan.title
    assert _spec_t is not None          # ⚠️ 上一段已判过标题存在
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
        ratio_canvas._rect_mm = [100.0, 100.0, 200.0, 300.0]   # w/h = 2/3
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
        ratio_canvas._rect_mm = [100.0, 100.0, 200.0, 100.0]
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
        ratio_canvas._rect_mm = [100.0, 100.0, 200.0, 100.0]
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

        # ---- 8. 贴图底图：源图先平滑降到上限，拖框期间复用缓存 ----
        # 用户报「rembg 图放大看还行，PDF 排版页发虚」：画布是 8~10 倍缩小 +
        # 最近邻采样。现在源图一次性平滑降到 DISPLAY_IMAGE_EDGE，贴图再平滑缩。
        from PySide6.QtGui import QColor, QImage

        from desktop.components.viewers.print_layout_canvas import (
            DISPLAY_IMAGE_EDGE,
        )

        big = QImage(4000, 2600, QImage.Format.Format_RGB32)
        big.fill(QColor("#ffffff"))
        ratio_canvas.set_page(297, 210, big, [20, 20, 250, 170])
        cached = ratio_canvas._display_image_for()
        ok("贴图底图按上限平滑降采样（4000px 源图 → 2000px）",
           cached is not None
           and max(cached.width(), cached.height()) == DISPLAY_IMAGE_EDGE,
           "" if cached is None else f"{cached.width()}x{cached.height()}")
        ok("同一张图重复取底图复用缓存（拖框不重采样）",
           ratio_canvas._display_image_for() is cached, "")

        # ---- 8.1 负边距顶出纸边：纸外不显示图片内容 ----
        # 成品 PDF 把纸外内容交给纸张裁掉（见 print_margin_negative），编辑
        # 画布也必须只显示纸内那部分，否则"看起来出的纸"与 PDF 对不上。
        red = QImage(100, 100, QImage.Format.Format_RGB32)
        red.fill(QColor("#e53935"))
        ratio_canvas.set_page(100, 100, red, [-10, -10, 120, 120])
        pump(app, 4)
        shot = ratio_canvas.grab().toImage()
        ppm = ratio_canvas._px_per_mm
        row = round(ratio_canvas._off_y + 50 * ppm)
        out_px = shot.pixelColor(round(ratio_canvas._off_x - 5 * ppm), row)
        in_px = shot.pixelColor(round(ratio_canvas._off_x + 3 * ppm), row)

        def _is_red(color) -> bool:
            return (color.red() > 200 and color.green() < 100
                    and color.blue() < 100)

        ok("负边距：纸外的图片内容被裁掉（不显示越界部分）",
           not _is_red(out_px), str(out_px.getRgb()))
        ok("负边距：纸内的图片内容照常显示",
           _is_red(in_px), str(in_px.getRgb()))
        frame_x = round(ratio_canvas._rect_px().left())
        frame_px = [
            shot.pixelColor(frame_x + dx, round(ratio_canvas._off_y) - 4)
            for dx in (0, 1, 2)
        ]
        ok("负边距：图片画框也裁到纸内（纸外不画框线）",
           not any(c.blue() > 150 and c.red() < 120 for c in frame_px),
           str([c.getRgb() for c in frame_px]))
        # 纸面缩放只由纸张尺寸决定：图片框再大也不能把 A4 撑大/缩小
        ppm_before = ratio_canvas._px_per_mm
        ratio_canvas.set_page(100, 100, red, [-40, -40, 180, 180])
        pump(app, 4)
        ok("纸张显示比例与图片框无关（A4 纸不随图缩放）",
           ratio_canvas._px_per_mm == ppm_before,
           f"{ppm_before} → {ratio_canvas._px_per_mm}")

        # 定位方块（手柄）落在纸外也不画：用只越界一点点的框，保证手柄
        # 还在控件可视区内，扫它的方块区域确认没有蓝色描边。
        ratio_canvas.set_page(100, 100, red, [-10, -2, 120, 104])
        pump(app, 4)
        shot2 = ratio_canvas.grab().toImage()
        hx, hy = ratio_canvas._handle_positions()[0]
        span = 9
        blue_px = sum(
            1
            for xx in range(max(0, round(hx) - span),
                            min(shot2.width(), round(hx) + span + 1))
            for yy in range(max(0, round(hy) - span),
                            min(shot2.height(), round(hy) + span + 1))
            if shot2.pixelColor(xx, yy).blue() > 150
            and shot2.pixelColor(xx, yy).red() < 120
        )
        ok("负边距：纸外的定位方块（手柄）不显示",
           blue_px == 0, f"蓝色像素={blue_px}")
    finally:
        ratio_canvas.deleteLater()

    # ---- 9. 版面编辑的旋转钮：任意角度 → 条目 → 落盘 ----
    # 用户 2026-11-02：「旋转组件跟图片拼版中的一样，而不是 90 度旋转组件」。
    # 口径是**浮点角度（顺时针为正，(-180, 180]）**，存进 print.json 的
    # pages[].rotate；预览与 PDF 都先转位图、再按旋转后的外接框等比放进同一个框。
    from utils.page_layout import normalize_page_rotation, rotated_bbox_size

    cases = (0, 90, 180, 270, 360, -90, 45.5, None, 181, -180)
    expected = [0, 90, 180, -90, 0, -90, 45.5, 0, -179, 180]
    ok("旋转角归一为 (-180, 180] 浮点（顺时针为正，270→-90）",
       [normalize_page_rotation(v) for v in cases] == expected,
       str([normalize_page_rotation(v) for v in cases]))

    rot = PrintPreviewWidget(params_provider=lambda: dict(full))
    rot.resize(1000, 700)
    rot.canvas.resize(600, 500)
    rot.show()
    pump(app, 6)
    rot.set_entries([{"file": str(png), "label": "0001", "rotate": 90}])
    pump(app, 6)
    c90 = rot.canvas.current_rect()
    ok("存过的朝向进版面编辑器：画布角度=90，框是**旋转后**的外接框",
       rot.canvas.rotation() == 90
       and abs(c90[2] / c90[3] - 1200 / 800) < 0.02
       and rot._canvas_image_size == [800, 1200],
       f"rotate={rot.canvas.rotation()} rect={c90} "
       f"size={rot._canvas_image_size}")

    knob = rot.canvas._rotate_knob_pos()
    ok("旋转钮在框外上方且可命中（与图片拼版同款组件）",
       rot.canvas._hit_handle(knob) == 8
       and knob.y() < rot.canvas._rect_px().y() - 10,
       f"knob=({knob.x():.1f},{knob.y():.1f})")

    rot_changed = []
    rot.canvas.rect_changed.connect(rot_changed.append)
    rot.canvas.set_rotation(180)
    pump(app, 4)
    c180 = rot.canvas.current_rect()
    ok("set_rotation(180)：框宽高交换、条目写回 rotate、立即上报",
       rot.canvas.rotation() == 180
       and rot.entries()[0].get("rotate") == 180
       and rot_changed[-1:] == [[round(v, 2) for v in c180]]
       and abs(c180[2] / c180[3] - c90[3] / c90[2]) < 0.05
       and c180[0] >= -0.01 and c180[1] >= -0.01
       and c180[0] + c180[2] <= rot.canvas._page_w_mm + 0.01
       and c180[1] + c180[3] <= rot.canvas._page_h_mm + 0.01,
       f"{c90} -> {c180}, rotate={rot.entries()[0].get('rotate')}")

    rot.canvas.set_rotation(30)
    pump(app, 4)
    c30 = rot.canvas.current_rect()
    want = rotated_bbox_size(800, 1200, 30)
    ok("任意角度（30°）：框=旋转后外接框，条目存浮点角度",
       rot.canvas.rotation() == 30
       and rot.entries()[0].get("rotate") == 30
       and abs(c30[2] / c30[3] - want[0] / want[1]) < 0.02,
       f"rect={c30} bbox={want}")

    spec, note = rot._print_spec(0, Path(str(png)))
    ok("预览 print_spec 带上浮点朝向（worker 先转位图再排版）",
       spec is not None and spec.get("rotate") == 30 and note == "",
       str((spec or {}).get("rotate")))

    ok("旧的左右转按钮已移除（旋转统一走画布圆钮）",
       not hasattr(rot, "rotate_left_button")
       and not hasattr(rot, "rotate_right_button"), "")
    rot.close()

    # ---- 10. 落盘口径：pages[].rotate 非 0 才写 ----
    from desktop.services.print_plan import ordered_page_record

    rec = ordered_page_record({
        "file": str(png), "label": "0001", "rotate": 90,
        "rect": [10, 10, 100, 50], "rect_size": [800, 1200],
    })
    ok("ordered_page_record 写出 rotate，rect_size 仍是未旋转源图尺寸",
       rec.get("rotate") == 90
       and rec.get("rect_size") == [800, 1200], str(rec))
    ok("0° 不写 rotate（没有旋转就不算覆盖）",
       "rotate" not in ordered_page_record({
           "file": str(png), "label": "0001", "rotate": 0,
       }), "")

