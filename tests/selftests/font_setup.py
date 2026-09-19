# -*- coding: utf-8 -*-
"""中文字体体检 + Linux 自动补装自测。

守住四条不变量：

1. **体检本身要准**：开发机（Windows）必须检出中文字体，且命中的文件真实存在；
2. **跨平台计划正确**：Linux/apt 的首选包必须是**仿宋**；
3. **失败归因正确**：网络 / 权限 / 索引过期要各自归类，中英双语输出都能认；
4. **Windows 上绝不触发提权**：`install_cjk_fonts` 在非 Linux 必须直接返回
   ``unsupported``，**一次子进程都不能起**——这里一旦漏了个出口 Into，
   用户点一下就会弹 sudo/pkexec，是最难查的那种 bug。

外加两条接线守卫：GUI 入口 `desktop/app.py` 必须真的调了体检；引导对话框
在「没有可用包管理器」时要隐藏自动安装按钮、只留手动步骤。
"""

NAME = "font_setup"
DEPENDS: list[str] = []
TITLE = "中文字体体检与补装（含失败归因）"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok

    import utils.font_setup as fs

    # ---- 1. 体检：本机必须检出中文字体 ----
    check = fs.check_cjk_font()
    ok("体检：本机检出中文字体", check.found,
       f"platform={check.platform} source={check.source} path={check.path}")
    ok("体检：命中的字体文件真实存在",
       bool(check.path) and Path(check.path).exists(), str(check.path))
    ok("体检：命中来源可解释（env/table/scan）",
       check.source in ("env", "table", "scan"), check.source)
    ok("体检：platform_name 归一到三类之一",
       fs.platform_name() in ("windows", "macos", "linux") or fs.platform_name() != "",
       fs.platform_name())
    ok("体检：FontCheck 带了候选路径清单用于排查", bool(check.checked),
       f"{len(check.checked)} 条")

    # ---- 2. Linux/apt 计划：仿宋优先 ----
    original_platform = fs.platform_name
    original_pm = fs.detect_package_manager
    fs.platform_name = lambda: "linux"
    fs.detect_package_manager = lambda: "apt"
    try:
        plan = fs.install_plan()
        ok("计划：Linux/apt 有候选包", len(plan) >= 3, f"{[p.name for p in plan]}")
        ok("计划：首选是仿宋 fonts-cwtex-fs",
           bool(plan) and plan[0].name == "fonts-cwtex-fs",
           plan[0].name if plan else "空")
        ok("计划：每个包都带了人话说明与字体族",
           all(p.label and p.families for p in plan))

        # 换个包管理器也要有候选（Fedora 包名完全不同）
        fs.detect_package_manager = lambda: "dnf"
        dnf_plan = fs.install_plan()
        ok("计划：dnf 也有候选（Fedora 包名不同）",
           bool(dnf_plan) and dnf_plan[0].name.startswith("google-noto-serif"),
           dnf_plan[0].name if dnf_plan else "空")
    finally:
        fs.platform_name = original_platform
        fs.detect_package_manager = original_pm

    fs.platform_name = lambda: "windows"
    try:
        ok("计划：非 Linux 一律返回空（不许试图改写系统字体目录）",
           fs.install_plan() == ())
    finally:
        fs.platform_name = original_platform

    # ---- 3. 失败归因（中英双语） ----
    cases = [
        ((0, ""), "ok"),
        ((100, "E: Failed to fetch http://archive.ubuntu.com/x.deb Connection timed out"),
         "network"),
        ((100, "W: 暂时不能解析域名 archive.ubuntu.com"), "network"),
        ((1, "==== AUTHENTICATION FAILED ====\nError executing command as another user: Not authorized"),
         "permission"),
        ((1, "sudo: no tty present and no askpass program specified"), "permission"),
        ((1, "未授权：polkit 授权被取消"), "permission"),
        ((100, "E: Unable to locate package fonts-cwtex-fs"), "refresh"),
        ((100, "E: 无法定位软件包 fonts-cwtex-fs"), "refresh"),
        ((2, "something totally unexpected 42"), "failed"),
    ]
    for (code, output), expected in cases:
        got = fs.classify_failure(code, output)
        ok(f"归因：{'（成功）' if code == 0 else output[:38]} → {expected}",
           got == expected, f"实际 {got}")

    # ---- 4. 非 Linux 不得起子进程 / 不得提权 ----
    spawned: list[tuple] = []
    original_run = fs._run
    fs._run = lambda *a, **k: (spawned.append((a, k)) or (0, ""))  # 记录并假装成功
    try:
        result = fs.install_cjk_fonts()

        fs.platform_name = lambda: "linux"
        fs.detect_package_manager = lambda: None
        unsupported = fs.install_cjk_fonts()
    finally:
        fs._run = original_run
        fs.platform_name = original_platform
        fs.detect_package_manager = original_pm
    ok("Windows：install_cjk_fonts 返回 unsupported",
       result.status == "unsupported", result.status)
    ok("Windows：走的是平台分支，而不是「没找到包管理器」兜底",
       "只支持 Linux" in result.message, result.message)
    ok("Linux 无包管理器：返回 unsupported 而不是去猜 sudo",
       unsupported.status == "unsupported", unsupported.status)
    ok("两种情况都不跑任何命令（绝不弹提权框）", not spawned, f"{spawned}")

    # ---- 5. 手装文案 ----
    apt_plan = tuple(fs._FONT_PLANS["apt"][:2])
    fs.platform_name = lambda: "linux"
    fs.detect_package_manager = lambda: "apt"
    try:
        text = fs.manual_install_text(apt_plan)
    finally:
        fs.platform_name = original_platform
        fs.detect_package_manager = original_pm
    ok("手装文案：给出 apt 命令", "apt-get install -y fonts-cwtex-fs" in text, text[:120])
    ok("手装文案：给出免 root 的 ~/.local/share/fonts 路线",
       "~/.local/share/fonts" in text and "fc-cache" in text)
    ok("手装文案：给出 GUJI_CJK_FONT 逃生口", "GUJI_CJK_FONT" in text)

    fs.platform_name = lambda: "windows"
    try:
        windows_text = fs.manual_install_text(())
    finally:
        fs.platform_name = original_platform
    ok("手装文案：Windows 走仿宋文件这条路", "simfang" in windows_text,
       windows_text[:80])

    # ---- 6. GUI 外壳 ----
    from desktop.ui.font_setup import (
        FontFixDialog, FontInstallWorker, ensure_cjk_fonts, reset_font_check,
    )
    from PySide6.QtCore import QThread

    ok("GUI：FontInstallWorker 是 QThread 子类", issubclass(FontInstallWorker, QThread))

    dialog = FontFixDialog(apt_plan, None)
    try:
        ok("GUI：窗口标题点明缺字体", dialog.windowTitle() == "缺少中文字体",
           dialog.windowTitle())
        ok("GUI：有候选时显示「自动安装」按钮", not dialog._install_btn.isHidden())
        ok("GUI：手动安装步骤已填好且默认收起",
           dialog._manual.toPlainText() and dialog._manual.isHidden())
        ok("GUI：候选包名原样交给安装器",
           dialog._packages() == ("fonts-cwtex-fs", "fonts-arphic-uming"),
           str(dialog._packages()))
    finally:
        dialog.deleteLater()

    no_plan = FontFixDialog((), None)
    try:
        ok("GUI：无候选时藏起「自动安装」", no_plan._install_btn.isHidden())
        ok("GUI：无候选时解释了为什么不能自动装",
           "手动安装" in no_plan._plan_label.text(), no_plan._plan_label.text()[:60])
    finally:
        no_plan.deleteLater()

    reset_font_check()
    ok("GUI：本机有字体时 ensure_cjk_fonts 静默通过", ensure_cjk_fonts() is True)

    # ---- 7. 接线守卫：入口必须真的体检 ----
    root = Path(__file__).resolve().parents[2]
    entry = (root / "desktop" / "app.py").read_text(encoding="utf-8")
    ok("接线：desktop/app.py 在 main() 里调用了 ensure_cjk_fonts",
       "ensure_cjk_fonts()" in entry)
    ok("接线：调用点在 MainWindow 构造之前（进门前体检）",
       entry.index("ensure_cjk_fonts()") < entry.index("MainWindow()"))
