# -*- coding: utf-8 -*-
"""独立功能页的**执行进度**（2026-10-03 新增）。

起因：四个步骤页（提取 / 去底色 / 生成 PDF / 检测）点执行之后，右栏只有一行
"正在处理…"的文字，几十秒的活儿看不出跑到哪儿；拼图页与 detect 的「导出标注图」
更糟——它们连 ``progress`` 信号都没接，导出期间界面**完全**没有反馈。

守护五件事（都是"少接一根线就静默失效"的那种）：

1. **组件自身**：``ProgressRow`` 四个状态方法各自把条与文案带到该去的形态；
   总量未知时走滑动态、且**不摆条**（摆一根空条看着像卡死）；
2. **四个步骤页都有**：``StepControl`` 内部那条进度行摆出来了，``run()`` 点亮、
   ``progress`` 推进、成功走到头、失败停住；换个源再跑会重新点亮（不被上一次的
   残值骗到）；
3. **拼图页 / detect 导出**是**各自独立**的一条执行线，进度不与主执行混用；
4. **``progress_total`` 两处口径一致**：子进程（``JsonLinesReporter``）与进程内
   （``CallbackReporter``）都必须把它归一化成 ``done=0`` 的 progress——只改一处
   的话，独立页永远拿不到上限（这正是本次修的 bug）；
5. **服务层回调可用**：``compose_doc`` / ``export_annotated`` 的 ``report`` /
   ``progress`` 回调真的会逐项被调（纯函数断言，不起线程）。

⚠️ **DEPENDS 为空、自建页面**（与 ``module_edit_sync`` 同款做法）：借主窗口
（``DEPENDS`` 挂 ``tasklist``）时，本模块在段 2 构造 ``RembgModulePage`` 会触发
``QThread: Destroyed`` 硬中止——症状是**退出码 127、stderr 全空、断言打到一半
就停**，且会连带吃掉排在其后的模块。页面级断言不需要主窗口，隔离掉更稳也更快。
"""

from __future__ import annotations

from pathlib import Path

NAME = "module_progress"
DEPENDS: list[str] = []
TITLE = "独立功能页执行进度"


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_widget(ctx, ok)
    _check_control(ctx, ok)
    _check_extra_lines(ctx, ok)
    _check_reporter_parity(ctx, ok)
    _check_services(ctx, ok)
    # ⚠️ 能力探测：导出标注图那条链可能还没进主干。⚠️ 探测的是**真正用到的那个
    #    符号**（``utils.box_draw.draw_slots``）而不是 ``detect_export`` 模块本身
    #    ——后者能导入成功、只在调用时才缺 draw_slots，探模块会漏判（实测踩过）。
    try:
        from utils.box_draw import draw_slots  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"    （跳过 export_annotated 进度：缺 {type(exc).__name__}）")
    else:
        _check_detect_export(ctx, ok)


def _shutdown(page, app) -> None:
    """收尾页面 + 查看器两个 WorkerHost，再 pump 两轮让 ``deleteLater`` 落地。

    与 ``module_edit_sync._shutdown`` 同款：不给它们收尾，退出时那些线程还在跑，
    Qt 会硬中止（症状同上）。``RuntimeError`` 是"对象已析构"，忽略即可。
    """
    from tests.selftests._context import pump

    for owner in (getattr(page, "viewer", None), page):
        if owner is None:
            continue
        try:
            owner.shutdown_workers()
        except RuntimeError:
            pass
    pump(app, times=2)


