# -*- coding: utf-8 -*-
"""任务详情页的收尾：toast、关窗口、关前补发、停全部 worker。"""

from __future__ import annotations

from desktop.ui.toast import show_toast
from ._qt import QProcess, QWidget
from typing import TYPE_CHECKING, Any, cast


class PageLifecycleMixin:
    """页面收尾与关窗前补发。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _flush_param_drafts: Any
        detect_process: Any
        findChildren: Any
        process: Any
        release_stage_buffers: Any
        shutdown_workers: Any

    # ------------------------------------------------------------------ 工具
    def _toast(self, kind: str, title: str, content: str) -> None:
        """弹 InfoBar；实现收在 :mod:`desktop.ui.toast`（与独立任务页共用）。"""
        show_toast(cast("QWidget", self), kind, title, content)

    def closeEvent(self, event) -> None:
        """关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。

        详情页持有 QProcess 与多个 WorkerHost 线程；先 kill 正在跑的执行/
        检测子进程并等待（最多 1.5s），再 shutdown_all_workers 收尾其余线程，
        最后接受关闭事件，避免解释器退出时被强杀崩溃。
        """
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1500)
        if self.detect_process and self.detect_process.state() != QProcess.ProcessState.NotRunning:
            self.detect_process.kill()
        # ⚠️ 先把「拖住图片框不松手」的版面改动补发出去，再走落盘与线程收尾：
        #    rect_changed 只在 mouseRelease 发，不补发就会**丢掉这次拖动**
        #    （2026-09-26 审计）。
        self.flush_layout_pending()
        self._flush_param_drafts()
        # 关窗口：预览区的位图（大图 + 每条缩略图）先放掉再收线程，避免
        # 退出时几十上百 MB 的 QPixmap 与线程收尾抢同一段收尾时间。
        self.release_stage_buffers()
        self.shutdown_all_workers()
        event.accept()

    def flush_layout_pending(self) -> None:
        """把各处"未提交的界面改动"补发/落盘（关窗口、切步骤、切页前都要调）。

        目前是第四步的版面画布与拼版画布：拖动中不落盘，只在松手/补发时提交。

        ⚠️ **只按具体的类 `findChildren`，绝不用 `getattr(widget, ...)` 探测能力**：
        四个阶段面板是 `LazyPanelHost`，属性转发（`__getattr__`）会**立刻把面板
        构造出来**——那就把用户要求的「不进去就不建」破坏掉了。（2026-09-26 自己
        踩到：写成 `getattr(w, "flush_pending", None)` 之后，`detail_prewarm`
        护栏直接红成"四个面板全建"。）
        ⚠️ 拼版画布是**直接构造**的（不在 LazyPanelHost 里），按类查安全。
        """
        from desktop.components.imposition.canvas import ImpositionCanvas
        from desktop.components.viewers.print_layout_canvas import PrintLayoutCanvas

        for cls in (PrintLayoutCanvas, ImpositionCanvas):
            for canvas in self.findChildren(cls):
                try:
                    canvas.flush_pending()
                except RuntimeError:
                    pass  # 控件已析构

    def shutdown_all_workers(self) -> None:
        """连同各预览控件自己的缩略图线程一起收尾。

        页面自身、PDF 预览、打印预览、缩略图条分别持有 WorkerHost 的线程，
        只停页面的会让其余线程在解释器退出时被强杀（偶发崩溃/卡顿）。
        """
        self.shutdown_workers()
        # 「导出YOLO标注」那台后台内核（懒建的，没导出过就没有）
        yolo_kernel = getattr(self, "_yolo_kernel", None)
        if yolo_kernel is not None:
            yolo_kernel.shutdown()
        # ``peek`` / ``panel`` 是 LazyPanelHost 上的属性，QWidget 类型里没有；
        # 标成 ``Any`` 即可按鸭子类型直接访问（运行时完全一致）。
        widgets: list[Any] = list(self.findChildren(QWidget))
        for widget in widgets:
            # ⚠️ 没建过的惰性面板直接跳过：`getattr` 探测会被 `LazyPanelHost` 的
            #    属性转发接住，顺手把面板构造出来——关页面时白建四个面板
            #    （2026-09-26 审计：同一类坑见 flush_layout_pending）。
            if hasattr(widget, "peek") and widget.peek() is None:
                continue
            shutdown = getattr(widget, "shutdown_workers", None)
            if callable(shutdown):
                try:
                    shutdown()
                except RuntimeError:
                    pass  # 控件已析构
