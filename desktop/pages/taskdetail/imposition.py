# -*- coding: utf-8 -*-
"""任务详情页的「图片拼版」共享基元与 Mixin 装配。

流程条上的「图片拼版」是**虚线可选节点**（``desktop.components.step_bar``）。
它牵涉**三个判据，各管一件事、互不替代**（2026-10-05 逐层查证业务流程后定）：

1. **在不在流程里** ← **本任务的流程图**。图上画了「图片拼版」就有这一格
   （:meth:`ImpositionBaseMixin._imposition_node_visible`）。
2. **这一步有没有意义** ← **第三步的「区域模式」``area``**。这是**业务前提**
   而不是显示开关：流程里**有检测数据**时（「检测文本框」在去底色上游），
   ``area=1``「左右分开」让每个文本框产出**成对的两张**半页图
   （``-l`` / ``-r``），两张并排才拼得出古籍的正刊对开版面；``area=2/3``
   输出并集整图、``area=4`` 输出整页，**本来就是一张图**。而流程里**没有
   检测数据**时（去底色不在流程里，或它自己就是入口拿不到框——判据
   ``desktop.steps.ports.detect_feeds_rembg``），拼版吃**整图**照样拼：
   整幅单独一页、手动任意两张一页——「拼版作为第一个节点，也不需要
   detect 数据」（用户 2026-10-07）。见 :meth:`_imposition_area_ok`。
3. **要不要真跑** ← **拼版面板底部的开关**（:meth:`imposition_active`
   只看勾没勾，那是"用户意图"）。开关在 ①②不满足时**置灰并写明原因**。

⚠️ **别把 ② 当成"显示开关"扔掉**（本轮曾误判过一次）：它决定"拼版这一步
在当前参数下有没有意义"。``area`` 的其余取值与它无关，只管去底色怎么裁。

按操作逻辑拆成三个文件（后续可由不同 agent 分头维护，互不影响）：

- **本文件** ``ImpositionBaseMixin``：两个模块都要用的**共享基元**——
  节点可见性（查流程图）、区域模式读取（拼版的适用前提）、
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
from desktop.utils.files import list_stage_images
from utils.sort_utils import natural_sort_key

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStackedWidget, QWidget
    from desktop.components.detect_stats import DetectStatsWidget
    from desktop.components.step_bar import StepBar
    from desktop.store.store import TaskStore

#: 拼版的**业务前提**：只有「左右分开」才产出成对的半页图（``-l``/``-r``），
#:: 两张并排才拼得出正刊对开版面。
#:
#: ⚠️ 这**不是**"要不要显示拼版节点"的开关（那由流程图决定），而是"这一步在
#: 当前参数下**有没有意义**"。``area=2/3`` 输出并集整图、``area=4`` 输出整页，
#: 本来就是一张图，拼版没意义——旧代码拿它当显示条件，2026-10-05 一度被误删。
IMPOSITION_AREA = 1

#: 区域模式各值的中文名（"为什么不能拼版"的提示用，勿另写一份）
AREA_LABELS: dict[int, str] = {
    1: "左右分开",
    2: "合并单图",
    3: "整页合并",
    4: "整页/不检测",
}


def _as_area(value) -> int:
    """任意来源的 area 值 → 合法整数（非法/缺失返回 0 = "还不知道"）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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

        ⚠️ 2026-10-05 口径变更（用户要求）：原先看第三步的 ``area``
        （``area == 1`` 就显示）。那是流程图还不存在时的权宜之计，既
        **语义错配**（``area=1`` 是"每个框各自外扩产出多张图"，属裁剪方式），
        又与用户画的图**打架**（图上把「图片拼版」删了、area 还是 1，那一格
        照样冒出来）。现在**流程图是唯一真源**：图上画了就有这一步。

        实现上直接复用 :meth:`bar_index_of_step`（它查 :meth:`flow_slots`），
        因而与步骤条、与 ``store.task_slots()`` **必然同源**——不可能出现
        "流程条上没有、详情却能切进去"这类不同步（那正是旧的
        区域模式判据与流程槽位各算一套时的隐患）。

        宿主判"记录的步骤 key 还能不能匹配"（``page.py::_stage_index_of``）
        也走这里，两处同源。
        """
        return self.bar_index_of_step(IMPOSITION_STAGE) is not None

    # ------------------------------------------------------------- 区域模式
    def _imposition_rembg_node(self) -> str | None:
        """喂给**当前拼版节点**的「图片去底色」节点 id（按连线回溯）。

        ⚠️ area/border 这类"上游参数"必须按**喂我的那个节点**读（B 方案）：
        同一步骤可以有多个「图片去底色」，第二个拼版节点连的是第二个去底色
        节点——读主节点的参数等于"用户没填过的那份表单"。

        ``node_supplier`` 在"图说不清"时会退回**阶段名**（``rembg_submit``，
        同格多动作折过），那种情况退回该阶段的主节点。

        ⚠️ 这里**绝不能**传 ``self.imposition_effective()``：那条判据自己就要问
        ``_rembg_area_value()``（本函数的调用者），传进去就是
        ``_rembg_area_value → _imposition_rembg_node → imposition_effective →
        _imposition_area_ok → _rembg_area_value`` 无限递归（2026-10-17 实测
        RecursionError：任务列表点开详情直接炸）。"谁喂我"本来就与拼版开关无关，
        传 ``False`` 即可。
        """
        if not self.task_id:
            return None
        node = self.node_of_stage("imposition")
        if not node:
            return None
        ref = self.store.node_supplier(
            self.task_id, node, "pages", imposition_active=False
        )
        if not ref:
            return None
        if self.store.node_stage_of(self.task_id, ref) == "rembg":
            return ref
        return self._stage_primary.get("rembg")

    def _rembg_area_value(self) -> int:
        """当前**已知**的「区域模式」``area``；没有任何依据时返回 0。

        优先级：第三步面板当前值 > 暂存（``drafts/rembg.json``）> 最近一次
        执行参数——与 ``HistoryMixin._restore_stage_params`` 同源。

        ⚠️ 面板未构造时**只读盘上数据**，绝不能走 ``LazyPanelHost`` 的属性
        转发——那会把面板整个建出来，"谁进去谁才建"就白做了。

        ⚠️ 返回 0 = **还不知道**（全新任务没配过 / 没跑过），**不等于
        "不支持拼版"**：三态判据里它走"请先确认区域模式"那条提示。
        """
        host = self.panel_host_of_step("rembg")
        # ⚠️ 流程里没有「图片去底色」这一格时 ``host`` 是 ``None``：没有任何
        #    area 依据，直接往下走暂存/历史（自定义流程把去底色删掉是合法的）。
        #    绝不能兜一个别的面板——那是"用户没填过的表单"。
        peek: Any = getattr(host, "peek", None)
        panel: Any = peek() if callable(peek) else None
        if panel is not None:
            try:
                value = _as_area(panel.area.currentData())
            except Exception:  # noqa: BLE001 - 面板半构造时不该拖垮流程条
                value = 0
            if value:
                return value
        if self.task_id:
            # ⚠️ 暂存/历史按**喂我的那个去底色节点**读（B 方案）
            node = self._imposition_rembg_node()
            scope = self._node_scope(node)
            draft = self.store.load_draft(self.task_id, "rembg", **scope) or {}
            value = _as_area(draft.get("area"))
            if value:
                return value
            history = (
                self.store.list_node_runs(self.task_id, node, "rembg")
                if node
                else self.store.list_stage_runs(self.task_id, "rembg")
            )
            if history:
                value = _as_area((history[0].get("parameters") or {}).get("area"))
                if value:
                    return value
        return 0

    def _flow_has_detect_data(self) -> bool:
        """本流程里「图片去底色」**能不能拿到检测框**（判据唯一处：
        :func:`desktop.steps.ports.detect_feeds_rembg`）。

        没任务（静态展示，理论上不会走到拼版开关）按**默认流程**算——
        默认流程里有「检测文本框」。
        """
        task_id = getattr(self, "task_id", None)
        if not task_id:
            return True
        from desktop.steps.ports import detect_feeds_rembg

        return detect_feeds_rembg(self.store.task_diagram(task_id))

    def _imposition_area_ok(self) -> bool:
        """当前区域模式**支持拼版**（``area == 1``「左右分开」）。

        ⚠️ 分两种情形（用户 2026-10-07）：

        - 流程里**有检测数据**（「检测文本框」在去底色上游）→ 仍要求
          ``area == 1``：只有左右分开才产出成对的 ``-l``/``-r`` 半页图，
          两张并排才拼得出正刊对开版面。**0（还不知道）不算支持**：全新
          任务没配过区域模式时，先让用户去第三步确认。
        - **没有检测数据**（去底色不在流程里，或它自己就是入口拿不到框，
          此时它的 area 也被锁成 4）→ 拼版吃**整图**照样拼：整幅单独一页、
          手动任意两张一页——「拼版作为第一个节点，也不需要 detect 数据」，
          area 前提不再适用。
        """
        if not self._flow_has_detect_data():
            return True
        return self._rembg_area_value() == IMPOSITION_AREA

    def _imposition_switch_state(self) -> tuple[bool, str]:
        """「在流程中启用图片拼版」开关的**可用性与原因**（三个判据合成）。

        返回 ``(可用, 原因)``，可用时原因为空串。三条判据见模块头：

        1. **图里没有**「图片拼版」⇒ 勾了也不跑（它压根不在执行链里）；
        2. **区域模式还没确认** ⇒ 先去第三步确认（这是拼版的业务前提）；
        3. **区域模式不是「左右分开」** ⇒ 每页已经是一张整图，拼版没意义。

        ⚠️ 2/3 只在流程里**有检测数据**时适用：没有检测数据（去底色不在
        流程里 / 它自己就是入口）时拼版吃整图照样拼，直接放行。

        ⚠️ 处置是**置灰 + 说明**，不是隐藏：用户要看得见"流程里有这一步，
        但当前参数下用不上"，才知道该去改参数还是改流程图。旧实现是
        "``area != 1`` 就不显示"，用户报过"改了 area 节点凭空消失"。
        """
        if not self._imposition_node_visible():
            return False, (
                "当前流程里没有「图片拼版」这一步，勾了也不会生效"
                "（可在页头「查看 / 编辑流程」里把它加回来）"
            )
        if not self._flow_has_detect_data():
            # 没有检测数据（去底色不在流程里 / 它自己就是入口）：拼版吃
            # 整图照样拼，area 前提不适用（见 _imposition_area_ok）
            return True, ""
        area = self._rembg_area_value()
        if area == 0:
            return False, (
                "先到第三步「图片去底色」确认区域模式"
                "（「左右分开」才需要拼版），再回来启用"
            )
        if area != IMPOSITION_AREA:
            return False, (
                f"当前区域模式是「{AREA_LABELS.get(area, area)}」，"
                "每页已经是一张整图，不需要拼版"
            )
        return True, ""

    def imposition_effective(self) -> bool:
        """拼版这一步**当前能不能真跑**（三个判据全过）。

        与 :meth:`imposition_active`（"用户意图：勾没勾"）**刻意分开**：
        勾了但流程图里没这一步、或区域模式不支持，都**不会**真跑。取图来源
        认这个，步骤条"生效态"也认这个。
        """
        return (
            self._imposition_node_visible()
            and self._imposition_area_ok()
            and self.imposition_active()
        )

    def _sync_imposition_step_bar(self) -> None:
        """把拼版节点三态（可见/已选择/生效）**按节点**同步到流程条。

        ⚠️ **流程条上这一格表达的是"这一步处理到哪了"**（2026-10-18 用户口径：
        「第一个拼版已经运行过 → 高亮；第二个还没到那一步 → 不高亮」）：判据是
        **这个节点自己有没有拼版页**（``drafts/imposition[~<节点>].json`` 的
        ``pages``）——它才等于"运行过"。**不能**拿「在流程中启用图片拼版」开关
        当判据：那是**流程级**条件（流程图上那个「是否拼版」网关问的就是它，
        状态机的 ``imposition`` 标志也只有一份），勾了它对同一步骤的每个节点
        都成立，用它会让没拼过版的节点也亮起来（用户 2026-10-18 前一条报障：
        "操作了其中一个，另一个也仿佛已经被处理过了，其实没有"）。

        有页 ⇒ 节点显示「已选择」+ 绿色对勾、两侧连接线点亮；
        没页 ⇒ 「未选择」+ 灰色「＋」、连接线灰虚线、「去底色 → PDF排版」走
        节点上方绕行线（等于"这一支还没产出东西"）。
        """
        visible = self._imposition_node_visible()
        self.step_bar.set_imposition_visible(visible)
        self._sync_imposition_nodes()
        self._sync_imposition_switch(visible)

    def _sync_imposition_nodes(self) -> None:
        """逐节点刷流程条上每个可选拼版节点自己的状态（B 方案，2026-10-18）。

        ``selected``/``active`` 同取**该节点有没有拼版页**：同一步骤有两个
        「图片拼版」时各算各的，互不替代。
        """
        if not self.task_id:
            # 无任务（构造期静态展示）：全部按未选择、未生效。
            self.step_bar.set_imposition_selected(False)
            self.step_bar.set_imposition_active(False)
            return
        for bar_index in self.step_bar.optional_bar_indices:
            done = self._imposition_has_pages_of(self.node_at_index(bar_index))
            self.step_bar.set_imposition_node_state(
                bar_index, selected=done, active=done,
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
        # 保持"勾着但灰着"——用户改回支持拼版的区域模式就自动恢复生效，
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

        ⚠️ ``imposition_effective`` 传的是**图里有没有这一格 + area 前提**，
        不是"用户勾没勾"：这一格不存在时下方控件整体是置灰的，不该因为
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
                # ⚠️ 传"能不能真跑"而不是"勾没勾"：区域模式不支持（或图里没这一格）
                #    时不该取拼版产物——历史脏数据（先勾了、后来改了区域模式）会
                #    让第四步去读一个根本不该用的目录。
                imposition_active=self.imposition_effective(),
            )
        )
        # 连线表永远给得出路径（rembg_submit 是 print 的静态上游），
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
        # ⚠️ 藏**整行**（action_row =「生成预览 + 提交本次任务」并排），不是
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
        # 页面缩略图实体的管理者：清空内存态（旧任务的位图/排队页不能带进
        # 新任务）；目录切换交给下次刷新时的访问器判等（实体按内容签名寻址，
        # 目录不换就不会拿旧任务的实体）
        mgr = getattr(self, "_page_thumb_mgr", None)
        if mgr is not None:
            mgr.reset()
        # 新任务的取图来源未必和上个任务一样：让 _refresh_print_source 重新判定
        self._print_source_cache = None
        self._refresh_imposition_view()
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(0 if view.pages() else -1)
        self._update_imposition_status(view.current_index() if view is not None else -1)

    def _refresh_print_source(self) -> None:
        """第四步取图来源变了：让待打印列表跟上（拼版 ↔ 去底色 切换时用）。

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
        source = str(self.print_source_dir())
        if getattr(self, "_print_source_cache", None) == source:
            return
        if self.preview_stack.currentIndex() != self.stack_index_of_step("print"):
            self._print_source_cache = None
            # 第四步不可见：状态行/主按钮高亮留给进第四步时的那次刷新
            return
        self._print_source_cache = source
        try:
            entries, _doc = self._print_entries()
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
