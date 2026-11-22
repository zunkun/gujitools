# -*- coding: utf-8 -*-
"""1. 场景矩形 ∪ 双图（画布完整显示两张图） / 2. 真裁剪 ⇒ 内容原点平移，另一张图不漂 / 3. 换层：状态保持 + 各层视图 / 4. 撤销/还原带原点一起退 / 5. 变换烘焙（adjust 档）原点平移 / 6. 恢复会话进「统一变换」零等待（延迟建预览） / 7. 首次拖动**不**白出一帧精确重采样（2026-10-14 卡顿报障） / 8. 建预览失败/放弃拖动不能把画布永久留在\"拖动中\" / 裁剪\"移动\"留白 → 非活动图虚线框必须贴内容，不吃透明边距 / 5b. 裁剪\"移动\"→应用：回报给拼版的 rect 是**内容**且**整份平移** / ghost：切层**不**烘焙，旋转效果在另一边也看得见（2026-10-13） / 切层不跳：场景矩形在两层坐标系里必须是同一块版面地盘 / 边框：虚线、双方都有、包裹单张图片当前内容并随内容移动 / 内容被变换搬远后，场景矩形要圈住它（滚动条够得到，不\"显示不全\"） / 右侧面板：激活图层显示 + 切换"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import NAME, _make_image, _spread_dialog
    from desktop.components.viewers.image_editor.consts import CLIPPING_DEFAULT
    from pathlib import Path
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtGui import QColor, QPainter, QPen
    from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
    from PySide6.QtGui import QMouseEvent, QTransform
    from tests.selftests._context import ok
    from tests.common.tmpdir import temp_dir
    ok("双图：换层后非活动图元挂在场景里",
       st.canvas._context_item is not None, "")
    context_rect = st.canvas._context_item.sceneBoundingRect()
    ok("双图：场景矩形完整包住两张图（旧版 _sync_scene_rect 被同名旧版遮蔽）",
       st.canvas.sceneRect().contains(QRectF(0, 0, 200, 100))
       and st.canvas.sceneRect().contains(context_rect),
       f"scene={st.canvas.sceneRect()} context={context_rect}")
    ok("双图：非活动图摆在两图布局相对位置（scale=1、无收紧 ⇒ offset=delta）",
       st.canvas._context_offset == QPointF(250, 10),
       f"offset={st.canvas._context_offset}")
    st.dialog._pending_crop = QRectF(20, 10, 160, 80)
    st.dialog._commit_crop()
    ok("裁剪：活动层内容原点平移到裁剪框左上角",
       st.dialog._multi_layers[0]["origin"] == (20.0, 10.0),
       f"origin={st.dialog._multi_layers[0]['origin']}")
    ok("裁剪：另一张图相对位置跟着换算（250-20, 10-10）",
       st.canvas._context_offset == QPointF(230, 0),
       f"offset={st.canvas._context_offset}")
    ok("裁剪：画布尺寸落到裁剪框",
       st.canvas.image.width() == 160 and st.canvas.image.height() == 80, "")
    st.canvas.set_zoom(1.7)
    zoom_before_switch = st.canvas._zoom
    transform_before_switch = st.canvas.transform()
    st.dialog._switch_context_layer()
    ok("换层：活动层切到右图",
       st.dialog._active_layer == 1 and st.canvas.image.width() == 150, "")
    ok("换层不自动适配：view 变换（含缩放倍率）保持不变",
       abs(st.canvas._zoom - zoom_before_switch) < 1e-6
       and st.canvas.transform() == transform_before_switch,
       f"zoom={zoom_before_switch}->{st.canvas._zoom}")
    ok("换层：右图是新层、无历史",
       st.dialog._undo == [] and not st.dialog.undo_btn.isEnabled(), "")
    ok("换层：非活动图元切到左图（裁剪后 160×80）",
       st.canvas._context_item is not None
       and st.canvas._context_item.boundingRect().width() == 160, "")
    st.dialog._pending_crop = QRectF(5, 5, 140, 70)
    st.dialog._commit_crop()
    st.dialog._switch_context_layer()
    ok("换回：左图恢复裁剪后的状态（尺寸 + 撤销栈 + 原点）",
       st.dialog._active_layer == 0
       and st.canvas.image.width() == 160
       and len(st.dialog._undo) == 1
       and st.dialog._multi_layers[0]["origin"] == (20.0, 10.0), "")
    ok("换回：视图仍保持原缩放倍率",
       abs(st.canvas._zoom - zoom_before_switch) < 1e-6,
       f"zoom={st.canvas._zoom}")
    ok("换回：右图相对位置按两份原点换算（(250+5)-20, (10+5)-10）",
       st.canvas._context_offset == QPointF(235, 5),
       f"offset={st.canvas._context_offset}")
    ok("换层快照：列表是浅拷贝（不与 self 共享同一列表对象）",
       st.dialog._multi_layers[1]["state"]["_undo"] is not st.dialog._undo, "")
    st.dialog._undo_now()
    ok("撤销：左图回到裁剪前，原点退回 (0,0)，另一张图按右图自身原点回位",
       st.canvas.image.width() == 200
       and st.dialog._multi_layers[0]["origin"] == (0.0, 0.0)
       and st.canvas._context_offset == QPointF(255, 15),
       f"origin={st.dialog._multi_layers[0]['origin']} "
       f"offset={st.canvas._context_offset}")
    st.dialog._redo_now()
    ok("重做：原点重新前进到裁剪框",
       st.dialog._multi_layers[0]["origin"] == (20.0, 10.0)
       and st.canvas._context_offset == QPointF(235, 5), "")
    st.dialog._reset_all()
    ok("还原：原点退回本层初值（不透明图恒 (0,0)）",
       st.canvas.image.width() == 200
       and st.dialog._multi_layers[0]["origin"] == (0.0, 0.0), "")
    ok("剪裁默认档是 adjust（画布跟着内容长 ⇒ 烘焙后原点必平移）",
       CLIPPING_DEFAULT == "adjust", "")
    st.dialog._set_tool("transform")
    full = QRectF(0, 0, st.canvas.image.width(), st.canvas.image.height())
    st.canvas._rect = QRectF(full)
    st.canvas._xf_rect = QRectF(full)
    st.canvas._xf_region = st.canvas.image.copy()
    st.canvas._xf = QTransform().translate(30, 0)   # 内容整体右移 30px
    st.canvas._xf_touched = True
    ok("变换：挂起就绪", st.canvas.transform_pending() is not None, "")
    ok("变换烘焙：adjust 档原点平移 ≈ (30, 0)，另一张图回位 250+5-30",
       st.dialog._commit_transform(force=True)
       and abs(st.dialog._multi_layers[0]["origin"][0] - 30.0) <= 1.0
       and abs(st.canvas._context_offset.x() - 225.0) <= 1.0
       and abs(st.canvas._context_offset.y() - 15.0) <= 1.0,
       f"origin={st.dialog._multi_layers[0]['origin']} "
       f"offset={st.canvas._context_offset}")
    st.dialog._undo_now()
    ok("变换撤销：原点退回烘焙前（还原后的 0,0）",
       st.dialog._multi_layers[0]["origin"] == (0.0, 0.0), "")
    st.dialog._set_tool("transform")
    seed = QTransform().translate(5, 5)
    region = _make_image(40, 30, "#00ff00")
    st.canvas.begin_restored_transform(seed, region, QRectF(0, 0, 40, 30))
    ok("恢复会话：进工具即挂上内容框与矩阵（画布不换图）",
       st.canvas._xf_rect == QRectF(0, 0, 40, 30) and st.canvas._xf == seed
       and st.canvas.image.width() == 200, "")
    ok("恢复会话：**不**在进工具那一刻建预览（旧版缓存命中路径在这里"
       "重铺底图+重采样浮层 ⇒ 每次切进「统一变换」卡半秒）",
       st.canvas._float_item is None, "")
    st.canvas._ensure_transform_preview()
    ok("恢复会话：首次拖动才建预览（浮层用 upright 区域）",
       st.canvas._float_item is not None
       and st.canvas._xf_region.width() == 40, "")
    dialog7, _l7, _r7 = _spread_dialog()
    c7 = dialog7.canvas
    dialog7._set_tool("transform")
    exact_calls = []
    original_plane7 = c7._render_float_plane

    def counting_plane7():
        exact_calls.append(1)
        return original_plane7()

    c7._render_float_plane = counting_plane7
    try:
        mode7 = c7._begin_transform_drag(
            "inside", QPointF(c7._rect.center()),
            Qt.KeyboardModifier.NoModifier)
        ok("统一变换：首次拖动建预览时不做逐像素精确重采样"
           "（否则那几百 ms 全卡在按下瞬间，且随即被快档覆盖）",
           mode7 is not None and not exact_calls,
           f"重采样次数={len(exact_calls)}")
        ok("统一变换：首次拖动建完预览即处于拖动态"
           "（松手才补精确帧，预览 == 烘焙的判据不松）",
           c7._xf_dragging is True, f"_xf_dragging={c7._xf_dragging}")
        c7._apply_transform_drag(
            mode7, QPointF(c7._rect.center().x() + 20, c7._rect.center().y()),
            Qt.KeyboardModifier.NoModifier)
        c7.finish_transform_drag()
        ok("统一变换：松手仍补一帧精确结果（拖动中快档没被当成最终画面）",
           exact_calls == [1], f"重采样次数={len(exact_calls)}")
    finally:
        del c7._render_float_plane
    dialog7.close()
    dialog7.release_buffers()
    dialog8, _l8, _r8 = _spread_dialog()
    c8 = dialog8.canvas
    dialog8._set_tool("transform")

    def boom8():
        raise RuntimeError("建预览炸了")

    c8._ensure_transform_preview = boom8
    raised8 = False
    try:
        c8._begin_transform_drag(
            "inside", QPointF(c8._rect.center()),
            Qt.KeyboardModifier.NoModifier)
    except RuntimeError:
        raised8 = True
    del c8._ensure_transform_preview
    ok("统一变换：建预览抛异常时清掉拖动态（否则之后一直退化成快档、"
       "松手也不补精确帧）",
       raised8 and c8._xf_dragging is False,
       f"raised={raised8} _xf_dragging={c8._xf_dragging}")
    dialog8.close()
    dialog8.release_buffers()
    dialog_c, left_c, right_c = _spread_dialog()
    cc = dialog_c.canvas
    dialog_c._set_tool("crop")
    # 框内拖动 = crop_move：图片图元与选区一起平移
    cc._mode = ("crop_move", QPointF(100, 50), QRectF(cc._rect),
                QPointF(cc._crop_offset))
    cc._crop_offset = QPointF(-40, 30)
    cc._item.setPos(cc._crop_offset)
    cc._rect = QRectF(cc._rect).translated(QPointF(-40, 30))
    cc._sync_border()
    dialog_c._pending_crop = QRectF(cc._rect)
    dialog_c._pending_crop_offset = (cc._crop_offset.x(), cc._crop_offset.y())
    dialog_c._switch_context_layer()          # → 右图，Left 变成非活动图
    left_image = dialog_c._multi_layers[0]["state"]["_image"]
    ok("裁剪移动：像素被挪进更大的图（透明边距编码位移）",
       left_image.width() > 200 and left_image.height() > 100,
       f"image={left_image.width()}x{left_image.height()}")
    cb = cc._context_border
    ok("非活动图虚线框贴内容外框，不吃透明留白（旧版取整张 pixmap 外框，"
       "留白朝上/右时正好撑到另一张图那边去）",
       cb is not None
       and abs(cb.rect().width() - 200) <= 1
       and abs(cb.rect().height() - 100) <= 1,
       f"border={cb.rect() if cb else None}")
    ok("非活动图虚线框与场景矩形并集同口径（都按内容，不白撑留白）",
       cc._context_display_rect is not None and cb is not None
       and abs(cc._context_display_rect.width() - cb.rect().width()) <= 1
       and abs(cc._context_display_rect.height() - cb.rect().height()) <= 1,
       f"display={cc._context_display_rect} border={cb.rect()}")
    dialog_c.close()
    dialog_c.release_buffers()
    updates: list = []
    dialog_u, left_u, right_u = _spread_dialog()
    dialog_u._ask_overwrite = lambda: True
    dialog_u.multi_layout_saved.connect(
        lambda batch: updates.extend(batch if isinstance(batch, list) else [batch]))
    dialog_u.multi_image_saved.connect(lambda *args: None)
    # ⚠️ 本用例会**真调** ``_save_multiple_images``（它内部 overwrite 到
    #    ``layer["file"]``），而 ``_spread_dialog`` 用的是 "_left.png" 这种
    #    假路径 ⇒ 会真的往**当前工作目录**写文件、污染仓库根。把两层
    #    路径改到临时目录再跑（只借它的双图布局，不写回原路径）。
    tmp_dir = temp_dir(f"guji_multi_save_{NAME}_")
    left_file = str(Path(tmp_dir) / "left.png")
    right_file = str(Path(tmp_dir) / "right.png")
    for layer, path_text in ((dialog_u._multi_layers[0], left_file),
                             (dialog_u._multi_layers[1], right_file)):
        layer["file"] = path_text
    dialog_u._multi_layers[0]["page_item_index"] = 0
    dialog_u._multi_layers[1]["page_item_index"] = 1
    cu = dialog_u.canvas
    dialog_u._set_tool("crop")
    MOVE = 20.0
    cu._mode = ("crop_move", QPointF(100, 50), QRectF(cu._rect),
                QPointF(cu._crop_offset))
    cu._crop_offset = QPointF(0, MOVE)
    cu._item.setPos(cu._crop_offset)
    cu._rect = QRectF(cu._rect).translated(QPointF(0, MOVE))
    cu._sync_border()
    dialog_u._preview_crop()
    dialog_u._commit_crop()
    dialog_u._save_multiple_images()
    moved_image = dialog_u._multi_layers[0]["state"]["_image"]
    ok("裁剪移动：像素图长高（留白编码位移），但可见内容尺寸不变",
       moved_image.height() == 100 + int(MOVE)
       # ⚠️ 2026-10-15 修正：位移已由透明留白烤进像素，``origin`` **不再重复
       #    计入**（旧期望 ``(0, MOVE)`` 钉的是 ``box + shift``，正位移时等于
       #    「过冲一个位移」＝用户报障的「拖动后两图重合／挨得比拖动时更近」）。
       and dialog_u._multi_layers[0]["origin"] == (0.0, 0.0),
       f"image_h={moved_image.height()} "
       f"origin={dialog_u._multi_layers[0]['origin']} 期望=(0.0, 0.0)")
    ok("应用回报：宽高按**可见内容**（不是含留白的整张图），"
       "否则拼版虚线框比图大一圈",
       bool(updates)
       and abs(updates[0]["rect"][3] - 100) <= 1,
       f"updates={updates}")
    ok("应用回报：**整份平移**了位移量且大小不变"
       "（旧版顶部原地不动、底部长出一截 ⇒ 左右不等高）",
       bool(updates)
       and abs(updates[0]["rect"][1] - MOVE) <= 1
       and abs(updates[0]["rect"][3] - 100) <= 1,
       f"rect={updates[0]['rect'] if updates else None}")
    dialog_u.close()
    dialog_u.release_buffers()
    dialog3, left3, right3 = _spread_dialog()
    from PySide6.QtGui import QColor, QPainter, QPen

    painter = QPainter(dialog3._image)
    painter.setPen(QPen(QColor("#111111"), 12))
    painter.drawLine(20, 20, 120, 70)
    painter.end()
    dialog3.canvas.replace_image(dialog3._image)
    dialog3._switch_context_layer()
    st.ctx = dialog3.canvas._context_image
    ok("像素改写切走：非活动态显示改后的 LeftB（黑杠在）",
       st.ctx is not None
       and st.ctx.pixelColor(60, 40).red() < 100
       and dialog3._multi_layers[0]["state"]["_image"].pixelColor(60, 40).red()
       < 100, "")
    dialog3._switch_context_layer()
    dialog3._switch_context_layer()
    ok("二轮往返：非活动态仍是 LeftB",
       dialog3.canvas._context_image.pixelColor(60, 40).red() < 100, "")
    dialog3.close()
    dialog3.release_buffers()

    st.dialog2, left2, right2 = _spread_dialog()
    st.c2 = st.dialog2.canvas
    st.dialog2._set_tool("transform")
    st.c2.transform_rotate(15)          # 语义入口：建实时预览（浮层在屏、像素没动）
    ok("挂起变换：浮层在屏、像素未烘焙",
       st.c2._float_item is not None and st.c2.transform_pending() is not None, "")
    st.dialog2._switch_context_layer()  # → 右图
    ghost = st.dialog2._multi_layers[0]["ghost"]
    ok("切层不烘焙：左层存了 ghost（含旋转效果），state 像素原样",
       ghost is not None and ghost.width() > 200
       and st.dialog2._multi_layers[0]["state"]["_image"].width() == 200,
       f"ghost={ghost and ghost.width()}")
    ok("非活动层的旋转效果看得见：context 图就是 ghost",
       st.c2._context_image is not None and ghost is not None
       and st.c2._context_image.width() == ghost.width(), "")
    ok("非活动层挂起变换算改过（「完成」覆盖确认不漏）",
       st.dialog2._layer_has_changes(st.dialog2._multi_layers[0]), "")
    st.dialog2._switch_context_layer()  # → 回左图
    ok("切回：实时预览原样恢复、ghost 作废",
       st.dialog2._multi_layers[0]["ghost"] is None
       and st.c2._float_item is not None
       and st.c2.transform_pending() is not None, "")
    st.dialog2._switch_context_layer()  # 又切走：左层带 ghost 挂起
    st.dialog2._bake_inactive_pending()
    ok("「完成」补烘焙：左层挂起变换落进像素、ghost 与画布快照清空",
       st.dialog2._multi_layers[0]["ghost"] is None
       and st.dialog2._multi_layers[0]["canvas_state"] is None
       and st.dialog2._multi_layers[0]["state"]["_image"].width() > 200, "")
    ok("补烘焙不打扰活动层：右层仍是活动层",
       st.dialog2._active_layer == 1, "")
    def _sheet_scene_rect(dlg):
        layer = dlg._multi_layers[dlg._active_layer]
        sx, sy = dlg._layer_scale(layer)
        ox, oy = dlg._layer_display_origin(layer)
        rect = dlg.canvas.sceneRect()
        return QRectF(layer["rect"].x() + (rect.x() + ox) * sx,
                      layer["rect"].y() + (rect.y() + oy) * sy,
                      rect.width() * sx, rect.height() * sy)

    rect_right = _sheet_scene_rect(st.dialog2)
    st.dialog2._switch_context_layer()
    rect_left = _sheet_scene_rect(st.dialog2)
    ok("切层不跳：两层坐标系里场景矩形是同一块版面地盘",
       abs(rect_right.x() - rect_left.x()) < 0.5
       and abs(rect_right.y() - rect_left.y()) < 0.5
       and abs(rect_right.width() - rect_left.width()) < 0.5
       and abs(rect_right.height() - rect_left.height()) < 0.5,
       f"right={rect_right} left={rect_left}")
    from PySide6.QtCore import Qt

    ok("边框是虚线（不再是实体黑线）",
       st.dialog2.canvas._border_pen().style() == Qt.PenStyle.DashLine, "")
    ok("非活动图也有自己的虚线边框",
       st.dialog2.canvas._context_border is not None, "")
    ok("非活动图虚线框贴着它的内容（与显示矩形同尺，不虚胖）",
       st.dialog2.canvas._context_display_rect is not None
       and abs(st.dialog2.canvas._context_border.rect().width()
               - st.dialog2.canvas._context_display_rect.width()) < 2, "")
    st.c2.transform_rotate(45)   # 在已有挂起变换上再转：框 = 累计内容外框
    box = st.c2._border.rect()
    ok("边框包裹单图当前内容：随内容移动、不钉在原矩形上（不是并集）",
       box.top() < -1 and box.width() < st.c2.image_rect().width() + 0.5,
       f"border={box} image_rect={st.c2.image_rect()}")
    st.c2.transform_move(300, 0)
    st.dialog2._switch_context_layer()   # 搬过的层切走 → 变非活动 ghost
    ok("内容搬出基准范围后场景矩形跟着扩（可滚动可见，不显示不全）",
       st.dialog2.canvas._context_display_rect is not None
       and st.dialog2.canvas.sceneRect().contains(
           st.dialog2.canvas._context_display_rect), "")
    active = st.dialog2._active_layer
    ok("右侧面板：图层按钮齐备且随激活层点亮",
       [b.text() for b in st.dialog2._layer_buttons] == ["左图", "右图"]
       and st.dialog2._layer_buttons[active].isChecked()
       and not st.dialog2._layer_buttons[1 - active].isChecked(), "")
    st.dialog2._activate_layer(1 - active)
    ok("右侧面板：点另一张即切换激活层",
       st.dialog2._active_layer == 1 - active
       and st.dialog2._layer_buttons[1 - active].isChecked()
       and not st.dialog2._layer_buttons[active].isChecked(), "")
    st.dialog2._activate_layer(st.dialog2._active_layer)   # 点当前层：不空跑切层
    ok("右侧面板：点当前层不触发切层",
       st.dialog2._layer_buttons[st.dialog2._active_layer].isChecked(), "")

    st.dialog2.close()
    st.dialog2.release_buffers()

