# -*- coding: utf-8 -*-
"""1d. 清单只有一份：流程/导航/面板都从 SPECS 派生 / 独立功能目录名（磁盘路径）与显示文案**必须解耦** / 2. 执行内核：纯函数 job / 3. 命令 job：入参映射与\"输出目录精确生效\" / 3b. 产物是**单个文件**的步骤（print）：不能覆盖 outpath / 4. 共用控件：三个模块各持一份，互不影响 / 4a. 「查看处理文件」入口（2026-10-11 用户：singletask 执行成功"""

from typing import Any


def run(st: Any) -> None:
    from desktop.steps.spec import (
        FLOW_STAGES,
        NAV_STEPS,
        SPECS,
        STEP_KEYS,
        StepSpec,
        spec_by_key,
    )
    from desktop.store import (
        IMPOSITION_LABEL,
        IMPOSITION_STAGE,
        STAGE_LABELS,
        STAGE_SHORT,
        STAGES,
    )
    from desktop.modules import MODULES
    from desktop.components.panels import PANEL_CLASSES
    from pathlib import Path
    from desktop.steps.control import StepControl
    from desktop.steps.kernel import (
        CommandJob,
        StepKernel,
        StepRequest,
        callable_job,
        command_job,
    )
    from desktop.steps.kernel import StepKernel as _K
    import desktop.utils.files as _files_mod
    import desktop.steps.kernel as _kernel
    import desktop.store.tasks as _tasks_mod
    import functions
    from tests.selftests._context import ok, wait_until
    import time
    from desktop.store import (
        IMPOSITION_LABEL,
        IMPOSITION_STAGE,
        STAGE_LABELS,
        STAGE_SHORT,
        STAGES,
    )

    ok(
        "流程主链 = SPECS 里 role=='stage' 的派生（不再单独硬编码）",
        STAGES == tuple(s.key for s in SPECS if s.role == "stage") == FLOW_STAGES,
        str(STAGES),
    )
    ok(
        "流程主链正好是四步、顺序未变",
        STAGES == ("extract", "detect", "rembg", "print"),
        str(STAGES),
    )
    ok(
        "每条 role 取值合法",
        all(s.role in ("stage", "optional") for s in SPECS),
        str([(s.key, s.role) for s in SPECS]),
    )
    ok(
        "每条都声明了 BPM 端口（已由 desktop.steps.ports 接线）",
        all(s.inputs and s.outputs for s in SPECS),
        str([(s.key, s.inputs, s.outputs) for s in SPECS]),
    )

    ok(
        "步骤条文案由 stage_name() 派生",
        all(STAGE_LABELS[k] == st.spec_of(k).stage_name() for k in STAGES),
        str(STAGE_LABELS),
    )
    ok(
        "步骤条短名由 short_name() 派生",
        all(STAGE_SHORT[k] == st.spec_of(k).short_name() for k in STAGES),
        str(STAGE_SHORT),
    )
    ok(
        "步骤条四个名字逐字未变（用户手册配图依赖它）",
        [STAGE_LABELS[k] for k in STAGES]
        == ["提取图片", "检测文本框", "图片去底色", "PDF排版"],
        str([STAGE_LABELS[k] for k in STAGES]),
    )
    ok(
        "「提交本次任务」仍挂在第二步的文案表里（它不是独立步骤）",
        STAGE_LABELS.get("detect_submit") == "提交检测结果"
        and "detect_submit" not in STAGES,
    )

    ok(
        "可选节点派生正确（拼版：有模块页、但不在主链上）",
        (IMPOSITION_STAGE, IMPOSITION_LABEL) == ("imposition", "图片拼版"),
        f"{IMPOSITION_STAGE} / {IMPOSITION_LABEL}",
    )
    ok(
        "可选节点不在主链里",
        all(s.key not in STAGES for s in SPECS if s.role == "optional"),
    )
    # ⚠️ 「拼版占第几格」**不能**有常量：`IMPOSITION_INDEX = len(STAGES)` 是
    #    BPM 改造前的固定顺序口径，现在由流程图决定（槽位表的 bar_index）。
    #    留着那个常量就是给下一个人留一个"看起来能用"的默认流程假设。
    import desktop.store.tasks as _tasks_mod

    ok(
        "store 里不再有 IMPOSITION_INDEX（拼版格序问图，不问常量）",
        not hasattr(_tasks_mod, "IMPOSITION_INDEX"),
    )

    from desktop.modules import MODULES

    ok(
        "导航清单 = SPECS 里 nav=True 的派生",
        tuple(m.key for m in MODULES) == NAV_STEPS,
        str(NAV_STEPS),
    )
    ok(
        "导航文案/悬停提示/图标都由 spec 提供",
        all(
            m.title == st.spec_of(m.key).nav_name()
            and m.subtitle == st.spec_of(m.key).nav_tip()
            and m.icon == st.spec_of(m.key).nav_icon
            for m in MODULES
        ),
    )
    ok(
        "没有独立模块页的步骤不进导航（免得壳层去建不存在的页面）",
        all(st.spec_of(m.key).nav for m in MODULES)
        and set(NAV_STEPS) == {m.key for m in MODULES},
        str(NAV_STEPS),
    )
    # ⚠️ 逐字锁死：导航文案改动**必须**显式改spec.nav_title，而不是碰title
    #    （title 同时是模块页的大标题，一改就把页头也带走了）。用户 2026-10-03
    #    定的这一组名字——统一带对象名。第四步 2026-10-07 起是「PDF排版」
    #    （与流程图上那格同名；「生成PDF」只剩**按钮**与**结束事件**两处用法）。
    # ⚠️ 顺序里它仍在**最后**：它吃前几步的产物，出书是收尾动作
    #    （nav_order=100 把它挪到末尾），但流程条上它仍是第 4 步——两条线独立。
    ok(
        "导航文案与顺序逐字来自 spec（PDF排版 排最后）",
        [m.title for m in MODULES]
        == ["PDF/DjVu提取", "检测文本框", "图片去底色", "图片拼版", "PDF排版"],
        str([m.title for m in MODULES]),
    )
    # 护栏：调导航顺序**不许**动流程主链。FLOW_STAGES 从 SPECS 派生，若有人为了
    # 挪导航而去对调 SPECS 里两段的书写位置，流程的执行顺序就会被带着变。
    ok(
        "导航挪动不影响流程主链顺序（print 仍是第 4 步）",
        FLOW_STAGES == ("extract", "detect", "rembg", "print")
        and FLOW_STAGES.index("print") == 3,
        str(FLOW_STAGES),
    )
    ok(
        "nav_order 只影响导航、不泄漏到流程顺序",
        st.spec_of("print").nav_order != 0 and FLOW_STAGES[-1] == "print",
        f"nav_order={st.spec_of('print').nav_order}, FLOW={FLOW_STAGES}",
    )
    # 开了 nav 却忘了文案/图标 = 导航上出现一个没提示的空条目，肉眼很难发现。
    ok(
        "每个 nav=True 的 spec 都填了导航三件套（标题/悬停提示/图标）",
        all(
            st.spec_of(k).nav_name() and st.spec_of(k).nav_tip() and st.spec_of(k).nav_icon
            for k in NAV_STEPS
        ),
        str([(k, st.spec_of(k).nav_tooltip, st.spec_of(k).nav_icon) for k in NAV_STEPS]),
    )
    ok(
        "磁盘独立功能目录名取 disk_key，不取任何显示文案",
        all(st.spec_of(k).disk_key() == k for k in NAV_STEPS),
        str([(k, st.spec_of(k).disk_key()) for k in NAV_STEPS]),
    )
    ok(
        "磁盘目录名与导航/页头文案完全无关（改文案不会动磁盘路径）",
        all(
            st.spec_of(k).disk_key() not in (st.spec_of(k).title, st.spec_of(k).nav_name())
            for k in NAV_STEPS
        ),
    )

    ok(
        "只有 print 的产物是单个文件（其余都是一目录文件）",
        [s.key for s in SPECS if s.artifact_is_file] == ["print"],
        str([(s.key, s.artifact_is_file) for s in SPECS]),
    )
    ok(
        "「产物是文件」与「平铺」不会同时为真（两者语义互斥）",
        all(not (s.artifact_is_file and s.flat_output) for s in SPECS),
    )

    from desktop.components.panels import PANEL_CLASSES

    ok(
        "面板清单顺序 = 流程主链顺序（同样是派生的）",
        tuple(c.__name__ for c in PANEL_CLASSES)
        == tuple((st.spec_of(k).panel or "").split(":")[-1] for k in STAGES),
        str([c.__name__ for c in PANEL_CLASSES]),
    )
    ok(
        "模块页沿用旧名（面板类名没被这次重构改掉）",
        [c.__name__ for c in PANEL_CLASSES]
        == ["ExtractPanel", "DetectPanel", "RembgPanel", "PrintPanel"],
    )
    def _job(request, report):
        report("progress", {"done": 1, "total": 2})
        report("log", {"message": "干活中"})
        # 步骤**私有**的结构化事件（detect 报框走的就是这条）：
        report(
            "page_boxes",
            {"image": "0001", "left": [1, 2, 3, 4], "right": None, "full": None},
        )
        report("progress", {"done": 2, "total": 2})
        return str(request.dest)

    kernel = StepKernel(callable_job(_job))
    got: dict = {"progress": [], "logs": [], "events": []}
    kernel.progress.connect(lambda d, t: got["progress"].append((d, t)))
    kernel.log.connect(got["logs"].append)
    kernel.event.connect(lambda name, payload: got["events"].append((name, payload)))  # type: ignore[reportAttributeAccessIssue]  # ``event`` 与 QObject.event 同名，运行时是 Signal（pyright 按基类方法解析）
    kernel.finished.connect(lambda out: got.update(out=out))
    kernel.failed.connect(lambda msg: got.update(err=msg))
    ok(
        "内核受理请求",
        kernel.run(StepRequest(source=Path("s"), dest=Path("d"))) is True,
    )
    ok(
        "跑完收到完成信号（输出目录原样回传）",
        wait_until(st.app, lambda: "out" in got, timeout=5) and got["out"] == "d",
        str(got),
    )
    ok("进度事件按序送达", got["progress"] == [(1, 2), (2, 2)], str(got["progress"]))
    ok("日志事件送达", got["logs"] == ["干活中"], str(got["logs"]))
    # ⚠️ 这条是「检测文本框」独立模块页能不能显示框的前提：detect 默认不落盘，
    #    坐标只经 page_boxes 事件回来；内核只认 progress/log 的话它就永远空着。
    ok(
        "步骤私有事件经内核透传（page_boxes 到得了上层）",
        len(got["events"]) == 1
        and got["events"][0][0] == "page_boxes"
        and got["events"][0][1]["image"] == "0001",
        str(got["events"]),
    )
    ok(
        "progress/log 只走专用信号、不在 event 里重复投递",
        all(name not in ("progress", "log") for name, _ in got["events"]),
        str(got["events"]),
    )
    ok("跑完后不再 busy", kernel.busy() is False)
    ok("没有 job 的内核不启动", StepKernel(None).run(StepRequest()) is False)

    # 运行中拒绝第二次（用一个"慢"job 把窗口撑开，避免与线程赛跑）
    def _slow_job(request, report):
        time.sleep(0.4)
        return str(request.dest)

    slow = StepKernel(callable_job(_slow_job))
    done: dict = {}
    slow.finished.connect(lambda out: done.update(out=out))
    ok("慢 job 受理第一次", slow.run(StepRequest(dest=Path("d1"))) is True)
    ok("运行中 busy() 为真", slow.busy() is True)
    ok("运行中拒绝第二次", slow.run(StepRequest(dest=Path("d2"))) is False)
    ok("慢 job 最终完成", wait_until(st.app, lambda: "out" in done, timeout=6), str(done))

    def _bad_job(request, report):
        raise RuntimeError("故意炸")

    bad = StepKernel(callable_job(_bad_job))
    errs: list[str] = []
    bad.failed.connect(errs.append)
    bad.run(StepRequest(dest=Path("d")))
    ok(
        "job 异常转成 failed 信号（不抛进事件循环）",
        wait_until(st.app, lambda: bool(errs), timeout=5) and "故意炸" in errs[0],
        str(errs),
    )
    import functions

    st.captured: dict = {}

    class _FakeFunction:
        def __init__(self, command_args, reporter=None):
            st.captured["args"] = command_args
            self.outpath = None

        def execute(self):
            st.captured["outpath"] = self.outpath
            return {"output": "ok"}

    st.real_get = functions.get_function
    functions.get_function = lambda cmd, ca, reporter=None: _FakeFunction(ca, reporter)
    try:
        st.tmp_in = Path(st.ctx.tmp) / "in.pdf"
        st.tmp_in.write_bytes(b"%PDF-1.4\n")
        tmp_out = Path(st.ctx.tmp) / "out"
        cmd_kernel = StepKernel(command_job("extract"))
        cmd_done: dict = {}
        cmd_kernel.finished.connect(lambda out: cmd_done.update(out=out))
        cmd_kernel.failed.connect(lambda msg: cmd_done.update(err=msg))
        cmd_kernel.run(StepRequest(source=st.tmp_in, dest=tmp_out, args={"zoom": 3}))
        ok(
            "命令 job 跑完",
            wait_until(st.app, lambda: bool(cmd_done), timeout=5),
            str(cmd_done),
        )
        ok(
            "input/output 按 API 注入",
            str(st.captured["args"].get("input")) == str(st.tmp_in)
            and str(st.captured["args"].get("output")) == str(tmp_out),
        )
        ok("面板参数一并带上", st.captured["args"].get("zoom") == 3)
        ok(
            "输出目录精确生效（不被命令追加子目录）",
            st.captured.get("outpath") == tmp_out,
            str(st.captured.get("outpath")),
        )
    finally:
        functions.get_function = st.real_get
    st.captured.clear()

    class _FakeFileFunction:
        def __init__(self, command_args, reporter=None):
            st.captured["args"] = command_args
            self.outpath = Path(str(command_args.get("output"))) / "output.pdf"

        def execute(self):
            st.captured["outpath"] = self.outpath
            self.outpath.parent.mkdir(parents=True, exist_ok=True)
            self.outpath.write_bytes(b"%PDF-1.4\n")
            return {"output": str(self.outpath)}

    functions.get_function = lambda cmd, ca, reporter=None: _FakeFileFunction(
        ca, reporter
    )
    try:
        pdf_dir = Path(st.ctx.tmp) / "pdf_out"
        pdf_job = _kernel.job_for(st.spec_of("print"))
        assert pdf_job is not None  # print 声明了命令，必造得出 job
        pdf_result = pdf_job(
            StepRequest(source=st.tmp_in, dest=pdf_dir, args={}), lambda *a: None
        )
        ok(
            "产物是文件：--output 传目录、命令自己取名（outpath 不被覆盖）",
            st.captured.get("outpath") == pdf_dir / "output.pdf",
            str(st.captured.get("outpath")),
        )
        ok(
            "产物是文件：finished 回传的是**产物路径**而不是目录",
            pdf_result == str(pdf_dir / "output.pdf"),
            str(pdf_result),
        )
    finally:
        functions.get_function = st.real_get
    st.control_a = StepControl(st.extract)
    st.control_b = StepControl(st.rembg)
    ok("两个控件各持独立内核", st.control_a.kernel is not st.control_b.kernel)
    ok("初始都没有源", st.control_a.source() is None and st.control_b.source() is None)
    st.control_a.set_source(Path("/x/a.pdf"))
    ok(
        "A 选源不影响 B",
        st.control_a.source() == Path("/x/a.pdf") and st.control_b.source() is None,
    )
    ok(
        "A 的输出按规则自动派生",
        st.control_a.output() == Path("/x/a_提取"),
        str(st.control_a.output()),
    )
    st.control_a.set_output(Path("/y"))
    st.control_a.set_source(Path("/x/b.pdf"))
    ok(
        "手动选过输出后换源不覆盖",
        st.control_a.output() == Path("/y"),
        str(st.control_a.output()),
    )
    ok("参数面板可收集参数", "zoom" in st.control_a.args(), str(st.control_a.args()))

    # 模块页只跟 StepControl 打交道，所以"步骤私有事件"必须在它身上也能收到
    # （kernel 有、control 没有的话，模块页就得绕过 control 去够 kernel.event）。
    from desktop.steps.kernel import StepKernel as _K

    ok(
        "执行内核与共用控件都对外暴露事件通道",
        hasattr(_K, "event") and hasattr(StepControl, "event"),
        f"kernel={hasattr(_K, 'event')} control={hasattr(StepControl, 'event')}",
    )
    event_sink: list = []
    st.control_a.event.connect(lambda name, payload: event_sink.append((name, payload)))  # type: ignore[reportAttributeAccessIssue]  # 同上：event 与 QObject.event 同名
    st.control_a.kernel.event.emit("page_boxes", {"image": "0009"})  # type: ignore[reportAttributeAccessIssue]  # 同上
    st.app.processEvents()
    ok(
        "内核事件能经共用控件转出来（模块页的接入点）",
        event_sink == [("page_boxes", {"image": "0009"})],
        str(event_sink),
    )

    # 没选源就点执行：只发一条 warning 状态，绝不起线程（免得白跑一趟空活儿）
    idle = StepControl(st.rembg)
    blocked: list = []
    idle.status.connect(lambda text, kind: blocked.append((text, kind)))
    idle.run()
    ok(
        "没有源时执行被拦下（只发状态、不起线程）",
        bool(blocked) and blocked[0][1] == "warning" and idle.busy() is False,
        str(blocked),
    )
    idle.shutdown()
    ok("初始不显示「查看处理文件」", st.control_a.view_output_button.isHidden())
    import desktop.utils.files as _files_mod

    _opened: list = []
    _real_reveal = _files_mod.reveal_in_explorer
    _files_mod.reveal_in_explorer = lambda p: _opened.append(Path(p)) or True
    try:
        st.control_a.kernel.finished.emit(str(Path("/x/a_提取")))
        st.app.processEvents()
        ok(
            "执行成功后亮出「查看处理文件」",
            not st.control_a.view_output_button.isHidden(),
        )
        st.control_a.view_output_button.click()
        ok(
            "点「查看处理文件」→ 资源管理器打开成功输出目录",
            _opened == [Path("/x/a_提取")],
            str(_opened),
        )
    finally:
        _files_mod.reveal_in_explorer = _real_reveal
    st.control_a.set_source(Path("/x/c.pdf"))
    ok("换源后入口收起（旧结果对不上新源）", st.control_a.view_output_button.isHidden())

    st.control_a.shutdown()
    st.control_b.shutdown()

