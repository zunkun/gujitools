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
"""

from __future__ import annotations

from pathlib import Path

NAME = "step_ports"
#: 依赖 ``tasklist``：它提供了 ``ctx.tid``（一个已导入的任务）供详情页用例用。
#: 其余五节是纯逻辑，不碰窗口。
DEPENDS: list[str] = ["tasklist"]
TITLE = "步骤端口模型与模块页复用"

#: 模块页源码目录（相对仓库根）
_MODULES_DIR = Path("desktop") / "modules"

#: **普通步骤页**（应当继承 ``StepModulePage`` 的那批）。
#: ⚠️ 不写死数量：判断依据是"是不是一个带 command 的普通步骤"。拼版页**有意**
#: 不在其中（它的源是一批图、执行是纯函数导出，外壳对不上），见第 5 节。
_REGULAR_KEYS = ("extract", "detect", "rembg", "print")


def run(ctx) -> None:  # noqa: ARG001 - 不需要窗口夹具
    from tests.selftests._context import ok

    _check_ports(ok)
    _check_wiring(ok)
    _check_bpm_readiness(ok)
    _check_store_derivation(ctx, ok)
    _check_step_module_page_reuse(ok)
    _check_detail_metadata(ctx, ok)
    _check_entry_stage_input(ctx, ok)
    _check_blocking_inputs(ctx, ok)
    _check_source_pdf_pairing(ok)
    _check_end_event_cascade(ok)


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
    ok("rembg 的 boxes 无上游时不回落（仍报接口没接好）",
       ports.resolve_input_with_entry(task_dir, "rembg", "boxes", None) is None)
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
    ok("print 不是入口（上游有 rembg_submit）",
       not ports.is_entry_stage(diagram, "print"))
    ok("detect 的输入回落到该任务的入口目录",
       repo.stage_input(tid, "detect", "pages") == repo.task_input_dir(tid),
       f"{repo.stage_input(tid, 'detect', 'pages')}")
    ok("rembg 的图片输入同样回落到入口目录",
       repo.stage_input(tid, "rembg", "pages") == repo.task_input_dir(tid))
    ok("rembg 的检测框仍由 detect 供给（没被回落吃掉）",
       repo.stage_input(tid, "rembg", "boxes")
       == repo.task_dir(tid) / "boxes.json")
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
    ok("默认流程里 rembg 仍然要等 detect（boxes 是阻塞端口）",
       ports.stage_blocking_inputs(default, "rembg", active) == ("pages", "boxes"),
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
    ok("去底色打头、没有检测节点 ⇒ 只等图片，不等检测框",
       got == ("pages",), str(got))
    ok("rembg 的图片输入就是入口图片目录",
       repo.stage_input(tid, "rembg", "pages") == repo.task_input_dir(tid))
    ok("这条流程里 detect 压根不在图上 ⇒ 照声明返回（交给'不在流程里'守卫）",
       ports.stage_blocking_inputs(diagram, "detect", {"rembg", "print"})
       == ("pages",),
       str(ports.stage_blocking_inputs(diagram, "detect", {"rembg", "print"})))
    ok("空图/None 不炸（照声明返回）",
       ports.stage_blocking_inputs(None, "rembg") == ("pages", "boxes"))

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
    # 判据（业务事实）：``-l``/``-r`` 成对半页图**只有 area=1 的去底色产出**，
    #    且 ``task_default.bpmn`` 里「图片拼板」排在「图片去底色」**之后**。
    ok("拼版的 pages 由去底色提交供给（不是提取原图）",
       ports.supplier_of("imposition", "pages") == "rembg_submit",
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

    # ---- 9c'. detect_feeds_rembg：去底色拿得到检测框吗（area 锁 4 的判据）----
    # 用户 2026-10-07：去底色作为第一个节点（前面没有检测）时 area 必须
    # 固定 4 且不可改——1/2/3 都要吃检测框，没框的页裁出来一片空白。
    # 同一份判据还放行"没有检测数据"流程里的拼版（吃整图照样拼）。
    ok("默认流程里 detect 在 rembg 上游 ⇒ 有检测数据",
       ports.detect_feeds_rembg(default) is True,
       str(ports.detect_feeds_rembg(default)))
    ok("去底色打头、没有检测节点 ⇒ 没有检测数据（area 该锁 4）",
       ports.detect_feeds_rembg(diagram) is False,
       str(ports.detect_feeds_rembg(diagram)))
    ok("空图/None ⇒ 没有检测数据（保守答案）",
       ports.detect_feeds_rembg(None) is False)

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
        # ⚠️ rembg 仍在流程里（挂在 detect 后面），静态表的 rembg_submit 因此
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
    ok("默认连线：print 吃去底色提交（与改造前一致）",
       _got["A"] == (
           "rembg_submit", repo.rembg_output_dir(_tid_of["A"])),
       str(_got["A"]))
    ok("⚠️ 改过连线：print 吃图上**真正喂它**的那个（用户的线不被丢弃）",
       _got["B"] == ("extract", repo.extract_output_dir(_tid_of["B"])),
       str(_got["B"]))
    ok("两条连线不同的流程 ⇒ 取图目录**必须不同**（否则＝默认流程在起作用）",
       _got["A"][1] != _got["B"][1], f"A={_got['A'][1]} B={_got['B'][1]}")

    # ⚠️ 反过来：**网关分支（图说不清）必须仍走静态表 + 条件**，否则默认流程
    #    的「是否拼版」会变成随机（两条边在图上都是实线）。默认流程那份模板
    #    就是这种：沿图回溯 print 会同时看到「图片拼板」与「图片去底色」。
    _amb = repo.create_task("", "", "网关歧义")
    (repo.task_dir(_amb) / "flow.bpmn").write_text(_flow([
        ("extract", "detect"), ("detect", "rembg"), ("rembg", "print"),
        ("extract", "imposition"), ("imposition", "print"),
    ], stages={**_STAGE_NODES, "imposition": "图片拼版"}), encoding="utf-8")
    ok("图说不清（有两条产出方）⇒ 退回静态声明 + 条件，不随机挑一个",
       repo.stage_supplier(_amb, "print", "pages", False) == "rembg_submit"
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
       all(ports.spec_for_stage(s) is not None
           and ports.spec_for_stage(s).role == "optional"
           for s in CONDITIONS),
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


# ------------------------------------ 9. 源 PDF ↔ 提取图片：成对关系（纯逻辑）
def _check_source_pdf_pairing(ok) -> None:
    """「上传 PDF」与「提取图片」成对，判据是**图上的性质**（用户 2026-10-06）。

    > 如果删除了 上传pdf 或者 pdf图片提取中的一个，另外一个的存在没有意义，
    > 因此需要同步删除另外一个

    这里只验**判据**（纯逻辑，不碰界面）；真正的联动删除在
    ``bpmn_editor``（工具栏「删除」与 Delete 键**两条路径**都要成对），
    由 ``flow_ui`` 第 18 节端到端验。

    ⚠️ 「源 PDF」在图上**不是阶段**而是一个 ``startEvent``，所以
    **不能按 ``stage`` 判**——只能按事件类型或节点名认。
    """
    from desktop.steps import ports
    from desktop.steps.scheduler import load_default_diagram

    d = load_default_diagram()
    pdf_ids = ports.source_pdf_node_ids(d)
    ok("默认流程里认得出「源 PDF」节点（它是 startEvent，没有 stage）",
       len(pdf_ids) == 1, str(pdf_ids))
    ok("它是源 PDF 节点（is_source_pdf_node）",
       ports.is_source_pdf_node(d, pdf_ids[0]))
    extract = next(n.id for n in d.nodes if n.stage == "extract")
    detect = next(n.id for n in d.nodes if n.stage == "detect")

    ok("删 extract ⇒ 配对节点是「源 PDF」",
       ports.paired_node_for_stage(d, extract) in pdf_ids,
       str(ports.paired_node_for_stage(d, extract)))
    ok("删「源 PDF」⇒ 配对节点是 extract",
       ports.paired_node_for_stage(d, pdf_ids[0]) == extract,
       str(ports.paired_node_for_stage(d, pdf_ids[0])))
    ok("删其它步骤（detect）没有配对（别乱删）",
       ports.paired_node_for_stage(d, detect) is None,
       str(ports.paired_node_for_stage(d, detect)))

    # ⚠️ 已删掉 extract 时，删源 PDF **不能**再返回一个不存在的节点
    trimmed = type(d)(
        nodes=tuple(n for n in d.nodes if n.stage != "extract"),
        flows=tuple(f for f in d.flows
                    if f.source != extract and f.target != extract),
    )
    ok("extract 已经不在图里了 ⇒ 删源 PDF 没有配对（返回 None，不给幽灵 id）",
       ports.paired_node_for_stage(trimmed, pdf_ids[0]) is None,
       str(ports.paired_node_for_stage(trimmed, pdf_ids[0])))
    ok("空图/None 不炸（无节点、无配对）",
       ports.paired_node_for_stage(None, "x") is None
       and ports.source_pdf_node_ids(None) == ())


# ------------------------- 9b. 生成PDF结束事件附在PDF排版上（纯逻辑）
def _check_end_event_cascade(ok) -> None:
    """删「PDF排版」⇒ 附在后面的「生成PDF」结束事件被孤立（用户 2026-10-07）。

    > 流程图编辑中，生成PDF附在PDF排版，如果删除了PDF排版，
    > 那么生成PDF就一定不存在

    这里只验**判据**（纯逻辑，不碰界面）；编辑器两条删除路径的端到端
    联动由 ``flow_ui`` 第 19 节验。

    ⚠️ 判据是**图上的性质**（结束事件的入线是否全部来自被删节点），
    **不按名字认「生成PDF」**——结束事件不进拓扑序、没有运行语义。
    """
    from desktop.steps import ports
    from desktop.steps.bpmn_diagram import KIND_END
    from desktop.steps.scheduler import load_default_diagram

    d = load_default_diagram()
    print_node = next(n for n in d.nodes if n.stage == "print")
    imposition = next(n for n in d.nodes if n.stage == "imposition")
    detect = next(n for n in d.nodes if n.stage == "detect")
    ends = [n for n in d.nodes if n.kind == KIND_END]
    ok("默认流程里有一个结束事件（生成PDF），挂在「PDF排版」后面",
       len(ends) == 1, str([n.name for n in ends]))
    ok("删「PDF排版」⇒「生成PDF」结束事件被孤立",
       ports.orphaned_end_event_ids(d, print_node.id) == (ends[0].id,),
       str(ports.orphaned_end_event_ids(d, print_node.id)))
    ok("删「图片拼板」⇒「生成PDF」**不**孤立（入线还剩 PDF排版 那条）",
       ports.orphaned_end_event_ids(d, imposition.id) == (),
       str(ports.orphaned_end_event_ids(d, imposition.id)))
    ok("删其它步骤（detect）不牵连结束事件",
       ports.orphaned_end_event_ids(d, detect.id) == (),
       str(ports.orphaned_end_event_ids(d, detect.id)))
    ok("None/不传节点 不炸（返回空元组）",
       ports.orphaned_end_event_ids(None, "x") == ()
       and ports.orphaned_end_event_ids(d) == ())


#: 一条**不含 extract** 的自定义流程（detect 打头）——用户 2026-10-06 的报障现场。
_FLOW_WITHOUT_EXTRACT = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
 xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
 xmlns:guji="http://guji.local"
 id="Defs_1" targetNamespace="http://bpmn.io/schema/bpmn">
 <bpmn:process id="Process_1" isExecutable="false">
  <bpmn:startEvent id="start"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
  <bpmn:task id="t_detect" name="检测文本框" guji:stage="detect"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="t_rembg" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:task id="t_print" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
  <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="t_detect"/>
  <bpmn:sequenceFlow id="f2" sourceRef="t_detect" targetRef="t_rembg"/>
  <bpmn:sequenceFlow id="f3" sourceRef="t_rembg" targetRef="t_print"/>
 </bpmn:process>
 <bpmndi:BPMNDiagram id="D1"><bpmndi:BPMNPlane id="P1" bpmnElement="Process_1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


#: 一条**去底色打头**的自定义流程（用户 2026-10-06 的报障现场）：没有
#: 「检测文本框」，所以 ``rembg`` 的 ``boxes`` 在这张图上**没有供给方**。
_FLOW_REMBG_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:guji="http://guji.local"
  id="Defs_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="false">
   <bpmn:startEvent id="start"><bpmndi:OMNDIOSExtension/></bpmn:startEvent>
   <bpmn:task id="t_rembg" name="图片去底色" guji:stage="rembg"><bpmndi:OMNDIOSExtension/></bpmn:task>
   <bpmn:task id="t_print" name="生成PDF" guji:stage="print"><bpmndi:OMNDIOSExtension/></bpmn:task>
   <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="t_rembg"/>
   <bpmn:sequenceFlow id="f2" sourceRef="t_rembg" targetRef="t_print"/>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="D1"><bpmndi:BPMNPlane id="P1" bpmnElement="Process_1"/></bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


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
        spec = spec_by_key(stage)
        ok(f"{stage} 的输入端口 = spec.inputs",
           ports.stage_inputs(stage) == tuple(spec.inputs),
           f"{ports.stage_inputs(stage)} vs {spec.inputs}")
        ok(f"{stage} 的输出端口 = spec.outputs",
           ports.stage_outputs(stage) == tuple(spec.outputs),
           f"{ports.stage_outputs(stage)} vs {spec.outputs}")

    # rembg_submit 是「提交本次任务」：同一步骤的第二个动作，不重新吃框。
    ok("rembg_submit 复用 rembg 的步骤定义",
       ports.STAGE_STEPS["rembg_submit"] == "rembg")
    ok("rembg_submit 不重复消费检测框",
       ports.stage_inputs("rembg_submit") == ("pages",),
       str(ports.stage_inputs("rembg_submit")))

    # 声明了输出的阶段必须登记落点，否则产物没有去处。
    for stage in ports.STAGE_LOCATIONS:
        for port in ports.stage_outputs(stage):
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
    ok("rembg 的页面图来自 extract",
       ports.supplier_of("rembg", "pages") == "extract")
    ok("rembg 的检测框来自 detect",
       ports.supplier_of("rembg", "boxes") == "detect")
    ok("print 默认吃第三步提交的成品图",
       ports.supplier_of("print", "pages") == "rembg_submit")

    # ⚠️ **条件连线**：拼版生效时 print 的上游换成 imposition。BPM 编排要支持
    #    "按运行态换上游"，所以它必须落在覆盖表里而不是静态表里。
    ok("拼版开关关 → print 吃 rembg_submit",
       ports.print_pages_supplier(False) == "rembg_submit")
    ok("拼版开关开 → print 吃 imposition",
       ports.print_pages_supplier(True) == "imposition")
    ok("覆盖表只改 print 的 pages 端口",
       ports.print_input_overrides(True) == {("print", "pages"): "imposition"})

    base = "T"
    ok("rembg 的 pages 输入落在 extract 的产物目录",
       ports.resolve_input(base, "rembg", "pages")
       == Path(base) / "stages" / "extract")
    ok("rembg 的 boxes 输入落在任务根的 boxes.json",
       ports.resolve_input(base, "rembg", "boxes") == Path(base) / "boxes.json")
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

    order = ["extract", "detect", "rembg", "rembg_submit", "print"]
    ok("按正确顺序没有等待项",
       ports.missing_stages(order) == [], str(ports.missing_stages(order)))
    # 把 rembg 提到 detect 前面 → 它依赖的上游还没跑，必须被点出来。
    scrambled = ["extract", "rembg", "detect", "rembg_submit", "print"]
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


# ---------------------------------------------------------------- 4. store 派生
def _check_store_derivation(ctx, ok) -> None:
    """④ store 的路径方法必须**由端口表派生**（加一步不用改 store）。"""
    from desktop.steps import ports
    from desktop.store import TaskStore

    repo = TaskStore(Path(ctx.tmp) / "ports_store")
    tid = "0042"
    task_dir = repo.task_dir(tid)

    # ⚠️ 逐个对照：这些路径躺在用户磁盘的老任务上，改错一个就是数据事故。
    for name, stage, port in (
        ("extract_output_dir", "extract", "pages"),
        ("rembg_output_dir", "rembg_submit", "pages"),
        ("rembg_preview_output_dir", "rembg", "pages"),
        ("imposition_output_dir", "imposition", "pages"),
        ("print_output_pdf", "print", "pdf"),
    ):
        got = getattr(repo, name)(tid)
        want = ports.artifact_path(task_dir, stage, port)
        ok(f"{name} 与端口表一致", got == want, f"{got} vs {want}")

    ok("stage_input 按连线取 print 的上游图",
       repo.stage_input(tid, "print", "pages") == repo.rembg_output_dir(tid))
    ok("拼版生效时 stage_input 换上游",
       repo.stage_input(tid, "print", "pages", imposition_active=True)
       == repo.imposition_output_dir(tid))
    ok("detect 的坐标文件落在任务根",
       repo.stage_input(tid, "rembg", "boxes") == task_dir / "boxes.json")
    # 未登记的端口要给一个能看懂的错，而不是 NoneType 崩溃。
    try:
        repo.artifact(tid, "extract", "boxes")
    except KeyError:
        ok("未登记端口 → KeyError（不是 NoneType 崩溃）", True)
    else:
        ok("未登记端口 → KeyError（不是 NoneType 崩溃）", False, "居然成功了")


# ---------------------------------------------------------------- 5. 组件复用
def _check_step_module_page_reuse(ok) -> None:
    """⑤ 步骤页**继承** StepModulePage，且页面里不再抄一遍外设。"""
    import importlib

    from desktop.modules import module_by_key
    from desktop.modules.base import ModulePage, StepModulePage
    from tests.selftests._context import imported_modules

    ok("StepModulePage 是 ModulePage 的子类",
       issubclass(StepModulePage, ModulePage))

    # 拼版页**有意**不继承（源是一批图、执行是纯函数导出）——钉住它，免得将来
    # "为了统一"被硬塞进 StepModulePage 却对不上外壳。
    imposition_cls = importlib.import_module(
        "desktop.modules.imposition"
    ).PAGE
    ok("拼版页直接继承 ModulePage（外壳对不上 StepModulePage）",
       not issubclass(imposition_cls, StepModulePage)
       and issubclass(imposition_cls, ModulePage))

    root = Path(__file__).resolve().parents[2]
    # ⚠️ **只查普通步骤页**：它们共用的外设必须来自基类。页面里若还出现
    #    `SourceZone(` / `StepControl(`，就是又抄了一遍（这正是 2026-10-03
    #    之前四个页面各抄一遍的形态）。
    banned = ("SourceZone(", "StepControl(")
    for key in _REGULAR_KEYS:
        module = module_by_key(key)
        ok(f"{key} 有导航条目", module is not None, key)
        if module is None:
            continue
        source = (root / _MODULES_DIR / key / "page.py").read_text(encoding="utf-8")
        page_cls = importlib.import_module(
            f"desktop.modules.{module.key}"
        ).PAGE
        ok(f"{key} 页继承 StepModulePage",
           issubclass(page_cls, StepModulePage), str(page_cls.__mro__[:3]))
        clones = [token for token in banned if token in source]
        ok(f"{key} 页不再自建输入区/控制区", not clones, str(clones))
        # 页面也不该再直接 import 那两个模块（应当经基类拿）。
        imported = imported_modules(source)
        leaky = sorted(
            name for name in imported
            if name.endswith(".source_zone") or name.endswith(".control")
        )
        ok(f"{key} 页不直接 import 输入区/控制区模块", not leaky, str(leaky))


# ------------------------------------------------- 6. 详情页元数据（不再 if stage）
def _check_detail_metadata(ctx, ok) -> None:
    """⑥ 详情页那几处 if stage 已换成**声明**：值对、且页面确实读它。"""
    from desktop.steps import ports
    from desktop.store.tasks import STAGES

    # --- spec 层面的值（与改动前的 if-else 逐条对照）---
    ok("extract 按钮是「执行本子任务」",
       ports.spec_for_stage("extract").run_button_text == "执行本子任务")
    ok("rembg 按钮是「生成预览」且有提交按钮",
       ports.spec_for_stage("rembg").run_button_text == "生成预览"
       and ports.spec_for_stage("rembg").has_submit is True)
    ok("print 按钮是「生成PDF」且无提交按钮",
       ports.spec_for_stage("print").run_button_text == "生成PDF"
       and ports.spec_for_stage("print").has_submit is False)
    ok("只有 rembg 声明了提交按钮",
       [s for s in STAGES if ports.spec_for_stage(s).has_submit] == ["rembg"])
    ok("print 控制列更宽（400~580），其余 340~440",
       ports.spec_for_stage("print").control_width == (400, 580)
       and all(ports.spec_for_stage(s).control_width == (340, 440)
               for s in STAGES if s != "print"))
    ok("detect 用专属区块，其余用「执行记录」",
       [s for s in STAGES if ports.spec_for_stage(s).panel_extra] == ["detect"]
       and ports.spec_for_stage("detect").panel_extra == "detect_stats")
    ok("print 历史回填跳过 pdf_name/title_text",
       set(ports.spec_for_stage("print").history_skip) == {"pdf_name", "title_text"})
    ok("extract 的 pages 只在自动回填时跳过",
       ports.spec_for_stage("extract").auto_fill_skip == ("pages",)
       and ports.spec_for_stage("extract").history_skip == ())
    ok("每一步都声明了主预览控件",
       all(ports.spec_for_stage(s).preview_attr for s in STAGES),
       str({s: ports.spec_for_stage(s).preview_attr for s in STAGES}))

    # --- 页面层面：真的读 spec，而不是又写回 if stage ---
    # ⚠️ **另建一个详情页 + 一个任务**，不要动共享的 ``ctx.d``/``ctx.tid``：
    #    后面若干模块（rembg / print_stage / stale_chain…）依赖详情页停在特定步骤，
    #    这里 `_select_stage` 会把它们的前提改掉。范式同 ``param_draft``。
    from desktop.pages.taskdetail.page import TaskDetailPage
    from tests.selftests._context import pump

    app, repo = ctx.app, ctx.repo
    tid = repo.create_task(ctx.pdf, "hash-step-ports", "端口样本")
    page = TaskDetailPage(repo)
    try:
        page.set_task(tid)
        pump(app, times=6)

        page._select_stage(2)
        ok("第三步：按钮=生成预览、提交按钮出现",
           page.run_button.text() == "生成预览"
           and page.submit_button.isVisibleTo(page), page.run_button.text())
        page._select_stage(page.bar_index_of_step("print"))
        ok("第四步：按钮=生成PDF、提交按钮隐藏",
           page.run_button.text() == "生成PDF"
           and not page.submit_button.isVisibleTo(page), page.run_button.text())
        page._select_stage(0)
        ok("第一步：按钮=执行本子任务、提交按钮隐藏",
           page.run_button.text() == "执行本子任务"
           and not page.submit_button.isVisibleTo(page), page.run_button.text())

        page._select_stage(1)
        ok("第二步：显示检测统计、隐藏执行记录",
           page.detect_stats.isVisibleTo(page)
           and not page.history_block.isVisibleTo(page))
        page._select_stage(2)
        ok("第三步：显示执行记录、隐藏检测统计",
           page.history_block.isVisibleTo(page)
           and not page.detect_stats.isVisibleTo(page))

        # 控制列宽度跟着 spec 走（第四步更宽）。
        page._select_stage(page.bar_index_of_step("print"))
        wide = (page.control_widget.minimumWidth(),
                page.control_widget.maximumWidth())
        page._select_stage(0)
        narrow = (page.control_widget.minimumWidth(),
                  page.control_widget.maximumWidth())
        ok("控制列宽度按 spec 切换（第四步更宽）",
           wide == (400, 580) and narrow == (340, 440), f"{wide} vs {narrow}")

        # 历史回填的跳过集合也走 spec（值与搬进 spec 前一致）。
        ok("print 历史回填跳过 pdf_name/title_text",
           {"pdf_name", "title_text"} <= page._history_fill_keys("print"),
           str(page._history_fill_keys("print")))
        ok("extract 自动回填跳过 pages、手动历史不跳",
           "pages" in page._auto_fill_keys("extract")
           and "pages" not in page._history_fill_keys("extract"))
    finally:
        try:
            page.shutdown_all_workers()
        except Exception:  # noqa: BLE001 - 收尾失败不该让整个模块报错
            pass
        page.deleteLater()
        # ⚠️ **必须删掉自建任务**（同 ``param_draft``）：任务列表是**共享**的，
        #    后面 ``tasklist_pagination`` 断言"25 条 / 每页 10 条 = 3 页"——
        #    多留一个任务会让它算成 26 条而红，甚至把整条套件带崩。
        repo.delete_task(tid)
        pump(app, times=4)   # 让 deleteLater 真正析构，避免残留线程


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
