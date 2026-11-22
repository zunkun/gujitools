# -*- coding: utf-8 -*-
"""1~5 / 5b / 6~7"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import make_image
    from desktop.components.viewers.image_zoom_dialog import (
        MAX_RENDER_EDGE, MAX_ZOOM, MIN_RENDER_EDGE, MIN_ZOOM, PAN_MARGIN_RATIO,
        RENDER_HEADROOM,
        ZOOM_STOPS, ImageZoomDialog, ZoomableCanvas, ZoomTarget, save_image,
    )
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
    from PySide6.QtWidgets import QGraphicsView
    from PySide6.QtGui import (
        QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent,
    )
    import numpy as np
    from tests.selftests._context import ok, pump
    st.canvas = ZoomableCanvas()
    st.canvas.resize(800, 600)
    st.canvas.show()
    pump(st.app, times=4)
    st.canvas.set_image(make_image(1000, 1400, marks=True))
    pump(st.app, times=4)

    ok("装图后进入适应窗口（整图可见）",
       st.canvas.has_image and st.canvas.zoom < 1.0, f"zoom={st.canvas.zoom:.3f}")
    fit_zoom = st.canvas.zoom

    st.canvas.set_zoom(1.0)
    dpr = st.canvas.devicePixelRatioF() or 1.0
    ok("100% = 一个图片像素对一个设备像素（变换比例 = 倍率 ÷ dpr）",
       abs(st.canvas.transform().m11() * dpr - 1.0) < 1e-6,
       f"m11={st.canvas.transform().m11():.6f} dpr={dpr}")

    for _ in range(40):
        st.canvas.zoom_in()
    ok("放大连点夹在上限档位", st.canvas.zoom == MAX_ZOOM, str(st.canvas.zoom))
    ok("倍率始终落在档位表上（连点不漂移）",
       any(abs(st.canvas.zoom - stop) < 1e-9 for stop in ZOOM_STOPS),
       str(st.canvas.zoom))
    for _ in range(40):
        st.canvas.zoom_out()
    ok("缩小连点夹在下限档位", st.canvas.zoom == MIN_ZOOM, str(st.canvas.zoom))
    st.canvas.fit()
    ok("适应窗口能回到初始倍率", abs(st.canvas.zoom - fit_zoom) < 1e-6,
       f"{st.canvas.zoom:.4f} vs {fit_zoom:.4f}")

    # 锚点缩放：光标下的场景点缩放前后应基本不动。
    # ⚠️ 从 100% 起（内容比视口大）：否则 centerOn 会被滚动范围夹住，
    # 锚点本来就不可能精确保持，测出来的失败是假的。
    # ⚠️ 必须先把布局跑完再取基准：set_zoom(1.0) 会让滚动条出现、视口跟着
    # resize，而 resizeAnchor 会把视图重新居中——基准取在 resize 之前的话，
    # 测出来的"漂移"其实是 resize 造成的，与被测逻辑无关（踩过）。
    st.canvas.set_zoom(1.0)
    pump(st.app, times=4)
    anchor = QPointF(st.canvas.viewport().width() * 0.35,
                     st.canvas.viewport().height() * 0.4)
    global_pos = st.canvas.viewport().mapToGlobal(anchor.toPoint())
    st.app.sendEvent(st.canvas.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, anchor, global_pos, Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    ))
    before = st.canvas.mapToScene(anchor.toPoint())
    st.app.sendEvent(st.canvas.viewport(), QWheelEvent(
        anchor, global_pos, QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    ))
    pump(st.app, times=2)
    after = st.canvas.mapToScene(anchor.toPoint())
    ok("滚轮向上是放大", st.canvas.zoom > 1.0, f"{st.canvas.zoom:.3f}")
    ok("滚轮以光标为锚点（该场景点精确不动）",
       abs(before.x() - after.x()) < 1.0 and abs(before.y() - after.y()) < 1.0,
       f"before=({before.x():.1f},{before.y():.1f}) "
       f"after=({after.x():.1f},{after.y():.1f})")

    zoom_before_down = st.canvas.zoom
    st.app.sendEvent(st.canvas.viewport(), QWheelEvent(
        anchor, global_pos, QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    ))
    pump(st.app, times=2)
    ok("滚轮向下是缩小", st.canvas.zoom < zoom_before_down,
       f"{zoom_before_down:.3f} → {st.canvas.zoom:.3f}")

    # 连续多步：锚点漂移不能累积（曾经用 centerOn 补偏差，每步残留 ~0.9px
    # 会被滚轮连续事件叠起来，滚十几格光标下的位置就明显跑偏）
    worst = 0.0
    target = st.canvas.mapToScene(anchor.toPoint())
    for step in range(8):
        st.app.sendEvent(st.canvas.viewport(), QWheelEvent(
            anchor, global_pos, QPoint(0, 0),
            QPoint(0, 120 if step % 2 == 0 else -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        ))
        pump(st.app, times=2)
        now = st.canvas.mapToScene(anchor.toPoint())
        worst = max(worst, abs(now.x() - target.x()), abs(now.y() - target.y()))
    ok("连续 8 次滚轮后锚点漂移不累积（<1px）", worst < 1.0, f"最差 {worst:.3f}px")

    ok("左键拖拽平移已开启且未被禁用",
       st.canvas.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
       and not st.canvas.isInteractive() is False,
       str(st.canvas.dragMode()))
    ok("画布不抢焦点（方向键要留给弹窗翻页）",
       st.canvas.focusPolicy() == Qt.FocusPolicy.NoFocus,
       str(st.canvas.focusPolicy()))

    def dblclick() -> None:
        st.app.sendEvent(st.canvas.viewport(), QMouseEvent(
            QEvent.Type.MouseButtonDblClick, QPointF(200, 200),
            st.canvas.viewport().mapToGlobal(QPoint(200, 200)),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))

    # 双击切换。⚠️ 基准必须**现取**：视口尺寸会随滚动条出现而变化，用最开始
    # 记录的 fit_zoom 比会得到假失败（踩过）。
    st.canvas.fit()
    fit_now = st.canvas.zoom
    st.canvas.set_zoom(0.5)
    dblclick()
    ok("双击从任意倍率切到 100%", abs(st.canvas.zoom - 1.0) < 1e-6,
       f"{st.canvas.zoom:.3f}")
    dblclick()
    ok("再双击回到适应窗口", abs(st.canvas.zoom - fit_now) < 1e-6,
       f"{st.canvas.zoom:.4f} vs {fit_now:.4f}")

    # ⚠️ 几何/朝向断言一律用 image_rect()：sceneRect() 为了"不缩放也能拖"被
    # 居中**外加了留白**，拿它比尺寸会得出"旋转后没互换"这种假失败。
    rect_before = st.canvas.image_rect()
    st.canvas.rotate_clockwise()
    rect_after = st.canvas.image_rect()
    ok("旋转 90° 后图片占位宽高互换",
       abs(rect_before.width() - rect_after.height()) < 1.5
       and abs(rect_before.height() - rect_after.width()) < 1.5,
       f"{rect_before.size()} → {rect_after.size()}")
    st.canvas.rotate_counterclockwise()
    ok("反向旋转回到原朝向",
       abs(st.canvas.image_rect().width() - rect_before.width()) < 1.5,
       str(st.canvas.image_rect().size()))

    st.canvas.flip_horizontal()
    flipped_rect = st.canvas.image_rect()
    ok("水平翻转后图片占位落到负坐标（镜像轴在 0）",
       flipped_rect.left() <= -rect_before.width() + 1.5, str(flipped_rect))
    ok("翻转后图片占位不变大也不变小（完整可见）",
       abs(flipped_rect.width() - rect_before.width()) < 1.5, str(flipped_rect.size()))
    st.canvas.flip_horizontal()
    st.canvas.flip_vertical()
    ok("垂直翻转同理（状态可逆）",
       st.canvas._flip_h is False and st.canvas._flip_v is True,
       f"h={st.canvas._flip_h} v={st.canvas._flip_v}")
    st.canvas.flip_vertical()
    st.canvas.fit()
    pump(st.app, times=3)
    viewport = st.canvas.viewport()
    scene_rect = st.canvas._scene.sceneRect()
    image_rect = st.canvas.image_rect()
    ok("适应窗口时场景矩形比图片大（留出了可拖范围）",
       scene_rect.width() > image_rect.width() + 1.0
       and scene_rect.height() > image_rect.height() + 1.0,
       f"场景 {scene_rect.size()} vs 图片 {image_rect.size()}")
    # ⚠️ 只能看**跨度**：QGraphicsView 给滚动条的 [min,max] 原点会随场景原点漂移
    # （实测 min/max 都是负数），拿 maximum() 判定会得出"没有范围"的假结论。
    hbar, vbar = st.canvas.horizontalScrollBar(), st.canvas.verticalScrollBar()
    h_span = hbar.maximum() - hbar.minimum()
    v_span = vbar.maximum() - vbar.minimum()
    want_h = 2 * PAN_MARGIN_RATIO * viewport.width()
    want_v = 2 * PAN_MARGIN_RATIO * viewport.height()
    ok("适应窗口时滚动范围 = 两侧留白（视口的 25%×2）",
       h_span > 0 and v_span > 0
       and abs(h_span - want_h) <= 4 and abs(v_span - want_v) <= 4,
       f"横向跨度 {h_span} 期望 {want_h:.0f}；纵向 {v_span} 期望 {want_v:.0f}")
    grab = QPointF(viewport.width() / 2, viewport.height() / 2)
    global_pos = viewport.mapToGlobal(grab.toPoint())

    def drag_by(dx: float, dy: float) -> tuple[float, float]:
        """在画布中心模拟一次鼠标拖拽，返回光标下场景点的位移。"""
        scale = st.canvas.transform().m11()
        anchor = st.canvas.mapToScene(grab.toPoint())
        st.app.sendEvent(viewport, QMouseEvent(
            QEvent.Type.MouseButtonPress, grab, global_pos,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        for step in range(1, 7):
            point = QPointF(grab.x() + dx * step / 6, grab.y() + dy * step / 6)
            st.app.sendEvent(viewport, QMouseEvent(
                QEvent.Type.MouseMove, point, viewport.mapToGlobal(point.toPoint()),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ))
            pump(st.app, times=1)
        st.app.sendEvent(viewport, QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(grab.x() + dx, grab.y() + dy),
            viewport.mapToGlobal(QPointF(grab.x() + dx, grab.y() + dy).toPoint()),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        pump(st.app, times=2)
        moved = st.canvas.mapToScene(grab.toPoint())
        return (moved.x() - anchor.x(), moved.y() - anchor.y()) if scale else (0.0, 0.0)

    delta = drag_by(-60, -30)
    expected = (60 / st.canvas.transform().m11(), 30 / st.canvas.transform().m11())
    ok("适应窗口（未缩放）下拖拽能让图片跟手移动",
       abs(delta[0] - expected[0]) <= 3 and abs(delta[1] - expected[1]) <= 3,
       f"位移 {delta[0]:.1f},{delta[1]:.1f} 期望 {expected[0]:.1f},{expected[1]:.1f}")

    # 留白有限度：狂拖也拖不出视野（图片至少还有一部分在视口里）
    drag_by(-4000, -4000)
    visible = st.canvas.mapToScene(viewport.rect()).intersected(st.canvas.image_rect())
    ok("留白有限度：狂拖之后图片仍有一部分在视野内",
       not visible.isEmpty(), f"可见部分 {visible.size()}")
    st.canvas.set_image(make_image(4, 2, marks=True))
    plain = st.canvas.export_image()
    assert plain is not None          # ⚠️ 画布上有图时导出不会返回空
    ok("未做变换时导出即原图", plain.size().width() == 4, str(plain.size()))
    st.canvas.flip_horizontal()
    flipped = st.canvas.export_image()
    assert flipped is not None
    ok("导出已应用水平翻转（左右像素真的换了）",
       flipped.pixelColor(3, 0) == QColor("#ff0000")
       and flipped.pixelColor(0, 0) == QColor("#0000ff"),
       f"({flipped.pixelColor(3, 0).name()}, {flipped.pixelColor(0, 0).name()})")
    st.canvas.flip_horizontal()
    st.canvas.rotate_clockwise()
    rotated = st.canvas.export_image()
    assert rotated is not None
    ok("导出已应用旋转（尺寸互换）",
       rotated.width() == 2 and rotated.height() == 4, str(rotated.size()))
    ok("导出与屏幕用同一套变换（旋转+翻转组合一致）",
       st.canvas._rotation == 90 and st.canvas._flip_h is False, "")

    png_path = st.tmp / "out.png"
    ok("保存 PNG 成功（无损）",
       save_image(plain, png_path)
       and png_path.stat().st_size > 0, "")
    ok("PNG 回读尺寸与导出图一致",
       QImage(str(png_path)).size() == plain.size(),
       str(QImage(str(png_path)).size()))

    # JPEG 质量参数必须真的传下去（用噪声图才看得出差别：纯色图两种质量都极小）
    import numpy as np

    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, (240, 240, 3), dtype=np.uint8)
    noisy = QImage(arr.data, 240, 240, 240 * 3,
                   QImage.Format.Format_RGB888).copy()
    q95_path = st.tmp / "q95.jpg"
    q30_path = st.tmp / "q30.jpg"
    ok("保存 JPEG 成功", save_image(noisy, q95_path, 95), "")
    ok("JPEG 质量参数生效（q30 明显小于 q95）",
       save_image(noisy, q30_path, 30)
       and q30_path.stat().st_size < q95_path.stat().st_size * 0.7,
       f"q95={q95_path.stat().st_size} q30={q30_path.stat().st_size}")
    ok("JPEG 回读尺寸不变",
       QImage(str(q95_path)).size() == noisy.size(),
       str(QImage(str(q95_path)).size()))

    st.canvas.clear()
    ok("clear 后不再持有图片（关窗释放内存）", not st.canvas.has_image, "")

