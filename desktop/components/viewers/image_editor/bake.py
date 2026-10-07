# -*- coding: utf-8 -*-
"""全分辨率烘焙的**后台线程 + 进度对话框**（从 ``image_editor.py`` 拆出）。

重活（逐像素重映射）放这里跑，避免钉死 GUI 主线程。见 ``_BakeWorker`` 的
长注释。纯计算的工作函数（``_bake_*_work``）也在本模块。
"""
from __future__ import annotations

import contextlib
from typing import Any

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from desktop.workers.worker_host import connect_queued
from utils.cage_warp import deform_qimage

from .geometry import bake_puppet

@contextlib.contextmanager
def wait_cursor():
    """耗时操作期间挂等待光标。

    ⚠️ 必须 ``processEvents`` 一下，否则光标要等界面回到事件循环才换，
    而那时的等待已经结束了（等于没挂）。调用方负责别在里面重入。
    """
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


class _BakeWorker(QThread):
    """把**全分辨率烘焙**放到后台线程跑，并用进度对话框报告进度。

    为什么需要它（用户 2026-10-01 报"程序卡死崩溃，不能实时查看"）：
    ``deform_qimage`` / ``puppet_warp_qimage`` 是逐像素重映射，整页
    4000×3000 要 3~15 秒、12000×9000 到分钟级。**同步**跑会把 GUI 主线程
    钉死——界面不重绘、不响应点击，用户看到的就是"卡死/崩溃"（其实是假死）。

    做法：把"重活"（``work(params, progress)`` 返回结果）丢进本线程；工作
    函数通过 ``progress(done, total)`` 回调报进度，主线程每来一次就把
    ``QProgressDialog`` 往前推一格并 ``processEvents``（保持"取消"按钮可点）。
    主线程序列化地与工作线程通信：只传不可变的参数与结果，避免共享可变状态。

    ``progress`` 返回 ``False``（用户点了取消），工作函数应尽快返回 ``None``；
    本线程据此把结果标为"已取消"。
    """

    #: 进度回调在工作线程里被调用 → 用信号转发到主线程更新对话框
    ticked = Signal(int, int)
    #: 工作函数**抛异常**时发出（``str``），主线程据此报错而不是假装取消
    #: （见 :meth:`run` —— 异常绝不能一路逃出 ``run``）
    failed = Signal(str)

    def __init__(self, work, params: dict, parent=None):
        super().__init__(parent)
        self._work = work
        self._params = params
        self.cancelled = False
        self.result = None
        #: 工作函数抛出的异常对象（主线程读），``None`` 表示没出错。
        #: ⚠️ 类型是 **BaseException**：下面那个兜底 except 就是按 BaseException
        #: 接的（MemoryError / QThread 中断等），用 Exception 装不下。
        self.error: BaseException | None = None

    def cancel(self) -> None:
        """请求取消（主线程调；工作函数下次回调进度时即中止）。"""
        self.cancelled = True

    def progress(self, done: int, total: int):
        """工作函数调用的进度回调；返回 False 表示用户已请求取消。"""
        self.ticked.emit(int(done), int(total))
        return not self.cancelled

    def run(self) -> None:  # noqa: D102（QThread 入口）
        # ⚠️ **必须**在这里捕获所有异常（用户可见的"崩溃"头号来源）：
        #   ``run`` 是被 C++ 调用的虚函数，Python 异常直接逃出去只会打一段
        #   stderr（PySide6 6.9 实测，进程**存活**），但 ``self.result`` 停在
        #   ``None`` 而 ``cancelled`` 是 ``False`` —— 调用方
        #   （:func:`run_with_progress`）据此返回 ``None``，上层
        #   （``_commit_deform`` 等）就会把它当成"**用户取消**"，弹掉撤销点
        #   并且**一声不吭**。用户点了 20 秒，什么都没发生，也没提示。
        #   ⇒ 存下异常并置位 failed，让调用方弹错误框、退回撤销点。
        try:
            self.result = self._work(self._params, self.progress)
        except Exception as exc:      # noqa: BLE001（兜底，不透传）
            self.error = exc
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        # MemoryError / 其它 BaseException（如 QThread 被中断）也一并拦住：
        # 任何逃逸都会让调用方误判成"取消"，比崩掉更难排查。
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def run_with_progress(parent: QWidget | None, title: str, label: str,
                      work, params: dict):
    """在后台线程跑 ``work(params, progress)`` 并显示进度对话框。

    返回工作结果；被用户取消时返回 ``None``。``work`` 必须是**纯计算**
    （只用到形参，不碰 Qt 部件/画布），这样才能安全地放进工作线程。
    小任务（预估很快）也不亏：线程启动 + 对话框开销在毫秒级。

    ⚠️ 工作函数**抛异常**时**重新抛出**（``raise worker.error``），
    调用方负责弹错误框并退回撤销点。绝不能把它折叠成 ``None`` ——
    ``None`` 的既定含义是"用户取消"，混同的结果是"点了 20 秒什么都没发生
    且无提示"（用户报过的现象，见 :meth:`_BakeWorker.run`）。

    ⚠️ 本函数**不吞异常、也不留孤儿线程**：整体 ``try/finally``，
    ``finally`` 里 ``cancel() + wait()``。异常逃出等待循环时若不收尾，
    worker 会变成孤儿线程，而它是被 ``parent``（编辑器对话框）持有的 ——
    对话框一析构就是 ``QThread: Destroyed while thread is still running``，
    **Qt 直接 abort 整个进程**（本项目 ``worker_host`` 已记过这条）。
    """
    worker = _BakeWorker(work, params, parent)
    dialog = QProgressDialog(label, "取消", 0, 100, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setMinimumDuration(300)       # 快任务不闪一下对话框
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setValue(0)
    # ⚠️ ``QProgressDialog.close()`` **也会**发 ``canceled``（实测 Qt6），
    #    不区分的话"正常跑完 → close"会被当成用户取消，结果白丢。
    #    用一个闸门：只有对话框还开着时的 canceled 才算真取消。
    #    ⚠️ 键值类型显式标出来：done 是 bool、error 是 str（on_failed 写的
    #    是失败文案），不标的话类型检查器会把它们当 Unknown|None，
    #    下游 state["error"] 的读用全部变成类型错误。
    state: dict[str, Any] = {"done": False}

    def on_cancel() -> None:
        if not state["done"]:
            worker.cancel()

    dialog.canceled.connect(on_cancel)

    def on_tick(done: int, total: int) -> None:
        if total > 0:
            dialog.setValue(min(100, int(done * 100 / total)))

    def on_failed(message: str) -> None:
        state["error"] = message

    # ⚠️ 显式排队连接：**不依赖**"PySide6 给无接收者的闭包自动建 proxy 并
    #   queued 连接"这一隐式行为。实测（子线程真实 emit + 主线程 wait/processEvents
    #   循环）当前 PySide6 6.9.2 确实跑在主线程，但那是版本相关的实现细节；
    #   一旦某个版本按 Auto→Direct 处理，就会在工作线程里碰
    #   ``dialog.setValue``，而此刻主线程正在 ``processEvents`` 里操作同一个
    #   对话框 ⇒ 两个线程摸同一个 widget，Windows 上是访问违例。
    #   项目约定（``desktop/workers/worker_host.connect_queued``）也是这条。
    #   中继对象必须挂在**主线程内的 QObject** 上，所以 ``parent`` 为 None
    #   时退回"直接连"（本函数的所有实际调用方都传了对话框）。
    if parent is not None:
        connect_queued(parent, worker.ticked, on_tick, worker)
        connect_queued(parent, worker.failed, on_failed, worker)
    else:
        worker.ticked.connect(on_tick)
        worker.failed.connect(on_failed)
    # ⚠️ BaseException（与 worker.error 同宽）：worker 的兜底分支按
    #    BaseException 接（MemoryError / QThread 中断等），这里只往上报。
    error: BaseException | None = None
    cancelled = False
    result = None
    try:
        worker.start()
        # 主线程等它跑完，但每 50ms 醒一次让事件循环处理重绘/取消点击
        while not worker.wait(50):
            QApplication.processEvents()
        # 线程已停，此刻才能安全收尾（worker.error / result 已定型）。
        # ⚠️ **必须在这里读 `cancelled`**：下面的 `finally` 为了兜底会调
        #   `worker.cancel()`，那会把"正常跑完"也标成取消。
        state["done"] = True          # 先封住 canceled，再正常关闭
        error = worker.error
        cancelled = worker.cancelled
        result = worker.result
    finally:
        # 兜底：异常路径下也要确保线程结束、对话框销毁，绝不留孤儿
        state["done"] = True
        worker.cancel()
        worker.wait()
        dialog.close()
        dialog.deleteLater()
    if error is not None:
        raise error
    if cancelled:
        return None
    return result


def _bake_cage_work(params: dict, progress):
    """后台线程里的笼形变烘焙（纯计算，不碰 Qt 部件）。

    见 :func:`run_with_progress`：只读 ``params``、只写返回值，形变本身由
    ``utils.cage_warp.deform_qimage`` 完成（QImage 是隐式共享的值对象，
    在工作线程里用/生成是安全的——这里全程不触碰任何 QWidget/画布）。

    ``grow=True``：内容被拖出原边界时**不裁**，返回 ``(QImage, (ox, oy))``
    （用户 2026-10-02：「超出原本区域的不要截，最终结果要按最后图片的范围」）。
    """
    return deform_qimage(params["image"], params["src"], params["dst"],
                         grow=True, progress=progress)


def _bake_puppet_work(params: dict, progress):
    """后台线程里的 ARAP 形变烘焙（纯计算，不碰 Qt 部件）。见上。

    ``grow=True``：图钉被拖出原边界时**不裁**，返回 ``(QImage, (ox, oy))``
    （用户 2026-10-02：「超出原本区域的不要截」）。
    """
    return bake_puppet(params["image"], params["vertices"], params["moved"],
                       params["triangles"], grow=True, progress=progress)
