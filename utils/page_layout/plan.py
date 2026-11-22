# -*- coding: utf-8 -*-
"""单页排版几何：边距、标题/页码落点与整页计划。"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from utils.margin_utils import normalize_margin
from utils.page_layout.constants import (
    DEFAULT_PAGE_NUMBER_FORMAT,
    DEFAULT_PAGE_NUMBER_PREFIX,
    DEFAULT_PAGE_NUMBER_SUFFIX,
    TEXT_INSET_MM,
    TEXT_MARGIN_MM,
    TEXT_SIDE_OFFSET_MM,
)
from utils.page_layout.nodes import (
    _page_skipped,
    resolve_title_nodes,
    sides_for_pages,
)
from utils.page_layout.paper import print_page_size_mm
from utils.page_layout.spec import PrintPagePlan, PrintTextSpec
from utils.page_layout.vertical import text_block_width_mm, vertical_extent_mm

# ⚠️ 换算常量统一在 utils/units.py（本模块不再自己定义 MM_PER_INCH /
# POINTS_PER_MM——此前与 utils/pdf_utils.py、functions/print.py 各写一份）
from utils.units import POINTS_PER_MM


# ---------------------------------------------------------------- 单页几何
def _margins_for_page(
    margins: Sequence[float],
    left_margins,
    right_margins,
    page_index: int,
) -> Tuple[float, float, float, float]:
    """奇偶页边距：1-based 奇数页用 left_margins，偶数页用 right_margins。

    ⚠️ **只配一侧时不再整条规则被忽略**（2026-09-26 审计）：原实现要求两侧都非
    None 才生效，而 `command_spec` 允许单独提供 `left_page_margins`——结果是用户
    只填了左页边距，PDF 却仍按通用边距排，**毫无提示**。现在：配了的那侧按其奇偶
    生效，没配的那侧回落通用边距。
    """
    if left_margins is not None or right_margins is not None:
        source = left_margins if page_index % 2 == 1 else right_margins
        if source is not None:
            return tuple(float(v) for v in source)  # type: ignore[return-value]
    return tuple(float(v) for v in margins)  # type: ignore[return-value]


def text_insets(value: Any) -> Optional[List[float]]:
    """标题/页码的「距页边」设置 → [上, 右, 下, 左]（mm）。

    与 `page_margins` 同款 CSS 简写（1/2/3/4 值）。**空值返回 None**，
    表示"沿用由 page_margins 推导的旧行为"——老任务（没有这两个键）
    的输出必须一个像素都不变，所以这里绝不能回落到某个默认数字。

    非法输入也返回 None（宽松）：校验归入口层
    （`core.command_spec` / GUI 表单），库层不替调用方做决定。
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    vals = normalize_margin(value, default=None)
    if not vals:
        return None
    return [float(v) for v in vals]


def _text_anchor(
    page_w: float,
    page_h: float,
    side: str,
    is_top: bool,
    total_h: float,
    mt: float,
    mr: float,
    mb: float,
    ml: float,
    insets: Optional[Sequence[float]],
    block_w: float = 0.0,
) -> Tuple[float, float]:
    """标题/页码的落点 (x, y_start)；y_start 是**首字**位置。

    两种语义，只在这里切换：

    * ``insets`` 为 None（用户没填「距页边」）→ **旧行为**：横向落在页
      边距的中缝（左页 ml/2、右页 mr-6），纵向在页边距内再缩 2mm。
      老任务必须逐毫米保持原样，所以这段公式一个字都不能动。
      ⚠️ 唯一的例外是**负页边距**（2026-11-21 起允许）：那种情况下推导值会
      跑到纸外，落点被夹回纸内（见下面注释）——负边距的语义是"图片顶出
      纸边"，文字没有理由跟着消失。
    * ``insets`` 有值 → **距纸张边界**的绝对距离：左页取「左」值、右页
      取「右」值（所以左右可以不一样），纵向取「上」或「下」值。

    ⚠️ `block_w` 是这段文字的**横向宽度**（`text_block_width_mm`）。
    它只用在**右页**：文字从 x 往右画，而用户填的 `right_mm` 是
    **文字轮廓右边缘**到右纸边的距离，所以落点要再往左退一个块宽
    （`page_w - right_mm - block_w`）。不减去它，文字会比设定值多缩
    一个字宽——左页没这问题（轮廓左边缘就是落点）。
    """
    if insets is None:
        if side == "left":
            x_pos = ml / 2.0
        else:
            x_pos = page_w - mr + TEXT_SIDE_OFFSET_MM
        if is_top:
            y_start = mt + TEXT_INSET_MM
        else:
            y_start = page_h - mb - total_h - TEXT_INSET_MM
        # ⚠️ 夹在纸内（2026-11-21 起页边距可为负）：负边距是「图片顶出纸边」，
        #    但文字的落点若跟着出纸，标题/页码会**直接看不见**（用户只会以为
        #    "没生效"）。这里把落点收回 [0, 纸边−文字块]，正常（非负）边距下
        #    这两个夹取恒不生效，老任务几何一个像素都不变。
        x_pos = max(0.0, min(x_pos, page_w - float(block_w)))
        y_start = max(0.0, min(y_start, page_h - float(total_h)))
        return x_pos, y_start

    top_mm, right_mm, bottom_mm, left_mm = (
        float(insets[0]), float(insets[1]), float(insets[2]), float(insets[3])
    )
    x_pos = left_mm if side == "left" else page_w - right_mm - float(block_w)
    y_start = top_mm if is_top else page_h - bottom_mm - total_h
    return x_pos, y_start


