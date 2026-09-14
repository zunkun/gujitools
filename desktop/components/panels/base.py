# -*- coding: utf-8 -*-
"""阶段控制面板基类：标题 + 说明 + 参数表单骨架。

标题与说明都开启换行——右侧参数卡片只有 340~580px 宽，长说明不换行会
把面板撑出横向边界（原来靠各子类自己调 setWordWrap 兜着）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class StagePanel(QWidget):
    """阶段控制面板：标题 + 说明 + 参数表单。子类实现 _build_form/get_args。"""

    stage: str = ""
    title: str = ""
    description: str = ""

    def __init__(self, parent=None):
        """构建面板骨架：标题 + 说明 + 参数表单容器。

        title/description 来自子类类属性并开启换行，避免窄面板被长说明撑破；
        随后调用 build_form 生成子类表单并占满剩余垂直空间。
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        self.title_label = QLabel(self.title)
        apply_to(self.title_label, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.desc_label = QLabel(self.description)
        apply_to(self.desc_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        layout.addWidget(self.build_form())
        layout.addStretch()

    def build_form(self) -> QWidget:
        """参数表单容器（子类可整体替换，如 print 面板换成滚动区）。"""
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(0, T.SPACE_XS, 0, 0)
        form.setSpacing(T.SPACE_SM)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self._build_form(form)
        return container

    def _add_row(self, form: QFormLayout, label: str, widget) -> None:
        form.addRow(label, widget)

    def _build_form(self, form: QFormLayout) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_args(self) -> dict:
        """从表单收集该阶段参数（不含 input/output/clean）。"""
        raise NotImplementedError

    def apply_args(self, parameters: dict) -> None:
        """把一次历史执行的参数回填到表单（多余键忽略）。"""
        self._apply_args(parameters or {})

    def reset_to_default(self) -> None:
        """恢复控件初始默认值。

        各子类的 ``_apply_args`` 对缺失键都取自身默认值，因此传空字典
        即可复位——用于切换任务时清掉上一个任务残留的手改参数。
        """
        self.apply_args({})

    def _apply_args(self, parameters: dict) -> None:  # pragma: no cover
        raise NotImplementedError
