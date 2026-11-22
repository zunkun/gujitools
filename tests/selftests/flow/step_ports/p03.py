# -*- coding: utf-8 -*-
"""``step_ports`` 第 3 章：入口步骤输入 / 就绪守卫。"""

from __future__ import annotations

from pathlib import Path

from ._helpers import _FLOW_REMBG_FIRST, _FLOW_WITHOUT_EXTRACT, _spec_for


def run(st) -> None:
    _check_entry_stage_input(st.ctx, st.ok)
    _check_blocking_inputs(st.ctx, st.ok)


# ------------------------------------------------- 7. 入口步骤（无上游也要有输入）
def _check_entry_stage_input(ctx, ok) -> None:
    """⑦ 自定义流程里**第一个节点一定要有输入可用**（用户 2026-10-06 报障）。

    用户口径：

    > 如果某个节点作为第一个节点，一定要可以有输入可用。

    此前"图片输入"只有一条来路= 上游的 ``pages`` 端口，于是把「检测文本框」
    放在流程第一位时：取图回溯不到供给方 → 落成 ``None`` → 点执行弹"输入未接好"；
    预览永远"暂无图片，请先完成提取"；左下角插图又只往 extract 目录写。
    本节钉住回落的三条边界：

    1. ``pages`` 无上游 ⇒ 落到 ``stages/input/``（**且执行与插图同一目录**）；
    2. ``boxes`` / ``pdf`` **不许**回落（否则"接口没接好"被伪装成"有输入了"）；
    3. 有上游时行为**一字不变**（默认流程照旧走 extract 目录）。
    """
    from desktop.steps import ports
    from desktop.store import TaskStore

    task_dir = Path("X") / "t"
    entry = ports.task_input_dir(task_dir)

    # ---- 1. pages 无上游 → 入口目录 ----
    for stage in ("detect", "rembg", "print", "imposition"):
        got = ports.resolve_input_with_entry(task_dir, stage, "pages", None)
        ok(f"{stage} 无上游时落到入口图片目录", got == entry, f"{got}")
    ok("入口目录是 stages/input（布局唯一声明处）",
       entry.as_posix().endswith("t/stages/input"), str(entry))

    # ---- 2. boxes / pdf 不许回落 ----
    # ⚠️ 2026-10-22：去底色不再吃检测框（整图去底色），所以这里改成问
    #    "仍然不吃 boxes 的阶段也绝不回落"——判据本身（只放行 pages）没变。
    ok("boxes 无上游时不回落（仍报接口没接好）",
       ports.resolve_input_with_entry(task_dir, "detect", "boxes", None) is None)
    ok("extract 的 pdf 走任务源哨兵 → None（由调用方另判）",
       ports.resolve_input_with_entry(task_dir, "extract", "pdf",
                                      ports.SUPPLY_TASK_SOURCE) is None)
    ok("extract 不吃 pages，所以问它 pages 输入不回落",
       ports.resolve_input_with_entry(task_dir, "extract", "pages", None) is None)

    # ---- 3. 有上游时一字不变 ----
    ok("有上游时仍走上游目录（默认流程不受影响）",
       ports.resolve_input_with_entry(task_dir, "detect", "pages", "extract")
       == task_dir / "stages" / "extract")

    # ---- 4. 按图求解：无extract 的自定义流程里 detect 就是入口 ----
    repo = TaskStore(Path(ctx.tmp) / "entry_flow")
    tid = repo.create_task(source_path="", source_hash="", name="入口流程")
    (repo.task_dir(tid) / "flow.bpmn").write_text(
        _FLOW_WITHOUT_EXTRACT, encoding="utf-8")
    diagram = repo.task_diagram(tid)
    ok("图上没有 extract 时流程照样解析得出来",
       diagram.stage_order() == ("detect", "rembg", "print"),
       str(diagram.stage_order()))
    ok("detect 是入口（沿图没有活着的上游）",
       ports.is_entry_stage(diagram, "detect"))
    ok("print 不是入口（上游有 rembg）",
       not ports.is_entry_stage(diagram, "print"))
    ok("detect 的输入回落到该任务的入口目录",
       repo.stage_input(tid, "detect", "pages") == repo.task_input_dir(tid),
       f"{repo.stage_input(tid, 'detect', 'pages')}")
    ok("rembg 的图片输入由上游检测（提交后）供给，不再回落到入口目录",
       repo.stage_input(tid, "rembg", "pages")
       == repo.task_dir(tid) / "stages" / "detect",
       f"{repo.stage_input(tid, 'rembg', 'pages')}")
    # ⚠️ 2026-10-22：去底色的输入由「检测文本框**提交**」供给（裁好的图），
    #    不再是"原始页 + boxes"。这条流程里有 detect 节点 ⇒ rembg 吃它的 pages
    #    产物（``stages/detect``），没提交就是空的——正是"提交才算本步完成"。
    ok("rembg 的图片输入来自检测提交的裁图目录",
       repo.stage_input(tid, "rembg", "pages")
       == repo.task_dir(tid) / "stages" / "detect",
       f"{repo.stage_input(tid, 'rembg', 'pages')}")
    ok("rembg 不再消费检测框",
       "boxes" not in ports.stage_inputs("rembg"),
       str(ports.stage_inputs("rembg")))
    ok("print 仍走去底色提交产物（有上游就不该回落）",
       repo.stage_input(tid, "print", "pages") == repo.rembg_output_dir(tid))
    # ⚠️ 钉死下标：这条自定义流程里 detect 是**格序 0 / 栈页号 1**——两者不等
    #    正是"插了图左侧列表不刷新"的根因（_refresh_preview 拿栈页号当格序用）。
    slots = {s.step: (s.bar_index, s.stack_index) for s in diagram.stage_slots()}
    ok("detect 的格序与栈页号确实不同（复现插图不刷新的条件）",
       slots["detect"][0] != slots["detect"][1], str(slots.get("detect")))


