# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``ImageEditorDialog`` Mixin：**工具提交**（子包）。"""
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

from .async_apply import AsyncApplyMixin
from .content import ContentCommitMixin
from .crop import CropCommitMixin
from .jobs import (
    _apply_job, _render_text_payload, _same_rect, _transform_job,
    _transform_target_pixels, _unrotate_job,
)
from .state import _ACTIVE_APPLIES
from .text import TextCommitMixin
from .tool_transition import ToolTransitionMixin


class CommitTransformMixin(DialogHost):
    """统一变换的提交 / 后台烘焙 / 翻转。"""


    def _commit_transform(self, label: str = STEP_TRANSFORM,
                          force: bool = False,
                          update_canvas: bool = True) -> bool:
        """把未应用的变换烘焙进图片（一个撤销点）；没有变换就只清预览。

        返回 ``True`` = 没有变换或烘焙成功；``False`` = 用户在进度框里取消
        或烘焙失败（此时图已退回变换前，调用方「完成」据此中止收尾，
        绝不把未变换的图当结果写盘）。信号连接与翻转路径不看返回值，不受影响。

        ⚠️⚠️ **只在"必须"时烘焙**（用户 2026-10-09 报障："仍然不能实时预览，
        而是最后才预览……只做了旋转就要等很久"）。分工：

        * **拖动中 / 松手后**：内容由画布上的浮层实时显示（画布变换，便宜），
          不碰像素 ⇒ 随便转多少圈都不用等；
        * **离开变换工具 / 点「完成」**（``force=True``）：才真正烘焙一次；
        * 大选区在画布侧已自动退回"松手即烘焙"（拖不动的假实时没意义）。

        切走工具、「完成」、以及「水平/垂直翻转」按钮都走这里——预览即所见，
        烘焙结果与浮层显示一致。

        ⚠️ 面板上的三项在这里才生效（画布只存选项、不烘焙）：

        - **方向**：``backward``（校正）用**反向**矩阵烘焙——框摆到歪掉的那
          一块上，出来的是被掰正的；``forward``（正常）就是把内容搬到框的位置。
        - **插值**：交给 :func:`compose_transform` 的逐像素反向重采样档位
          （``nohalo`` / ``linear`` / ``cubic`` / ``nearest``）。
        - **剪裁**：``adjust``（调整）画布跟着内容长、超出的不丢；``clip``
          （裁剪到原画布）尺寸不变、超出的裁掉；``aspect``（裁剪到原比例）
          先长再按**原始长宽比**居中裁回来。

        ⚠️ 预览与提交走的是**同一个** :func:`compose_transform`：画布侧的
        ``_ensure_transform_preview`` 用它算底图，这里用它算最终像素。所以
        「松手之后图变成什么样」在拖动期间就和预览完全一致，不会再出现
        "框在这里、内容却落在别处"。

        ⚠️⚠️ **大区域必须移出主线程**。整幅重采样是逐目标像素算的，实测
        3000×4000（12 MP）整幅提交要 **11.3 秒**——同步跑就把界面钉死
        （用户报的"页面卡顿"）。判据同扭曲提交（``DISTORT_SYNC_RENDER_PIXELS``）：
        目标像素数在预算内直接算，超了就丢进 :func:`run_with_progress`
        （进度对话框 + 可取消），取消时把这一步退回、撤销点也退掉。
        """
        if not hasattr(self, "canvas"):
            return True
        canvas = self.canvas
        pending = canvas.transform_pending()
        if pending is None:
            canvas.reset_transform()
            was_restored = getattr(self, "_content_restored", False)
            self._content_exit_restore()  # 恢复会话没拖就走：画布本来就是原样
            # ⚠️ 恢复会话没拖就切走（裁剪没裁/文字/擦除/扭曲——都不改图片
            #    边缘）：下次进「统一变换」要重新恢复 PA1（用户 2026-10-10
            #    口径「图片边缘没有变化的话，切回统一变换需要恢复原先状态」）。
            #    节点仍有效才重挂：真裁剪/撤销/翻转已走 ``_content_clear``
            #    （state=None），这里自然放行不过。
            if was_restored and getattr(self, "_content_state", None) \
                    is not None:
                canvas.rearm_content_restore()
            return True
        # ⚠️ 松手挂起（没 force）时**不烘**：内容已经在画布上实时显示，
        #    再烘一遍就是"每次松手等 11 秒"（就是用户报的那个问题）。
        if not force and hasattr(canvas, "has_pending_transform") \
                and canvas.has_pending_transform():
            canvas.reset_transform_preview_flags()
            return True
        rect, xf, region = pending
        if getattr(canvas, "_xf_direction", DIRECTION_DEFAULT) == "backward":
            inverse, ok = xf.inverted()
            if ok:
                xf = inverse
        interpolation = getattr(canvas, "_xf_interpolation",
                                INTERPOLATION_DEFAULT)
        clipping = getattr(canvas, "_xf_clipping", CLIPPING_DEFAULT)
        # ⚠️ 恢复会话（内容节点挂回）：烘焙源＝**upright 内容**而不是画布
        #    PB1——画布里的内容是上一轮的烘焙结果，从它再采样就叠加代次；
        #    从 upright 一次重采样到新位，永远只有一代损失（2026-10-10）。
        upright = getattr(self, "_content_upright", None)
        if getattr(self, "_content_restored", False) and upright is not None:
            original = upright
        else:
            original = self._image
        # grow（画布跟着内容长）只由「剪裁」决定：``clip`` 保持原画布（
        # compose_transform 返单张 QImage），另外两档返 ``(图, 原点)``。
        grow = clipping != "clip"
        # 目标像素预算：按"变换后内容的外框"估（透视/旋转会把外框撑大）
        target = _transform_target_pixels(original, rect, xf, grow)
        # ⚠️ 撤销点**先压、两条路只压一次**：后台那条是模态进度框，用户能看见
        #    "在做什么"；点了取消就走 _undo_now() 把它退掉（不留空撤销步）。
        self._push_undo(label)
        # 新画布原点在旧坐标系里的平移（双图编辑的相对摆放靠它不漂；
        # clip 档画布不动恒 (0,0)，aspect 档在 job/同步分支里补居中裁剪量）
        bake_origin = (0.0, 0.0)
        if target <= TRANSFORM_SYNC_RENDER_PIXELS:
            result = compose_transform(original, rect, xf, region, grow=grow,
                                       interpolation=interpolation)
            if grow:
                image, bake_origin = result
                bake_origin = (float(bake_origin[0]), float(bake_origin[1]))
            else:
                image = result
            if clipping == "aspect":
                pre_w, pre_h = image.width(), image.height()
                image = center_crop_aspect(
                    image, original.width(), original.height())
                bake_origin = (
                    bake_origin[0] + (pre_w - image.width()) / 2.0,
                    bake_origin[1] + (pre_h - image.height()) / 2.0)
        else:
            baked = self._bake_transform_async(rect, xf, region, grow,
                                               clipping, interpolation,
                                               original)
            if baked is None:          # 用户在进度框里点了取消：下面统一退回
                image, bake_origin = None, (0.0, 0.0)
            else:
                image, bake_origin = baked
        if image is None:          # 用户在进度框里点了取消：这一步整条作废
            # ⚠️ 这里的 _undo_now 是"退掉本次烘焙的撤销点"，不是用户按了
            #    Ctrl+Z——挡住历史跳转钩子，别把内容节点整组作废掉。
            self._content_in_cancel = True
            try:
                self._undo_now()
            finally:
                self._content_in_cancel = False
            self.canvas.reset_transform()
            state = getattr(self, "_content_state", None)
            seed = getattr(self, "_content_seed", None)
            upright = getattr(self, "_content_upright", None)
            if state is not None and seed is not None and upright is not None:
                # 恢复会话里取消：画布本来就是文件原样（PB1 没换过），把
                # 种子矩阵重新挂回去——下一次拖拽依旧从"保存前的状态"继续。
                self._content_restored = True
                self.canvas.begin_restored_transform(seed, upright)
            else:
                self._content_exit_restore()
            return False
        self._image = image
        # ⚠️ 双图编辑：新画布的 (0,0) 挪到了 ``bake_origin``——内容原点跟着
        #    平移，另一张图的相对摆放才不漂。必须在 ``_push_undo`` 之后
        #    （撤销点带的是平移前的 origin）。
        if grow:
            self._multi_layer_shift(bake_origin[0], bake_origin[1])
        # ⚠️ ``refit=False``：画布会长大一点，但**不要**重新适应窗口——否则
        #    每次松手都把图缩小一档，反复旋转就是"越转越小"（用户报障）。
        # ⚠️ ``update_canvas=False``（「完成」收尾传）：弹窗马上就关，页面
        #    上的重渲染（QPixmap 转换 + 场景重建）纯属浪费——用户 2026-10-10
        #    口径「页面上的数据可以不保存，只需要将数据存到相应的底片上」。
        if update_canvas:
            self.canvas.set_image(self._image, refit=False)
            self._refresh_size_label()
            if getattr(self, "_multi_layers", None):
                self._refresh_multi_canvas()
        else:
            # 「完成」收尾不重渲染页面（弹窗马上关），但**变换状态必须清**：
            # 旧版是 set_image 顺手干的（换图清一切），跳过它就得显式清——
            # 否则 ``transform_pending()`` 仍非空，弹窗关闭前挂着假状态。
            self.canvas.reset_transform()
        self._content_after_bake(rect, xf, clipping, original)
        return True

    def _bake_transform_async(self, rect: QRectF, xf, region, grow: bool,
                              clipping: str, interpolation: str,
                              original=None):
        """把整幅烘焙丢进后台线程 + 进度框；返回 ``(新图, 原点平移)``，
        用户取消时返回 ``None``。

        ⚠️ **不压撤销点**：那是 :meth:`_commit_transform` 的职责（两条路只压
        一次）。这里只负责"跑重活 + 失败要说出来"，失败返回 ``None`` 由调用方
        统一退回（撤销点也一起退）。``original``＝烘焙源（恢复会话是
        upright 内容而不是画布 PB1，见 :meth:`_commit_transform`）。
        """
        params = {"image": self._image if original is None else original,
                  "rect": QRectF(rect),
                  "xf": xf, "region": region, "grow": grow,
                  "clipping": clipping, "interpolation": interpolation}
        try:
            return run_with_progress(
                self, "变换处理中", "正在应用变换（松开鼠标时的整幅重采样）…",
                _transform_job, params)
        except BaseException as exc:      # noqa: BLE001（兜底：不许逃出提交链）
            self._report_transform_failure(exc)
            return None

    def _report_transform_failure(self, exc: BaseException) -> None:
        """把提交失败说出来（否则用户只看到"点了没反应"）。"""
        from desktop.ui.toast import show_toast

        show_toast(self, "error", "变换没能应用",
                   f"已退回变换前的样子：{type(exc).__name__}: {exc}")

    def _flip_transform(self, horizontal: bool = True) -> None:
        """水平/垂直翻转：立即镜像并烘焙（一步撤销点，名字是「翻转」）。

        ⚠️⚠️ **纯镜像走快路径**（2026-10-09 用户报「水平/垂直翻转卡顿、太
        慢」）：画布上没有未应用的变换、选区就是整幅时，翻转 = 整幅镜像——
        ``QImage.mirrored`` 是像素级翻转，12 MP 也是一瞬；而走
        :meth:`_commit_transform` 那条路要整幅逐像素反向重采样（实测
        12 MP 约 11 秒，就是用户报的卡顿）。翻转不改外框，两条路产物一致。

        其余情况（选区局部 / 已有未应用变换）仍走 :meth:`_commit_transform`
        这条唯一通道——插值/剪裁选项与其它变换保持一致，烘焙结果和画布上
        的浮层预览是同一条代码路径。
        """
        if not hasattr(self, "canvas") or self._image is None:
            return
        canvas = self.canvas
        rect = canvas.selection()
        full = canvas.image_rect()
        if (canvas.transform_pending() is None and rect is not None
                and rect == QRectF(full)):
            self._push_undo(STEP_FLIP)
            self._image = self._image.mirrored(
                bool(horizontal), not horizontal)
            # refit=False：尺寸没变，视图不该跟着跳
            canvas.set_image(self._image, refit=False)
            self._content_clear()   # 镜像改变了节点几何语义（快路径没走 V 链）
            self._refresh_size_label()
            return
        canvas.transform_flip(bool(horizontal))
        # 翻转是**独立的一步**（按钮触发，不是拖动）：立刻烘焙，名字记「翻转」
        self._commit_transform(STEP_FLIP, force=True)


class CommitMixin(
    CommitTransformMixin,
    ToolTransitionMixin,
    CropCommitMixin,
    ContentCommitMixin,
    AsyncApplyMixin,
    TextCommitMixin,
    DialogHost,
):
    """把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。"""


__all__ = [
    "CommitMixin",
    "_ACTIVE_APPLIES", "_apply_job", "_render_text_payload", "_same_rect",
    "_transform_job", "_transform_target_pixels", "_unrotate_job",
    "center_crop_aspect", "compose_transform", "draw_text",
]
