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

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from desktop.components.log_panel import LogPanel
from desktop.ui import theme as T
from desktop.ui.toast import show_toast
from desktop.ui.widgets import Card, apply_to
from desktop.workers import WorkerHost

if TYPE_CHECKING:
    from desktop.steps.spec import StepSpec
    from desktop.steps.source_zone import SourceZone


class ModulePage(QWidget, WorkerHost):
    """独立模块页面骨架：页头（标题 + 副标题 + 操作区）+ 左右两栏 + 状态行。

    子类需要做的三件事：

    1. ``TITLE`` / ``SUBTITLE``：页头文案（``__init__`` 里已经摆好控件，
       有需要在构建后改文案的走 ``self.header.title_label``）；
    2. ``_build_preview()``：左栏预览控件（**必须实现**，返回 QWidget）；
    3. ``_build_control()``：右栏控制控件（**必须实现**，返回 QWidget）。

    ``status(text)`` 往页头的状态行写字，``toast(kind, title, content)`` 弹
    InfoBar —— 这两个是各模块反馈执行结果的标准出口，别自己 new InfoBar。

    ⚠️ **初始只显示大输入区**（用户 2026-10-03）：

        > 初始就只有一个输入框，下面的操作面板和预览这些都要选择输入文件后
        > 才显示出来

    所以左右分栏与日志区在构造完成后就被收起来，由
    :meth:`show_workspace` / :meth:`sync_workspace_visible` 在"用户真的给了
    输入"之后才点亮。⚠️ 收起来的只是**可见性**，控件照旧构造 —— 惰性构造
    会让各模块页的控件引用（``self.viewer`` / ``self.control``…）在
    ``_on_source_changed`` 里才存在，而那个信号恰好在构造期之后才发，
    早绑信号会 AttributeError；而且隐藏的控件不占布局，首帧也更快。

    子类**只需在"源变了"的回调里调一次**
    :meth:`sync_workspace_visible`（传"有没有源"），清空源时传 ``False``
    就自动收回去。
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
        self.input_zone: SourceZone | None = self._build_input()
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

        # ⚠️ 与详情页**用同一个**日志控件（`desktop.components.log_panel.LogPanel`：
        #    常驻一行状态条 + 点击唤出浮层）。此前这里是一只裸 QPlainTextEdit，
        #    常驻 76px 白框：空闲时是一块空白卡占位置，两套观感也对不上
        #    （用户 2026-10-03：「UI 要精美，不要傻大粗」）。
        self.log_panel = LogPanel()
        # 页面各处沿用的 self.log_view 直接指向面板内的文本域（调用点不变）
        self.log_view = self.log_panel.log_view
        root.addWidget(self.log_panel)

        # ---- 初始只留大输入区（用户 2026-10-03，见类 docstring）----
        # ⚠️ 走同一个容器一起收/一起放：分栏与日志区是"操作界面"的两半，
        #    收一半留一半会看起来像漏画了。
        self.workspace = splitter
        self._workspace_shown = True
        self.show_workspace(False)

    # ------------------------------------------------------------------ 骨架
    def show_workspace(self, shown: bool) -> None:
        """显隐"操作界面"（左右分栏 + 日志区）。

        初始为 ``False``（用户 2026-10-03：「初始就只有一个输入框，下面的操作
        面板和预览这些都要选择输入文件后才显示出来」）。有输入之后由
        :meth:`sync_workspace_visible` 打开。

        大输入区同时切成**独占模式**（自己撑满整幅，见
        :meth:`desktop.steps.source_zone.SourceZone.set_solo_mode`）——
        否则收起分栏后页面上半屏是框、下半屏一片空白，看着像没加载完。
        """
        self._workspace_shown = bool(shown)
        self.splitter.setVisible(self._workspace_shown)
        # ⚠️ 藏**面板**而不是 log_view：日志浮层是状态条的子控件，单独藏文本域
        #    会留下一条什么都不显示的状态条。
        self.log_panel.setVisible(self._workspace_shown)
        zone = getattr(self, "input_zone", None)
        if zone is not None and hasattr(zone, "set_solo_mode"):
            zone.set_solo_mode(not self._workspace_shown)

    def sync_workspace_visible(self, has_source) -> None:
        """按"当前有没有源"开关操作界面（各模块在源变化时调一次即可）。

        ``has_source`` 传 ``Path`` / ``None`` 都行，判的是"是不是空"。
        """
        self.show_workspace(has_source is not None)

    def workspace_shown(self) -> bool:
        """操作界面当前是否显示（自测与截图脚本用）。"""
        return self._workspace_shown

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

    def _build_input(self) -> SourceZone | None:
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
        """弹 InfoBar；实现收在 :mod:`desktop.ui.toast`（与详情页 ``_toast`` 共用）。"""
        show_toast(self, kind, title, content)

    def log(self, text: str) -> None:
        """往底部日志区追加一行。

        ⚠️ 用 ``append`` 而不是 ``appendPlainText``：日志区换成了
        :class:`desktop.components.log_panel.LogPanel`，它的文本域是
        qfluentwidgets 的 ``TextEdit``（与详情页同款），只有 ``append``。
        """
        self.log_view.append(text)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """关闭时收尾后台线程，避免解释器退出时被强杀（同详情页规矩）。"""
        self.shutdown_workers()
        event.accept()


class StepModulePage(ModulePage):
    """**带完整步骤控制**的模块页：绝大多数步骤页的直接基类（需求 2 的落点）。

    一个"独立步骤"的页面真正只差两件事：

    1. 左栏用哪个预览控件（:meth:`_build_preview`）；
    2. 跑完之后怎么把产物交给它（:meth:`on_result`）。

    其余全是**每个步骤都一样**的外设：摆一块横跨整幅的大输入区、建
    :class:`~desktop.steps.control.StepControl`（参数 + 输出目录 + 执行/中断）、
    把控制区的状态/日志/失败接到页面的反馈出口、源变了怎么改副标题与显隐、
    收尾执行线程。这些此前在 extract/rembg/print/detect 四个页面里**逐字抄了
    四遍**——加第五个步骤就再抄一遍。现在全部收在这里。

    子类要做的**全部**事情：

    .. code-block:: python

        class MyPage(StepModulePage):
            SPEC = spec_by_key("my_step")        # 1. 认领步骤元数据

            def _build_preview(self):            # 2. 左栏预览控件
                self.viewer = SomeViewer()
                return self.viewer

            def on_result(self, output, result): # 3. 产物怎么上屏
                self.viewer.set_images(...)

    ⚠️ **拼版页不继承它**（``desktop/modules/imposition/page.py``）：它的"源"是
    **一批图片**而非一个源（要 ``collect_files`` 摊平），执行也是纯函数导出
    而非 ``StepSpec.command``，外壳因此对不上。它继续直接继承
    :class:`ModulePage`。
    """

    #: 本页对应的步骤元数据（子类必须给；页头文案也由它派生）
    SPEC: StepSpec | None = None

    #: 子类覆盖：空闲时状态行写什么（默认「尚未选择 + 输入物称呼」）
    def idle_text(self) -> str:
        spec = self.SPEC
        noun = spec.input_noun() if spec else "文件"
        return f"尚未选择{noun}"

    def on_result(self, output: Path, result: dict) -> None:
        """执行成功：把产物交给左栏（子类实现）。

        ``output`` 是内核回传的产物路径——**目录还是文件取决于这一步**
        （``StepSpec.artifact_is_file``：``print`` 回传 PDF 文件，其余回传目录）。
        ``result`` 是 job 在 worker 线程里攒下的少量数据（如导出张数）。
        """
        raise NotImplementedError

    def on_failed(self, message: str) -> None:
        """执行失败：给一句人话（状态行与日志已由控制区写过）。"""
        title = f"{self.SPEC.title}失败" if self.SPEC else "处理失败"
        self.toast("error", title, message)

    # ------------------------------------------------------------------ 骨架
    def __init__(self, parent=None):
        """先把页头文案从 spec 落成实例属性，再建骨架。

        ⚠️ 必须在 ``super().__init__()`` **之前**赋值：``ModulePage.__init__``
        构造期就会读 ``self.TITLE`` / ``self.SUBTITLE`` 去建页头，晚一步就
        建出一张空标题的页头（而它之后不会再被重建）。实例属性遮蔽类属性，
        所以各页面不必再各自写一遍 ``TITLE = _SPEC.title``。
        """
        spec = self.SPEC
        self.TITLE = spec.title if spec else "模块"
        self.SUBTITLE = spec.subtitle if spec else ""
        #: job 在 worker 线程里写、主线程读的桥（只放标量/列表，不放控件）
        self._job_result: dict = {}
        super().__init__(parent)
        self.status(self.idle_text())
        # 左栏缩略图那一层还要接「图被编辑器覆盖」的同步（立即上屏 + 重渲缩略图
        # + 生效提示，见 ``ThumbSourceMixin._on_source_image_saved``）。这里用
        # ``getattr`` 探测而不是直接调用：本基类**不 import** thumb_source（守住
        # 「只依赖共享底座」），而没混入那个混入的页面本来就不需要这一步。
        # ⚠️ 必须在 ``super().__init__()`` **之后**：``_build_preview`` 在构造
        # 期跑，``self.viewer`` 那时才有。
        wire = getattr(self, "_wire_source_edit", None)
        if callable(wire):
            wire()

    # ------------------------------------------------------------------ 输入
    def _build_input(self):
        """页头下方横跨整幅的**大输入区**（共用组件，见 SourceZone）。"""
        from desktop.steps.source_zone import SourceZone

        spec = self.SPEC
        # 子类必须声明 SPEC（本类只做基类，不直接实例化）
        assert spec is not None, "步骤模块页必须声明 SPEC"
        self.zone = SourceZone(spec)
        # 控件自己没走通（如选择对话框打不开）时用 toast 说话——大输入区
        # 自己只发信号，"怎么说给用户听"是页面的事。
        # ⚠️ **"用户取消了选择对话框"不会走到这里**（用户 2026-10-04）：
        #    那不是错误，"这个用不上"纯属噪声。
        # ⚠️ **"东西给过来了但一步都跑不了"也不走这里**：那由
        #    ``StepControl._on_paths`` 经 ``resolve_source`` 给出理由，
        #    落到页头状态行（常驻可见），不拿 toast 打断用户。
        self.zone.rejected.connect(
            lambda message: self.toast("warning", "没能完成这次选择", message)
        )
        return self.zone

    # ------------------------------------------------------------------ 控制
    def _build_control(self):
        """右栏：整块交给共用步骤控件（面板 + 输出目录 + 执行/中断）。"""
        from desktop.steps.control import StepControl

        spec = self.SPEC
        # 子类必须声明 SPEC（本类只做基类，不直接实例化）
        assert spec is not None, "步骤模块页必须声明 SPEC"
        card = Card()
        self.control = StepControl(spec, zone=self.zone)
        # StepControl 只发信号、不弹提示；页头状态行与日志区由本页呈现
        self.control.status.connect(self.status)
        self.control.log.connect(self.log)
        self.control.source_changed.connect(self._on_source_changed)
        self.control.finished.connect(self._on_finished)
        self.control.failed.connect(self._on_failed)
        card.box.addWidget(self.control)
        return card

    # ------------------------------------------------------------------ 回调
    def _on_source_changed(self, source) -> None:
        """换了源：开关操作界面，并把「源 → 输出」写到副标题上。

        副标题按"有没有源"分两种写法：空态回落到 spec 的静态副标题（不要把
        上一页的路径留在屏幕上），有源才显示 ``<源> → <输出目录>``。
        """
        self.sync_workspace_visible(source)
        if source is None:
            self.header.set_subtitle(self.SUBTITLE)
            self.status(self.idle_text(), "info")
            return
        detail = self.source_summary(source)
        self.header.set_subtitle(detail or self.SUBTITLE)
        spec = self.SPEC
        # 子类必须声明 SPEC（本类只做基类，不直接实例化）
        assert spec is not None, "步骤模块页必须声明 SPEC"
        self.status(f"已选择{spec.input_noun()}，点击「{spec.run_text()}」",
                    "info")

    def source_summary(self, source) -> str:
        """副标题里那一行 ``<源> → <输出>``；子类可加图片张数等信息。"""
        return f"{Path(source).name} → {self.control.output()}"

    def source_images(self) -> list[Path]:
        """源里的图片清单：源是文件就是它自己，是目录就取顶层（认本步后缀）。

        ⚠️ 只在"这一步的输入物本身就是图片"时有意义（rembg/print）；提取的
        源是 PDF、检测的源是图片但不这么用，子类别硬调。
        """
        spec = self.SPEC
        source = self.control.source()
        if source is None or spec is None:
            return []
        source = Path(source)
        if source.is_file():
            return [source] if spec.accepts_path(source) else []
        return spec.listing(source)

    def _on_finished(self, output: str) -> None:
        """成功：把产物交给 :meth:`on_result`（状态行/日志已由控制区写过）。"""
        self.on_result(Path(output), self._job_result)

    def _on_failed(self, message: str) -> None:
        self.on_failed(message)

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾执行线程（壳层关窗口时会调到这里）。"""
        self.control.shutdown()
        super().shutdown_workers()


