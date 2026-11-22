# -*- coding: utf-8 -*-
"""问号帮助按钮与说明气泡（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

import textwrap

from qfluentwidgets import (
    Flyout,
    FlyoutAnimationType,
    FlyoutView,
    ToolTipFilter,
    ToolTipPosition,
    TransparentToolButton,
)

from desktop.ui.icons import HELP_CIRCLE

from ._qt import QSize, Qt
from .constants import HELP_BUBBLE_WIDTH, HELP_TOOLTIP_WIDTH

def _wrap_help_text(text: str, width: int = HELP_TOOLTIP_WIDTH) -> str:
    """把说明按固定字符数折行（ToolTip 气泡的 label 不开 wordWrap，必须预折）。"""
    return "\n".join(textwrap.wrap(text, width=width))


class _WrapFlyoutView(FlyoutView):
    """内容自动换行、整体限宽的 FlyoutView。

    ⚠️ 只给 contentLabel 开 wordWrap + setMaximumWidth **不够**：
    ``FlyoutView._adjustText`` 会先按屏幕宽把内容预折成最长 120 字符的行，
    label 的**期望宽度**（sizeHint）因此很大；气泡（本 view）若不限宽，
    Flyout 就按这个大 hint 撑开，文字却只渲染在左侧 360px 里——
    右侧一大块空白，看起来就是「气泡无限宽」。所以限宽必须加在整个 view 上。
    """

    def __init__(self, title: str, content: str, parent=None):
        super().__init__(title, content, parent=parent)
        self.contentLabel.setWordWrap(True)
        self.contentLabel.setMaximumWidth(HELP_BUBBLE_WIDTH)
        self.setMaximumWidth(HELP_BUBBLE_WIDTH)


class HelpButton(TransparentToolButton):
    """问号帮助按钮：hover 弹 ToolTip 气泡，点击弹/收说明 Flyout。

    各阶段面板（``StagePanel``）与「图片拼版」面板的标题旁都用它——
    说明文字不再平铺在标题下方占高度，全部收进这个按钮。
    """

    def __init__(self, title: str = "", description: str = "", parent=None):
        # ⚠️ 不能写 ``super().__init__(HELP_CIRCLE, parent)``：qfluentwidgets
        # 的图标构造分支内部是 ``self.__init__(parent)`` + 补 ``setIcon``——
        # 这个**虚调用**会带着 (parent) 重新进子类 __init__，改了签名的子类
        # 立刻 TypeError（缺 description）。所以走无图标分支完成 Qt 构造，
        # 图标由下面 setIcon 自己补（ToolButton.setIcon 直收 FluentIconBase）。
        super().__init__(parent)
        self._title = title
        self._description = description
        self._flyout: Flyout | None = None
        self.setIcon(HELP_CIRCLE)
        self.setFixedSize(26, 26)
        self.setIconSize(QSize(18, 18))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # hover 出气泡（ToolTip label 不换行，文字已预折行）
        self.setToolTip(_wrap_help_text(description))
        self.installEventFilter(
            ToolTipFilter(self, showDelay=300, position=ToolTipPosition.BOTTOM)
        )
        self.clicked.connect(self._toggle_help_flyout)

    def _toggle_help_flyout(self) -> None:
        """点问号按钮：弹出/关闭说明 Flyout（再点一次或点气泡外关闭）。

        ⚠️ 用 DROP_DOWN（按钮下方弹出）：按钮在面板顶部，PULL_UP（向上）
        会被屏幕边缘夹到窗口顶端，看起来像弹错了地方。
        """
        if self._flyout is not None and self._flyout.isVisible():
            self._flyout.close()
            return
        view = _WrapFlyoutView(self._title, self._description)
        self._flyout = Flyout.make(
            view, target=self, parent=self.window(),
            aniType=FlyoutAnimationType.DROP_DOWN,
        )
        # Flyout 默认 isDeleteOnClose：点气泡外/再点按钮关闭后 C++ 对象会被
        # 销毁，不清引用的话下次点击就是对已删对象调 isVisible() → RuntimeError
        self._flyout.destroyed.connect(lambda *_: setattr(self, "_flyout", None))
