# -*- coding: utf-8 -*-
"""创建任务页 / 快速任务 / 流程编辑页。"""

from __future__ import annotations

from pathlib import Path


class CreateFlowMixin:
    """创建任务页与任务流程编辑页的切页。"""

    # ------------------------------------------------------- 创建任务 / 流程编辑
    def create_page(self):
        """创建任务页（惰性构造；外部截图/自测按这个属性取）。"""
        if self._create_page is None:
            from desktop.pages.createtask.page import CreateTaskPage

            page = CreateTaskPage(self.store)
            # 取消/返回 → 回列表；建任务由列表页的既有链路处理（它要算指纹、查重）
            page.closed.connect(self.back_to_list)
            # 提交 → 列表页走既有链路（指纹/查重/预热都在那边，一字未改）
            page.create_requested.connect(self._on_create_submitted)
            # 聚合任务提交 → 列表页建聚合任务（无指纹/查重：不吃源文件）
            page.aggregate_requested.connect(self._on_aggregate_submitted)
            # ⚠️ 聚合成员表格的「详情」**不再**由壳层切详情页（用户 2026-11-17）：
            #    那个按钮现在开一个非模态预览窗（`CreateTaskPage.open_member_preview`），
            #    创建到一半的表单不该被路由跳走。
            self.pages.addWidget(page)
            self._create_page = page
        return self._create_page

    def _on_create_submitted(self, path: str, name: str, diagram) -> None:
        """创建页填完了 → 交给列表页建任务（建完它发 open_detail 进详情）。"""
        self.list_page.start_create(path, name, diagram)

    def _on_aggregate_submitted(self, members: list, member_stages: list,
                                name: str, diagram) -> None:
        """聚合任务填完了 → 列表页建聚合任务（建完进详情）。"""
        self.list_page.start_create_aggregate(
            members, member_stages, name, diagram
        )

    def open_create(self) -> None:
        """打开「创建任务」二级页（列表页的「创建任务」按钮走这里）。

        ⚠️ **每次进入都复位**（用户 2026-10-06："上一次创建任务信息没有清理"）：
        本页是**惰性单例**（建一次就长期留着），不复位的话上一次填的任务名、
        选的 PDF、勾的「自定义流程」、编过的流程图全都留在界面上——第二次
        建任务等于接着上一次半途而废的表单继续填。
        """
        page = self.create_page()
        # ⚠️ 复位放在"已经在这一页"判断**之前**：连着点两次「创建任务」，
        #    第二次该把第一次填的清掉，而不是因为"没换页"就跳过。
        page.reset()
        self.pages.setCurrentWidget(page)
        if self.pages.currentWidget() is page:
            self._sync_nav_to_page(0)

    def quick_task(self, path: str) -> None:
        """「快速任务」（菜单 文件 → 快速任务）：拿一个 PDF **直接建任务**。

        用户 2026-10-16：「导入PDF，直接创建任务」——省掉创建页那三步（选 PDF、
        填名称、看/编流程）。

        复用列表页那条**既有**链路（``start_create``：指纹 → 查重 → 建任务 →
        进详情页），本方法只喂参数：

        - **任务名 = PDF 文件名**（``Path(path).stem``，用户 2026-10-16：
          「快速任务，任务名称为PDF 文件名称默认」）。与创建页选完 PDF 后
          ``_autofill_name`` 自动填进去的那一份**完全一致**（那边也是取 stem，
          不带 ``.pdf``）；想改名去详情页页头的铅笔按钮。
        - ``diagram=None`` ⇒ 用默认流程模板（字节拷贝）。

        ⚠️ 唯一"少做"的一步是**不经过创建任务页**；**查重那道闸仍会弹**——同一个
        PDF 已经建过任务时再建第二个，多半是误操作，不该因为"快速"就跳过。
        """
        name = Path(path).stem
        self.list_page.start_create(str(path), name, None)

    def flow_page(self):
        """任务流程编辑页（惰性构造）。"""
        if self._flow_page is None:
            from desktop.pages.taskflow.page import TaskFlowPage

            page = TaskFlowPage(self.store)
            page.closed.connect(self._back_from_flow)
            page.flow_saved.connect(self._on_flow_saved)
            page.aggregate_start_changed.connect(
                self._on_aggregate_start_changed
            )
            self.pages.addWidget(page)
            self._flow_page = page
        return self._flow_page

    def open_flow(self, task_id: str) -> None:
        """打开某个任务的流程编辑页（详情页页头按钮走这里）。"""
        page = self.flow_page()
        if not page.open_task(task_id):
            self._toast_flow_error(task_id)
            return
        self.pages.setCurrentWidget(page)
        if self.pages.currentWidget() is page:
            self._sync_nav_to_page(0)

    def _toast_flow_error(self, task_id: str = "") -> None:
        """流程页打不开时的提示：**回列表 + 真的弹一条**。

        ⚠️ 这个方法名叫 ``_toast_*`` 却只 ``show_tasks()`` —— 用户点「查看 /
        编辑流程」后页面直接跳回列表，既没有提示也没有解释，看起来就是"点了
        没反应"。⚠️ 壳层**没有**自己的 ``_toast``，借详情页的。
        """
        self.show_tasks()
        page = getattr(self, "_detail_page", None)
        reason = ""
        if task_id and page is not None and page.store is not None:
            reason = page.store.flow_degraded_reason(task_id)
        detail = f"：{reason}" if reason else "，请稍后重试或重新进入任务。"
        toast = getattr(page, "_toast", None)
        if callable(toast):
            toast(
                "warning", "打不开流程图",
                f"这个任务的流程读不出来{detail}",
            )

    def _back_from_flow(self) -> None:
        """流程页「返回」→ 回该任务的详情页（没打开过任务就回列表）。"""
        task_id = getattr(self._flow_page, "_task_id", None)
        if task_id:
            self.open_detail(task_id)
        else:
            self.show_tasks()

    def _on_flow_saved(self, task_id: str) -> None:
        """流程保存后回详情页并**重载**（步骤条/槽位/取图来源要按新图重排）。"""
        self.open_detail(task_id)

    def _on_aggregate_start_changed(self, task_id: str) -> None:
        """聚合任务**改了起始节点**：旧起点汇集的数据已作废，立刻按新起点重取。

        用户 2026-11-18：「起始节点可以切换变更，如果变更了保存流程的时候，
        提示起始节点丢失，聚合任务之前历史处理数据都丢失」——确认之后这条
        链路就是"丢失"的落地：旧产物被新起点的成员产物覆盖（见
        ``services/aggregate_ingest``），不重取的话详情页那一步永远是空的。

        ⚠️ 这两步的顺序（先 open_detail 再起汇集）是有意的：详情页必须停在
        这个任务上（``restart_aggregate_ingest`` 只对当前任务生效），而它起来
        之前立好 ``.aggregate-pending`` 标记，页面才能说"正在汇集"而不是
        "没有输入"。
        """
        page = self._ensure_detail_page()
        if getattr(page, "task_id", None) != task_id:
            self.open_detail(task_id)
        restart = getattr(page, "restart_aggregate_ingest", None)
        if callable(restart):
            restart(task_id)