# ---------------------------------------------------------------- 1. 组件自身
def _check_widget(ctx, ok) -> None:
    """``ProgressRow`` 四个状态方法的形态。"""
    from desktop.components.progress_row import ProgressRow

    row = ProgressRow(noun="页")
    # ⚠️ 判"摆出来了没有"一律用 ``isHidden()``（只看控件自己的隐藏标记），
    #    **不要**用 ``isVisible()`` 或 ``isVisibleTo(父)``：本用例不把控件挂到
    #    已显示的窗口上（前者恒为 False），而独立页初始只显示输入区、整个分栏
    #    都是藏着的（后者跟着父级一起为 False）——两种都会假红。
    shown = lambda widget: not widget.isHidden()  # noqa: E731
    try:
        # 初始：条与文案都藏着（空闲时不占位）
        ok("初始时条与计数文案都不显示",
           not shown(row.bar) and not shown(row.count))

        # start：条摆出来（未知态滑块），文案是提示
        row.start()
        ok("start() 点亮进度条", shown(row.bar))
        ok("start() 显示提示文案", row.count.text() == "正在处理…",
           row.count.text())
        ok("start() 时总量未知（走滑动态）", row.bar.is_unknown())

        # update 有 total：定量 + x/y + 百分比
        row.update(12, 48)
        ok("update(12, 48) 把上限设成 48", row.bar.maximum() == 48)
        ok("update(12, 48) 定位到 12", row.bar.value() == 12)
        ok("update 阶段的文案是常规墨色（不是状态色）",
           not _is_green(_label_color(row.count))
           and not _is_red(_label_color(row.count)),
           _label_color(row.count))
        ok("update(12, 48) 文案含 12/48 与 25%",
           "12/48" in row.count.text() and "25%" in row.count.text(),
           row.count.text())
        ok("update 后不再是未知态", not row.bar.is_unknown())

        # update 无 total：只写已处理数，不写 x/y
        row.update(3, 0)
        ok("update(3, 0) 回到未知态", row.bar.is_unknown())
        ok("update(3, 0) 文案只说已处理 3 页（不写 3/0）",
           row.count.text() == "已处理 3 页", row.count.text())

        # succeed：条走到头 + 绿色收尾文案。
        # ⚠️ 默认文案只说"完成<单位>"；``x/x`` 计数是**宿主**通过 done_text()
        #    传进来的（``StepControl`` 在成功时调它），不在组件里自己算——
        #    组件不知道"总共几张"，那是命令的事。
        row.update(12, 48)
        row.succeed()
        ok("succeed() 让条走到上限", row.bar.value() == 48)
        ok("succeed() 默认文案是「完成 页」", row.count.text() == "完成 页",
           row.count.text())
        ok("succeed() 文案画成成功色（绿）",
           _is_green(_label_color(row.count)), _label_color(row.count))
        ok("done_text() 按上限拼出 x/x 计数",
           row.done_text() == "完成 48/48 页", row.done_text())

        # 宿主传自定义文案时用它（StepControl 走的就是这条）
        row.succeed("完成 12 张")
        ok("succeed() 接受宿主传入的文案", row.count.text() == "完成 12 张",
           row.count.text())

        # 未知态下 succeed：藏条、只留文案（别留滑块装忙）
        row.update(0, 0)
        ok("未知态时 done_text() 只说「已完成」（不写 完成 0/0 页）",
           row.done_text() == "已完成", row.done_text())
        row.succeed()
        ok("未知态 succeed() 藏掉滑块（不装忙）", not shown(row.bar))
        ok("未知态 succeed() 仍留完成文案（不空白）",
           row.count.text() == "完成 页", row.count.text())

        # fail：条停住不清零 + 红字
        row.update(7, 20)
        row.fail()
        ok("fail() 后条停在出错那一刻（不清零）", row.bar.value() == 7)
        ok("fail() 文案是失败提示", row.count.text() == "执行失败",
           row.count.text())
        ok("fail() 文案画成危险色（红）",
           _is_red(_label_color(row.count)), _label_color(row.count))

        # reset：全藏
        row.reset()
        ok("reset() 把条与文案都收起来",
           not shown(row.bar) and not shown(row.count)
           and row.count.text() == "")
    finally:
        row.deleteLater()
        from tests.selftests._context import pump

        pump(ctx.app, times=2)


def _is_green(rgb) -> bool:
    """这个颜色算不算绿字（成功色）。"""
    if rgb is None:
        return False
    red, green, blue = rgb
    return green > red + 30 and green > blue + 30


def _is_red(rgb) -> bool:
    """这个颜色算不算红字（危险色）。"""
    from tests.selftests._context import is_reddish

    return is_reddish(rgb)


