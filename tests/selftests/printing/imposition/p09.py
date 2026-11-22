# -*- coding: utf-8 -*-
"""6b-2. 取图目录**内容**变了也要判旧（2026-10-22 用户报障） / 6c. 「勾了就算启用」：不要求已经有拼版页（用户 2026-10-03 报障） / 6c-2. 关掉启用开关 → 流程图**不再经过**拼版（用户 2026-10-23）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _bar_of
    from desktop.store import IMPOSITION_STAGE, TaskStore
    from desktop.services import imposition as S
    from tests.selftests._context import make_pdf, ok, pump
    from desktop.services.stale_chain import print_input_changed
    from desktop.services.stale_chain import print_input_changed

    ok("内容判旧：从未成功生成过 → 不判旧", not print_input_changed({}, "d|x"))
    ok(
        "内容判旧：老记录没有 source_mark → 不误判（宁可少提示）",
        not print_input_changed(
            {"print": [{"status": "success", "finished_at": 1.0,
                        "parameters": {"pdf_name": "print.pdf"}}]},
            "d|x",
        ),
    )
    ok(
        "内容判旧：取图目录内容标记不同 → 判旧",
        print_input_changed(
            {"print": [{"status": "success", "finished_at": 1.0,
                        "parameters": {"source_mark": "d|old"}}]},
            "d|new",
        ),
    )
    ok(
        "内容判旧：标记一致 → 不判旧",
        not print_input_changed(
            {"print": [{"status": "success", "finished_at": 1.0,
                        "parameters": {"source_mark": "d|same"}}]},
            "d|same",
        ),
    )

    # 页面上：上一轮 PDF 的 source_mark 与此刻不同 ⇒ 判旧、不再提供下载
    stale_run = st.repo.create_stage_run(
        st.tid,
        "print",
        {
            "pdf_name": "print.pdf",
            "source_stage": st.page.print_source_stage(),
            "source_mark": "C:\\gone\\rembg|(1, 1, 1)",
        },
    )
    st.repo.finish_stage(st.tid, stale_run, "success", str(st.print_dir))
    st.page._refresh_print_source()
    pump(st.ctx.app, times=4)
    ok(
        "取图内容变了（来源阶段没换）→ 判为旧数据",
        st.page._print_data_stale,
        f"data_stale={st.page._print_data_stale}",
    )
    ok(
        "内容判旧后当前可用 PDF 为空、下载按钮收起",
        st.page._current_print_pdf_path() is None
        and st.page.download_row.isHidden(),
        str(st.page._current_print_pdf_path()),
    )
    notice = st.page._regenerate_notice("print")
    ok(
        "状态行提示「取图里的图片已更新」",
        bool(notice) and "取图里的图片已更新" in notice,
        str(notice),
    )
    # 按**此刻**的取图内容重新生成过 ⇒ 恢复可用（清标脏）
    fresh_run = st.repo.create_stage_run(
        st.tid,
        "print",
        {
            "pdf_name": "print.pdf",
            "source_stage": st.page.print_source_stage(),
            "source_mark": st.page._print_source_mark_text(),
        },
    )
    st.repo.finish_stage(st.tid, fresh_run, "success", str(st.print_dir))
    st.page._refresh_print_source()
    pump(st.ctx.app, times=4)
    ok(
        "按当前取图内容生成过 → 不再判旧、PDF 恢复可用",
        not st.page._print_data_stale
        and st.page._current_print_pdf_path() is not None,
        f"data_stale={st.page._print_data_stale} "
        f"pdf={st.page._current_print_pdf_path()}",
    )
    st.page._save_imposition_pages([])
    # ⚠️ **别停合成定时器**：清空拼版页必须真的跑一轮合成（``compose_doc``
    # 见 pages=[] 会 ``_sweep_stale(dest, 0)`` 把 stages/imposition 收干净）。
    # 残留的 0001.png 会让第四步把上一轮的图当成本轮结果——这正是
    # "启用后不按拼版来"的另一种形态，必须由真实路径清掉。
    st.page._compose_imposition_async()
    for _ in range(60):
        pump(st.ctx.app, times=2)
        if not st.page._imposition_composing and not st.page._imposition_dirty:
            break
    pump(st.ctx.app, times=6)
    stale_pngs = sorted(st.repo.imposition_output_dir(st.tid).glob("*.png"))
    ok(
        "清空拼版页后：产物目录被一并收干净（不拿上一轮的图当结果）",
        stale_pngs == [],
        str([p.name for p in stale_pngs]),
    )
    st.page._set_imposition_checked(False)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok(
        "（前置）未启用：取图 = 去底色",
        st.page.print_source_dir() == st.rembg_dir and not st.page.imposition_active(),
    )
    st.page._set_imposition_checked(True)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok("勾了启用（还没拼页）→ 判定为已启用", st.page.imposition_active())
    # ⚠️ 2026-10-18 口径：流程条上那一格表达的是"这一步处理到哪了"——判据是
    #    **本节点有没有拼版页**，不是这个开关（开关是**流程级**的，图上
    #    「是否拼版」网关问的就是它）。所以"勾了但还没拼页"时节点不该亮。
    ok(
        "勾了启用但还没拼页 → 流程条节点**不亮**（开关≠这一格的进度）",
        st.page.step_bar.imposition_node.badge._status != "success",
        f"badge={st.page.step_bar.imposition_node.badge._status}",
    )
    _imp_node = st.page.step_bar.imposition_node

    def _imp_segments():
        front = back = None
        for seg in st.page.step_bar._connector_segments():
            if seg[1] is _imp_node:
                front = seg
            elif seg[0] is _imp_node:
                back = seg
        return front, back

    ok(
        "启用但还没拼页 → 主线经过拼版（流向 = 启用，不画绕行）",
        st.page.step_bar._optional_flow[0] is True,
        f"flow={st.page.step_bar._optional_flow}",
    )
    st.page._save_imposition_pages(
        [{"items": S.single_items(str(st.a))}]  # 一页单图，制造"处理过"
    )
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    ok(
        "（前置）有了拼版页：徽标转绿勾、主线仍经过拼版",
        _imp_node.badge._status == "success"
        and st.page.step_bar._optional_flow[0] is True,
        f"badge={_imp_node.badge._status} "
        f"flow={st.page.step_bar._optional_flow}",
    )
    st.page._set_imposition_checked(False)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    front, back = _imp_segments()
    ok(
        "关掉启用开关 → 流程图走绕行线（不再经过拼版）",
        st.page.step_bar._optional_flow[0] is False
        and st.page.step_bar._bypass_points() is not None
        and front is not None and not front[2] and front[3]
        and back is not None and not back[2] and back[3],
        f"flow={st.page.step_bar._optional_flow} "
        f"bypass={st.page.step_bar._bypass_points()} front={front} back={back}",
    )
    ok(
        "关掉启用开关 → 徽标仍是绿勾（这一格确实处理过，与流向分开）",
        _imp_node.badge._status == "success" and _imp_node.is_selected(),
        f"badge={_imp_node.badge._status} selected={_imp_node.is_selected()}",
    )
    ok(
        "关掉启用开关 → 第四步取图回到上一步（去底色）",
        st.page.print_source_dir() == st.rembg_dir,
        str(st.page.print_source_dir()),
    )
    # 收尾：把这一页清掉，后面「启用但没拼页」的断言依赖空清单
    st.page._save_imposition_pages([])
    st.page._compose_imposition_async()
    for _ in range(60):
        pump(st.ctx.app, times=2)
        if not st.page._imposition_composing and not st.page._imposition_dirty:
            break
    st.page._set_imposition_checked(True)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok(
        "勾了启用（还没拼页）→ 第四步取图已切到 stages/imposition",
        st.page.print_source_dir() == st.repo.imposition_output_dir(st.tid),
        str(st.page.print_source_dir()),
    )
    ok(
        "启用与有无产物分两层：已启用但还没有页",
        st.page.imposition_active() and not st.page.imposition_has_pages(),
    )
    ok(
        "启用但没拼页时列表为空（而不是悄悄回退去底色）",
        st.page._print_entries()[0] == [],
        str([e["file"] for e in st.page._print_entries()[0]]),
    )
    ok(
        "启用但没拼页时状态行说清「没有拼版页」而不是「未生效」",
        "拼版已启用" in st.page.imposition_panel_status.text()
        and "没有拼版页" in st.page.imposition_panel_status.text(),
        st.page.imposition_panel_status.text(),
    )
    # 点「生成 PDF」必须给**拼版专属**提示，不能把人引去第三步
    toasts2: list = []
    real_toast2 = st.page._toast
    st.page._toast = lambda *a, **k: toasts2.append(a)
    try:
        st.page._select_stage(_bar_of(st.page, "print"))
        pump(st.ctx.app, times=4)
        st.page._run_stage_unchecked(False)
    finally:
        st.page._toast = real_toast2
    ok(
        "启用但没拼页时生成 PDF → 提示去拼版（不是回第三步）",
        any("拼版" in str(t) and "选择拼版" in str(t) for t in toasts2),
        str(toasts2),
    )
    # 拼一页 → "有产物"成立（同一判据下只是进度变了）
    st.page._select_stage(_bar_of(st.page, IMPOSITION_STAGE))
    pump(st.ctx.app, times=4)
    st.page._save_imposition_pages(
        [
            {
                "items": [
                    {"file": str(st.a), "rect": [0, 0, 200, 600], "rotation": 0.0},
                    {"file": str(st.b), "rect": [200, 0, 200, 600], "rotation": 0.0},
                ],
            }
        ]
    )
    st.page._imposition_timer.stop()
    st.page._compose_imposition_now()
    pump(st.ctx.app, times=4)
    ok(
        "拼上一页后：有产物成立、来源仍是拼版",
        st.page.imposition_has_pages()
        and st.page.print_source_dir() == st.repo.imposition_output_dir(st.tid),
    )
    # ⚠️ 恢复**两页**基线：6c 只拼了一页，而第 7 节的「上一页/下一页」用例
    # 需要能翻到第二页。别让这段的临时状态漏给后面。
    st.page._save_imposition_pages(
        [
            {
                "items": [
                    {"file": str(st.a), "rect": [0, 0, 200, 600], "rotation": 0.0},
                    {"file": str(st.b), "rect": [200, 0, 200, 600], "rotation": 0.0},
                ]
            },
            {
                "items": [
                    {"file": str(st.c), "rect": [0, 0, 200, 600], "rotation": 0.0},
                    {"file": str(st.d), "rect": [200, 0, 200, 600], "rotation": 0.0},
                ]
            },
        ]
    )
    st.page._imposition_timer.stop()
    st.page._compose_imposition_now()
    st.page.imposition_view.set_current(0)
    pump(st.ctx.app, times=4)
    ok(
        "（恢复）两页拼版就位，供第 7 节继续",
        len(st.page._imposition_pages()) == 2 and st.page.imposition_active(),
        f"pages={len(st.page._imposition_pages())} "
        f"active={st.page.imposition_active()}",
    )

