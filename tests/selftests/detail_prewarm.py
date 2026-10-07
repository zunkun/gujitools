# -*- coding: utf-8 -*-
"""进详情只建第一步：四个阶段面板**谁进去谁才建** + 缓存判据够快。

背景（2026-09-25 实测，真实 794MB / 320 页《长短经》）
    用户报「从列表点进详情要等几秒，点下去像没反应」。cProfile 钉到：
    首次进详情时 `set_task` 会遍历四个面板复位、并给第四步派默认名——
    碰到**惰性包装器**就把面板现造出来（第四步 print_panel 单项 ~150ms，
    详情页构造的一半），而导入后台正攥着 GIL（PyMuPDF 每页 ~160ms 连续持有）
    时，这段 Python 密集的建控件代码被拖成 **~2 秒**。

现在的契约（用户 2026-09-25 明确要求）：
1. **四个面板全部惰性**——`TaskDetailPage` 构造完成时一个都不建；
2. 进入某一步（`_select_stage`）才建那一步的面板，别的不建；
3. 预热（导入一开始 / 启动后空闲）**只预热第一步**，不替没进去的步骤提前买单；
4. 缓存新鲜度判据必须走 `os.scandir`（320 个文件从 181ms → <40ms）。
"""

NAME = "detail_prewarm"
DEPENDS: list[str] = ["tasklist"]  # 借它建好的窗口与已建任务
TITLE = "进详情只建第一步"


def _prewarm_only_first(probe) -> list[str]:
    """在**干净**详情页上跑一遍真实预热逻辑，返回四步面板的构造状态。

    走的是 ``MainWindow._prewarm_detail_page`` 里那三行的等价写法（取
    ``control_stack.widget(0).panel`` 触发构造）——本模块要钉的是"预热只碰
    第一步"这个**行为**，不是某个具体函数（那个函数在 shell 上，验它自己会
    依赖共享实例的状态）。
    """
    first = probe.control_stack.widget(0)
    if hasattr(first, "peek") and first.peek() is None:
        first.panel  # noqa: B018 - 触发构造即为本意
    return [
        "建" if probe.control_stack.widget(i).peek() is not None else "空"
        for i in range(4)
    ]


