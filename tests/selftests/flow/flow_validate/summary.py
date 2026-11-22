# -*- coding: utf-8 -*-
"""**流程合法性校验**（``desktop/steps/validate.py``）自测。

对应 ``docs/tasks/bpm测试.md``：BPM 可以任意组合，但并非所有组合都合法；
**不合法的流程在创建或编辑保存时就判出来、拒绝保存**。

本模块钉死五件事：

1. **文档里的 10 条合法组合全部放行**——包括"没有提取"的入口流程
   （detect/rembg/imposition 任意顺序任意个数）、单步流程（只留一个
   PDF排版）；
2. **反例全部拒绝**——``print → rembg``（用户给的原例）、拼版排在
   PDF排版 之后、只摆起止事件没有可执行步骤的空流程；
   ⚠️ 2026-11-15 起「没有开始节点」**不再**是反例：用户口径是"任何一个
   任务节点（方框）都能当开始节点、也能当结束节点"，起止圈纯属图示；
   仍然拒绝的是**两个及以上**开始事件（说不清几处入口）。
3. **警告只提示不拦**——extract 不在第一位、未接入运行的节点，``ok`` 仍为真。
   ⚠️ 「有拼版没判断节点」这条警告已于 2026-10-08 删除（网关依附「图片拼版」，
   界面上没有"添加判断"入口，提示用户去做一件做不到的事就是死胡同）。
   ⚠️ 「同一阶段多个节点」这条警告已于 2026-10-17 删除（B 方案：图片拼版 /
   检测文本框 / 图片去底色 / PDF排版 都可以有多个节点，它们彼此独立、各有
   产物落点）——本模块改为钉**零警告放行**。
4. **保存入口真的拦**——``FlowPanel.accept``（弹窗/创建页内嵌编辑器）
   与 ``TaskFlowPage._on_done``（流程编辑二级页）对不合法的图都
   **不落盘、不切页**；
5. **聚合流程必须以起始节点打头**（2026-11-18，``validate_flow`` 的
   ``aggregate_start`` 参数）：派生图天然满足、把别的步骤挪到起始节点前面
   会被拒，普通任务不传参数不受影响。

纯逻辑部分不建窗口；第 4 条建离屏控件（不弹模态）。

拆分约定（``docs/dev/testing-standards.md`` §2.1）：按原文件章节切分；
跨片夹具（``ctx`` 与 ``ok``）挂在 ``st`` 上。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03, p04, p05

NAME = "flow_validate"
DEPENDS: list[str] = ["flow_bpm"]
TITLE = "BPM 流程合法性校验（保存时拒绝不合法流程）"

#: 按顺序执行的分片（改哪章只动哪个 ``pNN.py``）。
PARTS = (
    (p01, "1. 合法组合 / 反例"),
    (p02, "2. 图结构 / 警告"),
    (p03, "3. 聚合起始节点 / 模板干净"),
    (p04, "4. 数据链"),
    (p05, "5. 两个保存入口的闸"),
)


def run(ctx) -> None:
    from tests.selftests._context import ok

    st = SimpleNamespace(ctx=ctx, ok=ok)
    for part, _title in PARTS:
        part.run(st)


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
