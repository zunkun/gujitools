# -*- coding: utf-8 -*-
"""阶段执行的进度/日志界面节流器。"""

from __future__ import annotations

from desktop.ui.log_throttle import LogCoalescer
from ._qt import QObject, QTimer
from typing import TYPE_CHECKING, Any, Callable, cast


class ProgressUiMixin:
    """进度与日志的界面刷新节流。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _last_progress: Any
        _poll_extract_results: Any
        _refresh_stage_views: Any
        log_panel: Any
        log_view: Any
        run_id: Any
        running_stage: Any
        store: Any
        task_id: Any

    #: 进度事件的**界面刷新合并窗口**(ms)。
    #:
    #: ⚠️ 为什么必须合并：extract 每渲染完一页就发一条 progress 事件，一本 100 页
    #: 的书就是 100 条。每条都去做「写 runs.json + 重建步骤条 + 重建提取结果缩略图
    #: 条」是几十毫秒级的重活（实测 GUI 每秒只吃得下十几条），GUI 于是远远落在
    #: worker 后面。后果有两个：界面明显发卡；更严重的是**进程退出时管道里还压着
    #: 一大批没读的事件**，收尾时被一并丢掉 —— 历史里留下「成功 done=14/total=84」、
    #: 日志缺「处理完成」那行，用户看到的就是"像被中断了/只提取了一半"。
    #: 进度条与状态文字仍逐条即时更新（纯内存操作，便宜）。
    _PROGRESS_UI_MS = 200

    #: 「多少秒没有任何 worker 输出」就提醒用户可能卡住（只提醒，不自动杀）。
    #: ⚠️ 真正的实现与判定在 ``desktop.steps.process.StageProcess``
    #: （``STALL_WARN_S``）——那里是"看门狗"的归属地；本页只负责把提醒
    #: 画到日志与状态行上（见 :meth:`_on_stage_stalled`）。
    #: 页面尺寸/检测框的攒批落盘间隔（ms）。逐条落盘在 320 页上累计 3.1 秒
    #: 主线程阻塞（见 _store_page_size / _store_stage_boxes 的说明）。
    #: ⚠️ 2026-10-20 从 400ms 放宽到 1200ms：配合 ``_DocCache`` 单写者内存文档
    #: （见 annotations.py），每次落盘已不再"整份读 + 整份写"；收尾仍在
    #: ``_worker_finished_impl`` 强制 flush，不丢数据。
    _ANNOT_FLUSH_MS = 1200

    #: 「右侧检测统计」重算的节流窗口（ms）。
    #:
    #: ⚠️ ``_refresh_detect_stats`` 每次要**整份读 boxes.json + 整份读 sizes.json
    #: + ``profile_book`` 全量重算** —— 1000+ 页时它是单次最贵的主线程动作，
    #: 而它原本被落盘定时器以同样频率拖着跑。改成"置脏 + 1s 节流"后，执行期间
    #: 统计按秒刷新，收尾/切阶段/手工改框仍**立即**重算（见 ``_refresh_stats_now``）。
    _STATS_UI_MS = 1000

    #: 去底色执行期间「某几页结果刚落盘」的界面刷新窗口（ms）。
    #:
    #: ⚠️ worker 每页完成就发一条 ``page_done``（一本 1000 页的书 = 1000 条）。
    #: 每条都去刷缩略图/大图会把主线程拖住（且同一批并发完成时更是连着来），
    #: 所以攒 400ms 一次、每次只刷**当前可见**的那几行（见
    #: ``RembgPreviewWidget.refresh_running_results``）——用户看到的是"一页页
    #: 陆续变成去底色结果"，主线程不做看不见的活。
    _REMBG_UI_MS = 400

    def _init_progress_ui(self) -> None:
        """建进度刷新节流器（宿主页面 __init__ 里调一次，须在 _init_ui 之后）。"""
        self._progress_ui_timer = QTimer(cast("QObject", self))
        self._progress_ui_timer.setSingleShot(True)
        self._progress_ui_timer.setInterval(self._PROGRESS_UI_MS)
        self._progress_ui_timer.timeout.connect(self._flush_progress_ui)
        self._progress_dirty = False

    def _init_log_coalescer(self) -> None:
        """建日志合并器（宿主页面 __init__ 里调一次，须在 ``self.log_view`` 之后）。

        ⚠️ 为什么要合并：执行阶段每来一行日志就 ``log_view.append`` 一次 =
        一次文档布局 + 一次状态条刷新；逐页打印的阶段一秒能来几十上百行，
        主线程就在这两件事上被拖住，界面看着就是"卡"（用户报的
        「检测文本框执行过程中页面卡顿」）。合并成一次
        ``append("\\n".join(lines))`` 后，这批行只付一次布局与一次刷新。

        见 :class:`desktop.ui.log_throttle.LogCoalescer`，
        与进度合并（``_progress_ui_timer``）**是两条独立节流线**。
        """
        self._logs = LogCoalescer(self.log_view)
        # ⚠️ 补接管「清空日志」：``LogPanel`` 自己接的是 ``log_view.clear``，
        #    而合并器里可能还压着尚未落笔的行 —— 不处理的话清空后它们会在定时器
        #    到期时**重新冒出来**（看着像"清空没生效"）。这里在面板那次 clear
        #    之后再补一枪（先落笔再清，反正都要清）。
        self.log_panel.clear_button.clicked.connect(self._clear_log)

    def _clear_log(self) -> None:
        """清空执行日志（连同合并器里压着、尚未落笔的行）。"""
        self._logs.flush()
        self.log_view.clear()

    def _flush_progress_ui(self) -> None:
        """把合并掉的进度落盘并刷新步骤条 / 提取结果（收尾时也必须调一次）。"""
        if self._progress_ui_timer.isActive():
            self._progress_ui_timer.stop()
        if not self._progress_dirty:
            return
        self._progress_dirty = False
        if self.task_id and self.run_id:
            done, total = self._last_progress
            if total:
                self.store.set_progress(self.task_id, self.run_id, done, total)
        self._refresh_stage_views()
        if self.running_stage == "extract":
            self._poll_extract_results()
