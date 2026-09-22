# -*- coding: utf-8 -*-
"""任务列表的搜索 + 分页护栏。

分两段：

1. **纯逻辑**（``Pager``，不碰 Qt）——切片区间、页码钳制、末页删空回退、
   换每页条数时的页码换算。这些是算错就会「白屏/跳页」的地方。
2. **行为**（走一遍真实页面）——每页 10 条、翻页、搜索过滤、跨页定位
   ``focus_task``、末页越界回退。

⚠️ 页码越界是最容易漏的一类：删掉末页唯一一条、或搜索后结果变少，
原页码就超出新的总页数，直接切片会得到空列表、界面变成空白页。
``Pager.clamped_page`` 为此存在，这里用行为断言钉住它真的生效了。

⚠️ 本模块**不得清空 store**：``tasklist`` 建的 ``ctx.tid`` / ``ctx.tid_dup``
是后续模块的依赖根。页面级行为一律用**合成行**灌进 ``_all_rows`` 再
``_render()``，不落盘；唯一的真实 store 用例只增删自己建的那几条，
并在 finally 里调 ``page.refresh()`` 还原界面。
"""

import time

NAME = "tasklist_pagination"
DEPENDS: list[str] = []
TITLE = "任务列表：搜索 + 分页"

# 合成任务数：够跨 3 页（10/页）且末页不满，能测到边界
FAKE_TOTAL = 25


def _fake_rows(n: int) -> list[dict]:
    """造 n 条合成任务行（只喂界面，不落盘）。"""
    return [
        {
            "id": f"fake-{i:03d}",
            "name": f"分页样本{i:02d}",
            "source_path": f"D:/books/sample-{i:02d}.pdf",
            "created_at": time.time() - i * 60,
            "stages": [],
        }
        for i in range(n)
    ]


