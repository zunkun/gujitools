# -*- coding: utf-8 -*-
"""拼版控制面板——**模块二：拼版操作** 的右列（详情页控制区）。

布局（用户 2026-09-30 晚定稿）：标题行（说明挂**问号按钮**，同其他步骤面板）
+ 状态行 + **两块分区** + 底部启用开关：

- **「操作当前图片页」**：页级操作——整体旋转（滑块/输入框，任意角度增量）、
  **复位本页版面**（独占一行 block）、**一行两个**的「新增图片」（只在单图页
  出现）与「删除选中图片」（只在选中某张图时出现；2026-09-30 用户定：删除
  按钮从图片样式区挪进来跟新增图片同行）——「删除本页拼版」按钮已删除
  （删页入口只剩左列的「✕」与批量删除），清空全部拼版保留；
- **「当前图片样式」**：图片级操作——旋转（绕图片中心）。这一块**只在画布里
  选中了某张图时激活并高亮**（``_ItemSection``），切页 / 点空白取消选中后
  整块灰掉；
- **「在流程中启用图片拼版」**复选框**放面板最底部**（用户 2026-09-30）：
  决定第四步取图来源（共享基元 ``print_source_dir``）。⚠️ 这是**任务流程
  专属**的概念——公共面板的契约只有输入/输出；没有下游流程的宿主（独立
  拼图页、未来的批处理界面）构造时传 ``enable_switch=False`` 收起它。

「选择拼版」按钮**不在本面板**（2026-09-30 删除）：入口只有左列末尾的
虚线「＋ 选择拼版」格（``page_list.py``），两处同义留一处。

这里只做控件与信号，所有动作都发信号交给模块二控制器
（``desktop/pages/taskdetail/imposition_layout.py``）与共享基元
（``imposition.py``）处理：
- 删除/清空是**页管理**（模块一控制器）；页序在左列**拖动排序**、翻页在
  画布下方「上一页/下一页」（``view.py``），都不在本面板；
- **整体旋转**（增量）与**选中图旋转**（绝对角度）是**版面操作**（模块二
  控制器）。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from qfluentwidgets import CaptionLabel, CheckBox, DoubleSpinBox, PushButton
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import Slider

from desktop.ui import theme as T
from desktop.ui.widgets import Card, HelpButton, SectionTitle, apply_to

#: 旋转组件的量程：-180°~180°。输入框 2 位小数（步进 0.1°）；
#: 滑块**通栏独占一行**、按 **0.01°/格** 走（值 = 度数 × ``ANGLE_SLIDER_SCALE``）
#: ——实际使用都是微调（用户 2026-09-30），大角度直接在输入框键入。
ANGLE_SPIN_RANGE = (-180.0, 180.0)
ANGLE_SLIDER_SCALE = 100
ANGLE_SLIDER_RANGE = (-180 * ANGLE_SLIDER_SCALE, 180 * ANGLE_SLIDER_SCALE)

#: 问号按钮里的面板说明（与流程条虚线节点的提示同一件事）
PANEL_DESCRIPTION = (
    "可选节点：第三步「区域模式」为 1（左右分开）时出现在流程中，位于"
    "「图片去底色」与「生成 PDF」之间。勾选下方开关后，「生成 PDF」将"
    "使用拼版结果；不勾选则用第三步的去底色产物。"
)


class _ItemSection(QFrame):
    """「当前图片样式」区块：画布里选中了图才**激活并高亮**，否则灰掉。

    ⚠️ 底色/描边**自己画**（``paintEvent``），不用样式表——样式表一旦进入
    子树，Qt 会把 QFrame 底色填白（步骤条 ``_StepBadge``、页清单
    ``_PageEntry`` 的同一条教训），还会连带影响子 QLabel 的取色路径。

    「删除选中图片」按钮**不在本区块里**（2026-09-30 用户定：挪到页级区的
    「新增图片」同一行），本区块只剩旋转样式；选中/取消选中的显隐由面板
    ``set_item_rotation`` 一并拨动删除按钮。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(T.SPACE_SM)
        self.title_label = QLabel("当前图片样式", self)
        column.addWidget(self.title_label)
        self.rotation_caption = CaptionLabel("旋转（绕图片中心）", self)
        apply_to(self.rotation_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        # 说明行：说明(拉伸) + 度数输入框（面板注入）；滑块通栏独占下一行
        self.cap_row = QHBoxLayout()
        self.cap_row.setSpacing(T.SPACE_SM)
        self.cap_row.addWidget(self.rotation_caption, 1)
        column.addLayout(self.cap_row)
        self.angle_row = QHBoxLayout()  # 通栏滑块行（面板注入滑块）
        self.angle_row.setSpacing(T.SPACE_SM)
        column.addLayout(self.angle_row)
        self.empty_hint = CaptionLabel("未选中图片——点击画布里的某张图后在这里调整", self)
        self.empty_hint.setWordWrap(True)
        apply_to(self.empty_hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        column.addWidget(self.empty_hint)
        self._apply_state()

    def set_active(self, on: bool) -> None:
        """有/没有选中的图：高亮整块 + 收起"未选中"提示。"""
        on = bool(on)
        self.empty_hint.setVisible(not on)
        if on != self._active:
            self._active = on
            self._apply_state()

    def _apply_state(self) -> None:
        apply_to(
            self.title_label,
            T.SIZE_CAPTION,
            bold=True,
            color=T.ACCENT if self._active else T.INK_FAINT,
        )
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._active:
            painter.setPen(QPen(QColor(T.ACCENT), 1.4))
            painter.setBrush(QColor(T.ACCENT_SOFT))
        else:
            painter.setPen(QPen(QColor(T.BORDER), 1.0))
            painter.setBrush(QColor(T.SURFACE))
        painter.drawRoundedRect(rect, T.RADIUS_SM, T.RADIUS_SM)
        painter.end()


class ImpositionPanel(Card):
    """「图片拼版」详情控制面板（control_stack 的第 5 页）。"""

    #: 启用开关切换（决定第四步取图来源）
    enabled_toggled = Signal(bool)
    #: **整版旋转**的增量（度，顺时针为正）——滑块/输入框连续吐增量，
    #: 控制器在停顿后统一 commit 落盘
    whole_rotate_delta = Signal(float)
    #: 选中图的旋转被设为**绝对角度**（度）
    item_rotation_edited = Signal(float)
    #: 复位本页版面
    reset_requested = Signal()
    #: 点了「新增图片」（只在单图页出现）：给本页再导一张图
    add_image_requested = Signal()
    #: 点了「删除选中图片」（页级区「新增图片」同行那颗红按钮）
    item_delete_requested = Signal()
    #: 清空全部页
    clear_requested = Signal()

    def __init__(self, parent=None, *, enable_switch: bool = True):
        """``enable_switch=False``：收起底部「在流程中启用图片拼版」开关。

        开关决定任务流程第四步的取图来源，是**任务流程专属**概念；没有
        下游流程的宿主（独立拼图页）传 ``False``。控件仍会构造（只是隐藏
        并置为已启用），宿主无需感知属性是否存在。
        """
        super().__init__(padding=T.SPACE_MD, spacing=T.SPACE_MD, radius=T.RADIUS_MD)
        column: QVBoxLayout = self.box
        # 标题行：说明挂问号按钮（同其他步骤面板），不再平铺占高度
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(T.SPACE_XS)
        title_row.addWidget(SectionTitle("图片拼版"))
        self.help_button = HelpButton("图片拼版", PANEL_DESCRIPTION)
        title_row.addWidget(self.help_button, 0, Qt.AlignmentFlag.AlignTop)
        title_row.addStretch(1)
        column.addLayout(title_row)

        self.status_label = CaptionLabel("尚未添加拼版页")
        self.status_label.setWordWrap(True)
        apply_to(self.status_label, T.SIZE_CAPTION, color=T.INK_SOFT)
        column.addWidget(self.status_label)

        # ---- 「操作当前图片页」：页级操作（用户 2026-09-30 分区口径）----
        column.addWidget(SectionTitle("操作当前图片页"))

        self._syncing_rotation = False  # 程序化回填滑块/输入框时挡住信号回抛
        self._whole_angle = 0.0  # 整版旋转组件当前显示的绝对角度

        # ---- 整体旋转（任意角度，绕两图公共中心）----
        # 用户 2026-09-30：滑块与输入框不挤一行——输入框挂说明行右侧，
        # 滑块通栏独占一行按 0.01°/格微调；大角度直接在输入框键入
        whole_head = QHBoxLayout()
        whole_head.setSpacing(T.SPACE_SM)
        self.whole_caption = CaptionLabel("整体旋转（绕两图公共中心）")
        apply_to(self.whole_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        whole_head.addWidget(self.whole_caption, 1)
        self.whole_spin = self._build_angle_spin()
        whole_head.addWidget(self.whole_spin)
        column.addLayout(whole_head)
        self.whole_slider = self._build_angle_slider(column)
        self.whole_slider.valueChanged.connect(self._on_whole_slider)
        self.whole_spin.valueChanged.connect(self._on_whole_spin)

        # 复位本页版面独占一行（block，2026-09-30 用户定：删除按钮挪去
        # 与「新增图片」同行后，复位不再拼行）
        self.reset_button = PushButton(FIF.SYNC, "复位本页版面")
        self.reset_button.setToolTip("把本页图片恢复成刚拼好时的样子（并排、原始大小、不旋转）")
        self.reset_button.clicked.connect(self.reset_requested)
        column.addWidget(self.reset_button)

        # 「新增图片」（只在单图页出现）+「删除选中图片」（只在选中某张图
        # 时出现）一行两个（2026-09-30 用户定：删除按钮从「当前图片样式」
        # 区块挪进页级区；显隐互不依赖，各占一半，独显时占满整行）
        page_actions = QHBoxLayout()
        page_actions.setSpacing(T.SPACE_SM)
        self.add_image_button = PushButton(FIF.ADD, "新增图片")
        self.add_image_button.setToolTip("本页只有一张图：再导入一张剩余未拼版的图片，拼成左右两图的一页")
        self.add_image_button.clicked.connect(self.add_image_requested)
        page_actions.addWidget(self.add_image_button, 1)
        self.add_image_button.hide()
        # 配色（用户 2026-09-30）：红底白字，样式对齐任务列表页的删除按钮
        # （`theme.danger_button_qss` 共享一份）。⚠️ 实例样式表会把 qfluent
        # 自带 qss（高度/内边距）整体顶掉——这里必须带上 fluent 同款内边距，
        # 高度才跟「新增图片」一致；⚠️ 也别用 `FluentStyleSheet.BUTTON.value`
        # 拼 qss——`.value` 只是文件名字符串 "button"，不是 qss 内容，拼出来
        # 会把样式顶光（按钮变矮、图标叠字，2026-09-30 用户截图报过）。
        # 纯文字不带图标：红底上 fluent 深色图标对比度差，任务列表删除按钮同款。
        self.delete_item_button = PushButton("删除选中图片", self)
        self.delete_item_button.setToolTip(
            "把选中的这张图从本页拼版里删掉（源图不受影响，"
            "回到未选择列表可重新选择）；若是本页最后一张，"
            "整页拼版会一并移除（会先确认）"
        )
        self.delete_item_button.setStyleSheet(
            # 上下内边距比 fluent 多 1px：fluent 按钮上下各还有 1px 边框
            # （5+6+2=32），红底按钮 border: none，补齐才同高
            T.danger_button_qss(padding="6px 12px 7px 12px")
        )
        self.delete_item_button.clicked.connect(self.item_delete_requested)
        page_actions.addWidget(self.delete_item_button, 1)
        self.delete_item_button.hide()
        column.addLayout(page_actions)

        self.clear_button = PushButton(FIF.CLEAR_SELECTION, "清空全部拼版")
        self.clear_button.clicked.connect(self.clear_requested)
        column.addWidget(self.clear_button)

        # ---- 「当前图片样式」：图片级操作，选中图才激活高亮 ----
        # （删除按钮在上面页级区的「新增图片」同行，不在这里）
        self.item_section = _ItemSection(self)
        column.addWidget(self.item_section)
        self.item_spin = self._build_angle_spin()
        self.item_section.cap_row.addWidget(self.item_spin)
        self.item_slider = self._build_angle_slider(self.item_section.angle_row)
        self.item_slider.setEnabled(False)
        self.item_spin.setEnabled(False)
        self.item_slider.valueChanged.connect(self._on_item_slider)
        self.item_spin.valueChanged.connect(self._on_item_spin)

        # 弹性空白收在启用开关之前：其余控件紧凑靠上，开关钉在面板最底部
        column.addStretch(1)

        # ---- 启用开关放面板最底部（用户 2026-09-30）：决定第四步取图来源；
        # 任务流程专属，独立页等无下游流程的宿主传 enable_switch=False 收起 ----
        self.enabled_checkbox = CheckBox("在流程中启用图片拼版")
        self.enabled_checkbox.setToolTip("启用后「生成 PDF」用拼版合成结果；不启用则从去底色直接生成 PDF")
        self.enabled_checkbox.toggled.connect(self.enabled_toggled)
        column.addWidget(self.enabled_checkbox)
        if not enable_switch:
            self.enabled_checkbox.setVisible(False)
            self.enabled_checkbox.setChecked(True)  # 面板内部按"已启用"渲染

    # ------------------------------------------------------------------ 状态
    def _build_angle_spin(self) -> DoubleSpinBox:
        """度数输入框：±180°、2 位小数、点按 0.1°（微调口径，用户 2026-09-30）。"""
        spin = DoubleSpinBox()
        spin.setRange(*ANGLE_SPIN_RANGE)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setSuffix("°")
        return spin

    def _build_angle_slider(self, box: QBoxLayout) -> Slider:
        """通栏旋转滑块：值 = 度数 ×100，即 **0.01°/格**（键盘 1 格、翻页 1°）。"""
        slider = Slider(Qt.Horizontal)
        slider.setRange(*ANGLE_SLIDER_RANGE)
        slider.setSingleStep(1)
        slider.setPageStep(ANGLE_SLIDER_SCALE)
        box.addWidget(slider)
        return slider

    @staticmethod
    def _wrap_angle(value: float) -> float:
        """任意角度收敛到 [-180, 180)，与画布 ``spread_rotation`` 同口径。"""
        return (float(value) + 180.0) % 360.0 - 180.0

    def _on_whole_slider(self, ticks: int) -> None:
        if self._syncing_rotation:
            return
        self._syncing_rotation = True
        self.whole_spin.setValue(ticks / ANGLE_SLIDER_SCALE)
        self._syncing_rotation = False
        self._emit_whole_delta(ticks / ANGLE_SLIDER_SCALE)

    def _on_whole_spin(self, value: float) -> None:
        if self._syncing_rotation:
            return
        self._syncing_rotation = True
        self.whole_slider.setValue(int(round(value * ANGLE_SLIDER_SCALE)))
        self._syncing_rotation = False
        self._emit_whole_delta(value)

    def _emit_whole_delta(self, new_value: float) -> None:
        """组件值变了 → 换算成**跨 ±180° 边界也正确**的增量发给控制器。"""
        delta = self._wrap_angle(new_value - self._whole_angle)
        self._whole_angle = self._wrap_angle(new_value)
        if abs(delta) > 1e-9:
            self.whole_rotate_delta.emit(delta)

    def _on_item_slider(self, ticks: int) -> None:
        if self._syncing_rotation:
            return
        self._syncing_rotation = True
        self.item_spin.setValue(ticks / ANGLE_SLIDER_SCALE)
        self._syncing_rotation = False
        self.item_rotation_edited.emit(ticks / ANGLE_SLIDER_SCALE)

    def _on_item_spin(self, value: float) -> None:
        if self._syncing_rotation:
            return
        self._syncing_rotation = True
        self.item_slider.setValue(int(round(value * ANGLE_SLIDER_SCALE)))
        self._syncing_rotation = False
        self.item_rotation_edited.emit(value)

    def set_whole_angle(self, value: float) -> None:
        """程序化回填整版角度（blockSignals 语义，绝不回抛增量）。"""
        value = self._wrap_angle(value)
        self._whole_angle = value
        self._syncing_rotation = True
        self.whole_slider.setValue(int(round(value * ANGLE_SLIDER_SCALE)))
        self.whole_spin.setValue(value)
        self._syncing_rotation = False

    def set_item_rotation(self, value: float | None) -> None:
        """程序化回填选中图角度；``None`` = 没有选中。

        ``None`` 时「当前图片样式」整块灰掉、组件禁用清零，页级区的
        「删除选中图片」一并隐藏；有值则高亮激活、删除按钮露出
        （用户 2026-09-30：只有某张图片选中 active 时图片区才高亮）。
        """
        self.item_section.set_active(value is not None)
        self.delete_item_button.setVisible(value is not None)
        if value is None:
            self._syncing_rotation = True
            self.item_slider.setValue(0)
            self.item_spin.setValue(0.0)
            self._syncing_rotation = False
            self.item_slider.setEnabled(False)
            self.item_spin.setEnabled(False)
            return
        self.item_slider.setEnabled(True)
        self.item_spin.setEnabled(True)
        value = self._wrap_angle(value)
        self._syncing_rotation = True
        self.item_slider.setValue(int(round(value * ANGLE_SLIDER_SCALE)))
        self.item_spin.setValue(value)
        self._syncing_rotation = False

    def set_page_available(self, on: bool) -> None:
        """有没有可操作的拼版页：没有时整版旋转组件一并禁用。"""
        self.whole_slider.setEnabled(bool(on))
        self.whole_spin.setEnabled(bool(on))

    def set_single_page(self, on: bool) -> None:
        """当前页是不是**单图页**：是才露出「新增图片」（两图页隐藏）。"""
        self.add_image_button.setVisible(bool(on))

    def set_enabled_checked(self, on: bool) -> None:
        """程序化回填启用开关（blockSignals 避免回抛覆盖落盘值）。"""
        self.enabled_checkbox.blockSignals(True)
        self.enabled_checkbox.setChecked(bool(on))
        self.enabled_checkbox.blockSignals(False)

    def set_status(self, text: str) -> None:
        """状态行：当前页 + 选中槽位 + 生效与否。"""
        self.status_label.setText(text)
