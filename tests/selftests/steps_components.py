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
        StepSpec,
        callable_job,
        command_job,
        spec_by_key,
    )
    from desktop.steps.process import worker_arguments, worker_env

    # ---- 1. 步骤元数据 ----
    ok(
        "步骤注册表五条（4 步主链 + 1 个可选节点）",
        STEP_KEYS == ("extract", "detect", "rembg", "print", "imposition"),
        str(STEP_KEYS),
    )
    ok("按 key 取到同一条", spec_by_key("extract") is SPECS[0])
    ok("未知 key 返回 None", spec_by_key("nope") is None)
    ok("每条都声明了参数面板", all(s.panel for s in SPECS), str([s.panel for s in SPECS]))
    ok("面板类都能解析出来", all(s.panel_class() is not None for s in SPECS))
    ok("执行按钮文案", spec_by_key("extract").run_text() == "开始提取", spec_by_key("extract").run_text())

    extract = spec_by_key("extract")
    rembg = spec_by_key("rembg")
    imposition = spec_by_key("imposition")
    ok("拼图允许对话框里一次多选（拖拽天然支持多选）", imposition.allow_multi and not extract.allow_multi)
    ok(
        "默认输出：文件源 → 父目录/文件名+后缀",
        extract.default_output(Path("/a/b/c.pdf")) == Path("/a/b/c_提取"),
        str(extract.default_output(Path("/a/b/c.pdf"))),
    )
    ok(
        "默认输出：目录源 → 父目录/目录名+后缀",
        rembg.default_output(Path("/a/b/dir")) == Path("/a/b/dir_去底"),
        str(rembg.default_output(Path("/a/b/dir"))),
    )
    ok(
        "默认输出：固定名优先",
        imposition.default_output(Path("/a/b/x.png")) == Path("/a/b/拼图成品"),
        str(imposition.default_output(Path("/a/b/x.png"))),
    )
    ok("源为空时输出为 None", extract.default_output(None) is None)

    # ---- 1b. 「入口」规则：后缀 / 目录 / 一堆路径归一成一个源 ----
    # 用户 2026-10-02：「页面上有一个大的输入框，可以输入图片和输入文件，或者输入
    # 目录，也可以把文件拖进去，目录投进去」——下面这些就是那句话的规则化。
    ok(
        "后缀从过滤串推导（不另写一份后缀表）",
        extract.suffixes() == (".pdf",) and ".png" in rembg.suffixes(),
        f"{extract.suffixes()} / {rembg.suffixes()}",
    )
    ok(
        "输入物称呼由 pick_label 派生",
        (extract.input_noun(), rembg.input_noun()) == ("PDF", "图片"),
        f"{extract.input_noun()} / {rembg.input_noun()}",
    )
    # ⚠️ 「PDF 只支持文件」（用户 2026-10-03）——所以**不是**每条都收目录。
    #    断言写成"谁不收目录"，加一条新步骤时不必回来改这里。
    ok(
        "只有图片提取不收目录（PDF 只支持文件）",
        [s.key for s in SPECS if not s.accepts_dir] == ["extract"],
        str([(s.key, s.accepts_dir) for s in SPECS]),
    )
    ok(
        "大输入区文案齐备（图标 + 两行）",
        all(s.drop_icon and s.drop_title_text() and s.drop_hint_text() for s in SPECS),
        str([s.drop_title_text() for s in SPECS]),
    )

    drop_dir = Path(ctx.tmp) / "drop"
    drop_dir.mkdir(exist_ok=True)
    (drop_dir / "a.pdf").write_bytes(b"%PDF-1.4\n")
    (drop_dir / "b.pdf").write_bytes(b"%PDF-1.4\n")
    (drop_dir / "c.png").write_bytes(b"x")
    other_dir = Path(ctx.tmp) / "drop2"
    other_dir.mkdir(exist_ok=True)
    (other_dir / "d.pdf").write_bytes(b"%PDF-1.4\n")

    ok("文件按后缀判定", extract.accepts_path(drop_dir / "a.pdf") and not extract.accepts_path(drop_dir / "c.png"))
    ok(
        "目录按 accepts_dir 判定（提取这一步不收目录）",
        not extract.accepts_path(drop_dir) and rembg.accepts_path(drop_dir),
    )
    ok(
        "目录清单只取本步骤的后缀",
        [p.name for p in extract.listing(drop_dir)] == ["a.pdf", "b.pdf"],
        str([p.name for p in extract.listing(drop_dir)]),
    )
    ok("读不了的目录返回空表", extract.listing(Path(ctx.tmp) / "nope") == [])

    ok("拖一个文件 → 就是它自己", extract.resolve_source([drop_dir / "a.pdf"])[0] == drop_dir / "a.pdf")
    # ⚠️ 「PDF 只支持文件」（用户 2026-10-03）：拖文件夹**直接拒绝**，不从
    #    里面替用户挑 PDF——挑了哪几个、为什么是这几个，界面上看不见。
    ok(
        "拖一个文件夹 → 拒绝并说明只支持文件",
        (lambda r: r[0] is None and "只支持" in r[1] and "不支持文件夹" in r[1])(extract.resolve_source([drop_dir])),
        str(extract.resolve_source([drop_dir])),
    )
    ok(
        "文件与文件夹混着给 → 同样拒绝（按最严的来）",
        (lambda r: r[0] is None and "只支持" in r[1])(extract.resolve_source([drop_dir / "a.pdf", drop_dir])),
        str(extract.resolve_source([drop_dir / "a.pdf", drop_dir])),
    )
    ok("收目录的步骤：拖文件夹就是它", rembg.resolve_source([drop_dir])[0] == drop_dir)
    ok(
        "后缀不符 → 拒绝并给理由",
        (lambda r: r[0] is None and "支持" in r[1])(extract.resolve_source([drop_dir / "c.png"])),
    )
    ok("空输入 → 拒绝", extract.resolve_source([])[0] is None)
    ok("路径都不存在 → 拒绝", extract.resolve_source([Path(ctx.tmp) / "ghost.pdf"])[0] is None)

    # ---- 1c. 出口布局：入口自动下钻 + 单 PDF 平铺 ----
    # 这两条是「提取 → 去底色」这条链能不能接上的关键（2026-10-02 实测断过）：
    # extract 的产物固定落在 <输出根>/<PDF名>/images/（run_on_input_directory 的
    # 布局，与 CLI 同源）。既要在"把输出根拖给下一步"时认得路，又要在单 PDF 时
    # 把那层多余的嵌套抹掉。
    import desktop.steps.kernel as _kernel

    ok(
        "只有图片提取声明了「单源平铺」",
        [s.key for s in SPECS if s.flat_output] == ["extract"],
        str([(s.key, s.flat_output) for s in SPECS]),
    )
    ok(
        "job 一律经 job_for 装配（唯一入口）",
        (
            lambda je, jr, ji: je.command == "extract"
            and je._after is not None
            and jr.command == "rembg"
            and jr._after is None
            and ji is None
        )(_kernel.job_for(extract), _kernel.job_for(rembg), _kernel.job_for(imposition)),
        "extract 要带收尾钩子、rembg 不带、拼图无命令",
    )
    ok("没有命令的步骤不造 job", _kernel.job_for(imposition) is None)

    # 顶层没文件、下一层唯一 → 自动指过去
    nested_root = Path(ctx.tmp) / "nested"
    (nested_root / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (nested_root / "样书" / "images" / "1.png").write_bytes(b"x")
    ok(
        "目录顶层没有 → 自动下钻到唯一子目录并交代一句",
        (lambda r: r[0] == nested_root / "样书" / "images" and bool(r[1]))(rembg.resolve_source([nested_root])),
        str(rembg.resolve_source([nested_root])),
    )

    # 顶层没文件、多个子目录各装着 → 让用户自己挑（混着处理会把两本书拼在一起）
    multi_root = Path(ctx.tmp) / "multi"
    for name in ("甲", "乙"):
        deep = multi_root / name / "images"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "1.png").write_bytes(b"x")
    ok(
        "多个子目录各装着 → 拒绝并让用户挑一个",
        (lambda r: r[0] is None and "请直接把其中一个" in r[1])(rembg.resolve_source([multi_root])),
        str(rembg.resolve_source([multi_root])),
    )

    # 拼图要的是"一份文件清单"（不是"一个源"）
    imgs_dir = Path(ctx.tmp) / "imgs"
    imgs_dir.mkdir(exist_ok=True)
    for name in ("z.png", "a.png", "m.jpg"):
        (imgs_dir / name).write_bytes(b"x")
    (imgs_dir / "note.txt").write_bytes(b"x")
    ok(
        "拼图清单：只要图片、按名排序、忽略别的文件",
        [p.name for p in imposition.collect_files([imgs_dir])] == ["a.png", "m.jpg", "z.png"],
        str([p.name for p in imposition.collect_files([imgs_dir])]),
    )
    ok(
        "拼图清单：复用下钻规则（顶层没图、唯一子目录装着）",
        [p.name for p in imposition.collect_files([nested_root])] == ["1.png"],
        str([p.name for p in imposition.collect_files([nested_root])]),
    )
    ok(
        "拼图清单：文件去重",
        len(imposition.collect_files([imgs_dir / "a.png", imgs_dir / "a.png", imgs_dir])) == 3,
        str([p.name for p in imposition.collect_files([imgs_dir / "a.png", imgs_dir / "a.png", imgs_dir])]),
    )

    # 单 PDF：把 <输出>/<PDF名>/** 平铺到 <输出>/ 并删空壳
    single_pdf = Path(ctx.tmp) / "样书.pdf"
    single_pdf.write_bytes(b"%PDF-1.4\n")
    flat_dest = Path(ctx.tmp) / "flat_out"
    (flat_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    for name in ("1.jpg", "2.jpg"):
        (flat_dest / "样书" / "images" / name).write_bytes(b"x")
    _kernel._flatten_single_pdf_output(StepRequest(source=single_pdf, dest=flat_dest))
    ok(
        "单 PDF：产物平铺到输出目录根下、嵌套壳被清掉",
        sorted(p.name for p in flat_dest.iterdir()) == ["1.jpg", "2.jpg"],
        str(sorted(p.name for p in flat_dest.iterdir())),
    )

    # 单 PDF 但根下已有同名文件：整个不动（宁可多留一层，也不能覆盖/丢产物）
    clash_dest = Path(ctx.tmp) / "flat_clash"
    (clash_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (clash_dest / "样书" / "images" / "1.jpg").write_bytes(b"nested")
    (clash_dest / "1.jpg").write_bytes(b"root")
    _kernel._flatten_single_pdf_output(StepRequest(source=single_pdf, dest=clash_dest))
    ok(
        "单 PDF 平铺遇到同名：整个不动（不覆盖、不删产物）",
        (clash_dest / "样书" / "images" / "1.jpg").read_bytes() == b"nested"
        and (clash_dest / "1.jpg").read_bytes() == b"root",
        "同名冲突时两处内容都得原样留着",
    )

    # ⚠️ 同一个 PDF **重跑**：根下已有上一轮平铺的同名文件，内容**完全一样**
    #    （用户 2026-10-03 报：输出目录里躺着两套 192 张，预览里每页出现两次）。
    #    内容相同 ⇒ 那是重跑产生的副本，不是冲突：搬上去、嵌套壳清掉。
    rerun_dest = Path(ctx.tmp) / "flat_rerun"
    (rerun_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    for name in ("1.jpg", "2.jpg"):
        (rerun_dest / "样书" / "images" / name).write_bytes(b"same")
        (rerun_dest / name).write_bytes(b"same")
    _kernel._flatten_single_pdf_output(StepRequest(source=single_pdf, dest=rerun_dest))
    ok(
        "重跑（同名同内容）：不算冲突，嵌套壳被清掉、不留两套",
        sorted(p.name for p in rerun_dest.iterdir()) == ["1.jpg", "2.jpg"],
        str(sorted(p.name for p in rerun_dest.iterdir())),
    )

    # 混合：1.jpg 同内容（重跑）但 2.jpg 内容不同（真冲突）⇒ 嵌套树整体保留，
    # 且**已经搬走的也要放回去**？—— 不行：已搬走的 1.jpg 与根下同名同内容，
    # 留在根下等价于没丢；关键是 2.jpg 必须在 nested 里还在。
    mixed_dest = Path(ctx.tmp) / "flat_mixed"
    (mixed_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (mixed_dest / "样书" / "images" / "1.jpg").write_bytes(b"same")
    (mixed_dest / "1.jpg").write_bytes(b"same")
    (mixed_dest / "样书" / "images" / "2.jpg").write_bytes(b"new")
    (mixed_dest / "2.jpg").write_bytes(b"old")
    _kernel._flatten_single_pdf_output(StepRequest(source=single_pdf, dest=mixed_dest))
    ok(
        "混合情况：真冲突那份留在嵌套里，且不覆盖根下的旧文件",
        (mixed_dest / "样书" / "images" / "2.jpg").read_bytes() == b"new"
        and (mixed_dest / "2.jpg").read_bytes() == b"old",
        f"nested2={(mixed_dest / '样书' / 'images' / '2.jpg').exists()}",
    )

    # 目录源 = 批量：每个 PDF 一个子目录是**对的**（否则大家的 1.jpg 互相覆盖）
    batch_dest = Path(ctx.tmp) / "flat_batch"
    (batch_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (batch_dest / "样书" / "images" / "1.jpg").write_bytes(b"x")
    _kernel._flatten_single_pdf_output(StepRequest(source=drop_dir, dest=batch_dest))
    ok("目录源（批量）保持每个 PDF 一个子目录", (batch_dest / "样书" / "images" / "1.jpg").exists())

    # ---- 1d. 清单只有一份：流程/导航/面板都从 SPECS 派生 ----
    # 用户 2026-10-02：后期要做「步骤随意搭配」的自定义流程（类 BPM），前提是
    # **步骤清单只有一个事实来源**。改造前有四份（STAGES / SPECS / MODULES /
    # PANEL_CLASSES）各写各的，加一步要改四处、漏一处没有任何守卫能发现。
    from desktop.store import (
        IMPOSITION_INDEX,
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
    ok("流程主链正好是四步、顺序未变", STAGES == ("extract", "detect", "rembg", "print"), str(STAGES))
    ok("每条 role 取值合法", all(s.role in ("stage", "optional") for s in SPECS), str([(s.key, s.role) for s in SPECS]))
    ok(
        "每条都声明了 BPM 端口（已由 desktop.steps.ports 接线）",
        all(s.inputs and s.outputs for s in SPECS),
        str([(s.key, s.inputs, s.outputs) for s in SPECS]),
    )

    ok(
        "步骤条文案由 stage_name() 派生",
        all(STAGE_LABELS[k] == spec_by_key(k).stage_name() for k in STAGES),
        str(STAGE_LABELS),
    )
    ok(
        "步骤条短名由 short_name() 派生",
        all(STAGE_SHORT[k] == spec_by_key(k).short_name() for k in STAGES),
        str(STAGE_SHORT),
    )
    ok(
        "步骤条四个名字逐字未变（用户手册配图依赖它）",
        [STAGE_LABELS[k] for k in STAGES] == ["提取图片", "检测文本框", "图片去底色", "生成 PDF"],
        str([STAGE_LABELS[k] for k in STAGES]),
    )
    ok(
        "「提交本次任务」仍挂在第三步的文案表里（它不是独立步骤）",
        STAGE_LABELS.get("rembg_submit") == "提交去底色结果" and "rembg_submit" not in STAGES,
    )

    ok(
        "可选节点派生正确（拼版：有模块页、但不在主链上）",
        (IMPOSITION_STAGE, IMPOSITION_LABEL, IMPOSITION_INDEX) == ("imposition", "图片拼版", len(STAGES)),
        f"{IMPOSITION_STAGE} / {IMPOSITION_LABEL} / {IMPOSITION_INDEX}",
    )
    ok("可选节点不在主链里", all(s.key not in STAGES for s in SPECS if s.role == "optional"))

    from desktop.modules import MODULES

    ok("导航清单 = SPECS 里 nav=True 的派生", tuple(m.key for m in MODULES) == NAV_STEPS, str(NAV_STEPS))
    ok(
        "导航文案/悬停提示/图标都由 spec 提供",
        all(
            m.title == spec_by_key(m.key).nav_name()
            and m.subtitle == spec_by_key(m.key).nav_tip()
            and m.icon == spec_by_key(m.key).nav_icon
            for m in MODULES
        ),
    )
    ok(
        "没有独立模块页的步骤不进导航（免得壳层去建不存在的页面）",
        all(spec_by_key(m.key).nav for m in MODULES) and set(NAV_STEPS) == {m.key for m in MODULES},
        str(NAV_STEPS),
    )
    # ⚠️ 逐字锁死：导航文案改动**必须**显式改spec.nav_title，而不是碰title
    #    （title 同时是模块页的大标题，一改就把页头也带走了）。用户 2026-10-03
    #    定的这一组名字——统一带对象名、且「生成PDF」不加空格。
    #    ⚠️ 顺序里「生成PDF」在**最后**：它吃前几步的产物，"生成"是收尾动作
    #    （nav_order=100 把它挪到末尾），但流程条上它仍是第 4 步——两条线独立。
    ok(
        "导航文案与顺序逐字来自 spec（生成PDF 排最后）",
        [m.title for m in MODULES] == ["PDF图片提取", "检测文本框", "图片去底色", "图片拼板", "生成PDF"],
        str([m.title for m in MODULES]),
    )
    # 护栏：调导航顺序**不许**动流程主链。FLOW_STAGES 从 SPECS 派生，若有人为了
    # 挪导航而去对调 SPECS 里两段的书写位置，流程的执行顺序就会被带着变。
    ok(
        "导航挪动不影响流程主链顺序（print 仍是第 4 步）",
        FLOW_STAGES == ("extract", "detect", "rembg", "print") and FLOW_STAGES.index("print") == 3,
        str(FLOW_STAGES),
    )
    ok(
        "nav_order 只影响导航、不泄漏到流程顺序",
        spec_by_key("print").nav_order != 0 and FLOW_STAGES[-1] == "print",
        f"nav_order={spec_by_key('print').nav_order}, FLOW={FLOW_STAGES}",
    )
    # 开了 nav 却忘了文案/图标 = 导航上出现一个没提示的空条目，肉眼很难发现。
    ok(
        "每个 nav=True 的 spec 都填了导航三件套（标题/悬停提示/图标）",
        all(spec_by_key(k).nav_name() and spec_by_key(k).nav_tip() and spec_by_key(k).nav_icon for k in NAV_STEPS),
        str([(k, spec_by_key(k).nav_tooltip, spec_by_key(k).nav_icon) for k in NAV_STEPS]),
    )

    # ---- 子任务目录名（磁盘路径）与显示文案**必须解耦** ----
    # singletask/<子任务>/ 里是缩略图缓存与**用户手改过的版面图**。目录名一旦
    # 跟着文案变，那些文件就成了没人再去找的孤儿（"我明明改过版面，重新打开又
    # 变回原样"）。所以目录名锚在 disk_key（路由键）上，与 title/nav_title 无关。
    ok(
        "磁盘子任务目录名取 disk_key，不取任何显示文案",
        all(spec_by_key(k).disk_key() == k for k in NAV_STEPS),
        str([(k, spec_by_key(k).disk_key()) for k in NAV_STEPS]),
    )
    ok(
        "磁盘目录名与导航/页头文案完全无关（改文案不会动磁盘路径）",
        all(spec_by_key(k).disk_key() not in (spec_by_key(k).title, spec_by_key(k).nav_name()) for k in NAV_STEPS),
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
        tuple(c.__name__ for c in PANEL_CLASSES) == tuple(spec_by_key(k).panel.split(":")[-1] for k in STAGES),
        str([c.__name__ for c in PANEL_CLASSES]),
    )
    ok(
        "模块页沿用旧名（面板类名没被这次重构改掉）",
        [c.__name__ for c in PANEL_CLASSES] == ["ExtractPanel", "DetectPanel", "RembgPanel", "PrintPanel"],
    )

    # ---- 2. 执行内核：纯函数 job ----
    def _job(request, report):
        report("progress", {"done": 1, "total": 2})
        report("log", {"message": "干活中"})
        # 步骤**私有**的结构化事件（detect 报框走的就是这条）：
        report("page_boxes", {"image": "0001", "left": [1, 2, 3, 4], "right": None, "full": None})
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
    ok(
        "跑完收到完成信号（输出目录原样回传）",
        wait_until(app, lambda: "out" in got, timeout=5) and got["out"] == "d",
        str(got),
    )
    ok("进度事件按序送达", got["progress"] == [(1, 2), (2, 2)], str(got["progress"]))
    ok("日志事件送达", got["logs"] == ["干活中"], str(got["logs"]))
    # ⚠️ 这条是「检测文本框」独立模块页能不能显示框的前提：detect 默认不落盘，
    #    坐标只经 page_boxes 事件回来；内核只认 progress/log 的话它就永远空着。
    ok(
        "步骤私有事件经内核透传（page_boxes 到得了上层）",
        len(got["events"]) == 1 and got["events"][0][0] == "page_boxes" and got["events"][0][1]["image"] == "0001",
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
    ok("慢 job 最终完成", wait_until(app, lambda: "out" in done, timeout=6), str(done))

    def _bad_job(request, report):
        raise RuntimeError("故意炸")

    bad = StepKernel(callable_job(_bad_job))
    errs: list[str] = []
    bad.failed.connect(errs.append)
    bad.run(StepRequest(dest=Path("d")))
    ok(
        "job 异常转成 failed 信号（不抛进事件循环）",
        wait_until(app, lambda: bool(errs), timeout=5) and "故意炸" in errs[0],
        str(errs),
    )

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
        ok(
            "input/output 按 API 注入",
            str(captured["args"].get("input")) == str(tmp_in) and str(captured["args"].get("output")) == str(tmp_out),
        )
        ok("面板参数一并带上", captured["args"].get("zoom") == 3)
        ok("输出目录精确生效（不被命令追加子目录）", captured.get("outpath") == tmp_out, str(captured.get("outpath")))
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

    functions.get_function = lambda cmd, ca, reporter=None: _FakeFileFunction(ca, reporter)
    try:
        pdf_dir = Path(ctx.tmp) / "pdf_out"
        pdf_job = _kernel.job_for(spec_by_key("print"))
        pdf_result = pdf_job(StepRequest(source=tmp_in, dest=pdf_dir, args={}), lambda *a: None)
        ok(
            "产物是文件：--output 传目录、命令自己取名（outpath 不被覆盖）",
            captured.get("outpath") == pdf_dir / "output.pdf",
            str(captured.get("outpath")),
        )
        ok(
            "产物是文件：finished 回传的是**产物路径**而不是目录",
            pdf_result == str(pdf_dir / "output.pdf"),
            str(pdf_result),
        )
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

    ok(
        "执行内核与共用控件都对外暴露事件通道",
        hasattr(_K, "event") and hasattr(StepControl, "event"),
        f"kernel={hasattr(_K, 'event')} control={hasattr(StepControl, 'event')}",
    )
    event_sink: list = []
    control_a.event.connect(lambda name, payload: event_sink.append((name, payload)))
    control_a.kernel.event.emit("page_boxes", {"image": "0009"})
    app.processEvents()
    ok(
        "内核事件能经共用控件转出来（模块页的接入点）",
        event_sink == [("page_boxes", {"image": "0009"})],
        str(event_sink),
    )

    # 没选源就点执行：只发一条 warning 状态，绝不起线程（免得白跑一趟空活儿）
    idle = StepControl(rembg)
    blocked: list = []
    idle.status.connect(lambda text, kind: blocked.append((text, kind)))
    idle.run()
    ok(
        "没有源时执行被拦下（只发状态、不起线程）",
        bool(blocked) and blocked[0][1] == "warning" and idle.busy() is False,
        str(blocked),
    )
    idle.shutdown()

    control_a.shutdown()
    control_b.shutdown()

    # ---- 4b. 大输入区（用户要的那块"大的输入框"）----
    from PySide6.QtCore import QMimeData, QUrl

    from desktop.steps import SourceZone
    from desktop.steps.source_zone import EMPTY_HEIGHT, FILLED_HEIGHT

    # ⚠️ 用 rembg（仍收目录）当夹具，不用 extract：图片提取已经改成
    #    **只支持文件**（用户 2026-10-03），它不摆「选择文件夹」按钮。
    zone = SourceZone(rembg)
    zone.resize(420, 240)
    ok("大输入区默认收拖拽", zone.acceptDrops() is True)
    ok("空态是大块（还没选东西）", zone.source() is None and zone.height() == EMPTY_HEIGHT, str(zone.height()))

    zone_seen: list = []
    zone_rejected: list = []
    zone.paths_chosen.connect(zone_seen.append)
    zone.rejected.connect(zone_rejected.append)
    zone.offer([])
    ok("空拖拽不发路径、只报一句 rejected", zone_seen == [] and bool(zone_rejected), str(zone_rejected))

    mime = QMimeData()
    mime.setUrls(
        [
            QUrl.fromLocalFile(str(drop_dir)),
            QUrl("https://example.com/not-local"),
        ]
    )
    ok(
        "拖拽数据只取本地文件/文件夹",
        [Path(p) for p in SourceZone.paths_from_mime(mime)] == [drop_dir],
        str(SourceZone.paths_from_mime(mime)),
    )
    ok("纯文本的拖拽数据取不到路径", SourceZone.paths_from_mime(QMimeData()) == [])

    zone.offer(SourceZone.paths_from_mime(mime))
    ok(
        "拖进来的路径原样发出去（不做合法性判断）",
        len(zone_seen) == 1 and [Path(p) for p in zone_seen[0]] == [drop_dir],
        str(zone_seen),
    )
    zone.set_source(drop_dir, "12 个可用文件")
    ok("已选态收窄成一行", zone.source() == drop_dir and zone.height() == FILLED_HEIGHT, str(zone.height()))

    cleared: list = []
    zone.cleared.connect(lambda: cleared.append(True))
    zone.clear()
    ok("清空回到空态并发出 cleared", cleared == [True] and zone.source() is None and zone.height() == EMPTY_HEIGHT)

    # 拖动经过时的高亮开关（宿主页面转发整页拖拽时用）
    zone.set_hot(True)
    ok("可以外部点亮拖拽热区", zone._hot is True)
    zone.set_hot(False)
    ok("可以熄灭拖拽热区", zone._hot is False)

    # ---- 4b-2. 点空白处 → 直接开选择对话框（无小菜单、且不压在同一鼠标事件里）----
    # ⚠️ 2026-10-02 用户报的 bug：点大输入区弹出的选择界面不出现。根因是
    # `browse()` 被同步压在 mousePressEvent 里——模态叠在**同一个尚未返回**的
    # 鼠标事件里。修法：用 QTimer 推迟到事件返回之后再弹。
    #
    # ⚠️⚠️ 2026-10-03 用户要求：「能否底部不设置选择图片或者目录的弹窗」——
    #    去掉的是**点空白处那个两选项小菜单**（RoundMenu，锚在控件底部）。
    #    现在点空白处 = 直接开资源管理器的选文件对话框。
    # ⚠️ 这里刻意**不替换 `_open_dialog`**，而是替换更底层的 `QFileDialog`：
    #    那样才能同时钉住"没有小菜单"与"确实开的是文件对话框"。
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QFileDialog

    from desktop.utils.files import default_open_dir

    browse_calls: list = []
    original_name = QFileDialog.getOpenFileName
    original_menu = SourceZone._ask_kind if hasattr(SourceZone, "_ask_kind") else None

    # 若还留着那个小菜单方法，就让它一被调用就炸（用来证明它**没**被调用）
    def _menu_should_not_run(self):
        browse_calls.append("MENU")
        raise AssertionError("不该弹两选项小菜单（用户 2026-10-03 要求去掉）")

    if original_menu is not None:
        SourceZone._ask_kind = _menu_should_not_run
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (browse_calls.append(("file", a[2])), ("", ""))[1])
    try:
        zone.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(zone.width() // 2, zone.height() // 2),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        ok("点击大输入区**不当场**开模态（否则会叠在同一个鼠标事件里）", browse_calls == [], str(browse_calls))
        ok(
            "事件循环跑完直接开选文件对话框（不再先弹两选项小菜单）",
            wait_until(app, lambda: bool(browse_calls), timeout=3)
            and [c[0] if isinstance(c, tuple) else c for c in browse_calls] == ["file"],
            str(browse_calls),
        )
        ok(
            "对话框起始目录是文档目录，不是空串" "（空串会回退到进程工作目录，打包后就是程序目录）",
            browse_calls and browse_calls[0][1] == str(default_open_dir()),
            repr(browse_calls[0][1] if browse_calls else None),
        )
    finally:
        if original_menu is not None:
            SourceZone._ask_kind = original_menu
        QFileDialog.getOpenFileName = original_name

    # ---- 4b-3. 可见的选择按钮（用户 2026-10-03 报"不能直接点击按钮选择"）----
    # 此前唯一入口是"点空白处弹两选项小菜单"，界面上没有任何东西提示它能点。
    # 这里钉住：① 两个按钮真的存在且可见 ② 点了真的开对应对话框
    # ③ 起始目录仍是文档目录 ④ 已选态换成「更换」 ⑤ accepts_dir=False 不摆目录按钮。
    from desktop.steps.source_zone import BUTTON_HEIGHT, FILLED_HEIGHT as _FILLED

    # ⚠️ 用 `isVisibleTo(zone)` 而不是 `isVisible()`：后者要求**顶层窗口已 show**，
    #    而自测里这个 zone 从不显示，断言会假红（第一版就踩了这个）。
    ok("空态摆出「选择文件」按钮", zone.file_button.isVisibleTo(zone))
    ok("accepts_dir=True 时摆出「选择文件夹」按钮", zone.dir_button is not None and zone.dir_button.isVisibleTo(zone))
    ok(
        "按钮落在虚框内、不被裁掉",
        zone.file_button.height() == BUTTON_HEIGHT and zone.file_button.geometry().bottom() <= zone.height(),
        f"{zone.file_button.geometry()} h={zone.height()}",
    )
    ok(
        "空态按钮行居中",
        abs((zone.file_button.geometry().left() + zone.file_button.width() / 2) - zone.width() / 2) < zone.width() / 2,
        str(zone.file_button.geometry()),
    )

    # ⚠️ 2026-10-03：点按钮 = 直接开**资源管理器的选择对话框**（不是"弹一个
    #    资源管理器窗口去监听选中项"，用户明确纠正过两者区别）。
    #    这里钉住：文件按钮 → 选文件对话框、目录按钮 → 选目录对话框、起始目录
    #    仍是文档目录。
    btn_calls: list = []
    orig_multi = QFileDialog.getOpenFileNames
    orig_dir = QFileDialog.getExistingDirectory
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (btn_calls.append(("file", a[2])), ("", ""))[1])
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: (btn_calls.append(("dir", a[2])), "")[1])
    try:
        zone.file_button.click()
        ok("点「选择文件」**不当场**弹模态（仍在同一个鼠标事件里）", btn_calls == [], str(btn_calls))
        ok(
            "点「选择文件」弹出的是选文件对话框",
            wait_until(app, lambda: bool(btn_calls), timeout=3) and [c[0] for c in btn_calls] == ["file"],
            str(btn_calls),
        )
        ok(
            "按钮路径的起始目录也是文档目录（不是空串）",
            btn_calls and btn_calls[0][1] == str(default_open_dir()),
            repr(btn_calls[0][1] if btn_calls else None),
        )

        btn_calls.clear()
        zone.dir_button.click()
        ok(
            "点「选择文件夹」弹出的是选目录对话框",
            wait_until(app, lambda: bool(btn_calls), timeout=3) and [c[0] for c in btn_calls] == ["dir"],
            str(btn_calls),
        )
    finally:
        QFileDialog.getOpenFileName = original_name
        QFileDialog.getExistingDirectory = orig_dir
        QFileDialog.getOpenFileNames = orig_multi

    # 已选态：换成右端「更换」，两个选择按钮收起来
    zone.set_source(drop_dir / "a.pdf")
    ok("已选态出现「更换」按钮", zone._swap_button.isVisibleTo(zone))
    ok(
        "已选态收起两个选择按钮（不给人三个同权入口）",
        not zone.file_button.isVisibleTo(zone)
        and not (zone.dir_button is not None and zone.dir_button.isVisibleTo(zone)),
    )
    ok("已选态高度收窄成一行", zone.height() == _FILLED, str(zone.height()))
    ok(
        "已选态「更换」与清空 ✕ 不重叠",
        zone._swap_button.geometry().right() < zone.width() - 26 - 8 + 1,
        f"swap={zone._swap_button.geometry()} w={zone.width()}",
    )

    # accepts_dir=False 的步骤不该摆一个注定被拒的「选择文件夹」，
    # 但「选择文件」要照常在（那才是它唯一的合法入口）
    no_dir = SourceZone(
        StepSpec(
            key="probe",
            command=None,
            title="探针",
            panel=None,
            pick_label="选择文件",
            file_filter="PDF 文件 (*.pdf)",
            accepts_dir=False,
        )
    )
    ok(
        "不接受目录的步骤不摆「选择文件夹」，但保留「选择文件」",
        no_dir.dir_button is None and no_dir.file_button.isVisibleTo(no_dir),
    )

    # ---- 4b-3c. 「更换」真的能换源（用户 2026-10-03 报"点了没反应"）----
    # ⚠️ 必须走 **QTest.mouseClick**（Qt 自己的 hit-test 路径），不能用
    #    ``.click()`` —— 后者直接 emit ``clicked``，完全不经过命中测试，
    #    那样测不出"按钮画出来了却点不到"这类问题（第一版探针就栽在这）。
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    swap_calls: list = []
    orig_name2 = QFileDialog.getOpenFileName
    # 「更换」= 再选一次，走同一条选文件对话框。这段的重点是它的**几何/命中**
    # （QTest.mouseClick 走命中测试，测的是"画出来了却点不到"那类问题）。
    pdf_a, pdf_b = drop_dir / "a.pdf", drop_dir / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (swap_calls.append(str(a[2])), (str(pdf_b), ""))[1])
    # ⚠️ 必须 show 出来：``QTest.mouseClick`` 走的是**命中测试**路径，控件不在
    #    任何已显示的窗口里时命中不到，事件会悄悄丢掉（自测里表现为"点了没反应"
    #    ——正是本次要防的那个症状本身，不能自己踩一遍）。
    no_dir.show()
    no_dir.resize(900, _FILLED)
    app.processEvents()
    try:
        no_dir.set_source(pdf_a)
        app.processEvents()
        ok("PDF 步骤已选态有「更换」按钮", no_dir._swap_button.isVisibleTo(no_dir))
        QTest.mouseClick(no_dir._swap_button, Qt.MouseButton.LeftButton)
        ok(
            "点「更换」会请求文件对话框（不是目录对话框）",
            wait_until(app, lambda: bool(swap_calls), timeout=3),
            str(swap_calls),
        )
        ok(
            "「更换」的起始目录是文档目录",
            swap_calls and swap_calls[0] == str(default_open_dir()),
            repr(swap_calls[0] if swap_calls else None),
        )

        # 端到端：真的换掉（offer → paths_chosen → 宿主 set_source）
        picked: list = []
        no_dir.paths_chosen.connect(picked.append)
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(pdf_b), ""))
        no_dir.set_source(pdf_a)
        app.processEvents()
        QTest.mouseClick(no_dir._swap_button, Qt.MouseButton.LeftButton)
        wait_until(app, lambda: bool(picked), timeout=3)
        ok("「更换」选完真的把新路径交出去", picked == [[str(pdf_b)]], str(picked))

        # 点已选态的**空白处**也换源（2026-10-03 改回来：不再依赖子控件几何）
        # ⚠️ 这里必须把 stub 换回**会记账**的那个：上一段为了验"交出去的路径"
        #    换了个不记账的 stub，直接拿来断言 ``swap_calls`` 必然是空的
        #    （我自己踩了一次，别再踩）。
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (swap_calls.append(str(a[2])), (str(pdf_b), ""))[1])
        swap_calls.clear()
        QTest.mouseClick(no_dir, Qt.MouseButton.LeftButton, pos=no_dir.rect().center())
        ok(
            "点已选态空白处也能换源（不依赖按钮几何）",
            wait_until(app, lambda: bool(swap_calls), timeout=3),
            str(swap_calls),
        )

        # ✕ 仍是清空（别被上面的"点哪都换源"吃掉）
        cleared: list = []
        no_dir.cleared.connect(lambda: cleared.append(1))
        no_dir.set_source(pdf_a)
        app.processEvents()
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent

        hit = no_dir._close_rect.center().toPoint()
        no_dir.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(hit),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        ok("点右上角 ✕ 是清空、不是换源", bool(cleared), str(cleared))

        # 对话框炸了要说给用户听（Qt 会吞掉 singleShot 回调里的异常）
        boom: list = []
        no_dir.rejected.connect(boom.append)

        def _boom(*a, **k):
            raise RuntimeError("模拟对话框故障")

        QFileDialog.getOpenFileName = staticmethod(_boom)
        no_dir.set_source(pdf_a)
        app.processEvents()
        QTest.mouseClick(no_dir._swap_button, Qt.MouseButton.LeftButton)
        ok(
            "对话框异常会转成 rejected 提示（而不是静默无反应）",
            wait_until(app, lambda: bool(boom), timeout=3) and "对话框" in boom[0],
            str(boom),
        )
    finally:
        QFileDialog.getOpenFileName = orig_name2
        no_dir.hide()
        no_dir.deleteLater()

    # ---- 4b-3b. 独占模式（用户 2026-10-03：初始只有一个输入框）----
    # 页面上再没有别的控件时，输入区要撑满整幅——否则分栏一收，页面上半屏是
    # 框、下半屏空白，看着像没加载完。
    from desktop.steps.source_zone import SOLO_HEIGHT, SOLO_MIN_WIDTH

    solo = SourceZone(rembg)
    solo.resize(600, 200)
    solo.set_solo_mode(True)
    ok("独占模式：撑满整幅", solo.height() == SOLO_HEIGHT, str(solo.height()))
    solo.set_solo_mode(False)
    ok("退出独占：回到常规空态高度", solo.height() == EMPTY_HEIGHT, str(solo.height()))
    solo.set_solo_mode(True)
    solo.set_source(drop_dir / "a.png")
    ok("独占模式下选中源 → 收窄成一行（纵向空间让给分栏）", solo.height() == FILLED_HEIGHT, str(solo.height()))
    solo.set_source(None)
    ok("独占模式 + 回到空态 → 又撑满", solo.height() == SOLO_HEIGHT, str(solo.height()))
    # ⚠️ 这条是**真实 bug 的钉子**（靠截图发现的，断言全绿时根本看不出来）：
    #    独占模式最初用 setFixedHeight(320)，它同时钉死了 maximumHeight；
    #    后来改成"最小 320 + 可拉伸"却只改了 minimumHeight，控件就永远长不大
    #    ——整页只有一条 320px 的框，上下各留一片空白。
    ok(
        "独占模式真的能长高（不是被旧的最大高度钉住）",
        solo.maximumHeight() > solo.minimumHeight(),
        f"min={solo.minimumHeight()} max={solo.maximumHeight()}",
    )
    # ⚠️ 这条钉的是**stderr 警告**（用户 2026-10-03 报「单独拼板界面报错」）：
    #    "QWidget::setMaximumSize: The largest allowed size is (16777215,16777215)"。
    #    Qt 的硬上限 QWIDGETSIZE_MAX == (1<<24)-1 == 16777215，哨兵写成 1<<24
    #    就超了 1，Qt 截断回上限并往 stderr 打警告；拼板独立页初始即独占模式，
    #    于是每次进页面都刷一条，看着像报错。断言取"Qt 自己认的上限"。
    ok(
        "独占模式的最大高度哨兵不超 Qt 硬上限（否则进页面就刷警告）",
        solo.maximumHeight() <= (1 << 24) - 1,
        str(solo.maximumHeight()),
    )
    solo.set_solo_mode(False)

    # 独占模式的最小宽度也要比常规宽（独占时没有分栏挤它，不必那么窄）
    narrow = SourceZone(rembg)
    narrow.set_solo_mode(True)
    ok("独占模式抬高最小宽度", narrow.minimumWidth() == SOLO_MIN_WIDTH, str(narrow.minimumWidth()))
    narrow.set_solo_mode(False)
    ok("退出独占后最小宽度复原", narrow.minimumWidth() == 260, str(narrow.minimumWidth()))

    # ---- 4b-4. 传 str 的路径不许流到 PreviewWorker（用户 2026-10-03 报）----
    # 根因：模块页把 `str(p)` 列表交给 `set_images`，而 PreviewWorker.run() 里
    # 读 `self.path.suffix` —— 异常发生在**子线程内**，只经 failed 信号显示成
    # 「加载失败：'str' object has no attribute 'suffix'」。这里在两处边界
    # 各钉一道：viewer 的 set_images 与 worker 的构造。
    from desktop.components.viewers import ImageViewerWidget
    from desktop.workers import PreviewWorker

    viewer = ImageViewerWidget(editable=False)
    viewer.set_images([str(drop_dir / "a.png"), str(drop_dir / "c.png")])
    ok(
        "set_images 接受 str 列表并统一转成 Path",
        len(viewer.paths) == 2 and all(isinstance(p, Path) for p in viewer.paths),
        str([type(p).__name__ for p in viewer.paths]),
    )

    worker = PreviewWorker(str(drop_dir / "a.png"))
    ok("PreviewWorker 构造时把 str 收成 Path", isinstance(worker.path, Path), str(type(worker.path).__name__))

    # 真跑一次：不该出现 suffix 相关的 AttributeError
    probe_fail: list = []
    probe_worker = PreviewWorker(str(drop_dir / "a.png"))
    probe_worker.failed.connect(lambda _p, m: probe_fail.append(m))
    probe_worker.run()
    ok("PreviewWorker(str).run() 不抛 AttributeError", not any("suffix" in m for m in probe_fail), str(probe_fail))

    # ⚠️ 同名只保留一份（用户 2026-10-03 报：预览里每页出现两次）
    from desktop.modules.extract.page import collect_result_images

    dup_dir = Path(ctx.tmp) / "dup_out"
    (dup_dir / "样书" / "images").mkdir(parents=True, exist_ok=True)
    for name in ("1.jpg", "2.jpg", "10.jpg"):
        (dup_dir / name).write_bytes(b"x")
        (dup_dir / "样书" / "images" / name).write_bytes(b"x")
    picked = collect_result_images(dup_dir)
    ok(
        "平铺 + 嵌套两套同名：只收一份，且优先顶层",
        [p.name for p in picked] == ["1.jpg", "2.jpg", "10.jpg"] and all(p.parent == dup_dir for p in picked),
        str([(p.name, p.parent.name) for p in picked]),
    )
    ok(
        "去重后按数字自然排序（2 在 10 前面）",
        [p.name for p in picked] == ["1.jpg", "2.jpg", "10.jpg"],
        str([p.name for p in picked]),
    )

    # 只有嵌套那一套时也要收得到（不能因为"没有顶层"就漏掉）
    only_nested = Path(ctx.tmp) / "only_nested"
    (only_nested / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (only_nested / "样书" / "images" / "1.jpg").write_bytes(b"x")
    ok(
        "只有嵌套那一套时也能收到图",
        [p.name for p in collect_result_images(only_nested)] == ["1.jpg"],
        str(collect_result_images(only_nested)),
    )

    # ---- 4c. 大输入区 + 控制组件：外部摆、内部接线（模块页的用法）----
    zone_c = SourceZone(rembg)
    control_c = StepControl(rembg, zone=zone_c)
    ok("控件接受外部大输入区（不重复摆一块）", control_c.zone is zone_c)
    zone_c.offer([str(drop_dir / "c.png")])
    ok(
        "从大输入区拖入 → 控件拿到源（按 spec 归一化）",
        control_c.source() == drop_dir / "c.png",
        str(control_c.source()),
    )
    ok("大输入区同步显示成已选态", zone_c.source() == drop_dir / "c.png")
    zone_c.offer([str(drop_dir / "a.pdf")])
    ok("后缀不符时不动源（只发状态）", control_c.source() == drop_dir / "c.png")
    zone_c.clear()
    ok("清空大输入区 → 控件的源与输出一起复位", control_c.source() is None and control_c.output() is None)
    control_c.shutdown()

    # ---- 5. 子进程传输层：启动参数与 UTF-8 环境（不起真进程）----
    args_packed = worker_arguments(Path("/tmp/run-1.json"))
    ok(
        "源码环境按模块启动 worker",
        args_packed[:2] == ["-m", "desktop.worker"] and "--config" in args_packed,
        str(args_packed),
    )
    env = worker_env()
    ok("子进程强制 UTF-8", env.value("PYTHONIOENCODING") == "utf-8" and env.value("PYTHONUTF8") == "1")
    ok("传输层初始没有进程", StageProcess().process is None)
    ok("传输层初始不忙", StageProcess().running() is False)

    # ---- 6. 子任务目录改名的一次性迁移（磁盘路径不能被文案改动带走）----
    # singletask/<子任务>/ 里是缩略图缓存与用户手改过的版面图，目录名换成
    # disk_key 后，老的中文名目录必须被搬过去，且**旧目录不删**（误删不可恢复）。
    import tempfile

    from desktop.utils import files as F

    with tempfile.TemporaryDirectory() as td:
        real_root = Path(td) / "guji"

        def _fake_root():
            return real_root

        orig = F.guji_data_dir
        F.guji_data_dir = _fake_root  # type: ignore[assignment]
        try:
            base = real_root / "singletask"
            # 造两个"老中文名"目录，各放一个标记文件（模拟缓存/手改件）
            (base / "拼图" / "edited").mkdir(parents=True)
            (base / "拼图" / "edited" / "p1.png").write_bytes(b"edited")
            (base / "去底色" / "thumbs").mkdir(parents=True)
            (base / "去底色" / "thumbs" / "a.jpg").write_bytes(b"thumb")
            # 再造一个"新名已存在"的场景，验证不会被覆盖
            (base / "detect").mkdir(parents=True)
            (base / "detect" / "keep.jpg").write_bytes(b"keep")
            (base / "检测文本框").mkdir(parents=True)
            (base / "检测文本框" / "old.jpg").write_bytes(b"old")

            moved = F.migrate_legacy_singletask_dirs()
            ok(
                "老中文名目录被搬到 disk_key 名下",
                (base / "imposition" / "edited" / "p1.png").exists() and (base / "rembg" / "thumbs" / "a.jpg").exists(),
                str(moved),
            )
            ok(
                "搬过去的是原内容（一个字节不差）",
                (base / "imposition" / "edited" / "p1.png").read_bytes() == b"edited",
            )
            ok("迁移报出了搬动清单（给日志/排查用）", any("拼图" in m for m in moved), str(moved))
            # 新目录已存在时**不动**旧目录（不覆盖、不合并、绝不删）
            ok(
                "新目录已存在时旧目录原样保留（绝不覆盖用户数据）",
                (base / "detect" / "keep.jpg").read_bytes() == b"keep"
                and (base / "检测文本框" / "old.jpg").read_bytes() == b"old",
            )
            # 幂等：再跑一遍什么都不该发生
            again = F.migrate_legacy_singletask_dirs()
            ok("迁移是幂等的（重复启动不重复搬）", again == [], str(again))
            ok(
                "旧目录不被删除（用户可自己确认后清理）",
                not (base / "拼图").exists() and not (base / "去底色").exists(),
            )
        finally:
            F.guji_data_dir = orig  # type: ignore[assignment]


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
