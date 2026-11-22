"""任务列表页（首页）。

2026-11-22 按职责拆成子包（只搬不改）：

- widget.py          TaskListPage：信号、构造、收尾
- view.py            页头 / 搜索条 / 表格与空状态 / 底栏 / toast
- rows.py            数据刷新、过滤与分页渲染
- importing.py       创建任务（指纹/查重/建任务/后台导入）、聚合任务汇集与删除
- messages.py        导入查重弹窗文案
- constants.py       文案常量

⚠️ 本 ``__init__`` 只做重导出：既有 ``from desktop.pages.tasklist.page import X``
完全不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from qfluentwidgets import InfoBar

from desktop.pages.tasklist.page.constants import HEADER_SUBTITLE, STATUS_LABELS
from desktop.pages.tasklist.page.messages import _duplicate_message
from desktop.pages.tasklist.page.widget import TaskListPage

__all__ = ["HEADER_SUBTITLE", "STATUS_LABELS", "TaskListPage"]
