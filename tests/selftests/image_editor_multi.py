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
7. **自动缩放只发生在"操作结束"，绝不发生在"点图切换"**（2026-10-14 用户
   口径）：点另一张图切层时视图必须**纹丝不动**（图片原来什么样、切换后还是
   什么样，保操作连续性）；自动缩放只在一次变换**松手之后**发生，且受开关
   约束。判据一律按**图片身份**（左图/右图）追踪各图中心的屏幕坐标——用
   "活动图/非活动图"这种会换人的槽位当不变量，量出来的位移是假的。
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
    from pathlib import Path
    from tests.tmpdir import temp_dir

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

    # ---- 7. 首次拖动**不**白出一帧精确重采样（2026-10-14 卡顿报障）----
    # 根因：``_begin_transform_drag`` 旧版先建预览、后置 ``_xf_dragging``，
    # 而 ``_sync_float`` 按这个标志分岔 ⇒ 建预览那一刻走了
    # ``_render_float_plane`` 的逐像素精确重采样（12 MP 实测 467 ms），
    # 紧接着第一次 move 就被 ``_apply_float_fast`` 整帧覆盖 ⇒ 纯浪费，
    # 且全卡在"按下"瞬间（用户报障：初次点击移动卡顿、几秒后正常、
    # 每换一张图重来一次）。这里钉死"建预览那一刻不得重采样"。
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

    # ---- 8. 建预览失败/放弃拖动不能把画布永久留在"拖动中" ----
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

    # ---- 裁剪"移动"留白 → 非活动图虚线框必须贴内容，不吃透明边距 ----
    # 2026-10-14 用户报障：裁剪框把 Left 移走后切到 Right，Left 的虚线框
    # 被放大（上/右撑到 Right 那边去，看着像串到隔壁图上）。根因：非活动图
    # 的边框取的是**整张 pixmap** 的外接矩形，而 ``_commit_crop`` 的移动
    # 分支会把像素挪进一张更大的图里（透明边距编码位移）⇒ 外框比看得见的
    # 内容大一圈。活动图早就是内容口径，这里钉死两侧一致。
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

    # ---- 5b. 裁剪"移动"→应用：回报给拼版的 rect 是**内容**且**整份平移** ----
    # 2026-10-14 用户报障（这条走的**不是** refresh_rects_for_edited_source，
    # 而是 ``_save_multiple_images`` → ``multi_layout_saved`` →
    # ``apply_editor_layout``）：双图编辑里把 Left 向下移 200px 并应用后，
    # 拼版页左图"变大了"——顶部仍与右图平齐、底部多出一截，左右不等高。
    # 两个独立成因，都要钉：
    #   ① 回报的宽高用**整张像素图**（含透明留白）⇒ 框比图大一圈；
    #   ② ``_multi_layer_shift`` 传 ``box+shift-pad``，而 pad 本身就是位移
    #      （200），正负抵消成 0 ⇒ 位移被吞掉，顶部不跟着走。
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

    # ---- 开关必须管住「适配选区」这条独立路径（2026-10-14 用户报障）----
    # ``fit_selection()`` 自己就 ``resetTransform``+``scale``+``centerOn``，
    # 等价于一次 fit，旧版**完全不看开关** ⇒ 用户没勾选也会被缩放
    # （实测选区 600×800 时 zoom 从 0.3885 直接翻到 0.7810），"选择一下
    # 图片画面就跳"。变换链上的 ``_finish_transform_auto_fit`` 早已认开关，
    # 这里补齐 ⇒ 关闭时不动视图。
    c4._rect = QRectF(60, 30, 80, 40)
    c4._xf_auto_fit_canvas = False
    c4.fit()
    QApplication.processEvents()
    zoom_before_selection_fit = c4._zoom
    c4.fit_selection()
    QApplication.processEvents()
    ok("「是否自动缩放画布」关闭时：适配选区也不缩放"
       "（旧版 fit_selection 无视开关，点选一下画面就跳）",
       abs(c4._zoom - zoom_before_selection_fit) < 1e-6,
       f"zoom={zoom_before_selection_fit}->{c4._zoom}")
    c4._xf_auto_fit_canvas = True
    c4.fit()
    QApplication.processEvents()
    zoom_before_selection_fit_on = c4._zoom
    c4.fit_selection()
    QApplication.processEvents()
    ok("开关勾选时：适配选区照旧生效（别把功能改死）",
       abs(c4._zoom - zoom_before_selection_fit_on) > 1e-6,
       f"zoom={zoom_before_selection_fit_on}->{c4._zoom}")
    dialog4.close()
    dialog4.release_buffers()

    # ---- 切层绝不缩放；自动缩放只发生在"操作结束"（2026-10-14 用户口径）----
    # 「点另一张图切换 ⇒ 视图纹丝不动（图片原来什么样、切换后还是什么样，
    #   保证操作连续性）；自动缩放 ⇒ 只在一次变换松手之后发生、且听开关的」。
    # ⚠️ 判据按**图片身份**追踪各图中心的屏幕坐标。**不能**用"活动图/
    #    非活动图"槽位当不变量——切层时身份换人，同一槽位前后指着不同的图，
    #    量出来的位移是假的（我据此误判过"两图各跳 249px"，A/B 对照后证明
    #    是探针错觉）。
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

    # ---- 开关关闭＝**画面绝对不动**（不只是不缩放，2026-10-14 用户口径
    #      「松鼠标也不要自动缩放**和平移**」）----
    # 裁剪框内移动松手时 ``_sync_scene_rect`` 会换场景矩形，而本视图设了
    # ``setAlignment(AlignCenter)`` ⇒ ``setSceneRect`` **调用本身**就把视口
    # 重排（实测额外平移 27px，zoom 不变）。试过四版补救全部无效（临时改
    # alignment／事后 centerOn／还原滚动条／按矩形位移补偿滚动条）：视口小于
    # 场景时 centerOn 被对齐钳制、居中对齐下滚动条不代表真实位置。
    # ⇒ 开关为假时干脆**不调** ``setSceneRect``，画面一个像素都不动。
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

    # ---- 裁剪负向平移后切工具，再点击切回该层，边框仍贴合非透明内容 ----
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

    # ---- 完成双图编辑：新画布原点/尺寸要回写为页面版面 rect ----
    from tests.tmpdir import temp_dir

    output_dir = temp_dir("guji_editor_layout_")
    left6 = _make_image(200, 100, "#ffffff")
    right6 = _make_image(150, 80, "#dddddd")
    left_path = output_dir / "left.png"
    right_path = output_dir / "right.png"
    assert left6.save(str(left_path)) and right6.save(str(right_path))
    dialog6 = ImageEditorDialog(None, left6, save_back=True)
    dialog6.configure_multiple_images([
        {"image": left6, "file": str(left_path), "rect": (0, 0, 200, 100)},
        {"image": right6, "file": str(right_path),
         "rect": (250, 10, 150, 80)},
    ])
    layout_updates = []
    dialog6.multi_layout_saved.connect(layout_updates.append)
    dialog6._activate_layer(1)
    dialog6._pending_crop = QRectF(20, 5, 120, 60)
    dialog6._commit_crop()
    ok("双图编辑保存：裁剪后的画布位置和尺寸回传页面",
       dialog6._save_multiple_images()
       and layout_updates == [[{
           "index": 1,
           "file": str(right_path),
           # ⚠️ 2026-10-15：位移口径 ＝ **内容框在新画布里的偏移** ＋
           #    **画布原点平移 origin**（两者之和）。**纯裁剪**内容框偏移为 0，
           #    但新画布从被裁掉的 ``box``(20,5) 起 ⇒ 剩下的内容在页面上整体
           #    右/下移一个 ``box`` ⇒ 版面框 = 250+20 / 10+5。只取内容框偏移
           #    会让位置不回写（页面没动、弹窗里却挪了）。
           "rect": [270.0, 15.0, 120.0, 60.0],
       }]],
       f"updates={layout_updates}")
    from desktop.services.imposition import apply_editor_layout

    page_items = [
        {"file": str(left_path), "rect": [0, 0, 200, 100]},
        {"file": str(right_path), "rect": [250, 10, 150, 80]},
    ]
    changed_layout_files = apply_editor_layout(page_items, layout_updates[0])
    ok("拼版页面应用双图编辑布局：左右图间距/重叠按弹窗结果更新",
       changed_layout_files == {str(right_path)}
       and page_items[1]["rect"] == [270.0, 15.0, 120.0, 60.0],
       f"items={page_items}")
    from types import SimpleNamespace

    from desktop.modules.imposition.page import ImpositionModulePage

    module_items = [
        {"file": str(left_path), "rect": [0, 0, 200, 100]},
        {"file": str(right_path), "rect": [250, 10, 150, 80]},
    ]
    module_refreshes = []
    module_invalidations = []
    module_probe = SimpleNamespace(
        _doc={"pages": [{"items": module_items}]},
        _refresh_view=lambda: module_refreshes.append(True),
        _invalidate_page_thumbs_for=module_invalidations.append,
    )
    ImpositionModulePage._after_spread_layout_edited(
        module_probe, 0, layout_updates[0]
    )
    ok("独立拼版页：双图布局更新后重绘画布并失效缩略图",
       module_items[1]["rect"] == [270.0, 15.0, 120.0, 60.0]
       and module_refreshes == [True]
       and module_invalidations == [str(right_path)],
       f"rect={module_items[1]['rect']}, "
       f"refreshes={module_refreshes}, invalidations={module_invalidations}")

    from desktop.pages.taskdetail.imposition_layout import ImpositionLayoutMixin

    task_items = [
        {"file": str(left_path), "rect": [0, 0, 200, 100]},
        {"file": str(right_path), "rect": [250, 10, 150, 80]},
    ]
    persisted_pages = []
    task_probe = SimpleNamespace(
        _imposition_pages=lambda: [{"items": task_items}],
        _save_imposition_pages=persisted_pages.append,
    )
    ImpositionLayoutMixin._on_imposition_spread_layout_saved(
        task_probe, 0, layout_updates[0]
    )
    ok("任务详情页：双图布局更新写回并保存拼版文档",
       task_items[1]["rect"] == [270.0, 15.0, 120.0, 60.0]
       and len(persisted_pages) == 1
       and persisted_pages[0][0]["items"][1]["rect"]
       == [270.0, 15.0, 120.0, 60.0],
       f"rect={task_items[1]['rect']}, saves={len(persisted_pages)}")
    dialog6.close()
    dialog6.release_buffers()

    # ---- 带透明留白的源图：入口版面对齐 + 移动后尺寸不回缩 ----
    # 用户 2026-10-15 报障：拼版页移动图片后进「编辑整图」，弹窗里两张图的
    # 位置/大小与页面**对不上**；在弹窗里移动图片并应用，回到拼版页位置不对、
    # 大小不对（**图片高度被压缩**）。根因两处：入口 ``scale`` 按**整张原图**
    # 算（而拼版 rect 是**可见内容框**），入口 ``origin`` 又把收紧偏移记了一遍。
    from PySide6.QtGui import QColor, QImage, QPainter

    pad_dir = temp_dir("guji_editor_pad_")
    pad_left_path = pad_dir / "pad_left.png"
    pad_right_path = pad_dir / "pad_right.png"

    def _write_padded(path: str) -> None:
        """240×180 里只有 (40,40,160,100) 是不透明内容，其余透明。"""
        image = QImage(240, 180, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.fillRect(QRectF(40, 40, 160, 100), QColor("#ffffff"))
        painter.end()
        assert image.save(path)

    def _write_solid(path: str) -> None:
        """整张不透明（无留白）——左右两图留白不同是报障现场的关键变量。"""
        image = QImage(240, 180, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        assert image.save(path)

    _write_padded(str(pad_left_path))
    _write_solid(str(pad_right_path))
    # 入口按真实链路传 ``QImage(路径)``（整张含留白），rect 用页码面的
    # "整尺寸" 版面（``default_items`` 是整图尺寸口径）——两处都是报障现场。
    # 左右两图页面 rect 一样大（240×180）⇒ 拼版页上两图**看起来一样大**；
    # 弹窗里也必须一样大（见下面的显示尺寸断言）。
    dialog_pad = ImageEditorDialog(None, QImage(str(pad_left_path)),
                                   save_back=True)
    dialog_pad.configure_multiple_images([
        {"image": QImage(str(pad_left_path)), "file": str(pad_left_path),
         "rect": (0, 0, 240, 180)},
        {"image": QImage(str(pad_right_path)), "file": str(pad_right_path),
         "rect": (240, 0, 240, 180)},
    ])
    pad_canvas = dialog_pad.canvas
    pad_layer0 = dialog_pad._multi_layers[0]
    ok("含留白源图：入口比例按**可见内容**算（rect/内容，不是 rect/整图）",
       pad_layer0["scale"] == (1.5, 1.8)
       and dialog_pad._multi_layers[1]["scale"] == (1.0, 1.0)
       and pad_layer0["origin"] == (0.0, 0.0),
       f"scale0={pad_layer0['scale']} "
       f"scale1={dialog_pad._multi_layers[1]['scale']} "
       f"origin={pad_layer0['origin']}")
    # ⚠️ 用户 2026-10-15 报障核心：拼版页上两图一样大，弹窗里左图却明显偏小
    #    （右/左宽比 ≈ 1.18，而页面 ≈ 1.00）。判据＝**两图在弹窗里的显示尺寸
    #    之比必须等于页面 rect 之比**：页面两 rect 都是 240×180 ⇒ 弹窗里
    #    左图（内容 160×100，1:1 显示）与右图（内容 240×180，按 s₁/s₀ 缩）
    #    必须都是 160×100。旧版按整图算比例（s₀=(1,1)）⇒ 右图显示成 240×180，
    #    左图偏小——正是截图里的现象。
    ok("含留白源图：弹窗里两图显示尺寸之比 == 拼版页 rect 之比",
       abs(pad_canvas._context_scale_x * 240 - 160) < 1e-6
       and abs(pad_canvas._context_scale_y * 180 - 100) < 1e-6,
       f"context_scale=({pad_canvas._context_scale_x}, "
       f"{pad_canvas._context_scale_y})")
    # 页面 delta=240、活动比例 1.5 ⇒ 弹窗里两图间距 240/1.5=160（旧版按整图
    # 算比例=1、且 origin 重复计留白 ⇒ 间距被放大到 200，与拼版页对不上）。
    ok("含留白源图：弹窗入口两图相对位置与拼版页一致",
       pad_canvas._context_offset == QPointF(160, 0),
       f"offset={pad_canvas._context_offset}")

    # 弹窗里把活动图整体移动 (30,30)（选区随图一起走 ⇒ 内容尺寸不变）。
    dialog_pad._pending_crop = QRectF(30, 30, 160, 100)
    dialog_pad._pending_crop_offset = (30.0, 30.0)
    dialog_pad._commit_crop()
    pad_updates = []
    dialog_pad.multi_layout_saved.connect(pad_updates.append)
    ok("含留白源图：移动后回写版面尺寸＝入口 rect 尺寸（高度不压缩）",
       dialog_pad._save_multiple_images()
       and pad_updates == [[{
           "index": 0,
           "file": str(pad_left_path),
           # 位移 = 内容偏移 + 画布原点，再乘**内容比例**：(30×1.5, 30×1.8)；
           # 尺寸 = 内容尺寸 × 比例 = 入口 rect（240×180）。旧版按整图算比例
           # (1,1)，尺寸会回成 (160,100)——拼版页据此摆框，高度就短了一截。
           "rect": [45.0, 54.0, 240.0, 180.0],
       }]],
       f"updates={pad_updates}")
    dialog_pad.close()
    dialog_pad.release_buffers()

    dialog.close()
    dialog.release_buffers()
    ok("释放：双图各层整图缓冲一并放掉",
       all(layer["state"]["_image"] is None for layer in dialog._multi_layers),
       "")
