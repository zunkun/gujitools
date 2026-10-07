# -*- coding: utf-8 -*-
"""「批量删除拼版页」确认弹窗（**模块一：选择拼版** 的 UI）。

用户口径（2026-09-30）：
- **宽度固定**：弹窗不再随文字一行拉到很宽，正文允许折成多行；
- **逐页列名**：多选时用户看不清要删的是哪几页，正文下方按
  「第一页：图名 · 图名」逐行列出被勾选的页（与左列清单同源文案）；
- **高度封顶**：勾选的页再多，弹窗也不能无限变高——列表放进滚动区，
  超出封顶高度出现滚动条。

宿主（唤起与删除落盘）见 ``desktop/pages/taskdetail/imposition_pages.py``
的 ``_on_imposition_batch_delete``。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import MessageBoxBase, ScrollArea

from desktop.services.imposition import cn_page_label, page_source_stems
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to

#: 弹窗固定宽度（用户要求：宽度固定，文字折行）
DIALOG_W = 520
#: 页列表滚动区的封顶高度（超过即滚动，弹窗不再变高）
LIST_MAX_H = 264


class BatchDeleteConfirmDialog(MessageBoxBase):
    """批量删除拼版页的确认框：正文折行 + 逐页列名 + 列表滚动。"""

    def __init__(self, pages: list, parent=None):
        """``pages`` 是被勾选的 ``[(页下标, 页数据), …]``（原顺序）。

        页数据只读它的 ``items``（两张源图），文案与左列清单同源
        （``page_source_stems`` + ``cn_page_label``）。
        """
        super().__init__(parent)
        self.setWindowTitle("批量删除拼版页")
        self.widget.setFixedWidth(DIALOG_W)

        count = len(pages)

        self.title_label = QLabel("批量删除拼版页", self.widget)
        apply_to(self.title_label, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        self.viewLayout.addWidget(self.title_label)

        # 正文不逐个罗列页码（用户 2026-09-30：第一行不要列举所有页，
        # 具体删哪几页看下面的逐页清单就够了）
        self.content_label = QLabel(
            f"本操作将删除共 {count} 页图片：这些页的版面调整"
            "（位置/大小/旋转）会丢失，图片释放回未选择列表，且无法撤销。",
            self.widget,
        )
        self.content_label.setWordWrap(True)
        apply_to(self.content_label, T.SIZE_BODY, color=T.INK)
        self.viewLayout.addWidget(self.content_label)

        self.question_label = QLabel(f"确定删除如下 {count} 页？", self.widget)
        apply_to(self.question_label, T.SIZE_BODY, bold=True, color=T.INK)
        self.viewLayout.addWidget(self.question_label)

        self.viewLayout.addWidget(self._make_page_list(pages))

        self.yesButton.setText("删除")
        self.cancelButton.setText("取消")

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
        ``viewLayout.addWidget`` 自己会完成挂接。
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
