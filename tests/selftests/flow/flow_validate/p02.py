# -*- coding: utf-8 -*-
"""``flow_validate`` 第 2 章：图结构 / 警告。"""

from __future__ import annotations

from ._helpers import _chain


def run(st) -> None:
    _check_structure(st.ok)
    _check_warnings(st.ok)


# --------------------------------------- ②b 图结构（2026-11-04，任务 0021）
def _check_structure(ok) -> None:
    """孤立节点 / 环形回路 / 多输出 / 开始节点数量。"""
    from desktop.steps.bpmn_diagram import (
        KIND_END, KIND_EXCLUSIVE, KIND_PARALLEL, KIND_START, KIND_TASK,
        DiagramFlow, DiagramNode, FlowDiagram,
    )
    from desktop.steps.validate import validate_flow

    # 孤立节点：主链之外挂着一个没有任何连线的「OCR 识别」
    chain = _chain("detect", "print")
    isolated = FlowDiagram(
        nodes=chain.nodes + (DiagramNode("iso", KIND_TASK, "OCR 识别"),),
        flows=chain.flows,
    )
    result = validate_flow(isolated)
    ok("有孤立节点 ⇒ 拒绝保存且点名节点",
       not result.ok and any("孤立" in e and "OCR 识别" in e
                             for e in result.errors),
       f"errors={result.errors}")

    # 两段图：主链从开始节点出发，另有一小段 b→e 接不上主链
    detached = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框", stage="detect"),
               DiagramNode("b", KIND_TASK, "图片去底色", stage="rembg"),
               DiagramNode("e", KIND_END, "生成PDF")),
        flows=(DiagramFlow("f1", "s", "a"),
               DiagramFlow("f2", "b", "e")),
    )
    result = validate_flow(detached)
    ok("断开的两段图 ⇒ 拒绝保存并指出孤立节点",
       not result.ok and any("孤立" in e for e in result.errors),
       f"errors={result.errors}")

    # 环形回路：rembg → detect 回流
    loop = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框", stage="detect"),
               DiagramNode("b", KIND_TASK, "图片去底色", stage="rembg")),
        flows=(DiagramFlow("f1", "s", "a"),
               DiagramFlow("f2", "a", "b"),
               DiagramFlow("f3", "b", "a")),
    )
    result = validate_flow(loop)
    ok("环形回路 ⇒ 拒绝保存且点名回路",
       not result.ok and any("环形回路" in e and "检测文本框" in e
                             for e in result.errors),
       f"errors={result.errors}")

    # 普通节点两条输出（不借 XOR）
    fork = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框", stage="detect"),
               DiagramNode("b", KIND_TASK, "图片去底色", stage="rembg"),
               DiagramNode("c", KIND_TASK, "图片去底色2", stage="rembg")),
        flows=(DiagramFlow("f1", "s", "a"),
               DiagramFlow("f2", "a", "b"),
               DiagramFlow("f3", "a", "c")),
    )
    result = validate_flow(fork)
    ok("普通节点两条输出 ⇒ 拒绝保存（只有 XOR 网关能分支）",
       not result.ok and any("输出连线" in e and "检测文本框" in e
                             for e in result.errors),
       f"errors={result.errors}")

    # XOR 网关两条输出 ⇒ 合法（默认流程「是否拼版」就靠它）
    xor = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框", stage="detect"),
               DiagramNode("g", KIND_EXCLUSIVE, "是否拼版"),
               DiagramNode("b", KIND_TASK, "图片拼版", stage="imposition"),
               DiagramNode("c", KIND_TASK, "图片去底色", stage="rembg")),
        flows=(DiagramFlow("f1", "s", "a"),
               DiagramFlow("f2", "a", "g"),
               DiagramFlow("f3", "g", "b"),
               DiagramFlow("f4", "g", "c")),
    )
    result = validate_flow(xor)
    ok("XOR 网关两条输出 ⇒ 合法放行",
       result.ok, f"errors={result.errors}")

    # 非 XOR 网关两条输出 ⇒ 拒绝（运行语义没有并行/包容网关）
    parallel = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框", stage="detect"),
               DiagramNode("g", KIND_PARALLEL, "并行"),
               DiagramNode("b", KIND_TASK, "图片去底色", stage="rembg"),
               DiagramNode("c", KIND_TASK, "图片去底色2", stage="rembg")),
        flows=(DiagramFlow("f1", "s", "a"),
               DiagramFlow("f2", "a", "g"),
               DiagramFlow("f3", "g", "b"),
               DiagramFlow("f4", "g", "c")),
    )
    result = validate_flow(parallel)
    ok("非 XOR 网关两条输出 ⇒ 拒绝保存",
       not result.ok and any("输出连线" in e for e in result.errors),
       f"errors={result.errors}")

    # 两个开始节点
    two_starts = FlowDiagram(
        nodes=(DiagramNode("s1", KIND_START, "源PDF"),
               DiagramNode("s2", KIND_START, "另一个开始"),
               DiagramNode("a", KIND_TASK, "检测文本框", stage="detect")),
        flows=(DiagramFlow("f1", "s1", "a"),
               DiagramFlow("f2", "s2", "a")),
    )
    result = validate_flow(two_starts)
    ok("两个开始节点 ⇒ 拒绝保存",
       not result.ok and any("只能有一个「开始节点」" in e
                             for e in result.errors),
       f"errors={result.errors}")

    # 没有开始节点时孤立节点**照样**要拦（0 个起点的分支：弱连通分量判据）
    no_source = _chain("detect", "print", source=False, end=False)
    lone = FlowDiagram(
        nodes=no_source.nodes + (DiagramNode("iso", KIND_TASK, "OCR 识别"),),
        flows=no_source.flows,
    )
    result = validate_flow(lone)
    ok("无开始节点时孤立节点仍被拒绝（弱连通分量兜底）",
       not result.ok and any("孤立" in e and "OCR 识别" in e
                             for e in result.errors),
       f"errors={result.errors}")


