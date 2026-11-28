# -*- coding: utf-8 -*-
"""导入链路的**线程归属**守卫：UI 回调必须回到 GUI 线程。

背景（2026-11-28 用户截图报障）：导入 PDF 之后桌面上不断冒出小窗——标题
``__main__``、内容是任务列表行里的东西（任务名 / 「详情·删除」按钮），一次
比一次多；同时表格"显示不全"（行在，格子是空的）。

根因是**跨线程填表**：

1. ``HashWorker.finished`` 在 worker 子线程 emit；
2. 它连的是 ``_hash_ready``——一个定义在 **mixin（普通 Python 类）**上的
   ``@Slot``。这种接收者在 PySide6 下没能按"主线程 QObject"排队，回调直接
   跑在子线程里；
3. 于是 ``refresh() → _render() → TaskTable.set_data()`` 整条链在子线程，
   ``set_data`` 给每个单元格新建控件（名字标签 / 状态胶囊 / 操作按钮）。
   Qt 拒绝把子线程创建的控件挂到表格视口，只刷一行
   ``QObject::setParent: Cannot set parent, new parent is in a different
   thread``，控件于是留在顶层、被 show 成独立小窗，每导入一次多一批。

修法：worker 信号一律走 ``connect_queued``（见 ``importing.py::_start_import``），
再加 ``_render`` 的 GUI 线程守卫兜底。本模块钉住三条不变量：

1. **运行时实证**：真跑 ``_start_import``，``TaskTable.set_data`` 每次都在
   GUI 线程；跑完没有游离小窗；
2. **界面结果正确**：新行真的出现在表格里（不是"行在格空"）；
3. **静态防回归**：``importing.py`` 不许再把 worker 信号裸连到 ``_hash_ready``。
"""

