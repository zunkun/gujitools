# -*- coding: utf-8 -*-
"""图片编辑弹窗自测：工具的纯逻辑 + 撤销栈 + 预览弹窗接线。

断言线（只看可观测行为）：

1. **裁剪**：进入工具**默认选中整幅图**、只许手柄内收/框内移动，不做
   截图式"拖拽画框"；应用后画布尺寸 = 选区尺寸，换图（应用/撤销/还原）
   后重新默认全选；
1b. **变换数学**：绕点旋转/缩放/切变（轴心不动、方向与系数钉死）；
1c. **变换**：默认全选、框内拖=移动、按下即实时预览（底图填白+浮层）、
   应用烘焙（原位置填白、内容落位）、切走工具自动烘焙、从轴心缩放、
   重置、命中测试；「调整范围」收边进入小区域（自动退出+轴心跟随）、
   局部烘焙后**区域外像素一动不动**；
2. **擦除**：橡皮擦涂过的污点被擦成白底；一笔开始就压撤销点
   （``stroke_started`` → ``_push_undo`` 已接线）；悬停时空白光标 +
   实圈指示，圈直径恒等于橡皮擦直径（所见即所擦）；
3. **文字**：落点生成就地编辑的文字块（文本交互开启）、**键盘输入直达
   文字块**（焦点路由：画布 StrongFocus → 场景焦点项）、按住拖动超过
   阈值移动整块、「插入文字」写入图片并压撤销点、切走工具自动写入；
   空白文本不动图；字体下拉**以中文字体为主**（西文只留几个常用）；
   颜色是**一个按钮**，常用色块收在它弹出的面板里（不再散在选项行上）；
3b. **回归（2026-10-01 用户报障"文字大小不生效"）**：选项行控件抢走画布
   键盘焦点后，改字号/颜色仍必须作用在当前文字块上（样式走"当前样式块"
   而不是场景焦点项；字号滑杆另设 NoFocus 保住光标）；
2b. **变形（PS 操控变形）**：进入工具建网格（无图钉、无待应用形变）；
   点图放钉（吸附最近顶点、同一顶点不重复）、拖动图钉→附近内容跟着走、
   远场逐字节不动（ARAP 局部 + 边框锚点）、松手/应用/切走工具都烘焙、
   应用后图钉留在原地、重置/右键删除、改网格疏密清空图钉；
4. **撤销/重做/还原**：状态按步回退/前进，还原可撤销，栈深 ≤ 12；
5. **选区门槛**：小于 4px 的选区视为没有（误点不产生 1px 裁剪）；
6. **初始自适应**：窗口就位/改变大小后画布自动适应窗口（没手动缩放过时），
   修复"打开时图片缩成指甲盖"（fit 在布局前算到脏尺寸）；
7. **两行工具栏**：撤销/还原/缩放按钮都在窗口内（单行时会被挤出左上角），
   工具选项行在主工具栏下方；
8. **窗口旗标**：最小化/最大化/关闭按钮齐备（缺 CloseButtonHint 时
   Windows 上关闭按钮失效，用户报障过）；
9. **预览弹窗接线**：有「编辑」按钮、宽度取满（理想 1360，超出屏幕时夹进
   可用区域）、无图禁用/有图可用、``_open_editor`` 拿到画布整图；
10. **编辑结果写回画布**：``_edit_image`` 走的通道（set_image）会替换画布图。
"""
from __future__ import annotations

NAME = "image_editor"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗（裁剪/变换/擦除/文字）"


def make_image(width: int, height: int):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    return image


def is_dark(color) -> bool:
    """足够深的像素（文字/黑笔刷落点，抗锯齿边缘不算）。"""
    return color.red() < 100 and color.green() < 100 and color.blue() < 100


