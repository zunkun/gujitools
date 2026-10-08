# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**各功能的参数页**（右侧面板里那一块）。

每个功能一张竖排参数页（裁剪/变换/扭曲/擦除/文字）。（从
``image_editor/dialog.py`` 拆出，2026-10-07；2026-10-08 由"横向选项行"改成
"右侧面板竖排"，并**删掉三个单步确认按钮**——「应用裁剪」「应用变换」
「插入文字」：编辑改为实时生效，见 ``canvas/interaction.py`` 的
``crop_committed`` / ``transform_committed`` 与 ``_set_tool`` 里的自动提交。）
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, Slider,
)
from desktop.ui.widgets import combo_box
from desktop.ui import theme as T
from desktop.ui.color_picker import ColorPickerButton
from desktop.ui.fonts import text_font_families
from .consts import ERASER_MAX, ERASER_MIN, TEXT_MAX, TEXT_MIN, TEXT_SWATCHES
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class ToolPagesMixin(DialogHost):
    """每个功能右侧的参数面板（裁剪/变换/扭曲/擦除/文字）。"""

    # ------------------------------------------------------------ 小工具
    @staticmethod
    def _labeled(title: str, control: QWidget) -> QWidget:
        """「标题 + 控件」一行（右侧面板窄，控件靠左、余量撑开）。"""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)
        row.addWidget(QLabel(title))
        row.addWidget(control)
        row.addStretch(1)
        return box


    def _slider_group(self, title: str, key: str, low: int, high: int,
                      suffix: str) -> QWidget:
        """「标题 … 数值」+ 整条滑杆（扭曲参数用）。"""
        canvas = self.canvas
        value = int(getattr(canvas, f"_distort_{key}"))
        box = QWidget(self._option_page)
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        value_label = CaptionLabel(f"{value}{suffix}")
        value_label.setTextColor(QColor(T.INK_SOFT))
        head.addWidget(QLabel(title))
        head.addStretch(1)
        head.addWidget(value_label)
        column.addLayout(head)
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.setToolTip(f"{title}（{low}–{high}{suffix}）")
        column.addWidget(slider)

        def changed(new_value: int) -> None:
            value_label.setText(f"{new_value}{suffix}")
            canvas.set_distortion_options(**{key: new_value})

        slider.valueChanged.connect(changed)
        return box


    # ------------------------------------------------------------ 各功能
    def _page_crop(self, layout: QVBoxLayout) -> None:
        """裁剪：**没有**「应用裁剪」按钮——拖完松手就裁（实时）。"""
        self._hint(
            layout,
            "默认选中整幅图：沿四边/四角任意位置向内拖收小选区，拖框中间移动。"
            "松手即裁到当前选区（不用再点按钮）；裁错了按 Ctrl+Z 退回。")
        note = CaptionLabel("拖动中变暗的部分就是将要被裁掉的范围。")
        note.setTextColor(QColor(T.INK_SOFT))
        note.setWordWrap(True)
        layout.addWidget(note)


    def _page_transform(self, layout: QVBoxLayout) -> None:
        """变换：**没有**「应用变换」按钮——拖完松手即烘焙（实时）。"""
        self._hint(
            layout,
            "拖角=缩放（Shift 等比）· 拖边=切变 · 框内拖=移动 · 框外拖=绕轴心"
            "旋转（Shift 每 15°）。松手即应用（原区域填白），一步一个撤销点。")
        reshape = CheckBox("调整范围")
        reshape.setToolTip(
            "勾选后沿边拖动收小要处理的区域（收完自动回到变换模式）——"
            "小范围修褶皱：先框住褶皱，再旋转/切变把它正回来"
        )
        reshape.setChecked(self.canvas._xf_reshape)
        reshape.toggled.connect(self.canvas.set_transform_reshape)
        # ⚠️ 参数页每次切功能都重建，旧复选框随旧页销毁；画布信号上的连接
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
                pass  # 切功能时参数页已重建，老复选框随旧页销毁

        self._reshape_uncheck = _uncheck_reshape
        self.canvas.reshape_finished.connect(_uncheck_reshape)
        layout.addWidget(reshape)
        check = CheckBox("从轴心缩放/切变")
        check.setToolTip("勾选后缩放/切变以轴心为锚（旋转永远绕轴心）")
        check.setChecked(self.canvas._xf_about_pivot)
        check.toggled.connect(self.canvas.set_transform_about_pivot)
        layout.addWidget(check)


    def _page_distort(self, layout: QVBoxLayout) -> None:
        """GIMP-style deformation brush options (values are image pixels/%)."""
        self._hint(layout, "圆形软笔刷：一笔一个撤销点；笔刷尺寸按图片像素。")
        canvas = self.canvas
        modes = (
            ("移动像素", "move"),
            ("扩张区域", "grow"),
            ("收缩区域", "shrink"),
            ("顺时针旋转", "swirl_cw"),
            ("逆时针旋转", "swirl_ccw"),
            ("平滑扭曲", "smooth"),
            ("恢复原状", "restore"),
        )
        mode_combo = combo_box(modes, width=132)
        mode_combo.setCurrentIndex(max(
            0, mode_combo.findData(canvas._distort_mode)))
        mode_combo.setToolTip("移动、扩缩、旋转、平滑或恢复笔刷经过的区域")
        mode_combo.currentIndexChanged.connect(
            lambda _index: canvas.set_distortion_options(
                mode=mode_combo.currentData()))
        layout.addWidget(self._labeled("笔刷模式", mode_combo))

        for title, key, low, high, suffix in (
            ("大小", "size", 4, 600, "px"),
            ("硬度", "hardness", 0, 100, "%"),
            ("强度", "strength", 0, 100, "%"),
            ("间距", "spacing", 1, 100, "%"),
        ):
            layout.addWidget(self._slider_group(title, key, low, high, suffix))

        interpolation = combo_box(
            (("最近邻", "nearest"), ("线性", "linear"), ("立方", "cubic")),
            width=100,
        )
        interpolation.setCurrentIndex(max(
            0, interpolation.findData(canvas._distort_interpolation)))
        interpolation.setToolTip("最终笔触的像素插值方式")
        interpolation.currentIndexChanged.connect(
            lambda _index: canvas.set_distortion_options(
                interpolation=interpolation.currentData()))
        layout.addWidget(self._labeled("插值", interpolation))

        realtime = CheckBox("实时预览")
        realtime.setChecked(canvas._distort_realtime)
        realtime.setToolTip("勾选时拖动过程中变形；取消后松开鼠标时应用整笔")
        realtime.toggled.connect(
            lambda checked: canvas.set_distortion_options(realtime=checked))
        layout.addWidget(realtime)
        quality = CheckBox("高质量预览")
        quality.setChecked(canvas._distort_high_quality_preview)
        quality.setToolTip(
            "勾选时预览使用平滑插值（所选立方插值会以线性方式实时预览）；"
            "取消时拖动预览用最近邻；松开后均按所选插值提交")
        quality.toggled.connect(lambda checked: canvas.set_distortion_options(
            high_quality_preview=checked))
        layout.addWidget(quality)


    def _page_erase(self, layout: QVBoxLayout) -> None:
        self._hint(layout, "按住左键在污点上涂抹，把它擦成白底"
                           "（古籍页面去污点）；一笔一个撤销点。")
        size_label = CaptionLabel(f"{self._erase_size}px")
        size_label.setTextColor(QColor(T.INK_SOFT))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(QLabel("橡皮擦大小"))
        head.addStretch(1)
        head.addWidget(size_label)
        layout.addLayout(head)
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(ERASER_MIN, ERASER_MAX)
        slider.setValue(self._erase_size)
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def apply_size(value: int) -> None:
            size_label.setText(f"{value}px")
            self._erase_size = value
            self.canvas.set_eraser(value)

        slider.valueChanged.connect(apply_size)
        layout.addWidget(slider)
        # 初次进入按默认大小生效
        self.canvas.set_eraser(self._erase_size)


    def _page_text(self, layout: QVBoxLayout) -> None:
        """文字：**没有**「插入文字」按钮——文字块本身就是实时预览，
        切走功能或点「完成」时自动写进图片。"""
        self._hint(layout, "点击图片落点就地输入（光标可见）；样式对整块即时生效；"
                           "悬停文字出现虚线框，按住可拖动整块。")
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
        layout.addWidget(self._labeled("字体", combo))

        size_label = CaptionLabel(f"{self._text_size}px")
        size_label.setTextColor(QColor(T.INK_SOFT))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(QLabel("字号"))
        head.addStretch(1)
        head.addWidget(size_label)
        layout.addLayout(head)
        slider = Slider(Qt.Orientation.Horizontal)
        slider.setRange(TEXT_MIN, TEXT_MAX)
        slider.setValue(self._text_size)
        # ⚠️ NoFocus：qfluentwidgets 的 Slider 默认是 StrongFocus，一拖就把
        # 键盘焦点从画布抢走——就地编辑的文字块随之丢焦点、光标消失。
        # （改样式走"当前样式块"后功能上已不依赖焦点，但保住光标体验更好。）
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slider.setToolTip("文字大小（图片像素）")
        layout.addWidget(slider)

        # 颜色：常用色块与任意色**都收在这一个按钮弹出的面板里**（用户
        # 2026-10-01：色块不要在外面，要在颜色选择器里面，且要好看）
        picker = ColorPickerButton(QColor(self._text_color), TEXT_SWATCHES,
                                   parent=self)
        layout.addWidget(self._labeled("颜色", picker))

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
