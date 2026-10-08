# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**各工具的选项页**。

每个工具右侧的选项面板（裁剪/变换/擦除/文字）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel
from qfluentwidgets import CaptionLabel, CheckBox, ComboBox, PrimaryPushButton, PushButton, Slider
from desktop.ui.color_picker import ColorPickerButton
from desktop.ui.fonts import text_font_families
from .consts import ERASER_MAX, ERASER_MIN, TEXT_MAX, TEXT_MIN, TEXT_SWATCHES
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class ToolPagesMixin(DialogHost):
    """每个工具右侧的选项面板（裁剪/变换/擦除/文字）。"""

    def _page_crop(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "默认选中整幅图：沿四边/四角任意位置向内拖收小选区，"
                   "拖框中间移动；松手后视图自动放大到新选区")
        apply_btn = PrimaryPushButton("应用裁剪")
        apply_btn.setToolTip("把画布裁成当前选区（可撤销）")
        apply_btn.clicked.connect(self._apply_crop)
        layout.addWidget(apply_btn)


    def _page_transform(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "拖角=缩放（Shift 等比）· 拖边=切变 · 框内拖=移动"
                           " · 框外拖=绕轴心旋转（Shift 每 15°）；轴心圆点可拖动")
        reshape = CheckBox("调整范围")
        reshape.setToolTip(
            "勾选后沿边拖动收小要处理的区域（收完自动回到变换模式）——"
            "小范围修褶皱：先框住褶皱，再旋转/切变把它正回来"
        )
        reshape.setChecked(self.canvas._xf_reshape)
        reshape.toggled.connect(self.canvas.set_transform_reshape)
        # ⚠️ 选项页每次切工具都重建，旧复选框随旧页销毁；画布信号上的连接
        #    却一直活着——下次 reshape 完成时会调到已销毁的控件上抛
        #    RuntimeError（用户 2026-10-08 报的刷屏）。所以先解掉上一份页
        #    留下的连接，再连新的（回调里也兜住"页已重建"的竞态）。
        old_uncheck = getattr(self, "_reshape_uncheck", None)
        if old_uncheck is not None:
            try:
                self.canvas.reshape_finished.disconnect(old_uncheck)
            except (RuntimeError, TypeError):
                pass  # 从没连上 / 接收端已死：本来就是要清掉的状态

        def _uncheck_reshape() -> None:
            try:
                reshape.setChecked(False)
            except RuntimeError:
                pass  # 切工具时选项页已重建，老复选框随旧页销毁

        self._reshape_uncheck = _uncheck_reshape
        self.canvas.reshape_finished.connect(_uncheck_reshape)
        layout.addWidget(reshape)
        check = CheckBox("从轴心缩放/切变")
        check.setChecked(self.canvas._xf_about_pivot)
        check.toggled.connect(self.canvas.set_transform_about_pivot)
        layout.addWidget(check)
        reset_btn = PushButton("重置")
        reset_btn.setToolTip("丢弃未应用的变换，选区回到整幅（不动已应用的编辑）")
        reset_btn.clicked.connect(self.canvas.reset_transform)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用变换")
        apply_btn.setToolTip("把当前变换烘焙进图片：原区域填白（可撤销）")
        apply_btn.clicked.connect(self._commit_transform)
        layout.addWidget(apply_btn)


    def _page_erase(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "按住左键在污点上涂抹，把它擦成白底（古籍页面去污点）")
        size_label = CaptionLabel(f"{self._erase_size}px")
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(ERASER_MIN, ERASER_MAX)
        slider.setValue(self._erase_size)
        slider.setFixedWidth(160)

        def apply_size(value: int) -> None:
            size_label.setText(f"{value}px")
            self._erase_size = value
            self.canvas.set_eraser(value)

        slider.valueChanged.connect(apply_size)
        layout.addWidget(QLabel("橡皮擦大小"))
        layout.addWidget(slider)
        layout.addWidget(size_label)
        # 初次进入按默认大小生效
        self.canvas.set_eraser(self._erase_size)


    def _page_text(self, layout: QHBoxLayout) -> None:
        self._hint(layout, "点击图片落点就地输入（光标可见）；样式对**整块**"
                           "即时生效；悬停文字出现虚线框，按住可拖动整块；"
                           "「插入文字」把文字写进图片")
        # 字体：**中文字体为主** + 几个常用西文（用户 2026-10-01 定：系统字体
        # 库里两三百个族全列出来，中文反而被淹没、翻半天找不到"仿宋"）
        combo = ComboBox()
        combo.setFixedWidth(170)
        for family in text_font_families():
            combo.addItem(family, userData=family)
        combo.setCurrentIndex(max(0, combo.findData(self._text_family)))
        family = combo.currentData()
        if family:  # 存的族名不在清单里时以清单首项为准，别错位
            self._text_family = family
        combo.setToolTip("文字字体（中文字体为主）")
        layout.addWidget(QLabel("字体"))
        layout.addWidget(combo)

        size_label = CaptionLabel(f"{self._text_size}px")
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(TEXT_MIN, TEXT_MAX)
        slider.setValue(self._text_size)
        slider.setFixedWidth(160)
        # ⚠️ NoFocus：qfluentwidgets 的 Slider 默认是 StrongFocus，一拖就把
        # 键盘焦点从画布抢走——就地编辑的文字块随之丢焦点、光标消失。
        # （改样式走"当前样式块"后功能上已不依赖焦点，但保住光标体验更好。）
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.setToolTip("文字大小（图片像素）")
        layout.addWidget(QLabel("字号"))
        layout.addWidget(slider)
        layout.addWidget(size_label)

        # 颜色：常用色块与任意色**都收在这一个按钮弹出的面板里**（用户
        # 2026-10-01：色块不要在外面，要在颜色选择器里面，且要好看）
        layout.addWidget(QLabel("颜色"))
        picker = ColorPickerButton(QColor(self._text_color), TEXT_SWATCHES,
                                   parent=self)
        layout.addWidget(picker)

        def style_changed() -> None:
            block = self.canvas.style_target_block()
            if block is not None:
                block.apply_style(
                    self._text_family, self._text_size,
                    QColor(self._text_color))

        combo.currentIndexChanged.connect(
            lambda _index: (
                setattr(self, "_text_family",
                        combo.currentData() or self._text_family),
                style_changed()))
        slider.valueChanged.connect(
            lambda value: (setattr(self, "_text_size", value),
                           size_label.setText(f"{value}px"), style_changed()))
        picker.colorChanged.connect(
            lambda color: (setattr(self, "_text_color", color.name()),
                           style_changed()))
        # 颜色面板关掉后把键盘焦点还给文字块，接着打字不中断
        picker.panelClosed.connect(self.canvas.focus_text_block)

        insert_btn = PrimaryPushButton("插入文字")
        insert_btn.setToolTip("把画布上的文字块写进图片（可撤销）")
        insert_btn.clicked.connect(self._commit_text_blocks)
        layout.addWidget(insert_btn)
