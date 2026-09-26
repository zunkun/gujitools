# -*- coding: utf-8 -*-
"""中文字体探测与降级：候选表、优先级链、字形覆盖查询的唯一定义处。

为什么要抽这一层
----------------
PDF 的标题与页码（`utils.pdf_draw.register_fonts`）和检测框标注
（`utils.box_draw.find_cjk_font`）都要画中文，此前两处各自硬编码了四条
``C:\\Windows\\Fonts\\*``。Windows 上一切正常；换到 Linux / macOS 时探测
全部落空 → PDF 里的中文退回 ``Helvetica``（方块或丢字）、框标注退回
ASCII 的 ``L`` / ``R`` / ``U``——**输出内容是错的却不报任何错**。

为什么不能"指定死一个字体"（本层存在的根本原因）
------------------------------------------------
古籍标题里常有**异体字 / 生僻字**：仿宋只覆盖 GB2312 与扩展 A，遇到
扩展 B（`U+20000` 起）的字就没有字形，fpdf 会静默画出空白（控制台只留一行
"missing the following glyphs"）。系统里并非没有这些字——Windows 自带
``simsunb.ttf``（宋体-ExtB）、``mingliub.ttc``——只是它们**不是仿宋**。

因此这里提供三件事：

1. **候选表**：跨平台的中文字体清单，带中文显示名与优先级分组
   （仿宋 → 宋体 → 微软雅黑 → 黑体 → 其它），供用户挑选；
2. **降级链**：把候选按优先级串成一条链，逐个字挑第一个"有这个字"的字体，
   生僻字因此自动落到 ExtB 补字字体上，仿宋该用的地方仍是仿宋；
3. **补字字体**（``fallback_only``）：只有扩展区生僻字的字体（宋体-ExtB 等）
   只补字、不做主字体——它连常用字都没有，选它当主字体整页都会空。

依赖方向：只 import 标准库，是 ``utils`` 的最底层（与 ``utils/units.py``
同级），任何层都可引用。字形查询按需 import ``fontTools``（缺失时退化为
"假定全部支持"，只是不再逐字降级，不会崩）。

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
from dataclasses import dataclass

#: 手动指定中文字体文件的环境变量（优先级最高，便于容器与随包自带字体）
GUJI_FONT_ENV = "GUJI_CJK_FONT"

# ------------------------------------------------------------------ 优先级组
#: 排序即用户要求的降级顺序；数字越小越优先。
GROUP_FANGSONG = 0    # 仿宋：古籍竖排标题的首选字形
GROUP_SONG = 1        # 宋体：仿宋缺字时的第一顺位（同为衬线）
GROUP_YAHEI = 2       # 微软雅黑（Windows）/ 思源黑体（Linux）
GROUP_HEI = 3         # 黑体
GROUP_OTHER = 4       # 其它可用中文字体（楷体、隶书、等线…）
#: 只用来补生僻字，**不出现在用户可选列表里**：这类字体（宋体-ExtB）只有
#: 扩展区字符，拿它当主字体连"古籍"两个字都画不出来。
GROUP_SUPPLEMENT = 9

#: 字体文件扩展名。**唯一定义处**（2026-09-26 审计）：以前
#: fonts.py / font_scan.py / font_setup.py 各写一份，而且 font_setup 那份
#: 多一个 `.otc`（OpenType Collection）→ `.otc` 字体能被"体检"扫到、
#: 却不在候选表里，两边口径对不上。现在统一从这里取。
FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")


@dataclass(frozen=True)
class FontEntry:
    """一个可用的中文字体：显示名 + 文件路径 + 优先级组。

    ``fallback_only`` 为真的条目只用于补字（缺字时才用），不作为主字体、
    也不出现在用户的选择列表里。
    """

    display: str
    path: str
    group: int = GROUP_OTHER
    fallback_only: bool = False

    @property
    def exists(self) -> bool:
        """字体文件是否真实存在（构造时不校验，用到才探测）。"""
        try:
            return os.path.isfile(self.path)
        except OSError:
            # 环境变量里可能塞进带 NUL / 非法字符的东西
            return False


# ------------------------------------------------------------------ 候选表
# ⚠️ 同组内**顺序不变**：这决定了"仿宋缺字时先落到谁"，换了会改变已有 PDF
# 的字体选择结果（同一台机器上取到不同字体 = 排版位置不同）。
#
# 只列**常规字重**：Light/Bold 是同一族的不同粗细，PDF 里没必要各占一个
# 嵌入字体，列表里出现三个"微软雅黑"对用户也没意义。
_WINDOWS_FONTS = (
    # 仿宋
    ("仿宋 GB2312", "C:\\Windows\\Fonts\\fsgb2312.ttf", GROUP_FANGSONG),
    ("仿宋", "C:\\Windows\\Fonts\\simfang.ttf", GROUP_FANGSONG),
    ("华文仿宋", "C:\\Windows\\Fonts\\STFANGSO.TTF", GROUP_FANGSONG),
    # 宋体
    ("宋体", "C:\\Windows\\Fonts\\simsun.ttc", GROUP_SONG),
    ("新宋体", "C:\\Windows\\Fonts\\nsimsun.ttc", GROUP_SONG),
    ("华文宋体", "C:\\Windows\\Fonts\\STSONG.TTF", GROUP_SONG),
    ("华文中宋", "C:\\Windows\\Fonts\\STZHONGS.TTF", GROUP_SONG),
    # 微软雅黑
    ("微软雅黑", "C:\\Windows\\Fonts\\msyh.ttc", GROUP_YAHEI),
    # 黑体
    ("黑体", "C:\\Windows\\Fonts\\simhei.ttf", GROUP_HEI),
    ("华文细黑", "C:\\Windows\\Fonts\\STXIHEI.TTF", GROUP_HEI),
    # 其它中文字体
    ("楷体", "C:\\Windows\\Fonts\\simkai.ttf", GROUP_OTHER),
    ("华文楷体", "C:\\Windows\\Fonts\\STKAITI.TTF", GROUP_OTHER),
    ("隶书", "C:\\Windows\\Fonts\\SIMLI.TTF", GROUP_OTHER),
    ("幼圆", "C:\\Windows\\Fonts\\SIMYOU.TTF", GROUP_OTHER),
    ("等线", "C:\\Windows\\Fonts\\Deng.ttf", GROUP_OTHER),
    ("方正舒体", "C:\\Windows\\Fonts\\FZSTK.TTF", GROUP_OTHER),
    ("方正姚体", "C:\\Windows\\Fonts\\FZYTK.TTF", GROUP_OTHER),
    ("华文行楷", "C:\\Windows\\Fonts\\STXINGKA.TTF", GROUP_OTHER),
    ("华文新魏", "C:\\Windows\\Fonts\\STXINWEI.TTF", GROUP_OTHER),
    ("华文彩云", "C:\\Windows\\Fonts\\STCAIYUN.TTF", GROUP_OTHER),
    ("华文琥珀", "C:\\Windows\\Fonts\\STHUPO.TTF", GROUP_OTHER),
    ("微软正黑体", "C:\\Windows\\Fonts\\msjh.ttc", GROUP_OTHER),
)

# Ubuntu 22.04/24.04、Debian 12 等常见发行版的默认 CJK 字体位置。
# ⚠️ Linux 通常**没有**仿宋；第一款是 `utils.font_setup` 补装 fonts-cwtex-fs
# 后落地的路径（真仿宋，最接近 Windows 仿宋），装了就会自动排到最前。
_LINUX_FONTS = (
    # 仿宋（补装才有）
    ("cwTeX 仿宋體", "/usr/share/fonts/truetype/cwtex/cwfs.ttf", GROUP_FANGSONG),
    ("cwTeX 仿宋體", "/usr/share/fonts/opentype/cwtex/cwfs.otf", GROUP_FANGSONG),
    ("cwTeX 仿宋體", "/usr/share/fonts/truetype/cwtex-fs/cwfs.ttf", GROUP_FANGSONG),
    # 宋体 / 明体
    ("Noto Serif CJK", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", GROUP_SONG),
    ("Noto Serif CJK SC", "/usr/share/fonts/opentype/noto/NotoSerifCJKsc-Regular.otf", GROUP_SONG),
    ("Noto Serif CJK", "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc", GROUP_SONG),
    ("文鼎明體", "/usr/share/fonts/truetype/arphic/uming.ttc", GROUP_SONG),
    # 黑体（Linux 没有雅黑，思源黑体是等价顺位）
    ("Noto Sans CJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", GROUP_YAHEI),
    ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf", GROUP_YAHEI),
    ("文泉驿正黑", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", GROUP_HEI),
    ("文泉驿微米黑", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", GROUP_HEI),
)

# macOS 自带中文字体（ttc 内的合集首面孔通常是国字标准宋体/苹方）
_MACOS_FONTS = (
    # 宋体 / 明体（macOS 无仿宋，宋体是最贴近古籍的衬线）
    ("宋体-简", "/System/Library/Fonts/Supplemental/Songti.ttc", GROUP_SONG),
    ("华文宋体", "/System/Library/Fonts/Supplemental/STSong.ttc", GROUP_SONG),
    ("宋体-简", "/Library/Fonts/Songti.ttc", GROUP_SONG),
    # 黑体
    ("苹方", "/System/Library/Fonts/PingFang.ttc", GROUP_HEI),
    ("黑体-简", "/System/Library/Fonts/STHeiti Medium.ttc", GROUP_HEI),
    # 其它
    ("楷体-简", "/System/Library/Fonts/Supplemental/Kaiti.ttc", GROUP_OTHER),
    ("华文楷体", "/System/Library/Fonts/Supplemental/STKaiti.ttc", GROUP_OTHER),
)

# ------------------------------------------------------------------ 补字字体
# 只有扩展区生僻字、没有常用字的字体。它们是"仿宋缺字"这道题的真正答案：
# 古籍异体字大多落在 CJK 扩展 B，而仿宋/宋体/雅黑/黑体**都没有**那些字。
# ⚠️ 只补字不做主字体（见 GROUP_SUPPLEMENT 的说明）。
_SUPPLEMENT_FONTS = (
    ("宋体-ExtB", "C:\\Windows\\Fonts\\simsunb.ttf"),
    ("细明体-ExtB", "C:\\Windows\\Fonts\\mingliub.ttc"),
    ("花园明朝", "/usr/share/fonts/truetype/hanazono/HanaMinA.ttf"),
    ("花园明朝 B", "/usr/share/fonts/truetype/hanazono/HanaMinB.ttf"),
)


def _platform_entries() -> tuple[FontEntry, ...]:
    """按当前系统返回内置候选条目。**不保证存在**，由调用方筛。"""
    if sys.platform == "win32":
        rows = _WINDOWS_FONTS
    elif sys.platform == "darwin":
        rows = _MACOS_FONTS
    else:
        rows = _LINUX_FONTS
    entries = [FontEntry(display=d, path=p, group=g) for d, p, g in rows]
    entries += [
        FontEntry(display=d, path=p, group=GROUP_SUPPLEMENT, fallback_only=True)
        for d, p in _SUPPLEMENT_FONTS
    ]
    return tuple(entries)


def known_entries() -> tuple[FontEntry, ...]:
    """全部已知候选（按优先级），含不存在的。

    ``GUJI_CJK_FONT`` 指定的文件排在最前且只出现一次——它是用户/CI 的
    显式指定，优先级高于"仿宋优先"。
    """
    override = os.environ.get(GUJI_FONT_ENV, "").strip()
    entries = list(_platform_entries())
    if override:
        name = os.path.splitext(os.path.basename(override))[0]
        entries.insert(0, FontEntry(display=f"{name}（{GUJI_FONT_ENV} 指定）",
                                    path=override, group=GROUP_FANGSONG))
    return tuple(entries)


def available_entries(with_supplement: bool = True) -> tuple[FontEntry, ...]:
    """系统里真实存在的候选，按优先级排序（仿宋 → 宋体 → …）。

    ``with_supplement=False`` 时不含"仅补字"字体——那种字体不能当主字体。

    ⚠️ 排序**只按组**、组内保持候选表里的书写顺序（Python 的 sort 是稳定的）：
    早先按 display 排序，结果"华文中宋"跑到"宋体"前面、"华文彩云"跑到
    "楷体"前面——缺字降级会先落到装饰字体上，视觉上很突兀。
    """
    seen: set[str] = set()
    out: list[FontEntry] = []
    for entry in known_entries():
        if entry.fallback_only and not with_supplement:
            continue
        if not entry.exists or entry.path in seen:
            continue
        seen.add(entry.path)
        out.append(entry)
    return tuple(sorted(out, key=lambda e: e.group))


def selectable_entries() -> tuple[FontEntry, ...]:
    """给用户挑的字体列表：不含"仅补字"字体，按优先级排序。"""
    return available_entries(with_supplement=False)


def find_entry(value) -> FontEntry | None:
    """按显示名 / 文件路径 / 文件名反查条目（用户配置回填用）。

    找不到返回 None——用户的机器上可能没有配置里记的那个字体（换机器、
    卸载字体），此时应当回落到自动选择而不是报错。
    """
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    matches = [
        e for e in known_entries()
        if e.display == text or e.path == text
        or os.path.basename(e.path).lower() == lowered
    ]
    if not matches:
        return None
    # ⚠️ 优先返回**真实存在**的那份：同一个显示名在候选表里可能对应多条
    # 路径（Linux 的 cwTeX 仿宋就列了三个发行版常见的落点），只按显示名取
    # 第一条会拿到一个本机没有的路径，用户明明选了仿宋却悄悄回落成别的字体。
    for entry in matches:
        if entry.exists:
            return entry
    return matches[0]


def resolve_chain(preferred=None) -> list[FontEntry]:
    """按优先级串出降级链：首选字体在前，补字字体垫底。

    ``preferred`` 可以是显示名 / 路径 / 文件名（用户选择或配置里的值）；
    找不到就忽略，链条从"仿宋优先"的自动顺序开始——**不会因为配置里记了
    一个本机没有的字体就整条链失效**。
    """
    chain: list[FontEntry] = []
    seen: set[str] = set()

    def add(entry: FontEntry | None) -> None:
        if entry is None or entry.path in seen:
            return
        seen.add(entry.path)
        chain.append(entry)

    add(find_entry(preferred))
    for entry in available_entries(with_supplement=True):
        add(entry)
    return chain


# ------------------------------------------------------------------ 字形覆盖
_GLYPH_CACHE: dict[str, frozenset | None] = {}


def glyphs(entry: FontEntry) -> frozenset | None:
    """该字体覆盖的码位集合；解析失败或没有 fontTools 时返回 None。

    None 表示"不知道"，调用方应按"支持"处理（乐观）——宁可画出空白，
    也不要因为读不出 cmap 就把整段文字降级成另一种字体。
    """
    path = entry.path
    if path in _GLYPH_CACHE:
        return _GLYPH_CACHE[path]
    coverage: frozenset | None = None
    try:
        from fontTools.ttLib import TTCollection, TTFont

        if path.lower().endswith(".ttc"):
            fonts = TTCollection(path, lazy=True).fonts
        else:
            fonts = [TTFont(path, lazy=True)]
        codepoints: set[int] = set()
        for font in fonts:
            codepoints.update(font.getBestCmap().keys())
        coverage = frozenset(codepoints) if codepoints else None
    except Exception:
        coverage = None
    _GLYPH_CACHE[path] = coverage
    return coverage


def supports(entry: FontEntry, char: str) -> bool:
    """该字体是否有这个字符的字形（读不出 cmap 时按"有"处理）。"""
    if not char:
        return True
    coverage = glyphs(entry)
    if coverage is None:
        return True
    return ord(char) in coverage


def pick_font(chain, char: str) -> FontEntry | None:
    """从降级链里挑第一个有这个字的字体；都没有则返回链首。

    返回链首（而非 None）是刻意的：此时无论选谁都画不出这个字，但至少
    字体是确定的（不会因为返回 None 让调用方崩）。
    """
    if not chain:
        return None
    for entry in chain:
        if supports(entry, char):
            return entry
    return chain[0]


# ------------------------------------------------------------------ 兼容入口
# ⚠️ 下面四个是**历史 API**：路径候选仍被 `utils.box_draw` / 旧自测使用，
# 族名候选仍用于界面文字与 PDF 内容的"族名"场景。新代码请用上面的
# FontEntry 体系（它同时给出显示名与路径，PDF 与预览能共用同一份）。
def cjk_font_paths() -> tuple:
    """中文字体文件候选路径（按优先级）。返回的可能全都不存在。"""
    override = os.environ.get(GUJI_FONT_ENV, "").strip()
    paths = [e.path for e in known_entries() if not e.fallback_only]
    if override:
        paths = [override] + [p for p in paths if p != override]
    return tuple(paths)


def first_existing_cjk_font() -> str | None:
    """返回第一个真实存在的中文字体文件路径；全部缺失返回 None。"""
    for entry in known_entries():
        if entry.exists:
            return entry.path
    return None


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
    """按当前平台返回中文字体族名（按优先级），供 Qt 侧挑**界面**文字。"""
    if sys.platform == "win32":
        return _WINDOWS_FAMILIES
    if sys.platform == "darwin":
        return _MACOS_FAMILIES
    return _LINUX_FAMILIES


# 「印刷内容」——第四步 PDF 里的标题与页码——用的族名候选。
#
# ⚠️ 顺序必须与上面的候选表对齐：PDF 侧按**文件路径**取（Windows 上命中
# simfang.ttf = 仿宋），预览若按**界面**候选（雅黑打头）取，就会出现
# 「预览是雅黑、导出却是仿宋」。
#
# 📌 新代码不要再走族名：改用 `resolve_chain()` + `QFontDatabase.
# addApplicationFont(路径)` 让预览与 PDF 用**同一个文件**，比两边各查一张
# 族名表可靠得多（离屏/精简环境下 Qt 的 families() 甚至可能是空的）。
_WINDOWS_CONTENT_FAMILIES = (
    "FangSong",  # 仿宋（= simfang.ttf 的族名）
    "FangSong_GB2312",  # 仿宋 GB2312（= fsgb2312.ttf）
    "SimFang",
    "SimSun",  # 宋体
    "Microsoft YaHei",
)
_LINUX_CONTENT_FAMILIES = (
    "Noto Serif CJK SC",
    "Source Han Serif SC",
    "AR PL UMing CN",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
)
_MACOS_CONTENT_FAMILIES = (
    "Songti SC",
    "STSong",
    "PingFang SC",
)


def content_font_families() -> tuple:
    """第四步 PDF 内容（标题 / 页码）的字体族名候选：仿宋（衬线）优先。"""
    if sys.platform == "win32":
        return _WINDOWS_CONTENT_FAMILIES
    if sys.platform == "darwin":
        return _MACOS_CONTENT_FAMILIES
    return _LINUX_CONTENT_FAMILIES
