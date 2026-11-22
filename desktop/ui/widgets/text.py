# -*- coding: utf-8 -*-
"""字体/颜色与文本类基础控件（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

from qfluentwidgets import FluentLabelBase

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font

from ._qt import QColor, QLabel, QPainter, QRectF, QWidget, Qt

def apply_to(
    widget: QWidget,
    size: int = T.SIZE_BODY,
    bold: bool = False,
    color: str | None = None,
) -> QWidget:
    """给控件统一设置字体与颜色（返回原控件，便于链式书写）。

    ⚠️ **上色有两条路，按控件类型分流**：

    - qfluentwidgets 的标签（``FluentLabelBase`` 子类：CaptionLabel / BodyLabel /
      StrongBodyLabel / TitleLabel / SubtitleLabel）**不读调色板**——它们用
      ``setStyleSheet("color: …")`` 自己画（``setTextColor``）。对它们只 ``setPalette``
      的话调色板里明明写着红色、**渲染出来仍是黑的**（2026-09-23 用户报「这个红色
      没有修改过来」就是这么来的）。所以必须走 ``setTextColor``。
    - 原生 ``QLabel`` 仍走调色板（原来的做法；对它用样式表反而会牵连子控件，
      见模块头那段"样式表会把 QFrame 底色刷白"的教训）。

    判据用 ``isinstance`` 而不是 ``hasattr(widget, "setTextColor")``：
    ``QTextEdit`` 也有同名方法，但它设的是"以后输入的文字颜色"，语义完全不同。
    """
    widget.setFont(ui_font(size, bold))
    if color:
        if isinstance(widget, FluentLabelBase):
            widget.setTextColor(QColor(color))
        else:
            palette = widget.palette()
            palette.setColor(widget.foregroundRole(), QColor(color))
            widget.setPalette(palette)
    return widget


def bold_button(button: QWidget, bold: bool) -> None:
    """把按钮文字加粗 / 还原（高亮用）。

    ⚠️ **别用 ``setStyleSheet("…{font-weight:bold;}")`` 干这件事**：qfluentwidgets
    给每个按钮的样式表是**整串 setStyleSheet 进去的**（约 7.6KB），里面有一条
    ``PushButton[hasIcon=true] { padding: 5px 12px 6px 36px; }`` —— 图标是
    ``paintEvent`` 手绘在左边 12px 处的，**全靠这 36px 左边距让居中的文字让开**。
    整串替换后 padding 全没了，图标就画到文字上了（2026-09-23 用户报
    「执行本步骤按钮中的图片显示在了文字上面」）。``setFont`` 只动字体，
    不碰样式表；按钮 qss 里没有 ``font:`` 规则，所以控件字体生效。
    """
    font = button.font()
    font.setBold(bold)
    button.setFont(font)


def mark_input_entry(button: QWidget) -> None:
    """给「给这一步喂图片」这类**输入入口**按钮加**常驻红框**。

    用户 2026-10-06："右上角的选择图片还可以选择目录，都是红色框住"、
    "左下角输入图片和目录也用红色框住"。红框的作用是**标识入口**（一眼找到
    该点哪儿喂图片），所以是**常驻**的，不随"缺不缺输入"变。

    ⚠️ **别和"缺输入才亮"的那套高亮混用**：详情页
    ``manifest._set_tool_highlight`` 是**动态**的（补上文件就灭），两套样式
    互相覆盖——动态那套灭的时候会把常驻红框一起抹掉。同一个按钮上**只能**
    选一套：要"入口标识"用本函数，要"缺什么提醒"用 ``_set_tool_highlight``。

    ⚠️ 用样式表而不是换 ``PrimaryPushButton``：那会让这一排工具按钮的
    **尺寸**变掉（文字按钮比图标按钮宽），把页头撑变形（同 ``bold_button``）。
    """
    from desktop.ui import theme as T

    button.setStyleSheet(
        f"ToolButton {{ border: 1.5px solid {T.DANGER};"
        f" border-radius: 6px; background-color: {T.DANGER_SOFT}; }}"
        f"ToolButton:hover {{ background-color: {T.DANGER_SOFT}; }}"
    )



class SectionTitle(QLabel):
    """控制面板里的分组小标题（比正文略重，前面带一条主色短竖线）。

    所有步骤面板的「小分类/分块标题」统一走这一个组件（用户 2026-11-16：
    「参考检测文本框的『识别文本框模式』这种风格样式，只是文字要大一些」）
    ——字号用 ``SIZE_LABEL``（14px，比正文大一号），别再各自用
    ``StrongBodyLabel`` 之类的另起一套。
    """

    def __init__(self, text: str, parent=None):
        """左侧预留 10px 给主色竖线，控件固定高 24px。"""
        super().__init__(text, parent)
        self.setFont(ui_font(T.SIZE_LABEL, bold=True))
        # 左侧留出 10px 给主色短竖线
        self.setContentsMargins(10, 0, 0, 0)
        self.setFixedHeight(24)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(T.ACCENT))
        painter.drawRoundedRect(QRectF(0, 5, 3, 14), 1.5, 1.5)
        super().paintEvent(event)
