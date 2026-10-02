# -*- coding: utf-8 -*-
"""共用步骤组件层（``desktop/steps``）的自测（2026-10-02 新增）。

守护三件事：

1. **步骤元数据**（:class:`StepSpec`）：注册表、默认输出规则、以及"入口"这一侧
   的全部规则——认哪些后缀、能不能直接收目录、用户拖进来一堆文件/文件夹到底
   算哪个源（:meth:`StepSpec.resolve_source`）。写错会让三个模块把产物落到别处
   或整页收不下东西；出口这一侧同样钉住（单 PDF 平铺、目录源保留下钻结构、
   job 一律经 ``job_for`` 装配）——那是「提取 → 去底色」这条链的接缝；
2. **执行内核**（:class:`StepKernel`）：单次运行、进度/日志/完成/失败的信号
   契约、运行中拒绝第二次、异常必须变成 ``failed`` 而不是抛进事件循环；
3. **共用控件**：大输入区（:class:`SourceZone`）能拖能点能清空，且三个模块
   各持一份 :class:`StepControl` ⇒ **互不影响**（没有共享可变状态），
   "手动选过输出目录就不再被换源覆盖"。

⚠️ 这里**不**真的跑 ``functions`` 的活儿（那是 extract/rembg/print 各模块自测的
范围，且需要它们的依赖）。命令 job 的入参映射用假功能类验证，只钉"API 契约"。

依赖：tasklist（要主窗口已经建好）。
"""

from __future__ import annotations

import time
from pathlib import Path

NAME = "steps_components"
DEPENDS: list[str] = ["tasklist"]
TITLE = "共用步骤组件层"


