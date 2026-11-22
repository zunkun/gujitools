# -*- coding: utf-8 -*-
"""「管理图片」弹窗的共享常量（见 :mod:`desktop.components.print_manage_dialog`）。"""

from __future__ import annotations

from desktop.components.print_manage_dialog._qt import QSize, Qt

#: 草稿条目的临时标记：刚从本地选入、还没复制进任务目录（保存时才复制）。
PENDING_KEY = "_pending"
#: 复制任务的目标路径（宿主在后台复制前写进来，完成回调据此替换文件）。
TARGET_KEY = "_target"

#: 缩略图框（与插入弹窗的恢复页一致，视觉统一）
THUMB_SIZE = QSize(96, 128)
#: 图标网格单元：缩略图 + 下方一行文字
CELL_SIZE = QSize(THUMB_SIZE.width() + 40, THUMB_SIZE.height() + 38)
#: 网格单元里名称区的高度（框高之外的固定部分）
CELL_LABEL_H = CELL_SIZE.height() - THUMB_SIZE.height()
#: 条目数据角色：图标的**实际显示尺寸**（自绘 x 与虚线框都要用它定位）
SHOWN_SIZE_ROLE = Qt.ItemDataRole.UserRole + 1
#: 右上角 x 的边长
CLOSE_SIZE = 18
#: 左上角多选框的边长
CHECK_SIZE = 18
