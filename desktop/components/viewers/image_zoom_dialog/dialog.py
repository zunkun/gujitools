# -*- coding: utf-8 -*-
"""图片预览弹窗 ``ImageZoomDialog``（工具栏/缩放/翻页/下载/编辑入口）。

从 ``image_zoom_dialog.py`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, PrimaryPushButton, PushButton, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T
from desktop.ui.widgets import apply_to
from desktop.ui.window_size import apply_window_size
from desktop.workers import WorkerHost, connect_queued

from .canvas import ZoomTarget, ZoomableCanvas
from .consts import (
    MAX_RENDER_EDGE, MIN_RENDER_EDGE, RENDER_HEADROOM, ZOOM_DIALOG_SIZE,
)
from .icons import flip_icon, mirrored_rotate_icon
from .io import overwrite_image_file, save_image

if TYPE_CHECKING:
    # ImageEditorDialog 在 _open_editor 里**延迟导入**（编辑器模块重，不能拖进
    # 启动），但本文件的返回注解要引它 —— 类型侧先声明，运行时不动。
    from desktop.components.viewers.image_editor import ImageEditorDialog

class ImageZoomDialog(QDialog, WorkerHost):
    """图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。"""

    #: 编辑器「完成」且成功覆盖原图后发出：``image_saved(path, edited)``。
    #: ``path`` = 被覆盖的文件路径文本；``edited`` = 编辑结果 QImage（是
    #: 全分辨率原图，预览画布只是它的降采样）——宿主拿它**立即**把主查看
    #: 器的大图/条目图标同步成编辑后的样子（见各查看器的
    #: ``apply_edited_image``），不必等缩略图后台重生成的窗口期还显示旧图。
    #: 只在 ``ZoomTarget.save_path`` 回写路径上发出。
    image_saved = Signal(str, object)

    def __init__(self, parent=None, factory=None, max_edge: int = MAX_RENDER_EDGE,
                 editable: bool = True):
        """``factory(index) -> ZoomTarget | None``，在**主线程**里现造该页来源。

        ``editable=False``：本弹窗**只许预览、不许编辑**——工具栏不给「编辑」
        按钮（图片去底色阶段的预览，2026-10-09 用户）。
        """
        super().__init__(parent)
        self._edit_enabled = bool(editable)
        self._init_worker_host()
        self._factory = factory
        self._max_edge = int(max_edge)
        self._index = 0
        self._target: ZoomTarget | None = None
        self._token = None  # 渲染令牌：只认最新一次请求的结果
        self._editor = None  # 图片编辑弹窗（懒建，见 _edit_image）
        self.setWindowTitle("图片预览")
        self.setModal(False)
        # ⚠️ 1360 起：工具条一行摆了缩放/朝向/翻页/打印/下载/编辑十几个
        # 控件，1120 时「编辑」会被挤到翻页组旁边贴成一团（用户 19:20 报
        # "宽度放不下编辑按钮"）。宽度给足，配合 addStretch 兜底。
        # 但"给足"要让位于屏幕：1920×1080 @125% 的机器可用高只有 824，
        # 860 会顶到任务栏后面（用户报「不最大化显示不完整」），统一交给
        # apply_window_size 夹一次（只夹不涨，大屏上仍是 1360×860）。
        apply_window_size(self, ZOOM_DIALOG_SIZE)
        # ⚠️ QDialog 默认标题栏**只有关闭（和帮助）**，没有最小化/最大化——
        # 用户找不到「还原」入口、双击标题栏也没反应（17:08 截图报障）。
        # 补上 min/max 提示后：右上角有最小化/最大化按钮，双击标题栏 =
        # 最大化/还原（系统惯例，OS 自己处理，无需我们写代码）。
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        # 键盘翻页/全屏：用 **QShortcut（窗口级）**，不受焦点在哪个控件影响。
        # ⚠️ 只靠 keyPressEvent 会掉：真实键盘走焦点链，焦点在画布/按钮上时
        # 方向键被消费或导航走，到不了对话框——离屏 QTest 直接把按键发给
        # 对话框，测不出来；用户实测「方向键没有实现」就是这个原因。
        # Esc 不在这里抢：保留 QDialog 默认的关窗语义。
        for seq, slot in (
            (QKeySequence(Qt.Key.Key_Left), lambda: self._goto(-1)),
            (QKeySequence(Qt.Key.Key_Right), lambda: self._goto(1)),
            (QKeySequence(Qt.Key.Key_F11), self._toggle_fullscreen),
        ):
            QShortcut(seq, self).activated.connect(slot)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(T.SPACE_LG, T.SPACE_MD, T.SPACE_LG, T.SPACE_MD)
        layout.setSpacing(T.SPACE_SM)

        # ⚠️ 先造画布再造工具条：工具条的按钮要连画布的方法
        self.canvas = ZoomableCanvas(self)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self._build_status())
        self._sync_controls()

    # ------------------------------------------------------------------ 构建
    def _build_toolbar(self) -> QHBoxLayout:
        """工具条：缩放 / 适应 · 朝向 · 翻页 · 下载。"""
        row = QHBoxLayout()
        row.setSpacing(T.SPACE_SM)

        self.zoom_out_btn = ToolButton(FIF.ZOOM_OUT)
        self.zoom_out_btn.setToolTip("缩小（滚轮向下 / − 键）")
        self.zoom_out_btn.clicked.connect(self.canvas.zoom_out)
        self.zoom_label = CaptionLabel("100%")
        self.zoom_label.setToolTip("当前显示比例（点击回到 100%）")
        self.zoom_label.setFixedWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.installEventFilter(self)  # 点击 → 回 100%
        self.zoom_in_btn = ToolButton(FIF.ZOOM_IN)
        self.zoom_in_btn.setToolTip("放大（滚轮向上 / + 键）")
        self.zoom_in_btn.clicked.connect(self.canvas.zoom_in)
        row.addWidget(self.zoom_out_btn)
        row.addWidget(self.zoom_label)
        row.addWidget(self.zoom_in_btn)

        row.addSpacing(T.SPACE_MD)
        self.fit_btn = PushButton(FIF.FIT_PAGE, "适应窗口")
        self.fit_btn.setToolTip("整图完整可见（快捷键 0）")
        self.fit_btn.clicked.connect(self.canvas.fit)
        self.actual_btn = PushButton("100%")
        self.actual_btn.setToolTip("一个图片像素对一个屏幕像素（快捷键 1）")
        self.actual_btn.clicked.connect(self._zoom_actual)
        row.addWidget(self.fit_btn)
        row.addWidget(self.actual_btn)

        row.addSpacing(T.SPACE_MD)
        self.rotate_ccw_btn = PushButton(mirrored_rotate_icon(), "左旋")
        self.rotate_ccw_btn.setToolTip("逆时针旋转 90°")
        self.rotate_ccw_btn.clicked.connect(self.canvas.rotate_counterclockwise)
        self.rotate_cw_btn = PushButton(FIF.ROTATE, "右旋")
        self.rotate_cw_btn.setToolTip("顺时针旋转 90°（快捷键 R）")
        self.rotate_cw_btn.clicked.connect(self.canvas.rotate_clockwise)
        self.flip_h_btn = PushButton(flip_icon(True), "水平翻转")
        self.flip_h_btn.setToolTip("左右镜像（非破坏性，只影响显示与下载）")
        self.flip_h_btn.clicked.connect(self.canvas.flip_horizontal)
        self.flip_v_btn = PushButton(flip_icon(False), "垂直翻转")
        self.flip_v_btn.setToolTip("上下镜像（非破坏性，只影响显示与下载）")
        self.flip_v_btn.clicked.connect(self.canvas.flip_vertical)
        row.addWidget(self.rotate_ccw_btn)
        row.addWidget(self.rotate_cw_btn)
        row.addWidget(self.flip_h_btn)
        row.addWidget(self.flip_v_btn)

        row.addStretch(1)
        self.prev_btn = ToolButton(FIF.LEFT_ARROW)
        self.prev_btn.setToolTip("上一页（← 键）")
        self.prev_btn.clicked.connect(lambda: self._goto(-1))
        self.page_label = CaptionLabel("")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_btn = ToolButton(FIF.RIGHT_ARROW)
        self.next_btn.setToolTip("下一页（→ 键）")
        self.next_btn.clicked.connect(lambda: self._goto(1))
        row.addWidget(self.prev_btn)
        row.addWidget(self.page_label)
        row.addWidget(self.next_btn)

        row.addSpacing(T.SPACE_MD)
        self.edit_btn = PushButton(FIF.EDIT, "编辑")
        self.edit_btn.setToolTip("打开图片编辑器：裁剪 / 变换 / 擦除 / 插入文字")
        self.edit_btn.clicked.connect(self._edit_image)
        # 只许预览的宿主（image_editable=False）连按钮都不给，而不是置灰：
        # 「编辑」在这个步骤就不是能力（2026-10-09 用户）。
        self.edit_btn.setVisible(self._edit_enabled)
        row.addWidget(self.edit_btn)
        self.print_btn = PushButton(FIF.PRINT, "打印")
        self.print_btn.setToolTip("把当前图（含翻转/旋转）送到打印机")
        self.print_btn.clicked.connect(self._print_image)
        self.download_btn = PrimaryPushButton(FIF.DOWNLOAD, "下载")
        self.download_btn.setToolTip("把整分辨率图片另存为 PNG（无损）或 JPEG")
        self.download_btn.clicked.connect(self._download)
        row.addWidget(self.print_btn)
        row.addWidget(self.download_btn)
        return row

    def _build_status(self) -> QWidget:
        """状态条：左边是本页说明（页面/尺寸），右边是临时提示（已保存…）。"""
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_MD)
        self.note_label = CaptionLabel("")
        apply_to(self.note_label, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.tip_label = CaptionLabel("")
        apply_to(self.tip_label, T.SIZE_CAPTION, color=T.INK_SOFT)
        self.tip_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.note_label, 1)
        row.addWidget(self.tip_label)
        return bar

    # ------------------------------------------------------------------ 对外
    def set_editable(self, editable: bool) -> None:
        """运行期改「是否可以编辑」：工具栏「编辑」按钮显隐随之同步。

        由宿主混入（``ZoomPopupMixin.set_image_editable``）在每次打开弹窗时
        校准；直接改 ``edit_btn`` 显隐会绕过 :meth:`_edit_image` 的守卫，别那么做。
        """
        self._edit_enabled = bool(editable)
        self.edit_btn.setVisible(self._edit_enabled)

    def show_for(self, factory=None, index: int = 0) -> None:
        """打开/翻到某一页。``factory(index) -> ZoomTarget | None``（主线程现造）。"""
        if factory is not None:
            self._factory = factory
        if self._factory is None:
            return
        target = self._factory(int(index))
        if target is None:
            self._token = None
            self._target = None
            self.canvas.clear()
            self.note_label.setText("没有可预览的图片")
            self._sync_controls()
            return
        self._target = target
        self._index = int(index)
        self._render()

    # ------------------------------------------------------------------ 渲染
    def _render_edge(self) -> int:
        """本页渲染密度 = 视口**物理**长边 × 余量。

        约束顺序（**先下限、再全局上限、最后宿主的硬上限**）：下限是"控件还没
        布局"时的兜底；``ZoomTarget.cap``（如位图的原生边长）必须最后生效且
        能低于下限——宿主说"这图只有 900px"时，渲到 1600 只是白放大还白占内存。

        语义：100% 是"一个图片像素对一个设备像素"，所以这个密度决定的是
        **100% 时能看到多大一块**（约 1.5 个窗口），而不是"放大到多少倍还不糊"。
        """
        viewport = self.canvas.viewport()
        dpr = self.canvas.devicePixelRatioF() or 1.0
        longest = max(viewport.width(), viewport.height()) * dpr
        edge = max(MIN_RENDER_EDGE, int(round(longest * RENDER_HEADROOM)))
        edge = min(edge, self._max_edge)
        if self._target is not None and self._target.cap:
            edge = min(edge, int(self._target.cap))
        return max(1, edge)

    def _render(self) -> None:
        """起一个后台渲染。``render`` 在 worker 线程里跑，只读快照。"""
        target = self._target
        if target is None:
            return
        edge = self._render_edge()
        self.canvas.clear()
        self.note_label.setText("正在渲染…")
        self.tip_label.setText("")
        self._sync_controls()  # 渲染期间处理图的按钮先禁用（翻页不受影响）
        token = self._token = object()
        self.run_worker(
            lambda: target.render(edge),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished,
                    lambda _p, image, _s, t=token: self._display(t, image),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda _p, msg, t=token: self._failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _display(self, token, image) -> None:
        """渲染就绪：装图并刷新状态（迟到的旧结果直接丢弃）。"""
        if token is not self._token:
            return
        self.canvas.set_image(image)
        self._on_zoom_changed(self.canvas.zoom)
        self._sync_controls()
        self.note_label.setText(self._note_text(image))

    def _failed(self, token, msg: str) -> None:
        """渲染失败：只在还是最新一次请求时报错。"""
        if token is not self._token:
            return
        self.canvas.clear()
        self.note_label.setText(f"渲染失败：{msg}")
        self._sync_controls()

    def _note_text(self, image) -> str:
        """状态条说明：页面信息 ｜ 原始尺寸 ｜ 本页渲染尺寸。"""
        parts = [self._target.note if self._target else "预览"]
        original = self._target.original if self._target else None
        if original is not None:
            parts.append(f"原始 {original.width()}×{original.height()}")
        parts.append(f"渲染 {image.width()}×{image.height()}")
        return " ｜ ".join(parts)

    # ------------------------------------------------------------------ 交互
    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{zoom * 100:.0f}%")

    def _zoom_actual(self) -> None:
        """100%：一个图片像素对一个屏幕像素。"""
        self.canvas.set_zoom(1.0)

    # ------------------------------------------------------- 窗口态与键盘
    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击**顶部工具栏**空白 → 全屏/还原。

        ⚠️ 系统标题栏的双击（最大化/还原）由 windowFlags 提供的 min/max
        按钮接管；这里只管我们自己的工具栏行（用户 17:07 报「双击顶部栏
        也可以全屏」「双击顶部栏，不是单击」）。画布的双击是 100%↔适应，
        语义不同，互不干扰。
        """
        if event.button() == Qt.MouseButton.LeftButton and \
                event.position().y() < self.canvas.y():
            self._toggle_fullscreen()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _toggle_fullscreen(self) -> None:
        """全屏 ↔ 正常（全屏时 Esc 先退全屏，见 keyPressEvent）。"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        """点「百分比」标签 → 回 100%（标签兼做缩放复位的入口）。"""
        if obj is self.zoom_label and \
                event.type() == QEvent.Type.MouseButtonPress:
            self._zoom_actual()
            return True
        return super().eventFilter(obj, event)

    def _goto(self, delta: int) -> None:
        """翻页：夹在两端（不回绕、不越界），越界即无动作。"""
        if self._target is None or self._target.count <= 1:
            return
        index = max(0, min(self._target.count - 1, self._index + int(delta)))
        if index != self._index:
            self.show_for(index=index)

    def _sync_controls(self) -> None:
        """按"能不能翻页 / 有没有图"开关按钮，别留死按钮。

        ⚠️ 翻页按钮**不看** ``has_image``：渲染是异步的（PDF 高密度要几百毫秒），
        若把翻页也绑在"有图"上，连点下一页时中途会突然点不动。翻页只由
        位置决定，处理图的按钮（缩放/翻转/下载）才要求有图。
        """
        target = self._target
        count = target.count if target else 1
        has_image = self.canvas.has_image
        self.prev_btn.setEnabled(count > 1 and self._index > 0)
        self.next_btn.setEnabled(count > 1 and self._index < count - 1)
        self.page_label.setText(
            f"第 {self._index + 1}/{count} 页" if count > 1 else ""
        )
        for button in (
            self.zoom_out_btn, self.zoom_in_btn, self.fit_btn, self.actual_btn,
            self.rotate_ccw_btn, self.rotate_cw_btn, self.flip_h_btn,
            self.flip_v_btn, self.edit_btn, self.print_btn, self.download_btn,
        ):
            button.setEnabled(has_image)

    # ------------------------------------------------------------------ 编辑
    def _open_editor(self, image, save_back: bool = False
                     ) -> "ImageEditorDialog | None":
        """造编辑器弹窗（不 exec，便于离屏测试）。无图时返回 None。

        ``save_back``：本页有真实文件可回写——编辑器文案改成「完成 = 覆盖
        原图片」（并先弹覆盖确认），别再让用户以为还要去「下载」。

        ⚠️ **不要给本方法加参数**：自测的替身编辑器
        （``_StubEditor(parent, image, save_back)`` / ``_stub_open``）按死签名
        覆盖它，多一个关键字参数就让整条自测抛 ``TypeError``。要带文件名给
        覆盖确认，由调用方在拿到返回值后回填 ``editor.target_name``。
        """
        from desktop.components.viewers.image_editor import ImageEditorDialog

        if image is None or image.isNull():
            return None
        self._editor = ImageEditorDialog(self, image, save_back=save_back)
        return self._editor

    def _edit_image(self) -> None:
        """打开编辑器；「完成」后把编辑结果写回**真实文件**（可回写时）。

        可回写目标 = ``ZoomTarget.edit_path``（本页显示图对应的真实文件）。
        用户原则（2026-10-01）：**图片编辑不是"本步骤看看"，各步骤改动要串成
        一条链、最终落到 PDF**——所以按"显示的是处理前还是处理后的图"决定改谁：

        - 处理前的图（如第三步「原图」）→ 改该源图文件；
        - 处理后的图（如第三步「去底色结果」、第四步待打印图）→ 改该结果
          文件（本步产出，下一步读的就是它）。

        派生显示（区域合成 / 打印效果）显示的不是某个文件的全部像素，但编辑
        改的仍是它派生的那个真实文件；「完成」后**重新合成当前显示**，而不是
        把合成结果盖回文件。

        没有真实文件（PDF 矢量页）时维持旧行为：只改画布，满意用「下载」落盘。
        """
        if not self._edit_enabled:
            return  # 只许预览的宿主：按钮已藏，键盘/其他路径兜底拒绝
        target = self._target
        edit_path = target.edit_path if target else None
        is_direct = (
            edit_path is not None
            and target is not None
            and target.save_path == edit_path
        )
        if edit_path is not None:
            base = QImage(str(edit_path))
            if base.isNull():
                self.tip_label.setText(f"无法读取原图：{edit_path.name}")
                return
            # 只有"显示内容就是这个文件"（1:1）时才把预览的翻转/旋转烤进
            # 像素；派生显示（区域合成/打印效果）的朝向不属于该文件，不烤。
            if is_direct:
                transform = self.canvas.orientation()
                if not transform.isIdentity():
                    base = base.transformed(
                        transform, Qt.TransformationMode.SmoothTransformation
                    )
            editor = self._open_editor(base, save_back=True)
            if editor is not None:
                # 覆盖确认里点名是哪个文件（不知道文件名的覆盖确认等于没确认）
                editor.target_name = edit_path.name
                # 内容节点 sidecar（统一变换二次编辑恢复，2026-10-10）
                editor.source_path = str(edit_path)
        else:
            editor = self._open_editor(self.canvas.export_image())
        if editor is None:
            self.tip_label.setText("没有可编辑的图片")
            return
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        edited = editor.result_image()
        if edited is None or edited.isNull():
            return
        if edit_path is not None:
            if not overwrite_image_file(edited, edit_path):
                self.tip_label.setText(f"保存失败，编辑未生效：{edit_path}")
                return
            from desktop.components.viewers.image_editor import (
                sync_content_quad,
            )

            sync_content_quad(str(edit_path), editor)
            # 三处同步：① 主查看器（信号携带编辑图，宿主立即上屏并登记尺寸）
            # ② 本弹窗画布 ③ 磁盘文件（上面已原子覆盖）。缩略图缓存由宿主
            # 后台重生，不阻塞前两处。
            self.image_saved.emit(str(edit_path), edited)
            if is_direct:
                self.canvas.set_image(edited)
                self._on_zoom_changed(self.canvas.zoom)
            else:
                # 派生显示：按新文件重新合成当前页（区域/打印效果随之更新）
                self.show_for(index=self._index)
            self.tip_label.setText(
                f"已覆盖原图：{edit_path.name}（后续步骤将使用编辑后的图）"
            )
            return
        self.canvas.set_image(edited)
        self._on_zoom_changed(self.canvas.zoom)
        self.tip_label.setText("已应用编辑：满意就用「下载」保存；翻页会丢弃未保存的修改")

    def _print_image(self) -> None:
        """把当前图送到打印机（对话框里选打印机/纸张/份数）。

        ⚠️ 一律取 ``canvas.export_image()``——**画布当前的整分辨率图**
        （含翻转/旋转）。图可能是**虚拟图片**：第三步 area=1 的左右分页
        实时合成预览并没有落盘，按路径重读会读不到——所以打印与下载走
        同一条取图通道。
        绘制：等比铺满可打印区并居中（源图比例与纸张无关，不拉伸变形）。
        """
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        image = self.canvas.export_image()
        if image is None or image.isNull():
            self.tip_label.setText("没有可打印的图片")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("打印图片")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        page = printer.pageRect(QPrinter.Unit.DevicePixel)
        scaled = image.scaled(
            page.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(printer)
        painter.drawImage(
            QPointF(page.x() + (page.width() - scaled.width()) / 2,
                    page.y() + (page.height() - scaled.height()) / 2),
            scaled,
        )
        painter.end()
        self.tip_label.setText(f"已发送打印机：{printer.printerName()}")

    def _download(self) -> None:
        """把**整分辨率**（已应用翻转/旋转）的图另存到磁盘。"""
        image = self.canvas.export_image()
        if image is None or image.isNull():
            self.tip_label.setText("没有可下载的图片")
            return
        stem = self._target.stem if self._target else "preview"
        suggested = str(Path.home() / f"{stem}.png")
        path, selected = QFileDialog.getSaveFileName(
            self, "保存图片", suggested,
            "PNG 图片（无损） (*.png);;JPEG 图片（有损，画质 90） (*.jpg *.jpeg)",
        )
        if not path:
            return
        target = Path(path)
        if not target.suffix:
            target = target.with_suffix(
                ".jpg"
                if "jpg" in selected.lower() or "jpeg" in selected.lower()
                else ".png"
            )
        if save_image(image, target):
            self.tip_label.setText(f"已保存：{target}")
        else:
            self.tip_label.setText(f"保存失败：{target}")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """快捷键：←/→ 翻页、+/- 缩放、0 适应窗口、1 原始比例、R 旋转。

        Esc 交给 QDialog 自己处理（关窗）。
        """
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self._goto(-1)
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self._goto(1)
            return
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.canvas.zoom_in()
            return
        if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.canvas.zoom_out()
            return
        if key == Qt.Key.Key_0:
            self.canvas.fit()
            return
        if key == Qt.Key.Key_1:
            self._zoom_actual()
            return
        if key == Qt.Key.Key_F11:
            # 全屏↔还原（另一条路：双击顶部工具栏空白）。
            # ⚠️ 不动 Esc：QDialog 的「Esc 关窗」在更深的事件层，这里抢不到。
            self._toggle_fullscreen()
            return
        if key == Qt.Key.Key_R:
            self.canvas.rotate_clockwise()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        """关窗即作废在飞的渲染并释放大图（一张 4000px 预览约 45MB）。"""
        self._token = None
        self.shutdown_workers()
        self.canvas.clear()
        super().closeEvent(event)
