# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``ImageViewerWidget`` 的**大图展示**（DisplayMixin）：上屏、刷新与尺寸文案。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from desktop.utils.image_scaling import smooth_downscale

if TYPE_CHECKING:
    from ._host import ImageViewerHost
else:
    ImageViewerHost = object


class DisplayMixin(ImageViewerHost):
    """当前页大图的上屏、重载与信息条。"""

    def set_preview_spec_provider(self, provider) -> None:
        """设置「大图按参数合成」的提供者（``None`` = 关掉，显示原图）。

        ``provider(path_text, index, total) -> dict | None``：返回的字典原样交给
        ``PreviewWorker(print_spec=...)``（几何规则见 ``utils.page_layout``），
        并可带一个 ``note`` 键——它会顶替大图下方那行"原始像素尺寸"文案。

        用户 2026-11-21：独立功能页也要"改参数立刻看单张效果"。参数变化后的
        重载走 :meth:`refresh_current`，两者配合就是实时预览。

        ⚠️ **只影响大图**：缩略图条仍按真实文件解码——把排版效果套到缩略图上
        会让每一条都变成一整张纸（全白、看不清内容，还慢）。
        """
        self._preview_spec_provider = provider
        self.refresh_current()

    def refresh_current(self) -> None:
        """按**最新参数**重载当前页大图（清单、缩略图条、当前行都不动）。

        PDF 页模式（提取页未提取时的形态）直接返回：那里没有"按参数重合成"
        的语义，页内容由 PDF 本身决定。
        """
        if self._page_source is not None:
            return
        row = max(self.strip.currentRow(), 0)
        if 0 <= row < len(self._paths):
            self._select_image(row, str(self._paths[row]))

    def _preview_spec_for(self, path_text: str, index: int) -> dict | None:
        """向宿主要这一页的合成参数；没接提供者/宿主抛异常时退回原图。

        宿主抛异常（参数填了一半、条目越界）不该阻断预览——这一帧显示原图，
        参数改对之后下一个防抖周期再来。
        """
        provider = self._preview_spec_provider
        if provider is None:
            return None
        try:
            spec = provider(path_text, index, len(self._paths))
        except Exception:  # noqa: BLE001 - 预览不该被宿主参数问题拖死
            return None
        return spec if isinstance(spec, dict) and spec else None

    def _image_ready_if_current(
        self, token: int, page: int, image, path: str, spec: dict | None = None
    ) -> None:
        """只接受最新一次选择的渲染结果，迟到的旧图直接丢弃。"""
        if token == self._load_token:
            self._image_ready(page, image, path, spec)

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

    def _image_ready(
        self, _page: int, image, _path: str, spec: dict | None = None
    ) -> None:
        path = self.current_path()
        original = self._original_size(str(path)) if path else None
        # 无框坐标场景（如尺寸信息缺失）回退为显示图自身尺寸
        self.view.set_image(image, image_size=original if original else None)
        if spec is not None:
            # 合成预览（打印效果）显示的不是原图：别再拿"原始像素尺寸/预览已
            # 缩放"去解释它（会让人以为图被裁了）。宿主给的 note 才说得清。
            note = str(spec.get("note") or "")
            if note:
                self.info_label.setText(note)
                return
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
        # 编辑结果可能是全分辨率大图：走分档降采样，缩略图才不糊（见 image_scaling）
        icon = smooth_downscale(image, edge)
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
