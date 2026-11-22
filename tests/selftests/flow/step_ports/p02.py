# -*- coding: utf-8 -*-
"""``step_ports`` 第 2 章：store 派生 / 步骤页复用 / 详情页元数据。"""

from __future__ import annotations

from pathlib import Path

from ._helpers import _MODULES_DIR, _REGULAR_KEYS, _spec_for


def run(st) -> None:
    _check_store_derivation(st.ctx, st.ok)
    _check_step_module_page_reuse(st.ok)
    _check_detail_metadata(st.ctx, st.ok)


# ---------------------------------------------------------------- 4. store 派生
def _check_store_derivation(ctx, ok) -> None:
    """④ store 的路径方法必须**由端口表派生**（加一步不用改 store）。"""
    from desktop.steps import ports
    from desktop.store import TaskStore

    repo = TaskStore(Path(ctx.tmp) / "ports_store")
    tid = "0042"
    task_dir = repo.task_dir(tid)

    # ⚠️ 逐个对照：这些路径躺在用户磁盘的老任务上，改错一个就是数据事故。
    for name, stage, port in (
        ("extract_output_dir", "extract", "pages"),
        ("rembg_output_dir", "rembg", "pages"),
        ("imposition_output_dir", "imposition", "pages"),
        ("print_output_pdf", "print", "pdf"),
    ):
        got = getattr(repo, name)(tid)
        want = ports.artifact_path(task_dir, stage, port)
        ok(f"{name} 与端口表一致", got == want, f"{got} vs {want}")

    ok("stage_input 按连线取 print 的上游图",
       repo.stage_input(tid, "print", "pages") == repo.rembg_output_dir(tid))
    ok("拼版生效时 stage_input 换上游",
       repo.stage_input(tid, "print", "pages", imposition_active=True)
       == repo.imposition_output_dir(tid))
    # ⚠️ 2026-10-22：去底色不再吃 boxes（整图去底色）。坐标文件仍落在任务根，
    #    但那是**检测步骤自己的产物**，按 artifact 取（不再经 rembg 的输入端口）。
    ok("detect 的坐标文件落在任务根",
       repo.artifact(tid, "detect", "boxes") == task_dir / "boxes.json",
       str(repo.artifact(tid, "detect", "boxes")))
    # 未登记的端口要给一个能看懂的错，而不是 NoneType 崩溃。
    try:
        repo.artifact(tid, "extract", "boxes")
    except KeyError:
        ok("未登记端口 → KeyError（不是 NoneType 崩溃）", True)
    else:
        ok("未登记端口 → KeyError（不是 NoneType 崩溃）", False, "居然成功了")


# ---------------------------------------------------------------- 5. 组件复用
def _check_step_module_page_reuse(ok) -> None:
    """⑤ 步骤页**继承** StepModulePage，且页面里不再抄一遍外设。"""
    import importlib

    from desktop.modules import module_by_key
    from desktop.modules.base import ModulePage, StepModulePage
    from tests.selftests._context import imported_modules

    ok("StepModulePage 是 ModulePage 的子类",
       issubclass(StepModulePage, ModulePage))

    # 拼版页**有意**不继承（源是一批图、执行是纯函数导出）——钉住它，免得将来
    # "为了统一"被硬塞进 StepModulePage 却对不上外壳。
    imposition_cls = importlib.import_module(
        "desktop.modules.imposition"
    ).PAGE
    ok("拼版页直接继承 ModulePage（外壳对不上 StepModulePage）",
       not issubclass(imposition_cls, StepModulePage)
       and issubclass(imposition_cls, ModulePage))

    # 包形态：tests/selftests/flow/step_ports/p02.py → 仓库根是 parents[4]
    root = Path(__file__).resolve().parents[4]
    # ⚠️ **只查普通步骤页**：它们共用的外设必须来自基类。页面里若还出现
    #    `SourceZone(` / `StepControl(`，就是又抄了一遍（这正是 2026-10-03
    #    之前四个页面各抄一遍的形态）。
    banned = ("SourceZone(", "StepControl(")
    for key in _REGULAR_KEYS:
        module = module_by_key(key)
        ok(f"{key} 有导航条目", module is not None, key)
        if module is None:
            continue
        source = (root / _MODULES_DIR / key / "page.py").read_text(encoding="utf-8")
        page_cls = importlib.import_module(
            f"desktop.modules.{module.key}"
        ).PAGE
        ok(f"{key} 页继承 StepModulePage",
           issubclass(page_cls, StepModulePage), str(page_cls.__mro__[:3]))
        clones = [token for token in banned if token in source]
        ok(f"{key} 页不再自建输入区/控制区", not clones, str(clones))
        # 页面也不该再直接 import 那两个模块（应当经基类拿）。
        imported = imported_modules(source)
        leaky = sorted(
            name for name in imported
            if name.endswith(".source_zone") or name.endswith(".control")
        )
        ok(f"{key} 页不直接 import 输入区/控制区模块", not leaky, str(leaky))


