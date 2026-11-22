# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""「完成」的后台应用与取消。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform
from PySide6.QtWidgets import QApplication, QProgressDialog

from desktop.workers.worker_host import connect_queued
from ..bake import _BakeWorker, run_with_progress
from ..consts import (
    CLIPPING_DEFAULT, DIRECTION_DEFAULT, DISTORT_SYNC_RENDER_PIXELS,
    INTERPOLATION_DEFAULT, STEP_CROP, STEP_DISTORT, STEP_ERASE, STEP_FLIP,
    STEP_TEXT, STEP_TRANSFORM, TRANSFORM_SYNC_RENDER_PIXELS,
)
from ..content_quad import quad_frame, read_quad, sync_content_quad, upright_image
from ..geometry import (
    center_crop_aspect, clamp_rect, compose_transform, draw_text,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object

from .state import _ACTIVE_APPLIES
from .jobs import _apply_job



class AsyncApplyMixin(DialogHost):
    """「完成」的后台应用与取消。"""

    # ------------------------------------------------------------ 后台应用
    def apply_in_progress(self) -> bool:
        """「完成」的**后台应用**是否进行中（宿主在 ``exec()`` 返回后分流）。

        True = 编辑器已关、烘焙+写底片在工作线程里跑；宿主不要再走
        ``result_image()`` → 写盘那条同步路（图还没烘出来），改接
        ``apply_completed`` / ``apply_failed`` 信号收尾（2026-10-10）。
        """
        return getattr(self, "_async_apply", None) is not None

    def _begin_background_apply(self) -> bool:
        """「完成」→ **立即关窗**，烘焙+写底片放后台线程；启动成功返回 True。

        用户 2026-10-10 口径：「应用保存的时候页面上的数据可以不保存，只
        需要将数据存到相应的底片上」。之前「覆盖并应用」要点着等整幅重采样
        （12 MP 实测 11 秒）+ 写盘，界面全程钉死。现在：

        * 确认后弹窗**立刻** ``accept()``，宿主页恢复可交互；
        * 工作线程里烘焙（``_apply_job``：compose + 原子覆盖 ``source_path``）；
        * 完成回调里补文字块、维护内容节点、写 sidecar，然后发
          ``apply_completed(底片路径, 最终图)`` ——宿主接它做刷新链；
        * 失败/取消发 ``apply_failed(路径, 原因)``，底片原样未动（原子写）。

        前提：``save_back`` + 宿主回填了 ``source_path`` + 有挂起变换。只有
        统一变换的烘焙是秒级重活；裁剪/文字毫秒级，不值得异步（那些走原
        同步路，宿主代码零改动）。返回 False = 条件不满足，调用方退回原路。
        """
        if not getattr(self, "_save_back", False) \
                or getattr(self, "_multi_layers", None):
            return False
        path = str(getattr(self, "source_path", "") or "")
        if not path:
            return False
        pending = self.canvas.transform_pending()
        if pending is None:
            return False
        rect, xf, region = pending
        if getattr(self.canvas, "_xf_direction", DIRECTION_DEFAULT) == "backward":
            inverse, ok = xf.inverted()
            if ok:
                xf = inverse
        interpolation = getattr(self.canvas, "_xf_interpolation",
                                INTERPOLATION_DEFAULT)
        clipping = getattr(self.canvas, "_xf_clipping", CLIPPING_DEFAULT)
        upright = getattr(self, "_content_upright", None)
        if getattr(self, "_content_restored", False) and upright is not None:
            original = upright          # 恢复会话：从 upright 一次重采样
        else:
            original = self._image
        grow = clipping != "clip"
        # 文字块先摘走（画布立刻干净）；后台任务在写盘前将其重放到最终图，
        # 与同步路径「先变换后写字」的顺序一致（文字不被一起转掉）。
        payload = self._text_payload()
        params = {"image": original, "rect": QRectF(rect),
                  "xf": QTransform(xf), "region": QImage(region),
                  "grow": grow, "clipping": clipping,
                  "interpolation": interpolation, "target": path,
                  "payload": payload}
        self._async_apply = {
            "path": path, "rect": QRectF(rect), "xf": QTransform(xf),
            "clipping": clipping, "original": original, "payload": payload,
        }
        # ⚠️ worker 不能以 dialog 为 parent：exec() 一返回宿主的引用就松了，
        #    GC 掉 dialog 会连坐 QThread ⇒ abort。改为 _ACTIVE_APPLIES 持
        #    强引用（完成/失败回调里移除），worker 无 parent 由 dialog 持。
        worker = _BakeWorker(_apply_job, params, None)
        self._async_worker = worker
        _ACTIVE_APPLIES.append(self)
        app = QApplication.instance()
        if app is not None and not getattr(self, "_async_quit_hooked", False):
            self._async_quit_hooked = True
            # 退出时把在跑的烘焙收掉：进度回调粒度足够细，cancel 后
            # wait() 只等一瞬间；绝不留"线程还跑着对象全没了"的局面
            app.aboutToQuit.connect(self._cancel_async_apply)
        worker.finished.connect(self._on_async_apply_done)
        worker.start()
        self.accept()
        return True

    def _on_async_apply_done(self) -> None:
        """后台应用完成（``worker.finished``，排队回主线程）：收尾 + 发信号。"""
        state = getattr(self, "_async_apply", None)
        worker = getattr(self, "_async_worker", None)
        if state is None or worker is None:
            return
        self._async_worker = None
        result = worker.result
        image, saved = result if isinstance(result, tuple) else (None, False)
        path_text = str(state["path"])
        try:
            if worker.error is not None:
                detail = worker.error
                self.apply_failed.emit(
                    path_text, f"{type(detail).__name__}: {detail}")
            elif worker.cancelled or image is None:
                self.apply_failed.emit(path_text, "应用已取消，底片未改动")
            elif not saved:
                self.apply_failed.emit(path_text,
                                       "写入底片失败（文件可能被占用）")
            else:
                self._image = image
                self._content_after_bake(state["rect"], state["xf"],
                                         state["clipping"],
                                         state["original"])
                if state["payload"]:
                    # 文字是烘焙**之后**重放到画布像素上的：upright 缓存已
                    # 不含文字 ⇒ 置脏（下次恢复会话从当前画布重算）
                    self._content_pixels_dirty = True
                sync_content_quad(path_text, self)
                self.apply_completed.emit(path_text, QImage(image))
        finally:
            self._async_apply = None
            if self in _ACTIVE_APPLIES:
                _ACTIVE_APPLIES.remove(self)
            worker.deleteLater()
            # ⚠️ 释放整图级缓冲再析构（2026-10-13「内存越来越大」）：deleteLater
            #    只销毁 C++ 对象，Python 侧 ``_original``/``_undo`` 等 QImage 引用
            #    还被宿主的 ``_editor`` 属性攥着——不显式清掉，整图（撤销栈最多
            #    12 份）会跨任务驻留。信号已在上面发完，宿主拿到的是拷贝。
            #    ⚠️ keep_result：宿主约定「关窗后仍可取 result_image()」（自测
            #    image_editor_saveback 钉死），``_image`` 这一份要留着。
            release = getattr(self, "release_buffers", None)
            if callable(release):
                release(keep_result=True)
            self.deleteLater()

    def _cancel_async_apply(self) -> None:
        """应用退出时的兜底：请求取消在跑的烘焙并等它停下（不写半截文件）。"""
        worker = getattr(self, "_async_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait()
