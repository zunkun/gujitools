# -*- coding: utf-8 -*-
"""图片编辑弹窗·裁剪工具（2026-09-30 起用户定的交互口径）。

断言线：

1. **默认全选 + 手柄内收**：进入工具默认选中整幅图、只许拖边/框内移动，
   **不做截图式"拖拽画框"**（图外远处按下不产生橡皮筋选区）；
2. **非破坏性**：松手只记下待定裁剪（像素不动），切走工具/「完成」才
   落定成"画布尺寸 = 选区尺寸"；待定不进历史（Ctrl+Z 先退它）；
3. **边缘命中带**：整条边都是命中带、角部双边交叠命中角手柄、框内远处
   不命中（那是移动）；
4. **框内拖动**：图片与裁剪框一同移动、虚线外框贴合图片；拖回左上角时
   两者同步反向移动，待定结果含透明边距；
5. **裁剪切变换的边界**：负向移动后切入「统一变换」，边框/预览都紧贴
   图片内容、不含透明留白；切回裁剪虚线框仍贴合内容；
6. **待定期间**：右下角写出「裁完是多大」、**视图不跳**（画面不动，用户
   才好继续推拉）、历史一步都不增；
7. **能向外拖回去**（2026-10-10 报障）：旧版松手即 ``QImage.copy``，
   图被裁小、手柄顶到新边界上向外无处可拖；现在待定态画布始终是原图，
   往外拖时被遮罩盖住的区域重新露出来，遮罩显著缩小；
8. **落定与撤销**：切走工具才落定、落定是一步撤销点且历史多一格「裁剪」、
   落定后选区重新默认全选新图且视图重新适应；撤销/重做整段退进退出；
   选区没变时松手不产生空撤销步；
9. **悬停反馈**：左边缘 SizeHor、左上角 SizeFDiag、框内 OpenHand、
   擦除是空白光标 + 实圈（直径 = 橡皮擦直径、圈心 = 光标）。
"""

from __future__ import annotations

NAME = "image_editor_crop"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·裁剪工具"


