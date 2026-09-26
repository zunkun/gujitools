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


def run(ctx) -> None:
    import time
    from pathlib import Path

    from desktop.pages.taskdetail.view import LazyPanelHost
    from tests.selftests._context import ok

    app, w, d = ctx.app, ctx.w, ctx.d

    def built() -> list[str]:
        """四步面板的构造状态：'建' / '空'。"""
        stack = d.control_stack
        return [
            "建" if stack.widget(i).peek() is not None else "空"
            for i in range(stack.count())
        ]

    # ---- 1. 四个面板都是惰性宿主 ----
    stack = d.control_stack
    lazy_count = sum(
        1 for i in range(stack.count())
        if isinstance(stack.widget(i), LazyPanelHost)
    )
    ok(
        "四个阶段面板全是惰性宿主（谁进去谁才建）",
        lazy_count == stack.count() == 4,
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
    ok("预热只构造第一步的面板，其余保持惰性",
       built() == ["建", "空", "空", "空"], str(built()))

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
       "findChildren(PrintLayoutCanvas)" in code)

    # ---- 3. 进入任务：只有第一步被建出来 ----
    d.set_task(ctx.tid)
    after_enter = built()
    ok("进入详情后第 2/3/4 步面板仍未构造",
       after_enter[1:] == ["空", "空", "空"], str(after_enter))
    ok("第 1 步面板已构造（否则左侧控制区是空白）",
       after_enter[0] == "建", str(after_enter))

    # ---- 4. 切到某一步，才建那一步 ----
    d._select_stage(3)
    app.processEvents()
    ok("切到第四步时第四步面板才被构造",
       built()[3] == "建", str(built()))

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
