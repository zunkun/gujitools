# -*- coding: utf-8 -*-
"""**详情页按 BPMN 节点渲染**（``docs/tasks/bpm.md`` 的 M2）自测。

M1 只做了数据层（``desktop/steps/flow.py`` 的流程定义 + 落盘 + 解析），
界面却仍按 ``STAGES`` 四步**硬索引**寻址——换流程不改代码不生效。本模块
钉死 M2 的契约：

1. **默认流程零行为变化**——步骤条 4 步、控制栈/预览栈各 5 页、拼版节点
   夹在第三步与第四步之间、可选节点插在第 2 个真实步骤之后（与改造前逐值
   相等）。这条是 M2 的**回归底线**：投影层算错一个下标，用户就会看到
   步骤乱序或点节点跳错步骤。
2. **换流程即换步骤条**——手写一份 ``flow.bpmn``（摘掉 detect、拼版异位）
   后重进任务，步骤条按新顺序重建、可选节点挪到新位置。
3. **寻址跟着流程走**——``current_stage()`` / ``_stage_index_of()`` 查的是
   **本任务流程的槽位表**，不是 ``STAGES`` 固定下标：流程外的步骤匹配不上
   （回第一步），流程内换了序的步骤能正确互相定位。
4. **越界不崩**——点一个流程里不存在的格序，页面自己退回有效步骤而不是
   拿越界页号去 ``setCurrentIndex``。

⚠️ 几何类断言必须在**真正显示**详情页之后做（见 ``detail_structure``
文件头的说明）：藏在 ``QStackedWidget`` 里未选中的页面从未参与布局。
"""

from __future__ import annotations

from pathlib import Path

NAME = "detail_bpm_render"
DEPENDS: list[str] = ["detail_structure"]
TITLE = "详情页按 BPMN 节点渲染"

#: 自定义流程：**摘掉 detect**（少一步）+ **拼版异位**（挪到第一步之后）。
#: 入口extract 仍在最前（BPMN 里源PDF 由任务供给，它必然是根）。
_CUSTOM_FLOW = """\
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:guji="https://guji.tools/bpmn/2025">
  <bpmn:process id="guji_ui_reorder" isExecutable="false">
    <bpmn:startEvent id="start" name="源 PDF"/>
    <bpmn:task id="extract" name="提取PDF图片" guji:stage="extract"/>
    <bpmn:task id="imposition" name="图片拼版" guji:stage="imposition"/>
    <bpmn:task id="rembg" name="图片去底色" guji:stage="rembg"/>
    <bpmn:task id="rembg_submit" name="提交" guji:stage="rembg_submit"/>
    <bpmn:task id="print" name="生成PDF" guji:stage="print"/>
    <bpmn:endEvent id="end" name="完成"/>
    <bpmn:sequenceFlow id="f0" sourceRef="start" targetRef="extract" guji:port="pdf"/>
    <bpmn:sequenceFlow id="f1" sourceRef="extract" targetRef="imposition" guji:port="pages"/>
    <bpmn:sequenceFlow id="f2" sourceRef="imposition" targetRef="rembg" guji:port="pages"/>
    <bpmn:sequenceFlow id="f3" sourceRef="rembg_submit" targetRef="print" guji:port="pages"/>
  </bpmn:process>
</bpmn:definitions>
"""


def _write_flow(repo, tid: str, xml: str) -> None:
    """覆盖任务的流程定义并**打掉 store 的 mtime 缓存**。

    ⚠️ ``store.task_flow`` 按 ``(task_id, mtime_ns)`` 缓存，不清缓存的话同一
    毫秒内两次写入会拿到旧值，断言就成了假绿。
    """
    path = Path(repo.task_dir(tid)) / "flow.bpmn"
    path.write_text(xml, encoding="utf-8")
    getattr(repo, "_flow_cache", {}).clear()


def _bar_labels(bar) -> list[str]:
    """步骤条上真实步骤的标题序列（可选节点不在 buttons 里）。"""
    return [item.title_label.text() for item in bar.buttons]


