# -*- coding: utf-8 -*-
"""框的配色/名称与绘制样式（**纯数据 + 纯函数**，无 Qt 部件依赖）。

从 ``image_view.py`` 拆出（2026-10-07）。其它模块（检测框/去底色/打印预览）
可直接复用这里的框配色口径，不必依赖画布控件。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from utils.book_layout import is_single_wide_box
from utils.box_draw import BOX_COLORS_RGB, BOX_KIND_INDEX, BOX_NAMES as _BOX_NAMES
from utils.box_geometry import half_sides


# 框颜色/名称**不在本文件定义**：唯一事实来源是 utils/box_draw.py —— CLI 的
# `detect --save` 标注图用的也是它，两边各抄一份（只靠注释对齐）迟早漂移。
# 顺序：绿 / 蓝 / 琥珀 / 靛蓝 / 青 对应 左框 / 右框 / 合并框 / 整幅 / 半幅
# （整幅 = fullcontent 单框整页；半幅 = 单栏书里横跨整页的那一栏，见
#  functions/detect.PageBoxes 与 utils/book_layout）
BOX_COLORS = [QColor(*rgb) for rgb in BOX_COLORS_RGB]


BOX_NAMES = list(_BOX_NAMES)


#: 类型键 → 下标（映射本身在 utils/box_draw，各层不再各记一份）
SIDE_INDEX = {"left": BOX_KIND_INDEX["left"], "right": BOX_KIND_INDEX["right"]}


FULL_INDEX = BOX_KIND_INDEX["full"]


HALF_INDEX = BOX_KIND_INDEX["half"]


#: 整幅内容框（fullcontent）专用的名称/颜色。
FULL_BOX_NAME = BOX_NAMES[FULL_INDEX]


FULL_BOX_COLOR = BOX_COLORS[FULL_INDEX]


#: 半幅（单栏书里横跨整页的那一栏）专用的名称/颜色。
HALF_BOX_NAME = BOX_NAMES[HALF_INDEX]


HALF_BOX_COLOR = BOX_COLORS[HALF_INDEX]


REFERENCE_COLOR = QColor("#f97316")


HANDLE_RADIUS = 5  # 缩放手柄半径（控件像素）


# 选中框四角手柄：0=左上 1=右上 2=右下 3=左下
_HANDLE_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]


def is_half_page(boxes, image_size, full: bool = False,
                 single_column: bool = False) -> bool:
    """本页是否该标成「半幅」（一个横跨整页的框，且整本书是单栏书）。

    三条同时成立：非整幅页、**恰好一个框**、该框宽 ≥60% 页宽
    （:func:`utils.book_layout.is_single_wide_box`——阈值只有那一处）。

    ⚠️ ``single_column``（整本书判定）必须由宿主传进来：单页**分不出**
    「一栏横跨整页」和「真双栏书里漏检了一侧」，只有整本书的统计能分。
    缺它时返回 ``False``——宁可标成左/右框（旧行为），也不要在没证据时
    把一页的形态改了。
    """
    if full or not single_column:
        return False
    present = [b for b in (boxes or []) if b]
    if len(present) != 1:
        return False
    width = image_size[0] if image_size else None
    return is_single_wide_box(present[0], width)


def box_styles(boxes, image_size=None, full: bool = False,
               single_column: bool = False, side_override: str | None = None):
    """框列表 → ``(names, colors)``，与 ``boxes``（去掉空项后）等长。

    - ``full=True``（整幅页 / fullcontent）：每个框都是「整幅」+ 靛蓝；
    - ``side_override``（``"left"``/``"right"``）：**用户在「半幅」页上指定的
      左右**（存 ``boxes.json`` 的 ``side``）——优先于一切自动判定，直接标
      左框/右框。这种页的框横跨整页、中心压在中线上，按位置算出来的左右
      没有意义（用户 2026-10-17）；
    - ``single_column=True`` 且本页只有一个横跨整页的框：标「半幅」+ 青
      （见 :func:`is_half_page`）——单栏书里它就是一整栏；
    - 否则是半幅页：按**中心位置**判左右（`utils.box_geometry.half_sides`）。

    ⚠️ 优先级：``full`` > ``side_override`` > ``半幅``。整幅是 1 槽形态，
    与半幅互斥；用户指定的左右则是对「半幅」的**明确否定**（他说这页其实
    是某一边），所以要先于半幅判定。

    ⚠️ 这里以前按"框的序号/个数"命名（1 个框→「整幅」、2 个→「左/右」），于是
    删掉一个框会让剩下的框"变身"（用户 2026-09-29 报）。现在类型只由上述
    四条决定，**与有几个框无关**。
    """
    present = [b for b in (boxes or []) if b]
    if full:
        return [FULL_BOX_NAME] * len(present), [FULL_BOX_COLOR] * len(present)
    if side_override in ("left", "right"):
        index = SIDE_INDEX[side_override]
        return [BOX_NAMES[index]] * len(present), [BOX_COLORS[index]] * len(present)
    if is_half_page(present, image_size, full, single_column):
        return [HALF_BOX_NAME] * len(present), [HALF_BOX_COLOR] * len(present)
    names, colors = [], []
    for side in half_sides(present, image_size):
        index = SIDE_INDEX[side]
        names.append(BOX_NAMES[index])
        colors.append(BOX_COLORS[index])
    return names, colors


def box_names(boxes, image_size=None, full: bool = False,
              single_column: bool = False, side_override: str | None = None) -> list:
    """框名称列表（大图信息条文案用）——与 :func:`box_styles` 同一份规则。"""
    return box_styles(boxes, image_size, full, single_column, side_override)[0]
