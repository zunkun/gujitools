# -*- coding: utf-8 -*-
"""界面设计令牌：颜色、间距、圆角、字号。

全应用只在这里定义视觉常量，页面/组件一律引用这里的名字，避免出现
"这里 #E5E9F0、那里 #EEF1F4" 的散落色值。换算关系（Fluent 基准）:

- 间距按 4 的倍数：XS=4 / SM=8 / MD=12 / LG=16 / XL=24
- 圆角三档：控件 6、卡片 10、大容器 14
- 文本三级：正文 INK、次要 INK_SOFT、辅助/占位 INK_FAINT
"""

from __future__ import annotations

from utils.fonts import cjk_font_families

# ---------------------------------------------------------------- 中性色
INK = "#1A1D21"           # 正文
INK_SOFT = "#4E5862"      # 次要说明
INK_FAINT = "#8B949D"     # 辅助信息 / 占位符
INK_DISABLED = "#B7BEC5"

CANVAS = "#F3F5F7"        # 窗口底色
SURFACE = "#FFFFFF"       # 卡片
SURFACE_SOFT = "#F7F9FB"  # 次级面：表头、代码块、空状态
SURFACE_HOVER = "#EEF3F6"  # 悬停
SURFACE_SUNKEN = "#E4EAEF"  # 内凹底：分段开关轨道等「容器槽」
BORDER = "#E2E7EC"        # 常规描边
BORDER_SOFT = "#EDF1F4"   # 分隔线
BORDER_STRONG = "#C9D1D8"  # 浮层/悬浮面板描边（需要压过底下卡片时用）

# ---------------------------------------------------------------- 语义色
ACCENT = "#0E7C8B"        # 主色（深青，古籍纸张 + 靛青的取色）
ACCENT_HOVER = "#0B6A77"
ACCENT_SOFT = "#E6F2F4"   # 主色浅底
SUCCESS = "#0F7B3F"
SUCCESS_SOFT = "#E7F4EC"
WARNING = "#B9760A"
WARNING_SOFT = "#FBF2E2"
DANGER = "#C93A3A"
DANGER_HOVER = "#B03333"    # 危险按钮悬停（比 DANGER 深一档）
DANGER_PRESSED = "#962B2B"  # 危险按钮按下（再深一档）
DANGER_SOFT = "#FBEAEA"
NEUTRAL = "#7A838C"
NEUTRAL_SOFT = "#EFF2F4"

# 阶段状态 → (强调色, 浅底色) —— 步骤条、状态胶囊、列表统一取这里
STATUS_COLORS = {
    "pending": (NEUTRAL, NEUTRAL_SOFT),
    "running": (ACCENT, ACCENT_SOFT),
    "success": (SUCCESS, SUCCESS_SOFT),
    "failed": (DANGER, DANGER_SOFT),
    "cancelled": (WARNING, WARNING_SOFT),
    "draft": (NEUTRAL, NEUTRAL_SOFT),
    "completed": (SUCCESS, SUCCESS_SOFT),
}

STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
    "draft": "未开始",
    "completed": "已完成",
}


def status_colors(status: str) -> tuple[str, str]:
    """状态 → (前景色, 底色)，未知状态按未执行处理。"""
    return STATUS_COLORS.get(status, STATUS_COLORS["pending"])


def status_label(status: str) -> str:
    """状态键 → 中文短标签，未知或空状态回退到"未知"。

    取值来自 STATUS_LABELS（如 "running"→"执行中"）。
    """
    return STATUS_LABELS.get(status, status or "未知")


# ---------------------------------------------------------------- 间距/圆角
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14

# ---------------------------------------------------------------- 滚动条
SCROLLBAR_WIDTH = 10        # 纵向滚动条宽度 / 横向滚动条高度
SCROLLBAR_MARGIN = 2        # 滚动条与容器边缘的留白

# ---------------------------------------------------------------- 字体
# ⚠️ 候选字体族只此一份：按平台从 `utils.fonts.cjk_font_families()` 派生。
# 曾经这里写死 Windows 的 Microsoft YaHei UI + 三个 fallback，换平台后
# Linux/macOS 上一个都命中不了 → 整个界面落到无衬线默认字体，中文好不好看
# 全凭运气。resolve_font_family() 会取第一个系统里真实存在的族。
_CJK_FAMILIES = cjk_font_families()
FONT_FAMILY = _CJK_FAMILIES[0]
FONT_FALLBACK = tuple(_CJK_FAMILIES[1:])

SIZE_CAPTION = 12   # 辅助说明
SIZE_BODY = 13      # 正文/表格
SIZE_LABEL = 14     # 表单标签
SIZE_SUBTITLE = 16  # 分区标题
SIZE_TITLE = 22     # 页面标题
SIZE_HERO = 26      # 数字强调