def run(ctx) -> None:
    from desktop.components.step_bar import _Connector
    from desktop.store import STAGES
    from tests.selftests._context import ok, pump, show_detail

    app, d = ctx.app, ctx.d
    repo, tid = ctx.repo, ctx.tid

    # ---------------------------------------------------------------- 1
    # 默认流程：投影层算出的下标必须与改造前的硬编码逐值相等。
    slots = {s.step: s for s in repo.task_slots(tid)}
    ok("默认流程槽位数 = 4 真实步骤 + 1 可选节点",
       len(repo.task_slots(tid)) == len(STAGES) + 1,
       str([s.step for s in repo.task_slots(tid)]))
    # ⚠️ 与旧硬编码逐值相等的是 **stack_index**（栈页号）。bar_index 是
    # 步骤条格子序号，**含可选节点占位**，拼版之后的步骤会顺延一格。
    legacy = {step: index for index, step in enumerate(STAGES)}
    ok("默认流程：真实步骤的栈页号 = 旧下标 STAGES[index]",
       all(slots[step].stack_index == index
           for step, index in legacy.items()),
       str({s.step: s.stack_index for s in repo.task_slots(tid)}))
    ok("默认流程：可选节点之前的格序 = 旧下标",
       all(slots[step].bar_index == index
           for step, index in legacy.items()
           if index <= legacy["rembg"]),
       str({s.step: s.bar_index for s in repo.task_slots(tid)}))
    ok("默认流程：可选节点之后的格序顺延一格",
       all(slots[step].bar_index == index + 1
           for step, index in legacy.items()
           if index > legacy["rembg"]),
       str({s.step: s.bar_index for s in repo.task_slots(tid)}))
    ok("可选节点格序排在第三步之后、第四步之前",
       slots["imposition"].bar_index == slots["rembg"].bar_index + 1
       and slots["imposition"].bar_index < slots["print"].bar_index,
       str({s.step: s.bar_index for s in repo.task_slots(tid)}))
    ok("可选节点插在第 2 个真实步骤之后（与改造前一致）",
       repo.task_flow(tid).optional_after("imposition") == 2,
       str(repo.task_flow(tid).optional_after("imposition")))

    # 步骤条实物：4 步 + 可选节点夹在第三/第四之间（左右都是连接件）
    show_detail(ctx, stage=0)
    pump(app)
    ok("步骤条仍是 4 个真实步骤", len(d.step_bar.buttons) == 4,
       str(len(d.step_bar.buttons)))
    row = d.step_bar._row
    node_pos = row.indexOf(d.step_bar.imposition_slot)
    ok("拼版节点夹在两条连接线之间",
       node_pos > 0
       and isinstance(row.itemAt(node_pos - 1).widget(), _Connector)
       and isinstance(row.itemAt(node_pos + 1).widget(), _Connector),
       f"pos={node_pos}")

    # 寻址：当前步骤 ⇄ 格序 双向一致（默认流程下等于旧口径）
    ok("格序 0 → 第一步", d.step_at_index(0) == "extract", str(d.step_at_index(0)))
    ok("格序 3 → 拼版（格序含可选节点占位，不是第四步）",
       d.step_at_index(3) == "imposition", str(d.step_at_index(3)))
    ok("格序 4 → 第四步", d.step_at_index(4) == "print", str(d.step_at_index(4)))
    ok("第三步 → 格序 2", d.bar_index_of_step("rembg") == 2,
       str(d.bar_index_of_step("rembg")))
    ok("拼版 → 格序（第三步之后那一格）",
       d.bar_index_of_step("imposition") == 3,
       str(d.bar_index_of_step("imposition")))
    ok("越界格序反查为 None", d.step_at_index(99) is None)
    ok("两个栈的页号在默认流程下 = 旧下标（格序不等，拼版后顺延）",
       all(d.stack_index_of(s.bar_index) == index
           for step, index in legacy.items()
           for s in [slots[step]]),
       str({s.step: (s.bar_index, s.stack_index)
            for s in repo.task_slots(tid)}))
    ok("可选节点的栈页号顺延到真实步骤之后（不占中间页）",
       slots["imposition"].stack_index == len(STAGES),
       str(slots["imposition"].stack_index))

    # ---------------------------------------------------------------- 2
    # 换流程 → 步骤条重建、顺序与可选节点位置都跟着变。
    # ⚠️ 必须走 **set_task**（用户「打开任务」的真实路径）：步骤条在
    #    set_task 里才按本任务流程重建，show_detail 只切页不重进。
    try:
        _write_flow(repo, tid, _CUSTOM_FLOW)
        ok("切任务被接受", d.set_task(tid))
        show_detail(ctx, stage=0)
        pump(app)

        slots_new = sorted(repo.task_slots(tid), key=lambda s: s.bar_index)
        order = [s.step for s in slots_new]
        ok("自定义流程：detect 从步骤条上消失",
           "detect" not in order, str(order))
        ok("自定义流程：步骤条按新顺序重建",
           _bar_labels(d.step_bar) == [s.label for s in slots_new if not s.optional],
           str(_bar_labels(d.step_bar)))
        ok("自定义流程：真实步骤降为 3 个（摘掉了 detect）",
           len(d.step_bar.buttons) == 3, str(len(d.step_bar.buttons)))
        ok("步骤条标题与流程槽位一致（第一个是提取图片）",
           _bar_labels(d.step_bar)[0] == "提取图片",
           str(_bar_labels(d.step_bar)))

        # 可选节点异位：现在插在**第一个真实步骤之后**（布局下标 2）
        ok("自定义流程：拼版插在第 0 个真实步骤之后",
           repo.task_flow(tid).optional_after("imposition") == 0,
           str(repo.task_flow(tid).optional_after("imposition")))
        node_pos = d.step_bar._row.indexOf(d.step_bar.imposition_slot)
        ok("自定义流程：可选节点布局位置随流程改变",
           node_pos == 2, f"pos={node_pos}")
        ok("自定义流程：可选节点仍在两条连接线之间",
           isinstance(d.step_bar._row.itemAt(node_pos - 1).widget(), _Connector)
           and isinstance(d.step_bar._row.itemAt(node_pos + 1).widget(), _Connector),
           f"pos={node_pos}")

        # ---------------------------------------------------------------- 3
        # 寻址跟着流程走：流程外的步骤匹配不上，流程内的能互相定位。
        ok("自定义流程：第三步的格序是 2（extract→拼版→rembg）",
           d.bar_index_of_step("rembg") == 2, str(d.bar_index_of_step("rembg")))
        ok("自定义流程：detect 已不在流程里 → 格序反查 None",
           d.bar_index_of_step("detect") is None)
        ok("自定义流程：detect 匹配不上下标（回 None）",
           d._stage_index_of("detect") is None,
           str(d._stage_index_of("detect")))
        ok("自定义流程：rembg 能匹配到自己的格序",
           d._stage_index_of("rembg") == 2, str(d._stage_index_of("rembg")))
        ok("自定义流程：两个栈页号与格序已不再相等（可选节点顺延）",
           d.stack_index_of(d.bar_index_of_step("imposition"))
           != d.bar_index_of_step("imposition"),
           f"bar={d.bar_index_of_step('imposition')} "
           f"stack={d.stack_index_of(d.bar_index_of_step('imposition'))}")

        # 切步骤：点/切到第三步，页面认得出来
        d._select_stage(2)
        pump(app)
        ok("自定义流程：切到格序 2 → 当前阶段是 rembg",
           d.current_stage() == "rembg", d.current_stage())
        ok("自定义流程：控制栈切到 rembg 那一页",
           d.control_stack.currentIndex() == d.stack_index_of(2),
           f"stack={d.control_stack.currentIndex()}")

        # 「上次停留的步骤」按 key 记，换顺序后仍能回到同一步
        d._select_stage(d.bar_index_of_step("print"))
        pump(app)
        ok("切到第四步后记住的是 print 这个 key",
           d.store.load_last_stage(tid) == "print",
           str(d.store.load_last_stage(tid)))

        # ---------------------------------------------------------------- 4
        # 越界不崩：点一个流程里没有的格序。
        d._select_stage(99)
        pump(app)
        ok("越界格序 → 页面回落到有效步骤而不是崩",
           d.current_stage() in (s.step for s in repo.task_slots(tid)),
           d.current_stage())
    finally:
        # 复原成默认流程，**必须重新 set_task** 才能把步骤条也恢复成 4 步，
        # 否则共享的 ctx.d 会给后续模块留一个 3 步的怪状态。
        from desktop.steps.flow import FlowDefinition, default_flow_path

        FlowDefinition.default().save(default_flow_path(repo.task_dir(tid)))
        getattr(repo, "_flow_cache", {}).clear()
        d.set_task(tid)
        show_detail(ctx, stage=0)
        pump(app)
        ok("复原：步骤条回到 4 个真实步骤", len(d.step_bar.buttons) == 4,
           str(len(d.step_bar.buttons)))


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]