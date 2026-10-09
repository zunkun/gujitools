# -*- coding: utf-8 -*-
"""``ImageViewerWidget``：**装配点 + 基座 + 展示主路径**。

从 ``image_viewer.py`` 拆出（2026-10-07）。本文件放类头（信号/类属性）、
``__init__``、条目装填与当前页展示、以及宿主协议（``_zoom_*``）。
缩略图缓存、PDF 页源、框数据分别在兄弟模块的 Mixin 里；方法体逐字未改。

⚠️ 宿主协议三个方法留在本类，才能盖住 ``ZoomPopupMixin`` 的默认实现。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon as FIF, ToolButton
from desktop.ui.widgets import mark_input_entry
from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin

from .boxes import BoxesMixin
from .pdf import PdfSourceMixin
from .thumbs import ThumbsCacheMixin


class ImageViewerWidget(
    ThumbsCacheMixin,
    PdfSourceMixin,
    BoxesMixin,
    QWidget,
    ThumbsMixin,
    ZoomPopupMixin,
):
    """图片查看器：缩略图条 + 大图，支持切割框叠加、拖动与页面增删按钮。"""

    current_changed = Signal(int, str)
    delete_requested = Signal()
    insert_requested = Signal()
    #: 「选文件夹」按钮：宿主弹**目录**选择框，把一个文件夹批量插进来
    #: （用户 2026-10-06）。⚠️ 与 :attr:`insert_requested` 分开是因为
    #: ``QFileDialog`` 选不了目录，两者是不同的对话框、不同的语义。
    insert_folder_requested = Signal()
    boxes_edited = Signal(str, list)  # (图片路径, 全部框坐标) 拖动结束后发出
    #: 选中框变化（-1 = 无选中）：宿主据此同步「选中框类型」控件
    selection_changed = Signal(int)
    #: 编辑被拒绝（超框数上限等）：宿主弹提示
    box_edit_rejected = Signal(str)
    #: 编辑器在放大弹窗里覆盖了某张页面图 ``image_saved(path, edited)``：
    #: 宿主据此同步 sizes.json、重生成缩略图并刷新各处显示
    image_saved = Signal(str, object)

    def __init__(
        self,
        editable: bool = False,
        show_boxes: bool = False,
        empty_hint: str = "暂无图片",
        image_size_provider=None,
        thumb_provider=None,
        image_editable: bool = True,
        parent=None,
    ):
        """
        构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。

        image_size_provider 供大图降采样时还原原始像素尺寸；thumb_provider
        让缩略图条改用预生成小图，避免反复解码原图。

        ⚠️ ``editable`` 与 ``image_editable`` 是**两件事**：前者管**页面清单**
        （增删/插入按钮，提取页等只读宿主传 False），后者管**图片内容**
        （右键「编辑图片」+ 预览弹窗「编辑」按钮，2026-10-09 新增接口；
        去底色阶段的 ``RembgPreviewWidget`` 传 False，只许预览）。
        """
        super().__init__(parent)
        self._init_thumbs()
        # ⚠️ 元素类型是 ``Path | str``（set_images 的入参就是两者都收，调用方
        # 有时给 Path、有时给字符串路径），不是 list[Path]：list 不协变，写成
        # list[Path] 会让每一处 list(paths) 赋值都变成类型错误。
        self._paths: list[Path | str] = []
        self._empty_hint = empty_hint
        #: PDF 页模式：``(pdf 路径, 代际号)``。非 None 时左栏是「页缩略图条」，
        #: 大图按需从 PDF 渲那一页——而不是拿 256px 缓存小图放大（会糊）。
        #: 见 :meth:`set_pdf_source`。
        self._page_source: tuple[Path, int] | None = None
        #: PDF 页模式下的页缩略图缓存目录（``None`` = 不落盘缓存）。
        #: 供宿主/自测核对"缩略图真的落在 singletask 下"。
        self._page_source_cache: Path | None = None
        #: 缩略图缓存接线（:meth:`set_thumb_source` 装上）：目录、边长，
        #: 以及「真实图片路径 → 已就绪的缓存小图」。
        self._thumb_cache_dir: Path | None = None
        self._thumb_cache_edge: int | None = None
        self._thumb_cache_ready: dict[str, Path] = {}
        self._thumb_cache_lookup = None
        #: 每条清单对应的**显式**缓存文件名（extract 的序号口径用；None 项
        #: 回落到图键命名）。与 :attr:`_paths` 同序，长度不一致时按越界回落。
        self._thumb_cache_names: list[str | None] | None = None
        # 原始尺寸提供者：(path_text) -> QSize | None。
        # 预览加载的大图可能被降采样，框坐标以原始尺寸为坐标系基准。
        self._image_size_provider = image_size_provider
        # 缩略图提供者：(path_text) -> Path | None。返回预生成的小图路径，
        # 避免左侧缩略图条反复解码原始分辨率大图；返回 None/原路径则解码真图。
        self._thumb_provider = thumb_provider
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        left = QVBoxLayout()
        self.strip = ThumbStrip()
        self.strip.current_path_changed.connect(self._select_image)
        left.addWidget(self.strip, 1)
        if editable:
            buttons = QHBoxLayout()
            delete_btn = ToolButton(FIF.DELETE)
            delete_btn.setToolTip("从页面清单删除所选图片")
            delete_btn.clicked.connect(self.delete_requested.emit)
            insert_btn = ToolButton(FIF.ADD)
            insert_btn.setToolTip("插入图片（可多选）")
            insert_btn.clicked.connect(self.insert_requested.emit)
            # ⚠️ **「选文件夹」是独立按钮，不靠文件对话框顺带选目录**（用户
            #    2026-10-06："是否可以选择目录"）。Qt 的 ``getOpenFileNames``
            #    **不能**选目录（原生 Windows 对话框只接受文件），所以"把整个
            #    扫描结果文件夹丢进来"这个最自然的批量用法**必须**有单独入口——
            #    指望用户在文件对话框里选中文件夹是不成立的。
            folder_btn = ToolButton(FIF.FOLDER)
            folder_btn.setToolTip("把一个文件夹里的图片批量插入")
            folder_btn.clicked.connect(self.insert_folder_requested.emit)
            buttons.addWidget(delete_btn)
            buttons.addWidget(insert_btn)
            buttons.addWidget(folder_btn)
            # ⚠️ ＋与📁 加**常驻红框**（用户 2026-10-06"左下角输入图片和目录
            #    也用红色框住"）：它们是"给这一步喂图片"的入口，自定义流程
            #    第一步不吃 PDF 时全靠它们。删除按钮**不标红**——删图不是入口。
            # ⚠️ 显隐归**宿主**：这些输入控件只属于流程的**入口**那一步
            #    （用户 2026-10-06 规则③"非第一个流程节点，不存在这些输入
            #    控件"），入口吃什么由宿主按 :func:`ports.flow_entry_input_kind`
            #    决定后调 :meth:`set_insert_visible`。组件构造时默认显示，
            #    免得宿主忘了调就一直没入口。
            self._insert_buttons = (insert_btn, folder_btn)
            for button in self._insert_buttons:
                mark_input_entry(button)
            buttons.addStretch()
            left.addLayout(buttons)
        layout.addLayout(left)
        right = QVBoxLayout()
        self.view = ImageView(empty_hint)
        right.addWidget(self.view, 1)
        self.info_label = CaptionLabel("")
        right.addWidget(self.info_label)
        layout.addLayout(right, 1)
        self.show_boxes = show_boxes
        self.view.set_boxes_editable(show_boxes)
        self.view.boxes_edited.connect(self._boxes_edited)
        # 选中态与"编辑被拒"直接转发给宿主（第二步面板据此高亮框类型/提示）
        self.view.selection_changed.connect(self.selection_changed.emit)
        self.view.edit_rejected.connect(self.box_edit_rejected.emit)
        # 双击大图 → 图片预览弹窗（只读查看；编辑仍在原画布上做）
        self._init_zoom_popup(self.view, editable=image_editable)
        self._pending_boxes: tuple | None = None  # (boxes, image_size, info, full)，等大图加载后应用
        #: 每次选页递增的加载令牌，只有最新一次选择的渲染结果允许上屏。
        #: ⚠️ 不能改用「路径是否相同」判断：同一页也会被重复选择（见
        #: ``_select_image`` 的递归回调），路径一样但加载任务有两个。
        self._load_token = 0


    @property
    def paths(self) -> list[Path | str]:
        """当前页面清单（按显示顺序）。

        ⚠️ 元素是 ``Path | str``（与 :meth:`set_images` 的入参一致）：调用方
        两种都传，要拿名字/后缀时用 ``Path(x)`` 收一下。
        """
        return self._paths


    def current_path(self) -> Path | None:
        """当前选中的页面路径；无选中或无清单时为 None。

        返回 ``Path``：清单元素可能是 str，这里统一成 Path 交出去，调用方
        就直接 ``.name`` / ``.stem`` 了。
        """
        row = max(self.strip.currentRow(), 0)
        if row < len(self._paths):
            return Path(self._paths[row])
        return None


    def navigate(self, forward: bool) -> None:
        """方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。"""
        self.strip.navigate(forward)


    def set_insert_visible(self, visible: bool) -> None:
        """「＋/📁」两个**图片输入入口**的显隐（宿主按流程入口决定）。

        ⚠️ 只动这两个，**不碰**🗑：删图是清单管理，不是"喂图片"的入口，
        在哪一步都该有（详情页把它留在原地，见构造处的红框注释）。
        ``editable=False`` 的查看器没有这两个按钮，静默忽略。
        """
        for button in getattr(self, "_insert_buttons", ()):
            button.setVisible(visible)


    def set_empty_hint(self, hint: str) -> None:
        """换空态文案（输入入口藏起来后，"请点下方「＋」"就指错方向了）。

        当前正空着的话立刻把两处占位（缩略图条 + 大图）一起换掉；有图时
        只存着，等下次清空自然用新文案。⚠️ 占位要**清了重加**：
        ``add_placeholder`` 是追加语义，直接再调会叠出两条占位条目。
        """
        self._empty_hint = hint
        if self._paths:
            return
        self.strip.clear()
        self.strip.add_placeholder(hint)
        self.view.clear_image(hint)


    def set_images(self, paths: list[Path | str], boxes_map: dict | None = None) -> None:
        """设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。

        ``paths`` 元素可以是 ``Path`` **或** ``str``——统一在这里转成 ``Path``
        再往下传。⚠️ 这不是顺手为之：内部 ``_select_image`` 把元素直接交给
        :class:`~desktop.workers.PreviewWorker`，而那个 worker 在 ``run()`` 里
        要读 ``self.path.suffix``；调用方传字符串的话，异常发生在**子线程
        run() 内部**，只经 ``failed`` 信号回到预览区显示成
        「加载失败：'str' object has no attribute 'suffix'」（用户 2026-10-03 报）。
        在边界一次收干净，比让每个调用点各自记得 ``str(p)``→``p`` 可靠。

        ``boxes_map`` 预留（当前未用）。清单不变时跳过重建，但仍 emit
        current_changed 让宿主重新读取该页检测框/参数。
        """
        # ⚠️ 进图片模式先退出 PDF 页模式：``set_pdf_source`` 把清单留空、
        #    条目标签是「第 N 页」，若不退出，:meth:`_select_image` 会把
        #    ``1.jpg`` 当页号去 PDF 里渲第 1 页——提取完成后左栏看着有图，
        #    点哪页都是同一页（extract 页踩过这个：上屏的是 PDF 而不是产物）。
        self._clear_page_source()
        paths = [Path(p) for p in paths]
        if (
            paths == self._paths
            and self.strip.count() == len(paths)
        ):
            # 页面清单未变化，跳过重建；但仍需通知宿主重新读取
            # 该页的检测框/参数（可能在其他阶段被更新过）
            index = max(self.strip.currentRow(), 0)
            if self._paths:
                self.current_changed.emit(index, str(self._paths[index]))
            return
        self.close_zoom_popup()  # 清单换了：弹窗里那页已是旧数据
        # ⚠️ 前缀扩展走**增量 append**（2026-09-26 第二轮审计 L1）：extract
        #    执行期每 200ms 轮询一次输出目录，页面陆续落地；整表 clear+重建
        #    320 个条目 = O(N²) 控件 churn。清单尾部追加时只补新条目。
        old = self._paths
        if (
            len(paths) > len(old)
            and old
            and paths[: len(old)] == old
            and self.strip.count() == len(old)
        ):
            for path in paths[len(old):]:
                self.strip.add_page_item(Path(path).stem, str(path))
            self._paths = list(paths)
            self._load_thumbs(self.strip, self._paths, start=len(old))
            return
        self._paths = list(paths)
        self.strip.clear()
        if not paths:
            self.strip.add_placeholder(self._empty_hint)
            self.view.clear_image(self._empty_hint)
            self.info_label.setText("")
            return
        for index, path in enumerate(paths):
            self.strip.add_page_item(Path(path).stem, str(path))
        self._load_thumbs(self.strip, paths)
        self._select_image(0, str(paths[0]))


    def _thumb_for(self, path_text: str) -> Path:
        # ⚠️ **缓存优先于 provider**：:meth:`set_thumb_source` 的缓存小图就绪后，
        #    没必要再让宿主那个 provider 去合成区域效果（去底色页那条 provider
        #    会现算一遍，几十页就是几十次全尺寸合成）。缓存没就绪的那张回落到
        #    provider，最后才回落原图。
        cached = self._thumb_cache_ready.get(path_text)
        if cached is not None:
            return cached
        if self._thumb_cache_dir is not None and self._thumb_cache_lookup:
            candidate = self._thumb_cache_lookup(path_text)
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        if self._thumb_provider:
            spec = self._thumb_provider(path_text)
            if spec is None:
                return Path(path_text)
            if isinstance(spec, dict):
                return Path(spec["path"])
            return Path(spec)
        return Path(path_text)


    def _load_thumbs(self, strip, paths: list[Path | str], start: int = 0) -> None:
        """带提供者时加载映射后的缩略图，标签仍使用真实页面名。

        ⚠️ 分批调度走基类的 ``_load_thumbs_chunked``（首批立即、其余延后），
        这里只负责给出「切片 → worker」与「全局下标 → 条目」两个函数。
        ``start`` 透传基类（增量追加时跳过已有图标的条目）。
        """
        if not self._thumb_provider:
            super()._load_thumbs(strip, paths, start)
            return
        real_paths = list(paths)
        thumb_paths = [self._thumb_for(str(p)) for p in real_paths]
        labels = [Path(p).stem for p in real_paths]
        edge = self._decode_edge()
        self._load_thumbs_chunked(
            len(real_paths),
            make_worker=lambda s, e: ImageListWorker(
                thumb_paths[s:e], edge=edge
            ),
            sink=lambda index, image, _path: strip.set_item_icon(
                index, image, str(real_paths[index]), labels[index]
            ),
            start=start,
        )


    def _select_image(self, index: int, _path: str) -> None:
        """选中某页并异步加载大图；同一页被重复选中时只加载一次。

        ⚠️ ``self.strip.setCurrentRow(index)`` 会经 ``ThumbStrip`` 的
        ``currentRowChanged`` **递归回调**回本函数（ThumbStrip 必须监听
        currentRowChanged 才能响应键盘翻页，见其 ``__init__``）。若不设防，
        同一张图会起**两个** ``PreviewWorker``，两个都走 ``_image_ready`` →
        ``view.set_image()``，而后到的那个会把已经画好的检测框清成 ``[]``、
        信息条也从「左框(…)｜右框(…)」退化成像素尺寸文案——用户看到的就是
        「第二步预览里一个框都没有」（2026-09-19 重跑手册截图时抓到）。
        令牌让**权限归最新一次选择**：递归那次会递增令牌，外层回到这里时
        发现已被顶替就直接退出，只留一个加载任务。
        """
        # ⚠️ PDF 页模式优先：清单里存的是**页号**而不是图片路径，
        #    交给 PreviewWorker 会去解码一个叫「0」的文件（必然失败）。
        if self._page_source is not None:
            self._select_pdf_page(index)
            return
        if not self._paths or index >= len(self._paths):
            return
        self._load_token += 1
        token = self._load_token
        path = self._paths[index]
        self.strip.setCurrentRow(index)
        if token != self._load_token:
            return  # 已被递归的那次选择接手，本次不再另起加载
        self._pending_boxes = None
        self.view.clear_image("正在加载图片...")
        # ⚠️ 渲染密度必须在 **GUI 线程**先算好再传进 worker：``preview_edge()``
        # 读的是控件尺寸与 dpr，worker 线程里碰 QWidget 是越界的
        # （见 selftests/worker_thread_affinity.py）。
        edge = self.view.preview_edge()
        self.run_worker(
            lambda: PreviewWorker(path, longest_edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda page, image, p: self._image_ready_if_current(
                        token, page, image, p
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg: self._load_failed_if_current(token, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )
        self.current_changed.emit(index, str(path))


    def _image_ready_if_current(self, token: int, page: int, image, path: str) -> None:
        """只接受最新一次选择的渲染结果，迟到的旧图直接丢弃。"""
        if token == self._load_token:
            self._image_ready(page, image, path)


    def _load_failed_if_current(self, token: int, msg: str) -> None:
        """同上：只有最新一次选择的失败才允许清屏报错。"""
        if token == self._load_token:
            self.view.clear_image(f"加载失败：{msg}")


    def _original_size(self, path_text: str):
        """图片原始尺寸：优先 size_provider，否则回退读文件头。"""
        if self._image_size_provider is not None:
            size = self._image_size_provider(path_text)
            if size is not None and size.isValid():
                return size
        from PySide6.QtGui import QImageReader

        size = QImageReader(path_text).size()
        return size if size.isValid() else None


    def _image_ready(self, _page: int, image, _path: str) -> None:
        path = self.current_path()
        original = self._original_size(str(path)) if path else None
        # 无框坐标场景（如尺寸信息缺失）回退为显示图自身尺寸
        self.view.set_image(image, image_size=original if original else None)
        if self._pending_boxes is not None:
            boxes, size, info_text, full, selected = self._pending_boxes
            self._pending_boxes = None
            self.view.set_boxes(boxes, size, full=full, selected=selected)
            if info_text:
                self.info_label.setText(info_text)
                return
        if original is not None and original != image.size():
            self.info_label.setText(
                f"{original.width()} × {original.height()} 像素（预览已缩放）"
            )
        else:
            self.info_label.setText(f"{image.width()} × {image.height()} px")


    def apply_edited_image(self, path_text: str, image) -> None:
        """编辑结果**立即上屏**（不等文件重解码/缩略图重生成）。

        编辑弹窗确认后由宿主调用：当前页大图直接换成编辑结果，条目图标
        用编辑结果现缩一张，缩略图缓存随后由宿主后台重生兜底。清单里没有
        这个路径（或图无效）时是空操作。
        """
        try:
            row = [str(p) for p in self._paths].index(path_text)
        except ValueError:
            return
        if image is None or getattr(image, "isNull", lambda: True)():
            return
        # 作废在飞的加载：迟到的旧文件解码结果不许盖掉刚上屏的编辑图
        self._load_token += 1
        if row == max(self.strip.currentRow(), 0):
            size = QSize(image.width(), image.height())
            self.view.set_image(image, image_size=size)
            self.info_label.setText(f"{size.width()} × {size.height()} px")
            # 让宿主按新尺寸重读检测框（sizes.json 已先行更新）
            self.current_changed.emit(row, path_text)
        edge = self._decode_edge()
        icon = image.scaled(
            edge, edge, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.strip.set_item_icon(row, icon, path_text, Path(path_text).stem)


    def refresh_page(self, path_text: str) -> None:
        """某页缩略图缓存重生成后刷新条目图标（大图由 apply_edited_image
        即时同步过，不再重载）。路径不在清单里时是空操作。"""
        try:
            row = [str(p) for p in self._paths].index(path_text)
        except ValueError:
            return
        image = QImage(str(self._thumb_for(path_text)))
        if not image.isNull():
            self.strip.set_item_icon(
                row, image, path_text, Path(path_text).stem
            )


    def reload_thumb(self, path_text: str) -> None:
        """某张图的**文件内容**被覆盖后：忘掉旧缓存记忆并按新文件重取缩略图。

        ⚠️ 必须真的"忘掉"（:attr:`_thumb_cache_ready` 里那条）：缓存文件名带
        **大小**（``book_key`` 含 size），编辑器改了像素尺寸就换了文件名，
        而记忆里那条旧路径仍指向**覆盖前**的缓存文件——只刷不丢会一直显示
        编辑前的样子（用户报「独立步骤里编辑不生效」就是这么来的）。
        """
        text = str(path_text)
        self._thumb_cache_ready.pop(text, None)
        self.refresh_page(text)


    # -------------------------------------------------------------- 图片预览
    def _zoom_index(self) -> int:
        """放大弹窗当前页 = 缩略图条的当前行。"""
        return max(self.strip.currentRow(), 0)


    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 页的图片预览来源。

        ``cap`` 取原图原生边长：解码到超过原生尺寸只是白放大（还会白占内存），
        所以超过就按原生渲——此时 100% 恰好是"一个原生像素对一个屏幕像素"。

        ⚠️ **PDF 页模式**（图片提取页未提取时的形态）也要给得出目标：这时
        ``_paths`` 是空的、条目上写的是**页号**，走的必须是
        ``PreviewWorker(page=index)`` 那条渲页通道。不认这个形态的话，双击/
        右键在那一屏上**整个没反应**（连「预览图片」都没有），而任务流程里
        对应的「PDF 预览」标签页是能双击放大的——同一件事两处行为不一样。
        矢量页没有可回写的图片文件，所以这一支**不给** ``edit_path``。
        """
        if self._page_source is not None:
            pdf = self._page_source[0]
            total = self.strip.count()
            if not (0 <= index < total):
                return None
            return ZoomTarget(
                render=lambda edge: PreviewWorker(pdf, page=index, longest_edge=edge),
                note=f"第 {index + 1}/{total} 页 · {pdf.name}",
                stem=f"{pdf.stem}-{index + 1:04d}",
                count=total,
            )
        if not (0 <= index < len(self._paths)):
            return None
        path = self._paths[index]
        original = self._original_size(str(path))
        cap = max(original.width(), original.height()) if original else None
        return ZoomTarget(
            render=lambda edge: PreviewWorker(path, longest_edge=edge),
            note=f"第 {index + 1}/{len(self._paths)} 页 · {Path(path).name}",
            stem=Path(path).stem,
            count=len(self._paths),
            original=original,
            cap=cap,
            # 页面图就是磁盘上的真实文件：编辑器「完成」= 覆盖它
            save_path=path,
            # 编辑目标 = 这张页面图本身（第一步产出，第二步检测读的就是它）
            edit_path=path,
        )


    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """弹窗里覆盖了页面图：转发给宿主（同步 sizes.json/缩略图）。"""
        self.image_saved.emit(path_text, image)
