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
   **不许**再抄一遍输入区/控制区/收尾那一套。

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
        page._select_stage(3)
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
        page._select_stage(3)
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
