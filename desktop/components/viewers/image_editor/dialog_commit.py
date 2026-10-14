# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**工具提交**。

把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform
from PySide6.QtWidgets import QApplication, QProgressDialog
from .bake import _BakeWorker, run_with_progress
from .content_quad import quad_frame, read_quad, sync_content_quad, upright_image
from .consts import (
    CLIPPING_DEFAULT, DIRECTION_DEFAULT, DISTORT_SYNC_RENDER_PIXELS,
    INTERPOLATION_DEFAULT, STEP_CROP, STEP_DISTORT, STEP_ERASE, STEP_FLIP,
    STEP_TEXT, STEP_TRANSFORM, TRANSFORM_SYNC_RENDER_PIXELS,
)
from .geometry import (
    center_crop_aspect, clamp_rect, compose_transform, draw_text,
)
from typing import TYPE_CHECKING
from desktop.workers.worker_host import connect_queued


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


#: 后台应用进行中的编辑器（「完成」关窗即返回，烘焙+写底片在工作线程）。
#: ⚠️ 必须持有**Python 强引用**：``exec()`` 返回后宿主的局部变量会释放，
#: 没有它 dialog（连同工作线程）会被 GC 掉 ⇒ ``QThread: Destroyed while
#: thread is still running`` 直接 abort 整个进程。完成/失败回调里移除。
_ACTIVE_APPLIES: list = []


def _same_rect(a: QRectF, b: QRectF, tol: float = 0.5) -> bool:
    """两个矩形是不是同一块（带半像素容差，浮点坐标用）。"""
    return (abs(a.left() - b.left()) < tol
            and abs(a.top() - b.top()) < tol
            and abs(a.width() - b.width()) < tol
            and abs(a.height() - b.height()) < tol)


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

    返回 ``(image, (ox, oy))``：``(ox, oy)``＝**新画布左上角在旧坐标系里的
    位置**（grow 档画布跟着内容长，双图编辑靠它平移内容原点让另一张图不
    漂走；clip 档画布不动，恒 ``(0, 0)``）。用户取消返回 ``None``。
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
    if grow:
        image, origin = result
        origin = (float(origin[0]), float(origin[1]))
    else:
        image, origin = result, (0.0, 0.0)
    if values["clipping"] == "aspect":
        pre_w, pre_h = image.width(), image.height()
        image = center_crop_aspect(image, original.width(), original.height())
        # 居中裁回原比例也是一段原点平移（裁掉的是两边对称的边）
        origin = (origin[0] + (pre_w - image.width()) / 2.0,
                  origin[1] + (pre_h - image.height()) / 2.0)
    return image, origin


def _unrotate_job(values: dict, progress=None):
    """后台线程里跑的**纯计算**：把落盘文件反变换回 upright 内容。

    「内容四角节点」恢复的前半程（2026-10-10）：sidecar 里的 ``(rect0, V)``
    记着内容怎么从摆正状态变成现在这样；把像素按 ``V⁻¹(+原点+收紧偏移)``
    反变换回 rect0，后续变换以它为烘焙源——烘焙永远从 upright 一次重采样，
    不叠加代次损失。⚠️ 画布**不换图**（PB1 保持原样），upright 只当浮层
    源与烘焙源（用户口径「PB1 作为画布，PA1 作为可操作区域」）。
    """
    return upright_image(values["image"], values["rect"], values["xf"],
                         values["interpolation"], progress,
                         values.get("origin_shift", (0.0, 0.0)))


def _apply_job(values: dict, progress=None):
    """后台线程里跑的**纯计算**：「完成」的烘焙 + **原子写盘**（底片）。

    用户 2026-10-10 口径：「应用保存的时候页面上的数据可以不保存，只需要
    将数据存到相应的底片上」——弹窗在确认后**立即**关闭，本函数在工作线程
    里把变换烘焙出来并直接覆盖到 ``values["target"]``（宿主回填的
    ``source_path``，与各宿主自己的写盘目标是同一个文件，已逐一核对）。

    返回 ``(image, saved: bool)``；用户取消返回 ``(None, False)``。
    ⚠️ ``QImage.save`` / ``os.replace`` 都不碰 GUI 对象，工作线程里跑是
    安全的（``overwrite_image_file`` 的临时文件名自带线程 id）；它**必须**
    延迟导入——``image_zoom_dialog`` 包反过来导入本包，模块级导入会成环。
    """
    from desktop.components.viewers.image_zoom_dialog.io import (
        overwrite_image_file,
    )

    image_and_origin = _transform_job(values, progress)
    if image_and_origin is None:
        return None, False
    image, _origin = image_and_origin
    image = _render_text_payload(image, values.get("payload", []))
    saved = overwrite_image_file(image, Path(values["target"]))
    return image, saved


