# -*- coding: utf-8 -*-
"""``ImageViewerWidget`` Mixin：**缩略图缓存**。

缩略图来源/缓存键/后台重渲。（从 ``image_viewer.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import ImageViewerHost
else:
    ImageViewerHost = object


class ThumbsCacheMixin(ImageViewerHost):
    """缩略图来源/缓存键/后台重渲。"""

    # ------------------------------------------------------- 缩略图缓存接线
    def set_thumb_source(
        self, paths: list[Path | str], cache_dir: Path | str,
        edge: int | None = None,
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
        cache_dir = self._thumb_cache_dir
        assert cache_dir is not None  # 调用点（_lookup_thumb_path）已判过 None
        names = self._thumb_cache_names
        if names is not None and 0 <= index < len(names) and names[index]:
            # ⚠️ names[index] 已判过非空，这里再 cast 一次让类型收窄落到 str：
            # 索引取值后类型检查器不再记得上面的真值判断。
            return cache_dir / str(names[index])
        from desktop.workers.thumb_cache_worker import thumb_cache_file

        return thumb_cache_file(cache_dir, path)


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


    def _start_thumb_cache(self, paths: list[Path | str]) -> None:
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
        # ⚠️ 没设缓存目录（set_thumb_source 没调）时下面拼不出缩略图路径，
        #     直接不启动——与 _lookup_thumb_path 的同一道守卫。
        if cache_dir is None:
            return
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
