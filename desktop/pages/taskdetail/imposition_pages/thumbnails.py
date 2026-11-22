# -*- coding: utf-8 -*-
"""模块一「选择拼版」的**左列缩略图**分片：可视窗口、实体管理者与刷新。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.services.imposition import same_path

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_pages._host import (
        ImpositionPagesHost,
    )
else:
    ImpositionPagesHost = object


class ThumbnailsMixin(ImpositionPagesHost):
    """左列页面缩略图的可见窗口、实体管理者与重生成。"""

    # ------------------------------------------------------------- 左列缩略图
    def _imposition_thumb_window(self) -> tuple[int, int] | None:
        """左列**当前可见**的页号闭区间（缩略图只给这几页生成实体）。

        取不到（视图还没建/还没布局）返回 ``None`` ⇒ 管理者退化成"不筛"。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return None
        return view.visible_page_range()

    def _on_imposition_viewport_changed(self) -> None:
        """左列滚动/翻页/换任务：把新进窗口的页排进缩略图生成队列。

        ⚠️ 生成期间**不抢**（``refresh_window`` 在飞时直接返回）：那一批跑完
        的收尾回调会按**那一刻**的窗口再补一批，正好接上用户滚到的位置。
        """
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is not None:
            manager.refresh_window()

    def _imposition_page_thumb_manager(self):
        """页面缩略图**实体**的管理者（懒建；换任务自动换目录重读映射）。"""
        from desktop.components.imposition.page_thumb import PageThumbManager
        from desktop.utils.files import THUMBNAIL_EDGE

        if not self.task_id:
            return None
        # ⚠️ 目录按**当前拼版节点**取（B 方案）：两个「图片拼版」节点各有各的
        #    版面文档与合成产物，页面效果缩略图实体也跟着分
        #    （``thumbnails/imposition_pages[~<节点>]``），否则副本节点会读到主
        #    节点的实体（用户在另一节点改动版面，这一节点左列却显示旧图）。
        target = self.store.imposition_page_thumbs_dir(
            self.task_id, self.node_of_stage("imposition")
        )
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is None:
            manager = PageThumbManager(
                target, THUMBNAIL_EDGE, self.run_worker, parent=self,
                # 只生成左列**看得见**的那几页（用户 2026-11-21：拼版首屏
                # 在生产环境要等 5 分钟——整本 81 页一次性排进去，还要跟整本
                # 成品合成抢同一个进程）
                window_provider=self._imposition_thumb_window,
            )
            manager.page_ready.connect(self._on_imposition_page_thumb_ready)
            self._page_thumb_mgr = manager
        elif manager.directory != target:
            manager.bind(target)
        manager.set_window_provider(self._imposition_thumb_window)
        return manager

    def _on_imposition_page_thumb_ready(self, index: int, pixmap) -> None:
        """一页的实体缩略图生成完：**只贴那一条**（反 O(N²) 护栏，2026-10-06）。"""
        view = getattr(self, "imposition_view", None)
        if view is not None and pixmap is not None and not pixmap.isNull():
            view.set_thumb_at(index, pixmap)

    def _refresh_imposition_page_thumbs(self, pages: list) -> None:
        """左列每页的缩略图：**落盘实体**（页面效果，``pageN.jpg``）。

        用户 2026-10-09 两轮报障的合流：①一页拼版是两张图合成的页面，旧
        口径"每页取第一张源图当代表"只显示半幅；②内存合成口径页内某张
        源图缩略图没到就出半张、且回填反查表只登记每页第一张（0002 任务
        实测 3-l·4-r 页只有半边有内容）。现在改**实体**口径：按版面把整页
        合成一张小图落盘（``tasks/<id>/thumbnails/imposition_pages/
        page<N>.jpg`` + ``index.json`` 映射），UI 只贴实体文件；签名（版面
        + 源图文件指纹）不匹配的页后台重生成。命中的页直接读盘——重进
        任务零生成。

        ⚠️ 与独立拼图页（``modules/imposition/page.py``）共用管理者组件，
        但**缓存根各归各**（用户 2026-10-04 明确「singletask 和 taskdetail
        不是一回事」）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        manager = self._imposition_page_thumb_manager()
        if manager is None:
            return
        manager.retain(len(pages))
        by_index = [manager.pixmap_for(i, page) for i, page in enumerate(pages)]
        view.set_page_thumbs(by_index)
        manager.flush()

    def _drop_imposition_source_thumb(self, path_text: str) -> None:
        """某个源图被覆盖（编辑落盘）：含它的页重新生成缩略图实体。

        ⚠️ 签名里带**源图文件指纹**（大小 + mtime）：覆盖后签名必然变
        ⇒ 把含这个路径的页排进重生成批次即可，不用逐张清内存缓存（旧
        内存口径的坑：同路径换内容照旧贴回旧 QPixmap——用户 2026-10-08
        报"编辑完左列还是老图"）。路径形态（斜杠/大小写）仍走
        :func:`same_path` 判等。
        """
        pages = self._imposition_pages()
        hits = [
            index for index, page in enumerate(pages)
            if any(
                same_path(str(item.get("file") or ""), path_text)
                for item in page.get("items") or []
            )
        ]
        manager = self._imposition_page_thumb_manager()
        if hits and manager is not None:
            manager.invalidate(hits, pages)
