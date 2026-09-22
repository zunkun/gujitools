"""桌面端页面层：按页面分子包，每个页面一个目录。

- tasklist/    任务列表页（首页）
- taskdetail/  任务详情页（骨架 + 按职责拆分的控制器 Mixin）

导入一律使用自顶向下的绝对路径，不使用相对导入，例如：

    from desktop.pages.taskdetail.page import TaskDetailPage

⚠️ **TaskDetailPage 刻意不在这里立即导入**：它自身及其子模块（第四步的
print_form / print_panel 等参数面板）合计约占 GUI 启动时间的 19%，而用户
双击图标时看到的只是任务列表页，详情页要等他点开某个任务才需要。所以改用
PEP 562 的模块级 ``__getattr__``，属性首次被访问时才真正导入。旧写法
``from desktop.pages import TaskDetailPage`` 依然可用，只是变懒了。
"""

from desktop.pages.tasklist.page import TaskListPage

__all__ = ["TaskDetailPage", "TaskListPage"]


def __getattr__(name: str):
    """属性兜底：惰性导入详情页（PEP 562）。"""
    if name == "TaskDetailPage":
        from desktop.pages.taskdetail.page import TaskDetailPage

        return TaskDetailPage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
