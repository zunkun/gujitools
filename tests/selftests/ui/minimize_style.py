# -*- coding: utf-8 -*-
"""无边框主窗口的原生最小化样式自测（用户 2026-11-18 报障）。

背景：``FramelessMainWindow``（``Qt.FramelessWindowHint`` → Win32
``WS_POPUP``）缺 ``WS_MINIMIZEBOX``，最小化退化为"左下角老式瓦片"且任务栏
没有按钮。修复：``desktop/ui/native_minimize.py::enable_native_minimize``
在构造后补回 ``WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_SYSMENU``。

守住四条不变量：

1. **Win32 常量抄对**：样式位数值与 winuser.h 一致（手抄错了就是静默改样式）；
2. **真窗口真生效**：默认（windows）平台下，构造后窗口的原生样式确实带
   这三个样式位，且函数幂等（二次调用不炸不变样）；
3. **离屏/假句柄优雅降级**：offscreen 平台拿到的 winId 不是真 HWND，函数
   必须**不抛异常**地返回 False，绝不打断启动；
4. **接线**：``desktop/app.py::MainWindow.__init__`` 必须真的调了它。
"""

NAME = "minimize_style"
DEPENDS: list[str] = []
TITLE = "无边框窗口原生最小化样式（左下角残留/任务栏无按钮修复）"


