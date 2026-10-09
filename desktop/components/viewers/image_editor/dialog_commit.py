# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**工具提交**。

把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from .bake import run_with_progress
from .consts import (
    CLIPPING_DEFAULT, DIRECTION_DEFAULT, DISTORT_SYNC_RENDER_PIXELS,
    INTERPOLATION_DEFAULT, STEP_CROP, STEP_DISTORT, STEP_ERASE, STEP_FLIP,
    STEP_TEXT, STEP_TRANSFORM,
)
from .geometry import (
    center_crop_aspect, clamp_rect, compose_transform, draw_text,
)
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


def _transform_target_pixels(image, rect: QRectF, xf, grow: bool) -> float:
    """这次烘焙大约要算多少**目标像素**（决定同步算还是丢后台）。

    ``grow`` 档的输出就是"变换后内容的外框"（``compose_transform`` 里由
    ``transform_region`` 算），所以直接量四角映射后的外接框；``clip`` 档
    输出恒 = 原画布。取不到图时返回 0（当作小任务同步算）。
    """
    if image is None or image.isNull():
        return 0.0
    if not grow:
        return float(image.width() * image.height())
    corners = [rect.topLeft(), rect.topRight(),
               rect.bottomRight(), rect.bottomLeft()]
    mapped = [xf.map(point) for point in corners]
    xs = [point.x() for point in mapped]
    ys = [point.y() for point in mapped]
    width = max(1.0, max(xs) - min(xs))
    height = max(1.0, max(ys) - min(ys))
    return width * height


def _transform_job(values: dict, progress=None):
    """后台线程里跑的**纯计算**：按 ``values`` 把变换烘焙成一张新图。

    ⚠️ 只用到形参（不碰画布/部件），这样才能安全放进 :class:`_BakeWorker`。
    参数全部在主线程打包好（``QImage`` 跨线程只读传递是安全的）。
    """
    rect, xf, region = values["rect"], values["xf"], values["region"]
    original = values["image"]
    grow = bool(values["grow"])
    result = compose_transform(
        original, rect, xf, region, grow=grow,
        interpolation=values["interpolation"], progress=progress)
    if result is None:                 # 用户取消
        return None
    # ⚠️ ``grow=False``（剪裁=裁剪到原画布）返单张 QImage，**不能**解包：
    #    QImage 是可迭代对象，误按元组解包会在运行期炸出难懂的错误。
    image = result[0] if grow else result
    if values["clipping"] == "aspect":
        image = center_crop_aspect(image, original.width(), original.height())
    return image


