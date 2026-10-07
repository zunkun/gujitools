# -*- coding: utf-8 -*-
"""任务列表行的读取（后台线程）。

列表页刷新要遍历全部任务、逐个读它的 ``runs.json`` 才能拿到四个阶段的状态。
任务一多、或单个任务的 runs 记录一多，这串读盘就会把 **UI 线程**占住——窗口
明明已经画出来了，内容却要再等一截才出现。

放到这里在后台线程读，读完一次性把整批行回传主线程渲染。只读不写，因此
与主线程的 store 访问不冲突。

⚠️ **每个任务的子任务数量不是固定的**（用户 2026-10-03 口径："任务列表子任务
到底有几个需要根据详情决定"）：胶囊**按本任务自己的流程图**给——图上有几步
就有几枚，图上删掉的步骤不显示。叠加一条用户 2026-10-05 的口径：「图片拼版」
要在**图里**且在详情里勾了「在流程中启用图片拼版」才进流程，此时「PDF」前面
多一个「拼版」胶囊；没勾的、或流程图里没有这一格的，都不占子任务。两处判据
必须同源：
- **插不插 / 详情里流程走不走** → ``store.imposition_enabled()``（只看勾没勾，
  与 ``ImpositionMixin.imposition_active`` 同一口径）；
- **胶囊的颜色** → 再叠一层"有没有拼版页"（绿=已能出图，灰=还没拼版）。
拼版没有 runs.json 记录（它是纯合成、不走 worker），所以状态只能这么派生。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from desktop.store import (
    IMPOSITION_STAGE, STAGE_LABELS, STAGE_SHORT,
)
from desktop.ui import theme as T


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

    def _stage_chips(self, task_id: str, states: dict) -> list[dict]:
        """这一行的子任务胶囊——**按本任务自己的流程图**给。

        ⚠️ 2026-10-05 口径变更：以前硬编码 ``for stage in STAGES``（四个固定
        阶段）+ 看 ``imposition_enabled`` 决定插不插拼版胶囊。后果是**改了
        流程图，列表不变**：图上删掉「图片去底色」它照样显示"去底"，图上加了
        新步骤它不显示——用户看到的"这条任务有几个子任务"与实际流程对不上。

        现在走 ``store.task_slots(task_id)``（**流程图的界面投影，唯一真源**）：

        - 顺序 = 步骤条格序（``bar_index``），不再靠"插在 print 之前"凑位置；
        - 不在图里的阶段不出胶囊（``in_flow`` 兜底，双保险）；
        - **拼版**要**在图里且已勾启用**才算一个子任务（用户 2026-10-03 口径
          "子任务到底有几个需要根据详情决定"）：勾了但流程图里没有它 ⇒ 不生效
          ⇒ 不占子任务；图里有但没勾 ⇒ 同样不占（与详情页那个灰色虚线一致）。

        读不到流程图时**一个胶囊也不造**（空列表）：行本身照常渲染（标题/
        时间都在），只是"有几个子任务"回答"不知道"。以前这里伪造四个静态
        阶段——流程图坏了的任务在列表里显示四个默认胶囊，正是"自定义流程里
        总是冒出默认流程"的观感来源之一；合法空图（用户把节点删光）也会触发
        这条，把"没有步骤"显示成"四个步骤"。
        """
        chips: list[dict] = []
        try:
            slots = list(self.store.task_slots(task_id))
        except Exception:  # noqa: BLE001 - 读不到流程就给空，不伪造
            return []
        for slot in sorted(slots, key=lambda s: s.bar_index):
            if slot.optional:
                # 可选节点（拼版）：**在图里 + 已勾启用**才算一个子任务
                try:
                    enabled = bool(self.store.imposition_enabled(task_id))
                except Exception:  # noqa: BLE001 - 同上：读不到就当没启用
                    enabled = False
                if enabled:
                    chips.append(self._imposition_chip(task_id))
                continue
            stage = slot.stage or slot.step
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
                rows.append(
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "source_path": task["source_path"],
                        "created_at": task["created_at"],
                        "stages": self._stage_chips(task["id"], states),
                    }
                )
            self.completed.emit(rows)
        except Exception as exc:  # noqa: BLE001 — 子线程异常必须回传主线程
            self.failed.emit(f"{type(exc).__name__}: {exc}")
