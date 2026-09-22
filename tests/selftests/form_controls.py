# -*- coding: utf-8 -*-
"""表单控件高度与联动自测：CONTROL_HEIGHT 对齐、pdf_name↔title_text 联动。

背景：qfluentwidgets 的 ``ComboBox`` 继承 QPushButton、默认 27px，比同列
``LineEdit``（固定 33px）矮一截，必须由 ``desktop.ui.widgets.combo_box()``
统一抬到 ``CONTROL_HEIGHT``。注：LineEdit 在构造里就 setFixedHeight，不
show 也能取到真实高度；裸 ComboBox 没有固定高度，未布局时 height() 返回
480（默认窗口高）——写断言别拿它当基准。
"""

NAME = "form_controls"
DEPENDS: list[str] = ["tasklist"]
TITLE = "表单控件高度"


def run(ctx) -> None:
    from qfluentwidgets import ComboBox as _QFComboBox, LineEdit as _QFLineEdit
    from qfluentwidgets import PrimaryPushButton as _PrimaryPushButton

    from desktop.ui.widgets import CONTROL_HEIGHT
    from desktop.components.panels.print_nodes import NodeListWidget
    from tests.selftests._context import ok

    d, w = ctx.d, ctx.w

    base_h = _QFLineEdit().height()
    ok("CONTROL_HEIGHT 与 qfluentwidgets 输入框实际高度一致",
       CONTROL_HEIGHT == base_h, f"常量 {CONTROL_HEIGHT} / 实测 {base_h}")

    panels = [d.control_stack.widget(i) for i in range(d.control_stack.count())]
    combos = [(p.stage, wdg) for p in panels for wdg in p.findChildren(_QFComboBox)]
    # print 面板原有「纸张尺寸/纸张方向/位置/文字方向×2」共 6 个下拉；
    # 标题与页码的「位置」「文字方向」已删除（固定为上/下 + 竖排，
    # 见 PrintFormMixin.FIXED_TEXT_LAYOUT），后来又加了「标题字体 / 页码字体」
    # 两个（字体不再写死仿宋，见 desktop.services.font_catalog）与「页码样式」
    # 一个（中文/阿拉伯/干支），所以现在是 5 个。
    # 下限取 4（= 各面板至少还有自己的下拉），同时精确钉住 print 面板的数量。
    ok("阶段面板内存在下拉框", len(combos) >= 4, f"实际 {len(combos)} 个")
    _print_combos = [wdg for stage, wdg in combos if stage == "print"]
    ok("print 面板只有纸张/字体/页码样式五个下拉（位置/文字方向已删除）",
       len(_print_combos) == 5,
       f"实际 {len(_print_combos)} 个：{[c.currentText() for c in _print_combos]}")
    tall_wrong = {f"{s}:{wdg.currentText()}": wdg.height() for s, wdg in combos
                  if wdg.height() != base_h}
    ok("面板下拉框与同列输入框等高", not tall_wrong, f"偏离：{tall_wrong}")
    ok("执行记录下拉与输入框等高",
       d.history_combo.height() == base_h, f"实测 {d.history_combo.height()}")

    # detect 面板没有表单字段、只有一颗主按钮，同样不该是 qfluent 默认的 27px
    _detect_btn = panels[1].findChild(_PrimaryPushButton)
    ok("检测面板主按钮与表单控件等高",
       _detect_btn is not None and _detect_btn.height() == CONTROL_HEIGHT,
       f"实测 {_detect_btn.height() if _detect_btn else 'None'}")

    # 标题切换节点行：页码 + 标题 + 侧别 + 删除按钮挤在一行，更需同高。
    # 用独立探针而非真实面板：add_row 会发 changed 信号，避免污染后续
    # print 面板的「是否已改动」相关断言。
    _probe = NodeListWidget()
    _row = _probe.add_row(1, "占位标题", "left")
    node_wrong = {name: getattr(_row, name).height()
                  for name in ("side_combo", "page_spin", "title_edit")
                  if getattr(_row, name).height() != base_h}
    ok("节点行内表单控件等高", not node_wrong, f"偏离：{node_wrong}")

    # 第四步默认 PDF 名/古籍名随源 PDF（古籍样例.pdf）派生
    _pp = d.control_stack.widget(3)
    ok("默认 PDF 名取源 PDF 名加[重制]",
       _pp.pdf_name.text() == "古籍样例[重制].pdf", _pp.pdf_name.text())
    ok("默认古籍名称取源 PDF 名",
       _pp.title_text.text() == "古籍样例", _pp.title_text.text())
    ok("默认参数收集含派生 PDF 名",
       _pp.get_args()["pdf_name"] == "古籍样例[重制].pdf"
       and _pp.get_args()["title_text"] == "古籍样例")
    _pp.pdf_name.setText("自定义.pdf")
    _pp.title_text.setText("自定义书名")
    _pp.reset_to_default()
    ok("恢复默认仍按源 PDF 名派生",
       _pp.pdf_name.text() == "古籍样例[重制].pdf"
       and _pp.title_text.text() == "古籍样例")
    # title_text ↔ pdf_name 联动测试
    ok("初始为自动态", _pp._pdf_name_auto is True)
    _pp.title_text.setText("红楼梦")
    _pp._on_title_text_edited("红楼梦")
    ok("编辑 title_text 时 pdf_name 联动更新",
       _pp.pdf_name.text() == "红楼梦[重制].pdf", _pp.pdf_name.text())
    ok("联动后仍为自动态", _pp._pdf_name_auto is True)
    _pp.pdf_name.setText("xxx.pdf")
    _pp._refresh_pdf_name_auto()  # 模拟用户直接改 pdf_name 后的状态
    ok("用户直接改 pdf_name 后联动解除", _pp._pdf_name_auto is False)
    _pp.title_text.setText("不再联动")
    _pp._on_title_text_edited("不再联动")
    ok("联动解除后改 title_text 不再影响 pdf_name",
       _pp.pdf_name.text() == "xxx.pdf", _pp.pdf_name.text())
    _pp.reset_to_default()
    ok("恢复默认后联动重新建立",
       _pp._pdf_name_auto is True
       and _pp.pdf_name.text() == "古籍样例[重制].pdf"
       and _pp.title_text.text() == "古籍样例")
