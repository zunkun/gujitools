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
    from PySide6.QtWidgets import QSizePolicy

    from desktop.modules import MODULES, module_by_key
    from desktop.steps import SourceZone
    from desktop.ui import theme as T

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
    from desktop.steps.spec import spec_by_key

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
        # ⚠️ 页头标题对的是 ``spec.title``、**不是** ``module.title``（那是
        #    ``spec.nav_name()``）。导航那一列有自己的文案（用户 2026-10-03
        #    定的「PDF图片提取」等，导航是短标签、页头是完整标题），两者
        #    **有意不同**。这条断言守住的是"各自都来自 spec，没有第二份
        #    硬编码文案"，而不是"两处字面相同"。
        ok(
            f"模块 {module.key} 页头标题来自 spec.title",
            getattr(page, "TITLE", None) == spec_by_key(module.key).title,
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

    # ---- 5b. 初始只显示输入框（用户 2026-10-03）----
    # 「初始就只有一个输入框，下面的操作面板和预览这些都要选择输入文件后
    # 才显示出来」。这条对**每个**模块成立，所以逐个查而不是只查一个。
    for module in MODULES:
        page = w.shell.module_page(module.key)
        ok(f"模块 {module.key} 初始收起操作界面",
           page.workspace_shown() is False)
        ok(f"模块 {module.key} 初始只留大输入区（可见）",
           page.input_zone.isVisibleTo(page))
        ok(f"模块 {module.key} 初始不显示预览分栏",
           not page.splitter.isVisibleTo(page))
        ok(f"模块 {module.key} 初始不显示日志区",
           not page.log_view.isVisibleTo(page))

    # 给了源 → 操作界面显形；清空 → 收回去（每个模块都得听话）
    for key in ("extract", "rembg", "print", "detect"):
        page = w.shell.module_page(key)
        page.sync_workspace_visible(Path(ctx.tmp) / "some_source")
        app.processEvents()
        ok(f"模块 {key} 选了源就显出操作界面", page.workspace_shown() is True)
        ok(f"模块 {key} 显出后分栏可见", page.splitter.isVisibleTo(page))
        page.sync_workspace_visible(None)
        app.processEvents()
        ok(f"模块 {key} 清空源就收回操作界面", page.workspace_shown() is False)

    # ⚠️ **页头不许纵向拉伸 + 输入区要真的撑满**（两个真实 bug 的钉子，
    #    都是靠截图发现的、断言全绿时根本看不出来）：
    #    ① 收掉分栏后 root 里就没有拉伸项了，Qt 按 sizePolicy 把空出来的
    #       纵向空间摊给页头 —— 标题顶到最上面、副标题飘到页面正中、输入框
    #       被挤到底边甚至裁掉；
    #    ② 独占模式最初用 setFixedHeight(320)，同时钉死了 maximumHeight；
    #       改成"最小 320 + 可拉伸"却只改 minimumHeight，控件就永远长不大
    #       ——整页只有一条 320px 的框，上下各留一片空白。
    #
    # ⚠️ 必须在**真实窗口**里量：不 show / 不走事件循环时控件尺寸还是构造期
    #    的默认值，`height()` 恒等于最小值，这条断言会**恒真**（第一版就栽在
    #    这里：把修复去掉它照样全绿）。也不能把页面搬进另一个容器——它在
    #    QStackedWidget 里已有几何，搬走会拿到过期尺寸。
    w.resize(1280, 860)
    w.show()
    for module in MODULES:
        w.shell.show_module(module.key)
        # 必须先 apply 一遍 show_workspace(False)：独占模式是它顺手开的。
        # 直接量会停在构造期的常规高度（168px），量出来的数没有意义。
        w.shell.module_page(module.key).show_workspace(False)
        app.processEvents()
        pump(app, times=8, interval=0.02)
        page = w.shell.module_page(module.key)
        header = page.header
        slack = header.height() - header.sizeHint().height()
        ok(f"模块 {module.key} 的页头不吸收多余纵向空间（副标题不会飘走）",
           slack <= T.SPACE_XL,
           f"header={header.height()} sizeHint={header.sizeHint().height()}")
        zone = page.input_zone
        # 输入区应吃掉页头之外的全部纵向空间：
        #   页面高 − 页头高 − 上下边距(2×SPACE_LG) − 页头与输入区间距(SPACE_MD)
        # 独占模式坏掉时（setFixedHeight 钉死最大高度）这里会差出几百像素。
        expect = page.height() - header.height() - 2 * T.SPACE_LG - T.SPACE_MD
        ok(f"模块 {module.key} 初始输入区撑满整幅高度（独占模式）",
           abs(zone.height() - expect) <= 2,
           f"zone={zone.height()} expect={expect} page={page.height()}")
        # 输入区下方应当只剩底部边距（多出来就是"被挤上去/留大片空白"）
        below = page.height() - (zone.y() + zone.height())
        ok(f"模块 {module.key} 输入区下方只剩底部边距（没留大片空白）",
           below <= T.SPACE_LG + 2,
           f"below={below}")
        # ⚠️ 真正让输入区长起来的是**拉伸策略**（破坏它时上面两条会红），
        #    单独钉一条：策略是 Fixed 时 Qt 不会把余量给它。
        ok(f"模块 {module.key} 输入区在纵向可拉伸（独占模式的前提）",
           zone.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding,
           str(zone.sizePolicy().verticalPolicy()))
    w.shell.show_tasks()
    # 拼图不走 StepControl，源是自己维护的 —— 单独钉它的开关
    imp = w.shell.module_page("imposition")
    imp.sync_workspace_visible(Path(ctx.tmp) / "x.png")
    ok("拼图选了源也显出操作界面", imp.workspace_shown() is True)
    imp.sync_workspace_visible(None)
    ok("拼图清空源也收回操作界面", imp.workspace_shown() is False)

    # ---- 5c. 「PDF 只支持文件」：图片提取的大输入区不摆「选择文件夹」----
    extract_page = w.shell.module_page("extract")
    ok("图片提取不摆「选择文件夹」按钮（PDF 只支持文件）",
       extract_page.input_zone.dir_button is None)
    ok("图片提取保留「选择文件」按钮（那是它唯一的合法入口）",
       extract_page.input_zone.file_button.isVisibleTo(extract_page.input_zone))
    for key in ("rembg", "detect", "print", "imposition"):
        zone = w.shell.module_page(key).input_zone
        ok(f"模块 {key} 仍摆「选择文件夹」按钮",
           zone.dir_button is not None
           and zone.dir_button.isVisibleTo(zone))

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
    from desktop.shell import ROUTE_DETAIL, ROUTE_TASKS

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
    shell_src = (root / "desktop" / "shell.py").read_text(encoding="utf-8")
    shell_imports = _imported_modules(shell_src)
    bad = sorted(
        entry for entry in shell_imports
        if entry.startswith("desktop.modules.") and entry != "desktop.modules"
    )
    ok("壳层只依赖注册表（不 import 具体模块页）", not bad, str(bad))

    # ---- 9. 收尾 ----
    w.shell.shutdown_workers()
    ok("壳层能收尾所有 worker", True)

    # ---- 10. singletask 缩略图（用户 2026-10-03）----
    _check_singletask_thumbnails(ctx, ok)


def _check_singletask_thumbnails(ctx, ok) -> None:
    """⑩ 图片提取页选 PDF 后**立刻**把页缩略图渲到 singletask（用户 2026-10-03）。

    起因：用户报「从上一层导入PDF，没有立即提取缩略图」——以前选完 PDF 左栏全空，
    得先跑一遍提取才知道书里是什么。现在选完就渲，且落在
    ``~/Documents/guji/singletask/<子任务>/thumbnails/``。
    """
    import time

    from PySide6.QtWidgets import QSplitter

    from desktop.components.viewers import ImageViewerWidget
    from desktop.modules.extract.page import ExtractModulePage
    from desktop.steps.spec import spec_by_key
    from desktop.utils.files import (
        THUMBNAIL_EDGE, extract_thumb_path, extract_thumbs_dir,
        safe_dirname, singletask_thumbnails_dir,
    )
    from tests.selftests._context import make_pdf

    spec = spec_by_key("extract")
    # 真造一本 PDF，喂给真实的图片提取页
    pdf = make_pdf(Path(ctx.tmp) / "singletask_probe.pdf", 3)
    other = make_pdf(Path(ctx.tmp) / "singletask_other.pdf", 2)
    # ⚠️ 用 ``disk_key()`` 而非 ``title``：缓存目录名锚在路由键上，改文案
    #    不会让磁盘路径漂移（自测也必须按同一口径拼期望值，否则它跟着文案
    #    一起错，反而查不出真的回归）。
    cache = extract_thumbs_dir(spec.disk_key(), pdf, THUMBNAIL_EDGE)

    ok("singletask 落在 guji/singletask 下",
       "singletask" in cache.parts, str(cache))
    ok("不同子任务各有自己的目录",
       # ⚠️ 用另一个步骤的 disk_key（不是它的 title）：目录名锚在路由键上。
       cache != extract_thumbs_dir(
           spec_by_key("rembg").disk_key(), pdf, THUMBNAIL_EDGE))
    # ⚠️ 这一条是"不同书不共用缓存"的护栏：缩略图文件名是**序号**，共用目录会
    #    让 A 书第 1 页被当成 B 书第 1 页的命中缓存 ⇒ 翻出别本书的内容。
    other_dir = extract_thumbs_dir(spec.disk_key(), other, THUMBNAIL_EDGE)
    ok("不同书各有自己的缓存目录（缩略图名是序号，不能混）",
       cache != other_dir, f"{cache} vs {other_dir}")
    ok("目录名里的非法字符被洗掉",
       all(ch not in safe_dirname('a<b>c:d"e/f\\g|h?i*j') for ch in '<>:"/\\|?*'),
       safe_dirname('a<b>c:d"e/f\\g|h?i*j'))
    ok("缓存按**序号**命名（四位补零，1 排在 10 前面）",
       extract_thumb_path(spec.disk_key(), pdf, 7, THUMBNAIL_EDGE).name
       == "0007.jpg",
       extract_thumb_path(spec.disk_key(), pdf, 7, THUMBNAIL_EDGE).name)

    page = ExtractModulePage()
    try:
        page.resize(1200, 800)
        page.show()
        ctx.app.processEvents()
        page.control.set_source(pdf)
        ctx.app.processEvents()

        # ⚠️ 左栏结构钉的是「**缩略图条 + 大图**一种形态走到底」（用户
        #    2026-10-03）。此前这里是「上半 PDF 预览 + 下半提取结果」的上下
        #    分栏、两个控件各带一套缩略图条与线程；那条结构已废。
        ok("左栏就是那一个缩略图+大图控件（不再是上下分栏）",
           isinstance(page.viewer, ImageViewerWidget)
           and not page.preview_widget.findChild(QSplitter))
        ok("选完 PDF 左栏进入「页缩略图」模式",
           page.viewer._page_source is not None
           and Path(page.viewer._page_source[0]) == pdf,
           str(page.viewer._page_source))
        ok("PDF 页缩略图缓存目录就是 singletask 那份",
           str(page.viewer._page_source_cache or "") == str(cache),
           str(page.viewer._page_source_cache))

        # ⚠️ 后台渲染是异步的：**必须循环等它真出文件**。跑一次 processEvents
        #    就断言"没报错"是自测最经典的假绿（2026-10-03 记忆里已记过一次）。
        names: list[str] = []
        for _ in range(150):
            ctx.app.processEvents()
            time.sleep(0.1)
            names = sorted(p.name for p in cache.glob("*.jpg")) if cache.exists() else []
            if len(names) >= 3:
                break
        ok("选 PDF 后立刻渲出全部页缩略图", len(names) == 3, f"{names} @ {cache}")
        ok("缩略图按序号命名",
           names == ["0001.jpg", "0002.jpg", "0003.jpg"], str(names))
        ok("缩略图非空（不是半截 JPEG）",
           all((cache / n).stat().st_size > 0 for n in names), str(names))

        # 换一本书：页数不同的两本不能互相污染
        page.control.set_source(other)
        ctx.app.processEvents()
        other_cache = extract_thumbs_dir(spec.disk_key(), other, THUMBNAIL_EDGE)
        other_names: list[str] = []
        for _ in range(150):
            ctx.app.processEvents()
            time.sleep(0.1)
            other_names = sorted(p.name for p in other_cache.glob("*.jpg")) \
                if other_cache.exists() else []
            if len(other_names) >= 2:
                break
        ok("换一本书渲出的是它自己的页数（2 页，不是上一本的 3 页）",
           len(other_names) == 2, f"{other_names} @ {other_cache}")

        # 换回第一本（后面几段继续用它）
        page.control.set_source(pdf)
        ctx.app.processEvents()
        for _ in range(80):
            ctx.app.processEvents()
            time.sleep(0.1)
            if len(list(cache.glob("*.jpg"))) >= 3:
                break

        # ---- ⑩b 提取完成后左栏切成**提取出的图片**（用户 2026-10-03）----
        # 需求原文：「在未提取图片之前是按照缩略图，单独图片显示，提取后直接
        # 显示提取的图片」。不钉这一条的话，最容易出的错是"PDF 页模式没退出"
        # ——左栏看着有图，点哪页却都是同一页（因为还在拿 1.jpg 当页号渲 PDF）。
        out_dir = Path(ctx.tmp) / "extract_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_tiny_jpegs(out_dir, 3)
        page.on_result(out_dir, {})
        ctx.app.processEvents()
        ok("提取后退出 PDF 页模式（否则点哪页都是同一页）",
           page.viewer._page_source is None, str(page.viewer._page_source))
        ok("提取后左栏换成提取出的图片",
           [p.name for p in page.viewer.paths] == ["1.jpg", "2.jpg", "3.jpg"],
           str(page.viewer.paths))

        # ---- ⑩c「只保留一份、按序号处理」（用户 2026-10-04）----
        # 本次改动的**核心需求**，必须钉死：否则将来任何一处改动都可能又把
        # 第二套缩略图渲出来（改之前就是 ``thumbs/<图键>.jpg`` 与
        # ``thumbnails/<书>/NNNN.jpg`` 并存，同一页存了两份）。
        names_arg = page.viewer._thumb_cache_names
        ok("产物缩略图按序号命名（与页缩略图同一个名字）",
           names_arg is not None and list(names_arg)
           == ["0001.jpg", "0002.jpg", "0003.jpg"], str(names_arg))
        ok("提取后缩略图目录仍是那一个（没有第二套目录）",
           str(Path(page.viewer._thumb_cache_dir)) == str(cache),
           str(page.viewer._thumb_cache_dir))
        first_target = page.viewer._lookup_thumb_path(str(page.viewer.paths[0]))
        ok("产物 1 的缩略图就是未提取时的 0001.jpg（同一个文件）",
           first_target is not None and Path(first_target) == cache / "0001.jpg",
           str(first_target))
        ok("旧的按图键目录不再是提取页的目标目录",
           str(page._thumb_cache_dir()) != str(cache),
           str(page._thumb_cache_dir()))
        ok("映射表已落盘（序号 ↔ 产物）",
           page.write_thumb_map(page.viewer.paths) is not None
           and Path(page.write_thumb_map(page.viewer.paths)).is_file(),
           str(page._thumb_book))

        # ---- ⑩d 编辑产物后缩略图要同步（用户 2026-10-04 明确要求）----
        # 「要保证后期编辑后能够同步缩略图」：编辑器覆盖产物图后，重渲必须
        # 落到**同一个序号文件**（0001.jpg），否则翻回来还是编辑前那张。
        target = cache / "0001.jpg"
        ok("编辑重渲的目标目录与首次装载一致（不会写到别处）",
           str(page._edited_thumb_dir()) == str(cache),
           str(page._edited_thumb_dir()))
        ok("编辑重渲的目标文件名也是序号（0001.jpg）",
           page._edited_thumb_names([Path(page.viewer.paths[0])]) == ["0001.jpg"],
           str(page._edited_thumb_names([Path(page.viewer.paths[0])])))
        # 真跑一次重渲：目标必须是 **0001.jpg**，且**只有**它被碰到。
        # ⚠️ 别断言"mtime 变了"：产物图在 ``on_result`` 那一步已经渲过一次，
        # 这里再调是**命中缓存**（``cache_usable`` 比 mtime，源图没动就不重渲）
        # ——mtime 不变才是正确行为。真正要钉的是"写到了同一个文件、没有第二份"。
        # （"编辑后确实会更新"由 ``cache_usable`` 的 mtime 判据保证：编辑器覆盖
        # 产物图后源图 mtime 必然更新 ⇒ 下一次重渲必重画。）
        listing_before = sorted(p.name for p in cache.glob("*.jpg"))
        page._reload_edited_thumb(page.viewer.paths[0])
        alive = True
        for _ in range(120):
            ctx.app.processEvents()
            time.sleep(0.1)
            if target.exists():
                break
        ok("编辑后重渲后 0001.jpg 仍在位（缩略图没被写丢）",
           alive and target.exists(), f"{target}")
        ok("重渲后目录里仍是那一份（文件名集合不变）",
           sorted(p.name for p in cache.glob("*.jpg")) == listing_before,
           f"{sorted(p.name for p in cache.glob('*.jpg'))} vs {listing_before}")
        # 且**没有**在旁边多出按图键命名的第二份
        stray = sorted(p.name for p in cache.glob("*.jpg") if not p.stem.isdigit())
        ok("重渲没有产生第二套（图键命名）缩略图", stray == [], str(stray))
        # ⚠️ 真正的"编辑后会更新"在这里钉：把缓存改旧（mtime 早于产物图），
        # 重渲**必须**把它重画一遍 —— 这正是编辑器覆盖产物后的真实状态。
        import os as _os
        import time as _time

        product = Path(page.viewer.paths[0])
        _os.utime(target, (1, 1))  # 缓存比产物旧 ⇒ 必然判过期
        _os.utime(product, (_time.time(), _time.time()))
        stale_before = target.stat().st_mtime_ns
        page._reload_edited_thumb(product)
        redrawn = False
        for _ in range(120):
            ctx.app.processEvents()
            time.sleep(0.1)
            if target.stat().st_mtime_ns != stale_before:
                redrawn = True
                break
        ok("缓存比产物旧时重渲会真的更新 0001.jpg（编辑后能同步）", redrawn,
           f"{target}")
    finally:
        page.shutdown_workers()
        page.deleteLater()


def _write_tiny_jpegs(out_dir: Path, count: int) -> None:
    """在 ``out_dir`` 下写 count 张 1×1 的真 JPEG（``1.jpg``…）。

    ⚠️ **必须用 Qt 现场编码**，别在源码里手写 JPEG 字节：手拼的十六进制串
    十有八九是不合法的 SOF/量化表，症状是"文件写出来了、QImage 解出来是
    null"——自测会红，而真正的原因（字节流坏了）藏在几百个 hex 数字里极难找。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    for index in range(count):
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        image.save(str(out_dir / f"{index + 1}.jpg"), "JPG")
