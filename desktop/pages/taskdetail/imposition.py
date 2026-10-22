# -*- coding: utf-8 -*-
"""任务详情页的「图片拼版」共享基元与 Mixin 装配。

流程条上的「图片拼版」是**虚线可选节点**（``desktop.components.step_bar``）。
它牵涉**两个判据，各管一件事、互不替代**（2026-10-05 逐层查证业务流程后定，
2026-10-22 移除 area 后简化为两条）：

1. **在不在流程里** ← **本任务的流程图**。图上画了「图片拼版」就有这一格
   （:meth:`ImpositionBaseMixin._imposition_node_visible`）。
2. **要不要真跑** ← **拼版面板底部的开关**（:meth:`imposition_active`
   只看勾没勾，那是"用户意图"）。开关在 ① 不满足时**置灰并写明原因**。

⚠️ 2026-10-22 起 **area 概念彻底移除**：检测文本框后永远逐框裁图，
半幅页天然产出成对的 ``-l`` / ``-r``，拼版不再需要"区域模式 = 左右分开"
这个业务前提；没有检测步骤时拼整图照样能拼。

按操作逻辑拆成三个文件（后续可由不同 agent 分头维护，互不影响）：

- **本文件** ``ImpositionBaseMixin``：两个模块都要用的**共享基元**——
  节点可见性（查流程图）、
  拼版文档读写（``drafts/imposition.json``）、
  源图清单与「拼版生效」判定、第四步取图切换（``print_source_dir``）、
  视图灌装、详情进出与切任务复位；
- **``imposition_pages.ImpositionPagesMixin``**（模块一「选择拼版」）：
  启用开关、弹窗加页、删页/页序/清空；
- **``imposition_layout.ImpositionLayoutMixin``**（模块二「拼版操作」）：
  旋转/复位、版面落盘、防抖后台合成、状态行。

⚠️ 拼版本身**不是** STAGES 里的一步：runs.json / 阶段面板机制一概不感知它，
执行按钮组在拼版详情里整组隐藏。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.pages.taskdetail.imposition_layout import ImpositionLayoutMixin
from desktop.pages.taskdetail.imposition_pages import ImpositionPagesMixin
from desktop.store import IMPOSITION_LABEL, IMPOSITION_STAGE
from desktop.utils.files import dir_content_signature, list_stage_images
from utils.sort_utils import natural_sort_key

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStackedWidget, QWidget
    from desktop.components.detect_stats import DetectStatsWidget
    from desktop.components.step_bar import StepBar
    from desktop.store.store import TaskStore


def _rect_of(entry: dict) -> list[float] | None:
    """条目的**逐页坐标**（mm）；没有就 ``None``。

    只服务"清单结构变了没有"的比对（见 ``_refresh_print_source``）：文件顺序一样
    但某页的坐标被换掉/失效时，也得走整列重建把新坐标灌进去。
    """
    rect = (entry or {}).get("rect")
    if rect is None:
        return None
    try:
        return [float(value) for value in rect[:4]]
    except (TypeError, ValueError):
        return None


class ImpositionBaseMixin:
    """拼版共享基元：节点可见性、文档读写、取图切换、详情进出。

    依赖宿主页面提供：store/task_id、control_stack、step_bar、
    _select_stage()、_set_stage_status()、_toast()、log_view。
    """

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法：Mixin 本体不持有，
        # 这里只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        step_bar: StepBar
        control_stack: QStackedWidget
        preview_stack: QStackedWidget
        action_row: QWidget
        followup_row: QWidget
        detect_stats: DetectStatsWidget
        history_block: QWidget
        bar_index_of_step: Callable[[str], int | None]
        node_of_stage: Callable[[str], str | None]
        #: 「去底色成品目录是否已提交」闸门（PrintListMixin 提供，见 print_list）
        rembg_source_committed: Callable[..., bool]
        #: 步骤条**格序** → 该格对应的**节点实例 id**（B 方案：逐节点刷状态用）
        node_at_index: Callable[[int], str | None]
        _node_scope: Callable[..., dict]
        _stage_primary: dict[str, str | None]
        step_at_index: Callable[[int], str | None]
        _rembg_step_index: Callable[[], int]
        _select_stage: Callable[[int], None]
        _set_stage_status: Callable[..., None]
        _apply_control_width: Callable[[], None]
        _refresh_stage_views: Callable[[], None]
        _refresh_stale_notices: Callable[[], None]
        _load_imposition_enabled: Callable[[], bool]
        _save_imposition_enabled: Callable[[bool], None]
        _schedule_imposition_compose: Callable[[], None]
        _refresh_imposition_page_thumbs: Callable[..., None]
        _drop_imposition_source_thumb: Callable[[str], None]
        _update_imposition_status: Callable[[int], None]
        close_imposition_zoom_popup: Callable[[], None]
        _current_print_pdf_path: Callable[[], Any]
        _print_entries: Callable[[], tuple]
        # ⚠️ 返回值是 LazyPanelHost 或真面板（属性转发、鸭子类型），用 Any 承接
        panel_host_of_step: Callable[[str], Any]
        stack_index_of_step: Callable[[str], int | None]

    # ------------------------------------------------------------- 节点可见性
    def _imposition_node_visible(self) -> bool:
        """拼版节点是否**在本任务的流程里**（判据唯一处：**流程图**）。

        ⚠️ 2026-10-05 口径变更（用户要求）：原本按「区域模式」显示，那是
        流程图还不存在时的权宜之计，与用户画的图**打架**（图上把「图片拼版」
        删了，那一格照样冒出来）。现在**流程图是唯一真源**：图上画了就有这一步。

        实现上直接复用 :meth:`bar_index_of_step`（它查 :meth:`flow_slots`），
        因而与步骤条、与 ``store.task_slots()`` **必然同源**——不可能出现
        "流程条上没有、详情却能切进去"这类不同步。

        宿主判"记录的步骤 key 还能不能匹配"（``page.py::_stage_index_of``）
        也走这里，两处同源。
        """
        return self.bar_index_of_step(IMPOSITION_STAGE) is not None

    # ------------------------------------------------------------- 拼版前提
    def _imposition_switch_state(self) -> tuple[bool, str]:
        """「在流程中启用图片拼版」开关的**可用性与原因**。

        2026-10-22 起只有一条判据：**图里有没有「图片拼版」**。检测文本框
        永远逐框裁图，半幅页天然成对（``-l``/``-r``），不再依赖 area。

        ⚠️ 处置是**置灰 + 说明**，不是隐藏：用户要看得见"流程里有这一步，
        但当前用不上"，才知道去改流程图。
        """
        if not self._imposition_node_visible():
            return False, (
                "当前流程里没有「图片拼版」这一步，勾了也不会生效"
                "（可在页头「查看 / 编辑流程」里把它加回来）"
            )
        return True, ""

    def imposition_effective(self) -> bool:
        """拼版这一步**当前能不能真跑**（节点在流程里 + 用户勾了）。

        与 :meth:`imposition_active`（"用户意图：勾没勾"）**刻意分开**：
        勾了但流程图里没这一步，**不会**真跑。取图来源认这个，步骤条
        "生效态"也认这个。
        """
        return (
            self._imposition_node_visible()
            and self.imposition_active()
        )

    def _sync_imposition_step_bar(self) -> None:
        """把拼版节点三态（可见/已选择/流向）**按节点**同步到流程条。

        「这一格处理到哪了」看**这个节点自己有没有拼版页**
        （``drafts/imposition[~<节点>].json`` 的 ``pages``；2026-10-18 用户口径：
        「第一个拼版已经运行过 → 高亮；第二个还没到那一步 → 不高亮」）。
        ⚠️ 这一条**不能**拿「在流程中启用图片拼版」开关当判据：那是**流程级**
        条件，勾了它对同一步骤的每个节点都成立，会让没拼过版的节点也亮起来
        （用户 2026-10-18：「操作了其中一个，另一个也仿佛已经被处理过了」）。

        「流程图走不走这一支」则**只看启用开关**（= 第四步从哪取图）。

        有页 ⇒ 节点显示「已选择」+ 绿色对勾（这一格处理过了）；
        **能真跑**（图里有这一格 + 启用开关勾着）⇒ 两侧连接线常规点亮、主线
        经过这一格；**不能真跑** ⇒ 连接线灰虚线、「去底色 → PDF排版」走节点
        上方绕行线——第四步取的是上一步的数据，图上就不该再经过拼版
        （用户 2026-10-23：「关闭在流程图中启用拼版……流程图节点经过了拼版，
        此时没有启用就不需要经过」）。

        ⚠️ 这两个判据**刻意分开**（``selected`` 按节点、``active`` 按"能不能真跑"）：
        「处理过没有」与「流程走不走这一支」是两件事——只用一个判据会把
        "有拼版页但没启用"画成经过拼版（2026-10-23 报障），或者把
        "启用了但还没拼页"画成已处理（2026-10-18 报障）。
        """
        visible = self._imposition_node_visible()
        self.step_bar.set_imposition_visible(visible)
        self._sync_imposition_nodes()
        self._sync_imposition_switch(visible)

    def _sync_imposition_nodes(self) -> None:
        """逐节点刷流程条上每个可选拼版节点的状态（B 方案，2026-10-18）。

        - ``selected``（节点徽标/副标题"已选择"）= **该节点自己有没有拼版页**：
          同一步骤有两个「图片拼版」时各算各的，互不替代；
        - ``active``（流向：连接线点亮 or 绕行）= **能不能真跑**
          （:meth:`imposition_effective`：图里有这一格 + 启用开关勾着）。它对应的
          正是"第四步从哪取图"，流程图必须跟着它走。
        """
        if not self.task_id:
            # 无任务（构造期静态展示）：全部按未选择、未生效。
            self.step_bar.set_imposition_selected(False)
            self.step_bar.set_imposition_active(False)
            return
        enabled = self.imposition_effective()
        for bar_index in self.step_bar.optional_bar_indices:
            done = self._imposition_has_pages_of(self.node_at_index(bar_index))
            self.step_bar.set_imposition_node_state(
                bar_index, selected=done, active=enabled,
            )

    def _imposition_has_pages_of(self, node_id: str | None) -> bool:
        """**指定拼版节点自己**有没有拼版页（= 这一步"运行过"没有）。

        单节点流程（默认流程与所有现存任务）下 ``node_id`` 就是主节点，读的
        仍是 ``drafts/imposition.json``——与改造前一致。
        """
        if not self.task_id:
            return False
        scope = self.store.scoped_file_scope(self.task_id, node_id)
        return bool(
            self.store.load_imposition_doc(self.task_id, **scope).get("pages")
        )

    def _sync_imposition_switch(self, _visible=None) -> None:
        """把三态判据的结果刷到拼版面板的启用开关上（可用性 + 原因）。

        判据本身在 :meth:`_imposition_switch_state`；这里只负责落到控件：

        - 置灰（``setEnabled(False)``）＋ tooltip 写明**为什么**——用户看到的是
          "这一步现在用不上以及为什么"，不是"勾了没反应"；
        - ``getattr`` 兜住"拼版面板还没构造"（``set_task`` 早期就调到这里）；
          ``enable_switch=False`` 的宿主（独立拼图页）没有这个开关，安全跳过。
        """
        checkbox = getattr(self, "imposition_enabled_checkbox", None)
        if checkbox is None:
            return
        usable, reason = self._imposition_switch_state()
        checkbox.setEnabled(usable)
        checkbox.setToolTip(
            "启用后「PDF排版」用拼版合成结果；不启用则从去底色直接出 PDF"
            if usable
            else reason
        )
        # ⚠️ **不取消勾选**（只在控件上取消会出现"控件未勾、盘上已勾"的
        # 不一致：blockSignals 挡住了落盘信号，下次刷新又会显示成勾）。
        # 保持"勾着但灰着"——把「图片拼版」加回流程图就自动恢复生效，
        # 这正是"条件决定是否生效"；tooltip 与步骤条的灰虚线+绕行线已经
        # 说明它现在不会跑。
        #
        # 反过来也要**回填**：盘上才是准的（可能被历史恢复、任务列表等其他
        # 入口改过），控件必须跟着走，否则会出现"盘上已勾、开关显示没勾"。
        want = self._load_imposition_enabled()
        if checkbox.isChecked() != want:
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(want))
            checkbox.blockSignals(False)
        # ⚠️ **红框引导**（2026-10-13 用户，两条件**缺一不可**）：
        # ① 开关**可用**且**没勾**——没勾才需要提醒去勾；
        # ② **左侧拼版页清单非空**（``imposition_has_pages``）——已经拼了页
        #    却没勾启用，框提醒"这些页 PDF排版用不上"；清单空白（还没拼任何
        #    页）时**不框**：此刻勾了也没东西可出，圈一个空提醒是噪声。
        from desktop.ui.widgets import set_red_frame

        frame_on = False
        if usable and not checkbox.isChecked():
            frame_on = self.imposition_has_pages()
        set_red_frame(checkbox, frame_on)

    def _refresh_imposition_node(self) -> None:
        """把拼版节点同步到流程条（可见性 + 选择态 + 生效态）。

        触发时机：切任务 / 切阶段（都经 ``_select_stage``）、**流程图保存后**
        （:meth:`FlowMixin._apply_flow_diagram`）。

        ⚠️ 可见性只看**流程图**（见 :meth:`_imposition_node_visible`），与第三步
        的参数无关——所以第三步面板参数变化**不再**触发这里。节点从流程里
        消失时，若用户正停在拼版详情上，退回第三步。
        """
        visible = self._imposition_node_visible()
        self._sync_imposition_step_bar()
        # ⚠️ 用格序反查判断"当前是不是停在拼版"（旧代码写死
        #    ``== IMPOSITION_INDEX``）：自定义流程里拼版的格序会变。
        if (
            not visible
            and self.step_at_index(self.step_bar._current) == IMPOSITION_STAGE
        ):
            self._select_stage(self._rembg_step_index())

    # ------------------------------------------------------------- 文档读写
    def _imposition_doc(self) -> dict:
        """**当前拼版节点**的拼版文档（含选择态与逐页版面）。

        ⚠️ 读写必须走**同一个**作用域（B 方案）：开关（``enabled``）与逐页版面
        （``pages``）都按节点存（``drafts/imposition[~<节点>].json``）。此前这个读法
        漏了作用域——写进副本节点的 122 页，读的却是主节点那份空文档 ⇒ 选完页
        「拼版窗口」里一张也不显示、左侧还停在「还没有拼版页」（用户 2026-10-17
        实测报障）。
        """
        if not self.task_id:
            return {"enabled": False, "pages": []}
        return self.store.load_imposition_doc(
            self.task_id, **self._imposition_scope()
        )

    def _imposition_pages(self, doc: dict | None = None) -> list[dict]:
        return list((doc or self._imposition_doc()).get("pages") or [])

    def _save_imposition_pages(self, pages: list[dict]) -> None:
        """把拼版页清单落盘（保持选择态不变）并刷新视图 + 重新合成。

        页数 0↔n 会翻转「生效」状态（流程条连线/绕行线跟着变），一并同步。
        """
        if not self.task_id:
            return
        # ⚠️ 版面按**节点**存（B 方案）：`enabled` 保持流程级那一份不动。
        scope = self._imposition_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["pages"] = [dict(page) for page in pages]
        self.store.save_imposition_doc(self.task_id, doc, **scope)
        self._sync_imposition_step_bar()
        self._refresh_imposition_view()
        self._schedule_imposition_compose()

    def _set_imposition_checked(self, on: bool) -> None:
        """程序化同步启用开关（blockSignals 避免回抛覆盖落盘值）。"""
        checkbox = getattr(self, "imposition_enabled_checkbox", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(on))
            checkbox.blockSignals(False)
        self._save_imposition_enabled(bool(on))
        self._sync_imposition_step_bar()
        if on:
            self._schedule_imposition_compose()
        self._refresh_print_source()
        self._update_imposition_status(
            getattr(
                getattr(self, "imposition_view", None), "current_index", lambda: -1
            )()
        )

    # ------------------------------------------------------------- 源图与生效
    def _imposition_scope(self) -> dict:
        """拼版**版面文档**的节点作用域（B 方案）：两个「图片拼版」节点各有
        自己的 ``drafts/imposition[~<节点>].json``（页面清单与逐页版面）。"""
        return self._node_scope(self.node_of_stage("imposition"))

    def _imposition_flag_scope(self) -> dict:
        """「在流程中启用图片拼版」这个**开关**的作用域：恒取拼版的主节点。

        ⚠️ 开关是**流程级条件**（流程图上那个「是否拼版」网关问的就是它；
        状态机的 ``imposition`` 标志没有节点上下文，见 ``store.scheduler_flags``），
        所以它只有一份、读写都走主节点的文件；**版面（pages）才是按节点分的**。
        在副本节点上勾选，改的仍是这一份——与"这个开关决定第四步取图来源"的
        既有语义一致。

        ⚠️ **流程条上那一格的"已选择/绿勾"不看这个开关**（2026-10-18）：那一格
        表达的是"这一步处理到哪了"，判据是**本节点有没有拼版页**
        （见 :meth:`_sync_imposition_nodes`）。开关只决定"第四步取不取拼版结果"。
        """
        return self._node_scope(self._stage_primary.get("imposition"))

    def _imposition_output_dir(self) -> Path:
        """**本节点**拼版成品的输出目录（``stages/imposition[~<节点>]``）。

        合成 worker 写这里、缩略图/编辑回写/新鲜度判定也读这里——按阶段取会让
        两个「图片拼版」节点互相覆盖成品页。
        """
        task_id = self.task_id
        if not task_id:
            return Path()
        return self.store.node_or_stage_output(
            task_id, self.node_of_stage("imposition"), "imposition"
        )

    def imposition_source_files(self) -> list[Path]:
        """可挑选的源图：**拼版这一步的 pages 端口**指向的目录。

        ⚠️ 此前这里写死 ``store.rembg_output_dir()``（＝``stages/rembg``）——
        那是**问输入却写成写死**：自定义流程把连线改了（或者压根没有去底色
        那一格）时，它会去读一个永远不会被产出的目录，于是「＋选择拼版」弹
        "没有可拼版的图片，请先提交本次任务"——而那一步压根不在流程里。
        现在与 :meth:`print_source_dir` 同构，走 ``store.stage_input``。

        ⚠️ ``imposition_effective`` 传的是**图里有没有这一格 + 用户勾没勾**，
        不是单独的"用户勾没勾"：这一格不存在时下方控件整体是置灰的，不该因为
        "还没勾" 就换一个别的取图来源。
        """
        if not self.task_id:
            return []
        # ⚠️ **按节点取图**（B 方案）：拼版这一步的源图跟着**当前拼版节点**的
        #    连线走——同一步骤多个节点时，按阶段取会读到主节点的上游（用户给
        #    第二个拼版节点连了另一批图，界面却列第一批）。
        node = self.node_of_stage("imposition")
        source = (
            self.store.node_input(
                self.task_id, node, "pages", imposition_active=self.imposition_effective()
            )
            if node
            else self.store.stage_input(
                self.task_id,
                "imposition",
                "pages",
                imposition_active=self.imposition_effective(),
            )
        ) or self.store.rembg_output_dir(self.task_id)
        files = list_stage_images(source)
        return sorted(files, key=lambda p: natural_sort_key(p.name))

    def imposition_active(self) -> bool:
        """拼版**是否已启用**（用户勾了「在流程中启用图片拼版」就是启用）。

        ⚠️ **只看勾没勾，不看有没有拼版页**（用户 2026-10-03 口径："如果启用了
        拼版，则最后一步生成 pdf 的数据来源就是拼版"）。早先这里额外要求
        "至少有一页"，于是勾了开关却还没拼页时——取图仍走去底色、流程条仍是
        灰虚线 + 绕行线，用户看到的就是"启用了却不生效"。「有没有拼版页」是
        另一件事（能不能真出东西），走 :meth:`imposition_has_pages`。

        ⚠️ 这是**流程级**的判据（决定第四步取图来源），开关只有一份、存在主节点
        那份 ``drafts/imposition.json`` 里（见 :meth:`_imposition_flag_scope`）。
        ⚠️ **流程条上每个拼版节点的"已选择/绿勾"不看它**（2026-10-18）：那一格
        表达"这一步处理到哪了"，判据是该节点自己有没有拼版页
        （见 :meth:`_sync_imposition_nodes`）。
        """
        task_id = getattr(self, "task_id", None)
        if not task_id:
            return False
        return self.store.step_enabled(task_id, "imposition")

    def imposition_has_pages(self) -> bool:
        """拼版文档里**至少有一页**版面（能不能真的合成出图）。

        与 :meth:`imposition_active` 分开：启用是**用户意图**（决定取图来源），
        有页是**当前进度**（决定要不要提示"还没拼版，PDF排版没有输入"）。
        """
        if not getattr(self, "task_id", None):
            return False
        return bool(self._imposition_doc().get("pages"))

    def print_source_dir(self) -> Path:
        """第四步的取图目录：拼版生效 → stages/imposition，否则 stages/rembg。

        ⚠️ 走的是 :mod:`desktop.steps.ports` 的**条件连线**（"print 的 pages
        端口由谁供给"），不是在这里 if/else 挑目录——BPM 换上游时只改连线表，
        这一行不用动。
        """
        task_id = self.task_id
        assert task_id is not None, "取图来源只在任务态被读取"
        # ⚠️ **按节点取图**（B 方案）：两个「PDF排版」节点各有自己的上游
        #    （可以一个吃去底色成品、另一个吃拼版成品），按阶段取会让两个节点
        #    都读同一个来源——面板说 A、执行做 B。
        node = self.node_of_stage("print")
        source = (
            self.store.node_input(
                task_id, node, "pages", imposition_active=self.imposition_effective()
            )
            if node
            else self.store.stage_input(
                task_id,
                "print",
                "pages",
                # ⚠️ 传"能不能真跑"而不是"勾没勾"：图里没这一格时不该取拼版
                #    产物——历史脏数据（先勾了、后来把节点删了）会让第四步去读
                #    一个根本不该用的目录。
                imposition_active=self.imposition_effective(),
            )
        )
        # 连线表永远给得出路径（rembg 是 print 的静态上游），
        # 但仍留一道兜底：将来若有人把静态上游摘掉，这里不该抛 AttributeError。
        return source or self.store.rembg_output_dir(task_id)

    # ------------------------------------------------------------- 视图刷新
    def _refresh_imposition_view(self) -> None:
        """把落盘的拼版文档灌进页面控件（左列清单 + 画布）。

        保留用户当前看的那一页；之前"没有页"（-1）而现在已经有了，就落到
        第一页——否则用户看不到刚加的那页（画布停在空纸）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        pages = self._imposition_pages()
        index = view.current_index()
        if index < 0 and pages:
            index = 0
        view.set_pages(pages, current=index)
        # 左列缩略图跟着页清单走（每页取"第一张源图"的缩略图；用户 2026-10-04
        # 报「任务流程里缩略图不显示、只有占位」——这条链此前从没喂过缩略图）
        self._refresh_imposition_page_thumbs(pages)

    # ------------------------------------------------------------- 拼版详情
    def _select_imposition_detail(self) -> None:
        """流程条点了「图片拼版」：预览区/控制区切到拼版详情。

        拼版没有可执行的子任务：执行/提交/继续/中断按钮整组隐藏，
        执行记录与检测统计也不适用。
        """
        self._refresh_imposition_view()
        view = getattr(self, "imposition_view", None)
        if view is not None and view.current_index() < 0 and view.pages():
            view.set_current(0)
        # ⚠️ 两个栈都按**页号**（``stack_index``）翻，不是步骤条格序：
        #    拼版节点在步骤条上插在它该在的位置，但栈里仍占"伪步骤"那一页。
        #    找不到（自定义流程删了拼版节点）就别动栈，交给调用方回退。
        page = self.stack_index_of_step(IMPOSITION_STAGE)
        if page is not None:
            self.control_stack.setCurrentIndex(page)
            self.preview_stack.setCurrentIndex(page)
        # ⚠️ 藏**整行**（action_row =「检测文本框 + 提交本次任务」并排），不是
        #    单个按钮：只藏按钮的话行高仍在，控制区底部会留一条空白。
        self.action_row.setVisible(False)
        self.followup_row.setVisible(False)
        self.detect_stats.setVisible(False)
        self.history_block.setVisible(False)
        self._set_stage_status(f"{IMPOSITION_LABEL}：可选节点（拼版版面）")
        self._apply_control_width()
        # 开关回填当前选择状态（blockSignals 避免回抛覆盖落盘值）
        checkbox = getattr(self, "imposition_enabled_checkbox", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(self._load_imposition_enabled())
            checkbox.blockSignals(False)
        self._update_imposition_status(view.current_index() if view is not None else -1)

    def _reset_imposition_state(self) -> None:
        """切任务：取消在飞合成、清忙标记，并把新任务的拼版文档灌进视图。"""
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            timer.stop()
        edit_timer = getattr(self, "_imposition_edit_timer", None)
        if edit_timer is not None:
            edit_timer.stop()  # 上一任务的旋转组件停顿提交别再落进新任务
        # 单页缩略图的重合成计时器同理：旧任务攒的页号不能落进新任务
        thumb_timer = getattr(self, "_imposition_thumb_timer", None)
        if thumb_timer is not None:
            thumb_timer.stop()
        self._imposition_thumb_dirty = set()
        # 预览弹窗里那页是上个任务打开时的快照，留着就是旧任务的图
        self.close_imposition_zoom_popup()
        self._imposition_dirty = False
        self._imposition_composing = False
        # 「上次落盘时的逐页签名」随任务清：新任务的版面与本任务无关，留着会让
        # "只重存变了的那几页"算错页（也会把本任务的成品误判成已最新）。
        # ⚠️ 真正的基线在**侧车文件**里（``drafts/imposition[~节点].composed.json``，
        #    跨会话有效）；这里清的是**内存缓存**，下次用到时按新任务重读。
        self._imposition_page_sigs = {}
        self._composed_sigs_cache = {}
        self._imposition_compose_doc = None
        self._imposition_compose_out_dir = None
        self._imposition_compose_sigs_path = None
        self._imposition_compose_doc_path = None
        self._imposition_compose_doc_mtime = None
        self._imposition_composed_pages = []
        # 页面缩略图实体的管理者：清空内存态（旧任务的位图/排队页不能带进
        # 新任务）；目录切换交给下次刷新时的访问器判等（实体按内容签名寻址，
        # 目录不换就不会拿旧任务的实体）
        mgr = getattr(self, "_page_thumb_mgr", None)
        if mgr is not None:
            mgr.reset()
        # 新任务的取图来源未必和上个任务一样：让 _refresh_print_source 重新判定
        self._print_source_cache = None
        # ⚠️ **不在这里灌拼版页清单**：``_refresh_imposition_view`` 会建 107 个页条
        #    控件 + 逐页缩略图实体（真实 GUI 实测 ~220ms），而落地步骤绝大多数
        #    是「图片去底色」——拼版页根本不可见，这笔钱纯属白付（用户 2026-10-21
        #    报"进详情要等 2~3 秒"）。这里只把视图清空（旧任务的页不能带进来），
        #    真进「图片拼版」时 ``_select_imposition_detail`` / ``_save_imposition_pages``
        #    会照常刷新。
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_pages([], current=-1)
            self._refresh_imposition_page_thumbs([])
        self._update_imposition_status(-1)

    def _print_source_mark(self) -> tuple:
        """第四步取图目录的**内容标记**：``(目录, 目录内容指纹)``。

        ``_print_source_cache`` 存的就是它。⚠️ 判据必须带上**内容指纹**而不是
        只比目录字符串：拼版成品重合成后目录一个字没变、内容全换了，只比路径
        会让后台合成的收尾回调（``_on_imposition_composed``）把这次变化当成
        "来源没换"直接跳过，第四步的待打印列表就永远停在旧图上——用户
        2026-10-18 报的「拼版图片发生变化，PDF排版不能实时更新」正是这一条。
        """
        directory = self.print_source_dir()
        return (str(directory), dir_content_signature(directory))

    def _print_source_mark_text(self) -> str:
        """第四步取图目录的**内容标记**（可落进 ``runs.json`` 的文本形态）。

        与 :meth:`_print_source_mark` **同一份判据**（目录 + 内容指纹），只是换成
        字符串好进执行记录：第四步据此回答"磁盘上那份 PDF 还是不是当前取图目录
        的产物"（``services.stale_chain.print_input_changed``）。
        """
        directory, signature = self._print_source_mark()
        return f"{directory}|{signature}"

    def _refresh_print_source(self, only_paths=None) -> None:
        """第四步取图来源变了：让待打印列表跟上（拼版 ↔ 去底色 切换、成品重存）。

        ``only_paths``：**这次刚被重存的那几张成品图**（拼版合成收尾时给出）。
        给了它、而且第四步的条目清单没变（同样的图、同样的顺序与逐页坐标）时，
        只就地刷新那几条（缩略图 + 当前页显示），**不整列重建**——否则每改一次
        拼版都会把整张待打印列表清掉重来、把用户正看的那一页翻回第一页
        （用户 2026-10-18：「那张图片变更……同时通知下一步要变更的图片」）。
        清单结构变了（页数/顺序/逐页坐标）时仍走整列重建（``set_entries``）。

        ⚠️ **只作废缓存，不在原地重建**（2026-09-30 用户报「开关拼版后顶部
        空白/卡住 2s 才恢复」）：重建 = 缩略条清空 + 几十条重建 +
        ``_select_entry(0)`` **在 UI 线程同步解码整张首图**——真实任务上
        冻结 1-2s，流程条的新状态（虚线/绕行线）也跟着画不出来。而本方法的
        触发点（启用开关、后台合成完成、自动启用）都发生在**拼版详情里**，
        那一刻第四步根本不可见：进第四步时 ``_refresh_preview`` 本来就会
        重建一次，不怕漏。只有第四步**正被看着**（比如开关后停在第四步等
        后台合成收尾）才当场重建，否则用户会一直盯着旧来源。

        另做两件**不重**的事（它们只动按钮/提示，不碰列表）：
        1. 重算"取图来源已换"缓存（``_print_source_stale``）——本方法是拼版开关
           变化的统一出口，缓存必须在这儿跟上，否则状态行还按旧来源显示提示；
        2. 同步下载按钮：来源一换，磁盘上那份 PDF 就是旧数据，得灭掉
           （用户 2026-10-03："旧的数据不显示"）。
        """
        # 缓存与按钮先无条件跟上（都很轻，不碰列表）
        try:
            self._refresh_stale_notices()
        except Exception:  # noqa: BLE001 - 判定失败不该拦住开关生效
            pass
        preview = getattr(self, "print_preview", None)
        if preview is None or not self.task_id:
            return
        try:
            preview.set_pdf_path(self._current_print_pdf_path())
        except Exception:  # noqa: BLE001 - 第四步尚未就绪时不该拖垮拼版页
            pass
        # ⚠️ 比对的是**内容标记**（路径 + 指纹，见 ``_print_source_mark``）：
        #    用目录字符串的话，"同一个目录、内容刚被重合成换掉"会被判成"没变"
        #    而跳过重建——用户 2026-10-18 报的就是这个（拼版成品变了，PDF排版
        #    的图还是旧的）。
        mark = self._print_source_mark()
        if getattr(self, "_print_source_cache", None) == mark:
            return
        if self.preview_stack.currentIndex() != self.stack_index_of_step("print"):
            self._print_source_cache = None
            # 第四步不可见：状态行/主按钮高亮留给进第四步时的那次刷新
            return
        self._print_source_cache = mark
        try:
            entries, _doc = self._print_entries()
            # 条目清单没变（同样的图、同样的顺序与逐页坐标）→ 只刷那几张：
            # 不整列重建、不动当前页、不重解整条缩略图条。
            current = [
                (str(e.get("file")), _rect_of(e)) for e in preview.entries()
            ]
            fresh = [(str(e.get("file")), _rect_of(e)) for e in entries]
            if only_paths and fresh == current:
                preview.refresh_paths(only_paths)
            else:
                preview.set_entries(entries)
            self._refresh_stage_views()
        except Exception:  # noqa: BLE001 - 第四步尚未就绪时不该拖垮拼版页
            self._print_source_cache = None
            return


class ImpositionMixin(ImpositionPagesMixin, ImpositionLayoutMixin, ImpositionBaseMixin):
    """「图片拼版」节点控制器 = 模块一（页管理） + 模块二（版面/合成） + 基元。

    方法查找顺序：模块一 → 模块二 → 共享基元；三个文件互不 import，
    只经 ``self`` 在组合后的宿主页面上协作。
    """


__all__ = ["ImpositionMixin", "ImpositionBaseMixin"]