def run(ctx) -> None:
    import time
    from pathlib import Path

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.pages.taskdetail.view import LazyPanelHost
    from tests.selftests._context import ok

    app, w = ctx.app, ctx.w

    def built(page) -> list[str]:
        """四步面板的构造状态：'建' / '空'（第 5 位是拼版占位面板，不查）。

        ⚠️ **必须显式传页**、且传的是**干净**实例——惰性面板不可逆
        （``LazyPanelHost`` 没有"退回未构造"的口子），而 ``ctx.d`` 是**全轮
        共享**的同一个详情页，前面的模块（如 detail_bpm_render 为了验寻址会
        ``_select_stage``）早把它的面板建满了，拿它断言"其余保持惰性"必然假红。
        共享 ``ctx.d`` 只用来查"实例存在"，不参与构造状态断言。
        """
        stack = page.control_stack
        return [
            "建" if stack.widget(i).peek() is not None else "空"
            for i in range(4)
        ]

    # ---- 1. 四个面板都是惰性宿主 ----
    # 控制栈共 5 位：4 个惰性阶段面板 + 1 个「图片拼版」占位详情面板
    # （伪步骤，无参数无惰性必要，见 ImpositionMixin）
    # ⚠️ 查在**干净**实例上：共享 ctx.d 的步骤条可能被前序模块按自定义流程
    # 重建过（格数未必还是 5），拿它断言会把流程差异误报成"不是惰性宿主"。
    probe = TaskDetailPage(store=w.list_page.store, parent=w)
    stack = probe.control_stack
    lazy_count = sum(
        1 for i in range(stack.count())
        if isinstance(stack.widget(i), LazyPanelHost)
    )
    ok(
        "四个阶段面板全是惰性宿主（谁进去谁才建）",
        lazy_count == 4 and stack.count() == 5,
        f"惰性 {lazy_count} / 共 {stack.count()}",
    )

    # ---- 2. 预热接线在（宿主页面级断言，不是组件级）----
    ok(
        "MainWindow 有启动预热的延时常量",
        getattr(w, "PREWARM_DELAY_MS", None) not in (None, 0),
        str(getattr(w, "PREWARM_DELAY_MS", None)),
    )
    ok("列表页暴露 import_queued（导入一开始就预热）",
       hasattr(w.list_page, "import_queued"))
    ok("预热方法存在（_prewarm_detail_page）",
       callable(getattr(w, "_prewarm_detail_page", None)))
    # ⚠️ 惰性面板**一旦构造就不可逆**（LazyPanelHost 没有"退回未构造"的口子），
    # 而 ctx.d 是**全轮共享**的同一个详情页。本模块断言的是"预热只建第一步、
    # 其余保持惰性"，前提是**此刻还没人进过任何步骤**——前面的模块（如
    # detail_bpm_render 为了验寻址会 _select_stage）早已把面板建出来了。
    # 所以第 1 段起就用**自建的干净详情页** ``probe`` 来验，而不是断言共享实例
    # 的初始态（否则任何在前面的模块碰过步骤，本模块就假红）。
    ok("新详情页构造完四个面板全是惰性的（谁进去谁才建）",
       built(probe) == ["空", "空", "空", "空"], str(built(probe)))
    warmed = _prewarm_only_first(probe)
    ok("预热只构造第一步的面板，其余保持惰性",
       warmed == ["建", "空", "空", "空"], str(warmed))
    # ---- 2b. 收尾/补发逻辑不许用 getattr 探测把面板"顺手建出来" ----
    # `LazyPanelHost.__getattr__` 会转发到内层面板（不存在就现造），所以
    # `getattr(host, "xxx", None)` 会**立刻构造**那个面板。2026-09-26 自己踩到：
    # 给 closeEvent 加"补发未提交的版面拖动"时用了 getattr 探测，护栏当场红成
    # 四个面板全建。收尾/补发一律按**具体类** findChildren，或先 peek() 判空跳过。
    page_src = (
        (Path(__file__).resolve().parents[2] / "desktop" / "pages" / "taskdetail" / "page.py")
        .read_text(encoding="utf-8")
    )
    code = "\n".join(line.split("#", 1)[0] for line in page_src.splitlines())
    ok("收尾逻辑不靠 getattr 探测能力（会 Materialize 惰性面板）",
       'getattr(widget, "shutdown_workers", None)' in code
       and 'widget.peek() is None' in code,
       "找不到 peek 保护")
    ok("版面补发按具体类查（不用属性探测）",
       "findChildren(cls)" in code
       and "(PrintLayoutCanvas, ImpositionCanvas)" in code,
       "补发应遍历具体类列表，不能 getattr 探测（会 Materialize 惰性面板）")

    # ---- 3. 进入任务：只有第一步被建出来 ----
    # ⚠️ 另起一个**干净**详情页：``probe`` 刚被预热建了第一步（不可逆），
    # 拿它验"进入任务只建第一步"会永远假红。
    fresh = TaskDetailPage(store=w.list_page.store, parent=w)
    # ⚠️ 进任务前先把"上次停留的步骤"钉回第一步：详情页现在会**回到上次停留的
    #    步骤**（page.py::_initial_stage_index，2026-09-30），本段要验的是
    #    "落在第一步时只建第一步的面板"，不能受前面模块切过哪一步的影响。
    #    （"回到上次那一步"本身由 tests/selftests/last_stage.py 单独验。）
    ctx.repo.save_last_stage(ctx.tid, "extract")
    ok("干净详情页在 set_task 之前四步全是惰性的",
       built(fresh) == ["空", "空", "空", "空"], str(built(fresh)))
    fresh.set_task(ctx.tid)
    after_enter = built(fresh)
    ok("进入详情后第 2/3/4 步面板仍未构造",
       after_enter[1:] == ["空", "空", "空"], str(after_enter))
    ok("第 1 步面板已构造（否则左侧控制区是空白）",
       after_enter[0] == "建", str(after_enter))

    # ---- 4. 切到某一步，才建那一步 ----
    # ⚠️ **不能再用写死下标 3**：BPM 驱动后格序含可选节点占位（默认流程
    # extract=0/detect=1/rembg=2/imposition=3/print=4），``_select_stage(3)``
    # 落在「图片拼版」上——它是条件伪步骤，不建 print 面板。这条断言正是
    # 被这次改造逼出来的：寻址必须走 ``bar_index_of_step`` 查表。
    print_index = fresh.bar_index_of_step("print")
    ok("第四步的格序是 4（不是 3：格序含拼版占位）",
       print_index == 4, str(print_index))
    assert print_index is not None      # ⚠️ 上一行已判过等于 4
    fresh._select_stage(print_index)
    app.processEvents()
    ok("切到第四步时第四步面板才被构造",
       built(fresh)[3] == "建", str(built(fresh)))
    fresh.deleteLater()
    probe.deleteLater()

    # ---- 5. 缓存新鲜度判据要够快（320 个文件的目录）----
    from desktop.components.viewers.pdf_viewer import PdfViewerWidget

    cache = ctx.tmp / "prewarm_cache_probe"
    cache.mkdir(parents=True, exist_ok=True)
    for i in range(320):
        (cache / f"{i + 1:04d}.jpg").write_bytes(b"x")
    viewer = PdfViewerWidget()
    viewer._cache_dir = cache
    started = time.perf_counter()
    viewer._cache_is_being_filled()
    cost_ms = (time.perf_counter() - started) * 1000
    ok("缓存新鲜度判据扫描 320 个文件 < 40ms（scandir，不是 glob+stat）",
       cost_ms < 40, f"实测 {cost_ms:.1f} ms")
    viewer.set_pdf(None)  # 收尾：停掉它的定时器
