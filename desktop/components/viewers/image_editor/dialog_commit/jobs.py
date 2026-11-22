# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""工具提交的后台任务纯函数（从 ``dialog_commit.py`` 拆出）。"""
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
    # ⚠️ 判据拿**烘焙源**算（二值稿与否与这次怎么变换无关）；见下面的"那一刀"。
    #    成本：一张 8MP 图多一趟通道统计（~30ms），烘焙本身是 300ms 级。
    from desktop.components.viewers.image_zoom_dialog.io import binary_ink

    ink = binary_ink(original)
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
    # ---- 二值稿的「那一刀」（2026-11-15，与 ``services.imposition.compose_page``
    #      同一个口径：判据看烘焙源，阈值化落在结果上）----
    # 不压这一刀的话：83KB 的二值页旋转 0.5° 会写回 732KB（8.8x），**而且**
    # 写回后不再是二值稿 ⇒ 拼版合成与 PDF 排版那边的"二值化省体积"直接失效
    # （同页 194KB → 1.2MB）。判据天然挡住两类不该动的图：
    #   · 照片/灰度页：alpha 恒 255，不是二值稿；
    #   · 已经加过文字的页：文字抗锯齿让 alpha 出现中间值，判否。
    # ⚠️ 墨色也要一起归一（``ink``）：Qt 的合成是非预乘的，黑墨混"白色透明"
    #    会出**灰色的墨**，只压 alpha 只到 7.1x、归一到 1x 级。
    if ink is not None:
        from desktop.components.viewers.image_zoom_dialog.io import (
            harden_alpha_image,
        )

        image = harden_alpha_image(image, ink)
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
