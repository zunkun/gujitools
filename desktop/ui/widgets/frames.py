# -*- coding: utf-8 -*-
"""卡片、面板、分隔线与红色虚线框（自 ``desktop/ui/widgets.py`` 拆出）。"""

from __future__ import annotations

from desktop.ui import theme as T

from ._qt import (
    QColor,
    QEvent,
    QFrame,
    QHBoxLayout,
    QPainter,
    QPen,
    QRect,
    QRectF,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    Qt,
)

class RedDashFrame(QWidget):
    """控件外围的**红色虚线框**（鼠标穿透）：圈出"当前该做而没做的动作"。

    谁在用（用户 2026-10-13）：第三步「提交本次任务」**预览成功但未提交**、
    拼版面板「在流程中启用图片拼版」**可勾但没勾且左侧有可拼图**。

    ⚠️ 是**覆盖层**而不是样式表：qfluent 按钮的 qss 是整串 setStyleSheet
    进去的，再 setStyleSheet 会把它抹掉（见 :func:`bold_button` 的说明）；
    覆盖层只画框，控件本体分毫不动。
    ⚠️ 框**不贴身**（用户 2026-10-13：「线框高一些，不要紧贴着」）：四周
    外扩 :data:`PAD` px。宿主**不是**无脑取直接父控件——按钮行那种布局
    容器高度==控件高度，外扩后整个落在父控件边界外会被**裁剪得一行不剩**
    （提交按钮的框"不显示"就是它）。:meth:`refit` 会沿祖先链向上找**第一个
    装得下外扩框**的祖先当宿主；正常都停在滚动内容层里，随内容一起滚动
    不会漂。
    ⚠️ ``WA_TransparentForMouseEvents``：框不挡任何点击。

    ⚠️ **要盯着整条祖先链，不能只盯目标**（用户 2026-10-23 报「切步骤节点
    返回后，提交按钮的红框定位不准确」）：提交按钮在「检测文本框 + 提交本次
    任务」那一行里，**行本身**被父布局整体搬走后，按钮相对行没变 ⇒ 它收不到
    Move，而框的宿主是行之上的祖先（紧身行装不下外扩框）⇒ 框停在旧位置。
    提示行显隐（实测差 24px）、切步骤重排都会触发这条。所以这里在目标**和
    它到窗口的整条祖先链**上装过滤器，任何一环挪动/缩放/显隐/布局失效都重适配。
    同理，祖先被隐藏时框也必须跟着隐藏，否则会浮在别的步骤面板上（拼版伪
    步骤整组藏掉执行按钮行，就是这种残留）。
    """

    #: 框沿到控件边缘的呼吸间距（px）
    PAD = 5

    #: 需要重适配的事件：祖先链上任何一环发生这些变化，目标相对宿主的坐标
    #: 都可能变（目标自己常常收不到 Move——它是被父布局整体搬走的）。
    _REFIT_EVENTS = frozenset((
        QEvent.Type.Move,
        QEvent.Type.Resize,
        QEvent.Type.Show,
        QEvent.Type.Hide,
        QEvent.Type.LayoutRequest,
        QEvent.Type.ParentChange,
    ))

    def __init__(self, target: QWidget):
        super().__init__(None)  # 顶层裸控件，宿主由 :meth:`refit` 现场挑
        self._target = target
        #: 业务上"该亮"（与真实可见性分开：祖先隐藏时先藏起来，回来后恢复）
        self._wanted = False
        #: 已装过滤器的对象（目标 + 祖先链，含窗口）
        self._watched: list[QWidget] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._watch_chain()

    # ---------------------------------------------------------- 事件监视
    def _watch_chain(self) -> None:
        """在**目标 + 它到窗口的整条祖先链**上装事件过滤器（幂等）。"""
        chain: list[QWidget] = []
        widget: QWidget | None = self._target
        while widget is not None:
            chain.append(widget)
            if widget.isWindow():
                break
            widget = widget.parentWidget()
        for old in self._watched:
            if old not in chain:
                try:
                    old.removeEventFilter(self)
                except RuntimeError:  # 已销毁的控件（C++ 对象已释放）
                    pass
        for item in chain:
            if item not in self._watched:
                item.installEventFilter(self)
        self._watched = chain

    def eventFilter(self, obj, event):  # noqa: N802 - Qt 命名
        if event.type() in self._REFIT_EVENTS and any(
            obj is item for item in self._watched
        ):
            if obj is self._target and event.type() == QEvent.Type.ParentChange:
                self._watch_chain()
            self._sync()
        return super().eventFilter(obj, event)

    # ---------------------------------------------------------- 显隐/定位
    def set_wanted(self, on: bool) -> None:
        """业务侧要求"亮/灭"：亮时按目标当前可见性决定是否真的显示。"""
        self._wanted = bool(on)
        self._sync()

    def _sync(self) -> None:
        """把"该亮 + 目标真的可见"落实成显示/隐藏并重算位置。"""
        if not self._wanted or not self._target.isVisible():
            self.hide()
            return
        self.refit()
        self.raise_()
        if not self.isVisible():
            self.show()

    def refit(self) -> None:
        """外扩 :data:`PAD` 重摆自己；沿祖先链找第一个装得下的宿主。"""
        target = self._target
        pad = self.PAD
        parent = target.parentWidget()
        if parent is None:
            # 兜底：控件没有父控件（顶层窗口）→ 贴自身 rect 画
            self.setParent(target)
            self.setGeometry(target.rect())
            self.raise_()
            return
        # 控件 rect 在直接父控件坐标系里的形态，向上爬时逐级换算
        rect = QRect(
            target.mapTo(parent, target.rect().topLeft()),
            target.mapTo(parent, target.rect().bottomRight()),
        )
        host, host_rect = parent, rect
        while True:
            inflated = host_rect.adjusted(-pad, -pad, pad, pad)
            if host.isWindow() or host.rect().contains(inflated):
                break
            grand = host.parentWidget()
            if grand is None:
                break  # 理论不可达（无父控件即 isWindow），保守退出
            host_rect = QRect(
                host.mapTo(grand, host_rect.topLeft()),
                host.mapTo(grand, host_rect.bottomRight()),
            )
            host = grand
        if self.parentWidget() is not host:
            self.setParent(host)
        self.setGeometry(inflated)
        self.raise_()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(
            QPen(
                QColor(T.DANGER), 1.8, Qt.PenStyle.DashLine,
                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(0.9, 0.9, self.width() - 1.8, self.height() - 1.8),
            T.RADIUS_SM, T.RADIUS_SM,
        )
        painter.end()


def set_red_frame(target: QWidget, on: bool) -> None:
    """给控件挂上/摘掉 :class:`RedDashFrame`（幂等；重复调用不重建控件）。

    ⚠️ 覆盖层挂在控件的**父控件**上（外扩画框），所以引用**不能**走
    ``target.findChild``（只搜子孙搜不到），钉在控件的动态属性里。
    摘掉只是 ``hide()``：控件留着，下次要亮直接 show，省一次构造。

    ⚠️ **另存一份 Python 强引用**（``_red_dash_frame_ref``）：动态属性里只
    留 C++ 指针，Python 包装器一旦被回收，再 ``property()`` 取回的就成了
    基类 ``QObject``（没有 ``set_wanted``/``isVisible``，自测当场炸过）。
    """
    frame = getattr(target, "_red_dash_frame_ref", None)
    if not isinstance(frame, RedDashFrame):
        frame = None
        stored = target.property("_red_dash_frame")
        if isinstance(stored, RedDashFrame):
            frame = stored
    if on:
        if frame is None:
            frame = RedDashFrame(target)
            target.setProperty("_red_dash_frame", frame)
            # 强引用保活；走 setattr 是为了不把动态属性写进 QWidget 的类型面
            setattr(target, "_red_dash_frame_ref", frame)
        frame.set_wanted(True)
    elif frame is not None:
        frame.set_wanted(False)



class Card(QFrame):
    """白底圆角卡片，可选描边与内边距。"""

    def __init__(
        self,
        parent=None,
        padding: int = T.SPACE_LG,
        spacing: int = T.SPACE_MD,
        radius: int = T.RADIUS_LG,
        fill: str = T.SURFACE,
        border: str = T.BORDER,
        layout: str = "v",
    ):
        """
        layout="v"/"h" 选择内部盒方向；padding 同时作为四边内边距。

        内部布局通过 ``self.box`` 暴露，调用方直接往里加控件。
        """
        super().__init__(parent)
        self._fill = QColor(fill)
        self._border = QColor(border) if border else None
        self._radius = radius
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        box = QVBoxLayout(self) if layout == "v" else QHBoxLayout(self)
        box.setContentsMargins(padding, padding, padding, padding)
        box.setSpacing(spacing)
        self.box = box

    def set_colors(self, fill: str | None = None, border: str | None = None) -> None:
        """改底色/描边后立即重绘；传 None 表示该项保持不变。"""
        if fill is not None:
            self._fill = QColor(fill)
        if border is not None:
            self._border = QColor(border)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(self._fill)
        if self._border is not None:
            painter.setPen(QPen(self._border, 1))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, self._radius, self._radius)