def _label_color(label):
    """标签当前画出来的文字颜色（RGB 元组）。

    ⚠️ 必须**渲染出来看**（``tests/selftests/_context.py::painted_color``），
    不能查 ``palette()`` 或 ``styleSheet()``：原生 QLabel 走调色板、qfluent 标签
    走 setTextColor，两条路都不反映在样式表里，查那些是假绿。
    """
    from tests.selftests._context import painted_color

    return painted_color(label)


# ---------------------------------------------------- 2. 四个步骤页的进度行
def _check_control(ctx, ok) -> None:
    """``StepControl`` 内部那条进度行被真正驱动。

    ⚠️ 这里从**真实模块页**上取 ``page.control``，不自己 new 一个
    ``StepControl``：单独构造的控件没有宿主页面替它收尾线程，析构时
    ``QThread: Destroyed`` 硬中止会把本模块后半段（以及排在其后的模块）
    一起吃掉——症状是"退出码 127、stderr 全空、断言打到一半就停"。
    """
    from desktop.modules.rembg.page import RembgModulePage
    from desktop.steps import spec_by_key

    from desktop.components.progress_row import ProgressRow

    spec = spec_by_key("rembg")
    assert spec is not None
    page = RembgModulePage()
    control = page.control
    try:
        row = control.progress_row
        ok("StepControl 内部摆的是 ProgressRow", isinstance(row, ProgressRow))
        ok("进度行的单位取自 spec.progress_unit()",
           row.unit().strip() == spec.progress_unit(),
           f"{row.unit()!r} vs {spec.progress_unit()!r}")

        # 空闲态（同上：用 isHidden()，别用 isVisible/isVisibleTo）
        shown = lambda widget: not widget.isHidden()  # noqa: E731
        ok("空闲时进度条不显示", not shown(row.bar))

        # 模拟一次完整执行：start → progress → finished
        row.start()
        ok("开始执行后进度条显示", shown(row.bar))

        # 直接驱动内核的 progress 转发（等价于 worker 线程汇报）
        control._on_progress(3, 10)
        ok("progress 事件把条推到 3/10",
           row.bar.value() == 3 and row.bar.maximum() == 10,
           f"{row.bar.value()}/{row.bar.maximum()}")
        ok("状态行也写了 done/total",
           "3/10" in _last_status(control), _last_status(control))

        control._on_finished(str(spec.default_output(Path("x.jpg"))))
        ok("成功后条走到头", row.bar.value() == 10)
        ok("成功后文案是完成计数", "完成" in row.count.text(),
           row.count.text())

        # ⚠️ 换源再跑：必须重新点亮，不能被上一次的残值骗到
        row.reset()
        control._on_progress(0, 0)
        ok("重跑时（total 未知）条回到滑动态", row.bar.is_unknown())
    finally:
        _shutdown(page, ctx.app)
        page.deleteLater()


def _last_status(control) -> str:
    """最后一条 status 文案（临时接一次监听取回来）。"""
    seen: list[str] = []
    control.status.connect(lambda text, kind: seen.append(text))
    control._on_progress(3, 10)
    return seen[-1] if seen else ""


