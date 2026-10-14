# -*- coding: utf-8 -*-
"""图片编辑弹窗·变换的大图视图锚定、参考线/校正/翻转、局部变换。

断言线：

0. **变换不污染 `_user_zoomed`**（2026-10-14 用户报障"旋转 45° 再切裁剪，
   图片被裁掉一部分"）：**像素没丢**（400×300 转 45° 正确烘焙成 494×494），
   丢的是**可见性**——倍率还停在按 400×300 算出的 1.92，494×494 只剩
   451×354 落在视口里。根因：``_apply_visual`` 把"变换期间临时抑制 resize
   自动适配"写进了 ``_user_zoomed``（那是**长期意图**"用户手动缩放过"）
   而且从不还原 ⇒ "做过一次变换"就永久关掉了 ``resizeEvent`` 的自动适配
   与 ``set_fit_ratio`` 的即时生效；「重置」也是变换结束，必须一并清。
1. **大图走降采样档**（2026-10-09 第三轮报障的根因所在）：选区大于预览
   预算才真的走 k<1 的降采样档；拖动档把区域像素**原样**映到图片坐标
   （不再多除一个 k）；浮层内容落在变换框上、内容中心恒在轴心上；
   转多少圈画布画面都不动（视图锚点恒定）、场景矩形恒定。
   ⚠️ 这些用例**必须用大于预览预算的图**——600×800 只有 0.48 MP，
   ``_xf_preview_scale`` 恒为 1，那个矩阵顺序错**完全测不出来**；
   锚点必须在**动手之前**取（用户说的是"画布画面是不变的"）；
   ⚠️ 先**平移**再转：绕中心的旋转外框对称、那点漂移"看不出来"，
   平移之后并集一边倒，旧实现才会把整幅画面推走；
2. **参考线**（2026-10-09 报障"太细了看不清"）：默认五分构图（8 根全显示）、
   加粗为 2 设备像素虚线（cosmetic，缩放不变细）；
3. **方向=校正**：框画 ``_xf``、内容走 ``_preview_xf``（= 逆）会让两者
   平移方向相反；现在统一吃视觉矩阵；
4. **水平/垂直翻转**（2026-10-09 报障"太慢"）：走快路径、翻两次精确复原
   （像素级一致，快路径产物与烘焙一致）；
5. **局部变换**（小范围修褶皱的核心路径）：「调整范围」收边进入小区域后
   自动退出「统一变换」且轴心跟随；局部烘焙后**区域外像素一动不动**；
   选项页重建后 ``reshape`` 信号不再打到已销毁的复选框。
"""

from __future__ import annotations

NAME = "image_editor_transform_local"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·变换视图锚定/参考线/翻转/局部变换"


