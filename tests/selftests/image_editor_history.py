# -*- coding: utf-8 -*-
"""图片编辑弹窗·步骤历史面板 + 擦除 + 扭曲笔刷。

断言线：

1. **步骤历史**（2026-10-08 用户定）：初始一格「打开」、光标停它上面；
   三步真实动作（擦除一笔 / 裁剪 / 写入文字）各记一格且名字按功能取；
   点第 0 格图回到打开时、三步进重做；点第 2 格前进到「裁剪」那一步；
   **在历史中间做新动作 ⇒ 后面的格子作废**（重做链被截断）；
2. **擦除**：橡皮擦涂过的污点被擦成白底；一笔开始就压撤销点
   （``stroke_started`` → ``_push_undo`` 已接线）；
3. **扭曲笔刷**：一笔一个撤销点；鼠标事件先合并、预览计算由 16ms 节流器
   统一调度；拖动时只刷新邻近脏瓦片、**原始全分辨率图保持不变**；
   松手提交整笔并清除预览瓦片；实时笔划同步返回图像；
   单帧渲染量有像素预算（超预算的整段挂回脏矩形留给下一次 tick，
   节流器不许停）；大图预览自动降采样。
"""

from __future__ import annotations

NAME = "image_editor_history"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·步骤历史/擦除/扭曲笔刷"


