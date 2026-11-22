# -*- coding: utf-8 -*-
"""公共控件的尺寸/文本常量（自 ``desktop/ui/widgets.py`` 拆出）。"""

#: 表单控件统一高度（px）。
#:
#: qfluentwidgets 的 ``LineEdit`` 在构造里写死 ``setFixedHeight(33)``，
#: ``SafeSpinBox`` / ``SafeDoubleSpinBox`` / ``EditableComboBox`` 都继承它，所以
#: 表单输入类天然同高；而 ``ComboBox`` 继承的是 ``QPushButton``，没有这个
#: 约束，实测只有 27px——和同列的输入框并排会明显矮一截。新建下拉框一律
#: 走 ``combo_box()``，由它抬到本高度；``tests/gui_selftest.py`` 有断言保证
#: 这个常量不会和库里的 ``LineEdit`` 实际高度脱节。
CONTROL_HEIGHT = 33


#: 阶段说明气泡每行的字符数（按 CJK 字宽估）：太窄频繁折行难读，
#: 太宽气泡会顶到屏幕边。26 字 ≈ 气泡宽 360px 上下。
HELP_TOOLTIP_WIDTH = 26

#: 说明气泡（ToolTip / Flyout）内容最大宽度：与 hover 气泡同宽量级。
HELP_BUBBLE_WIDTH = 360
