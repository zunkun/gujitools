# -*- coding: utf-8 -*-
"""手册目录、静态手册路径与模式判据（自 ``desktop/ui/help_dialog.py`` 拆出）。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from desktop.utils.files import package_dir

#: 手册条目：(键, 分段开关文案, 文件名)。新增手册只改这里。
MANUAL_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("gui", "桌面端操作", "user-guide.md"),
    ("cli", "命令行", "cli.md"),
)

#: 生成的 HTML 落在临时目录，**文件名带毫秒时间戳、每次都不一样**。
#:
#: ⚠️ 不要改回固定文件名 + ``?v=<时间戳>`` 查询串那套：
#: 1. Windows 上 ``webbrowser.open`` 走的是 ``os.startfile``，``?v=...``
#:    会被当成路径的一部分，实测地址栏里根本看不到查询串（缓存照旧命中）；
#: 2. 固定文件名 + file:// 会被浏览器按 URL 缓存，改了内容用户还是看到旧版
#:    （曾踩：屏幕上一直是原始 markdown，其实是早期一次 fallback 的产物）。
#: 文件名唯一 → URL 天然唯一 → 缓存不可能命中。
#: 代价是每次点会新开一个标签页（不能复用），但「看错内容」比「多开标签」严重得多。
_HTML_PREFIX = "guji_manual_"

#: 保留最近几份历史 HTML，更早的清理掉，避免临时目录里堆一堆文件。
_KEEP_RECENT = 3


def _cleanup_old_manuals() -> None:
    """删掉更早生成的手册 HTML，只留最近 ``_KEEP_RECENT`` 份。"""
    tmp = Path(tempfile.gettempdir())
    try:
        olds = sorted(
            tmp.glob(f"{_HTML_PREFIX}*.html"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for p in olds[_KEEP_RECENT:]:
        try:
            p.unlink()
        except OSError:
            pass  # 文件被浏览器占着就跳过，下次再清

def manual_dir() -> Path:
    """手册目录（源码与打包两种模式下都可用）。

    与 ``package_dir()`` 同源：源码模式下 ``desktop/`` 的上一级就是仓库根，
    打包后数据文件由 ``guji.spec`` 的 ``gui_datas`` 落到 ``_internal/``，
    ``package_dir()`` 在 frozen 下返回 ``_MEIPASS/desktop``，再上一级同样是
    资源根，因此 ``package_dir().parent / "docs" / "guide"`` 两种模式通用。
    """
    return package_dir().parent / "docs" / "guide"


#: 构建期预生成的自包含手册 HTML，**落在 ``desktop/static/`` 下**。
#:
#: 生产与开发两条路（判据见 ``prefer_static_manual``）：
#:
#: - **开发模式**：``docs/guide/*.md`` 随时在改，每次点按钮现渲染到 %TEMP%，
#:   改完立刻能看到效果；
#: - **打包模式（生产）**：手册内容在构建那一刻就定死了，构建期把它连**截图
#:   一起内联**渲染成单个 HTML 放进包里，运行时直接打开——不渲染、不写临时
#:   文件、不依赖任何外部文件。
#:
#: 内联（data URI）是必须的：``docs/guide/`` 整目录**不进安装包**（md 与截图
#: 对最终用户都没用，还占体积），所以既不能写相对路径、也不能写构建机的绝对
#: ``file://`` 路径。一个自包含文件 = 换台机器/复制出去都不碎图。
STATIC_MANUAL_NAME = "manual.html"


def static_manual_path() -> Path:
    """构建期预生成的自包含手册路径（**只有打包版才有**；可能不存在）。"""
    return package_dir() / "static" / STATIC_MANUAL_NAME


def prefer_static_manual() -> bool:
    """当前是否该走「构建期静态手册」这条路。

    判据是**打包与否（frozen）**，不是「静态文件在不在」：

    - 开发模式：``docs/guide/*.md`` 随时在改，必须每次现渲染，改完立刻能看到
      效果；若按「文件存在」判断，仓库里哪天留了一个 ``manual.html``（手动生成
      过一次、或从安装包里拷回来的），开发者就会一直看到旧内容；
    - 生产模式（PyInstaller 打包后）：手册内容在构建那一刻就定死了，直接打开
      预生成的静态 HTML，不渲染、不写临时文件。

    ``GUJI_MANUAL_STATIC=1`` / ``=0`` 可强制指定，供冒烟与自测用。
    """
    override = os.environ.get("GUJI_MANUAL_STATIC")
    if override is not None and override.strip() != "":
        return override.strip().lower() not in ("0", "false", "no")
    return bool(getattr(sys, "frozen", False))
