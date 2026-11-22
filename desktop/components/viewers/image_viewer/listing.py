# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``ImageViewerWidget`` 的**清单装填 / 缩略图 / 选页加载**（ListingMixin）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.thumb_strip import ThumbStrip

if TYPE_CHECKING:
    from ._host import ImageViewerHost
else:
    ImageViewerHost = object


class ListingMixin(ImageViewerHost):
    """页面清单、缩略图装填与当前页大图的加载编排。"""

    def set_images(
        self, paths: list[Path | str], boxes_map: dict | None = None,
        force: bool = False,
    ) -> None:
        """设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。

        ``paths`` 元素可以是 ``Path`` **或** ``str``——统一在这里转成 ``Path``
        再往下传。⚠️ 这不是顺手为之：内部 ``_select_image`` 把元素直接交给
        :class:`~desktop.workers.PreviewWorker`，而那个 worker 在 ``run()`` 里
        要读 ``self.path.suffix``；调用方传字符串的话，异常发生在**子线程
        run() 内部**，只经 ``failed`` 信号回到预览区显示成
        「加载失败：'str' object has no attribute 'suffix'」（用户 2026-10-03 报）。
        在边界一次收干净，比让每个调用点各自记得 ``str(p)``→``p`` 可靠。

        ``boxes_map`` 预留（当前未用）。

        ``force``：清单**一模一样**时也把图标重新解码一遍（保留当前行与选中）。
        ⚠️ 为什么需要：这些页面图会被**同名覆盖**（单页重提取、编辑器回写），
        路径清单看不出变化，而条目图标是**解码一次就存进 QIcon**的——不强制
        重装就永远停在覆盖前那张。判据由宿主按"上游产物内容变了没有"给出
        （``desktop.utils.files.dir_content_signature``），不是每次刷新都强制。
        """
        # ⚠️ 进图片模式先退出 PDF 页模式：``set_pdf_source`` 把清单留空、
        #    条目标签是「第 N 页」，若不退出，:meth:`_select_image` 会把
        #    ``1.jpg`` 当页号去 PDF 里渲第 1 页——提取完成后左栏看着有图，
        #    点哪页都是同一页（extract 页踩过这个：上屏的是 PDF 而不是产物）。
        self._clear_page_source()
        paths = [Path(p) for p in paths]
        if (
            self._buffers_released
            and paths == self._paths
            and self.strip.count() == len(paths)
        ):
            # 离开步骤时释放过、清单又没变：**只重装**，不整条 clear+重建
            # （重建会把当前行打回第一条——用户切回来看的应该还是那一页）。
            self.restore_buffers()
            index = max(self.strip.currentRow(), 0)
            if self._paths:
                self.current_changed.emit(index, str(self._paths[index]))
            return
        if (
            paths == self._paths
            and self.strip.count() == len(paths)
            and not self._buffers_released
        ):
            # 清单未变化：默认跳过重建，但仍需通知宿主重新读取
            # 该页的检测框/参数（可能在其他阶段被更新过）。
            # ⚠️ ``force`` 时**重解一遍图标**（不 clear 列表：当前行/选中要保持，
            #    条目高度与标签也不该因刷新而抖）。
            if not paths:
                # 本来就没图：顶部提示条不该留着上一批页的"在图上拖一下"
                self.set_hint_banner("")
            if force and self._paths:
                self._load_thumbs(self.strip, list(self._paths))
            index = max(self.strip.currentRow(), 0)
            if self._paths:
                self.current_changed.emit(index, str(self._paths[index]))
            return
        self.close_zoom_popup()  # 清单换了：弹窗里那页已是旧数据
        # 清单变了：本次会整条重建（图标 + 大图），释放标记自然失效
        self._buffers_released = False
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
            # 没有图就没有"在图上拖一下"的提示（不然提示条会浮在空态上）
            self.set_hint_banner("")
            return
        for index, path in enumerate(paths):
            self.strip.add_page_item(Path(path).stem, str(path))
        self._load_thumbs(self.strip, paths)
        self._select_image(0, str(paths[0]))

    def release_buffers(self) -> None:
        """离开本步骤：丢掉大图与整条缩略图位图（清单/当前行原地保留）。

        只释放**可重建的位图**：大图（含降采样底图）与条目图标都是几十 MB
        级的解码结果，离开这一步就再也用不到；回来由 :meth:`restore_buffers`
        按同一份清单重装（图标走 ``_load_thumbs`` 的缓存小图，不重新解码原图）。

        ⚠️ 不改 ``_paths`` / 不清 ``currentRow``：切回来要停在用户原来那页，
        且 ``set_images`` 的增量/早退判据都靠这两样。
        """
        self._buffers_released = True
        self._load_token += 1      # 在飞的大图加载作废（结果回来也不再上屏）
        self._pending_boxes = None
        self.view.clear_image("")
        self.strip.release_icons()

    def restore_buffers(self) -> None:
        """回来：重装条目图标 + 重载当前页大图（未被释放时是空操作）。"""
        if not self._buffers_released:
            return
        self._buffers_released = False
        if not self._paths:
            self.view.clear_image(self._empty_hint)
            return
        self._load_thumbs(self.strip, list(self._paths))
        row = max(self.strip.currentRow(), 0)
        self._select_image(row, str(self._paths[row]))

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

    def _load_thumbs(self, strip: ThumbStrip, paths: list[Path | str],
                     start: int = 0) -> None:
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
            strip=strip,
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
        # （见 selftests/safety/worker_thread_affinity.py）。
        edge = self.view.preview_edge()
        # 「按参数合成」的预览（目前只有 PDF排版 的打印效果）：只作用于大图，
        # 缩略图条仍按真实文件解码（见 set_preview_spec_provider）。
        spec = self._preview_spec_for(str(path), index)
        self.run_worker(
            lambda: PreviewWorker(
                path,
                # 给了 spec ⇒ 排版按 target_edge 的密度重新绘制，不能再缩放一次
                # （否则标题/页码糊掉；实测结论同 PrintPreviewWidget）。
                longest_edge=0 if spec else edge,
                print_spec=(
                    {**spec, "target_edge": max(edge, ImageView.MAX_PREVIEW_EDGE)}
                    if spec else None
                ),
            ),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda page, image, p, s=spec: self._image_ready_if_current(
                        token, page, image, p, s
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