NAME = "import_thread_affinity"
DEPENDS: list[str] = ["tasklist"]
TITLE = "导入回调的线程归属（跨线程填表＝游离小窗）"

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def run(ctx) -> None:
    import time

    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication

    from desktop.components import task_table as task_table_module
    from tests.selftests._context import ok, wait_until

    app, w, repo = ctx.app, ctx.w, ctx.repo
    page = w.list_page
    queue = page._thumb_queue
    src = ctx.pdf

    gui_thread = app.thread()
    before_ids = {t["id"] for t in repo.list_tasks()}

    def hash_idle() -> bool:
        """指纹线程是否已收尾（``_hash_thread_done`` 会 deleteLater ⇒ 可能已删）。"""
        try:
            return page.hash_thread is None or not page.hash_thread.isRunning()
        except RuntimeError:  # C++ 侧已销毁
            return True

    def strays(baseline: set) -> list:
        """本次导入**新冒出来**的游离窗口（详情/删除按钮）。

        ⚠️ 必须只认新增的：前面的用例（聚合任务）会把自己的弹窗留在屏幕上，
        拿"当前所有顶层窗口"当判据必然误报。
        """
        from qfluentwidgets import PushButton

        found = []
        for widget in QApplication.topLevelWidgets():
            if widget is w or not widget.isVisible() or id(widget) in baseline:
                continue
            texts = [b.text() for b in widget.findChildren(PushButton)]
            if "详情" in texts or "删除" in texts:
                found.append((widget.windowTitle(), texts[:3]))
        return found

    # ---- 运行时实证：真起 HashWorker 线程跑完整条导入链 ----
    calls: list[bool] = []
    real_set_data = task_table_module.TaskTable.set_data

    def spy_set_data(self, rows):
        calls.append(QThread.currentThread() is gui_thread)
        return real_set_data(self, rows)

    real_confirm = page._confirm_duplicate
    page._confirm_duplicate = lambda path, dups: True  # 同文件重复导入不弹模态
    task_table_module.TaskTable.set_data = spy_set_data
    created: list[str] = []
    baseline_tops = {id(x) for x in QApplication.topLevelWidgets()}
    try:
        page._start_import(src)
        ok("指纹线程收尾", wait_until(app, hash_idle, timeout=60.0))
        ok("后台导入也跑完", wait_until(app, lambda: not queue.busy(), timeout=120.0))
        # 让排队回主线程的 refresh/_render 事件都落地
        deadline = time.time() + 10
        while time.time() < deadline and not calls:
            app.processEvents()
            time.sleep(0.02)

        created = [t["id"] for t in repo.list_tasks() if t["id"] not in before_ids]
        ok("导入后建出了任务", len(created) == 1, str(created))
        # ⚠️ 不能拿"行数 +1"当判据：前面的模块会删任务、列表还停在上次渲染的
        #    行数上；而且分页会把行数钉在 page_size。只看"新任务进了缓存"。
        ok("新任务出现在列表里（不是建了不显示）",
           wait_until(
               app,
               lambda: any(r.get("id") in created for r in page._all_rows),
               timeout=20.0,
           ),
           f"缓存行数={len(page._all_rows)}")
        table = page.table.table
        # 症状就是"行在、格是空的"：每行的名字列（第 1 列）必须有控件
        empty_rows = [
            r for r in range(table.rowCount()) if table.cellWidget(r, 1) is None
        ]
        ok("每行都装上了单元格控件（不是「行在格空」）",
           empty_rows == [], f"空行={empty_rows}")
        ok("填表确实发生过", bool(calls), f"set_data 调用 {len(calls)} 次")
        ok("每一次填表都在 GUI 线程（否则单元格控件会变成游离小窗）",
           all(calls), f"逐次是否主线程 = {calls}")
        ok("没有游离的「详情/删除」小窗",
           strays(baseline_tops) == [], str(strays(baseline_tops)))
        ok("导入用的中继已回收（不随导入次数累积）",
           list(page._hash_relays) == [], str(page._hash_relays))

        # ---- 第二次导入：`hash_thread` 引用必须已清空 ----
        # 用户 2026-11-28「再导入一次就报错」：`_hash_thread_done` 只 deleteLater
        # 不清属性，下次 start_create 的守卫 `.isRunning()` 撞上已删 C++ 对象，
        # 抛 `RuntimeError: Internal C++ object already deleted`。
        second_error: Exception | None = None
        try:
            page.start_create(str(src), "", None)
        except Exception as exc:  # noqa: BLE001 - 就是要抓住它
            second_error = exc
        ok("第二次导入不抛「C++ object already deleted」",
           second_error is None, repr(second_error))
        ok("第二次导入的线程也能收尾",
           wait_until(app, hash_idle, timeout=60.0))
        ok("第二次导入的后台活也跑完",
           wait_until(app, lambda: not queue.busy(), timeout=120.0))
        more = [t["id"] for t in repo.list_tasks()
                if t["id"] not in before_ids and t["id"] not in created]
        ok("第二次导入也建出了任务", len(more) == 1, str(more))
        created.extend(more)
    finally:
        task_table_module.TaskTable.set_data = real_set_data
        page._confirm_duplicate = real_confirm
        # 清场：先等后台把副本/缩略图干完，再删任务，别让 worker 撞上已删目录
        wait_until(app, lambda: not queue.busy(), timeout=120.0)
        for tid in created:
            repo.delete_task(tid)
        wait_until(app, hash_idle, timeout=30.0)

    # ---- 静态防回归：worker 信号必须经 connect_queued 回主线程 ----
    source = (ROOT / "desktop" / "pages" / "tasklist" / "page" / "importing.py").read_text(
        encoding="utf-8"
    )
    ok("hash worker 的信号不再裸连 mixin 回调",
       ".finished.connect(self._hash_ready)" not in source
       and ".failed.connect(self._hash_failed)" not in source)
    ok("hash worker 走 connect_queued 中继",
       "self.hash_worker.finished, self._hash_ready" in source
       and "self.hash_worker.failed, self._hash_failed" in source)
