# -*- coding: utf-8 -*-
"""独立拼图页同一条实体链（真入口 + 后台 worker） / 批量删除（回归钉子） / 弹出瞬间的连点防护 + 宿主点击静音（2026-11-15 用户报） / 6b. 列表胶囊 + 「旧数据不显示」（用户 2026-10-03）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import GREEN, RED, _bar_of, _names, _px_near
    from desktop.store import IMPOSITION_STAGE, TaskStore
    from desktop.modules.imposition.page import ImpositionModulePage
    from pathlib import Path
    from desktop.services import imposition as S
    from desktop.store import IMPOSITION_STAGE, STAGE_SHORT
    from desktop.workers.task_rows_worker import TaskRowsWorker
    from PySide6.QtTest import QTest as _QTest
    from PySide6.QtCore import Qt as _Qt
    import desktop.components.imposition.confirm_delete as _icdel
    import time as _time
    from tests.selftests._context import make_pdf, ok, pump
    from desktop.services.stale_chain import print_source_switched
    from desktop.modules.imposition.page import ImpositionModulePage

    _mod = ImpositionModulePage()
    try:
        _mod._doc = {
            "enabled": True,
            "pages": [S.make_page([st.a, st.b])],
            "removed": [],
        }
        _mod._refresh_view()  # 建条目并触发实体生成（真入口）
        _mgr = _mod._page_thumb_manager()
        _mdir = _mgr.directory
        for _ in range(240):  # 等后台把 page1.jpg 生成并贴回
            _mentry = _mod.view.page_list.entries()[0]
            if (
                _mdir / "page1.jpg"
            ).is_file() and not _mentry.thumb.pixmap().isNull():
                break
            st.ctx.app.processEvents()
            _time.sleep(0.05)
        _mentry = _mod.view.page_list.entries()[0]
        _mimg = _mentry.thumb.pixmap().toImage()
        ok(
            "独立拼图页：实体落盘 page1.jpg + 左列 = 页面效果（两半各一张图）",
            (_mdir / "page1.jpg").is_file()
            and _px_near(_mimg, _mimg.width() // 4, _mimg.height() // 2, GREEN)
            and _px_near(_mimg, _mimg.width() * 3 // 4, _mimg.height() // 2, RED),
            f"size={(_mimg.width(), _mimg.height())} dir={_mdir}",
        )
        _first = _mgr.pixmap_for(0, _mod._doc["pages"][0])
        _again = _mgr.pixmap_for(0, _mod._doc["pages"][0])
        ok(
            "独立拼图页：版面没动 ⇒ 命中回**同一个** QPixmap（不重生成不重读盘）",
            _first is not None and _first is _again,
        )
        _mod._doc["pages"][0]["items"][0]["rect"][0] += 11.0
        _moved = _mgr.pixmap_for(0, _mod._doc["pages"][0])
        ok(
            "独立拼图页：版面动了 ⇒ 排队重生成（不拿旧图充数）",
            _moved is None and 0 in _mgr._pending,
            f"moved-null={_moved is None}",
        )
        # ---- 单步操作后防抖单页更新（2026-10-09）----
        _mkey = _mentry._thumb_key
        _mitems = [dict(it) for it in _mod._doc["pages"][0]["items"]]
        _mitems[0] = {**_mitems[0], "rect": [500.0, *_mitems[0]["rect"][1:]]}
        _mod._on_items_changed(0, _mitems)
        ok(
            "独立拼图页：版面改动攒页号等防抖（不立刻重灌）",
            _mod._thumb_dirty_pages == {0} and _mod._thumb_timer.isActive(),
        )
        _mod._thumb_timer.stop()
        _mod._refresh_dirty_page_thumbs()
        for _ in range(240):  # 等这一页的实体重生成并贴回
            if _mentry._thumb_key != _mkey:
                break
            st.ctx.app.processEvents()
            _time.sleep(0.05)
        ok(
            "独立拼图页：防抖到期**单页**重生成实体并贴回",
            _mentry._thumb_key != _mkey,
        )
    finally:
        try:
            _mod.shutdown_workers()
        except RuntimeError:
            pass
        _mod.deleteLater()
    st._pages_backup = [dict(p) for p in st.page._imposition_pages()]
    for _e in st.page.imposition_view.page_list.entries():
        _e.set_checked(True)
    import desktop.components.imposition.confirm_delete as _icdel

    # 确认框**本体**（2026-10-26 用户报）：此前底座是 qfluentwidgets 的
    # ``MessageBoxBase``（``MaskDialogBase``），它 ``setWindowFlags(
    # FramelessWindowHint)`` 把窗口降级成主窗口里的**子控件遮罩**——
    # 实机上点「删除」不生效、系统提示音"当当当"响（整个被模态禁用的
    # 窗口树收不到点击）。这里钉住"真窗口 + 点删除能 accept"，替身
    # 弹窗管不到这段。
    _confirm = _icdel.BatchDeleteConfirmDialog(
        [(0, st._pages_backup[0])], st.page,
    )
    ok(
        "批量删除确认框是**真窗口**（不是遮罩子控件）",
        _confirm.isWindow() and _confirm.isModal(),
        f"isWindow={_confirm.isWindow()} modal={_confirm.isModal()}",
    )
    ok(
        "批量删除确认框：固定 520 宽、按钮文案与旧版一致",
        _confirm.width() == _icdel.DIALOG_W
        and _confirm.yesButton.text() == "删除"
        and _confirm.cancelButton.text() == "取消",
        f"{_confirm.width()} {_confirm.yesButton.text()}",
    )
    _confirm.yesButton.click()
    ok(
        "批量删除确认框：点「删除」= accept（实机点不动的回归）",
        bool(_confirm.result()),  # 1 = QDialog.Accepted
        f"result={_confirm.result()}",
    )
    _confirm.deleteLater()
    pump(st.ctx.app, times=2)
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtTest import QTest as _QTest

    _confirm2 = _icdel.BatchDeleteConfirmDialog([(0, st._pages_backup[0])], st.page)
    _confirm2.show()
    pump(st.ctx.app, times=1)
    ok(
        "确认框刚弹出：落在弹窗上的点击先被吞（连点不会替用户按按钮）",
        _confirm2._armed is False,
        f"armed={_confirm2._armed}",
    )
    _QTest.mouseClick(_confirm2.yesButton, _Qt.MouseButton.LeftButton)
    ok(
        "保护期内点「删除」不生效（也就不会误删）",
        _confirm2.result() == 0,
        f"result={_confirm2.result()}",
    )
    for _ in range(60):  # 等 _ARM_MS 到期（上限 1.2s，别死等）
        if _confirm2._armed:
            break
        st.ctx.app.processEvents()
        _time.sleep(0.02)
    ok(
        "过了保护期点击照常生效（不重犯「点删除没反应」）",
        _confirm2._armed is True,
        f"armed={_confirm2._armed}",
    )
    _QTest.mouseClick(_confirm2.yesButton, _Qt.MouseButton.LeftButton)
    ok(
        "解除防连点后点「删除」= accept",
        bool(_confirm2.result()),
        f"result={_confirm2.result()}",
    )
    _confirm2.close()
    pump(st.ctx.app, times=2)
    ok(
        "确认框关掉后撤掉宿主点击静音（原生过滤器不残留）",
        _confirm2._mute._filter is None,
        str(_confirm2._mute._filter),
    )
    _confirm2.deleteLater()
    pump(st.ctx.app, times=2)

    class _FakeConfirmDialog:
        def __init__(self, items, parent=None):
            self.items = list(items)

        def exec(self):
            return 1

    _real_confirm = _icdel.BatchDeleteConfirmDialog
    _icdel.BatchDeleteConfirmDialog = _FakeConfirmDialog
    _log_at = len(st.page.log_view.toPlainText())
    try:
        st.page._on_imposition_batch_delete()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
    finally:
        _icdel.BatchDeleteConfirmDialog = _real_confirm
    ok(
        "批量删除：确认后真删了页、清单一空",
        len(st.page._imposition_pages()) == 0
        and len(st.page.imposition_view.page_list.entries()) == 0,
    )
    _tail = st.page.log_view.toPlainText()[_log_at:]
    ok(
        "批量删除：日志列出被删页码（回归：曾引用未定义变量直接崩）",
        "已批量删除 2 页拼版（第 1、2 页）" in _tail,
        _tail[-160:],
    )
    # 恢复两页：后面的取图来源/旧数据断言都建立在"拼版已生效"之上
    st.page._save_imposition_pages(st._pages_backup)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok(
        "批量删除回归用例收尾：页清单已恢复（2 页）",
        len(st.page._imposition_pages()) == 2
        and len(st.page.imposition_view.page_list.entries()) == 2,
    )

    ok("拼版生效", st.page.imposition_active())
    ok(
        "第四步取图目录切到 stages/imposition",
        st.page.print_source_dir() == st.repo.imposition_output_dir(st.tid),
        str(st.page.print_source_dir()),
    )

    # 同步合成一次（点「生成 PDF」前走的就是这条），产物可查
    st.page._compose_imposition_now()
    produced = sorted(st.repo.imposition_output_dir(st.tid).glob("*.png"))
    ok(
        "拼版产物落盘为 0001/0002",
        _names(produced) == ["0001.png", "0002.png"],
        str(_names(produced)),
    )
    st.entries, _doc = st.page._print_entries()
    ok(
        "待打印列表改从拼版产物取",
        {str(Path(e["file"]).parent) for e in st.entries}
        == {str(st.repo.imposition_output_dir(st.tid))},
        str(_names([e["file"] for e in st.entries])),
    )
    effects = st.page._build_print_effects(st.entries)
    ok(
        "拼版生效时整页透传（拼版页本身就是成品）",
        len(effects) == 2 and all(e["effect"] is None for e in effects),
        str(effects),
    )

    # 取消启用 → 回到去底色（用户口径：「否则从第三步去底色获取」）
    st.page._set_imposition_checked(False)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok(
        "取消启用后取图回到第三步去底色",
        st.page.print_source_dir() == st.rembg_dir and not st.page.imposition_active(),
    )
    st.entries, _doc = st.page._print_entries()
    ok(
        "取消启用后待打印列表回到去底色产物",
        {str(Path(e["file"]).parent) for e in st.entries} == {str(st.rembg_dir)},
        str(_names([e["file"] for e in st.entries])),
    )
    from desktop.services.stale_chain import print_source_switched
    from desktop.store import IMPOSITION_STAGE, STAGE_SHORT
    from desktop.workers.task_rows_worker import TaskRowsWorker

    def _chips_of(task_id: str) -> list[dict]:
        """列表行 worker 真实产出（不碰表格控件，纯数据层）。"""
        worker = TaskRowsWorker(st.repo)
        got: list = []
        worker.completed.connect(got.append)
        worker.failed.connect(lambda m: got.append(m))
        worker.run()
        rows = got[0]
        return rows[0]["stages"] if isinstance(rows, list) else []

    st.page._set_imposition_checked(False)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok(
        "未启用拼版：列表只有四个节点",
        len(_chips_of(st.tid)) == 4,
        str([c["short"] for c in _chips_of(st.tid)]),
    )
    st.page._set_imposition_checked(True)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    chips = _chips_of(st.tid)
    shorts = [c["short"] for c in chips]
    ok("启用拼版：列表多一个节点（共五个）", len(chips) == 5, str(shorts))
    ok(
        "拼版胶囊排在 PDF 之前（与流程条节点同位）",
        STAGE_SHORT[IMPOSITION_STAGE] in shorts
        and shorts.index(STAGE_SHORT[IMPOSITION_STAGE])
        == shorts.index(STAGE_SHORT["print"]) - 1,
        str(shorts),
    )
    ok(
        "拼版胶囊文案取自 spec 的 short_name（不另写一份中文）",
        STAGE_SHORT[IMPOSITION_STAGE] == "拼版",
        STAGE_SHORT[IMPOSITION_STAGE],
    )
    # 状态：勾了但没拼页 = 未生效（灰）；勾了且拼了页 = 生效（绿）
    # ⚠️ 这里临时清空 pages，测完**原样恢复**第 6 节拼好的两页——后面
    # 取图来源/旧数据的断言都建立在"拼版已生效"之上。
    doc_backup = st.repo.load_imposition_doc(st.tid)
    st.repo.save_imposition_doc(st.tid, {"enabled": True, "pages": []})
    pending_chip = next(
        c for c in _chips_of(st.tid) if c["short"] == STAGE_SHORT[IMPOSITION_STAGE]
    )
    ok(
        "启用但还没拼页 → 拼版胶囊为未执行（灰）",
        pending_chip["status"] == "pending",
        str(pending_chip),
    )
    st.repo.save_imposition_doc(st.tid, doc_backup)
    live_chip = next(
        c for c in _chips_of(st.tid) if c["short"] == STAGE_SHORT[IMPOSITION_STAGE]
    )
    ok(
        "启用且拼了页 → 拼版胶囊为成功（绿）",
        live_chip["status"] == "success",
        str(live_chip),
    )

    # 「旧数据」：伪造一份**去底色来源**下生成过的 PDF + 对应运行记录
    st.print_dir = st.repo.stage_dir(st.tid, "print")
    st.print_dir.mkdir(parents=True, exist_ok=True)
    (st.print_dir / "print.pdf").write_bytes(b"%PDF-1.4 old")
    old_run = st.repo.create_stage_run(
        st.tid,
        "print",
        {
            "pdf_name": "print.pdf",
            "source_stage": "rembg",
        },
    )
    st.repo.finish_stage(st.tid, old_run, "success", str(st.print_dir))
    st.page._set_imposition_checked(False)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    st.page._refresh_stale_notices()
    ok(
        "来源没变时那份 PDF 仍然可用（不误伤）",
        not st.page._print_source_switched()
        and st.page._current_print_pdf_path() is not None,
    )
    ok("从未成功生成过 → 不判过期", not print_source_switched({}, "imposition"))
    ok(
        "老记录没有 source_stage → 不误判过期",
        not print_source_switched(
            {
                "print": [
                    {
                        "status": "success",
                        "finished_at": 1.0,
                        "parameters": {"pdf_name": "print.pdf"},
                    }
                ]
            },
            "imposition",
        ),
    )

    # 现在启用拼版：那份 PDF 成了旧数据
    st.page._set_imposition_checked(True)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    st.page._select_stage(_bar_of(st.page, "print"))
    pump(st.ctx.app, times=6)
    ok(
        "启用拼版后取图来源切到 imposition",
        st.page.print_source_stage() == "imposition",
        st.page.print_source_stage(),
    )
    ok("换来源后旧 PDF 判为过期（缓存跟着开关走）", st.page._print_source_stale)
    ok(
        "旧数据不显示：当前可用 PDF 为空",
        st.page._current_print_pdf_path() is None,
        str(st.page._current_print_pdf_path()),
    )
    ok(
        "「下载 PDF」按钮随之收起",
        st.page.download_row.isHidden(),
    )
    ok(
        "预览控件的 PDF 绑定被清空",
        st.page.print_preview._pdf_path is None,
        str(st.page.print_preview._pdf_path),
    )
    notice = st.page._regenerate_notice("print")
    ok(
        "状态行提示取图来源已改（要点名拼版）",
        bool(notice) and "取图来源已改为" in notice and "拼版" in notice,
        str(notice),
    )
    # 磁盘上那份文件**不删**（用户自己的产物），只是不再提供/不再算结果
    ok(
        "旧 PDF 文件仍在磁盘上（只是不显示，不删用户产物）",
        (st.print_dir / "print.pdf").exists(),
    )
    toasts: list = []
    real_toast = st.page._toast
    st.page._toast = lambda *a, **k: toasts.append(a)
    try:
        st.page._download_print_pdf()
    finally:
        st.page._toast = real_toast
    ok(
        "旧数据下载被拦下并说明原因",
        any("重新生成" in str(t) for t in toasts),
        str(toasts),
    )
    # 反向也对称：取消启用 → 又变回去底色，但历史是去底色 → 不判旧
    st.page._select_stage(_bar_of(st.page, IMPOSITION_STAGE))
    pump(st.ctx.app, times=4)
    st.page._set_imposition_checked(False)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=6)
    ok(
        "反向切换对称：回到原来源后不再判旧、PDF 恢复可用",
        not st.page._print_source_switched()
        and st.page._current_print_pdf_path() is not None,
    )

