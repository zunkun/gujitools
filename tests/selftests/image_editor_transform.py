# -*- coding: utf-8 -*-
"""图片编辑弹窗·统一变换主线（移动/旋转/切变/缩放 + 实时预览 + 烘焙）。

断言线：

1. **进入即全选、无待应用变换**；
2. **框内拖 = 移动**：按下即实时预览（底图 = 原图矩形那块的残余、选区擦成
   透明）、范围**恒定**不跟变换走；**松手只挂起、离开工具才烘焙**
   （2026-10-09 起不再松手即烘焙，"不能实时预览、最后才预览"报障）；
3. **烘焙**：切走工具此刻才烘焙、一步一个撤销点、历史多一格「变换」；
   grow 档整幅左移 ⇒ 新画布 = 原图 ∪ 移位后内容；
4. **大图切换工具**：立即返回并启动后台 worker，完成回调才切工具
   （不在点击处理器里同步等待像素烘焙）；
5. **旋转/切变/缩放**：绕轴心（轴心不动）、切变右缘下斜左缘锚定、缩放
   从轴心向内收缩；切走工具自动烘焙，画布按**内容外框**收尺寸；
6. **命中测试**：角点中心 = 透视小菱形（≤ PERSP_HIT）、方形环带 = 角缩放
   （≤ CORNER_HIT）、框外 = 旋转；手柄尺寸钉的是**画出来的多边形/矩形**
   乘回倍率（改常量漏改绘制也照样红）；菱形与角方框同心、按半径分归属；
   节点底色默认中空、只有"当前节点"实心；
7. **预览 == 烘焙**（像素级）：预览渲染成图与 ``compose_transform``
   逐像素对照，只该差抗锯齿（实测 1–2）；
8. **底图恒定 = 原图矩形**：不跟变换外框每帧重算（2026-10-09 报障"白底和
   图片位置一直漂移"），场景矩形也不跟变换长大；
9. **病态投影被丢弃**（2026-10-09 崩溃回归）：把透视角拖到对角附近时
   手柄停住、矩阵保持不变；
10. **撤销点**：撤销/重做/还原整段退进退出。

（大图视图锚定/参考线/校正/翻转/局部变换见 ``image_editor_transform_local.py``，
完成收尾与内容四角 sidecar 见 ``image_editor_transform_bake.py``。）
"""

from __future__ import annotations

NAME = "image_editor_transform"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·统一变换（移动/旋转/切变/缩放/预览烘焙）"


