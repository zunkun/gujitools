"""
File: utils/pdf_utils.py
PDF 页面提取工具：将 PDF 每页渲染为图片并保存。

此模块是 `extract` 功能的核心实现层，负责：

1. **页码解析** (`parse_pages` / `validate_page_range`)
   支持两种页码选择方式：逗号分隔 + 范围字符串（如 "1,3-5,7"）或 start/end 整数对。

2. **缩放计算** (`calculate_zoom`)
   根据页面宽度限制最大输出尺寸（6000px），避免内存溢出。

3. **批量渲染** (`process_page_batch` / `extract_pdf_optimized`)
   使用 PyMuPDF (fitz) 渲染页面，支持两种模式：
   - quick=True：优先提取 PDF 内嵌图片（快但可能低分辨率）；
   - quick=False：直接渲染页面为高质量图片。

4. **目录遍历** (`run_on_input_directory`)
   支持输入为单个 PDF 文件或包含多个 PDF 的目录。
   统一为每个 PDF 在输出根目录下创建以 PDF 文件名命名的子目录，并在其下创建 images 子目录存放图片。

依赖: PyMuPDF (pymupdf), Pillow (PIL)。
"""

import os
import io
import time
import math
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Union, Tuple
from unittest.mock import DEFAULT

DEFAULT_PAGE_MARGINS: List[float] = [20, 20, 20, 20]  # 上右下左 (mm)
POINTS_PER_MM = 72.0 / 25.4


def parse_pages(pages_str: str, total_pages: int) -> List[int]:
    """解析页码字符串为 0-based 页码列表。

    支持格式: "1,3-5,7" → [0, 2, 3, 4, 6]
    页码为 1-based，返回值转换为 0-based。

    参数:
        pages_str: 页码字符串（逗号分隔，支持范围）。
        total_pages: PDF 总页数（用于越界检查）。

    返回:
        排序后的 0-based 页码列表。

    异常:
        ValueError: 页码格式错误或超出范围。
    """
    if not pages_str:
        return list(range(total_pages))
    selected_pages = set()
    parts = pages_str.split(",")
    for part in parts:
        part = part.strip()
        if "-" in part:
            # 范围: "3-5" → 页 3,4,5 → 0-based: 2,3,4
            a, b = part.split("-")
            start = int(a) - 1
            end = int(b) - 1
            if start < 0 or end >= total_pages or start > end:
                raise ValueError(f"页码范围无效: {part} (总页数: {total_pages})")
            for p in range(start, end + 1):
                selected_pages.add(p)
        else:
            # 单页: "7" → 0-based: 6
            p = int(part) - 1
            if p < 0 or p >= total_pages:
                raise ValueError(f"页码 {part} 超出范围 (总页数: {total_pages})")
            selected_pages.add(p)
    return sorted(selected_pages)


def validate_page_range(
    start: Optional[int], end: Optional[int], total_pages: int
) -> List[int]:
    """根据 start/end 整数对生成 0-based 页码列表。

    参数:
        start: 起始页（1-based），None 表示从第 1 页开始。
        end: 结束页（1-based），None 表示到最后一页。
        total_pages: PDF 总页数。

    返回:
        0-based 页码列表。
    """
    if start is None and end is None:
        return list(range(total_pages))
    start_idx = start - 1 if start is not None else 0
    end_idx = end - 1 if end is not None else total_pages - 1
    if start_idx < 0:
        start_idx = 0
    if end_idx >= total_pages:
        end_idx = total_pages - 1
    if start_idx > end_idx:
        raise ValueError(f"起始页 {start_idx+1} 不能大于结束页 {end_idx+1}")
    return list(range(start_idx, end_idx + 1))