def run(ctx) -> None:
    from tests.selftests._context import ok, wait_until

    app = ctx.app

    from desktop.steps import (
        FLOW_STAGES,
        NAV_STEPS,
        SPECS,
        STEP_KEYS,
        StageProcess,
        StepControl,
        StepKernel,
        StepRequest,
        callable_job,
        command_job,
        spec_by_key,
    )
    from desktop.steps.process import worker_arguments, worker_env

    # ---- 1. 步骤元数据 ----
    ok("步骤注册表五条（4 步主链 + 1 个可选节点）",
       STEP_KEYS == ("extract", "detect", "rembg", "print", "imposition"),
       str(STEP_KEYS))
    ok("按 key 取到同一条", spec_by_key("extract") is SPECS[0])
    ok("未知 key 返回 None", spec_by_key("nope") is None)
    ok("每条都声明了参数面板", all(s.panel for s in SPECS), str([s.panel for s in SPECS]))
    ok("面板类都能解析出来", all(s.panel_class() is not None for s in SPECS))
    ok("执行按钮文案", spec_by_key("extract").run_text() == "开始提取",
       spec_by_key("extract").run_text())

    extract = spec_by_key("extract")
    rembg = spec_by_key("rembg")
    imposition = spec_by_key("imposition")
    ok("拼图允许对话框里一次多选（拖拽天然支持多选）",
       imposition.allow_multi and not extract.allow_multi)
    ok("默认输出：文件源 → 父目录/文件名+后缀",
       extract.default_output(Path("/a/b/c.pdf")) == Path("/a/b/c_提取"),
       str(extract.default_output(Path("/a/b/c.pdf"))))
    ok("默认输出：目录源 → 父目录/目录名+后缀",
       rembg.default_output(Path("/a/b/dir")) == Path("/a/b/dir_去底"),
       str(rembg.default_output(Path("/a/b/dir"))))
    ok("默认输出：固定名优先",
       imposition.default_output(Path("/a/b/x.png")) == Path("/a/b/拼图成品"),
       str(imposition.default_output(Path("/a/b/x.png"))))
    ok("源为空时输出为 None", extract.default_output(None) is None)

    # ---- 1b. 「入口」规则：后缀 / 目录 / 一堆路径归一成一个源 ----
    # 用户 2026-10-02：「页面上有一个大的输入框，可以输入图片和输入文件，或者输入
    # 目录，也可以把文件拖进去，目录投进去」——下面这些就是那句话的规则化。
    ok("后缀从过滤串推导（不另写一份后缀表）",
       extract.suffixes() == (".pdf",) and ".png" in rembg.suffixes(),
       f"{extract.suffixes()} / {rembg.suffixes()}")
    ok("输入物称呼由 pick_label 派生",
       (extract.input_noun(), rembg.input_noun()) == ("PDF", "图片"),
       f"{extract.input_noun()} / {rembg.input_noun()}")
    ok("每条都允许直接收目录（默认值）", all(s.accepts_dir for s in SPECS))
    ok("大输入区文案齐备（图标 + 两行）",
       all(s.drop_icon and s.drop_title_text() and s.drop_hint_text() for s in SPECS),
       str([s.drop_title_text() for s in SPECS]))

    drop_dir = Path(ctx.tmp) / "drop"
    drop_dir.mkdir(exist_ok=True)
    (drop_dir / "a.pdf").write_bytes(b"%PDF-1.4\n")
    (drop_dir / "b.pdf").write_bytes(b"%PDF-1.4\n")
    (drop_dir / "c.png").write_bytes(b"x")
    other_dir = Path(ctx.tmp) / "drop2"
    other_dir.mkdir(exist_ok=True)
    (other_dir / "d.pdf").write_bytes(b"%PDF-1.4\n")

    ok("文件按后缀判定",
       extract.accepts_path(drop_dir / "a.pdf")
       and not extract.accepts_path(drop_dir / "c.png"))
    ok("目录按 accepts_dir 判定", extract.accepts_path(drop_dir))
    ok("目录清单只取本步骤的后缀",
       [p.name for p in extract.listing(drop_dir)] == ["a.pdf", "b.pdf"],
       str([p.name for p in extract.listing(drop_dir)]))
    ok("读不了的目录返回空表", extract.listing(Path(ctx.tmp) / "nope") == [])

    ok("拖一个文件 → 就是它自己",
       extract.resolve_source([drop_dir / "a.pdf"])[0] == drop_dir / "a.pdf")
    ok("拖一个文件夹 → 就是它",
       extract.resolve_source([drop_dir])[0] == drop_dir)
    ok("拖同目录多个文件 → 收成该目录",
       extract.resolve_source([drop_dir / "a.pdf", drop_dir / "b.pdf"])[0] == drop_dir)
    ok("跨目录多个文件 → 落到第一个文件所在目录",
       extract.resolve_source([drop_dir / "a.pdf", other_dir / "d.pdf"])[0] == drop_dir)
    ok("文件与文件夹混着给 → 用文件夹并交代一句",
       (lambda r: r[0] == drop_dir and bool(r[1]))(extract.resolve_source([drop_dir / "a.pdf", drop_dir])))
    ok("后缀不符 → 拒绝并给理由",
       (lambda r: r[0] is None and "支持" in r[1])(extract.resolve_source([drop_dir / "c.png"])))
    ok("空输入 → 拒绝", extract.resolve_source([])[0] is None)
    ok("路径都不存在 → 拒绝", extract.resolve_source([Path(ctx.tmp) / "ghost.pdf"])[0] is None)

    # ---- 1c. 出口布局：入口自动下钻 + 单 PDF 平铺 ----
    # 这两条是「提取 → 去底色」这条链能不能接上的关键（2026-10-02 实测断过）：
    # extract 的产物固定落在 <输出根>/<PDF名>/images/（run_on_input_directory 的
    # 布局，与 CLI 同源）。既要在"把输出根拖给下一步"时认得路，又要在单 PDF 时
    # 把那层多余的嵌套抹掉。
    import desktop.steps.kernel as _kernel

    ok("只有图片提取声明了「单源平铺」",
       [s.key for s in SPECS if s.flat_output] == ["extract"],
       str([(s.key, s.flat_output) for s in SPECS]))
    ok("job 一律经 job_for 装配（唯一入口）",
       (lambda je, jr, ji: je.command == "extract" and je._after is not None
        and jr.command == "rembg" and jr._after is None and ji is None)(
            _kernel.job_for(extract), _kernel.job_for(rembg),
            _kernel.job_for(imposition)),
       "extract 要带收尾钩子、rembg 不带、拼图无命令")
    ok("没有命令的步骤不造 job", _kernel.job_for(imposition) is None)

    # 顶层没文件、下一层唯一 → 自动指过去
    nested_root = Path(ctx.tmp) / "nested"
    (nested_root / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (nested_root / "样书" / "images" / "1.png").write_bytes(b"x")
    ok("目录顶层没有 → 自动下钻到唯一子目录并交代一句",
       (lambda r: r[0] == nested_root / "样书" / "images" and bool(r[1]))(
           rembg.resolve_source([nested_root])),
       str(rembg.resolve_source([nested_root])))

    # 顶层没文件、多个子目录各装着 → 让用户自己挑（混着处理会把两本书拼在一起）
    multi_root = Path(ctx.tmp) / "multi"
    for name in ("甲", "乙"):
        deep = multi_root / name / "images"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "1.png").write_bytes(b"x")
    ok("多个子目录各装着 → 拒绝并让用户挑一个",
       (lambda r: r[0] is None and "请直接把其中一个" in r[1])(
           rembg.resolve_source([multi_root])),
       str(rembg.resolve_source([multi_root])))

    # 拼图要的是"一份文件清单"（不是"一个源"）
    imgs_dir = Path(ctx.tmp) / "imgs"
    imgs_dir.mkdir(exist_ok=True)
    for name in ("z.png", "a.png", "m.jpg"):
        (imgs_dir / name).write_bytes(b"x")
    (imgs_dir / "note.txt").write_bytes(b"x")
    ok("拼图清单：只要图片、按名排序、忽略别的文件",
       [p.name for p in imposition.collect_files([imgs_dir])]
       == ["a.png", "m.jpg", "z.png"],
       str([p.name for p in imposition.collect_files([imgs_dir])]))
    ok("拼图清单：复用下钻规则（顶层没图、唯一子目录装着）",
       [p.name for p in imposition.collect_files([nested_root])] == ["1.png"],
       str([p.name for p in imposition.collect_files([nested_root])]))
    ok("拼图清单：文件去重",
       len(imposition.collect_files([imgs_dir / "a.png", imgs_dir / "a.png",
                                     imgs_dir])) == 3,
       str([p.name for p in imposition.collect_files(
           [imgs_dir / "a.png", imgs_dir / "a.png", imgs_dir])]))

    # 单 PDF：把 <输出>/<PDF名>/** 平铺到 <输出>/ 并删空壳
    single_pdf = Path(ctx.tmp) / "样书.pdf"
    single_pdf.write_bytes(b"%PDF-1.4\n")
    flat_dest = Path(ctx.tmp) / "flat_out"
    (flat_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    for name in ("1.jpg", "2.jpg"):
        (flat_dest / "样书" / "images" / name).write_bytes(b"x")
    _kernel._flatten_single_pdf_output(StepRequest(source=single_pdf, dest=flat_dest))
    ok("单 PDF：产物平铺到输出目录根下、嵌套壳被清掉",
       sorted(p.name for p in flat_dest.iterdir()) == ["1.jpg", "2.jpg"],
       str(sorted(p.name for p in flat_dest.iterdir())))

    # 单 PDF 但根下已有同名文件：整个不动（宁可多留一层，也不能覆盖/丢产物）
    clash_dest = Path(ctx.tmp) / "flat_clash"
    (clash_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (clash_dest / "样书" / "images" / "1.jpg").write_bytes(b"nested")
    (clash_dest / "1.jpg").write_bytes(b"root")
    _kernel._flatten_single_pdf_output(StepRequest(source=single_pdf, dest=clash_dest))
    ok("单 PDF 平铺遇到同名：整个不动（不覆盖、不删产物）",
       (clash_dest / "样书" / "images" / "1.jpg").read_bytes() == b"nested"
       and (clash_dest / "1.jpg").read_bytes() == b"root",
       "同名冲突时两处内容都得原样留着")

    # 目录源 = 批量：每个 PDF 一个子目录是**对的**（否则大家的 1.jpg 互相覆盖）
    batch_dest = Path(ctx.tmp) / "flat_batch"
    (batch_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (batch_dest / "样书" / "images" / "1.jpg").write_bytes(b"x")
    _kernel._flatten_single_pdf_output(StepRequest(source=drop_dir, dest=batch_dest))
    ok("目录源（批量）保持每个 PDF 一个子目录",
       (batch_dest / "样书" / "images" / "1.jpg").exists())

    # ---- 1d. 清单只有一份：流程/导航/面板都从 SPECS 派生 ----
    # 用户 2026-10-02：后期要做「步骤随意搭配」的自定义流程（类 BPM），前提是
    # **步骤清单只有一个事实来源**。改造前有四份（STAGES / SPECS / MODULES /
    # PANEL_CLASSES）各写各的，加一步要改四处、漏一处没有任何守卫能发现。
    from desktop.store import (
        IMPOSITION_INDEX, IMPOSITION_LABEL, IMPOSITION_STAGE,
        STAGE_LABELS, STAGE_SHORT, STAGES,
    )

    ok("流程主链 = SPECS 里 role=='stage' 的派生（不再单独硬编码）",
       STAGES == tuple(s.key for s in SPECS if s.role == "stage") == FLOW_STAGES,
       str(STAGES))
    ok("流程主链正好是四步、顺序未变",
       STAGES == ("extract", "detect", "rembg", "print"), str(STAGES))
    ok("每条 role 取值合法",
       all(s.role in ("stage", "optional") for s in SPECS),
       str([(s.key, s.role) for s in SPECS]))
    ok("每条都声明了 BPM 端口（本次只声明未接线）",
       all(s.inputs and s.outputs for s in SPECS),
       str([(s.key, s.inputs, s.outputs) for s in SPECS]))

    ok("步骤条文案由 stage_name() 派生",
       all(STAGE_LABELS[k] == spec_by_key(k).stage_name() for k in STAGES),
       str(STAGE_LABELS))
    ok("步骤条短名由 short_name() 派生",
       all(STAGE_SHORT[k] == spec_by_key(k).short_name() for k in STAGES),
       str(STAGE_SHORT))
    ok("步骤条四个名字逐字未变（用户手册配图依赖它）",
       [STAGE_LABELS[k] for k in STAGES]
       == ["提取图片", "检测文本框", "图片去底色", "生成 PDF"],
       str([STAGE_LABELS[k] for k in STAGES]))
    ok("「提交本次任务」仍挂在第三步的文案表里（它不是独立步骤）",
       STAGE_LABELS.get("rembg_submit") == "提交去底色结果"
       and "rembg_submit" not in STAGES)

    ok("可选节点派生正确（拼版：有模块页、但不在主链上）",
       (IMPOSITION_STAGE, IMPOSITION_LABEL, IMPOSITION_INDEX)
       == ("imposition", "图片拼版", len(STAGES)),
       f"{IMPOSITION_STAGE} / {IMPOSITION_LABEL} / {IMPOSITION_INDEX}")
    ok("可选节点不在主链里",
       all(s.key not in STAGES for s in SPECS if s.role == "optional"))

    from desktop.modules import MODULES

    ok("导航清单 = SPECS 里 nav=True 的派生",
       tuple(m.key for m in MODULES) == NAV_STEPS, str(NAV_STEPS))
    ok("导航文案/悬停提示/图标都由 spec 提供",
       all(m.title == spec_by_key(m.key).title
           and m.subtitle == spec_by_key(m.key).nav_tip()
           and m.icon == spec_by_key(m.key).nav_icon
           for m in MODULES))
    ok("没有独立模块页的步骤不进导航（免得壳层去建不存在的页面）",
       all(spec_by_key(m.key).nav for m in MODULES)
       and set(NAV_STEPS) == {m.key for m in MODULES},
       str(NAV_STEPS))
    ok("导航文案按流程顺序、逐字来自 spec",
       [m.title for m in MODULES]
       == ["图片提取", "检测文本框", "去底色", "生成 PDF", "拼图"],
       str([m.title for m in MODULES]))
    # 开了 nav 却忘了文案/图标 = 导航上出现一个没提示的空条目，肉眼很难发现。
    ok("每个 nav=True 的 spec 都填了导航三件套（标题/悬停提示/图标）",
       all(spec_by_key(k).title and spec_by_key(k).nav_tip()
           and spec_by_key(k).nav_icon for k in NAV_STEPS),
       str([(k, spec_by_key(k).nav_tooltip, spec_by_key(k).nav_icon)
            for k in NAV_STEPS]))

    ok("只有 print 的产物是单个文件（其余都是一目录文件）",
       [s.key for s in SPECS if s.artifact_is_file] == ["print"],
       str([(s.key, s.artifact_is_file) for s in SPECS]))
    ok("「产物是文件」与「平铺」不会同时为真（两者语义互斥）",
       all(not (s.artifact_is_file and s.flat_output) for s in SPECS))

    from desktop.components.panels import PANEL_CLASSES

    ok("面板清单顺序 = 流程主链顺序（同样是派生的）",
       tuple(c.__name__ for c in PANEL_CLASSES)
       == tuple(spec_by_key(k).panel.split(":")[-1] for k in STAGES),
       str([c.__name__ for c in PANEL_CLASSES]))
    ok("模块页沿用旧名（面板类名没被这次重构改掉）",
       [c.__name__ for c in PANEL_CLASSES]
       == ["ExtractPanel", "DetectPanel", "RembgPanel", "PrintPanel"])

    # ---- 2. 执行内核：纯函数 job ----
    def _job(request, report):
        report("progress", {"done": 1, "total": 2})
        report("log", {"message": "干活中"})
        # 步骤**私有**的结构化事件（detect 报框走的就是这条）：
        report("page_boxes", {"image": "0001", "left": [1, 2, 3, 4],
                              "right": None, "full": None})
        report("progress", {"done": 2, "total": 2})
        return str(request.dest)

    kernel = StepKernel(callable_job(_job))
    got: dict = {"progress": [], "logs": [], "events": []}
    kernel.progress.connect(lambda d, t: got["progress"].append((d, t)))
    kernel.log.connect(got["logs"].append)
    kernel.event.connect(lambda name, payload: got["events"].append((name, payload)))
    kernel.finished.connect(lambda out: got.update(out=out))
    kernel.failed.connect(lambda msg: got.update(err=msg))
    ok("内核受理请求", kernel.run(StepRequest(source=Path("s"), dest=Path("d"))) is True)
    ok("跑完收到完成信号（输出目录原样回传）",
       wait_until(app, lambda: "out" in got, timeout=5) and got["out"] == "d", str(got))
    ok("进度事件按序送达", got["progress"] == [(1, 2), (2, 2)], str(got["progress"]))
    ok("日志事件送达", got["logs"] == ["干活中"], str(got["logs"]))
    # ⚠️ 这条是「检测文本框」独立模块页能不能显示框的前提：detect 默认不落盘，
    #    坐标只经 page_boxes 事件回来；内核只认 progress/log 的话它就永远空着。
    ok("步骤私有事件经内核透传（page_boxes 到得了上层）",
       len(got["events"]) == 1 and got["events"][0][0] == "page_boxes"
       and got["events"][0][1]["image"] == "0001", str(got["events"]))
    ok("progress/log 只走专用信号、不在 event 里重复投递",
       all(name not in ("progress", "log") for name, _ in got["events"]),
       str(got["events"]))
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
    ok("慢 job 最终完成", wait_until(app, lambda: "out" in done, timeout=6), str(done))

    def _bad_job(request, report):
        raise RuntimeError("故意炸")

    bad = StepKernel(callable_job(_bad_job))
    errs: list[str] = []
    bad.failed.connect(errs.append)
    bad.run(StepRequest(dest=Path("d")))
    ok("job 异常转成 failed 信号（不抛进事件循环）",
       wait_until(app, lambda: bool(errs), timeout=5) and "故意炸" in errs[0], str(errs))

    # ---- 3. 命令 job：入参映射与"输出目录精确生效" ----
    # 用假功能类替掉 functions.get_function，只验 API 契约（不跑真活儿）
    import functions

    captured: dict = {}

    class _FakeFunction:
        def __init__(self, command_args, reporter=None):
            captured["args"] = command_args
            self.outpath = None

        def execute(self):
            captured["outpath"] = self.outpath
            return {"output": "ok"}

    real_get = functions.get_function
    functions.get_function = lambda cmd, ca, reporter=None: _FakeFunction(ca, reporter)
    try:
        tmp_in = Path(ctx.tmp) / "in.pdf"
        tmp_in.write_bytes(b"%PDF-1.4\n")
        tmp_out = Path(ctx.tmp) / "out"
        cmd_kernel = StepKernel(command_job("extract"))
        cmd_done: dict = {}
        cmd_kernel.finished.connect(lambda out: cmd_done.update(out=out))
        cmd_kernel.failed.connect(lambda msg: cmd_done.update(err=msg))
        cmd_kernel.run(StepRequest(source=tmp_in, dest=tmp_out, args={"zoom": 3}))
        ok("命令 job 跑完", wait_until(app, lambda: bool(cmd_done), timeout=5), str(cmd_done))
        ok("input/output 按 API 注入",
           str(captured["args"].get("input")) == str(tmp_in)
           and str(captured["args"].get("output")) == str(tmp_out))
        ok("面板参数一并带上", captured["args"].get("zoom") == 3)
        ok("输出目录精确生效（不被命令追加子目录）",
           captured.get("outpath") == tmp_out, str(captured.get("outpath")))
    finally:
        functions.get_function = real_get

    # ---- 3b. 产物是**单个文件**的步骤（print）：不能覆盖 outpath ----
    # print 的 --output 是**目录**，文件名由命令自己在其下取（<输出>/output.pdf）。
    # 内核若照常把 function.outpath 覆盖成那个目录，就会拿目录当文件路径写。
    # 这里用假功能类模拟 print 的 _calc_output_path，钉住这两条语义。
    captured.clear()

    class _FakeFileFunction:
        def __init__(self, command_args, reporter=None):
            captured["args"] = command_args
            self.outpath = Path(str(command_args.get("output"))) / "output.pdf"

        def execute(self):
            captured["outpath"] = self.outpath
            self.outpath.parent.mkdir(parents=True, exist_ok=True)
            self.outpath.write_bytes(b"%PDF-1.4\n")
            return {"output": str(self.outpath)}

    functions.get_function = (
        lambda cmd, ca, reporter=None: _FakeFileFunction(ca, reporter)
    )
    try:
        pdf_dir = Path(ctx.tmp) / "pdf_out"
        pdf_job = _kernel.job_for(spec_by_key("print"))
        pdf_result = pdf_job(
            StepRequest(source=tmp_in, dest=pdf_dir, args={}), lambda *a: None
        )
        ok("产物是文件：--output 传目录、命令自己取名（outpath 不被覆盖）",
           captured.get("outpath") == pdf_dir / "output.pdf",
           str(captured.get("outpath")))
        ok("产物是文件：finished 回传的是**产物路径**而不是目录",
           pdf_result == str(pdf_dir / "output.pdf"), str(pdf_result))
    finally:
        functions.get_function = real_get

    # ---- 4. 共用控件：三个模块各持一份，互不影响 ----
    control_a = StepControl(extract)
    control_b = StepControl(rembg)
    ok("两个控件各持独立内核", control_a.kernel is not control_b.kernel)
    ok("初始都没有源", control_a.source() is None and control_b.source() is None)
    control_a.set_source(Path("/x/a.pdf"))
    ok("A 选源不影响 B", control_a.source() == Path("/x/a.pdf") and control_b.source() is None)
    ok("A 的输出按规则自动派生", control_a.output() == Path("/x/a_提取"), str(control_a.output()))
    control_a.set_output(Path("/y"))
    control_a.set_source(Path("/x/b.pdf"))
    ok("手动选过输出后换源不覆盖", control_a.output() == Path("/y"), str(control_a.output()))
    ok("参数面板可收集参数", "zoom" in control_a.args(), str(control_a.args()))

    # 模块页只跟 StepControl 打交道，所以"步骤私有事件"必须在它身上也能收到
    # （kernel 有、control 没有的话，模块页就得绕过 control 去够 kernel.event）。
    from desktop.steps.kernel import StepKernel as _K

    ok("执行内核与共用控件都对外暴露事件通道",
       hasattr(_K, "event") and hasattr(StepControl, "event"),
       f"kernel={hasattr(_K, 'event')} control={hasattr(StepControl, 'event')}")
    event_sink: list = []
    control_a.event.connect(lambda name, payload: event_sink.append((name, payload)))
    control_a.kernel.event.emit("page_boxes", {"image": "0009"})
    app.processEvents()
    ok("内核事件能经共用控件转出来（模块页的接入点）",
       event_sink == [("page_boxes", {"image": "0009"})], str(event_sink))

    # 没选源就点执行：只发一条 warning 状态，绝不起线程（免得白跑一趟空活儿）
    idle = StepControl(rembg)
    blocked: list = []
    idle.status.connect(lambda text, kind: blocked.append((text, kind)))
    idle.run()
    ok("没有源时执行被拦下（只发状态、不起线程）",
       bool(blocked) and blocked[0][1] == "warning" and idle.busy() is False,
       str(blocked))
    idle.shutdown()

    control_a.shutdown()
    control_b.shutdown()

    # ---- 4b. 大输入区（用户要的那块"大的输入框"）----
    from PySide6.QtCore import QMimeData, QUrl

    from desktop.steps import SourceZone

    zone = SourceZone(extract)
    zone.resize(420, 240)
    ok("大输入区默认收拖拽", zone.acceptDrops() is True)
    ok("空态是大块（还没选东西）",
       zone.source() is None and zone.height() == 132, str(zone.height()))

    zone_seen: list = []
    zone_rejected: list = []
    zone.paths_chosen.connect(zone_seen.append)
    zone.rejected.connect(zone_rejected.append)
    zone.offer([])
    ok("空拖拽不发路径、只报一句 rejected",
       zone_seen == [] and bool(zone_rejected), str(zone_rejected))

    mime = QMimeData()
    mime.setUrls([
        QUrl.fromLocalFile(str(drop_dir)),
        QUrl("https://example.com/not-local"),
    ])
    ok("拖拽数据只取本地文件/文件夹",
       [Path(p) for p in SourceZone.paths_from_mime(mime)] == [drop_dir],
       str(SourceZone.paths_from_mime(mime)))
    ok("纯文本的拖拽数据取不到路径", SourceZone.paths_from_mime(QMimeData()) == [])

    zone.offer(SourceZone.paths_from_mime(mime))
    ok("拖进来的路径原样发出去（不做合法性判断）",
       len(zone_seen) == 1 and [Path(p) for p in zone_seen[0]] == [drop_dir],
       str(zone_seen))
    zone.set_source(drop_dir, "12 个可用文件")
    ok("已选态收窄成一行",
       zone.source() == drop_dir and zone.height() == 74, str(zone.height()))

    cleared: list = []
    zone.cleared.connect(lambda: cleared.append(True))
    zone.clear()
    ok("清空回到空态并发出 cleared",
       cleared == [True] and zone.source() is None and zone.height() == 132)

    # 拖动经过时的高亮开关（宿主页面转发整页拖拽时用）
    zone.set_hot(True)
    ok("可以外部点亮拖拽热区", zone._hot is True)
    zone.set_hot(False)
    ok("可以熄灭拖拽热区", zone._hot is False)

    # ---- 4b-2. 点一下 → 选择对话框（推迟到事件返回之后 + 起始目录）----
    # ⚠️ 2026-10-02 用户报的 bug：点大输入区弹出"选择图片 / 选择文件夹"小菜单，
    #    选完**资源管理器不出现**。根因是 `browse()` 被同步压在 mousePressEvent
    #    里——小菜单与随后的 QFileDialog 两层模态叠在**同一个尚未返回**的鼠标事件
    #    里。修法：用 QTimer 推迟到事件返回之后再弹。这里把两个真正弹窗的调用换成
    #    记录器，钉住"① 不当场弹 ② 事件循环跑完才弹 ③ 起始目录不是空串"。
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QFileDialog

    from desktop.utils.files import default_open_dir

    browse_calls: list = []
    original_ask = SourceZone._ask_kind
    original_name = QFileDialog.getOpenFileName
    SourceZone._ask_kind = lambda self: (browse_calls.append("ask"), (True, True))[1]
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **k: (browse_calls.append(("file", a[2])), ("", ""))[1]
    )
    try:
        zone.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(zone.width() // 2, zone.height() // 2),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        ok("点击大输入区**不当场**开模态（否则菜单与对话框会叠在同一个鼠标事件里）",
           browse_calls == [], str(browse_calls))
        ok("事件循环跑完才弹（先问文件/文件夹，再开对话框）",
           wait_until(app, lambda: len(browse_calls) >= 2, timeout=3)
           and [c[0] if isinstance(c, tuple) else c for c in browse_calls] == ["ask", "file"],
           str(browse_calls))
        ok("对话框起始目录是文档目录，不是空串",
           browse_calls[1][1] == str(default_open_dir()), repr(browse_calls[1][1]))
    finally:
        SourceZone._ask_kind = original_ask
        QFileDialog.getOpenFileName = original_name

    # ---- 4c. 大输入区 + 控制组件：外部摆、内部接线（模块页的用法）----
    zone_c = SourceZone(rembg)
    control_c = StepControl(rembg, zone=zone_c)
    ok("控件接受外部大输入区（不重复摆一块）", control_c.zone is zone_c)
    zone_c.offer([str(drop_dir / "c.png")])
    ok("从大输入区拖入 → 控件拿到源（按 spec 归一化）",
       control_c.source() == drop_dir / "c.png", str(control_c.source()))
    ok("大输入区同步显示成已选态", zone_c.source() == drop_dir / "c.png")
    zone_c.offer([str(drop_dir / "a.pdf")])
    ok("后缀不符时不动源（只发状态）", control_c.source() == drop_dir / "c.png")
    zone_c.clear()
    ok("清空大输入区 → 控件的源与输出一起复位",
       control_c.source() is None and control_c.output() is None)
    control_c.shutdown()

    # ---- 5. 子进程传输层：启动参数与 UTF-8 环境（不起真进程）----
    args_packed = worker_arguments(Path("/tmp/run-1.json"))
    ok("源码环境按模块启动 worker",
       args_packed[:2] == ["-m", "desktop.worker"] and "--config" in args_packed,
       str(args_packed))
    env = worker_env()
    ok("子进程强制 UTF-8",
       env.value("PYTHONIOENCODING") == "utf-8" and env.value("PYTHONUTF8") == "1")
    ok("传输层初始没有进程", StageProcess().process is None)
    ok("传输层初始不忙", StageProcess().running() is False)


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