# --------------------------------------------------------------- ③ 警告
def _check_warnings(ok) -> None:
    """与习惯不符但跑得通的组合：只给警告，``ok`` 仍为真。"""
    from desktop.steps.validate import validate_flow

    # 拼版在但没有判断节点：⚠️ 2026-10-08 起**不再警告**——网关依附「图片拼版」
    # 且界面上已没有"添加判断"入口（用户："其实根本就没有判断这个组件"），
    # 提示用户去做一件界面上做不到的事就是死胡同。这是合法且常见的状态：
    # 那一步无条件执行，启用与否由「图片拼版」面板的开关决定。
    result = validate_flow(_chain("imposition", "print"))
    ok("有拼版没判断节点 ⇒ 合法且**不再**警告（入口已撤，提示无用）",
       result.ok and not any("判断" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # extract 不在第一位
    result = validate_flow(_chain("detect", "extract", "print"))
    ok("extract 不在第一位 ⇒ 警告且不拦",
       result.ok and any("提取" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # ⚠️ 2026-11-04 起「有 extract 但没有源PDF」不再只是警告：缺少开始节点
    #    是硬错误（见 _check_illegal_combos 的同一条用例）。

    # 同一阶段两个节点（两个「PDF排版」）——**B 方案后这是合法且零警告的**：
    # 图片拼版/检测文本框/图片去底色/PDF排版都可以有多个节点，它们彼此独立
    # （各自参数、各自产物落点 ``stages/<阶段>~<节点>``），所以不能把用户明确
    # 要的能力说成"有问题"（旧警告已于 2026-10-17 删除）。
    from desktop.steps.bpmn_diagram import (
        KIND_START, KIND_TASK, DiagramFlow, DiagramNode, FlowDiagram,
        stage_of_name,
    )

    diagram = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "PDF排版",
                           stage=stage_of_name("PDF排版")),
               DiagramNode("b", KIND_TASK, "PDF排版2",
                           stage=stage_of_name("PDF排版"))),
        flows=(DiagramFlow("f0", "s", "a"),
               DiagramFlow("f1", "a", "b")),
    )
    result = validate_flow(diagram)
    ok("同一阶段两个节点 ⇒ 合法且**不**警告（支持多节点）",
       result.ok and not result.warnings,
       f"ok={result.ok} warnings={result.warnings}")

    # 未接入运行的节点（随手画的「OCR 识别」，但**连着**主流程）
    diagram = FlowDiagram(
        nodes=(DiagramNode("s", KIND_START, "源PDF"),
               DiagramNode("a", KIND_TASK, "检测文本框",
                           stage=stage_of_name("检测文本框")),
               DiagramNode("b", KIND_TASK, "OCR 识别")),
        flows=(DiagramFlow("f0", "s", "a"),
               DiagramFlow("f1", "a", "b")),
    )
    result = validate_flow(diagram)
    ok("未接入运行的节点 ⇒ 警告且不拦",
       result.ok and any("OCR 识别" in w for w in result.warnings),
       f"warnings={result.warnings}")

    # 合法且干净的图：零警告（别让警告变噪声）
    result = validate_flow(_chain("extract", "detect", "rembg",
                                  "imposition", "print", gateway=True))
    ok("完整默认流程零警告", result.ok and not result.warnings,
       f"warnings={result.warnings}")
