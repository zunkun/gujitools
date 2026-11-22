# -*- coding: utf-8 -*-
"""7c. 整版/单图旋转组件 + 红色对齐线（用户 2026-09-30） / 整版旋转的几何：绕公共中心公转 + 自转，公共中心不动 / 单图绝对角度：只改选中的那张 / 红色对齐线恒显（对比：框线未按住时不画，对齐线必须一直在） / 单图页红线判据（用户 2026-09-30 晚：单独一张半页图片在某页， / 成品截图范围框：两图外接框并集的灰虚线（用户 2026-09-30） / 7d. 滚轮缩放 + 渲染按帧合并（用户 2026-09-30） / 渲染合并：连发期间只有一个帧窗口，多余的滚动并到下一帧 / 倍率钳制 / 尺寸变化保留倍率；载页 / refit 才归一"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import BLUE, CROP_RGB, SPINE_RGB, _count_near, _mk, ROOT
    from desktop.components.imposition.canvas import ImpositionCanvas
    from pathlib import Path
    from PySide6.QtCore import QPoint
    from PySide6.QtCore import QPointF, QSize, Qt
    from desktop.services import imposition as S
    from PySide6.QtGui import QWheelEvent as _QWheelEvent
    from desktop.components.imposition import canvas as _canvas_mod
    import math
    from tests.selftests._context import make_pdf, ok, pump
    import math

    from desktop.components.imposition.panel import ImpositionPanel
    from desktop.ui.widgets import HelpButton

    def _centers(items):
        return [
            (
                it["rect"][0] + it["rect"][2] / 2.0,
                it["rect"][1] + it["rect"][3] / 2.0,
            )
            for it in items
        ]
    st._centers = _centers
    st.canvas2 = ImpositionCanvas()
    st.canvas2.resize(600, 600)
    st.canvas2.set_page(S.default_items([str(st.a), str(st.b)]))
    st.canvas2.select(0)
    centers_before = st._centers(st.canvas2._items)
    mid_before = st.canvas2._spread_center_units()
    st.canvas2.rotate_whole(30.0)
    centers_after = st._centers(st.canvas2._items)
    mid_after = st.canvas2._spread_center_units()
    ok(
        "整版旋转：两图中心间距不变（相对位置不动）",
        abs(
            math.dist(centers_after[0], centers_after[1])
            - math.dist(centers_before[0], centers_before[1])
        )
        < 1e-6,
    )
    ok(
        "整版旋转：公共中心（红色对齐线落点）不动",
        all(abs(a - b) < 1e-9 for a, b in zip(mid_before, mid_after)),
    )
    ok(
        "整版旋转：两图 rotation 都叠加增量（自转）",
        all(abs(it["rotation"] - 30.0) < 0.01 for it in st.canvas2.items()),
        str([it["rotation"] for it in st.canvas2.items()]),
    )
    _spread_rot = st.canvas2.spread_rotation()
    assert _spread_rot is not None  # ⚠️ 两张图都有 rotation，必然有公共角
    ok(
        "spread_rotation = 两图平均角",
        abs(_spread_rot - 30.0) < 0.01,
        str(_spread_rot),
    )
    st.canvas2.set_item_rotation(45.0)
    ok(
        "set_item_rotation 只改选中图的绝对角度",
        abs(st.canvas2.items()[0]["rotation"] - 45.0) < 0.01
        and abs(st.canvas2.items()[1]["rotation"] - 30.0) < 0.01,
        str([it["rotation"] for it in st.canvas2.items()]),
    )
    _sel_rot = st.canvas2.selected_rotation()
    assert _sel_rot is not None  # ⚠️ 刚选中过，必然读得到
    ok("selected_rotation 读到选中角", abs(_sel_rot - 45.0) < 0.01)
    st.canvas2.deleteLater()
    st.spine_cv = ImpositionCanvas()
    st.spine_cv.resize(600, 600)
    # ⚠️ 判据用 BLUE/YELLOW 图：测试用的 RED (220,40,40) 与对齐线
    # (224,32,32) 太接近，会污染像素计数
    st.spine_cv.set_page(
        [
            {"file": str(st.c), "rect": [400.0, 0.0, 400.0, 600.0], "rotation": 0.0},
            {"file": str(st.d), "rect": [0.0, 0.0, 400.0, 600.0], "rotation": 0.0},
        ]
    )

    def _red_hits(image, x_px, band=8):
        """数 ``x_px ± band`` 这一竖条里的对齐线红像素（窄带扫描，快）。"""
        total = 0
        for x in range(max(0, x_px - band), min(image.width(), x_px + band + 1)):
            for y in range(0, image.height()):
                color = image.pixelColor(x, y)
                if (
                    abs(color.red() - SPINE_RGB[0]) <= 40
                    and abs(color.green() - SPINE_RGB[1]) <= 40
                    and abs(color.blue() - SPINE_RGB[2]) <= 40
                ):
                    total += 1
        return total
    st._red_hits = _red_hits

    st.spine_img = st.spine_cv.grab().toImage()
    x_units, _ = st.spine_cv._spread_center_units()
    st.x_px = int(round(st.spine_cv._off_x + x_units * st.spine_cv._px_per_unit))
    ok(
        "红色对齐线**恒显**（未按住鼠标也在画）",
        st._red_hits(st.spine_img, st.x_px) > 20,
        f"命中 {st._red_hits(st.spine_img, st.x_px)} 像素",
    )
    ok(
        "对齐线只画在两图中心中点那条竖线上（别处没有）",
        st._red_hits(st.spine_img, st.x_px + 150, band=4) == 0,
        f"远处命中 {st._red_hits(st.spine_img, st.x_px + 150, band=4)}",
    )
    single_portrait = _mk(st.tmp / "single-half.png", BLUE)  # 400×600 竖图
    st.spine_cv.set_page(
        [
            {
                "file": str(single_portrait),
                "rect": [0.0, 0.0, 400.0, 600.0],
                "rotation": 0.0,
            },
        ]
    )
    portrait_img = st.spine_cv.grab().toImage()
    ok(
        "单图页是**竖图**（半页/单页，含无后缀的）：整幅画面没有红线",
        _count_near(portrait_img, SPINE_RGB) == 0,
        f"命中 {_count_near(portrait_img, SPINE_RGB)} 像素",
    )
    single_land = _mk(st.tmp / "single-spread.png", BLUE, size=(600, 400))
    st.spine_cv.set_page(
        [
            {
                "file": str(single_land),
                "rect": [0.0, 0.0, 600.0, 400.0],
                "rotation": 0.0,
            },
        ]
    )
    land_img = st.spine_cv.grab().toImage()
    ok(
        "单图页是**横图**（整幅对开）：红色对齐线仍要画（旋转基准）",
        _count_near(land_img, SPINE_RGB) > 20,
        f"命中 {_count_near(land_img, SPINE_RGB)} 像素",
    )
    def _crop_hits_x(image, x_px, band=6, y_from=None, y_to=None):
        """数 ``x_px ± band`` 竖条里的截图框灰像素；y 范围可裁（避开横边）。"""
        total = 0
        for x in range(max(0, x_px - band), min(image.width(), x_px + band + 1)):
            for y in range(
                y_from if y_from is not None else 0,
                y_to if y_to is not None else image.height(),
            ):
                color = image.pixelColor(x, y)
                if (
                    abs(color.red() - CROP_RGB[0]) <= 40
                    and abs(color.green() - CROP_RGB[1]) <= 40
                    and abs(color.blue() - CROP_RGB[2]) <= 40
                ):
                    total += 1
        return total

    def _bbox_px(cv):
        """外接框并集（=产出紧裁范围）→ 控件像素 (l,t,r,b) + 图坐标元组。"""
        boxes = [cv._item_box_units(it) for it in cv._items]
        ul = min(b[0] for b in boxes)
        ut = min(b[1] for b in boxes)
        ur = max(b[2] for b in boxes)
        ub = max(b[3] for b in boxes)
        px = tuple(
            int(round(off + u * cv._px_per_unit))
            for off, u in (
                (cv._off_x, ul),
                (cv._off_y, ut),
                (cv._off_x, ur),
                (cv._off_y, ub),
            )
        )
        return px, (ul, ut, ur, ub)

    (l_px, t_px, r_px, b_px), _ubox = _bbox_px(st.spine_cv)
    ok(
        "成品截图范围框**恒显**：边线画在两图最外侧点的并集上",
        _crop_hits_x(st.spine_img, l_px) > 20 and _crop_hits_x(st.spine_img, r_px) > 20,
        f"左 {_crop_hits_x(st.spine_img, l_px)} / "
        f"右 {_crop_hits_x(st.spine_img, r_px)} 像素",
    )
    # 内部查灰要避开上下横边所在的行（矩形边框本来就贯穿全宽）
    _inner_l = _crop_hits_x(
        st.spine_img, l_px + 150, band=4, y_from=t_px + 10, y_to=b_px - 10
    )
    _inner_r = _crop_hits_x(
        st.spine_img, r_px - 150, band=4, y_from=t_px + 10, y_to=b_px - 10
    )
    ok(
        "并集内部没有截图框线（虚线只在最外侧）",
        _inner_l == 0 and _inner_r == 0,
        f"内测命中 {_inner_l} / {_inner_r}",
    )
    _w_before = _ubox[2] - _ubox[0]
    st.spine_cv.rotate_whole(30.0)
    spine_img2 = st.spine_cv.grab().toImage()
    ok(
        "整版旋转时对齐线仍在原位（旋转对比基准）",
        st._red_hits(spine_img2, st.x_px) > 5,
        f"命中 {st._red_hits(spine_img2, st.x_px)}",
    )
    st.spine_cv.refit()
    crop_img2 = st.spine_cv.grab().toImage()
    (_l2, _t2, _r2, _b2), _ubox2 = _bbox_px(st.spine_cv)
    ok(
        "整版旋转后外接框并集外扩（截图范围跟着最外侧点走）",
        _ubox2[2] - _ubox2[0] > _w_before
        and _crop_hits_x(crop_img2, _l2) > 20
        and _crop_hits_x(crop_img2, _r2) > 20,
        f"宽 {_w_before:.0f}→{_ubox2[2] - _ubox2[0]:.0f}，"
        f"边线命中 {_crop_hits_x(crop_img2, _l2)} / "
        f"{_crop_hits_x(crop_img2, _r2)}",
    )
    st.spine_cv.deleteLater()
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent as _QWheelEvent

    from desktop.components.imposition import canvas as _canvas_mod

    st.zoom_cv = ImpositionCanvas()
    st.zoom_cv.resize(600, 600)
    st.zoom_cv.set_page(S.default_items([str(st.a), str(st.b)]))
    st.zoom_cv.show()
    st.ctx.app.processEvents()
    st.zoom_cv.grab()  # 强制画一帧：把两张图解进缓存

    def _notch(dy: int, pos=None) -> None:
        """给画布发一格滚轮（+120 上滚/放大，-120 下滚/缩小），处理事件。"""
        p = pos or QPointF(st.zoom_cv.width() / 2, st.zoom_cv.height() / 2)
        st.ctx.app.sendEvent(
            st.zoom_cv,
            _QWheelEvent(
                p,
                st.zoom_cv.mapToGlobal(p.toPoint()),
                QPoint(0, 0),
                QPoint(0, dy),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            ),
        )
        for _ in range(2):
            st.ctx.app.processEvents()
    st._notch = _notch

    ok(
        "载页默认倍率 = 适配可视区（不缩放）",
        abs(st.zoom_cv._zoom - 1.0) < 1e-9
        and abs(st.zoom_cv._px_per_unit - st.zoom_cv._fit_ppu) < 1e-9,
    )

    st.anchor = QPointF(st.zoom_cv.width() * 0.6, st.zoom_cv.height() * 0.4)
    unit_before = st.zoom_cv._to_units(st.anchor)
    items_before = st.zoom_cv.items()
    st._notch(120, st.anchor)
    unit_after = st.zoom_cv._to_units(st.anchor)
    ok(
        "滚轮放大：锚点下的图坐标不动（以光标为锚）",
        abs(unit_before[0] - unit_after[0]) < 1e-6
        and abs(unit_before[1] - unit_after[1]) < 1e-6,
        f"{unit_before} → {unit_after}",
    )
    ok(
        "缩放只改几何：items 原样、图缓存不重解码",
        st.zoom_cv.items() == items_before
        and len(st.zoom_cv._images) == 2
        and st.zoom_cv._px_per_unit > st.zoom_cv._fit_ppu,
        f"ppu={st.zoom_cv._px_per_unit:.2f} fit={st.zoom_cv._fit_ppu:.2f}",
    )
    ok(
        "一格滚轮 = 1.15 倍",
        abs(st.zoom_cv._zoom - _canvas_mod.WHEEL_ZOOM_STEP) < 1e-6,
        f"zoom={st.zoom_cv._zoom:.4f}",
    )
    wheel_src = (
        ROOT
        / "desktop"
        / "components"
        / "imposition"
        / "canvas"
        / "interaction.py"
    ).read_text(encoding="utf-8")
    wheel_src = wheel_src[
        wheel_src.index("def wheelEvent") : wheel_src.index("def _zoom_at")
    ]
    ok(
        "滚轮事件不直接要重绘（重绘归帧窗口，减渲染的口子）",
        "self.update()" not in wheel_src,
    )
    ok("连发第一滚：启动帧窗口（不立刻重绘）", st.zoom_cv._wheel_timer.isActive())
    st._notch(120, st.anchor)
    st._notch(120, st.anchor)
    ok(
        "窗口内的后续滚动只挂起、不重复开窗（按帧合并）",
        st.zoom_cv._wheel_timer.isActive() and st.zoom_cv._wheel_paint_pending,
    )
    st.zoom_cv._wheel_timer.stop()
    st.zoom_cv._on_wheel_frame()
    ok(
        "窗口到期：画一帧，还有挂起就滚到下一帧（快速档保持）",
        st.zoom_cv._wheel_paint_pending is False
        and st.zoom_cv._wheel_timer.isActive()
        and st.zoom_cv._wheel_burst,
    )
    st.zoom_cv._wheel_timer.stop()
    st.zoom_cv._on_wheel_frame()
    ok("滚动停稳：关快速档、补一帧高质量重绘", st.zoom_cv._wheel_burst is False)
    for _ in range(40):
        st.zoom_cv._zoom_at(QPointF(300, 300), 10.0)
    ok(
        "放大利住在上限（相对适配基准）",
        abs(st.zoom_cv._zoom - _canvas_mod.ZOOM_MAX) < 1e-9,
        f"zoom={st.zoom_cv._zoom}",
    )
    for _ in range(40):
        st.zoom_cv._zoom_at(QPointF(300, 300), 0.01)
    ok(
        "缩不利住在下限",
        abs(st.zoom_cv._zoom - _canvas_mod.ZOOM_MIN) < 1e-9,
        f"zoom={st.zoom_cv._zoom}",
    )
    st.zoom_cv.refit()  # 钳制测试把倍率利在了下限：先归一再放大
    st.zoom_cv._zoom_at(QPointF(300, 300), 1.5)
    ppu_before = st.zoom_cv._px_per_unit
    st.zoom_cv.resize(500, 500)
    st.ctx.app.processEvents()
    ok(
        "窗口尺寸变化保留滚轮倍率（不打回原形）",
        abs(st.zoom_cv._zoom - 1.5) < 1e-9
        and abs(st.zoom_cv._px_per_unit - st.zoom_cv._fit_ppu * 1.5) < 1e-9
        and not math.isclose(st.zoom_cv._px_per_unit, ppu_before),
    )
    st.zoom_cv.refit()
    ok(
        "refit 归一倍率（回到打开时的样子）",
        abs(st.zoom_cv._zoom - 1.0) < 1e-9
        and abs(st.zoom_cv._px_per_unit - st.zoom_cv._fit_ppu) < 1e-9,
    )
    st.zoom_cv.set_page(S.default_items([str(st.a), str(st.b)]))
    ok("载页归一倍率（换页回'打开就能看全'）", abs(st.zoom_cv._zoom - 1.0) < 1e-9)
    st.zoom_cv.clear_page()
    st._notch(120)
    ok("空画布滚轮不炸、不动倍率", abs(st.zoom_cv._zoom - 1.0) < 1e-9)
    st.zoom_cv.deleteLater()

