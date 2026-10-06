# -*- coding: utf-8 -*-
"""BPM 各弹窗共用的**外壳**：标题 + 内容 + 底部按钮。

## 为什么不用 qfluentwidgets 的 ``Dialog``

``Dialog``（``MessageBox`` 的子类）的签名是 ``(title, content: str, parent)``，
它只支持"一段文字 + 两个按钮"：

- 第二参是**字符串** content（塞进 ``BodyLabel``），传控件会在
  ``FluentLabelBase.__init__()`` 处报 ``takes 1 to 2 positional arguments``；
- 它**没有** ``viewLayout()``——那是我们当初误以为存在的 API。

而这三个弹窗要放的是一整套流程面板（节点图 + 工具栏 + 状态行）。于是
:func:`shell_dialog` 用普通 ``QDialog`` + qfluentwidgets 的按钮自己搭。

⚠️ 这个坑是**三个弹窗同时踩中**的（创建任务/ 编辑流程 / 查看流程），而且
自测全都直接实例化 Panel、从不构造外壳，所以一直没人发现。凡是"点按钮就
炸、但自测全绿"，先怀疑外壳。
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import PrimaryPushButton, PushButton, StrongBodyLabel

from desktop import ui
from desktop.ui import theme as T


def shell_dialog(title: str, panel: QWidget, parent=None, *,
                 size=(920, 620),
                 ok_text: str = "确定",
                 cancel_text: str = "取消",
                 on_ok=None, on_cancel=None,
                 show_cancel: bool = True,
                 own_chrome: bool = False) -> QDialog:
    """搭一个模态弹窗，返回 ``QDialog``。

    :param panel: 内容面板（三个 ``*Panel`` 之一）。
    :param on_ok: 点确定回调（默认关闭弹窗）。
    :param show_cancel: ``False`` = 只留一个按钮（如"查看流程"只读态）。
    :param own_chrome:
        ``True`` = **面板自带标题与按钮行**（``CreateTaskPanel`` 就是这种），
        外壳不再加——否则同一弹窗里会出现两套标题、两排按钮。

    ⚠️ 面板自带的按钮**只是外观**，真正决定"确定/取消"的是本外壳：
    面板上的按钮是给自测与"无外壳直接用面板"的场景留的。
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setMinimumSize(*size)
    dlg.resize(*size)

    root = QVBoxLayout(dlg)
    if own_chrome:
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
    else:
        root.setContentsMargins(
            T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG
        )
        root.setSpacing(T.SPACE_MD)
        heading = StrongBodyLabel(title)
        ui.apply_to(heading, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        root.addWidget(heading)
    root.addWidget(panel, 1)

    if own_chrome:
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        return dlg

    buttons = QHBoxLayout()
    buttons.addStretch()
    cancel = PushButton(cancel_text)
    buttons.addWidget(cancel)
    ok = PrimaryPushButton(ok_text)
    buttons.addWidget(ok)
    root.addLayout(buttons)

    ok.clicked.connect(on_ok if on_ok is not None else dlg.accept)
    cancel.clicked.connect(on_cancel if on_cancel is not None else dlg.reject)
    if not show_cancel:
        cancel.setVisible(False)
    return dlg


__all__ = ["shell_dialog"]