def run(ctx) -> None:
    from tests.selftests._context import ok, wait_until

    from desktop.components.pagination import (
        DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, Pager,
    )
    from desktop.pages.tasklist.page import TaskListPage

    # ---------------------------------------------------------------- 纯逻辑
    ok("默认每页 10 条", DEFAULT_PAGE_SIZE == 10, str(DEFAULT_PAGE_SIZE))
    ok("每页条数候选项含 10", 10 in PAGE_SIZE_OPTIONS, str(PAGE_SIZE_OPTIONS))

    p = Pager(25, 10, 1)
    ok("25 条 / 每页 10 → 3 页", p.total_pages == 3, str(p.total_pages))
    ok("第 1 页切片 [0,10)", p.slice_bounds() == (0, 10), str(p.slice_bounds()))
    ok("第 3 页切片 [20,25)（末页不满）",
       p.with_page(3).slice_bounds() == (20, 25),
       str(p.with_page(3).slice_bounds()))
    # 「序号」列现在显示**任务自己的编号**（0001 / fake-001 …），不再是
    # 「页内行号 + 全局偏移」：任务号与排序/搜索/翻页无关，用户按号找
    # tasks/<号> 目录才对得上。
    ok("Pager 不再提供「全局行号」入口（序号列改用任务号）",
       not hasattr(Pager, "first_index"))

    ok("页码超过总页数时钳制", p.with_page(99).clamped_page == 3,
       str(p.with_page(99).clamped_page))
    ok("页码小于 1 时钳制", p.with_page(0).clamped_page == 1)
    ok("越界页码不会切出空页",
       len(p.with_page(99).page_slice(list(range(25)))) == 5,
       str(p.with_page(99).slice_bounds()))

    # 末页删空：21 条在第 3 页（只有 1 条），删到 20 条后必须回第 2 页
    ok("删掉末页最后一条后页码回退",
       Pager(21, 10, 3).with_total(20).clamped_page == 2,
       str(Pager(21, 10, 3).with_total(20).clamped_page))
    ok("0 条时仍算 1 页（避免显示「第 1 / 0 页」）",
       Pager(0, 10, 1).total_pages == 1)
    ok("0 条时切片为空且不越界", Pager(0, 10, 1).page_slice([]) == [])

    # 换每页条数：第 3 页第 21~30 条 → 每页 50 后应落在第 1 页，而不是第 3 页
    ok("每页 10→50 时页码按比例回落到第 1 页",
       Pager(100, 10, 3).with_page_size(50).clamped_page == 1,
       str(Pager(100, 10, 3).with_page_size(50).clamped_page))
    ok("每页条数非法时兜底为默认", Pager(25, 0, 1).page_size == DEFAULT_PAGE_SIZE)

    # ------------------------------------------------------------------ 行为
    page = ctx.w.list_page
    ok("页面暴露分页渲染与跨页定位入口",
       hasattr(TaskListPage, "_render") and hasattr(TaskListPage, "focus_task"),
       "缺少 _render / focus_task")

    def feed(rows: list[dict], keyword: str = "", page_no: int = 1) -> None:
        """把合成行灌进页面并重渲染（不落盘）。"""
        page._all_rows = rows
        page._keyword = keyword
        page._page = page_no
        page._render()

    try:
        feed(_fake_rows(FAKE_TOTAL))
        ok("第 1 页只渲染 10 行",
           page.table.table.rowCount() == 10,
           str(page.table.table.rowCount()))
        ok("分页条显示共 25 条", "共 25 条" in page.pagination.total_label.text(),
           page.pagination.total_label.text())
        ok("分页条显示第 1 / 3 页",
           page.pagination.page_label.text() == "第 1 / 3 页",
           page.pagination.page_label.text())
        ok("第 1 页时上一页禁用", not page.pagination.prev_btn.isEnabled())
        ok("第 1 页时下一页可用", page.pagination.next_btn.isEnabled())

        def col0() -> list[str]:
            return [
                page.table.table.item(r, 0).text()
                for r in range(page.table.table.rowCount())
            ]

        ok("第 1 页序号列 = 前 10 条任务号（不是 1..10 的行号）",
           col0() == [f"fake-{i:03d}" for i in range(10)], str(col0()))

        # ---- 翻页 ----
        page._on_page_changed(2)
        ok("第 2 页序号列 = 后 10 条任务号（翻页不改任务号）",
           col0() == [f"fake-{i:03d}" for i in range(10, 20)], str(col0()))
        ok("第 2 页页码显示正确",
           page.pagination.page_label.text() == "第 2 / 3 页",
           page.pagination.page_label.text())

        page._on_page_changed(3)
        ok("第 3 页只剩 5 行（25 - 20）",
           page.table.table.rowCount() == 5,
           str(page.table.table.rowCount()))
        ok("末页时下一页禁用", not page.pagination.next_btn.isEnabled())

        # ---- 跨页定位：目标在第 3 页，从第 1 页跳过去 ----
        target_id = page._filtered[23]["id"]
        page._on_page_changed(1)
        ok("切回第 1 页后目标确实不在本页",
           all(r["id"] != target_id for r in page._filtered[:10]),
           "测试数据与假设不符")
        ok("focus_task 能跨页定位", page.focus_task(target_id))
        ok("定位后停在第 3 页",
           page.pagination.page_label.text() == "第 3 / 3 页",
           page.pagination.page_label.text())

        # ---- 搜索：模糊匹配 ----
        page.search_edit.setText("分页样本0")
        ok("搜索命中 10 条（样本00..09）",
           len(page._filtered) == 10, str(len(page._filtered)))
        ok("搜索后重置到第 1 页",
           page.pagination.page_label.text() == "第 1 / 1 页",
           page.pagination.page_label.text())
        ok("搜索后表格只剩命中行",
           page.table.table.rowCount() == 10,
           str(page.table.table.rowCount()))
        ok("提示文案显示 匹配/总数",
           "匹配 10 / 25" in page.hint_label.text(),
           page.hint_label.text())
        # 任务名由单元格里的 QLabel 呈现（item 文本留空，避免和标签重影）
        from PySide6.QtWidgets import QLabel

        names = [
            page.table.table.cellWidget(r, 1).findChildren(QLabel)[0].text()
            for r in range(page.table.table.rowCount())
        ]
        ok("命中行都是匹配项", all("分页样本0" in n for n in names), str(names[:3]))

        # 大小写不敏感：源文件名是大写后缀，用小写去搜
        page.search_edit.setText("sample-01.pdf")
        ok("可按源文件名搜索", len(page._filtered) == 1, str(len(page._filtered)))
        page.search_edit.setText("SAMPLE-01.PDF")
        ok("搜索大小写不敏感", len(page._filtered) == 1, str(len(page._filtered)))

        # 无命中 → 空状态
        page.search_edit.setText("绝不可能存在的任务名xyz")
        ok("无命中时过滤结果为空", len(page._filtered) == 0)
        ok("无命中时切到空状态卡片",
           page.content_stack.currentIndex() == 1,
           str(page.content_stack.currentIndex()))

        page.search_edit.setText("")
        ok("清空搜索后恢复 25 条", len(page._filtered) == FAKE_TOTAL)
        ok("清空后回到表格卡片", page.content_stack.currentIndex() == 0)

        # ---- 末页越界：停在第 3 页，把总数降到 20 ----
        page._on_page_changed(3)
        feed(_fake_rows(20), page_no=3)
        ok("总数降到 20 后页码自动回退到第 2 页（不白屏）",
           page.pagination.page_label.text() == "第 2 / 2 页",
           page.pagination.page_label.text())
        ok("回退后仍有 10 行", page.table.table.rowCount() == 10,
           str(page.table.table.rowCount()))

        # ---- 每页条数 ----
        page._on_page_size_changed(50)
        ok("每页 50 时 20 条只占 1 页",
           page.pagination.page_label.text() == "第 1 / 1 页",
           page.pagination.page_label.text())
        ok("每页 50 时渲染 20 行", page.table.table.rowCount() == 20,
           str(page.table.table.rowCount()))
        page._on_page_size_changed(10)
        ok("改回每页 10 条", page._page_size == 10)

        # ---- 真实 store 打通：refresh() 必须能重建 _all_rows 并分页 ----
        store = page.store
        before = len(store.list_tasks())
        mine = [
            store.create_task(ctx.pdf, f"hash-page-{i}", f"真数据样本{i:02d}")
            for i in range(12)
        ]
        try:
            page.refresh()
            # refresh 是异步的（后台线程读盘），等 _all_rows 追上再断言
            wait_until(
                ctx.app,
                lambda: len(page._all_rows) == before + 12,
                timeout=5.0,
            )
            ok("refresh() 后总数含新增的 12 条",
               len(page._all_rows) == before + 12,
               f"{len(page._all_rows)} vs {before + 12}")
            ok("真实数据下每页仍只渲染 10 行",
               page.table.table.rowCount() == 10,
               str(page.table.table.rowCount()))
        finally:
            for tid in mine:
                store.delete_task(tid)
    finally:
        # 还原界面：清空搜索、回到第 1 页，并按真实 store 重建
        page.search_edit.blockSignals(True)
        page.search_edit.setText("")
        page.search_edit.blockSignals(False)
        page._keyword = ""
        page._page = 1
        page._page_size = DEFAULT_PAGE_SIZE
        page.refresh()
        # refresh 是异步的：等后台读盘落地再断言，否则读到的还是旧集合
        wait_until(
            ctx.app,
            lambda: len(page._all_rows) == len(page.store.list_tasks()),
            timeout=5.0,
        )

    ok("收尾后界面回到真实任务集合",
       len(page._all_rows) == len(page.store.list_tasks()),
       f"{len(page._all_rows)} vs {len(page.store.list_tasks())}")
