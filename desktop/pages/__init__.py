"""桌面端页面层：按页面分子包，每个页面一个目录。

- tasklist/    任务列表页（首页）
- taskdetail/  任务详情页（骨架 + 按职责拆分的控制器 Mixin）

导入一律使用自顶向下的绝对路径，不使用相对导入，例如：

    from desktop.pages.taskdetail.page import TaskDetailPage
"""

from desktop.pages.taskdetail.page import TaskDetailPage
from desktop.pages.tasklist.page import TaskListPage

__all__ = ["TaskDetailPage", "TaskListPage"]
