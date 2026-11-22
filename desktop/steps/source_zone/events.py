# -*- coding: utf-8 -*-
"""大输入区的事件入口：拖拽 / 键盘 / 鼠标。"""

from __future__ import annotations

from desktop.steps.source_zone.qt import Qt
from desktop.steps.source_zone.widget import _SourceZoneBase


class SourceZone(_SourceZoneBase):
    """一个步骤的**大输入区**：拖入 / 点选文件或文件夹（自绘，可清空）。

    信号：

    - ``paths_chosen(list)``：用户拖入或选中了一批路径（``list[str]``，**原始**，
      未做任何合法性判断）；空拖拽不会发。
    - ``cleared()``：用户点了右上角的清空。
    - ``rejected(str)``：**控件自己没能完成这次选择**（如选择对话框根本打不开）
      —— 一句给用户看的话。调用方通常转成页头的 toast/状态行。

    ⚠️ **"用户取消了对话框"不算 rejected**（用户2026-10-04）：那是"我什么都没
    选"，弹提示是噪声。**"给的东西一步都跑不了"也不走这里**——那属于归一化
    层的判断，由 :meth:`StepSpec.resolve_source` 给出理由并经宿主的 ``status``
    通道呈现（见 :meth:`offer`）。

    显示与语义分离：``set_source()`` 只负责"把现在选中的源画出来"，不发信号，
    因此宿主（:class:`~desktop.steps.control.StepControl`）说了算——它才是
    "文件/目录 → 一个源"的归一化权威。
    """

    # ------------------------------------------------------------ 拖 / 点 / 键
    @staticmethod
    def paths_from_mime(mime) -> list[str]:
        """从拖拽数据里取**本地**路径（URL 形式的文件/文件夹，非本地的丢掉）。

        单独抽成 staticmethod 是为了能直接单测——不用去合成 Qt 拖拽事件。
        """
        if mime is None or not mime.hasUrls():
            return []
        found: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            local = url.toLocalFile()
            if local:
                found.append(local)
        return found

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """有东西拖上来：认得本地文件/文件夹就收，并亮起来。"""
        paths = self.paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        self.set_hot(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖拽移动中：保持接受（Qt 要求显式接受才会给 drop）。"""
        if self.paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖出控件：熄灭高亮。"""
        self.set_hot(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """松手放下：把原始路径交给宿主。"""
        paths = self.paths_from_mime(event.mimeData())
        self.set_hot(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.offer(paths)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """鼠标进来：底色淡一档（可点的暗示）。"""
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """鼠标离开：恢复底色。"""
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """回车/空格 = 点一下（键盘可达）。"""
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self._browse_soon()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """点清空 = 清空；点已选态的 ✕ = 清空；点其余任何地方 = 换源（开对话框）。

        ⚠️ **已选态"点哪都能换源"是 2026-10-03 改回来的**（此前是"只有右上角那枚
        「更换」按钮能点"，因为担心用户只是想点空白让控件失焦）。改回来的理由是
        用户报「更换点了没反应」：那一枚按钮是**子控件**（见 :meth:`_build_buttons`），
        它能否收到点击取决于几何是否已随布局重排——一旦布局晚一步（懒构造的模块页
        正是如此），按钮画出来了却还不在正确位置，事件就落到了父控件上，而父控件
        那时又什么都不做 ⇒ 用户看到的就是"点了完全没反应"。

        把整条已选态都做成入口，就**不再依赖任何子控件的几何**：无论按钮在哪、
        是否被盖住，点这块区域都能换源。右上角 ✕ 优先（它更靠右、语义不同）。
        """
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self._source is not None:
            if self._close_rect.contains(event.position()):
                self.clear()
            else:
                self._browse_soon()
            event.accept()
            return
        self._browse_soon()
        event.accept()
