# -*- coding: utf-8 -*-
"""共用「大输入区」：拖拽 / 点选，把**文件或文件夹**交给一个步骤。

用户 2026-10-02 的要求（原话）：

> 你就在左侧这些目录点上去，页面上有一个大的输入框，可以输入图片和输入文件，
> 或者输入目录，也可以把文件拖进去，目录投进去。

于是有了这一块：**一个控件同时承担"选择"和"放下"两件事**，三条入口都通——

1. 拖**文件**进来；
2. 拖**文件夹**进来（含图片/PDF 的目录）；
3. **点一下**从对话框里选（``accepts_dir`` 为真时先问"选文件还是选文件夹"）。

它是 :mod:`desktop.steps` 层的一部分，所以左侧三个模块与任务流程**共用同一份
实现**——这正是用户要的"抽成公共组件、定义好入口/出口 API"。

设计要点（改之前先读）：

- **只管"用户给了哪些路径"，不管"这算不算合法输入"**。归一化（一堆文件/文件夹
  → 一个"源"）由 :meth:`desktop.steps.spec.StepSpec.resolve_source` 负责，
  那是纯逻辑、可以脱离 Qt 单测；本控件只把原始路径经 ``paths_chosen`` 发出去。
  这样"拼图"这种要整份清单的调用方也能直接复用本控件。
- **自绘**（项目规矩：基础控件一律 ``paintEvent``，不引样式表）：两种形态——
  空态是大块（图标 + 两行提示），已选态收窄成一行（图标 + 名字 + 路径 + 清空）。
- **拖拽热区**：拖到控件上（或宿主页面上，见 ``ModulePage``）时描边与底色变主色，
  给"松手就放这儿"的反馈。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFileDialog, QWidget
from qfluentwidgets import FluentIcon as FIF, Theme

from desktop.steps.spec import StepSpec
from desktop.ui import theme as T
from desktop.utils.files import default_open_dir

#: 空态高度（px）：要"大"，一眼看出这里是主入口
EMPTY_HEIGHT = 132
#: 已选态高度（px）：收窄成一行，把纵向空间还给预览
FILLED_HEIGHT = 74
#: 空态图标盒子边长（px）
ICON_BOX = 30
#: 清空按钮的点击盒边长（px）
CLOSE_BOX = 26
#: 内容与虚框的左右留白（px）
PAD = T.SPACE_LG


class SourceZone(QWidget):
    """一个步骤的**大输入区**：拖入 / 点选文件或文件夹（自绘，可清空）。

    信号：

    - ``paths_chosen(list)``：用户拖入或选中了一批路径（``list[str]``，**原始**，
      未做任何合法性判断）；空拖拽不会发。
    - ``cleared()``：用户点了右上角的清空。
    - ``rejected(str)``：拖进来的东西一件都用不了（一句给用户看的话）。
      调用方通常转成页头的 toast/状态行。

    显示与语义分离：``set_source()`` 只负责"把现在选中的源画出来"，不发信号，
    因此宿主（:class:`~desktop.steps.control.StepControl`）说了算——它才是
    "文件/目录 → 一个源"的归一化权威。
    """

    paths_chosen = Signal(list)
    cleared = Signal()
    rejected = Signal(str)

    def __init__(self, spec: StepSpec, parent=None):
        """按 ``spec`` 取文案/图标/过滤串；初始为空态。"""
        super().__init__(parent)
        self.spec = spec
        self._source: Path | None = None
        self._detail = ""
        self._hot = False        # 有东西正拖在本控件上方
        self._hover = False      # 鼠标悬停
        self._close_rect = QRectF()
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(260)
        self._sync_height()
        self.setToolTip(self._hint_text())

    # ------------------------------------------------------------------ 对外
    def source(self) -> Path | None:
        """当前**显示**的源（宿主设进来的；未设为 ``None``）。"""
        return self._source

    def set_source(self, path: Path | str | None, detail: str = "") -> None:
        """把"当前源"画出来（不发 ``paths_chosen``，避免与宿主来回打环）。

        ``path=None`` 回到空态；``detail`` 是已选态的第二行小字（如"文件夹 ·
        12 个文件"），留空时按路径自动生成。
        """
        self._source = Path(path) if path else None
        self._detail = detail or self._auto_detail(self._source)
        self._sync_height()
        self.setToolTip(self._hint_text())
        self.update()

    def offer(self, paths) -> None:
        """把一批路径当作用户给的输入送出去（拖拽/点选/宿主转发都走这里）。

        空列表不进主流程（避免下游收到"什么都没有"的信号），改为发一条
        ``rejected`` 让界面说话。
        """
        cleaned = [str(p) for p in (paths or []) if str(p or "").strip()]
        if not cleaned:
            self.rejected.emit("没有拿到可用的文件或文件夹")
            return
        self.paths_chosen.emit(cleaned)

    def set_hot(self, hot: bool) -> None:
        """外部（宿主页面的整页拖拽）切换"正在拖入"高亮。"""
        if self._hot != bool(hot):
            self._hot = bool(hot)
            self.update()

    def clear(self) -> None:
        """清空当前源并发 ``cleared``（点右上角 ✕ 与宿主主动复位走同一条）。"""
        self.set_source(None)
        self.cleared.emit()

    def busy_lock(self, locked: bool) -> None:
        """执行中禁用（拖拽也不收），并保持当前画面。"""
        self.setEnabled(not locked)

    # ------------------------------------------------------------ 拖 / 点 / 键
    @staticmethod
    def paths_from_mime(mime) -> list[str]:
        """从拖拽数据里取**本地**路径（URL 形式的文件/文件夹，非本地的丢掉）。

        单独抽成 staticmethod 是为了能直接单测——不用去合成 Qt 拖拽事件。
        """
        if mime is None or not mime.hasUrls():
            return []
        found: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            local = url.toLocalFile()
            if local:
                found.append(local)
        return found

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """有东西拖上来：认得本地文件/文件夹就收，并亮起来。"""
        paths = self.paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        self.set_hot(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖拽移动中：保持接受（Qt 要求显式接受才会给 drop）。"""
        if self.paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖出控件：熄灭高亮。"""
        self.set_hot(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """松手放下：把原始路径交给宿主。"""
        paths = self.paths_from_mime(event.mimeData())
        self.set_hot(False)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.offer(paths)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """鼠标进来：底色淡一档（可点的暗示）。"""
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """鼠标离开：恢复底色。"""
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """回车/空格 = 点一下（键盘可达）。"""
        if event.key() in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space,
        ):
            self._browse_soon()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """点清空按钮 = 清空；点别处 = 选文件/文件夹。"""
        if (
            self._source is not None
            and self._close_rect.contains(event.position())
        ):
            self.clear()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._browse_soon()
            event.accept()
            return
        super().mousePressEvent(event)

    def _browse_soon(self) -> None:
        """把"弹对话框"推迟到当前鼠标/键盘事件**返回之后**再执行。

        ⚠️ 别在 ``mousePressEvent`` 里直接 ``self.browse()``：``browse()`` 会先
        弹一个"选文件 / 选文件夹"的小菜单（:meth:`_ask_kind`），用户选完**紧接着**
        再弹 ``QFileDialog``。两层模态都压在**同一个尚未返回**的鼠标事件里，Windows
        上表现为"小菜单点完，资源管理器不出现"（用户 2026-10-02 报的 bug）。

        ``QTimer.singleShot(0, ...)`` 让当前事件先返回、Qt 的鼠标抓取状态归位，
        下一轮事件循环再开对话框——这是"在控件事件里开模态"的标准做法。
        """
        QTimer.singleShot(0, self.browse)

    # ------------------------------------------------------------------ 选择
    def browse(self) -> None:
        """打开对话框选输入；``accepts_dir`` 为真时先让用户挑"文件还是文件夹"。"""
        from_files, wanted = self._ask_kind()
        if not wanted:
            return
        # ⚠️ 起始目录**不能传空串**：QFileDialog 空串会回退到进程工作目录
        #    （打包后就是程序所在目录 / 可能只读），入口很别扭。走项目既有约定
        #    `desktop.utils.files.default_open_dir()`（文档目录起步）。
        start = str(default_open_dir())
        if from_files:
            if self.spec.allow_multi:
                paths, _ = QFileDialog.getOpenFileNames(
                    self, self.spec.pick_label, start, self.spec.file_filter
                )
            else:
                one, _ = QFileDialog.getOpenFileName(
                    self, self.spec.pick_label, start, self.spec.file_filter
                )
                paths = [one] if one else []
        else:
            directory = QFileDialog.getExistingDirectory(
                self, "选择文件夹", start
            )
            paths = [directory] if directory else []
        self.offer(paths)

    def _ask_kind(self) -> tuple[bool, bool]:
        """问"选文件还是选文件夹"。返回 ``(是不是选文件, 是否继续)``。

        不接受目录的步骤（``accepts_dir=False``）没啥可问的，直接选文件；
        只在两种都行时才弹菜单——这是 :meth:`browse` 的唯一分支来源。
        """
        if not self.spec.accepts_dir:
            return True, True
        from qfluentwidgets import Action, RoundMenu

        menu = RoundMenu(parent=self)
        menu.addAction(Action(FIF.DOCUMENT, self.spec.pick_label, parent=menu))
        menu.addAction(Action(FIF.FOLDER, "选择文件夹", parent=menu))
        chosen = menu.exec(self.mapToGlobal(self._anchor_point()))
        if chosen is None:
            return True, False
        return str(getattr(chosen, "text", "")) != "选择文件夹", True

    def _anchor_point(self):
        """菜单弹出的锚点：控件左下角（贴着触发它的那块区域）。"""
        from PySide6.QtCore import QPoint

        return QPoint(self.width() // 2, self.height())

    # ------------------------------------------------------------------ 绘制
    def _sync_height(self) -> None:
        """空态/已选态用两个固定高度，切换时重排一次父布局。"""
        self.setFixedHeight(EMPTY_HEIGHT if self._source is None else FILLED_HEIGHT)
        self.updateGeometry()

    def _font(self, size: int, bold: bool = False) -> QFont:
        """按设计令牌造字体（不引样式表，与自绘控件保持一致）。"""
        font = QFont(self.font())
        font.setPixelSize(size)
        font.setBold(bold)
        return font

    @staticmethod
    def _elide(painter: QPainter, text: str, width: float) -> str:
        """按可用宽度做省略号截断（路径很长时不要撑破虚框）。"""
        metrics = QFontMetrics(painter.font())
        return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(width))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """画底（圆角虚线框）+ 内容（空态两行 / 已选态一行）。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)

        # ⚠️ 高亮只认 `_hot`（有东西正拖在上面），**不认 hasFocus()**：输入区是
        #    页面里第一个可聚焦控件，启动时往往就持有焦点——按焦点上色的话，
        #    每个模块页一进来就是"已激活"的样子，看不出"可以拖进来"这件事。
        lit = self._hot
        if self._hot:
            fill = T.ACCENT_SOFT
        elif self._hover:
            fill = T.SURFACE_HOVER
        else:
            fill = T.SURFACE_SOFT
        painter.setBrush(QColor(fill))
        pen = QPen(QColor(T.ACCENT if lit else T.BORDER_STRONG), 1.5)
        pen.setStyle(Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.drawRoundedRect(rect, T.RADIUS_MD, T.RADIUS_MD)

        if self._source is None:
            self._paint_empty(painter, rect)
        else:
            self._paint_filled(painter, rect)
        painter.end()

    def _paint_empty(self, painter: QPainter, rect: QRectF) -> None:
        """空态：图标居中偏上 + 标题 + 提示。"""
        icon_rect = QRectF(
            rect.center().x() - ICON_BOX / 2, rect.top() + T.SPACE_LG,
            ICON_BOX, ICON_BOX,
        )
        self._icon().render(painter, icon_rect, Theme.LIGHT)

        painter.setFont(self._font(T.SIZE_LABEL, bold=True))
        painter.setPen(QColor(T.ACCENT if self._hot else T.INK))
        title_rect = QRectF(
            rect.left() + PAD, icon_rect.bottom() + T.SPACE_SM,
            rect.width() - 2 * PAD, 22,
        )
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, self.spec.drop_title_text(), title_rect.width()),
        )

        painter.setFont(self._font(T.SIZE_CAPTION))
        painter.setPen(QColor(T.INK_FAINT))
        hint_rect = QRectF(
            rect.left() + PAD, title_rect.bottom() + 2,
            rect.width() - 2 * PAD, 18,
        )
        painter.drawText(
            hint_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, self.spec.drop_hint_text(), hint_rect.width()),
        )

    def _paint_filled(self, painter: QPainter, rect: QRectF) -> None:
        """已选态：图标 + 名字 + 路径 + 右上角清空。"""
        icon_rect = QRectF(
            rect.left() + PAD, rect.center().y() - ICON_BOX / 2 * 0.8,
            ICON_BOX * 0.8, ICON_BOX * 0.8,
        )
        self._icon().render(painter, icon_rect, Theme.LIGHT)

        text_left = icon_rect.right() + T.SPACE_MD
        text_width = rect.right() - CLOSE_BOX - T.SPACE_MD - text_left
        if text_width < 40:
            return

        painter.setFont(self._font(T.SIZE_LABEL, bold=True))
        painter.setPen(QColor(T.INK))
        name = self._source.name or str(self._source)
        painter.drawText(
            QRectF(text_left, rect.top() + T.SPACE_LG, text_width, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, name, text_width),
        )

        painter.setFont(self._font(T.SIZE_CAPTION))
        painter.setPen(QColor(T.INK_FAINT))
        painter.drawText(
            QRectF(text_left, rect.top() + T.SPACE_LG + 20, text_width, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._elide(painter, self._detail or str(self._source), text_width),
        )

        self._close_rect = QRectF(
            rect.right() - CLOSE_BOX - T.SPACE_SM,
            rect.center().y() - CLOSE_BOX / 2,
            CLOSE_BOX, CLOSE_BOX,
        )
        FIF.CLOSE.render(painter, self._close_rect, Theme.LIGHT)

    def _icon(self):
        """步骤声明的大图标（``StepSpec.drop_icon``，未知名字回退到文件夹）。"""
        return getattr(FIF, self.spec.drop_icon, FIF.FOLDER_ADD)

    # ------------------------------------------------------------------ 文案
    def _hint_text(self) -> str:
        """tooltip：空态给完整说明，已选态给完整路径（名字被截断时能看全）。"""
        if self._source is None:
            return f"{self.spec.drop_title_text()}\n{self.spec.drop_hint_text()}"
        return str(self._source)

    def _auto_detail(self, source: Path | None) -> str:
        """已选态第二行小字（宿主没给 ``detail`` 时的兜底）。

        - 文件夹 → ``完整路径 · N 个可用文件``（N 按本步骤的后缀数）；
        - 文件 → 它所在的目录。
        """
        if source is None:
            return ""
        if source.is_dir():
            count = len(self.spec.listing(source))
            return f"{source} · {count} 个可用文件"
        return str(source.parent)


__all__ = ["SourceZone", "EMPTY_HEIGHT", "FILLED_HEIGHT"]
