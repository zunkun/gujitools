# -*- coding: utf-8 -*-
"""拼版共享基元的**节点可见性**分片：节点是否在流程里、三态同步到流程条。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.store import IMPOSITION_STAGE

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition._host import ImpositionBaseHost
else:
    ImpositionBaseHost = object


class NodeVisibilityMixin(ImpositionBaseHost):
    """节点可见性、启用开关判据与步骤条三态同步。"""

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
