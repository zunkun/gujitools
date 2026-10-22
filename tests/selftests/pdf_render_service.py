# -*- coding: utf-8 -*-
"""PDF 渲染**出进程**自测（2026-10-21 用户报「创建任务/切缩略图卡」的回归护栏）。

背景（量化见 ``desktop/workers/pdf_render_service.py`` 的模块说明）：扫描古籍
常见内嵌格式是 **JPX（JPEG2000）**，MuPDF 解码一页 4285×5736 要 ~850ms，且
**整段持 GIL**——GUI 线程在这 850ms 里拿不到一次时间片。于是：

- 导入后整本缩略图 = 28 个 0.85 秒的卡顿块（"创建任务卡"）；
- 进详情页要与导入线程抢同一把渲染锁（实测进页面 11.5s，界面冻 10.7s）；
- 点一下缩略图触发的单页提取 = 一次 1.3s 的整屏冻结（"切缩略图卡"）。

断言线：

1. **语义不变**：出进程渲出来的 JPEG 与"进程内直接 get_pixmap"**逐字节相同**
   （缩略图/大图/提取三处的参数口径没有被改动）；
2. **真的出进程**：默认模式下 ``mode == "proc"`` 且 ``fallbacks == 0``；
3. **单页失败不炸整批**：越界页返回空字节，同批其它页照常；
4. **两处降级都能兜住**：``GUJI_PDF_RENDER=inproc``、以及池不可用（打桩
   ``_pool_or_none`` 返回 None）时，渲染结果仍然正确（宁可慢，不能不出图）；
5. **单页提取可用**：``extract_page`` 落盘并回报尺寸；
6. **护栏（源码级）**：GUI 侧三个宿主（``preview_worker`` /
   ``source_thumbnails_worker`` / ``extract_viewer``）里**不许再出现**
   ``get_pixmap`` / ``extract_single_page``——那是把渲染搬回 GUI 进程的入口，
   一搬回去就重新冻界面（本用例存在的全部意义）。
"""

from __future__ import annotations

from pathlib import Path

NAME = "pdf_render_service"
DEPENDS: list[str] = []
TITLE = "PDF 渲染出进程（GUI 不被冻）"


def _inproc_render(pdf: Path, page: int, edge: int, quality: int) -> bytes:
    """**旧实现**的渲染口径（本进程直接 get_pixmap），用来对齐字节。"""
    import pymupdf as fitz

    document = fitz.open(str(pdf))
    try:
        loaded = document.load_page(page)
        rect = loaded.rect
        scale = edge / max(rect.width, rect.height)
        pixmap = loaded.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pixmap.tobytes("jpg", jpg_quality=quality)
    finally:
        document.close()


