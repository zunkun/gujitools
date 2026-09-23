# -*- coding: utf-8 -*-
"""跨阶段「上游重新执行 → 下游产物已过期」的判定（纯函数，无 Qt 依赖）。

只看**成功运行的时间戳链**：某个下游阶段最近一次成功运行，比它的前置阶段里
某一个的最近一次成功运行还旧 → 这个下游产物可能已经不是最新参数下的结果。

⚠️ 只做判定，不做任何动作：**不自动重跑、不删产物、不改参数**。界面据此给一句
提示（第四步状态行 + 主按钮高亮），要不要重跑由用户决定。

⚠️ 不比对参数。参数级的"待更新"另有专门机制（见 `submit_state.py`：
生成预览 → 提交本次任务的 new_version / preview_stale），本模块只回答
"上游又跑过一次、而下游还是那之前的产物吗"。
"""

from __future__ import annotations

#: 参与比对的阶段链，顺序即依赖方向（与 desktop.store.tasks.STAGES 一致，
#: 另加不是独立步骤的 rembg_submit）。此处刻意写字面量：本模块是纯函数，
#: 不 import 任何 desktop 包，便于独立自测。
CHAIN = ("extract", "detect", "rembg", "rembg_submit", "print")

#: 下游阶段 → 它的前置阶段（上游跑过之后，下游产物就可能过期）
UPSTREAM = {
    # 生成预览：读提取出的页图 + 检测框
    "rembg": ("extract", "detect"),
    # 提交：合成最终图，源是「生成预览」的去底图
    "rembg_submit": ("rembg",),
    # 生成 PDF：worker 内实时合成，源是去底图 + **当时**的检测框/area/border，
    # 列表则来自提交产物 —— 所以 extract/detect/rembg/rembg_submit 都是它的上游
    "print": ("extract", "detect", "rembg", "rembg_submit"),
}

#: 时间戳容差（秒）：同一次连续操作里几个阶段前后脚完成，不该判成过期。
TIMESTAMP_TOLERANCE_S = 2.0


def latest_success(records) -> dict | None:
    """一组运行记录里最近一次**成功**的那条（按 finished_at 取最大）。

    失败/中断的跑动不算数：它们没产出可用于比对的产物。
    """
    best: dict | None = None
    best_at = 0.0
    for record in records or ():
        if not isinstance(record, dict) or record.get("status") != "success":
            continue
        try:
            at = float(record.get("finished_at") or 0.0)
        except (TypeError, ValueError):
            at = 0.0
        if best is None or at > best_at:
            best, best_at = record, at
    return best


def stale_upstream(runs: dict) -> dict[str, dict]:
    """runs（``{阶段: [记录, ...]}``）→ 过期判定 ``{下游阶段: 详情}``。

    详情：``{"stage": 更新了的上游阶段, "upstream_at": ts, "downstream_at": ts}``。
    下游**从未成功过**时不判过期——那种情况界面本来就在说"未执行"，再叠一句
    "已过期"只会让人困惑。
    """
    out: dict[str, dict] = {}
    for stage, upstreams in UPSTREAM.items():
        downstream = latest_success(runs.get(stage))
        if downstream is None:
            continue
        try:
            down_at = float(downstream.get("finished_at") or 0.0)
        except (TypeError, ValueError):
            down_at = 0.0
        newest: dict | None = None
        for upstream in upstreams:
            record = latest_success(runs.get(upstream))
            if record is None:
                continue
            try:
                up_at = float(record.get("finished_at") or 0.0)
            except (TypeError, ValueError):
                continue
            if up_at <= down_at + TIMESTAMP_TOLERANCE_S:
                continue
            if newest is None or up_at > float(newest["upstream_at"]):
                newest = {
                    "stage": upstream,
                    "upstream_at": up_at,
                    "downstream_at": down_at,
                }
        if newest is not None:
            out[stage] = newest
    return out