def run(ctx) -> None:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import (
        canvas_img, make_image, mouse_event, plane_diff,
    )

    from desktop.components.viewers.image_editor import ImageEditorDialog

    app = ctx.app

    # ⚠️⚠️ 回归（2026-10-14 用户报障）：「图片编辑『统一变换』功能，图片
    #   旋转 45 度，然后切换『裁剪』功能，发现图片被裁剪了一部分」。
    #   **像素没丢**（400×300 转 45° 正确烘焙成 494×494），丢的是
    #   **可见性**：倍率还停在按 400×300 算出的 1.92，494×494 只剩
    #   451×354 落在视口里，右侧和底部被切掉。
    #   根因：``_apply_visual`` 把"变换期间临时抑制 resize 自动适配"
    #   写进了 ``_user_zoomed``——那是**长期意图**"用户手动缩放过"
    #   ——而且从不还原 ⇒ "做过一次变换"就永久关掉了 ``resizeEvent``
    #   的自动适配与 ``set_fit_ratio``（= 切工具时的重新适配）的即时生效。
    #   修法：临时抑制改用 ``_xf_fit_suppressed``，用完即清。
    dialog_rot = ImageEditorDialog(None, make_image(400, 300))
    try:
        dialog_rot.resize(1300, 900)
        dialog_rot.show()
        app.processEvents()
        canvas_rot = dialog_rot.canvas

        def visible_gap(canvas) -> tuple[float, float]:
            """图矩形有多少落在视口外（场景坐标）。"""
            image_rect = canvas.image_rect()
            visible = canvas.mapToScene(
                canvas.viewport().rect()).boundingRect()
            covered = image_rect.intersected(visible)
            return (image_rect.width() - covered.width(),
                    image_rect.height() - covered.height())

        canvas_rot.set_tool("transform")
        canvas_rot.transform_rotate(45.0)
        ok("回归·变换后切工具：变换**不污染** _user_zoomed"
           "（那是用户长期意图，不是临时抑制）",
           canvas_rot._user_zoomed is False,
           f"_user_zoomed={canvas_rot._user_zoomed}")
        ok("回归·变换后切工具：临时抑制标志用完即清",
           canvas_rot._xf_fit_suppressed is False,
           f"_xf_fit_suppressed={canvas_rot._xf_fit_suppressed}")
        dialog_rot._set_tool("crop")
        app.processEvents()
        gap_x, gap_y = visible_gap(canvas_rot)
        ok("回归·旋转 45° 后切裁剪：整图完整可见（不再被切掉一块）",
           gap_x <= 1.0 and gap_y <= 1.0,
           f"视口外 {gap_x:.1f}x{gap_y:.1f}px, "
           f"image={canvas_rot.image.width()}x"
           f"{canvas_rot.image.height()} zoom={canvas_rot._zoom:.3f}")
        # 场景矩形必须跟着长：否则超出去的部分连滚都滚不到
        ok("回归·旋转 45° 后切裁剪：场景矩形罩住整图（能滚到每一块）",
           canvas_rot.sceneRect().contains(canvas_rot.image_rect()),
           f"sceneRect={canvas_rot.sceneRect()} "
           f"image_rect={canvas_rot.image_rect()}")
        # 反复旋转不许"越转越小"（历史报障）：45° 是包络稳定角，
        # 连续烘焙四轮尺寸必须恒定。
        sizes_rot = []
        for _ in range(3):
            canvas_rot.set_tool("transform")
            canvas_rot.transform_rotate(45.0)
            dialog_rot._set_tool("crop")
            sizes_rot.append(
                (canvas_rot.image.width(), canvas_rot.image.height()))
        ok("回归·连续旋转四轮：尺寸稳定不逐轮缩小",
           len(set(sizes_rot)) == 1, f"尺寸序列={sizes_rot}")

        # ⚠️ 反向：用户**真的**手动缩放过时，长期意图必须保留
        canvas_rot.set_zoom(canvas_rot._zoom * 1.3)
        ok("回归·手动缩放仍置位 _user_zoomed（长期意图不受影响）",
           canvas_rot._user_zoomed is True, "")
        canvas_rot.fit()
        ok("回归·fit() 不清 _user_zoomed（闸门不被自己打开）",
           canvas_rot._user_zoomed is True, "")
    finally:
        dialog_rot.deleteLater()

    # ⚠️ 拖动路径上的临时抑制：期间为真（防视图跟着跳），松手后必须清。
    dialog_sup = ImageEditorDialog(None, make_image(200, 120))
    try:
        dialog_sup.show()
        app.processEvents()
        canvas_sup = dialog_sup.canvas
        canvas_sup.set_tool("transform")
        mode_sup = canvas_sup._begin_transform_drag(
            "br", QPointF(100, 60), Qt.KeyboardModifier.NoModifier)
        if mode_sup is not None:
            canvas_sup._apply_transform_drag(
                mode_sup, QPointF(125, 80),
                Qt.KeyboardModifier.NoModifier)
            suppressed_during = canvas_sup._xf_fit_suppressed
        else:
            suppressed_during = None
        canvas_sup.finish_transform_drag()
        ok("回归·拖动期间临时抑制生效（视图不跟着图片跳）",
           suppressed_during is True,
           f"_xf_fit_suppressed={suppressed_during}")
        ok("回归·松手后临时抑制已清（不永久关掉自动适配）",
           canvas_sup._xf_fit_suppressed is False
           and canvas_sup._user_zoomed is False,
           f"suppressed={canvas_sup._xf_fit_suppressed} "
           f"user_zoomed={canvas_sup._user_zoomed}")
        # 「重置」也是变换结束，必须一并清
        canvas_sup._xf_fit_suppressed = True   # 模拟脏标志
        canvas_sup.reset_transform()
        ok("回归·「重置」清掉临时抑制标志",
           canvas_sup._xf_fit_suppressed is False,
           f"={canvas_sup._xf_fit_suppressed}")
    finally:
        dialog_sup.deleteLater()

    # ⚠️⚠️ 回归（2026-10-09 第三轮用户报障）：「图片边框那些操作框也应该
    #   跟着图片移动旋转，现在是分离了」「格子区域块跟图片相互远离」
    #   「画布画面是不变的」。
    #   根因是 ``QTransform`` 的复合顺序：``A * B`` 是**先 A 后 B**（行向量
    #   约定），而 ``S(k) ∘ placed ∘ S(1/k)`` 那种数学记号是**先右后左**。
    #   旧版按记号直译成 ``S(k) * placed * S(1/k)`` ⇒ 矩阵成了
    #   ``placed(k·u)/k``，**平移量被多除一个 k**，内容整体偏 ``t·(1/k−1)``
    #   （k=0.6 时 100px 的位移能偏出 66px）。
    #   ⚠️ 600×800 只有 0.48 MP，`_xf_preview_scale` 恒为 1 ⇒ 这个错**完全
    #   测不出来**，旧自测全绿。所以这条用例必须用**大于预览预算**的图。
    img6 = QImage(1000, 1400, QImage.Format.Format_ARGB32)
    img6.fill(QColor("#f2ecdd"))
    dialog6 = ImageEditorDialog(None, img6)
    try:
        canvas6 = dialog6.canvas
        canvas6.set_tool("transform")
        dialog6.show()
        app.processEvents()
        app.processEvents()
        canvas6.fit()
        app.processEvents()
        # ⚠️ 锚点在**动手之前**取：用户说的是"画布画面是不变的"——从操作前
        #   到操作后整幅画面都不能动，而不只是"转两次之间别动"。
        anchor6 = canvas6.mapFromScene(QPointF(0, 0))
        scene6 = QRectF(canvas6.sceneRect())
        # ⚠️ 先**平移**再转：绕中心的旋转外框是对称的、并集中心几乎不动，
        #   旧实现那点漂移会被"看不出来"；平移之后并集一边倒，旧实现就会
        #   把整幅画面推走（实测同样是"转+移"，用户截图里就是这么偏的）。
        canvas6.transform_move(160, -110)
        canvas6.transform_rotate(20)
        region6 = canvas6._xf_region
        ok("变换（大图）：选区大于预览预算 ⇒ 真的走降采样档（k<1）",
           canvas6._xf_preview_scale < 0.9,
           f"k={canvas6._xf_preview_scale:.3f} 区域="
           + (f"{region6.width()}x{region6.height()}"
              if region6 is not None else "未建预览"))
        placed6 = canvas6._placed_xf()
        ok("变换（大图）：拖动档把区域像素**原样**映到图片坐标"
           "（不再多除一个 k）",
           (canvas6._float_fast_xf().map(QPointF(0, 0))
            - placed6.map(QPointF(0, 0))).manhattanLength() < 1e-6,
           f"fast={canvas6._float_fast_xf().map(QPointF(0, 0))} "
           f"placed={placed6.map(QPointF(0, 0))}")
        quad6 = canvas6._transform_quad()
        xs6 = [point.x() for point in quad6.values()]
        ys6 = [point.y() for point in quad6.values()]
        expect6 = QRectF(min(xs6), min(ys6),
                         max(xs6) - min(xs6), max(ys6) - min(ys6))
        got6 = canvas6._float_item.sceneBoundingRect()
        ok("变换（大图）：浮层内容落在变换框上（框与内容不再分离）",
           got6.contains(expect6)
           and abs(got6.width() - expect6.width()) <= 8.0
           and abs(got6.height() - expect6.height()) <= 8.0,
           f"float={got6} expect={expect6}")
        pivot6 = canvas6._xf.map(canvas6._xf_pivot)
        center6 = QPointF((got6.left() + got6.right()) / 2,
                          (got6.top() + got6.bottom()) / 2)
        ok("变换（大图）：内容中心恒在轴心上（绕轴心变换，不跑位）",
           (center6 - pivot6).manhattanLength() < 6.0,
           f"center={center6} pivot={pivot6}")
        for _ in range(4):
            canvas6.transform_rotate(9)
        ok("变换（大图）：转多少圈画布画面都不动（视图锚点恒定）",
           canvas6.mapFromScene(QPointF(0, 0)) == anchor6,
           f"anchor={canvas6.mapFromScene(QPointF(0, 0))} vs {anchor6}")
        ok("变换（大图）：场景矩形恒定（不跟变换长大）",
           QRectF(canvas6.sceneRect()) == scene6,
           f"sceneRect={canvas6.sceneRect()} vs {scene6}")
        paper6 = QRectF(canvas6.image_rect())
        ok("变换（大图）：底图（纸）仍恒定 = 原图矩形（不跟变换长）",
           canvas6._base_target_rect() == paper6
           and canvas6._base_current_rect() == paper6,
           f"target={canvas6._base_target_rect()} "
           f"base={canvas6._base_current_rect()} expect={paper6}")
        canvas6.reset_transform()
    finally:
        dialog6.deleteLater()

    # ⚠️⚠️ 回归（2026-10-09 用户报障三项）：①「统一变换参考线不显眼，
    #   太细了看不清，默认 5 分构图」②「方向：校正，图片和操作框方向
    #   相反」③「水平翻转、垂直翻转卡顿，太慢」。
    img7 = make_image(300, 200)
    for x in range(200, 230):  # 黑块 x∈[200,230)×y∈[80,110)（翻转方向用）
        for y in range(80, 110):
            img7.setPixel(x, y, 0xFF000000)
    dialog7 = ImageEditorDialog(None, img7)
    try:
        canvas7 = dialog7.canvas
        canvas7.set_tool("transform")
        dialog7.show()
        app.processEvents()
        app.processEvents()

        # ---- ① 参考线：默认五分 + 2 设备像素虚线（cosmetic 不随缩放变细）
        visible7 = sum(1 for item in canvas7._guides if item.isVisible())
        ok("变换：参考线默认五分构图（8 根全显示）",
           canvas7._xf_guide == "fifths" and visible7 == 8,
           f"guide={canvas7._xf_guide} visible={visible7}")
        gpen = canvas7._guides[0].pen()
        ok("变换：参考线加粗为 2 设备像素虚线（cosmetic，缩放不变细）",
           gpen.isCosmetic() and gpen.widthF() >= 2.0
           and gpen.style() == Qt.PenStyle.DashLine,
           f"cosmetic={gpen.isCosmetic()} width={gpen.widthF()} "
           f"style={gpen.style()}")

        # ---- ② 校正（向后）：框与内容同向
        #   旧 bug：框画 ``_xf``、内容走 ``_preview_xf``（=逆），平移时
        #   内容往 −x 跑、框往 +x 跑。现在两者统一吃视觉矩阵。
        canvas7.set_transform_options(direction="backward")
        canvas7.reset_transform()
        canvas7.transform_move(40, 0)
        quad7 = canvas7._transform_quad()
        float7 = canvas7._float_item.sceneBoundingRect()
        ok("变换（校正）：平移后框与内容同向（都向 +x 40，不再相反）",
           abs(quad7["tl"].x() - 40.0) < 1e-6
           and abs(float7.left() - 40.0) <= 2.0,
           f"quad_tl={quad7['tl']} float_left={float7.left()}")
        # 旋转同理：校正模式下的视觉框必须与正向**同一操作**一致
        # （旧 bug：框用正向矩阵画 ⇒ 与浮层内容反向转）
        canvas7.set_transform_options(direction="forward")
        canvas7.reset_transform()
        canvas7.transform_rotate(90)
        quad_fwd = dict(canvas7._transform_quad())
        canvas7.set_transform_options(direction="backward")
        canvas7.reset_transform()
        canvas7.transform_rotate(90)
        quad_bwd = dict(canvas7._transform_quad())
        ok("变换（校正）：旋转后框的视觉位置与正向一致（跟随内容）",
           all((quad_fwd[k] - quad_bwd[k]).manhattanLength() < 1e-6
               for k in quad_fwd),
           f"fwd_tl={quad_fwd['tl']} bwd_tl={quad_bwd['tl']}")

        # ---- ③ 翻转快路径：纯镜像不走逐像素重采样（12MP 曾 ~11 秒）
        #   ⚠️ 别用 _set_tool 离开变换——切工具会把挂起变换**烘焙**掉
        #   （这里要的是丢弃）；reset_transform 才是"丢弃不烘焙"。
        canvas7.set_transform_options(direction="forward")
        canvas7.reset_transform()
        before7 = canvas_img(canvas7).copy()
        undo7 = len(dialog7._undo)
        # 快路径判据：纯镜像**不该**触发整幅重采样（compose_transform），
        # 也不该建预览浮层——打桩计数，旧实现（全走烘焙通道）会红。
        import desktop.components.viewers.image_editor.dialog_commit \
            as commit_mod
        real_compose = commit_mod.compose_transform
        compose_calls: list[int] = []

        def _counting_compose(*args, **kwargs):
            compose_calls.append(1)
            return real_compose(*args, **kwargs)

        commit_mod.compose_transform = _counting_compose
        try:
            dialog7._flip_transform(True)
        finally:
            commit_mod.compose_transform = real_compose
        flipped7 = canvas_img(canvas7)
        ok("翻转：纯镜像走快路径（零整幅重采样、不留预览浮层）",
           not compose_calls and canvas7._float_item is None,
           f"compose={len(compose_calls)} float={canvas7._float_item}")
        ok("翻转：水平翻转 = 整幅镜像（黑块从 [200,230) 到 [70,100)，尺寸不变）",
           flipped7.size() == before7.size()
           and canvas7.transform_pending() is None
           and all(flipped7.pixelColor(x, 90).value() < 128
                   for x in (75, 85, 95))
           and all(flipped7.pixelColor(x, 90).value() > 230
                   for x in (205, 215, 225)),
           f"size={flipped7.width()}x{flipped7.height()} "
           f"pending={canvas7.transform_pending()}")
        ok("翻转：一步一个撤销点、名字记「翻转」",
           len(dialog7._undo) == undo7 + 1
           and dialog7.history_list.item(
               dialog7.history_list.count() - 1).text() == "翻转",
           f"undo={len(dialog7._undo)} before={undo7}")
        dialog7._flip_transform(True)      # 再翻一次 = 回到原图
        ok("翻转：翻两次精确复原（像素级一致，快路径产物与烘焙一致）",
           plane_diff(canvas_img(canvas7), before7) < 1.0, "")
    finally:
        dialog7.deleteLater()

    # ---- 调整范围 + 局部变换（小范围修褶皱的核心路径） ----
    img5 = make_image(200, 120)
    for x in range(150, 170):  # 区域内的"褶皱"块 x∈[150,170)×y∈[50,70)
        for y in range(50, 70):
            img5.setPixel(x, y, 0xFF000000)
    for x in range(185, 195):  # 区域**外**的标记块（烘焙后必须原样）
        for y in range(50, 70):
            img5.setPixel(x, y, 0xFF000000)
    dialog5 = ImageEditorDialog(None, img5)
    try:
        canvas5 = dialog5.canvas
        canvas5.set_tool("transform")
        dialog5.show()
        app.processEvents()
        app.processEvents()

        def vpos5(scene: QPointF) -> QPointF:
            return QPointF(canvas5.mapFromScene(scene))

        finished: list[int] = []
        canvas5.reshape_finished.connect(lambda: finished.append(1))
        ok("调整范围：默认关闭（拖手柄 = 缩放内容）",
           canvas5._xf_reshape is False, "")

        canvas5.set_transform_reshape(True)
        canvas5.mousePressEvent(mouse_event("press", vpos5(QPointF(201, 60))))
        ok("调整范围：右缘按下进入收边（而非缩放）",
           canvas5._mode is not None and canvas5._mode[0] == "handle"
           and canvas5._mode[1] == "r", f"mode={canvas5._mode}")
        canvas5.mouseMoveEvent(mouse_event(
            "move", vpos5(QPointF(179, 60))))
        canvas5.mouseReleaseEvent(mouse_event(
            "release", vpos5(QPointF(179, 60))))
        sel5 = canvas5.selection()
        ok("调整范围：区域收小到 x<180、自动退出该模式并回告弹窗",
           sel5 is not None and abs(sel5.right() - 180) < 1.5
           and canvas5._xf_reshape is False and finished == [1],
           f"sel={sel5} flag={canvas5._xf_reshape} finished={finished}")
        ok("调整范围：轴心跟随新区域中心（≈90,60）",
           (canvas5._xf_pivot - QPointF(90, 60)).manhattanLength() < 1.5,
           f"pivot={canvas5._xf_pivot}")

        undo_before = len(dialog5._undo)
        canvas5.transform_scale(0.5, 0.5)  # 区域内容向轴心收缩一半
        dialog5._commit_transform()
        baked5 = canvas_img(canvas5)
        # grow：区域 x∈[0,180) 收缩到 x∈[45,135)（×0.5 绕轴心 90）⇒ 画布
        # 按**内容外框**重裁，左上角落在原坐标 (45, 0)、尺寸 155×120。
        # 新画布坐标 = 原坐标 − 45。折叠块原 150→新 0.5·150=75 处；
        # 原 160 处（新 0.5·160=80）被收走 ⇒ 空白；区域外标记块
        # 原 185→新 140 处原样。
        ok("局部变换：非全幅变换后画布按内容外框重裁（155×120，左上角 45,0）",
           (baked5.width(), baked5.height()) == (155, 120),
           f"size={baked5.width()}x{baked5.height()}")
        ok("局部变换：区域内内容缩向轴心（黑块 150→75 处）",
           baked5.pixelColor(75, 60).value() < 128
           and baked5.pixelColor(105, 60).value() > 230,
           f"dark={baked5.pixelColor(75, 60).value()} "
           f"white={baked5.pixelColor(105, 60).value()}")
        ok("局部变换：区域外像素一动不动（标记块 185→140 处原样）",
           baked5.pixelColor(140, 60).value() < 128,
           f"outside={baked5.pixelColor(140, 60).value()}")
        ok("局部变换：一批一个撤销点",
           len(dialog5._undo) == undo_before + 1,
           f"undo={len(dialog5._undo)} before={undo_before}")

        # 回归（2026-10-08 用户报障）：刚进变换工具就抓轴心拖，
        # 预览还没建——以前这里直接进 xf_pivot，第一个 move 事件就
        # 撞 `assert _xf_rect`，拖动全程刷屏 AssertionError。
        dialog5._set_tool("transform")
        pivot_before = QPointF(canvas5._xf_pivot)
        pivot_view = vpos5(canvas5._xf.map(pivot_before))
        canvas5.mousePressEvent(mouse_event("press", pivot_view))
        ok("变换：按下轴心不提前建预览",
           canvas5._mode is not None
           and canvas5._mode[0] == "xf_pending"
           and canvas5._xf_rect is None, f"mode={canvas5._mode}")
        moved_view = vpos5(canvas5._xf.map(pivot_before)
                           + QPointF(20, 10))
        canvas5.mouseMoveEvent(mouse_event("move", moved_view))
        ok("变换：首个实际拖动才建轴心预览",
           canvas5._mode is not None and canvas5._mode[0] == "xf_pivot"
           and canvas5._xf_rect is not None, f"mode={canvas5._mode}")
        canvas5.mouseReleaseEvent(mouse_event("release", moved_view))
        ok("变换：轴心拖动全程无异常、轴心跟到新位置、松手复位",
           canvas5._mode is None
           and (canvas5._xf_pivot - (pivot_before + QPointF(20, 10)))
           .manhattanLength() < 2.0,
           f"pivot={canvas5._xf_pivot} mode={canvas5._mode}")

        # 回归（2026-10-08 用户报障）：「调整范围」复选框的信号连接
        # 随选项页重建而泄漏——旧页销毁后下一次 reshape 完成就调到
        # 已销毁的 CheckBox 上抛 RuntimeError 刷屏。
        dialog5._set_tool("transform")
        app.processEvents()
        dialog5._set_tool("crop")
        app.processEvents()  # 旧选项页 deleteLater 在此真正销毁
        dialog5._set_tool("transform")
        app.processEvents()
        try:
            canvas5.reshape_finished.emit()
            reshape_ok = True
        except RuntimeError:
            reshape_ok = False
        ok("变换：选项页重建后 reshape 信号不再打到已销毁的复选框",
           reshape_ok, "")
    finally:
        dialog5.deleteLater()
    app.processEvents()