# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
"""预览绘制用的字体选择（内容字与界面字分开取，与成品 PDF 同源）。"""

from __future__ import annotations

from PySide6.QtGui import QFont

from .constants import MM_PER_PT


def _pick_font(candidates, point_size: float) -> QFont:
    """从给定族名候选里挑第一个系统真装了的；都没命中则交给 Qt 兜底。

    ⚠️ 别用裸 `QFont()`：它落到平台的 generic "Sans Serif" 上，在离屏
    （`QT_QPA_PLATFORM=offscreen`）或字体缺失的环境里中文会渲染成空心
    方框；而且它的字宽度量恰好等于字号，横向文字的占宽会被严重高估。
    """
    from PySide6.QtGui import QFontDatabase

    available = set(QFontDatabase.families())
    for candidate in candidates:
        if candidate in available:
            font = QFont(candidate)
            break
    else:
        font = QFont()
    font.setPointSizeF(max(1.0, float(point_size)))
    return font


def _pick_preview_font(point_size: float) -> QFont:
    """**界面**文字（效果预览的边距标注等）用的字体：走界面族名候选。"""
    from utils.fonts import cjk_font_families

    return _pick_font(cjk_font_families(), point_size)


#: 字体文件 → Qt 族名的缓存。``addApplicationFont`` 每次调用都会再占一个
#: 字体 id，重复加载同一个文件纯属浪费；而且 worker 线程每次都去加载会让
#: 预览刷新明显变卡。
_QT_FONT_FILES: dict[str, str | None] = {}


def qt_family_for_file(path: str) -> str | None:
    """按**字体文件**加载并取回 Qt 族名；失败返回 None。

    为什么要按文件而不是按族名：PDF 侧（`utils.pdf_draw.build_font_chain`）
    也是按文件注册字体的，两边用同一个文件才能保证「预览 = 成品」。按族名
    查表在离屏/精简环境下会落空（那时 `QFontDatabase.families()` 几乎是
    空的），预览就退回默认字体，与成品对不上。
    """
    key = str(path)
    if key in _QT_FONT_FILES:
        return _QT_FONT_FILES[key]
    family: str | None = None
    try:
        from PySide6.QtGui import QFontDatabase

        font_id = QFontDatabase.addApplicationFont(key)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    except Exception:
        family = None
    _QT_FONT_FILES[key] = family
    return family


def _pick_content_font(point_size: float, preferred=None) -> QFont:
    """**PDF 内容**（标题 / 页码）用的字体：**仿宋优先**，可被指定覆盖。

    ``preferred`` 是用户选的字体（显示名 / 路径 / 文件名），能解析到真实文件
    时按**该文件**加载——与 PDF 侧同一个文件，预览与成品才对得上；解析不到
    （本机没这个字体）就回落到自动候选，不会因为一条配置失效而预览不出来。

    必须与 `pdf_draw.register_fonts` 实际选中的字体对齐——那一侧按**文件路径**
    取（Windows 上命中 simfang.ttf = 仿宋），这一侧若按界面候选（雅黑打头）
    取，就会出现「预览是雅黑、导出是仿宋」，所见即所得直接破掉。
    """
    from utils.fonts import content_font_families, resolve_chain

    # ⚠️ 一律**按文件**加载，与 PDF 侧 `build_font_chain` 的链首是同一个
    # 文件——这是「预览 = 成品」唯一可靠的保证。早先默认走族名查表
    # （content_font_families），离屏/精简环境下 `QFontDatabase.families()`
    # 里根本没有那些族，QFont 静默落到 "Sans Serif"，预览与成品对不上。
    chain = resolve_chain(preferred)
    if chain:
        family = qt_family_for_file(chain[0].path)
        if family:
            font = QFont(family)
            font.setPointSizeF(max(1.0, float(point_size)))
            return font
    return _pick_font(content_font_families(), point_size)


def preview_text_font(spec, px_per_mm: float) -> QFont:
    """按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。

    字体族走 ``_pick_content_font``（内容是标题 / 页码，仿宋优先）——与
    ``pdf_draw.register_fonts`` 取到的字体同一种，预览与成品才对得上。

    ⚠️ 不能直接用 ``setPointSizeF(spec.font_size_pt)``：那是固定像素大小，
    而逐字步进是 ``char_h_mm × px_per_mm``（随密度缩放）。两处口径不同时，
    密度一变小（第四步版面编辑画布把整页缩到可视区，≈2 px/mm，远小于效果
    预览的 ≈5.4 px/mm），字仍是原大小、步进却按比例缩小 → **字叠在一起**。

    统一口径后：字高 = 字号(mm) × 密度，与步进同源，任何密度下都不重叠，
    且与成品 PDF 的真实字号（pt → mm）一致。

    ``spec.font`` 是用户为这段文字（标题 / 页码各自独立）指定的字体，
    能解析到文件就按文件加载——与成品 PDF 用同一个字体文件。
    """
    font = _pick_content_font(float(spec.font_size_pt), getattr(spec, "font", None))
    font.setPixelSize(
        max(1, int(round(float(spec.font_size_pt) * MM_PER_PT * px_per_mm)))
    )
    return font
