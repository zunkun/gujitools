"""任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。

2026-11-22 起由单文件拆成子包，对外导入路径
``desktop.pages.taskdetail.print_list`` 与名字完全不变。
"""

from __future__ import annotations

from desktop.pages.taskdetail.print_list.constants import PRINT_WARM_DELAY_MS
from desktop.pages.taskdetail.print_list.entries import PrintEntriesMixin
from desktop.pages.taskdetail.print_list.manage import PrintManageMixin
from desktop.pages.taskdetail.print_list.pdf import PrintPdfMixin
from desktop.pages.taskdetail.print_list.thumbs import PrintThumbsMixin
from desktop.utils.files import book_key

__all__ = [
    "PRINT_WARM_DELAY_MS",
    "PrintListMixin",
    "book_key",
]


class PrintListMixin(
    PrintThumbsMixin,
    PrintEntriesMixin,
    PrintManageMixin,
    PrintPdfMixin,
):
    """依赖宿主页面提供的属性：store/task_id、print_preview、log_view、
    _toast()。"""