def calculate_zoom(page_width: float, requested_zoom: float = 1) -> float:
    """计算实际缩放因子，限制最大输出宽度为 6000px。

    参数:
        page_width: PDF 页面宽度（pt 单位，1pt ≈ 1/72 inch）。
        requested_zoom: 用户请求的缩放因子。

    返回:
        实际使用的缩放因子。
    """
    # 页面已足够宽时不再放大
    if page_width > 3000:
        return 1
    target_width = page_width * requested_zoom
    # 限制最大输出宽度，防止内存溢出
    if target_width > 6000:
        return max(1, 6000 // int(page_width))
    return requested_zoom


def process_page_batch(
    pdf_path: str,
    page_indices: List[int],
    out_dir: str,
    zoom: float,
    ext: str,
    quick: bool = False,
    progress: dict = None,
) -> List[bool]:
    """处理一批 PDF 页面，返回每页的成功状态。

    参数:
        pdf_path: PDF 文件路径。
        page_indices: 0-based 页码列表。
        out_dir: 输出目录。
        zoom: 缩放因子。
        ext: 输出格式（jpg/png/tiff）。
        quick: True=优先提取内嵌图片（zoom 按图片原始像素缩放），False=渲染页面。
        progress: 共享进度字典（含 lock, done, total），用于线程安全打印进度。

    返回:
        每页成功/失败的 bool 列表。
    """
    results = []
    try:
        try:
            import pymupdf as fitz
        except ImportError as e:
            raise RuntimeError(
                "依赖缺失: PyMuPDF 未安装。请运行: pip install PyMuPDF"
            ) from e
        try:
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(
                "依赖缺失: Pillow 未安装。请运行: pip install Pillow"
            ) from e

        doc = fitz.open(pdf_path)
        for page_idx in page_indices:
            try:
                page = doc.load_page(page_idx)
                page_rect = page.rect
                original_width = page_rect.width
                actual_zoom = calculate_zoom(original_width, zoom)
                page_start = time.time()

                if quick:
                    images = page.get_images(full=True)
                    if not images:
                        # 当前页面没有内嵌图片，降级整页渲染
                        mat = fitz.Matrix(actual_zoom, actual_zoom)
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        img_path = os.path.join(out_dir, f"{page_idx+1}.{ext}")
                        pix.save(img_path)
                    else:
                        for idx, img_info in enumerate(images):
                            xref = img_info[0]
                            img_dict = doc.extract_image(xref)
                            img_bytes = img_dict["image"]
                            # 载入原始图像
                            stream = io.BytesIO(img_bytes)
                            pil_img = Image.open(stream)

                            # 内嵌图缩放直接使用用户传入zoom
                            img_zoom = zoom
                            if not math.isclose(img_zoom, 1.0):
                                nw = int(pil_img.width * img_zoom)
                                nh = int(pil_img.height * img_zoom)
                                pil_img = pil_img.resize((nw, nh), Image.LANCZOS)

                            suffix = f"_{idx+1}" if len(images) > 1 else ""
                            img_path = os.path.join(
                                out_dir, f"{page_idx+1}{suffix}.{ext}"
                            )

                            # 根据目标格式保存
                            if ext.lower() == "jpg":
                                # JPG不支持透明通道
                                if pil_img.mode in ("RGBA", "P"):
                                    pil_img = pil_img.convert("RGB")
                                pil_img.save(img_path, "JPEG", quality=85)
                            else:
                                pil_img.save(img_path, ext.upper())

                else:
                    # 标准模式：渲染整页为高质量图片
                    mat = fitz.Matrix(actual_zoom, actual_zoom)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    fmt = "JPEG" if ext == "jpg" else "PNG"
                    save_kw = {"quality": 95, "subsampling": 0} if ext == "jpg" else {}
                    img_path = os.path.join(out_dir, f"{page_idx+1}.{ext}")
                    img.save(img_path, fmt, **save_kw)

                page_elapsed = time.time() - page_start
                results.append(True)
                if progress is not None:
                    # 线程安全更新进度计数器
                    with progress["lock"]:
                        progress["done"] += 1
                        done = progress["done"]
                        total = progress["total"]
                    print(
                        f"进度: {done}/{total} 页 - 第 {page_idx+1} 页 用时: {page_elapsed:.2f}s"
                    )
            except Exception as e:
                print(f"❌ 第 {page_idx+1} 页失败: {e}")
                results.append(False)
        doc.close()
        return results
    except Exception as e:
        print(f"❌ 处理批次失败: {e}")
        return [False] * len(page_indices)


def extract_pdf_optimized(
    pdf_path: str,
    out_dir: str,
    zoom: float = 2,
    ext: str = "jpg",
    workers: int = 4,
    quick: bool = False,
    pages: str = None,
    start: int = None,
    end: int = None,
    batch_size: int = 4,
    clean: bool = False,
) -> bool:
    """提取 PDF 页面为图片，支持多线程批次处理。

    参数:
        pdf_path: PDF 文件路径。
        out_dir: 输出目录（此目录将存放该 PDF 的所有页面图片）。
        zoom: 缩放因子（整数，如 2 表示 2 倍分辨率）。
        ext: 输出格式 jpg/png/tiff。
        workers: 线程数。
        quick: True=快速模式（优先提取内嵌图片）。
        pages: 页码字符串（如 "1,3-5,7"），优先级高于 start/end。
        start: 起始页（1-based）。
        end: 结束页（1-based）。
        batch_size: 每批次处理的页数。
        clean: True=清空输出目录后重新提取。

    返回:
        True=处理完成（部分页面可能失败，查看日志），False=整体失败。
    """
    try:
        start_time = time.time()
        if not os.path.exists(pdf_path):
            print(f"❌ 错误: PDF文件不存在: {pdf_path}")
            return False
        try:
            import pymupdf as fitz
        except ImportError:
            return False

        doc = fitz.open(pdf_path)
        if clean and os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        total_pages = len(doc)

        # 确定要处理的页码列表
        if pages is not None:
            try:
                page_indices = parse_pages(pages, total_pages)
            except ValueError as e:
                doc.close()
                print(f"❌ 页面参数错误: {e}")
                return False
        elif start is not None or end is not None:
            try:
                page_indices = validate_page_range(start, end, total_pages)
            except ValueError as e:
                doc.close()
                print(f"❌ 页面范围错误: {e}")
                return False
        else:
            page_indices = list(range(total_pages))

        # 用首页宽度计算实际缩放因子
        first_page = doc.load_page(0)
        page_width = first_page.rect.width
        doc.close()
        actual_zoom = calculate_zoom(page_width, zoom)

        total_selected = len(page_indices)
        # 将页码列表切分为批次
        batches = [
            page_indices[i : i + batch_size]
            for i in range(0, total_selected, batch_size)
        ]
        print(f"\n📄 开始处理: {os.path.basename(pdf_path)}")
        print(f"📂 输出目录: {out_dir}")
        print(f"📏 总页数: {total_pages}")
        print(f"📄 处理页数: {total_selected}")
        print(f"🔧 实际 zoom: {actual_zoom}")

        # 线程安全的进度计数器
        progress = {"total": total_selected, "done": 0, "lock": threading.Lock()}

        # 多线程处理各批次
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    process_page_batch,
                    pdf_path,
                    batch,
                    out_dir,
                    zoom,
                    ext,
                    quick,
                    progress,
                )
                for batch in batches
            ]
            all_results = []
            for f in futures:
                all_results.extend(f.result())

        success_count = sum(all_results)
        elapsed_time = time.time() - start_time
        print(
            f"\n🎉 处理完成！ 成功: {success_count}/{total_selected} 页 用时: {elapsed_time:.2f} 秒"
        )
        return True
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def run_on_input_directory(
    input_path: str,
    out_root: str,
    zoom: float = 1,
    ext: str = "jpg",
    workers: int = 4,
    quick: bool = False,
    pages: str = None,
    start: int = None,
    end: int = None,
    batch_size: int = 4,
    clean: bool = False,
    subdir_name: str = "images",  # 新增参数，默认保持兼容
):
    """
    处理输入路径（文件或目录），对每个 PDF 在 out_root 下创建以其文件名命名的子目录，
    并在该子目录下创建 subdir_name 目录存放图片。

    参数:
        input_path: 输入路径（单个 PDF 文件或包含 PDF 的目录）。
        out_root: 输出根目录（所有 PDF 的子目录将创建在此目录下）。
        zoom, ext, workers, quick, pages, start, end, batch_size, clean:
            透传给 extract_pdf_optimized 的参数。
        subdir_name: 每个 PDF 子目录下存放图片的子目录名。
    """
    print(
        f"[debug] run_on_input_directory called with: {input_path}, out_root={out_root}, subdir_name={subdir_name}"
    )
    if not os.path.exists(input_path):
        print(f"❌ 错误: 路径不存在: {input_path}")
        return

    if os.path.isfile(input_path):
        pdfs = [input_path]
    else:
        pdfs = [
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if f.lower().endswith(".pdf")
        ]

    print(f"[debug] Found {len(pdfs)} pdf(s) to process")
    if not pdfs:
        print("❌ 未找到 PDF")
        return

    # 确保输出根目录存在
    os.makedirs(out_root, exist_ok=True)

    for pdf in sorted(pdfs):
        try:
            fname = os.path.basename(pdf)
            folder_name = os.path.splitext(fname)[0]
            # 使用 subdir_name 拼接最终输出目录
            out_dir = os.path.join(out_root, folder_name, subdir_name)
            print(f"[debug] processing {pdf} -> {out_dir}")
            extract_pdf_optimized(
                pdf,
                out_dir,
                zoom,
                ext,
                workers,
                quick,
                pages,
                start,
                end,
                batch_size,
                clean=clean,
            )
        except KeyboardInterrupt:
            print("\n⚠️  用户中断")
            raise
        except Exception as e:
            print(f"❌ 处理失败: {e}")


