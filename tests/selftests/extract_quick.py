# -*- coding: utf-8 -*-
"""quick 提取的自适应降级自测。

背景：quick 模式原本「只要有内嵌图就取」，三个问题：
1. 一页多图时产出 `1_1.jpg`/`1_2.jpg` 多个文件，而 detect/rembg/print 全部按
   「一页一图」工作，多出来的文件会变成孤儿页；
2. 内嵌图是 jp2/jbig2/CCITT 等格式时要解码再重编码，可能比整页渲染还慢
   （"quick" 名不副实），而且 PIL 缺解码器时整页直接失败；
3. 内嵌图比整页渲染尺寸还小时（低清缩略图/装饰图），取它只会更糊。

现在 `_embedded_page_image()` 只有在「单张内嵌图 + jpg/png + 像素不低于渲染
尺寸」时才返回可取，否则给出原因降级整页渲染。本模块守住这个契约，同时也
验证 GUI 与 CLI 共用同一份并发实现（`render_pages_parallel`）。
"""

import io

NAME = "extract_quick"
DEPENDS: list[str] = []
TITLE = "quick 自适应降级"


def _make_pdf(path, stream, pages=3, per_page=1):
    """每页贴 per_page 张同样的图。"""
    import pymupdf as fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        if per_page == 1:
            page.insert_image(fitz.Rect(0, 0, 595, 842), stream=stream,
                              keep_proportion=False)
        else:
            half = 595 / per_page
            for i in range(per_page):
                page.insert_image(fitz.Rect(i * half, 0, (i + 1) * half, 842),
                                  stream=stream, keep_proportion=False)
    doc.save(str(path))
    doc.close()
    return str(path)


def _jpg_bytes(w=1600, h=2400):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 235, 225)).save(buf, "JPEG", quality=88)
    return buf.getvalue()


def _jp2_bytes(w=1600, h=2400):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 235, 225)).save(buf, "JPEG2000")
    return buf.getvalue()


