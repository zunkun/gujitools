# -*- coding: utf-8 -*-
"""构建 / 安装的职责边界 + PATH 注册位置守卫。

背景（用户明确要求，2026-09-19）：`build.py` 曾经在打包后把 `dist/guji`
复制到 `C:\\Software\\guji` 当作"部署"，安装包的默认目录也一度是
`{sd}\\Software\\guji`（= `C:\\Software\\guji`），用户 PATH 里注册的就是那个
`{app}`。后果：本机同时躺着 dist / 部署副本 / 安装目录好几份 650MB 的东西，
排障时"跑的是哪一份"说不清；而 `C:\\Software` 还是个装着别家工具的公共目录。

定下来的分工：

| 环节             | 职责                                              |
| ---------------- | ------------------------------------------------- |
| `build.py`       | **只产出** `dist/`（可执行目录 + 安装包），不部署  |
| `guji_setup.iss` | 装到哪 + 把**实际安装目录**注册进用户 PATH         |

本模块把这些钉死：谁把"复制到 C:\\Software"加回 build.py、谁把安装目录写死、
谁让 PATH 不跟着安装目录走、谁忘了清历史旧条目，这里就红。
"""

NAME = "installer_paths"
DEPENDS: list[str] = []
TITLE = "构建只出安装包 + 安装目录与 PATH 注册同源"

#: 安装包应当使用的安装目录（= %LOCALAPPDATA%\Programs\guji）
EXPECTED_DIR = r"{localappdata}\Programs\guji"

#: 历史默认目录；升级/卸载时必须从 PATH 里清掉，否则留下指向不存在目录的死路径
LEGACY_DIRS = (
    r"{localappdata}\Software\guji",
    r"{sd}\Software\guji",
)


def _blank_docstrings(text: str) -> str:
    """把模块 docstring 的**内容**抹成空行（保留行号，便于报错定位）。"""
    import re

    def _replace(match):
        return "\n" * match.group(0).count("\n")

    return re.sub(r'""".*?"""', _replace, text, count=1, flags=re.S)


