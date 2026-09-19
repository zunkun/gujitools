# -*- coding: utf-8 -*-
"""配置文件模板 `static/guji.yaml` 与命令规格的一致性自测。

背景：`core/command_spec.py` 的 `COMMAND_SPECS` 是「命令与参数」的唯一事实
来源，但用户实际编辑的是 `static/guji.yaml` 模板。两者若不同步，后果是
**静默的**：模板里少一个命令块，`guji run <cmd>` 只会在运行时抛
「config section missing」，用户照着模板抄却永远抄不出来。

`detect` 就是这样一个案例：它在 `COMMAND_SPECS` 里登记为真实命令、CLI 有
子命令、工厂能构造，但模板里**没有对应小节**——`guji run detect` 必然失败。
补齐后，本模块守住这些不变量：

1. 每个「可从配置驱动的命令」在模板里都有自己的小节；
2. 模板小节的键名必须都在该命令的 `CommandSpec.defaults` 里（无拼写漂移）；
3. 模板里必须显式标注 `detect` 是**非必要**步骤（用户在模板里就能看到）；
4. 模板小节的取值能直接构造 `CommandArgs` 并通过 `validate()`；
5. **索引型文档（README / docs/README / docs/guide/cli / overview）不得漏记任何命令**，
   且都要说明 detect 是非必要的；
6. **docs/guide/cli.md 里列出的 CLI 参数必须真实存在于对应 parser**；
7. **模板里 print 的「数值型」默认值必须与 CLI 的 `PRINT_DEFAULTS` 逐值相等**。

第 5、6 条是同一类漂移的另一半：命令加进代码后，文档常被留在旧状态——
detect 落地时 `docs/guide/cli.md` 甚至写着「不存在 detect 子命令」。

第 7 条补的是另一类盲区：本模块原来只校验**键名**存在，于是
`title_font_size` 模板写 18、CLI 已是 20 这种**数值漂移**照样全绿——
三层默认值（CLI / desktop 面板 / guji.yaml）就此悄悄分叉。
"""

NAME = "config_template"
DEPENDS: list[str] = []
TITLE = "配置模板与命令规格一致"


#: 模板里不参与校验的键（跨命令的通用键，不属于 CommandSpec.defaults）。
_GENERIC_KEYS = {"input", "output", "clean", "workers"}

#: 必须出现在模板小节里的命令。
#: extract/crop/rembg/cropremove/print 是流程主力；detect 虽非必要，但既然
#: 已登记为真实命令，就应当能从配置驱动（只是允许删掉整段）。
_REQUIRED_SECTIONS = ("extract", "detect", "crop", "rembg", "cropremove", "print")


def subs_map(parser) -> dict:
    """从主 parser 取出 {子命令名: 子 parser}（别名去重，保留首次出现的）。"""
    out: dict = {}
    for action in parser._subparsers._group_actions:
        if not getattr(action, "choices", None):
            continue
        for name, sp in action.choices.items():
            out.setdefault(name, sp)
    return out


