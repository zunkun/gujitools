# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**各功能的参数页**（右侧面板里那一块）。

每个功能一张竖排参数页（裁剪/变换/扭曲/擦除/文字）。（从
``image_editor/dialog.py`` 拆出，2026-10-07；2026-10-08 由"横向选项行"改成
"右侧面板竖排"，并**删掉三个单步确认按钮**——「应用裁剪」「应用变换」
「插入文字」：裁剪改为**非破坏性**（松手只记选区，切走功能/「完成」才落定），
文字块本身就是画布预览，见 ``canvas/interaction.py`` 的
``crop_selection_changed`` 与 ``_set_tool`` 里的自动提交。）
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, PushButton, Slider, StrongBodyLabel,
)
from desktop.ui.widgets import combo_box
from desktop.ui import theme as T
from desktop.ui.color_picker import ColorPickerButton
from desktop.ui.fonts import text_font_families
from .consts import (
    CLIPPINGS, DIRECTIONS, ERASER_MAX, ERASER_MIN, GUIDES, INTERPOLATIONS,
    TEXT_MAX, TEXT_MIN, TEXT_SWATCHES,
)
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

    @staticmethod
    def _section(layout: QVBoxLayout, title: str) -> None:
        """参数区里的一节标题（照 GIMP 工具选项那样分节）。

        右侧面板窄、参数竖排，靠标题分组读起来才不乱；用 ``StrongBodyLabel``
        与 ``_hint`` 的 ``CaptionLabel`` 拉开层次（同一面板里两种字号）。
        """
        label = StrongBodyLabel(title)
        label.setToolTip(title)
        layout.addWidget(label)


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
        """裁剪：**非破坏性**——松手只定下选区，像素不切，可来回推拉。"""
        self._hint(
            layout,
            "默认选中整幅图：沿四边/四角任意位置拖动收放选区，拖框中间移动。"
            "松手只是定下选区，原图不会被切掉——向外拖回去，裁剪线外原本变暗的"
            "区域会重新显示出来，可以反复推拉；切到别的功能或点「完成」时才真正裁。")
        note = CaptionLabel("裁剪线外变暗的部分就是将要被裁掉的范围。")
        note.setTextColor(QColor(T.INK_SOFT))
        note.setWordWrap(True)
        layout.addWidget(note)
        # ⚠️ 按钮行要留 ``addStretch``（同「翻转」那两个）：面板竖排，裸
        #    ``addWidget`` 会把按钮拉成整行宽，看着像一块大色块。
        reset_row = QWidget(self._option_page)
        reset_layout = QHBoxLayout(reset_row)
        reset_layout.setContentsMargins(0, 0, 0, 0)
        reset_layout.setSpacing(T.SPACE_SM)
        reset = PushButton("重置选区")
        reset.setToolTip(
            "选区恢复到整幅图（原图像素本来就没被裁，不算一步编辑，随时可再拖）")
        reset.clicked.connect(self._reset_crop_selection)
        reset_layout.addWidget(reset)
        reset_layout.addStretch(1)
        layout.addWidget(reset_row)


    def _reset_crop_selection(self) -> None:
        """参数页「重置选区」：框弹回整幅，待定裁剪一并丢掉（不产生撤销点）。"""
        self._discard_crop()
        self.canvas.reset_selection()


    def _page_transform(self, layout: QVBoxLayout) -> None:
        """统一变换（GIMP「Unified Transform」口径）：**没有**「应用变换」按钮，
        拖完松手即烘焙。

        版面照 GIMP 的工具选项分节：**方向 → 插值 → 剪裁 → 预览 →
        参考线 → 限制 (Shift) → 从轴心 (Ctrl) → 轴心 → 其它**。
        """
        canvas = self.canvas
        self._hint(
            layout,
            "方框=缩放（角=双轴、边中=单轴）· 菱形=切变 · 角内小菱形=透视 · "
            "框内拖=移动 · 框外拖=绕轴心旋转。松手后由画布实时预览（原位置"
            "留白），离开本功能时才落地，一步一个撤销点。")
        note = CaptionLabel(
            "「方向：校正（向后）」= 把框摆到歪掉的那一块上，按反向矩阵"
            "把它掰正（预览里看到的就是校正后的样子）。")
        note.setTextColor(QColor(T.INK_SOFT))
        note.setWordWrap(True)
        layout.addWidget(note)

        direction = combo_box(DIRECTIONS, width=150)
        direction.setCurrentIndex(max(0, direction.findData(canvas._xf_direction)))
        direction.setToolTip(
            "正常（向前）：把内容搬到框的位置；校正（向后）：按**反向**矩阵烘焙"
            "——扫描件拍歪了，把框摆到歪的那块上再校正回正的")
        direction.currentIndexChanged.connect(
            lambda _index: canvas.set_transform_options(
                direction=direction.currentData()))
        layout.addWidget(self._labeled("方向", direction))

        interpolation = combo_box(INTERPOLATIONS, width=150)
        interpolation.setCurrentIndex(max(
            0, interpolation.findData(canvas._xf_interpolation)))
        interpolation.setToolTip(
            "无光晕：缩小按倍数叠加子采样再平均（最干净，默认）；"
            "立方：放大最平滑；线性：折中；最近邻：保留硬边（做像素画/线稿）")
        interpolation.currentIndexChanged.connect(
            lambda _index: canvas.set_transform_options(
                interpolation=interpolation.currentData()))
        layout.addWidget(self._labeled("插值", interpolation))

        clipping = combo_box(CLIPPINGS, width=150)
        clipping.setCurrentIndex(max(0, clipping.findData(canvas._xf_clipping)))
        clipping.setToolTip(
            "调整：画布跟着内容长（超出边界的部分不丢）；"
            "裁剪到原画布：保持原尺寸，超出的内容裁掉；"
            "裁剪到原比例：先按内容长，再居中裁回原来的长宽比")
        clipping.currentIndexChanged.connect(
            lambda _index: canvas.set_transform_options(
                clipping=clipping.currentData()))
        layout.addWidget(self._labeled("剪裁", clipping))

        show_preview = CheckBox("显示图像预览")
        show_preview.setChecked(canvas._xf_show_preview)
        show_preview.setToolTip("取消后只留变换框，看不到内容是怎么变的")
        show_preview.toggled.connect(
            lambda checked: canvas.set_transform_options(show_preview=checked))
        layout.addWidget(show_preview)

        compose = CheckBox("合成预览")
        compose.setChecked(canvas._xf_compose_preview)
        compose.setToolTip(
            "勾选=变形内容画在底图（选区原位留白）上——预览与烘焙一致；"
            "取消=底图也藏起来，只显示变形后的那一块")
        compose.toggled.connect(
            lambda checked: canvas.set_transform_options(compose_preview=checked))
        layout.addWidget(compose)

        opacity_label = CaptionLabel(f"{canvas._xf_preview_opacity}%")
        opacity_label.setTextColor(QColor(T.INK_SOFT))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(QLabel("图像不透明度"))
        head.addStretch(1)
        head.addWidget(opacity_label)
        layout.addLayout(head)
        opacity = Slider(Qt.Orientation.Horizontal)
        opacity.setRange(0, 100)
        opacity.setValue(canvas._xf_preview_opacity)
        opacity.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        opacity.setToolTip("只影响**预览**的浓淡，不影响烘焙结果")

        def apply_opacity(value: int) -> None:
            opacity_label.setText(f"{value}%")
            canvas.set_transform_options(opacity=value)

        opacity.valueChanged.connect(apply_opacity)
        layout.addWidget(opacity)

        guide = combo_box(GUIDES, width=150)
        guide.setCurrentIndex(max(0, guide.findData(canvas._xf_guide)))
        guide.setToolTip("框内的构图辅助线（跟着变换一起变形）")
        guide.currentIndexChanged.connect(
            lambda _index: canvas.set_transform_options(
                guide=guide.currentData()))
        layout.addWidget(self._labeled("参考线", guide))

        # ---- 限制 (Shift) ----
        self._section(layout, "限制 (Shift)")
        constraints = (
            ("移动", "move", "位移吸附到 45° 的整数倍"),
            ("缩放", "scale", "保持长宽比（等比缩放）"),
            ("旋转", "rotate", "旋转吸附到 15° 一档"),
            ("切变", "shear", "切变时被抓的边不离开原边线"),
            ("透视", "perspective", "透视手柄只能沿边或对角线走"),
        )
        for title, key, tip in constraints:
            box = CheckBox(title)
            box.setChecked(bool(canvas._xf_constraints.get(key, False)))
            box.setToolTip(
                f"{tip}；按住 Shift 可临时**取反**（GIMP 同款：没勾的勾上、"
                "勾了的取消）")
            box.toggled.connect(
                lambda checked, k=key: canvas.set_transform_constraint(k, checked))
            layout.addWidget(box)

        # ---- 从轴心 (Ctrl) ----
        self._section(layout, "从轴心 (Ctrl)")
        pivot_boxes = (
            ("缩放", "scale", "以轴心为锚缩放（默认锚在对角/对边）"),
            ("切变", "shear", "绕轴心切变：两边反向各走一半"),
            ("透视", "perspective", "透视时轴心位置保持不动"),
        )
        for title, key, tip in pivot_boxes:
            box = CheckBox(title)
            box.setChecked(bool(canvas._xf_pivot_ops.get(key, False)))
            box.setToolTip(f"{tip}；按住 Ctrl 可临时取反")
            box.toggled.connect(
                lambda checked, k=key: canvas.set_transform_pivot_op(k, checked))
            layout.addWidget(box)

        # ---- 轴心 ----
        self._section(layout, "轴心")
        snap = CheckBox("吸附 (Shift)")
        snap.setChecked(canvas._xf_snap_pivot)
        snap.setToolTip("轴心拖到框中心/四角附近时自动贴上去")
        snap.toggled.connect(
            lambda checked: canvas.set_transform_options(snap_pivot=checked))
        layout.addWidget(snap)
        lock = CheckBox("锁定")
        lock.setChecked(canvas._xf_lock_pivot)
        lock.setToolTip("锁住轴心：只能绕当前位置旋转/缩放，拖不动它")
        lock.toggled.connect(
            lambda checked: canvas.set_transform_options(lock_pivot=checked))
        layout.addWidget(lock)

        # ---- 其它：调整范围 + 翻转 ----
        self._section(layout, "其它")
        reshape = CheckBox("调整范围")
        reshape.setToolTip(
            "勾选后沿边拖动收小要处理的区域（收完自动回到变换模式）——"
            "小范围修褶皱：先框住褶皱，再旋转/切变把它正回来"
        )
        reshape.setChecked(canvas._xf_reshape)
        reshape.toggled.connect(canvas.set_transform_reshape)
        # ⚠️ 参数页每次切功能都重建，旧复选框随旧页销毁；画布信号上的连接
        #    却一直活着——下次 reshape 完成时会调到已销毁的控件上抛
        #    RuntimeError（用户 2026-10-08 报的刷屏）。所以先解掉上一份页
        #    留下的连接，再连新的（回调里也兜住"页已重建"的竞态）。
        old_uncheck = getattr(self, "_reshape_uncheck", None)
        if old_uncheck is not None:
            try:
                canvas.reshape_finished.disconnect(old_uncheck)
            except (RuntimeError, TypeError):
                pass  # 从没连上 / 接收端已死：本来就是要清掉的状态

        def _uncheck_reshape() -> None:
            try:
                reshape.setChecked(False)
            except RuntimeError:
                pass  # 切功能时参数页已重建，老复选框随旧页销毁

        self._reshape_uncheck = _uncheck_reshape
        canvas.reshape_finished.connect(_uncheck_reshape)
        layout.addWidget(reshape)

        flip_row = QWidget(self._option_page)
        flips = QHBoxLayout(flip_row)
        flips.setContentsMargins(0, 0, 0, 0)
        flips.setSpacing(T.SPACE_SM)
        for title, horizontal, tip in (
            ("水平翻转", True, "左右镜像（立即应用，一步一个撤销点）"),
            ("垂直翻转", False, "上下镜像（立即应用，一步一个撤销点）"),
        ):
            button = PushButton(title)
            button.setToolTip(tip)
            button.clicked.connect(
                lambda _checked=False, h=horizontal: self._flip_transform(h))
            flips.addWidget(button)
        flips.addStretch(1)
        layout.addWidget(flip_row)


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
