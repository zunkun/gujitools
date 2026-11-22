# -*- coding: utf-8 -*-
"""第 16 / 17 章：输入入口红框 + 提示层主按钮选目录。"""

from __future__ import annotations

from pathlib import Path
import tempfile
import shutil
import time

from ._helpers import _FLOW_DETECT_FIRST, _viewer_entry_button


def run(st) -> None:
    _check_input_entry_marks()
    _check_prompt_picks_folder()


def _check_input_entry_marks() -> None:
    """红框标在"输入入口"上，「打开任务数据目录」搬到**右下角**。

    用户 2026-10-06 三条一起提的：

    1. 右上角的选择图片还可以选择目录，都是红色框住；
    2. 左下角输入图片和目录也用红色框住；
    3. 右上角的打开任务数据目录，统一放到右下角。

    ⚠️ **判"有没有红框"不能看有没有 border**：qfluentwidgets 的按钮**自带**
    border 样式表，那样判**所有按钮都是红的**（我第一版自测就栽在这，全绿）。
    必须看**我们加的那条**——``theme.DANGER`` 色值在不在样式表里。
    """
    import shutil
    import tempfile

    from pathlib import Path

    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import ToolButton

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from desktop.ui import theme as theme
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_marks_"))
    try:
        store = TaskStore(tmp)
        shell = ModuleShell(store)
        shell.resize(1500, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="红框")
        page = shell.detail_page
        assert isinstance(page, TaskDetailPage)  # 壳层惰性建的详情页
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()

        def marked(button) -> bool:
            """有没有我们加的那层红框（**不是**看有没有 border）。"""
            return bool(button is not None) and \
                str(theme.DANGER) in (button.styleSheet() or "")

        # ---- ① 页头：插图 + 插目录都红框 ----
        ok("页头「插入图片」有红框", marked(page.insert_button))
        ok("页头「选文件夹」有红框（目录入口同在页头）",
           marked(page.insert_dir_button))
        # ⚠️ **不该红的别红**：标红＝"这里能喂图片"，标到无关按钮上就成了噪声
        ok("页头「查看/编辑流程」没有红框（它不是输入入口）",
           not marked(page.flow_button))
        ok("页头「修改任务名称」没有红框",
           not marked(page.rename_button))

        # ---- ② 预览区左下角：＋与📁 红框，🗑 不红 ----
        tips = {b.toolTip(): marked(b)
                for b in page.detect_viewer.findChildren(ToolButton)}
        ok("预览区「插入图片（可多选）」有红框",
           tips.get("插入图片（可多选）") is True, str(tips))
        ok("预览区「把一个文件夹里的图片批量插入」有红框",
           tips.get("把一个文件夹里的图片批量插入") is True, str(tips))
        ok("预览区「删除」没有红框（删图不是入口）",
           tips.get("从页面清单删除所选图片") is False, str(tips))

        # ---- ②b 显隐跟着**流程入口**走（用户 2026-10-06 三条规则）----
        # 这个任务是默认流程（「图片提取」打头）⇒ 输入是 PDF：页头只亮
        # PDF，图片/目录入口整对藏起来（规则①）；红框在样式表里常驻，
        # 但按钮不可见。左下角「＋/📁」只属于**入口**那一步的查看器——
        # 检测页不是入口，它的输入来自上游 ⇒ 藏（规则③）。
        ok("默认流程（图片提取打头）⇒ 页头只显示 PDF，图片/目录入口藏起来",
           not page.source_button.isHidden()
           and page.insert_button.isHidden()
           and page.insert_dir_button.isHidden())
        ok("检测页左下角「＋/📁」藏起来（不是入口步骤，规则③）",
           (_btn_img := _viewer_entry_button(
               page.detect_viewer, "插入图片（可多选）")) is not None
           and _btn_img.isHidden()
           and (_btn_dir := _viewer_entry_button(
               page.detect_viewer,
               "把一个文件夹里的图片批量插入")) is not None
           and _btn_dir.isHidden())

        # ---- ③「打开任务目录」在右下角（底部状态条最右端）----
        ok("「打开任务目录」已挂进底部状态条",
           shell and page.log_panel.isAncestorOf(page.task_dir_button))
        ok("它不在页头那一排里了（页头只留输入/流程类按钮）",
           not page.detail_title.isAncestorOf(page.task_dir_button))
        # 用户 2026-10-18：改成图标 + 文字；打开目标＝**节点目录优先，其次任务根**
        ok("「打开任务目录」是图标 + 文字按钮",
           page.task_dir_button.text() == "打开任务目录")
        # 默认流程第一步是「图片提取」。节点目录是"跑过那一步才有"的，还没产出
        # 时打开它会点了没反应 ⇒ 必须回落任务根（否则"并非所有节点都能打开"）
        ok("节点目录还没有 ⇒ 回落任务根（否则点了没反应）",
           page._current_node_dir() == store.task_dir(tid))
        # 产出该节点目录后 ⇒ 优先打开它（stages/extract，而不再是任务根）
        node_dir = store.extract_output_dir(tid)
        node_dir.mkdir(parents=True, exist_ok=True)
        ok("节点目录存在 ⇒ 优先打开节点目录",
           page._current_node_dir() == node_dir
           and page._current_node_dir() != store.task_dir(tid))
        # 用户 2026-10-18：「图片去底色」节点打开的是**成品图**目录
        # （stages/rembg）；还没产出时回落任务根。
        rembg_bar = page.bar_index_of_step("rembg")
        if rembg_bar is not None:
            page._select_stage(rembg_bar)
            app.processEvents()
            ok("去底色节点：成品图目录还没产出 ⇒ 回落任务根",
               page._current_node_dir() == store.task_dir(tid))
            apply_dir = store.rembg_output_dir(tid)
            apply_dir.mkdir(parents=True, exist_ok=True)
            ok("去底色节点：有成品图目录时 ⇒ 打开 stages/rembg",
               page._current_node_dir() == apply_dir)

        shell.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def _check_prompt_picks_folder() -> None:
    """缺入口图片时，提示层主按钮**真的开目录框**并把整目录导进来。

    用户 2026-10-06："改成选择图片目录"（配图是那张「这个流程的第一步需要图片」
    的提示层，按钮写着"选择图片"）。

    ⚠️ **文案与行为必须一致**，只改文案等于骗人：``getOpenFileNames`` **选不了
    目录**，所以按钮写着"选目录"就必须走 ``getExistingDirectory``。本节**真点
    一次按钮**（``QTest.mouseClick``）并记录开的是哪个框——不是只断言文案。
    """
    import shutil
    import tempfile
    import time

    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QFileDialog

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.shell import ModuleShell
    from desktop.store.store import TaskStore
    from tests.selftests._context import ok, silence_source_prompt

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    tmp = Path(tempfile.mkdtemp(prefix="guji_pickdir_"))
    orig_dir = QFileDialog.getExistingDirectory
    orig_files = QFileDialog.getOpenFileNames
    try:
        source = tmp / "扫描结果"
        source.mkdir()
        for name in ("0001.jpg", "0002.jpg"):
            (source / name).write_bytes(b"x")

        store = TaskStore(tmp / "data")
        shell = ModuleShell(store)
        shell.resize(1400, 900)
        shell.show()
        app.processEvents()

        tid = store.create_task(source_path="", source_hash="", name="提示选目录")
        (store.task_dir(tid) / "flow.bpmn").write_text(
            _FLOW_DETECT_FIRST, encoding="utf-8")

        page = shell.detail_page
        assert isinstance(page, TaskDetailPage)  # 壳层惰性建的详情页
        silence_source_prompt(page)
        shell.open_detail(tid)
        app.processEvents()

        prompt = page._source_prompt
        assert prompt is not None  # 缺源任务进详情后提示层必然已建
        ok("第一步不吃 PDF ⇒ 判据是「缺图片」",
           page._missing_input_kind() == "images",
           repr(page._missing_input_kind()))
        ok("主按钮文案是「选择图片目录」",
           prompt.pick_button.text() == "选择图片目录",
           prompt.pick_button.text())

        # ---- 真点一次，记录开的是哪个对话框 ----
        opened: list[str] = []
        QFileDialog.getExistingDirectory = staticmethod(  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把目录框换成记录器，离屏不许真弹
            lambda *a, **k: (opened.append("目录"), str(source))[1])
        QFileDialog.getOpenFileNames = staticmethod(  # type: ignore[reportAttributeAccessIssue]  # 测试替身：把文件框换成记录器，离屏不许真弹
            lambda *a, **k: (opened.append("文件"), ([], ""))[1])
        prompt.show_prompt()
        app.processEvents()
        QTest.mouseClick(prompt.pick_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        for _ in range(60):
            app.processEvents()
            time.sleep(0.05)

        ok("点主按钮开的是**目录框**（不是文件框——它选不了目录）",
           opened == ["目录"], str(opened))
        target = page._current_stage_input_dir()
        ok("选中的目录被整批导进输入目录",
           target is not None
           and sorted(p.name for p in target.iterdir()) == ["0001.jpg", "0002.jpg"],
           str(sorted(p.name for p in target.iterdir())) if target else "")
        ok("清单里也是这两张（执行时读得到）",
           [Path(p["file"]).name for p in page.pages] == ["0001.jpg", "0002.jpg"],
           str([Path(p["file"]).name for p in page.pages]))

        shell.close()
    finally:
        QFileDialog.getExistingDirectory = orig_dir
        QFileDialog.getOpenFileNames = orig_files
        shutil.rmtree(tmp, ignore_errors=True)
