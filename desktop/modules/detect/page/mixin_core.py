# -*- coding: utf-8 -*-
"""检测文本框独立页的骨架、左右两栏与识别方式（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

import PySide6.QtCore as QtCore
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PrimaryPushButton, PushButton

from desktop.components.progress_row import ProgressRow
from desktop.components.viewers import ImageViewerWidget
from desktop.settings.config import app_config
from desktop.stages.detect_stage import run_detect_pages
from desktop.steps import (
    StepKernel,
    StepRequest,
    callable_job,
)
from desktop.ui import theme as T
from desktop.ui.widgets import Card, SectionTitle
from utils.box_geometry import YOLO_CLASS_NAMES

from .constants import EXPORT_NAME, _EXPORT_ANNOTATED


class CoreMixin:
    """构造期骨架、预览/控制栏搭建、执行 job 与识别方式显隐。"""

    def __init__(self, parent=None):
        """建骨架、共用步骤控件与内存中的框表。"""
        #: 文件名去后缀 → **槽位表示**（半幅 2 槽 / 整幅 1 槽）。
        #: 与任务流程同构：不在内存里存"用户画了几个框"，只存槽位。
        self._boxes: dict[str, list] = {}
        #: 用户在半幅页上**指定**的左右：``{stem: "left"|"right"}``。
        #: 半幅的框横跨整页、中心压在中线上，位置判定没意义，所以由用户指定
        #: （用户 2026-10-17）。本页不落盘这些框，故只存内存。
        self._sides: dict[str, str] = {}
        #: 页宽缓存 ``{stem: 宽}``：整本书判据要逐页宽度，而 ``_image_size`` 走
        #: ``QImageReader`` 读文件头——每次重建判定都重读一遍是白花开销。
        self._widths: dict[str, int] = {}
        #: 同上，键 → "auto"（检测来的）/ "manual"（用户改过）。
        #: 与任务流程一样，人工框不被后续自动检测覆盖。
        self._origins: dict[str, str] = {}
        #: 导出标注图的结果：文件名列表（job 在 worker 线程里写、主线程读）
        self._exported: list[str] = []
        #: 当前这条导出线的产物形态（``_EXPORT_ANNOTATED`` / ``_EXPORT_YOLO``），
        #: 由 :meth:`_begin_export` 置位、收尾回调据此写不同的状态文案。
        self._export_kind = _EXPORT_ANNOTATED
        #: YOLO 导出 job 的统计（见 ``detect_export.export_yolo`` 的返回值）
        self._yolo_summary: dict = {}
        #: 应用配置（YOLO 标注等开关，见 desktop.settings.config）
        self.cfg = app_config()
        # ---- 识别方式与沿用上一页标注（与共享 DetectPanel 同一套参数）----
        # ⚠️ 必须在 super() 之前给默认值：_build_control 在构造期跑，接面板
        #    信号后要把面板现值抄进来（面板的真实默认在 params_spec/控件里）。
        self._detect_mode = "auto"
        self._reuse_prev = True
        #: 当前停留页的 stem（「沿用上一页标注」的参照页）。
        self._last_page_key: str | None = None
        super().__init__(parent)
        # 整本书形态判定的重算节流（见 _LAYOUT_UI_MS / _flush_layout_ui）。
        # ⚠️ 只能建在 super() **之后**：QTimer 要一个已初始化的 QObject 当父。
        self._layout_dirty = False
        self._layout_timer = QtCore.QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(self._LAYOUT_UI_MS)
        self._layout_timer.timeout.connect(self._flush_layout_ui)

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImageViewerWidget:
        """左栏：图片查看器（复用共享控件），框可编辑所以能在图上直接修正。"""
        self.viewer = ImageViewerWidget(
            editable=False,          # 不做页面增删（那是任务流程第一步的事）
            show_boxes=True,         # 框可手绘/拖动/缩放/Delete
            empty_hint="还没有图片——先拖入图片或图片文件夹",
        )
        self.viewer.current_changed.connect(self._on_page_changed)
        self.viewer.boxes_edited.connect(self._on_boxes_edited)
        self.viewer.box_edit_rejected.connect(
            lambda message: self.toast("warning", "这个框改不了", message)
        )
        # 手绘的框太小 → 不生效 + 即时提示（用户 2026-11-16；与任务流程第二步同一条链）
        self.viewer.box_too_small.connect(
            lambda message: self.toast("warning", "画框太小", message)
        )
        # 选中态 → 回填右栏「选中框类型」与删除按钮（任务流程第二步同一条链）
        self.viewer.selection_changed.connect(self._on_selection_changed)
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：共用步骤控件（含**共享 DetectPanel**）+ 导出块。

        ⚠️ 面板即任务流程第二步那个 ``DetectPanel``（识别方式/沿用上一页/框
        类型全在其中），本页只做**接线**，不重建控件——主任务面板一改这里
        自动同步（用户 2026-11-17）。本页在共用控制区之外**只加**「导出」一段
        （任务流程没有导出标注图/YOLO 的概念），它经
        :meth:`StepControl.add_extra` 插在底部动作区（输出目录/执行/中断）
        **上方**，执行按钮因此恒在右栏最底下。
        """
        card = super()._build_control()
        #: 步骤私有事件：这一步的产物（每页框坐标）就是从这里上来的。
        self.control.event.connect(  # type: ignore[reportAttributeAccessIssue]  # ``event`` 与 QObject.event 同名，运行时是 Signal
            self._on_step_event
        )
        panel = self.control.panel
        assert panel is not None, "detect 的 spec 必须带 DetectPanel"
        # ---- 与任务流程第二步同一条接线（view.py::_wire_detect_panel）----
        # 人工干预：选中框类型（左框/右框/整幅）与删除选中框
        panel.box_kind_changed.connect(self._on_box_kind_changed)
        panel.delete_box_requested.connect(self._delete_selected_box)
        # 识别方式切换：人工标注不调 YOLO ⇒ 藏执行按钮（_sync_detect_mode_ui
        # 的单机版）；「自动使用上一个文本框标注」勾选随切随记。
        panel.mode_changed.connect(self._on_detect_mode_changed)
        panel.reuse_prev_changed.connect(self._on_reuse_prev_changed)
        self._reuse_prev = panel.reuse_prev.isChecked()
        # 共享面板控件的别名（老调用点与自测沿用 page.box_kind/page.delete_box）
        self.box_kind = panel.box_kind
        self.delete_box = panel.delete_box
        self._on_detect_mode_changed(self._detect_mode)

        # ---- 导出（标注图 / YOLO 标签）走**另一条**执行内核：它是纯函数 job
        #    （画框 / 写标签 + 落盘），与 detect 的命令 job 互不干扰——用户可以在
        #    检测跑完后再导出，两次执行不抢同一个槽位，也不会因为 detect 失败而
        #    不能导出。
        # ⚠️ 两种导出**共用**这一条线（job 按 ``request.args["kind"]`` 分派）：
        #    它们都是"把已有框落盘"的短活，并行没有意义，各占一条进度行反而让
        #    用户看不出是哪条在跑。
        self._export_kernel = StepKernel(callable_job(self._export_job), self)
        self._export_kernel.log.connect(self.log)
        self._export_kernel.progress.connect(self._on_export_progress)
        self._export_kernel.finished.connect(self._on_export_finished)
        self._export_kernel.failed.connect(self._on_export_failed)

        # ⚠️ 导出标注图是本页的**第二条执行线**（另一条是 detect 本身，走
        #    ``StepControl``），两者能同时跑（用户可以边检测边导出上一批的框）。
        #    所以它要**自己一条**进度行，不能借用 control 那条——共用的话两边的
        #    进度会互相覆盖，用户看到"12/30"却不知道是谁在跑。
        #    ⚠️ 导出块与导出进度都走 add_extra：排到底部动作区（执行/中断）
        #    **上方**（用户 2026-11-17：执行/中断恒在控制面板底部）。
        self.export_progress = ProgressRow(noun="张")
        self.control.add_extra(self._build_export_buttons())
        self.control.add_extra(self.export_progress)
        return card

    # ------------------------------------------------------------------ 执行内核
    def step_job(self):
        """本页执行内核要跑的 job：走**共用逐页循环**（见 :func:`run_detect_pages`）。

        为什么不沿用 ``StepControl`` 默认的命令 job（``CommandJob → CommandArgs
        → DetectFunction``）：本页要的是**逐页事件**（``page_boxes`` 把坐标
        送回界面），默认命令 job 只转进度/日志；注入纯函数 job 后，本页与任务
        流程第二步跑的是**同一份**批量检测实现。
        """
        return callable_job(self._run_detect_job)

    def _run_detect_job(self, request: StepRequest, report) -> str | None:
        """批量检测 job（跑在 worker 线程）：**每次重新检测全部页**。

        ⚠️ 事件名形状与 ``desktop.steps.kernel.Report`` 一致（``log`` /
        ``progress`` / ``page_boxes``），经 ``_JobWorker._report`` → 内核
        ``event`` → 本页 :meth:`_on_step_event` 原样接住——界面这条链一个字都不改。
        """
        run_detect_pages(self.source_images(), workers=0, report=report)
        return str(request.dest) if request.dest is not None else None

    # ------------------------------------------------- 识别方式（人工标注）
    #
    # 与任务详情页 ``_sync_detect_mode_ui`` 同口径：人工标注 = **完全不调
    # YOLO**，执行按钮隐藏，逐页自己画框；「自动使用上一个文本框标注」只在
    # 人工标注下有意义。

    def _on_detect_mode_changed(self, mode: str) -> None:
        """识别方式变了：记下现值并按模式显隐执行按钮（单机版状态机）。"""
        self._detect_mode = "manual" if mode == "manual" else "auto"
        self.control.set_run_visible(self._detect_mode == "auto")
        # 有源时把状态行纠正过来：人工标注下"点击「检测文本框」"是误导
        # （按钮已经藏了，交付走手绘 + 导出）。
        if self.control.source() is not None:
            if self._detect_mode == "manual":
                self.status("人工标注：逐页手绘文本框，画完用「导出」交付", "info")
            else:
                spec = self.SPEC
                if spec is not None:
                    self.status(
                        f"已选择{spec.input_noun()}，点击「{spec.run_text()}」",
                        "info",
                    )

    def _on_reuse_prev_changed(self, checked: bool) -> None:
        """「自动使用上一个文本框标注」勾选随切随记（仅人工标注下生效）。"""
        self._reuse_prev = bool(checked)

    def _carry_prev_boxes(self, path_text: str) -> None:
        """人工标注 + 勾选沿用：切页时把上一页的框带过来。

        判据与任务流程一致：**上一页有真框 + 本页零框**才整份带过来；本页已
        画过（或上一页没画）都不动。带过来的框记 ``origin=manual``——后续就算
        跑自动检测也不许覆盖用户（继承）的框。
        """
        if self._detect_mode != "manual" or not self._reuse_prev:
            return
        key = Path(path_text).stem
        prev_key = self._last_page_key
        if (
            prev_key
            and prev_key != key
            and any(self._boxes.get(prev_key) or [])
            and not self._boxes.get(key)
        ):
            self._boxes[key] = list(self._boxes[prev_key])
            self._origins[key] = "manual"
            self._sync_export_buttons()

    def _build_export_buttons(self) -> Card:
        """三个交付出口（前两个是用户 2026-10-03 定的两条路，第三个是 2026-10-16 的 YOLO 标注）。

        ⚠️ **整个「导出」分类随设置里「启用YOLO标注」开关显隐**（用户
        2026-11-17：这个分类要"根据设置中 yolo 参数决定是否显示"）——开关关
        着时三颗导出按钮一起收起，开着时一起回来。设置页拨开关经
        ``cfg.yoloAnnotation.valueChanged`` 实时联动，不用重开页面。
        """
        holder = Card(padding=T.SPACE_SM, spacing=T.SPACE_XS, radius=T.RADIUS_SM)
        self._export_holder = holder
        holder.box.addWidget(SectionTitle("导出"))

        self.annotated_button = PrimaryPushButton(FIF.PHOTO, "导出标注图")
        self.annotated_button.setFixedHeight(34)
        self.annotated_button.setToolTip(
            "把框画回原图导出成 PNG（一眼核对框对不对）；"
            "会让你选输出目录，目录已存在时询问是否覆盖"
        )
        self.annotated_button.setEnabled(False)
        self.annotated_button.clicked.connect(self.export_annotated_images)
        holder.box.addWidget(self.annotated_button)

        self.export_button = PushButton(FIF.SAVE_AS, "导出坐标 JSON")
        self.export_button.setFixedHeight(34)
        self.export_button.setToolTip(
            f"把各页框坐标写成 {EXPORT_NAME}（与任务流程同格式）"
        )
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_boxes)
        holder.box.addWidget(self.export_button)

        # ---- YOLO 标注（摆在导出区**最底部**）----
        self.yolo_button = PushButton(FIF.TAG, "导出YOLO标注")
        self.yolo_button.setFixedHeight(34)
        self.yolo_button.setToolTip(
            "把各页导出成 YOLO 训练数据集切片（点它先弹窗填名称、选导出目录）：\n"
            "<导出目录>/<名称>/images/<名称>-1.jpg（按页序复制原图）\n"
            "<导出目录>/<名称>/labels/<名称>-1.txt（同页的框）\n"
            f"类别顺序 {YOLO_CLASS_NAMES[0]}=左框/右框、{YOLO_CLASS_NAMES[1]}=整幅；\n"
            "没有框的页面写空标签（负样本）。"
        )
        self.yolo_button.setEnabled(False)
        self.yolo_button.clicked.connect(self.export_yolo_labels)
        holder.box.addWidget(self.yolo_button)

        # 开关变化要重算显隐（配置项是长期存活的 QObject，页面销毁时 Qt 自动断开）
        self.cfg.yoloAnnotation.valueChanged.connect(self._sync_yolo_button)
        self._sync_yolo_button()
        return holder

    def _sync_yolo_button(self, *_args) -> None:
        """「导出」分类的显隐：YOLO 标注开关开着就显示（用户 2026-11-17）。

        ⚠️ 开关关着时**整块收起**（``_export_holder`` 连同里面的标注图/坐标
        JSON/YOLO 三颗），不是只藏第三颗。
        ⚠️ 按钮**自己**也要显式 setVisible：``isHidden()`` 只看控件自身的显式
        隐藏标记——父卡片藏了但按钮没被显式藏的话，``isHidden()`` 仍报 False
        （自测 ``dev_yolo`` 靠这个判），所以要两处一起设。
        """
        visible = bool(self.cfg.yoloAnnotation.value)
        self._export_holder.setVisible(visible)
        self.yolo_button.setVisible(visible)
