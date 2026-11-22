# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""工具提交：内容四角节点恢复会话。"""
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
from .jobs import _same_rect, _unrotate_job

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class ContentCommitMixin(DialogHost):
    """工具提交：内容四角节点恢复会话。"""



    # ------------------------------------------------------------ 变换
    # ---- 内容四角节点（sidecar 恢复，2026-10-10） ----
    def content_state(self):
        """内容节点 ``(rect0, V)``；None = 无节点（宿主据此写/清 sidecar）。"""
        state = getattr(self, "_content_state", None)
        if state is None:
            return None
        return QRectF(state[0]), QTransform(state[1])

    def _content_clear(self) -> None:
        """节点整组作废（裁剪/镜像/clip 档/历史跳转/反变换失败）。

        ⚠️ 宁可不恢复也不能错恢复：任何几何语义变化后，旧 (rect0, V) 对
        新像素不再成立；清掉后二次编辑退回"整幅矩形"框架（bumper：入口
        收紧仍然保证主体是内容）。
        """
        self._content_state = None
        self._content_upright = None
        self._content_seed = None
        self._content_restored = False
        self._content_pixels_dirty = False
        canvas = getattr(self, "canvas", None)
        if canvas is not None and hasattr(canvas, "consume_content_restore"):
            canvas.consume_content_restore()

    def _content_exit_restore(self) -> None:
        """恢复会话没烘焙就结束（切工具/「完成」都没拖过）。

        ⚠️ 画布从头到尾都是文件原样（PB1 一个像素没换），这里只需落标志；
        挂着的预览由调用方 ``reset_transform`` 撤掉。
        """
        self._content_restored = False

    def _content_on_history_jump(self) -> None:
        """撤销/重做/历史跳转后：节点状态与像素快照可能不再对应。

        跳转后的 ``_image`` 是历史里的某一帧，与 (rect0, V) 的对应关系已断
        ——整组作废，保证**永不错恢复**。（烘焙取消路径内部的 ``_undo_now``
        走 :attr:`_content_in_cancel` 守卫，不算历史跳转。）
        """
        if getattr(self, "_content_in_cancel", False):
            return
        self._content_exit_restore()
        self._content_clear()

    def _on_content_restore_requested(self) -> None:
        """画布进入变换工具：读 sidecar，把内容四边形恢复成可操作区域。

        ⚠️ **画布不换图**（用户 2026-10-10 口径「PB1 要作为画布，PA1 要
        作为可操作的区域恢复」）：``self._image`` 保持文件原样；upright
        （sidecar 反变换产物）只作浮层源与烘焙源，种子矩阵挂回变换工具后
        框/手柄/轴心直接落在内容四边形上，视觉与打开时零跳变。

        ⚠️⚠️ **反变换延迟**（2026-10-10「切换卡顿」）：这里**只**做读
        sidecar + 算种子矩阵（JSON 微秒级 + 矩阵乘法，零等待），像素反变换
        （秒级重活）推迟到第一次建预览（＝第一次拖动）——画布发
        ``restore_pixels_requested``、本类 :meth:`_on_restore_pixels_requested`
        接住才算。之前每次进变换工具都卡在那里等它，用户报的正是这个。
        已有 upright 缓存（本会话早先烘焙过）时直接挂完整版，零额外成本。
        """
        canvas = self.canvas
        if not getattr(self, "_content_read", False):
            self._content_read = True
            path = str(getattr(self, "source_path", "") or "")
            quad = read_quad(path) if path else None
            if quad is not None:
                self._content_state = quad
        state = self._content_state
        if state is None:
            canvas.consume_content_restore()
            return
        rect0, xf = state
        tx, ty = getattr(self, "_content_trim_offset", (0, 0))
        # ⚠️ 种子矩阵＝**画布系**：sidecar 的 V 是文件系（文件＝V×rect0 外框
        #    裁剪，外框左上角 o＝quad_frame），入口收紧又把文件平移了 -t，
        #    所以内容四边形在 PB1 里 ＝ V×rect0 −(o+t)——挂到画布的矩阵要
        #    补上这两个平移，浮层/框/手柄才与已烘焙的内容严丝合缝。
        ox, oy, _fw, _fh = quad_frame(xf, rect0)
        seed = (QTransform(xf)
                * QTransform().translate(-(ox + tx), -(oy + ty)))
        self._content_seed = seed
        canvas.consume_content_restore()
        # ⚠️ upright 缓存**只在像素真变过时作废**（2026-10-11：之前"一律
        #    作废"让每轮切走再切回都重算秒级反变换＝切换卡顿，且重算产物
        #    是烘焙产物的再采样 ⇒ 每轮多一代重采样、PA1 边缘元素逐轮流失）。
        #    擦除/文字/扭曲会置脏位；旋转/空裁剪不改像素 ⇒ 缓存仍有效 ⇒
        #    **全量武装**（零等待，烘焙仍从同一份 upright 单代次重采样）。
        upright = getattr(self, "_content_upright", None)
        if upright is not None and not getattr(
                self, "_content_pixels_dirty", False):
            self._content_restore_params = None
            self._content_restored = True
            canvas.begin_restored_transform(seed, upright)
            return
        # 像素变过（或还没算过）：作废缓存，挂"框 + 矩阵"的延迟版，反变换
        # 参数留给补像素槽（首次拖动才算，源＝**当前画布**——擦除原地改
        # 引用不变，身份比对不可靠，脏位是唯一可靠信号）。
        self._content_upright = None
        self._content_pixels_dirty = False   # 重算源＝当前画布，自此一致
        # 挂"框 + 矩阵"的延迟版，反变换参数留给补像素槽（首次拖动才算）。
        # ⚠️ ``_content_restored`` 此刻就要置位：它标记"本会话是恢复会话"
        #    （烘焙源＝upright、V 链延续），与"像素算没算"是两回事——等
        #    像素补上用户才拖得动，那时烘焙源必须是 upright。
        self._content_restore_params = {
            "image": self._image, "rect": QRectF(rect0),
            "xf": QTransform(xf), "origin_shift": (tx, ty),
            "interpolation": INTERPOLATION_DEFAULT,
        }
        self._content_restore_target = rect0.width() * rect0.height()
        self._content_restored = True
        canvas.begin_restored_transform(seed, None, QRectF(rect0))

    def _on_restore_pixels_requested(self) -> None:
        """画布第一次建预览（＝第一次拖动）要 upright 像素了：现在才算。

        进变换工具那一刻（:meth:`_on_content_restore_requested`）是零等待
        的；真正的秒级反变换挪到这一刻，且只此一次（算完进
        ``_content_upright`` 缓存）。失败/取消 = 整组放弃（画布退回普通
        会话），口径同前：**宁可不恢复，也不能错恢复**。
        """
        canvas = self.canvas
        upright = getattr(self, "_content_upright", None)
        if upright is None or upright.isNull():
            params = getattr(self, "_content_restore_params", None)
            if not params:
                self._content_clear()
                canvas.abort_content_restore()
                return
            target = getattr(self, "_content_restore_target", 0.0)
            if target <= DISTORT_SYNC_RENDER_PIXELS:
                upright = _unrotate_job(params)
            else:
                try:
                    upright = run_with_progress(
                        self, "恢复内容区域",
                        "正在还原上次的内容变换（反变换回摆正的内容）…",
                        _unrotate_job, params)
                except BaseException as exc:  # noqa: BLE001（兜底不许逃出）
                    self._report_transform_failure(exc)
                    upright = None
            if upright is None or upright.isNull():
                self._content_clear()
                canvas.abort_content_restore()
                return
            self._content_upright = upright
            self._content_restore_params = None
        canvas.provide_restore_pixels(upright)

    def _content_after_bake(self, rect: QRectF, xf, clipping: str,
                            original) -> None:
        """变换烘焙成功后维护节点：adjust+整幅 ⇒ V=总量矩阵；否则整组作废。"""
        input_was_upright = bool(getattr(self, "_content_restored", False))
        self._content_restored = False
        if clipping != "adjust" or not _same_rect(rect, QRectF(original.rect())):
            self._content_clear()         # 裁到原画布/局部选区：四边形语义失效
            return
        if input_was_upright or self._content_state is None:
            # 输入＝upright（恢复会话）或首次建链：xf 就是"upright→呈现"
            # 的纯总量矩阵（拖拽都叠加在种子矩阵上），rect0＝本次输入整幅。
            self._content_state = (QRectF(rect), QTransform(xf))
            # ⚠️ 烘焙输入**就是** upright 基准像素（恢复会话 original＝
            #    upright 本身；首次建链 original＝烘焙前的画布——V 正是
            #    从它出发的）。缓存住它：之后切走再切回全量武装零重算，
            #    每轮烘焙都从同一份像素单代次重采样（不缓存的话下一轮
            #    得从烘焙产物再采样一代，PA1 边缘逐轮流失——2026-10-11）。
            self._content_upright = original
            self._content_pixels_dirty = False
            # ⚠️ 画布此刻已是**烘焙产物**（＝新底片的坐标，自洽成帧）：入口
            #    收紧偏移 t 是"打开文件那一刻"的量，对新画布不再成立——不清
            #    掉的话，重挂种子矩阵 V·T(-(o+t)) 会整体错位 t。
            self._content_trim_offset = (0.0, 0.0)
            # ⚠️ 节点有效 ⇒ 重新武装恢复闸门（用户 2026-10-10 报障：旋转后
            #    切到裁剪再切回，「统一变换」的 PA1 框丢了——带挂起变换的
            #    烘焙分支之前不 rearm，``_content_restore_done`` 永久为 True，
            #    再进变换工具不会发恢复请求，框退成整幅）。只在**有底片文件**
            #    时武装：sidecar 机制围着文件转，无 source_path 的会话（测试
            #    裸画布等）保持普通会话语义。
            if str(getattr(self, "source_path", "") or ""):
                canvas = getattr(self, "canvas", None)
                if canvas is not None and hasattr(
                        canvas, "rearm_content_restore"):
                    canvas.rearm_content_restore()
            return
        self._content_clear()             # 链路断了：宁可不恢复
