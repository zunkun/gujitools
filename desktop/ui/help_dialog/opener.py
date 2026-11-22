# -*- coding: utf-8 -*-
"""把手册交给系统浏览器打开（自 ``desktop/ui/help_dialog.py`` 拆出）。"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from .document import generate_manual_html
from .paths import prefer_static_manual, static_manual_path

#: ``cmd /c start`` 用到的进程创建标志：不继承控制台、不进 Job，
#: 关掉主程序时不会把浏览器一起带走。
_NO_WINDOW_FLAGS = (
    getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
)


def _open_with_system(path: Path) -> bool:
    """把文件交给系统默认程序打开，成功返回 True。

    ⚠️ **Windows 上绝不能传 ``file:///...`` URI**（``webbrowser.open(path.as_uri())``
    就是那么干的）。实测（2026-09-19）：``ShellExecute`` 拿到 file:// URI 会走
    **file: 协议处理器**（``HKCR\\file`` → ``CLSID {00000303-...}``），那玩意儿在
    这台机器上没注册成功，``os.startfile`` 于是**卡死不返回**——手册按钮点下去，
    界面冻住、浏览器永远不出现，症状就是用户说的「点用户手册按钮不打开浏览器了」。
    同一台机器上传**原生路径**（``os.startfile(str(path))``）秒开 Edge：原生路径
    走的是**扩展名关联**（``.html`` → 默认浏览器），跟 file: 协议处理器无关。

    失败时逐级回退：原生路径 → Qt ``QDesktopServices``（返回 bool，不挂）→
    ``cmd /c start``（独立进程，挂也挂不到我们界面上）。**回退链里刻意不放
    ``webbrowser.open``**——它在 Windows 上就是 ``os.startfile``，既是最上面那条
    （会挂的），再放一遍没有意义；只有非 Windows 平台才用它。
    """
    if sys.platform == "win32":
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except OSError:
            pass  # 关联坏了/被策略拦了 → 继续回退

    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return True
    except Exception:
        pass  # 无 Qt / 无平台插件 → 继续回退

    if sys.platform == "win32":
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", str(path)],
                creationflags=_NO_WINDOW_FLAGS,
                close_fds=True,
            )
            return True
        except Exception:
            return False

    try:
        return bool(webbrowser.open(path.as_uri()))
    except Exception:
        return False


def _notify_open_failed(path: Path) -> None:
    """所有打开方式都失败时，把路径摆在用户面前（可选中复制），别让人干瞪眼。

    只在真有 QApplication 时弹（纯命令行/自测里调用不弹），弹不出来就算了——
    手册文件已经生成好了，路径也写在返回值和日志里。
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    if QApplication.instance() is None:
        return
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        "用户手册",
        "没能唤起系统浏览器，手册已经生成好了。\n"
        "可以复制下面的路径，手动粘到浏览器地址栏（或双击文件）打开：",
        QMessageBox.StandardButton.Ok,
    )
    # 标准按钮文字由系统语言决定（英文环境显示 "OK"），显式改成中文
    box.button(QMessageBox.StandardButton.Ok).setText("知道了")
    box.setInformativeText(str(path))
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.exec()


def open_manual(entry: str | None = None) -> Path:
    """打开用户手册，返回被打开的 HTML 路径。

    **按模式分流**（见 ``prefer_static_manual``）：

    - 打包版（frozen）：直接打开构建期预生成的 ``docs/guide/manual.html``——
      不渲染、不写临时文件，点下去就只剩开浏览器那一下；万一产物里没有这个
      文件（老包 / 构建步骤没跑到），退回现渲染，功能不受影响；
    - 开发模式：**一律现渲染**到临时目录，改完 md 立刻看到新内容，不会被仓库里
      可能存在的旧静态文件顶掉。

    返回路径是为了调用方（或测试）能拿到产物做进一步处理。
    打不开浏览器时不抛异常——手册文件仍然在，用户可以手动打开，
    界面上会弹一个带路径的提示框。

    ⚠️ 不要给 URL 加 ``?v=<时间戳>`` 去防缓存：Windows 上最终还是要走系统 shell，
    查询串会被当成路径的一部分，实测地址栏里根本不出现。临时文件靠**文件名本身
    带时间戳**（见 ``_HTML_PREFIX``）保证 URL 唯一；静态文件靠"重装即替换"。

    ⚠️ 不要把 ``html_path.as_uri()`` 直接丢给系统（见 ``_open_with_system``）。
    """
    html_path = None
    if prefer_static_manual():
        static = static_manual_path()
        if static.exists():
            html_path = static
    if html_path is None:
        html_path = generate_manual_html(entry)
    if not _open_with_system(html_path):
        _notify_open_failed(html_path)
    return html_path
