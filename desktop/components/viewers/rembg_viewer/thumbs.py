# -*- coding: utf-8 -*-
"""``RembgPreviewWidget`` Mixin：**缩略图缓存**。

缩略图批量加载与缓存回填/重渲。（从 ``rembg_viewer.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from desktop.workers import ImageListWorker
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import RembgViewerHost
else:
    RembgViewerHost = object


class ThumbsCacheMixin(RembgViewerHost):
    """缩略图批量加载与缓存回填/重渲。"""

    def _load_page_thumbs(self, entries: list[dict],
                          rows: list[int] | None = None) -> None:
        """加载各条目缩略图：按检测框 + area/border 合成，只显示所属部分。

        条目缩略图不是整页缩略图——area=1 时要显示"该条目那半页"，
        所以这里必须把 ``_page_thumb_for`` 返回的 ``effect`` 交给
        ``ImageListWorker`` 走 ``compose_region_output`` 合成，而不是
        传像素裁剪框 ``crops``（那会整页原样显示）。

        合成后的图按"覆盖填充"放大到条目图标尺寸并居中裁切，
        保证占满整个图标宽度（避免半幅图旁边留白）。

        ``rows``：``entries`` 是整条清单的**子集**时给出对应条目在缩略图条
        里的行号（单页文件被覆盖后只刷那几行，不重建整个条）；None = 全量，
        行号即切片下标。
        """
        thumb_paths = []
        effects = []
        labels = []
        border_mm = None
        if self._region_params_provider:
            try:
                _, border_mm = self._region_params_provider()
            except Exception:
                border_mm = None
        for entry in entries:
            real = entry["path"]
            spec = None
            # ⚠️ 缓存整页小图优先：它已经是缩放解码过的 256px 图，直接喂
            #    ImageListWorker 比再解一遍几千像素的原图省一个数量级。
            cached = self._cached_thumbs.get(real)
            if cached:
                spec = cached
            elif self._thumb_provider:
                spec = self._thumb_provider(
                    real, entry.get("box"), entry.get("parea", 1), border_mm,
                    boxes=entry.get("boxes"), full=entry.get("full", False),
                )
            if isinstance(spec, dict):
                thumb_paths.append(Path(spec["path"]))
                effects.append(spec.get("effect"))
            elif spec:
                thumb_paths.append(Path(spec))
                effects.append(None)
            else:
                thumb_paths.append(Path(real))
                effects.append(None)
            labels.append(entry["title"])
        edge = self._decode_edge()
        self._load_thumbs_chunked(
            len(thumb_paths),
            make_worker=lambda start, end: ImageListWorker(
                thumb_paths[start:end],
                edge=edge,
                effects=effects[start:end],
            ),
            sink=lambda index, image, _path: self.strip.set_item_icon(
                rows[index] if rows else index,
                self._fill_icon(image), "", labels[index]
            ),
        )


    def set_cached_thumbs(self, mapping: dict[str, str]) -> None:
        """告诉本控件哪些图已有缓存小图（``真实图路径 → 缓存路径``）。

        用户 2026-10-03：所有独立任务左栏都显示缩略图，且统一缓存在
        ``~/Documents/guji/singletask``。这里**只换缩略图来源**、不动条目与
        大图——所以宿主渲好一张就能立刻刷那一条（``refresh_page``），
        不必重建整个缩略图条。

        ⚠️ 缓存里存的是**整页**小图；条目若按检测框裁了一块/合成区域
        （area=1 的 ``-l``/``-r``），仍由 :meth:`_load_page_thumbs` 走区域合成
        ——只是输入图从「原图」换成「已缩好的整页小图」，省掉整张解码。

        ⚠️ 语义是**整体替换**（调用点给的就是完整的映射）。只更新一条请用
        :meth:`set_cached_thumb`。
        """
        self._cached_thumbs = {
            str(k): str(v) for k, v in (mapping or {}).items()
        }
        if not self._cached_thumbs or not self._entries:
            return
        rows = [
            i for i, entry in enumerate(self._entries)
            if entry["path"] in self._cached_thumbs
        ]
        if rows:
            self._load_page_thumbs([self._entries[i] for i in rows], rows=rows)


    def set_cached_thumb(self, path_text: str, cache: str) -> None:
        """**单张**：记下它的缓存小图并只刷相关条目 + 当前大图。

        与 :meth:`set_cached_thumbs` 的差别是**合并一条**而不是整体替换——
        宿主在"某张图被编辑后重渲缩略图"这条路上只关心这一条，整体替换会
        把其余条目的缓存映射一起丢掉（它们随后只能回落去解码原图）。
        """
        text = str(path_text)
        if cache:
            self._cached_thumbs[text] = str(cache)
        else:
            self._cached_thumbs.pop(text, None)
        self.refresh_page(text)


    def reload_thumb(self, path_text: str) -> None:
        """某张图的**文件内容**被覆盖后：丢掉它的缓存映射并按新文件重取。

        ⚠️ 与 :meth:`desktop.components.viewers.ImageViewerWidget.reload_thumb`
        同一个理由：缓存文件名带**大小**，编辑改了像素尺寸就换了文件名，
        留着旧映射会一直显示覆盖前的缩略图。
        """
        text = str(path_text)
        self._cached_thumbs.pop(text, None)
        self.refresh_page(text)
