"""
图片目录 → PDF：纸张/方向/页边距、标题与页码、双页左右标注。

本模块同时被 CLI（``guji run print``）与 GUI 的 print 阶段复用。页序完全由
数据层决定：GUI 把列表顺序作为 ``files`` 清单传进来，这里照单执行，不再解析
文件名；CLI 独立用法（无清单）才回退按文件名排序。
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from fpdf import FPDF
from fpdf.syntax import DestinationXYZ
from PIL import Image

from core.command_spec import PRINT_DEFAULTS
from functions.base import FunctionBase
from utils.color_utils import parse_color
from utils.margin_utils import DEFAULT_PAGE_MARGINS, normalize_margin
from utils.units import MM_PER_INCH
from utils.page_layout import (
    PrintTextSpec,
    image_name_parts,
    paper_size_mm,
    plan_print_page,
    resolve_title_nodes,
    sides_for_pages,
    text_insets,
    TEXT_MARGIN_MM,
)
from utils.path_utils import resolve_final_output_dir
from utils.pdf_draw import (
    build_font_chain, draw_horizontal_text, draw_vertical_text,
)
from utils.sort_utils import pdf_custom_sort_key

# 嵌入 PDF 前把超大扫描图缩放到的打印分辨率（仅缩小、不放大）。
# 300DPI 对古籍扫描足够清晰，同时避免 fpdf 对数千像素原图逐页 zlib 压缩。
PRINT_IMAGE_DPI = 300


def _normalize_page_rects(raw) -> dict:
    """把逐图坐标覆盖的页号键归一为 int。

    ⚠️ 这条归一不能省：GUI 把 ``{1: [x,y,w,h]}`` 写进运行配置，而运行配置
    要落盘成 JSON（``write_json``）——**JSON 对象的键只能是字符串**——
    子进程读回来就成了 ``{"1": [...]}``。若仍用 int 查表（``get(i + 1)``）
    永远查不到，坐标覆盖静默失效，PDF 依旧按 page_margins 自动排版：
    表现为「预览里拖好了位置和大小，生成的 PDF 却还是原来那样」。

    同时兼容 CLI/模板里写成字符串键（``page_rects: {"1": [...]}``）的用法。
    解析不了的键直接丢弃（对应页回退自动排版）。
    """
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            out[int(key)] = value
        except (TypeError, ValueError):
            continue
    return out


def _draw_plan_text(pdf, spec: PrintTextSpec, font_name: str, chain=None) -> None:
    """把 `plan_print_page` 算好的一段文字画到当前页。

    竖排走 `draw_vertical_text`（逐字下移），横排用 fpdf 的 `text` ——
    横排的基线在 `baseline_mm`（竖排不需要，逐字用 `y_start_mm`）。

    ``chain`` 是 `utils.pdf_draw.FontChain`：给出时**逐字挑选字体**，主字体
    缺这个字的字形就顺位降级（古籍标题里的异体字因此落到宋体-ExtB 这类补字
    字体上，而不是画出空白）。
    """
    if spec.vertical:
        draw_vertical_text(
            pdf,
            spec.text,
            spec.x_mm,
            spec.y_start_mm,
            font_name,
            spec.font_size_pt,
            spec.color,
            direction=spec.direction,
            chain=chain,
        )
        return
    y_text = spec.y_start_mm if spec.baseline_mm is None else spec.baseline_mm
    if chain is not None:
        draw_horizontal_text(
            pdf,
            spec.text,
            spec.x_mm,
            y_text,
            font_name,
            spec.font_size_pt,
            spec.color,
            chain=chain,
        )
        return
    pdf.set_font(font_name, "", spec.font_size_pt)
    pdf.set_text_color(*spec.color)
    pdf.text(spec.x_mm, y_text, spec.text)


def _get_pdf_format(paper_size):
    """将纸张配置转换为毫米尺寸，避免依赖 FPDF 的格式表。

    几何真源已搬到 ``utils.page_layout.paper_size_mm``（第四步的「打印
    效果预览」与这里共用同一份纸张表），本函数保留为兼容入口。
    """
    return paper_size_mm(paper_size)


def _resolve_title_nodes(image_files, title_switch_nodes):
    """（兼容入口）章节节点解析，规则见 ``utils.page_layout``。

    ``页名`` 为**原始页码**（如 ``5`` / ``5-r`` 的 ``5``），不是列表下标，
    因此规则里按同名回查图片在最终清单中的下标。
    """
    return resolve_title_nodes(image_files, title_switch_nodes)


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

    def __init__(self, command_args, reporter=None):
        """调用基类完成输入解析后，立即计算输出 PDF 路径。"""
        super().__init__(command_args, reporter)
        self._calc_output_path()

    def _calc_output_path(self):
        """计算最终 PDF 路径。

        注意：不能依赖 `get("pdf_name", "output.pdf")` 的兜底——CommandArgs
        总会注入 pdf_name 键（默认值为 None），键存在时 dict.get 的默认值
        不生效，结果 pdf_name 为 None，`out_dir / None` 直接抛 TypeError。
        因此此处显式判空后再取名。
        """
        pdf_name = self.command_args.get("pdf_name") or "output.pdf"
        if self.output_raw:
            out_dir = Path(self.output_raw)
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

        # 第三步 crop/rembg 的 border 级联：上游已设真实留白时，第四步通用
        # 边距默认回落为 0，避免「图片内留白 + 页面边距」双重留白。
        # GUI 在 runner 里把上游 border 作为 upstream_border 传进来；CLI 不传
        # （默认 None）→ 保持内置默认 20。用户显式给了 page_margins 时一律优先。
        from core.command_spec import effective_page_margin_default

        margin_default = effective_page_margin_default(
            self.command_args.get("upstream_border")
        )
        margins = normalize_margin(
            self.command_args.get("page_margins") or margin_default,
            default=margin_default,
        )
        # ⚠️ normalize_margin(None) 会回落默认 [20,20,20,20]，直接对左右页调用
        # 会让「未填左右页」变成「左右页都是默认 20」——于是通用页边距
        # 永远不生效（曾经的实际行为）。只在用户真的填了才解析。
        left_raw = self.command_args.get("left_page_margins")
        right_raw = self.command_args.get("right_page_margins")
        left_margins = (
            normalize_margin(left_raw, default=DEFAULT_PAGE_MARGINS)
            if left_raw not in (None, "")
            else None
        )
        right_margins = (
            normalize_margin(right_raw, default=DEFAULT_PAGE_MARGINS)
            if right_raw not in (None, "")
            else None
        )

        title_printing = self.command_args.get("title_printing", False)
        title_text = self.command_args.get("title_text", "") or ""
        # ⚠️ 兜底值一律取 PRINT_DEFAULTS，别写字面量：这里曾写着 18，
        # 而 CLI 默认已是 20——同一参数两套默认值，改一处漏一处。
        # 用 `or`（不是 get 的第二参数）：显式传 None 时兜底才生效。
        title_font_size = (
            self.command_args.get("title_font_size")
            or PRINT_DEFAULTS["title_font_size"]
        )
        # 字体：None / 空 = 自动（仿宋优先，缺字沿降级链顺延）。
        # 标题与页码各一个——古籍常见"书名用仿宋、页码用黑体"的搭配。
        title_font = self.command_args.get("title_font")
        page_number_font = self.command_args.get("page_number_font")
        title_color = parse_color(self.command_args.get("title_color", "0,0,0"))
        title_position = self.command_args.get("title_position", "top")
        title_orientation = self.command_args.get("title_orientation", "vertical")
        title_switch_nodes = self.command_args.get("title_switch_nodes", []) or []

        page_number_printing = self.command_args.get("page_number_printing", False)
        page_number_start_page = self.command_args.get("page_number_start_page", 1)
        page_number_end_page = self.command_args.get("page_number_end_page", None)
        page_number_base = self.command_args.get("page_number_base", 0)
        page_number_font_size = (
            self.command_args.get("page_number_font_size")
            or PRINT_DEFAULTS["page_number_font_size"]
        )
        page_number_color = parse_color(
            self.command_args.get("page_number_color", "0,0,0")
        )
        page_number_position = self.command_args.get("page_number_position", "bottom")
        page_number_orientation = self.command_args.get(
            "page_number_orientation", "vertical"
        )
        # 标题/页码「距纸张边界」的距离（mm，[上,右,下,左]）；None = 旧行为。
        # ⚠️ 与 page_margins 不同：这里 None 是**合法值**（表示没配置），
        # 不能走 parse_margins —— 它会把 None 回落成默认 [20,20,20,20]。
        title_margins = text_insets(self.command_args.get("title_margins"))
        page_number_margins = text_insets(
            self.command_args.get("page_number_margins")
        )

        skip_pages = self.command_args.get("skip_pages", [])
        if skip_pages is None:
            skip_pages = []
        elif isinstance(skip_pages, str):
            skip_pages = [p.strip() for p in skip_pages.split(",") if p.strip()]

        # 第四步「版面编辑器」逐图坐标覆盖：{页号(1-based): [x,y,w,h] mm}。
        # GUI 从 print.json 的 pages[].rect 收集后注入；给定页直接用其坐标作
        # 图片框，不走 page_margins 自动排版。消费处用 `or {}` 兜底空值。
        # ⚠️ 键必须归一：运行配置要过一遍 JSON，而 JSON 对象的键只能是
        # 字符串——GUI 写的 {1: [...]} 到本进程手里是 {"1": [...]}，
        # 直接用 int 查表永远查不到，坐标覆盖会静默失效（PDF 回到自动排版）。
        page_rects = _normalize_page_rects(
            self.command_args.get("page_rects")
        )

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
            title_margins=title_margins,
            page_number_margins=page_number_margins,
            skip_pages=skip_pages,
            workers=workers,
            page_rects=page_rects,
            files=files,
            title_font=title_font,
            page_number_font=page_number_font,
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
        page_rects: Optional[dict] = None,
        files: Optional[List[str]] = None,
        title_margins: Optional[List[float]] = None,
        page_number_margins: Optional[List[float]] = None,
        title_font: Optional[str] = None,
        page_number_font: Optional[str] = None,
    ) -> dict:
        if skip_pages is None:
            skip_pages = []
        if title_switch_nodes is None:
            title_switch_nodes = []
        if margins is None:
            margins = DEFAULT_PAGE_MARGINS
        # 与 execute() 侧同样归一（幂等）：本方法也供 CLI/测试直接调用，
        # 键可能是 YAML/JSON 里的字符串形态。
        page_rects = _normalize_page_rects(page_rects)
        if page_rects:
            print(f"采用版面编辑器坐标：{len(page_rects)} 页"
                  f"（第 {min(page_rects)}–{max(page_rects)} 页）")

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
                page, side = image_name_parts(text)
                if page is None:
                    continue
                for index, path in enumerate(image_files, start=1):
                    file_page, file_side = image_name_parts(path)
                    if file_page == page and (side is None or file_side == side):
                        skip_indices.add(index)
                        break

        # 先按纸张/方向/边距算出页面可放置图片的实际显示尺寸，
        # 在加载阶段把超大扫描图缩放到打印 DPI，避免 fpdf 对数千像素原图
        # 逐页 zlib 压缩（163 页会长时间卡住并产生巨大 PDF）。
        # 排版参数打包成一份 dict 交给 utils.page_layout —— 图片落点、标题
        # 与页码的位置**只在那儿算一次**，这里不再抄第二份公式（抄一份就
        # 意味着预览与成品迟早漂移）。
        plan_args = {
            "paper_size": paper_size,
            "orientation": orientation,
            "page_margins": list(margins),
            "left_page_margins": left_margins,
            "right_page_margins": right_margins,
            "title_printing": title_printing,
            "title_text": title_text,
            "title_font_size": title_font_size,
            "title_color": title_color,
            "title_position": title_position,
            "title_orientation": title_orientation,
            "title_switch_nodes": title_switch_nodes,
            "page_number_printing": page_number_printing,
            "page_number_start_page": page_number_start_page,
            "page_number_end_page": page_number_end_page,
            "page_number_base": page_number_base,
            "page_number_font_size": page_number_font_size,
            "page_number_color": page_number_color,
            "page_number_position": page_number_position,
            "page_number_orientation": page_number_orientation,
            "title_margins": title_margins,
            "page_number_margins": page_number_margins,
            "skip_pages": skip_pages,
            # ⚠️ 下面五个键**必须**转进来：`plan_print_page` 靠它们决定
            # 页码文本（样式/前后缀）与 PrintTextSpec.font（标题/页码字体）。
            # 漏掉字体键的后果最隐蔽——PDF 侧另按 command_args 建链，用的
            # 是用户选的字体；而预览只读 spec.font，取不到就退回自动，
            # 于是「预览一种字体、成品另一种」。
            "title_font": title_font,
            "page_number_font": page_number_font,
            "page_number_format": self.command_args.get("page_number_format"),
            "page_number_prefix": self.command_args.get("page_number_prefix"),
            "page_number_suffix": self.command_args.get("page_number_suffix"),
        }

        pdf = FPDF(
            orientation=orientation,
            unit="mm",
            format=_get_pdf_format(paper_size),
        )
        page_w = pdf.w
        page_h = pdf.h
        # 图片左右固定留白（与预览同一份：utils.page_layout.TEXT_MARGIN_MM）。
        # 「距页边」不再收窄图片——用户设的距离只决定文字画在哪儿。
        text_margin = TEXT_MARGIN_MM
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

        # ----- 字体链：标题与页码各一条 -----
        # 用户可分别指定字体（title_font / page_number_font），未指定则按
        # 仿宋 → 宋体 → 微软雅黑 → 黑体 → 其它 的优先级自动选。
        # ⚠️ 建链时传入待排文字，只为**实际用到的**字体注册：古籍标题里的
        # 异体字会顺位落到宋体-ExtB 这类补字字体，常用字仍是仿宋，而 PDF
        # 里不会白白多嵌十几个字体子集。
        title_texts = [title_text] + [
            str(node[1]) for node in title_switch_nodes if len(node) >= 2
        ]
        title_chain = build_font_chain(pdf, texts=title_texts, preferred=title_font)
        # 页码是数字（ASCII），任何中文字体都有字形；仍建链是为了尊重
        # 用户"页码用另一种字体"的选择。
        number_chain = build_font_chain(
            pdf, texts=["0123456789"], preferred=page_number_font
        )

        # 将配置中的页名节点解析为排序后图片的序号，用于章节切换和书签。
        sorted_nodes = _resolve_title_nodes(image_files, title_switch_nodes)

        processed_count = 0

        # ---- 逐页左右侧：从起始标注页或章节节点开始按图片序号交替 ----
        # 规则在 utils.page_layout.sides_for_pages（预览与 PDF 同一份）
        sides = sides_for_pages(total, sorted_nodes, page_number_start_page)

        for i, data in enumerate(page_data):
            if not data or data.get("skip"):
                continue

            img = data["img"]
            if img is None:
                continue
            w_img, h_img = data["size"]

            pdf.add_page()

            # ---- 布局：几何全部来自 utils.page_layout（预览与 PDF 同一份）----
            # page_rects 由 GUI 从 print.json pages[].rect 收集：给定页直接用
            # 其坐标作图片框（所见即所得），否则走 page_margins 自动排版。
            image_rect = page_rects.get(i + 1)
            plan = plan_print_page(
                (w_img, h_img), plan_args, i, total,
                sides=sides, sorted_nodes=sorted_nodes,
                image_name=Path(image_files[i]).stem,
                image_rect=image_rect,
            )
            x_img, y_img, new_w, new_h = plan.image
            pdf.image(img, x=x_img, y=y_img, w=new_w, h=new_h)

            # 书签在章节节点对应的具体图片上创建。
            for node_index, (node_title, _) in sorted_nodes:
                if i == node_index:
                    pdf.start_section(node_title, level=0)
                    pdf._outline[-1].dest = DestinationXYZ(
                        page=pdf.page, top=pdf.h_pt, left=0
                    )
                    break

            # ----- 标题（与页码同步起始页；内容与几何都在 plan 里）-----
            if plan.title is not None:
                _draw_plan_text(
                    pdf, plan.title, title_chain.primary, chain=title_chain
                )

            # ----- 页码 -----
            if plan.page_number is not None:
                _draw_plan_text(
                    pdf, plan.page_number, number_chain.primary, chain=number_chain
                )

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