def run(ctx) -> None:
    import math

    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QTransform
    from PySide6.QtTest import QTest

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import (
        canvas_img, history_labels, make_image, mouse_event, plane_diff,
    )

    from desktop.components.viewers.image_editor import (
        ImageEditorDialog, center_crop_aspect, compose_transform,
    )
    from desktop.components.viewers.image_editor.geometry import mapped_bounds
    from desktop.components.viewers.image_editor.consts import (
        CORNER_HIT_VIEW_PX, PERSP_HIT_VIEW_PX, PERSP_VIEW_PX,
    )

    app = ctx.app

    # ---- 变换：统一变换（移动/旋转/切变/缩放 + 实时预览 + 烘焙） ----
    timg = make_image(200, 120)
    for x in range(150, 170):  # 黑块 x∈[150,170) × y∈[50,70)
        for y in range(50, 70):
            timg.setPixel(x, y, 0xFF000000)
    dialog4 = ImageEditorDialog(None, timg)
    try:
        canvas4 = dialog4.canvas
        canvas4.set_tool("transform")
        ok("变换：进入工具默认全选、无待应用变换",
           canvas4.selection() == canvas4.image_rect()
           and canvas4.transform_pending() is None, "")

        def vpos(scene: QPointF) -> QPointF:
            return QPointF(canvas4.mapFromScene(scene))

        # 框内拖 = 移动（真实鼠标事件走一遍）；**松手只挂起、离开工具才烘焙**
        dialog4.show()
        app.processEvents()
        app.processEvents()
        undo_before = len(dialog4._undo)
        canvas4.mousePressEvent(mouse_event("press", vpos(QPointF(160, 60))))
        _base = canvas4._image
        assert _base is not None
        ok("变换：纯按下暂不创建像素预览",
           canvas4._mode is not None
           and canvas4._mode[0] == "xf_pending"
           and canvas4._float_item is None,
           f"mode={canvas4._mode}")
        canvas4.mouseMoveEvent(mouse_event("move", vpos(QPointF(130, 60))))
        _paint = canvas4._paint_image
        assert _paint is not None and canvas4._float_item is not None
        ok("变换：实际拖动才创建预览（真像素未动）",
           canvas4._mode is not None and canvas4._mode[0] == "xf_move"
           and _base.pixelColor(160, 60).value() < 128,
           f"mode={canvas4._mode} "
           f"base={_base.pixelColor(160, 60).value()}")
        canvas4.mouseReleaseEvent(mouse_event(
            "release", vpos(QPointF(130, 60))))
        # ⚠️ 2026-10-09 起**松手不烘焙**（用户报"不能实时预览、最后才预览"）：
        #    松手只是把这次变换挂起，画布上的浮层继续实时显示；整幅重采样
        #    推迟到离开变换工具/点「完成」——所以此刻像素、撤销点都没动。
        ok("变换：松手只挂起预览（像素与撤销栈都没动）",
           canvas4.has_pending_transform()
           and len(dialog4._undo) == undo_before
           and canvas_img(canvas4).pixelColor(160, 60).value() < 128,
           f"pending={canvas4.has_pending_transform()} "
           f"undo={len(dialog4._undo)} before={undo_before}")
        # 离开变换工具 → 此刻才烘焙，且一步一个撤销点
        dialog4._set_tool("erase")
        baked = canvas_img(canvas4)
        # grow：整幅选区左移 30 ⇒ 新画布 = 原图 ∪ 移位后内容，左上角在
        # 原坐标 (−30, 0)，尺寸不变（移位量正好等于外扩量）。新画布里的
        # 坐标 = 原坐标 − origin = 原坐标 + 30。
        ok("变换：切走工具才烘焙（−30,0 平移已落地，画布尺寸不变）",
           baked.width() == 200 and baked.height() == 120
           and canvas4.transform_pending() is None,
           f"size={baked.width()}x{baked.height()} "
           f"pending={canvas4.transform_pending()}")
        ok("变换：烘焙后内容平移、原位置填白（烘焙与预览一致）",
           baked.pixelColor(125 + 30, 60).value() < 128
           and baked.pixelColor(160 + 30, 60).value() > 230,
           f"dark={baked.pixelColor(155, 60).value()} "
           f"white={baked.pixelColor(190, 60).value()}")
        ok("变换：一步一个撤销点、历史多一格「变换」",
           len(dialog4._undo) == undo_before + 1
           and dialog4.history_list.item(
               dialog4.history_list.count() - 1).text() == "变换"
           and dialog4.history_list.currentRow()
           == dialog4.history_list.count() - 1,
           f"undo={len(dialog4._undo)} before={undo_before} "
           f"历史={history_labels(dialog4)}")

        # 大图离开统一变换时先启动 worker；工具切换由完成回调收尾，
        # 不在点击处理器里同步等待像素烘焙。
        async_dialog = ImageEditorDialog(None, make_image(800, 600))
        try:
            async_dialog.canvas.set_tool("transform")
            async_dialog.canvas.transform_rotate(15)
            async_dialog.canvas.make_transform_pending()
            async_dialog._set_tool("erase")
            async_worker = async_dialog._tool_transition_worker
            ok("大图切换工具立即返回并启动后台变换",
               async_worker is not None
               and async_dialog.canvas.tool == "transform",
               f"worker={async_worker is not None} "
               f"tool={async_dialog.canvas.tool}")
            from time import monotonic

            deadline = monotonic() + 30
            while async_dialog._tool_transition_worker is not None \
                    and monotonic() < deadline:
                app.processEvents()
                QTest.qWait(10)
            app.processEvents()
            ok("后台变换完成后才切换工具并清除挂起状态",
               async_dialog._tool_transition_worker is None
               and async_dialog.canvas.tool == "erase"
               and async_dialog.canvas.transform_pending() is None,
               f"worker={async_dialog._tool_transition_worker is not None} "
               f"tool={async_dialog.canvas.tool} "
               f"pending={async_dialog.canvas.transform_pending() is not None}")
        finally:
            running_worker = async_dialog._tool_transition_worker
            if running_worker is not None:
                running_worker.cancel()
                running_worker.wait()
                app.processEvents()
            async_dialog.reject()
            async_dialog.release_buffers()
        # 旋转：绕轴心（轴心不动）；切走工具自动烘焙
        canvas4.set_tool("transform")
        undo_before = len(dialog4._undo)
        canvas4.transform_rotate(90)
        pivot = canvas4.image_rect().center()
        ok("变换：绕轴心旋转 90°（轴心视觉位置不动）",
           (canvas4._xf.map(pivot) - pivot).manhattanLength() < 1e-6
           and canvas4.transform_pending() is not None, "")
        dialog4._set_tool("erase")
        ok("变换：切走工具自动烘焙（压撤销点）",
           len(dialog4._undo) == undo_before + 1
           and canvas4.transform_pending() is None,
           f"undo={len(dialog4._undo)} before={undo_before}")
        # grow：200×120 全选旋转 90°，内容真占了 120×200 那一整块 ⇒
        # 画布按**内容外框**收成 120×200（不是"原图 ∪ 内容"=200×200）。
        # 老图不要了：旋转后原位早被填白，没理由留着 200×200 的空白。
        _rotated = canvas_img(canvas4)
        ok("变换：非正方图旋转 90° ⇒ 画布按内容外框收成 120×200",
           (_rotated.width(), _rotated.height()) == (120, 200),
           f"size={_rotated.width()}x{_rotated.height()}")

        # 切变：右缘下斜、左缘锚定（尺寸随轮转后的图走，不写死 200×120）
        # 语义见「变换数学：绕锚点切变」——绕 ``rect.top()`` 做 y 随 x 斜切：
        # ``y' = y + k·x``。拖右边整条，左缘 (x=0) 不动；右缘下移 k·w。
        canvas4.set_tool("transform")
        w = canvas4.image_rect().width()
        h = canvas4.image_rect().height()
        canvas4.transform_shear("r", 0.5)
        xf = canvas4._xf
        ok("变换：拖边切变（右缘下移 k·w、左缘锚定）",
           (xf.map(QPointF(w, h / 2)) - QPointF(w, h / 2 + 0.5 * w))
           .manhattanLength() < 1e-6
           and (xf.map(QPointF(0, h / 2)) - QPointF(0, h / 2))
           .manhattanLength() < 1e-6,
           f"right={xf.map(QPointF(w, h / 2))} "
           f"left={xf.map(QPointF(0, h / 2))}")

        # 缩放：从轴心（轴心不动、内容向轴心收缩）
        canvas4.set_tool("transform")
        canvas4.set_transform_about_pivot(True)
        canvas4.transform_scale(0.5, 0.5)
        pivot = canvas4.image_rect().center()
        ok("变换：从轴心缩放 50%（轴心不动）",
           (canvas4._xf.map(QPointF(0, 0)) - pivot / 2)
           .manhattanLength() < 1e-6
           and (canvas4._xf.map(pivot) - pivot).manhattanLength() < 1e-6,
           f"tl={canvas4._xf.map(QPointF(0, 0))} pivot={pivot}")
        canvas4.set_transform_about_pivot(False)
        canvas4.reset_transform()
        ok("变换：重置清掉待应用变换、选区回到整幅",
           canvas4.transform_pending() is None
           and canvas4.selection() == canvas4.image_rect(), "")

        # 命中测试：角点**中心** = 透视小菱形、方框描边那圈 = 角缩放、框外 = 旋转。
        # ⚠️ 2026-10-09 起菱形与角方框**同心**（用户口径「四个边角的菱形要在
        #    方块正中心」），所以"角点归谁"改由**半径**分：≤ PERSP_HIT(8) 是
        #    透视，往外到 CORNER_HIT(13) 的方形环带仍是缩放。
        _pts = canvas4._transform_handle_points()
        ok("变换：透视小菱形与角方框同心（不再向框内偏置）",
           _pts["p_tl"] == _pts["tl"] and _pts["p_br"] == _pts["br"]
           and _pts["p_tr"] == _pts["tr"] and _pts["p_bl"] == _pts["bl"],
           f"p_tl={_pts['p_tl']} tl={_pts['tl']}")
        tl_view = vpos(_pts["tl"])
        # 沿 tl→tr 走 10 视图像素：出了透视半径(8)、仍在角方框方形判定(13)内
        _dir = vpos(_pts["tr"]) - tl_view
        _len = math.hypot(_dir.x(), _dir.y())
        edge_view = tl_view + _dir / _len * 10.0
        far_view = vpos(QPointF(-60, -60))
        ok("变换：命中测试（角心=透视、方框边=缩放、远处=框外旋转）",
           canvas4._hit_transform(tl_view) == "p_tl"
           and canvas4._hit_transform(edge_view) == "tl"
           and canvas4._hit_transform(far_view) == "outside",
           f"center={canvas4._hit_transform(tl_view)} "
           f"edge={canvas4._hit_transform(edge_view)} "
           f"far={canvas4._hit_transform(far_view)}")

        # 手柄**尺寸**（用户 2026-10-09：「菱形大一些，四边中间的拉伸方块
        # 也大一些」）：四类节点里的菱形现在**一样大**，边中方框也长到同尺寸。
        # ⚠️ 读的是**画出来的多边形/矩形**（场景单位）再乘回倍率 ⇒ 断言的是
        #    视图像素，不是常量本身，改常量漏改绘制也照样红。
        canvas4._sync_overlay()
        _zoom = max(canvas4._zoom, 1e-6)
        _persp_px = (canvas4._persp["p_tl"].polygon().boundingRect().width()
                     * _zoom)
        _shear_px = (canvas4._diamonds["s_t"].polygon().boundingRect().width()
                     * _zoom)
        _side_px = canvas4._handles["t"].rect().width() * _zoom
        _corner_px = canvas4._handles["tl"].rect().width() * _zoom
        ok("变换：菱形放大到 16、边中方框也 16、角方框 28（视图像素）",
           abs(_persp_px - 16.0) < 0.6 and abs(_shear_px - 16.0) < 0.6
           and abs(_side_px - 16.0) < 0.6 and abs(_corner_px - 28.0) < 0.6,
           f"透视={_persp_px:.1f} 切变={_shear_px:.1f} "
           f"边中={_side_px:.1f} 角={_corner_px:.1f}")

        # 命中半径必须**正好**是菱形的视觉半径：小了 ⇒ 画出来的菱形点不着，
        # 大了 ⇒ 抢掉角方框的缩放。同时仍要小于角方框的方形判定。
        ok("变换：透视命中半径 = 菱形视觉半径，且仍小于角方框判定",
           abs(PERSP_HIT_VIEW_PX - PERSP_VIEW_PX / 2.0) < 1e-9
           and PERSP_HIT_VIEW_PX < CORNER_HIT_VIEW_PX,
           f"hit={PERSP_HIT_VIEW_PX} 视觉半径={PERSP_VIEW_PX / 2.0} "
           f"角判定={CORNER_HIT_VIEW_PX}")

        # 节点**底色**（用户 2026-10-09：「操作节点未选中，不要有背景色——
        # 拉伸方块不要用绿色，而是中空的」）：默认一律中空，**只有"当前
        # 节点"实心**。方框与菱形共用一套配色（形状才是语义）。
        canvas4._set_handle_focus("tl")
        ok("变换：未选中的节点中空、当前节点实心（不再是清一色绿块）",
           canvas4._handles["tl"].brush().style()
           == Qt.BrushStyle.SolidPattern
           and canvas4._handles["tr"].brush().style()
           == Qt.BrushStyle.NoBrush
           and canvas4._handles["t"].brush().style()
           == Qt.BrushStyle.NoBrush
           and canvas4._persp["p_tl"].brush().style()
           == Qt.BrushStyle.SolidPattern
           and canvas4._persp["p_tr"].brush().style()
           == Qt.BrushStyle.NoBrush,
           f"tl={canvas4._handles['tl'].brush().style()} "
           f"tr={canvas4._handles['tr'].brush().style()} "
           f"p_tl={canvas4._persp['p_tl'].brush().style()}")
        canvas4._set_handle_focus(None)
        ok("变换：焦点清掉后所有节点都回到中空",
           all(item.brush().style() == Qt.BrushStyle.NoBrush
               for item in (*canvas4._handles.values(),
                            *canvas4._diamonds.values(),
                            *canvas4._persp.values())),
           f"{[item.brush().style() for item in canvas4._handles.values()]}")

        # 裁剪/收边下是**同一批方框**，反馈改由悬停那个承担——不能变成
        # "全是空的、没有任何反馈"。
        canvas4._hover_handle = "bl"
        canvas4._apply_hover_highlight()
        ok("裁剪：悬停的方框实心、其余中空（与变换共用同一批图元）",
           canvas4._handles["bl"].brush().style()
           == Qt.BrushStyle.SolidPattern
           and canvas4._handles["br"].brush().style()
           == Qt.BrushStyle.NoBrush,
           f"bl={canvas4._handles['bl'].brush().style()} "
           f"br={canvas4._handles['br'].brush().style()}")
        canvas4._hover_handle = None
        canvas4._apply_hover_highlight()

        # ⚠️⚠️ 崩溃回归（用户 2026-10-09）：把透视角拖到**对角附近** ⇒
        # `quadToQuad` 给出"可逆但放大百万倍"的矩阵（外框 4.8e17）⇒ 预览
        # 重采样/烘焙画布全被撑爆（QImage(2.18e9) OverflowError）。现在这
        # 一步被判病态并**丢弃**：手柄停住、矩阵保持不变。
        canvas4.reset_transform()
        _paper = canvas4.image_rect()
        _before_xf = QTransform(canvas4._xf)
        canvas4.transform_perspective(
            "tl", _paper.bottomRight() - QPointF(1, 1))
        _sel = canvas4._xf_rect
        ok("变换：透视拖到对角附近被拒（矩阵不变形、不再算出天文数字外框）",
           QTransform(canvas4._xf) == _before_xf
           and _sel is not None
           and mapped_bounds(canvas4._xf, _sel) is not None,
           f"xf={canvas4._xf} bounds="
           f"{None if _sel is None else mapped_bounds(canvas4._xf, _sel)}")
        canvas4.transform_perspective("tl", _paper.topLeft() - QPointF(48, 36))
        ok("变换：正常透视仍然生效（只挡自交/塌陷的那一步）",
           QTransform(canvas4._xf) != _before_xf,
           f"xf={canvas4._xf}")

        # ⚠️⚠️ 回归（2026-10-09 用户报障「统一变换只旋转也有 bug」）：
        # ①"原本图片底还在"——旧版把整幅原图钉在 (0,0) 当底图，于是图转过
        #   来了、原来的图还在原地叠着看；②"旋转后图片不完整显示"——旧版把
        #   变换矩阵在"渲染浮层像素"和"浮层图元的 transform"里各套了一遍，
        #   内容被转两遍、还被固定大小的画布裁掉一半。
        # 这里把"预览 == 烘焙"钉成一条**像素级**断言：预览渲染成图，与
        # compose_transform（烘焙唯一实现）逐像素比。
        def scene_shot(canvas, rect: QRectF) -> QImage:
            """把场景按 ``rect``（图片坐标、1:1）渲染成一张图。

            ⚠️ 垫底用**白**：画布上"空"的那块（选区被搬走之后）现在是
            **透明**的（用户 2026-10-09：「图片旋转不再有白色的区域」），
            而烘焙产物那边仍是白底——这里比的是"内容落在纸上"，垫纸色再比
            才对得上。
            ⚠️ 构图参考线默认**五分**（2026-10-09）：它是纯 UI 叠加、烘焙
            里没有，拍进画面会把"预览 == 烘焙"的像素差顶过阈值——拍摄前
            先藏、拍完还原（四边形框/手柄一直都在画面里，阈值本来就有
            它们的余量，不动）。
            """
            guides = [item for item in canvas._guides if item.isVisible()]
            for item in guides:
                item.setVisible(False)
            shot = QImage(max(1, int(rect.width())),
                          max(1, int(rect.height())),
                          QImage.Format.Format_ARGB32)
            shot.fill(QColor("#ffffff"))
            painter = QPainter(shot)
            painter.setRenderHint(
                QPainter.RenderHint.SmoothPixmapTransform, True)
            canvas._scene.render(painter, QRectF(shot.rect()), rect)
            painter.end()
            for item in guides:
                item.setVisible(True)
            return shot

        def check_parity(canvas, label: str) -> None:
            pending = canvas.transform_pending()
            assert pending is not None  # 用例里必已发生一次变换
            sel, xf, region = pending
            if getattr(canvas, "_xf_direction", "forward") == "backward":
                inverse, ok_inv = xf.inverted()
                if ok_inv:
                    xf = inverse
            clipping = getattr(canvas, "_xf_clipping", "adjust")
            grow = clipping != "clip"
            bake = compose_transform(
                canvas_img(canvas), sel, xf, region, grow=grow,
                interpolation="linear")
            origin = (0.0, 0.0)
            if grow:
                bake, origin = bake
            if clipping == "aspect":
                crop = center_crop_aspect(
                    bake, canvas_img(canvas).width(),
                    canvas_img(canvas).height())
                origin = (origin[0] + (bake.width() - crop.width()) // 2,
                          origin[1] + (bake.height() - crop.height()) // 2)
                bake = crop
            shot = scene_shot(canvas, QRectF(
                origin[0], origin[1], bake.width(), bake.height()))
            value = plane_diff(shot, bake)
            ok(f"变换：{label}的预览 == 烘焙（逐像素平均通道差 < 6）",
               value < 6.0, f"diff={value:.2f} "
               f"bake={bake.width()}x{bake.height()}@{origin}")

        canvas4.set_tool("transform")
        undo_live = len(dialog4._undo)
        canvas4.transform_rotate(30)
        frame_before = canvas4._float_item.pixmap().cacheKey()
        pose_before = QTransform(canvas4._float_item.transform())
        canvas4.transform_rotate(15)
        ok("变换：只旋转就实时出画面（浮层像素与摆位都跟着变、像素没落地）",
           canvas4._float_item.pixmap().cacheKey() != frame_before
           and canvas4._float_item.transform() != pose_before
           and canvas_img(canvas4) is canvas4._image
           and len(dialog4._undo) == undo_live,
           f"key={canvas4._float_item.pixmap().cacheKey()} "
           f"before={frame_before} undo={len(dialog4._undo)} "
           f"expect={undo_live}")
        placement = canvas4._float_item.transform()
        ok("变换：浮层图元只做摆位（不带旋转 ⇒ 内容不会被转两次）",
           abs(placement.m12()) < 1e-9 and abs(placement.m21()) < 1e-9,
           f"transform={placement}")
        quad = canvas4._transform_quad()
        xs = [point.x() for point in quad.values()]
        ys = [point.y() for point in quad.values()]
        expect = QRectF(min(xs), min(ys),
                        max(xs) - min(xs), max(ys) - min(ys))
        got = canvas4._float_item.sceneBoundingRect()
        # ⚠️ 判据是"**盖住**内容外框"而不是"尺寸相等"：``warp_placement``
        #    取外框时向下取整/向上取整各留半像素，正好比精确外框大一点。
        ok("变换：浮层画布覆盖变换后内容的完整外框（不会裁掉一块）",
           got.contains(expect)
           and abs(got.width() - expect.width()) <= 3.0
           and abs(got.height() - expect.height()) <= 3.0,
           f"float={got} expect={expect}")
        # ⚠️⚠️ 用户第二轮报障（2026-10-09）：「白底和当前图片位置总是变化
        #   漂移……白底不应该扩大，应该是图片初始位置和大小」。旧版底图跟着
        #   旋转外框每帧重算：整幅转 30° 就涨到 920×992、原点跑到 (-160,-96)，
        #   再叠上 setSceneRect 一起变 ⇒ 看着就是"白底和图片一直在漂"。
        #   现在钉死：**恒定 = 原图矩形**。
        paper = QRectF(canvas4.image_rect())
        ok("变换：底图（纸）恒定 = 原图矩形，不随旋转长大（不再漂移）",
           canvas4._paint_image is not canvas4._image
           and canvas4._base_current_rect() == paper
           and canvas4._base_target_rect() == paper
           and canvas4._xf_base_origin == QPointF(0.0, 0.0),
           f"base={canvas4._base_current_rect()} "
           f"target={canvas4._base_target_rect()} "
           f"origin={canvas4._xf_base_origin} expect={paper}")
        # 「图片旋转不再有白色的区域」：整幅选区时底图整块**透明**
        #   （1×1 空图被缩放矩阵拉成原图矩形），露出来的画布条纹格才说得通。
        plane = canvas4._paint_image
        ok("变换：底图不再有白色区域（整幅选区时整块透明）",
           plane is not None and plane.width() == 1
           and plane.height() == 1 and plane.pixelColor(0, 0).alpha() == 0,
           f"paint={None if plane is None else (plane.width(), plane.height(), plane.pixelColor(0, 0).alpha())}")
        # 两个虚线框合成一个：固定在原位的纸边框改成**细实线**，
        #   虚线只留给跟着内容转的 _quad（用户截图里指出"两个框的虚线、
        #   颜色还不一样"）。
        ok("变换：边框与变换框都是虚线（2026-10-13 边框改虚线跟随四至）",
           canvas4._border is not None
           and canvas4._border.pen().style() == Qt.PenStyle.DashLine
           and canvas4._quad.pen().style() == Qt.PenStyle.DashLine,
           f"border={canvas4._border.pen().style() if canvas4._border else None} "
           f"quad={canvas4._quad.pen().style()}")
        check_parity(canvas4, "整幅旋转")
        # 校正（向后）走同一条路：反向矩阵同样要"预览 == 烘焙"
        canvas4.set_transform_options(direction="backward")
        check_parity(canvas4, "整幅校正（向后）")
        canvas4.set_transform_options(direction="forward")
        # 裁剪档：内容越出画布的部分要按画布边界切掉（与烘焙一致）
        canvas4.set_transform_options(clipping="clip")
        check_parity(canvas4, "裁剪到原画布")
        canvas4.set_transform_options(clipping="adjust")

        # ⚠️⚠️ 拖动中必须**实时**（2026-10-09 用户报障「只旋转不能实时渲染」）：
        # 精确档一帧要逐像素重采样整块选区（实测 12 MP `linear` 158 ms、
        # `nohalo` 442 ms），拖动根本跟不上。拖动中改成"像素不重采样、
        # 变换交给图元"（Qt 光栅器，实测 0.6–2.2 ms/帧），松手那一帧再回
        # 精确档——"预览 == 烘焙"的判据一点没松。这里把两条都钉死。
        canvas4.reset_transform()
        canvas4.set_tool("transform")
        canvas4.transform_rotate(25)
        resample_calls = []
        original_plane = canvas4._render_float_plane

        def counting_plane():
            resample_calls.append(1)
            return original_plane()

        canvas4._render_float_plane = counting_plane
        try:
            canvas4._xf_dragging = True
            for _ in range(5):
                canvas4.transform_rotate(1.0)
            fast_pose = QTransform(canvas4._float_item.transform())
            ok("变换：拖动中不逐像素重采样（每帧只改图元 ⇒ 才是实时）",
               not resample_calls, f"重采样次数={len(resample_calls)}")
            ok("变换：拖动中由浮层图元承担变换本身"
               "（与松手后的纯摆位不同口径）",
               fast_pose == canvas4._float_fast_xf()
               and (abs(fast_pose.m12()) > 1e-6
                    or abs(fast_pose.m21()) > 1e-6),
               f"transform={fast_pose}")
            ok("变换：拖动中的浮层画布 = 预览缩放的选区原图"
               "（不是重采样后的外框）",
               canvas4._float_item.pixmap().size()
               == canvas4._float_fast_plane().size(),
               f"pixmap={canvas4._float_item.pixmap().size()} "
               f"plane={canvas4._float_fast_plane().size()}")

            # 快档 vs 精确档：**同一处内容**（只差插值），取景框固定成
            # "图片 ∪ 变换后选区外框"，免得两边的 sceneRect 取整差把判据带偏
            quad_fast = canvas4._transform_quad()
            xs_fast = [point.x() for point in quad_fast.values()]
            ys_fast = [point.y() for point in quad_fast.values()]
            frame = QRectF(canvas4.image_rect()).united(
                QRectF(min(xs_fast), min(ys_fast),
                       max(xs_fast) - min(xs_fast),
                       max(ys_fast) - min(ys_fast))
            ).adjusted(-40, -40, 40, 40)
            fast_shot = scene_shot(canvas4, frame)
            canvas4.finish_transform_drag()
            exact_shot = scene_shot(canvas4, frame)
            settled_pose = QTransform(canvas4._float_item.transform())
        finally:
            del canvas4._render_float_plane
        fast_vs_exact = plane_diff(fast_shot, exact_shot)
        ok("变换：拖动中的快预览与松手后的精确预览逐像素一致（只差插值）",
           fast_vs_exact < 6.0, f"diff={fast_vs_exact:.2f}")
        ok("变换：松手立刻回到精确档（重新逐像素重采样 + 图元回到纯摆位）",
           resample_calls == [1]
           and abs(settled_pose.m12()) < 1e-9
           and abs(settled_pose.m21()) < 1e-9,
           f"重采样={len(resample_calls)} transform={settled_pose}")

        # ⚠️ 拖动中的裁剪掩膜方向（踩过的坑）：``setClipPath`` 是把笔限制在
        #    路径**之内**，配 ``CompositionMode_Clear`` 必须传**补集**——
        #    传原集会清反（该留的透明、该清的留着，画面像内容整块消失）。
        canvas4.set_transform_options(clipping="clip")
        canvas4._xf_dragging = True
        canvas4._sync_float()
        mask_plane = canvas4._float_fast_plane()
        mask_mid = mask_plane.pixelColor(mask_plane.width() // 2,
                                         mask_plane.height() // 2).alpha()
        # 全幅选区 + 旋转 ⇒ 区域局部坐标里"图片矩形"是一个被转过的平行
        # 四边形，四角必然落在画布外 ⇒ 必须被清成透明
        mask_corner = mask_plane.pixelColor(1, 1).alpha()
        ok("变换：拖动中的裁剪掩膜方向正确（中间留内容、画布外清透明）",
           mask_mid > 200 and mask_corner == 0,
           f"mid_alpha={mask_mid} corner_alpha={mask_corner}")
        canvas4._xf_dragging = False
        canvas4._xf_preview_keyframe = None
        canvas4._sync_float()
        canvas4.set_transform_options(clipping="adjust")
        canvas4.reset_transform()
    finally:
        dialog4.deleteLater()
    app.processEvents()