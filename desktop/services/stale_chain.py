# -*- coding: utf-8 -*-
"""跨阶段「上游重新执行 → 下游产物已过期」的判定（纯函数，无 Qt 依赖）。

只看**成功运行的时间戳链**：某个下游阶段最近一次成功运行，比它的前置阶段里
某一个的最近一次成功运行还旧 → 这个下游产物可能已经不是最新参数下的结果。

⚠️ 只做判定，不做任何动作：**不自动重跑、不删产物、不改参数**。界面据此给一句
提示（第四步状态行 + 主按钮高亮），要不要重跑由用户决定。

⚠️ 不比对参数。参数级的"待更新"另有专门机制（见 `submit_state.py`：
生成预览 → 提交本次任务的 new_version / preview_stale），本模块只回答
"上游又跑过一次、而下游还是那之前的产物吗"。

另有一类**不是**时间戳的过期：第四步「PDF排版」的取图来源可以整体换掉
（勾上「图片拼版」后从去底色产物改成拼版产物）。换来源之后磁盘上那份 PDF
就属于旧数据了——由 :func:`print_source_switched` 判定（比对运行记录里
记下的来源，而不是时间）。
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
    # 生成 PDF：只排版「提交本次任务」的成品图（2026-10-01 起不再拿去底图现算），
    # 列表与图片都来自提交产物；但 extract/detect/rembg 跑过就意味着这份提交
    # 产物已经落后于上游（用户多半要重新「生成预览」再提交），照旧算它的上游
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


def upstream_from_diagram(diagram) -> dict[str, tuple[str, ...]]:
    """按**流程图**算"下游阶段 → 它的上游阶段"（替代写死的 :data:`UPSTREAM`）。

    ⚠️ 为什么必须按图算：用户改了流程（加一步、去掉一步、换分支）之后，写死的
    链会把不相干的步骤算成上游（提示"上游已重新执行"却指错人），或者漏掉真正
    影响它的那一步。判定用的链必须与驱动用的图是同一份。

    ``diagram`` 只要求有 ``stage_order()`` 与 ``upstream_stages(stage)``
    （鸭子类型）——本模块是纯函数，**不 import desktop 包**。
    """
    out: dict[str, tuple[str, ...]] = {}
    for stage in diagram.stage_order():
        ups = diagram.upstream_stages(stage)
        if ups:
            out[stage] = ups
    return out


def stale_upstream(runs: dict, upstream: dict | None = None) -> dict[str, dict]:
    """runs（``{阶段: [记录, ...]}``）→ 过期判定 ``{下游阶段: 详情}``。

    详情：``{"stage": 更新了的上游阶段, "upstream_at": ts, "downstream_at": ts}``。
    下游**从未成功过**时不判过期——那种情况界面本来就在说"未执行"，再叠一句
    "已过期"只会让人困惑。

    ``upstream`` 不给就用 :data:`UPSTREAM`（写死的那份，只适合"没有任务/读不到
    流程图"的兜底）；有任务时应传
    :func:`upstream_from_diagram` 的结果，让判定跟着**本任务的流程图**走。
    """
    out: dict[str, dict] = {}
    for stage, upstreams in (upstream or UPSTREAM).items():
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


# ---------------------------------------------------------------- 拼版开关
def print_source_switched(runs: dict, current_source: str) -> bool:
    """已生成的 PDF 是不是在**换了取图来源之后**生成的（旧数据）。

    用户 2026-10-03 的口径：

    > 任务详情里面如果启用了拼板，则最后一步生成 pdf 的数据来源就是拼板，
    > 如果之前流程里面没有启用拼板，但是生成了 pdf，此时再次启用拼板，
    > 则生成 PDF 的数据要来源于拼板，旧的数据不显示

    所以第四步要能回答"磁盘上那份 PDF 还是当前来源下的产物吗"——不能
    变了来源还让用户下载/预览上一轮的去底色 PDF，那正是"旧数据"。

    判据：最近一次**成功**的 print 运行记录里存了当时的取图来源
    （``parameters["source_stage"]``，见 runner 注入），与当前来源不同即过期。

    - 下游从未成功过 → 不判过期（界面本来就说"未执行"）；
    - 老任务的记录里没有 ``source_stage``（本字段引入前生成的）→ **不判过期**，
      宁可少提示也不凭空说用户的 PDF 有问题。
    """
    latest = latest_success(runs.get("print"))
    if latest is None:
        return False
    params = latest.get("parameters") or {}
    recorded = params.get("source_stage")
    if not recorded:
        return False  # 老记录没有这个字段 → 无从判断，别误报
    return str(recorded) != str(current_source)