def run(ctx) -> None:
    from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import (
        canvas_img, history_labels, make_image, mouse_event,
    )

    from desktop.components.viewers.image_editor import (
        ERASER_DEFAULT, ImageEditorDialog,
    )

    app = ctx.app
    img = make_image(200, 120)
    dialog = ImageEditorDialog(None, img)
    try:
        dialog.show()
        app.processEvents()
        dialog.resize(1000, 720)
        app.processEvents()
        app.processEvents()
        canvas = dialog.canvas

        # ---- 裁剪交互（2026-09-30 用户定）：默认全选 + 手柄内收，不做画框 ----
        full = dialog.canvas.image_rect()
        ok("裁剪：进入工具默认选中整幅图",
           dialog.canvas._tool == "crop"
           and dialog.canvas.selection() == full,
           f"sel={dialog.canvas.selection()} full={full}")
        dialog.canvas._resize_rect("tl", QPointF(20, 15))
        ok("裁剪：拖左上手柄向内收边",
           dialog.canvas.selection()
           == QRectF(20, 15, full.width() - 20, full.height() - 15),
           f"sel={dialog.canvas.selection()}")
        dialog.canvas.set_tool("crop")
        ok("裁剪：重新进入工具恢复默认全选",
           dialog.canvas.selection() == full, "")
        # 截图式画框必须不存在：图外远处按下不产生橡皮筋选区
        # （⚠️ 用远处：手柄有视觉尺寸+3px 容差，图外太近会命中角手柄）
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent

        outside = QPointF(dialog.canvas.mapFromScene(QPointF(-300, -300)))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, outside,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        dialog.canvas.mousePressEvent(press)
        ok("裁剪：图外按下不产生新选区（不支持截图式拖拽画框）",
           dialog.canvas._mode is None and dialog.canvas.selection() == full,
           f"mode={dialog.canvas._mode}")
        dialog.canvas.set_tool("crop")
        # ---- 边缘命中带 + 松手视图适配新选区（用户 20:18 定） ----
        def mouse_event(kind: str, view_pos: QPointF,
                        button: Qt.MouseButton = Qt.MouseButton.LeftButton):
            types = {
                "press": QEvent.Type.MouseButtonPress,
                "move": QEvent.Type.MouseMove,
                "release": QEvent.Type.MouseButtonRelease,
            }
            buttons = (Qt.MouseButton.NoButton if kind == "move"
                       else button)
            return QMouseEvent(types[kind], view_pos,
                               button, buttons,
                               Qt.KeyboardModifier.NoModifier)

        move_start = QPointF(canvas.mapFromScene(QPointF(100, 60)))
        move_end = QPointF(canvas.mapFromScene(QPointF(120, 70)))
        canvas.mousePressEvent(mouse_event("press", move_start))
        canvas.mouseMoveEvent(mouse_event("move", move_end))
        canvas.mouseReleaseEvent(mouse_event("release", move_end))
        moved_selection = canvas.selection()
        moved_offset = canvas.crop_offset()
        assert canvas._border is not None and canvas._item is not None
        moved_item = canvas._item.pos()
        moved_border = canvas._border.sceneBoundingRect()
        moved_image = canvas._item.sceneBoundingRect()
        border_local = canvas._border.rect()
        image_local = canvas._item.boundingRect()
        ok("裁剪：拖动框内图片时图片和裁剪框一同移动",
           abs(moved_offset.x() - 20) < 1
           and abs(moved_offset.y() - 10) < 1
           and moved_selection is not None
           and abs(moved_selection.left() - moved_offset.x()) < 1
           and abs(moved_selection.top() - moved_offset.y()) < 1
           and abs(moved_item.x() - moved_offset.x()) < 1
           and abs(moved_item.y() - moved_offset.y()) < 1,
           f"offset={moved_offset} selection={moved_selection} item={moved_item}")
        # ---- 裁剪框上界：原文件大小（2026-10-15 用户报障）----
        # 「裁剪框最大就是图片大小，不要超过图片外；但图片初始被向内裁掉
        #  一部分时，可以向外扩到**原始大小**」——夹取基准是原文件矩形，
        #  不是当前图（收紧过的图因此能扩回 200×120）。
        canvas.reset_selection()
        canvas._resize_rect("br", QPointF(9999, 9999))
        ok("裁剪：未收紧的图，角手柄外拖不超过图片大小",
           canvas.selection() == full,
           f"sel={canvas.selection()} full={full}")
        canvas._resize_rect("tl", QPointF(-9999, -9999))
        ok("裁剪：未收紧的图，反向也不越界",
           canvas.selection() == full,
           f"sel={canvas.selection()} full={full}")
        padded = QImage(240, 160, QImage.Format.Format_ARGB32)
        padded.fill(Qt.GlobalColor.transparent)
        pad_painter = QPainter(padded)
        pad_painter.drawImage(20, 15, img)
        pad_painter.end()
        slack_dialog = ImageEditorDialog(None, padded)
        try:
            slack_dialog.show()
            app.processEvents()
            slack_canvas = slack_dialog.canvas
            ok("裁剪：收紧过的图认得出原文件余量（可扩回原始大小）",
               slack_canvas.selection() == QRectF(0, 0, 200, 120),
               f"extent={slack_canvas.source_extent_rect()} "
               f"sel={slack_canvas.selection()}")
            slack_canvas._resize_rect("tl", QPointF(-9999, -9999))
            # ⚠️ 拖 tl **只动左/上两条边**（右/下锚定不动）：从 (0,0,200,120)
            #    左上各挪 20/15 ⇒ 宽高变成 220×135，不是原文件满幅。
            ok("裁剪：向外拖到原文件左上角（右边仍锚定）",
               slack_canvas.selection() == QRectF(-20, -15, 220, 135),
               f"sel={slack_canvas.selection()}")
            slack_canvas._resize_rect("br", QPointF(9999, 9999))
            ok("裁剪：可向外扩到**原始大小** 240×160，且不越界",
               slack_canvas.selection() == QRectF(-20, -15, 240, 160),
               f"sel={slack_canvas.selection()}")
            slack_canvas._resize_rect("br", QPointF(9999, 9999))
            ok("裁剪：反复外拖也不越界（无「无限扩张」）",
               slack_canvas.selection() == QRectF(-20, -15, 240, 160),
               f"sel={slack_canvas.selection()}")
        finally:
            slack_dialog.deleteLater()
            app.processEvents()
        move_start = QPointF(canvas.mapFromScene(QPointF(100, 60)))
        move_end = QPointF(canvas.mapFromScene(QPointF(80, 50)))
        canvas.mousePressEvent(mouse_event("press", move_start))
        canvas.mouseMoveEvent(mouse_event("move", move_end))
        canvas.mouseReleaseEvent(mouse_event("release", move_end))
        moved_offset = canvas.crop_offset()
        moved_selection = canvas.selection()
        assert canvas._border is not None and canvas._item is not None
        moved_border = canvas._border.sceneBoundingRect()
        moved_image = canvas._item.sceneBoundingRect()
        ok("裁剪：向左上拖动时图片和裁剪框同步反向移动",
           abs(moved_offset.x() + 20) < 1
           and abs(moved_offset.y() + 10) < 1
           and moved_selection is not None
           and abs(moved_selection.left() - moved_offset.x()) < 1
           and abs(moved_selection.top() - moved_offset.y()) < 1
           and canvas._border.pos() == canvas._item.pos()
           and canvas._border.rect() == canvas._item.boundingRect()
           and abs(moved_border.width() - moved_image.width()) <= 1.1
           and abs(moved_border.height() - moved_image.height()) <= 1.1,
           f"offset={moved_offset} selection={moved_selection} "
           f"border={moved_border} image={moved_image}")
        ok("裁剪：平移整图后的待定结果包含透明边距",
           dialog._pending_crop is not None
           and abs(dialog._pending_crop_offset[0] + 20) < 1
           and abs(dialog._pending_crop_offset[1] + 10) < 1
           and "裁剪后 220 × 130 px" in dialog.size_label.text(),
           f"offset={dialog._pending_crop_offset} "
           f"label={dialog.size_label.text()}")
        dialog._discard_crop()

        transition_dialog = ImageEditorDialog(None, img)
        try:
            transition_dialog.show()
            app.processEvents()
            transition_canvas = transition_dialog.canvas
            move_start = QPointF(
                transition_canvas.mapFromScene(QPointF(100, 60)))
            move_end = QPointF(
                transition_canvas.mapFromScene(QPointF(80, 50)))
            transition_canvas.mousePressEvent(mouse_event("press", move_start))
            transition_canvas.mouseMoveEvent(mouse_event("move", move_end))
            transition_canvas.mouseReleaseEvent(
                mouse_event("release", move_end))
            transition_dialog._set_tool("transform")
            content_rect = QRectF(0, 0, 200, 120)
            transform_frame = transition_canvas._quad.boundingRect()
            border_frame = transition_canvas._border.sceneBoundingRect()
            ok("裁剪负向移动切统一变换后边框紧贴图片（不含右侧/底部透明留白）",
               transition_canvas._rect == content_rect
               and abs(transform_frame.left() - content_rect.left()) < 1
               and abs(transform_frame.top() - content_rect.top()) < 1
               and abs(transform_frame.width() - content_rect.width()) < 1
               and abs(transform_frame.height() - content_rect.height()) < 1
               and abs(border_frame.left() - content_rect.left()) < 1
               and abs(border_frame.top() - content_rect.top()) < 1
               and abs(border_frame.width() - content_rect.width()) <= 1.1
               and abs(border_frame.height() - content_rect.height()) <= 1.1,
               f"selection={transition_canvas._rect} frame={transform_frame} "
               f"border={border_frame} canvas={transition_canvas._image.size()}")
            transition_canvas._ensure_transform_preview()
            preview_bounds = transition_canvas._display_bounds()
            ok("统一变换预览边框仍不包含透明留白",
               transition_canvas._backdrop_is_whole()
               and abs(preview_bounds.left() - content_rect.left()) < 1
               and abs(preview_bounds.top() - content_rect.top()) < 1
               and abs(preview_bounds.width() - content_rect.width()) <= 1.1
               and abs(preview_bounds.height() - content_rect.height()) <= 1.1,
               f"preview={preview_bounds} "
               f"whole={transition_canvas._backdrop_is_whole()}")
        finally:
            transition_dialog.deleteLater()
            app.processEvents()

        padded_image = QImage(220, 130, QImage.Format.Format_ARGB32)
        padded_image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(padded_image)
        painter.drawImage(0, 0, img)
        painter.end()
        reverse_dialog = ImageEditorDialog(None, padded_image)
        try:
            reverse_dialog.show()
            app.processEvents()
            reverse_canvas = reverse_dialog.canvas
            crop_start = QPointF(
                reverse_canvas.mapFromScene(QPointF(100, 60)))
            crop_end = QPointF(
                reverse_canvas.mapFromScene(QPointF(120, 70)))
            reverse_canvas.mousePressEvent(mouse_event("press", crop_start))
            reverse_canvas.mouseMoveEvent(mouse_event("move", crop_end))
            reverse_canvas.mouseReleaseEvent(
                mouse_event("release", crop_end))
            reverse_dialog._set_tool("transform")
            reverse_canvas.transform_move(20, 0)
            transform_bounds = reverse_canvas._display_bounds()
            transform_border = reverse_canvas._border.sceneBoundingRect()
            ok("裁剪移动后切入统一变换，虚线框不叠加旧图元偏移",
               abs(transform_border.left() - transform_bounds.left()) <= 0.6
               and abs(transform_border.top() - transform_bounds.top()) <= 0.6
               and abs(transform_border.width() - transform_bounds.width()) <= 1.1
               and abs(transform_border.height() - transform_bounds.height()) <= 1.1,
               f"display={transform_bounds} border={transform_border}")
            before_switch = QImage(canvas_img(reverse_canvas))
            reverse_dialog._set_tool("crop")
            crop_border = reverse_canvas._border.sceneBoundingRect()
            content = reverse_canvas._content_rect()
            assert content is not None and reverse_canvas._item is not None
            expected_content = content.translated(
                reverse_canvas._item.pos())
            ok("统一变换切回裁剪后虚线框仍贴合图片内容（不含右侧/底部透明留白）",
               reverse_canvas._tool == "crop"
               and reverse_canvas.selection() is not None
               and canvas_img(reverse_canvas).size() != before_switch.size()
               and abs(crop_border.left() - expected_content.left()) < 1
               and abs(crop_border.top() - expected_content.top()) < 1
               and abs(crop_border.width() - expected_content.width()) <= 1.1
               and abs(crop_border.height() - expected_content.height()) <= 1.1,
               f"selection={reverse_canvas.selection()} border={crop_border} "
               f"canvas={reverse_canvas._image.size()}")
        finally:
            reverse_dialog.deleteLater()
            app.processEvents()

        left_mid = QPointF(canvas.mapFromScene(QPointF(-1.0, 60)))
        ok("裁剪：整条边都是命中带（左边缘中点、远离小方块）",
           canvas._hit_handle(left_mid) == "l",
           f"hit={canvas._hit_handle(left_mid)}")
        corner = QPointF(canvas.mapFromScene(QPointF(-1.0, -1.0)))
        ok("裁剪：角部双边交叠命中角手柄",
           canvas._hit_handle(corner) == "tl",
           f"hit={canvas._hit_handle(corner)}")
        middle = QPointF(canvas.mapFromScene(QPointF(100, 60)))
        ok("裁剪：远离边缘的框内不命中手柄（那是移动）",
           canvas._hit_handle(middle) is None,
           f"hit={canvas._hit_handle(middle)}")

        def mask_area(cv) -> float:
            """选区外那 4 块遮罩的总面积（= 被"藏起来"的像素数）。"""
            return sum(max(0.0, it.rect().width()) * max(0.0, it.rect().height())
                       for it in cv._mask)

        zoom_before = canvas._zoom
        undo_before = len(dialog._undo)
        history_before = dialog.history_list.count()
        canvas.mousePressEvent(mouse_event("press", corner))
        ok("裁剪：角部按下进入收边状态",
           canvas._mode is not None and canvas._mode[0] == "handle"
           and canvas._mode[1] == "tl", f"mode={canvas._mode}")
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(60, 30)))))
        ok("裁剪：拖动过程中图仍是整幅（松手也不切像素）",
           canvas_img(canvas).width() == 200
           and canvas.selection() is not None
           and abs(canvas.selection().left() - 60) < 1,
           f"w={canvas_img(canvas).width()} sel={canvas.selection()}")
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(60, 30)))))
        sel_now2 = canvas.selection()
        masked_in = mask_area(canvas)
        ok("裁剪：松手**不落定**＝画布仍是原图、选区留着、不进历史",
           canvas_img(canvas).width() == 200
           and canvas_img(canvas).height() == 120
           and sel_now2 is not None
           and abs(sel_now2.left() - 60) < 1
           and dialog._pending_crop is not None
           and len(dialog._undo) == undo_before
           and dialog.history_list.count() == history_before,
           f"w={canvas_img(canvas).width()} sel={sel_now2} "
           f"待定={dialog._pending_crop} undo={len(dialog._undo)}")
        ok("裁剪：待定期间右下角并排写出「裁完是多大」",
           "裁剪后 140 × 90 px" in dialog.size_label.text(),
           f"label={dialog.size_label.text()!r}")
        ok("裁剪：待定期间视图不跳（画面不动，用户才好继续推拉）",
           canvas._zoom == zoom_before,
           f"zoom {zoom_before:.2f} -> {canvas._zoom:.2f}")

        # ---- 回归（用户 2026-10-10 报障）：裁剪线要能向外拖回去 ----
        # 旧版松手即 QImage.copy，把图裁小、选区重置成新图整幅 ⇒ 第二次拖动
        # 时手柄已经压在边界上，向外无处可拖；现在待定状态下画布始终是原图，
        # 往外拖时被遮罩盖住的区域会重新露出来。
        tl_now = QPointF(canvas.mapFromScene(QPointF(60, 30)))
        canvas.mousePressEvent(mouse_event("press", tl_now))
        ok("裁剪：收小后角手柄仍可再抓（没有换图把手柄顶到新边界上）",
           canvas._mode is not None and canvas._mode[0] == "handle"
           and canvas._mode[1] == "tl", f"mode={canvas._mode}")
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(10, 8)))))
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(10, 8)))))
        sel_out = canvas.selection()
        masked_out = mask_area(canvas)
        ok("裁剪：向外拖回去＝原本被隐藏的区域重新显示（遮罩显著缩小）",
           sel_out is not None
           and abs(sel_out.left() - 10) < 1 and abs(sel_out.top() - 8) < 1
           and abs(sel_out.width() - 190) < 1
           and masked_out < masked_in / 2
           and canvas_img(canvas).width() == 200,
           f"sel={sel_out} 遮罩 {masked_in:.0f} -> {masked_out:.0f} "
           f"w={canvas_img(canvas).width()}")
        ok("裁剪：反复推拉期间图一直是原图、历史一步都不增",
           canvas_img(canvas).height() == 120
           and dialog._pending_crop is not None
           and len(dialog._undo) == undo_before
           and dialog.history_list.count() == history_before,
           f"待定={dialog._pending_crop} undo={len(dialog._undo)}")
        # 再拖一次回到整幅：这一下等于"没裁"，待定就该自己消失
        tl_out = QPointF(canvas.mapFromScene(QPointF(10, 8)))
        canvas.mousePressEvent(mouse_event("press", tl_out))
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(0, 0)))))
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(0, 0)))))
        ok("裁剪：一路拖回整幅＝当成没裁（待定清空、历史不增）",
           canvas.selection() == canvas.image_rect()
           and dialog._pending_crop is None
           and len(dialog._undo) == undo_before
           and dialog.history_list.count() == history_before,
           f"sel={canvas.selection()} 待定={dialog._pending_crop} "
           f"undo={len(dialog._undo)}")

        # 再收小一次，然后**切走裁剪工具**才真正落定（GIMP 口径）
        canvas._rect = QRectF(60, 30, 140, 90)
        dialog._preview_crop()
        ok("裁剪：切走工具前仍是原图（待定没落定）",
           canvas_img(canvas).width() == 200, "")
        dialog._set_tool("erase")
        cropped = canvas_img(canvas)
        ok("裁剪：切走裁剪工具＝确认这次裁剪（画布尺寸 = 选区尺寸）",
           abs(cropped.width() - 140) < 1 and abs(cropped.height() - 90) < 1,
           f"size={cropped.width()}x{cropped.height()}")
        ok("裁剪：落定后待定状态清空（不会二次落定）",
           dialog._pending_crop is None, f"待定={dialog._pending_crop}")
        ok("裁剪：落定是一步撤销点，历史多一格「裁剪」且光标停在那儿",
           len(dialog._undo) == undo_before + 1
           and dialog.history_list.count() == history_before + 1
           and dialog.history_list.item(
               dialog.history_list.count() - 1).text() == "裁剪"
           and dialog.history_list.currentRow()
           == dialog.history_list.count() - 1,
           f"undo={len(dialog._undo)} 行={dialog.history_list.currentRow()} "
           f"历史={history_labels(dialog)}")
        # 回到裁剪工具：换图后选区重新默认全选新图
        dialog._set_tool("crop")
        ok("裁剪：落定后选区重新默认全选新图",
           canvas.selection() == canvas.image_rect(),
           f"sel={canvas.selection()} full={canvas.image_rect()}")
        ok("裁剪：落定后视图重新适应新图（形状变了，倍率随之重算）",
           canvas._zoom > zoom_before,
           f"zoom {zoom_before:.2f} -> {canvas._zoom:.2f}")
        sel_sel = canvas.selection()
        assert sel_sel is not None  # 裁剪态必有选区
        sel_view = canvas.mapFromScene(sel_sel).boundingRect()
        vp = canvas.viewport().rect()
        ok("裁剪：适应后四周留白（图约占 80% 视口，不顶边）",
           sel_view.width() < vp.width() and sel_view.height() < vp.height(),
           f"sel_view={sel_view.width():.0f}x{sel_view.height():.0f} "
           f"viewport={vp.width()}x{vp.height()}")
        # 撤销/重做把裁剪整段退回去又前进回来（历史光标跟着走）
        dialog._undo_now()
        ok("裁剪：撤销把裁剪完整回退（图回 200×120、历史光标回第 0 格）",
           canvas_img(canvas).width() == 200
           and dialog.history_list.currentRow() == 0,
           f"w={canvas_img(canvas).width()} "
           f"行={dialog.history_list.currentRow()}")
        dialog._redo_now()
        ok("裁剪：重做回到裁后 140×90、历史光标回末格",
           canvas_img(canvas).width() == 140
           and dialog.history_list.currentRow()
           == dialog.history_list.count() - 1, "")
        # 待定裁剪不进历史：Ctrl+Z 要先退掉它（框弹回整幅），再按一次才撤真步骤
        dialog._redo_now()          # 先把重做链走空，保证下面按一次就能撤到 140
        canvas.set_tool("crop")
        canvas._rect = QRectF(10, 10, 120, 70)      # 当前图已是 140×90
        dialog._preview_crop()
        steps_now = len(dialog._undo)
        dialog._undo_now()
        ok("裁剪：待定时 Ctrl+Z 先退掉裁剪框（图不动、历史不撤）",
           dialog._pending_crop is None
           and canvas.selection() == canvas.image_rect()
           and len(dialog._undo) == steps_now
           and canvas_img(canvas).width() == 140,
           f"待定={dialog._pending_crop} sel={canvas.selection()} "
           f"undo={len(dialog._undo)} before={steps_now} "
           f"w={canvas_img(canvas).width()}")
        # 选区没变（点一下手柄但不拖）时松手：不许白压一个空撤销步
        steps_now = len(dialog._undo)
        handle_top = QPointF(canvas.mapFromScene(
            canvas.image_rect().topLeft()))
        canvas.mousePressEvent(mouse_event("press", handle_top))
        canvas.mouseReleaseEvent(mouse_event("release", handle_top))
        ok("裁剪：选区没变时松手不产生空撤销步（点一下不算一步）",
           len(dialog._undo) == steps_now
           and dialog._pending_crop is None
           and canvas_img(canvas).width() == 140,
           f"undo={len(dialog._undo)} before={steps_now}")

        # ---- 悬停反馈：光标形态 + 边界高亮（用户 20:28 定） ----
        app.processEvents()
        sel_now = canvas.selection()
        assert sel_now is not None  # 裁剪态必有选区
        hover_l = QPointF(canvas.mapFromScene(QPointF(
            sel_now.left() - 1.0, sel_now.center().y())))
        canvas.mouseMoveEvent(mouse_event("move", hover_l))
        ok("悬停：左边缘上光标变左右缩放、该边高亮",
           canvas.viewport().cursor().shape() == Qt.CursorShape.SizeHorCursor
           and canvas._edge_lines["l"].isVisible()
           and not canvas._edge_lines["t"].isVisible(),
           f"cursor={canvas.viewport().cursor().shape()} "
           f"l={canvas._edge_lines['l'].isVisible()}")
        hover_tl = QPointF(canvas.mapFromScene(QPointF(
            sel_now.left() - 1.0, sel_now.top() - 1.0)))
        canvas.mouseMoveEvent(mouse_event("move", hover_tl))
        ok("悬停：左上角光标变对角缩放、相邻两边都高亮",
           canvas.viewport().cursor().shape() == Qt.CursorShape.SizeFDiagCursor
           and canvas._edge_lines["l"].isVisible()
           and canvas._edge_lines["t"].isVisible(),
           f"cursor={canvas.viewport().cursor().shape()}")
        hover_mid = QPointF(canvas.mapFromScene(sel_now.center()))
        canvas.mouseMoveEvent(mouse_event("move", hover_mid))
        ok("悬停：框内是抓手光标、高亮熄灭",
           canvas.viewport().cursor().shape() == Qt.CursorShape.OpenHandCursor
           and not any(i.isVisible() for i in canvas._edge_lines.values()),
           f"cursor={canvas.viewport().cursor().shape()}")
        canvas.set_tool("erase")
        canvas.mouseMoveEvent(mouse_event("move", hover_mid))
        ring = canvas._eraser_ring[0].rect()
        ring_center = canvas.mapFromScene(ring.center())
        ok("悬停：擦除是空白光标 + 实圈指示（直径=橡皮擦大小、圈心=光标）",
           canvas.viewport().cursor().shape() == Qt.CursorShape.BlankCursor
           and all(i.isVisible() for i in canvas._eraser_ring)
           and abs(ring.width() - ERASER_DEFAULT) < 1e-6
           and (QPointF(ring_center) - hover_mid).manhattanLength() < 2.0
           and not any(i.isVisible() for i in canvas._edge_lines.values()),
           f"cursor={canvas.viewport().cursor().shape()} "
           f"ring={ring.width():.1f} vs {ERASER_DEFAULT}")
        canvas.set_tool("crop")
        ok("工具栏：撤销/还原/完成按钮都在窗口内（不再被挤出）",
           dialog.undo_btn.x() >= 0
           and dialog.reset_btn.geometry().right() < dialog.width()
           and dialog.done_btn.geometry().right() <= dialog.width(),
           f"undo.x={dialog.undo_btn.x()} "
           f"done.right={dialog.done_btn.geometry().right()} "
           f"win={dialog.width()}")
        ok("工具栏：缩放按钮进了顶部动作行（在「还原」右侧、有宽度）",
           all(
               getattr(dialog, n).x() > dialog.reset_btn.x()
               and getattr(dialog, n).width() > 0
               for n in ("zoom_in_btn", "zoom_out_btn", "fit_btn")
           ),
           f"reset.x={dialog.reset_btn.x()} "
           f"zoom.x={[getattr(dialog, n).x() for n in ('zoom_in_btn', 'zoom_out_btn', 'fit_btn')]}")
    finally:
        dialog.deleteLater()
    app.processEvents()