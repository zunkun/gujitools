# -*- coding: utf-8 -*-
"""「上次停留的步骤」自测：打开任务详情默认回到上次那一步。

用户口径（2026-09-30）：
1. 每个任务各记一份：下次打开任务详情，默认回到**上次停留的步骤**；
2. 没有记录（新任务）→ 第一步；
3. 记录在**当前流程里匹配不上** → 回到第一步（例如「图片拼版」那一格被
   从流程图里删掉时，它根本不在流程里）；
4. 记录按**语义 key** 存（"rembg" / "imposition"，不是下标）：步骤增删后
   下标会错位，那就把用户送到**另一个**步骤去了；
5. **启动不再自动跳回上次任务**（2026-10-06 改口径，之前是 09-30 加的"重启
   回到上次任务"）：启动一律停在任务列表页，由用户点哪个任务；但点进去后
   仍然落到上次停留的步骤。全局「上次任务」记录照写不误（给将来的显式入口
   留底子），只是不再被启动路径消费。

验法：**独立构造**详情页 + 独立数据目录（同 tests/selftests/imposition.py
第 6 节的做法），不碰 ``ctx.tid`` / ``ctx.d`` 的"当前步"——否则本模块会把
别的模块的状态改掉，反过来被它们当成 bug。
"""

NAME = "last_stage"
DEPENDS: list[str] = ["tasklist"]
TITLE = "上次停留的步骤"


