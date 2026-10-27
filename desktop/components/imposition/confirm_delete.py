# -*- coding: utf-8 -*-
"""「批量删除拼版页」确认弹窗（**模块一：选择拼版** 的 UI）。

用户口径（2026-09-30）：
- **宽度固定**：弹窗不再随文字一行拉到很宽，正文允许折成多行；
- **逐页列名**：多选时用户看不清要删的是哪几页，正文下方按
  「第一页：图名 · 图名」逐行列出被勾选的页（与左列清单同源文案）；
- **高度封顶**：勾选的页再多，弹窗也不能无限变高——列表放进滚动区，
  超出封顶高度出现滚动条。

⚠️ 底座是**真正的顶层模态窗口**（``QDialog``），**不能**用 qfluentwidgets 的
``MessageBoxBase`` / ``MessageBox``：它们的 ``MaskDialogBase`` 会
``setWindowFlags(Qt.FramelessWindowHint)``，把窗口类型降级成 ``Qt::Widget``
——弹窗于是变成主窗口里的**子控件遮罩层**（``isWindow() == False``），
不是窗口，就没有"模态窗口"该有的激活与焦点语义。实机（2026-10-26 用户报）
表现为：点「删除」不生效、电脑还"当当当"响（点击落在一个不是窗口的遮罩上）。
同页的「清空拼版」用的是 ``qfluentwidgets.Dialog``（``FramelessDialog``，
真窗口），本弹窗此前是**全仓唯一**的遮罩式确认框，这就是差异所在。

宿主（唤起与删除落盘）见 ``desktop/pages/taskdetail/imposition_pages.py``
的 ``_on_imposition_batch_delete``。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import PrimaryPushButton, PushButton, ScrollArea

from desktop.services.imposition import cn_page_label, page_source_stems
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to

#: 弹窗固定宽度（用户要求：宽度固定，文字折行）
DIALOG_W = 520
#: 页列表滚动区的封顶高度（超过即滚动，弹窗不再变高）
LIST_MAX_H = 264


class BatchDeleteConfirmDialog(QDialog):
    """批量删除拼版页的确认框：正文折行 + 逐页列名 + 列表滚动。

    ``exec()`` 走 ``QDialog`` 的嵌套事件循环：点「删除」= ``accept()``
    （返回 ``QDialog.Accepted``），点「取消」/按 Esc = ``reject()``。
    """

    def __init__(self, pages: list, parent=None):
        """``pages`` 是被勾选的 ``[(页下标, 页数据), …]``（原顺序）。

        页数据只读它的 ``items``（两张源图），文案与左列清单同源
        （``page_source_stems`` + ``cn_page_label``）。
        """
        super().__init__(parent)
        self.setWindowTitle("批量删除拼版页")
        # 模态 + 固定宽度：这是**真窗口**，``exec()`` 时由窗口管理器激活，
        # 点击不会被当成"点到被挡住的地方"（那会触发系统提示音）。
        self.setModal(True)
        self.setFixedWidth(DIALOG_W)

        count = len(pages)

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)

        self.title_label = QLabel("批量删除拼版页", self)
        apply_to(self.title_label, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        root.addWidget(self.title_label)

        # 正文不逐个罗列页码（用户 2026-09-30：第一行不要列举所有页，
        # 具体删哪几页看下面的逐页清单就够了）
        self.content_label = QLabel(
            f"本操作将删除共 {count} 页图片：这些页的版面调整"
            "（位置/大小/旋转）会丢失，图片释放回未选择列表，且无法撤销。",
            self,
        )
        self.content_label.setWordWrap(True)
        apply_to(self.content_label, T.SIZE_BODY, color=T.INK)
        root.addWidget(self.content_label)

        self.question_label = QLabel(f"确定删除如下 {count} 页？", self)
        apply_to(self.question_label, T.SIZE_BODY, bold=True, color=T.INK)
        root.addWidget(self.question_label)

        root.addWidget(self._make_page_list(pages))

        buttons = QHBoxLayout()
        buttons.setSpacing(T.SPACE_SM)
        buttons.addStretch(1)
        self.cancelButton = PushButton("取消", self)
        self.cancelButton.clicked.connect(self.reject)
        buttons.addWidget(self.cancelButton)
        self.yesButton = PrimaryPushButton("删除", self)
        self.yesButton.clicked.connect(self.accept)
        buttons.addWidget(self.yesButton)
        root.addLayout(buttons)

        self._fit_height()

    # ------------------------------------------------------------------ 版式
    def _fit_height(self) -> None:
        """宽度已钉死，高度按**折行后的内容**收敛（列表同时受封顶约束）。

        ⚠️ 不能用 ``adjustSize()``：它按 ``sizeHint()`` 同时改宽高，会把
        "固定 520 宽"重新算成正文的自然宽度，宽度约束就丢了。这里只取
        "在 520 宽下折行需要多高"——``totalHeightForWidth`` 已含布局外边距。
        """
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        self.setFixedHeight(layout.totalHeightForWidth(DIALOG_W))

    def showEvent(self, event) -> None:  # noqa: N802
        """显示时**显式置顶并激活**。

        父窗口是 qframelesswindow 的无边框主窗口，个别情况下（远程桌面、
        多屏、窗口刚从最小化恢复）系统不会把新弹窗提到最前；不置顶时
        用户点按钮点到的其实是"后面"的窗口，Windows 会响提示音。
        """
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------ 列表
    def _make_page_list(self, pages: list) -> ScrollArea:
        """被勾选页的逐行清单：一行一页「第一页：图名 · 图名」。

        ⚠️ 高度封顶（``LIST_MAX_H``）：页数少时弹窗贴合内容，页数多时
        列表内部滚动，弹窗整体不再变高（用户 2026-09-30 要求）。

        ⚠️ ``ScrollArea`` **不能以 ``container`` 为父构造**：紧接着
        ``setWidget(container)`` 会把 container 反挂进滚动区视口，
        形成「scroll 的 parent 是 container、container 的 parent 是
        scroll 的 viewport」的父子环——Qt 重挂父级时直接把进程打死
        （实测 offscreen 连 faulthandler 都来不及跑）。无父构造，
        外层布局 ``addWidget`` 自己会完成挂接。
        """
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(T.SPACE_SM, T.SPACE_XS, T.SPACE_SM, 0)
        box.setSpacing(T.SPACE_XS)
        for index, page in pages:
            row = QLabel(
                f"{cn_page_label(index)}："
                + " · ".join(page_source_stems(page)),
                container,
            )
            # 长图名折行而不是把弹窗撑宽（宽度已钉死）
            row.setWordWrap(True)
            apply_to(row, T.SIZE_CAPTION, color=T.INK_SOFT)
            box.addWidget(row)
        box.addStretch(1)

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(container)
        scroll.setMaximumHeight(LIST_MAX_H)
        # 透明底：列表融进弹窗白底（qfluent 提供的现成方法，避免自己写
        # 样式表把整棵子树填白——page_list 的老教训）
        scroll.enableTransparentBackground()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll
