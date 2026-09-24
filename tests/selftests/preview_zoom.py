# -*- coding: utf-8 -*-
"""图片预览弹窗自测：缩放语义、锚点、翻转旋转、导出、翻页、接线。

断言线（都只看可观测行为，不看实现细节）：

1. **缩放语义**：1.0 = 100% = 1 图片像素对 1 设备像素 → 视图变换比例 = 倍率 ÷ dpr；
2. **档位**：放大/缩小走 ``ZOOM_STOPS``，两端夹在 MIN/MAX_ZOOM（连点不越界）；
3. **锚点缩放**：滚轮以光标下的那一点为不动点（缩放后该场景点仍落在光标处）；
4. **双击**在 100% 与适应窗口之间切换；
5. **旋转 90°** 后场景宽高互换、**翻转**后落到负坐标但仍完整可见；
6. **导出**：已应用翻转/旋转、尺寸随旋转互换、翻转真的换了左右像素；
7. **保存**：PNG 与 JPEG 都能写出，JPEG 有损（体积更小）；
8. **翻页**：两端按钮禁用、边界不回绕、翻页重新渲染、状态条给出页面与尺寸；
9. **渲染密度** = 视口物理长边 × 余量，并受 ``ZoomTarget.cap`` 与全局上限约束；
10. **打印效果按目标边长重新排版**（``print_spec['target_edge']``）——不是把
    1600px 的合成图放大；
11. **双击 ``ImageView`` 不留手绘框残影**（回归：ghost/new_start 必须清空）；
12. **四个宿主都接上了**（调 ``_init_zoom_popup`` + 实现 ``_zoom_target``）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

NAME = "preview_zoom"
DEPENDS: list[str] = []
TITLE = "图片预览弹窗"

#: 必须接上放大弹窗的四个预览宿主
HOST_FILES = [
    "desktop/components/viewers/image_viewer.py",
    "desktop/components/viewers/pdf_viewer.py",
    "desktop/components/viewers/rembg_viewer.py",
    "desktop/components/viewers/print_preview.py",
]


def make_image(width: int, height: int, marks: bool = False):
    """造一张测试图；marks=True 时在左上/右上放不同颜色（验翻转方向用）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    if marks:
        image.setPixelColor(0, 0, QColor("#ff0000"))          # 左上 红
        image.setPixelColor(width - 1, 0, QColor("#0000ff"))  # 右上 蓝
    return image


def rgb_array(image):
    """QImage → (h, w, 3) 的 float 数组（去掉行填充）。"""
    import numpy as np
    from PySide6.QtGui import QImage

    img = image.convertToFormat(QImage.Format_RGB888)
    raw = np.frombuffer(bytes(img.constBits()), dtype=np.uint8)
    raw = raw[: img.height() * img.bytesPerLine()]
    return raw.reshape(img.height(), img.bytesPerLine())[
        :, : img.width() * 3
    ].reshape(img.height(), img.width(), 3).astype(float)


class _FakeWorker:
    """替身 worker：不真渲染，直接把给定图发回来（隔离弹窗自身逻辑）。

    ⚠️ 真 worker 是 ``QObject`` + ``run`` 槽 + ``finished`` 信号，弹窗只依赖
    这三样，所以替身必须长得一样（否则测的是替身而不是弹窗）。
    """

    def __init__(self, image, log: list):
        from PySide6.QtCore import QObject, Signal, Slot

        self._log = log

        class Worker(QObject):
            finished = Signal(int, object, str)
            failed = Signal(int, str)

            def __init__(self, image):
                super().__init__()
                self._image = image

            @Slot()
            def run(self):
                if self._image is None:
                    self.failed.emit(0, "没有图")
                else:
                    self.finished.emit(0, self._image, "")

        _ = (Slot,)
        self.instance = Worker(image)


