# -*- coding: utf-8 -*-
"""独立模块页面的**基类**：把「页头 + 左预览 + 右控制 + 日志」这套骨架收在一处。

为什么需要它（而不是每个模块各写一遍 QVBoxLayout）：

- 三个模块（图片提取 / 去底色 / 拼图）的**外壳**长得一样——都是「选文件 →
  调参数 → 出结果」。骨架统一后，模块页只剩「参数面板是谁、执行怎么跑」两件事，
  新增模块的成本降到几十行；
- 骨架统一也保证了**左导航切换时页面不跳变**：三页的页头高度、内容内边距、
  控制列宽度都来自同一组常量（``desktop.ui.theme``）。

⚠️ 本类**只依赖共享底座**（``desktop.ui.*``、``desktop.workers``），不 import
任何模块页、不 import ``TaskDetailPage``——「模块独立」这条底线由本文件守住。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import InfoBar, InfoBarPosition

from desktop.ui import theme as T
from desktop.ui.widgets import Card, apply_to
from desktop.workers import WorkerHost


class ModulePage(QWidget, WorkerHost):
    """独立模块页面骨架：页头（标题 + 副标题 + 操作区）+ 左右两栏 + 状态行。

    子类需要做的三件事：

    1. ``TITLE`` / ``SUBTITLE``：页头文案（``__init__`` 里已经摆好控件，
       有需要在构建后改文案的走 ``self.header.title_label``）；
    2. ``_build_preview()``：左栏预览控件（**必须实现**，返回 QWidget）；
    3. ``_build_control()``：右栏控制控件（**必须实现**，返回 QWidget）。

    ``status(text)`` 往页头的状态行写字，``toast(kind, title, content)`` 弹
    InfoBar —— 这两个是各模块反馈执行结果的标准出口，别自己 new InfoBar。
    """

    #: 页头文案；子类覆盖（这里给兜底值，避免忘记时页头是空的）
    TITLE = "模块"
    SUBTITLE = ""

    #: 控制列宽度区间（与详情页 ``_apply_control_width`` 的常规档一致：
    #: 参数表单 340~440px 是实测「标签不折行、输入框不被压扁」的舒适区）。
    CONTROL_MIN_WIDTH = 340
    CONTROL_MAX_WIDTH = 440

    #: 状态行的颜色语义（``status(kind=...)``）：取 theme 里的语义色
    _STATUS_COLORS = {
        "info": T.INK_SOFT,
        "success": T.SUCCESS,
        "warning": T.WARNING,
        "error": T.DANGER,
    }

    def __init__(self, parent=None):
        """组装骨架：页头 → 整幅输入区（可选）→ 左右分栏 → 状态行。"""
        super().__init__(parent)
        self._init_worker_host()
        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        root.setSpacing(T.SPACE_MD)

        root.addWidget(self._build_header())

        # ⚠️ 「整幅输入区」要在建控制列**之前**建好：控制列里的 StepControl 会
        #    把它接管过去（共用同一块控件），顺序反了就会各建一块、显示两份。
        self.input_zone = self._build_input()
        if self.input_zone is not None:
            root.addWidget(self.input_zone)
            # 拖到页面任何空白处也算拖进输入区（用户 2026-10-02 要的"拖进来"，
            # 落到非热区上不该没反应）；具体转发见下面几个 drag/drop 覆写。
            self.setAcceptDrops(True)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(T.SPACE_SM)

        preview_card = Card(padding=T.SPACE_SM, spacing=0, radius=T.RADIUS_MD)
        preview_card.box.addWidget(self._build_preview())
        self.preview_widget = preview_card
        splitter.addWidget(preview_card)

        control = self._build_control()
        control.setMinimumWidth(self.CONTROL_MIN_WIDTH)
        control.setMaximumWidth(self.CONTROL_MAX_WIDTH)
        # ⚠️ 控制卡片**顶部对齐**：Card 默认 Preferred/Preferred，塞进 QSplitter
        #    后会被拉成满高——参数面板只占上面一小块，下面一大片白边很难看
        #    （实测 920 高的窗口里控制卡片比内容高 500px）。这里把它包进一个
        #    自顶向下的容器，卡片自己保持自然高度。
        control_column = QWidget()
        column_layout = QVBoxLayout(control_column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        column_layout.addWidget(control)
        column_layout.addStretch(1)
        control_column.setMinimumWidth(self.CONTROL_MIN_WIDTH)
        control_column.setMaximumWidth(self.CONTROL_MAX_WIDTH)
        self.control_widget = control_column
        splitter.addWidget(control_column)
        # 左宽右窄：预览是主体，控制列只要放得下表单即可
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        # 初始宽度只在**首次布局前**生效；给个"够宽的预览 + 控制列最小宽"。
        splitter.setSizes([1000, self.CONTROL_MIN_WIDTH])
        root.addWidget(splitter, 1)
        self.splitter = splitter

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(76)
        self.log_view.setObjectName("logView")
        # ⚠️ 关掉日志区自己的拖放：QPlainTextEdit 默认会**吃掉**拖拽事件，
        #    用户把文件拖到页面底部时就落在它身上、页面级转发收不到，
        #    表现是"拖到下面没反应"。关掉后事件冒泡到本页，统一转给输入区。
        self.log_view.setAcceptDrops(False)
        root.addWidget(self.log_view)

    # ------------------------------------------------------------------ 骨架
    def _build_header(self) -> QWidget:
        """页头：标题 + 副标题 + 右侧操作区（``self.header.actions`` 加按钮）。"""
        from qfluentwidgets import CaptionLabel

        header = _ModuleHeader(self.TITLE, self.SUBTITLE)
        self.header = header
        self.status_label = CaptionLabel("")
        apply_to(self.status_label, T.SIZE_CAPTION, color=T.INK_SOFT)
        header.actions.addWidget(self.status_label)
        return header

    def _build_preview(self) -> QWidget:  # pragma: no cover - 子类实现
        raise NotImplementedError

    def _build_input(self) -> QWidget | None:
        """可选的**整幅输入区**（默认没有，子类覆盖）。

        返回一个控件时，它会插在页头与左右分栏之间、**横跨整幅宽度**——左侧
        三个模块的"大输入框"就是这么来的（用户 2026-10-02：「页面上有一个大的
        输入框，可以输入图片和输入文件，或者输入目录，也可以把文件拖进去」）。
        典型实现就是返回一块 :class:`~desktop.steps.source_zone.SourceZone`，
        并在 :meth:`_build_control` 里把它交给 ``StepControl(zone=...)``。
        """
        return None

    def _build_control(self) -> QWidget:  # pragma: no cover - 子类实现
        raise NotImplementedError

    # -------------------------------------------------- 整页拖拽 → 转给输入区
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖到页面空白处：当作拖向输入区（点亮它），避免"拖上去没反应"。"""
        if self._forward_paths(event.mimeData(), preview_only=True):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖拽移动中：保持接受（Qt 要求显式接受才会给 drop）。"""
        if self._forward_paths(event.mimeData(), preview_only=True):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """拖出页面：熄灭输入区高亮。"""
        if self.input_zone is not None:
            self.input_zone.set_hot(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """松手：把路径交给输入区，由它按步骤规则归一成源。"""
        if self._forward_paths(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _forward_paths(self, mime, preview_only: bool = False) -> bool:
        """把拖拽数据里的本地路径转给输入区；返回是否认领了这次拖拽。

        ``preview_only=True`` 只点亮高亮（拖拽经过），不真的提交路径。
        """
        if self.input_zone is None or not self.input_zone.isEnabled():
            return False
        from desktop.steps.source_zone import SourceZone

        paths = SourceZone.paths_from_mime(mime)
        if not paths:
            return False
        if preview_only:
            self.input_zone.set_hot(True)
        else:
            self.input_zone.set_hot(False)
            self.input_zone.offer(paths)
        return True

    # ------------------------------------------------------------------ 反馈
    def status(self, text: str, kind: str = "info") -> None:
        """写页头状态行；``kind`` 取 info/success/warning/error 决定颜色。"""
        self.status_label.setText(text)
        apply_to(
            self.status_label,
            T.SIZE_CAPTION,
            color=self._STATUS_COLORS.get(kind, T.INK_SOFT),
        )

    def toast(self, kind: str, title: str, content: str) -> None:
        """弹 InfoBar（右下角，与详情页 ``_toast`` 同一位置/时长）。"""
        factory = getattr(InfoBar, kind, InfoBar.info)
        factory(
            title=title,
            content=content,
            parent=self,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2500,
        )

    def log(self, text: str) -> None:
        """往底部日志区追加一行。"""
        self.log_view.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """关闭时收尾后台线程，避免解释器退出时被强杀（同详情页规矩）。"""
        self.shutdown_workers()
        event.accept()


class _ModuleHeader(QWidget):
    """模块页头：左标题列 + 右操作区，底部一条分隔线。

    ⚠️ 没有直接复用 ``desktop.ui.widgets.PageHeader`` 的原因只有一个：
    那个页头是**固定 64px**、给列表页用的；模块页要在操作区右侧常驻一条
    **状态行**（执行进度/结果），它会随文案变宽，64px 固定高会把两行挤在一起。
    所以这里给标题列留出副标题行的高度，并允许操作区纵向居中自适应。

    结构与 ``PageHeader`` 保持一致（title_label / subtitle_label / actions），
    子类/壳层的用法不必分两套。
    """

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(T.SPACE_XS, 0, T.SPACE_XS, T.SPACE_SM)
        layout.setSpacing(T.SPACE_MD)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        self.title_label = QLabel(title, self)
        apply_to(self.title_label, T.SIZE_TITLE, bold=True, color=T.INK)
        text_column.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle, self)
        apply_to(self.subtitle_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.subtitle_label.setVisible(bool(subtitle))
        text_column.addWidget(self.subtitle_label)
        layout.addLayout(text_column)
        layout.addStretch()

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(T.SPACE_SM)
        layout.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        """改副标题；空串则隐藏副标题行。"""
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


__all__ = ["ModulePage"]


#: 未使用但保留的提示：``Signal`` 供子类自由定义信号时直接从这里 import
_ = Signal
