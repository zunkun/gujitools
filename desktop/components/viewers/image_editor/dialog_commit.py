# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**工具提交**。

把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QTransform
from .bake import run_with_progress
from .content_quad import quad_frame, read_quad, upright_image
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


class CommitMixin(DialogHost):
    """把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。"""

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
        - 画布上画的始终是原图，选区外那 4 块半透明遮罩每帧按选区重算
          （``overlay._sync_overlay``）⇒ 向外拖时被变暗的区域立刻重新显露；
        - 真正的 ``copy()`` 推迟到 :meth:`_commit_crop`（切走裁剪工具 / 点
          「完成」），一次落定 = 一个撤销点。

        选区就是整幅（点一下不拖、拖回原位）时当成"没裁"，把待定清掉——
        不该白压一个空撤销步、也不该换图（换图会把视图 fit 一遍，闪一下）。
        """
        rect = self._selection()
        if rect is None:
            return  # 选区被拖成 <MIN_RECT_EDGE 的废框：不动任何东西
        if _same_rect(rect, self.canvas.image_rect()):
            self._discard_crop()
            return
        self._pending_crop = QRectF(rect)
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
        self._pending_crop = None
        # 选区已经夹在 image_rect() 里；toRect() 会向外取整，再与图像矩形求交
        # 兜住"取整后越界 1px"（否则 QImage.copy 拿到越界矩形会开天窗）。
        box = QRectF(rect).toRect().intersected(self._image.rect())
        if box.isEmpty():
            self.canvas.reset_selection()
            return
        self._push_undo(STEP_CROP)
        self._image = self._image.copy(box)
        self.canvas.set_image(self._image)   # 换图后选区重置为新图的整幅
        self._refresh_size_label()


    def _discard_crop(self) -> None:
        """丢掉待定裁剪、选区弹回整幅；像素本来就没动过，**不产生撤销点**。

        Ctrl+Z / Ctrl+Y / 「还原」/ 参数页「重置选区」都走这里（见
        ``dialog_undo``：有待定裁剪时按键先退它，再按一次才动历史）。
        """
        had = getattr(self, "_pending_crop", None) is not None
        self._pending_crop = None
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

        懒读取（sidecar 很小，纯 JSON 微秒级）：宿主构造**后**才回填
        :attr:`source_path`，所以读这件事推迟到第一次进变换工具。反变换
        大图像烘焙一样走后台线程 + 进度框；失败/无数据就 consume（本会话
        退回"整幅矩形"框架，入口收紧仍保证主体是内容）。
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
        target = rect0.width() * rect0.height()
        upright = getattr(self, "_content_upright", None)
        if upright is None:
            params = {"image": self._image, "rect": QRectF(rect0),
                      "xf": QTransform(xf), "origin_shift": (tx, ty),
                      "interpolation": INTERPOLATION_DEFAULT}
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
                self._content_clear()         # 反变换失败：宁可不恢复
                return
            self._content_upright = upright
        # ⚠️ 种子矩阵＝**画布系**：sidecar 的 V 是文件系（文件＝V×rect0 外框
        #    裁剪，外框左上角 o＝quad_frame），入口收紧又把文件平移了 -t，
        #    所以内容四边形在 PB1 里 ＝ V×rect0 −(o+t)——挂到画布的矩阵要
        #    补上这两个平移，浮层/框/手柄才与已烘焙的内容严丝合缝。
        ox, oy, _fw, _fh = quad_frame(xf, rect0)
        seed = (QTransform(xf)
                * QTransform().translate(-(ox + tx), -(oy + ty)))
        self._content_seed = seed
        canvas.consume_content_restore()
        canvas.begin_restored_transform(seed, upright)
        self._content_restored = True

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
            return
        self._content_clear()             # 链路断了：宁可不恢复

    def _commit_transform(self, label: str = STEP_TRANSFORM,
                          force: bool = False) -> bool:
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
            self._content_exit_restore()  # 恢复会话没拖就走：画布本来就是原样
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
        if target <= DISTORT_SYNC_RENDER_PIXELS:
            result = compose_transform(original, rect, xf, region, grow=grow,
                                       interpolation=interpolation)
            image = result[0] if grow else result
            if clipping == "aspect":
                image = center_crop_aspect(
                    image, original.width(), original.height())
        else:
            image = self._bake_transform_async(rect, xf, region, grow,
                                               clipping, interpolation,
                                               original)
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
        # ⚠️ ``refit=False``：画布会长大一点，但**不要**重新适应窗口——否则
        #    每次松手都把图缩小一档，反复旋转就是"越转越小"（用户报障）。
        self.canvas.set_image(self._image, refit=False)
        self._refresh_size_label()
        self._content_after_bake(rect, xf, clipping, original)
        return True

    def _bake_transform_async(self, rect: QRectF, xf, region, grow: bool,
                              clipping: str, interpolation: str,
                              original=None):
        """把整幅烘焙丢进后台线程 + 进度框；返回新图，用户取消时返回 ``None``。

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
