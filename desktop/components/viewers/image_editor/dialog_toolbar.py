# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**顶部功能条 + 右侧参数面板 + 状态栏**。

布局（2026-10-08 重排，用户定：「顶部是功能选择，右侧是每个功能的相关参数
面板」）::

    ┌──────────────────────────────────────────────────────┐
    │ 撤销 重做 还原 │ 缩小 放大 适应窗口 │        │  完成   │  ← _build_toolbar_row 上半
    ├──────────────────────────────────────────────────────┤
    │ 裁剪  变换  扭曲  擦除  文字                          │  ← _build_toolbar_row 下半
    ├───────────────────────────────┬──────────────────────┤
    │                               │  裁剪                │
    │          画布                  │  （提示）            │
    │                               │  ── 参数（随功能换）── │
    │                               │  ── 编辑历史 ──────── │
    ├───────────────────────────────┴──────────────────────┤
    │ 状态提示                                    200×120px │
    └──────────────────────────────────────────────────────┘

旧版把工具按钮挤在动作行、参数挤在第二行横向排——一行摆不下时左侧按钮被
挤出窗口（用户截图报过），而且参数一多就横向溢出。现在动作行只放全局动作、
功能单独一行、参数竖排在右侧固定宽度面板里。

（原「左侧工具竖排 + 第二行选项」版从 ``image_editor/dialog.py`` 拆出，
2026-10-07。）
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel, FluentIcon as FIF, ListWidget, PrimaryPushButton,
    PushButton, StrongBodyLabel, ToggleButton, ToolButton,
)
from desktop.ui import theme as T
from .consts import EDIT_FIT_RATIO, HISTORY_HEIGHT, PANEL_WIDTH, TOOLS
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


#: 工具键 → 中文名（面板标题用）
TOOL_LABELS = {key: label for key, _icon, label in TOOLS}