# ----------------------------- 8. 就绪守卫：只查"这张图上真的阻塞"的端口
def _check_blocking_inputs(ctx, ok) -> None:
    """⑧ **就绪守卫不能拿静态声明当判据**（用户 2026-10-06 报障）。

    用户现场：自定义流程把「图片去底色」放**第一个**节点、导了图片目录，
    点执行却弹"这一步的输入还没就位——先把它的上游步骤执行完"。可那条
    流程压根**没有**「检测文本框」，``boxes`` 没有任何供给方，那一步完全
    能跑（按 area 处理整张图）。

    同一处判据还锁死了另一条路：``extract`` 的 ``pdf`` 由**任务自己**供给
    （不是阶段产物目录，``resolve_input_with_entry`` 对任务哨兵返回
    ``None``），拿它当路径查 ``exists()`` 恒为假 ⇒「图片提取」永远点不动。

    规则只一份，见 :func:`desktop.steps.ports.stage_blocking_inputs`。
    """
    from desktop.steps import ports
    from desktop.steps.scheduler import Scheduler, load_default_diagram
    from desktop.store import TaskStore

    default = load_default_diagram()
    active = set(Scheduler.from_diagram(default, {"imposition": True}).stages)

    # ---- 默认流程：行为一字不变 ----
    ok("默认流程里 extract 没有阻塞端口（pdf 由任务自己供给）",
       ports.stage_blocking_inputs(default, "extract", active) == (),
       str(ports.stage_blocking_inputs(default, "extract", active)))
    ok("默认流程里 rembg 只等图片（不再等检测框）",
       ports.stage_blocking_inputs(default, "rembg", active) == ("pages",),
       str(ports.stage_blocking_inputs(default, "rembg", active)))
    ok("默认流程里 detect 要等 extract 的图片",
       ports.stage_blocking_inputs(default, "detect", active) == ("pages",),
       str(ports.stage_blocking_inputs(default, "detect", active)))

    # ---- 没有检测节点的去底色流程：boxes 不再阻塞 ----
    repo = TaskStore(Path(ctx.tmp) / "blocking_flow")
    tid = repo.create_task(source_path="", source_hash="", name="去底色打头")
    (repo.task_dir(tid) / "flow.bpmn").write_text(
        _FLOW_REMBG_FIRST, encoding="utf-8")
    diagram = repo.task_diagram(tid)
    got = repo.required_stage_inputs(tid, "rembg")
    ok("去底色打头、没有检测节点 ⇒ 只等图片",
       got == ("pages",), str(got))
    ok("rembg 的图片输入就是入口图片目录",
       repo.stage_input(tid, "rembg", "pages") == repo.task_input_dir(tid))
    ok("这条流程里 detect 压根不在图上 ⇒ 照声明返回（交给'不在流程里'守卫）",
       ports.stage_blocking_inputs(diagram, "detect", {"rembg", "print"})
       == ("pages",),
       str(ports.stage_blocking_inputs(diagram, "detect", {"rembg", "print"})))
    ok("空图/None 不炸（照声明返回）",
       ports.stage_blocking_inputs(None, "rembg") == ("pages",))

    # ---- store 门面与 ports 判据必须一致（别处别再判一遍）----
    ok("required_stage_inputs 与 ports 判据同源",
       repo.required_stage_inputs(tid, "rembg")
       == ports.stage_blocking_inputs(
           diagram, "rembg",
           set(Scheduler.from_diagram(diagram, {"imposition": True}).stages)))

    # ---- 9b. 拼版的源图是**去底色提交后的成品图**，不是提取出的原图 ----
    # ⚠️ 此前这条连线写的是 ``"extract"``，而页面侧又写死读 ``stages/rembg``，
    #    **一处错、一处掩盖**：默认流程下用户看到的候选池一直是对的，直到页面
    #    按连线取图（正确的做法）才暴露出连线是错的。
    # 判据（业务事实）：``-l``/``-r`` 成对半页图由「检测文本框」的提交产出，
    #    且 ``task_default.bpmn`` 里「图片拼版」排在「图片去底色」**之后**。
    ok("拼版的 pages 由去底色供给（不是提取原图）",
       ports.supplier_of("imposition", "pages") == "rembg",
       str(ports.supplier_of("imposition", "pages")))
    ok("默认流程里拼版取图落在 stages/rembg（去底色成品目录）",
       repo.stage_input(tid, "imposition", "pages")
       == repo.rembg_output_dir(tid),
       f"{repo.stage_input(tid, 'imposition', 'pages')} vs "
       f"{repo.rembg_output_dir(tid)}")

    # ---- 9c. 单一真源：store 不得自带第二份 stage→step 映射 ----
    import desktop.store.tasks as _store_tasks

    ok("store.STAGE_STEP 就是 ports.STAGE_STEPS 的别名（不是第二份）",
       _store_tasks.STAGE_STEP is ports.STAGE_STEPS)
    ok("映射含 imposition（旧的手写表漏了它）",
       ports.STAGE_STEPS.get("imposition") == "imposition",
       str(ports.STAGE_STEPS))

    # ---- 9c'. flow_crops_pages：这批图会不会被第二步按 area 裁过 ----
    # ⚠️ 2026-10-22：area 从去底色搬到「检测文本框」，它决定"提交时怎么裁图"。
    # 拼版要不要成对 ``-l``/``-r`` 全靠这条判据（没有检测步骤 ⇒ 图是整页的 ⇒
    # 拼版吃整图照样拼，area 前提不适用）。
    ok("默认流程里有检测步骤 ⇒ 图会被按 area 裁",
       ports.flow_crops_pages(default) is True,
       str(ports.flow_crops_pages(default)))
    ok("去底色打头、没有检测节点 ⇒ 不裁图（拼版吃整图）",
       ports.flow_crops_pages(diagram) is False,
       str(ports.flow_crops_pages(diagram)))
    ok("空图/None ⇒ 不裁图（保守答案）",
       ports.flow_crops_pages(None) is False)

    # ---- 9d. ⚠️⚠️ **图必须压过静态表**（"这个问题再次提出"的病根）----
    # 用户 2026-10-06 第二次提同一个问题："自定义流程中，总是会有默认流程以及
    # 相关逻辑出现"。上一轮清掉了 27 处**症状**（硬编码下标/写死目录/静默回落），
    # 但没找到**结构病**：`stage_supplier` 的规则是"**先静态声明、后沿图回退**"，
    # 于是 `ports.SUPPLIERS`（一份写死在代码里的**默认流程连线**）在它给的
    # 供给方还留在流程里时**压过用户画的连线**。
    #
    # 复现：两条**节点集合完全相同、连线不同**的流程
    #   A: extract→detect→rembg→print（默认）
    #   B: extract→detect→rembg（支线）+ extract→print（用户明确要跳过检测/去底色）
    # 旧规则下 B 的 print 也读 stages/rembg——**用户画的线被静默丢弃**。
    _STAGE_NODES = {
        "extract": "提取图片", "detect": "检测文本框",
        "rembg": "图片去底色", "print": "PDF排版",
    }

    def _flow(wiring, stages=None):
        stages = stages or _STAGE_NODES
        nodes = "".join(
            f'<bpmn:task id="{s}" name="{n}" guji:stage="{s}"/>'
            for s, n in stages.items()
        )
        flows = "".join(
            f'<bpmn:sequenceFlow id="f{i}" sourceRef="{a}" targetRef="{b}"/>'
            for i, (a, b) in enumerate(wiring)
        )
        return (
            '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/'
            '20100524/MODEL" xmlns:guji="https://guji.tools/bpmn/2025">'
            f'<bpmn:process id="p" isExecutable="false">{nodes}{flows}'
            "</bpmn:process></bpmn:definitions>"
        )

    _got = {}
    _tid_of = {}
    for _label, _wiring in (
        ("A", [("extract", "detect"), ("detect", "rembg"),
               ("rembg", "print")]),
        # ⚠️ rembg 仍在流程里（挂在 detect 后面），静态表的 rembg 因此
        #    "在流程里"——这正是旧规则会把它当赢家的条件。
        ("B", [("extract", "detect"), ("detect", "rembg"),
               ("extract", "print")]),
    ):
        _t = repo.create_task("", "", f"图优先-{_label}")
        _tid_of[_label] = _t
        (repo.task_dir(_t) / "flow.bpmn").write_text(
            _flow(_wiring), encoding="utf-8")
        _got[_label] = (
            repo.stage_supplier(_t, "print", "pages"),
            repo.stage_input(_t, "print", "pages"),
        )
    ok("默认连线：print 吃去底色成品（与改造前一致）",
       _got["A"] == (
           "rembg", repo.rembg_output_dir(_tid_of["A"])),
       str(_got["A"]))
    ok("⚠️ 改过连线：print 吃图上**真正喂它**的那个（用户的线不被丢弃）",
       _got["B"] == ("extract", repo.extract_output_dir(_tid_of["B"])),
       str(_got["B"]))
    ok("两条连线不同的流程 ⇒ 取图目录**必须不同**（否则＝默认流程在起作用）",
       _got["A"][1] != _got["B"][1], f"A={_got['A'][1]} B={_got['B'][1]}")

    # ⚠️ 反过来：**网关分支（图说不清）必须仍走静态表 + 条件**，否则默认流程
    #    的「是否拼版」会变成随机（两条边在图上都是实线）。默认流程那份模板
    #    就是这种：沿图回溯 print 会同时看到「图片拼版」与「图片去底色」。
    _amb = repo.create_task("", "", "网关歧义")
    (repo.task_dir(_amb) / "flow.bpmn").write_text(_flow([
        ("extract", "detect"), ("detect", "rembg"), ("rembg", "print"),
        ("extract", "imposition"), ("imposition", "print"),
    ], stages={**_STAGE_NODES, "imposition": "图片拼版"}), encoding="utf-8")
    ok("图说不清（有两条产出方）⇒ 退回静态声明 + 条件，不随机挑一个",
       repo.stage_supplier(_amb, "print", "pages", False) == "rembg"
       and repo.stage_supplier(_amb, "print", "pages", True) == "imposition",
       f"off={repo.stage_supplier(_amb, 'print', 'pages', False)} "
       f"on={repo.stage_supplier(_amb, 'print', 'pages', True)}")

    # ⚠️ 端口声明仍是"这一步吃什么"的唯一真源：图上有人产出 boxes 不等于
    #    print 吃 boxes（曾因漏这条守卫，`print.boxes` 解析出了 boxes.json）。
    ok("这一步不声明的端口 ⇒ 没有这个输入（哪怕图上有人产出它）",
       repo.stage_input(_amb, "print", "boxes") is None,
       str(repo.stage_input(_amb, "print", "boxes")))

    # ---- 9e. 条件开关通用化：CONDITIONS 从 spec 派生，不再手写 ----
    # 以前 ``scheduler.CONDITIONS == {"imposition": "imposition"}`` 是手写表，
    # 再加一个可选步骤就要同时改条件表、store 的 flags 构造、调用方传参三处。
    # 现在：键集合从 ``role == "optional"`` 派生，开关状态走通用的
    # ``store.step_enabled``（``drafts/<步骤>.json`` 的 ``enabled``）。
    from desktop.steps.scheduler import CONDITIONS
    from desktop.steps.spec import OPTIONAL_STEPS
    ok("CONDITIONS 从 spec 的 optional 角色派生（不是第二份手写表）",
       CONDITIONS == {step: step for step in OPTIONAL_STEPS},
       str(CONDITIONS))
    ok("CONDITIONS 里只有可选步骤（主链步骤不受开关控制）",
       all(_spec_for(s).role == "optional" for s in CONDITIONS),
       str(CONDITIONS))
    _flag_task = repo.create_task("", "", "开关读写")
    ok("新任务的可选开关默认全关",
       all(repo.step_enabled(_flag_task, s) is False for s in OPTIONAL_STEPS))
    repo.save_imposition_doc(
        _flag_task, {"enabled": True, "pages": []})
    ok("step_enabled 与拼版开关同源（同一文件同一键）",
       repo.step_enabled(_flag_task, "imposition") is True
       and repo.imposition_enabled(_flag_task) is True)
    repo.save_imposition_doc(
        _flag_task, {"enabled": False, "pages": []})
    ok("开关关掉 ⇒ 两边一起是 False（不会各说各话）",
       repo.step_enabled(_flag_task, "imposition") is False
       and repo.imposition_enabled(_flag_task) is False)
    ok("非法任务号查开关不抛（当没开）",
       repo.step_enabled("xxxx", "imposition") is False)
    # flags 构造器：键自动覆盖全部可选步骤，imposition 用调用方的值
    #（调用方传的是 effective，含 area＋在流程里 两道闸，不能只读开关）
    _flags = repo.scheduler_flags(_flag_task, imposition_active=True)
    ok("scheduler_flags 的键 == 全部可选步骤（加步骤不用改调用方）",
       set(_flags) == set(OPTIONAL_STEPS), str(_flags))
    ok("imposition 那一键用调用方传的值（effective，不是纯开关）",
       _flags.get("imposition") is True)
    _flags_off = repo.scheduler_flags(_flag_task, imposition_active=False)
    ok("调用方传 False ⇒ imposition 关（area 不支持时下游退回走去底色）",
       _flags_off.get("imposition") is False)
    # 通用 flags 真的能驱动状态机跳过（走 Scheduler，不走任何特例）
    _sched = Scheduler.from_diagram(
        repo.task_diagram(_flag_task), repo.scheduler_flags(_flag_task))
    ok("开关全关 ⇒ 可选步骤被跳过（SKIPPED，不是凭空消失）",
       all(_sched.states.get(s) == "skipped" or s not in _sched.stages
           for s in OPTIONAL_STEPS),
       str(_sched.stages))
