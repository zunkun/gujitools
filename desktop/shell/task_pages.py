# -*- coding: utf-8 -*-
"""任务列表 / 详情页的切换与预热。"""

from __future__ import annotations

from PySide6.QtCore import QProcess


class TaskPagesMixin:
    """任务列表页与惰性详情页的切换。"""

    def show_tasks(self) -> None:
        """切回任务列表页并刷新列表。

        ⚠️ 不去手动 ``setCurrentItem``：切页会触发 ``pages.currentChanged``
        → :meth:`_sync_nav_to_page` 统一同步高亮，单点维护不易漏。
        """
        # 返回列表：详情页是**常驻实例**（下次还要复用），但预览区那些
        # 大图/缩略图位图没必要留在内存里（用户 2026-11-21「离开就释放」）。
        # 释放的是可重建的位图；清单、当前页、暂存在离开前已落盘。
        if self._detail_page is not None:
            self._detail_page.release_stage_buffers()
        self.pages.setCurrentWidget(self.list_page)
        self.list_page.refresh()

    @property
    def detail_page(self):
        """任务详情页（惰性构造）。

        保留这个名字：``tests/selftests/_context.py``
        按 ``window.detail_page`` 取页面来操作控件（原来在 MainWindow 上，
        现在壳层转发一层，外部契约不变）。
        """
        return self._ensure_detail_page()

    def _ensure_detail_page(self):
        """首次需要时建详情页、挂进栈并接「返回」信号（同 app.py 原实现）。"""
        if self._detail_page is None:
            from desktop.pages import TaskDetailPage

            page = TaskDetailPage(self.store)
            page.back_requested.connect(self.back_to_list)
            # 详情页页头「查看/编辑流程」→ **切到流程编辑页**（不再是弹窗）
            page.flow_edit_requested.connect(self.open_flow)
            self.pages.addWidget(page)
            self._detail_page = page
        return self._detail_page

    def _on_aggregate_ready(self, task_id: str) -> None:
        """聚合汇集完成：详情页正开着这个任务就重载一次。

        ⚠️ 只在**同一任务**上重载：用户可能已经切去别的任务/别的页面，这时
        抢着切回详情页是打扰。重载走 ``set_task``（它会复位各阶段面板并重读
        页面清单），与"重新点进这一行"完全等价。
        """
        page = self._detail_page
        if page is None:
            return
        if getattr(page, "task_id", None) != task_id:
            return
        page.set_task(task_id)

    def prewarm_detail_page(self) -> None:
        """预构造详情页骨架与**流程第一步**面板（同 app.py 原 ``_prewarm_detail_page``）。"""
        page = self._ensure_detail_page()
        # ⚠️ 按 **step key** 查，不写死 ``widget(0)``：预热的是"用户最先会看到的
        #    那一步"，自定义流程第一步可以是「检测文本框」而不是「提取图片」
        #    （``widget(0)`` 恒是**静态步骤表**的第一格）。没有任务时
        #    ``panel_host_of_step`` 走默认流程兜底，行为与旧写法一致。
        step = page.flow_entry_step()
        first = page.panel_host_of_step(step) if step else None
        if first is None:
            return
        if hasattr(first, "peek") and first.peek() is None:
            first.panel  # noqa: B018 - 触发构造，返回值不用

    def open_detail(self, task_id: str) -> None:
        """打开某个任务的详情页（行为与 ``app.py::_open_detail`` 一致）。

        ⚠️ 顺带把「PDF 渲染子进程池」**预热**一次（见
        ``pdf_render_service.prewarm``）：那套池首次建起来要 ~1.5s，不预热就
        会砸在"用户看到的第一张缩略图"上。预热在后台线程做、幂等、不阻塞。
        """
        self._prewarm_pdf_renderer()
        page = self._ensure_detail_page()
        if page.set_task(task_id):
            self.pages.setCurrentWidget(page)
        else:
            busy = page.running_stage is not None or (
                page.process is not None
                and page.process.state() != QProcess.ProcessState.NotRunning
            )
            if busy:
                self.pages.setCurrentWidget(page)
            # ⚠️⚠️ **别静默丢**（2026-10-06 用户报障"编辑流程后顶部流程图没更新"）：
            #    ``set_task`` 返回 False 的原因只有两个——任务不存在，或**正在
            #    跑步骤**（见 ``set_task`` 开头的守卫）。前一种已由 ``get_task``
            #    兜住，后一种**原来什么都不做**：用户从流程页保存回来，被留在流程
            #    页上，详情页的步骤条还是旧流程；等他"重新进入"才更新，全然不知
            #    刚才那次保存其实没落到界面上。这里明确提示，并把详情页显示出来
            #    （至少让他看到旧流程 + 一句解释，而不是停在流程编辑页）。
            #⚠️ 不弹 MessageBox 打断，直接把详情页切出来 + toast 说明。
            self.pages.setCurrentWidget(page)
            if not busy:
                page._toast(
                    "info", "流程已保存",
                    "本任务的流程已保存，但详情页未能重载（请稍后重进任务查看）。",
                )
            self.list_page.refresh()

    def _prewarm_pdf_renderer(self) -> None:
        """把 PDF 渲染子进程池预热一次（幂等；失败无害）。

        ⚠️ 延迟导入：``pdf_render_service`` 在**首次真要渲染**时才 import
        pymupdf 相关的东西，这里只碰它的池（不影响启动路径的导入量）。
        """
        if self._render_prewarmed:
            return
        self._render_prewarmed = True
        try:
            from desktop.workers import pdf_render_service

            pdf_render_service.prewarm()
        except Exception:  # noqa: BLE001 - 预热是加速，失败就按需建池
            pass

    def back_to_list(self) -> None:
        """详情页「返回」→ 切回列表并刷新。"""
        self.show_tasks()
