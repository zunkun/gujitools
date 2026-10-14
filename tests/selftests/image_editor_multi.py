# -*- coding: utf-8 -*-
"""图片编辑弹窗·双图编辑（拼版「编辑整图」）自测。

断言线（只看可观测行为，2026-10-13 用户报障三条）：

1. **画布完整显示两张图**：场景矩形 ＝ 活动图矩形 ∪ 非活动图矩形——
   旧版有两个 ``_sync_scene_rect``（后定义的"恒定＝原图矩形"把新的
   "∪ context"版整个遮蔽），``fit()`` 只装得下活动图（用户截图报障）；
2. **裁剪/变换后两张图不漂移**：每层记"内容原点"（当前画布 (0,0) 在初始
   图像素系里的位置），真裁剪/变换烘焙后原点平移、双图相对摆放随之换算
   （旧版只算入口收紧偏移，一边裁剪另一边就"漂走"）；
3. **撤销/重做/还原带着原点一起退**：原点有与撤销栈平行的栈（各步撤销点
   带当时的原点），退历史不会把相对摆放留在"未来"；
4. **换层状态保持 + 丝滑**：快照全部浅拷贝（QImage 隐式共享，列表浅拷贝——
   旧版深拷贝 12 份整图快照 ×2 层，12 MP 下一刀几百 MB memcpy）；换层不适配、
   不自动调整中心与缩放；
5. **恢复会话进「统一变换」零等待**：upright 缓存命中路径也**不**在进工具
   那刻建预览（底图重铺 + 浮层逐像素重采样 150–450ms 全在切换里），只挂
   框/矩阵/区域，预览推迟到第一次拖动（与"延迟供像素"路径同款）。
6. **统一变换自动缩放画布**：默认关闭；关闭时移动/形变不自动 fit 或平移
   视口，开启后每次操作结束自动缩放并居中显示内容。
"""
from __future__ import annotations

NAME = "image_editor_multi"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·双图编辑（拼版编辑整图）"


def _make_image(width: int, height: int, color: str):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def _spread_dialog():
    """双图弹窗：左图 200×100 @ (0,0)，右图 150×80 @ (250,10)。均为不透明
    纯色图（入口收紧不触发，trim 恒 (0,0)，断言里不含收紧变量）。"""
    from desktop.components.viewers.image_editor import ImageEditorDialog

    left = _make_image(200, 100, "#ffffff")
    right = _make_image(150, 80, "#dddddd")
    items = [
        {"image": left, "file": "_left.png", "rect": (0, 0, 200, 100)},
        {"image": right, "file": "_right.png", "rect": (250, 10, 150, 80)},
    ]
    dialog = ImageEditorDialog(None, left, save_back=True)
    dialog.configure_multiple_images(items)
    return dialog, left, right


