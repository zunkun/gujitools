# -*- coding: utf-8 -*-
"""整页渲染的 DPI 下限自测（72 DPI 陷阱）。

背景：PDF 的页面单位是 pt（1pt = 1/72 inch），PyMuPDF 在 zoom=1 时把 1pt
渲染成 1px —— 也就是 72 DPI。古籍扫描件不受影响：quick 模式直接取内嵌的
原图字节，分辨率由扫描件决定。但**普通矢量 PDF**没有内嵌图（或内嵌图被
quick 拒绝），只能整页渲染，zoom=1 就只有 72 DPI，去底色后再打回 PDF
必然发虚。

现在的规则（`utils.pdf_utils.render_zoom`）：

* 整页渲染：zoom = max(用户 zoom, dpi/72)，仍受 6000px 宽度封顶；
* 内嵌图路径：仍按 `calculate_zoom`（用户 zoom）判定与落盘，**不因 DPI
  下限被放大**，也**不因下限变严而被判成低清**（否则 240 DPI 的扫描件会被
  重新渲染成插值放大图，更糊）。

本模块守住这三条，并做一次端到端：矢量 PDF 提取出来必须是 300 DPI 量级。
"""

import io

NAME = "extract_dpi"
DEPENDS: list[str] = []
TITLE = "提取 DPI 下限"


def _vector_pdf(path, pages=2, width=595, height=842):
    """纯矢量页面：只画文字/线条，不贴任何位图。"""
    import pymupdf as fitz

    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text((72, 100 + i * 20), f"vector page {i + 1}", fontsize=24)
        page.draw_line(fitz.Point(72, 300), fitz.Point(500, 300))
    doc.save(str(path))
    doc.close()
    return str(path)


def _scan_pdf(path, w=1600, h=2400):
    """扫描页：整页贴一张 jpg（模拟古籍扫描件）。"""
    import pymupdf as fitz
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 235, 225)).save(buf, "JPEG", quality=88)
    stream = buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 842), stream=stream)
    doc.save(str(path))
    doc.close()
    return str(path), stream


def run(ctx) -> None:
    import tempfile
    from pathlib import Path

    import pymupdf as fitz
    from PIL import Image

    from tests.selftests._context import ok
    from utils.pdf_utils import (
        DEFAULT_RENDER_DPI,
        MAX_OUTPUT_WIDTH_PX,
        calculate_zoom,
        render_pages_parallel,
        render_zoom,
    )

    tmp = Path(tempfile.mkdtemp(prefix="guji_dpi_"))

    # ---- 1. 纯函数：DPI 下限 ----
    ok("默认下限是 300 DPI", DEFAULT_RENDER_DPI == 300, str(DEFAULT_RENDER_DPI))
    # A4 宽 595pt：300 DPI => 595 * 300/72 ≈ 2479px
    z = render_zoom(595, 1)
    ok("zoom=1 时补到 300 DPI", abs(z - 300 / 72) < 0.01, f"zoom={z}")
    ok("补到的宽度约 2479px", abs(595 * z - 2479) < 5, f"宽={595 * z:.0f}px")
    # 用户 zoom 更高时以用户为准
    ok("zoom=8 不被下限削减", render_zoom(595, 8) == 8, str(render_zoom(595, 8)))
    # dpi=72 等价于旧行为
    ok("dpi=72 时等于旧 zoom", render_zoom(595, 1, 72) == calculate_zoom(595, 1),
       str(render_zoom(595, 1, 72)))
    # 封顶：极宽页面不许突破 6000px
    huge = render_zoom(4000, 1)
    ok("宽页面受 6000px 封顶", 4000 * huge <= MAX_OUTPUT_WIDTH_PX + 1,
       f"宽={4000 * huge:.0f}px")
    ok("下限永不小于 1", render_zoom(20000, 1) >= 1, str(render_zoom(20000, 1)))
    ok("下限不低于用户 zoom", render_zoom(800, 6) >= 6, str(render_zoom(800, 6)))

    # ---- 2. 端到端：矢量 PDF 必须渲染到 300 DPI 量级 ----
    vec = _vector_pdf(tmp / "vector.pdf")
    out = tmp / "out_vec"
    out.mkdir()
    res = render_pages_parallel(vec, [0, 1], str(out), 1, "png", quick=True,
                                workers=1, batch_size=2)
    ok("矢量 PDF 两页都成功", sum(res) == 2 and len(res) == 2, str(res))
    files = sorted(out.glob("*.png"))
    ok("一页一图（2 个文件）", len(files) == 2, f"{[f.name for f in files]}")
    if files:
        with Image.open(files[0]) as im:
            w, h = im.size
        dpi_equiv = w / 595 * 72
        ok("矢量页渲染到 ~300 DPI", 280 <= dpi_equiv <= 320, f"{w}x{h} ≈ {dpi_equiv:.0f}DPI")
        ok("不再是 72 DPI 的糊图", w > 2000, f"宽={w}px")

    # ---- 3. 显式 zoom 仍生效（zoom=2 → 600 DPI，未超 6000px 上限）----
    out2 = tmp / "out_vec2"
    out2.mkdir()
    render_pages_parallel(vec, [0], str(out2), 2, "png", quick=False,
                          workers=1, batch_size=1)
    with Image.open(sorted(out2.glob("*.png"))[0]) as im:
        w2 = im.size[0]
    ok("zoom=2 高于下限，按 zoom 走", w2 > 2479, f"宽={w2}px")

    # ---- 4. 扫描件不被下限拖累：内嵌图原样落盘 ----
    scan, raw = _scan_pdf(tmp / "scan.pdf")
    out3 = tmp / "out_scan"
    out3.mkdir()
    render_pages_parallel(scan, [0], str(out3), 1, "jpg", quick=True,
                          workers=1, batch_size=1)
    produced = sorted(out3.glob("*.jpg"))[0]
    ok("扫描件仍是原图字节（未被放大重编码）", produced.read_bytes() == raw,
       f"产出 {produced.stat().st_size}B vs 源 {len(raw)}B")
    with Image.open(produced) as im:
        ok("扫描件尺寸保持原生 1600x2400", im.size == (1600, 2400), str(im.size))

    # 240 DPI 的扫描件不能被判成"低清"而降级成插值放大图
    doc = fitz.open(scan)
    page = doc.load_page(0)
    from utils.pdf_utils import _embedded_page_image

    info, why = _embedded_page_image(doc, page, page.rect, "jpg", 1.0)
    ok("240 DPI 扫描件仍走内嵌路径", info is not None, str(why))
    doc.close()

    # ---- 5. 关掉 quick 时扫描件也被渲染（此时下限生效）----
    out4 = tmp / "out_scan_render"
    out4.mkdir()
    render_pages_parallel(scan, [0], str(out4), 1, "png", quick=False,
                          workers=1, batch_size=1)
    with Image.open(sorted(out4.glob("*.png"))[0]) as im:
        w4 = im.size[0]
    ok("强制渲染扫描件也补到 300 DPI", abs(w4 - 2479) < 5, f"宽={w4}px")
