# -*- coding: utf-8 -*-
"""右侧控制卡片、面板接线与第四步参数联动（从原 ``view.py`` 拆出）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from qfluentwidgets import PushButton
from qfluentwidgets import FluentIcon as FIF

from desktop.components import PANEL_CLASSES
from desktop.components.detect_stats import DetectStatsWidget
from desktop.components.imposition import ImpositionPanel
from desktop.steps.spec import FLOW_STAGES
from desktop.ui import theme as T
from desktop.ui.widgets import Card, Divider, SectionTitle

from desktop.pages.taskdetail.view._qt import QObject, QStackedWidget, QTimer, QWidget
from desktop.pages.taskdetail.view.lazy_host import LazyPanelHost

if TYPE_CHECKING:
    from desktop.pages.taskdetail.view._host import DetailViewHost
else:
    DetailViewHost = object


class DetailPanelsMixin(DetailViewHost):
    """控制列、惰性面板接线、YOLO 卡片与打印参数回填。"""
    def _build_imposition_panel(self) -> Card:
        """「图片拼版」详情面板（模块二的右侧控制区，控件实体在
        ``desktop/components/imposition/panel.py``），这里只接线。

        启用开关决定**第四步的取图来源**：勾选且有拼版页时，生成 PDF 用拼版
        结果，否则回到第三步的去底色产物（见 ``print_source_dir``）。
        """
        panel = ImpositionPanel()
        panel.enabled_toggled.connect(self._on_imposition_enabled_toggled)
        panel.whole_rotate_delta.connect(self._on_imposition_whole_rotate)
        panel.item_rotation_edited.connect(self._on_imposition_item_rotate)
        panel.reset_requested.connect(self._on_imposition_reset_layout)
        # 「新增图片」（单图页才出现）/「删除选中图片」（选中图才出现的按钮）
        panel.add_image_requested.connect(self._on_imposition_add_image)
        panel.item_delete_requested.connect(self._on_imposition_delete_item)
        panel.clear_requested.connect(self._on_imposition_clear)
        self.imposition_panel = panel
        # 既有控制器/自测沿用的宿主别名（控件实体在 panel 里）
        self.imposition_enabled_checkbox = panel.enabled_checkbox
        self.imposition_panel_status = panel.status_label
        return panel
    def _build_control_card(self) -> QWidget:
        card = Card(padding=T.SPACE_MD, spacing=T.SPACE_MD, radius=T.RADIUS_MD)
        column = card.box

        self.control_stack = QStackedWidget()
        # ⚠️ **四个阶段面板全部惰性**（2026-09-25 用户要求：进详情只建第一步，
        # 第 2/3/4 步"谁进去谁才建"）。面板构造是纯 Qt + Python 密集活：第四步
        # print_panel 单项就 ~150ms（空闲机器），是详情页构造的大头；而机器若
        # 正在跑导入后台（PyMuPDF 连续攥 GIL），同样的代码会被拖成 ~2 秒。
        # 用户可能整场都不点某一步，不该为它买单。
        # 接线一律走 LazyPanelHost 的 created 回调（hooks），**绝不在构造期
        # 直接 `widget(i)` 取面板**——属性转发会立刻把它建出来，惰性就白做了。
        _HOOKS = {
            "detect": self._wire_detect_panel,
            "print": self._wire_print_panel,
        }
        # ⚠️ 接线**按步骤 key**，不按 ``PANEL_CLASSES`` 的下标：那张元组与
        # ``FLOW_STAGES`` 同序（都由 ``SPECS`` 的 ``role=="stage"`` 派生），
        # 下标在这里只是巧合——``SPECS`` 前面插一个 stage，钩子会**集体
        # 错位一格**（detect 的联动刷新接到 rembg 上），且没有任何报错。
        for index, panel_class in enumerate(PANEL_CLASSES):
            key = FLOW_STAGES[index] if index < len(FLOW_STAGES) else None
            # ⚠️ dict.get(None) 运行时合法（返回 None）；这里显式判空语义相同
            hook = _HOOKS.get(key) if key is not None else None
            self.control_stack.addWidget(
                LazyPanelHost(panel_class, hooks=[hook] if hook else [])
            )
        # 拼版伪步骤（追加在主链之后）：占位详情面板——只在流程条点了虚线节点时
        # 显示，不属于任何真实阶段（STAGES/runs 机制不感知它）
        self.control_stack.addWidget(self._build_imposition_panel())
        column.addWidget(self.control_stack, 1)
        # 第二步右侧的「检测结果统计」：只在 detect 阶段显示（见 _select_stage），
        # 位置就是其它步骤「执行记录」的那块——执行记录对 detect 无用（无表单
        # 参数可回填，用户 2026-09-29 定），这一步改显统计。
        self.detect_stats = DetectStatsWidget()
        self.detect_stats.page_clicked.connect(self._goto_stats_page)
        self.detect_stats.hide()
        column.addWidget(self.detect_stats)
        # 边距级联的挂起值：print 面板还没建时先把当前值记下来（见
        # _sync_print_margin_default 与 _wire_print_panel）
        self._pending_print_border = None
        self._sync_print_margin_default()
        # 第四步面板建好时补「按源 PDF 名派生默认 PDF 名/古籍名」：set_task 只
        # 记下 _pending_source_stem，**不强制构造面板**（见 page.set_task）
        print_host = self.panel_host_of_step("print")
        if print_host is not None:
            print_host.add_created_hook(self._apply_pending_source_defaults)
            # 同理补「切任务时挂起的第四步状态复位」
            self._pending_print_reset = False
            print_host.add_created_hook(self._apply_pending_print_reset)

        column.addWidget(Divider())
        self._build_history_controls(column)
        column.addWidget(Divider())
        self._build_run_controls(column)
        # 「导出YOLO标注」：右栏**最底部**的独立入口，
        # 只在 detect 步骤 + YOLO 开关打开时出现（用户 2026-10-16）
        column.addWidget(self._build_yolo_export_card())

        # 控制面板限宽：参数表单需要舒适宽度，第四步 YAML 编辑器尤甚
        self.control_widget = card
        self._apply_control_width()
        return self.control_widget

    def _build_yolo_export_card(self) -> Card:
        """右栏最底部的「导出YOLO标注」。

        与模块页那一侧同一条业务链（``DetectMixin.export_yolo_labels``），
        只是**宿主不同**：卡片摆在详情页控制列末端，显隐由
        ``DetectMixin._sync_yolo_export_card`` 按"当前是不是 detect 步骤 +
        YOLO 开关"决定。
        """
        card = Card(padding=T.SPACE_SM, spacing=T.SPACE_XS, radius=T.RADIUS_SM)
        card.box.addWidget(SectionTitle("YOLO 标注"))
        self.yolo_export_button = PushButton(FIF.TAG, "导出YOLO标注")
        self.yolo_export_button.setFixedHeight(34)
        self.yolo_export_button.setToolTip(
            "把本任务的页面导出成 YOLO 训练数据集切片（点它先弹窗填名称、"
            "选导出目录）：\n"
            "<导出目录>/<名称>/images/<名称>-1.jpg（按页序复制原图）\n"
            "<导出目录>/<名称>/labels/<名称>-1.txt（同页的框）\n"
            "没有框的页面写空标签（负样本）。"
        )
        self.yolo_export_button.clicked.connect(self.export_yolo_labels)
        card.box.addWidget(self.yolo_export_button)
        self.yolo_export_card = card
        card.setVisible(False)
        # 显隐与配置订阅交给 DetectMixin（它才知道"当前是不是 detect 步骤"）
        self._wire_yolo_export_card()
        return card

    def _wire_detect_panel(self, detect_panel) -> None:
        """第二步面板**首次构造后**的接线（LazyPanelHost 的 created 回调）。"""
        # ⚠️ 2026-10-22：**area 参数已从整个项目移除**，所以这里没有
        #    「改 area → 重算参考框/提交按钮」这条联动。
        # 「识别方式」（**任务级**参数，2026-11-16）：人工标注不调 YOLO ⇒
        # 底部「检测文本框」主按钮不显示、提交门槛也不同，切一下要立刻反映。
        detect_panel.mode_changed.connect(self._on_detect_mode_changed)
        detect_panel.reuse_prev_changed.connect(self._on_reuse_prev_changed)
        # 控件建出来时的框编辑口径：实时预览被关掉编辑时，退出时要还原成它
        self._detect_boxes_editable = bool(
            getattr(self.detect_viewer, "show_boxes", True)
        )
        # 人工干预：选中框类型（左框/右框/整幅）与删除选中框
        detect_panel.box_kind_changed.connect(self._set_selected_box_kind)
        detect_panel.delete_box_requested.connect(self._delete_selected_box)
        # 预览里点/删/画框会改变选中态 → 回填面板的「选中框类型」高亮
        self.detect_viewer.selection_changed.connect(self._on_box_selection_changed)
        # 超框数上限（整幅 1 个 / 半幅 2 个）时给出可操作的提示
        self.detect_viewer.box_edit_rejected.connect(self._on_box_edit_rejected)
        # 手绘的框太小 → 不入库，并即时说明（用户 2026-11-16）
        self.detect_viewer.box_too_small.connect(self._on_box_too_small)

    def _sync_detect_mode_ui(self) -> None:
        """按识别方式显示/隐藏底部「检测文本框」主按钮（人工标注**不显示**它）。

        用户 2026-11-16 第 2 条：「人工标注模式的时候不显示『检测文本框』按钮，
        只显示『提交本次任务』按钮」。

        ⚠️ **只有第二步、且当前任务是人工标注时才藏**；其它步骤一律恢复显示
        ——否则在人工标注任务里切到第三步，那颗主按钮会一直是灰的/不见，
        整个流程就没法往下走了（它是每一步的"执行"按钮）。

        ⚠️ 走 ``_detect_manual()``（DetectMixin，内部 ``peek()`` 读面板）：
        这里绝不直接访问面板控件——``panel_host_of_step`` 拿到的是惰性宿主，
        属性访问会把面板立刻构造出来。
        """
        button = getattr(self, "run_button", None)
        if button is None:
            return
        on_detect = False
        if getattr(self, "task_id", None):
            try:
                on_detect = self.current_stage() == "detect"
            except Exception:  # noqa: BLE001 - 构造期没有步骤条，按"不在第二步"
                on_detect = False
        manual = on_detect and self._detect_manual()
        button.setVisible(not manual)

    def _wire_print_panel(self, panel) -> None:
        """第四步面板**首次构造后**的接线（LazyPanelHost 的 created 回调）。"""
        # 参数变化 → 效果预览按新参数重画（只是重画内存位图，不执行、不提交、
        # 不生成 PDF）。防抖 250ms：边距/颜色是逐字符输入，每次都重载一遍大图
        # 会明显卡顿。
        self._print_preview_timer = QTimer(cast("QObject", self))
        self._print_preview_timer.setSingleShot(True)
        self._print_preview_timer.setInterval(250)
        self._print_preview_timer.timeout.connect(self.print_preview.refresh_display)
        panel.params_changed.connect(self._print_preview_timer.start)
        # 补一次"面板还没建时"挂起的边距级联
        try:
            panel.set_upstream_border(getattr(self, "_pending_print_border", None))
        except Exception:
            pass

    def _print_params(self) -> dict:
        """第四步打印参数（供「打印效果」预览）：直接读面板表单。

        颜色/边距填到一半时 ``get_args()`` 会抛 ValueError，这里**不吞**——
        由 ``PrintPreviewWidget`` 捕获后退回「原图」并在说明行给出原因，
        避免用户每敲一个字符就弹窗。
        """
        host = self.panel_host_of_step("print")
        if host is None:
            # 本流程没有「PDF排版」这一格：没有表单可读（调用方会把预览退回
            # 「原图」，不该拿别的面板的参数冒充打印参数）
            raise ValueError("当前流程里没有「PDF排版」这一步")
        return host.get_args()

    def _apply_pending_source_defaults(self, panel: Any = None) -> None:
        """把「当前任务的源 PDF 名」派生的默认值补给第四步面板。

        ⚠️ 面板是惰性的：``set_task`` 只记下 ``_pending_source_stem``，真正应用
        由本方法负责——面板已建就立刻用，没建就等 created 回调在它建好时调用。
        """
        stem = getattr(self, "_pending_source_stem", None)
        if not stem:
            return
        if panel is None:
            host = self.panel_host_of_step("print")
            if host is None:
                return
            peek: Any = getattr(host, "peek", None)
            panel = peek() if callable(peek) else host
        if panel is None:
            return
        try:
            panel.set_source_defaults(stem)
        except Exception:  # noqa: BLE001 - 面板版本差异不该影响进任务
            pass

    def _apply_pending_print_reset(self, panel: Any = None) -> None:
        """清掉第四步面板上「属于上一个任务」的已应用参数快照。

        ⚠️ 为什么需要（2026-09-26 审计）：`print_panel._last_applied` 是「放弃本次
        修改」的回填源。切任务时不清，在任务 B 点「放弃本次修改」会把**任务 A 的
        参数**（含 A 派生的 pdf_name / title_text）回填进 B 的表单，后续可能用 A 的
        名字生成 B 的 PDF。

        与 `_apply_pending_source_defaults` 同一套惰性惯例：`set_task` 只置
        `_pending_print_reset`，**不强制构造面板**；面板已建就立刻清，没建就等
        它被建出来时由这里的 created 回调清。
        """
        if not getattr(self, "_pending_print_reset", False):
            return
        if panel is None:
            host = self.panel_host_of_step("print")
            if host is None:
                return
            peek: Any = getattr(host, "peek", None)
            panel = peek() if callable(peek) else host
            if panel is None:
                return  # 还没建：留着标记，等 created 回调
        try:
            panel._last_applied = None
        except Exception:  # noqa: BLE001 - 面板版本差异不该影响切任务
            return
        self._pending_print_reset = False

    def _sync_print_margin_default(self) -> None:
        """把「上游有没有留白」告诉第四步面板（决定它默认边距是 0 还是 20）。

        ⚠️ 2026-10-22：上游（去底色）**已经没有 border 了**——按框裁图归第二步
        的「分割图片」，那里固定不加留白（第四步会在纸上重新排版）。
        所以这里恒传 ``None``：第四步保持自己的默认边距（20mm），不再有
        "上游留白 + 页面边距"双重留白的级联分支。

        保留这个方法（而不是删掉调用点）是因为它同时负责**挂起值**：
        第四步面板还没构造时先把值记住，建好后由 ``_wire_print_panel`` 补同步。
        """
        border = None
        host = self.panel_host_of_step("print")
        if host is None:
            return
        peek: Any = getattr(host, "peek", None)
        panel: Any = peek() if callable(peek) else host
        if panel is None:
            # 第四步面板还没构造：先记住，等它建好时由 _wire_print_panel 补同步。
            self._pending_print_border = border
            return
        try:
            panel.set_upstream_border(border)
        except Exception:
            pass

    def _on_print_layout_changed(self, index: int, rect: list) -> None:
        """版面编辑器改了某页坐标：落盘 print.json 并标脏，提示可重新生成 PDF。

        落盘走 ``_save_print_order``（直接序列化当前条目，rect 已随条目携带），
        下次点「生成PDF」时 runner 会从 print.json 收集 page_rects 注入生成。
        """
        if not self.task_id:
            return
        self._save_print_order(silent=True)  # 拖拽频繁落盘，不打列表日志
        self._print_dirty = True
        # 与"上游已重跑"共用同一套产出（文案 + 警示色），避免两处各写一份；
        # 下一次 _refresh_stage_views 也由 _regenerate_notice 把它重新显出
        self._set_stage_status("● 版面已修改，点击「生成PDF」生效", alert=True)
        rx, ry, rw, rh = (list(rect) + [0, 0, 0, 0])[:4]
        self.log_view.append(
            f"第 {index + 1} 页版面已更新（x={rx:.0f}, y={ry:.0f}, "
            f"w={rw:.0f}, h={rh:.0f} mm），点击「生成PDF」生效"
        )