def run(ctx) -> None:
    from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
    from PySide6.QtGui import QMouseEvent, QTransform

    from tests.selftests._context import ok

    from desktop.components.viewers.image_editor.consts import CLIPPING_DEFAULT

    dialog, left, right = _spread_dialog()
    canvas = dialog.canvas

    # ---- 1. 场景矩形 ∪ 双图（画布完整显示两张图） ----
    ok("双图：换层后非活动图元挂在场景里",
       canvas._context_item is not None, "")
    context_rect = canvas._context_item.sceneBoundingRect()
    ok("双图：场景矩形完整包住两张图（旧版 _sync_scene_rect 被同名旧版遮蔽）",
       canvas.sceneRect().contains(QRectF(0, 0, 200, 100))
       and canvas.sceneRect().contains(context_rect),
       f"scene={canvas.sceneRect()} context={context_rect}")
    ok("双图：非活动图摆在两图布局相对位置（scale=1、无收紧 ⇒ offset=delta）",
       canvas._context_offset == QPointF(250, 10),
       f"offset={canvas._context_offset}")

    # ---- 2. 真裁剪 ⇒ 内容原点平移，另一张图不漂 ----
    dialog._pending_crop = QRectF(20, 10, 160, 80)
    dialog._commit_crop()
    ok("裁剪：活动层内容原点平移到裁剪框左上角",
       dialog._multi_layers[0]["origin"] == (20.0, 10.0),
       f"origin={dialog._multi_layers[0]['origin']}")
    ok("裁剪：另一张图相对位置跟着换算（250-20, 10-10）",
       canvas._context_offset == QPointF(230, 0),
       f"offset={canvas._context_offset}")
    ok("裁剪：画布尺寸落到裁剪框",
       canvas.image.width() == 160 and canvas.image.height() == 80, "")

    # ---- 3. 换层：状态保持 + 各层视图 ----
    canvas.set_zoom(1.7)
    zoom_before_switch = canvas._zoom
    transform_before_switch = canvas.transform()
    dialog._switch_context_layer()
    ok("换层：活动层切到右图",
       dialog._active_layer == 1 and canvas.image.width() == 150, "")
    ok("换层不自动适配：view 变换（含缩放倍率）保持不变",
       abs(canvas._zoom - zoom_before_switch) < 1e-6
       and canvas.transform() == transform_before_switch,
       f"zoom={zoom_before_switch}->{canvas._zoom}")
    ok("换层：右图是新层、无历史",
       dialog._undo == [] and not dialog.undo_btn.isEnabled(), "")
    ok("换层：非活动图元切到左图（裁剪后 160×80）",
       canvas._context_item is not None
       and canvas._context_item.boundingRect().width() == 160, "")
    dialog._pending_crop = QRectF(5, 5, 140, 70)
    dialog._commit_crop()
    dialog._switch_context_layer()
    ok("换回：左图恢复裁剪后的状态（尺寸 + 撤销栈 + 原点）",
       dialog._active_layer == 0
       and canvas.image.width() == 160
       and len(dialog._undo) == 1
       and dialog._multi_layers[0]["origin"] == (20.0, 10.0), "")
    ok("换回：视图仍保持原缩放倍率",
       abs(canvas._zoom - zoom_before_switch) < 1e-6,
       f"zoom={canvas._zoom}")
    ok("换回：右图相对位置按两份原点换算（(250+5)-20, (10+5)-10）",
       canvas._context_offset == QPointF(235, 5),
       f"offset={canvas._context_offset}")
    ok("换层快照：列表是浅拷贝（不与 self 共享同一列表对象）",
       dialog._multi_layers[1]["state"]["_undo"] is not dialog._undo, "")

    # ---- 4. 撤销/还原带原点一起退 ----
    dialog._undo_now()
    ok("撤销：左图回到裁剪前，原点退回 (0,0)，另一张图按右图自身原点回位",
       canvas.image.width() == 200
       and dialog._multi_layers[0]["origin"] == (0.0, 0.0)
       and canvas._context_offset == QPointF(255, 15),
       f"origin={dialog._multi_layers[0]['origin']} "
       f"offset={canvas._context_offset}")
    dialog._redo_now()
    ok("重做：原点重新前进到裁剪框",
       dialog._multi_layers[0]["origin"] == (20.0, 10.0)
       and canvas._context_offset == QPointF(235, 5), "")
    dialog._reset_all()
    ok("还原：原点退回本层初值（不透明图恒 (0,0)）",
       canvas.image.width() == 200
       and dialog._multi_layers[0]["origin"] == (0.0, 0.0), "")

    # ---- 5. 变换烘焙（adjust 档）原点平移 ----
    ok("剪裁默认档是 adjust（画布跟着内容长 ⇒ 烘焙后原点必平移）",
       CLIPPING_DEFAULT == "adjust", "")
    dialog._set_tool("transform")
    full = QRectF(0, 0, canvas.image.width(), canvas.image.height())
    canvas._rect = QRectF(full)
    canvas._xf_rect = QRectF(full)
    canvas._xf_region = canvas.image.copy()
    canvas._xf = QTransform().translate(30, 0)   # 内容整体右移 30px
    canvas._xf_touched = True
    ok("变换：挂起就绪", canvas.transform_pending() is not None, "")
    ok("变换烘焙：adjust 档原点平移 ≈ (30, 0)，另一张图回位 250+5-30",
       dialog._commit_transform(force=True)
       and abs(dialog._multi_layers[0]["origin"][0] - 30.0) <= 1.0
       and abs(canvas._context_offset.x() - 225.0) <= 1.0
       and abs(canvas._context_offset.y() - 15.0) <= 1.0,
       f"origin={dialog._multi_layers[0]['origin']} "
       f"offset={canvas._context_offset}")
    dialog._undo_now()
    ok("变换撤销：原点退回烘焙前（还原后的 0,0）",
       dialog._multi_layers[0]["origin"] == (0.0, 0.0), "")

    # ---- 6. 恢复会话进「统一变换」零等待（延迟建预览） ----
    dialog._set_tool("transform")
    seed = QTransform().translate(5, 5)
    region = _make_image(40, 30, "#00ff00")
    canvas.begin_restored_transform(seed, region, QRectF(0, 0, 40, 30))
    ok("恢复会话：进工具即挂上内容框与矩阵（画布不换图）",
       canvas._xf_rect == QRectF(0, 0, 40, 30) and canvas._xf == seed
       and canvas.image.width() == 200, "")
    ok("恢复会话：**不**在进工具那一刻建预览（旧版缓存命中路径在这里"
       "重铺底图+重采样浮层 ⇒ 每次切进「统一变换」卡半秒）",
       canvas._float_item is None, "")
    canvas._ensure_transform_preview()
    ok("恢复会话：首次拖动才建预览（浮层用 upright 区域）",
       canvas._float_item is not None
       and canvas._xf_region.width() == 40, "")

    # ---- ghost：切层**不**烘焙，旋转效果在另一边也看得见（2026-10-13） ----
    # 先钉"像素改写"这条路（用户 2026-10-13 报障：Left 改了切到 Right，
    # Left 显示的还是改前 LeftA）：擦除/文字都是就地改 `_image`，切走时
    # 快照必须抓到改后的帧，非活动态显示的恒是"切换前的最新状态"。
    dialog3, left3, right3 = _spread_dialog()
    from PySide6.QtGui import QColor, QPainter, QPen

    painter = QPainter(dialog3._image)
    painter.setPen(QPen(QColor("#111111"), 12))
    painter.drawLine(20, 20, 120, 70)
    painter.end()
    dialog3.canvas.replace_image(dialog3._image)
    dialog3._switch_context_layer()
    ctx = dialog3.canvas._context_image
    ok("像素改写切走：非活动态显示改后的 LeftB（黑杠在）",
       ctx is not None
       and ctx.pixelColor(60, 40).red() < 100
       and dialog3._multi_layers[0]["state"]["_image"].pixelColor(60, 40).red()
       < 100, "")
    dialog3._switch_context_layer()
    dialog3._switch_context_layer()
    ok("二轮往返：非活动态仍是 LeftB",
       dialog3.canvas._context_image.pixelColor(60, 40).red() < 100, "")
    dialog3.close()
    dialog3.release_buffers()

    dialog2, left2, right2 = _spread_dialog()
    c2 = dialog2.canvas
    dialog2._set_tool("transform")
    c2.transform_rotate(15)          # 语义入口：建实时预览（浮层在屏、像素没动）
    ok("挂起变换：浮层在屏、像素未烘焙",
       c2._float_item is not None and c2.transform_pending() is not None, "")
    dialog2._switch_context_layer()  # → 右图
    ghost = dialog2._multi_layers[0]["ghost"]
    ok("切层不烘焙：左层存了 ghost（含旋转效果），state 像素原样",
       ghost is not None and ghost.width() > 200
       and dialog2._multi_layers[0]["state"]["_image"].width() == 200,
       f"ghost={ghost and ghost.width()}")
    ok("非活动层的旋转效果看得见：context 图就是 ghost",
       c2._context_image is not None and ghost is not None
       and c2._context_image.width() == ghost.width(), "")
    ok("非活动层挂起变换算改过（「完成」覆盖确认不漏）",
       dialog2._layer_has_changes(dialog2._multi_layers[0]), "")
    dialog2._switch_context_layer()  # → 回左图
    ok("切回：实时预览原样恢复、ghost 作废",
       dialog2._multi_layers[0]["ghost"] is None
       and c2._float_item is not None
       and c2.transform_pending() is not None, "")
    dialog2._switch_context_layer()  # 又切走：左层带 ghost 挂起
    dialog2._bake_inactive_pending()
    ok("「完成」补烘焙：左层挂起变换落进像素、ghost 与画布快照清空",
       dialog2._multi_layers[0]["ghost"] is None
       and dialog2._multi_layers[0]["canvas_state"] is None
       and dialog2._multi_layers[0]["state"]["_image"].width() > 200, "")
    ok("补烘焙不打扰活动层：右层仍是活动层",
       dialog2._active_layer == 1, "")

    # ---- 切层不跳：场景矩形在两层坐标系里必须是同一块版面地盘 ----
    # （2026-10-13「点击 Left 两图向左移、点击 Right 向右移」的根：非活动
    #   侧曾按 ghost 外扩算并集，AlignCenter/滚动条每切一层整体平移一次）
    def _sheet_scene_rect(dlg):
        layer = dlg._multi_layers[dlg._active_layer]
        sx, sy = dlg._layer_scale(layer)
        ox, oy = dlg._layer_display_origin(layer)
        rect = dlg.canvas.sceneRect()
        return QRectF(layer["rect"].x() + (rect.x() + ox) * sx,
                      layer["rect"].y() + (rect.y() + oy) * sy,
                      rect.width() * sx, rect.height() * sy)

    rect_right = _sheet_scene_rect(dialog2)
    dialog2._switch_context_layer()
    rect_left = _sheet_scene_rect(dialog2)
    ok("切层不跳：两层坐标系里场景矩形是同一块版面地盘",
       abs(rect_right.x() - rect_left.x()) < 0.5
       and abs(rect_right.y() - rect_left.y()) < 0.5
       and abs(rect_right.width() - rect_left.width()) < 0.5
       and abs(rect_right.height() - rect_left.height()) < 0.5,
       f"right={rect_right} left={rect_left}")

    # ---- 边框：虚线、双方都有、包裹单张图片当前内容并随内容移动 ----
    from PySide6.QtCore import Qt

    ok("边框是虚线（不再是实体黑线）",
       dialog2.canvas._border_pen().style() == Qt.PenStyle.DashLine, "")
    ok("非活动图也有自己的虚线边框",
       dialog2.canvas._context_border is not None, "")
    ok("非活动图虚线框贴着它的内容（与显示矩形同尺，不虚胖）",
       dialog2.canvas._context_display_rect is not None
       and abs(dialog2.canvas._context_border.rect().width()
               - dialog2.canvas._context_display_rect.width()) < 2, "")
    c2.transform_rotate(45)   # 在已有挂起变换上再转：框 = 累计内容外框
    box = c2._border.rect()
    ok("边框包裹单图当前内容：随内容移动、不钉在原矩形上（不是并集）",
       box.top() < -1 and box.width() < c2.image_rect().width() + 0.5,
       f"border={box} image_rect={c2.image_rect()}")

    # ---- 内容被变换搬远后，场景矩形要圈住它（滚动条够得到，不"显示不全"） ----
    c2.transform_move(300, 0)
    dialog2._switch_context_layer()   # 搬过的层切走 → 变非活动 ghost
    ok("内容搬出基准范围后场景矩形跟着扩（可滚动可见，不显示不全）",
       dialog2.canvas._context_display_rect is not None
       and dialog2.canvas.sceneRect().contains(
           dialog2.canvas._context_display_rect), "")

    # ---- 右侧面板：激活图层显示 + 切换 ----
    active = dialog2._active_layer
    ok("右侧面板：图层按钮齐备且随激活层点亮",
       [b.text() for b in dialog2._layer_buttons] == ["左图", "右图"]
       and dialog2._layer_buttons[active].isChecked()
       and not dialog2._layer_buttons[1 - active].isChecked(), "")
    dialog2._activate_layer(1 - active)
    ok("右侧面板：点另一张即切换激活层",
       dialog2._active_layer == 1 - active
       and dialog2._layer_buttons[1 - active].isChecked()
       and not dialog2._layer_buttons[active].isChecked(), "")
    dialog2._activate_layer(dialog2._active_layer)   # 点当前层：不空跑切层
    ok("右侧面板：点当前层不触发切层",
       dialog2._layer_buttons[dialog2._active_layer].isChecked(), "")

    dialog2.close()
    dialog2.release_buffers()

    # ---- 拼版缩放不同也不自动调整 view 中心/倍率 ----
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import CheckBox

    from desktop.components.viewers.image_editor import ImageEditorDialog

    left4 = _make_image(200, 100, "#ffffff")
    right4 = _make_image(150, 80, "#dddddd")
    dialog4 = ImageEditorDialog(None, left4, save_back=True)
    dialog4.configure_multiple_images([
        {"image": left4, "file": "_l4.png", "rect": (0, 0, 200, 100)},
        {"image": right4, "file": "_r4.png",
         "rect": (250, 10, 150 * 1.57, 80 * 1.57)},
    ])
    c4 = dialog4.canvas
    dialog4.resize(1400, 900)
    dialog4.show()
    QApplication.processEvents()
    c4.fit()
    QApplication.processEvents()

    zoom_before_switch = c4._zoom
    transform_before_switch = c4.transform()
    context_pixmap_key = c4._context_item.pixmap().cacheKey()
    active_pixmap_key = c4._item.pixmap().cacheKey()
    dialog4._switch_context_layer()
    ok("拼版缩放不同时：切层不自动适配，view 变换和倍率保持不变",
       abs(c4._zoom - zoom_before_switch) < 1e-6
       and c4.transform() == transform_before_switch,
       f"zoom={zoom_before_switch}->{c4._zoom}")
    ok("切层复用两张图片的 QPixmap，不重复整图转换",
       c4._item.pixmap().cacheKey() == context_pixmap_key
       and c4._context_item.pixmap().cacheKey() == active_pixmap_key, "")
    dialog4._set_tool("transform")
    auto_fit_boxes = [
        box for box in dialog4._option_page.findChildren(CheckBox)
        if box.text() == "是否自动缩放画布"
    ]
    ok("统一变换选项：自动缩放画布默认不勾选",
       len(auto_fit_boxes) == 1 and not auto_fit_boxes[0].isChecked()
       and not c4._xf_auto_fit_canvas, "")
    click_pos = QPointF(c4.mapFromScene(QPointF(100, 50)))
    click = QMouseEvent(
        QEvent.Type.MouseButtonPress, click_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease, click_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier)
    c4.mousePressEvent(click)
    c4.mouseReleaseEvent(release)
    ok("统一变换：纯点选图片不创建重采样预览",
       c4._float_item is None and c4._mode is None, "")
    zoom_before_move = c4._zoom
    left_screen_before_move = c4.mapFromScene(QPointF(100, 50))
    scene_rect_before_move = c4.sceneRect()
    c4.transform_move(400, 0)
    ok("默认关闭时：移动图片不自动缩放画布",
       abs(c4._zoom - zoom_before_move) < 1e-6, f"{zoom_before_move}->{c4._zoom}")
    QApplication.processEvents()
    left_screen_after_move = c4.mapFromScene(QPointF(100, 50))
    ok("默认关闭时：移动图片不自动居中或平移画布",
       (left_screen_after_move - left_screen_before_move).manhattanLength() <= 3,
       f"{left_screen_before_move}->{left_screen_after_move}, "
       f"scene-rect={scene_rect_before_move}->{c4.sceneRect()}")
    auto_fit_boxes[0].setChecked(True)
    zoom_before_auto_fit = c4._zoom
    c4.transform_move(400, 0)
    content_center_after_auto_fit = c4._content_scene_rect().center()
    content_center_in_view = c4.mapFromScene(content_center_after_auto_fit)
    view_center = c4.viewport().rect().center()
    ok("勾选后：变换结束自动缩放并居中画布",
       c4._xf_auto_fit_canvas and c4._zoom < zoom_before_auto_fit
       and (content_center_in_view - view_center).manhattanLength() <= 20,
       f"zoom={zoom_before_auto_fit}->{c4._zoom}, "
       f"content-center-view={content_center_in_view}, "
       f"viewport-center={view_center}")
    dialog4.close()
    dialog4.release_buffers()

    # ---- 大图变换 ghost：先应用浮层变换、再移到 ghost 原点 ----
    # 小图预览倍率为 1，无法暴露坐标系顺序错误；大图降采样后，若先平移
    # 再缩放，非活动图虚线框仍对，但 ghost 内容会被裁掉一截。
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
    ok("大图右移切层：ghost 内容仍完整贴合虚线框",
       visible_columns
       and visible_columns[0] <= 2
       and visible_columns[-1] >= ghost_image.width() - 6
       and dialog5.canvas._context_border.rect()
       == dialog5.canvas._context_item.sceneBoundingRect(),
       f"image={ghost_image.size()}, "
       f"visible=({visible_columns[0] if visible_columns else None}, "
       f"{visible_columns[-1] if visible_columns else None})")
    dialog5.close()
    dialog5.release_buffers()

    dialog.close()
    dialog.release_buffers()
    ok("释放：双图各层整图缓冲一并放掉",
       all(layer["state"]["_image"] is None for layer in dialog._multi_layers),
       "")
