# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**各工具的选项页**。

每个工具右侧的选项面板（裁剪/变换/变形/笼/校正/擦除/文字）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel
from qfluentwidgets import CaptionLabel, CheckBox, ComboBox, PrimaryPushButton, PushButton, Slider
from desktop.ui.color_picker import ColorPickerButton
from desktop.ui.fonts import text_font_families
from .consts import CAGE_DENSITY_CHOICES, ERASER_MAX, ERASER_MIN, MESH_DENSITY_CHOICES, RECTIFY_RATIO_CHOICES, TEXT_MAX, TEXT_MIN, TEXT_SWATCHES
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class ToolPagesMixin(DialogHost):
    """每个工具右侧的选项面板（裁剪/变换/变形/笼/校正/擦除/文字）。"""

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
        self.canvas.reshape_finished.connect(
            lambda: reshape.setChecked(False))
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


    def _page_deform(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "点图放图钉 → 拖图钉：附近内容跟着走（近处动得多、远处"
                   "几乎不动，四边默认钉住）；Alt+点或右键删图钉；"
                   "图钉可拖到图外（往外拉＝拉伸）")
        combo = ComboBox()
        combo.setFixedWidth(150)
        # NoFocus：别把键盘焦点从画布抢走
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for cell, label in MESH_DENSITY_CHOICES:
            combo.addItem(label, userData=cell)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.mesh_density())))
        combo.setToolTip(
            "网格格距：越小越细腻、解算越慢。改档会**清空图钉**，"
            "所以有未应用的形变时先把当前形变落地")
        layout.addWidget(QLabel("网格疏密"))
        layout.addWidget(combo)

        def apply_density(_index: int) -> None:
            value = combo.currentData()
            if value is None:
                return
            if self.canvas.pins_pending() is not None:
                # 重建网格会把图钉清掉、已解的形变也就丢了：先落地（一个撤销点）
                self._commit_deform()
            self.canvas.set_mesh_density(float(value))

        combo.currentIndexChanged.connect(apply_density)

        reset_btn = PushButton("重置")
        reset_btn.setToolTip("清空所有图钉，丢掉未应用的形变")
        reset_btn.clicked.connect(self.canvas.reset_pins)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用变形")
        apply_btn.setToolTip(
            "把当前形变按全分辨率烘焙进图片（可撤销）；"
            "应用后图钉留在原地，方便接着微调")
        apply_btn.clicked.connect(self._commit_deform)
        layout.addWidget(apply_btn)


    def _page_cage(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "拖笼上的把手：只有把手附近的像素跟着走（远处逐字节不动）；"
                   "向外拉＝拉伸、向内推＝压缩；拖边/拖笼内＝整体平移；"
                   "把手可拖到图外")
        combo = ComboBox()
        combo.setFixedWidth(160)
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for per_side, label in CAGE_DENSITY_CHOICES:
            combo.addItem(label, userData=per_side)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.cage_density())))
        combo.setToolTip(
            "每边把手数：越多越能做出精细的局部形变。改档会**重建笼并丢掉"
            "未应用的形变**，所以有未应用的形变时先落地")
        layout.addWidget(QLabel("把手密度"))
        layout.addWidget(combo)

        def apply_density(_index: int) -> None:
            value = combo.currentData()
            if value is None:
                return
            if self.canvas.cage_pending() is not None:
                # 重建笼会把形变清掉：先落地（一个撤销点）
                self._commit_cage()
            self.canvas.set_cage_density(int(value))

        combo.currentIndexChanged.connect(apply_density)

        reset_btn = PushButton("重置")
        reset_btn.setToolTip("把手回到整幅图原位，丢掉未应用的形变")
        reset_btn.clicked.connect(self.canvas.reset_cage)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用形态")
        apply_btn.setToolTip(
            "把当前笼形变按全分辨率烘焙进图片（可撤销）；"
            "应用后把手留在原地，方便接着微调")
        apply_btn.clicked.connect(self._commit_cage)
        layout.addWidget(apply_btn)


    def _page_rectify(self, layout: QHBoxLayout) -> None:
        self._hint(layout,
                   "拖四个角框住要摆正的页面（拍摄角度/装订倾斜）："
                   "整页会被拉成矩形——四角默认压在图片四角，"
                   "往外拖可把拍进来的桌面也框进去")
        combo = ComboBox()
        combo.setFixedWidth(180)
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for mode, label in RECTIFY_RATIO_CHOICES:
            combo.addItem(label, userData=mode)
        combo.setCurrentIndex(
            max(0, combo.findData(self.canvas.rectify_ratio())))
        combo.setToolTip(
            "摆正后的目标矩形：「外接框」尺寸最省；「保持原比例」按对边"
            "平均长定宽高，内容不拉胖压扁（摆正书页推荐）")
        layout.addWidget(QLabel("目标尺寸"))
        layout.addWidget(combo)

        def apply_mode(_index: int) -> None:
            value = combo.currentData()
            if value is not None:
                self.canvas.set_rectify_ratio(str(value))

        combo.currentIndexChanged.connect(apply_mode)

        reset_btn = PushButton("重置")
        reset_btn.setToolTip("四角回到整幅图四角，丢掉未应用的校正")
        reset_btn.clicked.connect(self.canvas.reset_quad)
        layout.addWidget(reset_btn)
        apply_btn = PrimaryPushButton("应用校正")
        apply_btn.setToolTip(
            "把框住的区域透视摆正并替换整图（尺寸变为目标矩形，可撤销）")
        apply_btn.clicked.connect(self._commit_rectify)
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