def _extract_section(text: str, cmd: str):
    """截取 docs/guide/cli.md 里 `### <cmd> — ...` 到下一个 `### ` 之间的内容。

    找不到小节时返回 None。小节标题形如 `### detect — 文本框检测（非必要）`。
    """
    import re

    pattern = re.compile(
        rf"^###\s+{re.escape(cmd)}\b.*?$(.*?)(?=^###\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def run(ctx) -> None:
    from pathlib import Path

    import yaml

    from core.args import CommandArgs
    from core.command_spec import COMMAND_SPECS
    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]
    template = root / "static" / "guji.yaml"
    ok("模板文件存在", template.exists(), str(template))

    raw = template.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    ok("模板可被 YAML 解析为映射", isinstance(data, dict), type(data).__name__)

    # ---- 1. 每个命令都有自己的小节 ----
    for cmd in _REQUIRED_SECTIONS:
        ok(f"模板含 {cmd} 小节",
           cmd in data and isinstance(data[cmd], dict),
           f"实际顶层键={sorted(k for k in data if isinstance(data[k], dict))}")

    # ---- 2. 键名不得漂移：模板里的键都要能在 CommandSpec 里找到 ----
    for cmd in _REQUIRED_SECTIONS:
        spec = COMMAND_SPECS.get(cmd)
        ok(f"{cmd} 已在 COMMAND_SPECS 登记", spec is not None, str(cmd))
        allowed = set(spec.defaults) | _GENERIC_KEYS
        stray = sorted(set(data[cmd]) - allowed)
        ok(f"{cmd} 小节无未登记键（无拼写漂移）",
           not stray, f"多余键={stray}，规格允许={sorted(allowed)}")

    # ---- 3. detect 必须显式标注非必要 ----
    # 注释不参与 YAML 解析，直接查原文；detect 小节之前的那段注释块里
    # 必须出现「非必要」字样。
    lines = raw.splitlines()
    # 定位 detect 小节的行号
    detect_at = next(
        (i for i, ln in enumerate(lines) if ln.strip().startswith("detect:")), -1
    )
    ok("模板能找到 detect 小节行", detect_at >= 0, f"行号={detect_at}")
    # 往上回溯注释块（遇到空行或非注释即停）
    banner: list[str] = []
    for ln in reversed(lines[:detect_at]):
        stripped = ln.strip()
        if not stripped:
            break
        if not stripped.startswith("#"):
            break
        banner.insert(0, stripped)
    banner_text = "\n".join(banner)
    ok("detect 小节上方有说明注释块", bool(banner), f"回溯到 {len(banner)} 行")
    ok("detect 被显式标注为「非必要」",
       "非必要" in banner_text, f"注释块=\n{banner_text}")
    ok("注释块说明了 crop/cropremove 已含检测",
       "cropremove" in banner_text and "crop" in banner_text, banner_text)
    ok("文件头部命令清单也标注了 detect 非必要",
       "detect" in raw.split("extract:", 1)[0] and "非必要" in raw.split("extract:", 1)[0],
       "头部清单未标注 detect")

    # ---- 4. 模板取值能直接驱动命令（除路径外全部可校验）----
    # input 指向 ./sample/，仓库里不一定存在，这里替换成真实临时目录。
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="guji_cfg_tpl_"))
    try:
        for cmd in _REQUIRED_SECTIONS:
            block = dict(data[cmd])
            block["input"] = str(work)  # 换成真实存在的目录
            args = CommandArgs(command=cmd, **block)
            args.validate()  # 不抛即通过
            # 注意：CommandArgs 会把 input 标准化为绝对路径（.resolve()），
            # 因此比较的是 resolve 后的结果，不是原始字符串。
            ok(f"{cmd} 模板取值可构造 CommandArgs 并通过校验",
               args.get("input") == work.resolve(), str(args.get("input")))

        # detect 的模板必须开 save=true —— 否则 `guji run detect` 会被 CLI
        # 空跑拦截直接拒绝，用户照着模板抄却跑不起来（模板存在的意义就是落地标注图）。
        detect_args = CommandArgs(command="detect", **{**data["detect"], "input": str(work)})
        ok("detect 模板 save=true（该块存在就是为了落地标注图）",
           detect_args.get("save") is True, str(detect_args.get("save")))
        ok("detect 模板默认 ext=png",
           detect_args.get("ext") == "png", str(detect_args.get("ext")))

        # 用模板参数构造真实功能实例，确认会算出输出目录（与输入并列）
        from functions.detect import DetectFunction

        func = DetectFunction(detect_args)
        ok("按模板构造 detect 时有输出目录（与输入目录并列）",
           func.outpath == work.parent / "detect", str(func.outpath))

        # 模板不得让用户掉进「空跑被拒」的坑：用 CLI 的同一判据验一遍
        from cli.cli import _reject_dry_run

        import contextlib as _ctx
        import io as _io

        _buf = _io.StringIO()
        with _ctx.redirect_stdout(_buf):
            rejected = _reject_dry_run("detect", detect_args)
        ok("模板的 detect 参数能通过 CLI 空跑检查", rejected is False, _buf.getvalue())

        # 反向守卫：若有人把模板改回 save=false，run detect 会被拒——
        # 这里显式钉住这条因果关系，改动时能立刻发现
        _dry = CommandArgs(command="detect", **{**data["detect"], "input": str(work), "save": False})
        _buf2 = _io.StringIO()
        with _ctx.redirect_stdout(_buf2):
            _dry_rejected = _reject_dry_run("detect", _dry)
        ok("（对照）save=false 时确实会被拒绝，证明上面的放行断言有效",
           _dry_rejected is True, "判据失效，前一条断言形同虚设")
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)

    # ---- 5. run 子命令可选值覆盖所有已登记命令 ----
    from cli.cli_args import CliArgsParser

    parser = CliArgsParser().parser
    run_parser = next(
        (
            choice
            for action in parser._subparsers._group_actions
            if getattr(action, "choices", None)
            for name, choice in action.choices.items()
            if name == "run"
        ),
        None,
    )
    ok("CLI 已注册 run 子命令", run_parser is not None, "未找到 run 子命令")
    pos = [a for a in run_parser._actions if a.dest == "subcommand"]
    ok("run 已声明 subcommand 位置参数", bool(pos), "未找到 subcommand 参数")
    run_vals = set(pos[0].choices) if pos else set()
    missing = sorted(set(COMMAND_SPECS) - run_vals)
    ok("run 的 subcommand 覆盖全部已登记命令",
       not missing, f"缺失={missing}；run 可选={sorted(run_vals)}")

    # ---- 6. 用户文档不得漏掉任何已登记命令 ----
    # 背景：detect 变成真实命令后，README 的功能一览表、docs/README.md 的命令
    # 一览表、docs/functions/overview.md 的模块清单都还停在旧状态，文档里查不到
    # 这个命令。这类漂移靠人工审阅很容易漏，因此用「命令名必须出现在索引型文档里」
    # 这条机械规则守住；细节文案仍由人写。
    doc_files = {
        "README.md": root / "README.md",
        "docs/README.md": root / "docs" / "README.md",
        "docs/guide/cli.md": root / "docs" / "guide" / "cli.md",
        "docs/functions/overview.md": root / "docs" / "functions" / "overview.md",
    }
    for label, path in doc_files.items():
        ok(f"{label} 存在", path.exists(), str(path))
        text = path.read_text(encoding="utf-8")
        absent = sorted(cmd for cmd in COMMAND_SPECS if cmd not in text)
        ok(f"{label} 覆盖全部命令（无漏记）",
           not absent, f"未提及={absent}")

    # ---- 7. detect 的「非必要」定位必须在文档里说明 ----
    for label, path in doc_files.items():
        text = path.read_text(encoding="utf-8")
        ok(f"{label} 说明 detect 是非必要步骤",
           "非必要" in text, f"{label} 未标注 detect 非必要")

    # ---- 8. 文档里列出的 CLI 参数必须真实存在 ----
    # 只校验**参数表格里的行首参数名**（形如 `| `--zoom` | 1 | ...`），
    # 不扫正文——正文里会有「rembg 没有 `--ext` 参数」这类正常提及。
    import re as _re

    docs_text = (root / "docs" / "guide" / "cli.md").read_text(encoding="utf-8")
    for cmd_name, sp in subs_map(parser).items():
        if cmd_name not in COMMAND_SPECS:
            continue
        real = {
            o.lstrip("-")
            for a in sp._actions
            for o in a.option_strings
            if o.startswith("--")
        }
        section = _extract_section(docs_text, cmd_name)
        if section is None:
            ok(f"docs/guide/cli.md 有 {cmd_name} 参数小节", False, "未找到小节标题")
            continue
        # 只认表格行的第一个单元格里被反引号包住的 `--xxx`
        mentioned = set(
            _re.findall(r"^\|\s*`--([a-z][a-z0-9-]*)`", section, _re.MULTILINE)
        )
        bogus = sorted(m for m in mentioned if m not in real)
        ok(f"docs/guide/cli.md 中 {cmd_name} 的参数都存在",
           not bogus, f"文档写了但代码没有={bogus}；实际={sorted(real)}")

    # ---- 9. 模板各段的默认值必须与 CLI 逐值相等 ----
    #
    # 背景：本模块原来只校验**键名**存在，于是 yaml 写 18、CLI 已是 20 这种
    # **数值漂移**照样全绿——三层默认值（CLI / desktop / guji.yaml）就此悄悄
    # 分叉。这里改成按值比对，覆盖全部命令段。
    #
    # 用户原则：「CLI 与 desktop 原则上保持一致，因步骤或界面不同会有稍微
    # 差异」。模板同理——它有两处**登记在案**的例外，不能一刀切：
    #   - `_INTENTIONAL`：模板是给用户照抄的「已开启」样例，个别键刻意与
    #     CLI 的空表单不同（改它请先改这里并写明理由）；
    #   - `_OPTIONAL`：运行时才填的键，模板里不该出现。
    from core.command_spec import COMMAND_SPECS, normalize_margin

    _INTENTIONAL = {
        ("detect", "save"):
            "模板存在的意义就是落地标注图；save=false 会被 CLI 空跑拦截直接拒绝",
        ("print", "pdf_name"):
            "演示用的输出文件名；CLI 默认 None（自动按书名取）",
        ("print", "title_printing"):
            "模板是「已开启」样例；CLI 默认空表单",
        ("print", "title_text"):
            "示例书名；CLI 默认空",
        ("print", "title_switch_nodes"):
            "演示章节切换节点；CLI 默认无",
        ("print", "page_number_printing"):
            "模板是「已开启」样例；CLI 默认空表单",
    }
    _OPTIONAL = {
        ("print", "files"): "页序清单，运行时由程序作为 args['files'] 填入",
    }
    #: 不参与数值比对的通用键：input/output 是路径占位，
    #: workers 的 CLI 默认 = CPU 核数（机器相关，模板写示例数字即可）。
    _SKIP_VALUE_CHECK = {"input", "output", "workers"}
    #: clean 由 core/args.py 兜底，默认 False；模板若写 true，用户照抄就会
    #: 默认清空输出目录——这属于危险漂移，必须钉住。
    _CLEAN_DEFAULT = False

    for cmd in _REQUIRED_SECTIONS:
        block = data[cmd]
        pairs = list(COMMAND_SPECS[cmd].defaults.items()) + [("clean", _CLEAN_DEFAULT)]
        for key, want in pairs:
            if key in _SKIP_VALUE_CHECK:
                continue
            if (cmd, key) in _OPTIONAL:
                continue
            present = key in block
            ok(f"模板 {cmd} 段显式给出 {key}",
               present, f"缺失；现有键={sorted(block)}")
            if not present:
                continue
            got = block[key]
            # margins 在模板里可能是 "20,10" 这类简写，标准化后再比
            if key.endswith("margins"):
                got = normalize_margin(got, default=None)
                want = normalize_margin(want, default=None)
            if got == want:
                continue
            reason = _INTENTIONAL.get((cmd, key))
            ok(f"模板 {cmd}.{key} 与 CLI 默认值一致",
               reason is not None,
               f"模板={got}；CLI 默认={want}"
               + ("" if reason is None else f"（登记为故意差异：{reason}）"))
