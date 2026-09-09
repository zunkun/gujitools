# functions/print.py
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
    """将配置中的 [页名, 标题, side] 解析为排序后图片的序号。"""
    resolved = {}
    for node in title_switch_nodes:
        if len(node) < 2:
            continue
        page = int(node[0])
        title = node[1]
        requested_side = str(node[2]).lower() if len(node) > 2 else "left"
        candidates = [
            (index, _image_name_parts(path)[1])
            for index, path in enumerate(image_files)
            if _image_name_parts(path)[0] == page
        ]
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


class PrintFunction(FunctionBase):
    def __init__(self, command_args):
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
    ) -> dict:
        if skip_pages is None:
            skip_pages = []
        if title_switch_nodes is None:
            title_switch_nodes = []
        if margins is None:
            margins = DEFAULT_PAGE_MARGINS

        print(f"输入目录: {input_dir}")
        print(f"输出 PDF: {output_pdf}")

        image_files = []
        for f in os.listdir(input_dir):
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                image_files.append(os.path.join(input_dir, f))
        image_files.sort(key=pdf_custom_sort_key)
        total = len(image_files)
        if total == 0:
            print("未找到任何图片")
            return {"processed": 0, "output": str(output_pdf)}

        skip_set = set(skip_pages)
        page_data = [None] * total
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for i, path in enumerate(image_files):
                fname = os.path.basename(path)
                name_no_ext = os.path.splitext(fname)[0]
                if name_no_ext in skip_set:
                    page_data[i] = {
                        "idx": i,
                        "img": None,
                        "path": path,
                        "size": (0, 0),
                        "skip": True,
                    }
                    continue
                futures[executor.submit(self._load_image, i, path)] = i
            for future in as_completed(futures):
                res = future.result()
                if res:
                    page_data[res["idx"]] = res
                done = len([x for x in page_data if x is not None])
                print(f"\r图片加载进度: {done}/{total}", end="")
        print()

        pdf = FPDF(
            orientation=orientation,
            unit="mm",
            format=_get_pdf_format(paper_size),
        )
        page_w = pdf.w
        page_h = pdf.h
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

            # ---- 图片左右留出空白，防止文字覆盖 ----
            text_margin = 8.0  # mm
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
    def _load_image(idx, path):
        try:
            img = Image.open(path)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            return {"idx": idx, "img": img, "path": path, "size": img.size}
        except Exception as e:
            print(f"加载图片失败 {path}: {e}")
            return None
