# -*- coding: utf-8 -*-
"""「上次停留的步骤」自测：打开任务详情默认回到上次那一步。

用户口径（2026-09-30）：
1. 每个任务各记一份：下次打开任务详情，默认回到**上次停留的步骤**；
2. 没有记录（新任务）→ 第一步；
3. 记录在**当前流程里匹配不上** → 回到第一步（例如「图片拼版」是虚线可选
   节点，第三步 area≠1 时它根本不在流程里）；
4. 记录按**语义 key** 存（"rembg" / "imposition"，不是下标）：步骤增删后
   下标会错位，那就把用户送到**另一个**步骤去了；
5. 程序重启后**自动回到上次任务**的那一步（2026-09-30 新增）：全局记一份
   「上次任务」（id + source_hash 指纹），启动时任务还在（指纹对得上）就
   直接打开详情、落到步骤；已删/任务号被复用就留在列表页。

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
    from desktop.store import IMPOSITION_INDEX, TaskStore
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
        page._select_stage(3)
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
        ok("新页面的第三步面板还没被建出来（area 走暂存/默认）",
           page2.control_stack.widget(2).peek() is None)

        # 6a. 区域模式确定为 1（草稿；节点在流程里）→ 记录能匹配，落到拼版，
        #     **且节点要显示**（⚠️ 新判据下节点只认「已知」的 area——面板值/
        #     草稿/执行历史之一，不凭内置默认冒出来）
        repo.save_draft(tid, "rembg", {"area": 1})
        repo.save_last_stage(tid, "imposition")
        page2.set_task(tid)
        pump(ctx.app, times=8)
        ok("记录为「图片拼版」且节点在流程里 → 落到拼版",
           page2.step_bar._current == IMPOSITION_INDEX
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

        # 6b. 第三步区域模式改成 2（节点不在流程里）→ 记录匹配不上，回第一步
        #     ⚠️ area 的惰性读法是「第三步面板 > 暂存 > 最近执行 > 默认」，
        #     而上面那个页面从没进过第三步（面板没建），暂存才说话。
        repo.save_draft(tid3, "rembg", {"area": 2})
        repo.save_last_stage(tid3, "imposition")
        page2.set_task(tid3)
        pump(ctx.app, times=8)
        ok("拼版节点不在流程里时，「拼版」这条记录匹配不上 → 回第一步",
           page2.step_bar._current == 0, f"current={page2.step_bar._current}")
        ok("此时流程条上确实没有拼版节点",
           not page2._imposition_node_visible() and node.isHidden())

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

        # ---- 9. 「重启程序回到上次任务」：全局记录 + 启动恢复 ----
        # 两层记录各管一半：「哪个任务」在数据根目录 ui.json（进入任务即写）；
        # 「哪一步」仍在该任务自己的 ui.json。恢复入口是
        # MainWindow._restore_last_task（main() 启动后 RESTORE_DELAY_MS 调一次）。
        from desktop.app import MainWindow

        ok("进入任务时写入全局「上次任务」记录（id + 指纹）",
           repo.load_last_task() == {"id": tid, "source_hash": "last-stage-hash"},
           repr(repo.load_last_task()))
        ok("save_last_task 拒绝给不存在的任务留指针",
           repo.save_last_task("9999") is False
           and repo.load_last_task()["id"] == tid)
        global_ui = repo.app_ui_path()
        for payload, label in (
            ('{"last_task": 3, "source_hash": "x"}', "任务号非字符串"),
            ('{"last_task": ""}', "任务号为空"),
            ('{"other": 1}', "没有该字段"),
            ("not json", "整份写坏"),
        ):
            global_ui.write_text(payload, encoding="utf-8")
            ok(f"全局记录{label} → 当作没有记录", repo.load_last_task() is None)

        w = MainWindow()
        # 同 _context.prepare：主窗口自带的 store 指向真实数据目录，换成本模块
        # 的临时 repo（详情页是恢复时惰性建的，取的是当时的 w.store）。
        w.store = repo
        w.list_page.store = repo
        try:
            # 9a. 记录的任务已删 → 安静留在列表页
            global_ui.write_text(
                '{"last_task": "9999", "source_hash": "x"}', encoding="utf-8"
            )
            w._restore_last_task()
            pump(ctx.app, times=4)
            ok("记录的任务已不存在 → 留在列表页",
               w.pages.currentWidget() is w.list_page)

            # 9b. 防撞号：任务号顺序复用（删 0012 再新建也叫 0012），指纹
            #     对不上说明"这个号已经不是当初那个任务"，不能往里跳。
            global_ui.write_text(
                '{"last_task": "%s", "source_hash": "someone-else"}' % tid,
                encoding="utf-8",
            )
            w._restore_last_task()
            pump(ctx.app, times=4)
            ok("指纹对不上（任务号被复用）→ 留在列表页",
               w.pages.currentWidget() is w.list_page)

            # 9c. 正常恢复：自动打开上次任务，并落到上次停留的步骤
            repo.save_last_stage(tid, "rembg")
            repo.save_last_task(tid)
            w._restore_last_task()
            pump(ctx.app, times=8)
            ok("重启恢复：自动打开上次任务",
               w.pages.currentWidget() is w.detail_page
               and w.detail_page.task_id == tid,
               f"index={w.pages.currentIndex()} task={w.detail_page.task_id}")
            ok("恢复后落到上次停留的步骤（rembg）",
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
