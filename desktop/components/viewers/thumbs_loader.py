# -*- coding: utf-8 -*-
"""缩略图异步装载混入：为 ThumbStrip **按可见窗口**懒加载图片缩略图。

⚠️ 为什么必须按窗口、不能全量
    一次性把全部页面丢给一个 worker，worker 会在紧循环里连续做
    「QImageReader 缩放解码 + SmoothTransformation」，一个核直接打满——
    用户感知是「刚点进详情页，风扇突然转快」。

    早先的折中是「分批补齐」（首批 10、之后每批 12、间隙 150ms）：单批小了，
    但**仍然会把 1000+ 页全部解完**——一本千页书要持续解码十几秒，用户实际
    只看得见首屏那几行。2026-10-21 用户口径：

    > 所有步骤缩略图不用全部一次加载

    所以现在只在**可见窗口**（视口首末行）上下各留一点预取边距内解码；
    用户滚动到哪里，才补哪一段。不滚就永远不会为看不见的页付 CPU。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QWidget

from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.workers import ImageListWorker, WorkerHost, connect_queued


class ThumbsMixin(WorkerHost):
    """为持有 ThumbStrip 的查看器提供**可见窗口**缩略图加载。

    子类可以直接用基类的 :meth:`_load_thumbs`，也可以走
    :meth:`_load_thumbs_chunked` 自带 worker 工厂与回调（print/rembg 需要
    带 edge / effects / 自定义标签，都是走后者）。
    """

    #: 可见窗口**上方**预取的行数（往上滚时的缓冲）
    VISIBLE_MARGIN_UP = 4
    #: 可见窗口**下方**预取的行数（往下滚时先有图可看）
    VISIBLE_MARGIN_DOWN = 10
    #: 视口高为 0（控件还没 show / 离屏自测）时的兜底张数
    FALLBACK_VISIBLE = 16
    #: 单批最多解码多少张（窗口内的缺口按连续段派发，也受这个上限约束）
    BATCH_MAX = 16
    #: 滚动/布局变化后重新检查窗口的延迟（ms）：等手停下来再解码
    RECHECK_MS = 120

    def _init_thumbs(self) -> None:
        """初始化窗口装载状态（各查看器 __init__ 里调用一次）。"""
        self._init_worker_host()
        #: 代际令牌：切阶段/切任务会重新装载，旧批次的回调一律丢弃，
        #: 否则慢一批的缩略图会盖到新列表的同序号条目上（串图）。
        self._thumb_generation = 0
        self._thumb_factory = None
        self._thumb_sink = None
        #: 条目下标 → 真实图条行号（子集加载时用；None = 下标即行号）
        self._thumb_row_map: list[int] | None = None
        #: 已派发过的条目下标（含在飞的批次）：绝不重复解码
        self._thumb_loaded: set[int] = set()
        self._thumb_total = 0
        self._thumb_strip: ThumbStrip | None = None
        self._thumb_scroll_bar = None
        #: 子集刷新（:meth:`_load_thumbs_subset`）的独立代际：与主装载互不影响，
        #: 否则"某页结果刚落盘"的小补丁会把整条清单的窗口装载作废。
        self._thumb_refresh_generation = 0
        #: 单次触发的定时器，负责滚动/批次结束后重新检查窗口
        #: ⚠️ 必须给 parent：无主 QTimer 只靠 shutdown_workers 停，控件若未走
        #:    该路径销毁，定时器仍会触发并碰已析构的 C++ 对象（审计 L3）
        #:    宿主是 QWidget（QWidget + 本 Mixin 混入），self 需 cast 成 QObject。
        self._thumb_timer = QTimer(cast(QObject, self))
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.timeout.connect(self._dispatch_visible_thumbs)

    def _decode_edge(self, base: int | None = None) -> int:
        """当前 dpr 下的缩略图解码最长边（见 ``ThumbStrip.decode_edge``）。

        ⚠️ 必须在**主线程**先算好再闭包进 ``make_worker``：批次工厂是在 worker
        线程里被调用的，那里碰 QWidget（``devicePixelRatioF``）是越界的
        （见 selftests/worker_thread_affinity.py）。
        """
        return ThumbStrip.decode_edge(cast(QWidget, self).devicePixelRatioF() or 1.0, base)

    # ------------------------------------------------------------ 对外入口
    def _load_thumbs(self, strip: ThumbStrip, paths: list[Path | str],
                     start: int = 0) -> None:
        """按路径加载缩略图；标签取文件名。

        ⚠️ 只负责**窗口调度**，解码仍交给 ``ImageListWorker``（它用
        QImageReader 的缩放解码，不会把两三千像素的原图整张读进内存）。

        ``start``：从第几条开始加载（之前的条目已有图标）。给「清单只是
        前缀扩展」的增量刷新用（extract 执行期页面陆续落地，整表重跑是
        O(N²) 控件 churn——2026-09-26 第二轮审计 L1）。
        """
        edge = self._decode_edge()
        self._load_thumbs_chunked(
            len(paths),
            make_worker=lambda s, e: ImageListWorker(
                [Path(p) for p in paths[s:e]], edge=edge
            ),
            sink=lambda index, image, path: strip.set_item_icon(
                index, image, path, Path(path).name
            ),
            start=start,
            strip=strip,
        )

    def _load_thumbs_chunked(self, total: int, make_worker, sink,
                             start: int = 0, *, strip: ThumbStrip,
                             row_map: list[int] | None = None) -> None:
        """按**可见窗口**装载缩略图。

        参数:
            total: 总张数。
            make_worker: ``(start, end) -> ImageListWorker``，只处理切片
                ``[start, end)``；worker 发出的 ``thumbnail_ready`` 里带的是
                **切片内**下标，本方法会加回 start 变成全局下标。
            sink: ``(global_index, image, path)``，每张就绪时在**主线程**回调。
            start: 光标起点（该下标之前的条目已有图标，跳过）。
            strip: 承载这些条目的图条（**必给**：窗口由它的视口位置决定）。
            row_map: ``row_map[i]`` = 第 i 张的真实行号。``total`` 是整条清单的
                **子集**时（print/rembg 只刷几行）必须给，否则可见性判据会用
                子集下标去比真实行号，判错窗口。

        ⚠️ 调用即代表「重新装载」：会作废上一轮未跑完的批次（代际令牌），
        所以切阶段时旧的缩略图不会填进新列表。
        """
        self._thumb_generation += 1
        self._thumb_timer.stop()
        self._thumb_total = max(0, int(total))
        self._thumb_factory = make_worker
        self._thumb_sink = sink
        self._thumb_row_map = list(row_map) if row_map is not None else None
        # 光标之前的条目已有图标：一并视作"已装载"，不参与窗口计算
        self._thumb_loaded = set(range(0, max(0, min(int(start), self._thumb_total))))
        self._bind_strip(strip)
        if (
            self._thumb_total <= 0
            or make_worker is None
            or sink is None
        ):
            return
        # 首屏立即出：用户先看到当前视口那几张，页面才算"出来了"
        self._dispatch_visible_thumbs()

    def _load_thumbs_subset(self, total: int, make_worker, sink, *,
                            strip: ThumbStrip,
                            row_map: list[int] | None = None) -> None:
        """只重解**指定的这几行**（某页结果刚落盘 / 某文件被覆盖）。

        与 :meth:`_load_thumbs_chunked` 的分工：

        - 后者代表"整条清单（重新）装载"：作废旧批次、接管后续滚动；
        - 本方法只是一次性的小补丁：**不动主装载状态**，只把子集里当前
          看得见的行派给 worker。否则每次补一页都会把整条清单的窗口装载
          作废，用户再滚动时新露出来的行就再也不加载了（千页书的常态）。

        ``row_map[i]`` = 第 i 个待刷新条目在缩略图条里的**真实行号**。
        """
        if total <= 0 or make_worker is None or sink is None:
            return
        self._thumb_refresh_generation += 1
        generation = self._thumb_refresh_generation
        lo, hi = self._window_for(strip)
        visible = [
            index for index in range(total)
            if lo <= self._row_in(row_map, index) <= hi
        ]
        if not visible:
            return
        for start, end in self._contiguous_runs(visible):
            self._dispatch_thumb_batch(
                start, end, generation, refresh=True,
                factory=make_worker, sink=sink,
            )

    def shutdown_workers(self) -> None:
        """停掉窗口定时器、断开图条滚动信号，再走基类的线程收尾。"""
        self._thumb_timer.stop()
        self._thumb_generation += 1  # 作废在飞批次的回调
        self._thumb_refresh_generation += 1
        self._thumb_factory = None
        self._thumb_sink = None
        self._thumb_loaded.clear()
        self._unbind_strip()
        super().shutdown_workers()

    def _invalidate_thumbs(self) -> None:
        """让当前窗口的缩略图**重新解码**（内容变了：结果文件刚落地等）。

        只清「已装载」标记并重排一次窗口，不整条重建——窗口外的条目本来
        就没装载，等用户滚过去时自然按新内容解。
        """
        self._thumb_loaded.clear()
        self._schedule_recheck()

    # ------------------------------------------------------------ 图条接线
    def _bind_strip(self, strip: ThumbStrip) -> None:
        """接上图条的滚动/范围信号（同一个图条只接一次）。"""
        if strip is self._thumb_strip:
            return
        self._unbind_strip()
        self._thumb_strip = strip
        bar = strip.verticalScrollBar()
        # valueChanged：用户滚轮/拖动滚动条；rangeChanged：布局变了（条目增删、
        # 缩略图落地改高度、窗口尺寸变化）同样可能把新行"露出来"
        bar.valueChanged.connect(self._on_thumb_scroll)
        bar.rangeChanged.connect(self._on_thumb_scroll)
        self._thumb_scroll_bar = bar

    def _unbind_strip(self) -> None:
        """断开图条信号（换图条/收尾时；已析构的 C++ 对象按异常吞掉）。"""
        bar = self._thumb_scroll_bar
        self._thumb_scroll_bar = None
        self._thumb_strip = None
        if bar is None:
            return
        for signal in (bar.valueChanged, bar.rangeChanged):
            try:
                signal.disconnect(self._on_thumb_scroll)
            except (RuntimeError, TypeError):
                pass

    def _on_thumb_scroll(self, *_args) -> None:
        """滚动/布局变化：延迟一次窗口检查（等手停下来再解码）。"""
        if self._thumb_factory is None:
            return
        if not self._thumb_timer.isActive():
            self._thumb_timer.start(self.RECHECK_MS)

    def _schedule_recheck(self) -> None:
        if self._thumb_factory is not None and not self._thumb_timer.isActive():
            self._thumb_timer.start(self.RECHECK_MS)

    # ------------------------------------------------------------ 窗口计算
    @classmethod
    def _window_for(cls, strip: ThumbStrip) -> tuple[int, int]:
        """视口首末真实行号 ± 预取边距（``FALLBACK_VISIBLE`` 兜底）。"""
        first, last = strip.visible_row_range()
        if last < first:
            return (0, cls.FALLBACK_VISIBLE - 1)
        return (first - cls.VISIBLE_MARGIN_UP, last + cls.VISIBLE_MARGIN_DOWN)

    @staticmethod
    def _row_in(row_map: list[int] | None, index: int) -> int:
        """条目下标 → 真实图条行号（``row_map`` 缺省时下标即行号）。"""
        if row_map is None:
            return index
        if 0 <= index < len(row_map):
            return int(row_map[index])
        return -1

    @classmethod
    def _contiguous_runs(cls, pending: list[int]) -> list[tuple[int, int]]:
        """把待派发下标切成连续段（每段最多 ``BATCH_MAX`` 张、一次最多 3 段）。"""
        runs: list[tuple[int, int]] = []
        run_start = pending[0]
        run_end = run_start + 1
        for index in pending[1:]:
            if index == run_end and run_end - run_start < cls.BATCH_MAX:
                run_end = index + 1
                continue
            runs.append((run_start, run_end))
            run_start, run_end = index, index + 1
            if len(runs) >= 3:
                break
        else:
            runs.append((run_start, run_end))
        return runs

    def _row_of(self, index: int) -> int:
        """条目下标 → 真实图条行号（``row_map`` 缺省时下标即行号）。"""
        return self._row_in(self._thumb_row_map, index)

    def _wanted_window(self) -> tuple[int, int]:
        """本次要覆盖的**真实行号**区间（视口首末行 + 预取边距）。"""
        strip = self._thumb_strip
        if strip is None:
            return (0, self.FALLBACK_VISIBLE - 1)
        return self._window_for(strip)

    def _dispatch_visible_thumbs(self) -> None:
        """把窗口内**尚未装载**的连续段派给 worker（顺带限流）。"""
        factory = self._thumb_factory
        sink = self._thumb_sink
        if factory is None or sink is None:
            return
        total = self._thumb_total
        if total <= 0 or len(self._thumb_loaded) >= total:
            return
        lo, hi = self._wanted_window()
        pending = [
            index for index in range(total)
            if index not in self._thumb_loaded
            and lo <= self._row_of(index) <= hi
        ]
        if not pending:
            return
        generation = self._thumb_generation
        # 连续段派发（worker 按切片取图）；一次最多 3 段，剩余的等本段完成
        # 回调再续——别在同一帧里堆线程。
        for start, end in self._contiguous_runs(pending):
            self._dispatch_thumb_batch(start, end, generation, factory=factory,
                                       sink=sink)

    def _dispatch_thumb_batch(self, start: int, end: int, generation: int, *,
                              refresh: bool = False, factory=None,
                              sink=None) -> None:
        """派发 ``[start, end)`` 这一段。

        ``refresh=True``：子集刷新，代际看 ``_thumb_refresh_generation``，
        且不更新主装载器的"已装载"集合。
        """
        if factory is None:
            factory = self._thumb_factory
        if sink is None:
            sink = self._thumb_sink
        if factory is None or sink is None:
            return
        if not refresh:
            self._thumb_loaded.update(range(start, end))
        self.run_worker(
            lambda: factory(start, end),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.thumbnail_ready,
                    # 切片下标 → 全局下标；代际不符说明列表已重装，丢弃
                    lambda local, image, path, base=start, gen=generation,
                    refresh=refresh: (
                        sink(base + local, image, path)
                        if gen == (
                            self._thumb_refresh_generation
                            if refresh else self._thumb_generation
                        )
                        else None
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.completed,
                    lambda gen=generation, refresh=refresh: (
                        None if refresh else self._on_thumb_batch_done(gen)
                    ),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                # 失败不续批：整批报错多半是路径/权限问题，硬续只会刷屏
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_thumb_batch_done(self, generation: int) -> None:
        """一批跑完：窗口可能因为条目高度变化而移动，隔一小段再检查一次。"""
        if generation != self._thumb_generation:
            return
        self._schedule_recheck()