class SurfacePanel(QWidget):
    """白底容器：自己铺一层卡片白（``T.SURFACE``），用来盖住底色漏色。

    为什么要自绘：参数面板把表单塞进 ``ScrollArea``，滚动区的 viewport 会刷
    一层系统窗口灰（``#EFEFEF``），铺在白卡片上就是一块突兀的"灰砖"。
    qfluent 的 ``enableTransparentBackground()`` 帮不上忙——它必须在
    ``setWidget()`` **之后**调用才作用到内容上，而且靠样式表接管整棵子树，
    会把输入框一起刷成透明；``setPalette`` + ``autoFillBackground`` 也不行
    （样式表 polish 时调色板会被重置回系统灰）。自绘不受这两条影响，也符合
    本模块「基础视觉控件自绘、不靠样式表」的约定。
    """

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(T.SURFACE))


class Divider(QFrame):
    """水平分隔线（默认 1px）。"""

    def __init__(self, parent=None, color: str | None = None,
                 thickness: int = 1):
        """固定高、水平拉伸的水平分隔线。

        ``color`` 缺省用最淡的 ``BORDER_SOFT``（好当"同一组里的轻分隔"）；
        需要一眼看出"这是两段"时传 ``T.BORDER_STRONG`` 并给 ``thickness``。
        参数面板里**不再用它分「识别文本框 / 本页参数」**——用户 2026-11-16
        说那条深色横线"太深、太宽"，改用固定高度的空白行（见
        ``panels/detect_panel.py``）。
        """
        super().__init__(parent)
        self._color = color or T.BORDER_SOFT
        self.setFixedHeight(max(1, int(thickness)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._color))