def parse_margins(val) -> Optional[List[float]]:
    """解析边距为 [上,右,下,左] (mm)"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return [float(val)] * 4
    if isinstance(val, list):
        if not val:
            return DEFAULT_PAGE_MARGINS
        if len(val) == 1:
            return [float(val[0])] * 4
        if len(val) == 2:
            tb, lr = float(val[0]), float(val[1])
            return [tb, lr, tb, lr]
        if len(val) >= 4:
            return [float(x) for x in val[:4]]
        return DEFAULT_PAGE_MARGINS
    if isinstance(val, str):
        parts = [float(x.strip()) for x in val.split(",") if x.strip()]
        if not parts:
            return DEFAULT_PAGE_MARGINS
        if len(parts) == 1:
            return [parts[0]] * 4
        if len(parts) == 2:
            return [parts[0], parts[1], parts[0], parts[1]]
        if len(parts) >= 4:
            return parts[:4]
    return DEFAULT_PAGE_MARGINS


def parse_color(color_str: Union[str, tuple]) -> Tuple[int, int, int]:
    """解析颜色 'r,g,b' 或 (r,g,b) 为整数元组"""
    if isinstance(color_str, (tuple, list)) and len(color_str) >= 3:
        return (int(color_str[0]), int(color_str[1]), int(color_str[2]))
    if isinstance(color_str, str):
        parts = [int(x.strip()) for x in color_str.split(",") if x.strip()]
        if len(parts) >= 3:
            return tuple(parts[:3])
    return (0, 0, 0)


def register_fonts(pdf):
    """尝试注册系统中文字体，返回第一个成功注册的字体名。"""
    font_paths = [
        r"C:\Windows\Fonts\fsgb2312.ttf",
        r"C:\Windows\Fonts\simfang.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\msyh.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            font_name = os.path.splitext(os.path.basename(path))[0]
            try:
                pdf.add_font(font_name, "", path)
                return font_name
            except Exception:
                continue
    return "Helvetica"


def draw_vertical_text(
    pdf, text, x, y_start, font_name, font_size, color, direction="down"
):
    """在PDF上绘制垂直文字（逐字上下排列）。"""
    r, g, b = color
    if isinstance(r, float) and r <= 1:
        r, g, b = int(r * 255), int(g * 255), int(b * 255)
    pdf.set_font(font_name, "", font_size)
    pdf.set_text_color(r, g, b)
    char_height_mm = font_size / POINTS_PER_MM  # 点数转毫米
    y = y_start
    for ch in text:
        pdf.text(x, y, ch)
        if direction == "down":
            y -= char_height_mm
        else:
            y += char_height_mm


def get_page_side_from_name(name_without_ext):
    """根据文件名末尾 '-l' 或 '-r' 判断左右页。"""
    lower = name_without_ext.lower()
    if lower.endswith("-l"):
        return "left"
    if lower.endswith("-r"):
        return "right"
    return None


def get_page_side_by_start(image_files, current_index, start_page, default_side="left"):
    """根据起始页的左右属性推断当前页是左还是右。"""
    if not (1 <= start_page <= len(image_files)):
        start_side = default_side
    else:
        start_name = os.path.splitext(os.path.basename(image_files[start_page - 1]))[0]
        start_side = get_page_side_from_name(start_name) or default_side
    offset = current_index - start_page
    if offset % 2 == 0:
        return start_side == "left"
    return start_side == "right"
