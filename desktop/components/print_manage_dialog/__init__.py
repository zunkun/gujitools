# -*- coding: utf-8 -*-
"""第四步「管理图片」弹窗面板：**草稿式**缩略图网格 + 二次「插入图片」。

用户 2026-11-02 的口径：

- 缩略图条底部的「插入图片」按钮改为 **「管理图片」**，底部那行右键提示删掉；
- 点「管理图片」弹出本面板：缩略图**一行多列**（图标网格），可多选、可拖动排序；
- 面板底部仍有 **「插入图片」** 按钮，点开是原来的插入弹窗 B
  （``PrintInsertPanel``，上传图片 / 删除恢复）；
- 本面板里的改动只是**草稿**：点外壳的「保存」才写回，取消则一概不生效。

本版补充（用户 2026-11-02 第二轮）：

- 刚插入、还没保存的新图用**虚线框**圈起来（暖色，与已有图片区分）；
- 每张图**右上角有 x**，点它即从草稿里删掉；
- 选中一张或多张时，底部才出现 **「删除图片」** 按钮。

⚠️ 本面板只收集草稿，不碰数据层：顺序落盘、新图复制、恢复项出
``deleted_pages`` 全由宿主（``pages/taskdetail/print_list.py``）在「保存」后执行。

⚠️ 2026-11-22 起按职责拆成子包：常量 ``constants``、几何/缩略图辅助
``helpers``、条目自绘 ``delegate``、图标网格 ``grid``、面板 ``panel``。
本 ``__init__`` 只做重导出：既有 ``from desktop.components.print_manage_dialog
import X`` 全部不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.components.print_manage_dialog.constants import (
    CELL_LABEL_H,
    CELL_SIZE,
    CHECK_SIZE,
    CLOSE_SIZE,
    PENDING_KEY,
    SHOWN_SIZE_ROLE,
    TARGET_KEY,
    THUMB_SIZE,
)
from desktop.components.print_manage_dialog.delegate import _ThumbDelegate
from desktop.components.print_manage_dialog.grid import _ThumbGrid
from desktop.components.print_manage_dialog.helpers import (
    _check_rect,
    _close_rect,
    _icon_and_size,
    _image_rect,
    _typical_thumb_height,
    page_label,
)
from desktop.components.print_manage_dialog.panel import PrintManagePanel

__all__ = [
    "PrintManagePanel",
    "PENDING_KEY",
    "TARGET_KEY",
    "CELL_LABEL_H",
    "CELL_SIZE",
    "CHECK_SIZE",
    "CLOSE_SIZE",
    "SHOWN_SIZE_ROLE",
    "THUMB_SIZE",
    "page_label",
    "_ThumbDelegate",
    "_ThumbGrid",
    "_check_rect",
    "_close_rect",
    "_icon_and_size",
    "_image_rect",
    "_typical_thumb_height",
]
