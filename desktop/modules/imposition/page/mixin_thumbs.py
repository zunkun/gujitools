# -*- coding: utf-8 -*-
"""独立拼图页的左列缩略图实体管理（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from desktop.services.imposition import same_path
from desktop.utils.files import THUMBNAIL_EDGE as THUMB_EDGE

from .constants import _SPEC


class ThumbsMixin:
    """左列可见窗口、缩略图实体生成与失效。"""

    def _on_viewport_changed(self) -> None:
        """左列可见范围变了：让缩略图管理者按新窗口补一批。"""
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is not None:
            manager.refresh_window()

    # -------------------------------------------------------------- 缩略图
    def _page_thumb_manager(self):
        """页面缩略图**实体**的管理者（懒建，首用即钉在独立区目录上）。"""
        from desktop.components.imposition.page_thumb import PageThumbManager
        from desktop.utils.files import page_thumbs_dir

        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is None:
            manager = PageThumbManager(
                page_thumbs_dir(_SPEC.disk_key()), THUMB_EDGE,
                self.run_worker, parent=self,
                # 只生成左列看得见的那几页（同任务流程拼版页；2026-11-21）
                window_provider=self.view.visible_page_range,
            )
            manager.page_ready.connect(self._on_page_thumb_ready)
            self._page_thumb_mgr = manager
        manager.set_window_provider(self.view.visible_page_range)
        return manager

    def _on_page_thumb_ready(self, index: int, pixmap) -> None:
        """一页的实体缩略图生成完：贴回左列那一条。"""
        if pixmap is not None and not pixmap.isNull():
            self.view.set_thumb_at(index, pixmap)

    def _invalidate_page_thumbs_for(
        self, path_text: str, hits: list[int] | None = None
    ) -> None:
        """某张源图被覆盖（编辑落盘）：含它的页重新生成缩略图实体。

        ⚠️ 签名里带**源图文件指纹**（大小+mtime）：覆盖后签名必然变
        ⇒ 把含这个路径的页排进重生成批次即可。路径形态（斜杠/大小写）
        走 :func:`services.imposition.same_path` 判等（2026-10-08 报障
        "编辑完左列还是老图"的实体版防复发）。
        """
        pages = self._doc.get("pages") or []
        if hits is None:
            hits = [
                index for index, page in enumerate(pages)
                if any(same_path(str(item.get("file") or ""), path_text)
                       for item in page.get("items") or [])
            ]
        if hits:
            self._page_thumb_manager().invalidate(hits, pages)

    def _refresh_page_thumbs(self) -> None:
        """左列每页的缩略图：**页面效果**（落盘实体 ``pageN.jpg``）。

        旧口径"每页取第一张源图当代表"只显示半幅；上一版内存合成口径
        页内某张源图缩略图没到就出半张（用户 2026-10-09 在 0002 任务上
        二次报障，拍板：**缩略图实体要生成落地**，另放目录、按 page1
        page2 命名、做好映射数据）。现在是实体口径：按版面把整页合成
        一张小图落盘（``singletask/imposition/page_thumbs/page<N>.jpg``
        + ``index.json`` 映射），UI 只贴实体文件；签名（版面 + 源图文件
        指纹）不匹配的页后台重生成。命中的页直接读盘——重进页面零生成。

        ⚠️ 与任务流程拼版页共用管理者组件，但**缓存根各归各**（用户
        2026-10-04 明确「singletask 和 taskdetail 不是一回事」）。
        """
        pages = self._doc.get("pages") or []
        manager = self._page_thumb_manager()
        manager.retain(len(pages))
        thumbs = [manager.pixmap_for(i, page) for i, page in enumerate(pages)]
        self._page_thumbs = thumbs
        self.view.set_page_thumbs(thumbs)
        manager.flush()
