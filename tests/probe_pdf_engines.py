# -*- coding: utf-8 -*-
"""多引擎「PDF 整页渲染」A/B 探针（**只测不改生产代码**）。

对比对象（同一份 PDF、同一批页、同一目标 DPI）：

1. ``pymupdf``      —— 当前生产路径：``page.get_pixmap()`` → PIL 存 JPG
2. ``pymupdf_dl``   —— ``get_displaylist().get_pixmap()``（验证"能否省解析"）
3. ``pdfium``       —— ``pypdfium2``（PDFium 内核）→ ``to_pil()`` → PIL 存 JPG
4. ``rawcv``        —— ``doc.extract_image()`` 原始码流 → ``cv2.imdecode`` → PIL 存 JPG
                       （**只对"整页只有一张图"有效**，图像本身的分辨率，不做页面合成）

每个引擎在**独立子进程**里跑（``--all``），这样内存峰值互不污染。指标：

- 冷启动（打开文档）与单页首次渲染
- N 页顺序渲染的中位数 / 总耗时 / 页每秒
- JPG 编码逐项拆开（渲染 vs 编码）
- 峰值 RSS 增量（psutil）
- 输出尺寸（宽×高）、文件字节数
- 与 PyMuPDF 结果缩到 256px 后的 RMSE（判断是否同一画面）
- 同页二次渲染（验证 MuPDF 的图像缓存收益）
- 4 进程并行吞吐（可选 ``--parallel``）

用法::

    python tests/probe_pdf_engines.py --pdf 某书.pdf --pages 0-7 --dpi 300
    python tests/probe_pdf_engines.py --pdf 某书.pdf --pages 0-7 --all --parallel
"""

from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ⚠️ 探针会产生临时图；统一落 tests/tmp（仓库内、已被 gitignore），别落到系统临时目录
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.tmpdir import install  # noqa: E402

install()

ENGINES = ("pymupdf", "pymupdf_dl", "pdfium", "pdf_oxide", "rawcv", "rawcv_reduce")


# --------------------------------------------------------------------- 工具
def _parse_pages(text: str) -> list[int]:
    """``"0-7,10"`` → 0-based 页码列表。"""
    out: list[int] = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _rss_mb() -> float:
    import psutil

    return psutil.Process().memory_info().rss / 1024 / 1024


def _save_jpeg(img, path: Path) -> int:
    """与生产同一口径落盘：JPEG q95、subsampling=0。返回字节数。"""
    img.save(path, "JPEG", quality=95, subsampling=0)
    return path.stat().st_size


def _encode_jpeg_bytes(img) -> int:
    """只编码不落盘（并行通道用，避免把磁盘 IO 算进吞吐）。"""
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95, subsampling=0)
    return len(buf.getvalue())


def _thumbnail_array(path_or_bytes):
    """缩到 256px 的 RGB numpy 数组（跨引擎比画面，消掉尺寸差异）。"""
    import numpy as np
    from PIL import Image

    if isinstance(path_or_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(bytes(path_or_bytes)))
    else:
        img = Image.open(path_or_bytes)
    with img:
        rgb = img.convert("RGB")
        rgb.thumbnail((256, 256), Image.LANCZOS)  # type: ignore[attr-defined]
        return np.asarray(rgb, dtype=np.int16)


def _rmse(a, b) -> float:
    import numpy as np

    if a.shape != b.shape:
        h = min(a.shape[0], b.shape[0])
        w = min(a.shape[1], b.shape[1])
        a, b = a[:h, :w], b[:h, :w]
    diff = (a - b).astype(np.float64)
    return float(np.sqrt((diff * diff).mean()))