def plan_print_page(
    image_size_px: Tuple[float, float],
    args: dict,
    page_index: int,
    total: int,
    sides: Optional[Sequence[str]] = None,
    sorted_nodes: Optional[Sequence] = None,
    image_name: Optional[str] = None,
    image_rect: Optional[Sequence[float]] = None,
) -> PrintPagePlan:
    """单页排版几何。

    参数:
        image_size_px: 图片原始像素 (w, h)。
        args: print 参数（CLI 的 command_args 或 GUI 面板 get_args()）。
        page_index: **0-based** 图片下标。
        total: 图片总数（页码结束页缺省时用）。
        sides: 逐页左右侧（由 `sides_for_pages` 预计算）；不传则临时算。
        sorted_nodes: 章节节点（`resolve_title_nodes` 结果）；不传则临时算。
        image_name: 当前图片文件名（stem 即可），用于 ``skip_pages``
            按页名回查；不传则只能按序号匹配。
    """
    from utils.color_utils import parse_color
    from utils.string_utils import format_page_number

    page_w, page_h = print_page_size_mm(
        args.get("paper_size", "A4"), args.get("orientation", "landscape")
    )
    margins = args.get("page_margins") or [0.0, 0.0, 0.0, 0.0]
    mt, mr, mb, ml = _margins_for_page(
        margins,
        args.get("left_page_margins"),
        args.get("right_page_margins"),
        page_index + 1,
    )

    if sorted_nodes is None:
        # ⚠️ 兜底**解析不了节点**：这里拿不到条目清单，空列表匹配不到任何
        #    页名 → 节点被整体忽略、各页恒用主标题。带 title_switch_nodes
        #    的调用方（预览/版面编辑器/放大导出）必须自己用完整清单解析好
        #    再传进来（见 print_preview._resolved_nodes），执行层
        #    （functions/print.py）传的就是 image_files 解析结果。
        sorted_nodes = resolve_title_nodes([], args.get("title_switch_nodes") or [])
    if sides is None:
        sides = sides_for_pages(
            total, sorted_nodes, int(args.get("page_number_start_page", 1) or 1)
        )
    side = sides[page_index] if page_index < len(sides) else "left"

    # ---- 图片落点：与 functions/print.py 逐步等价 ----
    # 左右留白是固定值（不再随「距页边」涨）：填入的距离只决定文字落点，
    # 允许文字压在图片上——见模块 docstring 的说明。
    reserve = TEXT_MARGIN_MM
    w_px, h_px = float(image_size_px[0]), float(image_size_px[1])
    # ⚠️ 页边距**允许为负**（用户 2026-11-21）：「设 0 还不合适就继续往负值设」。
    #    负值让可用区比纸面更大 —— 图片按更大的可用区缩放，落点因此跑到纸外
    #    （`x_img < 0`），超出的部分由纸张自然裁掉。这是**预期语义**（按纸宽
    #    放大再裁边），不是要夹回去的脏数据；只有"可用区被大边距挤成负数"
    #    那种（正值过大）才夹到 0。
    avail_w_raw = page_w - ml - mr
    # ⚠️ 必须夹到 0 以上（2026-09-26 审计）：`avail_w_for_img` 早就夹了，
    #    `avail_h` 没夹——边距大到超过纸高时它是负数，于是 `scale` 取负值、
    #    图片框变成**负宽高**传给 `pdf.image()`（畸形 PDF 或直接报错）。
    #    校验层已经给边距加了上界，这里是纵深防线（调用方可以绕过校验直接进来）。
    avail_h = max(0.0, page_h - mt - mb)
    avail_w_for_img = max(0.0, avail_w_raw - 2 * reserve)
    if args.get("keep_ratio", True):
        scale = min(
            avail_w_for_img / w_px if w_px > 0 else 0.0,
            avail_h / h_px if h_px > 0 else 0.0,
        )
        new_w, new_h = w_px * scale, h_px * scale
    else:
        # 非原比例（`keep_ratio: false`）：图片**铺满可用区域**——宽、高各自取满，
        # 不再受原图宽高比约束（这就是"取消原比例缩放"的语义：按纸面铺开）。
        # 可用区域 = 纸张 − 页边距 − 左右各 TEXT_MARGIN_MM（给竖排标题/页码留的
        # 固定边距，与保比例分支同源，两条分支的可视区域完全一致）。
        new_w, new_h = avail_w_for_img, avail_h
    x_img = ml + reserve + (avail_w_for_img - new_w) / 2
    y_img = mt + (avail_h - new_h) / 2

    # 第四步「版面编辑器」逐图覆盖：用户在 A4 纸上拖拽/缩放后记录的坐标
    # （[x_mm, y_mm, w_mm, h_mm]，页面 mm 坐标系，与 plan.image 同源）。
    # 给定后**直接作为图片框**，不再由 page_margins 推导——即所见即所得。
    # 这是「显式值优先」原则：title/页码位置只取决于 page_margins（与图片框
    # 无关），故不受影响。坐标需在页面内，否则回落到自动排版。
    if image_rect is not None:
        try:
            rx, ry, rw, rh = (float(v) for v in image_rect[:4])
        except (TypeError, ValueError, IndexError):
            rx, ry, rw, rh = x_img, y_img, new_w, new_h
        if rw > 0 and rh > 0 and 0 <= rx and 0 <= ry and \
                rx + rw <= page_w + 1e-6 and ry + rh <= page_h + 1e-6:
            x_img, y_img, new_w, new_h = rx, ry, rw, rh

    title_insets = text_insets(args.get("title_margins"))
    number_insets = text_insets(args.get("page_number_margins"))

    current_page = page_index + 1  # 物理页码（1-based）
    skipped = _page_skipped(
        args.get("skip_pages"), current_page, image_name
    )

    # ---- 标题 ----
    title_spec = None
    start_page = int(args.get("page_number_start_page", 1) or 1)
    if args.get("title_printing") and current_page >= start_page:
        current_title = str(args.get("title_text") or "")
        for node_index, (node_title, _node_side) in sorted_nodes:
            if node_index <= page_index:
                current_title = str(node_title)
        if current_title:
            font_size = float(args.get("title_font_size", 12) or 12)
            char_h = font_size / POINTS_PER_MM
            vertical = args.get("title_orientation", "vertical") == "vertical"
            is_top = args.get("title_position", "top") == "top"
            # 竖排高度：拉丁段整体旋转 90°，每个字母不占一整格
            total_h = vertical_extent_mm(current_title, char_h)
            x_pos, y_start = _text_anchor(
                page_w, page_h, side, is_top, total_h,
                mt, mr, mb, ml, title_insets,
                # 横向宽度：右页的「距右」按**文字轮廓右边缘**算，
                # 落点要再退一个块宽（竖排是一列 = 一个字宽）
                text_block_width_mm(current_title, char_h, vertical),
            )
            title_spec = PrintTextSpec(
                text=current_title,
                x_mm=x_pos,
                y_start_mm=y_start,
                char_h_mm=char_h,
                vertical=vertical,
                font_size_pt=font_size,
                color=parse_color(args.get("title_color") or "0,0,0"),
                # 横排基线：顶部 +1 字高、底部 -1 字高（与 print.py 一致）
                baseline_mm=None if vertical else y_start + (char_h if is_top else -char_h),
                font=args.get("title_font"),
            )

    # ---- 页码 ----
    number_spec = None
    end_page = args.get("page_number_end_page")
    end_page = total if end_page is None else int(end_page)
    if args.get("page_number_printing") and start_page <= current_page <= end_page:
        base = int(args.get("page_number_base", 0) or 0)
        # ⚠️ 前缀/后缀用 `is None` 判断、不能 `or` 兜底：用户想"只要数字"时
        # 会把前缀填成空串，用 `or` 会把它悄悄变回默认的「第」。
        prefix = args.get("page_number_prefix")
        prefix = DEFAULT_PAGE_NUMBER_PREFIX if prefix is None else prefix
        suffix = args.get("page_number_suffix")
        suffix = DEFAULT_PAGE_NUMBER_SUFFIX if suffix is None else suffix
        number_text = format_page_number(
            base + current_page,
            args.get("page_number_format") or DEFAULT_PAGE_NUMBER_FORMAT,
            prefix,
            suffix,
        )
        font_size = float(args.get("page_number_font_size", 12) or 12)
        char_h = font_size / POINTS_PER_MM
        vertical = args.get("page_number_orientation", "vertical") == "vertical"
        is_top = args.get("page_number_position", "bottom") != "bottom"
        total_h = vertical_extent_mm(number_text, char_h)
        x_pos, y_start = _text_anchor(
            page_w, page_h, side, is_top, total_h,
            mt, mr, mb, ml, number_insets,
            text_block_width_mm(number_text, char_h, vertical),
        )
        number_spec = PrintTextSpec(
            text=number_text,
            x_mm=x_pos,
            y_start_mm=y_start,
            char_h_mm=char_h,
            vertical=vertical,
            font_size_pt=font_size,
            color=parse_color(args.get("page_number_color") or "0,0,0"),
            baseline_mm=None if vertical else y_start + (char_h if is_top else -char_h),
            font=args.get("page_number_font"),
        )

    return PrintPagePlan(
        page_w_mm=page_w,
        page_h_mm=page_h,
        image=(x_img, y_img, new_w, new_h),
        title=title_spec,
        page_number=number_spec,
        side=side,
        skipped=skipped,
        text_reserve_mm=reserve,
    )
