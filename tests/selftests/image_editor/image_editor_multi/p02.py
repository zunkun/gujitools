# -*- coding: utf-8 -*-
"""拼版缩放不同也不自动调整 view 中心/倍率 / 开关必须管住「适配选区」这条独立路径（2026-10-14 用户报障） / 切层绝不缩放；自动缩放只发生在\"操作结束\"（2026-10-14 用户口径） / 开关关闭＝**画面绝对不动**（不只是不缩放，2026-10-14 用户口径 / 大图变换 ghost：先应用浮层变换、再移到 ghost 原点 / 裁剪负向平移后切工具，再点击切回该层，边框仍贴合非透明内容"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _make_image, _spread_dialog
    from qfluentwidgets import CheckBox
    from desktop.components.viewers.image_editor import ImageEditorDialog
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
    from PySide6.QtGui import QMouseEvent, QTransform
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QEvent as _QEvent
    from PySide6.QtGui import QMouseEvent as _QMouseEvent
    from tests.selftests._context import ok
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import CheckBox

    from desktop.components.viewers.image_editor import ImageEditorDialog

    left4 = _make_image(200, 100, "#ffffff")
    right4 = _make_image(150, 80, "#dddddd")
    st.dialog4 = ImageEditorDialog(None, left4, save_back=True)
    st.dialog4.configure_multiple_images([
        {"image": left4, "file": "_l4.png", "rect": (0, 0, 200, 100)},
        {"image": right4, "file": "_r4.png",
         "rect": (250, 10, 150 * 1.57, 80 * 1.57)},
    ])
    st.c4 = st.dialog4.canvas
    st.dialog4.resize(1400, 900)
    st.dialog4.show()
    QApplication.processEvents()
    st.c4.fit()
    QApplication.processEvents()

    zoom_before_switch = st.c4._zoom
    transform_before_switch = st.c4.transform()
    context_pixmap_key = st.c4._context_item.pixmap().cacheKey()
    active_pixmap_key = st.c4._item.pixmap().cacheKey()
    st.dialog4._switch_context_layer()
    ok("拼版缩放不同时：切层不自动适配，view 变换和倍率保持不变",
       abs(st.c4._zoom - zoom_before_switch) < 1e-6
       and st.c4.transform() == transform_before_switch,
       f"zoom={zoom_before_switch}->{st.c4._zoom}")
    ok("切层复用两张图片的 QPixmap，不重复整图转换",
       st.c4._item.pixmap().cacheKey() == context_pixmap_key
       and st.c4._context_item.pixmap().cacheKey() == active_pixmap_key, "")
    st.dialog4._set_tool("transform")
    auto_fit_boxes = [
        box for box in st.dialog4._option_page.findChildren(CheckBox)
        if box.text() == "是否自动缩放画布"
    ]
    ok("统一变换选项：自动缩放画布默认不勾选",
       len(auto_fit_boxes) == 1 and not auto_fit_boxes[0].isChecked()
       and not st.c4._xf_auto_fit_canvas, "")
    click_pos = QPointF(st.c4.mapFromScene(QPointF(100, 50)))
    click = QMouseEvent(
        QEvent.Type.MouseButtonPress, click_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease, click_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier)
    st.c4.mousePressEvent(click)
    st.c4.mouseReleaseEvent(release)
    ok("统一变换：纯点选图片不创建重采样预览",
       st.c4._float_item is None and st.c4._mode is None, "")
    zoom_before_move = st.c4._zoom
    left_screen_before_move = st.c4.mapFromScene(QPointF(100, 50))
    scene_rect_before_move = st.c4.sceneRect()
    st.c4.transform_move(400, 0)
    ok("默认关闭时：移动图片不自动缩放画布",
       abs(st.c4._zoom - zoom_before_move) < 1e-6, f"{zoom_before_move}->{st.c4._zoom}")
    QApplication.processEvents()
    left_screen_after_move = st.c4.mapFromScene(QPointF(100, 50))
    ok("默认关闭时：移动图片不自动居中或平移画布",
       (left_screen_after_move - left_screen_before_move).manhattanLength() <= 3,
       f"{left_screen_before_move}->{left_screen_after_move}, "
       f"scene-rect={scene_rect_before_move}->{st.c4.sceneRect()}")
    auto_fit_boxes[0].setChecked(True)
    zoom_before_auto_fit = st.c4._zoom
    st.c4.transform_move(400, 0)
    content_center_after_auto_fit = st.c4._content_scene_rect().center()
    content_center_in_view = st.c4.mapFromScene(content_center_after_auto_fit)
    view_center = st.c4.viewport().rect().center()
    ok("勾选后：变换结束自动缩放并居中画布",
       st.c4._xf_auto_fit_canvas and st.c4._zoom < zoom_before_auto_fit
       and (content_center_in_view - view_center).manhattanLength() <= 20,
       f"zoom={zoom_before_auto_fit}->{st.c4._zoom}, "
       f"content-center-view={content_center_in_view}, "
       f"viewport-center={view_center}")
    st.c4._rect = QRectF(60, 30, 80, 40)
    st.c4._xf_auto_fit_canvas = False
    st.c4.fit()
    QApplication.processEvents()
    zoom_before_selection_fit = st.c4._zoom
    st.c4.fit_selection()
    QApplication.processEvents()
    ok("「是否自动缩放画布」关闭时：适配选区也不缩放"
       "（旧版 fit_selection 无视开关，点选一下画面就跳）",
       abs(st.c4._zoom - zoom_before_selection_fit) < 1e-6,
       f"zoom={zoom_before_selection_fit}->{st.c4._zoom}")
    st.c4._xf_auto_fit_canvas = True
    st.c4.fit()
    QApplication.processEvents()
    zoom_before_selection_fit_on = st.c4._zoom
    st.c4.fit_selection()
    QApplication.processEvents()
    ok("开关勾选时：适配选区照旧生效（别把功能改死）",
       abs(st.c4._zoom - zoom_before_selection_fit_on) > 1e-6,
       f"zoom={zoom_before_selection_fit_on}->{st.c4._zoom}")
    st.dialog4.close()
    st.dialog4.release_buffers()
    def _screen_positions(dlg):
        cvs = dlg.canvas
        out = {}
        for index, layer in enumerate(dlg._multi_layers):
            if index == dlg._active_layer:
                center = cvs.image_rect().center()
            elif cvs._context_display_rect is not None:
                center = cvs._context_display_rect.center()
            else:
                continue
            out[layer["label"]] = QPointF(cvs.mapFromScene(center))
        return out

    dialog_s, left_s, right_s = _spread_dialog()
    cs = dialog_s.canvas
    dialog_s.resize(1400, 900)
    dialog_s.show()
    QApplication.processEvents()
    dialog_s._set_tool("transform")
    QApplication.processEvents()
    cs.fit()
    QApplication.processEvents()
    zoom_before_switch2 = cs._zoom
    positions_before_switch2 = _screen_positions(dialog_s)
    dialog_s._switch_context_layer()
    QApplication.processEvents()
    positions_after_switch2 = _screen_positions(dialog_s)
    worst_switch = max(
        (positions_after_switch2[label] - positions_before_switch2[label]
         ).manhattanLength()
        for label in positions_before_switch2
        if label in positions_after_switch2)
    ok("点另一张图**切换**：视图不缩放（zoom 恒定）",
       abs(cs._zoom - zoom_before_switch2) < 1e-6,
       f"zoom={zoom_before_switch2}->{cs._zoom}")
    ok("点另一张图**切换**：两张图各自在屏幕上纹丝不动"
       "（按图片身份追踪；旧版误用活动图槽位当判据，会量出假位移）",
       worst_switch <= 3,
       f"最大位移={worst_switch:.0f}px, "
       f"before={positions_before_switch2}, "
       f"after={positions_after_switch2}")
    # 往返切层不累积
    dialog_s._switch_context_layer()
    QApplication.processEvents()
    positions_roundtrip = _screen_positions(dialog_s)
    worst_roundtrip = max(
        (positions_roundtrip[label] - positions_before_switch2[label]
         ).manhattanLength()
        for label in positions_before_switch2
        if label in positions_roundtrip)
    ok("来回切层不累积漂移",
       worst_roundtrip <= 3, f"最大位移={worst_roundtrip:.0f}px")
    # 自动缩放：开关开 ⇒ 操作结束松手才缩放；开关关 ⇒ 不缩放
    cs._xf_auto_fit_canvas = True
    cs.fit()
    QApplication.processEvents()
    zoom_before_op = cs._zoom
    cs.transform_rotate(20)
    QApplication.processEvents()
    cs.finish_transform_drag()
    QApplication.processEvents()
    ok("开关开启：变换**松手之后**才自动缩放（正是用户要的时机）",
       abs(cs._zoom - zoom_before_op) > 1e-6,
       f"zoom={zoom_before_op}->{cs._zoom}")
    cs._xf_auto_fit_canvas = False
    cs.fit()
    QApplication.processEvents()
    zoom_before_op_off = cs._zoom
    cs.transform_rotate(20)
    QApplication.processEvents()
    cs.finish_transform_drag()
    QApplication.processEvents()
    ok("开关关闭：操作结束也不自动缩放",
       abs(cs._zoom - zoom_before_op_off) < 1e-6,
       f"zoom={zoom_before_op_off}->{cs._zoom}")
    dialog_s.close()
    dialog_s.release_buffers()
    from PySide6.QtCore import QEvent as _QEvent
    from PySide6.QtGui import QMouseEvent as _QMouseEvent

    dialog_n, left_n, _right_n = _spread_dialog()
    cn = dialog_n.canvas
    dialog_n.resize(1400, 900)
    dialog_n.show()
    QApplication.processEvents()
    dialog_n._set_tool("crop")
    QApplication.processEvents()
    cn.fit()
    QApplication.processEvents()
    cn._xf_auto_fit_canvas = False
    # 盯住**图元上的一个固定像素**（不是固定场景坐标——裁剪移动会把图元
    # 整个挪走，用场景点量必然混进"图片跟着框挪"这一段预期位移）
    item_local = QPointF(100, 50)
    zoom_before_crop = cn._zoom
    item_before_crop = QPointF(cn.mapFromScene(
        cn._item.mapToScene(item_local)))
    cn._mode = ("crop_move", QPointF(100, 50), QRectF(cn._rect),
                QPointF(cn._crop_offset))
    cn._crop_offset = QPointF(-40, 30)
    cn._item.setPos(cn._crop_offset)
    cn._rect = QRectF(cn._rect).translated(QPointF(-40, 30))
    scene_rect_before_crop = QRectF(cn.sceneRect())
    cn.mouseReleaseEvent(_QMouseEvent(
        _QEvent.Type.MouseButtonRelease, QPointF(100, 50),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()
    # 换算：图片挪了 (-40,30)，画面若"纹丝不动"则该像素的屏幕位移
    # 恰好等于那次图片位移；多出来的部分才是视图被自动调整了。
    item_after_crop = QPointF(cn.mapFromScene(
        cn._item.mapToScene(item_local)))
    expected = QPointF(-40 * zoom_before_crop, 30 * zoom_before_crop)
    extra = (item_after_crop - item_before_crop - expected).manhattanLength()
    ok("开关关闭：裁剪框内移动松手**画面不额外平移**"
       "（_sync_scene_rect 不再重定位视图；扣除图片自身位移后应≈0）",
       abs(cn._zoom - zoom_before_crop) < 1e-6 and extra <= 3,
       f"zoom={zoom_before_crop}->{cn._zoom}, "
       f"实际位移={(item_after_crop - item_before_crop).manhattanLength():.1f}px, "
       f"图片自身位移={expected.manhattanLength():.1f}px, "
       f"多出来的={extra:.1f}px, "
       f"sceneRect {scene_rect_before_crop}->{cn.sceneRect()}")
    dialog_n.close()
    dialog_n.release_buffers()
    left5 = _make_image(100, 80, "#ff0000")
    right5 = _make_image(1000, 1000, "#00ff00")
    dialog5 = ImageEditorDialog(None, left5, save_back=True)
    dialog5.configure_multiple_images([
        {"image": left5, "file": "_l5.png", "rect": (0, 0, 100, 80)},
        {"image": right5, "file": "_r5.png", "rect": (200, 0, 1000, 1000)},
    ])
    dialog5._set_tool("transform")
    dialog5._activate_layer(1)
    dialog5.canvas.transform_move(200, 0)
    dialog5.canvas.make_transform_pending()
    dialog5._activate_layer(0)
    ghost_image = dialog5.canvas._context_image
    assert ghost_image is not None
    sample_y = ghost_image.height() // 2
    visible_columns = [
        x for x in range(ghost_image.width())
        if ghost_image.pixelColor(x, sample_y).alpha() > 0
    ]
    # ⚠️ 虚线框取**非透明内容**外框（2026-10-14）：ghost 由浮层像素按外框
    # 合成，右/下常带几像素透明边（实测 1004×1002 里内容只有 1000×1000），
    # 框必须贴内容而不是把这点留白也算进去——与活动图、活动图边框同口径。
    ghost_border = dialog5.canvas._context_border.rect()
    ok("大图右移切层：ghost 内容仍完整贴合虚线框",
       visible_columns
       and visible_columns[0] <= 2
       and visible_columns[-1] >= ghost_image.width() - 6
       and ghost_border.width() == visible_columns[-1] + 1
       and ghost_border.height() == ghost_image.height() - 2,
       f"image={ghost_image.size()}, border={ghost_border}, "
       f"visible=({visible_columns[0] if visible_columns else None}, "
       f"{visible_columns[-1] if visible_columns else None})")
    dialog5.close()
    dialog5.release_buffers()
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from desktop.components.viewers.image_editor import ImageEditorDialog

    left7 = _make_image(400, 400, "#ffffff")
    right7 = _make_image(100, 80, "#dddddd")
    dialog7 = ImageEditorDialog(None, left7, save_back=True)
    dialog7.configure_multiple_images([
        {"image": left7, "file": "_l7.png", "rect": (0, 0, 400, 400)},
        {"image": right7, "file": "_r7.png", "rect": (600, 0, 100, 80)},
    ])
    c7 = dialog7.canvas
    dialog7.show()
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    QApplication.processEvents()

    def send_crop_drag(start: QPointF, end: QPointF) -> None:
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, start,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        move = QMouseEvent(
            QEvent.Type.MouseMove, end,
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease, end,
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier)
        c7.mousePressEvent(press)
        c7.mouseMoveEvent(move)
        c7.mouseReleaseEvent(release)

    send_crop_drag(
        QPointF(c7.mapFromScene(QPointF(200, 200))),
        QPointF(c7.mapFromScene(QPointF(0, 400))),
    )
    crop_shift_x = round(c7.crop_offset().x())
    crop_shift_y = round(c7.crop_offset().y())
    ok("复现：裁剪左移 200px 后待应用画布保留完整尺寸",
       abs(crop_shift_x + 200) <= 2 and abs(crop_shift_y - 200) <= 2,
       f"offset={c7.crop_offset()}")
    dialog7._set_tool("transform")
    QTest.qWait(2000)
    dialog7._set_tool("crop")
    expected_width = 400 + abs(crop_shift_x)
    expected_height = 400 + abs(crop_shift_y)
    expected_content = QRectF(0, max(0, crop_shift_y), 400, 400)
    ok("复现：离开并返回裁剪后图片像素画布尺寸包含平移留白",
       c7.image is not None
       and c7.image.size().width() == expected_width
       and c7.image.size().height() == expected_height,
       f"image={c7.image.size() if c7.image is not None else None}")
    dialog7._set_tool("transform")
    dialog7._set_tool("crop")
    crop_content = c7._content_rect()
    assert crop_content is not None
    ok("复现：切回裁剪后选框只包住左下图片，不延伸到右图",
       c7.selection() == crop_content
       and crop_content == expected_content,
       f"selection={c7.selection()} content={crop_content}")
    ok("复现：扩展画布的透明留白不再被裁剪遮罩涂成灰色",
       all(not mask.isVisible() or mask.rect().isEmpty()
           for mask in c7._mask),
       f"masks={[mask.rect() for mask in c7._mask]}")

    def click_scene(point: QPointF) -> None:
        view_point = QPointF(c7.mapFromScene(point))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, view_point,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease, view_point,
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier)
        c7.mousePressEvent(press)
        c7.mouseReleaseEvent(release)

    context_right = c7._context_display_rect
    assert context_right is not None
    click_scene(context_right.center())
    ok("复现：点击右图实际切换激活层",
       dialog7._active_layer == 1, f"active={dialog7._active_layer}")
    context_left = c7._context_display_rect
    assert context_left is not None
    click_scene(context_left.center())
    left_content = c7._content_rect()
    assert left_content is not None
    left_border = c7._border.sceneBoundingRect()
    ok("点击切回裁剪后的左图，虚线框仍只包住左下图片",
       dialog7._active_layer == 0
       and left_content == expected_content
       and c7.selection() == left_content
       and all(not mask.isVisible() or mask.rect().isEmpty()
               for mask in c7._mask)
       and abs(left_border.left() - left_content.left()) < 1
       and abs(left_border.top() - left_content.top()) < 1
       and abs(left_border.width() - left_content.width()) <= 1.1
       and abs(left_border.height() - left_content.height()) <= 1.1,
       f"selection={c7.selection()} content={left_content} border={left_border} "
       f"canvas={c7.image.size() if c7.image is not None else None}")
    dialog7.close()
    dialog7.release_buffers()

