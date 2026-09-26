# -*- coding: utf-8 -*-
"""生成 PDF：**不许把整本书的图攒在内存里**（2026-09-26 极限测试实测）。

背景：真实 794MB / 320 页的书（area=1 → 601 张）跑 print 时，
老实现把所有页 `executor.submit(...)` 一次性提上去、等 `page_data` 收齐才开始
写 PDF —— 等于**整本书的位图同时驻留内存**，峰值 **2994MB**，且随页数线性增长
（2400 页的书就是几十 GB → OOM）。改成「按序窗口加载、写完即释放」后：

    601 页 / 463MB PDF 完全一致（页数、体积、6 张抽样页的渲染像素全同）
    耗时 85.4s → 74.6s；峰值内存 2994MB → **1166MB（−61%）**

本模块钉两件事：
1. **行为**：小样本（6 张图）照样生成正确页数的 PDF（改完不能坏功能）；
2. **回归形态**：源码里不许再出现"整本预加载"的写法，且必须有按序窗口消费。
"""

NAME = "print_stream"
DEPENDS: list[str] = []
TITLE = "生成 PDF 不攒整本图"


def run(ctx) -> None:
    from pathlib import Path

    import fitz
    from PIL import Image

    from core.args import CommandArgs
    from functions import get_function
    from tests.selftests._context import ok

    root = ctx.tmp / "print_stream"
    src = root / "images"
    src.mkdir(parents=True, exist_ok=True)
    # 6 张 800×600 的小图，两两一组覆盖"左右页交替"的排版
    for i in range(6):
        Image.new("RGB", (800, 600), (200 + i * 5, 190, 180)).save(
            src / f"{i + 1}.jpg", quality=90
        )

    args = CommandArgs(
        command="print", input=str(src), output=str(root / "out"),
        page_margins="10", workers=4,
    )
    result = get_function("print", args, None).execute()
    pdf_path = Path(result["output"])
    ok("print 产出 PDF 文件", pdf_path.is_file(), str(pdf_path))
    doc = fitz.open(str(pdf_path))
    ok("PDF 页数与输入图片数一致", doc.page_count == 6, f"{doc.page_count} 页")
    ok("返回的 processed 计数与页数一致", result["processed"] == 6, str(result))
    doc.close()
    ok("落盘的临时文件已清掉（不留 *.part）",
       not list(pdf_path.parent.glob("*.part")),
       str(list(pdf_path.parent.glob("*.part"))))

    # ---- 流式输出必须与 fpdf 原生 output 产物**逐字节一致** ----
    # `write_streaming` 把 OutputProducer 的 bytearray 换成写文件的假 buffer
    # （`output_producer_class` 注入口），连带覆盖 `file_id()` 去算 trailer 的
    # /ID。这里做 A/B：同一份内容，一条走流式、一条走原生，比字节。
    from datetime import datetime, timezone

    from utils.pdf_stream import PdfDocument, write_streaming

    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def build() -> PdfDocument:
        pdf = PdfDocument(orientation="L", unit="mm", format=(297, 210))
        pdf.set_creation_date(fixed)  # 不固定的话 /ID 里的时间戳两边不同
        for i in range(3):
            pdf.add_page()
            pdf.image(str(src / f"{i + 1}.jpg"), x=10, y=10, w=100)
        return pdf

    streamed, native = root / "streamed.pdf", root / "native.pdf"
    write_streaming(build(), streamed)
    build().output(str(native))
    ok("流式写出 PDF", streamed.is_file() and streamed.stat().st_size > 0)
    ok(
        "流式输出与 pdf.output() 的产物逐字节一致（含 trailer /ID）",
        streamed.read_bytes() == native.read_bytes(),
        f"量 {streamed.stat().st_size} vs {native.stat().st_size}",
    )

    # ---- 回归形态：源码层面钉住"按序 + 限窗 + 用完就放" ----
    # ⚠️ 先**剥掉注释**再扫：说明性注释里正当地提到了旧写法
    #    （`page_data = [None] * total`），不剥就会把自己的注释判成违规
    #    （踩过一次，项目里 installer_paths 护栏也踩过同类坑）。
    raw = (Path(__file__).resolve().parents[2] / "functions" / "print.py").read_text(
        encoding="utf-8"
    )
    code = "\n".join(line.split("#", 1)[0] for line in raw.splitlines())
    ok(
        "不许再整本预加载（page_data = [None] * total 是旧写法的标志）",
        "page_data = [None] * total" not in code,
    )
    ok(
        "加载是限窗的（pending 里同时在飞的页数受 workers 约束）",
        "len(pending) < max(1, workers)" in code,
        "找不到窗口约束",
    )
    ok(
        "写完一页立刻释放位图（data[\"img\"] = None）",
        'data["img"] = None' in code,
    )
    ok(
        "落盘走 write_streaming（不许退回 pdf.output(path) 的整本缓冲写法）",
        "write_streaming(pdf, output_pdf)" in code and "pdf.output(" not in code,
        "仍在使用 pdf.output()",
    )
