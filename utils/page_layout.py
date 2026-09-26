# -*- coding: utf-8 -*-
"""print 页面排版的几何规则（纯计算，不依赖 cv2 / Qt / fpdf）。

**这里是被 `functions/print.py`（生成 PDF）与 desktop 第四步「打印效果
预览」共用的唯一事实来源**——两处若各写一份公式，预览就会和成品悄悄
漂移（用户按预览调好边距，生成的 PDF 却不一样，最难排查）。

只算几何，不画图：
- CLI/desktop 拿到 `PrintPagePlan` 后各自用 fpdf / QPainter 渲染；
- 坐标单位统一为 **毫米**，与 fpdf 的 `unit="mm"` 一致；
- 输入图片尺寸为**像素**，换算只发生在"图片放进可用区"这一步
  （scale = mm/px，与 print.py 里的算法逐字等价）。

历史坑：`text_margin`（图片左右额外留白，给竖排标题/页码让位）原先是
print.py 里的裸字面量 `8.0`，现在提为 `TEXT_MARGIN_MM`。

竖排里的拉丁字符（`vertical_runs` / `vertical_extent_mm`）：
- 汉字等宽字符**一字一格**；ASCII 可打印字符连成一段**整体旋转 90°**，
  按竖排惯例（如「呵呵Happiness」）而不是把 9 个字母各占一格；
- 分段规则只在本模块定义，`functions/print.py`（fpdf）与 desktop 预览
  （QPainter）都调它，不会出现"预览排一版、成品排另一版"。

标题/页码的「距页边」（`title_margins` / `page_number_margins`）：
- 语义是**距纸张边界**的绝对距离（mm），不再由 page_margins 推导；
- 用与 `page_margins` 同一套 CSS 简写（1/2/3/4 值 → 上,右,下,左），
  所以「左页取左值、右页取右值」天然可以不一样；
- ⚠️ 横向的口径是**文字轮廓边缘**到纸边，不是落点/字格到纸边：
  文字从落点 x 往右画，所以**右页**要把落点再往左退一个文字宽度
  （`text_block_width_mm`：竖排 = 一个字宽，横排 = 整串宽），
  这样右页的**轮廓右缘**才正好离右纸边 `右` 值。不退的话右页空白会比
  左页多一个字宽（写 10mm 实得 10mm+字宽），左右看着不对称。
  左页不需要退——轮廓左缘就是落点。
- ⚠️ 四值里有**两个永远读不到**：上方文字（标题）只取「上」、下方文字
  （页码）只取「下」（见 `_text_anchor` 的 `is_top` 分支）。桌面端因此
  只摆用得上的两个分量、分两行（第一行「左右边距：」一个值管两边、第二行
  「上边距：」/「下边距：」，见
  `desktop.components.panels.print_form.PrintFormMixin.INSET_VISIBLE`），
  并按键把四值补全后导出（`_inset_values`）——但**参数契约仍是四元素**，
  命令行/YAML 照旧写四值；
- 不填（None）时**完全回落到旧行为**（左页 ml/2、右页 mr-6、上下 2mm），
  老任务的输出一个像素都不会变；
- ⚠️ **填了之后图片不再收窄**：用户填的是"文字离纸边多远"，就按这个距离画，
  **允许文字压在图片上**（用户明确要求取消"自动避让图片"这个限制）。
  图片左右始终只留固定的 `TEXT_MARGIN_MM`——那是「距页边」留空时竖排
  标题/页码的默认落点所在，也是老任务输出的既定几何。
  历史：这里曾经按「距页边 + 字宽」把图片收窄（`text_reserve_mm`），
  结果用户设一个 10mm 的左距就把图缩掉一大圈，且判定口径很难解释。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from utils.margin_utils import normalize_margin

# ⚠️ 换算常量统一在 utils/units.py（本模块不再自己定义 MM_PER_INCH /
# POINTS_PER_MM——此前与 utils/pdf_utils.py、functions/print.py 各写一份）
from utils.units import POINTS_PER_MM

# ---------------------------------------------------------------- 老行为修正量
# 「距页边」（title_margins / page_number_margins）**未配置**时，标题/页码
# 的落点要在页边距基础上再加的修正量。三者**全部归零**（用户决定）：
# 未配置 = 严格贴页边距，不加任何隐式修正，图片也不额外留白。
#
# 归零前是 8.0 / 2.0 / 6.0——那是早期为了「竖排文字别压到正文」加的经验值，
# 结果是**用户改不了、界面也看不到**的隐形默认值：想精确控制就得先猜出
# 这几个数，再手动把它们减掉。现在一律 0，要留白就明着填「距页边」。
#
# ⚠️ 后果：老任务（未配置距页边）的输出几何会变——图片左右不再留 8mm
# （图片变大）、标题/页码不再内缩 2mm、右页不再外推 6mm。
TEXT_MARGIN_MM = 0.0
TEXT_INSET_MM = 0.0
TEXT_SIDE_OFFSET_MM = 0.0

# ---------------------------------------------------------------- 页码样式
#: 页码数字的样式（下拉顺序即界面顺序）
PAGE_NUMBER_FORMATS = ("chinese", "arabic", "ganzhi")
#: 三者是**唯一定义处**：``core.command_spec.PRINT_DEFAULTS`` 从这里取，
#: 桌面表单与 guji.yaml 再跟着 CLI 走（默认值只保留一份）。
#: 默认「第X頁」是历史形态，改它会改变老任务的成品。
DEFAULT_PAGE_NUMBER_FORMAT = "chinese"
DEFAULT_PAGE_NUMBER_PREFIX = "第"
DEFAULT_PAGE_NUMBER_SUFFIX = "頁"

# 纸张短边 × 长边（mm），小写键
PAPER_SIZES_MM = {
    "a3": (297.0, 420.0),
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "b5": (176.0, 250.0),
}


@dataclass(frozen=True)
class PrintTextSpec:
    """一段要画到页面上的文字（标题或页码）。

    属性:
        text: 文本内容。
        x_mm: 落点横坐标（竖排为整列的 x）。
        y_start_mm: 起始纵坐标（竖排为**首字**的基线附近）。
        char_h_mm: 单字高度（竖排据此逐字下移）。
        vertical: 是否竖排。
        font_size_pt: 字号（pt，仅用于渲染端换算）。
        color: (r, g, b)。
        direction: 逐字排布方向，"up" 表示 y **递增**（自页顶向下
            排列），与 ``utils.pdf_draw.draw_vertical_text`` 同名参数一致。
        ⚠️ `vertical=True` 时文本按 `vertical_runs` 分段：宽字符（汉字等）
            各自占一格，ASCII（拉丁字母/数字/半角符号）连成一段**整体旋转
            90°**（`Happiness` 不会拆成九个字母格）。
        baseline_mm: 横排时的基线 y（竖排逐字用 y_start_mm，忽略本值）。
        font: 字体指定值（显示名 / 文件路径 / 文件名）；None = 自动
            （仿宋优先）。只用于**选字体**，不参与几何计算——渲染端据此
            挑字体，PDF 端还要按字形降级（见 `utils.pdf_draw.FontChain`）。
    """

    text: str
    x_mm: float
    y_start_mm: float
    char_h_mm: float
    vertical: bool
    font_size_pt: float
    color: Tuple[int, int, int]
    direction: str = "up"
    baseline_mm: Optional[float] = None
    font: Optional[str] = None


@dataclass(frozen=True)
class PrintPagePlan:
    """单页排版的完整几何。

    属性:
        page_w_mm / page_h_mm: 纸张尺寸（已按方向交换）。
        image: (x, y, w, h) 毫米，图片在页面上的落点与显示尺寸。
        title / page_number: 文字规格，未开启时为 None。
        side: 本页标题/页码所在侧（"left" / "right"）。
        skipped: 本页命中 skip_pages（生成 PDF 时整页不输出，预览留空）。
        text_reserve_mm: 图片左右两侧的固定留白（mm）——**恒为
            `TEXT_MARGIN_MM`**：「距页边」现在只决定文字画在哪儿，
            不再反过来收窄图片（见模块 docstring 的说明）。
    """

    page_w_mm: float
    page_h_mm: float
    image: Tuple[float, float, float, float]
    title: Optional[PrintTextSpec] = None
    page_number: Optional[PrintTextSpec] = None
    side: str = "left"
    skipped: bool = False
    text_reserve_mm: float = TEXT_MARGIN_MM


# ---------------------------------------------------------------- 竖排分段
# 竖排时"整段旋转 90°"的字符范围：ASCII 可打印字符（拉丁字母、数字、半角符号、
# 空格）。汉字/全角标点等宽字符才是"一个字占一格"。
# ⚠️ 这是排版惯例：竖排里的 `Happiness` 不能拆成 H/a/p/p/i/n/e/s/s 九格，
# 而要整体旋转 90° 变成一个"竖条"（各自独占一格会挤成一条竖线且认不出来）。
LATIN_ADVANCE_RATIO = 0.55
# 旋转段在竖排方向上占的高度 ≈ 字符数 × 平均字宽（字宽 / 字高）。
# 只是**估算**（比例字体里 i 与 W 差很多），仅用于 `vertical_extent_mm`
# 算整串占位高度；真正绘制时必须走 `vertical_chunk_advance_mm` 传入
# 渲染端的实测宽度——否则像「Harvard_drs_435580539_」这种数字/下划线
# 长段（实际 ≈0.5 字宽/字符）会按 0.55 高估，旋转段和后续汉字之间
# 多出一条肉眼可见的空隙。


def is_rotated_char(ch: str) -> bool:
    """该字符是否属于"整段旋转 90°"的拉丁/半角段。"""
    return 0x20 <= ord(ch) <= 0x7E


def vertical_runs(text: str) -> List[Tuple[str, bool]]:
    """竖排文本 → [(片段, 是否旋转 90°)]，相邻同类字符合并成一段。

    ``"呵呵Happiness"`` → ``[("呵呵", False), ("Happiness", True)]``：
    汉字各自占一格，英文整段旋转。绘制端（fpdf / QPainter）按这个分段渲染，
    所以两边的断段规则**只在这里定义一次**。
    """
    runs: List[Tuple[str, bool]] = []
    for ch in str(text or ""):
        rotated = is_rotated_char(ch)
        if runs and runs[-1][1] == rotated:
            runs[-1] = (runs[-1][0] + ch, rotated)
        else:
            runs.append((ch, rotated))
    return runs


def vertical_advance_mm(chunk: str, char_h_mm: float, rotated: bool) -> float:
    """一段竖排片段在竖直方向上占的高度（mm）——**估算值**。

    ⚠️ 只用于排版占位（`vertical_extent_mm` → 标题/页码落点）。绘制时的
    逐段步进请用 ``vertical_chunk_advance_mm`` 并传渲染端的实测宽度。
    """
    text = str(chunk or "")
    if not rotated:
        return len(text) * float(char_h_mm)
    return len(text) * LATIN_ADVANCE_RATIO * float(char_h_mm)


def vertical_chunk_advance_mm(
    chunk: str, char_h_mm: float, rotated: bool, latin_width_mm=None
) -> float:
    """绘制端一段竖排片段的实际步进（mm）——`draw_vertical_text`（fpdf）
    与 desktop 预览（QPainter）共用的同一份规则。

    - 宽字符段：仍是一字一格（``len × char_h_mm``）；
    - 旋转拉丁段：优先用渲染端**实测**的字符串宽度（fpdf 的
      ``get_string_width`` / Qt 的 ``QFontMetrics.horizontalAdvance``），
      拿不到实测值（``latin_width_mm=None``）才回落到 `LATIN_ADVANCE_RATIO`
      估算——回落只为兼容，正常路径两条渲染端都会传实测值。
    """
    text = str(chunk or "")
    if not rotated:
        return len(text) * float(char_h_mm)
    if latin_width_mm is None:
        return vertical_advance_mm(text, char_h_mm, True)
    return float(latin_width_mm)


def vertical_extent_mm(text: str, char_h_mm: float) -> float:
    """整串竖排文本的高度（mm）。"""
    return sum(
        vertical_advance_mm(chunk, char_h_mm, rotated)
        for chunk, rotated in vertical_runs(text)
    )


def text_block_width_mm(text: str, char_h_mm: float, vertical: bool) -> float:
    """一段文字的**横向宽度**（mm）——即它从落点 x 向右占多宽。

    用于「距右纸边」的口径：用户填的是**文字轮廓右边缘**到纸边的距离，
    所以落点得从右边往回退「右距 + 本宽度」，否则文字会比设定值多缩一个字宽
    （用户明确要求，见 `_text_anchor`）。

    * 竖排：整串是**一列**，宽度就是一个字宽（汉字方块格，等于字号）；
      拉丁段旋转 90° 后也只是一列的宽度，不额外加宽。
    * 横排：宽度 ≈ 字符数 × 字宽（比例字体的粗估，`LATIN_ADVANCE_RATIO`
      同一套近似口径；误差只体现在右页横向标题的 1~2mm 留白上）。
    """
    text = str(text or "")
    if not text:
        return 0.0
    cell = float(char_h_mm)
    if vertical:
        return cell
    return len(text) * cell


# ---------------------------------------------------------------- 纸张
def paper_size_mm(paper_size: str) -> Tuple[float, float]:
    """纸张名 → (短边, 长边) 毫米；非法纸张抛 ValueError。"""
    if not isinstance(paper_size, str):
        raise ValueError("paper_size 仅支持 A3、A4、A5、B5")
    key = paper_size.strip().lower()
    if key not in PAPER_SIZES_MM:
        raise ValueError(f"paper_size 仅支持 A3、A4、A5、B5，当前={paper_size}")
    return PAPER_SIZES_MM[key]


def print_page_size_mm(paper_size: str, orientation: str) -> Tuple[float, float]:
    """纸张 + 方向 → (页宽, 页高) 毫米。

    方向同时接受 fpdf 的 "P"/"L" 与 CLI/GUI 的 "portrait"/"landscape"：
    `functions/print.py` 在 execute() 里把后者映射成了前者再传给排版，
    两条路径都要能对上。
    """
    short_side, long_side = paper_size_mm(paper_size)
    flag = str(orientation or "landscape").strip().lower()
    if flag in ("l", "landscape"):
        return long_side, short_side
    return short_side, long_side


# ---------------------------------------------------------------- 页名解析
def image_name_parts(path) -> Tuple[Optional[int], Optional[str]]:
    """解析数字页名，返回 (页名数字, side)；side 可能为空。"""
    import os
    import re

    name = os.path.splitext(os.path.basename(str(path)))[0].lower()
    match = re.fullmatch(r"(\d+)(?:[_-](l|r))?", name)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2)


def resolve_title_nodes(
    image_files: Sequence, title_switch_nodes: Sequence
) -> List[Tuple[int, Tuple[str, str]]]:
    """把配置里的 [页名, 标题, side] 解析为「图片下标 → (标题, 侧别)」。

    ``页名`` 是**原始页码**（如 ``5`` / ``5-r``），不是列表下标——用户填
    「15」想的是原书第 15 页，即使该页被拖到别处，标题切换仍要跟着它。
    """
    resolved = {}
    for node in title_switch_nodes or []:
        if len(node) < 2:
            continue
        anchor_spec = str(node[0]).strip()
        title = node[1]
        requested_side = str(node[2]).lower() if len(node) > 2 else "left"
        page, node_side = image_name_parts(anchor_spec)
        if page is None and anchor_spec.isdigit():
            page, node_side = int(anchor_spec), None
        if page is None:
            continue
        candidates = []
        for index, path in enumerate(image_files):
            file_page, file_side = image_name_parts(path)
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


def sides_for_pages(
    total: int, sorted_nodes: Sequence, page_number_start_page: int
) -> List[str]:
    """逐页给出标题/页码所在侧（left / right）。

    从起始标注页（或最近的章节节点）开始按图片序号交替左右。
    """
    sides: List[str] = []
    for image_index in range(total):
        anchor_index = page_number_start_page - 1
        anchor_side = "left"
        for node_index, (_title, node_side) in sorted_nodes:
            if anchor_index <= node_index <= image_index and node_side in (
                "left",
                "right",
            ):
                anchor_index = node_index
                anchor_side = node_side
        offset = image_index - anchor_index
        sides.append(
            anchor_side
            if offset % 2 == 0
            else ("right" if anchor_side == "left" else "left")
        )
    return sides


# ---------------------------------------------------------------- 跳过页
def _page_skipped(skip_pages, current_page: int, image_name) -> bool:
    """本页是否命中 skip_pages（与 functions/print.py 的解析规则一致）。

    纯数字按**最终清单序号**（1 起）匹配；带侧别的写法（``5-r``）按同名回查。
    """
    for spec in skip_pages or []:
        text = str(spec).strip()
        if text.isdigit():
            if int(text) == current_page:
                return True
            continue
        page, side = image_name_parts(text)
        if page is None or not image_name:
            continue
        file_page, file_side = image_name_parts(image_name)
        if file_page == page and (side is None or file_side == side):
            return True
    return False


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
        return x_pos, y_start

    top_mm, right_mm, bottom_mm, left_mm = (
        float(insets[0]), float(insets[1]), float(insets[2]), float(insets[3])
    )
    x_pos = left_mm if side == "left" else page_w - right_mm - float(block_w)
    y_start = top_mm if is_top else page_h - bottom_mm - total_h
    return x_pos, y_start


def plan_print_page(
    image_size_px: Tuple[int, int],
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
