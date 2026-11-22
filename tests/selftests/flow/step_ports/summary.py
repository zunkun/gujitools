# -*- coding: utf-8 -*-
"""步骤**端口模型**与**模块页复用**的自测（需求 1 / 2 的护栏）。

用户 2026-10-03 的定调：

> 任务流程每一步解耦，后续我会使用 bpm 流程处理不同的任务流程顺序，
> 因此每一步都有输入，输出就可以了
>
> 左侧目录中也有相关功能，但都是独立的步骤，可以复用公共组件

守护四件事：

1. **端口是声明出来的、且真在接线**——每一步的输入/输出都来自
   :class:`~desktop.steps.spec.StepSpec`（不另写一份），产物落点与
   "谁供给谁"都在 :mod:`desktop.steps.ports` 一张表里；
2. **BPM 化的前提成立**：``resolve_input`` 按连线解析，改连线表就能换上游，
   调用点不用动；``missing_stages`` 能按顺序找出"上游还没跑"的阶段；
3. **store 不再自带一份任务目录布局**——它的 ``*_output_dir`` 必须与端口表
   逐字一致（这些路径躺在用户磁盘的老任务上，改错一个就是数据事故）；
4. **公共组件真的被复用**——四个步骤页共用 :class:`StepModulePage`，页面里
   **不许**再抄一遍输入区/控制区/收尾那一套；
5. **入口步骤也有输入可用**——自定义流程把某一步放在第一位时，它的
   ``pages`` 输入回落到 ``stages/input/``，而不是"没有输入"（第 7 节）；
6. **就绪守卫只查"这张图上真的阻塞"的端口**——``stage_inputs`` 是静态
   声明，"能不能跑"要另问图（:func:`~desktop.steps.ports.stage_blocking_inputs`，
   第 8 节）：任务自己供给的 ``pdf``、本流程没人产出的 ``boxes``
   （例如「图片去底色」打头且没接检测）都不构成阻塞。

不跑 YOLO、不起子进程，全是纯逻辑断言 + 一次不建页面的静态检查。

拆分约定（``docs/dev/testing-standards.md`` §2.1）：按原文件章节切分；
跨片夹具（``ctx`` 与 ``ok``）挂在 ``st`` 上。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03, p04

NAME = "step_ports"
#: 依赖 ``tasklist``：它提供了 ``ctx.tid``（一个已导入的任务）供详情页用例用。
#: 其余五节是纯逻辑，不碰窗口。
DEPENDS: list[str] = ["tasklist"]
TITLE = "步骤端口模型与模块页复用"

#: 按顺序执行的分片（改哪章只动哪个 ``pNN.py``）。
PARTS = (
    (p01, "1. 端口声明 / 连线 / BPM 就绪"),
    (p02, "2. store 派生 / 步骤页复用 / 详情页元数据"),
    (p03, "3. 入口步骤输入 / 就绪守卫"),
    (p04, "4. 源PDF 成对 / 结束事件级联 / 网关依附"),
)


def run(ctx) -> None:
    from tests.selftests._context import ok

    st = SimpleNamespace(ctx=ctx, ok=ok)
    for part, _title in PARTS:
        part.run(st)


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
