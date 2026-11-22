# -*- coding: utf-8 -*-
"""8~9 / 工具条按钮：图标 + 纯中文文案（界面文案口径：按钮不放键名/英文） / 窗口态：min/max 按钮、双击顶部栏全屏、F11、百分比点击复位 / 打印按钮：取图走 canvas.export_image()（虚拟图也适用） / 11"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _FakeWorker, make_image
    from desktop.components.viewers.image_view import ImageView
    from desktop.components.viewers.image_zoom_dialog import (
        MAX_RENDER_EDGE, MAX_ZOOM, MIN_RENDER_EDGE, MIN_ZOOM, PAN_MARGIN_RATIO,
        RENDER_HEADROOM,
        ZOOM_STOPS, ImageZoomDialog, ZoomableCanvas, ZoomTarget, save_image,
    )
    from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
    from PySide6.QtGui import (
        QColor, QImage, QKeyEvent, QMouseEvent, QWheelEvent,
    )
    from PySide6.QtGui import QShortcut
    from PySide6.QtTest import QTest
    from tests.selftests._context import ok, pump
    st.edges: list[int] = []
    # ⚠️ 显式标注成 ``dict``：否则推断成 ``dict[str, None]``，后面塞进真图
    #    会被判成类型错误（运行期当然塞得进去）。
    fake: dict = {"image": None}

    def render(edge: int):
        st.edges.append(edge)
        return _FakeWorker(fake["image"], []).instance
    st.render = render

    def factory(index: int):
        if not (0 <= index < 3):
            return None
        return ZoomTarget(
            render=st.render, note=f"第 {index + 1}/3 页", stem=f"p{index + 1}",
            count=3,
        )

    st.dialog = ImageZoomDialog(factory=factory)
    st.dialog.resize(1000, 700)
    st.dialog.show()
    pump(st.app, times=4)
    fake["image"] = make_image(1200, 900)
    st.dialog.show_for(index=1)
    pump(st.app, times=6)

    ok("弹窗装图成功", st.dialog.canvas.has_image, st.dialog.note_label.text())
    ok("状态条给出页面与渲染尺寸",
       "第 2/3 页" in st.dialog.note_label.text()
       and "渲染 1200×900" in st.dialog.note_label.text(),
       st.dialog.note_label.text())
    ok("中间页前后按钮都可点",
       st.dialog.prev_btn.isEnabled() and st.dialog.next_btn.isEnabled(), "")
    ok("倍率以百分比显示", st.dialog.zoom_label.text().endswith("%"),
       st.dialog.zoom_label.text())
    def icon_pixels(button) -> int:
        """按钮图标里不透明的像素数（用来判断"图标不是空白"）。"""
        image = button.icon().pixmap(QSize(32, 32)).toImage()
        return sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 40
        )

    ok("弹窗标题是「图片预览」", st.dialog.windowTitle() == "图片预览",
       st.dialog.windowTitle())
    buttons = {
        "左旋": st.dialog.rotate_ccw_btn,
        "右旋": st.dialog.rotate_cw_btn,
        "水平翻转": st.dialog.flip_h_btn,
        "垂直翻转": st.dialog.flip_v_btn,
    }
    for label, button in buttons.items():
        ok(f"「{label}」按钮：文案就是这两个字，且带图标",
           button.text() == label and not button.icon().isNull(),
           f"text={button.text()!r} icon_null={button.icon().isNull()}")
        ok(f"「{label}」的图标确实画了图形（不是空白）",
           icon_pixels(button) > 60, f"不透明像素 {icon_pixels(button)}")
    ok("左旋 / 右旋 的图标不同（互为镜像）",
       st.dialog.rotate_ccw_btn.icon().pixmap(QSize(32, 32)).toImage()
       != st.dialog.rotate_cw_btn.icon().pixmap(QSize(32, 32)).toImage(), "")
    ok("水平翻转 / 垂直翻转 的图标不同（同一个图形转 90°）",
       st.dialog.flip_h_btn.icon().pixmap(QSize(32, 32)).toImage()
       != st.dialog.flip_v_btn.icon().pixmap(QSize(32, 32)).toImage(), "")

    ok("首屏只渲染一次", len(st.edges) == 1, f"渲染次数={len(st.edges)}")
    st.dialog._goto(1)
    pump(st.app, times=6)
    ok("到最后一页后禁用「下一页」",
       st.dialog._index == 2 and not st.dialog.next_btn.isEnabled(), str(st.dialog._index))
    renders_at_last = len(st.edges)
    ok("有效翻页会重新渲染", renders_at_last == 2, f"渲染次数={renders_at_last}")
    st.dialog._goto(1)
    pump(st.app, times=4)
    ok("末页再点下一页不回绕", st.dialog._index == 2, str(st.dialog._index))
    ok("无效翻页不重复渲染", len(st.edges) == renders_at_last,
       f"渲染次数={len(st.edges)}")
    st.dialog._goto(-5)
    pump(st.app, times=6)
    ok("首页再点上一页不回绕（且禁用）",
       st.dialog._index == 0 and not st.dialog.prev_btn.isEnabled(), str(st.dialog._index))
    ok("跨多页跳转只渲染目标页（不逐页渲染）", len(st.edges) == 3,
       f"渲染次数={len(st.edges)}")

    viewport = st.dialog.canvas.viewport()
    expected = max(MIN_RENDER_EDGE, min(
        MAX_RENDER_EDGE,
        int(round(max(viewport.width(), viewport.height())
                  * (st.dialog.canvas.devicePixelRatioF() or 1.0)
                  * RENDER_HEADROOM)),
    ))
    ok("渲染密度 = 视口物理长边 × 余量", st.edges[-1] == expected,
       f"请求 {st.edges[-1]}，期望 {expected}")
    st.dialog._target = ZoomTarget(render=st.render, note="", count=1, cap=900)
    ok("渲染密度受 ZoomTarget.cap 约束（位图别白放大）",
       st.dialog._render_edge() == 900, str(st.dialog._render_edge()))
    st.dialog._target = ZoomTarget(render=st.render, note="", count=1)
    st.dialog._max_edge = 5000
    st.dialog._target = ZoomTarget(render=st.render, note="", count=1, cap=99999)
    ok("渲染密度有全局上限", st.dialog._render_edge() <= 5000,
       str(st.dialog._render_edge()))
    st.dialog._target = None

    # 恢复成一页正常的（上面为测密度把 _target 换成了测试替身）
    st.dialog.show_for(index=0)
    pump(st.app, times=6)
    ok("恢复后停在第一页", st.dialog._index == 0, str(st.dialog._index))
    st.app.sendEvent(st.dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right,
                                    Qt.KeyboardModifier.NoModifier))
    pump(st.app, times=6)
    ok("→ 键翻下一页", st.dialog._index == 1, str(st.dialog._index))
    st.app.sendEvent(st.dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_1,
                                    Qt.KeyboardModifier.NoModifier))
    ok("1 键切到 100%", abs(st.dialog.canvas.zoom - 1.0) < 1e-6,
       f"{st.dialog.canvas.zoom:.3f}")
    st.app.sendEvent(st.dialog, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R,
                                    Qt.KeyboardModifier.NoModifier))
    ok("R 键顺时针旋转 90°", st.dialog.canvas._rotation == 90,
       str(st.dialog.canvas._rotation))
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    ok("标题栏带最小化/最大化按钮（QDialog 默认没有，用户找不到「还原」）",
       bool(st.dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
       and bool(st.dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint),
       hex(int(st.dialog.windowFlags())))
    QTest.mouseDClick(st.dialog, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(600, 6))
    pump(st.app, times=4)
    ok("双击顶部工具栏空白 → 全屏", st.dialog.isFullScreen(), "")
    QTest.mouseDClick(st.dialog, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(600, 6))
    pump(st.app, times=4)
    ok("再双击顶部栏 → 还原", not st.dialog.isFullScreen(), "")
    QTest.keyClick(st.dialog, Qt.Key.Key_F11)
    pump(st.app, times=4)
    ok("F11 → 全屏", st.dialog.isFullScreen(), "")
    QTest.keyClick(st.dialog, Qt.Key.Key_F11)
    pump(st.app, times=4)
    ok("再按 F11 → 还原", not st.dialog.isFullScreen(), "")
    # 点「百分比」标签 → 回 100%：由 dialog 的 eventFilter 消费按压实现
    st.dialog.canvas.set_zoom(2.5)
    handled = st.dialog.eventFilter(
        st.dialog.zoom_label, QEvent(QEvent.Type.MouseButtonPress)
    )
    ok("百分比标签点击把倍率复位到 100%",
       handled and abs(st.dialog.canvas.zoom - 1.0) < 1e-6,
       f"handled={handled} zoom={st.dialog.canvas.zoom:.2f}")
    ok("「打印」按钮存在（文案纯中文，与下载并排）",
       st.dialog.print_btn.text() == "打印"
       and not st.dialog.print_btn.icon().isNull(), st.dialog.print_btn.text())
    ok("打印按钮随有图启停（_sync_controls 清单已登记）",
       st.dialog.print_btn.isEnabled(), "")
    pump(st.app, times=6)   # show_for 的渲染是异步的，等它落地再验取图
    exp = st.dialog.canvas.export_image()
    # ⚠️ 此时画布带着前面 R 键断言留下的 90° 旋转：export 含变换，尺寸对调
    # （1200×900 ↔ 900×1200）正是「含翻转/旋转」语义本身。
    ok("打印取图 = 画布整分辨率图（虚拟图片场景不按路径重读）",
       exp is not None and not exp.isNull()
       and (exp.width(), exp.height()) in ((1200, 900), (900, 1200)),
       f"{exp.size() if exp is not None else None}")
    # ⚠️ 翻页/全屏必须是**窗口级 QShortcut**：只靠 keyPressEvent 在真实 GUI
    # 会掉——焦点在画布/按钮上时方向键被消费或导航走，到不了对话框
    # （离屏 QTest 直接发给对话框测不出来；用户实测「没有实现」即此）。
    from PySide6.QtGui import QShortcut

    sc_keys = {s.key().toString() for s in st.dialog.findChildren(QShortcut)}
    ok("方向键翻页/全屏走窗口级 QShortcut（不受焦点影响）",
       {"Left", "Right", "F11"} <= sc_keys, str(sorted(sc_keys)))

    st.dialog.close()
    pump(st.app, times=3)
    ok("关闭后释放图片与后台线程",
       not st.dialog.canvas.has_image and not st.dialog._threads, "")
    st.dialog.deleteLater()

    empty = ImageZoomDialog(factory=lambda index: None)
    empty.resize(800, 600)
    empty.show()
    empty.show_for(index=0)
    pump(st.app, times=3)
    ok("没有可预览的页时给出提示且按钮全禁用",
       not empty.canvas.has_image and not empty.download_btn.isEnabled(),
       empty.note_label.text())
    empty.close()
    empty.deleteLater()
    view = ImageView()
    view.resize(600, 500)
    view.set_boxes_editable(True)
    view.set_image(make_image(1000, 1400), boxes=[])
    fired: list[int] = []
    view.double_clicked.connect(lambda: fired.append(1))
    st.app.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    st.app.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseButtonDblClick, QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    ok("双击大图发出 double_clicked", len(fired) == 1, str(fired))
    ok("双击不留手绘框残影（ghost / new_start 已清）",
       view._ghost_box is None and view._new_start is None
       and view._mode is None,
       f"ghost={view._ghost_box} start={view._new_start} mode={view._mode}")
    st.app.sendEvent(view, QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)), Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    ))
    ok("双击不会偷偷落一个框", view._boxes == [], str(view._boxes))
    view.deleteLater()

