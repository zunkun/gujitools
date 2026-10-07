# -*- coding: utf-8 -*-
"""任务详情页的 BPM 流程入口（查看 / 编辑本任务流程）。

对应 ``docs/tasks/bpm.md``：

> 按照 bpmn 节点渲染节点……**同时可以修改 bpmn 节点**

## 数据流（2026-10-05 第二轮：bpmn 文件成为真源）

::

    tasks/<任务号>/flow.bpmn  ──读──>  FlowDiagram  ──渲染──>  弹窗
              ▲                             │
              └──────── 保存（原子写）───────┘

页面渲染的是**文件本身**（节点类型 + 坐标 + 折点都来自文件），所以用
bpmn.io 画的图进页面长得一样。

## 为什么是 Mixin

页头那个「查看/编辑流程」按钮的行为只跟"BPM 流程"有关（读 ``flow.bpmn``、
落盘、提示重进），跟页面其他职责（预览、打印、执行）都无关。单独一个 Mixin
保持 :class:`TaskDetailPage` 不再胖，也让这段逻辑能单独被自测实例化验证。

## ⚠️ 改完流程为什么不自动重建页面

⚠️ **这段取舍只针对"详情页内直接改流程"这条老路径**（``_open_flow_panel``/
``_apply_flow_diagram``，弹窗版，2026-10-06 起已不是主流入口）。

页面此刻**可能正跑着某一阶段**（进度条在动、worker 在跑），直接重建会把运行
态撕碎（进度乱跳、按钮状态错乱）。所以这条老路径只**落盘 + 提示**。

⚠️ **主流路径（详情页页头 → 流程编辑二级页 → 保存）不受这条限制**：
那条链路是**整页切换**，用户本来就站在流程页上，回详情页是一次
``open_detail`` → ``set_task`` 全量重载，**步骤条当场按新图重排**，不必
"重新进入任务"（用户 2026-10-06 报障"编辑后顶部流程图没立即更新"）。
真遇到"子任务在跑导致重载被拒"时，壳层会切回详情页**并说明**，
不再静默把人留在流程页上。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from desktop.store.store import TaskStore


class FlowMixin:
    """详情页的流程查看/编辑入口。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法：Mixin 本体不持有，
        # 这里只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        _toast: Callable[..., None]
        _refresh_imposition_node: Callable[..., None]
        _refresh_source_actions: Callable[..., None]
        # 流程编辑请求（本 Mixin 发出，壳层接）：参数是本次编辑的流程定义
        flow_edit_requested: Callable[..., Any]

    def _on_show_flow(self) -> None:
        """页头「查看 / 编辑本任务的流程」→ **请求切到流程编辑页**。

        ⚠️ 2026-10-06 起不再弹模态窗：由宿主（壳层）切到
        :class:`~desktop.pages.taskflow.page.TaskFlowPage` 二级页。这里只
        **发请求**——详情页不知道壳层存在（自测里它没有壳层，发不出去也
        不会炸）。

        先自己查一遍流程读不读得出来：读不出就**当场提示**并返回，而不是
        让宿主切到一个空白的流程页（用户点了按钮却"什么都没发生"）。
        """
        if not self.task_id:
            return
        diagram = self.store.task_diagram(self.task_id)
        if not diagram.nodes:
            self._toast("warning", "流程为空",
                        "本任务的流程文件读不出节点，"
                        "请在列表页重新创建任务。")
            return
        self.flow_edit_requested.emit(self.task_id)

    def _open_flow_panel(self):
        """按本任务当前流程弹出「查看/编辑」面板（不自动落盘）。"""
        from desktop.components.flow_dialog import FlowDialog

        if not self.task_id:
            return None
        diagram = self.store.task_diagram(self.task_id)
        if not diagram.nodes:
            self._toast("warning", "流程为空",
                        "本任务的流程文件读不出节点，请在列表页重新创建任务。")
            return None
        # 「恢复默认」= 回到**默认模板**（`desktop/static/task_default.bpmn`）
        from desktop.steps.scheduler import load_default_diagram

        dialog = FlowDialog(diagram, self, reset_factory=load_default_diagram)
        self._flow_dialog = dialog
        panel = dialog.build_panel()
        panel.done.connect(lambda _ok: self._on_flow_panel_done(dialog))
        dialog.exec()
        return panel

    def _on_flow_panel_done(self, dialog) -> None:
        """弹窗关闭：接住结果并落盘（``edited`` 为真时）。"""
        if dialog.panel.edited():
            self._apply_flow_diagram(dialog.result_diagram())

    def _apply_flow_diagram(self, diagram) -> None:
        """把新图落进 ``flow.bpmn``（老弹窗路径；页头按钮走流程编辑二级页）。"""
        if diagram is None or not self.task_id:
            return
        self.store.save_task_diagram(self.task_id, diagram)
        # ⚠️ 拼版节点（「图片拼板」）的可见性**只看流程图**，所以这里能立刻
        #    同步：用户在弹窗里把这一步删掉/加回来，流程条当场跟着变。若他
        #    正停在拼版详情上而这一步已被删掉，``_refresh_imposition_node``
        #    会把他退回第三步——否则会停在一个"流程条上已不存在"的页面上。
        #    这一步只动拼版节点，**不重建**步骤条/两个栈（那要等重新进入），
        #    所以不会撕碎正在跑的执行态。
        self._refresh_imposition_node()
        # ⚠️ 页头三颗输入按钮 + 左下角「＋/📁」的显隐**只跟流程入口走**
        #    （用户 2026-10-06 三条规则，判据 ``_entry_input_kind``）。保存
        #    新图后入口可能换了（比如把「图片提取」删掉/挪后），按钮显隐必须
        #    当场重判——否则页头还摆着"这个流程根本不需要"的输入入口（这条
        #    老路径不重建页面，唯一的当场刷新机会就是这里）。
        self._refresh_source_actions()
        self._toast(
            "info",
            "流程已保存",
            "新的任务流程已保存。步骤条会在**重新进入本任务**后按新流程重排"
            "（若当前正在跑某一步，等它跑完再切，避免打断运行）。",
        )


__all__ = ["FlowMixin"]
