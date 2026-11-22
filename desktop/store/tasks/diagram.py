# -*- coding: utf-8 -*-
"""任务流程图（flow.bpmn）的解析、缓存与界面槽位投影。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）。文件是唯一真源，解析失败
回落默认模板并留下降级原因（见 ``flow_degraded_reason``）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from desktop.steps.flow import StageSlot, default_flow_path
from desktop.store.tasks.base import TaskMixinBase


class TaskDiagramMixin(TaskMixinBase):
    """流程图的读取/保存、槽位投影与降级提示。"""

    if TYPE_CHECKING:
        task_dir: Callable[[str], Path]

    def task_diagram(self, task_id: str):
        """本任务的**流程图**（``FlowDiagram``：节点类型 + 坐标 + 折点）。

        ⚠️ 与 :mod:`desktop.steps.flow`（``FlowDefinition``）的区别：那个是**旧模型**
        （阶段序列 + 端口边表），已不再被 store 暴露给界面——页面渲染、运行
        顺序、供给方、就绪判据全部走这张图。两者读的
        是同一个 ``flow.bpmn``——文件是唯一真源。

        读不到 / 文件坏一律**回落默认模板**：界面宁可显示默认流程，也不能
        整个详情页打不开。⚠️ 但**回落必须是可见的**——见
        :meth:`flow_degraded_reason`。

        ⚠️ **"解析得动但一个可执行步骤都认不出"也算坏**：那种图会让
        :meth:`stage_supplier` 的"在流程里"集合变成空集，于是**每个端口都
        解析成 None**（现象是"每一步都说找不到输入"，而流程看起来是有节点的，
        极难查）。所以这里判的是"有没有能跑的步骤"，不是"有没有节点"。

        ⚠️ 第三条最隐蔽：用户在 bpmn.io 里把「图片去底色」改名成「AI 抠图」
        ——一次完全合法的编辑——所有 ``task`` 节点的名字都认不出来，
        ``stage_order()`` 就是空，整张自定义图被**静默**判成"坏"并换回默认
        流程。所以回落一定要配一条提示，见 ``flow_degraded_reason``。
        """
        from desktop.steps.bpmn_diagram import FlowDiagram
        from desktop.steps.scheduler import load_default_diagram

        path = default_flow_path(self.task_dir(task_id))
        # ⚠️ 缓存键必须带 **mtime_ns + size**：这个方法是详情页最热的调用
        #    （一次进页面 2000+ 次），但流程文件随时可能被编辑器重写。只按
        #    任务号缓存会让"改了流程没反应"；带上文件指纹则任何落盘都自然
        #    失效，不必依赖每个写入点记得来作废。
        key: tuple[int, int] | None
        try:
            stat = path.stat()
            key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            key = None
        cache = self._diagram_map()
        if key is not None:
            cached = cache.get(task_id)
            if cached is not None and cached[0] == key:
                self._degraded_map().pop(task_id, None)
                return cached[1]
        reason = ""
        if path.is_file():
            try:
                diagram = FlowDiagram.load(path)
                if diagram.stage_order():
                    self._degraded_map().pop(task_id, None)
                    if key is not None:
                        cache[task_id] = (key, diagram)
                    return diagram
                reason = (
                    f"{path.name} 里的步骤一个都认不出来"
                    "（节点名对不上任何已有步骤——阶段是按**节点名**接回的，"
                    "改名后要改回「提取图片 / 检测文本框 / 图片去底色 / "
                    "图片拼版 / PDF排版」这类名字）"
                )
            except (ValueError, OSError) as exc:
                reason = f"{path.name} 解析失败：{exc}"
        else:
            reason = f"本任务目录下没有 {path.name}"
        # 降级路径**不进缓存**：坏文件被修好后 mtime 会变，但这里没有可信的
        # 键；默认模板本身很小，且只在真的降级时才解析。
        cache.pop(task_id, None)
        self._degraded_map()[task_id] = reason
        fallback = load_default_diagram()
        if fallback.nodes:
            return fallback
        return FlowDiagram()

    def flow_degraded_reason(self, task_id: str) -> str:
        """本任务的流程图是不是**降级**了（读的是默认模板而非自己的图）。

        空串 = 正常。⚠️ 这是"自定义流程莫名其妙变回默认"这类报障**唯一**的
        线索来源：``task_diagram`` 的回落必须配一条提示，否则用户看到的现象
        与"我没改过它"完全一样（用户 2026-10-06）。
        """
        return (self._flow_degraded or {}).get(task_id, "")

    @staticmethod
    def _log_flow_write_error(task_id: str, exc: OSError) -> None:
        """建任务时写 ``flow.bpmn`` 失败：留一条可见痕迹。

        ⚠️ 此前是 ``except OSError: pass``——任务照样建成，之后**每一次**读
        流程都回落默认模板。用户报"我编的流程变回默认了"时，没有任何线索。
        """
        import sys

        print(
            f"[store] 任务 {task_id} 写入 flow.bpmn 失败：{exc}。"
            "该任务将按默认流程显示，请检查目录权限。",
            file=sys.stderr,
        )

    def save_task_diagram(self, task_id: str, diagram) -> None:
        """把流程图写回 ``tasks/<任务号>/flow.bpmn``（原子写）。

        ⚠️ 只改**流程定义**，不碰任何产物。改完流程后已有产物是否还有效，是
        **界面该提示的事**，由调用方判断——store 只管存。

        ⚠️ 落盘后**只作废**解析缓存，不能拿传进来的这张图回填：调用方给的往往是
        编辑器手里的**在制品**（节点 ``stage`` 等派生字段可能是 None），而
        ``FlowDiagram.load`` 会按节点名把 ``stage`` 补出来——``stage_slots()``
        正是吃这个字段。回填未归一化的对象会让步骤条退化成"每格都是空步骤"
        （自测 last_stage 6b 当场红）。代价只是保存后多解析一次文件，保存本来
        就是低频操作。
        """
        path = default_flow_path(self.task_dir(task_id))
        diagram.save(path)
        self._diagram_map().pop(task_id, None)

    def task_slots(self, task_id: str) -> tuple[StageSlot, ...]:
        """本任务流程投影出的**界面槽位**（步骤条格子 + 两个栈的页号）。

        界面的步骤条与阶段寻址都走这里（``docs/tasks/bpm.md`` 的 M2），
        不再按``STAGES`` 四步硬索引——自定义流程换了顺序/增删了节点，
        步骤条与寻址一起跟着变。折叠规则见
        :meth:`desktop.steps.flow.FlowDefinition.stage_slots`。
        """
        # ⚠️ **走图模型，不走 FlowDefinition**：后者读不了 bpmn.io 的网关/
        # 自定义 id，解析失败会**静默回落默认流程**——那正是"无论选不选
        # 自定义，详情页永远显示 task_default.bpmn"的根因。
        return self.task_diagram(task_id).stage_slots()

    def task_stage_of(self, task_id: str, bar_index: int) -> str | None:
        """步骤条格序 → **运行阶段**（点节点后反查该跑/该显示什么）。

        返回 ``None`` 说明这一格在本流程里不存在（自定义流程删掉了它），
        调用方必须挡住而不是当成第一步。
        """
        diagram = self.task_diagram(task_id)
        step = diagram.step_at(bar_index)
        if step is None:
            return None
        slot = diagram.slot_of(step)
        return None if slot is None else slot.stage
