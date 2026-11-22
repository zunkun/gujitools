# -*- coding: utf-8 -*-
"""菜单动作的转发与窗口退出（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from typing import cast

from desktop.utils.files import default_open_dir

from ._qt import QApplication, QDialog, QFileDialog
from .constants import QUICK_TASK_PICK_TITLE

def _current_page(window):
    """当前页（壳层页面栈的 currentWidget）；窗口/壳层尚未就绪时返回 ``None``。

    ⚠️ 菜单是在 ``install_title_bar`` 里装的，那时 ``window.shell`` 还没建
    （见 ``desktop/app.py::MainWindow.__init__``），所以这里必须 ``getattr``
    现取、不能建菜单时就把页面钉住。
    """
    shell = getattr(window, "shell", None)
    pages = getattr(shell, "pages", None)
    return pages.currentWidget() if pages is not None else None


def _edit_hook(window, name: str):
    """当前页上名为 ``name`` 的可调用钩子；没实现/不可调时返回 ``None``。"""
    page = _current_page(window)
    hook = getattr(page, name, None)
    return hook if callable(hook) else None


def _can_edit_action(window, capability: str) -> bool:
    """某项编辑动作当前是否可点：问当前页（不认识的页面一律不可点）。"""
    probe = _edit_hook(window, f"can_edit_{capability}")
    return bool(probe()) if probe is not None else False


def _run_edit_action(window, capability: str) -> None:
    """执行某项编辑动作：转发给当前页自己的实现。"""
    action = _edit_hook(window, f"edit_{capability}")
    if action is not None:
        action()


#: 兼容旧名字（既有自测/文档按它断言「删除选中」的可用性）。
def _can_delete_selected(window) -> bool:
    return _can_edit_action(window, "delete_selected")


def _delete_selected(window) -> None:
    _run_edit_action(window, "delete_selected")


def open_quick_task(window) -> None:
    """「快速任务」：选一个 PDF，**随即建任务**（不再进创建页填名称/流程）。

    用户 2026-10-16：「菜单 文件下新增，快速任务选项，导入PDF，直接创建任务」。

    只做两件事——选文件、把路径交给 ``shell.quick_task()``；指纹/查重/建任务/
    进详情全走列表页那条**既有**链路（``start_create``），本模块不碰业务。

    ⚠️ 用**原生** ``QFileDialog``（不设 ``DontUseNativeDialog``）——项目硬规则：
    「资源管理器」指的是原生选择对话框。与 ``CreateTaskPanel._on_pick_pdf`` 同一款。
    ⚠️ 用户在对话框里按取消（返回空串）就**什么都不做**：尤其别当成"建一个
    空壳任务"——那是创建页「PDF 可留空」那条路的语义，与"快速任务"正好相反。
    """
    filename, _ = QFileDialog.getOpenFileName(
        window, QUICK_TASK_PICK_TITLE, str(default_open_dir()),
        "PDF/DjVu 文件 (*.pdf *.djvu *.djv)",
    )
    if not filename:
        return
    window.shell.quick_task(filename)


def _module_slot(window, key: str):
    """生成"点某个独立任务"的槽（吞掉 triggered 的 bool，理由见 ``build_file_menu``）。"""
    return lambda _checked=False: window.shell.show_module(key)


def quit_app(window) -> None:
    """「退出」：先收掉非模态子弹窗，再 ``window.close()``。

    ⚠️⚠️ **不能用 ``QApplication.quit()``**：它只退事件循环、**不触发**
    ``closeEvent``，而 QProcess 子进程与后台线程的收尾全挂在
    ``MainWindow.closeEvent``（→ ``shell.shutdown_workers()``）这条链上；
    绕过去就会出现 ``worker_host`` 里写的「QThread 运行中被析构 → Qt abort」。
    """
    app = QApplication.instance()
    if app is not None:
        # 强制告诉类型检查器，这是 QApplication 而不是 QCoreApplication
        app = cast(QApplication, app)
        for widget in app.topLevelWidgets():
            if (
                isinstance(widget, QDialog)
                and widget is not window
                and widget.isVisible()
            ):
                widget.close()
    window.close()
