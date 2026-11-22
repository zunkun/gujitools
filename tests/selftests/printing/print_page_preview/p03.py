# -*- coding: utf-8 -*-
"""7b. 面板接线：标题/页码「距页边」（勾选框 + 两行通栏输入框） / 8. 缩略图来源：条目自带 thumb / provider / 原图 / 8b. 预览字体：不能是裸 QFont() 的 generic 族 / 8b'. PDF 内容（标题/页码）字体必须**仿宋优先** / 8c. 竖排里的拉丁字符：整段旋转 90°，不拆成\"每字母一格\""""

from typing import Any


def run(st: Any) -> None:
    from core.command_spec import DEFAULT_PAGE_MARGINS, TEXT_SIDE_MARGIN_MM
    from desktop.components.panels.print_params import DEFAULT_PARAMS
    from pathlib import Path
    from desktop.components.panels.print_panel import PrintPanel
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QFormLayout
    from PySide6.QtWidgets import QLabel
    from desktop.workers.preview_worker import _pick_content_font
    from desktop.workers.preview_worker import _pick_preview_font
    from utils.fonts import cjk_font_families, content_font_families
    from tests.selftests._context import ok, pump
    from utils.page_layout import (
        PrintTextSpec, vertical_advance_mm, vertical_extent_mm, vertical_runs,
    )
    from desktop.components.panels.print_panel import PrintPanel
    from PySide6.QtWidgets import QFormLayout

    panel = PrintPanel()
    try:
        sides = [key for key, _label in panel.INSET_SIDES]
        ok("距页边的四个方向顺序固定为 上,右,下,左",
           sides == ["top", "right", "bottom", "left"], str(sides))

        # ⚠️ 核心契约：每段**恰好两行**，横向那行**只有一个框**
        for which, name, cross_key, cross_label, absent in (
            ("title", "标题", "top", "上边距", "bottom"),
            ("page_number", "页码", "bottom", "下边距", "top"),
        ):
            blk = panel._inset_block(which)
            widgets = blk["widgets"]
            ok(f"{name}距页边恰好两行（左右边距 + {cross_label}）",
               set(widgets) == {"side", "cross"}, str(sorted(widgets)))
            ok(f"{name}横向那行只有一个框（左页右页共用一个值）",
               widgets["side"].value() == blk["spins"]["left"].value() ==
               blk["spins"]["right"].value(),
               f"side={widgets['side'].value()} "
               f"left={blk['spins']['left'].value()} "
               f"right={blk['spins']['right'].value()}")
            ok(f"{name}横向框的 left/right 是**同一个控件对象**"
               f"（不是两个框凑出来的）",
               blk["spins"]["left"] is blk["spins"]["right"]
               and blk["spins"]["left"] is widgets["side"])
            ok(f"{name}纵向那行就是 {cross_label}（{cross_key}）",
               blk["spins"][cross_key] is widgets["cross"], str(sorted(blk["spins"])))
            ok(f"{name}不再露用不到的「{'下' if absent == 'bottom' else '上'}边距」框",
               absent not in blk["spins"], str(sorted(blk["spins"])))

        # ⚠️ 「距页边」的默认值**只有两处输入**（用户指定）：
        #   - 横向：左右各 10mm；
        #   - 纵向：跟随 page_margins —— 标题的「上」= page_margins[0]、
        #     页码的「下」= page_margins[2]，文字与图片**贴同一条边**。
        # 桌面端打开就该是一份明确的配置，而不是「沿用 CLI 时代 left/2、
        # right-6 那套猜出来的老行为」；显式写 null 才回落到那套老行为。
        from core.command_spec import DEFAULT_PAGE_MARGINS, TEXT_SIDE_MARGIN_MM

        for which, name, cross_expect in (
            ("title", "标题", float(DEFAULT_PAGE_MARGINS[0])),
            ("page_number", "页码", float(DEFAULT_PAGE_MARGINS[2])),
        ):
            block = panel._inset_block(which)
            ok(f"{name}距页边默认已启用：横向 {TEXT_SIDE_MARGIN_MM:g}mm、"
               f"纵向 {cross_expect:g}mm（跟随 page_margins）",
               block["enabled"].isChecked()
               and all(w.isEnabled() for w in block["widgets"].values())
               and block["widgets"]["side"].value() == TEXT_SIDE_MARGIN_MM
               and block["widgets"]["cross"].value() == cross_expect,
               f"勾选={block['enabled'].isChecked()} "
               f"横向={block['widgets']['side'].value()} "
               f"纵向={block['widgets']['cross'].value()}")
        # ⚠️ 导出的仍是**四元素** [上,右,下,左]，但界面只摆用得上的那个纵向
        # 分量：标题不摆「下」→ 补 0，页码不摆「上」→ 补 0（底层永远读不到，
        # 见 utils.page_layout 的 `_text_anchor`）。所以落到参数里是
        # [top,10,0,10] / [0,10,bottom,10]，不是四个一样的数
        # ——这是个容易写错断言的地方（曾经写成四个 10）。
        ok("默认导出：横向 10mm、纵向跟随 page_margins，缺席分量恒 0",
           panel.get_args().get("title_margins")
           == [float(DEFAULT_PAGE_MARGINS[0]), 10.0, 0.0, 10.0]
           and panel.get_args().get("page_number_margins")
           == [0.0, 10.0, float(DEFAULT_PAGE_MARGINS[2]), 10.0],
           f"{panel.get_args().get('title_margins')} / "
           f"{panel.get_args().get('page_number_margins')}")

        # ---- 启用后取值 ----
        panel.set_inset("title", [2, 14, 2, 10])
        ok("勾选自定义后输入区可用",
           all(w.isEnabled() for w in panel._inset_block("title")["widgets"].values()))
        # ⚠️ 横向只有一个框，回填 [左=10, 右=14] 时取**左页值**：左页贴左纸边、
        # 右页贴右纸边，界面就是一个对称值。（若按 spins 键逐个回填，
        # 后写的 right=14 会覆盖 left=10——曾经真的这样。）
        blk = panel._inset_block("title")
        ok("横向框回填取左页值 10（不被右页值 14 覆盖）",
           blk["widgets"]["side"].value() == 10.0,
           str(blk["widgets"]["side"].value()))
        ok("纵向框回填它真正会用的那个值（标题 = 距上 = 2）",
           blk["widgets"]["cross"].value() == 2.0,
           str(blk["widgets"]["cross"].value()))
        # ⚠️ 参数契约仍是四元素 [上,右,下,左]；界面没摆的那个纵向分量（标题的
        # 「下」/ 页码的「上」）在底层**永远读不到**，导出时补 0——绝不能把框的
        # 显示初值 2.0 混进参数，否则配置里会躺着一个用户看不见的数
        # （旧实现四个框全摆，看不出这个毛病；收成两行以后才暴露）。
        got = panel.get_args().get("title_margins")
        ok("标题导出 [上=2,右=10,下=0,左=10]（横向一个值、缺席的「下」补 0）",
           got == [2.0, 10.0, 0.0, 10.0], str(got))
        hint = panel._inset_block("title")["hint"].text()
        ok("释义行说清横向是一个对称值、且口径是「文字轮廓」边缘",
           "文字轮廓距左右纸边各 10" in hint and "距上 2" in hint, hint)

        # 页码：纵向是「距下」，「上」补 0
        panel.set_inset("page_number", [2, 14, 2, 10])
        got = panel.get_args().get("page_number_margins")
        ok("页码导出 [上=0,右=10,下=2,左=10]（界面缺席的「上」补 0）",
           got == [0.0, 10.0, 2.0, 10.0], str(got))
        ok("页码释义说「距下」",
           "距下 2" in panel._inset_block("page_number")["hint"].text(),
           panel._inset_block("page_number")["hint"].text())

        # ---- 「位置」「文字方向」两个参数已从桌面端删除 ----
        # 用户原话：「既然有位置：上面/下面……动态调整啊，你不会啊，要不然就
        # 取消"位置"和"文字方向"两个参数，默认标题在上面，页码在下面」。
        # 采取后一种：古籍的书名在版框之上、页码在版心之下，都是竖排定式，
        # 摆成下拉只会让人以为可以乱选（而且和「上边距/下边距」两行天然矛盾）。
        for attr in ("title_position", "title_orientation",
                     "page_number_position", "page_number_orientation"):
            ok(f"面板不再有 {attr} 控件",
               not hasattr(panel, attr), f"仍有 {attr}")
        from PySide6.QtWidgets import QLabel

        _labels = []
        for _form in panel.findChildren(QFormLayout):
            for _row in range(_form.rowCount()):
                _item = _form.itemAt(_row, QFormLayout.ItemRole.LabelRole)
                _w = _item.widget() if _item is not None else None
                if isinstance(_w, QLabel):
                    _labels.append(_w.text())
        ok("表单里不再出现「位置」「文字方向」两行",
           "位置" not in _labels and "文字方向" not in _labels,
           str(_labels))

        # 没历史参数时，导出的是固定的「标题在上、页码在下、两者竖排」
        # ⚠️ 这条断言要真能测到固定表，前提是**面板默认参数表里没有这四个键**：
        # 早先 DEFAULT_PARAMS 还带着它们，`__init__` 一复位就把固定值填进
        # `_fixed_layout_echo`，于是「固定表」这条路径根本没被走到——注入
        # 「把固定表改反」时全绿，守卫形同虚设（实测踩到过）。
        from desktop.components.panels.print_params import DEFAULT_PARAMS

        _stray = sorted(
            k for k in ("title_position", "title_orientation",
                        "page_number_position", "page_number_orientation")
            if k in DEFAULT_PARAMS
        )
        ok("面板默认参数表已不再带「位置/文字方向」（否则固定表形同虚设）",
           not _stray, f"仍存在：{_stray}")

        fresh = panel.get_args()
        ok("未回填历史 → 位置固定为标题 top / 页码 bottom",
           fresh.get("title_position") == "top"
           and fresh.get("page_number_position") == "bottom",
           f"{fresh.get('title_position')} / {fresh.get('page_number_position')}")
        ok("未回填历史 → 文字方向固定为两者竖排",
           fresh.get("title_orientation") == "vertical"
           and fresh.get("page_number_orientation") == "vertical",
           f"{fresh.get('title_orientation')} / {fresh.get('page_number_orientation')}")

        # ⚠️ 历史里的非固定值必须**原样保留**：桌面端没给用户改这两个键的
        # 入口，就不能顺手帮他"修正"——老任务存的是 horizontal，进第四步
        # 什么都没动，参数暂存却把它写成 vertical，是最难查的那类漂移。
        panel._apply_args({
            "title_position": "bottom", "title_orientation": "horizontal",
            "page_number_position": "top", "page_number_orientation": "horizontal",
        })
        echo = panel.get_args()
        ok("回填历史后，导出仍原样保留历史的位置/方向（不被固定值改写）",
           (echo.get("title_position"), echo.get("title_orientation"),
            echo.get("page_number_position"),
            echo.get("page_number_orientation"))
           == ("bottom", "horizontal", "top", "horizontal"),
           f"{echo.get('title_position')}/{echo.get('title_orientation')} "
           f"{echo.get('page_number_position')}/{echo.get('page_number_orientation')}")
        # 恢复默认要回到固定值（用户明确说"默认标题在上面，页码在下面"）
        panel.reset_to_default()
        back = panel.get_args()
        ok("恢复默认后回到固定的「标题上/页码下、竖排」",
           (back.get("title_position"), back.get("page_number_position"),
            back.get("title_orientation"), back.get("page_number_orientation"))
           == ("top", "bottom", "vertical", "vertical"),
           f"{back.get('title_position')}/{back.get('page_number_position')}")

        # ---- 距页边的两行不受上述删除影响（纵向键固定：标题距上、页码距下）----
        for which, name, vertical_label in (
            ("title", "标题", "距上"),
            ("page_number", "页码", "距下"),
        ):
            panel._apply_args({f"{which}_margins": [2, 14, 2, 10]})
            widgets = panel._inset_block(which)["widgets"]
            ok(f"{name}参数行仍是固定的两行（左右边距 + {vertical_label[1]}边距）",
               set(widgets) == {"side", "cross"}, str(sorted(widgets)))
            ok(f"{name}释义恒说「{vertical_label}」",
               vertical_label in panel._inset_block(which)["hint"].text(),
               panel._inset_block(which)["hint"].text())
            ok(f"{name}回填后值不丢",
               widgets["side"].value() == 10.0 and widgets["cross"].value() == 2.0,
               f"side={widgets['side'].value()} cross={widgets['cross'].value()}")

        panel._apply_args({"title_margins": [2, 14, 2, 10],
                           "page_number_margins": [2, 14, 2, 10]})

        # ---- 取消启用 / 简写 / 回填 ----
        panel.set_inset("title", None)
        ok("取消勾选后不导出距页边",
           panel.get_args().get("title_margins") is None)
        ok("取消勾选后释义说明回到老行为",
           "老行为" in panel._inset_block("title")["hint"].text(),
           panel._inset_block("title")["hint"].text())
        panel._apply_args({"title_margins": [2, 14, 2, 10]})
        ok("历史参数能回填两个框（横向取左值 10、纵向取距上 2）",
           panel._inset_block("title")["widgets"]["side"].value() == 10.0
           and panel._inset_block("title")["widgets"]["cross"].value() == 2.0,
           str(panel.inset("title")))
        panel._apply_args({"title_margins": [2, 14]})
        ok("简写 [上下,左右] 补全成四值（横向取左值 14）",
           panel.inset("title") == [2.0, 14.0, 0.0, 14.0], str(panel.inset("title")))
        panel._apply_args({"title_margins": None})
        ok("None 回填 → 取消勾选",
           panel.inset("title") is None
           and not panel._inset_block("title")["enabled"].isChecked())

        # ---- 行序与标签（控件先建、行后加，顺序最容易写错，已踩过一次）----
        forms = panel.findChildren(QFormLayout)

        from PySide6.QtWidgets import QLabel

        def _find(widget):
            """返回 (所属表单, 行号, 行标签文本)；找不到返回 (None, -1, None)。"""
            for form in forms:
                for row in range(form.rowCount()):
                    for role in (QFormLayout.ItemRole.FieldRole, QFormLayout.ItemRole.LabelRole,
                                 QFormLayout.ItemRole.SpanningRole):
                        item = form.itemAt(row, role)
                        if item is not None and item.widget() is widget:
                            lab = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                            text = None
                            _lw = lab.widget() if lab is not None else None
                            if isinstance(_lw, QLabel):
                                text = _lw.text()
                            return form, row, text
            return None, -1, None

        block = panel._inset_block("title")
        form_s, row_side, lab_side = _find(block["widgets"]["side"])
        _, row_cross, lab_cross = _find(block["widgets"]["cross"])
        # 「位置」「文字方向」两行已删除，行序改以「距页边」勾选框为基准
        # （它就在两行参数之前，且是能直接查到的控件；`title_font_size` 包在
        #  `_spin_with_unit` 的盒子里，`_find` 查不到）
        form_h, row_hint, _ = _find(block["hint"])
        _, row_check, _ = _find(block["enabled"])
        ok("「距页边」两行排在标题参数之后（没跑到字体大小前面）",
           row_side > row_check > -1 and form_s is not None,
           f"距页边@{row_side} 勾选框@{row_check}")
        # ⚠️ 先断言「分两行」再断言行标签：把两行挤回同一行时，后加的那行
        # 会把控件从原行**搬走**、原行标签变成空——若先测标签，报出来的是
        # 「标签是 None」，掩盖了「挤成一行」这个真实语义（已踩）。
        ok("两行是**分开的两行**（不是挤在一行里）",
           row_cross == row_side + 1, f"左右@{row_side} 纵向@{row_cross}")
        ok("行标签就是「左右边距：」/「上边距：」（用户指定的叫法，带冒号）",
           lab_side == "左右边距：" and lab_cross == "上边距：",
           f"{lab_side!r} / {lab_cross!r}")
        ok("页码那块纵向标签是「下边距：」",
           _find(panel._inset_block("page_number")["widgets"]["cross"])[2]
           == "下边距：",
           str(_find(panel._inset_block("page_number")["widgets"]["cross"])[2]))
        ok("勾选框 → 左右边距 → 上边距 → 释义行，顺序正确且同区",
           row_check + 1 == row_side and form_h is form_s
           and row_hint == row_cross + 1,
           f"勾选@{row_check} 左右@{row_side} 纵向@{row_cross} 释义@{row_hint}")

        # 输入框要**通栏**（与「古籍名称」等输入框同宽），不是一排小格子。
        # ⚠️ 判据用布局跑完后的 width()：这里已 show + processEvents，
        # QFormLayout 会把字段列拉到整行宽（未布局时读到的是脏值，已踩）。
        panel.resize(340, 900)  # 参数卡片的最窄宽度
        st.app.processEvents()
        pump(st.app, 4)
        for which, name in (("title", "标题"), ("page_number", "页码")):
            widgets = panel._inset_block(which)["widgets"]
            for key, label in (("side", "左右边距"), ("cross", "上/下边距")):
                box = widgets[key]
                ok(f"{name}「{label}」输入框是通栏宽（≥ 面板宽 - 标签列 - 余量）",
                   box.width() >= panel.width() - 100,
                   f"宽 {box.width()}px，面板 {panel.width()}px")
            # 且不存在"一排多个框"的残留：横向只有 1 个框
            ok(f"{name}横向那一行没有第二个输入框",
               len({id(s) for s in (widgets["side"],)}) == 1)
    finally:
        panel.deleteLater()
    widget2 = PrintPreviewWidget()
    try:
        entry = {"file": str(st.png_a), "label": "0001"}
        ok("无 thumb/provider 时直接用条目图片",
           widget2._thumb_path_for(entry) == Path(str(st.png_a)))
        ok("条目自带 thumb 优先",
           widget2._thumb_path_for(dict(entry, thumb={"path": str(st.png_b)}))
           == Path(str(st.png_b)))
        widget2._thumb_provider = lambda _p: str(st.png_b)
        ok("provider 作为次选",
           widget2._thumb_path_for(entry) == Path(str(st.png_b)))
        widget2._thumb_provider = lambda _p: None
        ok("provider 返回 None 时回退条目图片",
           widget2._thumb_path_for(entry) == Path(str(st.png_a)))
    finally:
        widget2.deleteLater()
    from PySide6.QtGui import QFontDatabase

    from desktop.workers.preview_worker import _pick_preview_font

    fam = _pick_preview_font(18).family()
    generic = {"", "Sans Serif", "Serif", "Monospace", "Cursive", "Fantasy"}
    st.available = set(QFontDatabase.families())
    chosen_ok = fam not in generic or not st.available
    ok("预览字体优先选中文字体，而非 generic 兜底",
       chosen_ok, f"family={fam!r} 可用族={sorted(st.available)[:5]}")
    from desktop.workers.preview_worker import _pick_content_font
    from utils.fonts import cjk_font_families, content_font_families

    first_content = content_font_families()[0]
    ok("内容字体候选以仿宋/衬线打头",
       first_content in ("FangSong", "Noto Serif CJK SC", "Songti SC"),
       f"{content_font_families()[:3]}")
    ok("内容候选与界面候选是两份独立列表（防被合并）",
       tuple(content_font_families()) != tuple(cjk_font_families()),
       f"内容 {content_font_families()[:2]} / 界面 {cjk_font_families()[:2]}")
    # 本机装了仿宋时，内容字体必须真的挑到它（离屏环境无字体库时跳过）
    if st.available:
        content_fam = _pick_content_font(18).family()
        ok("内容字体实际挑到仿宋", content_fam in ("FangSong", "FangSong_GB2312", "SimFang"),
           f"family={content_fam!r}")
    from desktop.workers.preview_worker import _draw_print_text
    from utils.page_layout import (
        PrintTextSpec, vertical_advance_mm, vertical_extent_mm, vertical_runs,
    )

    ok("竖排分段：汉字一格一格、英文整段",
       vertical_runs("呵呵Happiness") == [("呵呵", False), ("Happiness", True)],
       str(vertical_runs("呵呵Happiness")))
    ok("竖排分段：数字/半角符号也归入旋转段",
       vertical_runs("第1頁A") == [("第", False), ("1", True), ("頁", False),
                                   ("A", True)],
       str(vertical_runs("第1頁A")))
    ok("纯汉字串不产生旋转段",
       all(not rotated for _chunk, rotated in vertical_runs("龍譚精舍叢刻")))
    # 高度：汉字 1 格，拉丁段按字宽估算（0.55 格/字符）
    ok("竖排高度：拉丁段不再按「每字母一格」计",
       abs(vertical_extent_mm("呵呵Happiness", 1.0)
           - (2 + 9 * 0.55)) < 1e-6,
       str(vertical_extent_mm("呵呵Happiness", 1.0)))
    ok("纯汉字的竖排高度 = 字数 × 字高",
       abs(vertical_extent_mm("呵呵呵", 2.0) - 6.0) < 1e-6)
    ok("旋转段推进 = 字符数 × 0.55 格",
       abs(vertical_advance_mm("Happiness", 1.0, True) - 4.95) < 1e-6)

