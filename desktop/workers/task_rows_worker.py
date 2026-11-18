# -*- coding: utf-8 -*-
"""任务列表行的读取（后台线程）。

列表页刷新要遍历全部任务、逐个读它的 ``runs.json`` 才能拿到四个阶段的状态。
任务一多、或单个任务的 runs 记录一多，这串读盘就会把 **UI 线程**占住——窗口
明明已经画出来了，内容却要再等一截才出现。

放到这里在后台线程读，读完一次性把整批行回传主线程渲染。只读不写，因此
与主线程的 store 访问不冲突。

⚠️ **每个任务的节点数量不是固定的**（用户 2026-10-03 口径："任务列表节点
到底有几个需要根据详情决定"）：胶囊**按本任务自己的流程图**给——图上有几步
就有几枚，图上删掉的步骤不显示。叠加一条用户 2026-10-05 的口径：「图片拼版」
要在**图里**且在详情里勾了「在流程中启用图片拼版」才进流程，此时「PDF」前面
多一个「拼版」胶囊；没勾的、或流程图里没有这一格的，都不占节点。两处判据
必须同源：
- **插不插 / 详情里流程走不走** → ``store.imposition_enabled()``（只看勾没勾，
  与 ``ImpositionMixin.imposition_active`` 同一口径）；
- **胶囊的颜色** → 再叠一层"有没有拼版页"（绿=已能出图，灰=还没拼版）。
拼版没有 runs.json 记录（它是纯合成、不走 worker），所以状态只能这么派生。

⚠️⚠️ **颜色必须按"节点"取，不能按"阶段"取**（2026-11-17 用户报 0011）：
「检测文本框」这一格在 ``runs.json`` 里对应**两个动作**——``detect``（YOLO
出框）与 ``detect_submit``（提交裁图）。用户手工标注 / 沿用上一页时只跑
后者，``runs["detect"]`` 压根没有记录；按阶段取就会显示灰色「未执行」，
可它的产物（裁好的图）明明已经产出、下游去底/拼版/PDF 全跑完了。
用户口径：「只要这个节点执行过，那么就应当是生效的」。
判据与详情页步骤条**同一口径**（``TaskDetailPage._slot_state``）：
``store.node_states()`` 按**节点 id** 归并同格内的全部动作，谁跑过都算这一格
跑过。别在这里按 ``stage`` 取 ``stage_states()``——那会把同格的动作拆开看。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from desktop.store import (
    IMPOSITION_STAGE, STAGE_LABELS, STAGE_SHORT,
)
from desktop.ui import theme as T

#: 某节点从没跑过时的状态（胶囊画成灰色「未执行」）。
#: 与 ``TaskDetailPage._PENDING_STATE`` 同值——列表与详情页对"没跑过"的
#: 表达必须一致，否则会出现"列表灰、详情绿"的第二种错。
_PENDING_STATE = {"status": "pending", "done": 0, "total": 0, "completed": False}


class TaskRowsWorker(QObject):
    """读全量任务行（只读，不落任何盘）。"""

    #: 读取完成，携带完整行列表
    completed = Signal(list)
    #: 读取失败（携带错误信息）
    failed = Signal(str)

    def __init__(self, store) -> None:
        """store 只用于读（list_tasks / stage_states / imposition_enabled），不写。"""
        super().__init__()
        self.store = store

    def _imposition_chip(self, task_id: str) -> dict:
        """拼版节点的状态胶囊（它不在 runs.json 里，状态现算）。

        绿 = 已启用**且**已经有拼版页（能出东西）；灰 = 已启用但还没拼页。
        ⚠️ 这与详情页的**流程判据**分两层：那边 ``imposition_active()`` 只看
        "勾没勾"（决定取图来源与流程线），这边额外看"有没有页"，因为列表要
        回答的是**进度**而不是意图。
        ⚠️ 单条任务出错不能让整张列表刷不出来——这个节点是**附加**信息，读不到
        就按"未启用"处理，四个真实步骤的状态照常显示。
        """
        try:
            active = bool(self.store.imposition_enabled(task_id)) and bool(
                self.store.load_imposition_doc(task_id).get("pages")
            )
        except Exception:  # noqa: BLE001 - 附加信息读失败不该拖垮整张列表
            active = False
        status = "success" if active else "pending"
        tip = (
            f"{STAGE_LABELS[IMPOSITION_STAGE]}："
            f"{'已生效（PDF排版使用拼版结果）' if active else '已启用，尚未拼版'}"
        )
        return {
            "short": STAGE_SHORT[IMPOSITION_STAGE],
            "status": status,
            "tip": tip,
        }

    def _stage_chips(self, task_id: str, states: dict, nodes: dict) -> list[dict]:
        """这一行的节点胶囊——**按本任务自己的流程图**给。

        ⚠️ 2026-10-05 口径变更：以前硬编码 ``for stage in STAGES``（四个固定
        阶段）+ 看 ``imposition_enabled`` 决定插不插拼版胶囊。后果是**改了
        流程图，列表不变**：图上删掉「图片去底色」它照样显示"去底"，图上加了
        新步骤它不显示——用户看到的"这条任务有几个节点"与实际流程对不上。

        现在走 ``store.task_slots(task_id)``（**流程图的界面投影，唯一真源**）：

        - 顺序 = 步骤条格序（``bar_index``），不再靠"插在 print 之前"凑位置；
        - 不在图里的阶段不出胶囊（``in_flow`` 兜底，双保险）；
        - **拼版**要**在图里且已勾启用**才算一个节点（用户 2026-10-03 口径
          "节点到底有几个需要根据详情决定"）：勾了但流程图里没有它 ⇒ 不生效
          ⇒ 不占节点；图里有但没勾 ⇒ 同样不占（与详情页那个灰色虚线一致）。

        读不到流程图时**一个胶囊也不造**（空列表）：行本身照常渲染（标题/
        时间都在），只是"有几个节点"回答"不知道"。以前这里伪造四个静态
        阶段——流程图坏了的任务在列表里显示四个默认胶囊，正是"自定义流程里
        总是冒出默认流程"的观感来源之一；合法空图（用户把节点删光）也会触发
        这条，把"没有步骤"显示成"四个步骤"。

        ``states`` = :meth:`~desktop.store.runs.RunMixin.stage_states`
        （兜底用：槽位没有节点 id 的老模型投影）；``nodes`` =
        :meth:`~desktop.store.runs.RunMixin.node_states`（**主口径**）。
        空 ``nodes``（读盘异常时的降级）⇒ 自然退回阶段级，即旧行为。
        """
        chips: list[dict] = []
        try:
            slots = list(self.store.task_slots(task_id))
        except Exception:  # noqa: BLE001 - 读不到流程就给空，不伪造
            return []
        # ``nodes`` 空 = 节点级读盘失败（调用方已降级）⇒ 整行退回阶段级。
        # ⚠️ 别把它当成"每个节点都没跑过"：那样显示出来的是"全灰未执行"，
        #    正好就是这一轮要修的错相，只是换成了另一种触发路径。
        by_node = bool(nodes)
        for slot in sorted(slots, key=lambda s: s.bar_index):
            if slot.optional:
                # 可选节点（拼版）：**在图里 + 已勾启用**才算一个节点
                try:
                    enabled = bool(self.store.imposition_enabled(task_id))
                except Exception:  # noqa: BLE001 - 同上：读不到就当没启用
                    enabled = False
                if enabled:
                    chips.append(self._imposition_chip(task_id))
                continue
            stage = slot.stage or slot.step
            # ⚠️⚠️ 先按**节点**取（同格的 detect / detect_submit 归并在一起），
            #    没有节点 id 才退回**阶段**——反序就是 0011 那个"提交过却显示
            #    未执行"（详见模块 docstring）。
            if by_node and slot.node_id:
                # 这一格从没跑过 ⇒ 灰色「未执行」胶囊（**不是**不画）：新任务
                # 一个节点都没跑，列表照样要显示"有这几步、都还没开始"。
                # 与详情页 ``TaskDetailPage._slot_state`` 的 ``_PENDING_STATE``
                # 同一口径。
                state = nodes.get(slot.node_id) or dict(_PENDING_STATE)
            else:
                state = states.get(stage)
                if state is None or not state.get("in_flow", True):
                    continue
            status = state["status"]
            progress = (
                f" {state['done']}/{state['total']}" if state["total"] else ""
            )
            chips.append(
                {
                    "short": STAGE_SHORT.get(stage, slot.step),
                    "status": status,
                    "tip": (
                        f"{STAGE_LABELS.get(stage, slot.step)}："
                        f"{T.STATUS_LABELS.get(status, status)}{progress}"
                    ),
                }
            )
        return chips

    @Slot()
    def run(self) -> None:
        """遍历任务生成摘要行；异常回传 failed，不抛到线程外。"""
        try:
            rows = []
            for task in self.store.list_tasks():
                states = self.store.stage_states(task["id"])
                # 节点级状态（颜色主口径）：同一步骤的多个节点各算各的，
                # 同格多动作（detect / detect_submit）归并到同一个节点上。
                # ⚠️ 读失败不该拖垮整张列表：降级成空字典 ⇒ 胶囊退回阶段级
                #    （旧口径），行照常显示。
                try:
                    nodes = self.store.node_states(task["id"])
                except Exception:  # noqa: BLE001 - 降级见上
                    nodes = {}
                rows.append(
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "source_path": task.get("source_path", ""),
                        "created_at": task["created_at"],
                        # 「聚合」标记（aggregate 任务特有；普通任务没有这个键）
                        "kind": task.get("kind", ""),
                        "stages": self._stage_chips(task["id"], states, nodes),
                    }
                )
            self.completed.emit(rows)
        except Exception as exc:  # noqa: BLE001 — 子线程异常必须回传主线程
            self.failed.emit(f"{type(exc).__name__}: {exc}")
