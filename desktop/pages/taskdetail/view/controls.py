# -*- coding: utf-8 -*-
"""执行记录、运行按钮与右侧面板宽度（从原 ``view.py`` 拆出）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qfluentwidgets import (
    CaptionLabel,
    ComboBox,
    PrimaryPushButton,
    PushButton,
)
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui.icons import PDF_FILE
from desktop.ui.widgets import ProgressLine, SectionTitle, apply_to, combo_box

from desktop.pages.taskdetail.submit import SUBMIT_TEXT
from desktop.pages.taskdetail.view._qt import (
    QBoxLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from desktop.pages.taskdetail.view._host import DetailViewHost
else:
    DetailViewHost = object


class DetailControlsMixin(DetailViewHost):
    """执行记录下拉、运行/下载按钮与面板宽度区间。"""
    def _build_history_controls(self, control: QBoxLayout) -> None:
        # ---- 历史执行配置选择（detect 阶段整体隐藏，见 _select_stage）----
        # ⚠️ 必须包成独立 block 再整体 setVisible：散着藏的话，切到第二步要
        #    记住藏三个控件，漏一个就露出半截「执行记录」。
        self.history_block = QWidget()
        block = QVBoxLayout(self.history_block)
        block.setContentsMargins(0, 0, 0, 0)
        block.setSpacing(T.SPACE_SM)
        block.addWidget(SectionTitle("执行记录"))
        self.history_caption = CaptionLabel("历史执行配置（选择后回填到表单）")
        apply_to(self.history_caption, T.SIZE_CAPTION, color=T.INK_FAINT)
        block.addWidget(self.history_caption)
        self.history_combo = self._make_history_combo()
        block.addWidget(self.history_combo)
        control.addWidget(self.history_block)

        self.stage_status = CaptionLabel("未执行")
        apply_to(self.stage_status, T.SIZE_CAPTION, color=T.INK_SOFT)
        control.addWidget(self.stage_status)
        # 细进度条：只表达"执行到多少页"，不抢视觉
        self.stage_progress = ProgressLine()
        control.addWidget(self.stage_progress)

    def _make_history_combo(self) -> ComboBox:
        combo = combo_box()
        combo.currentIndexChanged.connect(self._on_history_selected)
        return combo

    def _build_run_controls(self, control: QBoxLayout) -> None:
        self.run_button = PrimaryPushButton(FIF.PLAY, "提取文档图片")
        self.run_button.setFixedHeight(36)
        self.run_button.clicked.connect(lambda: self.run_stage(resume=False))
        # 「分割图片」（原「提交本次任务」）：第二步（检测 → 逐框裁图）的**次动作**按钮。
        # ⚠️ 文案取 SUBMIT_TEXT（submit.py 的唯一来源）：并排一行后放不下
        #    更长的写法，"有新版本"由加粗 + 下方红字提示表达。
        self.submit_button = PrimaryPushButton(FIF.ACCEPT, SUBMIT_TEXT)
        self.submit_button.setFixedHeight(36)
        self.submit_button.setToolTip(
            "把检测出的每个文本框裁成一张图，交给下一步去底色"
        )
        self.submit_button.clicked.connect(self.run_submit)
        self.submit_button.setVisible(False)
        # 「检测文本框 / 分割图片」并排一行：它们是同一步骤的前后两跳
        # （先出框、再裁图），竖着堆叠会让人误以为是两个步骤。
        # ⚠️ 没有提交按钮的步骤（1/3/4）只有 run_button 可见，stretch=1 让它
        #    自动占满整行，视觉与并排前一致。
        # ⚠️ 整行包进独立 QWidget：拼版详情页要整组隐藏执行按钮
        #    （`_select_imposition_detail`），用 addLayout 的话行高仍在，
        #    控制区底部会留一条空白。
        self.action_row = QWidget()
        action = QHBoxLayout(self.action_row)
        action.setContentsMargins(0, 0, 0, 0)
        action.setSpacing(T.SPACE_SM)
        action.addWidget(self.run_button, 1)
        action.addWidget(self.submit_button, 1)
        # 新版本提示：检测框/结果变化后、提交前常驻提醒（位于提交按钮下方）
        self.submit_hint = CaptionLabel("")
        self.submit_hint.setWordWrap(True)
        apply_to(self.submit_hint, T.SIZE_CAPTION)
        self.submit_hint.hide()
        control.addWidget(self.action_row)
        # 「下载 PDF」：**生成PDF 之后**才出现的第二行（用户 2026-11-01）。
        # 摆在「生成PDF」正下方而不是预览区顶部——生成是这一行的主动作，
        # 下载是它的后续，竖着读就是"先跑、再拿结果"。
        self.download_print_button = PushButton(PDF_FILE, "下载 PDF")
        self.download_print_button.setFixedHeight(34)
        self.download_print_button.clicked.connect(self._download_print_pdf)
        self.download_row = QWidget()
        download_layout = QHBoxLayout(self.download_row)
        download_layout.setContentsMargins(0, 0, 0, 0)
        download_layout.addWidget(self.download_print_button, 1)
        self.download_row.setVisible(False)
        control.addWidget(self.download_row)
        control.addWidget(self.submit_hint)

    def _sync_download_print_button(self, _available: bool | None = None) -> None:
        """「下载 PDF」只在**第四步有可用 PDF**时出现在「生成PDF」下面。

        ``_available`` 是 ``PrintPreviewWidget.set_pdf_path`` 发来的状态位；
        在此之外（切步骤、进拼版详情）也会被无参调用，所以判据统一现读
        「当前步骤 + 预览控件记下的 PDF」，不信任传入值。
        """
        row = getattr(self, "download_row", None)
        if row is None:
            return
        row.setVisible(
            self.current_stage() == "print"
            and getattr(self.print_preview, "_pdf_path", None) is not None
        )

    # ------------------------------------------------------------------ 宽度
    def _apply_control_width(self) -> None:
        """按当前阶段调整右侧控制面板宽度：**查 spec**（不再 `if stage == "print"`）。

        第四步参数最多（版面/页码/字体…），要更宽的编辑区；其余步骤用 340~440px
        的舒适表单宽度（标签不折行、输入框不被压扁）。区间由
        ``StepSpec.control_width`` 声明，加一步要更宽只改它的 spec。
        """
        from desktop.steps import ports
        from desktop.steps.spec import StepSpec

        spec = ports.spec_for_stage(self.current_stage())
        # ⚠️ 兜底分支正常走不到（伪步骤也有自己的 spec）；StepSpec 必填字段
        #    无法空构造，这里保持原行为、不另造默认值。
        minimum, maximum = (
            spec.control_width if spec else StepSpec().control_width  # type: ignore[reportCallIssue]
        )
        self.control_widget.setMinimumWidth(minimum)
        self.control_widget.setMaximumWidth(maximum)
