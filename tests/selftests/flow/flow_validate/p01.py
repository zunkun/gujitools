# -*- coding: utf-8 -*-
"""``flow_validate`` 第 1 章：文档合法组合 / 反例。"""

from __future__ import annotations

from ._helpers import _chain


def run(st) -> None:
    _check_legal_combos(st.ok)
    _check_illegal_combos(st.ok)


# ------------------------------------------------------- ① 文档的合法组合
def _check_legal_combos(ok) -> None:
    """``docs/tasks/bpm测试.md`` 的 10 条组合（映射到运行阶段）必须全部放行。"""
    from desktop.steps.validate import validate_flow

    legal = [
        # 1. upload → extract → detect → rembg →(imposition) → print
        ("extract", "detect", "rembg", "imposition", "print"),
        # 2. detect → rembg →(imposition) → print
        ("detect", "rembg", "imposition", "print"),
        # 3. rembg →(imposition) → print
        ("rembg", "imposition", "print"),
        # 4. imposition → print
        ("imposition", "print"),
        # 5. print
        ("print",),
        # 6. extract
        ("extract",),
        # 7. detect
        ("detect",),
        # 8. rembg
        ("rembg",),
        # 9. imposition
        ("imposition",),
        # 10. detect/rembg/imposition 任意顺序任意个数（+print 收尾）
        ("rembg", "detect", "print"),
        ("detect", "print"),
        ("imposition", "detect", "rembg"),
        ("detect", "rembg"),
    ]
    for stages in legal:
        result = validate_flow(_chain(*stages))
        ok(f"合法组合 {' → '.join(stages)} 放行",
           result.ok, f"errors={result.errors}")

    # 带「提交检测结果」显式节点的图同样合法（它与 detect 同格折叠）
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_START, KIND_TASK, DiagramFlow, DiagramNode,
        FlowDiagram, stage_of_name,
    )

    diagram = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框",
                           stage=stage_of_name("检测文本框")),
               DiagramNode("b", KIND_TASK, "提交检测结果",
                           stage="detect_submit"),
               DiagramNode("c", KIND_TASK, "PDF排版",
                           stage=stage_of_name("PDF排版")),
               DiagramNode("e", KIND_END, "生成PDF")),
        flows=(DiagramFlow("f0", "s", "a"),
               DiagramFlow("f1", "a", "b"),
               DiagramFlow("f2", "b", "c"),
               DiagramFlow("f3", "c", "e")),
    )
    result = validate_flow(diagram)
    ok("「检测+提交」同格两个动作的图合法（不误判重复）",
       result.ok and not result.warnings,
       f"errors={result.errors} warnings={result.warnings}")

    # ---- 没有起止圈也合法（用户 2026-11-15）--------------------------------
    # 用户原话："任何一个任务节点，就说是方框形的那种任务节点都可以作为开始
    # 节点，所以说这个包括结束节点，任何一个任务节点都可以作为结束节点"。
    # 起止圈只是**图示**：图上没有入线的第一个步骤就是入口（输入回落到
    # ``stages/input/``），没有出线的最后一步就是收尾 —— 删掉圆圈不该拦保存。
    for stages in [("extract", "detect", "print"), ("detect", "rembg"),
                   ("rembg", "imposition", "print"), ("print",)]:
        for end in (True, False):
            result = validate_flow(_chain(*stages, source=False, end=end))
            label = " → ".join(stages) + ("（无开始节点）" if end
                                          else "（无起止节点）")
            ok(f"合法组合 {label} 放行", result.ok, f"errors={result.errors}")


# --------------------------------------------------------------- ② 反例
def _check_illegal_combos(ok) -> None:
    """反例必须给出硬错误（保存时拒绝）。"""
    from desktop.steps.validate import validate_flow

    illegal = [
        # 用户原例：PDF排版 后面还有去底色
        ("print", "rembg"),
        # 拼版排在 PDF排版 之后（PDF排版 不是最后）
        ("print", "imposition"),
        # PDF排版 夹在中间
        ("rembg", "print", "detect"),
        # PDF排版 后又回到提取
        ("print", "extract"),
        ("extract", "print", "detect"),
    ]
    for stages in illegal:
        result = validate_flow(_chain(*stages))
        ok(f"不合法组合 {' → '.join(stages)} 被拒绝",
           not result.ok and any("PDF排版" in e for e in result.errors),
           f"errors={result.errors}")

    # 空流程：只有起止事件，没有可执行步骤
    result = validate_flow(_chain())
    ok("空流程（无可执行步骤）被拒绝",
       not result.ok and any("没有可执行" in e for e in result.errors),
       f"errors={result.errors}")
    result = validate_flow(None)
    ok("None 图被拒绝", not result.ok)

    # 错误信息要点名问题步骤（用户得知道改哪儿）
    result = validate_flow(_chain("print", "rembg"))
    ok("错误信息点名「PDF排版」与其后的步骤",
       any("PDF排版" in e and "去底色" in e for e in result.errors),
       str(result.errors))

    # 缺少开始节点（源PDF）：2026-11-04 曾是硬错误；**2026-11-15 撤销**
    # （用户："任何一个任务节点都可以作为开始节点……包括结束节点"）——
    # 起止圈只是图示，见 _check_legal_combos 的"无起止节点"用例。
