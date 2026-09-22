# -*- coding: utf-8 -*-
"""desktop 各阶段面板的**默认参数**集中定义（唯一事实来源）。

面板散着写默认值会漂移：同一个参数在「构建控件初值」「``_apply_args`` 缺省
兜底」「``reset_to_default``」三处各写一遍，改一处漏两处（`page_number_font_size`
就曾出现「兜底 12 / 默认 18」两套值）。这里按阶段收成一张表，各消费方统一取用：

1. ``DEFAULTS[stage]`` —— 面板 ``_apply_args()`` 的缺键兜底与控件初值；
2. ``StagePanel.reset_to_default()`` —— 复位到本表；
3. 表单下拉的「中文显示 ↔ 参数值」候选表也在此登记。

## 与 core.command_spec 的关系

``core/command_spec.py`` 是**命令行**参数的唯一事实来源，本模块是**桌面表单**的
那一份。两者刻意分开：CLI 的 print 默认是「空表单」（不打印标题、pdf_name=None），
而桌面表单打开就该是一份能直接出 PDF 的配置（有书名、有页码）。print 段的差异
由 ``core.command_spec.PRINT_FORM_DEFAULTS`` 显式表达，这里直接引用，不再抄一份。

其余阶段（extract/detect/rembg）桌面与 CLI 语义一致，因此**以 command_spec 的
defaults 为底**，只覆盖表单侧特有的键（如 ``pages`` 表单里是空串而非 None），
见各表的 ``_base`` 调用。这样 CLI 改默认值时桌面自动跟随，不会再出现两份值。
"""

from __future__ import annotations

from core.command_spec import (
    COMMAND_SPECS,
    IMAGE_EXTS,
    PAPER_SIZES as _PAPER_SIZES,
    PRINT_FORM_DEFAULTS,
    REMBG_TYPES as _REMBG_TYPES,
    TEXT_SIDE_MARGIN_MM,
)
from utils.page_layout import PAGE_NUMBER_FORMATS as _PAGE_NUMBER_FORMAT_VALUES

# 不允许在表单中配置的键（系统管理：由 runner 按任务/阶段拼装）
EXCLUDED_KEYS = ("input", "output", "workers", "clean", "resume", "_outpath")


def _base(stage: str, **overrides) -> dict:
    """以 command_spec 的同名 defaults 为底，覆盖表单侧特有的键。

    ⚠️ 只在**导入期**调用一次；返回新字典，不会污染 command_spec。
    """
    merged = dict(COMMAND_SPECS[stage].defaults)
    merged.update(overrides)
    return merged


# ---------------------------------------------------------------- 下拉候选表
# 统一格式 ``(中文显示, 参数值)``；取值走 ``itemData()``，不解析显示文本，
# 避免「改一下中文文案就把参数解析弄挂」。

# extract
EXTRACT_EXTS = list(IMAGE_EXTS)

# rembg：area / type 的下拉（显示文本里带序号）
REMBG_AREAS = [
    ("1 (左右分开)", 1),
    ("2 (合并单图)", 2),
    ("3 (整页合并)", 3),
    ("4 (整页/不检测)", 4),
]
REMBG_TYPES = [(f"{v} ({name})", v) for v, name in zip(_REMBG_TYPES, ("二值", "1bit", "灰度"))]

# print
PAPER_SIZES = list(_PAPER_SIZES)
DIRECTIONS = [("横版", "landscape"), ("竖版", "portrait")]
# 页码数字样式：值必须来自 utils.page_layout（那里是唯一定义处），
# 这里只补中文显示名——顺序/取值漂移会直接改变成品页码。
PAGE_NUMBER_FORMATS = [
    ("中文数字（五）", "chinese"),
    ("阿拉伯数字（5）", "arabic"),
    ("干支（甲子，60 循环）", "ganzhi"),
]
assert tuple(v for _, v in PAGE_NUMBER_FORMATS) == _PAGE_NUMBER_FORMAT_VALUES, (
    "页码样式与 utils.page_layout.PAGE_NUMBER_FORMATS 不一致"
)
POSITIONS = [("上边", "top"), ("下边", "bottom")]
TEXT_ORIENTATIONS = [("竖排", "vertical"), ("横排", "horizontal")]
SIDES = [("双面", "both"), ("左页", "left"), ("右页", "right")]

# ---------------------------------------------------------------- 各阶段默认值

# extract：zoom/dpi/quick/ext 全与 CLI 一致；表单把 pages 的 None 显示成空串
EXTRACT_DEFAULTS: dict = _base("extract", pages="")

# detect：表单上没有参数（「整页模式」开关落到第三步的 area=4，参数归 rembg）
DETECT_DEFAULTS: dict = {}

# rembg：与 CLI 一致；表单把 border 的 None 显示成空串
REMBG_DEFAULTS: dict = _base("rembg", border="")

# print：桌面表单默认（比 CLI 更"已开启"：有书名、有页码），
# 唯一事实来源是 core.command_spec.PRINT_FORM_DEFAULTS，此处只做引用。
PRINT_DEFAULTS: dict = dict(PRINT_FORM_DEFAULTS)

# 按阶段名索引的总表（面板用 ``DEFAULTS[self.stage]`` 取用）
DEFAULTS: dict = {
    "extract": EXTRACT_DEFAULTS,
    "detect": DETECT_DEFAULTS,
    "rembg": REMBG_DEFAULTS,
    "print": PRINT_DEFAULTS,
}

# ---------------------------------------------------------- 界面专属初值（非参数）
# 只决定控件的**显示初值**，不进参数——「距页边」输入框即使刚建好也要有个数
# 显示着。⚠️ 它们不是默认参数，别混进 DEFAULTS。
#
# 取值 = 「距页边」的横向默认值（`TEXT_SIDE_MARGIN_MM`，当前 10mm）：
# `reset_to_default()` 立刻会按默认表把每个框填成它该有的值（纵向那个框是
# 跟 page_margins 走的，不是这个数），这里只是让**还没回填的那一瞬间**显示的
# 数与默认一致，避免用户看到 20 再跳成 10（早先这里写死 20.0，与默认 2mm/10mm
# 都对不上，是典型的「同一个值两处各写一份」）。
INSET_SPIN_VIEW_VALUE = float(TEXT_SIDE_MARGIN_MM)


def stage_defaults(stage: str) -> dict:
    """取某阶段的默认参数（副本，可安全改写）。"""
    return dict(DEFAULTS.get(stage) or {})


def default_value(stage: str, key: str, fallback=None):
    """取某阶段某键的默认值；未登记时返回 ``fallback``。

    ⚠️ 默认值可能是 ``None``（如 print 的 ``title_margins``），这里**不做**
    ``or`` 兜底——调用方要区分「默认就是 None」与「没登记」。
    """
    return DEFAULTS.get(stage, {}).get(key, fallback)
