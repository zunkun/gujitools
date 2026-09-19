# -*- coding: utf-8 -*-
"""可执行文件命名的**跨文件一致性**守卫。

背景（真实踩过）：把 GUI 产物从 `guji-gui.exe` 批量改名成 `guji-desktop.exe`
时，`build.py` / `guji_setup.iss` / `README.md` / `tools/smoke_frozen.py` 都改了，
**唯独漏掉 `guji.spec` 的 `name='guji-gui'`**——而 spec 才是产物名的真正来源。
后果不是报错，而是：

- PyInstaller 照样"构建成功"，dist 里躺着的却是 `guji-gui.exe`；
- `build.py` 的 `verify_outputs` 报"缺少 guji-desktop.exe"；
- 安装包的快捷方式指向一个不存在的文件。

产物名分散在四处（构建脚本常量、spec、安装脚本、冒烟脚本），靠人记必然漏。
本模块把它们钉在一起：改一处不改其它，这里就红。
"""

NAME = "exe_names"
DEPENDS: list[str] = []
TITLE = "可执行文件命名四处一致"

#: 改名前的旧名。除「安装脚本清理旧文件」那一行外，任何地方都不该再出现。
LEGACY = "guji-gui"

#: 必须与产物名保持同步的文件（相对仓库根）
SYNCED_FILES = (
    "build.py",
    "guji.spec",
    "guji_setup.iss",
    "tools/smoke_frozen.py",
    "README.md",
)


def run(ctx) -> None:
    import re
    from pathlib import Path

    from tests.selftests._context import ok

    import build

    root = Path(__file__).resolve().parents[2]
    texts = {
        name: (root / name).read_text(encoding="utf-8") for name in SYNCED_FILES
    }

    # ---- 1. build.py 的平台常量自洽 ----
    ok("build.py：Windows 的产物名带 .exe",
       build.CLI_EXE.endswith(".exe") and build.GUI_EXE.endswith(".exe"),
       f"{build.CLI_EXE} / {build.GUI_EXE}")
    ok("build.py：GUI 产物名已更名为 guji-desktop",
       build.GUI_EXE.startswith("guji-desktop"), build.GUI_EXE)

    spec_names = set(re.findall(r"name='([^']+)'", texts["guji.spec"]))
    expected = {"guji", build.GUI_EXE.removesuffix(".exe")}
    ok("guji.spec：两个 EXE + COLLECT 的 name 与 build.py 完全一致",
       spec_names == expected, f"spec={sorted(spec_names)} 期望={sorted(expected)}")

    # ---- 2. 安装包必须指向同一个 GUI 产物 ----
    iss = texts["guji_setup.iss"]
    gui_target = "{app}\\" + build.GUI_EXE
    # 指向「程序本体」的三处：卸载图标 + 开始菜单 + 桌面快捷方式
    # （开始菜单里另有一条卸载入口，Filename 是 {uninstallexe}，不算）
    app_lines = [
        line for line in iss.splitlines()
        if line.strip().startswith("UninstallDisplayIcon")
        or ("Filename:" in line and "{uninstallexe}" not in line)
    ]
    ok("guji_setup.iss：指向程序本体的快捷方式/卸载图标共 3 处",
       len(app_lines) == 3, f"{len(app_lines)} 处")
    ok("guji_setup.iss：这 3 处全部指向新 GUI 产物",
       all(gui_target in line for line in app_lines),
       "; ".join(line for line in app_lines if gui_target not in line))
    ok("guji_setup.iss：开始菜单里保留了卸载入口",
       any("{uninstallexe}" in line for line in iss.splitlines()
           if "Filename:" in line))

    legacy_iss_lines = [
        line.strip() for line in iss.splitlines() if LEGACY in line
    ]
    cleanup_prefix = 'Type: files; Name: "{app}\\' + LEGACY + '.exe"'

    def _legacy_allowed(line: str) -> bool:
        """注释里解释改名来龙去脉是允许的；功能行只允许那条 InstallDelete。"""
        return line.startswith(";") or line.startswith(cleanup_prefix)

    ok("guji_setup.iss：旧名只出现在注释与「升级时删掉旧 EXE」那一行",
       all(_legacy_allowed(line) for line in legacy_iss_lines),
       "; ".join(line for line in legacy_iss_lines if not _legacy_allowed(line)))
    ok("guji_setup.iss：确实保留着删掉旧 EXE 的那一行（否则旧版升级会留残留）",
       any(line.startswith(cleanup_prefix) for line in legacy_iss_lines),
       "; ".join(legacy_iss_lines))

    # ---- 3. 冒烟脚本校验的路径同名 ----
    ok("tools/smoke_frozen.py：校验的是新名",
       f'dist / "{build.GUI_EXE}"' in texts["tools/smoke_frozen.py"],
       "smoke_frozen 里找不到新产物名")

    # ---- 4. 用户文档里的名要对得上 ----
    ok("README.md：产物表列出的是新名",
       f"dist/guji/{build.GUI_EXE}" in texts["README.md"])
    ok("README.md：worker 子进程说明用的是新名",
       f"{build.GUI_EXE} --worker" in texts["README.md"])

    # ---- 5. 旧名不许在功能位置残留 ----
    offenders = []
    for name in ("build.py", "guji.spec", "tools/smoke_frozen.py", "README.md"):
        for number, line in enumerate(texts[name].splitlines(), 1):
            if LEGACY in line:
                offenders.append(f"{name}:{number}")
    ok("旧名 guji-gui 已从 build.py / guji.spec / smoke_frozen / README 清干净",
       not offenders, "; ".join(offenders))

    # ---- 6. 用户手册（docs/guide）里也不许出现旧名 ----
    guide_hits = [
        f"{path.relative_to(root)}:{number}"
        for path in (root / "docs" / "guide").rglob("*.md")
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        )
        if LEGACY in line
    ]
    ok("docs/guide/*.md 里没有旧产物名", not guide_hits, "; ".join(guide_hits))
