# -*- coding: utf-8 -*-
"""第 14 / 15 章：保存流程刷新步骤条 + 选文件夹批量导入。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import shutil

from ._helpers import _FLOW_4_SLOTS, _FLOW_REMBG_FIRST, _open_detail_failure_shows_page, _pump, _rebuild_keeps_highlight


def run(st) -> None:
    _check_flow_saved_refreshes_bar()
    _check_insert_from_folder()


def _check_flow_saved_refreshes_bar() -> None:
    """编辑流程保存后回详情页，步骤条**当场**按新图重排（不必重进任务）。

    用户 2026-10-06 报障：

    > 顶部的任务流程编辑后，顶部这个流程图没有立即更新，必须重新进入这个页面才能更新

    钉三件事（缺一件就复发）：

    1. 保存 → 自动回详情页，且步骤条**立刻**是���流程（4 格 → 3 格）；
    2. 高亮与完成态**按步骤 key 跨重建保住**——重建时若拿"旧格序"去查
       **新**槽位表（``flow_slots()`` 读的是磁盘上那张新图），会贴错格子；
    3. ``set_task`` 拒绝重载时（正在跑步骤）**不许静默**：必须把详情页
       切出来并说明，否则用户被留在流程页上、以为没保存成功。
    """
    import copy
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.pages.taskflow.page import TaskFlowPage
    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:  # 单独跑本节时自建一个
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_flowbar_"))
    try:
        store = TaskStore(tmp)
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="流程条刷新")
        (store.task_dir(tid) / "flow.bpmn").write_text(
            _FLOW_4_SLOTS, encoding="utf-8")

        page = shell.detail_page
        assert isinstance(page, TaskDetailPage)  # 壳层惰性建的详情页
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()
        before = [s.step for s in page.flow_slots()]
        ok("进详情时步骤条是四格流程",
           before == ["detect", "rembg", "imposition", "print"], str(before))

        # 停在 detect 并标记完成（重建后要靠 key 找回这两样）
        _bar_idx = page.bar_index_of_step("detect")
        assert _bar_idx is not None  # 四格流程里必有「检测文本框」
        page._select_stage(_bar_idx)
        page.step_bar.mark_completed(0)
        app.processEvents()

        # ---- 走真实保存链路：开流程页 → 删掉「图片拼版」→ 保存 ----
        shell.open_flow(tid)
        app.processEvents()
        flow_page = shell.flow_page()
        ok("流程页打开的是本任务的流程",
           getattr(flow_page, "_task_id", None) == tid,
           str(getattr(flow_page, "_task_id", None)))
        assert isinstance(flow_page, TaskFlowPage)  # 壳层惰性建的流程页
        assert flow_page._panel is not None  # 打开后面板必然已建
        editor = flow_page._panel.editor_panel.editor()
        assert editor is not None  # 打开后编辑器必然已建
        new = copy.deepcopy(editor.diagram())
        victim = next(n for n in new.nodes if n.stage == "imposition")
        new.nodes = tuple(n for n in new.nodes if n.id != victim.id)
        new.flows = tuple(f for f in new.flows
                          if f.source != victim.id and f.target != victim.id)
        # ⚠️ 2026-11-04 起孤立节点会被保存校验拒绝：删掉拼版后「PDF排版」
        #    没了入线，必须像用户在画布上那样把 去底色 → PDF排版 接回来。
        from desktop.steps.bpmn_diagram import DiagramFlow
        new.flows = new.flows + (
            DiagramFlow("f_saved", "b", "d"),
        )
        editor.set_diagram(new)
        flow_page._on_done(True)
        app.processEvents()

        # ---- ① 自动回详情页且当场重排 ----
        ok("保存后自动回到详情页（不用手动切）",
           shell.pages.currentWidget() is page,
           type(shell.pages.currentWidget()).__name__)
        after = [s.step for s in page.flow_slots()]
        ok("步骤条当场按新图重排（四格→三格，不必重进任务）",
           after == ["detect", "rembg", "print"], str(after))
        ok("被删掉的「图片拼版」节点已隐藏",
           page.step_bar.imposition_node.isHidden())

        # ---- ② 高亮按 key跨重建保住 ----
        # ⚠️ **不验完成态**：完成态由 ``_refresh_stage_views`` 按 runs.json
        #    重算（不是 ``mark_completed`` 手工标的），而 ``set_task`` 走的是
        #    "切任务"全量复位路径——手工标的完成态被清掉是**既有正确行为**，
        #    拿它当断言会钉错东西。真正要钉的是"高亮别跳错格"：重建时若拿
        #    **旧格序**去查**新**槽位表，下标含义已变，高亮会落到别的步骤上。
        current_step = page.step_at_index(page.step_bar._current)
        ok("重建后仍停在 detect（按 key 找回，不是按旧格序）",
           current_step == "detect", str(current_step))
        ok("detect 在新流程里确实是第 0 格（格序已随删节点前移）",
           page.bar_index_of_step("detect") == 0,
           str(page.bar_index_of_step("detect")))

        # ---- ②' 单独验"重建不跳格"：这一步不依赖 set_task 的"当前页"兜底 ----
        # ⚠️ 上一条断言在完整保存链路上**改前也绿**（当前停在 detect，而它
        #    恰好还是第 0 格，兜底与正确行为重合）⇒ 钉不住真正的缺陷。真正
        #    会跳格的是"停在中间某一步、且它前面的节点被删了"：旧格序 2 在
        #    新流程里指向别的步骤，于是高亮默默挪走（实测 rembg → imposition）。
        ok("重建步骤条时高亮按 key 保住，不被前面的节点删除带偏",
           _rebuild_keeps_highlight(page, store, tid),
           "重建后高亮跳到了别的步骤")

        # ---- ③ set_task 拒绝重载时不许静默 ----
        # ⚠️ 必须**在 shell.close() 之前**跑：close 之后 page 已析构，
        #    探针再切页/替换方法就拿到僵尸控件，判据恒假。
        ok("open_detail 在 set_task 失败时仍把详情页切出来并说明（不留在流程页）",
           _open_detail_failure_shows_page(shell, page),
           "拒绝重载后用户被留在流程页、或没有任何说明")

        shell.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _check_insert_from_folder() -> None:
    """「📁 选文件夹」能把整个目录批量插进来，**且执行时读的就是这批**。

    用户 2026-10-06：

    > 现在提示选择的是图片，是否可以选择目录，比如去底色在第一个节点的时候，
    > 是否也可以输入目录

    钉四件事：

    1. 界面上真的有「选文件夹」按钮（``getOpenFileNames`` 选不了目录，
       指望在文件对话框里选中文件夹是不成立的）；
    2. 目录被展开成图片清单——**非图片被忽略**、按名排序；
    3. 落在**这一步的输入目录**，与执行读的是同一处（否则"导入了却读不到"）；
    4. 再次选**同一个目录不产生重复**（否则清单里同一张图出现两次）。

    2026-11-21 追加两件（用户："任何节点都可以作为第一个节点，都可以导入数据"）：

    5. **入口节点**（流程里只有去底色这一步）导图时**不许**弹"上游尚未执行"
       —— 入口目录空着正是等着导图；
    6. 反例：这一步的图**真来自上游**（默认流程、检测没跑）时，仍然拦住。
    """
    import shutil
    import tempfile
    import time

    from pathlib import Path

    from PySide6.QtWidgets import QApplication, QFileDialog
    from qfluentwidgets import ToolButton

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_folder_"))
    original = QFileDialog.getExistingDirectory
    try:
        source = tmp / "扫描结果"
        source.mkdir()
        for name in ("0003.jpg", "0001.jpg", "0002.png"):
            (source / name).write_bytes(b"x")
        (source / "说明.txt").write_text("x", encoding="utf-8")

        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="去底色打头")
        (store.task_dir(tid) / "flow.bpmn").write_text(
            _FLOW_REMBG_FIRST, encoding="utf-8")

        page = shell.detail_page
        assert isinstance(page, TaskDetailPage)  # 壳层惰性建的详情页
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()
        _bar_idx = page.bar_index_of_step("rembg")
        assert _bar_idx is not None  # 流程里有「图片去底色」这一格
        page._select_stage(_bar_idx)
        app.processEvents()

        # 记下弹出的提示：入口节点导图**不该**被"上游还没跑"挡住（2026-11-21）
        toasts: list[tuple[str, str]] = []
        real_toast = page._toast

        def _record_toast(kind: str, title: str, content: str) -> None:
            toasts.append((str(title), str(content)))
            real_toast(kind, title, content)

        page._toast = _record_toast
        # 没有这一步时单靠"入口目录空着"就会误判成"上游没跑"；先确认现场如此
        _entry_before = page._current_stage_input_dir()
        ok("刚建好的去底色打头任务：入口图片目录还不存在（正是要导图的时候）",
           _entry_before is not None and not _entry_before.exists(),
           str(_entry_before))

        # ---- ① 按钮在（提示语要说清是"文件夹"）----
        tips = [b.toolTip() for b in page.detect_viewer.findChildren(ToolButton)]
        ok("预览区有「选文件夹」按钮（文件对话框选不了目录，得单独一个）",
           any("文件夹" in t for t in tips), str(tips))

        # ---- ②③④ 走真实导入链路 ----
        QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把目录框换成固定返回，离屏不许真弹
            lambda *a, **k: str(source))
        page.insert_pages_from_folder()
        _pump(app)

        target = page._current_stage_input_dir()
        ok("去底色作为入口节点时，输入目录是入口图片目录",
           target is not None and target.name == "input", str(target))
        assert target is not None  # 上一条 ok 已断言目录存在
        copied = sorted(p.name for p in target.iterdir())
        ok("整个目录被展开复制（非图片被忽略）",
           copied == ["0001.jpg", "0002.png", "0003.jpg"], str(copied))
        ok("清单按文件名排序（页序稳定，不靠目录枚举顺序）",
           [Path(p["file"]).name for p in page.pages]
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str([Path(p["file"]).name for p in page.pages]))
        ok("执行时读到的就是这批图（导入位置与读取位置同源）",
           [p.name for p in page._manifest_paths()]
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str([p.name for p in page._manifest_paths()]))
        # ⚠️ 2026-11-21 的回归点：入口目录空着 ≠ 上游没跑
        ok("入口节点导图**不提示**「上游尚未执行」（任何节点都能当第一个节点）",
           not any("上游尚未执行" in t for t, _ in toasts), str(toasts))

        # ---- 再选一次输入目录本身：不得重复 ----
        QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把目录框换成固定返回，离屏不许真弹
            lambda *a, **k: str(target))
        page.insert_pages_from_folder()
        _pump(app)
        ok("再选输入目录本身不产生 -1 副本",
           sorted(p.name for p in target.iterdir())
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str(sorted(p.name for p in target.iterdir())))
        ok("清单里也不出现重复条目",
           [Path(p["file"]).name for p in page.pages]
           == ["0001.jpg", "0002.png", "0003.jpg"],
           str([Path(p["file"]).name for p in page.pages]))

        # ---- 反例：这一步的图**真的来自上游**时，守卫照旧（不能放宽成"谁都能塞"）----
        # 默认流程 extract→detect→rembg→print：检测没跑，去底色的输入是上游的
        # 裁图目录，往那儿塞图既不会被看见、又可能被当成上游产物。
        tid2 = store.create_task(source_path="", source_hash="", name="默认流程")
        shell.open_detail(tid2)
        app.processEvents()
        _idx2 = page.bar_index_of_step("rembg")
        assert _idx2 is not None  # 默认流程里有「图片去底色」
        page._select_stage(_idx2)
        app.processEvents()
        upstream = page._current_stage_input_dir()
        toasts.clear()
        QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把目录框换成固定返回，离屏不许真弹
            lambda *a, **k: str(source))
        page.insert_pages_from_folder()
        _pump(app, rounds=6)
        ok("上游（检测）还没跑 ⇒ 插图仍被拦下（这一步的图确实来自上游）",
           any("上游尚未执行" in t for t, _ in toasts), str(toasts))
        leftover = (
            sorted(p.name for p in upstream.iterdir())
            if upstream is not None and upstream.exists() else []
        )
        ok("  拦下时一张也没复制进上游产物目录", not leftover, str(leftover))

        shell.close()
    finally:
        QFileDialog.getExistingDirectory = original
        shutil.rmtree(tmp, ignore_errors=True)