def run(ctx) -> None:
    import shutil
    import tempfile
    from pathlib import Path

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.store import IMPOSITION_STAGE, TaskStore
    from tests.selftests._context import make_pdf, ok, pump

    tmp = Path(tempfile.mkdtemp(prefix="last_stage_probe_"))
    repo = TaskStore(tmp / "data")
    pdf = make_pdf(tmp / "记忆样例.pdf", 2)
    tid = repo.create_task(pdf, "last-stage-hash", "记忆测试")
    repo.copy_source_to_task(tid, pdf)

    pages: list = []

    def new_page():
        """独立详情页（每建一个都记下来，收尾统一关停线程）。"""
        page = TaskDetailPage(repo)
        page.resize(1080, 720)
        page.show()
        pages.append(page)
        pump(ctx.app, times=12)
        return page

    try:
        page = new_page()

        # ---- 1. 新任务：没有记录 → 第一步 ----
        ok("新任务没有步骤记录（ui.json 都还没生成）",
           repo.load_last_stage(tid) is None
           and not repo.ui_state_path(tid).exists())
        ok("进入新任务", page.set_task(tid))
        pump(ctx.app, times=8)
        ok("无记录时落在第一步",
           page.step_bar._current == 0 and page.current_stage() == "extract",
           f"current={page.step_bar._current}")

        # ---- 2. 切步骤即记录：记的是**语义 key**，不是下标 ----
        page._select_stage(2)
        pump(ctx.app, times=8)
        ok("切到第三步后落盘（任务目录下的 ui.json）",
           repo.ui_state_path(tid).is_file())
        ok("记的是步骤 key（'rembg'）而不是下标 2",
           repo.load_last_stage(tid) == "rembg",
           repr(repo.load_last_stage(tid)))

        # ---- 3. 重新打开（set_task 就是列表页点「详情」走的入口）----
        ok("再次进入该任务", page.set_task(tid))
        pump(ctx.app, times=8)
        ok("重开任务回到上次停留的第三步",
           page.step_bar._current == 2 and page.current_stage() == "rembg",
           f"current={page.step_bar._current}")

        # ---- 4. 记录匹配不上 → 回到第一步 ----
        repo.save_last_stage(tid, "no_such_step")
        page.set_task(tid)
        pump(ctx.app, times=8)
        ok("记录的步骤在当前流程里找不到 → 回到第一步",
           page.step_bar._current == 0, f"current={page.step_bar._current}")

        # ---- 5. 每个任务各记一份（互不串味）----
        print_bar = page.bar_index_of_step("print")
        assert print_bar is not None      # ⚠️ 默认流程里有「生成PDF」这一格
        page._select_stage(print_bar)
        pump(ctx.app, times=8)
        ok("第四步被记录", repo.load_last_stage(tid) == "print")
        tid2 = repo.create_task(pdf, "last-stage-hash-2", "记忆测试2")
        repo.copy_source_to_task(tid2, pdf)
        page.set_task(tid2)
        pump(ctx.app, times=8)
        ok("新任务仍是第一步（不受上一个任务的记录影响）",
           page.step_bar._current == 0, f"current={page.step_bar._current}")
        ok("上一个任务的记录没被覆盖",
           repo.load_last_stage(tid) == "print",
           repr(repo.load_last_stage(tid)))

        # ---- 6. 「图片拼版」是条件节点：在流程里才认这条记录 ----
        # ⚠️ 6a/6b 都用**全新的详情页**：新页面的流程条上拼版节点从没被显示过
        #    （构造时就是 setVisible(False)）。这正是用户 2026-09-30 报的场景——
        #    "上次停在图片拼版，重进任务后流程条上没有那个虚线节点"。用一个已经
        #    切过第三步的页面验不出来（那时节点早被刷成可见了）。
        tid3 = repo.create_task(pdf, "last-stage-hash-3", "记忆测试3")
        repo.copy_source_to_task(tid3, pdf)
        page2 = new_page()
        _lazy_host = page2.control_stack.widget(2)
        ok("新页面的第三步面板还没被建出来（面板是惰性构建的）",
           # ⚠️ LazyPanelHost 的 peek() 只在真惰性宿主上有，源码标注退化成 QWidget
           _lazy_host is not None and getattr(_lazy_host, "peek")() is None)

        # 6a. 「图片拼板」在图里（默认模板就有）→ 记录能匹配，落到拼版，
        #     **且节点要显示**（⚠️ 判据 = **流程图**，与区域模式无关，所以这里
        #     不必再配 area）
        repo.save_last_stage(tid, "imposition")
        page2.set_task(tid)
        pump(ctx.app, times=8)
        # ⚠️ 期望值查表拿，别写死：``IMPOSITION_INDEX`` = len(STAGES) = 4 是
        # BPM 驱动**前**的格序；现在步骤条格序含可选节点占位，拼版在第 3 格。
        imposition_bar = page2.bar_index_of_step(IMPOSITION_STAGE)
        ok("拼版格序是 3（不是 len(STAGES)=4：格序含可选节点占位）",
           imposition_bar == 3, str(imposition_bar))
        ok("记录为「图片拼版」且节点在流程里 → 落到拼版",
           page2.step_bar._current == imposition_bar
           and page2.current_stage() == "imposition",
           f"current={page2.step_bar._current}")
        # 回归钉子：恢复只调了 _select_stage(拼版)，而节点显示是在 _select_stage
        # **末尾**刷的——拼版分支提前 return，于是"新任务进详情直接落在拼版"时
        # 流程条上根本没有那个虚线节点（用户报的就是它）。槽位/连接线要一起验，
        # 只藏节点会在流程条上留一段空白。
        node = page2.step_bar.imposition_node
        ok("恢复到拼版时流程条上的拼版节点也显示（不只是切了详情）",
           node.isVisible() and not node.isHidden(),
           f"visible={node.isVisible()} hidden={node.isHidden()}")
        ok("拼版槽位与它后面的连接线也一起显示",
           page2.step_bar.imposition_slot.isVisible()
           and page2.step_bar._imposition_connector.isVisible())

        # 6b. 把「图片拼板」从**流程图**里删掉 → 记录匹配不上，回第一步
        #     ⚠️ 判据是流程图（2026-10-05 口径变更），不再是第三步的区域模式：
        #     用户把那一格删了就该消失，而不是靠"去底色的裁剪方式"猜。
        from desktop.steps.bpmn_diagram import (
            DiagramFlow, DiagramNode, FlowDiagram, KIND_TASK,
        )
        repo.save_task_diagram(tid3, FlowDiagram(
            nodes=tuple(
                DiagramNode(f"s{i}", KIND_TASK, name)
                for i, name in enumerate(
                    ("提取图片", "检测文本框", "图片去底色", "PDF排版"))
            ),
            flows=tuple(DiagramFlow(f"sf{i}", f"s{i - 1}", f"s{i}")
                        for i in range(1, 4)),
        ))
        repo.save_last_stage(tid3, "imposition")
        page2.set_task(tid3)
        pump(ctx.app, times=8)
        ok("拼版节点不在流程里时，「拼版」这条记录匹配不上 → 回第一步",
           page2.step_bar._current == 0, f"current={page2.step_bar._current}")
        ok("此时流程条上确实没有拼版节点",
           not page2._imposition_node_visible()
           # ⚠️ **必须重新取节点**：``set_task`` 会走 ``_rebuild_step_bar``
           #    重建整个步骤条（``deleteLater`` 掉旧的）——上面 6a 缓存的
           #    ``node`` 指向的是**已析构的旧控件**，问它isHidden() 拿到的是
           #    僵尸对象的状态，不是当前步骤条的（曾因此假红）。
           and page2.step_bar.imposition_node.isHidden(),
           f'visible={page2._imposition_node_visible()} '
           f'hidden={page2.step_bar.imposition_node.isHidden()}')

        # ---- 7. 「重开程序」= 换一个全新详情页实例，仍回到记录的那一步 ----
        # 记录是**落盘**的，不依赖页面实例（上面 6b 那个页面从没切到过第三步）
        repo.clear_draft(tid3, "rembg")
        repo.save_last_stage(tid3, "rembg")
        page3 = new_page()
        ok("全新详情页（模拟下次启动/重开任务）也回到记录的那一步",
           page3.set_task(tid3) and page3.step_bar._current == 2
           and page3.current_stage() == "rembg",
           f"current={page3.step_bar._current}")

        # ---- 8. 存储层守卫 ----
        ok("已删任务不写记录、也不把目录重建出来",
           repo.save_last_stage("9999", "rembg") is False
           and not repo.task_dir("9999").exists())
        # 形状不对的记录一律当"没有记录"（外部工具/老版本写坏 JSON 都不能崩）
        bad = repo.ui_state_path(tid)
        for payload, label in (
            ('{"last_stage": 3}', "非字符串"),
            ('{"last_stage": ""}', "空字符串"),
            ('{"other": 1}', "没有该字段"),
        ):
            bad.write_text(payload, encoding="utf-8")
            ok(f"{label}的记录当作没有记录", repo.load_last_stage(tid) is None)
        page.set_task(tid)
        pump(ctx.app, times=8)
        ok("记录缺失/写坏时回落第一步（不崩、不乱跑）",
           page.step_bar._current == 0, f"current={page.step_bar._current}")

        # ---- 9. 「启动不再自动跳回上次任务」（2026-10-06 改口径）----
        # 全局「上次任务」记录（数据根目录 ui.json）**照写不误**，只是不再被
        # 启动路径消费；「哪一步」仍在该任务自己的 ui.json，点任务详情时落上去。
        from desktop.app import MainWindow

        ok("进入任务时写入全局「上次任务」记录（id + 指纹）",
           repo.load_last_task() == {"id": tid, "source_hash": "last-stage-hash"},
           repr(repo.load_last_task()))
        ok("save_last_task 拒绝给不存在的任务留指针",
           repo.save_last_task("9999") is False
           and (repo.load_last_task() or {}).get("id") == tid)
        global_ui = repo.app_ui_path()
        for payload, label in (
            ('{"last_task": 3, "source_hash": "x"}', "任务号非字符串"),
            ('{"last_task": ""}', "任务号为空"),
            ('{"other": 1}', "没有该字段"),
            ("not json", "整份写坏"),
        ):
            global_ui.write_text(payload, encoding="utf-8")
            ok(f"全局记录{label} → 当作没有记录", repo.load_last_task() is None)

        # 9a. 记录完好、指纹也对得上（就是以前会自动跳进去的那种情形）
        repo.save_last_stage(tid, "rembg")
        repo.save_last_task(tid)
        w = MainWindow()
        # 同_context.prepare：主窗口自带的 store 指向真实数据目录，换成本模块
        # 的临时 repo。
        w.store = repo
        w.list_page.store = repo
        try:
            ok("记录完好且指纹一致（以前会自动跳进去的那种情形）",
               repo.load_last_task() == {"id": tid, "source_hash": "last-stage-hash"},
               repr(repo.load_last_task()))
            # 9b. 启动路径**没有**恢复入口了：既不该有那个定时器常量，也不该
            #     残留恢复方法（留着就是"看起来还在跳"的假象/死代码）。
            ok("MainWindow 不再有启动恢复的常量与方法",
               not hasattr(MainWindow, "RESTORE_DELAY_MS")
               and not hasattr(w, "_restore_last_task"),
               f"const={hasattr(MainWindow, 'RESTORE_DELAY_MS')} "
               f"method={hasattr(w, '_restore_last_task')}")
            ok("启动后停在列表页，不自动跳进上次任务",
               w.pages.currentWidget() is w.list_page,
               f"index={w.pages.currentIndex()}")
            # 9c. 保留的口径：用户**自己点**进去时，仍落到上次停留的步骤
            # 走列表页「详情」那条真实入口（list_page.open_detail 连的就是它）
            w._open_detail(tid)
            pump(ctx.app, times=8)
            ok("点任务详情 → 打开该任务",
               w.pages.currentWidget() is w.detail_page
               and w.detail_page.task_id == tid,
               f"index={w.pages.currentIndex()} task={w.detail_page.task_id}")
            ok("点进去仍落到上次停留的步骤（rembg）",
               w.detail_page.step_bar._current == 2
               and w.detail_page.current_stage() == "rembg",
               f"current={w.detail_page.step_bar._current}")
        finally:
            w.close()
            pump(ctx.app, times=4)
    finally:
        for extra in reversed(pages):
            try:
                extra.shutdown_all_workers()
                extra.hide()
                extra.deleteLater()
            except RuntimeError:
                pass  # 控件已析构
            pump(ctx.app, times=4)
        shutil.rmtree(tmp, ignore_errors=True)
