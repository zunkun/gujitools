# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**工具栏与状态栏**。

左侧工具竖排按钮、右侧选项页切换、底部状态提示。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon as FIF, PrimaryPushButton, PushButton, ToggleButton, ToolButton
from desktop.ui import theme as T
from .consts import DEFORM_FIT_RATIO, EDIT_FIT_RATIO, TOOLS
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class ToolbarMixin(DialogHost):
    """左侧工具竖排按钮、右侧选项页切换、底部状态提示。"""

    # ------------------------------------------------------------ 构建
    def _build_toolbar_row(self) -> QHBoxLayout:
        """主工具栏：撤销/还原 ｜ 缩放 ｜ 五个工具 ｜ … ｜ 完成。"""
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
        self.fit_btn.clicked.connect(self.canvas.fit)
        row.addWidget(self.zoom_out_btn)
        row.addWidget(self.zoom_in_btn)
        row.addWidget(self.fit_btn)

        row.addSpacing(T.SPACE_MD)
        # 工具按钮用 ToggleButton：选中态有主色高亮（用户 20:18 定"选中后
        # 有相应颜色高亮"），PushButton 的 checked 视觉不明显
        self._tool_buttons: dict[str, ToggleButton] = {}
        for key, icon, label in TOOLS:
            button = ToggleButton(icon, label)
            button.setChecked(False)
            button.setToolTip(f"{label}工具")
            button.clicked.connect(lambda _=False, k=key: self._set_tool(k))
            self._tool_buttons[key] = button
            row.addWidget(button)

        row.addStretch(1)
        self.done_btn = PrimaryPushButton(FIF.SAVE, "完成")
        self.done_btn.setToolTip(
            "应用全部编辑，覆盖原图片（会先提示确认）"
            if self._save_back else
            "应用全部编辑并回到预览；满意再用预览弹窗的「下载」保存文件"
        )
        self.done_btn.clicked.connect(self._finish)
        row.addWidget(self.done_btn)
        self._set_tool("crop")  # 填充第二行选项（工具按钮已就位）
        return row


    # ------------------------------------------------------------ 选项行
    def _swap_option_page(self) -> QHBoxLayout:
        """换掉第二行整块工具选项区：整页 deleteLater，子控件一起释放。

        ⚠️ 旧页必须先 ``hide()``：``deleteLater`` 要等事件循环才有实效，
        在此期间旧页还挂在弹窗上，不藏起来的话会以默认几何 (0,0) 压在
        工具栏上（用户报的"左上角按钮被隐藏"就是它）。
        """
        if self._option_page is not None:
            self._option_row.removeWidget(self._option_page)
            self._option_page.hide()
            self._option_page.deleteLater()
            self._option_page = None
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        self._option_page = page
        self._option_row.insertWidget(0, page, 1)
        return layout


    def _set_tool(self, tool: str) -> None:
        """切换工具并重建选项区；离开文字/变换工具前把进行中的工作写进图。"""
        if not hasattr(self, "canvas"):
            return  # 构建期先于画布存在，等 __init__ 末尾再真切换
        if tool != "text":
            self._commit_text_blocks()
        if tool != "transform":
            self._commit_transform()
        if tool != "deform":
            self._commit_deform()
        if tool != "rectify":
            self._commit_rectify()
        if tool != "cage":
            self._commit_cage()
        self.canvas.set_tool(tool)
        # 图片**永不铺满视口**：四周恒留白（用户 2026-10-02 定：编辑区不要
        # 铺满整个界面，上下预留空白方便操作）。变形/变换笼的把手、校正的
        # 四角常要往图外拖，留白更多一点；其它工具也留出同样的余量，视线与
        # 手柄不会贴控件边缘。
        self.canvas.set_fit_ratio(
            DEFORM_FIT_RATIO if tool in ("deform", "cage") else EDIT_FIT_RATIO)
        for key, button in self._tool_buttons.items():
            button.setChecked(key == tool)
        layout = self._swap_option_page()
        if tool == "crop":
            self._page_crop(layout)
        elif tool == "transform":
            self._page_transform(layout)
        elif tool == "deform":
            self._page_deform(layout)
        elif tool == "cage":
            self._page_cage(layout)
        elif tool == "rectify":
            self._page_rectify(layout)
        elif tool == "erase":
            self._page_erase(layout)
        elif tool == "text":
            self._page_text(layout)


    @staticmethod
    def _hint(layout: QHBoxLayout, text: str) -> None:
        label = CaptionLabel(text)
        label.setTextColor(QColor(T.INK_FAINT))
        layout.addWidget(label, 1)


    def _build_status(self) -> QWidget:
        """状态行：左边是提醒，右边是当前图片尺寸。"""
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        hint = CaptionLabel(
            "「完成」会提示确认后覆盖原图片；直接关闭弹窗 = 放弃本次全部编辑"
            if self._save_back else
            "「完成」应用编辑并回到预览；直接关闭弹窗 = 放弃本次全部编辑"
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
