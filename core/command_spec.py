"""
File: core/command_spec.py
命令规格：参数默认值、枚举取值与校验规则的**唯一事实来源**。

设计目标：
- cli 侧（`CommandArgs._build_args`）与 desktop 侧（`print_params.DEFAULT_PARAMS`）
  原先各维护一份默认值，改一处必漏另一处；本模块把这些定义收敛到一处；
- 枚举值（纸张、方向、输出类型等）与校验规则同理，避免「命令行拒绝、界面放过」；
- 本模块是纯数据 + 纯函数，不导入任何上层模块，也不做 I/O。

新增命令或参数时，只需在 `COMMAND_SPECS` 登记一次。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.color_utils import parse_color as _parse_color_impl
from utils.margin_utils import (
    DEFAULT_PAGE_MARGINS as _DEFAULT_PAGE_MARGINS,
    normalize_margin as _normalize_margin_impl,
)
from utils.page_layout import (
    DEFAULT_PAGE_NUMBER_FORMAT as _DEFAULT_NUMBER_FORMAT,
    DEFAULT_PAGE_NUMBER_PREFIX as _DEFAULT_NUMBER_PREFIX,
    DEFAULT_PAGE_NUMBER_SUFFIX as _DEFAULT_NUMBER_SUFFIX,
)

# ---------------------------------------------------------------- 通用枚举

PAPER_SIZES: Tuple[str, ...] = ("A3", "A4", "A5", "B5")
ORIENTATIONS: Tuple[str, ...] = ("landscape", "portrait")
POSITIONS: Tuple[str, ...] = ("top", "bottom")
TEXT_ORIENTATIONS: Tuple[str, ...] = ("vertical", "horizontal")
TITLE_SIDES: Tuple[str, ...] = ("left", "right", "both")
IMAGE_EXTS: Tuple[str, ...] = ("jpg", "png")
REMBG_TYPES: Tuple[int, ...] = (1, 2, 3)
# area=4「整页」：不调用 YOLO，整页作为一个文本框（普通文档/检测失败时的兜底）
CROP_AREAS: Tuple[int, ...] = (1, 2, 3, 4)
WHOLE_PAGE_AREA: int = 4

# 边距默认值（print）
DEFAULT_PAGE_MARGINS: List[int] = [int(v) for v in _DEFAULT_PAGE_MARGINS]


# ---------------------------------------------------------------- CSS 简写


def normalize_margin(
    value: Any, default: Optional[List[float]] = None
) -> Optional[List[float]]:
    """把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左]。

    实现委托 utils.margin_utils.normalize_margin（最低层），使命令行、
    GUI 表单与 PDF 生成三方共用同一份规则，不再各自实现。
    """
    return _normalize_margin_impl(value, default=default)


def validate_border(border: Any) -> None:
    """校验 border 参数；支持 None / "30" / "20,30" / "20,30,25" / "20,30,20,25"。"""
    if border is None:
        return
    parts = str(border).strip().split(",")
    if len(parts) not in (1, 2, 3, 4):
        raise ValueError(
            f"border 格式错误，支持1/2/3/4个数字；示例：30｜20,30｜20,30,25｜20,30,20,25；输入:{border}"
        )
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        raise ValueError(f"border 必须为数字，输入:{border}")
    for n in nums:
        if n < 0:
            raise ValueError(f"border 边距不能为负数，输入值 {n}")


def parse_color(value: Any) -> Tuple[int, int, int]:
    """解析颜色为 (r, g, b) 整数元组，取值域 [0,255]。

    实现委托 utils.color_utils.parse_color（最低层），命令行与 GUI 共用，
    非法输入抛 ValueError，不做静默降级。
    """
    return _parse_color_impl(value)


def validate_color_fields(args) -> None:
    """校验 print 命令中的颜色参数（title_color / page_number_color）。"""
    for key in ("title_color", "page_number_color"):
        value = args.get(key)
        if value is not None:
            parse_color(value)


def _check_choice(value: Any, allowed: Tuple, label: str) -> None:
    """通用枚举校验。"""
    if value not in allowed:
        raise ValueError(f"{label} 仅允许 {'/'.join(map(str, allowed))}，当前={value}")


# ---------------------------------------------------------------- 规格描述


@dataclass(frozen=True)
class CommandSpec:
    """单个命令的参数规格。

    属性:
        name: 命令名。
        defaults: 参数名 → 默认值。用户未显式提供时注入。
        validators: 校验函数列表，每个函数接收 ArgsProvider 并可能抛 ValueError。
        ui_groups: GUI 表单分组（可选），供 desktop 面板生成表单时参考。
    """

    name: str
    defaults: Dict[str, Any] = field(default_factory=dict)
    validators: Tuple[Callable[[Any], None], ...] = ()


# ---------------------------------------------------------------- 各命令校验器


def _validate_extract(args) -> None:
    if args.get("zoom") < 1:
        raise ValueError(f"zoom 缩放因子必须 >=1，当前={args.get('zoom')}")
    dpi = args.get("dpi")
    if dpi is not None and not (72 <= float(dpi) <= 1200):
        raise ValueError(f"dpi 必须在 72~1200 之间，当前={dpi}")
    if args.get("batch_size") < 1:
        raise ValueError(f"batch‑size 必须 >=1，当前={args.get('batch_size')}")
    _check_choice(args.get("ext"), IMAGE_EXTS, "ext")
    start, end = args.get("start"), args.get("end")
    if start is not None and start < 1:
        raise ValueError(f"start 页码必须 >=1，当前={start}")
    if end is not None and end < 1:
        raise ValueError(f"end 页码必须 >=1，当前={end}")
    if start is not None and end is not None and start > end:
        raise ValueError(f"start({start}) 不能大于 end({end})")
    pages = args.get("pages")
    if pages is not None:
        allowed = set("0123456789,-")
        if any(ch not in allowed for ch in str(pages)):
            raise ValueError(f"pages 包含非法字符，示例：1,2,5‑7；输入:{pages}")


def _validate_crop(args) -> None:
    _check_choice(args.get("area"), CROP_AREAS, "area")
    _check_choice(args.get("ext"), IMAGE_EXTS, "ext")
    validate_border(args.get("border"))


def _validate_rembg(args) -> None:
    _check_choice(args.get("type"), REMBG_TYPES, "type")
    if args.get("sealarea") < 1:
        raise ValueError(f"sealarea 印章面积阈值必须 >=1，当前={args.get('sealarea')}")
    sat = args.get("sealmin_sat")
    if not (0 <= sat <= 255):
        raise ValueError(f"sealmin_sat 取值范围0‑255，当前={sat}")


def _validate_cropremove(args) -> None:
    _check_choice(args.get("area"), CROP_AREAS, "area")
    _check_choice(args.get("type"), REMBG_TYPES, "type")
    if args.get("sealarea") < 1:
        raise ValueError(f"sealarea 印章面积阈值必须 >=1，当前={args.get('sealarea')}")
    sat = args.get("sealmin_sat")
    if not (0 <= sat <= 255):
        raise ValueError(f"sealmin_sat 取值范围0‑255，当前={sat}")
    validate_border(args.get("border"))


def _validate_detect(args) -> None:
    """校验 detect 参数。

    **只校验取值范围，不强制 `--save`。**

    为什么不在校验层拒绝「不带 `--save`」：`CommandArgs.validate()` 是 CLI
    与 GUI **共用**的。GUI 的 detect 阶段本来就不落盘（坐标经事件通道交给
    界面画框），若在此处强制 save，会把 GUI 一并拦死。

    「命令行空跑」的拒绝放在 CLI 入口（`cli.__main__._reject_dry_run`），
    因为只有命令行语境下「不落盘」才等于「白算一趟」；作为代码调用
    （`functions.detect.DetectFunction` / `detect_page_boxes`）当中间步骤
    使用时必须保持可用。
    """
    _check_choice(
        str(args.get("ext") or "png").lower().lstrip("."), ("jpg", "png", "tiff"), "ext"
    )


def _validate_print(args) -> None:
    paper = args.get("paper_size")
    if not isinstance(paper, str) or paper.strip().upper() not in PAPER_SIZES:
        raise ValueError(f"paper_size 仅支持 {'、'.join(PAPER_SIZES)}，当前={paper}")
    _check_choice(args.get("orientation"), ORIENTATIONS, "orientation")

    pdf_name = args.get("pdf_name")
    if pdf_name is not None and not isinstance(pdf_name, str):
        raise ValueError("pdf_name 必须为字符串")

    for key in ("page_margins", "left_page_margins", "right_page_margins"):
        val = args.get(key)
        if val is not None:
            if not isinstance(val, list) or len(val) != 4:
                raise ValueError(f"{key} 应为四元素列表")
            if any(v < 0 for v in val):
                raise ValueError(f"{key} 中的值不能为负数")

    _check_choice(args.get("title_position"), POSITIONS, "title_position")
    _check_choice(args.get("page_number_position"), POSITIONS, "page_number_position")
    for key in ("title_orientation", "page_number_orientation"):
        _check_choice(args.get(key), TEXT_ORIENTATIONS, key)

    # 标题/页码「距页边」：与 page_margins 同一套校验，但允许为空（未配置）
    for key in ("title_margins", "page_number_margins"):
        val = args.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        parsed = normalize_margin(val, default=None)
        if parsed is None:
            raise ValueError(f"{key} 应为 1/2/3/4 个数字（mm），当前={val}")
        if any(v < 0 for v in parsed):
            raise ValueError(f"{key} 中的值不能为负数")

    start, end = args.get("page_number_start_page"), args.get("page_number_end_page")
    if start is not None and (not isinstance(start, int) or start < 1):
        raise ValueError(f"page_number_start_page 必须为 >=1 的整数，当前={start}")
    if end is not None and (not isinstance(end, int) or end < 1):
        raise ValueError(f"page_number_end_page 必须为 >=1 的整数，当前={end}")
    if start is not None and end is not None and start > end:
        raise ValueError(f"start({start}) 不能大于 end({end})")

    nodes = args.get("title_switch_nodes")
    if nodes is not None:
        if not isinstance(nodes, list):
            raise ValueError("title_switch_nodes 必须为列表")
        for item in nodes:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                raise ValueError(
                    "title_switch_nodes 每项必须为 [页码, 标题] 或 [页码, 标题, side]"
                )
            try:
                int(item[0])
            except (ValueError, TypeError):
                raise ValueError("标题切换节点页码必须为整数")
            if len(item) > 3:
                raise ValueError("每项最多3个元素")
            if len(item) == 3 and item[2] not in TITLE_SIDES:
                raise ValueError("side 仅允许 left/right/both")

    # 颜色必须合法：非法值若静默降级为黑色，用户只会看到一张黑字 PDF
    validate_color_fields(args)


# ---------------------------------------------------------------- print 默认值

# 标题/页码「距纸张边界」的默认值（mm，[上,右,下,左]）。
#
# 只有**两处**输入，别再散出第三个数字：
#   - 横向（左/右）：用户指定 10mm —— 不再跟页边距走除法（旧行为是左页
#     left/2、右页 right-6）。
#   - 纵向：跟随 `DEFAULT_PAGE_MARGINS` —— 标题的上边距 = page_margins[0]、页码的
#     下边距 = page_margins[2]，这样文字与图片**贴同一条边**（用户要求）。
#     缺席的那一侧填 0（标题不涉外边距、页码不涉上边距），底层读不到它。
#
# ⚠️ 改 `page_margins` 的默认值，这里的纵向会跟着变——这是刻意的，只有一份定义。
TEXT_SIDE_MARGIN_MM: float = 10.0

# 标题：上跟 page_margins[0]，左右各 TEXT_SIDE_MARGIN_MM，下缺席。
TITLE_MARGIN_DEFAULTS: List[float] = [
    float(_DEFAULT_PAGE_MARGINS[0]),
    TEXT_SIDE_MARGIN_MM,
    0.0,
    TEXT_SIDE_MARGIN_MM,
]

# 页码：下跟 page_margins[2]，左右同标题，上缺席。
PAGE_NUMBER_MARGIN_DEFAULTS: List[float] = [
    0.0,
    TEXT_SIDE_MARGIN_MM,
    float(_DEFAULT_PAGE_MARGINS[2]),
    TEXT_SIDE_MARGIN_MM,
]

def border_has_padding(border) -> bool:
    """上游 crop/rembg 的 border 是否真正加过留白（非 None/空/全 0）。

    用于 print 第四步的边距级联：上游已设真实留白时，第四步的通用边距
    默认回落为 0，避免「图片内留白 + 页面边距」双重留白。border 的取值
    形态同 ``validate_border``：``None`` / ``""`` / ``"30"`` / ``"20,30"`` /
    ``"20,30,25,35"``（逗号可用中文逗号）。
    """
    if border is None:
        return False
    text = str(border).strip()
    if not text:
        return False
    parts = [p for p in text.replace("，", ",").split(",") if p.strip()]
    if not parts:
        return False
    try:
        return any(float(p) > 0 for p in parts)
    except ValueError:
        return False


#: area=4「整页 / 不检测」：整页 `[0,0,W,H]` 即唯一文本框
AREA_WHOLE_PAGE = 4


def effective_border_default(area=None):
    """第三步（crop / rembg / cropremove）``border`` 的默认值——**随 area 变**。

    - ``area ∈ {1,2,3}`` → ``"0"``：第四步会把图重新排进 A4，第三步再外扩
      留白（如 30mm）等于「图片内留白 + 页面边距」双重留白，还会让第四步
      拿到的图尺寸失真，因此默认**不加留白**；
    - ``area = 4``（整页不检测）→ ``None``：整页输出既不裁剪也无留白可言，
      border 对它没有意义，保持原默认。

    ⚠️ 只在用户**没给** border（None / 空串）时生效；显式给值一律以用户为准。
    ⚠️ ``area=2/3`` 下 ``"0"`` 与 ``None`` **不等价**：``"0"`` 输出「文本框
    联合外边界」的紧裁，``None`` 输出整页原尺寸——这是用户确认过的取舍
    （第四步会重新排版，紧裁后的图在 A4 上更好排，见 docs/functions/crop.md）。
    """
    try:
        value = int(area)
    except (TypeError, ValueError):
        return "0"
    if value == AREA_WHOLE_PAGE:
        return None
    return "0"


def effective_page_margin_default(upstream_border=None) -> List[float]:
    """print 第四步的通用边距默认值（受上游 border 级联）。

    - 上游 crop/rembg 已设真实留白（``border_has_padding`` 为真）→ 默认 ``[0,0,0,0]``；
    - 否则（第四步独立运行、CLI、或上游 border 为 None/0）→ 保持内置默认 20。

    ⚠️ 只决定「默认值」：用户在表单/CLI 显式给了 ``page_margins`` 时一律以
    用户值为准（见 ``functions/print.py`` 的 ``or`` 兜底）。
    """
    if border_has_padding(upstream_border):
        return [0.0, 0.0, 0.0, 0.0]
    return list(DEFAULT_PAGE_MARGINS)


# GUI 表单与命令行共用的 print 默认参数。
# 注意：pdf_name 与 store.print_output_pdf 的默认文件名保持一致。
PRINT_DEFAULTS: Dict[str, Any] = {
    "pdf_name": None,
    "paper_size": "A4",
    "orientation": "landscape",
    "page_margins": list(DEFAULT_PAGE_MARGINS),
    "left_page_margins": None,
    "right_page_margins": None,
    "title_printing": False,
    "title_text": "",
    "title_font_size": 20,
    # 标题字体：字体显示名 / 文件路径 / 文件名（如 "仿宋"），
    # None = 自动（仿宋优先），缺字沿降级链顺延到宋体-ExtB 等补字字体。
    "title_font": None,
    "title_color": "0,0,0",
    "title_position": "top",
    "title_orientation": "vertical",
    # 标题/页码「距纸张边界」的距离（mm，[上,右,下,左]）。
    # 默认值见上方 TITLE_MARGIN_DEFAULTS / PAGE_NUMBER_MARGIN_DEFAULTS：
    # 横向 10mm，纵向跟随 page_margins（标题贴 top、页码贴 bottom）。
    # ⚠️ 显式写 `null` 才走旧行为分支（`utils.page_layout._text_anchor`
    # 的 `insets is None`），老配置若想保持原样就写 null。
    "title_margins": list(TITLE_MARGIN_DEFAULTS),
    "page_number_margins": list(PAGE_NUMBER_MARGIN_DEFAULTS),
    "title_switch_nodes": None,
    "page_number_printing": False,
    "page_number_start_page": 1,
    "page_number_end_page": None,
    "page_number_base": 0,
    "page_number_font_size": 20,
    # 页码字体：与 title_font 同规则，两者互不影响
    "page_number_font": None,
    # 页码样式与前后缀：默认「第X頁」（历史形态）。
    # chinese=中文数字 / arabic=阿拉伯数字 / ganzhi=干支（六十甲子）；
    # 前缀后缀原样拼接，想排「第 5 页」就把前缀写成 "第 "。
    "page_number_format": _DEFAULT_NUMBER_FORMAT,
    "page_number_prefix": _DEFAULT_NUMBER_PREFIX,
    "page_number_suffix": _DEFAULT_NUMBER_SUFFIX,
    "page_number_color": "0,0,0",
    "page_number_position": "bottom",
    "page_number_orientation": "vertical",
    "skip_pages": None,
    "files": None,
    # 运行时由 GUI runner 注入的上游（第三步 rembg/crop）border：用于 print
    # 第四步的通用边距级联默认（border 非 0 → 默认 0）。CLI 不传（默认 None），
    # 故 CLI 第四步普通边距保持内置默认 20。不出现在表单/模板里。
    "upstream_border": None,
    # 第四步「版面编辑器」逐图坐标覆盖：{页号(1-based): [x_mm, y_mm, w_mm, h_mm]}。
    # 由 GUI 从 print.json 的 pages[].rect 收集后注入；给定页直接用它作图片框，
    # 不再由 page_margins 推导。CLI 不传（默认 None）→ 全部走自动排版。
    "page_rects": None,
}

# GUI 表单的初次默认值（面向用户，比 CLI 更「已开启」一些）
#
# 与 CLI 的差异**只有「开关类」**：标题/页码默认开启、给一个示例书名和文件名。
# 数值类参数（字号、边距等）一律**不在这里重复**——直接吃 `PRINT_DEFAULTS`，
# 改一处两边同时生效（用户要求：默认值只保留一份，三层保持一致）。
PRINT_FORM_DEFAULTS: Dict[str, Any] = {
    # 列表值单独拷一份：两个表不再共享同一个 list 对象，避免就地修改串味
    **{k: (list(v) if isinstance(v, list) else v) for k, v in PRINT_DEFAULTS.items()},
    "title_text": "古籍名称",
    "pdf_name": "print.pdf",
    "title_printing": True,
    "title_switch_nodes": [],
    "page_number_printing": True,
    "skip_pages": [],
}


# ---------------------------------------------------------------- 命令表

COMMAND_SPECS: Dict[str, CommandSpec] = {
    "extract": CommandSpec(
        name="extract",
        defaults={
            "zoom": 1,
            # 整页渲染的 DPI 下限。矢量 PDF（没有内嵌图）在 zoom=1 时只会
            # 渲染出 72 DPI，去底色后打回 PDF 必然发虚，因此默认补到 300。
            # 取内嵌图时按原图字节落盘，不受这个值影响。
            "dpi": 300,
            "quick": True,
            "ext": "jpg",
            "pages": None,
            "start": None,
            "end": None,
            "batch_size": 4,
        },
        validators=(_validate_extract,),
    ),
    "crop": CommandSpec(
        name="crop",
        defaults={"area": 1, "border": None, "ext": "png"},
        validators=(_validate_crop,),
    ),
    "rembg": CommandSpec(
        name="rembg",
        defaults={
            "offset": 0,
            "type": 1,
            "seal": False,
            "sealcolor": False,
            "sealarea": 80,
            "sealmin_sat": 50,
            "area": 1,
            "border": None,
        },
        # 注意：这里**没有** ext。rembg 的输出格式固定为 PNG
        # （type=2 的 1bit 单色位图只有 PNG 能无损承载），
        # functions/rembg.py 里不读 ext，模板也不要提供该键。
        validators=(_validate_rembg,),
    ),
    "cropremove": CommandSpec(
        name="cropremove",
        defaults={
            "offset": 0,
            "type": 1,
            "seal": False,
            "ext": "png",
            "sealcolor": False,
            "sealarea": 80,
            "sealmin_sat": 50,
            "area": 1,
            "border": None,
        },
        # cropremove 继承 TextRegionProcessor，输出后缀读 ext
        # （与 crop 同一处赋值），故必须有 ext 默认值。
        validators=(_validate_cropremove,),
    ),
    "print": CommandSpec(
        name="print",
        defaults=dict(PRINT_DEFAULTS),
        validators=(_validate_print,),
    ),
    # detect：检测左右文本框并上报坐标。
    # 不带 save 时是**无产出的中间步骤**（仅代码调用有意义）；
    # 命令行下无 save 的空跑会被 CLI 入口直接拒绝（见 cli.__main__._reject_dry_run）。
    # 命令行用 --save 时不产出文件，故必须显式 --save 落地标注图，目录规则同 crop。
    "detect": CommandSpec(
        name="detect",
        defaults={"save": False, "ext": "png"},
        validators=(_validate_detect,),
    ),
}


def get_spec(command: Optional[str]) -> Optional[CommandSpec]:
    """按命令名取规格；未登记的命令返回 None。"""
    if command is None:
        return None
    return COMMAND_SPECS.get(command)


def supported_commands() -> Tuple[str, ...]:
    """返回所有已登记的命令名。"""
    return tuple(COMMAND_SPECS.keys())