class ToolbarMixin(DialogHost):
    """顶部功能条、右侧参数面板、底部状态提示。"""

    # ------------------------------------------------------------ 构建
    def _build_toolbar_row(self) -> QVBoxLayout:
        """顶部两段：动作行（撤销/缩放/完成）+ 功能选择行。"""
        column = QVBoxLayout()
        column.setSpacing(T.SPACE_SM)

        row = QHBoxLayout()
        row.setSpacing(T.SPACE_SM)
        self.undo_btn = ToolButton(FIF.RETURN)
        self.undo_btn.setToolTip("撤销上一步（Ctrl+Z）")
        self.undo_btn.clicked.connect(self._undo_now)
        self.redo_btn = ToolButton(FIF.SYNC)
        self.redo_btn.setToolTip("重做（Ctrl+Y）")
        self.redo_btn.clicked.connect(self._redo_now)
        self.reset_btn = PushButton("还原")
        self.reset_btn.setToolTip("放弃全部编辑，回到打开时的样子（可撤销）")
        self.reset_btn.clicked.connect(self._reset_all)
        row.addWidget(self.undo_btn)
        row.addWidget(self.redo_btn)
        row.addWidget(self.reset_btn)

        row.addSpacing(T.SPACE_MD)
        self.zoom_out_btn = ToolButton(FIF.ZOOM_OUT)
        self.zoom_out_btn.setToolTip("缩小（滚轮向下）")
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.zoom_in_btn = ToolButton(FIF.ZOOM_IN)
        self.zoom_in_btn.setToolTip("放大（滚轮向上）")
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        self.fit_btn = PushButton("适应窗口")
        self.fit_btn.setToolTip("整图完整可见")
        # ⚠️⚠️ **必须套一层 lambda**：``clicked`` 会顺手塞一个 ``checked: bool``
        #    进来，而 ``fit(ratio=None)`` 正好能接一个位置参数 ⇒ 收到的是
        #    ``False``；``float(False) == 0.0`` 被夹成下限 0.2，"适应窗口"
        #    于是把图缩成视口的 1/4 大小（用户 2026-10-08 报"图片立马变得非常小"）。
        #    同行的 ``zoom_in/zoom_out`` 没有参数，PySide6 才不会多塞这一个。
        self.fit_btn.clicked.connect(lambda: self.canvas.fit())
        row.addWidget(self.zoom_out_btn)
        row.addWidget(self.zoom_in_btn)
        row.addWidget(self.fit_btn)

        row.addStretch(1)
        self.done_btn = PrimaryPushButton(FIF.SAVE, "完成")
        self.done_btn.setToolTip(
            "应用全部编辑，覆盖原图片（会先提示确认）"
            if self._save_back else
            "应用全部编辑并回到预览；满意再用预览弹窗的「下载」保存文件"
        )
        self.done_btn.clicked.connect(self._finish)
        row.addWidget(self.done_btn)
        column.addLayout(row)

        # ---- 功能选择行（切功能 = 换右侧参数面板）----
        tabs = QHBoxLayout()
        tabs.setSpacing(T.SPACE_SM)
        # 工具按钮用 ToggleButton：选中态有主色高亮（用户 20:18 定"选中后
        # 有相应颜色高亮"），PushButton 的 checked 视觉不明显
        self._tool_buttons: dict[str, ToggleButton] = {}
        for key, icon, label in TOOLS:
            button = ToggleButton(icon, label)
            button.setIconSize(QSize(14, 14))
            button.setChecked(False)
            button.setToolTip(f"{label}（顶部切功能，参数在右侧面板）")
            button.clicked.connect(lambda _=False, k=key: self._set_tool(k))
            self._tool_buttons[key] = button
            tabs.addWidget(button)
        tabs.addStretch(1)
        column.addLayout(tabs)

        self._set_tool("crop")  # 填充右侧面板的第一份参数页
        return column


    def _build_side_panel(self) -> QWidget:
        """右侧参数面板：功能名 + 提示 + 参数区 + 编辑历史。

        ⚠️ 必须在 ``_build_toolbar_row`` **之前**建好：那个函数末尾的
        ``_set_tool`` 就会往 ``_option_host`` 里插第一份参数页。
        """
        panel = QWidget(self)
        panel.setFixedWidth(PANEL_WIDTH)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(T.SPACE_SM)

        self.panel_title = StrongBodyLabel(TOOL_LABELS["crop"])
        self.panel_title.setToolTip("当前功能；参数在下面")
        column.addWidget(self.panel_title)

        self._option_host = QWidget(panel)
        self._option_host_layout = QVBoxLayout(self._option_host)
        self._option_host_layout.setContentsMargins(0, 0, 0, 0)
        self._option_host_layout.setSpacing(T.SPACE_SM)
        column.addWidget(self._option_host)

        column.addStretch(1)
        history_title = CaptionLabel("编辑历史")
        history_title.setTextColor(QColor(T.INK_SOFT))
        history_title.setToolTip(
            "每一步一个节点，点某一格可直接回退或前进到那一步（同 Ctrl+Z / Ctrl+Y）")
        column.addWidget(history_title)
        self.history_list = ListWidget(panel)
        self.history_list.setFixedHeight(HISTORY_HEIGHT)
        self.history_list.setToolTip(
            "第 0 格是打开时的状态；当前停在的一格会被选中")
        self.history_list.currentRowChanged.connect(self._on_history_row)
        column.addWidget(self.history_list)
        return panel


    # ------------------------------------------------------------ 参数面板
    def _swap_option_page(self) -> QVBoxLayout:
        """换掉右侧面板里的整块参数区：整页 deleteLater，子控件一起释放。

        ⚠️ 旧页必须先 ``hide()``：``deleteLater`` 要等事件循环才有实效，
        在此期间旧页还挂在面板上，不藏起来的话会以默认几何 (0,0) 压住
        新页（旧版挤在工具栏行里时表现为"左上角按钮被隐藏"）。
        """
        if self._option_page is not None:
            self._option_host_layout.removeWidget(self._option_page)
            self._option_page.hide()
            self._option_page.deleteLater()
            self._option_page = None
        page = QWidget(self._option_host)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        self._option_page = page
        self._option_host_layout.addWidget(page)
        return layout


    def _set_tool(self, tool: str) -> None:
        """切换功能并重建右侧参数页；离开文字/变换前把进行中的工作写进图。"""
        if not hasattr(self, "canvas"):
            return  # 构建期先于画布存在，等 __init__ 末尾再真切换
        if tool != "text":
            self._commit_text_blocks()
        if tool != "transform":
            self._commit_transform()
        self.canvas.set_tool(tool)
        # 图片**永不铺满视口**：四周恒留白（用户 2026-10-02 定：编辑区不要
        # 铺满整个界面，上下预留空白方便操作）。
        self.canvas.set_fit_ratio(EDIT_FIT_RATIO)
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        self.panel_title.setText(TOOL_LABELS.get(tool, tool))
        layout = self._swap_option_page()
        if tool == "crop":
            self._page_crop(layout)
        elif tool == "transform":
            self._page_transform(layout)
        elif tool == "distort":
            self._page_distort(layout)
        elif tool == "erase":
            self._page_erase(layout)
        elif tool == "text":
            self._page_text(layout)


    @staticmethod
    def _hint(layout: QVBoxLayout, text: str) -> None:
        """参数区顶部的一行说明（竖排 + 自动换行，面板窄）。"""
        label = CaptionLabel(text)
        label.setTextColor(QColor(T.INK_FAINT))
        label.setWordWrap(True)
        layout.addWidget(label)


    def _build_status(self) -> QWidget:
        """状态行：左边是提醒，右边是当前图片尺寸。"""
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        hint = CaptionLabel(
            "编辑即时生效（松手即应用）；Ctrl+Z 撤销上一步，右侧「编辑历史」可点选跳转；"
            + ("「完成」会提示确认后覆盖原图片"
               if self._save_back else "「完成」应用编辑并回到预览")
            + "；直接关闭弹窗 = 放弃本次全部编辑"
        )
        hint.setTextColor(QColor(T.INK_FAINT))
        self.size_label = CaptionLabel("")
        self.size_label.setTextColor(QColor(T.INK_SOFT))
        row.addWidget(hint, 1)
        row.addWidget(self.size_label)
        if self._image is not None:
            self.size_label.setText(
                f"{self._image.width()} × {self._image.height()} px"
            )
        return bar


    def _refresh_size_label(self) -> None:
        """裁剪/变换换了画布尺寸后刷新右下角的尺寸提示。"""
        label = getattr(self, "size_label", None)
        if label is None or self._image is None:
            return
        label.setText(f"{self._image.width()} × {self._image.height()} px")