# --------------------------------------------------------------------- 单引擎实现
def _render_one(engine: str, doc, page_index: int, dpi: float, out_dir: Path,
                seq: int) -> tuple[float, float, int, tuple[int, int]]:
    """渲一页并落盘 JPG。返回 (渲染秒, 编码秒, 字节数, (宽, 高))。"""
    scale = dpi / 72.0
    name = f"{engine}_{page_index + 1}_{seq}.jpg"
    path = out_dir / name

    if engine in ("pymupdf", "pymupdf_dl"):
        import pymupdf as fitz
        from PIL import Image

        page = doc.load_page(page_index)
        # ⚠️ ``get_pixmap(dpi=...)`` 只收 int（float 会抛 fz_pixmap_xres_set）；
        #    DisplayList 的 get_pixmap 没有 dpi 参数，用等价的 Matrix。
        dpi_i = int(round(dpi))
        mat = fitz.Matrix(dpi_i / 72.0, dpi_i / 72.0)
        t0 = time.perf_counter()
        if engine == "pymupdf_dl":
            pix = page.get_displaylist().get_pixmap(matrix=mat, alpha=False)
        else:
            pix = page.get_pixmap(dpi=dpi_i, alpha=False)
        render_s = time.perf_counter() - t0
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        t0 = time.perf_counter()
        size = _save_jpeg(img, path)
        return render_s, time.perf_counter() - t0, size, (pix.width, pix.height)

    if engine == "pdfium":
        t0 = time.perf_counter()
        page = doc[page_index]
        bitmap = page.render(scale=scale)
        render_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        img = bitmap.to_pil()
        size = _save_jpeg(img, path)
        dims = img.size
        page.close()
        return render_s, time.perf_counter() - t0, size, dims

    if engine == "pdf_oxide":
        # pdf_oxide（Rust/PyO3）：render_pixmap 返回 **RGBA** 原始像素。
        # ⚠️ 0.3.78 有 16,000,000 像素的硬上限，超出会**静默降倍率**（并打一行警告）；
        #    Python 侧没有暴露 RenderOptions，因此大页拿不到请求的分辨率。
        from PIL import Image

        t0 = time.perf_counter()
        pm = doc.render_pixmap(page_index, dpi=int(round(dpi)))
        render_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        img = Image.frombytes("RGBA", (pm.width, pm.height), pm.data).convert("RGB")
        size = _save_jpeg(img, path)
        return render_s, time.perf_counter() - t0, size, img.size

    if engine == "rawcv":
        import cv2
        import numpy as np
        from PIL import Image

        page = doc.load_page(page_index)
        images = page.get_images(full=True)
        if not images:
            raise RuntimeError("rawcv：本页没有内嵌图")
        t0 = time.perf_counter()
        info = doc.extract_image(int(images[0][0]))
        arr = cv2.imdecode(np.frombuffer(info["image"], dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError("rawcv：cv2 无法解码该码流")
        render_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        img = Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
        size = _save_jpeg(img, path)
        return render_s, time.perf_counter() - t0, size, img.size

    if engine == "rawcv_reduce":
        # 优化候选：原始码流按**目标分辨率**降档解码（JPEG2000 小波层），
        # 再缩到目标尺寸。只在"整页一张图 + 原图明显大于目标"时有意义。
        from PIL import Image

        page = doc.load_page(page_index)
        images = page.get_images(full=True)
        if not images:
            raise RuntimeError("rawcv_reduce：本页没有内嵌图")
        info = doc.extract_image(int(images[0][0]))
        target = (
            max(1, round(page.rect.width * scale)),
            max(1, round(page.rect.height * scale)),
        )
        t0 = time.perf_counter()
        with Image.open(io.BytesIO(info["image"])) as src:
            w, h = src.size
            reduce = 0
            # 允许解码结果略小于目标（≥90% 线性尺寸），否则只能等"原图≥2×目标"
            # 才降档——实测同一本书里各页的原图/页高比例并不一致，阈值太严会让
            # 降档在多数页上不触发。
            while (
                reduce < 6
                and (max(w, h) >> (reduce + 1)) >= max(target) * 0.90
            ):
                reduce += 1
            try:
                if reduce:
                    src._reduce = reduce  # type: ignore[attr-defined]
                src.load()
                img = src.convert("RGB")
            except Exception:  # noqa: BLE001 - 码流不支持该降档层数
                with Image.open(io.BytesIO(info["image"])) as full:
                    full.load()
                    img = full.convert("RGB")
        # 只在**解码结果大于目标**时缩；小于目标时保持原图（与 quick 直拷口径一致，
        # 不做插值放大——放大只会更糊且更慢）。
        if max(img.size) > max(target) * 1.02:
            img = img.resize(target, Image.LANCZOS)  # type: ignore[attr-defined]
        render_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        size = _save_jpeg(img, path)
        return render_s, time.perf_counter() - t0, size, img.size

    raise ValueError(f"未知引擎: {engine}")


def _open_doc(engine: str, pdf: str) -> Any:
    if engine == "pdfium":
        import pypdfium2 as pdfium

        return pdfium.PdfDocument(pdf)
    if engine == "pdf_oxide":
        import pdf_oxide

        return pdf_oxide.PdfDocument(pdf)
    import pymupdf as fitz

    return fitz.open(pdf)


def _close_doc(engine: str, doc) -> None:
    try:
        doc.close()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------- 并行（子进程）
def _parallel_worker(spec: tuple) -> float:
    """子进程：渲一页（只计时，不写盘）。返回耗时。"""
    engine, pdf, page, dpi = spec
    doc = _open_doc(engine, pdf)
    try:
        if engine == "pdfium":
            page_obj = doc[page]
            bitmap = page_obj.render(scale=dpi / 72.0)
            img = bitmap.to_pil()
            _encode_jpeg_bytes(img)
            page_obj.close()
        elif engine == "pdf_oxide":
            from PIL import Image

            pm = doc.render_pixmap(page, dpi=int(round(dpi)))
            _encode_jpeg_bytes(
                Image.frombytes("RGBA", (pm.width, pm.height), pm.data).convert("RGB")
            )
        elif engine == "rawcv":
            import cv2
            import numpy as np
            from PIL import Image

            images = doc.load_page(page).get_images(full=True)
            info = doc.extract_image(int(images[0][0]))
            arr = cv2.imdecode(np.frombuffer(info["image"], dtype=np.uint8),
                               cv2.IMREAD_COLOR)
            if arr is None:
                raise RuntimeError("rawcv：cv2 无法解码该码流")
            _encode_jpeg_bytes(Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)))
        else:
            import pymupdf as fitz
            from PIL import Image

            page_obj = doc.load_page(page)
            if engine == "pymupdf_dl":
                pix = page_obj.get_displaylist().get_pixmap(
                    matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False
                )
            else:
                pix = page_obj.get_pixmap(dpi=int(round(dpi)), alpha=False)
            _encode_jpeg_bytes(
                Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            )
        return 0.0
    finally:
        _close_doc(engine, doc)


