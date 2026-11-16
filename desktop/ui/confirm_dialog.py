# -*- coding: utf-8 -*-
"""通用「真窗口」确认框：一点就响的那类弹窗的正确底座。

⚠️ **不要用 qfluentwidgets 的 ``MessageBox`` / ``MessageBoxBase``**：它们的
``MaskDialogBase`` 会 ``setWindowFlags(Qt.FramelessWindowHint)``，把窗口降级成
``Qt::Widget``——弹窗于是变成主窗口里的**子控件遮罩层**（``isWindow() == False``），
不是窗口，就没有"模态窗口"该有的激活与焦点语义。实机表现（2026-10-26 拼版批量
删除、2026-11-15 PDF 排版删除图片，两次都是这个坑）：点「确定」不生效、电脑
"当当当"响。

本类用真正的 ``QDialog``（``exec()`` → 真窗口 + 应用模态），并带三条"别响"的防线：

1. :meth:`_force_front` —— 上屏后隔一帧再抢前台（原生 ``SetForegroundWindow``）。
   ``activateWindow()`` 只在弹窗"不在任何按钮/菜单的 release 链里创建"时可靠，
   而确认框几乎总是被点击触发的，隔一帧成功率明显更高；
2. :meth:`eventFilter` —— 弹出后 ``ARM_MS`` 内吞掉**落在弹窗上**的点击，挡连点
   穿透（否则连点的第二下会替用户按到「确定」/「取消」）；
3. :class:`~desktop.ui.modal_quiet.HostClickMute` —— 弹窗期间落在**宿主窗口**上的
   点击连声音一起吞掉。Qt 对被模态阻塞窗口的点击一律 ``QApplication::beep()``
   （Windows 上就是"当"），用户连点时最常命中的就是这一条。

用法（与 qfluent ``MessageBox`` 的形状基本一致，替换时只改构造那几行）::

    dialog = ConfirmDialog("删除当前图片", "确定删除吗？", self.window())
    dialog.yesButton.setText("删除")
    if dialog.exec():
        ...

要在正文下方塞自定义内容（逐页清单之类）就往 ``dialog.body`` 里 ``addWidget``，
然后调一次 :meth:`fit_height` 重算高度。

要**强调其中某个词**（文件名、任务名）就传 ``rich=True`` 并用 ``<font color=…>``
包起来（见任务列表页的导入查重框）：宽度是钉死的、正文折行，长文件名只会让
弹窗**变高**，不会像 qfluent ``Dialog`` 那样把窗口撑到屏幕外。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import PrimaryPushButton, PushButton

from desktop.ui import theme as T
from desktop.ui.modal_quiet import HostClickMute
from desktop.ui.widgets import apply_to

#: 默认宽度（固定宽度、正文折行；旋钮在 ``width`` 参数上）
DIALOG_W = 440

#: 弹出后多久「解除防连点」（ms）。
#:
#: ⚠️ 这个窗口只用来挡**连点穿透**（两次点击间隔 100~200ms），绝不能取长：
#: 用户在 ``ARM_MS`` 内点按钮会被吞掉、需要再点一次——2026-10-26 已经有过
#: "点删除不生效"的投诉，别重犯。正常人从"看到弹窗"到"点下去"不少于 250ms，
#: 150ms 只可能落在机械连点上。
ARM_MS = 150

#: 防连点期间要吞掉的鼠标事件（只吞落在**本弹窗**上的）
_SWALLOWED_EVENTS = frozenset(
    (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,
    )
)


class ConfirmDialog(QDialog):
    """标题 + 正文（折行）+ 可选自定义区 + 「取消 / 确定」两按钮。

    点「确定」= ``accept()``（``exec()`` 返回真），点「取消」/Esc = ``reject()``。
    """

    def __init__(
        self,
        title: str,
        content: str,
        parent=None,
        *,
        width: int = DIALOG_W,
        yes_text: str = "确定",
        cancel_text: str = "取消",
        rich: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        # 模态 + 固定宽度：这是**真窗口**，``exec()`` 时由窗口管理器激活
        self.setModal(True)
        self.setFixedWidth(width)
        self._width = width

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)

        self.title_label = QLabel(title, self)
        apply_to(self.title_label, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        root.addWidget(self.title_label)

        self.content_label = QLabel(content, self)
        self.content_label.setWordWrap(True)
        # ⚠️ 富文本要**显式**设格式：AutoText 的嗅探靠"像不像标签"猜，正文里
        #    混了 ``<`` 之类的普通字符时会猜错，用户看到的就是一串尖括号。
        #    富文本里换行必须写 ``<br>``（``\n`` 会被当成空格吞掉）。
        if rich:
            self.content_label.setTextFormat(Qt.TextFormat.RichText)
        apply_to(self.content_label, T.SIZE_BODY, color=T.INK)
        root.addWidget(self.content_label)

        #: 正文之后、按钮之前的自定义区（子类/调用方往里 addWidget）
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(T.SPACE_MD)
        root.addLayout(self.body)

        buttons = QHBoxLayout()
        buttons.setSpacing(T.SPACE_SM)
        buttons.addStretch(1)
        self.cancelButton = PushButton(cancel_text, self)
        self.cancelButton.clicked.connect(self.reject)
        buttons.addWidget(self.cancelButton)
        self.yesButton = PrimaryPushButton(yes_text, self)
        self.yesButton.clicked.connect(self.accept)
        buttons.addWidget(self.yesButton)
        root.addLayout(buttons)

        self.fit_height()

        #: 防连点：``showEvent`` 起 ``ARM_MS`` 内为 False（见 ``eventFilter``）
        self._armed = True
        #: 抢前台：上屏后隔一帧再抢（``activateWindow`` 的兜底）。
        #: ⚠️ 用**挂在 self 上的 QTimer** 而不是 ``QTimer.singleShot``：后者
        #: 的 lambda 没有 owner，弹窗被销毁后仍可能回调到死对象。
        self._front_timer = QTimer(self)
        self._front_timer.setSingleShot(True)
        self._front_timer.timeout.connect(self._force_front)
        #: 解除防连点
        self._arm_timer = QTimer(self)
        self._arm_timer.setSingleShot(True)
        self._arm_timer.setInterval(ARM_MS)
        self._arm_timer.timeout.connect(self._arm)
        #: 宿主窗口点击静音
        self._mute = HostClickMute(parent)

    # ------------------------------------------------------------------ 版式
    def fit_height(self) -> None:
        """宽度已钉死，高度按**折行后的内容**收敛。

        ⚠️ 不能用 ``adjustSize()``：它按 ``sizeHint()`` 同时改宽高，会把
        "固定宽度"重新算成正文的自然宽度，宽度约束就丢了。这里只取
        "在这个宽度下折行需要多高"——``totalHeightForWidth`` 已含布局外边距。
        """
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        self.setFixedHeight(layout.totalHeightForWidth(self._width))

    # -------------------------------------------------------------- 三条防线
    def showEvent(self, event) -> None:  # noqa: N802
        """显示时**显式置顶并激活**，同时布好两道"别响"的防线。

        父窗口通常是 qframelesswindow 的无边框主窗口，个别情况下（远程桌面、
        多屏、窗口刚从最小化恢复、弹窗恰好在按钮/菜单的 release 处理链里创建）
        系统不会把新弹窗提到最前——那就等着"当当"响了。
        """
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self._front_timer.start(0)
        # ⚠️ 每次 show 都无条件重进保护期（不能写成 ``if self._armed``）：
        # 保护期内被关掉（Esc/取消）时 ``_armed`` 还是 False，再 show 若跳过
        # 这一步就永远解不开，之后所有点击都被吞 = "点不动"。
        self._armed = False
        self._arm_timer.start()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._mute.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        """关掉/掩掉就撤掉两道防线（幂等）。"""
        self._front_timer.stop()
        self._arm_timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self._mute.stop()
        super().hideEvent(event)

    def _arm(self) -> None:
        """解除防连点：此后的点击全部正常送进按钮。"""
        self._armed = True

    def _force_front(self) -> None:
        """再抢一次前台（``activateWindow`` 被前台锁拒绝时的兜底）。"""
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        if sys.platform != "win32":
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            # 顺序有讲究：BringWindowToTop 只改 z 序，SetForegroundWindow 才
            # 抢前台。两个都可能被系统拒绝（失败也无害——raise_ 已保证在上层）。
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """弹出后 ``ARM_MS`` 内吞掉落在本弹窗上的鼠标点击。

        ⚠️ 只吞**落在本弹窗**（含子控件）的事件：落在弹窗外的点击由
        ``HostClickMute`` 处理，别在这里抢——吞错了用户会以为"点不动"。
        """
        if not self._armed and event.type() in _SWALLOWED_EVENTS:
            target = obj if isinstance(obj, QWidget) else None
            if target is not None and (
                target is self or self.isAncestorOf(target)
            ):
                return True
        return super().eventFilter(obj, event)
