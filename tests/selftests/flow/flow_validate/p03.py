# -*- coding: utf-8 -*-
"""``flow_validate`` 第 3 章：聚合起始节点 / 默认模板干净。"""

from __future__ import annotations

from ._helpers import _chain


def run(st) -> None:
    _check_aggregate_start(st.ok)
    _check_templates_clean(st.ok)


# ----------------------------- ④a 聚合流程必须以起始节点打头（2026-11-18）
def _check_aggregate_start(ok) -> None:
    """聚合任务硬规则 ⑦（``aggregate_start`` 参数）。

    用户口径：聚合任务设置的起始节点，下面的流程图必须以这个节点作为
    **第一个任务节点**；修改流程图（添加步骤、改连线）把它挪到后面时，
    保存要校验、拒绝落盘——否则「聚合输入」汇集的成员产物喂给了错误的
    步骤（``aggregate_ingest`` 的汇集数据只对起始节点那一格有效）。
    """
    from desktop.steps.aggregate import (
        AGGREGATE_START_STAGES,
        derive_aggregate_diagram,
    )
    from desktop.steps.validate import validate_flow

    # 派生图（用户没编辑过）对每个合法起点都必须**天然满足**——
    # 派生逻辑把起始节点放在「聚合输入」后面第一位，规则不能误伤它。
    for stage in AGGREGATE_START_STAGES:
        result = validate_flow(
            derive_aggregate_diagram(stage), aggregate_start=stage
        )
        ok(f"派生图（起始={stage}）以起始节点打头 ⇒ 放行",
           result.ok, f"errors={result.errors}")

    # 反例：起始节点是「图片拼版」，用户把 检测/去底色 挪到了它前面
    result = validate_flow(
        _chain("detect", "rembg", "imposition", "print"),
        aggregate_start="imposition",
    )
    ok("聚合流程把检测挪到拼版前面 ⇒ 拒绝并点名起始节点",
       not result.ok and any("起始节点" in e and "拼版" in e
                             for e in result.errors),
       f"errors={result.errors}")

    # 起始节点在第一位 ⇒ 放行
    result = validate_flow(_chain("imposition", "print"),
                           aggregate_start="imposition")
    ok("聚合流程以拼版打头 ⇒ 放行", result.ok, f"errors={result.errors}")

    # 同一张反例图**不带** aggregate_start（普通任务）⇒ 照常放行——
    # 参数是聚合任务专用，不能影响普通任务的合法性判据
    result = validate_flow(_chain("detect", "rembg", "imposition", "print"))
    ok("同一张图不带 aggregate_start ⇒ 普通任务不受影响",
       result.ok, f"errors={result.errors}")


# ------------------------------------------------- ④ 模板必须干净通过
def _check_templates_clean(ok) -> None:
    """默认模板必须**零错误零警告**——模板是用户起点，
    一打开编辑器就被警告轰炸等于告诉用户"程序自己给的东西不合法"。"""
    from desktop.steps.scheduler import load_default_diagram
    from desktop.steps.validate import validate_flow

    result = validate_flow(load_default_diagram())
    ok("模板 task_default.bpmn 零错误零警告",
       result.ok and not result.warnings,
       f"errors={result.errors} warnings={result.warnings}")
