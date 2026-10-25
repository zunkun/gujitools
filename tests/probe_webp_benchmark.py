# -*- coding: utf-8 -*-
"""WebP 格式可用性与收益探针（**只测不改生产代码**）。

回答两个问题：

1. **能不能用**：extract / 检测提交 / 去底色 这几步的产物换成 webp 后，
   cv2（detect 取图）、PIL（rembg / print 取图）、Qt（界面预览与缩略图）
   是否都能正确解码与渲染？
2. **值不值得**：按「体积 / 编码耗时 /解码耗时 / 画质（PSNR、SSIM）/
   去底色二值稳定性 / 内存峰值 / Qt 缩放解码」多维度对比。

测试素材默认取本机任务目录里**真实古籍扫描件**（只读，不写回用户数据）：

- ``stages/extract/*.jpg`` —— 提取页（≈2400×2400）
- ``stages/detect/*.png``   —— 检测提交裁图（≈1100×1520，体积大头）
- ``stages/rembg/*.png``    —— 白底透明产物（1 位调色板）

指标口径：

- 体积：落盘字节数（KB/页）
- 编码/解码：单线程墙钟耗时（ms，取样本中位数）
- 画质：解码结果 vs 原始数组的 PSNR / 全局 SSIM；检测裁图额外测
  「经 ``utils.rembg_page`` 二值化后与原结果的像素差异比例」——这是
  比 PSNR 更贴近下游的判据
- 内存：**每个组合单独起子进程**，用 psutil 峰值 RSS 增量对比
- 渲染：Qt ``QImageReader`` 整幅/``setScaledSize`` 缩略图解码，并核对像素
- 链路：真实 PDF 单页 ``extract_single_page(ext=webp)``，再用 cv2/PIL/Qt
  读取；同时验证当前代码里两处「只认 jpg/png」的位置是否会漏掉 webp
- 检测一致性：同一页分别存 jpg q95 / webp q90，用真实 YOLO 模型检测，
  比较左右/整幅框是否完全相同

用法::

    & C:\\Users\\liuzu\\anaconda3\\envs\\py310\\python.exe tests\\probe_webp_benchmark.py
    ... --samples 6 --skip-yolo --skip-memory
    ... --task C:\\Users\\liuzu\\Documents\\guji\\tasks\\0021

产物落在 ``tests/tmp/webp_probe_*``（仓库内、已 gitignore），并打印 markdown
表格到 stdout；``results.json`` 供写报告时取数。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.tmpdir import install, temp_dir  # noqa: E402

# 临时数据统一落 tests/tmp（含子进程，见 tests/tmpdir.py）
install()
# Qt 无头渲染：缩略图/预览解码不需要真实窗口
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MB = 1024.0 * 1024.0


# ===================================================================== 编码器
def save_jpeg(rgb: np.ndarray, path: Path, quality: int = 95) -> None:
    """PIL 写 JPEG（与 ``utils.pdf_extract._save_pil`` 同口径：4:4:4）。"""
    Image.fromarray(rgb, "RGB").save(
        path, "JPEG", quality=quality, subsampling=0
    )


def save_webp_pil(
    rgb: np.ndarray,
    path: Path,
    *,
    quality: int | None = None,
    lossless: bool = False,
    method: int = 4,
) -> None:
    """PIL 写 WebP（提取/裁图链路本来就都走 PIL）。"""
    options: dict[str, Any] = {"format": "WEBP", "method": int(method)}
    if lossless:
        options["lossless"] = True
    else:
        options["quality"] = int(quality if quality is not None else 90)
    Image.fromarray(rgb, "RGB").save(path, **options)


def save_webp_cv2(rgb: np.ndarray, path: Path, quality: int = 90) -> None:
    """cv2 写 WebP（``utils.image_io.imwrite`` 那条链；只作编码器对照）。"""
    import cv2

    ok, buffer = cv2.imencode(
        ".webp", rgb[:, :, ::-1], [cv2.IMWRITE_WEBP_QUALITY, int(quality)]
    )
    if not ok:
        raise RuntimeError("cv2.imencode webp 失败")
    path.write_bytes(buffer.tobytes())


def save_png(rgb: np.ndarray, path: Path, level: int = 6) -> None:
    Image.fromarray(rgb, "RGB").save(path, "PNG", compress_level=int(level))


def save_png_compact(rgb: np.ndarray, path: Path) -> None:
    """检测提交当前的落盘形态（``utils.compact_png``，逐像素无损）。"""
    from utils.compact_png import save_png_compact as _save

    _save(rgb, path, dpi=(300, 300))


def save_webp_rgba(
    rgba: np.ndarray,
    path: Path,
    *,
    quality: int | None = None,
    lossless: bool = False,
    method: int = 4,
) -> None:
    options: dict[str, Any] = {"format": "WEBP", "method": int(method)}
    if lossless:
        options["lossless"] = True
    else:
        options["quality"] = int(quality if quality is not None else 90)
    Image.fromarray(rgba, "RGBA").save(path, **options)


def save_png_rgba(rgba: np.ndarray, path: Path, level: int = 6) -> None:
    Image.fromarray(rgba, "RGBA").save(path, "PNG", compress_level=int(level))


# ===================================================================== 指标
def measure(fn: Callable[[], Any]) -> tuple[Any, float]:
    """跑一次，返回 ``(结果, 墙钟毫秒)``。"""
    started = time.perf_counter()
    value = fn()
    return value, (time.perf_counter() - started) * 1000.0


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image.load()
        return np.array(image.convert("RGB"))


def load_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image.load()
        return np.array(image.convert("RGBA"))


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    """PSNR（dB）；完全一致返回 ``inf``。"""
    diff = a.astype(np.float64) - b.astype(np.float64)
    mse = float((diff * diff).mean())
    if mse <= 0.0:
        return float("inf")
    return 10.0 * math.log10((255.0 * 255.0) / mse)


def _box_mean(array: np.ndarray, size: int) -> np.ndarray:
    """积分图实现的均值滤波（避免为 SSIM 依赖 scipy/cv2）。"""
    pad = size // 2
    padded = np.pad(array, ((pad, pad), (pad, pad)), mode="reflect")
    integral = np.pad(padded, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    height, width = array.shape
    window = (
        integral[size:size + height, size:size + width]
        - integral[0:height, size:size + width]
        - integral[size:size + height, 0:width]
        + integral[0:height, 0:width]
    )
    return window / float(size * size)


def ssim_gray(a: np.ndarray, b: np.ndarray, size: int = 8) -> float:
    """全局平均 SSIM（单通道，标准常数 C1/C2）。"""
    x = a.astype(np.float64)
    y = b.astype(np.float64)
    mu_x = _box_mean(x, size)
    mu_y = _box_mean(y, size)
    mu_x2, mu_y2, mu_xy = mu_x * mu_x, mu_y * mu_y, mu_x * mu_y
    sigma_x2 = _box_mean(x * x, size) - mu_x2
    sigma_y2 = _box_mean(y * y, size) - mu_y2
    sigma_xy = _box_mean(x * y, size) - mu_xy
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    numerator = (2 * mu_xy + c1) * (2 * sigma_xy + c2)
    denominator = (mu_x2 + mu_y2 + c1) * (sigma_x2 + sigma_y2 + c2)
    return float((numerator / denominator).mean())


def gray_of(rgb: np.ndarray) -> np.ndarray:
    """与 ``functions.rembg.load_rgb_and_gray`` 同口径：PIL convert("L")。"""
    return np.array(Image.fromarray(rgb, "RGB").convert("L"))


def binarize(rgb: np.ndarray) -> np.ndarray:
    """走生产同一条去底色入口（默认全局 Otsu）。"""
    from utils import rembg_page

    return rembg_page(rgb, gray_of(rgb))


def rgb_of(array: np.ndarray) -> np.ndarray:
    if array.ndim == 3:
        return array[:, :, :3]
    return np.repeat(array[:, :, None], 3, axis=2)


def diff_ratio(a: np.ndarray, b: np.ndarray) -> float:
    """逐像素差异比例（任一通道不同即算不同）。"""
    if a.ndim == 3:
        return float(np.any(a != b, axis=-1).mean())
    return float((a != b).mean())


def flatten_alpha(rgba: np.ndarray) -> np.ndarray:
    """透明底合成到白纸（print 步骤的读法）。"""
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    out = rgb * alpha + 255.0 * (1.0 - alpha)
    return np.clip(out, 0, 255).astype(np.uint8)


def median(values: Iterable[float]) -> float:
    """真中位数（偶数个取中间两个的平均），避免 4 个样本时被上中位数带偏。"""
    data = sorted(values)
    if not data:
        return float("nan")
    middle = len(data) // 2
    if len(data) % 2:
        return float(data[middle])
    return float((data[middle - 1] + data[middle]) / 2.0)


def kb(value: float) -> float:
    return value / 1024.0


# ===================================================================== Qt
def qimage_to_rgb(image) -> np.ndarray | None:
    """QImage（任意格式）→ ``(H, W, 3)`` RGB 数组；空图返回 None。"""
    from PySide6.QtGui import QImage

    if image is None or image.isNull():
        return None
    if image.format() != QImage.Format.Format_RGB32:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    height, width = image.height(), image.width()
    stride = image.bytesPerLine()
    buffer = np.frombuffer(image.constBits(), np.uint8)
    rows = buffer[: stride * height].reshape(height, stride)
    pixels = rows[:, : width * 4].reshape(height, width, 4)
    return np.ascontiguousarray(pixels[:, :, 2::-1])


def qt_read(path: Path, edge: int = 0) -> tuple[Any, float]:
    """Qt 解码一张图；``edge > 0`` 时用 ``setScaledSize`` 缩放解码。"""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImageReader

    def _read():
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        if edge:
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(
                    size.scaled(
                        QSize(edge, edge),
                        # Qt6 的枚举全名，避免 import Qt 的旧别名
                        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt
                        .AspectRatioMode.KeepAspectRatio,
                    )
                )
        return reader.read()

    image, ms = measure(_read)
    return image, ms


# ===================================================================== 通用基准
def bench_rgb(
    images: list[np.ndarray],
    variants: list[tuple[str, Callable[[np.ndarray, Path], None], str]],
    out_dir: Path,
    tag: str,
    *,
    with_binarize: bool = False,
    references: list[int] | None = None,
) -> list[dict]:
    """逐变体编码/解码，统计体积、耗时、画质（可选二值稳定性）。

    ``references`` 是同一批图**当前落盘文件**的字节数（extract 是源 jpg、
    detect 是现状 png）。用它算「相对现状体积」的逐图比值，再取中位数——
    避免抽样页恰好偏大/偏小时把全量投影带偏。
    """
    originals_bin = [binarize(image) for image in images] if with_binarize else []
    rows: list[dict] = []
    for name, saver, suffix in variants:
        enc_ms: list[float] = []
        dec_ms: list[float] = []
        sizes: list[int] = []
        psnrs: list[float] = []
        ssims: list[float] = []
        bin_diffs: list[float] = []
        bin_sizes: list[int] = []
        ratios: list[float] = []
        paths: list[Path] = []
        for index, rgb in enumerate(images):
            path = out_dir / f"{tag}_{index:02d}_{name.replace('/', '-')}.{suffix}"
            _, encode_ms = measure(lambda rgb=rgb, path=path: saver(rgb, path))
            decoded, decode_ms = measure(lambda path=path: load_rgb(path))
            enc_ms.append(encode_ms)
            dec_ms.append(decode_ms)
            sizes.append(path.stat().st_size)
            if references is not None and index < len(references):
                ratios.append(path.stat().st_size / max(1, references[index]))
            psnrs.append(psnr(rgb, decoded))
            ssims.append(ssim_gray(gray_of(rgb), gray_of(decoded)))
            paths.append(path)
            if with_binarize:
                result = binarize(decoded)
                bin_diffs.append(diff_ratio(originals_bin[index], result))
                from utils.transparent_png import save_white_as_transparent

                probe_path = path.with_name(path.stem + "_bin.png")
                save_white_as_transparent(rgb_of(result), probe_path)
                bin_sizes.append(probe_path.stat().st_size)
        rows.append({
            "variant": name,
            "kb": median(kb(size) for size in sizes),
            "ratio": median(ratios) if ratios else None,
            "encode_ms": median(enc_ms),
            "decode_ms": median(dec_ms),
            "psnr": median(psnrs),
            "ssim": median(ssims),
            "bin_diff": median(bin_diffs) if bin_diffs else None,
            "bin_kb": median(kb(size) for size in bin_sizes) if bin_sizes else None,
            "paths": [str(path) for path in paths],
        })
    return rows


def bench_rgba(
    images: list[np.ndarray],
    variants: list[tuple[str, Callable[[np.ndarray, Path], None], str]],
    out_dir: Path,
    *,
    references: list[int] | None = None,
) -> list[dict]:
    """去底色产物（透明底）的变体对比：体积、耗时、alpha 是否逐位保留。"""
    originals = [flatten_alpha(rgba) for rgba in images]
    rows: list[dict] = []
    for name, saver, suffix in variants:
        enc_ms: list[float] = []
        dec_ms: list[float] = []
        sizes: list[int] = []
        ratios: list[float] = []
        alpha_exact: list[float] = []
        psnrs: list[float] = []
        for index, rgba in enumerate(images):
            path = out_dir / f"rgba_{index:02d}_{name}.{suffix}"
            _, encode_ms = measure(lambda rgba=rgba, path=path: saver(rgba, path))
            decoded, decode_ms = measure(lambda path=path: load_rgba(path))
            enc_ms.append(encode_ms)
            dec_ms.append(decode_ms)
            sizes.append(path.stat().st_size)
            if references is not None and index < len(references):
                ratios.append(path.stat().st_size / max(1, references[index]))
            alpha_exact.append(float((decoded[:, :, 3] == rgba[:, :, 3]).mean()))
            psnrs.append(psnr(originals[index], flatten_alpha(decoded)))
        rows.append({
            "variant": name,
            "kb": median(kb(size) for size in sizes),
            "ratio": median(ratios) if ratios else None,
            "encode_ms": median(enc_ms),
            "decode_ms": median(dec_ms),
            "alpha_exact": median(alpha_exact),
            "psnr": median(psnrs),
        })
    return rows


# ===================================================================== 内存子进程
def _mem_decode(kind: str, path: Path):
    if kind == "pil":
        with Image.open(path) as image:
            image.load()
            return image.convert("RGB")
    if kind == "cv2":
        from utils.image_io import imread

        return imread(path)
    if kind == "qt_scaled":
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QImageReader

        reader = QImageReader(str(path))
        reader.setScaledSize(QSize(256, 256))
        return reader.read()
    if kind == "qt_full":
        from PySide6.QtGui import QImage

        return QImage(str(path))
    raise ValueError(f"未知 kind: {kind}")


def mem_worker(kind: str, path: Path, loops: int) -> None:
    """子进程入口：反复解码同一张图，打印峰值 RSS 增量与中位耗时（JSON）。"""
    import gc

    try:
        import psutil

        process = psutil.Process()
        base = process.memory_info().rss
        peak = base
    except ImportError:  # pragma: no cover - 本机有 psutil
        process = None
        base = peak = 0

    times: list[float] = []
    for _ in range(max(1, int(loops))):
        object_, ms = measure(lambda: _mem_decode(kind, path))
        times.append(ms)
        if process is not None:
            peak = max(peak, process.memory_info().rss)
        del object_
        gc.collect()
    if process is not None:
        try:
            peak = max(peak, process.memory_info().peak_wset)
        except AttributeError:  # 非 Windows
            pass
    print(json.dumps({
        "kind": kind,
        "path": str(path),
        "base_mb": base / MB,
        "peak_mb": peak / MB,
        "delta_mb": (peak - base) / MB,
        "median_ms": median(times),
        "loops": len(times),
    }, ensure_ascii=False))


def run_mem(kind: str, path: Path, loops: int = 5) -> dict:
    """父进程起一个干净子进程跑内存探针（避免各格式互相污染峰值）。"""
    completed = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve()),
            "--mem-worker", "--kind", kind, "--path", str(path),
            "--loops", str(loops),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    for line in reversed((completed.stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "delta_mb" in payload:
            return payload
    return {
        "kind": kind,
        "path": str(path),
        "error": (completed.stderr or completed.stdout or "子进程无输出")[-500:],
    }


# ===================================================================== 素材
def find_task_dir() -> Path | None:
    base = Path.home() / "Documents" / "guji" / "tasks"
    if not base.is_dir():
        return None
    candidates = [
        entry for entry in base.iterdir()
        if (entry / "stages" / "extract").is_dir()
        and (entry / "stages" / "detect").is_dir()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: len(
        list((entry / "stages" / "extract").glob("*"))
    ))


T = TypeVar("T")


def pick_evenly(paths: list[T], count: int) -> list[T]:
    """从列表里均匀抽 ``count`` 个元素（不足则全给）。"""
    if not paths:
        return []
    if len(paths) <= count:
        return paths
    step = len(paths) / float(count)
    return [paths[min(len(paths) - 1, int(index * step))] for index in range(count)]


def stage_files(task: Path, name: str, count: int) -> tuple[list[Path], int, int]:
    """返回（抽样文件，目录文件数，目录总字节）。"""
    directory = task / "stages" / name
    files = [path for path in directory.iterdir() if path.is_file()] if directory.is_dir() else []
    total = sum(path.stat().st_size for path in files)
    return pick_evenly(sorted(files), count), len(files), total


# ===================================================================== 真实链路
def page_rgb_array(document, page_index: int) -> np.ndarray:
    """取 PDF 某页的「源像素」：优先单张内嵌图原码流，否则整页渲染。"""
    import pymupdf as fitz

    page = document.load_page(page_index)
    images = page.get_images(full=True)
    if len(images) == 1:
        try:
            info = document.extract_image(images[0][0])
            with Image.open(io.BytesIO(info["image"])) as source:
                source.load()
                orientation = source.getexif().get(274, 1)
                if orientation != 1:
                    from PIL import ImageOps

                    source = ImageOps.exif_transpose(source)
                return np.array(source.convert("RGB"))
        except Exception:  # noqa: BLE001 - 抽不出/解不开就整页渲染
            pass
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
    return np.array(
        Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    )


def run_integration(pdf: Path, pages: list[int], out_root: Path) -> list[dict]:
    """真实调 ``extract_single_page``，对比 ext=jpg / ext=webp 的产物与读取链路。"""
    from utils.file_utils import collect_image_files
    from utils.pdf_extract import extract_single_page

    rows: list[dict] = []
    for page_index in pages:
        outputs: dict[str, dict] = {}
        for ext in ("jpg", "webp"):
            # 每页独占一个目录：下面的 collect_image_files / 缩略图检查按目录
            # 统计，共用一个目录会把前面几页也算进来。
            out_dir = out_root / f"extract_{ext}" / f"p{page_index + 1}"
            out_dir.mkdir(parents=True, exist_ok=True)
            result, ms = measure(lambda ext=ext, out_dir=out_dir: extract_single_page(
                str(pdf), page_index, str(out_dir), ext=ext,
            ))
            result = dict(result)
            result["elapsed_ms"] = ms
            result["dir"] = str(out_dir)
            if result.get("path"):
                result["bytes"] = Path(result["path"]).stat().st_size
            outputs[ext] = result

        raw_webp_path = outputs["webp"].get("path")
        raw_jpg_path = outputs["jpg"].get("path")
        webp_text = str(raw_webp_path) if raw_webp_path else None
        jpg_text = str(raw_jpg_path) if raw_jpg_path else None
        row = {
            "page": page_index + 1,
            "jpg": outputs["jpg"],
            "webp": outputs["webp"],
        }
        if webp_text:
            webp_file = Path(webp_text)
            webp_image, webp_ms = measure(lambda: load_rgb(webp_file))
            cv2_image, cv2_ms = measure(lambda: __import__(
                "utils.image_io", fromlist=["imread"]).imread(webp_file))
            qt_image, qt_ms = qt_read(webp_file)
            qt_scaled, qt_scaled_ms = qt_read(webp_file, edge=256)
            from PySide6.QtGui import QImageReader

            reader = QImageReader(str(webp_file))
            row["checks"] = {
                "pil_ok": bool(webp_image is not None),
                "pil_size": list(webp_image.shape[:2][::-1]),
                "pil_ms": webp_ms,
                "cv2_ok": cv2_image is not None,
                "cv2_shape": list(cv2_image.shape) if cv2_image is not None else None,
                "cv2_ms": cv2_ms,
                "qt_can_read": bool(reader.canRead()),
                "qt_ok": not qt_image.isNull(),
                "qt_size": [qt_image.width(), qt_image.height()]
                if not qt_image.isNull() else None,
                "qt_ms": qt_ms,
                "qt_scaled_ok": not qt_scaled.isNull(),
                "qt_scaled_size": [qt_scaled.width(), qt_scaled.height()]
                if not qt_scaled.isNull() else None,
                "qt_scaled_ms": qt_scaled_ms,
                "collect_images": len(collect_image_files(
                    webp_file.parent, False)),
            }
            row["checks"]["print_collect"] = _print_collect_count(
                webp_file.parent)
            row["checks"]["page_thumb_bytes"] = _thumb_bytes(
                webp_file.parent, page_index)
            if jpg_text:
                jpg_image = load_rgb(Path(jpg_text))
                # 注意：jpg 走 quick 直拷（PDF 内嵌 JPEG 原字节），webp 走
                # PIL 默认 quality=80 重编码——这一项反映「实际切换后的差距」。
                row["psnr_webp_vs_jpg"] = psnr(jpg_image, webp_image) if (
                    jpg_image.shape == webp_image.shape) else None
                # 同一源像素再压一版 webp q90（单代）供体积对照
                q90_path = webp_file.parent / f"q90_{page_index + 1}.webp"
                save_webp_pil(jpg_image, q90_path, quality=90)
                row["webp_q90_bytes"] = q90_path.stat().st_size
        rows.append(row)
    return rows


def _print_collect_count(directory: Path) -> int | None:
    """验证 ``functions/print.py`` 的目录扫描是否认得 webp（预期 0）。"""
    try:
        from functions.print import _collect_image_files

        return len(_collect_image_files(directory, None))
    except Exception:  # noqa: BLE001 - 只为观察，不因导入失败中断
        return None


def _thumb_bytes(directory: Path, page_index: int) -> int | None:
    """验证 ``_thumb_from_page_image`` 是否认得 webp（预期 0 = 漏掉）。"""
    try:
        from desktop.workers.pdf_render_service import _thumb_from_page_image

        return len(_thumb_from_page_image(str(directory), int(page_index),
                                          256, 80, "jpg"))
    except Exception:  # noqa: BLE001
        return None


def run_yolo(pdf: Path, pages: list[int], out_root: Path) -> list[dict]:
    """真实 YOLO：同一页存 jpg q95 / webp q90 / webp 无损，比较检测框。"""
    import pymupdf as fitz

    import utils
    from functions.detect import detect_page_content

    model = utils.load_yolo_model()
    document = fitz.open(str(pdf))
    rows: list[dict] = []
    try:
        for page_index in pages:
            original = page_rgb_array(document, page_index)
            page_dir = out_root / "yolo"
            page_dir.mkdir(parents=True, exist_ok=True)
            variants = [
                ("jpg_q95", page_dir / f"{page_index + 1}_q95.jpg", "jpg", 95),
                ("webp_q90", page_dir / f"{page_index + 1}_q90.webp", "webp", 90),
                ("webp_lossless", page_dir / f"{page_index + 1}_ll.webp", "webp", None),
            ]
            results: dict[str, Any] = {}
            for name, path, kind, quality in variants:
                if kind == "jpg":
                    save_jpeg(original, path, quality=int(quality or 95))
                elif quality is None:
                    save_webp_pil(original, path, lossless=True)
                else:
                    save_webp_pil(original, path, quality=int(quality))
                image, decode_ms = measure(lambda path=path: utils.imread(path))
                boxes, infer_ms = measure(lambda image=image: detect_page_content(image, model))
                results[name] = {
                    "bytes": path.stat().st_size,
                    "decode_ms": decode_ms,
                    "detect_ms": infer_ms,
                    "left": list(boxes.left) if boxes.left else None,
                    "right": list(boxes.right) if boxes.right else None,
                    "full": list(boxes.full) if boxes.full else None,
                }
            baseline = results["jpg_q95"]
            for name in ("webp_q90", "webp_lossless"):
                results[name]["same_boxes"] = all(
                    results[name][key] == baseline[key]
                    for key in ("left", "right", "full")
                )
            results["page"] = page_index + 1
            rows.append(results)
    finally:
        document.close()
    return rows


# ===================================================================== 输出
def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for cell in row:
            if cell is None:
                cells.append("-")
            elif isinstance(cell, float):
                cells.append("inf" if math.isinf(cell) else f"{cell:.1f}")
            else:
                cells.append(str(cell))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def section(title: str) -> None:
    print(f"\n## {title}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path, default=None,
                        help="任务目录（默认自动找本机素材最多的任务）")
    parser.add_argument("--pdf", type=Path, default=None,
                        help="真实链路/检测一致性用的 PDF（默认取任务目录里的第一个）")
    parser.add_argument("--samples", type=int, default=4, help="每类抽样张数")
    parser.add_argument("--out", type=Path, default=None, help="产物目录")
    parser.add_argument("--skip-memory", action="store_true", help="跳过内存探针")
    parser.add_argument("--skip-yolo", action="store_true", help="跳过 YOLO 检测一致性")
    parser.add_argument("--skip-integration", action="store_true", help="跳过真实提取链路")
    parser.add_argument("--mem-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--kind", default="pil", help=argparse.SUPPRESS)
    parser.add_argument("--path", default="", help=argparse.SUPPRESS)
    parser.add_argument("--loops", type=int, default=5, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.mem_worker:
        mem_worker(args.kind, Path(args.path), args.loops)
        return 0

    task = args.task or find_task_dir()
    if task is None or not task.is_dir():
        print("❌ 找不到任务素材目录（可用 --task 指定）")
        return 2
    out_root = args.out or temp_dir("webp_probe_")
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"任务素材：{task}")
    print(f"产物目录：{out_root}")

    extract_files, extract_count, extract_bytes = stage_files(task, "extract", args.samples)
    detect_files, detect_count, detect_bytes = stage_files(task, "detect", args.samples)
    rembg_files, rembg_count, rembg_bytes = stage_files(task, "rembg", args.samples)
    print(f"抽样：extract {len(extract_files)}/{extract_count}、"
          f"detect {len(detect_files)}/{detect_count}、"
          f"rembg {len(rembg_files)}/{rembg_count}")

    results: dict[str, Any] = {
        "task": str(task),
        "samples": args.samples,
        "stage_totals": {
            "extract": {"count": extract_count, "bytes": extract_bytes},
            "detect": {"count": detect_count, "bytes": detect_bytes},
            "rembg": {"count": rembg_count, "bytes": rembg_bytes},
        },
    }

    # ---- 1. 提取页编码矩阵 ------------------------------------------------
    extract_variants = [
        ("jpeg_q95（现状）", lambda rgb, path: save_jpeg(rgb, path, 95), "jpg"),
        ("jpeg_q90", lambda rgb, path: save_jpeg(rgb, path, 90), "jpg"),
        ("webp_q95（PIL）", lambda rgb, path: save_webp_pil(rgb, path, quality=95), "webp"),
        ("webp_q90（PIL）", lambda rgb, path: save_webp_pil(rgb, path, quality=90), "webp"),
        ("webp_q80（PIL）", lambda rgb, path: save_webp_pil(rgb, path, quality=80), "webp"),
        ("webp_q90（cv2）", lambda rgb, path: save_webp_cv2(rgb, path, 90), "webp"),
        ("webp_lossless", lambda rgb, path: save_webp_pil(rgb, path, lossless=True), "webp"),
        ("png_l6（对照）", lambda rgb, path: save_png(rgb, path, 6), "png"),
    ]
    extract_images = [load_rgb(path) for path in extract_files]
    extract_refs = [path.stat().st_size for path in extract_files]
    extract_rows = bench_rgb(
        extract_images, extract_variants, out_root, "extract",
        references=extract_refs,
    ) if extract_images else []
    results["extract"] = extract_rows

    section("1. 提取页编码（RGB 扫描页）")
    print(md_table(
        ["变体", "KB/页", "编码 ms", "解码 ms", "PSNR dB", "SSIM"],
        [[row["variant"], row["kb"], row["encode_ms"], row["decode_ms"],
          row["psnr"], row["ssim"]] for row in extract_rows],
    ))

    # ---- 2. 检测提交裁图 --------------------------------------------------
    detect_variants = [
        ("png_compact（现状）", lambda rgb, path: save_png_compact(rgb, path), "png"),
        ("webp_lossless", lambda rgb, path: save_webp_pil(rgb, path, lossless=True), "webp"),
        ("webp_q95（PIL）", lambda rgb, path: save_webp_pil(rgb, path, quality=95), "webp"),
        ("webp_q90（PIL）", lambda rgb, path: save_webp_pil(rgb, path, quality=90), "webp"),
        ("webp_q80（PIL）", lambda rgb, path: save_webp_pil(rgb, path, quality=80), "webp"),
        ("webp_q90（cv2）", lambda rgb, path: save_webp_cv2(rgb, path, 90), "webp"),
        ("jpeg_q95", lambda rgb, path: save_jpeg(rgb, path, 95), "jpg"),
        ("png_l6（对照）", lambda rgb, path: save_png(rgb, path, 6), "png"),
    ]
    detect_images = [load_rgb(path) for path in detect_files]
    detect_refs = [path.stat().st_size for path in detect_files]
    detect_rows = bench_rgb(
        detect_images, detect_variants, out_root, "detect", with_binarize=True,
        references=detect_refs,
    ) if detect_images else []
    results["detect"] = detect_rows

    section("2. 检测提交裁图编码（RGB，体积大头）")
    print(md_table(
        ["变体", "KB/张", "编码 ms", "解码 ms", "PSNR dB", "SSIM",
         "去底色差异 %", "去底色产物 KB"],
        [[row["variant"], row["kb"], row["encode_ms"], row["decode_ms"],
          row["psnr"], row["ssim"],
          None if row["bin_diff"] is None else row["bin_diff"] * 100,
          row["bin_kb"]] for row in detect_rows],
    ))

    # ---- 3. 去底色产物（透明底） -----------------------------------------
    rembg_images = [load_rgba(path) for path in rembg_files]
    rembg_refs = [path.stat().st_size for path in rembg_files]
    rembg_rows = bench_rgba(
        rembg_images,
        [
            ("webp_lossless", lambda rgba, path: save_webp_rgba(rgba, path, lossless=True), "webp"),
            ("webp_q90", lambda rgba, path: save_webp_rgba(rgba, path, quality=90), "webp"),
            ("webp_q80", lambda rgba, path: save_webp_rgba(rgba, path, quality=80), "webp"),
            ("png_rgba_l6（对照）", lambda rgba, path: save_png_rgba(rgba, path, 6), "png"),
        ],
        out_root,
        references=rembg_refs,
    ) if rembg_images else []
    current_rembg_kb = median(kb(path.stat().st_size) for path in rembg_files) if rembg_files else None
    results["rembg"] = {"rows": rembg_rows, "current_kb": current_rembg_kb}

    section("3. 去底色产物（白底透明，1 位调色板 PNG 现状）")
    print(f"现状 PNG 实测量：{current_rembg_kb:.1f} KB/张")
    print(md_table(
        ["变体", "KB/张", "编码 ms", "解码 ms", "alpha 逐位一致 %", "白底合成 PSNR"],
        [[row["variant"], row["kb"], row["encode_ms"], row["decode_ms"],
          row["alpha_exact"] * 100, row["psnr"]] for row in rembg_rows],
    ))

    # ---- 4. Qt 渲染与解码矩阵 -------------------------------------------
    section("4. Qt 渲染矩阵（整幅 + 256px 缩放解码）")
    if extract_rows and extract_images:
        original = extract_images[0]
        qimage_rows = []
        for row in extract_rows:
            if not row["paths"]:
                continue
            path = Path(row["paths"][0])
            full_image, full_ms = qt_read(path)
            scaled_image, scaled_ms = qt_read(path, edge=256)
            full_rgb = qimage_to_rgb(full_image)
            qimage_rows.append({
                "variant": row["variant"],
                "full_ok": full_rgb is not None,
                "full_size": list(full_image.size().toTuple())
                if not full_image.isNull() else None,
                "full_ms": full_ms,
                "full_psnr": psnr(original, full_rgb) if (
                    full_rgb is not None and full_rgb.shape == original.shape) else None,
                "scaled_ok": not scaled_image.isNull(),
                "scaled_size": list(scaled_image.size().toTuple())
                if not scaled_image.isNull() else None,
                "scaled_ms": scaled_ms,
            })
        results["qt"] = qimage_rows
        print(md_table(
            ["变体", "整幅可读", "尺寸", "整幅 ms", "整幅 PSNR",
             "256px 可读", "缩放尺寸", "缩放 ms"],
            [[row["variant"], row["full_ok"], row["full_size"], row["full_ms"],
              row["full_psnr"], row["scaled_ok"], row["scaled_size"],
              row["scaled_ms"]] for row in qimage_rows],
        ))

    # ---- 5. 内存峰值 ------------------------------------------------------
    section("5. 内存峰值（每组合独立子进程，5 次解码）")
    memory_rows: list[dict] = []
    if not args.skip_memory and extract_rows:
        interesting = ("jpeg_q95（现状）", "webp_q90（PIL）", "webp_lossless", "png_l6（对照）")
        for row in extract_rows:
            if row["variant"] not in interesting or not row["paths"]:
                continue
            path = Path(row["paths"][0])
            for kind in ("pil", "cv2", "qt_full", "qt_scaled"):
                payload = run_mem(kind, path, loops=5)
                payload["variant"] = row["variant"]
                memory_rows.append(payload)
        results["memory"] = memory_rows
        print(md_table(
            ["变体", "解码", "峰值增量 MB", "峰值 MB", "中位耗时 ms"],
            [[row["variant"], row["kind"], row.get("delta_mb"),
              row.get("peak_mb"), row.get("median_ms")] for row in memory_rows],
        ))

    # ---- 6. 真实提取链路 --------------------------------------------------
    pdf = args.pdf
    if pdf is None:
        pdfs = sorted(task.glob("*.pdf"))
        pdf = pdfs[0] if pdfs else None
    integration_rows: list[dict] = []
    if pdf and pdf.is_file() and not args.skip_integration:
        section("6. 真实 PDF 提取链路（extract_single_page）")
        import pymupdf as fitz

        document = fitz.open(str(pdf))
        page_count = document.page_count
        document.close()
        pages = pick_evenly(list(range(page_count)), min(3, page_count))
        integration_rows = run_integration(pdf, pages, out_root / "integration")
        results["integration"] = integration_rows
        table = []
        for row in integration_rows:
            jpg = row["jpg"]
            webp = row["webp"]
            checks = row.get("checks") or {}
            table.append([
                row["page"],
                kb(jpg.get("bytes") or 0), jpg.get("elapsed_ms"),
                kb(webp.get("bytes") or 0), webp.get("elapsed_ms"),
                checks.get("pil_ok"), checks.get("cv2_ok"), checks.get("qt_ok"),
                checks.get("qt_scaled_ok"),
                row.get("psnr_webp_vs_jpg"),
                kb(row.get("webp_q90_bytes") or 0),
            ])
        print(md_table(
            ["页", "jpg KB", "jpg ms", "webp KB", "webp ms",
             "PIL", "cv2", "Qt", "Qt 缩放", "webp↔jpg PSNR", "webp q90 KB"],
            table,
        ))
        print("\n代码缺口（webp 产物）：")
        for row in integration_rows:
            checks = row.get("checks") or {}
            print(f"- 第 {row['page']} 页：collect_image_files="
                  f"{checks.get('collect_images')}、"
                  f"print 目录扫描={checks.get('print_collect')}、"
                  f"_thumb_from_page_image 字节={checks.get('page_thumb_bytes')}")

    # ---- 7. YOLO 检测一致性 ----------------------------------------------
    yolo_rows: list[dict] = []
    if pdf and pdf.is_file() and not args.skip_yolo:
        section("7. YOLO 检测一致性（jpg q95 vs webp q90 / 无损）")
        import pymupdf as fitz

        document = fitz.open(str(pdf))
        page_count = document.page_count
        document.close()
        pages = pick_evenly(list(range(page_count)), min(3, page_count))
        yolo_rows = run_yolo(pdf, pages, out_root / "yolo_run")
        results["yolo"] = yolo_rows
        table = []
        for row in yolo_rows:
            for name in ("jpg_q95", "webp_q90", "webp_lossless"):
                item = row[name]
                table.append([
                    row["page"], name, kb(item["bytes"]),
                    item["decode_ms"], item["detect_ms"],
                    item.get("same_boxes", "-"),
                    f"{item['left']}/{item['right']}/{item['full']}",
                ])
        print(md_table(
            ["页", "格式", "KB", "cv2 解码 ms", "检测 ms", "框与 jpg 相同", "左/右/整幅"],
            table,
        ))

    # ---- 8. 体积投影 ------------------------------------------------------
    section("8. 各阶段体积投影（逐图比值 × 现状总量）")
    projection = []
    for name, rows, count, current_bytes in (
        ("extract", extract_rows, extract_count, extract_bytes),
        ("detect", detect_rows, detect_count, detect_bytes),
    ):
        current_mb = current_bytes / MB
        projection.append([name, "现状", f"{current_mb:.1f}", "1.00×"])
        for row in rows:
            if row["variant"].startswith(("jpeg_q95（现状）", "png_compact（现状）")):
                continue
            # ⚠️ 用逐图比值（本变体字节 / 该页现状文件字节）外推，而不是
            #    「抽样均值 × 张数」：抽样页可能恰好比全量均值大/小很多，
            #    均值外推会把结论带偏（任务 0021 的 extract 就是这样）。
            ratio = row.get("ratio")
            if not ratio:
                continue
            projected = current_mb * float(ratio)
            projection.append([
                name, row["variant"], f"{projected:.1f}",
                f"{ratio:.2f}×" if current_mb else "-",
            ])
    if current_rembg_kb is not None:
        current_mb = rembg_bytes / MB
        projection.append(["rembg", "现状 PNG", f"{current_mb:.1f}", "1.00×"])
        for row in rembg_rows:
            ratio = row.get("ratio")
            if not ratio:
                continue
            projected = current_mb * float(ratio)
            projection.append([
                "rembg", row["variant"], f"{projected:.1f}", f"{ratio:.2f}×",
            ])
    results["projection"] = projection
    print(md_table(["阶段", "变体", "全量 MB", "相对现状"], projection))

    payload_path = out_root / "results.json"
    payload_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n结果 JSON：{payload_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
