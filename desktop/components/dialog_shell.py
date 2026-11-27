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

from PySide6.QtCore import Qt
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
                 own_chrome: bool = False,
                 resizable: bool = False,
                 min_size: tuple[int, int] | None = None,
                 fit_height: bool = False) -> QDialog:
    """搭一个模态弹窗，返回 ``QDialog``。

    :param panel: 内容面板（三个 ``*Panel`` 之一）。
    :param on_ok: 点确定回调（默认关闭弹窗）。
    :param show_cancel: ``False`` = 只留一个按钮（如"查看流程"只读态）。
    :param own_chrome:
        ``True`` = **面板自带标题与按钮行**（``CreateTaskPanel`` 就是这种），
        外壳不再加——否则同一弹窗里会出现两套标题、两排按钮。
    :param resizable:
        ``True`` = 标题栏给「最小化 / 最大化」按钮，窗口可自由拉伸（用户
        2026-11-18：「选择子任务弹窗要显示窗口功能，放大缩小」）。默认
        ``False`` 保持既有弹窗的固定观感——小弹窗（确认框、导出框）不需要
        最大化按钮，多了反而让人误以为能拉成任意形状。
    :param min_size: 仅 ``resizable`` 时有意义：窗口的**最小**尺寸。默认取
        ``size`` 的 3/4——不锁死成开窗尺寸，小屏上才缩得回屏幕里。
    :param fit_height:
        ``True`` = 高度**按内容量**（取 ``size[1]`` 与内容所需高度的较大值），
        不再认死 ``size`` 里那个数。用户 2026-11-27 报的「Linux 下关于弹窗高度
        被压缩、文字挤在一起」就是写死高度造成的：Windows 字体行高偏小、
        180px 刚好够四行；Linux（Noto/思源，行高更大）同样四行要 ~230px，
        而布局最小高度大于窗口高度时 Qt 只能**裁着摆**，行与行就叠上了。
        ⚠️ 量高度必须在本函数**排完布局之后**：``heightForWidth`` 才带着
        边距/间距/按钮行，先 resize 再量只会拿到上半截。

    ⚠️ 面板自带的按钮**只是外观**，真正决定"确定/取消"的是本外壳：
    面板上的按钮是给自测与"无外壳直接用面板"的场景留的。
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    if resizable:
        # ⚠️ QDialog 默认 flags = Dialog|WindowTitleHint|WindowSystemMenuHint|
        #    WindowCloseButtonHint —— **没有**最小化/最大化按钮，不加这个标志
        #    标题栏上就只有那个 ×。
        dlg.setWindowFlags(
            dlg.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        # 右下角的拖拽手柄：qfluent 窗口边框很窄，没这个不好抓
        dlg.setSizeGripEnabled(True)
    dlg.resize(*size)
    # ⚠️ 模态放在改 flags 之后：setWindowFlags 会重建原生窗口，先设模态容易被
    #    一并重置（弹窗不挡父窗口 ⇒ 用户能点创建页，正是本轮要避免的）
    dlg.setModal(True)

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
        _apply_size(dlg, size, resizable, min_size, fit_height)
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
    _apply_size(dlg, size, resizable, min_size, fit_height)
    return dlg


def _content_height(dlg: QDialog, width: int) -> int:
    """窗口要用多高才放得下内容（含边距/间距/按钮行）。

    ⚠️ 换行标签的高度**不写在 sizeHint 里**——只有 ``QLayout.heightForWidth``
    会带上 ``heightForWidth`` 的折算结果，所以优先问布局；布局不支持时才退回
    ``sizeHint``。
    """
    layout = dlg.layout()
    if layout is not None and layout.hasHeightForWidth():
        height = int(layout.heightForWidth(width))
        if height > 0:
            return height
    return int(dlg.sizeHint().height())


def _apply_size(dlg: QDialog, size: tuple[int, int], resizable: bool,
                min_size: tuple[int, int] | None, fit_height: bool) -> None:
    """落地窗口尺寸（必须在布局排完之后调）。"""
    width, height = int(size[0]), int(size[1])
    if fit_height:
        height = max(height, _content_height(dlg, width))
    # 不可拉伸的弹窗把最小尺寸锁成开窗尺寸（老观感：拉不动）；
    # 可拉伸的只锁到 3/4，小屏上才缩得回屏幕里。
    if resizable:
        dlg.setMinimumSize(*(min_size or (width * 3 // 4, height * 3 // 4)))
    else:
        dlg.setMinimumSize(width, height)
    dlg.resize(width, height)


__all__ = ["shell_dialog"]
