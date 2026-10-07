# -*- coding: utf-8 -*-
"""框的配色/名称与绘制样式（**纯数据 + 纯函数**，无 Qt 部件依赖）。

从 ``image_view.py`` 拆出（2026-10-07）。其它模块（检测框/去底色/打印预览）
可直接复用这里的框配色口径，不必依赖画布控件。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from utils.box_draw import BOX_COLORS_RGB, BOX_KIND_INDEX, BOX_NAMES as _BOX_NAMES
from utils.box_geometry import half_sides


# 框颜色/名称**不在本文件定义**：唯一事实来源是 utils/box_draw.py —— CLI 的
# `detect --save` 标注图用的也是它，两边各抄一份（只靠注释对齐）迟早漂移。
# 顺序：绿 / 蓝 / 琥珀 / 靛蓝 对应 左框 / 右框 / 合并框 / 整幅
# （整幅 = fullcontent 单框整页，见 functions/detect.PageBoxes）
BOX_COLORS = [QColor(*rgb) for rgb in BOX_COLORS_RGB]


BOX_NAMES = list(_BOX_NAMES)


#: 类型键 → 下标（映射本身在 utils/box_draw，各层不再各记一份）
SIDE_INDEX = {"left": BOX_KIND_INDEX["left"], "right": BOX_KIND_INDEX["right"]}


FULL_INDEX = BOX_KIND_INDEX["full"]


#: 整幅内容框（fullcontent）专用的名称/颜色。
FULL_BOX_NAME = BOX_NAMES[FULL_INDEX]


FULL_BOX_COLOR = BOX_COLORS[FULL_INDEX]


REFERENCE_COLOR = QColor("#f97316")


HANDLE_RADIUS = 5  # 缩放手柄半径（控件像素）


# 选中框四角手柄：0=左上 1=右上 2=右下 3=左下
_HANDLE_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]


def box_styles(boxes, image_size=None, full: bool = False):
    """框列表 → ``(names, colors)``，与 ``boxes``（去掉空项后）等长。

    - ``full=True``（整幅页 / fullcontent）：每个框都是「整幅」+ 靛蓝——
      整幅是**显式类型**，无论怎么移动、缩放都不变；
    - 否则是半幅页：按**中心位置**判左右（`utils.box_geometry.half_sides`，
      规则只有那一处实现），所以把框拖过中线时名字与颜色会跟着换。

    ⚠️ 这里以前按"框的序号/个数"命名（1 个框→「整幅」、2 个→「左/右」），于是
    删掉一个框会让剩下的框"变身"（用户 2026-09-29 报）。现在类型只由
    「是否整幅页」与「框的中心位置」决定，**与有几个框无关**。
    """
    present = [b for b in (boxes or []) if b]
    if full:
        return [FULL_BOX_NAME] * len(present), [FULL_BOX_COLOR] * len(present)
    names, colors = [], []
    for side in half_sides(present, image_size):
        index = SIDE_INDEX[side]
        names.append(BOX_NAMES[index])
        colors.append(BOX_COLORS[index])
    return names, colors


def box_names(boxes, image_size=None, full: bool = False) -> list:
    """框名称列表（大图信息条文案用）——与 :func:`box_styles` 同一份规则。"""
    return box_styles(boxes, image_size, full)[0]