def run(ctx) -> None:
    import os

    from PySide6.QtGui import QImage

    from desktop.workers import pdf_render_service as svc
    from tests.selftests._context import make_pdf, ok, wait_until

    repo = Path(__file__).resolve().parents[2]

    def code_of(rel: str) -> str:
        """只取**真代码**（AST 反解析：注释与文档字符串都不算）。

        ⚠️ 这几个模块的文档字符串里大段在解释"为什么曾经用 get_pixmap"，
        按纯文本匹配会当场误报（本次就是这么发现的第一版写法）。
        """
        import ast

        tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
        # 去掉各处文档字符串（ast.unparse 会把它们原样吐回来，说明文字里
        # 提到 "get_pixmap" 会误伤——注释由 unparse 自然丢弃）
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            head = body[0]
            if (
                isinstance(head, ast.Expr)
                and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)
            ):
                node.body = body[1:]
        return ast.unparse(tree)

    tmp = ctx.tmp / "pdf_render_service"
    tmp.mkdir(parents=True, exist_ok=True)
    pdf = make_pdf(tmp / "书.pdf", 4)

    # ---- 1. 页数 + 单页渲染 ----
    ok("渲染服务：页数正确", svc.page_count(pdf) == 4, str(svc.page_count(pdf)))
    data = svc.render_jpeg(pdf, 1, 256, 70)
    image = QImage.fromData(data)
    ok("渲染服务：缩略图能解码且最长边 = 256",
       (not image.isNull()) and max(image.width(), image.height()) == 256,
       f"{image.width()}x{image.height()}")

    # ---- 2. 语义不变（与旧实现逐字节相同）----
    old = _inproc_render(pdf, 1, 256, 70)
    ok("渲染服务：与旧实现的 JPEG 逐字节一致", data == old,
       f"new={len(data)}B old={len(old)}B")

    # ---- 3. 真的出进程 ----
    stats = svc.stats()
    ok("渲染服务：默认走子进程（mode=proc）", stats["mode"] == "proc", str(stats))
    ok("渲染服务：没有静默降级（fallbacks=0）", stats["fallbacks"] == 0, str(stats))
    ok("渲染服务：至少 1 个子进程", stats["workers"] >= 1, str(stats["workers"]))

    # ---- 4. 批量：越界页不炸整批 ----
    datas = svc.render_jpegs(pdf, [0, 2, 99], 256, 70)
    ok("批量渲染：按入参顺序返回 3 条", len(datas) == 3, str(len(datas)))
    ok("批量渲染：正常页有字节", bool(datas[0]) and bool(datas[1]),
       f"{len(datas[0])}/{len(datas[1])}")
    ok("批量渲染：越界页只让那一页空着（不抛整批）", datas[2] == b"",
       str(len(datas[2])))

    # ---- 5. 池不可用 → 进程内兜底仍然出图 ----
    before = svc.stats()["fallbacks"]
    real_pool = svc._pool_or_none
    svc._pool_or_none = lambda: None       # 打桩：假装子进程起不来
    try:
        fallback = svc.render_jpeg(pdf, 1, 256, 70)
        fell = svc.stats()["fallbacks"]
    finally:
        svc._pool_or_none = real_pool
    ok("兜底：池不可用时仍能渲出同一张图", fallback == old, f"{len(fallback)}B")
    ok("兜底：记了一次 fallback（可观测）", fell == before + 1, f"{before}→{fell}")

    # ---- 6. 环境变量强制进程内 ----
    saved = os.environ.get(svc.ENV_MODE)
    os.environ[svc.ENV_MODE] = "inproc"
    try:
        ok("inproc 模式：offloaded() 为假", svc.offloaded() is False)
        inproc = svc.render_jpeg(pdf, 1, 256, 70)
        ok("inproc 模式：结果与子进程一致", inproc == old, f"{len(inproc)}B")
    finally:
        if saved is None:
            os.environ.pop(svc.ENV_MODE, None)
        else:
            os.environ[svc.ENV_MODE] = saved
    ok("恢复默认：又回到出进程", svc.stats()["mode"] == "proc")

    # ---- 7. 单页提取 ----
    out_dir = tmp / "extract"
    result = svc.extract_page(pdf, 0, out_dir, zoom=1, ext="jpg", quick=True, dpi=300)
    target = Path(str(result.get("path") or ""))
    ok("单页提取：报告成功", bool(result.get("ok")), str(result))
    ok("单页提取：产物真的落盘且不为空",
       target.is_file() and target.stat().st_size > 0, str(target))
    ok("单页提取：回报的尺寸与实际图一致",
       (not QImage(str(target)).isNull())
       and QImage(str(target)).width() == int(result.get("w") or -1),
       f"{result.get('w')}x{result.get('h')}")

    # ---- 8. 源码护栏：GUI 侧不许自己渲染 ----
    hosts = {
        "缩略图预览 worker": "desktop/workers/preview_worker.py",
        "导入缩略图 worker": "desktop/workers/source_thumbnails_worker.py",
        "提取预览控件": "desktop/components/viewers/extract_viewer.py",
    }
    for label, rel in hosts.items():
        text = code_of(rel)
        ok(f"护栏：{label} 不再自己 get_pixmap（渲染必须出进程）",
           ".get_pixmap(" not in text, rel)
    extract_text = code_of("desktop/components/viewers/extract_viewer.py")
    ok("护栏：提取预览控件不再直接调 extract_single_page",
       "extract_single_page(" not in extract_text, "应走 pdf_render_service")

    service_text = code_of("desktop/workers/pdf_render_service.py")
    ok("护栏：渲染服务用的是进程池（ProcessPoolExecutor）",
       "ProcessPoolExecutor" in service_text)
    ok("护栏：渲染服务的进程内兜底持单飞锁",
       "single_flight" in service_text)

    # ---- 8b. 已提取的页：从产物 jpg 缩（21ms），不回 PDF 解 JPX（850ms）----
    from desktop.utils.files import task_extract_pages_dir

    task_dir = tmp / "task"
    (task_dir / "stages" / "extract").mkdir(parents=True, exist_ok=True)
    copy_pdf = task_dir / "书.pdf"
    copy_pdf.write_bytes(pdf.read_bytes())
    plain = svc.render_jpegs(pdf, [0], 256, 70)[0]
    pages_dir = task_extract_pages_dir(copy_pdf)
    ok("已提取页：能从任务目录认出 stages/extract", pages_dir is not None,
       str(pages_dir))
    ok("已提取页：非任务目录（用户原始 PDF）不认（行为不变）",
       task_extract_pages_dir(pdf) is None)
    # 造一张纯红整页图当"提取产物"：命中它出来的缩略图必然也是红的
    from PySide6.QtGui import QColor, QImage as _QImage

    product = task_dir / "stages" / "extract" / "1.jpg"
    red = _QImage(600, 800, _QImage.Format.Format_RGB32)
    red.fill(QColor(220, 20, 20))
    red.save(str(product), "JPEG")
    from_pages = svc.render_jpegs(
        copy_pdf, [0], 256, 70, pages_dir=pages_dir
    )[0]
    pixel = QImage.fromData(from_pages)
    ok("已提取页：缩略图来自产物（不再回 PDF 渲）",
       bool(from_pages) and from_pages != plain, f"{len(from_pages)}B")
    center = pixel.pixelColor(pixel.width() // 2, pixel.height() // 2)
    ok("已提取页：缩略图内容与产物一致（红色）",
       center.red() > 150 and center.green() < 90,
       f"rgb=({center.red()},{center.green()},{center.blue()})")

    # ---- 8c. JPX 快速通道（OpenJPEG 按需降分辨率，实测 5 倍）----
    import io as _io

    from PIL import Image, ImageDraw

    jpx_pdf = tmp / "扫描.pdf"
    canvas = Image.new("RGB", (1200, 1600), (232, 224, 205))
    pen = ImageDraw.Draw(canvas)
    for y in range(120, 1500, 90):
        pen.line([(120, y), (1080, y + 20)], fill=(40, 40, 40), width=7)
    jpx_buf = _io.BytesIO()
    canvas.save(jpx_buf, "JPEG2000", quality_mode="rates", quality_layers=[20])
    import pymupdf as _fitz

    _doc = _fitz.open()
    _page = _doc.new_page(width=432, height=576)
    _page.insert_image(_page.rect, stream=jpx_buf.getvalue())
    _doc.save(str(jpx_pdf))
    _doc.close()
    _probe = _fitz.open(str(jpx_pdf))
    _filter = _probe[0].get_images(full=True)[0][8]
    _probe.close()
    ok("JPX 用例夹具：内嵌图确实是 JPXDecode（没被重编码）",
       _filter == "JPXDecode", _filter)

    ok("JPX 快速通道：目标过大时不启用（交给 MuPDF）",
       svc._child_jpx_thumb(jpx_pdf, 0, 4096, 70, "jpg") == b""
       and svc.JPX_FAST_MAX_EDGE < 4096)
    ok("JPX 快速通道：要原始分辨率时不启用",
       svc._child_jpx_thumb(jpx_pdf, 0, 0, 70, "jpg") == b"")

    if svc.jpx_fast_available():
        fast = svc._child_jpx_thumb(jpx_pdf, 0, 256, 70, "jpg")
        fast_image = QImage.fromData(fast)
        ok("JPX 快速通道：出图且最长边 = 256（走 OpenJPEG 降分辨率）",
           bool(fast) and max(fast_image.width(), fast_image.height()) == 256,
           f"{fast_image.width()}x{fast_image.height()}")
        # 画的是横线：缩下来仍应是"有内容"的图，不是全白/全黑
        mid = fast_image.pixelColor(fast_image.width() // 2,
                                    fast_image.height() // 2)
        ok("JPX 快速通道：画面有内容（不是空白图）",
           mid.value() < 250, f"value={mid.value()}")
        saved = svc._OPJ_PATH
        svc._OPJ_PATH = None
        try:
            ok("JPX 快速通道：没有 OpenJPEG 时返回空（回落 MuPDF）",
               svc._child_jpx_thumb(jpx_pdf, 0, 256, 70, "jpg") == b"")
            fallback_pdf = svc._child_render_jpeg(jpx_pdf, 0, 256, 70, "jpg")
        finally:
            svc._OPJ_PATH = saved
        ok("JPX 快速通道：回落路径仍能出图",
           bool(fallback_pdf) and not QImage.fromData(fallback_pdf).isNull())
    else:
        print("  [SKIP] 本机没有 opj_decompress，跳过 JPX 快速通道的正向断言")
        ok("JPX 快速通道：没有解码器时照常出图（MuPDF）",
           bool(svc._child_render_jpeg(jpx_pdf, 0, 256, 70, "jpg")))

    # ---- 9. 「正在填缓存」的在场标记：查看器不重复渲整本 ----
    from desktop.components.viewers.pdf_viewer import PdfViewerWidget
    from desktop.utils.files import PRODUCING_MARKER

    cache = tmp / "thumbs"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / PRODUCING_MARKER).write_bytes(b"1")
    viewer = PdfViewerWidget()
    viewer.set_pdf(pdf, cache_dir=cache)
    ok("在场标记：查看器判定「有人在填这个缓存」", viewer._watching is True)
    ok("在场标记：这一轮只读缓存，不自己补渲（避免两边各渲一遍）",
       viewer._pass_kind == "read", viewer._pass_kind)
    viewer.shutdown_workers()

    (cache / PRODUCING_MARKER).unlink()
    # ⚠️ 用一个**全新的空目录**：read 那一轮会顺手写 ``.meta``（缓存边长提示），
    #    留在同一目录里会让 mtime 判据以为"刚有人在填"，把本条断言测成假绿。
    cache2 = tmp / "thumbs_idle"
    cache2.mkdir(parents=True, exist_ok=True)
    app = ctx.app
    viewer2 = PdfViewerWidget()
    viewer2.set_pdf(pdf, cache_dir=cache2)
    ok("没有标记且目录是旧的：不进入「等别人填」状态", viewer2._watching is False)
    # ⚠️ 2026-10-21 起不再"整本补渲"：第一轮只读（拿页数），随后
    #    ``_fill_window`` 只补**可见窗口**。所以这里断言"窗口内真的被补上"，
    #    而不是断言"整本 fill 通道"（那个通道按设计已经不再整本跑）。
    ok("没有标记且无人填：查看器自己补上窗口内的缩略图",
       wait_until(app, lambda: bool(viewer2._thumb_received), timeout=20.0),
       str(sorted(viewer2._thumb_received)))
    ok("补图是**按窗口**的：总量远小于总页数",
       len(viewer2._thumb_received) < 4, str(sorted(viewer2._thumb_received)))
    viewer2.shutdown_workers()

    from desktop.workers.source_thumbnails_worker import SourceThumbnailsWorker

    marker_dir = tmp / "thumbs_marker"
    worker = SourceThumbnailsWorker(pdf, marker_dir)
    worker._mark_producing(True)
    ok("生产者：渲染期间写下在场标记",
       (marker_dir / PRODUCING_MARKER).is_file())
    worker._mark_producing(False)
    ok("生产者：渲染结束撤掉在场标记",
       not (marker_dir / PRODUCING_MARKER).exists())

    svc.shutdown()
    # ⚠️ 本用例是**唯一**会显式收池的地方：收完必须把"正在关闭"复位，否则
    #    后续用例全都会退回进程内渲染（慢，而且"出进程"的语义被悄悄破坏）。
    svc._closing = False
