# -*- coding: utf-8 -*-
"""8c-2. 绘制端步进：旋转段用渲染端实测宽度 / 9. 密度与缩略图尺寸 / 10. 宿主接线：详情页必须把打印面板参数交给效果预览 / 进度来源唯一：一条进度条只能被一个阶段驱动 / 原比例缩放（keep_ratio）：自动排版的两种落点 / 11. 单页导出（「下载本页图片」）：A4 效果图，精度与 PDF 同级 / 打印本页：同一份 A4 效果渲染，交系统打印对话框 / 参数变化 → 已打开的弹窗重渲染（纸张快照不再过期） / 方向键翻页：「焦点在哪里，哪里就切换」"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _tmp_png, ROOT
    from pathlib import Path
    from functions.print import PrintFunction
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from utils.page_layout import (
        PrintTextSpec, vertical_advance_mm, vertical_extent_mm, vertical_runs,
    )
    from PySide6.QtGui import QIcon, QImage, QPixmap
    from PySide6.QtCore import QPoint
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtTest import QTest
    from utils.page_layout import (
        TEXT_INSET_MM, TEXT_MARGIN_MM, TEXT_SIDE_OFFSET_MM,
        plan_print_page, print_page_size_mm,
    )
    from desktop.components.viewers.thumb_strip import ThumbStrip
    from desktop.workers.preview_worker import _draw_print_text
    from utils.page_layout import TEXT_MARGIN_MM, plan_print_page as _plan4
    from typing import cast
    from tests.selftests._context import module_source_text
    from tests.selftests._context import ok, pump
    from desktop.workers.preview_worker import (
        compose_print_page, preview_px_per_mm,
    )
    import pymupdf
    from utils.page_layout import vertical_chunk_advance_mm
    from tests.selftests._context import wait_until
    from utils.page_layout import vertical_chunk_advance_mm

    ok("绘制步进：旋转段优先用渲染端实测宽度",
       abs(vertical_chunk_advance_mm("1234", 1.0, True, 2.0) - 2.0) < 1e-6,
       str(vertical_chunk_advance_mm("1234", 1.0, True, 2.0)))
    ok("绘制步进：实测缺失时回落到 0.55 估算",
       abs(vertical_chunk_advance_mm("1234", 1.0, True, None) - 2.2) < 1e-6,
       str(vertical_chunk_advance_mm("1234", 1.0, True, None)))
    ok("绘制步进：汉字段仍是一字一格（忽略实测值）",
       abs(vertical_chunk_advance_mm("呵呵", 2.0, False, 99.0) - 4.0) < 1e-6)

    # 绘制契约（确定性）：用假 painter 记录"画了哪些串、有没有旋转"
    class _SpyPainter:
        """只记录调用的假 painter（不真画），用于断言排版动作。"""

        def __init__(self):
            self.calls: list = []

        def setFont(self, font):
            # _draw_print_text 取 painter.font() 做 QFontMetrics（旋转段实测
            # 步进），spy 必须把字体存下来。⚠️ 存 `_font`——存 `font` 会把
            # 下面的 font() 方法遮蔽成 QFont 实例属性（QFont 不可调用）。
            self._font = font

        def font(self):
            return self._font

        def setPen(self, *_a):
            pass

        def save(self):
            self.calls.append(("save",))

        def restore(self):
            self.calls.append(("restore",))

        def translate(self, x, y):
            self.calls.append(("translate", round(float(x), 2), round(float(y), 2)))

        def rotate(self, deg):
            self.calls.append(("rotate", float(deg)))

        def drawText(self, _point, text):
            self.calls.append(("text", str(text)))

    spec = PrintTextSpec(
        text="呵呵Happiness", x_mm=10.0, y_start_mm=10.0, char_h_mm=8.0,
        vertical=True, font_size_pt=24.0, color=(0, 0, 0),
    )
    spy = _SpyPainter()
    _draw_print_text(spy, spec, 1.0)  # type: ignore[reportArgumentType]  # 测试替身：鸭子类型的记录器，签名与 QPainter 兼容
    texts = [call[1] for call in spy.calls if call[0] == "text"]
    ok("预览：英文整段一次画完（不是每个字母一次）",
       texts == ["呵", "呵", "Happiness"], str(texts))
    ok("预览：英文段外面套了 旋转 90° 的 save/restore",
       ("save",) in spy.calls and ("restore",) in spy.calls
       and ("rotate", 90.0) in spy.calls,
       str([c for c in spy.calls if c[0] in ("save", "restore", "rotate")]))
    ok("预览：汉字不旋转",
       len([c for c in spy.calls if c[0] == "rotate"]) == 1,
       str([c for c in spy.calls if c[0] == "rotate"]))

    # 成品 PDF 侧：拉丁段读回来必须是**一个**文本块（拆成九格会变成九行）
    mixed_args = dict(st.pdf_args, pdf_name="vertical_mixed.pdf")
    mixed_args.update({
        "title_printing": True, "title_text": "呵呵Happiness",
        "title_font_size": 24, "title_position": "top",
        "title_orientation": "vertical",
        "page_number_printing": False,
    })
    PrintFunction(dict(mixed_args)).execute()  # type: ignore[reportArgumentType]  # 同上
    mixed_pdf = st.tmp / "out" / "vertical_mixed.pdf"
    ok("混排标题的 PDF 已生成", mixed_pdf.exists(), str(mixed_pdf))
    from typing import cast

    doc3 = pymupdf.open(str(mixed_pdf))
    try:
        # 逐行取：既能看"分成几行"，也能看每行的书写方向（dir）
        _rawdict3 = cast(dict, doc3[0].get_text("rawdict"))  # 同上：存根偏差
        lines = [
            line
            for block in _rawdict3["blocks"]
            if block.get("type") == 0
            for line in block["lines"]
        ]

        def _line_text(line) -> str:
            return "".join(
                ch["c"] for span in line["spans"] for ch in span["chars"]
            )

        # ⚠️ 只断言"拉丁段占一行"、"总行数很少"：逐字母排版会变成 9+ 行。
        # 不要断言字串长度——PyMuPDF 对旋转文本的抽取有损耗（末尾字可能丢），
        # 拿长度当判据会把"方向写反"误报成"被拆成一格一格"（已踩）。
        latin_lines = [ln for ln in lines if "Happi" in _line_text(ln)]
        ok("PDF：拉丁段是一整行（不是每字母一行）",
           len(latin_lines) == 1 and len(lines) <= 4,
           str([_line_text(ln) for ln in lines]))
        if latin_lines:
            line = latin_lines[0]
            ok("PDF：拉丁段自上而下排（书写方向 = 向下）",
               tuple(round(float(v), 3) for v in line["dir"]) == (0.0, 1.0),
               str(line["dir"]))
            ys = [
                ch["bbox"][1]
                for span in line["spans"] for ch in span["chars"]
            ]
            ok("PDF：首字母在最上、末字母在最下（顺着往下读）",
               ys == sorted(ys) and ys[-1] > ys[0],
               f"{[round(y, 1) for y in ys[:3]]} … {round(ys[-1], 1)}")
            bw = line["bbox"][2] - line["bbox"][0]
            bh = line["bbox"][3] - line["bbox"][1]
            ok("PDF：拉丁段是旋转 90° 的竖条（高 ≫ 宽）",
               bh > bw * 2, f"{bw:.1f}x{bh:.1f}pt")
        cjk_lines = [ln for ln in lines if "呵" in _line_text(ln)]
        ok("PDF：汉字仍是一字一格（各自成行）",
           len(cjk_lines) == 2, str([_line_text(ln) for ln in lines]))
        # ---- 8c-3. 混排对齐：旋转段与汉字同一列、且紧接上一字 ----
        # 用户 2026-11-01 报「标题含英文字符/数字时没对齐、字符间有间隔」：
        # 汉字以基线为底向上长，旋转段从串首向下排，落点不补偿就会**左移一个
        # descent**（不同列）并在前面**空出约一个 ascent**（一条近一字高的缝）。
        if latin_lines and cjk_lines:
            latin = latin_lines[0]["bbox"]
            cjk_x0 = min(ln["bbox"][0] for ln in cjk_lines)
            ok("PDF：旋转段与汉字同一列（轮廓左缘一致，±1.5pt）",
               abs(latin[0] - cjk_x0) <= 1.5,
               f"latin={latin[0]:.1f} cjk={cjk_x0:.1f}")
            cjk_bottom = max(ln["bbox"][3] for ln in cjk_lines)
            ok("PDF：旋转段紧接上一汉字（不留一个 ascent 的空隙，±1.5pt）",
               abs(latin[1] - cjk_bottom) <= 1.5,
               f"latin.top={latin[1]:.1f} cjk.bottom={cjk_bottom:.1f}")
    finally:
        doc3.close()
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QIcon, QImage, QPixmap

    ok("效果预览密度有上下限（不会为超大纸分配巨图）",
       2.0 <= preview_px_per_mm(297, 210) <= 8.0
       and preview_px_per_mm(2000, 2000) == 2.0,
       str(preview_px_per_mm(297, 210)))

    # 解码边必须按**图标框的长边**取。ImageListWorker 的 edge 是"最长边"语义，
    # 竖开本古籍页受高度约束：取框宽（旧实现 96）时，1600x2800 的页面解码成
    # 55x96，缩略图只占条目宽度的一半（用户反馈「缩略图占用宽度太小」）。
    ok("缩略图解码边长取 ThumbStrip 的框长边（不是框宽）",
       PrintPreviewWidget.THUMB_EDGE == ThumbStrip.DECODE_EDGE
       and ThumbStrip.DECODE_EDGE
       == max(ThumbStrip.ICON_SIZE.width(), ThumbStrip.ICON_SIZE.height()),
       f"{PrintPreviewWidget.THUMB_EDGE}")

    # 契约：竖开本页面（宽高比 0.578，实测自《龍譚精舍叢刻》）的缩略图，
    # 必须占条目宽度的 60% 以上——否则就是"框没吃满宽度"的回归。
    portrait = _tmp_png(st.tmp / "portrait.png", 1156, 2000)  # ratio 0.578
    decoded = QImage(str(portrait)).scaled(
        ThumbStrip.DECODE_EDGE, ThumbStrip.DECODE_EDGE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    shown = QIcon(QPixmap.fromImage(decoded)).pixmap(
        QSize(ThumbStrip.ICON_SIZE)
    )
    ratio = shown.width() / max(ThumbStrip.GRID_SIZE.width(), 1)
    ok("竖开本页面的缩略图占条目宽度 ≥60%（不再只有一半）",
       ratio >= 0.6, f"{shown.width()}/{ThumbStrip.GRID_SIZE.width()}={ratio:.0%}")

    # 控件宽度要放得下网格 + 竖向滚动条，否则会多出一条横向滚动条
    ok("缩略图条宽度容得下网格与滚动条",
       ThumbStrip.STRIP_WIDTH >= ThumbStrip.GRID_SIZE.width() + 16,
       f"{ThumbStrip.STRIP_WIDTH} vs {ThumbStrip.GRID_SIZE.width()}")
    st.detail = st.ctx.d
    ok("详情页把打印面板参数接给了效果预览",
       getattr(st.detail.print_preview, "_params_provider", None) is not None,
       "PrintPreviewWidget(params_provider=...) 漏传")
    spec, note = st.detail.print_preview._print_spec(0, Path("0001.png"))
    ok("宿主提供的参数能直接构成 print_spec（无回退提示）",
       spec is not None and note == "",
       f"spec={spec is not None} note={note!r}")

    ok("详情页效果预览的缩略图条沿用 ThumbStrip 的固定宽度",
       st.detail.print_preview.strip.width() == ThumbStrip.STRIP_WIDTH,
       str(st.detail.print_preview.strip.width()))
    ok("详情页接上了单页导出的三个信号（按钮→对话框→提示）",
       hasattr(st.detail, "_export_print_image")
       and hasattr(st.detail, "_on_export_finished")
       and hasattr(st.detail, "_on_export_failed"), "")
    stage_text = (
        ROOT / "desktop/stages/print_stage.py"
    ).read_text(encoding="utf-8")
    func_text = (
        ROOT / "functions/print.py"
    ).read_text(encoding="utf-8")
    ok("合成阶段不发 progress（否则进度条会先跑完再跳回 0 重跑）",
       '"type": "progress"' not in stage_text, "")
    ok("进度唯一来源 = CLI 的已写入页数（reporter.progress）",
       "self.reporter.progress(" in func_text, "")
    from utils.page_layout import TEXT_MARGIN_MM, plan_print_page as _plan4

    base_args = {"paper_size": "A4", "orientation": "landscape",
                 "page_margins": [10, 10, 10, 10]}
    avail_w = 297 - 10 - 10 - 2 * TEXT_MARGIN_MM
    avail_h = 210 - 10 - 10
    ratio_plan = _plan4((2000, 1000), {**base_args, "keep_ratio": True}, 0, 1)
    ok("原比例（默认）：图片框保持源宽高比",
       abs((ratio_plan.image[2] / ratio_plan.image[3]) - 2.0) < 1e-6,
       f"{ratio_plan.image[2]:.1f}x{ratio_plan.image[3]:.1f}")
    fill_plan = _plan4((2000, 1000), {**base_args, "keep_ratio": False}, 0, 1)
    ok("取消原比例：图片铺满可用区域（受页边距约束）",
       abs(fill_plan.image[2] - avail_w) < 1e-6
       and abs(fill_plan.image[3] - avail_h) < 1e-6
       and abs(fill_plan.image[0] - 10) < 1e-6
       and abs(fill_plan.image[1] - 10) < 1e-6,
       f"{tuple(round(v, 1) for v in fill_plan.image)} vs 可用 {avail_w:.0f}x{avail_h:.0f}")
    # 老配置没有该键 → 等同 True（不改变既有任务的行为）
    legacy = _plan4((2000, 1000), base_args, 0, 1)
    ok("老配置无 keep_ratio 键：行为与 True 一致（不改变既有任务）",
       abs(legacy.image[2] - ratio_plan.image[2]) < 1e-6,
       f"{legacy.image[2]:.1f} vs {ratio_plan.image[2]:.1f}")
    from tests.selftests._context import wait_until

    export_src = _tmp_png(st.tmp / "export-src.png", 2000, 2828)
    exporter = PrintPreviewWidget(params_provider=lambda: dict(st.full))
    try:
        exporter._mode = "effect"
        ok("无页时不给默认文件名（宿主据此提示而不是弹空对话框）",
           exporter.export_default_name() is None,
           str(exporter.export_default_name()))
        ok("无页时「下载本页图片」按钮不可点（不留死按钮）",
           not exporter.export_image_button.isEnabled(), "")

        exporter.set_entries([{"file": str(export_src), "label": "0001"}])
        pump(st.app, times=4)
        ok("有页后按钮变为可点", exporter.export_image_button.isEnabled(), "")
        ok("有页时默认文件名 =「<页名>-打印效果.png」",
           exporter.export_default_name() == "export-src-打印效果.png",
           str(exporter.export_default_name()))
        ok("导出精度与 PDF 同级：A4 横向 300dpi → 长边 3508px",
           exporter._export_edge() == 3508, str(exporter._export_edge()))

        exporter._params_provider = lambda: dict(st.full, paper_size="A5")
        ok("换纸张后导出边长跟着变（不是写死的）",
           exporter._export_edge() < 3508, str(exporter._export_edge()))
        exporter._params_provider = lambda: dict(st.full)

        events: list[tuple[str, str]] = []
        exporter.export_finished.connect(lambda p: events.append(("ok", p)))
        exporter.export_failed.connect(lambda m: events.append(("err", m)))
        out_dir = st.tmp / "export"
        out_dir.mkdir(parents=True, exist_ok=True)

        png_path = out_dir / "page.png"
        exporter.export_current_effect(png_path)
        ok("导出走异步 worker 并回报成功",
           wait_until(st.app, lambda: bool(events), timeout=30)
           and events[0][0] == "ok", str(events))
        written = QImage(str(png_path))
        ok("落盘的确实是 A4 300dpi 的效果图（长边 3508）",
           png_path.exists() and max(written.width(), written.height()) == 3508,
           f"{written.width()}x{written.height()}")
        ok("导出的是**效果图**而不是屏幕预览那张（远超视口宽）",
           written.width() > 900, f"{written.width()} vs exporter 宽 900")

        jpg_path = out_dir / "page.jpg"
        events.clear()
        exporter.export_current_effect(jpg_path)
        wait_until(st.app, lambda: bool(events), timeout=30)
        ok("同一页也能导出 JPEG（save_image 按后缀选格式）",
           jpg_path.exists() and jpg_path.stat().st_size > 0,
           str(jpg_path.stat().st_size if jpg_path.exists() else "缺失"))

        # 源图本身不够 300dpi 时：密度被夹在**源图原生密度**内 → 不放大
        small_src = _tmp_png(st.tmp / "export-small.png", 620, 877)
        exporter.set_entries([{"file": str(small_src), "label": "small"}])
        pump(st.app, times=4)
        events.clear()
        small_out = out_dir / "small.png"
        exporter.export_current_effect(small_out)
        wait_until(st.app, lambda: bool(events), timeout=30)
        small_img = QImage(str(small_out))
        ok("小源图不会被放大（密度夹在原生密度内，长边 < 3508）",
           0 < max(small_img.width(), small_img.height()) < 3508,
           f"{small_img.width()}x{small_img.height()}（源图 620x877）")

        events.clear()

        def _bad_params():
            raise ValueError("坏参数")

        exporter._params_provider = _bad_params
        bad_path = out_dir / "bad.png"
        exporter.export_current_effect(bad_path)
        ok("打印参数不合法时明确报失败，且不落盘半成品",
           bool(events) and events[0][0] == "err" and not bad_path.exists(),
           str(events))
    finally:
        exporter.deleteLater()
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    st.print_src = _tmp_png(st.tmp / "print-src.png", 2000, 2828)
    printer_widget = PrintPreviewWidget(params_provider=lambda: dict(st.full))
    try:
        printer_widget.set_entries([{"file": str(st.print_src), "label": "0001"}])
        pump(st.app, times=4)
        ok("「打印本页」按钮存在、文案纯中文且随条目启停",
           printer_widget.print_button.text() == "打印本页"
           and printer_widget.print_button.isEnabled(), "")
        img, err = printer_widget._render_current_effect_sync()
        ok("打印渲染 = A4 300dpi 效果图（同步执行，长边 3508）",
           img is not None and max(img.width(), img.height()) == 3508,
           f"{img.width()}x{img.height()}" if img is not None else err)
        dbl: list[int] = []
        printer_widget.canvas.double_clicked.connect(lambda: dbl.append(1))
        QTest.mouseDClick(printer_widget.canvas, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier, QPoint(200, 150))
        pump(st.app, times=2)
        ok("版面编辑双击画布发出 double_clicked（宿主据此开预览弹窗）",
           dbl == [1], str(dbl))
    finally:
        printer_widget.deleteLater()

    ok("详情页接上打印完成的两个信号（toast + 日志）",
       hasattr(st.detail, "_on_print_finished")
       and hasattr(st.detail, "_on_print_failed"), "")
    ok("详情页接了参数变化 → 弹窗重渲染的钩子",
       "_refresh_zoom_popup_if_open" in module_source_text(
           ROOT,
           "desktop/components/viewers/print_preview"), "")
    stale = PrintPreviewWidget(params_provider=lambda: dict(st.full))
    try:
        stale.set_entries([{"file": str(st.print_src), "label": "0001"}])
        pump(st.app, times=4)
        calls: list[int] = []
        stale._refresh_zoom_popup_if_open = lambda: calls.append(1)  # 拦截验证
        stale.refresh_display()
        pump(st.app, times=2)
        ok("refresh_display（参数变化路径）会刷新已打开的弹窗",
           calls == [1], str(calls))
    finally:
        stale.deleteLater()
    ok("详情页接了 ←/→ 键盘处理（第四步翻页，输入类控件不抢）",
       "def keyPressEvent" in (ROOT
                               / "desktop/pages/taskdetail/page.py").read_text(
                                   encoding="utf-8")
       and "_arrow_free_to_navigate" in (ROOT
                                         / "desktop/pages/taskdetail/page.py").read_text(
                                             encoding="utf-8"), "")
    # ⚠️ 点击预览大图（QLabel 不收焦点）后焦点落在**主窗口本身**——按键只会
    # 到 MainWindow.keyPressEvent，不转发的话用户点完图片按左右毫无反应
    # （用户 18:29 实测）。主窗口转发 + page.navigate_by_arrow 公开入口。
    app_src = (ROOT
               / "desktop/app.py").read_text(encoding="utf-8")
    # ⚠️ 转发实现已搬到壳层（``ModuleShell.keyPressEvent`` → 详情页
    #    ``navigate_by_arrow``）：主窗口只负责"把键交给壳层"，两条断言要一起看，
    #    否则搬完家这条护栏会误报。
    shell_src = (ROOT
                 / "desktop/shell.py").read_text(encoding="utf-8")
    ok("主窗口把 ←/→ 转发给详情页（点击预览图后焦点落在主窗口）",
       "def keyPressEvent" in app_src and "self.shell.keyPressEvent" in app_src
       and "navigate_by_arrow" in shell_src, "")
    ok("详情页有 navigate_by_arrow 公开入口（主窗口转发用，含输入区守卫）",
       hasattr(st.detail, "navigate_by_arrow"), "")
    ok("预览组件暴露 navigate（方向键翻页入口）",
       hasattr(st.detail.print_preview, "navigate"), "")

