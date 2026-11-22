# -*- coding: utf-8 -*-
"""大输入区的尺寸/留白常量。"""

from __future__ import annotations

from desktop.ui import theme as T

#: 空态高度（px）：要"大"，一眼看出这里是主入口。
#:
#: ⚠️ 底部要给**文案与按钮整块**留位（用户 2026-10-03 报「有框说可以拖入，
#: 但没法直接点击按钮选择文件或文件夹」）：只靠"点空白处弹小菜单"这条隐式
#: 入口，用户根本不知道哪里能点。现在空态底部摆两个真按钮，且**与文案一起
#: 垂直居中**（见 ``_empty_block_top``）。
EMPTY_HEIGHT = 168
#: 已选态高度（px）：收窄成一行，把纵向空间还给预览
FILLED_HEIGHT = 74
#: 空态图标盒子边长（px）
ICON_BOX = 30
#: 清空按钮的点击盒边长（px）
CLOSE_BOX = 26
#: 选择按钮高度（px）与按钮之间的间距（px）
BUTTON_HEIGHT = 30
BUTTON_GAP = 10
#: 内容与虚框的左右留白（px）
PAD = T.SPACE_LG
#: **独占模式**（页面上再没有别的控件，见
#: :meth:`desktop.modules.base.ModulePage.show_workspace`）下的高度：
#: 撑满整幅，让"当前页只有一个输入框"看起来是**刻意设计**而不是内容没加载出来。
SOLO_HEIGHT = 320
#: 独占模式的最小宽度（px）：再窄就换行/省略，不必保持
SOLO_MIN_WIDTH = 360
#: 「高度不设上限」用的哨兵值 = Qt 自己的 ``QWIDGETSIZE_MAX``。
#:
#: ⚠️ Qt 的 ``QWIDGETSIZE_MAX`` 在 PySide6 里**没有导出**（``QtCore`` 与
#: ``QtWidgets`` 都 import 不到），所以按它的定义写死：它是 ``(1 << 24) - 1``，
#: 即 16777215。
#:
#: ⚠️⚠️ **必须是 ``- 1``，不能写 ``1 << 24``**（用户 2026-10-03 报「单独拼版
#: 界面报错」）：``setMaximumHeight(16777216)`` 超过 Qt 的硬上限，Qt 会往
#: stderr 打 ``QWidget::setMaximumSize: The largest allowed size is
#: (16777215,16777215)`` 并把值**截断**回 16777215。功能上无害（截断后正是
#: 我们要的"不设上限"），但拼版独立页初始就是独占模式，每次进页面都刷这条
#: 警告，看着像报错。控件实际高度由布局决定，永远碰不到这个上限。
HEIGHT_UNLIMITED = (1 << 24) - 1
