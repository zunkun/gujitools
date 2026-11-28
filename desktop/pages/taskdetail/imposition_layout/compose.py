# -*- coding: utf-8 -*-
"""模块二「拼版操作」的**后台合成**分片：防抖排期、增量合成、签名记录。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from desktop.pages.taskdetail.imposition_layout.compose_sigs import (
    _read_composed_sigs, _write_composed_sigs,
)
from desktop.pages.taskdetail.imposition_layout.constants import (
    COMPOSED_SIGS_SUFFIX, COMPOSE_DEBOUNCE_MS, COMPOSE_YIELD_MAX_MS,
    COMPOSE_YIELD_MIN_PAGES, COMPOSE_YIELD_TO_THUMBS_MS,
    EDIT_COMMIT_DEBOUNCE_MS, PRINT_WAIT_POLL_MS, PRINT_WAIT_TIMEOUT_MS,
    THUMB_REFRESH_DEBOUNCE_MS,
)
from desktop.services.imposition import (
    is_product_file, page_product_suffix, product_path,
)

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_layout._host import (
        ImpositionLayoutHost,
    )
else:
    ImpositionLayoutHost = object


class ComposeMixin(ImpositionLayoutHost):
    """拼版成品合成：防抖排期、单飞/补轮、增量签名与打印源通知。"""

    # ------------------------------------------------------------- 合成落盘
    def _schedule_imposition_page_thumb(self, index: int) -> None:
        """版面改动 → 防抖后**只重合成这一页**的左列缩略图（用户 2026-10-09）。

        拖动/缩放/旋转/复位落盘后，左列那条缩略图还是旧版面——攒下页号、
        停手 :data:`THUMB_REFRESH_DEBOUNCE_MS` 后单页重合成（memo 判据：
        版面没真变就原样回缓存里的同一张，不白跑）。页数增删/排序走
        ``_save_imposition_pages`` → ``_refresh_imposition_page_thumbs``
        的整列刷新，不经这里。
        """
        dirty = getattr(self, "_imposition_thumb_dirty", None)
        if dirty is None:
            dirty = self._imposition_thumb_dirty = set()
        dirty.add(int(index))
        timer = getattr(self, "_imposition_thumb_timer", None)
        if timer is not None:
            timer.start()

    def _refresh_imposition_dirty_page_thumbs(self) -> None:
        """防抖到期：把攒下的那几页**单页**重生成缩略图实体并贴回左列。"""
        view = getattr(self, "imposition_view", None)
        dirty = getattr(self, "_imposition_thumb_dirty", None)
        if view is None or not dirty:
            return
        self._imposition_thumb_dirty = set()
        pages = self._imposition_pages()
        manager = self._imposition_page_thumb_manager()
        if manager is not None:
            manager.invalidate(sorted(dirty), pages)

    def _schedule_imposition_compose(self) -> None:
        """版面/页数变化 → 防抖后**后台**把拼版页重写到 stages/imposition。"""
        if not getattr(self, "task_id", None):
            return
        self._imposition_dirty = True
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            # ⚠️ 间隔**显式给**：让路那条路径会把它临时改成 250ms（见
            # ``_defer_compose_for_thumbs``），不重设的话之后每轮防抖都被拖慢。
            timer.start(COMPOSE_DEBOUNCE_MS)
        else:
            # 定时器还没建（视图未初始化）：直接同步兜底，别让改动悬着
            self._compose_imposition_now()

    def _init_imposition_compose(self) -> None:
        """建防抖定时器（页面构造期一次）。"""
        self._imposition_dirty = False
        self._imposition_composing = False
        #: **页号 → 上次落盘时的内容签名**（``page_thumb.page_signature``）。
        #: 版面只动一页时靠它算出"只有这一页要重合成"（用户 2026-10-18：
        #: 「不是所有图片都重新存储一份，只存储当前拼版的图片页」）。真正的基线
        #: 存在**侧车文件**里（见 ``_composed_sigs``，跨会话有效）；这个属性只是
        #: "当前节点那一份"的引用，供自测/排查观察。
        self._imposition_page_sigs: dict[int, str] = {}
        #: 侧车签名表的**按路径缓存**（``{侧车文件路径: {页号: 签名}}``）：切节点/
        #: 切任务只换 key，不重读盘。
        self._composed_sigs_cache: dict[str, dict[int, str]] = {}
        #: 本轮合成用的是**哪份文档快照 / 哪张目录 / 哪份记录 / 正在写哪几页**
        #: （收尾时据此记签名、算"这次重存了哪几张图片"并通知第四步）
        self._imposition_compose_doc: dict | None = None
        self._imposition_compose_out_dir: Path | None = None
        self._imposition_compose_sigs_path: Path | None = None
        self._imposition_compose_doc_path: Path | None = None
        self._imposition_compose_doc_mtime: float | None = None
        self._imposition_composed_pages: list[int] = []
        #: 本轮合成为了给**可见页缩略图**让路，从什么时候开始往后挪的
        #: （``time.monotonic()``；None = 没在让）。见 ``_defer_compose_for_thumbs``。
        self._imposition_compose_deferred_at: float | None = None
        # ⚠️ Mixin 本体是普通类，类型检查器看不到宿主（TaskDetailPage）是 QWidget，
        #    故把 self 收窄成 QWidget 再当 QTimer 的 parent 用；运行时是恒等。
        self._imposition_timer = QTimer(cast(QWidget, self))
        self._imposition_timer.setSingleShot(True)
        self._imposition_timer.setInterval(COMPOSE_DEBOUNCE_MS)
        self._imposition_timer.timeout.connect(self._compose_imposition_async)
        # 旋转组件的停顿提交计时器（滑块连续吐增量期间只转画布，停手才落盘）
        self._imposition_edit_timer = QTimer(cast(QWidget, self))
        self._imposition_edit_timer.setSingleShot(True)
        self._imposition_edit_timer.setInterval(EDIT_COMMIT_DEBOUNCE_MS)
        self._imposition_edit_timer.timeout.connect(self._commit_imposition_edit)
        # 左列单页缩略图的重合成计时器（版面停手后几秒内跟上页面效果）
        self._imposition_thumb_dirty: set[int] = set()
        self._imposition_thumb_timer = QTimer(cast(QWidget, self))
        self._imposition_thumb_timer.setSingleShot(True)
        self._imposition_thumb_timer.setInterval(THUMB_REFRESH_DEBOUNCE_MS)
        self._imposition_thumb_timer.timeout.connect(
            self._refresh_imposition_dirty_page_thumbs
        )

    def _composed_sigs_path(self) -> Path | None:
        """当前拼版节点的「已落盘签名」侧车文件路径（与版面草稿同目录同作用域）。"""
        if not self.task_id:
            return None
        doc = self.store.imposition_doc_path(self.task_id, **self._imposition_scope())
        return doc.with_name(doc.stem + COMPOSED_SIGS_SUFFIX)

    def _composed_sigs(self, path: Path | None = None) -> dict[int, str]:
        """**某个**侧车文件的签名表（缺省 = 当前节点）；按路径缓存，切节点自动换一份。

        ⚠️ 缓存是必须的：本方法在"每次版面改动判过期"路上被调，每调一次读盘
        （几十 KB JSON）就白搭了；而**按路径**缓存又让同一步骤的多个拼版节点
        各拿各的记录（互不串味）。
        """
        target = self._composed_sigs_path() if path is None else path
        if target is None:
            return {}
        cache = getattr(self, "_composed_sigs_cache", None)
        if cache is None:
            cache = self._composed_sigs_cache = {}
        key = str(target)
        mapping = cache.get(key)
        if mapping is None:
            mapping = _read_composed_sigs(Path(target))
            cache[key] = mapping
        # 顺手暴露给自测/排查（"当前节点记了哪些页"）
        self._imposition_page_sigs = mapping
        return mapping

    def _stale_imposition_pages(self) -> list[int]:
        """本次**要重合成的页号**（0 基）：与上次落盘时的内容签名逐页比对。

        签名规则复用缩略图实体那一套（``components.imposition.page_thumb
        .page_signature``：版面 rect/rotation + 每张源图的 (大小, mtime)），所以
        "源图被覆盖"同样会被算成一页要重合成。

        基线来自**侧车文件**（:meth:`_composed_sigs`），因此跨会话也有效——
        这是用户 2026-10-18「不应该是只改变一张图片吗」的关键：内存基线一重启
        就没了，只能整本全量重合成。没有记录的页仍算过期（首次/换任务/记录被清）。
        """
        from desktop.components.imposition.page_thumb import page_signature

        pages = self._imposition_pages()
        recorded = self._composed_sigs()
        return [
            index for index, page in enumerate(pages)
            # ⚠️ ``page_signature`` 对**空页**返回 None：统一折成空串再比，
            #    免得"没签名"与"签名是 None"两种都算过期、反复重合成同一页。
            if (page_signature(page) or "") != recorded.get(index, "")
        ]

    def _defer_compose_for_thumbs(self) -> bool:
        """可见页缩略图**批量**生成中 → 把这一轮合成往后挪，返回 True（已让路）。

        两个 worker 同在一个进程里，成品合成每页约 0.5s 且 PIL 编码期间攥着
        GIL——实测把缩略图从 24ms/页 拖到 4~7 秒/页（用户 2026-11-21 报
        "拼版页 5 分钟没图"）。缩略图那一批小（只含可见页，十几页），让完
        立刻轮到合成，总时长几乎不变，但用户是"一进去就有图"。

        ⚠️ **只让批量批次**（:data:`COMPOSE_YIELD_MIN_PAGES`）：拖版面后单页
           重生成那一笔很快，而"松手 1 秒内看到成品更新"是用户定的硬指标，
           让单页批次插队会把它顶穿。
        ⚠️ **force_full 不走这里**（点「生成PDF」前那条要的是"磁盘一定最新"，
           用户已经在等结果，不能再往后挪）。
        ⚠️ 有上限（:data:`COMPOSE_YIELD_MAX_MS`）：用户一直滚，缩略图就一直
           有活，合成不能无限期饿着。
        """
        manager = getattr(self, "_page_thumb_mgr", None)
        batch = getattr(manager, "window_batch_size", 0) if manager else 0
        if batch < COMPOSE_YIELD_MIN_PAGES:
            self._imposition_compose_deferred_at = None
            return False
        now = time.monotonic()
        since = getattr(self, "_imposition_compose_deferred_at", None)
        if since is None:
            since = now
            self._imposition_compose_deferred_at = since
        elif (now - since) * 1000.0 >= COMPOSE_YIELD_MAX_MS:
            # 让够了：照常合成（否则用户一直滚，第四步永远拿不到新成品）
            self._imposition_compose_deferred_at = None
            return False
        # 改动还挂着：下一拍再看一眼（单飞/补轮机制原样保留）
        self._imposition_dirty = True
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            timer.start(COMPOSE_YIELD_TO_THUMBS_MS)
        else:
            QTimer.singleShot(
                COMPOSE_YIELD_TO_THUMBS_MS, self._compose_imposition_async
            )
        return True

    def _compose_imposition_async(self, force_full: bool = False) -> None:
        """后台合成（不阻塞界面）：拖动版面时会被反复触发。

        ``force_full=True``：无视签名记录整本重合成（点「生成PDF」前的兜底用
        ——那边要的是"磁盘一定与落盘版面一致"，不必省这几秒）。
        默认走**增量**：只重写"内容签名变了"的那几页（用户 2026-10-18：
        「不是所有图片都重新存储一份，只存储当前拼版的图片页」）。
        """
        if not self.task_id:
            return
        if self._imposition_composing:
            return  # 上一批还在跑；跑完会看 _imposition_dirty 再补一次
        # 首屏优先：可见页缩略图没出完就先别抢 GIL（见 _defer_compose_for_thumbs）
        if not force_full and self._defer_compose_for_thumbs():
            return
        self._imposition_compose_deferred_at = None
        doc = self._imposition_doc()
        out_dir = self._imposition_output_dir()
        only = None if force_full else self._stale_imposition_pages()
        # ⚠️ **``only=[]``（一页都没变）也要真跑一轮**：它一页都不重合成，但
        #    ``compose_doc`` 收尾的**清扫**（删掉多出来的页号 / 别的后缀）必须执行
        #    ——"用户清空拼版页、删掉后面几页"时，若因为"没有页要重写"就整个跳过，
        #    上一轮的成品会留在盘上，第四步照旧把旧图打进 PDF。这一轮的代价只是
        #    一次目录清扫，零次图片合成。
        page_count = len(doc.get("pages") or [])
        try:
            from utils.crash_log import breadcrumb

            todo = page_count if (force_full or only is None) else len(only)
            breadcrumb(f"开始合成拼版：共 {page_count} 页，本轮 {todo} 页，"
                       f"{'整本' if force_full else '增量'}")
        except Exception:  # noqa: BLE001 - 取证绝不该影响合成
            pass
        if force_full or only is None:
            order = list(range(page_count))
        else:
            order = sorted(only)
        # ⚠️ 把**用户正看着的那一页排在最前**（用户 2026-10-18：「移动图片松鼠标，
        #    1s 内将当前图片更新到实体图片上」）：全量那一轮（首次还没有"已落盘
        #    记录"时）也是先写他改的那页，不必等整本跑完。
        view = getattr(self, "imposition_view", None)
        current = view.current_index() if view is not None else -1
        if 0 <= current < page_count and current in order and order[0] != current:
            order.remove(current)
            order.insert(0, current)
        self._imposition_dirty = False
        self._imposition_composing = True
        self._imposition_compose_doc = doc
        # ⚠️ **连"这次是哪张目录/哪份记录/哪份快照"一起记下**：合成在后台跑，期间
        #    用户可能切到同一步骤的另一个拼版节点去了——收尾时若现查当前节点，会把
        #    记录与确认写进**别人**的目录/侧车文件（成品落点也就跟着错了）。
        self._imposition_compose_out_dir = out_dir
        self._imposition_compose_sigs_path = self._composed_sigs_path()
        self._imposition_compose_doc_path = self.store.imposition_doc_path(
            self.task_id, **self._imposition_scope()
        )
        # ⚠️ 记的是**这次合成所用快照**对应的文档 mtime，而不是收尾那一刻的实时
        #    mtime：合成跑着用户又改一版时，文档 mtime 会往前跳，拿它当基准会把
        #    已经写好的前几页误判成"没写成功"→ 再排一轮重写（用户 2026-10-18 实测：
        #    先重存了 77 页、紧接着又重存 8 页，那一轮白跑还让他等更久）。
        try:
            self._imposition_compose_doc_mtime = (
                self._imposition_compose_doc_path.stat().st_mtime
            )
        except OSError:
            self._imposition_compose_doc_mtime = None
        self._imposition_composed_pages = list(order)
        from desktop.workers import ImpositionComposeWorker, connect_queued

        self.run_worker(
            # 成品后缀随**该页源图**走（用户 2026-10-17）：输入 png 出 png、
            # 输入 jpg 出 jpg（同一目录里两种后缀可以并存）
            lambda: ImpositionComposeWorker(
                doc, out_dir, suffix_for=page_product_suffix, only=only,
            ),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished, self._on_imposition_composed, thread
                ),
                connect_queued(
                    self, worker.failed, self._on_imposition_compose_failed, thread
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _record_composed_pages(self) -> None:
        """合成收尾：记下"这次重存了哪几页"、更新签名、通知第四步。

        - **签名**（``_imposition_page_sigs``）：下次只重合成又变了的那几页；
        - **记录**：日志写明重存了哪几页（用户 2026-10-18："那张图片变更，就重新
          存储哪个图片，同时通知下一步要变更的图片"）；
        - **通知下游**：只刷那几页在第四步的条目（见 ``_refresh_print_source``）。

        ⚠️ 每页再核一次"成品确实比版面文档新"才记签名：写盘失败/进程被杀的那页
        不记 —— 下次它还会被算成过期而重试（自愈），不会悄悄留着旧图。
        """
        sigs_path = getattr(self, "_imposition_compose_sigs_path", None)
        out_dir = getattr(self, "_imposition_compose_out_dir", None)
        pages = (self._imposition_compose_doc or {}).get("pages") or []
        indexes = list(getattr(self, "_imposition_composed_pages", None) or [])
        self._imposition_composed_pages = []
        if not indexes or sigs_path is None or out_dir is None:
            return
        try:
            doc_mtime = getattr(self, "_imposition_compose_doc_mtime", None)
        except AttributeError:
            doc_mtime = None
        from desktop.components.imposition.page_thumb import page_signature
        from desktop.services.imposition import product_path

        sigs = self._composed_sigs(sigs_path)
        changed: list[int] = []
        for index in indexes:
            if not 0 <= index < len(pages):
                continue
            page = pages[index]
            if doc_mtime is not None:
                try:
                    if product_path(out_dir, index, page).stat().st_mtime < doc_mtime:
                        continue  # 这一页这次没写成功 → 不记签名，下轮重试
                except OSError:
                    continue
            sigs[index] = page_signature(page) or ""
            changed.append(index)
        if not changed:
            return
        _write_composed_sigs(Path(sigs_path), sigs)
        labels = "、".join(f"第 {i + 1} 页" for i in changed[:6])
        if len(changed) > 6:
            labels += f" 等 {len(changed)} 页"
        self.log_view.append(
            f"拼版成品已重存 {len(changed)} 页（{labels}），"
            "这几张图在第四步会按当前排版参数重新排版。"
        )
        self._refresh_print_source([
            str(product_path(out_dir, index, pages[index])) for index in changed
        ])

    def _on_imposition_composed(self, _out_dir: str, _count: int) -> None:
        """后台合成完成（主线程）：解除忙标记，记签名/通知下游，必要时补一轮。"""
        self._imposition_composing = False
        self._record_composed_pages()
        if self._imposition_dirty:
            # 间隔显式给（让路路径改过它，见 _schedule_imposition_compose）
            self._imposition_timer.start(COMPOSE_DEBOUNCE_MS)
            return
        self._refresh_print_source()

    def _on_imposition_compose_failed(self, message: str) -> None:
        self._imposition_composing = False
        self.log_view.append(f"拼版合成失败：{message}")
        self._toast("error", "拼版合成失败", message)

    def _imposition_products_fresh(self) -> bool:
        """stages/imposition 的成品是否已覆盖**落盘版面**（mtime + 页数，不解码）。

        「点生成PDF先同步合成」的**快路径判据**（2026-10-12，用户报障
        「点生成PDF后界面立刻冻结」）：用两个便宜的磁盘事实回答"还要不要
        合成"，避免每次点击都全量重合成——

        - **页数**：``NNNN.png`` 的个数 == 文档页数（compose_doc 收尾会清掉
          多余编号；页数不符 = 有增删还没合出来）；
        - **新旧**：成品里**最旧**一张的 mtime ≥ 拼版文档的 mtime。编辑总是
          先落文档、再防抖合成，文档比成品新 = 有改动还没合出来。

        ⚠️ 只回答**磁盘**问题，刻意不看 `_imposition_dirty` /
        `_imposition_composing` 这两个内存态：跨会话的陈旧（上次编辑后进程
        被杀、防抖合成没跑成）只有磁盘对比能兜住——快路径靠它兜底，后续
        改动别把"无条件全量合成"加回来。
        """
        if not self.task_id:
            return True
        pages = self._imposition_pages()
        if not pages:
            return True
        out_dir = self._imposition_output_dir()
        if not out_dir.is_dir():
            return False
        products = [
            entry for entry in out_dir.iterdir() if is_product_file(entry)
        ]
        if len(products) != len(pages):
            return False
        try:
            # ⚠️ 比对的是**本节点**的版面文档（B 方案）：比错了文件会让"成品
            #    是否最新"永远说不准（一个节点改版面、另一个节点误判新鲜）。
            doc_mtime = self.store.imposition_doc_path(
                self.task_id, **self._imposition_scope()
            ).stat().st_mtime
            oldest = min(entry.stat().st_mtime for entry in products)
        except OSError:
            # 读不到（任务目录被删/竞态）就当不新鲜：重合成一遍无害
            return False
        if oldest < doc_mtime:
            return False
        # ⚠️ mtime 只能回答"版面改过没有"；**源图被上游重跑覆盖**时成品 mtime
        #    照样比文档新，但图已经换了。逐页内容签名（rect/rotation + 每张源图
        #    的大小/mtime）才看得出这种陈旧（用户 2026-11-04「检查所有的步骤」）。
        return not self._stale_imposition_pages()

    def _compose_imposition_now(self) -> None:
        """点「生成PDF」前保证 stages/imposition 是**最新版面**。

        2026-10-12 改造（用户报障「点生成PDF后界面立刻冻结」，拼版生效时）：
        旧版在这里**无条件**把全部拼版页同步重合成一遍（加载原图→缩放→
        旋转→alpha 合成→整页 PNG 编码，全在 GUI 主线程），几百页的书每次
        点击都冻结几十秒——而绝大多数点击时版面根本没改过。现在分三层：

        1. **磁盘新鲜度快路径**（`_imposition_products_fresh`）：成品已覆盖
           落盘版面 → 一个字节都不碰，立即返回（常见情形，零开销）；
        2. 拼版未生效 → 直接返回（第四步根本不读拼版目录，合成了也白合；
           重新启用时 `_set_imposition_checked` 会重新调度合成）；
        3. 真要合成 → **后台线程**合成（复用 `_compose_imposition_async` 的
           单飞/补轮机制），主线程用 QEventLoop 等收敛——界面保持响应
           （能看日志、滚动界面），执行权仍在 run_stage 手里（按钮已置灰，
           不会重入）。

        ⚠️ 前置条件含 `imposition_has_pages()`：一页都没拼时没有版面可合成
        （真正的拦路在第四步：列表为空 → 点「生成PDF」会明确提示去拼版）。
        ⚠️ 等待期间用户再改版面：`_on_imposition_composed` 的补轮机制会再排
        一轮，本循环等到"无在飞、无待合成"才放行；等待期间切走任务则立即
        放手（磁盘与内存状态由 `_reset_imposition_state` 复位）。
        ⚠️ 合成失败不拦住后续（与旧版同口径）：`_on_imposition_compose_failed`
        会弹 toast，这里把"PDF 按现有成品继续"说进日志。
        """
        if not self.task_id or not self.imposition_has_pages():
            return
        if not self.imposition_effective():
            return
        if self._imposition_products_fresh():
            self._imposition_dirty = False
            return
        owner_task = self.task_id
        self.log_view.append(
            "拼版版面有更新：正在后台合成（界面不阻塞），完成后继续生成PDF…"
        )
        try:
            self._set_stage_status("正在合成最新拼版页…")
        except Exception:  # noqa: BLE001 - 状态行只是提示，不该拖垮流程
            pass
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            # 防抖别再插队：改动已落盘，直接走单飞的异步合成
            timer.stop()
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        poll = QTimer(cast(QWidget, self))
        poll.setInterval(PRINT_WAIT_POLL_MS)

        def _settled() -> None:
            """收敛判据：没有在飞合成、没有待合成的改动（或任务已切走）。"""
            if self.task_id != owner_task or (
                not self._imposition_composing and not self._imposition_dirty
            ):
                loop.quit()

        poll.timeout.connect(_settled)
        poll.start()
        # 兜底：后台那轮合成若因任何原因不返回，这个 loop 会**永远转下去**——
        # 主线程在转（心跳/探活/定时器都正常），执行权却卡在 run_stage 手里、
        # 按钮已置灰，用户看到的就是"点什么都没反应，日志一个字没有"。
        # 到点就放手（见 PRINT_WAIT_TIMEOUT_MS 的说明）。
        deadline = QTimer(cast(QWidget, self))
        deadline.setSingleShot(True)
        timed_out = {"yes": False}

        def _give_up() -> None:
            timed_out["yes"] = True
            try:
                from utils.crash_log import dump_stacks, log

                log(f"[imposition] 等后台合成超过 {PRINT_WAIT_TIMEOUT_MS}ms 仍未收敛"
                    f"（在飞={self._imposition_composing}"
                    f", 待合成={self._imposition_dirty}）→ 不再等，按现有成品继续")
                dump_stacks("[imposition] 等合成超时的线程栈")
            except Exception:  # noqa: BLE001 - 取证不该影响放行
                pass
            loop.quit()

        deadline.timeout.connect(_give_up)
        deadline.start(PRINT_WAIT_TIMEOUT_MS)
        try:
            # ⚠️ 这一条**整本重合成**（``force_full``）：它要的是"磁盘一定与落盘
            #    版面一致"，而签名记录是内存态的、可能不准（跨会话/写盘失败），
            #    宁可多花几秒也不能把一页旧图打进 PDF。拖版面的后台那条走增量。
            self._compose_imposition_async(force_full=True)
            # ⚠️ 事件循环里界面照常收事件（这正是"不冻结"的实现方式）；
            #    期间用户改版面 → 补轮机制再排合成 → 下一轮收敛才放行。
            loop.exec()
        finally:
            poll.stop()
            deadline.stop()
        if self.task_id != owner_task:
            # 等待期间切了任务：内存态已被 _reset_imposition_state 复位，
            # 旧任务的合成自会收尾，这里什么都不补。
            return
        self._imposition_dirty = False
        if timed_out["yes"]:
            self.log_view.append(
                f"⚠️ 后台合成等待超时（{max(1, PRINT_WAIT_TIMEOUT_MS // 1000)} 秒）仍未完成，"
                "不再等：PDF 按现有成品继续（线程栈已写进 logs/crash.log）。"
            )
            self._toast("warning", "拼版合成超时",
                        "已按现有成品继续生成 PDF，详见日志")
        elif not self._imposition_products_fresh():
            self.log_view.append("⚠️ 拼版合成未完成，PDF 将按现有成品页继续。")
