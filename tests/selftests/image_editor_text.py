# -*- coding: utf-8 -*-
"""图片编辑弹窗·文字工具（就地编辑文字块）。

断言线：

1. **落点即编辑**：点画布生成文字块、开启就地编辑（文本交互）；
2. **焦点路由**（2026-10-01 回归"打字没效果"）：画布 NoFocus 时键盘输入
   必须经"视图 → 场景焦点项"到达文字块；
3. **拖动移动整块**：按住拖动超过阈值才移动（单击放光标不受影响）；
4. **写入图片**：「插入文字」把文字块画进图片、压一个撤销点、画布上的
   块清空；切走工具时未插入的非空块自动写入；**空块失焦自删**且不产生
   撤销点；
5. **字体下拉以中文字体为主**（西文只留几个常用、且全排在中文字体之后）；
6. **颜色是一个按钮**（色点 + 十六进制 + 下拉），常用色块收在它弹出的
   面板里，不再散在选项行上；
7. **回归"文字大小不生效"**（2026-10-01）：选项行控件抢走画布键盘焦点后，
   改字号/颜色仍必须作用在当前文字块上（样式走"当前样式块"而不是场景
   焦点项）；⚠️ 这条必须**真显示弹窗**（不显示时 ``setFocus`` 是空操作）；
8. **悬停虚线框**：悬停显示并框住块身、拖动时跟随、松手消失、离开隐藏；
   ⚠️ 按下/松手必须走 ``QTest``（合成 ``sendEvent`` 的 press/release
   场景不受理）。
"""

from __future__ import annotations

NAME = "image_editor_text"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·文字工具"


def run(ctx) -> None:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import canvas_img, is_dark, make_image

    from desktop.components.viewers.image_editor import (
        ImageEditorDialog, TextBlockItem,
    )

    app = ctx.app

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
    app.processEvents()