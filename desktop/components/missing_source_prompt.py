# -*- coding: utf-8 -*-
"""**「该上传 PDF 了」提示层**：遮住内容区、留页头与操作按钮可用。

## 为什么不用 qfluentwidgets 的 ``MessageBox``（用户 2026-10-06）

用户看到的是：**遮罩只盖住页面左上角一小块**，流程条（步骤条）没被盖住，
而右上角的操作按钮又在遮罩之外。三条要求：遮罩完整、盖住流程条、**按钮留在
遮罩之上**。

根因在库里：``MaskDialogBase.__init__`` 里那句
``self.setGeometry(0, 0, parent.width(), parent.height())`` **只在构造那一刻取
一次**父控件尺寸。任务详情页刚被切到页面栈里时布局还没定，遮罩就按那个临时
尺寸铺好，之后**再也不跟随后续 resize**（`resizeEvent` 只调整自己的
``windowMask``，不会重算 dialog 的 geometry）——于是就留了那一小块。

但即便把尺寸修对，``MessageBox`` 也满足不了后两条：

1. 它铺满 **parent**（详情页），**没法只盖内容区、留页头**；
2. 它是**模态**的（``exec()``），模态会拦截父窗口内**所有**其它控件的事件——
   按钮就算靠 ``raise_()`` 画在遮罩之上，**也点不动**。

所以这个组件自己搭：遮罩盖「步骤条及其以下」，页头（任务名、红字提示、右上角
那排操作按钮）**留在遮罩之上、照常可点**；整体**非模态**（用 ``show()`` 而非
``exec()``），用户可以一边看提示一边直接点右上角的 PDF 按钮去上传。

## 层次

::

    ┌────────────────────────────────────────────┐
    │ 页头：任务名 / 红字提示 / [改名][流程][图片][目录]│ ← 留在遮罩之上，可点
    ├────────────────────────────────────────────┤
    │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 遮罩（半透明变暗）▓▓▓▓▓▓▓▓▓ │
    │        ┌─────��──────────────────┐          │
    │        │ 提示卡片（居中偏上）      │          │
    │        │ [稍后再说] [选择图片目录]  │          │
    │        └────────────────────────┘          │
    │ 步骤条 / 预览区 / 参数列 / 日志                │ ← 全被盖住、点不到
    └────────────────────────────────────────────┘

⚠️ **点遮罩空白处不关提示**（只是把它吃掉）：用户点内容区多半是**想按某个
按钮**，若那时把提示关掉，他会看到"提示没了、但我想按的那个按钮没反应"——
比"点了没反应"更让人困惑。想关就点卡片上的「稍后再说」，两条路都清楚。
（qfluentwidgets 的 ``MaskDialogBase`` 也是这个默认值：
``self._isClosableOnMaskClicked = False``。）

## 两种「缺输入」（用户 2026-10-06）

提示层**不只服务"缺 PDF"**，还有"**缺入口图片**"——自定义流程把「检测文本框」
之类**不吃 PDF** 的步骤放在第一位时（``stages/input/`` 是它的输入，见
:func:`desktop.steps.ports.resolve_input_with_entry`），用户该被告知的是
"往输入目录放图 / 插图"，而不是"去补 PDF"。所以文案与图标都由宿主
:meth:`configure` 传进来，**组件自己不含任何"缺 PDF"的假设**。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractButton, QGraphicsDropShadowEffect, QHBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, PrimaryPushButton, PushButton, StrongBodyLabel,
)

from desktop import ui
from desktop.ui import theme as T
from desktop.ui.widgets import Card

__all__ = ["DEFAULT_CONTENT", "MissingSourcePrompt"]

#: 提示卡片相对「内容区」竖直方向的位置（0=顶、1=底）。放在偏上而不是正中：
#: 正中会压住预览区正中，而用户第一眼看的是页头提示与右上角按钮。
CARD_TOP_RATIO = 0.12
#: 提示卡片的宽度（px）。与项目其它浮层一致，别做成一条横幅或撑满整行。
CARD_WIDTH = 420

#: 默认文案＝「缺 PDF」这一种。缺入口图片时宿主用 :meth:`MissingSourcePrompt.configure`
#: 换掉（见``manifest.py``的 ``_source_prompt_content``）。
DEFAULT_CONTENT = {
    "title": "这个任务还没有 PDF",
    "body": "当前任务的流程里有「提取图片」这一步，它需要一个 PDF 源文件。\n\n"
            "· 现在选择 → 选完立刻就能开始处理；\n"
            "· 稍后再说 → 右上角那个高亮的 PDF 按钮随时能补上。",
    "hint": "内容区暂时不可操作，页头与右上角按钮照常可用。",
    "later_text": "稍后再说",
    "pick_text": "现在选择",
    #: 主按钮要宿主开哪种对话框：``"files"``＝文件框（缺 PDF 时选一个文件）。
    #: 缺入口图片时宿主会换成 ``"folder"``＝**目录**框（用户 2026-10-06
    #："改成选择图片目录"——一两百页图逐张多选不现实）。
    "pick_kind": "files",
}


class MissingSourcePrompt(QWidget):
    """「这个任务还没有 PDF」的页内提示层（**非模态**）。

    :param parent: 任务详情页（提示层作为它的子控件铺在内容区上）。
    :param area_top_fn: 无参可调用，返回要遮盖区域的**上沿 y**（页内坐标）。
        由宿主给出（步骤条的上沿）——组件自己不知道宿主怎么排的版。
    """

    #: 用户点了主按钮（``"现在选择"``／``"选择图片目录"``…），携带
    #: ``pick_kind``：``"folder"``＝宿主该开**目录**框、``"files"``/空＝文件框。
    #: ⚠️ 带参是因为"选目录"和"选文件"是**两个不同的 QFileDialog 调用**
    #:（``getExistingDirectory`` **选不了目录**，反过来文件框也选不了文件夹），
    #:   组件自己不知道该开哪个——它只是把文案里那份意图（``pick_kind``）传出去。
    picked = Signal(str)
    #: 用户点了「稍后再说」或遮罩空白处（宿主把提示收掉）
    dismissed = Signal()

    def __init__(self, parent, area_top_fn, **content):
        super().__init__(parent)
        self._area_top_fn = area_top_fn
        #: 宿主传进来的文案（见 :meth:`configure` 的默认值说明）
        self._content = dict(DEFAULT_CONTENT)
        self._content.update(content)
        self.setObjectName("missingSourcePrompt")
        # ⚠️ 非模态：右上角那排按钮要照常可点（模态会把它们的事件全吃掉）。
        #   提示层只是"盖住 + 变暗"，不接管交互。
        self.setWindowModality(Qt.WindowModality.NonModal)
        # 盖在兄弟控件之上；不抢焦点（用户不该被强行打断当前操作）
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet(_mask_style())
        self._build_card(parent)
        self._reanchor()

    # ------------------------------------------------------------------ 构建
    def _build_card(self, page) -> None:
        """提示卡片：标题 + 说明 + 两个按钮。"""
        self.card = Card(parent=self)
        self.card.setFixedWidth(CARD_WIDTH)
        # ⚠️ **必须用 ``card.box``**（``Card`` 自己在 ``__init__`` 里已经建了
        #    ``QVBoxLayout(self)``）。再 ``QVBoxLayout(self.card)`` 建第二个会
        #    被 Qt 忽略（"already has a layout"），加进去的控件**一个都留不下**
        #    ——表现是卡片空成 32×32 的一条白条，文字全被裁掉。
        col = self.card.box
        col.setContentsMargins(
            T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        col.setSpacing(T.SPACE_MD)

        title = StrongBodyLabel(self._content["title"])
        ui.apply_to(title, T.SIZE_SUBTITLE, bold=True, color=T.INK)
        self.title_label = title
        col.addWidget(title)

        text = BodyLabel(self._content["body"])
        ui.apply_to(text, T.SIZE_BODY, color=T.INK_SOFT)
        text.setWordWrap(True)
        self.body_label = text
        col.addWidget(text)

        hint = CaptionLabel(self._content["hint"])
        ui.apply_to(hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        hint.setWordWrap(True)
        self.hint_label = hint
        col.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch()
        self.later_button = PushButton(self._content["later_text"])
        self.later_button.clicked.connect(self.dismiss)
        row.addWidget(self.later_button)
        self.pick_button = PrimaryPushButton(self._content["pick_text"])
        self.pick_button.clicked.connect(self._on_pick)
        row.addWidget(self.pick_button)
        col.addLayout(row)

        # ⚠️ **投影**：遮罩是半透明白，卡片也是白底，不给阴影它就"糊"在遮罩
        #    里看不出边界（第一版没加，出图只看到一条白条还以为卡片没渲染）。
        # ⚠️ 留着局部变量再用：``graphicsEffect()`` 的注解是 QGraphicsEffect
        # （| None），而 setBlurRadius/setOffset/setColor 是
        # QGraphicsDropShadowEffect 才有的 API——写局部变量既让类型检查器
        # 看得见真类型，也省掉三次取属性。
        shadow = QGraphicsDropShadowEffect(self.card)
        self.card.setGraphicsEffect(shadow)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 60))
        # ⚠️ 过滤器**只装在卡片上**，且只对"按在空白处"生效（见 eventFilter 的
        #    警告：装到按钮上会��按钮点不动）。
        self._drag_pos = QPoint()
        self.card.installEventFilter(self)

    # ------------------------------------------------------------------ 几何
    def _reanchor(self) -> None:
        """按宿主当前尺寸与上沿重铺（遮罩 + 卡片位置）。

        ⚠️ 宿主每次 ``set_task`` / ``resize`` / ``showEvent`` 都要调一次：库里
        的 ``MessageBox`` 就是**只在构造时**取一次 ``parent.width()`` 才出的
        问题（遮罩留在一个临时尺寸上、再也不跟随），我们不能重犯。

        ⚠️⚠️ **布局未就绪时宁可什么都不铺**（用户 2026-10-06 报"第一次进入
        没有弹窗"）：宿主第一次 ``set_task`` 跑在 ``setCurrentWidget`` **之前**，
        页面尺寸还是 QWidget 默认的 ``640x480``、``area_top_fn`` 返回的是布局
        没跑时的垃圾值（实测 491）。直接铺会得到 ``(0, 491, 640, 0)``——**高度
        0**的遮罩，看着就是"压根没弹"，而且它已经 ``show()`` 过了，后面没人
        再纠正（``resizeEvent`` 原本还用 ``isVisible()`` 拦，见该方法说明）。
        改成：上沿大到不像话（超过页面高度的 60%）就**放弃这一次**，等
        ``showEvent`` 来铺。
        """
        page = self.parentWidget()
        if page is None:
            return
        top = int(self._area_top_fn() or 0)
        if top < 0 or (page.height() > 0 and top > page.height() * 0.6):
            # 布局还没定：这次不铺（show_prompt 会紧接着 show()，几何是旧的，
            # 但showEvent 会来纠正；这里只是别主动写一个错的上去）。
            return
        # 遮罩只盖「内容区」：上沿往下、左右到底。**页头留出来**——
        # 红字提示与那排操作按钮要看得见、按得动。
        self.setGeometry(0, top, page.width(), max(0, page.height() - top))
        self.card_host_center()

    def configure(self, **content) -> None:
        """改文案（宿主在 :meth:`show_prompt` 之前调）。

        ⚠️ 组件**不持有**任何"缺 PDF"的假设——两种缺输入（缺 PDF / 缺入口图片）
        的说法完全不同，写死一份就必然有一半场景在说错话。
        ⚠️ 改完必须让卡片**重新按宽度算高度**：正文长度变了，高度会变，
        旧高度会把文字裁掉（用户报过"文字显示不完整"）。
        """
        self._content.update(content)
        self.title_label.setText(self._content["title"])
        self.body_label.setText(self._content["body"])
        self.hint_label.setText(self._content["hint"])
        self.later_button.setText(self._content["later_text"])
        self.pick_button.setText(self._content["pick_text"])
        self.card_host_center()

    def card_host_center(self) -> None:
        """把卡片摆好：宽度固定、**高度按换行后的实际需要**、水平居中偏上。

        ⚠️⚠️ 高度**必须用 ``heightForWidth``**，不能用 ``sizeHint``/``adjustSize``：
        正文是 ``setWordWrap(True)`` 的标签，``sizeHint`` 给的是**未换行**的
        高度，按它摆卡片 ⇒ 文字被裁掉一截（用户截图：第二段只露上半行）。
        实测差 30px（181 vs 211）。

        ⚠️ 也别再套一层"装卡片的中层容器 + addStretch"：带 stretch 的布局
        ``sizeHint`` 更算不准，第一版就这样把卡片压成一条 20px 的白条。
        """
        w = CARD_WIDTH
        self.card.setFixedWidth(w)
        self.card.box.activate()
        need = self.card.heightForWidth(w)
        if need <= 0:                      # 布局给不出就退回 sizeHint
            need = self.card.sizeHint().height()
        h = max(need, self.card.sizeHint().height())
        self.card.setGeometry(
            max(0, (self.width() - w) // 2),
            int(self.height() * CARD_TOP_RATIO), w, h,
        )

    def show_prompt(self) -> None:
        """显示并重铺（每次显示前都重铺，尺寸可能早变了）。"""
        self._reanchor()
        self.card_host_center()
        self.show()
        self.raise_()

    # ------------------------------------------------------------------ 动作
    def _on_pick(self) -> None:
        """主按钮：先收掉提示层，再把「要哪种对话框」告诉宿主。

        ⚠️ **顺序要紧**：提示层是宿主的孩子，不先 ``hide`` 就去开模态文件框，
        遮罩会盖在文件对话框上面（两个模态叠在一起，用户看到"点了没反应"）。
        """
        self.dismiss()
        self.picked.emit(str(self._content.get("pick_kind") or ""))

    def dismiss(self) -> None:
        """「稍后再说」/ 点遮罩：收掉提示层并通知宿主。"""
        was_visible = self.isVisible()
        self.hide()
        if was_visible:
            self.dismissed.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """遮罩把点击**吃掉**（不关提示，也不透给底下的控件）。

        ⚠️ 为什么不"点遮罩 = 稍后再说"：用户点内容区通常是**想按某个按钮**，
        那里把提示关掉会造成"提示没了、按钮也没反应"——比单纯"点了没反应"
        更让人困惑（他以为自己已经关掉了提示，于是又点一次）。关提示只有
        卡片上那一个入口（「稍后再说」），语义单一不歧义。
        """
        event.accept()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt 命名
        """卡片**空白处**的按下/拖动/抬起；按钮与文字一概不碰。

        ⚠️⚠️ **绝不能把过滤器装到按钮上再吞所有 MouseButtonPress**（我第一版
        这么干，结果「现在选择」「稍后再说」两个按钮**点了没反应**——事件在
        到达按钮之前就被自己的过滤器吃掉了，``QAbstractButton`` 收不到
        press 就不可能发 clicked）。现在只在 ``self.card`` 上按**空白处**
        （``childAt`` 为空——QLabel 默认忽略鼠标，事件会落到卡片）才接管，
        用于拖动；按钮上的事件原样放行。

        吞掉空白处的按下还有一个作用：不让它冒到遮罩去（遮罩的
        ``mousePressEvent`` 只 ``accept``，不会关提示，但也不该让卡片区
        的按下看起来像"按在遮罩上"）。
        """
        if watched is not self.card:
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind == event.Type.MouseButtonPress:
            # ⚠️ 判据是"这里是不是**按钮**"，**不能**用 ``childAt(...) is None``：
            #    卡片上有说明文字标签，``childAt`` 会返回它（``QLabel`` 默认
            #    接受鼠标事件、只是事件本身 ignore），于是"空白处"永远判不成立、
            #    拖动完全失效（我踩过一次）。按钮要留给按钮自己处理。
            child = self.card.childAt(event.pos())
            if not isinstance(child, QAbstractButton):
                self._drag_pos = event.pos()
                return True
            return super().eventFilter(watched, event)
        if kind == event.Type.MouseMove:
            if not self._drag_pos.isNull() and (
                    event.buttons() & Qt.MouseButton.LeftButton):
                self._move_card(event.pos() - self._drag_pos)
                return True
            return super().eventFilter(watched, event)
        if kind == event.Type.MouseButtonRelease:
            self._drag_pos = QPoint()
            return super().eventFilter(watched, event)
        return super().eventFilter(watched, event)

    def _move_card(self, delta) -> None:
        """把卡片按 ``delta`` 移动，并**夹在提示层范围内**（别拖出可视区）。"""
        w, h = self.card.width(), self.card.height()
        x = max(0, min(self.card.x() + delta.x(), max(0, self.width() - w)))
        y = max(0, min(self.card.y() + delta.y(), max(0, self.height() - h)))
        self.card.move(x, y)


def _mask_style() -> str:
    """遮罩底色：浅色主题铺半透明白、深色铺半透明黑（与 qfluentwidgets 一致）。

    ⚠️ 深浅判据用**画布色的亮度**算，而不是列一份"哪些色算深色"的白名单——
    改一次主题色这里的判断就跟着走，不会悄悄错色。
    """
    r, g, b = (int(T.CANVAS[i:i + 2], 16) for i in (1, 3, 5))
    dark = (0.299 * r + 0.587 * g + 0.114 * b) < 140
    return f"background: rgba({'0, 0, 0' if dark else '255, 255, 255'}, 0.55);"
