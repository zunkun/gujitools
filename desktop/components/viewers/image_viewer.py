# -*- coding: utf-8 -*-
"""图片查看器：缩略图条 + 大图，支持切割框叠加与页面增删按钮。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import (
    ZoomPopupMixin, ZoomTarget,
)
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin


class ImageViewerWidget(QWidget, ThumbsMixin, ZoomPopupMixin):
    """图片查看器：缩略图条 + 大图，支持切割框叠加、拖动与页面增删按钮。"""

    current_changed = Signal(int, str)
    delete_requested = Signal()
    insert_requested = Signal()
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
        parent=None,
    ):
        """
        构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。

        image_size_provider 供大图降采样时还原原始像素尺寸；thumb_provider
        让缩略图条改用预生成小图，避免反复解码原图。
        """
        super().__init__(parent)
        self._init_thumbs()
        self._paths: list[Path] = []
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
            insert_btn.setToolTip("插入外部图片到所选位置之后")
            insert_btn.clicked.connect(self.insert_requested.emit)
            buttons.addWidget(delete_btn)
            buttons.addWidget(insert_btn)
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
        self._init_zoom_popup(self.view)
        self._pending_boxes: tuple | None = None  # (boxes, image_size, info, full)，等大图加载后应用
        #: 每次选页递增的加载令牌，只有最新一次选择的渲染结果允许上屏。
        #: ⚠️ 不能改用「路径是否相同」判断：同一页也会被重复选择（见
        #: ``_select_image`` 的递归回调），路径一样但加载任务有两个。
        self._load_token = 0

    @property
    def paths(self) -> list[Path]:
        """当前页面清单（按显示顺序）。"""
        return self._paths

    def current_path(self) -> Path | None:
        """当前选中的页面路径；无选中或无清单时为 None。"""
        row = max(self.strip.currentRow(), 0)
        if row < len(self._paths):
            return self._paths[row]
        return None

    def navigate(self, forward: bool) -> None:
        """方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。"""
        self.strip.navigate(forward)

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

    # ------------------------------------------------------- 缩略图缓存接线
    def set_thumb_source(
        self, paths: list[Path], cache_dir: Path, edge: int | None = None,
        names: list[str | None] | None = None,
    ) -> None:
        """清单是真实图片，但左侧缩略图走 ``cache_dir`` 下的**缓存小图**。

        用户 2026-10-03：所有独立任务左侧都显示缩略图，且统一缓存在
        ``~/Documents/guji/singletask``。清单本身**仍然是真实图片路径**——
        右侧大图、检测框按 ``Path(path).stem`` 取键、放大弹窗的编辑回写，
        全都指着真实文件；缓存只喂缩略图条。

        实现方式是**替换缩略图来源**而不是替换清单：``_thumb_provider`` 由
        :meth:`set_thumb_source` 装上，:meth:`set_images` 的
        ``_load_thumbs`` 会自动走它（它本来就支持 ``thumb_provider``）。

        ``names``（可选，与 ``paths`` 等长）：每张图的**显式缓存文件名**。
        extract 的缓存名是**序号**（``0001.jpg``）而非图键——同一页在
        「未提取」阶段是 PDF 渲染、「提取后」是产物重渲，两次写**同一个文件**，
        目标名只能由调用方给出（用户 2026-10-04「只保留一份、按序号处理」）。
        """
        self._thumb_cache_dir = Path(cache_dir)
        self._thumb_cache_edge = edge
        self._thumb_cache_ready: dict[str, Path] = {}
        self._thumb_cache_worker = None
        #: 每条清单对应的缓存文件名（None = 按图键命名）；供 ``_thumb_cache_lookup``
        #: 与 ``_reload_edited_thumb`` 用**同一份**规则算出目标路径。
        self._thumb_cache_names = list(names) if names is not None else None
        self.set_images(paths)
        self._start_thumb_cache(paths)

    def _thumb_cache_target(self, index: int, path: Path) -> Path:
        """第 ``index`` 张清单项的缓存文件路径（显式名优先，否则按图键）。"""
        names = self._thumb_cache_names
        if names is not None and 0 <= index < len(names) and names[index]:
            return Path(self._thumb_cache_dir) / names[index]
        from desktop.workers.thumb_cache_worker import thumb_cache_file

        return thumb_cache_file(Path(self._thumb_cache_dir), path)

    def _lookup_thumb_path(self, path_text: str) -> Path | None:
        """``thumb_provider`` 用的查询：某张清单项的缓存文件路径。

        ⚠️ 必须按**清单下标**定位显式名，不能按 ``path_text`` 猜：序号口径下
        缓存名是 ``0001.jpg``，与源图文件名无关，只有清单顺序能对上。
        找不到就返回 None（调用点回落到 provider / 原图）。
        """
        if self._thumb_cache_dir is None:
            return None
        try:
            index = [str(p) for p in self._paths].index(path_text)
        except ValueError:
            return None
        try:
            return self._thumb_cache_target(index, Path(path_text))
        except (IndexError, TypeError):
            return None

    def _start_thumb_cache(self, paths: list[Path]) -> None:
        """后台把这批图的缩略图渲进缓存，逐张回填缩略图条。

        ⚠️ **分批调度交给基类**（:meth:`ThumbsMixin._load_thumbs_chunked`，
        首批立即、其余延后），**不要**在这里自己切两批起两个 worker：切片
        下标要另行换算，且一批空转也会走一遍 ``set_item_icon``——那正是
        ``worker_thread_affinity`` 自测逮到的那类"同一页被画两次"。

        ⚠️ **不等它跑完就先把清单上屏**（``set_images`` 已在上一步做完）：用户
        选完源就该立刻看到这批图（缩略图条先占位），而不是等磁盘缓存写完。
        """
        from desktop.workers.thumb_cache_worker import ImageThumbCacheWorker

        if not paths:
            return
        edge = self._thumb_cache_edge or self._decode_edge()
        cache_dir = self._thumb_cache_dir
        names = self._thumb_cache_names
        # ⚠️ 切片要**连同 names 一起切**：序号口径下缓存文件名与清单下标一一
        # 对应，忘了切片就会拿第 0..N 项的名字配第 N..2N 项的图（张冠李戴）。
        # 洞位（None）会回落到图键命名，所以拼接时原样保留 None。
        worker_names = (
            None if names is None else names[: len(paths)]
        )
        self._load_thumbs_chunked(
            len(paths),
            make_worker=lambda s, e: ImageThumbCacheWorker(
                paths[s:e], cache_dir, edge=edge,
                names=None if worker_names is None else worker_names[s:e],
            ),
            sink=lambda index, image, cached: self._on_thumb_cached(
                index, image, cached
            ),
        )
        # 供宿主/自测查询某张图的缓存路径（显式名优先，与 worker 同一份规则）
        self._thumb_cache_lookup = lambda path: self._lookup_thumb_path(path)

    def _on_thumb_cached(self, index: int, image, cached: str) -> None:
        """一张缓存缩略图就绪：记下路径并把缩略图条上那一条换成小图。

        ⚠️ 清单已经换过（用户又选了别的源）时这一条直接跳过——否则会拿旧清单
        的图盖到新条目上。基类的代际令牌也会挡掉上一轮的迟到回调。
        """
        if not (0 <= index < len(self._paths)) or index >= self.strip.count():
            return
        real = self._paths[index]
        if cached:
            self._thumb_cache_ready[str(real)] = Path(cached)
        if image is not None and not getattr(image, "isNull", lambda: True)():
            self.strip.set_item_icon(
                index, image, str(real), Path(real).stem
            )

    def set_pdf_source(
        self, pdf: Path | str, cache_dir: Path | None = None, gen: int = 0,
    ) -> None:
        """源是一本 **PDF**：左栏显示它的页缩略图，右侧大图按需渲高清页。

        这是「图片提取」页未提取时的形态（用户 2026-10-03：「在未提取图片之前
        是按照缩略图，单独图片显示」）——选完 PDF 就能翻页看，不必先跑一遍提取。

        ⚠️ 缩略图条显示的是 256px 缓存小图，但**右侧大图不是拿小图放大**：
        点哪页就按需从 PDF 渲那一页（``_select_image`` 见 ``_page_source``），
        所以放大事先看得清。缩略图由宿主用
        :class:`~desktop.modules.thumb_source.ThumbSourceMixin` 起 pass 填充，
        本方法只负责建条目（:meth:`begin_pdf_pages`）。

        ``gen`` 是代际号：换书时宿主递增，本控件据此丢弃旧书迟到的缩略图信号。
        """
        self._clear_page_source()
        self._page_source = (Path(pdf), gen)
        self._page_source_cache = Path(cache_dir) if cache_dir else None
        self._thumb_provider = None
        self._thumb_cache_dir = None
        self._thumb_cache_ready = {}
        self._thumb_cache_names = None
        self._paths = []
        self.close_zoom_popup()
        self.view.clear_image("正在加载缩略图…")
        self.strip.clear()
        self.strip.add_placeholder("缩略图生成中…")
        self.info_label.setText("")

    def begin_pdf_pages(self, count: int, path: str = "") -> None:
        """PDF 页数已known：按「第 N 页」建缩略图条目并选中第一页。

        ⚠️ 与 ``PdfViewerWidget._metadata_ready`` 同一道护栏：后续轮次
        （回扫/补缺页）页数没变时**不能清空重建**——那会把已经加载好的图标
        全丢掉，只剩占位符。
        """
        if self._page_source is None or count <= 0:
            return
        if self.strip.count() == count:
            return
        self.strip.clear()
        self._paths = []
        for page in range(count):
            self.strip.add_page_item(f"第 {page + 1} 页", str(page))
        self.strip.setCurrentRow(0)
        self._select_pdf_page(0)

    def set_pdf_thumb(self, gen: int, index: int, image) -> None:
        """PDF 第 index 页的缩略图就绪：填进缩略图条第 index 条。

        ``gen`` 与 :meth:`set_pdf_source` 传的一致才算数——旧书那个还在跑的
        worker 迟到时会被丢弃，否则**旧书的页会画进新书的缩略图条**。
        """
        if self._page_source is None or gen != self._page_source[1]:
            return
        if not (0 <= index < self.strip.count()):
            return
        if image is None or getattr(image, "isNull", lambda: True)():
            return
        scaled = image.scaled(
            ThumbStrip.ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.strip.set_item_icon(
            index, scaled, str(index), f"第 {index + 1} 页"
        )

    def _clear_page_source(self) -> None:
        """退出 PDF 页模式（提取完成 → 换成提取出的图片）。"""
        self._page_source = None
        self._page_source_cache = None

    def _select_pdf_page(self, index: int) -> None:
        """按需渲 PDF 第 index 页的高清大图（未命中页间缓存时）。"""
        if self._page_source is None:
            return
        if not (0 <= index < self.strip.count()):
            return
        self.strip.setCurrentRow(index)
        self._load_token += 1
        token = self._load_token
        pdf = self._page_source[0]
        self.view.clear_image(f"正在渲染第 {index + 1} 页...")
        # ⚠️ 渲染密度在 GUI 线程先算好：worker 线程里碰 QWidget 是越界的
        edge = self.view.preview_edge()
        self.run_worker(
            lambda: PreviewWorker(pdf, page=index, longest_edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda page, image, _p, t=token: (
                        self._pdf_page_ready(t, image)
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg, t=token: self._pdf_page_failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )
        self.current_changed.emit(index, str(index))

    def _pdf_page_ready(self, token: int, image) -> None:
        """PDF 高清页就绪：只有最新一次选页的结果允许上屏。"""
        if token != self._load_token:
            return  # 用户已经点了别的页：迟到的旧页不上屏
        self.view.set_image(image)
        row = max(self.strip.currentRow(), 0)
        total = self.strip.count()
        self.info_label.setText(
            f"第 {row + 1}/{total} 页 · 缩略图预览"
            if total else ""
        )

    def _pdf_page_failed(self, token: int, message: str) -> None:
        if token != self._load_token:
            return
        self.view.clear_image(f"渲染失败：{message}")

    def apply_boxes(self, boxes: list[tuple], image_size: QSize, info_text: str = "",
                    full: bool = False, selected: int = -1) -> None:
        """在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。

        ``full=True`` 表示本页是整幅(fullcontent)：框显示为「整幅」且只允许一个；
        否则按框的**中心位置**显示为左/右框。名称/颜色由控件每帧现算，不用传。
        ``selected`` 为要选中的框下标（-1 = 不选），用于切换类型后保持选中。
        """
        if self.view.has_image:
            self.view.set_boxes(boxes, image_size, full=full, selected=selected)
            if info_text:
                self.info_label.setText(info_text)
        else:
            self._pending_boxes = (boxes, image_size, info_text, full, selected)

    def set_reference_boxes(self, boxes: list) -> None:
        """设置参考框（最终裁剪大框，虚线显示，不参与编辑）。"""
        self.view.set_reference_boxes(boxes)

    def select_box(self, index: int) -> None:
        """程序化选中第 index 个框（-1 = 取消选中）。"""
        self.view.select_box(index)

    def selected_index(self) -> int:
        """当前选中的框下标；无选中为 -1。"""
        return self.view.selected_index()

    def box_full_mode(self) -> bool:
        """本页是否为整幅(fullcontent)。"""
        return self.view.full_mode

    def box_kinds(self) -> list:
        """当前每个框的类型（"left"/"right"/"full"）。"""
        return self.view.box_kinds()

    def _boxes_edited(self, boxes: list) -> None:
        path = self.current_path()
        if path is not None:
            self.boxes_edited.emit(str(path), boxes)

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

    def _load_thumbs(self, strip, paths: list[Path], start: int = 0) -> None:
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
            note=f"第 {index + 1}/{len(self._paths)} 页 · {path.name}",
            stem=path.stem,
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
