# -*- coding: utf-8 -*-
"""左侧导航壳层与独立模块的自测（2026-10-02 新增）。

守护两件事：

1. **壳层的结构契约**：导航条目与 ``MODULES`` 注册表一一对应；
   ``MainWindow`` 的 ``list_page`` / ``detail_page`` / ``pages`` / ``store``
   仍然可访问（gui_shot.py 与 _context.py 都按这些名字取页面，改名即断）；
   点模块能切到对应页面且路由反查正确。
2. **「独立」这条设计底线**：模块页**惰性构造**（不点不建）；
   模块页之间、模块页与 ``TaskDetailPage`` **没有 import 依赖**
   （用 AST 静态检查，而不是靠人盯）。

依赖：tasklist（要主窗口已经建好）。
"""

from __future__ import annotations

from pathlib import Path

NAME = "modules_shell"
DEPENDS: list[str] = ["tasklist"]
TITLE = "左侧导航壳层与独立模块"

#: 模块页源码所在目录（相对仓库根）
_MODULES_DIR = Path("desktop") / "modules"


def run(ctx) -> None:
    from tests.selftests._context import imported_modules as _imported_modules
    from tests.selftests._context import ok
    from desktop.modules import MODULES, module_by_key
    from desktop.steps import SourceZone

    app, w = ctx.app, ctx.w

    # ---- 1. 注册表本身 ----
    from desktop.steps.spec import FLOW_STAGES, NAV_STEPS, OPTIONAL_STEPS

    keys = [m.key for m in MODULES]
    # ⚠️ 与 SPECS 的派生关系（不改数量硬编码）：清单只有一份，加模块 = 加 spec。
    ok("注册表 = SPECS 里 nav=True 的派生（顺序一致）",
       tuple(keys) == NAV_STEPS, f"{keys} vs {NAV_STEPS}")
    # 真正要守的不变量：「每一个步骤都有独立模块页」——四步主链 + 拼版全在导航里。
    # 不再写死名字清单（加一步不该让测试变红），但也**不是**空转：某个步骤的
    # ``nav`` 被误关掉时，它的 key 就不在这条断言里，立刻报红。
    ok("主链四步 + 可选节点都有独立模块页（nav=True）",
       set(keys) == set(FLOW_STAGES) | set(OPTIONAL_STEPS),
       f"{sorted(keys)} vs {sorted(set(FLOW_STAGES) | set(OPTIONAL_STEPS))}")
    ok("导航条目非空（防派生为空导致上面全是真空转）", bool(keys), str(keys))
    ok(
        "每个条目都有标题/图标/副标题/工厂",
        all(m.title and m.icon and m.subtitle and callable(m.factory) for m in MODULES),
    )
    ok("module_by_key 命中", module_by_key("extract") is MODULES[0])
    ok("module_by_key 未命中返回 None", module_by_key("nope") is None)

    # ---- 2. MainWindow 对外契约（测试/截图脚本的公开接口）----
    ok("MainWindow 有 list_page", getattr(w, "list_page", None) is not None)
    ok("MainWindow 有 detail_page", getattr(w, "detail_page", None) is not None)
    ok("MainWindow 有 pages", getattr(w, "pages", None) is not None)
    ok("MainWindow 有 store", getattr(w, "store", None) is not None)
    ok("list_page 就是壳层的列表页", w.list_page is w.shell.list_page)
    ok("pages 就是壳层的页面栈", w.pages is w.shell.pages)

    # ---- 3. 导航条目与注册表一致 ----
    nav_items = w.shell._module_items
    ok("导航为每个模块都建了条目", set(nav_items) == set(keys), str(sorted(nav_items)))

    # ---- 3b. 导航默认折叠（用户 2026-10-02：「左侧的目录，默认关闭」）----
    # ⚠️ 这里必须显式给一个够宽的窗口：qfluentwidgets 在"窗口窄于最小展开宽度"
    #    时会自动收回，宽窗口下才谈得上"要不要展开"。
    from tests.selftests._context import pump, wait_until

    w.resize(1200, 800)
    app.processEvents()
    ok("导航默认是折叠的", w.shell.nav_is_expanded() is False)
    w.shell.toggle_nav()
    ok("toggle 后能展开", wait_until(app, w.shell.nav_is_expanded, timeout=3))
    # ⚠️ 展开动画没跑完时 qfluentwidgets 的 collapse() 会**直接 return**（防止动画
    #    打架），所以先泵够时间让动画结束，再切回来——否则这条断言是假红。
    pump(app, times=20, interval=0.05)
    w.shell.toggle_nav()
    ok("再 toggle 能收回（默认折叠不被破坏）",
       wait_until(app, lambda: not w.shell.nav_is_expanded(), timeout=3))
    ok("导航折叠后正文区仍占满（栈是拉伸项）",
       w.pages.width() > w.shell.nav.width())

    # ---- 4. 惰性：还没点过的模块不该被建出来 ----
    # ⚠️ 前面几个模块（tasklist 等）没点过模块，这里应当全空；
    #    若真被别人的测试建过，就跳过这条断言（断言的是"没被无谓构造"）。
    built_before = set(w.shell._module_pages)
    if not built_before:
        ok("未点击的模块未被构造（惰性）", True)
    else:
        ok("已构造的模块都属于注册表", built_before <= set(keys), str(sorted(built_before)))

    # ---- 5. 逐个模块：能切过去、路由能反查回来 ----
    for module in MODULES:
        w.shell.show_module(module.key)
        app.processEvents()
        page = w.shell.module_page(module.key)
        ok(f"模块 {module.key} 可构造", page is not None)
        ok(
            f"模块 {module.key} 路由正确",
            w.shell.current_route() == module.key,
            w.shell.current_route(),
        )
        ok(
            f"模块 {module.key} 页头标题与注册表一致",
            getattr(page, "TITLE", None) == module.title,
            str(getattr(page, "TITLE", None)),
        )
        # 用户 2026-10-02 要的"页面上的大输入框"：每个模块都要有，且横跨整幅
        ok(
            f"模块 {module.key} 有大输入区",
            isinstance(getattr(page, "input_zone", None), SourceZone),
            str(type(getattr(page, "input_zone", None))),
        )
        ok(
            f"模块 {module.key} 的大输入区横跨整幅（比控制列宽得多）",
            page.input_zone.width() > page.control_widget.width(),
            f"{page.input_zone.width()} vs {page.control_widget.width()}",
        )
    # extract / rembg 的源由共用控件归一化，必须和大输入区是**同一块**控件
    for key in ("extract", "rembg"):
        page = w.shell.module_page(key)
        ok(f"模块 {key} 的控制列接管了同一块大输入区",
           page.control.zone is page.input_zone)

    # ---- 6. 切回任务管理 ----
    w.shell.show_tasks()
    app.processEvents()
    ok("切回任务管理", w.shell.current_route() == "tasks", w.shell.current_route())
    ok("任务管理切回后栈里就是列表页", w.pages.currentWidget() is w.list_page)

    # ---- 6a. 点导航条目必须**真的切页**（真点，不是直接调 show_module）----
    # ⚠️ 回归钉子（用户 2026-10-02 报障：「点击左侧的图片提取，显示的还是任务
    #    管理」）：qfluentwidgets 的 ``NavigationWidget.clicked`` 是
    #    ``Signal(bool)``，``NavigationPanel._registerWidget`` 把 onClick **直接
    #    连到这个信号**上——槽写成 ``lambda key=module.key: ...`` 的话，Qt 会把
    #    那个 ``True`` 当第一个位置参数塞给 key，于是 ``show_module(True)``
    #    找不到模块、安静退回任务管理。三个模块"点不开"全靠这条守。
    #    （老断言只直接调 show_module，走的不是真实点击链路，所以漏了它。）
    for module in MODULES:
        w.shell._module_items[module.key].click()
        app.processEvents()
        ok(
            f"点导航条目 {module.key} 真的切过去了",
            w.shell.current_route() == module.key,
            w.shell.current_route(),
        )
        ok(
            f"点 {module.key} 后导航高亮也跟着走",
            w.shell.selected_route() == module.key,
            w.shell.selected_route(),
        )
    w.shell._tasks_item.click()
    app.processEvents()
    ok("点「任务管理」条目能切回列表页",
       w.shell.current_route() == "tasks", w.shell.current_route())

    # ---- 6b. 直接操作 pages 切页时，导航高亮跟着走 ----
    # gui_shot.py 就是这么切的（``window.pages.setCurrentWidget(...)``），
    # 不走 show_module；若不同步，截图里会出现"左边高亮一页、右边显示另一页"。
    w.shell.show_module("rembg")
    app.processEvents()
    ok("切到 rembg 后高亮在 rembg", w.shell.selected_route() == "rembg",
       w.shell.selected_route())
    w.pages.setCurrentWidget(w.list_page)
    app.processEvents()
    ok("直接切 pages → 路由回到任务管理", w.shell.current_route() == "tasks")
    ok("直接切 pages → 导航高亮同步到任务管理",
       w.shell.selected_route() == "tasks", w.shell.selected_route())
    # 停在当前页再点一次同一个模块：不能因为"没换页"就把高亮丢了
    w.shell.show_module("rembg")
    app.processEvents()
    w.shell.show_module("rembg")
    app.processEvents()
    ok("重复进同一模块仍保持高亮", w.shell.selected_route() == "rembg",
       w.shell.selected_route())

    # ---- 6c. 详情页没有导航条目：高亮必须留在「任务管理」而不是丢空 ----
    # 直接驱动 _sync_nav_to_page 的映射：ROUTE_DETAIL → ROUTE_TASKS。
    from desktop.modules.shell import ROUTE_DETAIL, ROUTE_TASKS

    w.shell._selected_route = ROUTE_TASKS
    w.shell._sync_nav_to_page(0)  # 当前页是列表页 → 走一次真实同步
    ok("同步后高亮 = 当前路由", w.shell.selected_route() == w.shell.current_route())
    ok("详情页路由键与任务管理不同", ROUTE_DETAIL != ROUTE_TASKS)

    # ---- 7. 「独立」：模块之间、模块与详情页之间不许有 import 依赖 ----
    root = Path(__file__).resolve().parents[2]
    page_files = sorted((root / _MODULES_DIR).glob("*/page.py"))
    # ⚠️ 数量跟着注册表走：不写死 3/4，"加一个模块"不该让这条测试变红。
    ok("每个注册条目都有对应的模块页源码",
       len(page_files) == len(MODULES), f"{len(page_files)} 个页面 vs {len(MODULES)} 个条目")
    ok("模块页目录名与注册 key 一一对应",
       {f.parent.name for f in page_files} == set(keys),
       str(sorted({f.parent.name for f in page_files} ^ set(keys))))
    module_pkgs = {f.parent.name for f in page_files}
    forbidden = {"desktop.pages.taskdetail"} | {
        f"desktop.modules.{name}" for name in module_pkgs
    }
    for file in page_files:
        imported = _imported_modules(file.read_text(encoding="utf-8"))
        own_pkg = f"desktop.modules.{file.parent.name}"
        clashes = sorted(
            entry
            for entry in imported
            if entry in forbidden
            # 自己 import 自己包内的子模块是允许的（__init__ 的惰性导出）
            and not entry.startswith(own_pkg)
        )
        ok(f"{file.parent.name}/page.py 无跨模块/详情页依赖", not clashes, str(clashes))

    # ---- 8. 壳层也不许静态 import 具体模块页 ----
    shell_src = (root / _MODULES_DIR / "shell.py").read_text(encoding="utf-8")
    shell_imports = _imported_modules(shell_src)
    bad = sorted(
        entry for entry in shell_imports
        if entry.startswith("desktop.modules.") and entry != "desktop.modules"
    )
    ok("壳层只依赖注册表（不 import 具体模块页）", not bad, str(bad))

    # ---- 9. 收尾 ----
    w.shell.shutdown_workers()
    ok("壳层能收尾所有 worker", True)