# ------------------------------------------- 3. 拼图页 / detect 导出的独立进度
def _check_extra_lines(ctx, ok) -> None:
    """另外两条执行线各有自己的一条进度，且不与主执行共用。"""
    from desktop.modules.detect.page import DetectModulePage
    from desktop.modules.imposition.page import ImpositionModulePage

    from desktop.components.progress_row import ProgressRow

    # 拼图页（不继承 StepModulePage，得自备）
    imposition = ImpositionModulePage()
    try:
        ok("拼图页有自己的进度行", isinstance(imposition.progress_row, ProgressRow))
        ok("拼图页进度单位是「页」",
           imposition.progress_row.unit().strip() == "页",
           imposition.progress_row.unit())
        ok("拼图页没有 StepControl（不与主执行共用进度）",
           not hasattr(imposition, "control"))
        # 走**信号**而不是直接调回调：这条线接没接上，正是要钉的东西
        imposition.kernel.progress.emit(2, 5)
        ok("拼图页进度能推到 2/5", imposition.progress_row.bar.value() == 2)
    finally:
        _shutdown(imposition, ctx.app)
        imposition.deleteLater()

    # detect 页：主执行（StepControl）与导出标注图各有各的。
    # ⚠️ 「导出标注图」这条执行线本身可能还没进主干（``_export_kernel`` 是
    #    detect 页后续加的功能）。所以这里**按能力探测**：有就断言它与主执行
    #    各有一条、互不干扰；没有就只断言主执行那条——别让这个用例反过来
    #    依赖一个还没落地的功能（那会让它先于那个功能挂掉）。
    detect = DetectModulePage()
    try:
        ok("detect 主执行有进度行（走共用的 StepControl）",
           isinstance(detect.control.progress_row, ProgressRow))
        if not hasattr(detect, "export_progress"):
            print("    （跳过 detect 导出进度：导出标注图功能尚未落地）")
            return
        ok("detect 页给导出标注图单配了一条进度行",
           isinstance(detect.export_progress, ProgressRow))
        ok("detect 主执行与导出进度**不是同一条**",
           detect.export_progress is not detect.control.progress_row)
        # 同上：经信号驱动，验证 export_kernel.progress 真的接到了这条行
        detect._export_kernel.progress.emit(4, 8)
        ok("导出进度能推到 4/8", detect.export_progress.bar.value() == 4)
        ok("推导出进度不动主执行的条",
           detect.control.progress_row.bar.value() == 0)
    finally:
        _shutdown(detect, ctx.app)
        detect.deleteLater()

    # ⚠️ job 契约允许「只干活不汇报」：``report=None`` 是既有自测的调用方式
    #    （``module_edit_sync`` 就直接传 None 调 ``_compose_job``）。加了进度
    #    之后若忘了判None，那条路会 TypeError 崩掉——这里钉住。
    #    ⚠️ 必须**另起一个页面实例**：上面那个已 ``deleteLater()``，再拿它跑 job
    #    会在已析构的对象上调用（症状是莫名其妙的 AttributeError）。
    from desktop.steps import StepRequest

    out = Path(ctx.tmp) / "module_progress" / "no_report"
    out.mkdir(parents=True, exist_ok=True)
    src = out.parent / "src.png"
    if not src.is_file():
        import numpy as np

        import utils

        utils.imwrite(src, np.full((40, 50, 3), 210, dtype="uint8"))
    doc = {"pages": [{"items": [
        {"file": str(src), "rect": [0.0, 0.0, 50.0, 40.0], "rotation": 0.0},
    ]}]}
    job_page = ImpositionModulePage()
    try:
        written = job_page._compose_job(
            StepRequest(dest=out, args={"doc": doc}), None
        )
        ok("拼版 job 传 report=None 也能跑完（不汇报≠不能干活）",
           isinstance(written, str) and list(out.glob("*.png")),
           str(written))
    finally:
        _shutdown(job_page, ctx.app)
        job_page.deleteLater()

# --------------------------------------------- 4. progress_total 两处口径一致
def _check_reporter_parity(ctx, ok) -> None:
    """子进程与进程内两个 reporter 对 ``progress_total`` 必须同一口径。"""
    from core.reporter import CallbackReporter
    from desktop.stages.events import JsonLinesReporter

    # 进程内（独立功能页走这条）
    events: list[tuple[str, dict]] = []
    CallbackReporter(lambda name, payload: events.append((name, payload))).event(
        "progress_total", total=42
    )
    ok("CallbackReporter 把 progress_total 归一化成 done=0 的 progress",
       events == [("progress", {"done": 0, "total": 42})], str(events))

    # 子进程（任务流程走这条）——两边必须一致
    import io

    stream = io.StringIO()
    JsonLinesReporter({}, stream=stream).event("progress_total", total=42)
    import json

    line = json.loads(stream.getvalue().strip())
    ok("JsonLinesReporter 口径与进程内一致",
       line["type"] == "progress" and line["done"] == 0 and line["total"] == 42,
       str(line))

    # 别的具名事件仍原样透传（别把归一化做过头）
    events.clear()
    CallbackReporter(lambda name, payload: events.append((name, payload))).event(
        "page_boxes", image="0001"
    )
    ok("非 progress_total 事件仍原样透传",
       events == [("page_boxes", {"image": "0001"})], str(events))


