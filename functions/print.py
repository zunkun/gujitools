"""
图片目录 → PDF：纸张/方向/页边距、标题与页码、双页左右标注。

本模块同时被 CLI（``guji run print``）与 GUI 的 print 阶段复用。页序完全由
数据层决定：GUI 把列表顺序作为 ``files`` 清单传进来，这里照单执行，不再解析
文件名；CLI 独立用法（无清单）才回退按文件名排序。
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from fpdf import FPDF
from fpdf.syntax import DestinationXYZ
from PIL import Image

from functions.base import FunctionBase
from utils.path_utils import resolve_final_output_dir
from utils.pdf_utils import (
    parse_margins,
    parse_color,
    register_fonts,
    draw_vertical_text,
    DEFAULT_PAGE_MARGINS,
    POINTS_PER_MM,
)
from utils.string_utils import num_to_chinese
from utils.sort_utils import pdf_custom_sort_key

# 嵌入 PDF 前把超大扫描图缩放到的打印分辨率（仅缩小、不放大）。
# 300DPI 对古籍扫描足够清晰，同时避免 fpdf 对数千像素原图逐页 zlib 压缩。
MM_PER_INCH = 25.4
PRINT_IMAGE_DPI = 300


def _get_pdf_format(paper_size):
    """将纸张配置转换为毫米尺寸，避免依赖 FPDF 的格式表。"""
    formats = {
        "a3": (297, 420),
        "a4": (210, 297),
        "a5": (148, 210),
        "b5": (176, 250),
    }
    if not isinstance(paper_size, str):
        raise ValueError("paper_size 仅支持 A3、A4、A5、B5")
    format_name = paper_size.strip().lower()
    if format_name not in formats:
        raise ValueError(f"paper_size 仅支持 A3、A4、A5、B5，当前={paper_size}")
    return formats[format_name]


def _image_name_parts(path):
    """解析数字页名，返回 (页名数字, side)；side 可能为空。"""
    name = os.path.splitext(os.path.basename(path))[0].lower()
    match = re.fullmatch(r"(\d+)(?:[_-](l|r))?", name)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2)


def _resolve_title_nodes(image_files, title_switch_nodes):
    """将配置中的 [页名, 标题, side] 解析为排序后图片的序号。

    ``页名`` 为**原始页码**（extract 里的数字页号，如 ``5``、``5-r`` 的
    ``5``），不是列表下标——用户填「15」时想的是原书第 15 页，即使该页
    被拖到列表别处，标题切换仍要跟着这一页走。因此这里按**同名**回查
    图片在最终清单中的下标，与页序是否等于文件名序无关。
    """
    resolved = {}
    for node in title_switch_nodes:
        if len(node) < 2:
            continue
        anchor_spec = str(node[0]).strip()
        title = node[1]
        requested_side = str(node[2]).lower() if len(node) > 2 else "left"
        # 页名支持 <页号> / <页号>-l / <页号>-r；带侧别时只认该侧
        page, node_side = _image_name_parts(anchor_spec)
        if page is None and anchor_spec.isdigit():
            page, node_side = int(anchor_spec), None
        if page is None:
            continue
        candidates = []
        for index, path in enumerate(image_files):
            file_page, file_side = _image_name_parts(path)
            if file_page != page:
                continue
            if node_side and file_side != node_side:
                continue
            candidates.append((index, file_side))
        if not candidates:
            continue
        if requested_side in ("left", "right"):
            matching = [
                index for index, side in candidates if side == requested_side[0]
            ]
            if not matching:
                matching = [index for index, side in candidates if side is None]
            anchor = matching[0] if matching else candidates[0][0]
        else:
            anchor = candidates[0][0]
        resolved[anchor] = (title, requested_side)
    return sorted(resolved.items())


def _collect_image_files(input_dir: Path, files: Optional[List[str]] = None) -> List[str]:
    """收集待打印图片，返回**按最终页序排列**的路径列表。

    页序规则（二选一）：
    - ``files`` 非空：直接采用该清单顺序（GUI 第四步的列表顺序，即
      ``print.json`` 的 pages 数组序）。**不再解析文件名**——文件名只是
      标识，顺序完全由数据层决定，拖拽重排无需改动任何物理文件。
    - ``files`` 为空：退回 CLI 独立用法——扫描目录并按
      ``pdf_custom_sort_key``（cover/menu 优先、同编号 r→l、数字自然序）
      推导顺序。

    清单中不存在的路径会被跳过，让「数据表里有记录但物理文件已删」的
    条目静默失效，而不是让整次打印失败。
    """
    if files:
        out = []
        for text in files:
            p = Path(text)
            if p.is_file():
                out.append(str(p))
        return out
    image_files = []
    for name in os.listdir(input_dir):
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
            image_files.append(os.path.join(str(input_dir), name))
    image_files.sort(key=pdf_custom_sort_key)
    return image_files


class PrintFunction(FunctionBase):
    """把图片目录合成 PDF 的命令实现。

    直接重写 ``execute()``：参数全部来自命令行 / YAML 配置块，实际排版由
    ``_generate_pdf`` 完成，不使用基类的并发图片处理引擎。
    """

    def __init__(self, command_args):
        """调用基类完成输入解析后，立即计算输出 PDF 路径。"""
        super().__init__(command_args)
        self._calc_output_path()

    def _calc_output_path(self):
        pdf_name = self.command_args.get("pdf_name", "output.pdf")
        if self.output_raw:
            out_dir = Path(self.output_raw)
            self.outpath = out_dir / pdf_name
        else:
            out_dir = resolve_final_output_dir(
                self.input, None, self.is_file, self.default_temp_name
            )
            self.outpath = out_dir / pdf_name
        self.outpath.parent.mkdir(parents=True, exist_ok=True)

    def execute(self) -> dict:
        """收集打印参数并委托 _generate_pdf 生成 PDF。

        从 command_args 读取纸张尺寸（默认 A4）、方向（默认 landscape）、
        页边距、标题与页码相关配置，以及 skip_pages（默认空列表）与
        workers（默认 4）。将参数透传给 _generate_pdf，返回其
        {"processed": N, "output": path} 结果字典。
        """
        input_dir = self.input
        output_pdf = self.outpath

        paper_size = self.command_args.get("paper_size", "A4")
        orient_map = {"landscape": "L", "l": "L", "portrait": "P", "p": "P"}
        orientation = orient_map.get(
            self.command_args.get("orientation", "landscape").lower(), "L"
        )

        margins = parse_margins(
            self.command_args.get("page_margins", DEFAULT_PAGE_MARGINS)
        )
        left_margins = parse_margins(self.command_args.get("left_page_margins"))
        right_margins = parse_margins(self.command_args.get("right_page_margins"))

        title_printing = self.command_args.get("title_printing", False)
        title_text = self.command_args.get("title_text", "") or ""
        title_font_size = self.command_args.get("title_font_size", 18)
        title_color = parse_color(self.command_args.get("title_color", "0,0,0"))
        title_position = self.command_args.get("title_position", "top")
        title_orientation = self.command_args.get("title_orientation", "vertical")
        title_switch_nodes = self.command_args.get("title_switch_nodes", []) or []

        page_number_printing = self.command_args.get("page_number_printing", False)
        page_number_start_page = self.command_args.get("page_number_start_page", 1)
        page_number_end_page = self.command_args.get("page_number_end_page", None)
        page_number_base = self.command_args.get("page_number_base", 0)
        page_number_font_size = self.command_args.get("page_number_font_size", 12)
        page_number_color = parse_color(
            self.command_args.get("page_number_color", "0,0,0")
        )
        page_number_position = self.command_args.get("page_number_position", "bottom")
        page_number_orientation = self.command_args.get(
            "page_number_orientation", "vertical"
        )

        skip_pages = self.command_args.get("skip_pages", [])
        if skip_pages is None:
            skip_pages = []
        elif isinstance(skip_pages, str):
            skip_pages = [p.strip() for p in skip_pages.split(",") if p.strip()]

        workers = self.command_args.get("workers", 4)

        # 有序文件清单（GUI 第四步的列表顺序）；为空时按目录扫描 + 文件名排序
        files = self.command_args.get("files") or []

        return self._generate_pdf(
            input_dir,
            output_pdf,
            paper_size=paper_size,
            orientation=orientation,
            margins=margins,
            left_margins=left_margins,
            right_margins=right_margins,
            title_printing=title_printing,
            title_text=title_text,
            title_font_size=title_font_size,
            title_color=title_color,
            title_position=title_position,
            title_orientation=title_orientation,
            title_switch_nodes=title_switch_nodes,
            page_number_printing=page_number_printing,
            page_number_start_page=page_number_start_page,
            page_number_end_page=page_number_end_page,
            page_number_base=page_number_base,
            page_number_font_size=page_number_font_size,
            page_number_color=page_number_color,
            page_number_position=page_number_position,
            page_number_orientation=page_number_orientation,
            skip_pages=skip_pages,
            workers=workers,
            files=files,
        )

    def _generate_pdf(
        self,
        input_dir: Path,
        output_pdf: Path,
        paper_size: str,
        orientation: str,
        margins: List[float],
        left_margins: Optional[List[float]],
        right_margins: Optional[List[float]],
        title_printing: bool,
        title_text: str,
        title_font_size: int,
        title_color: Tuple[int, int, int],
        title_position: str,
        title_orientation: str,
        title_switch_nodes: List,
        page_number_printing: bool,
        page_number_start_page: int,
        page_number_end_page: Optional[int],
        page_number_base: int,
        page_number_font_size: int,
        page_number_color: Tuple[int, int, int],
        page_number_position: str,
        page_number_orientation: str,
        skip_pages: List[str],
        workers: int,
        files: Optional[List[str]] = None,
    ) -> dict:
        if skip_pages is None:
            skip_pages = []
        if title_switch_nodes is None:
            title_switch_nodes = []
        if margins is None:
            margins = DEFAULT_PAGE_MARGINS

        print(f"输入目录: {input_dir}")
        print(f"输出 PDF: {output_pdf}")

        image_files = _collect_image_files(input_dir, files)
        total = len(image_files)
        if total == 0:
            print("未找到任何图片")
            return {"processed": 0, "output": str(output_pdf)}

        # skip_pages 按**最终清单序号**（1 起）匹配：拖拽重排后仍指向
        # 同一位置。兼容旧写法——纯数字串既可能是序号也可能是原始页码，
        # 这里优先按序号解释（第 N 页），与 GUI 表单的提示语一致。
        skip_indices: set[int] = set()
        for spec in skip_pages:
            text = str(spec).strip()
            if text.isdigit():
                skip_indices.add(int(text))
            else:
                # 带侧别的写法（如 "5-r"）：按同名回查清单下标
                page, side = _image_name_parts(text)
                if page is None:
                    continue
                for index, path in enumerate(image_files, start=1):
                    file_page, file_side = _image_name_parts(path)
                    if file_page == page and (side is None or file_side == side):
                        skip_indices.add(index)
                        break

        # 先按纸张/方向/边距算出页面可放置图片的实际显示尺寸，
        # 在加载阶段把超大扫描图缩放到打印 DPI，避免 fpdf 对数千像素原图
        # 逐页 zlib 压缩（163 页会长时间卡住并产生巨大 PDF）。
        pdf = FPDF(
            orientation=orientation,
            unit="mm",
            format=_get_pdf_format(paper_size),
        )
        page_w = pdf.w
        page_h = pdf.h
        text_margin = 8.0  # mm，与下方排版一致
        _mt, _mr, _mb, _ml = margins
        avail_w_mm = max(1.0, page_w - _ml - _mr - 2 * text_margin)
        avail_h_mm = max(1.0, page_h - _mt - _mb)
        max_w_px = int(avail_w_mm / MM_PER_INCH * PRINT_IMAGE_DPI)
        max_h_px = int(avail_h_mm / MM_PER_INCH * PRINT_IMAGE_DPI)

        page_data = [None] * total
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for i, path in enumerate(image_files):
                if (i + 1) in skip_indices:  # 序号从 1 起，与表单一致
                    page_data[i] = {
                        "idx": i,
                        "img": None,
                        "path": path,
                        "size": (0, 0),
                        "skip": True,
                    }
                    continue
                futures[
                    executor.submit(
                        self._load_image, i, path, max_w_px, max_h_px
                    )
                ] = i
            for future in as_completed(futures):
                res = future.result()
                if res:
                    page_data[res["idx"]] = res
                done = len([x for x in page_data if x is not None])
                print(f"\r图片加载进度: {done}/{total}", end="")
        print()

        font_name = register_fonts(pdf)

        # 将配置中的页名节点解析为排序后图片的序号，用于章节切换和书签。
        sorted_nodes = _resolve_title_nodes(image_files, title_switch_nodes)

        end_page = page_number_end_page if page_number_end_page is not None else total
        processed_count = 0

        # ---- 辅助函数：从起始标注页或章节节点开始按图片序号交替左右 ----
        def get_side_for_page(image_index):
            anchor_index = page_number_start_page - 1
            anchor_side = "left"
            for node_index, (_, node_side) in sorted_nodes:
                if anchor_index <= node_index <= image_index and node_side in (
                    "left",
                    "right",
                ):
                    anchor_index = node_index
                    anchor_side = node_side
            offset = image_index - anchor_index
            return (
                anchor_side
                if offset % 2 == 0
                else ("right" if anchor_side == "left" else "left")
            )

        for i, data in enumerate(page_data):
            if not data or data.get("skip"):
                continue

            img = data["img"]
            if img is None:
                continue
            w_img, h_img = data["size"]
            current_page = i + 1  # 物理页码（1-based）

            pdf.add_page()

            # 布局图片
            if left_margins is not None and right_margins is not None:
                if current_page % 2 == 1:
                    mt, mr, mb, ml = left_margins
                else:
                    mt, mr, mb, ml = right_margins
            else:
                mt, mr, mb, ml = margins

            # ---- 图片左右留出空白，防止文字覆盖（text_margin 已在预缩放时定义）----
            avail_w_raw = page_w - ml - mr
            avail_h = page_h - mt - mb
            avail_w_for_img = max(0, avail_w_raw - 2 * text_margin)
            scale = min(avail_w_for_img / w_img, avail_h / h_img)
            new_w, new_h = w_img * scale, h_img * scale
            x_img = ml + text_margin + (avail_w_for_img - new_w) / 2
            y_img = mt + (avail_h - new_h) / 2
            pdf.image(img, x=x_img, y=y_img, w=new_w, h=new_h)

            # 书签在章节节点对应的具体图片上创建。
            for node_index, (node_title, _) in sorted_nodes:
                if i == node_index:
                    pdf.start_section(node_title, level=0)
                    pdf._outline[-1].dest = DestinationXYZ(
                        page=pdf.page, top=pdf.h_pt, left=0
                    )
                    break

            # ----- 标题（与页码同步起始页）-----
            if title_printing and current_page >= page_number_start_page:
                # 计算当前标题：从 title_text 开始，取最后一个已到达的标题节点
                current_title = title_text
                for node_index, (node_title, _) in sorted_nodes:
                    if node_index <= i:
                        current_title = node_title

                if current_title:
                    char_height_mm = title_font_size / POINTS_PER_MM
                    side = get_side_for_page(i)
                    if side == "left":
                        x_pos = ml / 2.0
                    else:
                        x_pos = page_w - mr + 6

                    if title_position == "top":
                        y_start = mt + 2.0
                        direction = "up"
                    else:
                        total_h = len(current_title) * char_height_mm
                        y_start = page_h - mb - total_h - 2.0
                        direction = "up"

                    if title_orientation == "vertical":
                        draw_vertical_text(
                            pdf,
                            current_title,
                            x_pos,
                            y_start,
                            font_name,
                            title_font_size,
                            title_color,
                            direction=direction,
                        )
                    else:
                        pdf.set_font(font_name, "", title_font_size)
                        pdf.set_text_color(*title_color)
                        if title_position == "top":
                            y_text = y_start + char_height_mm
                        else:
                            y_text = y_start - char_height_mm
                        pdf.text(x_pos, y_text, current_title)

            # ----- 页码 -----
            if (
                page_number_printing
                and page_number_start_page <= current_page <= end_page
            ):
                actual_num = page_number_base + current_page  # 显示页码
                page_chinese = num_to_chinese(actual_num)
                page_text = f"第{page_chinese}頁"

                char_height_mm = page_number_font_size / POINTS_PER_MM
                side = get_side_for_page(i)
                if side == "left":
                    x_pos = ml / 2.0
                else:
                    x_pos = page_w - mr + 6

                if page_number_position == "bottom":
                    total_h = len(page_text) * char_height_mm
                    y_start = page_h - mb - total_h - 2.0
                    direction = "up"
                else:
                    y_start = mt + 2.0
                    direction = "up"

                if page_number_orientation == "vertical":
                    draw_vertical_text(
                        pdf,
                        page_text,
                        x_pos,
                        y_start,
                        font_name,
                        page_number_font_size,
                        page_number_color,
                        direction=direction,
                    )
                else:
                    pdf.set_font(font_name, "", page_number_font_size)
                    pdf.set_text_color(*page_number_color)
                    if page_number_position == "bottom":
                        y_text = y_start - char_height_mm
                    else:
                        y_text = y_start + char_height_mm
                    pdf.text(x_pos, y_text, page_text)

            processed_count += 1
            if processed_count % 10 == 0 or processed_count == total:
                print(f"\r写入进度: {processed_count}/{total}", end="")

        print(f"\nPDF 生成完成: {output_pdf}")
        pdf.output(str(output_pdf))
        return {"processed": processed_count, "output": str(output_pdf)}

    @staticmethod
    def _load_image(idx, path, max_w_px=0, max_h_px=0):
        try:
            img = Image.open(path)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            # 超过打印所需像素时等比缩小（只缩不放），宽高比不变，
            # 后续排版几何完全一致，但压缩速度与 PDF 体积大幅改善。
            w, h = img.size
            if (
                max_w_px > 0
                and max_h_px > 0
                and (w > max_w_px or h > max_h_px)
            ):
                scale = min(max_w_px / w, max_h_px / h)
                target = (
                    max(1, int(w * scale)),
                    max(1, int(h * scale)),
                )
                img = img.resize(target, Image.LANCZOS)
            return {"idx": idx, "img": img, "path": path, "size": img.size}
        except Exception as e:
            print(f"加载图片失败 {path}: {e}")
            return None
