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

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    return image


def is_dark(color) -> bool:
    """足够深的像素（文字/黑笔刷落点，抗锯齿边缘不算）。"""
    return color.red() < 100 and color.green() < 100 and color.blue() < 100


def canvas_img(canvas):
    """取画布当前图（``canvas.image`` 声明为可空，但本文件用例都在有图态访问）。"""
    img = canvas.image
    assert img is not None  # 编辑过程中画布必有图
    return img


def run(ctx) -> None:
    import math

    from PySide6.QtCore import QPointF, QRect, QRectF, Qt
    from PySide6.QtGui import QColor, QImage

    from tests.selftests._context import ok

    from desktop.components.viewers.image_editor import (
        EDIT_FIT_RATIO, ERASER_DEFAULT,
        EditorCanvas, ImageEditorDialog, TextBlockItem, bake_transform,
        clamp_rect, draw_text, rotate_about, scale_about,
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
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120, "")

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
        assert area is not None  # 离屏环境下可用区域总能取到
        expect_w = min(EDITOR_SIZE.width(),
                       int((area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        expect_h = min(EDITOR_SIZE.height(),
                       int((area.height() - FRAME_ALLOWANCE.height()) * FIT_RATIO))
        ok("弹窗：默认开大（1440×940，超出屏幕时夹进可用区域）并带"
           "最小化/最大化/关闭按钮",
           dialog.width() == expect_w and dialog.height() == expect_h
           and dialog.width() <= area.width()
           and dialog.height() + FRAME_ALLOWANCE.height() <= area.height()
           and bool(dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint),
           f"size={dialog.width()}x{dialog.height()} 期望={expect_w}x{expect_h} "
           f"可用区={area.width()}x{area.height()} "
           f"flags={hex(int(dialog.windowFlags()))}")
        ok("弹窗：最小尺寸也被夹进可用区域（小屏上仍能拖到放得下）",
           dialog.minimumWidth() <= min(EDITOR_MIN_SIZE.width(), dialog.width())
           and dialog.minimumHeight() <= min(EDITOR_MIN_SIZE.height(), dialog.height()),
           f"min={dialog.minimumWidth()}x{dialog.minimumHeight()}")
        ok("工具栏：工具按钮是 ToggleButton（选中态有主色高亮），"
           "裁剪/变换/擦除/文字四个",
           all(type(dialog._tool_buttons[k]).__name__ == "ToggleButton"
               for k in dialog._tool_buttons)
           and set(dialog._tool_buttons) == {"crop", "transform", "erase",
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
        sel_sel = canvas.selection()
        assert sel_sel is not None  # 裁剪态必有选区
        sel_view = canvas.mapFromScene(sel_sel).boundingRect()
        vp = canvas.viewport().rect()
        ok("裁剪：适配选区后四周留白（选区约占 80% 视口，不顶边）",
           sel_view.width() < vp.width() and sel_view.height() < vp.height(),
           f"sel_view={sel_view.width():.0f}x{sel_view.height():.0f} "
           f"viewport={vp.width()}x{vp.height()}")

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
           f"page.y={dialog._option_page.y() if dialog._option_page else None} "
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
           canvas_img(dialog.canvas).width() == 100
           and canvas_img(dialog.canvas).height() == 120, "")
        ok("裁剪：应用（换图）后裁剪区重新默认全选新图",
           dialog.canvas.selection() == dialog.canvas.image_rect(),
           f"sel={dialog.canvas.selection()}")
        dialog._undo_now()
        ok("撤销：裁剪被完整回退",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120, "")
        dialog._redo_now()
        ok("重做：裁剪被重新应用", canvas_img(dialog.canvas).width() == 100, "")
        dialog._reset_all()
        ok("还原：回到打开时的图", canvas_img(dialog.canvas).width() == 200, "")
        dialog._undo_now()
        ok("还原本身可撤销：回到还原前的裁剪结果",
           canvas_img(dialog.canvas).width() == 100, "")

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
            wiped = canvas_img(dialog2.canvas).pixelColor(100, 60)
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
            burned = canvas_img(dialog3.canvas)
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
            _op3 = dialog3._option_page
            assert _op3 is not None  # 文字工具的选项行必然已建
            combo = _op3.findChild(ComboBox)
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

            picker = _op3.findChild(GujiColorPicker)
            ok("文字：选项行是一个颜色按钮（色点 + 十六进制 + 下拉）",
               picker is not None
               and picker.color().name() == dialog3._text_color,
               f"picker={picker}")
            assert picker is not None  # 上一条 ok 已断言颜色按钮存在
            ok("文字：常用色块不再散在选项行上（已搬进选择器面板）",
               _op3.findChildren(SwatchButton) == [], "")
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
            assert panel is not None  # 上一条 ok 已断言面板存在
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
            assert combo is not None  # 上一条 ok 已断言字体下拉存在
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

            _op3b = dialog3._option_page
            assert _op3b is not None  # 文字工具的选项行必然已建
            size_slider = _op3b.findChild(FluentSlider)
            ok("回归：字号滑杆是 NoFocus（拖动不抢画布焦点、光标不丢）",
               size_slider is not None
               and size_slider.focusPolicy() == Qt.FocusPolicy.NoFocus,
               f"policy={size_slider.focusPolicy() if size_slider else None}")
            assert size_slider is not None  # 上一条 ok 已断言滑杆存在
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
            _paint = canvas4._paint_image
            _base = canvas4._image
            assert _paint is not None and _base is not None  # 进入预览态后浮层/底图必有
            ok("变换：按下即进入实时预览（底图填白 + 浮层，真像素未动）",
               canvas4._mode is not None and canvas4._mode[0] == "xf_move"
               and canvas4._float_item is not None
               and _paint.pixelColor(160, 60).value() > 230
               and _base.pixelColor(160, 60).value() < 128,
               f"mode={canvas4._mode} "
               f"paint={_paint.pixelColor(160, 60).value()}")
            canvas4.mouseMoveEvent(mouse_event("move", vpos(QPointF(130, 60))))
            canvas4.mouseReleaseEvent(mouse_event(
                "release", vpos(QPointF(130, 60))))
            origin = canvas4._xf.map(QPointF(0, 0))
            ok("变换：框内拖动 = 平移（−30,0，视口取整容差 <1.5px）",
               (origin - QPointF(-30, 0)).manhattanLength() <= 1.5,
               f"origin={origin}")

            undo_before = len(dialog4._undo)
            dialog4._commit_transform()
            baked = canvas_img(canvas4)
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
            ok("变换：第一个动作就是拖轴心也能进拖动（先建预览，不炸断言）",
               canvas5._mode is not None and canvas5._mode[0] == "xf_pivot"
               and canvas5._xf_rect is not None, f"mode={canvas5._mode}")
            moved_view = vpos5(canvas5._xf.map(pivot_before)
                               + QPointF(20, 10))
            canvas5.mouseMoveEvent(mouse_event("move", moved_view))
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
        assert zoom_area is not None  # 离屏环境下可用区域总能取到
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
        assert source is not None  # 刚 set 过图，导出必有
        editor = zoom._open_editor(source)
        ok("预览弹窗：_open_editor 拿到画布整图",
           editor is not None
           and editor.canvas.image is not None
           and editor.canvas.image.width() == source.width()
           and editor.canvas.image.height() == source.height(), "")
        assert editor is not None  # 上一条 ok 已断言编辑器打开成功
        ok("预览弹窗：编辑器以弹窗为父（生命周期跟随）",
           editor.parent() is zoom, "")
        editor.deleteLater()

        # 编辑结果写回：set_image 通道替换画布图（_edit_image 内同款调用）
        edited = make_image(30, 20)
        zoom.canvas.set_image(edited)
        _written_back = zoom.canvas.export_image()
        assert _written_back is not None  # 刚 set 过图，导出必有
        ok("预览弹窗：编辑结果写回后画布就是新图",
           _written_back.width() == 30, "")
        zoom._sync_controls()
    finally:
        zoom.deleteLater()
        zoom.shutdown_workers()
    app.processEvents()

    # ---- 崩溃守卫（2026-10-02）：后台线程的异常/取消/收尾 ----
    # 这几条守的都是用户报过的"程序崩溃 / 点了没反应"，且都**实测复现过**。
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
    for name in ("_commit_transform", "_commit_text_blocks"):
        setattr(ed2, name, (lambda n: lambda: calls.append(n))(name))
    ed2._finish()
    first = list(calls)
    ed2._finishing = True            # 模拟烘焙中 processEvents 派发第二次点击
    ed2._finish()
    ok("崩溃守卫：双击「完成」不重入（_finishing 挡住）",
       calls == first, f"→ 实际 {len(calls)} 次调用")
    ed2._finishing = False
    ed2.deleteLater()

    host.deleteLater()
    app.processEvents()
