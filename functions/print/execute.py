# -*- coding: utf-8 -*-
"""`PrintFunction`：图片目录 → PDF 的执行核心。"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

from fpdf.syntax import DestinationXYZ

from core.command_spec import PRINT_DEFAULTS
from core.reporter import PROGRESS_TOTAL_EVENT
from functions.base import FunctionBase
from functions.print.constants import PRINT_IMAGE_DPI, PRINT_IMAGE_ZLIB_LEVEL
from functions.print.drawing import (
    _draw_plan_text,
    _get_pdf_format,
    _resolve_title_nodes,
)
from functions.print.files import _collect_image_files
from functions.print.image import _load_image
from functions.print.overrides import (
    _normalize_page_rects,
    _normalize_page_rotations,
    _rotate_pil,
)
from utils.color_utils import parse_color
from utils.margin_utils import DEFAULT_PAGE_MARGINS, normalize_margin
from utils.page_layout import (
    TEXT_MARGIN_MM,
    fit_rotated_rect,
    image_name_parts,
    plan_print_page,
    rotated_bbox_size,
    sides_for_pages,
    text_insets,
)
from utils.path_utils import resolve_final_output_dir
from utils.pdf_draw import build_font_chain
from utils.pdf_stream import PdfDocument, write_streaming
from utils.units import MM_PER_INCH


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
        assert self.outpath is not None
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
        assert output_pdf is not None

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
        assert margins is not None
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
        # 逐图旋转覆盖：{页号(1-based): 角度}（float，顺时针为正）。与
        # page_rects 同源，PDF 侧先按角度旋转位图，再贴进同一个框。
        page_rotations = _normalize_page_rotations(
            self.command_args.get("page_rotations")
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
            page_rotations=page_rotations,
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
        page_rotations: Optional[dict] = None,
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
        page_rotations = _normalize_page_rotations(page_rotations)
        if page_rotations:
            print(f"采用版面编辑器旋转：{len(page_rotations)} 页"
                  f"（第 {min(page_rotations)}–{max(page_rotations)} 页）")

        print(f"输入目录: {input_dir}")
        print(f"输出 PDF: {output_pdf}")

        image_files = _collect_image_files(input_dir, files)
        total = len(image_files)
        if total == 0:
            # ⚠️ 必须**报错**，不能静默返回 `{"processed": 0}`：曾出现
            # 「输入目录写错一层（`-i final` 而图在 `final/rembg`）」时命令
            # 以退出码 0 成功结束、既不产 PDF 也不报错，脚本完全发现不了
            # （2026-09-26 极限测试实测）。空输入意味着这次调用不可能完成，
            # 让 CLI 拿 FAILED 退出码、GUI 弹出原因。
            raise FileNotFoundError(
                f"未在 {input_dir} 找到任何图片"
                "（支持 jpg/jpeg/png 等；若图片在子目录里，请指向该子目录）"
            )

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

        # 用 PdfDocument 而不是 FPDF：它只多一件事——把 trailer 的 /ID 接到
        # 流式缓冲的增量摘要上（见 utils/pdf_stream.py）；不流式时行为与 FPDF 相同。
        pdf = PdfDocument(
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
        # ⚠️ 页边距可为负（2026-11-21）：负值只会把可用区算得更大（图更少被缩），
        #    `max(1.0, …)` 只兜"正边距过大把可用区挤成 0"那一种。
        avail_w_mm = max(1.0, page_w - _ml - _mr - 2 * text_margin)
        avail_h_mm = max(1.0, page_h - _mt - _mb)
        max_w_px = int(avail_w_mm / MM_PER_INCH * PRINT_IMAGE_DPI)
        max_h_px = int(avail_h_mm / MM_PER_INCH * PRINT_IMAGE_DPI)

        # ⚠️ 这里**不再**预先加载整本图片（老实现 `page_data = [None] * total`
        #    把每一页的位图都攒在内存里，真实 320 页的书峰值 2994MB、且随页数
        #    线性增长 → 2400 页会 OOM）。现在加载与写页在下面同一个循环里按序
        #    进行，写完一页立刻释放（见「加载要按序、限窗、写完即释放」）。

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
        # 页码建链要喂**真实页码文本**（2026-09-26 第二轮审计）：默认样式是
        # 「第X頁」这类纯中文，不含 ASCII 数字——按 "0123456789" 建链时，
        # 用户选了无 CJK 字形的页码字体（如 Arial）的话，「第/頁」在链里
        # 找不到支持者 → 渲染成空白/notdef，且无任何告警。采首尾两个页码
        # （含前后缀、前缀里可能有中文）覆盖实际会用到的字形。
        from utils.string_utils import format_page_number

        _pn_base = int(self.command_args.get("page_number_base") or 0)
        _pn_fmt = str(self.command_args.get("page_number_format") or "chinese")
        _pn_prefix = self.command_args.get("page_number_prefix")
        _pn_prefix = "" if _pn_prefix is None else str(_pn_prefix)
        _pn_suffix = self.command_args.get("page_number_suffix")
        _pn_suffix = "" if _pn_suffix is None else str(_pn_suffix)
        # 实际打印的编号是 base + 当前页（1-based），采首尾两页覆盖字形
        number_texts = [
            format_page_number(_pn_base + 1, _pn_fmt, _pn_prefix, _pn_suffix),
            format_page_number(_pn_base + max(1, total), _pn_fmt, _pn_prefix, _pn_suffix),
        ]
        number_chain = build_font_chain(
            pdf, texts=number_texts, preferred=page_number_font
        )

        # 将配置中的页名节点解析为排序后图片的序号，用于章节切换和书签。
        sorted_nodes = _resolve_title_nodes(image_files, title_switch_nodes)

        processed_count = 0
        # 进度分母 = 实际要写的页数（2026-09-26 第二轮审计）：total 含被
        # skip_pages 跳过的页，processed_count 最大只能到 total-跳过数，
        # 原先进度永远到不了 100%。
        _zero_img_warned = False
        total_written = max(0, total - len(skip_indices))

        # ---- 逐页左右侧：从起始标注页或章节节点开始按图片序号交替 ----
        # 规则在 utils.page_layout.sides_for_pages（预览与 PDF 同一份）
        sides = sides_for_pages(total, sorted_nodes, page_number_start_page)

        # 先报一次**总数**（还没有完成量）：界面立刻能把进度条上限设成
        # total_written，而不是停在启动时那个 0/1 的空条上干等（用户
        # 2026-10-24：「页面反馈少」）。协议细节见 core.reporter。
        self.reporter.event(PROGRESS_TOTAL_EVENT, total=total_written)

        # ⚠️ **加载要按序、限窗、写完即释放**（2026-09-26 极限测试实测）
        #    老实现把所有页 `executor.submit(...)` 一次性提上去、再等全部
        #    `page_data` 收齐才开始写 PDF：等于**整本书的图同时驻留内存**。
        #    真实 794MB/320 页的书（area=1 → 601 张）峰值 **2994MB**，而按页
        #    数线性增长——2400 页的书就是几十 GB，直接 OOM。
        #    现在只保留 `workers` 张在飞、按序号消费，写完立刻丢掉引用。
        executor = ThreadPoolExecutor(max_workers=workers)
        pending: dict[int, Future[dict | None]] = {}
        submit_cursor = 0
        # fpdf 的图片压缩级别是**模块级**设置（见 PRINT_IMAGE_ZLIB_LEVEL）：
        # 只在本轮的贴图循环里调低，结束时还原，别把副作用留给同进程的其它活儿。
        from fpdf.image_parsing import SETTINGS as _fpdf_image_settings

        _previous_zlib_level = _fpdf_image_settings.compression_level
        _fpdf_image_settings.compression_level = PRINT_IMAGE_ZLIB_LEVEL

        def _submit_until_window_full() -> None:
            """把待加载的页补到窗口上限（跳过 skip_pages 的页）。"""
            nonlocal submit_cursor
            while submit_cursor < total and len(pending) < max(1, workers):
                index = submit_cursor
                submit_cursor += 1
                if (index + 1) in skip_indices:
                    continue
                pending[index] = executor.submit(
                    self._load_image, index, image_files[index], max_w_px, max_h_px
                )

        try:
            for i in range(total):
                if (i + 1) in skip_indices:
                    continue
                _submit_until_window_full()
                future = pending.pop(i, None)
                data = future.result() if future is not None else None
                if not data or data.get("img") is None:
                    continue
                img = data["img"]
                # 逐图旋转：先转位图（直角无损转置、任意角度扩图），再按旋转后
                # 的外接框走同一份排版几何——与预览侧「先转 QImage 再 plan」同序。
                angle = page_rotations.get(i + 1) or 0.0
                source_size = img.size
                if angle:
                    img = _rotate_pil(img, angle)
                w_img, h_img = img.size
                if angle:
                    # 外接框尺寸按旋转前源图算（PIL 扩图会四舍五入差 1px，
                    # 用它会让 preview 与 PDF 的落点差一丝）。
                    w_img, h_img = rotated_bbox_size(
                        source_size[0], source_size[1], angle
                    )

                pdf.add_page()

                # ---- 布局：几何全部来自 utils.page_layout（预览与 PDF 同一份）----
                # page_rects 由 GUI 从 print.json pages[].rect 收集：给定页直接用
                # 其坐标作图片框（所见即所得），否则走 page_margins 自动排版。
                image_rect = page_rects.get(i + 1)
                if image_rect is not None and angle:
                    # 旋转后的图等比放进同一个用户框（不裁剪不拉伸），与预览/
                    # 画布共用 fit_rotated_rect。
                    image_rect = fit_rotated_rect(
                        image_rect, source_size, angle
                    )
                plan = plan_print_page(
                    (w_img, h_img), plan_args, i, total,
                    sides=sides, sorted_nodes=sorted_nodes,
                    image_name=Path(image_files[i]).stem,
                    image_rect=image_rect,
                )
                x_img, y_img, new_w, new_h = plan.image
                # ⚠️ 边距把可用区挤到 0 时 plan 会给出 0×0（2026-09-26 第二轮
                #    审计）：直接传给 fpdf2 会走它「w=h=0 → 按 72dpi 原尺寸」
                #    的另一条语义分支，页面上落一颗小斑点图还毫无提示。这里
                #    跳过贴图并告警（标题/页码照画，页不缺）。
                if new_w <= 0 or new_h <= 0:
                    if not _zero_img_warned:
                        print(
                            f"\n警告: 第 {i + 1} 页可排版区域为 0"
                            "（边距过大），该页仅保留标题/页码。"
                        )
                        _zero_img_warned = True
                    new_w = new_h = 0
                if new_w > 0 and new_h > 0:
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

                # 这一页的位图已经交给 fpdf，立刻释放（峰值内存不随页数增长）
                data["img"] = None
                del img, data
                processed_count += 1
                # 结构化进度：**整个 print 阶段进度条的唯一来源**（total = 实际写入
                # PDF 的页数，页面清单增删后自然跟着变）。合成阶段刻意不发进度，
                # 否则两条独立进度会交替驱动同一条进度条（见 print_stage 的说明）。
                #
                # ⚠️ **每页都发**（2026-10-24）：GUI 侧对进度事件有 200ms 合并窗口
                #    （见 runner._PROGRESS_UI_MS），逐页事件的代价可忽略；而原先
                #    每 10 页才发一次，50 页的书半分钟里进度条只跳 5 下，用户看到
                #    的就是「卡在那里、没什么反馈」（用户报障）。
                self.reporter.progress(processed_count, total_written)
                if processed_count % 10 == 0 or processed_count == total_written:
                    print(f"\r写入进度: {processed_count}/{total_written}", end="")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            _fpdf_image_settings.compression_level = _previous_zlib_level

        if processed_count == 0:
            # 有图片但一页都没写出来（全被 skip_pages 跳过、或图片全部解码失败）
            # —— 同样不能当成成功：一个 0 页的 PDF 不是用户要的东西。
            raise ValueError(
                f"{total} 张图片全部被跳过或读取失败，没有生成任何页面"
                "（检查 skip_pages 是否把页面全排除了）"
            )

        print(f"\nPDF 生成完成: {output_pdf}")
        # ⚠️ **边写边落盘**，不要用 `pdf.output(path)`：后者会把整本 PDF 先建进
        # 一个 bytearray 再 write_bytes，于是内存 ≈ 图片缓存（≈PDF 体积）+
        # 输出缓冲（≈PDF 体积）。实测 320 页：峰值 5146MB → 2819MB（−45%）、
        # output() 16.5s → 8.1s，产物逐字节一致。详见 utils/pdf_stream.py。
        write_streaming(pdf, output_pdf)
        return {"processed": processed_count, "output": str(output_pdf)}

    # 图片加载的实现搬到 ``functions/print/image.py``（本文件只留职责：
    # 参数收集与写页）；类属性保持原样，``PrintFunction._load_image`` 仍可用。
    _load_image = staticmethod(_load_image)