def _run_parallel(engine: str, pdf: str, pages: list[int], dpi: float,
                  procs: int) -> float:
    """多进程墙钟秒数（每页一个任务；子进程各自打开文档）。"""
    from concurrent.futures import ProcessPoolExecutor

    specs = [(engine, pdf, p, dpi) for p in pages]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=procs) as pool:
        list(pool.map(_parallel_worker, specs))
    return time.perf_counter() - t0


# --------------------------------------------------------------------- 单引擎基准
def run_engine(engine: str, pdf: str, pages: list[int], dpi: float,
               out_dir: Path, parallel_procs: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rss0 = _rss_mb()
    t0 = time.perf_counter()
    doc = _open_doc(engine, pdf)
    open_s = time.perf_counter() - t0

    page_times: list[float] = []
    detail: list[dict] = []
    peak = rss0
    first_dims: tuple[int, int] | None = None
    first_path: Path | None = None
    cached_s = None
    immediate_repeat_s = None
    error = None
    try:
        for seq, page_index in enumerate(pages):
            t0 = time.perf_counter()
            render_s, encode_s, size, dims = _render_one(
                engine, doc, page_index, dpi, out_dir, seq
            )
            total = time.perf_counter() - t0
            page_times.append(total)
            detail.append({
                "page": page_index,
                "render_s": round(render_s, 4),
                "encode_s": round(encode_s, 4),
                "total_s": round(total, 4),
                "bytes": size,
                "w": dims[0],
                "h": dims[1],
            })
            peak = max(peak, _rss_mb())
            if first_dims is None:
                first_dims = dims
                first_path = out_dir / f"{engine}_{page_index + 1}_0.jpg"
            if seq == 0:
                # 紧接着再渲同一页：量"引擎是否缓存了解码结果"
                t0 = time.perf_counter()
                _render_one(engine, doc, page_index, dpi, out_dir, 9_000)
                immediate_repeat_s = time.perf_counter() - t0

        # 同页二次渲染：验证引擎是否缓存了解码后的图像
        cached_s = None
        if pages:
            t0 = time.perf_counter()
            _render_one(engine, doc, pages[0], dpi, out_dir, len(pages) + 1_000)
            cached_s = time.perf_counter() - t0
    except Exception as exc:  # noqa: BLE001 - 探针：把失败原因带回去
        error = f"{type(exc).__name__}: {exc}"
    finally:
        _close_doc(engine, doc)

    parallel_s = None
    if parallel_procs > 1 and pages and error is None and engine != "rawcv_reduce":
        parallel_s = _run_parallel(engine, pdf, pages, dpi, parallel_procs)

    return {
        "engine": engine,
        "pdf": pdf,
        "pages": pages,
        "dpi": dpi,
        "open_s": round(open_s, 3),
        "median_s": round(statistics.median(page_times), 3) if page_times else None,
        "mean_s": round(statistics.fmean(page_times), 3) if page_times else None,
        "pages_per_s": round(len(page_times) / sum(page_times), 2)
        if page_times and sum(page_times)
        else None,
        "cached_second_s": round(cached_s, 3) if cached_s is not None else None,
        "immediate_repeat_s": round(immediate_repeat_s, 3)
        if immediate_repeat_s is not None
        else None,
        "peak_rss_delta_mb": round(max(0.0, peak - rss0), 1),
        "first_dims": list(first_dims) if first_dims else None,
        "detail": detail,
        "parallel_s": round(parallel_s, 2) if parallel_s else None,
        "parallel_pages_per_s": round(len(pages) / parallel_s, 2)
        if parallel_s
        else None,
        "error": error,
        "_first_path": str(first_path) if first_path else None,
    }


# --------------------------------------------------------------------- 报告
def _print_table(results: list[dict]) -> None:
    print(f"\n{'engine':<12}{'open':>7}{'median':>9}{'pages/s':>9}"
          f"{'2nd now':>9}{'2nd later':>10}{'RSS+MB':>9}{'dims':>16}"
          f"{'par4':>8}{'par p/s':>9}")
    print("-" * 100)
    for r in results:
        if r.get("error"):
            print(f"{r['engine']:<12}  ERROR: {r['error']}")
            continue
        dims = r.get("first_dims") or (0, 0)
        print(
            f"{r['engine']:<12}{r.get('open_s', 0):>7.3f}"
            f"{(r.get('median_s') or 0):>9.3f}"
            f"{(r.get('pages_per_s') or 0):>9.2f}"
            f"{(r.get('immediate_repeat_s') or 0):>9.3f}"
            f"{(r.get('cached_second_s') or 0):>10.3f}"
            f"{(r.get('peak_rss_delta_mb') or 0):>9.1f}"
            f"{f'{dims[0]}x{dims[1]}':>16}"
            f"{(r.get('parallel_s') or 0):>8.2f}"
            f"{(r.get('parallel_pages_per_s') or 0):>9.2f}"
        )


def _all(pdf: str, pages: list[int], dpi: float, out_dir: Path,
         parallel_procs: int) -> int:
    """每个引擎一个子进程（内存隔离），汇总后打印表格 + 写 JSON。"""
    results: list[dict] = []
    for engine in ENGINES:
        out_json = out_dir / f"result_{engine}.json"
        cmd = [
            sys.executable, str(Path(__file__).resolve()), "--pdf", pdf,
            "--pages", ",".join(str(p) for p in pages), "--dpi", str(dpi),
            "--engine", engine, "--out-dir", str(out_dir),
            "--json", str(out_json), "--parallel", str(parallel_procs),
        ]
        print(f"[probe] {engine} ...", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out_json.is_file():
            results.append({
                "engine": engine,
                "error": (proc.stderr or proc.stdout or "子进程失败").strip()[-400:],
            })
            continue
        results.append(json.loads(out_json.read_text(encoding="utf-8")))

    # 画面一致性：与 pymupdf 的 256px 缩略图比 RMSE
    baseline = next(
        (r for r in results if r["engine"] == "pymupdf" and r.get("_first_path")),
        None,
    )
    base_arr = None
    if baseline and baseline.get("_first_path"):
        try:
            base_arr = _thumbnail_array(baseline["_first_path"])
        except Exception:  # noqa: BLE001
            base_arr = None
    for r in results:
        r["rmse_vs_pymupdf"] = None
        if base_arr is not None and r.get("_first_path"):
            try:
                r["rmse_vs_pymupdf"] = round(
                    _rmse(base_arr, _thumbnail_array(r["_first_path"])), 2
                )
            except Exception:  # noqa: BLE001
                pass

    _print_table(results)
    print(f"\n{'engine':<12}{'RMSE(256px)':>14}")
    print("-" * 28)
    for r in results:
        rmse = r.get("rmse_vs_pymupdf")
        print(f"{r['engine']:<12}{(f'{rmse:.2f}' if rmse is not None else '-'):>14}")

    merged = out_dir / "report.json"
    for r in results:
        r.pop("_first_path", None)
    merged.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"\n[probe] JSON: {merged}")
    return 0 if any(not r.get("error") for r in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="多引擎 PDF 整页渲染 A/B")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--pages", default="0-3")
    parser.add_argument("--dpi", type=float, default=300)
    parser.add_argument("--engine", choices=(*ENGINES, "all"), default="all")
    parser.add_argument("--parallel", type=int, default=0, help="并行进程数（0=不测）")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--json", default="", help="单引擎结果写到这个 JSON")
    args = parser.parse_args()

    pdf = str(Path(args.pdf).expanduser().resolve())
    pages = _parse_pages(args.pages)
    out_dir = Path(args.out_dir) if args.out_dir else Path("tests/tmp/probe_pdf_engines")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.engine == "all":
        return _all(pdf, pages, args.dpi, out_dir, args.parallel)

    result = run_engine(args.engine, pdf, pages, args.dpi, out_dir, args.parallel)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
