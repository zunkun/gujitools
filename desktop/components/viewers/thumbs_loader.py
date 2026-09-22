# -*- coding: utf-8 -*-
"""缩略图异步装载混入：为 ThumbStrip **分批**加载图片缩略图。

⚠️ 为什么必须分批
    一次性把全部页面丢给一个 worker，worker 会在紧循环里连续做
    「QImageReader 缩放解码 + SmoothTransformation」，一个核直接打满——
    用户感知是「刚点进详情页，风扇突然转快」。而首屏真正看得见的只有
    最上面几行缩略图，其余几十张晚一两秒补齐完全不影响使用。

    分批后 CPU 从「连续满负载几秒」变成「一小段脉冲 + 间隙 + 若干小脉冲」，
    风扇不会明显起转；界面反而更早可交互（首批只做十几张的分量）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.workers import ImageListWorker, WorkerHost, connect_queued


class ThumbsMixin(WorkerHost):
    """为持有 ThumbStrip 的查看器提供分批缩略图加载。

    子类可以直接用基类的 :meth:`_load_thumbs`，也可以走
    :meth:`_load_thumbs_chunked` 自带 worker 工厂与回调（print/rembg 需要
    带 edge / effects / 自定义标签，都是走后者）。
    """

    #: 首批立即加载的张数：约等于一屏可见量，再多就是浪费
    FIRST_BATCH = 10
    #: 首批之后每批张数
    SUCCESSIVE_BATCH = 12
    #: 首批之后延迟多久才开始补齐（ms）。刻意留这段空档：此刻 CPU 还要
    #: 忙着画界面、解码右侧大图，缩略图没必要和它们抢。
    BATCH_DELAY_MS = 2000
    #: 批与批之间的间隔（ms），保证每个批次之间都有一段真正的空闲
    BATCH_GAP_MS = 150

    def _init_thumbs(self) -> None:
        """初始化分批装载状态（各查看器 __init__ 里调用一次）。"""
        self._init_worker_host()
        #: 代际令牌：切阶段/切任务会重新装载，旧批次的回调一律丢弃，
        #: 否则慢一批的缩略图会盖到新列表的同序号条目上（串图）。
        self._thumb_generation = 0
        self._thumb_factory = None
        self._thumb_sink = None
        self._thumb_next = 0
        self._thumb_total = 0
        #: 单次触发的定时器，负责在间隙后拉起下一批
        self._thumb_timer = QTimer()
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.timeout.connect(self._dispatch_next_thumb_batch)

    # ------------------------------------------------------------ 对外入口
    def _load_thumbs(self, strip: ThumbStrip, paths: list[Path]) -> None:
        """按路径加载缩略图；标签取文件名。

        ⚠️ 只负责**分批调度**，解码仍交给 ``ImageListWorker``（它用
        QImageReader 的缩放解码，不会把两三千像素的原图整张读进内存）。
        """
        self._load_thumbs_chunked(
            len(paths),
            make_worker=lambda start, end: ImageListWorker(list(paths[start:end])),
            sink=lambda index, image, path: strip.set_item_icon(
                index, image, path, Path(path).name
            ),
        )

    def _load_thumbs_chunked(self, total: int, make_worker, sink) -> None:
        """把 total 张缩略图分批加载。

        参数:
            total: 总张数。
            make_worker: ``(start, end) -> ImageListWorker``，只处理切片
                ``[start, end)``；worker 发出的 ``thumbnail_ready`` 里带的是
                **切片内**下标，本方法会加回 start 变成全局下标。
            sink: ``(global_index, image, path)``，每张就绪时在**主线程**回调。

        ⚠️ 调用即代表「重新装载」：会作废上一轮未跑完的批次（代际令牌），
        所以切阶段时旧的缩略图不会填进新列表。
        """
        self._thumb_generation += 1
        self._thumb_timer.stop()
        self._thumb_total = max(0, int(total))
        self._thumb_factory = make_worker
        self._thumb_sink = sink
        self._thumb_next = 0
        if self._thumb_total == 0 or make_worker is None or sink is None:
            return
        # 首批立即出：用户先看到开头几张，页面才算"出来了"
        self._dispatch_next_thumb_batch()

    def shutdown_workers(self) -> None:
        """停掉分批定时器与未完成的批次，再走基类的线程收尾。"""
        self._thumb_timer.stop()
        self._thumb_generation += 1  # 作废在飞批次的回调
        self._thumb_factory = None
        self._thumb_sink = None
        super().shutdown_workers()

    # ------------------------------------------------------------ 内部分批
    def _dispatch_next_thumb_batch(self) -> None:
        """派发 [光标, 光标+批大小) 这一段；由首批或定时器触发。"""
        factory = self._thumb_factory
        sink = self._thumb_sink
        if factory is None or sink is None:
            return
        start = self._thumb_next
        if start >= self._thumb_total:
            return
        # 首批用 FIRST_BATCH，之后用 SUCCESSIVE_BATCH
        size = self.FIRST_BATCH if start == 0 else self.SUCCESSIVE_BATCH
        end = min(start + size, self._thumb_total)
        self._thumb_next = end
        generation = self._thumb_generation
        self.run_worker(
            lambda: factory(start, end),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.thumbnail_ready,
                    # 切片下标 → 全局下标；代际不符说明列表已重装，丢弃
                    lambda local, image, path, base=start, gen=generation: (
                        sink(base + local, image, path)
                        if gen == self._thumb_generation
                        else None
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.completed,
                    lambda gen=generation: self._on_thumb_batch_done(gen),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                # 失败不续批：整批报错多半是路径/权限问题，硬续只会刷屏
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_thumb_batch_done(self, generation: int) -> None:
        """一批跑完：还有剩的就排下一批，并按阶段取不同的等待时长。"""
        if generation != self._thumb_generation:
            return
        if self._thumb_next >= self._thumb_total:
            return
        # 首批之后用较长的 BATCH_DELAY_MS（让位给画界面/载大图），
        # 之后只是小间隙，避免整批一次打满又能尽快补齐
        delay = (
            self.BATCH_DELAY_MS
            if self._thumb_next <= self.FIRST_BATCH
            else self.BATCH_GAP_MS
        )
        self._thumb_timer.start(delay)