def run(ctx) -> None:
    import re
    from pathlib import Path

    from tests.selftests._context import ok

    import build

    root = Path(__file__).resolve().parents[2]
    build_src = (root / "build.py").read_text(encoding="utf-8")
    iss = (root / "guji_setup.iss").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    # ---- 1. 构建脚本不再负责部署（只出 dist/ 与安装包）----
    ok("build.py：部署函数 copy_to_software / clean_old_backups 已删除",
       not hasattr(build, "copy_to_software")
       and not hasattr(build, "clean_old_backups"),
       "build.py 里还有部署函数")

    # 只看“功能代码行”：注释里解释历史是允许的（docstring 先抹掉且保留行号）
    func_lines = [
        (number, line)
        for number, line in enumerate(_blank_docstrings(build_src).splitlines(), 1)
        if not line.strip().startswith("#")
    ]
    offenders = [
        f"build.py:{number}" for number, line in func_lines if "Software" in line
    ]
    ok("build.py：功能代码里不再出现 C:\\Software 部署路径（仅注释可解释历史）",
       not offenders, "; ".join(offenders))

    copy_steps = [
        f"build.py:{number}" for number, line in func_lines if "复制到" in line
    ]
    ok("build.py：构建步骤里没有「复制到 …」这一步",
       not copy_steps, "; ".join(copy_steps))
    ok("build.py：不再复制产物目录（shutil.copytree 已无引用）",
       "copytree" not in build_src)

    # ---- 2. 安装目录：用户级 Programs，不再进 Software ----
    match = re.search(r"^DefaultDirName=(.+)$", iss, re.M)
    ok("guji_setup.iss：有 DefaultDirName", match is not None)
    dir_value = match.group(1).strip() if match else ""
    ok(f"guji_setup.iss：安装目录 = {EXPECTED_DIR}", dir_value == EXPECTED_DIR, dir_value)
    ok("guji_setup.iss：不再装到 Software 目录下",
       "Software" not in dir_value, dir_value)
    ok("guji_setup.iss：UsePreviousAppDir=no（否则老用户被粘在旧目录里）",
       any(line.strip() == "UsePreviousAppDir=no" for line in iss.splitlines()),
       "升级会沿用上次的安装目录，迁不出旧的 Software\\guji")

    # ---- 3. PATH 注册必须跟着安装目录走 ----
    app_hits = iss.count("ExpandConstant('{app}')")
    ok("guji_setup.iss：PATH 注册用的是 {app}（实际安装目录）",
       app_hits >= 3, f"只出现 {app_hits} 处")
    ok("guji_setup.iss：没有把绝对路径写进 PATH（不允许出现 'C:\\ 字面量）",
       "'C:\\" not in iss, "安装脚本里写死了绝对路径")

    step_block = re.search(r"procedure CurStepChanged.*?end;", iss, re.S)
    step_body = step_block.group(0) if step_block else ""
    ok("guji_setup.iss：安装时先清历史条目、再加 {app}（顺序不能反）",
       "RemoveLegacyPathEntries;" in step_body
       and "AddToUserPath;" in step_body
       and step_body.index("RemoveLegacyPathEntries;") < step_body.index("AddToUserPath;"),
       step_body.strip())

    # ---- 4. 历史遗留的旧目录条目确实被清 ----
    for legacy in LEGACY_DIRS:
        ok(f"guji_setup.iss：清理历史 PATH 条目 {legacy}",
           legacy in iss, "历史条目不清，PATH 里会留下死路径")
    ok("guji_setup.iss：卸载时也清历史条目",
       "RemoveLegacyPathEntries;" in
       (re.search(r"procedure CurUninstallStepChanged.*?end;", iss, re.S) or
        re.match(r"$", "")).group(0))

    # ---- 5. Inno 的 { } 注释不能嵌套 {}：注释在第一个 } 就闭合 ----
    # （真踩过：注释里写 {app} 会让后半句变成代码 → 编译报错）
    brace_bugs = []
    for number, line in enumerate(iss.splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        if "{" in stripped[1:].split("}", 1)[0]:
            brace_bugs.append(f"guji_setup.iss:{number}")
    ok("guji_setup.iss：{ } 注释里没有嵌套的 {（会提前闭合注释）",
       not brace_bugs, "; ".join(brace_bugs))

    # ---- 5b. [Code] 里不许有以 # 开头的**续行** ----
    # （真踩过：`#13#10` 换行写在行首，ISPP 把它当预处理指令，
    #   报 "Unknown preprocessor directive on line N" 直接中断编译）
    # ⚠️ 定位 [Code] 必须用「行首匹配」：注释里也会提到 `[Code]` 这三个字，
    # 用 partition 会切错位置（本用例第一版就这么误报过）。
    code_head = re.search(r"^\[Code\]", iss, re.M)
    ok("guji_setup.iss：存在 [Code] 段", code_head is not None)
    code_first_line = iss[: code_head.start()].count("\n") + 1 if code_head else 0
    code_section = iss[code_head.end():] if code_head else ""
    hash_lines = [
        f"guji_setup.iss:{code_first_line + index}"
        for index, line in enumerate(code_section.splitlines(), 1)
        if line.strip().startswith("#")
    ]
    ok("guji_setup.iss：[Code] 里没有行首 # 的续行（ISPP 会当预处理指令）",
       not hash_lines, "; ".join(hash_lines))

    # ---- 6. 安装完成提示：短句多行，不写用户不关心的东西 ----
    # （用户 2026-09-23：弹窗里一行太长读不动；"安装目录"这种用户不关心，别写）
    finish = re.search(r"procedure RefreshEnvironment;(.*?)\nend;", iss, re.S)
    ok("guji_setup.iss：存在 RefreshEnvironment（安装完成提示）", finish is not None)
    body = finish.group(1) if finish else ""
    # ExpandConstant 的参数不是提示文案；`{ }` 注释（不许嵌套，见下面第 5 节）
    # 是写给维护者看的，也不算文案 —— 都剥掉再统计
    prose = re.sub(r"ExpandConstant\('[^']*'\)", "", body)
    prose = re.sub(r"\{[^{}]*\}", "", prose)
    ok("guji_setup.iss：完成提示不写安装目录（用户不关心装在哪）",
       "安装目录" not in prose, prose[:120])

    # 路径变量必须独占一行：路径又长又断不开，混进句子里就是"一行太长"的根源
    path_uses = len(re.findall(r"\b(?:AppDir|OldDir)\b\s*\+\s*(?:#13#10\s*\+)?", prose))
    path_alone = len([ln for ln in prose.splitlines()
                      if re.match(r"^\s*(?:AppDir|OldDir)\s*\+", ln)])
    ok("guji_setup.iss：提示里的路径变量独占一行（不与文案混排）",
       path_uses == path_alone and path_uses >= 1,
       f"{path_uses} 处里只有 {path_alone} 处独占一行")

    # 还原实际显示的行：`'A' + #13#10 + 'B' + 'C'` 里，被 #13#10 隔开的是两行，
    # 同一块里的字面量是**同一行**的续接
    def _width(text: str) -> int:
        import unicodedata

        return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1
                   for ch in text)

    shown = []
    for chunk in prose.split("#13#10"):
        text = "".join(re.findall(r"'([^']*)'", chunk))
        if text:
            shown.append(text)
    ok("guji_setup.iss：完成提示确实拆出了多行（别因为解析错了而假绿）",
       len(shown) >= 4, f"{len(shown)} 行：{shown[:2]}…")
    too_long = [(t, _width(t)) for t in shown if _width(t) > 56]
    ok("guji_setup.iss：完成提示每行不超过 56 个显示列（MsgBox 不给中文断行）",
       not too_long, "; ".join(f"「{t}」={w} 列" for t, w in too_long))

    # ---- 7. 用户文档与实现同源 ----
    ok("README：写清了安装目录（用户级 Programs，不装 Software）",
       EXPECTED_DIR in readme)
    ok("README：写明构建只产出安装包、不做部署",
       "构建只产出" in readme, "README 没写清构建只出安装包")