def _render_text_payload(image: QImage, payload: list) -> QImage:
    """把待提交文字画进最终图片，确保返回值与磁盘文件一致。"""
    for pos, text, px, color, family in payload:
        image = draw_text(image, pos, text, px, QColor(color), family)
    return image


class CommitMixin(DialogHost):
    """把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。"""

    def _start_async_tool_transition(self, tool: str) -> bool:
        """对大图先后台烘焙；完成后再切工具，避免主线程同步等待。"""
        pending = self.canvas.transform_pending()
        if pending is None:
            return False
        rect, xf, region = pending
        if getattr(self.canvas, "_xf_direction", DIRECTION_DEFAULT) == "backward":
            inverse, ok = xf.inverted()
            if ok:
                xf = inverse
        clipping = getattr(self.canvas, "_xf_clipping", CLIPPING_DEFAULT)
        grow = clipping != "clip"
        upright = getattr(self, "_content_upright", None)
        original = (
            upright if getattr(self, "_content_restored", False)
            and upright is not None else self._image
        )
        target = _transform_target_pixels(original, rect, xf, grow)
        if target <= TRANSFORM_SYNC_RENDER_PIXELS:
            return False

        params = {
            "image": original,
            "rect": QRectF(rect),
            "xf": QTransform(xf),
            "region": QImage(region),
            "grow": grow,
            "clipping": clipping,
            "interpolation": getattr(
                self.canvas, "_xf_interpolation", INTERPOLATION_DEFAULT),
        }
        worker = _BakeWorker(_transform_job, params, self)
        progress = QProgressDialog(
            "正在应用变换；完成后将切换功能…", "取消", 0, 100, self)
        progress.setWindowTitle("变换处理中")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        progress.canceled.connect(worker.cancel)
        connect_queued(self, worker.ticked,
                       self._on_async_tool_transition_progress, worker)
        connect_queued(self, worker.finished,
                       self._on_async_tool_transition_finished, worker)

        self._tool_transition_worker = worker
        self._tool_transition_progress = progress
        self._tool_transition_target = tool
        self._tool_transition_data = (QRectF(rect), QTransform(xf),
                                      clipping, original)
        # grow（画布跟内容长）与否：完成回调里决定要不要平移双图内容原点
        self._tool_transition_grow = grow
        self._set_async_tool_transition_busy(True)
        worker.start()
        return True

    def _set_async_tool_transition_busy(self, busy: bool) -> None:
        """冻结会改动当前图像/变换的控件，进度框仍保持响应。"""
        widgets = [
            self.canvas, self.undo_btn, self.redo_btn, self.reset_btn,
            self.zoom_out_btn, self.zoom_in_btn, self.fit_btn, self.done_btn,
            self._option_page,
            *getattr(self, "_tool_buttons", {}).values(),
        ]
        for widget in widgets:
            if widget is not None:
                widget.setEnabled(not busy)

    def _on_async_tool_transition_progress(self, done: int, total: int) -> None:
        progress = getattr(self, "_tool_transition_progress", None)
        if progress is not None and total > 0:
            progress.setValue(min(100, int(done * 100 / total)))

    def _on_async_tool_transition_finished(self) -> None:
        worker = getattr(self, "_tool_transition_worker", None)
        if worker is None:
            return
        progress = getattr(self, "_tool_transition_progress", None)
        tool = getattr(self, "_tool_transition_target", "erase")
        data = getattr(self, "_tool_transition_data", None)
        assert data is not None
        rect, xf, clipping, original = data
        self._tool_transition_worker = None
        self._tool_transition_progress = None
        self._tool_transition_target = None
        self._tool_transition_data = None
        grow = getattr(self, "_tool_transition_grow", False)
        self._tool_transition_grow = False
        if progress is not None:
            progress.canceled.disconnect(worker.cancel)
            progress.close()
            progress.deleteLater()

        try:
            result = worker.result
            image = None if result is None else result[0]
            bake_origin = (0.0, 0.0) if result is None else (
                float(result[1][0]), float(result[1][1]))
            if worker.error is not None:
                from desktop.ui.toast import show_toast

                show_toast(
                    self, "error", "变换没能应用",
                    f"变换预览仍保留，可重试或重置："
                    f"{type(worker.error).__name__}: {worker.error}",
                )
            elif image is not None and not image.isNull():
                self._push_undo(STEP_TRANSFORM)
                self._image = image
                # 双图编辑：新画布原点平移要在压撤销点**之后**记账
                if grow:
                    self._multi_layer_shift(bake_origin[0], bake_origin[1])
                self.canvas.set_image(image, refit=False)
                if getattr(self, "_multi_layers", None):
                    self._refresh_multi_canvas()
                self._content_after_bake(rect, xf, clipping, original)
                self._refresh_size_label()
                self._activate_tool(tool)
                self._sync_undo_buttons()
                self._sync_history()
            elif not worker.cancelled:
                from desktop.ui.toast import show_toast

                show_toast(
                    self, "error", "变换没能应用",
                    "后台变换未返回结果；变换预览仍保留，可重试或重置。",
                )
            # 用户取消时保留未烘焙的变换预览，允许重试或重置。
        finally:
            self._set_async_tool_transition_busy(False)
            self._sync_undo_buttons()
            worker.deleteLater()

    # ------------------------------------------------------------ 应用
    def _selection(self) -> QRectF | None:
        rect = self.canvas.selection()
        if rect is None:
            return None
        return clamp_rect(rect, self.canvas.image_rect())


    # ------------------------------------------------------------ 裁剪（待定 → 落定）
    def _preview_crop(self) -> None:
        """裁剪框拖完松手：**只记下选区**，一个像素都不动。

        ⚠️⚠️ 非破坏性裁剪（用户 2026-10-10 报障：「裁剪线可以向内移动也可以
        向外移动，向外移动，原本被隐藏的区域要显示出来」）。旧版在这里直接
        ``self._image.copy(rect)`` 把图裁小、画布换图并把选区重置成新图的
        整幅——于是**第二次拖动时手柄已经压在边界上，向外无处可拖**，系统里
        根本没有"还没落定"这个中间态（想找回只能 Ctrl+Z 或点历史某一格）。

        现在裁剪是**待定**的：

        - 松手只写 ``_pending_crop`` + 刷右下角的尺寸提示；
        - 拖动框内会预览整张图片与选区一起平移；选区外那 4 块半透明遮罩每帧按选区重算
          （``overlay._sync_overlay``）⇒ 向外拖时被变暗的区域立刻重新显露；
        - 真正的 ``copy()`` 推迟到 :meth:`_commit_crop`（切走裁剪工具 / 点
          「完成」），一次落定 = 一个撤销点。

        选区就是整幅且图片没有位移时当成"没裁"，把待定清掉。图片有位移时，
        应用会扩展画布并保留透明边距，以便位移写入图片文件。
        """
        rect = self._selection()
        if rect is None:
            return  # 选区被拖成 <MIN_RECT_EDGE 的废框：不动任何东西
        offset = self.canvas.crop_offset()
        if _same_rect(rect, self.canvas.image_rect()) \
                and offset == QPointF():
            self._discard_crop()
            return
        self._pending_crop = QRectF(rect)
        self._pending_crop_offset = (offset.x(), offset.y())
        self._refresh_size_label()


    def _commit_crop(self) -> None:
        """把**待定**裁剪真正落到像素上（切走裁剪工具 / 点「完成」时各调一次）。

        GIMP 口径："带着未确认的裁剪切走工具 = 确认这次裁剪"。不定这条规则
        的话两头都不对——切到擦除/变换时画布上还是整幅原图，用户以为裁剪丢了；
        而留在裁剪工具里又永远落不了地。

        没有待定裁剪就**直接返回**（连选区都不动：切功能不该顺手清掉用户的框）。
        """
        rect = getattr(self, "_pending_crop", None)
        if rect is None or self._image is None or self._image.isNull():
            return
        offset_x, offset_y = getattr(self, "_pending_crop_offset", (0.0, 0.0))
        self._pending_crop = None
        self._pending_crop_offset = (0.0, 0.0)
        shift_x, shift_y = round(offset_x), round(offset_y)
        source_rect = QRectF(rect).translated(-shift_x, -shift_y)
        # 选区和图片一起移动；换回源图坐标后裁切，再用透明边距编码图片位移。
        # toRect() 向外取整，再与源图矩形求交以兜住取整后越界 1px。
        box = source_rect.toRect().intersected(self._image.rect())
        if box.isEmpty():
            self.canvas.reset_selection()
            return
        pad_x, pad_y = max(0, shift_x), max(0, shift_y)
        result_width = box.width() + abs(shift_x)
        result_height = box.height() + abs(shift_y)
        self._push_undo(STEP_CROP)
        if box != self._image.rect() or shift_x or shift_y:
            # ⚠️ 真裁了（尺寸变了）：内容四边形 (rect0, V) 对新尺寸的像素
            #    不再成立，整组作废——切回「统一变换」退回整幅矩形框架，
            #    宁可不恢复也不能错恢复（用户 2026-10-10 口径「边缘变了
            #    就不恢复」）。选区＝整幅的"裁剪"像素没变，节点保留。
            self._content_clear()
        cropped = self._image.copy(box)
        if shift_x or shift_y:
            shifted = QImage(
                result_width, result_height,
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            shifted.fill(Qt.GlobalColor.transparent)
            painter = QPainter(shifted)
            painter.drawImage(QPoint(pad_x, pad_y), cropped)
            painter.end()
            self._image = shifted
        else:
            self._image = cropped
        # ⚠️⚠️ 原点累加的是**选区在新画布里的位移**，即 ``box + shift``
        #    （＝裁剪前选区在旧画布中的位置），**不能再减 ``pad``**
        #    （2026-10-14 用户报障「弹窗里把图下移 200px、应用后拼版页左图
        #    顶部没跟着走、底部反而长出一截」）：
        #    纯裁剪 shift=pad=0，两种写法一致（既有断言 origin==(20,10) 不受影响）；
        #    纯"移动"时 shift_y 与 pad_y **都等于位移**（200），旧式
        #    ``box.y + shift_y - pad_y`` 正好抵消成 0 ⇒ 位移被吞掉，
        #    回报给拼版的 rect 原地不动，而像素图已多出 200px 透明留白。
        self._multi_layer_shift(
            float(box.x() + shift_x),
            float(box.y() + shift_y),
        )
        # ⚠️ 双图模式换图**不**重新适应窗口（世界缩放保持，2026-10-13
        #    「不要放大缩小」）；单图维持"裁完 fit 一遍"的旧行为。
        self.canvas.set_image(self._image, refit=not self._multi_layers)
        if getattr(self, "_multi_layers", None):
            self._refresh_multi_canvas()
        self._refresh_size_label()


    def _discard_crop(self) -> None:
        """丢掉待定裁剪、选区弹回整幅；像素本来就没动过，**不产生撤销点**。

        Ctrl+Z / Ctrl+Y / 「还原」/ 参数页「重置选区」都走这里（见
        ``dialog_undo``：有待定裁剪时按键先退它，再按一次才动历史）。
        """
        had = getattr(self, "_pending_crop", None) is not None
        self._pending_crop = None
        self._pending_crop_offset = (0.0, 0.0)
        if had:
            self.canvas.reset_selection()
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
        # ⚠️ 擦除/扭曲**真的改像素**（擦除原地画、扭曲整幅重采样）：upright
        #    缓存作废，下次进「统一变换」要从当前画布重算（2026-10-11 脏位）
        self._content_pixels_dirty = True


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


    # ------------------------------------------------------------ 文字
    def _spawn_text_block(self, pos: QPointF) -> None:
        """文字工具点击落点 → 画布上生成文字块就地编辑（光标可见）。"""
        if self._image is None or self._image.isNull():
            return
        self.canvas.add_text_block(
            pos, self._text_size, QColor(self._text_color),
            self._text_family,
        )


    def _text_payload(self) -> list:
        """摘走画布上的非空文字块，返回可重放的 ``(pos,text,px,color,family)``。

        「完成」的**后台应用**要用两段式：关窗前先把块摘下来（画布立即干净、
        ``_commit_crop`` 拿到的是干净图），烘焙完成后在回调里重放到最终图上
        （普通路径由 :meth:`_commit_text_blocks` 一次做完，语义不变）。
        """
        if not hasattr(self, "canvas"):
            return []
        blocks = self.canvas.text_blocks()
        payload = [
            (b.pos(), b.toPlainText(), b.font().pixelSize(),
             QColor(b.defaultTextColor()), b.font().family())
            for b in blocks if b.toPlainText().strip()
        ]
        self.canvas.clear_text_blocks()
        return payload

    def _commit_text_blocks(self) -> None:
        """把画布上非空文字块写进图片（一个批次一个撤销点），然后清块。"""
        payload = self._text_payload()
        if not payload or self._image is None or self._image.isNull():
            return
        self._push_undo(STEP_TEXT)
        for pos, text, px, color, family in payload:
            self._image = draw_text(
                self._image, pos, text, px, color, family)
        self._content_pixels_dirty = True   # 文字改了像素：upright 缓存作废
        self.canvas.replace_image(self._image)

    def _apply_text_payload(self, payload: list, image: QImage) -> QImage:
        """把 :meth:`_text_payload` 摘走的文字块重放到 ``image`` 上。

        ⚠️ 只碰像素（``draw_text`` 纯 QPainter），不碰撤销栈与画布——调用
        方是「完成」的完成回调（弹窗已关、栈已无用），**普通路径不走这里**
        （那边走 :meth:`_commit_text_blocks`，带撤销点）。
        """
        if image is None or image.isNull():
            return image
        return _render_text_payload(image, payload)