class _ModuleHeader(QWidget):
    """模块页头：左标题列 + 右操作区，底部一条分隔线。

    ⚠️ 没有直接复用 ``desktop.ui.widgets.PageHeader`` 的原因只有一个：
    那个页头是**固定 64px**、给列表页用的；模块页要在操作区右侧常驻一条
    **状态行**（执行进度/结果），它会随文案变宽，64px 固定高会把两行挤在一起。
    所以这里给标题列留出副标题行的高度，并允许操作区纵向居中自适应。

    结构与 ``PageHeader`` 保持一致（title_label / subtitle_label / actions），
    子类/壳层的用法不必分两套。
    """

    if TYPE_CHECKING:
        # ⚠️ ``actions`` 遮住了基类 QWidget.actions() 方法（同 PageHeader.actions
        # 的情况），类型检查器会按基类方法解析 → 判成「布局没有 addWidget」。
        # 这条类型侧声明把它钉回布局，只影响类型检查。
        actions: QHBoxLayout

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        # ⚠️ **页头不参与纵向拉伸**。
        #
        # 起因（用户 2026-10-03 截图反馈）：做成"初始只有输入框"之后，副标题
        # 飘到了页面正中、输入框被挤到底边。原因是 `ModulePage.root` 里唯一
        # 带 stretch 的是分栏，分栏一隐藏，Qt 就把空出来的纵向空间按
        # sizePolicy 摊给了页头（默认 Preferred 会长）。
        #
        # 现在真正让它长出来的是输入区的 `Expanding` 策略（见
        # `SourceZone._sync_height`），所以这一行是**双保险**：万一将来输入区
        # 走了固定高度（例如某种步骤不需要撑满），页头也不会突然长到半屏高。
        # 实测把这一行去掉、只留输入区的拉伸策略，当前布局仍然正确。
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Maximum,
        )
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


__all__ = ["ModulePage", "StepModulePage"]


#: 未使用但保留的提示：``Signal`` 供子类自由定义信号时直接从这里 import
_ = Signal