def sharpness(image) -> float:
    """Laplacian 方差：越高越锐（糊图的高频被抹掉，这个值会明显掉）。"""
    import numpy as np

    gray = rgb_array(image).mean(axis=2)
    lap = (
        -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    return float(lap.var())


def run(ctx) -> None:
    from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
    from PySide6.QtGui import (
        QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent,
    )
    from PySide6.QtWidgets import QGraphicsView

    from desktop.components.viewers.image_view import ImageView
    from desktop.components.viewers.image_zoom_dialog import (
        MAX_RENDER_EDGE, MAX_ZOOM, MIN_RENDER_EDGE, MIN_ZOOM, PAN_MARGIN_RATIO,
        RENDER_HEADROOM,
        ZOOM_STOPS, ImageZoomDialog, ZoomableCanvas, ZoomTarget, save_image,
    )
    from tests.selftests._context import ok, pump

    root = Path(__file__).resolve().parents[2]
    app = ctx.app
    tmp = Path(tempfile.mkdtemp(prefix="guji_zoom_"))

    # ---------------------------------------------------------------- 1~5
    canvas = ZoomableCanvas()
    canvas.resize(800, 600)
    canvas.show()
    pump(app, times=4)
    canvas.set_image(make_image(1000, 1400, marks=True))
    pump(app, times=4)

    ok("装图后进入适应窗口（整图可见）",
       canvas.has_image and canvas.zoom < 1.0, f"zoom={canvas.zoom:.3f}")
    fit_zoom = canvas.zoom

    canvas.set_zoom(1.0)
    dpr = canvas.devicePixelRatioF() or 1.0
    ok("100% = 一个图片像素对一个设备像素（变换比例 = 倍率 ÷ dpr）",
       abs(canvas.transform().m11() * dpr - 1.0) < 1e-6,
       f"m11={canvas.transform().m11():.6f} dpr={dpr}")

    for _ in range(40):
        canvas.zoom_in()
    ok("放大连点夹在上限档位", canvas.zoom == MAX_ZOOM, str(canvas.zoom))
    ok("倍率始终落在档位表上（连点不漂移）",
       any(abs(canvas.zoom - stop) < 1e-9 for stop in ZOOM_STOPS),
       str(canvas.zoom))
    for _ in range(40):
        canvas.zoom_out()
    ok("缩小连点夹在下限档位", canvas.zoom == MIN_ZOOM, str(canvas.zoom))
    canvas.fit()
    ok("适应窗口能回到初始倍率", abs(canvas.zoom - fit_zoom) < 1e-6,
       f"{canvas.zoom:.4f} vs {fit_zoom:.4f}")

    # 锚点缩放：光标下的场景点缩放前后应基本不动。
    # ⚠️ 从 100% 起（内容比视口大）：否则 centerOn 会被滚动范围夹住，
    # 锚点本来就不可能精确保持，测出来的失败是假的。
    # ⚠️ 必须先把布局跑完再取基准：set_zoom(1.0) 会让滚动条出现、视口跟着
    # resize，而 resizeAnchor 会把视图重新居中——基准取在 resize 之前的话，
    # 测出来的"漂移"其实是 resize 造成的，与被测逻辑无关（踩过）。
    canvas.set_zoom(1.0)
    pump(app, times=4)
    anchor = QPointF(canvas.viewport().width() * 0.35,
                     canvas.viewport().height() * 0.4)
    global_pos = canvas.viewport().mapToGlobal(anchor.toPoint())
    app.sendEvent(canvas.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, anchor, global_pos, Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    ))
    before = canvas.mapToScene(anchor.toPoint())
    app.sendEvent(canvas.viewport(), QWheelEvent(
        anchor, global_pos, QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    ))
    pump(app, times=2)
    after = canvas.mapToScene(anchor.toPoint())
    ok("滚轮向上是放大", canvas.zoom > 1.0, f"{canvas.zoom:.3f}")
    ok("滚轮以光标为锚点（该场景点精确不动）",
       abs(before.x() - after.x()) < 1.0 and abs(before.y() - after.y()) < 1.0,
       f"before=({before.x():.1f},{before.y():.1f}) "
       f"after=({after.x():.1f},{after.y():.1f})")

    zoom_before_down = canvas.zoom
    app.sendEvent(canvas.viewport(), QWheelEvent(
        anchor, global_pos, QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    ))
    pump(app, times=2)
    ok("滚轮向下是缩小", canvas.zoom < zoom_before_down,
       f"{zoom_before_down:.3f} → {canvas.zoom:.3f}")

    # 连续多步：锚点漂移不能累积（曾经用 centerOn 补偏差，每步残留 ~0.9px
    # 会被滚轮连续事件叠起来，滚十几格光标下的位置就明显跑偏）
    worst = 0.0
    target = canvas.mapToScene(anchor.toPoint())
    for step in range(8):
        app.sendEvent(canvas.viewport(), QWheelEvent(
            anchor, global_pos, QPoint(0, 0),
            QPoint(0, 120 if step % 2 == 0 else -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        ))
        pump(app, times=2)
        now = canvas.mapToScene(anchor.toPoint())
        worst = max(worst, abs(now.x() - target.x()), abs(now.y() - target.y()))
    ok("连续 8 次滚轮后锚点漂移不累积（<1px）", worst < 1.0, f"最差 {worst:.3f}px")

    ok("左键拖拽平移已开启且未被禁用",
       canvas.dragMode() == QGraphicsView.DragMode.ScrollHandDrag
       and not canvas.isInteractive() is False,
       str(canvas.dragMode()))
    ok("画布不抢焦点（方向键要留给弹窗翻页）",
       canvas.focusPolicy() == Qt.FocusPolicy.NoFocus,
       str(canvas.focusPolicy()))

    def dblclick() -> None:
        app.sendEvent(canvas.viewport(), QMouseEvent(
            QEvent.Type.MouseButtonDblClick, QPointF(200, 200),
            canvas.viewport().mapToGlobal(QPoint(200, 200)),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))

    # 双击切换。⚠️ 基准必须**现取**：视口尺寸会随滚动条出现而变化，用最开始
    # 记录的 fit_zoom 比会得到假失败（踩过）。
    canvas.fit()
    fit_now = canvas.zoom
    canvas.set_zoom(0.5)
    dblclick()
    ok("双击从任意倍率切到 100%", abs(canvas.zoom - 1.0) < 1e-6,
       f"{canvas.zoom:.3f}")
    dblclick()
    ok("再双击回到适应窗口", abs(canvas.zoom - fit_now) < 1e-6,
       f"{canvas.zoom:.4f} vs {fit_now:.4f}")

    # ⚠️ 几何/朝向断言一律用 image_rect()：sceneRect() 为了"不缩放也能拖"被
    # 居中**外加了留白**，拿它比尺寸会得出"旋转后没互换"这种假失败。
    rect_before = canvas.image_rect()
    canvas.rotate_clockwise()
    rect_after = canvas.image_rect()
    ok("旋转 90° 后图片占位宽高互换",
       abs(rect_before.width() - rect_after.height()) < 1.5
       and abs(rect_before.height() - rect_after.width()) < 1.5,
       f"{rect_before.size()} → {rect_after.size()}")
    canvas.rotate_counterclockwise()
    ok("反向旋转回到原朝向",
       abs(canvas.image_rect().width() - rect_before.width()) < 1.5,
       str(canvas.image_rect().size()))

    canvas.flip_horizontal()
    flipped_rect = canvas.image_rect()
    ok("水平翻转后图片占位落到负坐标（镜像轴在 0）",
       flipped_rect.left() <= -rect_before.width() + 1.5, str(flipped_rect))
    ok("翻转后图片占位不变大也不变小（完整可见）",
       abs(flipped_rect.width() - rect_before.width()) < 1.5, str(flipped_rect.size()))
    canvas.flip_horizontal()
    canvas.flip_vertical()
    ok("垂直翻转同理（状态可逆）",
       canvas._flip_h is False and canvas._flip_v is True,
       f"h={canvas._flip_h} v={canvas._flip_v}")
    canvas.flip_vertical()

    # ---------------------------------------------------------------- 5b
    # 「不缩放也能拖」：图片在适应窗口时正好铺满视口 → Qt 的滚动范围是 0，
    # 此时 ScrollHandDrag 一点都拖不动（用户报的现象）。修法是场景矩形外加留白。
    canvas.fit()
    pump(app, times=3)
    viewport = canvas.viewport()
    scene_rect = canvas._scene.sceneRect()
    image_rect = canvas.image_rect()
    ok("适应窗口时场景矩形比图片大（留出了可拖范围）",
       scene_rect.width() > image_rect.width() + 1.0
       and scene_rect.height() > image_rect.height() + 1.0,
       f"场景 {scene_rect.size()} vs 图片 {image_rect.size()}")
    # ⚠️ 只能看**跨度**：QGraphicsView 给滚动条的 [min,max] 原点会随场景原点漂移
    # （实测 min/max 都是负数），拿 maximum() 判定会得出"没有范围"的假结论。
    hbar, vbar = canvas.horizontalScrollBar(), canvas.verticalScrollBar()
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
        scale = canvas.transform().m11()
        anchor = canvas.mapToScene(grab.toPoint())
        app.sendEvent(viewport, QMouseEvent(
            QEvent.Type.MouseButtonPress, grab, global_pos,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        for step in range(1, 7):
            point = QPointF(grab.x() + dx * step / 6, grab.y() + dy * step / 6)
            app.sendEvent(viewport, QMouseEvent(
                QEvent.Type.MouseMove, point, viewport.mapToGlobal(point.toPoint()),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            ))
            pump(app, times=1)
        app.sendEvent(viewport, QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(grab.x() + dx, grab.y() + dy),
            viewport.mapToGlobal(QPointF(grab.x() + dx, grab.y() + dy).toPoint()),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        pump(app, times=2)
        moved = canvas.mapToScene(grab.toPoint())
        return (moved.x() - anchor.x(), moved.y() - anchor.y()) if scale else (0.0, 0.0)

    delta = drag_by(-60, -30)
    expected = (60 / canvas.transform().m11(), 30 / canvas.transform().m11())
    ok("适应窗口（未缩放）下拖拽能让图片跟手移动",
       abs(delta[0] - expected[0]) <= 3 and abs(delta[1] - expected[1]) <= 3,
       f"位移 {delta[0]:.1f},{delta[1]:.1f} 期望 {expected[0]:.1f},{expected[1]:.1f}")

    # 留白有限度：狂拖也拖不出视野（图片至少还有一部分在视口里）
    drag_by(-4000, -4000)
    visible = canvas.mapToScene(viewport.rect()).intersected(canvas.image_rect())
    ok("留白有限度：狂拖之后图片仍有一部分在视野内",
       not visible.isEmpty(), f"可见部分 {visible.size()}")

    # ---------------------------------------------------------------- 6~7
    canvas.set_image(make_image(4, 2, marks=True))
    ok("未做变换时导出即原图", canvas.export_image().size().width() == 4,
       str(canvas.export_image().size()))
    canvas.flip_horizontal()
    flipped = canvas.export_image()
    ok("导出已应用水平翻转（左右像素真的换了）",
       flipped.pixelColor(3, 0) == QColor("#ff0000")
       and flipped.pixelColor(0, 0) == QColor("#0000ff"),
       f"({flipped.pixelColor(3, 0).name()}, {flipped.pixelColor(0, 0).name()})")
    canvas.flip_horizontal()
    canvas.rotate_clockwise()
    rotated = canvas.export_image()
    ok("导出已应用旋转（尺寸互换）",
       rotated.width() == 2 and rotated.height() == 4, str(rotated.size()))
    ok("导出与屏幕用同一套变换（旋转+翻转组合一致）",
       canvas._rotation == 90 and canvas._flip_h is False, "")

    png_path = tmp / "out.png"
    ok("保存 PNG 成功（无损）",
       save_image(canvas.export_image(), png_path)
       and png_path.stat().st_size > 0, "")
    ok("PNG 回读尺寸与导出图一致",
       QImage(str(png_path)).size() == canvas.export_image().size(),
       str(QImage(str(png_path)).size()))

    # JPEG 质量参数必须真的传下去（用噪声图才看得出差别：纯色图两种质量都极小）
    import numpy as np

    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, (240, 240, 3), dtype=np.uint8)
    noisy = QImage(arr.data, 240, 240, 240 * 3,
                   QImage.Format_RGB888).copy()
    q95_path = tmp / "q95.jpg"
    q30_path = tmp / "q30.jpg"
    ok("保存 JPEG 成功", save_image(noisy, q95_path, 95), "")
    ok("JPEG 质量参数生效（q30 明显小于 q95）",
       save_image(noisy, q30_path, 30)
       and q30_path.stat().st_size < q95_path.stat().st_size * 0.7,
       f"q95={q95_path.stat().st_size} q30={q30_path.stat().st_size}")
    ok("JPEG 回读尺寸不变",
       QImage(str(q95_path)).size() == noisy.size(),
       str(QImage(str(q95_path)).size()))

    canvas.clear()
    ok("clear 后不再持有图片（关窗释放内存）", not canvas.has_image, "")

    # ---------------------------------------------------------------- 8~9
    edges: list[int] = []
    fake = {"image": None}

    def render(edge: int):
        edges.append(edge)
        return _FakeWorker(fake["image"], []).instance

    def factory(index: int):
        if not (0 <= index < 3):
            return None
        return ZoomTarget(
            render=render, note=f"第 {index + 1}/3 页", stem=f"p{index + 1}",
            count=3,
        )

    dialog = ImageZoomDialog(factory=factory)
    dialog.resize(1000, 700)
    dialog.show()
    pump(app, times=4)
    fake["image"] = make_image(1200, 900)
    dialog.show_for(index=1)
    pump(app, times=6)

    ok("弹窗装图成功", dialog.canvas.has_image, dialog.note_label.text())
    ok("状态条给出页面与渲染尺寸",
       "第 2/3 页" in dialog.note_label.text()
       and "渲染 1200×900" in dialog.note_label.text(),
       dialog.note_label.text())
    ok("中间页前后按钮都可点",
       dialog.prev_btn.isEnabled() and dialog.next_btn.isEnabled(), "")
    ok("倍率以百分比显示", dialog.zoom_label.text().endswith("%"),
       dialog.zoom_label.text())

    # ---- 工具条按钮：图标 + 纯中文文案（界面文案口径：按钮不放键名/英文）----
    def icon_pixels(button) -> int:
        """按钮图标里不透明的像素数（用来判断"图标不是空白"）。"""
        image = button.icon().pixmap(QSize(32, 32)).toImage()
        return sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 40
        )

    ok("弹窗标题是「图片预览」", dialog.windowTitle() == "图片预览",
       dialog.windowTitle())
    buttons = {
        "左旋": dialog.rotate_ccw_btn,
        "右旋": dialog.rotate_cw_btn,
        "水平翻转": dialog.flip_h_btn,
        "垂直翻转": dialog.flip_v_btn,
    }
    for label, button in buttons.items():
        ok(f"「{label}」按钮：文案就是这两个字，且带图标",
           button.text() == label and not button.icon().isNull(),
           f"text={button.text()!r} icon_null={button.icon().isNull()}")
        ok(f"「{label}」的图标确实画了图形（不是空白）",
           icon_pixels(button) > 60, f"不透明像素 {icon_pixels(button)}")
    ok("左旋 / 右旋 的图标不同（互为镜像）",
       dialog.rotate_ccw_btn.icon().pixmap(QSize(32, 32)).toImage()
       != dialog.rotate_cw_btn.icon().pixmap(QSize(32, 32)).toImage(), "")
    ok("水平翻转 / 垂直翻转 的图标不同（同一个图形转 90°）",
       dialog.flip_h_btn.icon().pixmap(QSize(32, 32)).toImage()
       != dialog.flip_v_btn.icon().pixmap(QSize(32, 32)).toImage(), "")

    ok("首屏只渲染一次", len(edges) == 1, f"渲染次数={len(edges)}")
    dialog._goto(1)
    pump(app, times=6)
    ok("到最后一页后禁用「下一页」",
       dialog._index == 2 and not dialog.next_btn.isEnabled(), str(dialog._index))
    renders_at_last = len(edges)
    ok("有效翻页会重新渲染", renders_at_last == 2, f"渲染次数={renders_at_last}")
    dialog._goto(1)
    pump(app, times=4)
    ok("末页再点下一页不回绕", dialog._index == 2, str(dialog._index))
    ok("无效翻页不重复渲染", len(edges) == renders_at_last,
       f"渲染次数={len(edges)}")
    dialog._goto(-5)
    pump(app, times=6)
    ok("首页再点上一页不回绕（且禁用）",
       dialog._index == 0 and not dialog.prev_btn.isEnabled(), str(dialog._index))
    ok("跨多页跳转只渲染目标页（不逐页渲染）", len(edges) == 3,
       f"渲染次数={len(edges)}")

    viewport = dialog.canvas.viewport()
    expected = max(MIN_RENDER_EDGE, min(
        MAX_RENDER_EDGE,
        int(round(max(viewport.width(), viewport.height())
                  * (dialog.canvas.devicePixelRatioF() or 1.0)
                  * RENDER_HEADROOM)),
    ))
    ok("渲染密度 = 视口物理长边 × 余量", edges[-1] == expected,
       f"请求 {edges[-1]}，期望 {expected}")
    dialog._target = ZoomTarget(render=render, note="", count=1, cap=900)
    ok("渲染密度受 ZoomTarget.cap 约束（位图别白放大）",
       dialog._render_edge() == 900, str(dialog._render_edge()))
    dialog._target = ZoomTarget(render=render, note="", count=1)
    dialog._max_edge = 5000
    dialog._target = ZoomTarget(render=render, note="", count=1, cap=99999)
    ok("渲染密度有全局上限", dialog._render_edge() <= 5000,
       str(dialog._render_edge()))
    dialog._target = None

    # 恢复成一页正常的（上面为测密度把 _target 换成了测试替身）
    dialog.show_for(index=0)
    pump(app, times=6)
    ok("恢复后停在第一页", dialog._index == 0, str(dialog._index))
    app.sendEvent(dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right,
                                    Qt.KeyboardModifier.NoModifier))
    pump(app, times=6)
    ok("→ 键翻下一页", dialog._index == 1, str(dialog._index))
    app.sendEvent(dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_1,
                                    Qt.KeyboardModifier.NoModifier))
    ok("1 键切到 100%", abs(dialog.canvas.zoom - 1.0) < 1e-6,
       f"{dialog.canvas.zoom:.3f}")
    app.sendEvent(dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R,
                                    Qt.KeyboardModifier.NoModifier))
    ok("R 键顺时针旋转 90°", dialog.canvas._rotation == 90,
       str(dialog.canvas._rotation))

    # ---- 窗口态：min/max 按钮、双击顶部栏全屏、F11、百分比点击复位 ----
    # 用户 17:03~17:08 报：弹窗右上没有最小化/还原（QDialog 默认标题栏只有
    # 关闭）、双击顶部栏要能全屏。⚠️ 全屏切换走 fit() 不触发渲染，放在
    # 渲染计数断言之后才不污染 edges。
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    ok("标题栏带最小化/最大化按钮（QDialog 默认没有，用户找不到「还原」）",
       bool(dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
       and bool(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint),
       hex(int(dialog.windowFlags())))
    QTest.mouseDClick(dialog, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(600, 6))
    pump(app, times=4)
    ok("双击顶部工具栏空白 → 全屏", dialog.isFullScreen(), "")
    QTest.mouseDClick(dialog, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(600, 6))
    pump(app, times=4)
    ok("再双击顶部栏 → 还原", not dialog.isFullScreen(), "")
    QTest.keyClick(dialog, Qt.Key_F11)
    pump(app, times=4)
    ok("F11 → 全屏", dialog.isFullScreen(), "")
    QTest.keyClick(dialog, Qt.Key_F11)
    pump(app, times=4)
    ok("再按 F11 → 还原", not dialog.isFullScreen(), "")
    # 点「百分比」标签 → 回 100%：由 dialog 的 eventFilter 消费按压实现
    dialog.canvas.set_zoom(2.5)
    handled = dialog.eventFilter(
        dialog.zoom_label, QEvent(QEvent.Type.MouseButtonPress)
    )
    ok("百分比标签点击把倍率复位到 100%",
       handled and abs(dialog.canvas.zoom - 1.0) < 1e-6,
       f"handled={handled} zoom={dialog.canvas.zoom:.2f}")
    # ⚠️ 翻页/全屏必须是**窗口级 QShortcut**：只靠 keyPressEvent 在真实 GUI
    # 会掉——焦点在画布/按钮上时方向键被消费或导航走，到不了对话框
    # （离屏 QTest 直接发给对话框测不出来；用户实测「没有实现」即此）。
    from PySide6.QtGui import QShortcut

    sc_keys = {s.key().toString() for s in dialog.findChildren(QShortcut)}
    ok("方向键翻页/全屏走窗口级 QShortcut（不受焦点影响）",
       {"Left", "Right", "F11"} <= sc_keys, str(sorted(sc_keys)))

    dialog.close()
    pump(app, times=3)
    ok("关闭后释放图片与后台线程",
       not dialog.canvas.has_image and not dialog._threads, "")
    dialog.deleteLater()

    empty = ImageZoomDialog(factory=lambda index: None)
    empty.resize(800, 600)
    empty.show()
    empty.show_for(index=0)
    pump(app, times=3)
    ok("没有可预览的页时给出提示且按钮全禁用",
       not empty.canvas.has_image and not empty.download_btn.isEnabled(),
       empty.note_label.text())
    empty.close()
    empty.deleteLater()

    # ---------------------------------------------------------------- 11
    view = ImageView()
    view.resize(600, 500)
    view.set_boxes_editable(True)
    view.set_image(make_image(1000, 1400), boxes=[])
    fired: list[int] = []
    view.double_clicked.connect(lambda: fired.append(1))
    app.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    app.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseButtonDblClick, QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    ok("双击大图发出 double_clicked", len(fired) == 1, str(fired))
    ok("双击不留手绘框残影（ghost / new_start 已清）",
       view._ghost_box is None and view._new_start is None
       and view._mode is None,
       f"ghost={view._ghost_box} start={view._new_start} mode={view._mode}")
    app.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)), Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    ))
    ok("双击不会偷偷落一个框", view._boxes == [], str(view._boxes))
    view.deleteLater()

    # ---------------------------------------------------------------- 10
    # 打印效果必须按 target_edge **重新排版**，而不是把 1600px 的合成图放大
    import numpy as np

    from desktop.workers.preview_worker import PreviewWorker

    # 源图用**有纹理**的（模拟扫描件的网点/纸纹）：纯色图的差异只出现在标题
    # 那一小块，全局 RMSE 会被大片相同的白底稀释掉，测不出真实差别。
    rng = np.random.default_rng(20260924)
    base = np.full((1754, 1240, 3), 235, dtype=np.uint8)
    noise = rng.integers(-28, 29, (1754, 1240, 3), dtype=np.int16)
    textured = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    src_path = tmp / "page.png"
    QImage(textured.data, 1240, 1754, 1240 * 3,
           QImage.Format_RGB888).copy().save(str(src_path))
    base_spec = {
        "args": {"title_printing": True, "title_text": "古籍重製",
                 "title_font_size": 12},
        "index": 0, "total": 1, "name": "page",
    }

    def compose(edge: int, extra: dict):
        captured: dict = {}
        worker = PreviewWorker(
            src_path, longest_edge=edge, print_spec={**base_spec, **extra}
        )
        worker.finished.connect(
            lambda _p, image, _s: captured.update(image=image)
        )
        worker.run()
        return captured.get("image")

    # 两者输出边长相同，差别只在"排版密度"：不指定 target_edge 时是
    # 「按 1600px 密度合成 → 再缩放到请求边长」，指定时才是按请求边长重排。
    upscaled = compose(3000, {})
    big = compose(3000, {"target_edge": 3000})
    ok("不指定 target_edge 时输出边长仍由 longest_edge 决定",
       max(upscaled.width(), upscaled.height()) == 3000,
       f"{upscaled.width()}x{upscaled.height()}")
    ok("指定 target_edge 后长边就是该值",
       max(big.width(), big.height()) == 3000,
       f"{big.width()}x{big.height()}")

    a, b = rgb_array(big), rgb_array(upscaled)
    rows = min(a.shape[0], b.shape[0])  # 两种密度取整会差一行，裁到公共区
    cols = min(a.shape[1], b.shape[1])
    rmse = float(((a[:rows, :cols] - b[:rows, :cols]) ** 2).mean() ** 0.5)
    ok("是「按目标边长重新排版」而不是「把 1600px 合成图放大」",
       rmse > 5.0, f"RMSE={rmse:.2f}")
    ok("重排出来的确实更锐（不是放大的糊图）",
       sharpness(big) > sharpness(upscaled) * 1.2,
       f"重排={sharpness(big):.0f} 放大={sharpness(upscaled):.0f}")

    # ---------------------------------------------------------------- 11
    # 「打印效果」密度约束（2026-09-24）：①合成不得**放大**源图；②给了
    # target_edge 就不能再让 longest_edge 缩一次（白扔细节）；
    # ③longest_edge=0 在 PDF 分支必须返回原始尺寸，而不是历史上那张空图。
    def compose_src(path, longest, spec):
        captured: dict = {}
        worker = PreviewWorker(path, longest_edge=longest, print_spec=spec)
        worker.finished.connect(
            lambda _p, image, _s: captured.update(image=image)
        )
        worker.run()
        return captured.get("image")

    small_path = tmp / "small.png"
    QImage(800, 1131, QImage.Format_RGB888).copy().save(str(small_path))
    # 夹住的是**图片区域**的密度，不是画布（画布还要放标题/纸面留白）。
    # 所以这里不比画布尺寸，而是比"要更大的边长能不能拿到更多像素"——
    # 上限一旦存在，4000 与 8000 必然得到同一张画布。
    ask_4000 = compose_src(small_path, 0, {**base_spec, "target_edge": 4000})
    ask_8000 = compose_src(small_path, 0, {**base_spec, "target_edge": 8000})
    ok("密度有上限：不放大源图（要 4000 与要 8000 得到同一张画布）",
       ask_4000 is not None and ask_4000.size() == ask_8000.size(),
       f"{ask_4000.size()} vs {ask_8000.size()}")
    ok("…而且确实被夹住（没有真按请求边长合成）",
       max(ask_4000.width(), ask_4000.height()) < 4000,
       f"{ask_4000.width()}x{ask_4000.height()}（源图 800x1131）")

    import fitz

    pdf_path = tmp / "one.pdf"
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    pg.insert_text((72, 72), "x")
    doc.save(str(pdf_path))
    doc.close()
    pdf_img = compose_src(pdf_path, 0, None)
    ok("longest_edge=0 在 PDF 分支返回原始尺寸（不再得到空图）",
       pdf_img is not None and not pdf_img.isNull() and pdf_img.width() >= 590,
       f"{pdf_img.width()}x{pdf_img.height()}")

    host_text = (
        root / "desktop/components/viewers/print_preview.py"
    ).read_text(encoding="utf-8")
    ok("第四步主预览：打印效果按 target_edge 重排（密度不写死 1600）",
       "target_edge" in host_text and "MAX_PREVIEW_EDGE" in host_text, "")
    ok("第四步主预览：给了 target_edge 就不再做 longest_edge 缩放",
       "longest_edge=0" in host_text, "")

    # ---------------------------------------------------------------- 12
    for rel in HOST_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        ok(f"{rel}：接上了弹窗", "_init_zoom_popup(self.view)" in text, "")
        ok(f"{rel}：实现了 _zoom_target", "def _zoom_target(" in text, "")

    # 混入 ZoomPopupMixin 不能和既有的 ThumbsMixin/WorkerHost 抢方法：
    # _init_zoom_popup 之前也要能安全调 close_zoom_popup / shutdown_workers
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from desktop.components.viewers.pdf_viewer import PdfViewerWidget
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget

    for cls in (ImageViewerWidget, PdfViewerWidget, RembgPreviewWidget,
                PrintPreviewWidget):
        host = cls()
        mro_ok = True
        try:
            host.close_zoom_popup()   # 还没开过弹窗：必须是无动作而非 AttributeError
            host.shutdown_workers()   # MRO 必须仍落到 WorkerHost 那一版
        except Exception as exc:  # noqa: BLE001
            mro_ok = False
            detail = f"{type(exc).__name__}: {exc}"
        ok(f"{cls.__name__}：混入弹窗后收尾路径仍正常（MRO 无冲突）",
           mro_ok, "" if mro_ok else detail)
        ok(f"{cls.__name__}：双击入口已接上",
           hasattr(host, "_open_zoom_popup") and hasattr(host, "_zoom_target"), "")
        host.deleteLater()

    text = (root / "desktop/components/viewers/image_zoom_dialog.py").read_text(
        encoding="utf-8"
    )
    ok("弹窗不自己拼图片路径（渲染口径交给宿主）",
       "PreviewWorker" not in text, "")
