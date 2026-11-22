# -*- coding: utf-8 -*-
"""7. 面板动作：复位 / 删除 / 「上一页/下一页」：翻页在中间编辑区底部右侧（用户 2026-09-30） / 7b. 拖动排序与「✕」释放图片 / 7b-2. 「删除选中图片」+ 单图页「新增图片」"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _names
    from pathlib import Path
    from desktop.services import imposition as S
    import desktop.components.imposition.picker as _picker_mod
    import qfluentwidgets as _qw
    from tests.selftests._context import make_pdf, ok, pump
    import sys
    st.page._set_imposition_checked(True)
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    st.page.imposition_view.canvas.select(0)
    st.page.imposition_view.canvas.rotate_selected(90.0)
    st.page._imposition_timer.stop()
    ok(
        "画布旋转选中图作用到版面",
        abs(st.page.imposition_view.current_items()[0]["rotation"] - 90.0) < 0.01,
        str(st.page.imposition_view.current_items()[0]["rotation"]),
    )

    st.page._on_imposition_reset_layout()
    st.page._imposition_timer.stop()
    reset_items = st.page._imposition_pages()[0]["items"]
    ok(
        "「复位本页版面」把两张图恢复成默认并排（尺寸回原始、旋转归零）",
        [item["rotation"] for item in reset_items] == [0.0, 0.0]
        and reset_items[1]["rect"][:2] == [0.0, 0.0]
        and reset_items[0]["rect"][0] == reset_items[1]["rect"][2],
        str(reset_items),
    )
    ok("复位后画布也同步了", st.page.imposition_view.current_items() == reset_items)
    nav_seen: list[int] = []
    st.page.imposition_view.page_selected.connect(nav_seen.append)
    ok(
        "第一页：「上一页」禁用、「下一页」可用",
        not st.page.imposition_view.prev_button.isEnabled()
        and st.page.imposition_view.next_button.isEnabled(),
    )
    st.page.imposition_view.next_button.click()
    st.page._imposition_timer.stop()
    ok(
        "「下一页」切到第二页（与左列点选同一条路径）",
        st.page.imposition_view.current_index() == 1 and nav_seen == [1],
        f"current={st.page.imposition_view.current_index()} nav={nav_seen}",
    )
    ok(
        "末页：「下一页」禁用、「上一页」可用",
        not st.page.imposition_view.next_button.isEnabled()
        and st.page.imposition_view.prev_button.isEnabled(),
    )
    st.page.imposition_view.prev_button.click()
    st.page._imposition_timer.stop()
    ok(
        "「上一页」切回第一页",
        st.page.imposition_view.current_index() == 0 and nav_seen == [1, 0],
        f"current={st.page.imposition_view.current_index()} nav={nav_seen}",
    )
    st.page.imposition_view.page_selected.disconnect(nav_seen.append)
    st.page._on_imposition_page_reorder(1, 0)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    reordered = st.page._imposition_pages()
    ok(
        "拖动排序：原第二页变第一页（顺序即 PDF 页序）",
        len(reordered) == 2
        and Path(reordered[0]["items"][0]["file"]).name == "2-r.png"
        and Path(reordered[1]["items"][0]["file"]).name == "1-r.png",
        str([Path(i["items"][0]["file"]).name for i in reordered]),
    )
    ok(
        "左列页码标签随新顺序重建（第几页同步）",
        [e.title_label.text() for e in st.page.imposition_view.page_list.entries()]
        == ["第一页", "第二页"],
    )
    ok(
        "画布落到拖动后的那一页",
        st.page.imposition_view.current_index() == 0,
        str(st.page.imposition_view.current_index()),
    )
    st.page._on_imposition_page_reorder(1, 0)  # 拖回去，恢复原顺序
    st.page._imposition_timer.stop()

    st.before_release = st.page._imposition_pages()
    st.page._on_imposition_release_page(0)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    remaining = _names(
        S.remaining_files(st.page.imposition_source_files(), st.page._imposition_doc())
    )
    ok(
        "「✕」删掉该页，另一页保留",
        len(st.page._imposition_pages()) == 1
        and Path(st.page._imposition_pages()[0]["items"][0]["file"]).name == "2-r.png",
    )
    ok(
        "被释放的两张回到未选择列表",
        "1-r.png" in remaining and "1-l.png" in remaining,
        str(remaining),
    )
    st.page._save_imposition_pages(st.before_release)
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    pump(st.ctx.app, times=4)
    st.page._save_imposition_pages(st.before_release)
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    pump(st.ctx.app, times=4)
    st.page.imposition_view.canvas.select(1)  # 选中左槽「1-l」
    st.page._on_imposition_delete_item()
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    kept = st.page._imposition_pages()
    ok(
        "「删除选中图片」：页保留、只删被选中的那一张",
        len(kept) == 2
        and len(kept[0]["items"]) == 1
        and Path(kept[0]["items"][0]["file"]).name == "1-r.png",
        str([[Path(i["file"]).name for i in p["items"]] for p in kept]),
    )
    ok(
        "删完后面板出现「新增图片」（单图页），画布选中清空",
        not st.page.imposition_panel.add_image_button.isHidden()
        and st.page.imposition_view.selected_slot() < 0
        and st.page.imposition_view.current_index() == 0,
    )
    # 删掉单图页的最后一张图：页整个消失（空页没有意义）——另一页保留，
    # 仍是生效态；把剩余页也删光才回退去底色。
    # （2026-09-30 用户定：删最后一张=整页移除，要弹确认框——真实弹窗是
    # 模态的，测试里不能 exec，用替身同 picker 套路，可编排确认/取消）
    import qfluentwidgets as _qw

    _real_dialog = _qw.Dialog

    class _FakeConfirm:
        result = 1  # 1=确认，0=取消
        asked = []

        def __init__(self, title, content, parent=None):
            _FakeConfirm.asked.append((title, content))

            class _Btn:
                def setText(self, text):
                    pass

            self.yesButton = _Btn()
            self.cancelButton = _Btn()

        def exec(self):
            return _FakeConfirm.result

    _qw.Dialog = _FakeConfirm

    st.page.imposition_view.canvas.select(0)
    _FakeConfirm.result = 0  # 先试「取消」
    st.page._on_imposition_delete_item()
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    ok(
        "删最后一张弹确认框、点「取消」：页保留不动",
        len(st.page._imposition_pages()) == 2
        and [Path(i["file"]).name for i in st.page._imposition_pages()[0]["items"]]
        == ["1-r.png"]
        and _FakeConfirm.asked[-1][0] == "删除图片"
        and "整页拼版" in _FakeConfirm.asked[-1][1],
        f"pages={[[Path(i['file']).name for i in p['items']] for p in st.page._imposition_pages()]} "
        f"asked={_FakeConfirm.asked}",
    )

    st.page.imposition_view.canvas.select(0)
    _FakeConfirm.result = 1  # 「删除」
    st.page._on_imposition_delete_item()
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    ok(
        "删掉单图页最后一张：页一并删除，另一页保留（仍是生效态）",
        len(st.page._imposition_pages()) == 1
        and [Path(i["file"]).name for i in st.page._imposition_pages()[0]["items"]]
        == ["2-r.png", "2-l.png"]
        and st.page.imposition_view.current_index() == 0
        and st.page.imposition_active()
        and st.page.print_source_dir() != st.rembg_dir,
        f"pages={[[Path(i['file']).name for i in p['items']] for p in st.page._imposition_pages()]} "
        f"cur={st.page.imposition_view.current_index()} "
        f"active={st.page.imposition_active()}",
    )
    # 把最后一页的两张也删光：全部页清空。
    # ⚠️ 口径（用户 2026-10-03）：**删光只是"没有可拼的图"，不等于"未启用"**
    # ——拼版仍启用，所以取图来源仍指向 stages/imposition（此时是空目录），
    # 第四步会提示先去拼版。早先这里断言"回退去底色"，那是"启用还要额外
    # 满足有拼页"的旧口径，正是用户报的"启用不生效"的根源。
    st.page.imposition_view.canvas.select(0)
    st.page._on_imposition_delete_item()
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    st.page.imposition_view.canvas.select(0)
    st.page._on_imposition_delete_item()
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    ok(
        "删光全部图片：页清空，但仍保持启用（取图来源不退回去底色）",
        st.page._imposition_pages() == []
        and st.page.imposition_view.current_index() == -1
        and not st.page.imposition_has_pages()
        and st.page.imposition_active()
        and st.page.print_source_dir() == st.repo.imposition_output_dir(st.tid),
        f"pages={st.page._imposition_pages()} "
        f"cur={st.page.imposition_view.current_index()} "
        f"active={st.page.imposition_active()} "
        f"has_pages={st.page.imposition_has_pages()} "
        f"src={st.page.print_source_dir()} vs {st.rembg_dir}",
    )
    _qw.Dialog = _real_dialog  # 恢复真实弹窗

    # 单图页「新增图片」：append 弹窗替身返回 1 张右半幅「2-r」
    # ——原图是左半幅「1-l」→ 新图进右槽、贴在原图右边（原图版面不动）
    single_left = S.single_items(str(st.b))  # 1-l（左半幅，GREEN）
    assert single_left is not None  # ⚠️ 传的是存在的图，必然造得出单项
    st.page._save_imposition_pages([{"items": single_left}])
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    pump(st.ctx.app, times=4)
    ok(
        "单图页进入后面板露出「新增图片」",
        not st.page.imposition_panel.add_image_button.isHidden(),
    )
    import desktop.components.imposition.picker as _picker_mod

    _real_picker = _picker_mod.ImpositionPickerDialog

    class _FakeAppend:
        """替身弹窗：固定返回一张图（append 模式只放行 1 张）。"""

        def __init__(self, picked):
            self._picked = picked
            import sys

            print("PROBE fake picker constructed", file=sys.stderr)

        def exec(self):
            return 1

        def picked_files(self):
            return self._picked

    # ⚠️ 赋给弹窗槽位的必须是**可调用对象**（工厂），不能是替身实例——
    # 控制器拿到的是 `ImpositionPickerDialog(...)` 调用形式。
    _picker_mod.ImpositionPickerDialog = lambda *a, **k: _FakeAppend(
        [str(st.c)]
    )  # 2-r
    try:
        st.page.imposition_panel.add_image_button.click()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
        merged = st.page._imposition_pages()
        ok(
            "左半幅原图 + 新增右半幅：新图进右槽、贴原图右边",
            len(merged) == 1
            and len(merged[0]["items"]) == 2
            and Path(merged[0]["items"][0]["file"]).name == "2-r.png"
            and Path(merged[0]["items"][1]["file"]).name == "1-l.png"
            and merged[0]["items"][0]["rect"][0]
            == merged[0]["items"][1]["rect"][0] + 400.0
            and merged[0]["items"][1]["rect"] == single_left[0]["rect"],
            str([[Path(i["file"]).name for i in p["items"]] for p in merged]),
        )
    finally:
        _picker_mod.ImpositionPickerDialog = _real_picker

    # 原图是右半幅「1-r」：新增「2-l」进左槽、贴原图左边
    st.page._save_imposition_pages([{"items": S.single_items(str(st.a))}])
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    pump(st.ctx.app, times=4)
    _picker_mod.ImpositionPickerDialog = lambda *a, **k: _FakeAppend(
        [str(st.d)]
    )  # 2-l
    try:
        st.page.imposition_panel.add_image_button.click()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
        merged = st.page._imposition_pages()
        ok(
            "右半幅原图 + 新增左半幅：新图进左槽、贴原图左边",
            len(merged) == 1
            and len(merged[0]["items"]) == 2
            and Path(merged[0]["items"][0]["file"]).name == "1-r.png"
            and Path(merged[0]["items"][1]["file"]).name == "2-l.png"
            and merged[0]["items"][1]["rect"][0] == -400.0,
            str([i["rect"] for i in merged[0]["items"]]),
        )
    finally:
        _picker_mod.ImpositionPickerDialog = _real_picker
    st.page._save_imposition_pages(st.before_release)
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    pump(st.ctx.app, times=4)

