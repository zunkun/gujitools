# -*- coding: utf-8 -*-
"""中文字体探测：跨平台候选路径 / 字体族名的**唯一定义处**。

为什么要抽这一层
----------------
PDF 的标题与页码（`utils.pdf_draw.register_fonts`）和检测框标注
（`utils.box_draw.find_cjk_font`）都要画中文，此前两处各自硬编码了四条
``C:\\Windows\\Fonts\\*``。Windows 上一切正常；换到 Linux / macOS 时探测
全部落空 → PDF 里的中文退回 ``Helvetica``（方块或丢字）、框标注退回
ASCII 的 ``L`` / ``R`` / ``U``——**输出内容是错的却不报任何错**。

依赖方向：只 import 标准库，是 ``utils`` 的最底层（与 ``utils/units.py``
同级），任何层都可引用。

设计取舍
--------
- **不做 fontconfig / ``fc-match`` 动态查询**：静态路径已覆盖主流发行版
  的默认字体，而 spawn 子进程会让打包产物和自测行为都变复杂。
- **留了环境变量逃生口 ``GUJI_CJK_FONT``**：精简镜像 / CI / AppImage 里常常
  没有系统 CJK 字体，指向随包自带的 .ttf / .ttc 即可，它**永远排在最前**。
"""

from __future__ import annotations

import os
import sys

#: 手动指定中文字体文件的环境变量（优先级最高，便于容器与随包自带字体）
GUJI_FONT_ENV = "GUJI_CJK_FONT"

# ------------------------------------------------------------------ 候选路径
# ⚠️ Windows 四条**顺序不变**：这是历史沿用顺序，换了会改变已有 PDF 的字体
# 选择结果（同一台机器上取到不同字体 = 排版位置不同）。
_WINDOWS_PATHS = (
    "C:\\Windows\\Fonts\\fsgb2312.ttf",   # 仿宋 GB2312（竖排标题最贴近古籍）
    "C:\\Windows\\Fonts\\simfang.ttf",    # 仿宋
    "C:\\Windows\\Fonts\\simsun.ttc",     # 宋体
    "C:\\Windows\\Fonts\\msyh.ttc",       # 微软雅黑
)

# Ubuntu 22.04/24.04、Debian 12 等常见发行版的默认 CJK 字体位置。
# Noto 优先（与 Windows 侧的仿宋/宋体同为衬线），文泉驿与 AR PL 作为兜底。
_LINUX_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",     # 文泉驿正黑
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # 文泉驿微米黑
    "/usr/share/fonts/truetype/arphic/uming.ttc",       # AR PL UMing（宋体风）
)

# macOS 自带中文字体（ttc 内的合集首面孔通常是国字标准宋体/苹方）
_MACOS_PATHS = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/STSong.ttc",
    "/Library/Fonts/Songti.ttc",
)


def _platform_paths() -> tuple:
    """按当前系统返回内置候选路径。**不保证存在**，由调用方逐个探测。"""
    if sys.platform == "win32":
        return _WINDOWS_PATHS
    if sys.platform == "darwin":
        return _MACOS_PATHS
    return _LINUX_PATHS


def cjk_font_paths() -> tuple:
    """中文字体文件候选路径（按优先级）。

    ``GUJI_CJK_FONT`` 指定的文件排在最前且只出现一次；其后是本平台的
    内置候选。返回的可能全都不存在——调用方必须自己 ``Path.exists()``。
    """
    override = os.environ.get(GUJI_FONT_ENV, "").strip()
    paths = list(_platform_paths())
    if override:
        paths = [override] + [p for p in paths if p != override]
    return tuple(paths)


def first_existing_cjk_font() -> str | None:
    """返回第一个真实存在的中文字体文件路径；全部缺失返回 None。"""
    from pathlib import Path

    for path in cjk_font_paths():
        try:
            if Path(path).exists():
                return path
        except OSError:
            # 环境变量里可能塞进带 NUL / 非法字符的东西，跳过即可
            continue
    return None


# ------------------------------------------------------------------ 字体族名
# GUI 侧（QFontDatabase.families()）用的是**族名**而不是文件路径，两者不能
# 混用——这里是 GUI 那份候选，同样按平台给。
_WINDOWS_FAMILIES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "FangSong",
    "SimFang",
    "SimSun",
    "SimHei",
)
_LINUX_FAMILIES = (
    "Noto Serif CJK SC",
    "Source Han Serif SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "AR PL UMing CN",
)
_MACOS_FAMILIES = (
    "PingFang SC",
    "Songti SC",
    "STSong",
    "Heiti SC",
)


def cjk_font_families() -> tuple:
    """按当前平台返回中文字体族名（按优先级），供 Qt 侧挑选。

    调用方（如第四步预览）再与 `QFontDatabase.families()` 求交集取第一个命中的。
    """
    if sys.platform == "win32":
        return _WINDOWS_FAMILIES
    if sys.platform == "darwin":
        return _MACOS_FAMILIES
    return _LINUX_FAMILIES
