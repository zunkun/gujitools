# -*- coding: utf-8 -*-
"""检测结果统计自测：第二步右侧按页形态分类统计（总览/明细两级）。

钉住四件事：
1. 分类规则（`utils.box_geometry.classify_page_slots`）：整幅=单槽、
   半幅=双槽齐全、单独页=双槽缺一侧、无框=无文本框；
2. 第二步右侧显示「检测结果统计」，且**「执行记录」整体隐藏**（用户
   2026-09-29 定：detect 无表单参数，历史回填没有用武之地）；其它步骤
   反过来；
3. 总览计数与明细页码：点分类看页码，点页码跳转预览；
4. 人工编辑框（拖动/删框）后统计实时重算。

放在 print 之后跑（同 detect_boxes），避免改写 boxes.json 影响上游断言；
结束前把 boxes.json 原样还原。
"""

NAME = "detect_stats"
DEPENDS: list[str] = ["print"]
TITLE = "检测结果统计"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok
    from utils.box_geometry import (
        PAGE_CLASS_EMPTY, PAGE_CLASS_FULLCONTENT, PAGE_CLASS_HARFCONTENT,
        PAGE_CLASS_SINGLE, classify_page_slots,
    )

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    # ---- 1. 纯分类规则（槽位约定，过滤 None 会误判，必须喂槽位） ----
    ok("整幅=单槽", classify_page_slots([[0, 0, 10, 10]]) == PAGE_CLASS_FULLCONTENT)
    ok("半幅=双槽齐全",
       classify_page_slots([[0, 0, 10, 10], [20, 0, 30, 10]]) == PAGE_CLASS_HARFCONTENT)
    ok("单独页=双槽缺一侧",
       classify_page_slots([[0, 0, 10, 10], None]) == PAGE_CLASS_SINGLE)
    ok("无文本框=空/全空槽",
       classify_page_slots([]) == PAGE_CLASS_EMPTY
       and classify_page_slots([None, None]) == PAGE_CLASS_EMPTY
       and classify_page_slots(None) == PAGE_CLASS_EMPTY)

    d.set_task(tid)
    pages = d._manifest_paths()
    ok("存在页面清单（≥4 页）", len(pages) >= 4, str(len(pages)))
    if len(pages) < 4:
        return

    # boxes.json 先备份，测完还原（本测试改写的条目不该影响后续断言）
    boxes_path = repo.boxes_path(tid)
    backup = boxes_path.read_text(encoding="utf-8") if boxes_path.exists() else None
    try:
        # 造四类页：整幅 1 / 半幅 0（验证 0 页分类不显示）/ 单独页 2 / 其余无框
        repo.save_detect_boxes(tid, pages[0].stem, [[0, 0, 100, 100]], origin="auto")
        repo.save_detect_boxes(tid, pages[1].stem, [[0, 0, 100, 100], None], origin="auto")
        repo.save_detect_boxes(tid, pages[2].stem, [None, [200, 0, 300, 100]], origin="auto")
        d.detect_cache.clear()

        # ---- 2. 步骤专属区块的可见性 ----
        d._select_stage(1)
        app.processEvents()
        ok("第二步隐藏「执行记录」", not d.history_block.isVisibleTo(d))
        ok("第二步显示「检测结果统计」", d.detect_stats.isVisibleTo(d))
        d._select_stage(0)
        app.processEvents()
        ok("其它步骤恢复「执行记录」", d.history_block.isVisibleTo(d))
        ok("其它步骤隐藏统计", not d.detect_stats.isVisibleTo(d))
        d._select_stage(1)
        app.processEvents()

        # ---- 3. 总览计数 + 明细页码 + 跳转 ----
        texts = {k: b.text() for k, b in d.detect_stats.class_buttons.items()}
        # 文案是「<分类> · <N> 页」：必须 endswith 整段比对，"1 页" 会是
        # "11 页" 的子串（页数两位数时误判）
        ok("整幅计数 1 页", texts[PAGE_CLASS_FULLCONTENT].endswith("1 页"),
           texts[PAGE_CLASS_FULLCONTENT])
        # 0 页的分类不显示（用户 2026-09-29：左右双栏/左右单栏为 0 时不占位）
        ok("半幅 0 页不显示",
           d.detect_stats.class_buttons[PAGE_CLASS_HARFCONTENT].isHidden(),
           texts[PAGE_CLASS_HARFCONTENT])
        ok("单独页计数 2 页", texts[PAGE_CLASS_SINGLE].endswith("2 页"),
           texts[PAGE_CLASS_SINGLE])
        ok("无框计数 = 页数-3",
           texts[PAGE_CLASS_EMPTY].endswith(f"{len(pages) - 3} 页"),
           texts[PAGE_CLASS_EMPTY])

        d.detect_stats.show_detail(PAGE_CLASS_SINGLE)
        app.processEvents()
        ok("单独页明细 2 条", d.detect_stats.page_list.count() == 2)
        rows: list[int] = []
        d.detect_stats.page_clicked.connect(rows.append)
        item = d.detect_stats.page_list.item(0)
        d.detect_stats.page_list.itemClicked.emit(item)
        app.processEvents()
        ok("明细页码携带行号", rows == [1], str(rows))
        ok("点页码跳转预览", d.detect_viewer.strip.currentRow() == 1,
           str(d.detect_viewer.strip.currentRow()))

        # 总览级联刷新：打开着明细时数据变了也要同步（批量检测实时刷新走这条路）
        d.detect_stats.show_detail(PAGE_CLASS_SINGLE)
        repo.save_detect_boxes(tid, pages[3].stem, [[0, 0, 100, 100], None], origin="auto")
        d._refresh_detect_stats()
        ok("明细打开时刷新同步", d.detect_stats.page_list.count() == 3,
           str(d.detect_stats.page_list.count()))

        # 打开着的分类被清空 → 自动退回总览（0 页分类不显示的连带行为）
        d.detect_stats.set_results(len(pages), {})
        ok("分类清空后退回总览", d.detect_stats.stack.currentIndex() == 0
           and d.detect_stats.back_button.isHidden())

        # ---- 4. 人工编辑框 → 统计实时重算 ----
        # 第 4 页刚被写成单独页；删掉它的框（人工）后应回到「无文本框」。
        # 注意 _save_manual_boxes 存半幅恒 2 槽：空框列表 → []（无文本框）。
        d._save_manual_boxes(str(pages[3]), [])
        texts = {k: b.text() for k, b in d.detect_stats.class_buttons.items()}
        ok("人工删框后无框计数复原",
           texts[PAGE_CLASS_EMPTY].endswith(f"{len(pages) - 3} 页"),
           texts[PAGE_CLASS_EMPTY])
    finally:
        if backup is None:
            boxes_path.unlink(missing_ok=True)
        else:
            boxes_path.write_text(backup, encoding="utf-8")
        d.detect_cache.clear()
        d._refresh_detect_stats()