def run(ctx) -> None:
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import (
        canvas_img, is_dark, make_image, mouse_event,
    )

    from desktop.components.viewers.image_editor import ImageEditorDialog

    app = ctx.app

    # ---- 步骤历史面板：记录步骤数据 + 点选跳转（2026-10-08 用户定）----
    hist_img = make_image(120, 80)
    dialog_h = ImageEditorDialog(None, hist_img)
    try:
        cvh = dialog_h.canvas
        ctrl = dialog_h.history_list
        ok("步骤历史：初始一格「打开」、光标停在它上面",
           ctrl.count() == 1 and ctrl.item(0).text() == "打开"
           and ctrl.currentRow() == 0,
           f"n={ctrl.count()} row={ctrl.currentRow()}")
        # 三步真实动作：擦除一笔 / 裁剪 / 写入文字
        cvh.set_eraser(16)
        cvh.set_tool("erase")
        cvh.stroke_started.emit()
        cvh._erase_at(QPointF(20, 40), QPointF(40, 40))
        dialog_h._set_tool("crop")
        cvh._rect = QRectF(0, 0, 60, 80)
        dialog_h._preview_crop()
        dialog_h._set_tool("text")
        block = cvh.add_text_block(
            QPointF(6, 6), 24, QColor("#000000"), "SimSun")
        block.setPlainText("历")
        dialog_h._commit_text_blocks()
        labels = [ctrl.item(i).text() for i in range(ctrl.count())]
        ok("步骤历史：三步各记一格、名字按功能取（打开/擦除/裁剪/文字）",
           labels == ["打开", "擦除", "裁剪", "文字"]
           and ctrl.currentRow() == 3,
           f"labels={labels} row={ctrl.currentRow()}")
        ok("步骤历史：三步走完图是 60×80",
           canvas_img(cvh).width() == 60
           and canvas_img(cvh).height() == 80,
           f"size={canvas_img(cvh).width()}x{canvas_img(cvh).height()}")
        ctrl.setCurrentRow(0)
        app.processEvents()
        ok("步骤历史：点第 0 格 → 图回到打开时（120×80）、三步进重做",
           canvas_img(cvh).width() == 120 and len(dialog_h._redo) == 3
           and ctrl.currentRow() == 0,
           f"w={canvas_img(cvh).width()} redo={len(dialog_h._redo)} "
           f"row={ctrl.currentRow()}")
        ctrl.setCurrentRow(2)
        app.processEvents()
        ok("步骤历史：点第 2 格 → 前进到「裁剪」那一步（60×80）",
           canvas_img(cvh).width() == 60 and ctrl.currentRow() == 2,
           f"w={canvas_img(cvh).width()} row={ctrl.currentRow()}")
        # 在历史中间做新动作 ⇒ 后面那格作废（重做链被截断）
        dialog_h._set_tool("crop")
        cvh._rect = QRectF(0, 0, 30, 80)
        dialog_h._preview_crop()
        dialog_h._commit_crop()
        labels = [ctrl.item(i).text() for i in range(ctrl.count())]
        ok("步骤历史：跳回中间后再改动 ⇒ 后面的「文字」那格作废",
           labels == ["打开", "擦除", "裁剪", "裁剪"]
           and ctrl.currentRow() == 3
           and canvas_img(cvh).width() == 30,
           f"labels={labels} row={ctrl.currentRow()} "
           f"w={canvas_img(cvh).width()}")
    finally:
        dialog_h.deleteLater()

    # 擦除：橡皮擦涂过的地方污点被擦成白底（白 → 黑 → 白）
    white_img = make_image(200, 120)
    for x in range(95, 105):  # 黑污点 x∈[95,105) × y∈[55,65)
        for y in range(55, 65):
            white_img.setPixel(x, y, 0xFF000000)
    dialog2 = ImageEditorDialog(None, white_img)
    try:
        dialog2.canvas.set_eraser(20)
        dialog2.canvas.set_tool("erase")
        # 真实一笔 = 先发 stroke_started（压撤销点）再擦
        dialog2.canvas.stroke_started.emit()
        dialog2.canvas._erase_at(QPointF(100, 60), QPointF(120, 60))
        wiped = canvas_img(dialog2.canvas).pixelColor(100, 60)
        ok("擦除：橡皮擦涂过的污点被擦成白底", wiped.value() > 230,
           f"pixel={wiped.value()}")
        ok("擦除：一笔开始压了撤销点（stroke_started 接线）",
           len(dialog2._undo) == 1, f"undo={len(dialog2._undo)}")
    finally:
        dialog2.deleteLater()

    # 扭曲：一笔一个撤销点；非实时预览在松手时回放完整笔划
    distort_img = make_image(200, 120)
    for x in range(70, 73):
        for y in range(58, 63):
            distort_img.setPixel(x, y, 0xFF000000)
    dialog_distort = ImageEditorDialog(None, distort_img)
    try:
        distort_canvas = dialog_distort.canvas
        dialog_distort.show()
        app.processEvents()
        distort_canvas.set_tool("distort")
        distort_canvas.set_distortion_options(
            size=40, hardness=100, strength=100, spacing=25,
            mode="move", interpolation="nearest",
            high_quality_preview=True, realtime=True)
        start = QPointF(70, 60)
        end = QPointF(80, 60)
        start_view = QPointF(distort_canvas.mapFromScene(start))
        end_view = QPointF(distort_canvas.mapFromScene(end))
        distort_canvas.mousePressEvent(mouse_event("press", start_view))
        preview_before_move = distort_canvas._distort_preview_image.copy()
        distort_canvas.mouseMoveEvent(mouse_event("move", end_view))
        ok("扭曲：鼠标事件先合并，预览计算由 16ms 节流器统一调度",
           distort_canvas._distort_preview_pending_end is not None
           and distort_canvas._distort_preview_image == preview_before_move
           and distort_canvas._distort_preview_timer is not None
           and distort_canvas._distort_preview_timer.isActive(),
           "")
        distort_canvas._on_distortion_preview_tick()
        ok("扭曲：拖动时只刷新邻近瓦片，原始全分辨率图保持不变",
           bool(distort_canvas._distort_preview_items)
           and not distort_canvas._distort_preview_dirty_tiles
           and is_dark(canvas_img(distort_canvas).pixelColor(70, 60))
           and canvas_img(distort_canvas).pixelColor(80, 60).value() > 230,
           f"tiles={len(distort_canvas._distort_preview_items)}")
        distort_canvas.mouseReleaseEvent(mouse_event("release", end_view))
        ok("扭曲：松开后提交整笔并清除预览瓦片",
           not distort_canvas._distort_preview_items,
           "")
        result_after_stroke = dialog_distort.result_image()
        ok("扭曲：实时笔划移动像素、同步返回图像并压入一个撤销点",
           is_dark(canvas_img(distort_canvas).pixelColor(80, 60))
           and canvas_img(distort_canvas).pixelColor(70, 60).value() > 230
           and result_after_stroke is not None
           and is_dark(result_after_stroke.pixelColor(80, 60))
           and len(dialog_distort._undo) == 1,
           f"target={canvas_img(distort_canvas).pixelColor(80, 60).value()} "
           f"undo={len(dialog_distort._undo)}")
        dialog_distort._undo_now()
        ok("扭曲：撤销整笔恢复原图",
           is_dark(canvas_img(distort_canvas).pixelColor(70, 60))
           and canvas_img(distort_canvas).pixelColor(80, 60).value() > 230,
           "")

        distort_canvas.set_distortion_options(realtime=False)
        distort_canvas.mousePressEvent(mouse_event("press", start_view))
        distort_canvas.mouseMoveEvent(mouse_event("move", end_view))
        ok("扭曲：关闭实时预览时拖动暂不改像素",
           is_dark(canvas_img(distort_canvas).pixelColor(70, 60))
           and canvas_img(distort_canvas).pixelColor(80, 60).value() > 230,
           "")
        distort_canvas.mouseReleaseEvent(mouse_event("release", end_view))
        ok("扭曲：关闭实时预览后松手应用完整笔划",
           is_dark(canvas_img(distort_canvas).pixelColor(80, 60))
           and canvas_img(distort_canvas).pixelColor(70, 60).value() > 230,
           "")

        distort_canvas.set_image(make_image(2400, 1400))
        distort_canvas.set_distortion_options(realtime=True)
        distort_canvas._begin_distortion_stroke(QPointF(1200, 700))
        preview = distort_canvas._distort_preview_image
        ok("扭曲：大图实时预览自动降采样至 200 万像素预算",
           preview is not None
           and preview.width() * preview.height() <= 2_000_000
           and preview.width() * preview.height() < 2400 * 1400,
           f"preview={preview.size() if preview is not None else None}")
        distort_canvas._finish_distortion_stroke()

        # ⚠️ 单帧渲染量必须有预算：鼠标猛地一跳（或系统把一串 move 并成
        #    一个事件）时脏区能横跨上千像素，一次渲染完就是一次卡顿。
        #    超预算的部分**整段挂回脏矩形**留给下一次 tick，且节流器不许停。
        import desktop.components.viewers.image_editor.canvas.distortion \
            as canvas_distortion_mod
        original_budget = canvas_distortion_mod.DISTORT_PREVIEW_RENDER_PIXELS
        real_render = canvas_distortion_mod.render_rect_into
        rendered: list[tuple[int, int, int, int]] = []

        def spy_render(image, origin, field, scale, rect, interpolation):
            rendered.append(rect)
            return real_render(image, origin, field, scale, rect,
                               interpolation)

        canvas_distortion_mod.DISTORT_PREVIEW_RENDER_PIXELS = 4096
        canvas_distortion_mod.render_rect_into = spy_render
        try:
            distort_canvas.set_distortion_options(
                size=200, hardness=50, strength=50, spacing=5,
                mode="move", interpolation="nearest", realtime=True)
            jump_start = QPointF(600, 700)
            jump_end = QPointF(1800, 700)
            distort_canvas.mousePressEvent(mouse_event(
                "press", QPointF(distort_canvas.mapFromScene(jump_start))))
            distort_canvas.mouseMoveEvent(mouse_event(
                "move", QPointF(distort_canvas.mapFromScene(jump_end))))
            distort_canvas._on_distortion_preview_tick()
            pending = distort_canvas._distort_preview_dirty_rect
            budget_rows = 4096 // max(1, rendered[0][2] - rendered[0][0]) \
                if rendered else 0
            ok("扭曲预览：单帧渲染量受像素预算约束，超出的脏区挂给下一帧",
               len(rendered) == 1
               and rendered[0][3] - rendered[0][1] <= budget_rows
               and pending is not None
               and pending[3] - pending[1] > rendered[0][3] - rendered[0][1]
               and distort_canvas._distort_preview_timer is not None
               and distort_canvas._distort_preview_timer.isActive(),
               f"rendered={rendered} 预算行={budget_rows} pending={pending}")
            distort_canvas.mouseReleaseEvent(mouse_event(
                "release", QPointF(distort_canvas.mapFromScene(jump_end))))
        finally:
            canvas_distortion_mod.DISTORT_PREVIEW_RENDER_PIXELS = original_budget
            canvas_distortion_mod.render_rect_into = real_render
    finally:
        dialog_distort.deleteLater()
    app.processEvents()