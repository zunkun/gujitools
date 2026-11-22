# -*- coding: utf-8 -*-
"""检测文本框独立页的常量与步骤元数据（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from desktop.steps import spec_by_key

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("detect")


#: 导出文件名。⚠️ 与任务流程 ``tasks/<id>/boxes.json`` **同名**是刻意的：
#: 用户拿它跟任务里的那份对照/替换时不必换算名字，格式也是同一套。
EXPORT_NAME = "boxes.json"

#: 导出执行线的两条**产物形态**：同一个 ``_export_kernel`` 按
#: ``request.args["kind"]`` 分派（见 :meth:`_export_job`）。
_EXPORT_ANNOTATED = "annotated"
_EXPORT_YOLO = "yolo"

#: 本页「导出YOLO标注」记忆文件里的两个键（与 ``store.ui_state`` 那份同名同义，
#: 但不是同一个文件：那边按任务记在 ``ui.json`` 里，这边按独立功能单独一份）。
_YOLO_EXPORT_DIR_KEY = "yolo_export_dir"
_YOLO_EXPORT_NAME_KEY = "yolo_export_name"
