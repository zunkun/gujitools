# -*- coding: utf-8 -*-
"""TaskMixin 的共享状态：数据根、流程图/开关读盘缓存与跨 Mixin 声明。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）：这些缓存与方法原先挂在
唯一的 ``TaskMixin`` 上，供「流程图解析」与「可选步骤开关」两处共用。
各职责 Mixin 都继承本类，组合后的 ``TaskMixin`` 行为不变。

⚠️ 缓存字典**必须是每实例一份**（见各自的注释），所以只声明默认值、
惰性建在实例上。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable


class TaskMixinBase:
    """共享状态与读盘缓存的宿主（不直接实例化）。"""

    root: Path

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        drafts_dir: Callable[[str], Path]
        # 执行历史读取（RunsMixin 提供）：判"上游动作是否真的执行成功"用。
        list_stage_runs: Callable[[str, str], list[dict]]
        list_node_runs: Callable[[str, str, str | None], list[dict]]
        # 仅类型检查期导入：流程图模块在热路径上是惰性导入的（见 task_diagram）
        from desktop.steps.bpmn_diagram import FlowDiagram

    #: ``任务号 → 流程降级原因``（见 :meth:`task_diagram` / :meth:`flow_degraded_reason`）。
    #:
    #: ⚠️ **必须是每实例一份**，不能放类属性当默认值：键是任务号，而自测里
    #: 一堆临时 store 都用 ``0001`` 这类同名任务 ⇒ 类属性会让 A 任务降级的
    #: 原因"传染"给 B 任务。惰性建在实例上（见 :meth:`_degraded_map`）。
    _flow_degraded: dict[str, str] | None = None

    #: ``任务号 → ((mtime_ns, size), FlowDiagram)``：``flow.bpmn`` 的解析缓存。
    #:
    #: ⚠️ **必须有**：详情页一次刷新会调 :meth:`task_diagram` 上千次（阶段
    #: 槽位、按节点寻址、端口供给、逐页取框都会来问），每次都完整解析 XML
    #: 就是用户实测的「进详情要等 3~5 秒」。键带 **mtime_ns + size**，任何
    #: 落盘（:meth:`save_task_diagram` 会显式作废）都会让旧条目自然失效。
    #: 同样必须**每实例一份**（理由同上一条：自测里同名任务号会串味）。
    _diagram_cache: dict[str, "tuple[tuple[int, int], FlowDiagram]"] | None = None

    #: ``(任务号, 步骤) → ((mtime_ns, size), 开关值)``：``step_enabled`` 的读盘缓存。
    #:
    #: ⚠️ 为什么值得缓存：``imposition_effective()`` 会经 ``_boxes_read_path``
    #: 被**每页**问一次（第三步刷新条目 110 页 = 110 次），而它最终落到
    #: ``step_enabled`` 的一次 JSON 读盘。开关文件只在用户拨开关时才变，
    #: 键带文件指纹即可保证"拨了立刻生效"；同样是**每实例一份**。
    _step_flags_cache: dict[tuple[str, str], tuple[tuple[int, int], bool]] | None = None

    def _degraded_map(self) -> dict[str, str]:
        """本实例的降级原因表（惰性建，避免覆盖类属性默认值）。"""
        if self._flow_degraded is None:
            self._flow_degraded = {}
        return self._flow_degraded

    def _step_flags_map(self) -> dict[tuple[str, str], tuple[tuple[int, int], bool]]:
        """本实例的可选步骤开关读盘缓存（惰性建）。"""
        if self._step_flags_cache is None:
            self._step_flags_cache = {}
        return self._step_flags_cache

    def _diagram_map(self) -> dict[str, "tuple[tuple[int, int], FlowDiagram]"]:
        """本实例的流程图解析缓存（惰性建，避免覆盖类属性默认值）。"""
        if self._diagram_cache is None:
            self._diagram_cache = {}
        return self._diagram_cache
