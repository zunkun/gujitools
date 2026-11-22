# -*- coding: utf-8 -*-
"""``step_ports`` 第 1 章：端口声明 / 连线 / BPM 就绪。"""

from __future__ import annotations

from pathlib import Path

from ._helpers import _spec_for


def run(st) -> None:
    _check_ports(st.ok)
    _check_wiring(st.ok)
    _check_bpm_readiness(st.ok)


# ---------------------------------------------------------------- 1. 端口声明
def _check_ports(ok) -> None:
    """① 端口声明来自 spec；产物类型表与落点表自洽。"""
    from desktop.steps import ports
    from desktop.steps.spec import SPECS, spec_by_key

    # 每个步骤的 inputs/outputs 都得是**已登记的端口名**——否则 BPM 连线时
    # 解析不出产物类型，"解耦"就退化成"换个地方硬编码"。
    for spec in SPECS:
        unknown = [
            port for port in (*spec.inputs, *spec.outputs)
            if port not in ports.PORT_ARTIFACTS
        ]
        ok(f"{spec.key} 的端口名都在类型表里", not unknown, str(unknown))

    # 运行阶段的输入/输出应当**等于**对应 spec 的声明。
    for stage in ("extract", "detect", "rembg", "print"):
        spec = _spec_for(stage)
        ok(f"{stage} 的输入端口 = spec.inputs",
           ports.stage_inputs(stage) == tuple(spec.inputs),
           f"{ports.stage_inputs(stage)} vs {spec.inputs}")
        # ⚠️ ``stage_outputs`` 是**步骤级**声明（detect 声明两样都产出）。
        ok(f"{stage} 的输出端口 = spec.outputs",
           ports.stage_outputs(stage) == tuple(spec.outputs),
           f"{ports.stage_outputs(stage)} vs {spec.outputs}")

    # ⚠️ 动作级：同格两个动作各自只产一样——这是 fold_forward 能正确折到
    #   detect_submit（而不是折回 detect 自己）的前提。
    ok("detect 这个动作只产 boxes",
       ports.action_outputs("detect") == ("boxes",),
       str(ports.action_outputs("detect")))
    ok("detect_submit 这个动作只产 pages（裁好的图）",
       ports.action_outputs("detect_submit") == ("pages",),
       str(ports.action_outputs("detect_submit")))
    ok("detect_submit 复用 detect 的步骤定义",
       ports.STAGE_STEPS["detect_submit"] == "detect")
    # fold_forward：要 pages 折到提交、要 boxes 留在检测
    ok("要 pages ⇒ 折到 detect_submit",
       ports.fold_forward("detect", "pages") == "detect_submit",
       ports.fold_forward("detect", "pages"))
    ok("要 boxes ⇒ 留在 detect",
       ports.fold_forward("detect", "boxes") == "detect",
       ports.fold_forward("detect", "boxes"))

    # ⚠️ rembg 是**单一步动作**（2026-10-22 起没有预览/提交两段）。
    ok("rembg 这个动作直接产出 pages（整图去底色成品）",
       ports.action_outputs("rembg") == ("pages",),
       str(ports.action_outputs("rembg")))
    ok("rembg 不再有第二个提交动作",
       "rembg_submit" not in ports.STAGE_STEPS,
       str(ports.STAGE_STEPS))

    # 声明了输出的**动作**必须登记落点，否则产物没有去处。
    # ⚠️ 按动作级判（detect 声明了 pages，但那个落点属于 detect_submit）。
    for stage in ports.STAGE_LOCATIONS:
        for port in ports.action_outputs(stage):
            ok(f"{stage}.{port} 有落点登记",
               ports.location_of(stage, port) is not None, stage)

    # 未知阶段/未知端口返回 None 而不是抛异常（界面上不能因此崩）。
    ok("未登记阶段 → None", ports.artifact_path("T", "nope", "pages") is None)
    ok("未登记端口 → None", ports.artifact_path("T", "extract", "boxes") is None)


# ---------------------------------------------------------------- 2. 连线
def _check_wiring(ok) -> None:
    """② 连线 = BPM 的边。rembg 吃两样、print 的上游可换。"""
    from desktop.steps import ports

    ok("extract 没有上游阶段（源 PDF 由任务供给）",
       ports.supplier_of("extract", "pdf") == ports.SUPPLY_TASK_SOURCE)
    ok("rembg 的页面图来自「检测文本框」的提交（裁好的图）",
       ports.supplier_of("rembg", "pages") == "detect_submit",
       str(ports.supplier_of("rembg", "pages")))
    ok("rembg 不再有 boxes 连线（去底色=整图去底色）",
       ports.supplier_of("rembg", "boxes") is None)
    ok("print 默认吃第三步去底色的成品图",
       ports.supplier_of("print", "pages") == "rembg")

    # ⚠️ **条件连线**：拼版生效时 print 的上游换成 imposition。BPM 编排要支持
    #    "按运行态换上游"，所以它必须落在覆盖表里而不是静态表里。
    ok("拼版开关关 → print 吃 rembg",
       ports.print_pages_supplier(False) == "rembg")
    ok("拼版开关开 → print 吃 imposition",
       ports.print_pages_supplier(True) == "imposition")
    ok("覆盖表只改 print 的 pages 端口",
       ports.print_input_overrides(True) == {("print", "pages"): "imposition"})

    base = "T"
    ok("rembg 的 pages 输入落在检测提交的裁图目录",
       ports.resolve_input(base, "rembg", "pages")
       == Path(base) / "stages" / "detect",
       str(ports.resolve_input(base, "rembg", "pages")))
    ok("检测提交的产物落点是 stages/detect",
       ports.location_of("detect_submit", "pages") == "stages/detect")
    ok("print 默认取图落在 rembg",
       ports.resolve_input(base, "print", "pages")
       == Path(base) / "stages" / "rembg")
    ok("覆盖生效：print 改从 imposition 取图",
       ports.resolve_input(base, "print", "pages",
                           ports.print_input_overrides(True))
       == Path(base) / "stages" / "imposition")
    ok("没连线的端口解析为 None",
       ports.resolve_input(base, "print", "boxes") is None)

    # describe 出中文产物名，别让日志里出现裸英文键名。
    ok("describe 出中文产物名",
       "图片" in ports.describe("rembg") and "→" in ports.describe("rembg"),
       ports.describe("rembg"))


# ---------------------------------------------------------------- 3. BPM 就绪
def _check_bpm_readiness(ok) -> None:
    """③ 与顺序无关的依赖检查——BPM 编排的前置能力。"""
    from desktop.steps import ports

    order = ["extract", "detect", "rembg", "print"]
    ok("按正确顺序没有等待项",
       ports.missing_stages(order) == [], str(ports.missing_stages(order)))
    # 把 rembg 提到 detect 前面 → 它依赖的上游还没跑，必须被点出来。
    scrambled = ["extract", "rembg", "detect", "print"]
    ok("rembg 抢在 detect 前会被点名为缺上游",
       "rembg" in ports.missing_stages(scrambled),
       str(ports.missing_stages(scrambled)))
    ok("extract 永远不缺上游（它是入口）",
       "extract" not in ports.missing_stages(order),
       str(ports.missing_stages(order)))
    # 给了起点 = 跳过已完成的阶段，不把它算成"缺上游"。
    ok("给了起点就不再等它的上游",
       ports.missing_stages(order, start="extract") == [],
       str(ports.missing_stages(order, start="extract")))
