# -*- coding: utf-8 -*-
"""任务列表页的数据刷新、过滤与分页渲染。"""

from __future__ import annotations

from PySide6.QtCore import QThread

from desktop.components.pagination import Pager
from desktop.components.task_table import task_row_matches
from desktop.workers import TaskRowsWorker, connect_queued


class TaskListRowsMixin:
    """从 store 读全量行并渲染当前页（搜索只重渲染，不读盘）。"""

    # ------------------------------------------------------------------ 数据
    def refresh(self) -> None:
        """刷新任务行：**读盘放后台线程**，读完回主线程渲染。

        ⚠️ 读盘不能占着 UI 线程：这里要遍历全部任务、逐个读它的 runs.json
        （任务一多就是几十次文件 IO），同步做会把已经画出来的窗口卡住。行的
        组装挪进了 ``TaskRowsWorker``，结果走 ``_on_rows_ready`` 回来渲染。

        ⚠️ 每次刷新带一个**代际令牌**：连续调用（导入任务后紧跟着又刷新）会让
        多个 worker 并发跑，先发的可能后回来，把新数据盖成旧的——只认最后
        一次发出的那个令牌，其余结果直接丢弃。
        """
        token = object()
        self._refresh_token = token
        self.run_worker(
            lambda: TaskRowsWorker(self.store),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.completed,
                    lambda rows, t=token: self._on_rows_ready(t, rows),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda message, t=token: self._on_rows_failed(t, message),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_rows_ready(self, token, rows: list) -> None:
        """后台读完 → 主线程：更新缓存，再走过滤/分页/填表（过期结果丢弃）。"""
        if token is not self.__dict__.get("_refresh_token"):
            return
        self._all_rows = rows
        self._render()
        # 列表行已经画出来了，这时候才放后台的复制/缩略图开工——否则它们
        # 会和上面这几个读盘动作抢 GIL，新行要等 0.5~2.5s 才出现
        self._thumb_queue.release()

    def _on_rows_failed(self, token, message: str) -> None:
        """读失败（任务目录被删/权限不足等）：保留原列表，别把界面清空。"""
        if token is not self.__dict__.get("_refresh_token"):
            return
        print(f"任务列表刷新失败：{message}")
        self._thumb_queue.release()  # 列表虽然没画成，后台活也不能一直扣着

    # ------------------------------------------------------- 过滤 / 分页渲染
    @staticmethod
    def _matches(row: dict, keyword: str) -> bool:
        """模糊匹配：任务名或源文件名（不含目录）包含关键词，大小写不敏感。

        实现在 ``components/task_table.task_row_matches``——聚合任务「选择
        子任务」弹窗用同一份判据，别在这里再抄一份。
        """
        return task_row_matches(row, keyword)

    def _render(self) -> None:
        """过滤 → 分页 → 填表，并同步空状态、分页条与提示文案。

        只依赖缓存的 ``_all_rows``，不读盘，所以搜索时可以逐字符调用。

        ⚠️ **必须在 GUI 线程执行**：``set_data`` 会给每个单元格创建控件
        （任务名标签 / 状态胶囊 / 详情删除按钮）。跨线程装单元格控件时 Qt 只会
        刷一行 ``QObject::setParent: Cannot set parent, new parent is in a
        different thread`` 然后**拒绝设父**——控件于是留在顶层，被 show 出来
        就会变成一个个独立小窗（标题 ``__main__``，内容是行内的任务名、
        「详情 / 删除」按钮），每次刷新再多一批，并且表格行在、格子是空的。
        （用户 2026-11-28 报的就是这个：弹窗越来越多、"感觉是表格的一部分被
        拆开了"、"显示不全"。）

        根因已在 ``importing.py::_start_import`` 修掉（worker 信号改走
        ``connect_queued``）。这里再兜一道：真被别的线程调到，就把自己排队
        回 GUI 线程，绝不带病填表。
        """
        if QThread.currentThread() is not self.thread():
            self._render_requested.emit()
            return
        keyword = self._keyword.strip()
        self._filtered = [r for r in self._all_rows if self._matches(r, keyword)]

        pager = Pager(len(self._filtered), self._page_size, self._page)
        # ⚠️ 页码可能越界（删了末页最后一条 / 搜索后结果变少），
        #    一律用钳制后的页码算切片，否则会渲染出空白页。
        self._page = pager.clamped_page
        page_rows = pager.page_slice(self._filtered)

        # 「序号」列由任务自己的编号填充（表格从 rows 里的 id 取），与分页无关
        self.table.set_data(page_rows)
        self.pagination.set_pager(pager)
        has_rows = bool(page_rows)
        self.content_stack.setCurrentIndex(0 if has_rows else 1)

        total = len(self._all_rows)
        if keyword and total != len(self._filtered):
            self.hint_label.setText(f"匹配 {len(self._filtered)} / {total} 个任务")
        elif keyword:
            self.hint_label.setText(f"匹配 {len(self._filtered)} 个任务")
        else:
            self.hint_label.setText("")

        self.tip_label.setText(
            f"共 {total} 个任务 · 数据目录 {self.store.root}"
            if total
            else f"数据目录 {self.store.root}"
        )

    def focus_task(self, task_id: str) -> bool:
        """翻到任务所在页并选中它；不在当前过滤结果里则返回 False。

        ⚠️ 分页后不能直接用 ``table.select_task``：任务可能不在当前页，
        表格里根本没有那一行。要先按**过滤后**的下标算出页码、切过去，
        再在表格里选中。
        """
        index = next(
            (i for i, r in enumerate(self._filtered) if r["id"] == task_id), None
        )
        if index is None:
            return False
        self._page = index // self._page_size + 1
        self._render()
        return self.table.select_task(task_id)

    # ------------------------------------------------------------ 搜索 / 分页
    def _on_keyword_changed(self, text: str) -> None:
        """搜索框变化：重置到第 1 页再渲染（否则会停在越界的旧页码上）。"""
        self._keyword = text or ""
        self._page = 1
        self._render()

    def _on_page_changed(self, page: int) -> None:
        self._page = page
        self._render()

    def _on_page_size_changed(self, page_size: int) -> None:
        """换每页条数时按当前页第一条换算页码，别让用户看着列表乱跳。"""
        pager = Pager(len(self._filtered), self._page_size, self._page)
        self._page = pager.with_page_size(page_size).page
        self._page_size = page_size
        self._render()