class CommitMixin(DialogHost):
    """把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。"""

    # ------------------------------------------------------------ 应用
    def _selection(self) -> QRectF | None:
        rect = self.canvas.selection()
        if rect is None:
            return None
        return clamp_rect(rect, self.canvas.image_rect())


    def _apply_crop(self) -> None:
        """把图裁成当前选区（一步撤销点）。

        ⚠️ 裁剪**没有**「应用裁剪」按钮：画布拖完松手发 ``crop_committed``，
        弹窗直接调这里（松手即应用）。
        ⚠️ 选区就是整幅时**直接返回**：点一下不拖、或拖回原位，不该白压一个
        空撤销步、也不该换图（换图会把视图 fit 一遍，看起来像闪了一下）。
        """
        rect = self._selection()
        if rect is None or self._image is None:
            return
        full = self.canvas.image_rect()
        if (abs(rect.left() - full.left()) < 0.5
                and abs(rect.top() - full.top()) < 0.5
                and abs(rect.width() - full.width()) < 0.5
                and abs(rect.height() - full.height()) < 0.5):
            return
        self._push_undo(STEP_CROP)
        self._image = self._image.copy(rect.toRect())
        self.canvas.set_image(self._image)
        self._refresh_size_label()


    # ------------------------------------------------------------ 一笔开始
    def _on_stroke_started(self) -> None:
        """画布上一笔开始（擦除 / 扭曲提交）：压撤销点，步骤名按当前工具取。

        橡皮擦在**按下时**就发 ``stroke_started``；扭曲在**松手提交前**发
        （见 ``DistortionMixin._finish_distortion_stroke``）。两条路都要求
        "先压点、后改像素"，所以统一在这里按工具分流取名。
        """
        label = STEP_DISTORT if self.canvas.tool == "distort" else STEP_ERASE
        self._push_undo(label)


    # ------------------------------------------------------------ 变换
    def _commit_transform(self, label: str = STEP_TRANSFORM,
                          force: bool = False) -> None:
        """把未应用的变换烘焙进图片（一个撤销点）；没有变换就只清预览。

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
            return
        canvas = self.canvas
        pending = canvas.transform_pending()
        if pending is None:
            canvas.reset_transform()
            return
        # ⚠️ 松手挂起（没 force）时**不烘**：内容已经在画布上实时显示，
        #    再烘一遍就是"每次松手等 11 秒"（就是用户报的那个问题）。
        if not force and hasattr(canvas, "has_pending_transform") \
                and canvas.has_pending_transform():
            canvas.reset_transform_preview_flags()
            return
        rect, xf, region = pending
        if getattr(canvas, "_xf_direction", DIRECTION_DEFAULT) == "backward":
            inverse, ok = xf.inverted()
            if ok:
                xf = inverse
        interpolation = getattr(canvas, "_xf_interpolation",
                                INTERPOLATION_DEFAULT)
        clipping = getattr(canvas, "_xf_clipping", CLIPPING_DEFAULT)
        original = self._image
        # grow（画布跟着内容长）只由「剪裁」决定：``clip`` 保持原画布（
        # compose_transform 返单张 QImage），另外两档返 ``(图, 原点)``。
        grow = clipping != "clip"
        # 目标像素预算：按"变换后内容的外框"估（透视/旋转会把外框撑大）
        target = _transform_target_pixels(original, rect, xf, grow)
        # ⚠️ 撤销点**先压、两条路只压一次**：后台那条是模态进度框，用户能看见
        #    "在做什么"；点了取消就走 _undo_now() 把它退掉（不留空撤销步）。
        self._push_undo(label)
        if target <= DISTORT_SYNC_RENDER_PIXELS:
            result = compose_transform(original, rect, xf, region, grow=grow,
                                       interpolation=interpolation)
            image = result[0] if grow else result
            if clipping == "aspect":
                image = center_crop_aspect(
                    image, original.width(), original.height())
        else:
            image = self._bake_transform_async(rect, xf, region, grow, clipping,
                                               interpolation)
        if image is None:          # 用户在进度框里点了取消：这一步整条作废
            self._undo_now()
            self.canvas.reset_transform()
            return
        self._image = image
        # ⚠️ ``refit=False``：画布会长大一点，但**不要**重新适应窗口——否则
        #    每次松手都把图缩小一档，反复旋转就是"越转越小"（用户报障）。
        self.canvas.set_image(self._image, refit=False)
        self._refresh_size_label()

    def _bake_transform_async(self, rect: QRectF, xf, region, grow: bool,
                              clipping: str, interpolation: str):
        """把整幅烘焙丢进后台线程 + 进度框；返回新图，用户取消时返回 ``None``。

        ⚠️ **不压撤销点**：那是 :meth:`_commit_transform` 的职责（两条路只压
        一次）。这里只负责"跑重活 + 失败要说出来"，失败返回 ``None`` 由调用方
        统一退回（撤销点也一起退）。
        """
        params = {"image": self._image, "rect": QRectF(rect),
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
            self._refresh_size_label()
            return
        canvas.transform_flip(bool(horizontal))
        # 翻转是**独立的一步**（按钮触发，不是拖动）：立刻烘焙，名字记「翻转」
        self._commit_transform(STEP_FLIP, force=True)


    # ------------------------------------------------------------ 文字
    def _spawn_text_block(self, pos: QPointF) -> None:
        """文字工具点击落点 → 画布上生成文字块就地编辑（光标可见）。"""
        if self._image is None or self._image.isNull():
            return
        self.canvas.add_text_block(
            pos, self._text_size, QColor(self._text_color),
            self._text_family,
        )


    def _commit_text_blocks(self) -> None:
        """把画布上非空文字块写进图片（一个批次一个撤销点），然后清块。"""
        if not hasattr(self, "canvas"):
            return
        blocks = self.canvas.text_blocks()
        payload = [
            (b.pos(), b.toPlainText(), b.font().pixelSize(),
             QColor(b.defaultTextColor()), b.font().family())
            for b in blocks if b.toPlainText().strip()
        ]
        self.canvas.clear_text_blocks()
        if not payload or self._image is None or self._image.isNull():
            return
        self._push_undo(STEP_TEXT)
        for pos, text, px, color, family in payload:
            self._image = draw_text(
                self._image, pos, text, px, color, family)
        self.canvas.replace_image(self._image)
