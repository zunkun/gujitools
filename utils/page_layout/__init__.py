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

子模块（按职责）::

    constants   常量（留白修正量 / 页码样式 / 纸张表 / 竖排比例）
    rotation    逐页旋转角与外接框
    spec        PrintTextSpec / PrintPagePlan
    vertical    竖排分段与占位
    paper       纸张尺寸
    nodes       页名解析 / 标题节点 / 左右侧
    plan        单页几何与整页计划

本包的 ``__init__`` 显式重导出全部名字，`from utils.page_layout import X`
与拆分前完全一致。
"""

from __future__ import annotations

from utils.margin_utils import normalize_margin
from utils.page_layout.constants import (
    DEFAULT_ASCENT_RATIO,
    DEFAULT_DESCENT_RATIO,
    DEFAULT_PAGE_NUMBER_FORMAT,
    DEFAULT_PAGE_NUMBER_PREFIX,
    DEFAULT_PAGE_NUMBER_SUFFIX,
    LATIN_ADVANCE_RATIO,
    PAGE_NUMBER_FORMATS,
    PAPER_SIZES_MM,
    TEXT_INSET_MM,
    TEXT_MARGIN_MM,
    TEXT_SIDE_OFFSET_MM,
)
from utils.page_layout.nodes import (
    _page_skipped,
    image_name_parts,
    resolve_title_nodes,
    sides_for_pages,
)
from utils.page_layout.paper import paper_size_mm, print_page_size_mm
from utils.page_layout.plan import (
    _margins_for_page,
    _text_anchor,
    plan_print_page,
    text_insets,
)
from utils.page_layout.rotation import (
    fit_rotated_rect,
    normalize_page_rotation,
    rotated_bbox_size,
)
from utils.page_layout.spec import PrintPagePlan, PrintTextSpec
from utils.page_layout.vertical import (
    is_rotated_char,
    rotated_run_offset_mm,
    text_block_width_mm,
    vertical_advance_mm,
    vertical_chunk_advance_mm,
    vertical_extent_mm,
    vertical_runs,
)
from utils.units import POINTS_PER_MM

__all__ = [
    "DEFAULT_ASCENT_RATIO",
    "DEFAULT_DESCENT_RATIO",
    "DEFAULT_PAGE_NUMBER_FORMAT",
    "DEFAULT_PAGE_NUMBER_PREFIX",
    "DEFAULT_PAGE_NUMBER_SUFFIX",
    "LATIN_ADVANCE_RATIO",
    "PAGE_NUMBER_FORMATS",
    "PAPER_SIZES_MM",
    "POINTS_PER_MM",
    "PrintPagePlan",
    "PrintTextSpec",
    "TEXT_INSET_MM",
    "TEXT_MARGIN_MM",
    "TEXT_SIDE_OFFSET_MM",
    "fit_rotated_rect",
    "image_name_parts",
    "is_rotated_char",
    "normalize_margin",
    "normalize_page_rotation",
    "paper_size_mm",
    "plan_print_page",
    "print_page_size_mm",
    "resolve_title_nodes",
    "rotated_bbox_size",
    "rotated_run_offset_mm",
    "sides_for_pages",
    "text_block_width_mm",
    "text_insets",
    "vertical_advance_mm",
    "vertical_chunk_advance_mm",
    "vertical_extent_mm",
    "vertical_runs",
]