def run(ctx) -> None:
    import tempfile
    from pathlib import Path

    import pymupdf as fitz

    from tests.selftests._context import ok
    from utils.pdf_utils import (
        QUICK_MIN_COVERAGE,
        _embedded_page_image,
        render_pages_parallel,
    )

    tmp = Path(tempfile.mkdtemp(prefix="guji_quick_"))
    jpg = _jpg_bytes()
    jp2 = _jp2_bytes()

    # ---- 1. 判定层：_embedded_page_image 的三种降级 ----
    single = _make_pdf(tmp / "single.pdf", jpg)
    doc = fitz.open(single)
    page = doc.load_page(0)
    info, why = _embedded_page_image(doc, page, page.rect, "jpg", 1.0)
    ok("单张 jpg 内嵌图可取", info is not None, str(why))
    ok("可取时原因为空", why is None, str(why))
    doc.close()

    multi = _make_pdf(tmp / "multi.pdf", jpg, per_page=2)
    doc = fitz.open(multi)
    # 注意：断言详情别打印 info —— 它含整张图的字节，会让失败输出爆炸
    info, why = _embedded_page_image(doc, doc.load_page(0), doc.load_page(0).rect,
                                     "jpg", 1.0)
    ok("一页多图降级", info is None, f"info={'非空' if info else 'None'}")
    ok("多图降级原因说明张数", why is not None and "2 张图" in why, str(why))
    doc.close()

    jp2pdf = _make_pdf(tmp / "jp2.pdf", jp2)
    doc = fitz.open(jp2pdf)
    info, why = _embedded_page_image(doc, doc.load_page(0), doc.load_page(0).rect,
                                     "jpg", 1.0)
    ok("jp2/jpx 内嵌降级", info is None, f"info={'非空' if info else 'None'}")
    ok("非 jpg/png 原因点明格式", why is not None and "非 jpg/png" in why, str(why))
    doc.close()

    # 低清缩略图：120x90 远小于 595x842 的渲染尺寸
    thumb = _jpg_bytes(120, 90)
    lowres = _make_pdf(tmp / "lowres.pdf", thumb)
    doc = fitz.open(lowres)
    info, why = _embedded_page_image(doc, doc.load_page(0), doc.load_page(0).rect,
                                     "jpg", 1.0)
    ok("低清内嵌图降级", info is None, f"info={'非空' if info else 'None'}")
    ok("低清原因说明尺寸", why is not None and "小于渲染尺寸" in why, str(why))
    doc.close()

    # 覆盖率阈值必须落在 (0, 1]，否则判定会退化成"永远/永不降级"
    ok("覆盖率阈值在 (0,1]", 0 < QUICK_MIN_COVERAGE <= 1, str(QUICK_MIN_COVERAGE))

    # ---- 2. 行为层：不管走哪条路，每页都只产出一个文件 ----
    for name, pdf_path in [("单图", single), ("多图", multi),
                           ("jp2", jp2pdf), ("低清", lowres)]:
        out = tmp / f"out_{name}"
        out.mkdir()
        res = render_pages_parallel(pdf_path, [0, 1, 2], str(out), 1, "jpg",
                                    quick=True, workers=2, batch_size=2)
        files = sorted(out.glob("*.jpg"))
        ok(f"{name}：3 页全部成功", sum(res) == 3 and len(res) == 3, str(res))
        ok(f"{name}：一页一图（3 个文件）", len(files) == 3,
           f"实际 {len(files)}：{[f.name for f in files]}")

    # ---- 3. quick 直拷：产出字节 == PDF 内嵌原始字节（零解码零重编码）----
    out = tmp / "out_copy"
    out.mkdir()
    render_pages_parallel(single, [0], str(out), 1, "jpg", quick=True,
                          workers=1, batch_size=1)
    produced = sorted(out.glob("*.jpg"))[0].read_bytes()
    ok("jpg 直拷未重编码", produced == jpg,
       f"产出 {len(produced)}B vs 源 {len(jpg)}B")

    # ---- 3b. JPX 快通道：整页一张 JPX 时直接解码流，但尺寸必须跟 zoom/dpi 走 ----
    import threading

    from PIL import Image

    def _run(pdf_path, pages, out, **kwargs):
        progress = {"lock": threading.Lock(), "done": 0, "total": len(pages)}
        render_pages_parallel(pdf_path, pages, str(out), 1, "jpg",
                              quick=True, workers=1, batch_size=len(pages),
                              progress=progress, **kwargs)
        return progress

    out = tmp / "out_jpx_fast"
    out.mkdir()
    # ⚠️ 用 dpi=72 让目标(595×842)明显小于原生(1600×2400)：快通道只在
    #    "能降档"时启用（降不下档交给 MuPDF 更快、更省内存）。
    progress = _run(jp2pdf, [0, 1, 2], out, dpi=72)
    ok("JPX 快通道：全部页直接解码流（跳过整页渲染）",
       progress.get("jpx_fast") == 3, str(progress))
    with Image.open(out / "1.jpg") as image:
        fast_size = image.size

    # 自适应解析结果必须与整页渲染**逐尺寸一致**（zoom/dpi 语义不能丢）
    out_ref = tmp / "out_jpx_ref"
    out_ref.mkdir()
    render_pages_parallel(jp2pdf, [0], str(out_ref), 1, "jpg", quick=False,
                          workers=1, batch_size=1, dpi=72)
    with Image.open(out_ref / "1.jpg") as image:
        ref_size = image.size
    ok("JPX 快通道：输出尺寸与整页渲染一致", fast_size == ref_size,
       f"{fast_size} vs {ref_size}")

    # zoom 必须生效：dpi=72 时 zoom 说了算（595×842 → 1190×1684）
    out_zoom = tmp / "out_jpx_zoom"
    out_zoom.mkdir()
    render_pages_parallel(jp2pdf, [0], str(out_zoom), 2, "jpg", quick=True,
                          workers=1, batch_size=1, dpi=72)
    with Image.open(out_zoom / "1.jpg") as image:
        zoom_size = image.size
    ok("JPX 快通道：zoom 生效", abs(zoom_size[0] - 1190) <= 2
       and abs(zoom_size[1] - 1684) <= 2, str(zoom_size))

    # 旋转页 / 一页多图：不许走快通道（会丢旋转、丢其它内容）
    rotated = tmp / "rotated.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 842), stream=jp2,
                      keep_proportion=False)
    page.set_rotation(90)
    doc.save(str(rotated))
    doc.close()
    out_rot = tmp / "out_jpx_rot"
    out_rot.mkdir()
    ok("JPX 快通道：旋转页自动回退整页渲染",
       _run(rotated, [0], out_rot, dpi=300).get("jpx_fast") == 0)

    multi_jp2 = _make_pdf(tmp / "multi_jp2.pdf", jp2, per_page=2)
    out_multi = tmp / "out_jpx_multi"
    out_multi.mkdir()
    ok("JPX 快通道：一页多图自动回退整页渲染",
       _run(multi_jp2, [0, 1, 2], out_multi, dpi=300).get("jpx_fast") == 0)

    # ---- 3c. 纯扫描页守卫：有可见内容就必须回退整页渲染 ----
    def _scan_page(name, *, text=False, invisible=False, highlight=False,
                   link=False, rotation=0):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(0, 0, 595, 842), stream=jpg,
                          keep_proportion=False)
        if text:
            page.insert_text((50, 100), "Visible text", fontsize=20)
        if invisible:
            page.insert_text((50, 100), "OCR layer", fontsize=20, render_mode=3)
        if highlight:
            page.add_highlight_annot(fitz.Rect(50, 90, 300, 120))
        if link:
            page.insert_link({"kind": fitz.LINK_URI,
                              "from": fitz.Rect(10, 10, 100, 40),
                              "uri": "https://example.com"})
        if rotation:
            page.set_rotation(rotation)
        path = tmp / f"guard_{name}.pdf"
        doc.save(str(path))
        doc.close()
        return path

    def _copy_is_raw(pdf_path, name, zoom=1, dpi=300):
        out = tmp / f"out_guard_{name}"
        out.mkdir()
        render_pages_parallel(pdf_path, [0], str(out), zoom, "jpg", quick=True,
                              workers=1, batch_size=1, dpi=dpi)
        return sorted(out.glob("*.jpg"))[0].read_bytes() == jpg

    ok("守卫：纯扫描页仍直拷原图", _copy_is_raw(_scan_page("plain"), "plain"))
    ok("守卫：不可见 OCR 文字层不阻止直拷",
       _copy_is_raw(_scan_page("invisible", invisible=True), "invisible"))
    ok("守卫：/Link 链接注释不阻止直拷",
       _copy_is_raw(_scan_page("link", link=True), "link"))
    ok("守卫：可见文字回退整页渲染",
       not _copy_is_raw(_scan_page("text", text=True), "text"))
    ok("守卫：高亮注释回退整页渲染",
       not _copy_is_raw(_scan_page("highlight", highlight=True), "highlight"))
    ok("守卫：旋转页回退整页渲染",
       not _copy_is_raw(_scan_page("rot", rotation=90), "rot"))
    ok("守卫：zoom≠1 一律整页渲染",
       not _copy_is_raw(_scan_page("zoom2"), "zoom2", zoom=2))

    # ---- 4. 降级统计：多图时全部降级且原因被记录 ----
    out = tmp / "out_stat"
    out.mkdir()
    import threading

    progress = {"lock": threading.Lock(), "done": 0, "total": 3}
    render_pages_parallel(multi, [0, 1, 2], str(out), 1, "jpg", quick=True,
                          workers=1, batch_size=3, progress=progress)
    ok("降级页数被统计", progress.get("fallback") == 3, str(progress.get("fallback")))
    ok("降级原因被记录", bool(progress.get("reasons")), str(progress.get("reasons")))
