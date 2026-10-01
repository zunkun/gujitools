# -*- coding: utf-8 -*-
"""界面字体：统一的字体族解析与构造，以及「文字工具」的可选字体清单。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）。
`ui_font` 跟「控件」没什么关系，却被日志面板、分段开关等多处共用；留在
widgets 里会让 `segmented_toggle` 反向 import widgets，形成循环导入。
"""

from __future__ import annotations

import re

from PySide6.QtGui import QFont, QFontDatabase

from desktop.ui import theme as T
from utils.fonts import cjk_font_families

_FONT_FAMILY: str | None = None
#: ``text_font_families()`` 的结果缓存（逐族查书写系统在 200+ 字体上要 ~150ms）
_TEXT_FONTS_CACHE: list[str] | None = None


def ui_font(size: int = T.SIZE_BODY, bold: bool = False) -> QFont:
    """统一的界面字体（族名 + 像素字号）。

    族名走 ``resolve_font_family()`` 解析出的系统实际字体，与
    ``apply_app_style`` 给整个应用设置的字体保持一致；否则在没有
    ``Microsoft YaHei UI`` 的机器上，这些控件会各自回退到默认字体，
    和应用其它文字对不上。
    """
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        from desktop.ui.style import resolve_font_family

        _FONT_FAMILY = resolve_font_family()
    font = QFont(_FONT_FAMILY)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


# ------------------------------------------------------------ 文字工具字体清单
#: 文字工具里保留的**西文**字体：只留几个常用（用户 2026-10-01 定
#: 「中文为主，英文选择几个常用不要太多」）。系统字体库动辄两三百个族，
#: 全列出来中文反而被淹没、翻半天找不到"仿宋"。
LATIN_TEXT_FONTS = (
    "Arial",
    "Times New Roman",
    "Georgia",
    "Verdana",
    "Calibri",
    "Courier New",
)

#: 中文字体的推荐顺序（古籍批注口径）：衬线/书写体（仿宋、宋体、楷体）在前，
#: 黑体系与装饰字体在后，不在表里的按族名排在其后。⚠️ 中英两种写法都列——
#: Qt 在中文 Windows 上既可能注册成 ``SimSun`` 也可能注册成 ``宋体``。
_CJK_PRIORITY = (
    "FangSong", "仿宋", "FangSong_GB2312", "仿宋_GB2312", "STFangsong",
    "华文仿宋",
    "SimSun", "宋体", "NSimSun", "新宋体", "STSong", "华文宋体",
    "STZhongsong", "华文中宋", "KingHwa_OldSong", "京華老宋体",
    "KaiTi", "楷体", "KaiTi_GB2312", "楷体_GB2312", "STKaiti", "华文楷体",
    "SimHei", "黑体", "STHeiti", "华文细黑",
    "Microsoft YaHei", "Microsoft YaHei UI", "微软雅黑",
    "DengXian", "等线",
)

#: 「只有扩展区生僻字」的字体族名特征：这类字体连常用字都没有，拿它当主
#: 字体整块文字都画不出来（与 `utils/fonts.py` 的 GROUP_SUPPLEMENT 同理）。
_SUPPLEMENT_RE = re.compile(r"[-_ ]?ext[bg]\b", re.IGNORECASE)
#: 字重/字形变体后缀：Light/Bold/Italic… 是同一族的不同形态，单列出来只是
#: 噪音（与 `utils/fonts.py` 候选表「只列常规字重」的口径一致）。
_WEIGHT_RE = re.compile(
    r"\b(thin|extralight|ultralight|light|semilight|demilight|regular|medium|"
    r"semibold|demibold|bold|extrabold|ultrabold|black|heavy|italic|oblique)"
    r"\s*$",
    re.IGNORECASE,
)
#: 老式系统位图字体：能渲染中文，但拿来当批注文字很难看，不该出现在下拉里。
_NON_TEXT_FAMILIES = frozenset({"System", "Terminal", "Fixedsys", "yyb"})


def _keep_family(family: str) -> bool:
    """该族能不能进「文字工具」下拉（滤掉补字字体 / 字重变体 / 系统位图字体）。"""
    return not (
        family in _NON_TEXT_FAMILIES
        or _SUPPLEMENT_RE.search(family)
        or _WEIGHT_RE.search(family)
    )


def _is_cjk_family(family: str) -> bool:
    """该族是否自带中文（简/繁）字形。"""
    systems = QFontDatabase.writingSystems(family)
    return (QFontDatabase.WritingSystem.SimplifiedChinese in systems
            or QFontDatabase.WritingSystem.TraditionalChinese in systems)


def _cjk_rank(family: str) -> tuple:
    """中文族排序键：推荐表里的按表序，其余按族名（稳定且可预期）。"""
    try:
        return (0, _CJK_PRIORITY.index(family), "")
    except ValueError:
        return (1, 0, family)


def text_font_families(refresh: bool = False) -> list[str]:
    """文字工具可选字体：**中文字体在前**，其后是几个常用西文字体。

    ⚠️ 离屏（``QT_QPA_PLATFORM=offscreen``）与精简镜像里 ``QFontDatabase``
    可能是空的——此时退回 `utils.fonts` 的候选族名 + 西文常量，保证下拉不空、
    控件可用；真实机器上取到的当然是系统里**实际装了**的字体。

    结果缓存：逐个族查 ``writingSystems()`` 在 200+ 字体的机器上要 ~150ms，
    而文字工具每次切换都会重建选项行。装了新字体想立刻看到就传 ``refresh``。
    """
    global _TEXT_FONTS_CACHE
    if _TEXT_FONTS_CACHE is not None and not refresh:
        return list(_TEXT_FONTS_CACHE)
    available = set(QFontDatabase.families())
    if available:
        cjk = sorted(
            (f for f in available if _keep_family(f) and _is_cjk_family(f)),
            key=_cjk_rank,
        )
        latin = [f for f in LATIN_TEXT_FONTS if f in available]
    else:
        cjk = [f for f in cjk_font_families() if _keep_family(f)]
        latin = list(LATIN_TEXT_FONTS)
    _TEXT_FONTS_CACHE = cjk + [f for f in latin if f not in cjk]
    return list(_TEXT_FONTS_CACHE)
