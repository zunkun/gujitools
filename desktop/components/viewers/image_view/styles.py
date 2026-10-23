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


#: 图片边缘的虚线颜色（去底色页用）：去底色成品是**透明底**，在白底画布上
#: 看不出边界，用中性灰虚线勾一圈（用户 2026-10-23）。
EDGE_DASH_COLOR = QColor("#8b949e")


HANDLE_RADIUS = 5  # 缩放手柄半径（控件像素）


# 选中框四角手柄：0=左上 1=右上 2=右下 3=左下
_HANDLE_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]


def is_half_page(boxes, image_size, full: bool = False,
                 single_column: bool = False) -> bool:
    """本页是否该标成「半幅」（一个横跨整页的框）。

    两条同时成立：非整幅页、**恰好一个框**、该框宽 ≥60% 页宽
    （:func:`utils.book_layout.is_single_wide_box`——阈值只有那一处）。

    ⚠️ 用户 2026-10-23（任务 0004）：一页只检出一个 ``harfcontent``、框宽
    >60% 时，中心位置**没有鉴别力**——它不可能与另一栏并排，必然是「半幅」。
    所以这里是**页级判据**，不再像 2026-10-17 那样依赖 ``single_column``
    （整本书是否单栏书）了：混合书里单个宽框页同样得认成半幅，不能按中心
    硬拆左框/右框。``single_column`` 形参仅保留以兼容旧调用方，**不再参与判定**。

    页宽未知（``None``/0）时返回 ``False``：没证据不下结论，宁可标成左/右框。
    """
    if full:
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
    - 本页只有一个横跨整页的框：标「半幅」+ 青（见 :func:`is_half_page`）
      ——它不可能有并排的另一栏，**不要求整本书是单栏书**（用户 2026-10-23，
      任务 0004）；
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