def run(ctx) -> None:
    import math

    from PySide6.QtCore import QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QImage

    from tests.selftests._context import ok

    from desktop.components.viewers.image_editor import (
        CAGE_DENSITY_CHOICES, CAGE_DENSITY_DEFAULT, CAGE_PREVIEW_PIXELS,
        CAGE_PREVIEW_SETTLE_PIXELS, EDIT_FIT_RATIO,
        DEFORM_FIT_RATIO, DEFORM_PREVIEW_PIXELS, DEFORM_PREVIEW_SETTLE_PIXELS,
        ERASER_DEFAULT, MESH_DENSITY_CHOICES, MESH_DENSITY_DEFAULT,
        RECTIFY_RATIO_CHOICES, RECTIFY_RATIO_DEFAULT,
        EditorCanvas, ImageEditorDialog, TextBlockItem, bake_transform,
        cage_preview_scale, clamp_rect, draw_text, rotate_about, scale_about,
        shear_about,
    )

    # ---- 1. clamp_rect ----
    bounds = QRectF(0, 0, 100, 80)
    ok("clamp_rect：界内矩形原样保留",
       clamp_rect(QRectF(10, 10, 30, 20), bounds) == QRectF(10, 10, 30, 20), "")
    ok("clamp_rect：越界矩形先平移夹回",
       clamp_rect(QRectF(90, 70, 30, 20), bounds) == QRectF(70, 60, 30, 20), "")
    ok("clamp_rect：比画布还大的矩形缩到画布",
       clamp_rect(QRectF(-10, -10, 200, 160), bounds) == bounds, "")

    # ---- 1b. 变换数学（QTransform 复合约定在这里钉死） ----
    center = QPointF(100, 60)
    rotated = rotate_about(center, 90).map(QPointF(0, 0))
    expected = center + QPointF(60, -100)  # (0,0) 绕中心顺时针 90°
    ok("变换数学：绕点旋转（轴心不动、角点落到顺时针 90° 位置）",
       (rotated - expected).manhattanLength() < 1e-6
       and (rotate_about(center, 90).map(center) - center).manhattanLength()
       < 1e-6,
       f"rotated={rotated} expected={expected}")
    scaled = scale_about(QPointF(200, 120), 2.0, 2.0).map(QPointF(0, 0))
    ok("变换数学：绕锚点缩放",
       (scaled - QPointF(-200, -120)).manhattanLength() < 1e-6,
       f"scaled={scaled}")
    sheared = shear_about(QPointF(0, 0), 0.0, 0.5).map(QPointF(200, 0))
    ok("变换数学：绕锚点切变（y 随 x 斜切）",
       (sheared - QPointF(200, 100)).manhattanLength() < 1e-6,
       f"sheared={sheared}")

    # ---- 4. draw_text ----
    text_base = make_image(400, 120)
    written = draw_text(text_base, QPointF(20, 20), "测试", 64, QColor("#000000"))
    has_dark = any(
        is_dark(written.pixelColor(x, y))
        for y in range(20, 90, 2) for x in range(20, 160, 2)
    )
    ok("文字：非空文本在落点附近留下深色像素", has_dark, "")
    untouched = draw_text(text_base, QPointF(20, 20), "  ", 64, QColor("#000000"))
    same = all(
        untouched.pixelColor(x, y).rgba() == text_base.pixelColor(x, y).rgba()
        for y in range(0, 120, 7) for x in range(0, 400, 7)
    )
    ok("文字：空白文本不改动图片", same, "")

    # ---- 3/5/6. 弹窗级：擦除、撤销、选区门槛 ----
    app = ctx.app
    img = make_image(200, 120)
    dialog = ImageEditorDialog(None, img)
    try:
        ok("弹窗：编辑画布装入了整图",
           dialog.canvas.image.width() == 200
           and dialog.canvas.image.height() == 120, "")

        # ---- 弹窗开大 + 最小化/最大化/关闭按钮 + 工具按钮选中高亮 ----
        # ⚠️ 期望 1440×940 只是**上限**：落地尺寸会被 apply_window_size 夹进
        #    屏幕可用区域（1920×1080 @125% 的机器可用高只有 824）。这里按同
        #    一个公式算期望值，既守住"默认开大"，也守住"不许顶出屏幕"。
        from desktop.components.viewers.image_editor import (
            EDITOR_MIN_SIZE, EDITOR_SIZE,
        )
        from desktop.ui.window_size import (
            FRAME_ALLOWANCE, FIT_RATIO, available_area,
        )

        area = available_area(dialog)
        expect_w = min(EDITOR_SIZE.width(),
                       int((area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        expect_h = min(EDITOR_SIZE.height(),
                       int((area.height() - FRAME_ALLOWANCE.height()) * FIT_RATIO))
        ok("弹窗：默认开大（1440×940，超出屏幕时夹进可用区域）并带"
           "最小化/最大化/关闭按钮",
           dialog.width() == expect_w and dialog.height() == expect_h
           and dialog.width() <= area.width()
           and dialog.height() + FRAME_ALLOWANCE.height() <= area.height()
           and bool(dialog.windowFlags() & Qt.WindowMinimizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowMaximizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowCloseButtonHint),
           f"size={dialog.width()}x{dialog.height()} 期望={expect_w}x{expect_h} "
           f"可用区={area.width()}x{area.height()} "
           f"flags={hex(int(dialog.windowFlags()))}")
        ok("弹窗：最小尺寸也被夹进可用区域（小屏上仍能拖到放得下）",
           dialog.minimumWidth() <= min(EDITOR_MIN_SIZE.width(), dialog.width())
           and dialog.minimumHeight() <= min(EDITOR_MIN_SIZE.height(), dialog.height()),
           f"min={dialog.minimumWidth()}x{dialog.minimumHeight()}")
        ok("工具栏：工具按钮是 ToggleButton（选中态有主色高亮），"
           "裁剪/变换/变形/变换笼/校正/擦除/文字七个",
           all(type(dialog._tool_buttons[k]).__name__ == "ToggleButton"
               for k in dialog._tool_buttons)
           and set(dialog._tool_buttons) == {"crop", "transform", "deform",
                                             "cage", "rectify", "erase",
                                             "text"}
           and dialog._tool_buttons["crop"].isChecked()
           and not dialog._tool_buttons["erase"].isChecked(),
           f"tools={sorted(dialog._tool_buttons)} "
           f"crop={dialog._tool_buttons['crop'].isChecked()} "
           f"erase={dialog._tool_buttons['erase'].isChecked()}")

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

        # ---- 初始自适应 + 两行工具栏（需要真实布局几何，先显示） ----
        dialog.show()
        app.processEvents()
        dialog.resize(1000, 720)
        app.processEvents()
        app.processEvents()
        canvas = dialog.canvas
        vw, vh = canvas.viewport().width(), canvas.viewport().height()
        # 图片占视口 EDIT_FIT_RATIO（缺省不铺满，四周留白，用户 2026-10-02 定）
        expected = EDIT_FIT_RATIO * min(vw / 200, vh / 120)
        ok("画布：窗口就位后自动适应窗口（修复初始过小，四周留白）",
           abs(canvas.transform().m11() - expected) <= expected * 0.05
           and canvas._user_zoomed is False,
           f"m11={canvas.transform().m11():.3f} expected={expected:.3f} "
           f"viewport={vw}x{vh}")
        # 手柄视觉尺寸 = 视图像素(12) ÷ 倍率 × 倍率 ≈ 12px：fit() 换倍率后
        # 必须重算覆盖层，否则 set_image 时脏 viewport 算的小倍率会留下巨型手柄
        tl_view = canvas.mapFromScene(
            canvas._handle_boxes(canvas.image_rect())["tl"]).boundingRect()
        ok("画布：手柄视觉尺寸 ≈ 12px（fit 换倍率后覆盖层已重算）",
           7 <= tl_view.width() <= 20 and 7 <= tl_view.height() <= 20,
           f"tl_view={tl_view.width():.1f}x{tl_view.height():.1f}")

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
        zoom_before = canvas._zoom
        canvas.mousePressEvent(mouse_event("press", corner))
        ok("裁剪：角部按下进入收边状态",
           canvas._mode is not None and canvas._mode[0] == "handle"
           and canvas._mode[1] == "tl", f"mode={canvas._mode}")
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(60, 30)))))
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(60, 30)))))
        sel = canvas.selection()
        ok("裁剪：边缘拖动后选区收窄（视图取整容差 <1px）",
           sel is not None and abs(sel.left() - 60) < 1
           and abs(sel.top() - 30) < 1
           and abs(sel.right() - 200) < 1 and abs(sel.bottom() - 120) < 1,
           f"sel={sel}")
        ok("裁剪：松手后视图自动放大到新选区",
           canvas._zoom > zoom_before,
           f"zoom {zoom_before:.2f} -> {canvas._zoom:.2f}")
        sel_view = canvas.mapFromScene(canvas.selection()).boundingRect()
        vp = canvas.viewport().rect()
        ok("裁剪：适配选区后四周留白（选区约占 80% 视口，不顶边）",
           sel_view.width() < vp.width() and sel_view.height() < vp.height(),
           f"sel_view={sel_view.width():.0f}x{sel_view.height():.0f} "
           f"viewport={vp.width()}x{vp.height()}")

        # ---- 悬停反馈：光标形态 + 边界高亮（用户 20:28 定） ----
        app.processEvents()
        sel_now = canvas.selection()
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
        ok("工具栏：缩放按钮进了主工具栏行（在「还原」右侧、有宽度）",
           all(
               getattr(dialog, n).x() > dialog.reset_btn.x()
               and getattr(dialog, n).width() > 0
               for n in ("zoom_in_btn", "zoom_out_btn", "fit_btn")
           ),
           f"reset.x={dialog.reset_btn.x()} "
           f"zoom.x={[getattr(dialog, n).x() for n in ('zoom_in_btn', 'zoom_out_btn', 'fit_btn')]}")
        ok("工具栏：两行结构（选项行在主工具栏下方）",
           dialog._option_page is not None
           and dialog._option_page.y()
           >= dialog.undo_btn.y() + dialog.undo_btn.height(),
           f"page.y={dialog._option_page.y()} "
           f"undo.bottom={dialog.undo_btn.y() + dialog.undo_btn.height()}")
        # 回归（2026-09-30 用户截图）：__init__ 里 _set_tool 被调两次，
        # 被遗弃的旧选项页以默认几何 (0,0,100,30) 悬在左上角盖住撤销按钮
        # （deleteLater 在构造期不生效）。所有可见直儿子都不许落在 (0,0)。
        from PySide6.QtWidgets import QWidget as _QW

        strays = [
            c for c in dialog.findChildren(_QW)
            if c.parent() is dialog and c.isVisible()
            and c.x() == 0 and c.y() == 0
        ]
        ok("工具栏：没有游离控件压在左上角（旧选项页不会盖住撤销按钮）",
           not strays,
           f"strays={[f'{type(c).__name__}@{c.geometry().getRect()}' for c in strays]}")
        app.processEvents()

        # 选区门槛：< 4px 视为没有
        dialog.canvas.set_tool("crop")
        dialog.canvas._rect = QRectF(10, 10, 3, 60)
        ok("选区：小于 4px 的选区视为没有", dialog.canvas.selection() is None, "")
        dialog.canvas._rect = QRectF(10, 10, 3, 3)
        ok("选区：小于 4px 的方块也视为没有",
           dialog.canvas.selection() is None, "")

        # 裁剪 + 撤销 + 重做 + 还原
        dialog.canvas._rect = QRectF(0, 0, 100, 120)
        dialog._apply_crop()
        ok("裁剪：应用后画布尺寸 = 选区尺寸",
           dialog.canvas.image.width() == 100
           and dialog.canvas.image.height() == 120, "")
        ok("裁剪：应用（换图）后裁剪区重新默认全选新图",
           dialog.canvas.selection() == dialog.canvas.image_rect(),
           f"sel={dialog.canvas.selection()}")
        dialog._undo_now()
        ok("撤销：裁剪被完整回退",
           dialog.canvas.image.width() == 200
           and dialog.canvas.image.height() == 120, "")
        dialog._redo_now()
        ok("重做：裁剪被重新应用", dialog.canvas.image.width() == 100, "")
        dialog._reset_all()
        ok("还原：回到打开时的图", dialog.canvas.image.width() == 200, "")
        dialog._undo_now()
        ok("还原本身可撤销：回到还原前的裁剪结果",
           dialog.canvas.image.width() == 100, "")

        # 栈深上限
        for _ in range(20):
            dialog._push_undo()
        ok("撤销栈：深度被夹在 12 以内", len(dialog._undo) <= 12,
           f"depth={len(dialog._undo)}")

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
            wiped = dialog2.canvas.image.pixelColor(100, 60)
            ok("擦除：橡皮擦涂过的污点被擦成白底", wiped.value() > 230,
               f"pixel={wiped.value()}")
            ok("擦除：一笔开始压了撤销点（stroke_started 接线）",
               len(dialog2._undo) == 1, f"undo={len(dialog2._undo)}")
        finally:
            dialog2.deleteLater()

        # 文字：就地文字块（编辑态 + 拖拽移动 + 插入写图 + 切工具自动写入）
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent
        from qfluentwidgets import ComboBox

        dialog3 = ImageEditorDialog(None, make_image(400, 200))
        try:
            canvas3 = dialog3.canvas
            canvas3.set_tool("text")
            item = canvas3.add_text_block(
                QPointF(30, 30), 48, QColor("#000000"), "SimSun")
            ok("文字：落点生成文字块、开启就地编辑（文本交互）",
               isinstance(item, TextBlockItem)
               and bool(item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction),
               f"type={type(item).__name__} "
               f"flags={item.textInteractionFlags()}")

            # 焦点路由：键盘输入必须能到达就地文字块（2026-10-01 回归：
            # 画布 NoFocus 时打字全部落空，用户报「输入没效果」）
            from PySide6.QtTest import QTest

            typing = canvas3.add_text_block(
                QPointF(100, 100), 48, QColor("#000000"), "SimSun")
            QTest.keyClicks(canvas3, "Ab")
            ok("文字：键盘输入直达就地文字块（视图→场景焦点项）",
               typing.toPlainText() == "Ab",
               f"text={typing.toPlainText()!r}")

            def item_mouse(kind: str, item, scene_pos: QPointF):
                types = {
                    "press": QEvent.Type.GraphicsSceneMousePress,
                    "move": QEvent.Type.GraphicsSceneMouseMove,
                    "release": QEvent.Type.GraphicsSceneMouseRelease,
                }
                ev = QGraphicsSceneMouseEvent(types[kind])
                ev.setButton(
                    Qt.MouseButton.LeftButton if kind != "move"
                    else Qt.MouseButton.NoButton)
                # move：拖拽进行中（按住左键）；release：左键已松开
                ev.setButtons(
                    Qt.MouseButton.LeftButton if kind != "release"
                    else Qt.MouseButton.NoButton)
                ev.setScenePos(scene_pos)
                ev.setPos(item.mapFromScene(scene_pos))
                return ev

            item.setPlainText("测试")
            item.mousePressEvent(item_mouse(
                "press", item, QPointF(30, 30)))
            item.mouseMoveEvent(item_mouse(
                "move", item, QPointF(80, 95)))
            item.mouseReleaseEvent(item_mouse(
                "release", item, QPointF(80, 95)))
            ok("文字：按住拖动移动文字块（单击放光标不受影响）",
               (item.pos() - QPointF(80, 95)).manhattanLength() < 1e-6,
               f"pos={item.pos()}")

            undo_before = len(dialog3._undo)
            dialog3._commit_text_blocks()
            burned = dialog3.canvas.image
            has_dark = any(
                is_dark(burned.pixelColor(x, y))
                for y in range(40, 130, 3) for x in range(60, 200, 3)
            )
            ok("文字：「插入文字」把文字块写进图片（落点附近出现深色像素）",
               has_dark, "")
            ok("文字：插入压了撤销点",
               len(dialog3._undo) == undo_before + 1,
               f"undo={len(dialog3._undo)} before={undo_before}")
            ok("文字：插入后画布上的文字块清空",
               canvas3.text_blocks() == [], "")

            # 切走工具：未插入的非空文字块自动写入
            item2 = canvas3.add_text_block(
                QPointF(250, 30), 48, QColor("#000000"), "SimSun")
            item2.setPlainText("自动")
            undo_before = len(dialog3._undo)
            dialog3._set_tool("crop")
            ok("文字：切走工具时未插入的文字自动写入",
               canvas3.text_blocks() == []
               and len(dialog3._undo) == undo_before + 1,
               f"undo={len(dialog3._undo)} before={undo_before}")
            # 空块（点了落点没打字）失焦自删、不产生撤销点
            dialog3._set_tool("text")
            canvas3.add_text_block(
                QPointF(60, 60), 48, QColor("#000000"), "SimSun")
            undo_before = len(dialog3._undo)
            dialog3._set_tool("crop")
            ok("文字：空文字块既不写入也不压撤销点",
               len(dialog3._undo) == undo_before, "")
            # ---- 选项行：字体下拉（中文为主 + 几个常用西文） ----
            from desktop.ui.fonts import LATIN_TEXT_FONTS, text_font_families

            dialog3._set_tool("text")
            combo = dialog3._option_page.findChild(ComboBox)
            texts = ([combo.itemText(i) for i in range(combo.count())]
                     if combo is not None else [])
            latin_here = [t for t in texts if t in LATIN_TEXT_FONTS]
            first_latin = (texts.index(latin_here[0]) if latin_here
                           else len(texts))
            ok("文字：选项行有字体下拉，且用的是「中文为主」的清单"
               "（不是系统全量字体）",
               combo is not None and texts == text_font_families()
               and len(texts) > 0,
               f"n={len(texts)} first={texts[:3]}")
            ok("文字：西文只留几个常用、且全排在中文字体之后",
               len(latin_here) <= len(LATIN_TEXT_FONTS)
               and all(t not in LATIN_TEXT_FONTS for t in texts[:first_latin]),
               f"latin={latin_here} first_latin={first_latin}")

            # ---- 颜色：一个按钮 + 面板里的常用色块 + 整块样式（手机作图口径） ----
            from desktop.ui.color_picker import (
                ColorPickerButton as GujiColorPicker,
            )
            from desktop.ui.color_picker import SwatchButton

            from desktop.components.viewers.image_editor import TEXT_SWATCHES

            picker = dialog3._option_page.findChild(GujiColorPicker)
            ok("文字：选项行是一个颜色按钮（色点 + 十六进制 + 下拉）",
               picker is not None
               and picker.color().name() == dialog3._text_color,
               f"picker={picker}")
            ok("文字：常用色块不再散在选项行上（已搬进选择器面板）",
               dialog3._option_page.findChildren(SwatchButton) == [], "")
            styled = canvas3.add_text_block(
                QPointF(150, 110), 48, QColor("#000000"), "SimSun")
            styled.setPlainText("样式块")
            ok("文字：新块即焦点块", canvas3.focused_text_block() is styled, "")
            picker._open_popup()
            app.processEvents()
            panel = picker.popup()
            swatches = list(panel._swatches) if panel is not None else []
            ok("文字：面板里有全部常用色块（黑墨/白粉/朱批/藏蓝/赭黄/黛绿）",
               panel is not None and len(swatches) == len(TEXT_SWATCHES)
               and all(s.toolTip() for s in swatches),
               f"n={len(swatches)}")
            zhu = next(s for s in swatches
                       if s.color().name().lower() == "#d32f2f")
            dialog3._text_color = "#000000"
            zhu.click()
            app.processEvents()
            ok("文字：面板里点常用色块 → 整块即时换色并收起面板",
               styled.defaultTextColor().name() == "#d32f2f"
               and dialog3._text_color == "#d32f2f"
               and not panel.isVisible(),
               f"color={styled.defaultTextColor().name()} "
               f"visible={panel.isVisible()}")
            picker.colorChanged.emit(QColor("#1976d2"))
            ok("文字：选择器换色对整块即时生效",
               styled.defaultTextColor().name() == "#1976d2"
               and dialog3._text_color == "#1976d2",
               f"color={styled.defaultTextColor().name()}")
            # ⚠️ 别硬编码 "Arial"：离屏环境若注册过内置字体，QFontDatabase
            # 就非空但只剩那一种族（如 FangSong），Arial 根本不在下拉里
            # （findData 落到 -1 → 换成下标 0，断言就假红了）。护栏的本意
            # 是"换字体对整块生效"：能挑到与当前不同的族（优先 Arial）
            # 才切换验证；整个下拉只有当前一种族的环境越过。
            target_family = ("Arial" if "Arial" in texts
                             else (latin_here[0] if latin_here else None))
            if target_family is None or target_family == "SimSun":
                others = [t for t in texts if t != "SimSun"]
                target_family = others[-1] if others else None
            combo.setCurrentIndex(max(0, combo.findData(target_family)))
            app.processEvents()
            ok("文字：换字体对整块即时生效（整体切换，非逐字；"
               "下拉只有当前一种族的环境越过）",
               len(texts) < 2
               or (target_family is not None
                   and styled.font().family().lower() == target_family.lower()),
               f"want={target_family} got={styled.font().family()} "
               f"texts={texts[:4]}")

            # ---- 回归（2026-10-01 用户报障「文字大小不生效」）----
            # 根因：选项行控件抢走画布键盘焦点 → 场景焦点项变 None → 按焦点项
            # 找块的样式改动全部落空。样式现在走"当前样式块"，与焦点解耦。
            from qfluentwidgets import Slider as FluentSlider

            size_slider = dialog3._option_page.findChild(FluentSlider)
            ok("回归：字号滑杆是 NoFocus（拖动不抢画布焦点、光标不丢）",
               size_slider is not None
               and size_slider.focusPolicy() == Qt.FocusPolicy.NoFocus,
               f"policy={size_slider.focusPolicy() if size_slider else None}")
            # ⚠️ 必须真显示弹窗：控件焦点只在真窗口里才生效（不显示时
            #    setFocus 是空操作，场景焦点项也不会被清）
            dialog3.show()
            app.processEvents()
            app.processEvents()
            canvas3.setFocus()
            styled.setFocus()
            app.processEvents()
            ok("回归：文字块拿着场景焦点", canvas3.focused_text_block() is styled,
               "")
            # 工具栏「完成」按钮是可聚焦控件，点它（或任何选项行控件）就会把
            # 键盘焦点从画布抢走——正是用户报障的触发动作
            dialog3.done_btn.setFocus()
            app.processEvents()
            ok("回归：焦点被抢走后场景焦点项为空",
               canvas3.focused_text_block() is None, "")
            size_slider.setValue(96)
            app.processEvents()
            ok("回归：焦点被抢后改字号仍作用在当前文字块上（不再落空）",
               styled.font().pixelSize() == 96 and dialog3._text_size == 96,
               f"px={styled.font().pixelSize()} size={dialog3._text_size}")
            picker.colorChanged.emit(QColor("#2e7d32"))
            ok("回归：焦点被抢后换颜色同样落在当前文字块上",
               styled.defaultTextColor().name() == "#2e7d32",
               f"color={styled.defaultTextColor().name()}")
            canvas3.setFocus()
            styled.setFocus()
            app.processEvents()

            # ---- 悬停边界虚线框：悬停显示 / 拖动跟随 / 松手消失 ----
            # ⚠️ 事件走 **viewport 事件管线**（与真实鼠标一致）；直接调
            # canvas.mousePressEvent 不经 viewportEvent，场景收不到
            dialog3.show()
            app.processEvents()
            app.processEvents()

            def post(kind: str, pos: QPointF,
                     drag: bool = False) -> None:
                types = {
                    "press": QEvent.Type.MouseButtonPress,
                    "move": QEvent.Type.MouseMove,
                    "release": QEvent.Type.MouseButtonRelease,
                }
                app.sendEvent(canvas3.viewport(), QMouseEvent(
                    types[kind], pos,
                    Qt.MouseButton.LeftButton if kind == "press"
                    else Qt.MouseButton.NoButton,
                    Qt.MouseButton.LeftButton
                    if kind == "press" or drag
                    else Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier))
                app.processEvents()

            block_center = QPointF(
                canvas3.mapFromScene(styled.mapToScene(
                    styled.boundingRect().center())))
            # 悬停：虚线框出现且框住块身
            post("move", block_center)
            hover_rect = canvas3._text_outline.rect()
            expect_rect = styled.mapRectToScene(styled.boundingRect())
            ok("文字：悬停文字出现边界虚线框（范围=块身）",
               canvas3._text_outline.isVisible()
               and (hover_rect.center() - expect_rect.center())
               .manhattanLength() < 2.0
               and abs(hover_rect.width() - expect_rect.width()) < 2.0,
               f"rect={hover_rect} expect={expect_rect}")
            # 拖动（画布→场景→块的真实链路）：框跟随、块整体移动。
            # ⚠️ 按下必须走 QTest（合成 sendEvent 的 press 场景不受理），
            #    移动/松手 sendEvent 即可（块已抓住鼠标，画布只做转发）
            from PySide6.QtTest import QTest

            QTest.mousePress(
                canvas3.viewport(), Qt.MouseButton.LeftButton,
                pos=block_center.toPoint())
            post("move", block_center + QPointF(60, 30), drag=True)
            moved_rect = canvas3._text_outline.rect()
            moved_expect = styled.mapRectToScene(styled.boundingRect())
            ok("文字：按住拖动整块移动、虚线框跟随",
               styled.scenePos() != QPointF(150, 110)
               and canvas3._text_outline.isVisible()
               and (moved_rect.center() - moved_expect.center())
               .manhattanLength() < 1.0
               and abs(moved_rect.width() - moved_expect.width()) < 1.0,
               f"pos={styled.scenePos()} rect={moved_rect} "
               f"expect={moved_expect}")
            # ⚠️ 松手同样必须走 QTest：合成 sendEvent 的 release 场景不受理
            QTest.mouseRelease(
                canvas3.viewport(), Qt.MouseButton.LeftButton,
                pos=(block_center + QPointF(60, 30)).toPoint())
            ok("文字：松手落位、虚线框消失",
               not canvas3._text_outline.isVisible()
               and canvas3._scene.mouseGrabberItem() is None,
               f"visible={canvas3._text_outline.isVisible()}")
            # 悬停离开块：虚线框隐藏
            post("move", QPointF(5, 5))
            ok("文字：悬停离开文字块，虚线框隐藏",
               not canvas3._text_outline.isVisible(), "")
            canvas3.clear_text_blocks()
        finally:
            dialog3.deleteLater()

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

            # 框内拖 = 移动（真实鼠标事件走一遍）
            dialog4.show()
            app.processEvents()
            app.processEvents()
            canvas4.mousePressEvent(mouse_event("press", vpos(QPointF(160, 60))))
            ok("变换：按下即进入实时预览（底图填白 + 浮层，真像素未动）",
               canvas4._mode is not None and canvas4._mode[0] == "xf_move"
               and canvas4._float_item is not None
               and canvas4._paint_image.pixelColor(160, 60).value() > 230
               and canvas4._image.pixelColor(160, 60).value() < 128,
               f"mode={canvas4._mode} "
               f"paint={canvas4._paint_image.pixelColor(160, 60).value()}")
            canvas4.mouseMoveEvent(mouse_event("move", vpos(QPointF(130, 60))))
            canvas4.mouseReleaseEvent(mouse_event(
                "release", vpos(QPointF(130, 60))))
            origin = canvas4._xf.map(QPointF(0, 0))
            ok("变换：框内拖动 = 平移（−30,0，视口取整容差 <1.5px）",
               (origin - QPointF(-30, 0)).manhattanLength() <= 1.5,
               f"origin={origin}")

            undo_before = len(dialog4._undo)
            dialog4._commit_transform()
            baked = canvas4.image
            # grow：整幅选区左移 30 ⇒ 新画布 = 原图 ∪ 移位后内容，左上角在
            # 原坐标 (−30, 0)，尺寸不变（移位量正好等于外扩量）。新画布里的
            # 坐标 = 原坐标 − origin = 原坐标 + 30。
            ok("变换：应用后画布按内容外扩（左移 30 ⇒ 原位置 −30 起算）",
               baked.width() == 200 and baked.height() == 120,
               f"size={baked.width()}x{baked.height()}")
            ok("变换：应用后内容平移、原位置填白（烘焙与预览一致）",
               baked.pixelColor(125 + 30, 60).value() < 128
               and baked.pixelColor(160 + 30, 60).value() > 230,
               f"dark={baked.pixelColor(155, 60).value()} "
               f"white={baked.pixelColor(190, 60).value()}")
            ok("变换：应用压撤销点并清掉待应用状态",
               len(dialog4._undo) == undo_before + 1
               and canvas4.transform_pending() is None,
               f"undo={len(dialog4._undo)} before={undo_before}")

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
            ok("变换：非正方图旋转 90° ⇒ 画布按内容外框收成 120×200",
               (canvas4.image.width(), canvas4.image.height()) == (120, 200),
               f"size={canvas4.image.width()}x{canvas4.image.height()}")

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

            # 命中测试：角手柄 / 框外（旋转）
            tl_view = vpos(QPointF(canvas4.image_rect().topLeft()))
            far_view = vpos(QPointF(-60, -60))
            ok("变换：命中测试（角=手柄、远处=框外旋转）",
               canvas4._hit_transform(tl_view) == "tl"
               and canvas4._hit_transform(far_view) == "outside",
               f"tl={canvas4._hit_transform(tl_view)} "
               f"far={canvas4._hit_transform(far_view)}")
        finally:
            dialog4.deleteLater()

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
            baked5 = canvas5.image
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
        finally:
            dialog5.deleteLater()

        # ---- 变形：PS「操控变形」（钉图钉 → 拖图钉 → 附近内容跟着走） ----
        cimg = make_image(200, 120)
        for x in range(100, 130):      # 会被扯走的黑块
            for y in range(20, 50):
                cimg.setPixel(x, y, 0xFF000000)
        dialog6 = ImageEditorDialog(None, cimg)
        try:
            canvas6 = dialog6.canvas
            dialog6._set_tool("deform")
            ok("变形：进入工具即建网格、无图钉、无待应用形变",
               canvas6._tool == "deform" and canvas6.pin_count() == 0
               and canvas6.pins_pending() is None
               and canvas6.mesh_density() == MESH_DENSITY_DEFAULT,
               f"图钉 {canvas6.pin_count()} 个，pending="
               f"{canvas6.pins_pending() is not None}")

            from qfluentwidgets import ComboBox as _Combo
            from qfluentwidgets import PushButton as _Push

            texts = [b.text() for b in dialog6._option_page.findChildren(_Push)]
            combos = dialog6._option_page.findChildren(_Combo)
            ok("变形：选项行有「重置 / 应用变形」按钮与「网格疏密」下拉",
               {"重置", "应用变形"} <= set(texts)
               and len(combos) == 1
               and combos[0].count() == len(MESH_DENSITY_CHOICES),
               f"按钮={texts} 下拉项数={[c.count() for c in combos]}")

            # 改格距会重建网格（顶点下标全变）→ 必须清空图钉
            canvas6.pin_add(QPointF(150, 60))
            ok("变形：改网格疏密会重建网格并清空图钉（旧钉指向老顶点，无意义）",
               canvas6.pin_count() == 1
               and (canvas6.set_mesh_density(80.0) or canvas6.pin_count() == 0),
               f"改前 {canvas6.pin_count() if canvas6.pin_count() else '?'} 钉")
            canvas6.set_mesh_density(MESH_DENSITY_DEFAULT)

            dialog6.show()
            app.processEvents()
            app.processEvents()
            ok("变形：无图钉时画布上不显示任何图钉圆点",
               len(canvas6._pin_dots) == 0, f"圆点 {len(canvas6._pin_dots)} 个")

            # 进「变形」时图片不铺满视口：四周留白，好把图钉往图外拖。
            # ⚠️ 所有工具现在都留白（用户 2026-10-02：编辑区不要铺满、上下
            #    留白），所以"铺满"必须**显式**量 ratio=1.0 的倍率。不能靠
            #    ``fit(1.0)``：``resizeEvent`` 会在 ``_user_zoomed=False`` 时
            #    用 ``_fit_ratio`` 重新 fit，把显式值覆盖掉；因此临时把
            #    fit_ratio 设为 1.0 量完再还原。
            dialog6._set_tool("crop")
            app.processEvents()
            old_ratio6 = canvas6._fit_ratio
            canvas6.set_fit_ratio(1.0)
            app.processEvents()
            full_zoom6 = canvas6._zoom
            canvas6.set_fit_ratio(old_ratio6)
            dialog6._set_tool("deform")
            app.processEvents()
            ok("变形：进这个工具时图片不铺满视口（四周留出可操作空间）",
               full_zoom6 > 0
               and abs(canvas6._zoom / full_zoom6 - DEFORM_FIT_RATIO) < 0.03,
               f"铺满 {full_zoom6:.4f} → 留白 {canvas6._zoom:.4f}"
               f"（比值 {canvas6._zoom / full_zoom6:.3f}，期望 {DEFORM_FIT_RATIO}）")
            dialog6._set_tool("crop")
            app.processEvents()
            ok("变形：切走工具后也只留白（不再铺满视口）",
               abs(canvas6._zoom / full_zoom6 - EDIT_FIT_RATIO) < 0.03,
               f"切走后 {canvas6._zoom:.4f}"
               f"（比值 {canvas6._zoom / full_zoom6:.3f}，期望 {EDIT_FIT_RATIO}）")
            dialog6._set_tool("deform")
            app.processEvents()

            # 点图放钉：吸附到最近网格顶点；同一顶点不重复放
            def cview(scene: QPointF) -> QPointF:
                return QPointF(canvas6.mapFromScene(scene))

            first6 = canvas6.pin_add(QPointF(120.0, 40.0))
            ok("变形：点图放图钉（吸附到最近网格顶点），返回下标 0",
               first6 == 0 and canvas6.pin_count() == 1
               and canvas6.pins_pending() is None,
               f"下标 {first6}，钉 {canvas6.pin_count()} 个")
            again6 = canvas6.pin_add(QPointF(120.5, 40.3))
            ok("变形：同一网格顶点再点一次不重复放钉（直接返回已有下标）",
               again6 == 0 and canvas6.pin_count() == 1, "")
            second6 = canvas6.pin_add(QPointF(60.0, 90.0))
            ok("变形：另一处再放第二个钉", second6 == 1 and canvas6.pin_count() == 2,
               f"钉 {canvas6.pin_count()} 个")

            dialog6.show()
            app.processEvents()
            ok("变形：图钉圆点与图钉一一对应（悬停/拖动看圆点大小）",
               len(canvas6._pin_dots) == 2
               and all(item.isVisible() for item in canvas6._pin_dots),
               f"圆点 {len(canvas6._pin_dots)} 个")

            pin6 = canvas6.pins()[0]
            ok("变形：悬停到图钉上命中（顶点上也能抓着），空白处不命中",
               canvas6._hit_pin(cview(pin6[1])) == 0
               and canvas6._hit_pin(cview(QPointF(5.0, 5.0))) is None,
               f"hit={canvas6._hit_pin(cview(pin6[1]))}")

            view6 = cview(pin6[1])
            canvas6.mousePressEvent(mouse_event("press", view6))
            ok("变形：按下图钉进入拖动状态（不是移动整幅）",
               canvas6._mode == ("deform", 0), f"mode={canvas6._mode}")
            drag_to = cview(QPointF(150.0, 62.0))
            canvas6.mouseMoveEvent(mouse_event("move", drag_to))
            ok("变形：拖图钉即产生待应用形变 + 显示像素预览浮层",
               canvas6.pins_pending() is not None
               and canvas6._deform_item is not None, "")
            canvas6.mouseReleaseEvent(mouse_event("release", drag_to))
            ok("变形：松手后模式复位、预览保留（松手的是最终结果）",
               canvas6._mode is None and canvas6._deform_item is not None, "")

            # 拖动只改被抓的那个钉：另一个钉原地不动
            moved_pins = canvas6.pins()
            ok("变形：只有被拖的图钉动了，其余图钉原地不动",
               len(moved_pins) == 2
               and moved_pins[0][0] != moved_pins[1][0]
               and abs(moved_pins[1][1].x() - canvas6._mesh[0][moved_pins[1][0]][0])
               < 1e-6,
               f"钉位 {[(i, (round(p.x(), 1), round(p.y(), 1))) for i, p in moved_pins]}")

            home6, moved6, _tri6 = canvas6.pins_pending()
            ok("变形：待应用形变的网格确实动过（rest ≠ moved）",
               float(abs(moved6 - home6).max()) > 0.1,
               f"最大位移 {float(abs(moved6 - home6).max()):.2f}px")
            # 局部性：远场（离被抓图钉最远的一角）位移应为 0
            far_idx = int(min(range(len(home6)),
                              key=lambda i: -(home6[i, 0] ** 2 + home6[i, 1] ** 2)))
            far_shift = float(abs(moved6[far_idx] - home6[far_idx]).max())
            ok("变形：远场网格顶点位移为 0（ARAP 局部形变 + 边框锚点）",
               far_shift <= 1e-6, f"最远角位移 {far_shift:.2e}px")

            # 预览分辨率规则（纯函数钉死）：清晰度与成本取小
            span = 4000 * 3000
            ok("变形：预览分辨率 = min(屏幕清晰度, 成本上限)",
               cage_preview_scale(100, 100, 1.0, 200_000) == 1.0
               and cage_preview_scale(400, 400, 0.1, 200_000) == 0.1
               and abs(cage_preview_scale(4000, 3000, 0.36, DEFORM_PREVIEW_PIXELS)
                       - (DEFORM_PREVIEW_PIXELS / span) ** 0.5) < 1e-9
               and abs(cage_preview_scale(4000, 3000, 1.0,
                                          DEFORM_PREVIEW_SETTLE_PIXELS)
                       - (DEFORM_PREVIEW_SETTLE_PIXELS / span) ** 0.5) < 1e-9,
               f"整页拖动={cage_preview_scale(4000, 3000, 0.36, DEFORM_PREVIEW_PIXELS):.3f} "
               f"松手={cage_preview_scale(4000, 3000, 1.0, DEFORM_PREVIEW_SETTLE_PIXELS):.3f}")

            # 应用：内容跟着图钉走、远处不动、压一个撤销点、图钉留在原地
            snapshot6 = canvas6.image.copy()
            pins_before6 = [(i, (p.x(), p.y())) for i, p in canvas6.pins()]
            undo_before6 = len(dialog6._undo)
            dialog6._commit_deform()
            baked6 = dialog6.canvas.image
            inside_changed = any(
                baked6.pixelColor(x, y).rgba() != snapshot6.pixelColor(x, y).rgba()
                for y in range(0, 120, 2) for x in range(0, 200, 2))
            ok("变形：应用后图钉附近像素真的变了、尺寸不变",
               inside_changed and baked6.size() == snapshot6.size(),
               f"有变化={inside_changed}")
            # 离图钉足够远的地方（与边框锚点一并）逐字节不动
            far6 = [(5, 5), (5, 115), (196, 116), (5, 60)]
            far_same6 = all(baked6.pixelColor(x, y).rgba()
                            == snapshot6.pixelColor(x, y).rgba()
                            for x, y in far6)
            ok("变形：远场（含图角锚点那一带）逐字节不动", far_same6,
               f"远场 {len(far6)} 点全同={far_same6}")
            ok("变形：应用压一个撤销点、待应用状态清掉",
               len(dialog6._undo) == undo_before6 + 1
               and dialog6.canvas.pins_pending() is None,
               f"undo={len(dialog6._undo)} before={undo_before6}")
            ok("变形：应用后图钉留在原地（接着微调同一块，不用重新钉）",
               [i for i, _p in dialog6.canvas.pins()]
               == [i for i, _p in pins_before6]
               and len(dialog6.canvas.pins()) == 2,
               f"钉 {[(i, (round(p.x(), 1), round(p.y(), 1))) for i, p in dialog6.canvas.pins()]}")
            dialog6._undo_now()
            ok("变形：撤销回到形变前（整图逐字节一致）",
               all(dialog6.canvas.image.pixelColor(x, y).rgba()
                   == snapshot6.pixelColor(x, y).rgba()
                   for y in range(0, 120, 2) for x in range(0, 200, 2)),
               f"undo={len(dialog6._undo)}")

            # 「重置」：清空图钉、丢掉未应用的形变
            canvas6.pin_add(QPointF(120.0, 40.0))
            canvas6.pin_move(0, QPointF(150.0, 60.0))
            ok("变形：拖过的图钉产生待应用形变", canvas6.pins_pending() is not None,
               f"钉 {canvas6.pin_count()} 个")
            canvas6.reset_pins()
            ok("变形：「重置」丢掉未应用的形变并清空图钉",
               canvas6.pins_pending() is None and canvas6.pin_count() == 0, "")

            # Alt+点 / 右键删图钉
            canvas6.pin_add(QPointF(120.0, 40.0))
            canvas6.pin_add(QPointF(60.0, 90.0))
            ok("变形：放两个钉准备删除", canvas6.pin_count() == 2, "")
            del_view = cview(canvas6.pins()[0][1])
            canvas6.mousePressEvent(mouse_event(
                "press", del_view, button=Qt.MouseButton.RightButton))
            ok("变形：右键点图钉即删除（不用先切换模式）",
               canvas6.pin_count() == 1, f"剩 {canvas6.pin_count()} 个")

            # 切走工具自动烘焙（与变换、文字同款口径：不留"未落地"的编辑）
            canvas6.pin_move(0, QPointF(90.0, 100.0))
            snapshot6b = dialog6.canvas.image.copy()
            undo_before6c = len(dialog6._undo)
            dialog6._set_tool("crop")
            baked6b = dialog6.canvas.image
            ok("变形：切走工具自动烘焙未应用的形变（压撤销点、像素真的变了）",
               len(dialog6._undo) == undo_before6c + 1
               and dialog6.canvas._tool == "crop"
               and any(baked6b.pixelColor(x, y).rgba()
                       != snapshot6b.pixelColor(x, y).rgba()
                       for y in range(0, 120, 2) for x in range(0, 200, 2)),
               f"undo={len(dialog6._undo)} before={undo_before6c}")

            dialog6._escape()
            ok("变形：Esc 仍是原行为（关闭弹窗 = 放弃本次编辑）",
               not dialog6.isVisible(), "")
        finally:
            dialog6.deleteLater()
    finally:
        dialog.deleteLater()
    app.processEvents()

    # ---- 2c. 变换笼：GIMP 口径的「局部笼形变」（与操控变形并存的独立工具） ----
    gimg = make_image(200, 120)
    for x in range(60, 90):        # 会被笼扯动的黑块
        for y in range(20, 50):
            gimg.setPixel(x, y, 0xFF000000)
    dialog8 = ImageEditorDialog(None, gimg)
    try:
        canvas8 = dialog8.canvas
        dialog8._set_tool("cage")
        ok("变换笼：进入工具即建笼（贴图边、原位＝当前位置、无待应用形变）",
           canvas8._tool == "cage"
           and len(canvas8.cage()) == 4 * CAGE_DENSITY_DEFAULT
           and all(a == b for a, b in canvas8.cage())
           and canvas8.cage_pending() is None,
           f"把手 {len(canvas8.cage())} 个，pending="
           f"{canvas8.cage_pending() is not None}")

        from qfluentwidgets import ComboBox as _Combo8
        from qfluentwidgets import PushButton as _Push8

        texts8 = [b.text() for b in dialog8._option_page.findChildren(_Push8)]
        combos8 = dialog8._option_page.findChildren(_Combo8)
        ok("变换笼：选项行有「重置 / 应用形态」按钮与「把手密度」下拉",
           {"重置", "应用形态"} <= set(texts8)
           and len(combos8) == 1
           and combos8[0].count() == len(CAGE_DENSITY_CHOICES),
           f"按钮={texts8} 下拉项数={[c.count() for c in combos8]}")

        dialog8.show()
        app.processEvents()
        app.processEvents()
        ok("变换笼：把手圆点画出来（与把手一一对应且可见）",
           len(canvas8._cage_dots) == len(canvas8.cage())
           and all(item.isVisible() for item in canvas8._cage_dots), "")

        # 进「变换笼」时图片不铺满视口（把手要能往图外拖）。同「变形」：
        # "铺满"用临时 fit_ratio=1.0 量（resizeEvent 会覆盖显式 fit）。
        dialog8._set_tool("crop")
        app.processEvents()
        old_ratio8 = canvas8._fit_ratio
        canvas8.set_fit_ratio(1.0)
        app.processEvents()
        full_zoom8 = canvas8._zoom
        canvas8.set_fit_ratio(old_ratio8)
        dialog8._set_tool("cage")
        app.processEvents()
        ok("变换笼：进这个工具时图片不铺满视口（四周留出可操作空间）",
           full_zoom8 > 0
           and abs(canvas8._zoom / full_zoom8 - DEFORM_FIT_RATIO) < 0.03,
           f"铺满 {full_zoom8:.4f} → 留白 {canvas8._zoom:.4f}")
        dialog8._set_tool("crop")
        app.processEvents()
        ok("变换笼：切走工具后也只留白（不再铺满视口）",
           abs(canvas8._zoom / full_zoom8 - EDIT_FIT_RATIO) < 0.03,
           f"切走后 {canvas8._zoom:.4f}")
        dialog8._set_tool("cage")
        app.processEvents()

        # 改密度会重建笼 → 未应用的形变先落地、把手序号全变
        handles8 = canvas8.cage()
        canvas8.cage_move(0, QPointF(handles8[0][0].x() + 20,
                                     handles8[0][0].y() + 20))
        ok("变换笼：拖把手产生待应用形变",
           canvas8.cage_pending() is not None,
           f"pending={canvas8.cage_pending() is not None}")
        canvas8.reset_cage()
        ok("变换笼：「重置」把手回到原位、丢掉未应用形变",
           canvas8.cage_pending() is None
           and all(a == b for a, b in canvas8.cage()), "")
        canvas8.set_cage_density(3)
        ok("变换笼：改把手密度重建笼（每边 3 个 = 12 把手）",
           canvas8.cage_density() == 3 and len(canvas8.cage()) == 12,
           f"每边 {canvas8.cage_density()}，把手 {len(canvas8.cage())}")
        canvas8.set_cage_density(CAGE_DENSITY_DEFAULT)

        def cview8(scene: QPointF) -> QPointF:
            return QPointF(canvas8.mapFromScene(scene))

        # 悬停命中：把手处命中、空白处不命中
        first_handle8 = canvas8.cage()[0]
        ok("变换笼：悬停到把手上命中，空白处不命中",
           canvas8._hit_cage_handle(cview8(first_handle8[1])) == 0
           and canvas8._hit_cage_handle(cview8(QPointF(100.0, 60.0))) is None,
           f"hit={canvas8._hit_cage_handle(cview8(first_handle8[1]))}")

        # 拖一个角把手：只影响它附近、产生待应用形变 + 显示预览浮层
        corner8 = canvas8._hit_cage_handle(cview8(first_handle8[1]))
        view8 = cview8(first_handle8[1])
        canvas8.mousePressEvent(mouse_event("press", view8))
        ok("变换笼：按下把手进入拖动状态",
           canvas8._mode is not None and canvas8._mode[0] == "cage"
           and canvas8._mode[1] == corner8, f"mode={canvas8._mode}")
        drag_to8 = cview8(QPointF(first_handle8[1].x() + 25,
                                  first_handle8[1].y() + 25))
        canvas8.mouseMoveEvent(mouse_event("move", drag_to8))
        ok("变换笼：拖把手即产生待应用形变 + 显示像素预览浮层",
           canvas8.cage_pending() is not None
           and canvas8._cage_preview_item is not None, "")
        canvas8.mouseReleaseEvent(mouse_event("release", drag_to8))
        ok("变换笼：松手后模式复位、预览保留（松手的是最终结果）",
           canvas8._mode is None and canvas8._cage_preview_item is not None, "")

        src8, dst8 = canvas8.cage_pending()
        ok("变换笼：待应用形变的把手确实动过（原位 ≠ 当前位置）",
           any((a - b).manhattanLength() > 1e-6 for a, b in zip(src8, dst8)),
           f"位移 {[(round(b.x() - a.x(), 1), round(b.y() - a.y(), 1)) for a, b in zip(src8, dst8)]}")

        # 预览分辨率规则同 deform（纯函数钉死）
        ok("变换笼：预览分辨率 = min(屏幕清晰度, 成本上限)",
           cage_preview_scale(100, 100, 1.0, 200_000) == 1.0
           and cage_preview_scale(400, 400, 0.1, 200_000) == 0.1,
           f"{cage_preview_scale(100, 100, 1.0, 200_000)}")

        # 应用：局部内容跟着把手走、远处逐字节不动、压一个撤销点、把手留在原位
        snapshot8 = canvas8.image.copy()
        undo_before8 = len(dialog8._undo)
        dialog8._commit_cage()
        baked8 = dialog8.canvas.image
        changed8 = any(baked8.pixelColor(x, y).rgba()
                       != snapshot8.pixelColor(x, y).rgba()
                       for y in range(0, 120, 2) for x in range(0, 200, 2))
        ok("变换笼：应用后把手附近像素真的变了、尺寸不变",
           changed8 and baked8.size() == snapshot8.size(),
           f"有变化={changed8}")
        # RBF 紧支撑：影响半径外逐字节不动（拖的是左上角，右下角必然在半径外）
        far8 = [(195, 115), (195, 60), (100, 115), (190, 118)]
        far_same8 = all(baked8.pixelColor(x, y).rgba()
                        == snapshot8.pixelColor(x, y).rgba()
                        for x, y in far8)
        ok("变换笼：影响半径外逐字节不动（RBF 紧支撑的局部性）", far_same8,
           f"远场 {len(far8)} 点全同={far_same8}")
        ok("变换笼：应用压一个撤销点、待应用状态清掉",
           len(dialog8._undo) == undo_before8 + 1
           and dialog8.canvas.cage_pending() is None,
           f"undo={len(dialog8._undo)} before={undo_before8}")
        ok("变换笼：应用后把手回到贴图边原位（可接着拖第二次）",
           all(a == b for a, b in dialog8.canvas.cage()),
           f"把手 {[(round(a.x()), round(a.y())) for a, _b in dialog8.canvas.cage()][:2]}")
        dialog8._undo_now()
        ok("变换笼：撤销回到形变前（整图逐字节一致）",
           all(dialog8.canvas.image.pixelColor(x, y).rgba()
               == snapshot8.pixelColor(x, y).rgba()
               for y in range(0, 120, 2) for x in range(0, 200, 2)),
           f"undo={len(dialog8._undo)}")

        # 切走工具自动烘焙
        dialog8._set_tool("cage")
        c0 = dialog8.canvas.cage()[0][1]
        dialog8.canvas.cage_move(0, QPointF(c0.x() + 20, c0.y() + 20))
        snapshot8b = dialog8.canvas.image.copy()
        undo_before8c = len(dialog8._undo)
        dialog8._set_tool("crop")
        baked8b = dialog8.canvas.image
        ok("变换笼：切走工具自动烘焙未应用的形变（压撤销点、像素真的变了）",
           len(dialog8._undo) == undo_before8c + 1
           and dialog8.canvas._tool == "crop"
           and any(baked8b.pixelColor(x, y).rgba()
                   != snapshot8b.pixelColor(x, y).rgba()
                   for y in range(0, 120, 2) for x in range(0, 200, 2)),
           f"undo={len(dialog8._undo)} before={undo_before8c}")

        dialog8._escape()
        ok("变换笼：Esc 仍是原行为（关闭弹窗 = 放弃本次编辑）",
           not dialog8.isVisible(), "")
    finally:
        dialog8.deleteLater()
    app.processEvents()

    # ---- 重影回归（2026-10-02 用户报障）----
    # "拖动图片变化形态，图片变换了，但是原图片还是在背景上面"
    # 根因：形变预览是**局部浮层**（Z=4），底图仍是一整张原图；形变结果
    # 让开的位置，底图里的**旧像素透出来** → 看上去两张图叠着（重影）。
    # 修法：画浮层前把底图上**受影响框**挖空（不透明图填白、透明图填透明），
    # 预览清掉时回填。下面用两个工具各钉一遍"挖空确实发生/回填确实发生"。
    gimg = make_image(200, 120)            # 整幅浅灰，便于分辨"被挖空"的纯白
    for y in range(120):
        for x in range(200):
            gimg.setPixel(x, y, 0xFFE8E8E8)
    gdialog = ImageEditorDialog(None, gimg)
    try:
        gcanvas = gdialog.canvas
        # ---- 变换笼 ----
        gdialog._set_tool("cage")
        gh = gcanvas.cage()[0][1]           # 挑一个把手，拖一下产生形变
        gcanvas.cage_move(0, QPointF(gh.x() + 30, gh.y() + 20))
        gcanvas._refresh_cage_preview(force=True)
        box = gcanvas._preview_cutout
        ok("重影修复（笼）：预览时底图上确实挖了框",
           box is not None and not box.isEmpty(), f"cutout={box}")
        # 挖空框内应当是纯白（源图不透明 ⇒ 填白），而不是原来的浅灰
        cx, cy = box.center().x(), box.center().y()
        center = gcanvas._item.pixmap().toImage().pixelColor(int(cx), int(cy))
        ok("重影修复（笼）：挖空框内是纯白（旧像素不再透出）",
           (center.red(), center.green(), center.blue()) == (255, 255, 255),
           f"中心色 {center.red(), center.green(), center.blue()}")
        # grow 之后浮层被移到任意 origin，挖的是**整张原图**（不能只挖受影响
        # 小框：浮层没盖到而原图有旧像素的地方都会透出来，正是重影本身）。
        # 所以"框外"不存在——整幅底图都挖空了。
        ok("重影修复（笼）：挖空范围 = 整张原图（grow 后浮层可移到任意处）",
           box == QRect(0, 0, gimg.width(), gimg.height()),
           f"cutout={box} 原图={gimg.width()}x{gimg.height()}")
        # 清预览 → 回填：中心恢复浅灰（不留白洞）
        gcanvas._clear_cage_preview()
        restored = gcanvas._item.pixmap().toImage().pixelColor(int(cx), int(cy))
        ok("重影修复（笼）：清预览后底图回填（不留白洞）",
           (restored.red(), restored.green(), restored.blue()) == (232, 232, 232)
           and gcanvas._preview_cutout is None,
           f"回填色 {restored.red(), restored.green(), restored.blue()}")

        # ---- 变形（PS 操控变形）----
        gdialog._set_tool("deform")
        # 中间偏里放一个钉（pin_add 会吸附到最近网格顶点）
        gcanvas.pin_add(QPointF(100, 60))
        ok("重影修复（变形）：成功放上一个图钉（有未形变网格）",
           gcanvas.pin_count() == 1 and gcanvas._mesh is not None, "")
        gcanvas.pin_move(0, QPointF(120, 80))
        gcanvas._refresh_deform_preview(force=True)
        dbox = gcanvas._preview_cutout
        ok("重影修复（变形）：预览时底图上确实挖了框",
           dbox is not None and not dbox.isEmpty(), f"cutout={dbox}")
        dcx, dcy = dbox.center().x(), dbox.center().y()
        dcenter = gcanvas._item.pixmap().toImage().pixelColor(int(dcx), int(dcy))
        ok("重影修复（变形）：挖空框内是纯白（旧像素不再透出）",
           (dcenter.red(), dcenter.green(), dcenter.blue()) == (255, 255, 255),
           f"中心色 {dcenter.red(), dcenter.green(), dcenter.blue()}")
        gcanvas._clear_deform_preview()
        drestored = gcanvas._item.pixmap().toImage().pixelColor(int(dcx), int(dcy))
        ok("重影修复（变形）：清预览后底图回填（不留白洞）",
           (drestored.red(), drestored.green(), drestored.blue())
           == (232, 232, 232) and gcanvas._preview_cutout is None,
           f"回填色 {drestored.red(), drestored.green(), drestored.blue()}")

        # ---- 透明源图 ⇒ 挖成透明（而不是白块）----
        timg = QImage(120, 80, QImage.Format.Format_ARGB32)
        timg.fill(QColor(0, 0, 0, 0))          # 全透明底
        for y in range(40):                  # 上半不透明红
            for x in range(120):
                timg.setPixelColor(x, y, QColor(200, 30, 30, 255))
        tcanvas = EditorCanvas()
        tcanvas.set_image(timg)
        ok("重影修复：透明源图判定为『有透明像素』",
           tcanvas._has_alpha() is True, "")
        tcanvas._paint_canvas_cutout(QRect(0, 0, 120, 80))
        ta = tcanvas._item.pixmap().toImage().pixelColor(60, 20)
        ok("重影修复：透明源图挖空填透明（保持白底透明 PNG 不成白块）",
           ta.alpha() == 0, f"alpha={ta.alpha()}")
    finally:
        gdialog.deleteLater()
    app.processEvents()

    # ---- 校正：PS/摄影口径的「四点透视摆正」（独立入口） ----
    rimg = make_image(200, 120)
    for y in range(120):               # 一根倾斜的黑斜条
        x0 = int(20 + y * 0.5)
        for dx in range(6):
            if 0 <= x0 + dx < 200:
                rimg.setPixel(x0 + dx, y, 0xFF000000)
    dialog7 = ImageEditorDialog(None, rimg)
    try:
        canvas7 = dialog7.canvas
        dialog7._set_tool("rectify")
        quad7 = canvas7.quad()
        ok("校正：进入工具默认四角压在图片四角（≡ 没动过、无待应用校正）",
           canvas7._tool == "rectify"
           and [(round(p.x()), round(p.y())) for p in quad7]
           == [(0, 0), (200, 0), (200, 120), (0, 120)]
           and canvas7.quad_pending() is None,
           f"四角 {[(round(p.x()), round(p.y())) for p in quad7]}")

        from qfluentwidgets import ComboBox as _C7
        from qfluentwidgets import PushButton as _P7

        texts7 = [b.text() for b in dialog7._option_page.findChildren(_P7)]
        combos7 = dialog7._option_page.findChildren(_C7)
        ok("校正：选项行有「重置 / 应用校正」按钮与「目标尺寸」下拉",
           {"重置", "应用校正"} <= set(texts7)
           and len(combos7) == 1
           and combos7[0].count() == len(RECTIFY_RATIO_CHOICES),
           f"按钮={texts7} 下拉项数={[c.count() for c in combos7]}")

        dialog7.show()
        app.processEvents()
        app.processEvents()
        ok("校正：四角手柄画出来（4 个方块角点可见）",
           len(canvas7._rect_dots) == 4
           and all(item.isVisible() for item in canvas7._rect_dots), "")

        def cview7(scene: QPointF) -> QPointF:
            return QPointF(canvas7.mapFromScene(scene))

        corner7 = cview7(QPointF(200, 0))
        ok("校正：悬停到角点命中，空白处不命中",
           canvas7._hit_quad(corner7) == 1
           and canvas7._hit_quad(cview7(QPointF(100, 60))) is None,
           f"hit={canvas7._hit_quad(corner7)}")
        canvas7.mousePressEvent(mouse_event("press", corner7))
        ok("校正：按下角点进入拖动状态",
           canvas7._mode == ("rect", 1), f"mode={canvas7._mode}")
        drag7 = cview7(QPointF(190, 24))
        canvas7.mouseMoveEvent(mouse_event("move", drag7))
        ok("校正：拖角点即产生待应用校正 + 显示预览浮层",
           canvas7.quad_pending() is not None
           and canvas7._deform_item is not None, "")
        canvas7.mouseReleaseEvent(mouse_event("release", drag7))
        ok("校正：松手后模式复位、预览保留",
           canvas7._mode is None and canvas7._deform_item is not None, "")
        pending7 = canvas7.quad_pending()
        ok("校正：待应用校正 = 四角坐标 + 目标口径",
           pending7 is not None and len(pending7[0]) == 4
           and pending7[1] == RECTIFY_RATIO_DEFAULT,
           f"pending={pending7}")

        # 拖到图外（往外扩）允许
        canvas7.quad_move(0, QPointF(-30.0, -20.0))
        outside7 = canvas7.quad()[0]
        ok("校正：角点能拖到图片外面（把拍进来的桌面也框进去）",
           outside7.x() < 0 and outside7.y() < 0, "")
        canvas7.reset_quad()
        ok("校正：「重置」把四角拉回图片四角并丢掉未应用校正",
           canvas7.quad_pending() is None
           and [(round(p.x()), round(p.y())) for p in canvas7.quad()]
           == [(0, 0), (200, 0), (200, 120), (0, 120)], "")

        # 应用：整图被替换成摆正图（尺寸变），压一个撤销点，四角回新图四角
        canvas7.quad_move(0, QPointF(10.0, 5.0))
        canvas7.quad_move(1, QPointF(75.0, 5.0))
        canvas7.quad_move(2, QPointF(145.0, 118.0))
        canvas7.quad_move(3, QPointF(80.0, 118.0))
        size_before7 = (canvas7.image.width(), canvas7.image.height())
        undo_before7 = len(dialog7._undo)
        dialog7._commit_rectify()
        baked7 = dialog7.canvas.image
        ok("校正：应用后整图被替换成摆正图（尺寸变为目标矩形）",
           (baked7.width(), baked7.height()) != size_before7
           and baked7.width() > 0 and baked7.height() > 0,
           f"{size_before7} → ({baked7.width()}, {baked7.height()})")
        ok("校正：应用压一个撤销点、待应用状态清掉",
           len(dialog7._undo) == undo_before7 + 1
           and dialog7.canvas.quad_pending() is None,
           f"undo={len(dialog7._undo)} before={undo_before7}")
        ok("校正：应用后四角回到新图四角（可接着校第二次）",
           [(round(p.x()), round(p.y())) for p in dialog7.canvas.quad()]
           == [(0, 0), (baked7.width(), 0),
               (baked7.width(), baked7.height()), (0, baked7.height())],
           f"四角 {[(round(p.x()), round(p.y())) for p in dialog7.canvas.quad()]}")
        dialog7._undo_now()
        ok("校正：撤销回到校正前（尺寸与像素都还原）",
           (dialog7.canvas.image.width(), dialog7.canvas.image.height())
           == size_before7,
           f"undo 后 {dialog7.canvas.image.width()}×{dialog7.canvas.image.height()}")

        # 切走工具自动烘焙
        canvas7.quad_move(1, QPointF(190.0, 20.0))
        undo_before7b = len(dialog7._undo)
        dialog7._set_tool("crop")
        ok("校正：切走工具自动烘焙未应用的校正（压撤销点）",
           len(dialog7._undo) == undo_before7b + 1
           and dialog7.canvas._tool == "crop",
           f"undo={len(dialog7._undo)} before={undo_before7b}")
    finally:
        dialog7.deleteLater()
    app.processEvents()

    # ---- 7/8. 预览弹窗接线 ----
    from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

    zoom = ImageZoomDialog(None)
    try:
        ok("预览弹窗：工具条上有「编辑」按钮",
           getattr(zoom, "edit_btn", None) is not None, "")
        # 期望 1360 宽（一行摆得下缩放/朝向/翻页/打印/下载/编辑），但落地尺寸
        # 会先被夹进屏幕可用区域——按同一个公式算期望值，别写死 1280。
        from desktop.components.viewers.image_zoom_dialog import ZOOM_DIALOG_SIZE
        from desktop.ui.window_size import (
            FRAME_ALLOWANCE, FIT_RATIO, available_area,
        )

        zoom_area = available_area(zoom)
        zoom_w = min(ZOOM_DIALOG_SIZE.width(),
                     int((zoom_area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        ok("预览弹窗：宽度取满（理想 1360，超出屏幕时夹进可用区域）",
           zoom.width() == zoom_w and zoom.width() <= zoom_area.width(),
           f"width={zoom.width()} 期望={zoom_w} 可用区={zoom_area.width()}")
        ok("预览弹窗：无图时编辑按钮禁用", not zoom.edit_btn.isEnabled(), "")
        zoom.canvas.set_image(make_image(64, 48))
        zoom._sync_controls()
        ok("预览弹窗：有图时编辑按钮可用", zoom.edit_btn.isEnabled(), "")
        source = zoom.canvas.export_image()
        editor = zoom._open_editor(source)
        ok("预览弹窗：_open_editor 拿到画布整图",
           editor is not None
           and editor.canvas.image.width() == source.width()
           and editor.canvas.image.height() == source.height(), "")
        ok("预览弹窗：编辑器以弹窗为父（生命周期跟随）",
           editor.parent() is zoom, "")
        editor.deleteLater()

        # 编辑结果写回：set_image 通道替换画布图（_edit_image 内同款调用）
        edited = make_image(30, 20)
        zoom.canvas.set_image(edited)
        ok("预览弹窗：编辑结果写回后画布就是新图",
           zoom.canvas.export_image().width() == 30, "")
        zoom._sync_controls()
    finally:
        zoom.deleteLater()
        zoom.shutdown_workers()
    app.processEvents()

    # ---- 崩溃守卫（2026-10-02）：后台烘焙线程的异常/取消/收尾 ----
    # 这几条守的都是用户报过的"程序崩溃 / 点了没反应"，且都**实测复现过**。
    from PySide6.QtCore import QPointF as _QPointF
    from desktop.components.viewers.image_editor import (
        ImageEditorDialog as _Ed, _BakeWorker, run_with_progress)

    def _drain(w):
        from PySide6.QtWidgets import QApplication as _QA
        while not w.wait(20):
            _QA.processEvents()

    # 1. worker 里抛的异常必须被**捕获**（原来它逃出 QThread.run，
    #    result 停在 None、cancelled 是 False，被上层当成"用户取消"）
    def _boom(_params, _progress):
        raise MemoryError("模拟大图内存不足")

    w = _BakeWorker(_boom, {})
    w.start()
    _drain(w)
    ok("崩溃守卫：worker 捕获工作函数异常（不是让它逃出 QThread.run）",
       isinstance(w.error, MemoryError),
       f"→ error={type(w.error).__name__ if w.error else None}")
    ok("崩溃守卫：异常时线程正常结束（不留孤儿）", w.isFinished(), "")

    # 2. run_with_progress 必须**重抛**，让上层能区分"失败"与"用户取消"
    host = _Ed()
    try:
        run_with_progress(host, "t", "l", _boom, {})
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", False, "没有抛")
    except MemoryError:
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", True, "")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", False,
           f"抛了别的 {type(exc).__name__}")

    # 3. 正常完成仍要拿到结果（别被收尾的 cancel() 误标成"取消"）
    ok("崩溃守卫：正常完成返回结果（收尾 cancel 不污染语义）",
       run_with_progress(host, "t", "l",
                         lambda p, pr: (pr(1, 2), "结果图")[1], {}) == "结果图", "")

    # 4. progress 的取消信号：工作函数要能看见
    wc = _BakeWorker(lambda p, pr: None, {})
    a1 = wc.progress(1, 10)
    wc.cancelled = True
    a2 = wc.progress(2, 10)
    wc.cancelled = False
    ok("崩溃守卫：progress 取消信号（未取消 True / 取消 False）",
       a1 is True and a2 is False, f"→ {a1}, {a2}")

    # 5. closeEvent 存在且关窗不炸（缺它 ⇒ 线程在飞时析构 ⇒
    #    QThread: Destroyed while thread is still running ⇒ abort）
    ok("崩溃守卫：编辑器有 closeEvent（关窗时收尾在飞线程）",
       hasattr(_Ed, "closeEvent"), "")
    try:
        host.close()
        ok("崩溃守卫：关窗正常（不 abort）", True, "")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：关窗正常（不 abort）", False, repr(exc))

    # 6. 「完成」整体防重入（三个 busy 标志只挡同名方法，挡不住整体重入）
    ed2 = _Ed()
    calls = []
    for name in ("_commit_rectify", "_commit_deform", "_commit_cage",
                 "_commit_transform", "_commit_text_blocks"):
        setattr(ed2, name, (lambda n: lambda: calls.append(n))(name))
    ed2._finish()
    first = list(calls)
    ed2._finishing = True            # 模拟烘焙中 processEvents 派发第二次点击
    ed2._finish()
    ok("崩溃守卫：双击「完成」不重入（_finishing 挡住）",
       calls == first, f"→ 实际 {len(calls)} 次调用")
    ed2._finishing = False
    ed2.deleteLater()

    # 7. 校正退化**不污染撤销栈**（rectify_qimage 对退化抛 ValueError，
    #    原来异常逸出、压入的撤销点永不弹出 ⇒ Ctrl+Z 撤销空操作）
    img_deg = make_image(120, 90)
    ed3 = _Ed(image=img_deg)
    ed3.canvas.set_tool("rectify")
    for i, pt in enumerate([(0., 0.), (120., 0.), (120., 0.), (0., 0.)]):
        ed3.canvas.quad_move(i, _QPointF(pt[0], pt[1]))
    before_undo = len(ed3._undo)
    try:
        ed3._commit_rectify()
        ok("崩溃守卫：校正退化不抛异常（ValueError 被接住）", True, "")
        ok("崩溃守卫：校正退化不污染撤销栈（Ctrl+Z 不撤销空操作）",
           len(ed3._undo) == before_undo,
           f"→ {before_undo} → {len(ed3._undo)}")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：校正退化不抛异常（ValueError 被接住）", False,
           f"抛了 {type(exc).__name__}: {exc}")
    ed3.deleteLater()
    host.deleteLater()
    app.processEvents()