# ------------------------------------------------- 5. 服务层的进度回调可用
def _check_services(ctx, ok) -> None:
    """``compose_doc`` 真的会逐项回调（``export_annotated`` 另见下一段）。"""
    from desktop.services.imposition import compose_doc

    tmp = Path(ctx.tmp) / "module_progress"
    tmp.mkdir(parents=True, exist_ok=True)

    # compose_doc：两页拼版（单图页也算一页）
    import utils

    images = []
    for index in range(2):
        import numpy as np

        path = tmp / f"src{index + 1}.png"
        utils.imwrite(path, np.full((60, 80, 3), 200, dtype="uint8"))
        images.append(path)
    # ⚠️ ``rect`` 是**必需**字段：``normalize_page`` 会把缺 rect / 零宽高的项
    #    静默丢掉，整页因此变成 None ——用没有 rect 的 doc 测compose_doc 会得到
    #    "回调一次都没触发"，看起来像回调坏了，其实是数据本身不合法。
    doc = {
        "pages": [
            {"items": [{"file": str(images[0]),
                        "rect": [0.0, 0.0, 80.0, 60.0], "rotation": 0.0}]},
            {"items": [{"file": str(images[1]),
                        "rect": [0.0, 0.0, 80.0, 60.0], "rotation": 0.0}]},
        ]
    }
    seen: list[tuple[int, int]] = []
    compose_doc(doc, tmp / "out", report=lambda d, t: seen.append((d, t)))
    ok("compose_doc 逐页回调 (done, total)",
       seen == [(1, 2), (2, 2)], str(seen))

    # 不传回调也能跑（任务流程那条路就是不传的）
    ok("compose_doc 不传 report 也能跑",
       len(compose_doc(doc, tmp / "out2")) == 2)

    # 回调自己抛异常不许带崩合成
    def boom(done, total):
        raise RuntimeError("进度回调炸了")

    ok("进度回调抛异常也不影响合成",
       len(compose_doc(doc, tmp / "out3", report=boom)) == 2)


# ------------------------------------------- 6. export_annotated 的进度回调
def _check_detect_export(ctx, ok) -> None:
    """``export_annotated`` 的 ``progress`` 回调真的会逐项被调。

    ⚠️ 由 :func:`run` 做**能力探测**后才调：本模块 ``desktop/services/
    detect_export.py`` 与它依赖的 ``utils.box_draw.draw_slots`` 都可能还没进
    主干（那是「导出标注图」功能链的一部分），导入失败就该跳过，不能让本用例
    先于那个功能挂掉。
    """
    import numpy as np

    import utils

    from desktop.services.detect_export import export_annotated

    tmp = Path(ctx.tmp) / "module_progress"
    tmp.mkdir(parents=True, exist_ok=True)
    images = []
    for index in range(2):
        path = tmp / f"annot{index + 1}.png"
        utils.imwrite(path, np.full((60, 80, 3), 200, dtype="uint8"))
        images.append(path)

    entries = [(images[0], [[10, 10, 60, 50]]), (images[1], [[5, 5, 70, 55]])]
    seen: list[tuple[int, int]] = []
    written = export_annotated(
        entries, tmp / "annot", progress=lambda d, t: seen.append((d, t))
    )
    ok("export_annotated 逐页回调 (done, total)",
       seen == [(1, 2), (2, 2)], str(seen))
    ok("export_annotated 真的写出了两张", len(written) == 2, str(written))

    def boom(done, total):
        raise RuntimeError("进度回调炸了")

    ok("export_annotated 的进度回调抛异常也不影响导出",
       len(export_annotated(entries, tmp / "annot2", progress=boom)) == 2)
