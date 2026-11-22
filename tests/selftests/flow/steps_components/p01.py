# -*- coding: utf-8 -*-
"""1. 步骤元数据 / 1b. 「入口」规则：后缀 / 目录 / 一堆路径归一成一个源 / 1c. 出口布局：入口自动下钻 + 单 PDF 平铺"""

from typing import Any


def run(st: Any) -> None:
    from desktop.steps.kernel import (
        CommandJob,
        StepKernel,
        StepRequest,
        callable_job,
        command_job,
    )
    from pathlib import Path
    from desktop.steps.spec import (
        FLOW_STAGES,
        NAV_STEPS,
        SPECS,
        STEP_KEYS,
        StepSpec,
        spec_by_key,
    )
    import desktop.steps.kernel as _kernel
    from tests.selftests._context import ok, wait_until
    ok(
        "步骤注册表五条（4 步主链 + 1 个可选节点）",
        STEP_KEYS == ("extract", "detect", "rembg", "print", "imposition"),
        str(STEP_KEYS),
    )
    ok("按 key 取到同一条", spec_by_key("extract") is SPECS[0])
    ok("未知 key 返回 None", spec_by_key("nope") is None)
    ok(
        "每条都声明了参数面板",
        all(s.panel for s in SPECS),
        str([s.panel for s in SPECS]),
    )
    ok("面板类都能解析出来", all(s.panel_class() is not None for s in SPECS))

    def spec_of(key: str) -> StepSpec:
        """查注册表里**必然存在**的 key（None 只会出现在"未知 key"用例里）。"""
        s = spec_by_key(key)
        assert s is not None
        return s
    st.spec_of = spec_of

    st.extract = st.spec_of("extract")
    st.rembg = st.spec_of("rembg")
    st.imposition = st.spec_of("imposition")

    ok("执行按钮文案", st.extract.run_text() == "开始提取", st.extract.run_text())

    ok(
        "拼图允许对话框里一次多选（拖拽天然支持多选）",
        st.imposition.allow_multi and not st.extract.allow_multi,
    )
    ok(
        "默认输出：文件源 → 父目录/文件名+后缀",
        st.extract.default_output(Path("/a/b/c.pdf")) == Path("/a/b/c_提取"),
        str(st.extract.default_output(Path("/a/b/c.pdf"))),
    )
    ok(
        "默认输出：目录源 → 父目录/目录名+后缀",
        st.rembg.default_output(Path("/a/b/dir")) == Path("/a/b/dir_去底"),
        str(st.rembg.default_output(Path("/a/b/dir"))),
    )
    ok(
        "默认输出：固定名优先",
        st.imposition.default_output(Path("/a/b/x.png")) == Path("/a/b/拼图成品"),
        str(st.imposition.default_output(Path("/a/b/x.png"))),
    )
    ok("源为空时输出为 None", st.extract.default_output(None) is None)
    ok(
        "后缀从过滤串推导（不另写一份后缀表）",
        st.extract.suffixes() == (".pdf", ".djvu", ".djv")
        and ".png" in st.rembg.suffixes(),
        f"{st.extract.suffixes()} / {st.rembg.suffixes()}",
    )
    ok(
        "输入物称呼由 pick_label 派生",
        (st.extract.input_noun(), st.rembg.input_noun()) == ("PDF/DjVu", "图片"),
        f"{st.extract.input_noun()} / {st.rembg.input_noun()}",
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

    st.drop_dir = Path(st.ctx.tmp) / "drop"
    st.drop_dir.mkdir(exist_ok=True)
    (st.drop_dir / "a.pdf").write_bytes(b"%PDF-1.4\n")
    (st.drop_dir / "b.pdf").write_bytes(b"%PDF-1.4\n")
    (st.drop_dir / "c.png").write_bytes(b"x")
    other_dir = Path(st.ctx.tmp) / "drop2"
    other_dir.mkdir(exist_ok=True)
    (other_dir / "d.pdf").write_bytes(b"%PDF-1.4\n")

    ok(
        "文件按后缀判定",
        st.extract.accepts_path(st.drop_dir / "a.pdf")
        and not st.extract.accepts_path(st.drop_dir / "c.png"),
    )
    ok(
        "目录按 accepts_dir 判定（提取这一步不收目录）",
        not st.extract.accepts_path(st.drop_dir) and st.rembg.accepts_path(st.drop_dir),
    )
    ok(
        "目录清单只取本步骤的后缀",
        [p.name for p in st.extract.listing(st.drop_dir)] == ["a.pdf", "b.pdf"],
        str([p.name for p in st.extract.listing(st.drop_dir)]),
    )
    ok("读不了的目录返回空表", st.extract.listing(Path(st.ctx.tmp) / "nope") == [])
    # ⚠️ listing 顺序有真实消费方（singletask 左栏缩略图条/source_images）
    #    ——必须自然排序，不能字典序（2026-10-11 用户报障"1,10,11,2…"）。
    nat_drop = Path(st.ctx.tmp) / "drop_nat"
    nat_drop.mkdir(exist_ok=True)
    for name in ("10.png", "2.png", "1.png"):
        (nat_drop / name).write_bytes(b"x")
    ok(
        "目录清单按页序自然排序（1,2,10 而非 1,10,2）",
        [p.name for p in st.rembg.listing(nat_drop)] == ["1.png", "2.png", "10.png"],
        str([p.name for p in st.rembg.listing(nat_drop)]),
    )

    ok(
        "拖一个文件 → 就是它自己",
        st.extract.resolve_source([st.drop_dir / "a.pdf"])[0] == st.drop_dir / "a.pdf",
    )
    # ⚠️ 「PDF 只支持文件」（用户 2026-10-03）：拖文件夹**直接拒绝**，不从
    #    里面替用户挑 PDF——挑了哪几个、为什么是这几个，界面上看不见。
    ok(
        "拖一个文件夹 → 拒绝并说明只支持文件",
        (lambda r: r[0] is None and "只支持" in r[1] and "不支持文件夹" in r[1])(
            st.extract.resolve_source([st.drop_dir])
        ),
        str(st.extract.resolve_source([st.drop_dir])),
    )
    ok(
        "文件与文件夹混着给 → 同样拒绝（按最严的来）",
        (lambda r: r[0] is None and "只支持" in r[1])(
            st.extract.resolve_source([st.drop_dir / "a.pdf", st.drop_dir])
        ),
        str(st.extract.resolve_source([st.drop_dir / "a.pdf", st.drop_dir])),
    )
    ok("收目录的步骤：拖文件夹就是它", st.rembg.resolve_source([st.drop_dir])[0] == st.drop_dir)
    ok(
        "后缀不符 → 拒绝并给理由",
        (lambda r: r[0] is None and "支持" in r[1])(
            st.extract.resolve_source([st.drop_dir / "c.png"])
        ),
    )
    ok("空输入 → 拒绝", st.extract.resolve_source([])[0] is None)
    ok(
        "路径都不存在 → 拒绝",
        st.extract.resolve_source([Path(st.ctx.tmp) / "ghost.pdf"])[0] is None,
    )
    import desktop.steps.kernel as _kernel

    ok(
        "只有图片提取声明了「单源平铺」",
        [s.key for s in SPECS if s.flat_output] == ["extract"],
        str([(s.key, s.flat_output) for s in SPECS]),
    )
    ok(
        "job 一律经 job_for 装配（唯一入口）",
        (
            isinstance(_je := _kernel.job_for(st.extract), CommandJob)
            and isinstance(_jr := _kernel.job_for(st.rembg), CommandJob)
            and _je.command == "extract"
            and _je._after is not None
            and _jr.command == "rembg"
            and _jr._after is None
            and _kernel.job_for(st.imposition) is None
        ),
        "extract 要带收尾钩子、rembg 不带、拼图无命令",
    )
    ok("没有命令的步骤不造 job", _kernel.job_for(st.imposition) is None)

    # 顶层没文件、下一层唯一 → 自动指过去
    nested_root = Path(st.ctx.tmp) / "nested"
    (nested_root / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (nested_root / "样书" / "images" / "1.png").write_bytes(b"x")
    ok(
        "目录顶层没有 → 自动下钻到唯一子目录并交代一句",
        (lambda r: r[0] == nested_root / "样书" / "images" and bool(r[1]))(
            st.rembg.resolve_source([nested_root])
        ),
        str(st.rembg.resolve_source([nested_root])),
    )

    # 顶层没文件、多个子目录各装着 → 让用户自己挑（混着处理会把两本书拼在一起）
    multi_root = Path(st.ctx.tmp) / "multi"
    for name in ("甲", "乙"):
        deep = multi_root / name / "images"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "1.png").write_bytes(b"x")
    ok(
        "多个子目录各装着 → 拒绝并让用户挑一个",
        (lambda r: r[0] is None and "请直接把其中一个" in r[1])(
            st.rembg.resolve_source([multi_root])
        ),
        str(st.rembg.resolve_source([multi_root])),
    )

    # ⚠️ 目录里一个目标文件都没有（含往下两层也找不到）→ **当场**说清，
    #    而不是放行、让功能层稍后报一句"未找到图片"（用户 2026-10-04：
    #    「如果导入的是目录，可以检测是否有需要的图片或者文件，没有则可以提示」）。
    #    那时源已选上、输出目录已推好、预览空着，用户得回头猜是哪步挑错了。
    barren_root = Path(st.ctx.tmp) / "barren"
    (barren_root / "子目录").mkdir(parents=True, exist_ok=True)
    (barren_root / "说明.txt").write_bytes(b"x")
    (barren_root / "子目录" / "readme.md").write_bytes(b"x")
    _rs, _rs_note = st.rembg.resolve_source([barren_root])
    ok(
        "目录里没有目标文件（含子目录）→ 拒绝并当场说明",
        _rs is None and "没有可用" in _rs_note,
        str((_rs, _rs_note)),
    )
    # ⚠️ 边界：目录**压根不存在**时也归到"这些路径都不存在"，不是"没有可用文件"
    ok(
        "目录不存在 → 说「路径不存在」而不是「没有可用文件」",
        (lambda r: r[0] is None and "都不存在" in r[1])(
            st.rembg.resolve_source([Path(st.ctx.tmp) / "ghost_dir"])
        ),
        str(st.rembg.resolve_source([Path(st.ctx.tmp) / "ghost_dir"])),
    )

    # 拼图要的是"一份文件清单"（不是"一个源"）
    imgs_dir = Path(st.ctx.tmp) / "imgs"
    imgs_dir.mkdir(exist_ok=True)
    for name in ("z.png", "a.png", "m.jpg"):
        (imgs_dir / name).write_bytes(b"x")
    (imgs_dir / "note.txt").write_bytes(b"x")
    ok(
        "拼图清单：只要图片、按页序排序、忽略别的文件",
        [p.name for p in st.imposition.collect_files([imgs_dir])]
        == ["a.png", "m.jpg", "z.png"],
        str([p.name for p in st.imposition.collect_files([imgs_dir])]),
    )
    # ⚠️ 页序必须**自然排序**（natural_sort_key），不能用字典序——
    #    否则 "page10" 排到 "page2" 前面，拼版左右半幅配错对（2026-10-11 报障）。
    nat_dir = Path(st.ctx.tmp) / "nat"
    nat_dir.mkdir(exist_ok=True)
    for name in ("10.png", "2.png", "2-l.png", "2-r.png", "cover.png"):
        (nat_dir / name).write_bytes(b"x")
    ok(
        "拼图清单：页号按数值（2<10）、同页号 r 在 l 前、cover 优先",
        [p.name for p in st.imposition.collect_files([nat_dir])]
        == ["cover.png", "2-r.png", "2-l.png", "2.png", "10.png"],
        str([p.name for p in st.imposition.collect_files([nat_dir])]),
    )
    ok(
        "拼图清单：复用下钻规则（顶层没图、唯一子目录装着）",
        [p.name for p in st.imposition.collect_files([nested_root])] == ["1.png"],
        str([p.name for p in st.imposition.collect_files([nested_root])]),
    )
    ok(
        "拼图清单：文件去重",
        len(
            st.imposition.collect_files([imgs_dir / "a.png", imgs_dir / "a.png", imgs_dir])
        )
        == 3,
        str(
            [
                p.name
                for p in st.imposition.collect_files(
                    [imgs_dir / "a.png", imgs_dir / "a.png", imgs_dir]
                )
            ]
        ),
    )

    # 单 PDF：把 <输出>/<PDF名>/** 平铺到 <输出>/ 并删空壳
    single_pdf = Path(st.ctx.tmp) / "样书.pdf"
    single_pdf.write_bytes(b"%PDF-1.4\n")
    flat_dest = Path(st.ctx.tmp) / "flat_out"
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
    clash_dest = Path(st.ctx.tmp) / "flat_clash"
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
    rerun_dest = Path(st.ctx.tmp) / "flat_rerun"
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
    mixed_dest = Path(st.ctx.tmp) / "flat_mixed"
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
    batch_dest = Path(st.ctx.tmp) / "flat_batch"
    (batch_dest / "样书" / "images").mkdir(parents=True, exist_ok=True)
    (batch_dest / "样书" / "images" / "1.jpg").write_bytes(b"x")
    _kernel._flatten_single_pdf_output(StepRequest(source=st.drop_dir, dest=batch_dest))
    ok(
        "目录源（批量）保持每个 PDF 一个子目录",
        (batch_dest / "样书" / "images" / "1.jpg").exists(),
    )

