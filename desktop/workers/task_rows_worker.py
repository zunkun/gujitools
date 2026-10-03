# -*- coding: utf-8 -*-
"""任务列表行的读取（后台线程）。

列表页刷新要遍历全部任务、逐个读它的 ``runs.json`` 才能拿到四个阶段的状态。
任务一多、或单个任务的 runs 记录一多，这串读盘就会把 **UI 线程**占住——窗口
明明已经画出来了，内容却要再等一截才出现。

放到这里在后台线程读，读完一次性把整批行回传主线程渲染。只读不写，因此
与主线程的 store 访问不冲突。

⚠️ **每个任务的子任务数量不是固定的**（用户 2026-10-03 口径："任务列表子任务
到底有几个需要根据详情决定"）：「图片拼版」是可选节点，只有在任务详情里勾了
「在流程中启用图片拼版」才进流程，此时「PDF」前面多一个「拼版」胶囊；没勾的
任务仍是四个。两处判据必须同源：
- **插不插 / 详情里流程走不走** → ``store.imposition_enabled()``（只看勾没勾，
  与 ``ImpositionMixin.imposition_active`` 同一口径）；
- **胶囊的颜色** → 再叠一层"有没有拼版页"（绿=已能出图，灰=还没拼版）。
拼版没有 runs.json 记录（它是纯合成、不走 worker），所以状态只能这么派生。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from desktop.store import (
    IMPOSITION_STAGE, STAGES, STAGE_LABELS, STAGE_SHORT,
)
from desktop.steps.ports import IMPOSITION_ANCHOR
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
            f"{'已生效（生成 PDF 使用拼版结果）' if active else '已启用，尚未拼版'}"
        )
        return {
            "short": STAGE_SHORT[IMPOSITION_STAGE],
            "status": status,
            "tip": tip,
        }

    def _stage_chips(self, task_id: str, states: dict) -> list[dict]:
        """这一行的子任务胶囊（四个真实步骤 + 按详情决定要不要的拼版）。

        拼版插在 :data:`~desktop.steps.ports.IMPOSITION_ANCHOR`（"print"）**之前**
        ——与详情页流程条上节点的位置一致，别在这里数下标。
        """
        try:
            enabled = bool(self.store.imposition_enabled(task_id))
        except Exception:  # noqa: BLE001 - 同上：读不到就当没启用
            enabled = False
        chips = []
        for stage in STAGES:
            if enabled and stage == IMPOSITION_ANCHOR:
                chips.append(self._imposition_chip(task_id))
            state = states[stage]
            status = state["status"]
            progress = (
                f" {state['done']}/{state['total']}" if state["total"] else ""
            )
            chips.append(
                {
                    "short": STAGE_SHORT[stage],
                    "status": status,
                    "tip": (
                        f"{STAGE_LABELS[stage]}："
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
