# -*- coding: utf-8 -*-
"""图片查看器：缩略图条 + 大图，支持切割框叠加与页面增删按钮。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, ToolButton
from qfluentwidgets import FluentIcon as FIF

from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin


class ImageViewerWidget(QWidget, ThumbsMixin):
    """图片查看器：缩略图条 + 大图，支持切割框叠加、拖动与页面增删按钮。"""

    current_changed = Signal(int, str)
    delete_requested = Signal()
    insert_requested = Signal()
    boxes_edited = Signal(str, list)  # (图片路径, 全部框坐标) 拖动结束后发出

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
        self._pending_boxes: tuple | None = None  # (boxes, image_size, info)，等大图加载后应用
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

    def set_images(self, paths: list[Path], boxes_map: dict | None = None) -> None:
        """设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。

        paths 为 Path 列表；boxes_map 预留（当前未用）。清单不变时跳过
        重建，但仍 emit current_changed 让宿主重新读取该页检测框/参数。
        """
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

    def apply_boxes(self, boxes: list[tuple], image_size: QSize, info_text: str = "") -> None:
        """在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。"""
        if self.view.has_image:
            self.view.set_boxes(boxes, image_size)
            if info_text:
                self.info_label.setText(info_text)
        else:
            self._pending_boxes = (boxes, image_size, info_text)

    def set_reference_boxes(self, boxes: list) -> None:
        """设置参考框（最终裁剪大框，虚线显示，不参与编辑）。"""
        self.view.set_reference_boxes(boxes)

    def _boxes_edited(self, boxes: list) -> None:
        path = self.current_path()
        if path is not None:
            self.boxes_edited.emit(str(path), boxes)

    def _thumb_for(self, path_text: str) -> Path:
        if self._thumb_provider:
            spec = self._thumb_provider(path_text)
            if spec is None:
                return Path(path_text)
            if isinstance(spec, dict):
                return Path(spec["path"])
            return Path(spec)
        return Path(path_text)

    def _load_thumbs(self, strip, paths: list[Path]) -> None:
        """带提供者时加载映射后的缩略图，标签仍使用真实页面名。

        ⚠️ 分批调度走基类的 ``_load_thumbs_chunked``（首批立即、其余延后），
        这里只负责给出「切片 → worker」与「全局下标 → 条目」两个函数。
        """
        if not self._thumb_provider:
            super()._load_thumbs(strip, paths)
            return
        real_paths = list(paths)
        thumb_paths = [self._thumb_for(str(p)) for p in real_paths]
        labels = [Path(p).stem for p in real_paths]
        self._load_thumbs_chunked(
            len(real_paths),
            make_worker=lambda start, end: ImageListWorker(
                thumb_paths[start:end], edge=ThumbStrip.DECODE_EDGE
            ),
            sink=lambda index, image, _path: strip.set_item_icon(
                index, image, str(real_paths[index]), labels[index]
            ),
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
        self.run_worker(
            lambda: PreviewWorker(path, longest_edge=1600),
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
            boxes, size, info_text = self._pending_boxes
            self._pending_boxes = None
            self.view.set_boxes(boxes, size)
            if info_text:
                self.info_label.setText(info_text)
                return
        if original is not None and original != image.size():
            self.info_label.setText(
                f"{original.width()} × {original.height()} px（预览已缩放）"
            )
        else:
            self.info_label.setText(f"{image.width()} × {image.height()} px")