# ------------------------------------------------- 6. 详情页元数据（不再 if stage）
def _check_detail_metadata(ctx, ok) -> None:
    """⑥ 详情页那几处 if stage 已换成**声明**：值对、且页面确实读它。"""
    from desktop.steps import ports
    from desktop.store.tasks import STAGES

    # --- spec 层面的值（与改动前的 if-else 逐条对照）---
    ok("extract 按钮是「提取文档图片」",
       _spec_for("extract").run_button_text == "提取文档图片")
    ok("rembg 按钮是「图片去底色」且无提交按钮",
       _spec_for("rembg").run_button_text == "图片去底色"
       and _spec_for("rembg").has_submit is False)
    ok("print 按钮是「生成PDF」且无提交按钮",
       _spec_for("print").run_button_text == "生成PDF"
       and _spec_for("print").has_submit is False)
    # ⚠️ 2026-10-22：第二步「检测文本框」是两步式（检测 → 提交裁图），
    #    第三步去底色只有一步。所以声明 has_submit 的步骤只有 detect。
    ok("detect 按钮是「检测文本框」且有提交按钮",
       _spec_for("detect").run_button_text == "检测文本框"
       and _spec_for("detect").has_submit is True,
       f"{_spec_for('detect').run_button_text} / {_spec_for('detect').has_submit}")
    ok("只有 detect 声明了提交按钮",
       [s for s in STAGES if _spec_for(s).has_submit] == ["detect"],
       str([s for s in STAGES if _spec_for(s).has_submit]))
    ok("print 控制列更宽（400~580），其余 340~440",
       _spec_for("print").control_width == (400, 580)
       and all(_spec_for(s).control_width == (340, 440)
               for s in STAGES if s != "print"))
    ok("detect 用专属区块，其余用「执行记录」",
       [s for s in STAGES if _spec_for(s).panel_extra] == ["detect"]
       and _spec_for("detect").panel_extra == "detect_stats")
    ok("print 历史回填跳过 pdf_name/title_text",
       set(_spec_for("print").history_skip) == {"pdf_name", "title_text"})
    ok("extract 的 pages 只在自动回填时跳过",
       _spec_for("extract").auto_fill_skip == ("pages",)
       and _spec_for("extract").history_skip == ())
    ok("每一步都声明了主预览控件",
       all(_spec_for(s).preview_attr for s in STAGES),
       str({s: _spec_for(s).preview_attr for s in STAGES}))

    # --- 页面层面：真的读 spec，而不是又写回 if stage ---
    # ⚠️ **另建一个详情页 + 一个任务**，不要动共享的 ``ctx.d``/``ctx.tid``：
    #    后面若干模块（rembg / print_stage / stale_chain…）依赖详情页停在特定步骤，
    #    这里 `_select_stage` 会把它们的前提改掉。范式同 ``param_draft``。
    from desktop.pages.taskdetail.page import TaskDetailPage
    from tests.selftests._context import pump

    app, repo = ctx.app, ctx.repo
    tid = repo.create_task(ctx.pdf, "hash-step-ports", "端口样本")
    page = TaskDetailPage(repo)
    try:
        page.set_task(tid)
        pump(app, times=6)

        page._select_stage(2)
        ok("第三步：按钮=图片去底色、提交按钮隐藏",
           page.run_button.text() == "图片去底色"
           and not page.submit_button.isVisibleTo(page), page.run_button.text())
        print_bar = page.bar_index_of_step("print")
        assert print_bar is not None      # ⚠️ 默认流程里有「生成PDF」这一格
        page._select_stage(print_bar)
        ok("第四步：按钮=生成PDF、提交按钮隐藏",
           page.run_button.text() == "生成PDF"
           and not page.submit_button.isVisibleTo(page), page.run_button.text())
        page._select_stage(0)
        ok("第一步：按钮=提取文档图片、提交按钮隐藏",
           page.run_button.text() == "提取文档图片"
           and not page.submit_button.isVisibleTo(page), page.run_button.text())

        page._select_stage(1)
        ok("第二步：显示检测统计、隐藏执行记录",
           page.detect_stats.isVisibleTo(page)
           and not page.history_block.isVisibleTo(page))
        # 「执行记录」另有设置总开关（默认关，用户 2026-11-16）：临时打开再判
        # "第三步用执行记录、不用检测统计"这条 spec 判据。
        from desktop.settings.config import app_config

        _cfg = app_config()
        _before_show = bool(_cfg.showHistory.value)
        _cfg.showHistory.value = True
        try:
            page._select_stage(2)
            ok("第三步：显示执行记录、隐藏检测统计",
               page.history_block.isVisibleTo(page)
               and not page.detect_stats.isVisibleTo(page))
        finally:
            _cfg.showHistory.value = _before_show

        # 控制列宽度跟着 spec 走（第四步更宽）。
        page._select_stage(print_bar)
        wide = (page.control_widget.minimumWidth(),
                page.control_widget.maximumWidth())
        page._select_stage(0)
        narrow = (page.control_widget.minimumWidth(),
                  page.control_widget.maximumWidth())
        ok("控制列宽度按 spec 切换（第四步更宽）",
           wide == (400, 580) and narrow == (340, 440), f"{wide} vs {narrow}")

        # 历史回填的跳过集合也走 spec（值与搬进 spec 前一致）。
        ok("print 历史回填跳过 pdf_name/title_text",
           {"pdf_name", "title_text"} <= page._history_fill_keys("print"),
           str(page._history_fill_keys("print")))
        ok("extract 自动回填跳过 pages、手动历史不跳",
           "pages" in page._auto_fill_keys("extract")
           and "pages" not in page._history_fill_keys("extract"))
    finally:
        try:
            page.shutdown_all_workers()
        except Exception:  # noqa: BLE001 - 收尾失败不该让整个模块报错
            pass
        page.deleteLater()
        # ⚠️ **必须删掉自建任务**（同 ``param_draft``）：任务列表是**共享**的，
        #    后面 ``tasklist_pagination`` 断言"25 条 / 每页 10 条 = 3 页"——
        #    多留一个任务会让它算成 26 条而红，甚至把整条套件带崩。
        repo.delete_task(tid)
        pump(app, times=4)   # 让 deleteLater 真正析构，避免残留线程