def run(ctx) -> None:
    import ctypes
    import os
    import sys as _sys
    from pathlib import Path
    from unittest.mock import patch

    from tests.selftests._context import ok

    import desktop.ui.native_minimize as nm

    # ---- 1. Win32 常量与 winuser.h 一致 ----
    ok("常量：WS_MAXIMIZEBOX = 0x10000", nm.WS_MAXIMIZEBOX == 0x0001_0000,
       hex(nm.WS_MAXIMIZEBOX))
    ok("常量：WS_MINIMIZEBOX = 0x20000", nm.WS_MINIMIZEBOX == 0x0002_0000,
       hex(nm.WS_MINIMIZEBOX))
    ok("常量：WS_SYSMENU = 0x80000", nm.WS_SYSMENU == 0x0008_0000,
       hex(nm.WS_SYSMENU))
    ok("常量：GWL_STYLE = -16", nm.GWL_STYLE == -16)
    ok("常量：SWP_FRAMECHANGED = 0x20", nm.SWP_FRAMECHANGED == 0x0020)
    ok("常量：GWL_EXSTYLE = -20", nm.GWL_EXSTYLE == -20)
    ok("常量：WS_EX_APPWINDOW = 0x40000", nm.WS_EX_APPWINDOW == 0x0004_0000)

    # ---- 2. 取函数对：Windows 给真函数；非 Windows 返回 (None, None) ----
    if _sys.platform == "win32":
        get_fn, set_fn = nm._long_style_fns()
        ok("取函数：Windows 返回可调用对",
           callable(get_fn) and callable(set_fn))
        ok("取函数：返回值宽度是指针宽（c_ssize_t，64 位不截断）",
           get_fn.restype is ctypes.c_ssize_t
           and set_fn.argtypes == [ctypes.c_ssize_t, ctypes.c_int,
                                   ctypes.c_ssize_t])
    with patch.object(nm, "sys") as shim:
        shim.platform = "linux"
        ok("取函数：非 Windows 返回 (None, None)",
           nm._long_style_fns() == (None, None))

    # ---- 3. 主窗口构造后样式位已补上（平台自适应） ----
    from PySide6.QtGui import QGuiApplication

    window = ctx.w
    platform = QGuiApplication.platformName()
    if platform == "windows":
        # 真平台：构造链路里 enable_native_minimize 已经跑过，直接读样式验证
        user32 = ctypes.windll.user32
        hwnd = int(window.winId())
        get_fn, _ = nm._long_style_fns()
        style = get_fn(hwnd, nm.GWL_STYLE)
        want = nm.WS_MINIMIZEBOX | nm.WS_MAXIMIZEBOX | nm.WS_SYSMENU
        ok("真平台：主窗口原生样式带 WS_MINIMIZEBOX（最小化动画+任务栏按钮）",
           bool(style & nm.WS_MINIMIZEBOX), f"style={style:#x}")
        ok("真平台：主窗口原生样式带 WS_MAXIMIZEBOX（Win11 Snap Layout）",
           bool(style & nm.WS_MAXIMIZEBOX), f"style={style:#x}")
        ok("真平台：主窗口原生样式带 WS_SYSMENU（MSDN 要求与 MINIMIZEBOX 同给）",
           bool(style & nm.WS_SYSMENU), f"style={style:#x}")
        # 幂等：再调一次不变样、不炸
        before = style
        ok("真平台：二次调用幂等",
           nm.enable_native_minimize(window) is True
           and get_fn(hwnd, nm.GWL_STYLE) == before)
    else:
        # 离屏自测：winId 不是真 HWND，必须优雅返回 False、绝不抛异常
        ok("离屏：enable_native_minimize 优雅返回 False（不抛异常）",
           nm.enable_native_minimize(window) is False,
           f"platform={platform}")
        ok("离屏：假句柄（winId 命中容错分支）也不会写坏样式",
           isinstance(nm.enable_native_minimize(window), bool))
        ok("离屏：enable_taskbar_button 优雅返回 False（不抛异常）",
           nm.enable_taskbar_button(window) is False,
           f"platform={platform}")

    # ---- 3.5 子窗口任务栏按钮（WS_EX_APPWINDOW）接线守卫 ----
    # 图片预览 / 图片编辑 / 聚合任务预览 / 拼版选图四个"真窗口"必须在
    # setWindowFlags 之后调 enable_taskbar_button（否则样式位随原生窗口
    # 重建而丢）。
    root = Path(__file__).resolve().parents[3]
    wiring = [
        ("components/viewers/image_zoom_dialog/dialog.py",
         "enable_taskbar_button(self)"),
        ("components/viewers/image_editor/dialog.py",
         "enable_taskbar_button(self)"),
        ("pages/taskdetail/preview.py", "enable_taskbar_button(self)"),
        ("components/imposition/picker.py", "enable_taskbar_button(self)"),
    ]
    for rel, call in wiring:
        src = (root / "desktop" / rel).read_text(encoding="utf-8")
        ok(f"接线：{rel} 调用了 enable_taskbar_button", call in src)
        if rel.endswith("picker.py"):
            ok("接线：选图窗在恢复最大化样式之后补任务栏位",
               src.index("_restore_maximize_style()") < src.index(call))
        else:
            ok(f"接线：{rel} 调用点在 setWindowFlags 之后",
               src.rindex("setWindowFlags(") < src.index(call))

    # ---- 3.6 A/B 开关：GUJI_NO_TASKBAR_BUTTON 整层关掉任务栏位 ----
    # 崩溃排查用（2026-11-22）：关掉后这四个弹窗回到 owned window 形态，
    # 用来验证「WS_EX_APPWINDOW 扩大 WM_NCHITTEST 暴露面」这个假设。
    # 关键是置位时必须**连句柄都不碰**（否则只是晚一步设置样式，A/B 无效）。
    class _Probe:
        touched = False

        def winId(self):  # noqa: N802 - 模拟 QWidget 接口
            _Probe.touched = True
            return 0

    os.environ[nm.TASKBAR_BUTTON_ENV] = "1"
    try:
        ok("A/B 开关：置位时直接返回 False，且不碰窗口句柄",
           nm.enable_taskbar_button(_Probe()) is False and not _Probe.touched)
    finally:
        os.environ.pop(nm.TASKBAR_BUTTON_ENV, None)
    ok("A/B 开关：默认不生效（还原后仍走原路径）",
       nm.enable_taskbar_button(_Probe()) is False and _Probe.touched)

    # ---- 4. 接线守卫：入口必须真的调了修复 ----
    entry = (root / "desktop" / "app.py").read_text(encoding="utf-8")
    ok("接线：desktop/app.py 导入了 enable_native_minimize",
       "from desktop.ui.native_minimize import enable_native_minimize" in entry)
    ok("接线：MainWindow.__init__ 里调用了 enable_native_minimize(self)",
       "enable_native_minimize(self)" in entry)
    ok("接线：调用点在 install_title_bar 之后（原生窗口已随 _initFrameless 建立）",
       entry.index("install_title_bar(self)")
       < entry.index("enable_native_minimize(self)"))
