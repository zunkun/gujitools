# -*- coding: utf-8 -*-
"""图片编辑器的**纯几何/变换数学**与图像合成原语（无 Qt 部件依赖）。

从 ``image_editor.py`` 拆出（2026-10-07）。这里只做像素与矩阵运算，
不碰 QWidget / 画布状态，因此可被任何宿主复用（含后台线程）。
"""
from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QLineF, QPointF, QRectF
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPolygonF,
    QTransform,
)

from desktop.ui import theme as T

#: 一次重采样最多产出多少目标像素；超出（病态投影 / 超大放大）退回 QPainter，
#: 免得一块临时数组把内存吃穿。
WARP_MAX_PIXELS = 40_000_000

#: "病态投影"的坐标上限。**近**共线的透视四点（把 tl 拖到 br 附近、或拖成
#: 自交的蝴蝶结）会让 ``quadToQuad`` 给出一个"可逆但把内容放大百万倍"的矩阵：
#: 外框坐标实测到 1e9、面积 4.8e17。任何坐标到这个量级就一律当垃圾扔掉——
#: 拿去建 ``QImage(w, h)`` 会直接崩（用户 2026-10-09 报的 OverflowError）。
ABSURD_COORD = 1e8

#: 重采样分块的目标像素预算（每种插值每个目标像素要展开 4~16 个采样点，
#: 分块是为了限制临时内存：整幅 12 MP 一次算需要几百 MB）。
_WARP_CHUNK_PIXELS = 400_000

# ------------------------------------------------------------------ 纯逻辑
def clamp_rect(rect: QRectF, bounds: QRectF) -> QRectF:
    """把矩形夹进边界内（先平移、超界再缩边）；空矩形原样返回。"""
    if rect.isNull():
        return rect
    rect = rect.normalized()
    width = min(rect.width(), bounds.width())
    height = min(rect.height(), bounds.height())
    x = max(bounds.left(), min(rect.left(), bounds.right() - width))
    y = max(bounds.top(), min(rect.top(), bounds.bottom() - height))
    return QRectF(x, y, width, height)


# ------------------------------------------------------------------ 变换数学
# ⚠️ PySide6 的 QTransform 复合约定（离屏实测）：
#   * ``(A * B).map(p)`` = **先 A 后 B**（与 QPainter 的调用顺序一致）；
#   * 链式 builder ``translate(c).rotate(a).translate(-c)`` 恰好是"绕 c 旋转"；
#   * ``shear(sh, sv)``：x' = x + sh·y，y' = y + sv·x；rotate 正角度 = 顺时针
#     （y 向下坐标系）。下面的组合全按这套语义写，并有自测盯着。
def rotate_about(point: QPointF, degrees: float) -> QTransform:
    """绕 ``point`` 旋转 ``degrees``（正=顺时针）。"""
    t = QTransform()
    t.translate(point.x(), point.y())
    t.rotate(degrees)
    t.translate(-point.x(), -point.y())
    return t


def scale_about(point: QPointF, sx: float, sy: float) -> QTransform:
    """绕 ``point`` 缩放（sx/sy 为 0 会退化，调用方保证非零）。"""
    t = QTransform()
    t.translate(point.x(), point.y())
    t.scale(sx, sy)
    t.translate(-point.x(), -point.y())
    return t


def shear_about(point: QPointF, sh: float, sv: float) -> QTransform:
    """绕 ``point`` 切变：水平 sh（x 随 y 斜切）、垂直 sv（y 随 x 斜切）。"""
    t = QTransform()
    t.translate(point.x(), point.y())
    t.shear(sh, sv)
    t.translate(-point.x(), -point.y())
    return t


def quad_to_quad_transform(src, dst) -> QTransform | None:
    """``src`` 四点 → ``dst`` 四点的**投影**变换（同序、顺时针逆时针都行）。

    统一变换的"透视"手柄靠它：把当前四边形整体映到"挪了一个角"的新四边形。
    四点退化（共线 / 重合）时 ``quadToQuad`` 失败，这里返回 ``None``——
    调用方把这一步当"没发生"，不要留下一个把内容甩到无穷远的矩阵。
    """
    if len(src) != 4 or len(dst) != 4:
        return None
    try:
        xf = QTransform.quadToQuad(
            QPolygonF([QPointF(p) for p in src]),
            QPolygonF([QPointF(p) for p in dst]),
        )
    except Exception:      # noqa: BLE001（Qt 在不同版本上要么返回 None 要么抛）
        return None
    if xf is None or not xf.isInvertible():
        return None
    return xf


def flip_transform(rect: QRectF, horizontal: bool) -> QTransform:
    """绕 ``rect`` 中心做水平/垂直翻转（统一变换面板的「翻转」）。"""
    center = rect.normalized().center()
    if horizontal:
        return scale_about(center, -1.0, 1.0)
    return scale_about(center, 1.0, -1.0)


def quad_point(corners, u: float, v: float) -> QPointF:
    """四边形的双线性插值点；``corners`` = ``(tl, tr, br, bl)``（或同序四元组）。

    ``u/v`` ∈ [0, 1]：``(0,0)`` = tl、``(1,1)`` = br。参考线、角点与
    "框内/框外"判定都要按**变形后的四边形**插值，不能拿原矩形算。
    """
    if isinstance(corners, dict):
        tl, tr = corners["tl"], corners["tr"]
        br, bl = corners["br"], corners["bl"]
    else:
        tl, tr, br, bl = corners
    top = QPointF(tl.x() + (tr.x() - tl.x()) * u,
                  tl.y() + (tr.y() - tl.y()) * u)
    bottom = QPointF(bl.x() + (br.x() - bl.x()) * u,
                     bl.y() + (br.y() - bl.y()) * u)
    return QPointF(top.x() + (bottom.x() - top.x()) * v,
                   top.y() + (bottom.y() - top.y()) * v)


def _resample_plan(xf: QTransform, interpolation: str):
    """把插值档位翻译成 ``(采样算法, [(dx, dy, weight), ...])``。

    * ``nearest`` / ``linear`` / ``cubic``：一趟，偏移为 0；
    * ``nohalo``（默认档，对应用户报的"缩小后发糊/有噪点"）：**放大用立方**，
      **缩小按比例叠加 N×N 子采样再平均**——这正是 GIMP 的 NoHalo/LoHalo
      相对线性插值的增益：目标像素覆盖了源图多个像素时，只取一个采样点
      必然产生摩尔纹与"光晕"，平均掉就干净了。

    返回的偏移表是**目标空间**的（把目标像素的足迹摊开），权重和为 1。
    """
    if interpolation == "nearest":
        return "nearest", ((0.0, 0.0, 1.0),)
    if interpolation != "nohalo":
        return interpolation, ((0.0, 0.0, 1.0),)
    scale = _linear_scale(xf)
    if scale >= 0.999:
        return "cubic", ((0.0, 0.0, 1.0),)
    steps = min(3, max(2, int(math.ceil(1.0 / scale))))
    weight = 1.0 / (steps * steps)
    offsets = [(index + 0.5) / steps - 0.5 for index in range(steps)]
    return "linear", tuple(
        (dx, dy, weight) for dy in offsets for dx in offsets)


def _linear_scale(xf: QTransform) -> float:
    """变换在"面积"意义上的平均线性倍率（|det| 的平方根）。"""
    det = xf.m11() * xf.m22() - xf.m12() * xf.m21()
    if not math.isfinite(det) or abs(det) < 1e-12:
        return 1.0
    return math.sqrt(abs(det))


def mapped_bounds(xf: QTransform, rect: QRectF,
                  limit: int = WARP_MAX_PIXELS) -> tuple[int, int, int, int] | None:
    """``xf`` 把 ``rect`` 这张矩形映出去后，落在哪个整数外框里。

    ``rect`` 必须用**与 ``xf`` 同域**的坐标（``xf`` 的输入系）。返回
    ``(x0, y0, x1, y1)``（**含两端**，与 :func:`warp_region` 里那段同口径）。

    ⚠️⚠️ **返回 ``None`` 表示"这个外框根本不能用"，调用方一律"宁可不画"**：
    坐标非有限（投影在 w→0 处把角甩到无穷远）、坐标大到天文数字
    （``ABSURD_COORD``；近共线投影实测到 1e9）、或外框像素数超过 ``limit``。

    ⚠️ 这是**唯一**该拿来做"尺寸闸门"的判据：这是本项目里崩溃的直接来源——
    2026-10-09 用户把透视角拖到对角附近，``warp_region`` 已经拒绝了（超 40 MP），
    但 :func:`warp_placement` 的 QPainter 兜底没挡，``QImage(2.18e9, 1.49e9)``
    直接 OverflowError（另一路 ``compose_transform(grow=True)`` 的
    ``QImage(width, height)`` 同病）。**别在各处另写一遍 min/max/floor/ceil**。
    """
    points = (rect.topLeft(), rect.topRight(),
              rect.bottomRight(), rect.bottomLeft())
    xs, ys = [], []
    for point in points:
        mapped = xf.map(point)
        xs.append(mapped.x())
        ys.append(mapped.y())
    if not all(math.isfinite(value) for value in (*xs, *ys)):
        return None                        # 病态投影（w→0）把角甩到无穷远
    if max(abs(value) for value in (*xs, *ys)) > ABSURD_COORD:
        return None                        # 近共线投影：天文数字
    x0, y0 = int(math.floor(min(xs))), int(math.floor(min(ys)))
    x1, y1 = int(math.ceil(max(xs))), int(math.ceil(max(ys)))
    if (x1 - x0 + 1) * (y1 - y0 + 1) > limit:
        return None
    return x0, y0, x1, y1


def warp_region(region: QImage, xf: QTransform, interpolation: str = "linear",
                progress=None) -> tuple[QImage, int, int] | None:
    """把 ``region`` 按 ``xf`` 重采样成一张新图（``xf``：区域坐标 → 输出坐标）。

    返回 ``(新图, x, y)``，``(x, y)`` = 新图左上角在**输出坐标系**里的位置。
    取不到 numpy / 变换退化 / 目标尺寸离谱时返回 ``None``，调用方退回
    QPainter 平滑路径（旧行为）。

    ``progress(done, total)`` 是可选的进度回调（后台烘焙用）；返回 ``False``
    表示用户取消，本函数**立刻返回 ``None``**（半成品不返回，免得算出一张
    缺一块的图）。逐行分块算，所以取消能在一帧之内生效。

    做法是**反向映射**：对每个目标像素求它在源块里的浮点坐标再采样。所以
    透视（投影）变换也天然支持——QPainter 的投影绘制是近似的，而这里
    逐像素精确，烘焙结果与预览框的角点严格对应。
    """
    if region is None or region.isNull() or not xf.isInvertible():
        return None
    try:                                   # 延迟导入：numpy 与采样器是项目既有件
        import numpy as np
        from .distortion import _gather, _pixel_view
    except Exception:                      # noqa: BLE001（缺 numpy ⇒ 走 QPainter）
        return None
    source = (
        region if region.format() == QImage.Format.Format_ARGB32
        else region.convertToFormat(QImage.Format.Format_ARGB32)
    )
    width, height = source.width(), source.height()
    bounds = mapped_bounds(xf, QRectF(0, 0, width, height))
    if bounds is None:
        return None                        # 病态投影 / 外框太大：不画
    x0, y0, x1, y1 = bounds
    out_w, out_h = x1 - x0 + 1, y1 - y0 + 1
    inverse, ok = xf.inverted()
    if not ok:
        return None
    m11, m12, m13 = inverse.m11(), inverse.m12(), inverse.m13()
    m21, m22, m23 = inverse.m21(), inverse.m22(), inverse.m23()
    m31, m32, m33 = inverse.m31(), inverse.m32(), inverse.m33()
    flat = np.ascontiguousarray(_pixel_view(source, np, False).reshape(-1, 4))
    out = np.zeros((out_h, out_w, 4), dtype=np.uint8)
    mode, passes = _resample_plan(xf, interpolation)
    chunk = max(1, min(out_h, _WARP_CHUNK_PIXELS // max(1, out_w)))
    columns = np.arange(out_w, dtype=np.float32)[None, :]
    for row0 in range(0, out_h, chunk):
        if progress is not None and not progress(row0, out_h):
            return None                    # 用户取消：宁可不给结果
        row1 = min(out_h, row0 + chunk)
        rows = row1 - row0
        gx = columns + x0
        gy = np.arange(row0, row1, dtype=np.float32)[:, None] + y0
        total = np.zeros((rows, out_w, 4), dtype=np.float32)
        covered = np.zeros((rows, out_w), dtype=bool)
        with np.errstate(divide="ignore", invalid="ignore"):
            for dx, dy, weight in passes:
                px, py = gx + dx, gy + dy
                den = m13 * px + m23 * py + m33
                sx = (m11 * px + m21 * py + m31) / den
                sy = (m12 * px + m22 * py + m32) / den
                valid = ((sx >= -0.5) & (sx <= width - 0.5)
                         & (sy >= -0.5) & (sy <= height - 0.5))
                if not valid.any():
                    continue
                total[valid] += weight * _gather(
                    flat, width, height, sx[valid], sy[valid], mode, np)
                covered |= valid
        if covered.any():
            out[row0:row1][covered] = np.clip(
                np.rint(total[covered]), 0, 255).astype(np.uint8)
    return (QImage(out.tobytes(), out_w, out_h, out_w * 4,
                   QImage.Format.Format_ARGB32),
            x0, y0)


def center_crop_aspect(image: QImage, width: int, height: int) -> QImage:
    """把 ``image`` **居中**裁成 ``width:height`` 这个长宽比（居中不动内容）。

    统一变换面板的「裁剪到原比例」用它：先按「调整」让画布跟着内容长，再拿
    原始尺寸的长宽比居中裁回来——结果尺寸可能比原图大也可能小，但**比例
    不变**（GIMP 的 "Crop to original aspect ratio" 同口径）。

    ``width/height`` 非法或图是空的时原样返回（宁可不动，也不裁出 0 像素）。
    """
    if image is None or image.isNull() or width <= 0 or height <= 0:
        return image
    source_w, source_h = image.width(), image.height()
    if source_w <= 0 or source_h <= 0:
        return image
    target = width / height
    if source_w / source_h > target:            # 偏宽 ⇒ 裁左右
        new_w = max(1, int(round(source_h * target)))
        new_w = min(new_w, source_w)
        return image.copy((source_w - new_w) // 2, 0, new_w, source_h)
    new_h = max(1, int(round(source_w / target)))   # 偏高 ⇒ 裁上下
    new_h = min(new_h, source_h)
    return image.copy(0, (source_h - new_h) // 2, source_w, new_h)


def warp_placement(region: QImage, xf: QTransform, interpolation: str,
                   progress=None) -> tuple[QImage, int, int] | None:
    """``region`` 按 ``xf`` 重采样（``xf``：区域局部坐标 → 输出坐标）。

    返回 ``(新图, x0, y0)``，``(x0, y0)`` = 新图左上角在**输出坐标系**里的位置；
    **用户取消返回 ``None``**（宁可整步作废，也不交付一张缺一块的图）。

    ⚠️ 这是烘焙的**唯一**像素入口（预览与提交共用同一条数学）。以前还有一条
    "``interpolation="smooth"`` 就直接 ``painter.setTransform(xf)`` +
    ``drawImage(rect, region)``"的 QPainter 兜底路径，实测**内容整体漂移约
    10px**：``QPainter.drawImage(rect, image)`` 在带变换的 painter 下并不等价
    于 ``map(rect)``（平移量会被加回去、旋转会绕错原点），而且它只支持仿射、
    投影（透视）会被 Qt 近似掉。现在统一走逐像素反向重采样，结果与画布上的
    预览框严格一致。

    只有"取不到 numpy"这一种极端情况才退回 QPainter 平滑档——那时只保证
    看得见，不保证与框严格对齐。⚠️ "病态矩阵 / 外框离谱"**不算**这一种：
    退回去的那条路自己也要先过 :func:`mapped_bounds`，过不了就返回空图。
    """
    if region is None or region.isNull():
        return (QImage(), 0, 0)
    # ⚠️ 必须分清"用户取消"与"取不到 numpy"这两种 ``warp_region`` 返回 None
    #    的情形：前者绝不能退回 QPainter 硬画（那等于无视取消），后者才可以。
    #    用一个显式标记记下取消发生过。
    cancelled = False

    def _tracked(done: int, total: int) -> bool:
        nonlocal cancelled
        if progress is None:
            return True
        if not progress(done, total):
            cancelled = True
            return False
        return True

    warped = warp_region(region, xf, interpolation,
                         _tracked if progress is not None else None)
    if warped is not None:
        return warped
    if cancelled:
        return None
    # ⚠️⚠️ 兜底路径**必须自己再挡一次病态输入**：``warp_region`` 拒绝的原因有
    #    四种（缺 numpy / 不可逆 / 坐标非有限 / 外框超 40 MP），下面这一段只该
    #    接住**第一种**。旧版没有这道守卫，于是"透视拖到对角附近"那种近共线
    #    投影（外框 1e9）一路走到 ``QImage(width, height)`` ⇒ OverflowError
    #    崩掉整个编辑器（用户 2026-10-09 的报障）。
    if not xf.isInvertible():
        return (QImage(), 0, 0)
    bounds = mapped_bounds(xf, QRectF(0, 0, region.width(), region.height()))
    if bounds is None:
        return (QImage(), 0, 0)             # 病态投影 / 离谱尺寸：宁可什么都不画
    x0, y0, x1, y1 = bounds
    width, height = x1 - x0 + 1, y1 - y0 + 1
    out = QImage(width, height, QImage.Format.Format_ARGB32)
    out.fill(QColor(0, 0, 0, 0))
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.translate(-x0, -y0)
    painter.setTransform(xf, True)
    painter.drawImage(QPointF(0, 0), region)
    painter.end()
    return out, x0, y0


def _empty_fill(image: QImage) -> QColor:
    """变换后**空出来的地方**填什么色（预览与烘焙共用的唯一口径）。

    - 源图**真有透明像素**（去底色产物）：填**透明**——旋转/平移空出的地方
      必须保持透明，不能染白（用户 2026-10-10 报障："保存落地的图片会增加
      白色背景色，这个不需要"）。画布预览 2026-10-09 起就把选区擦透明了，
      烘焙不同步的话就是"预览透明、存盘变白"。
    - 源图全不透明（扫描件）：填白——外扩区没有内容可透，存 JPEG 时透明
      会被压成黑底，白更接近"纸"的预期。
    """
    if image.hasAlphaChannel() and _image_has_alpha(image):
        return QColor(0, 0, 0, 0)
    return QColor("#ffffff")


def _trim_transparent_edges(base: QImage):
    """把 grow 底图四周**纯透明**的边裁掉，返回 ``(裁后图, dx, dy)``。

    为什么要有这一步（2026-10-10 用户报障「旋转保存再旋转保存，图片越来
    越大，内容占比越来越小」）：``transform_region`` 的外框是按**画布矩形
    四角**映射算的。第一次旋转 45°，外框恰好＝内容的完整外框（没有多余边）；
    可这张图存盘后二次编辑，编辑主体变成了 A1（含四角空白），再转 45° 时
    外框按 A1 的四角又扩 √2 倍——空白越滚越大，内容占比每转一次缩一截。
    把结果裁到**非透明像素的真实外框**，存盘的图每一步都＝内容本身的
    外框（用户口径里的 B1），下次编辑的主体天然就是内容，不需要任何
    旁路的"内容区域元数据"。

    只在**透明档**（源图真有 alpha）做：不透明扫描件的四周白边可能就是
    "纸"的内容，按非白裁会切掉真内容。缺 numpy 时返回 ``None`` 跳过
    （宁可不裁，不能错裁）。
    """
    try:
        import numpy as np
        from .distortion import _pixel_view
    except Exception:                      # noqa: BLE001（缺 numpy ⇒ 不裁）
        return None
    source = (base if base.format() == QImage.Format.Format_ARGB32
              else base.convertToFormat(QImage.Format.Format_ARGB32))
    if source.isNull() or source.width() <= 2 or source.height() <= 2:
        return None
    alpha = _pixel_view(source, np, False)[..., 3]
    rows = np.nonzero((alpha > 0).any(axis=1))[0]
    cols = np.nonzero((alpha > 0).any(axis=0))[0]
    if rows.size == 0 or cols.size == 0:
        return None                        # 全透明：没有"内容"可对齐，不裁
    y0, y1 = int(rows[0]), int(rows[-1])
    x0, x1 = int(cols[0]), int(cols[-1])
    if x0 == 0 and y0 == 0 and x1 == source.width() - 1 \
            and y1 == source.height() - 1:
        return source, 0, 0                # 四边都贴着内容：无需裁
    return (source.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1), x0, y0)


def compose_transform(image: QImage, rect: QRectF, xf: QTransform,
                      region: QImage, grow: bool = False,
                      interpolation: str = "smooth",
                      progress=None) -> Any:
    """把「选区内容经 ``xf`` 变换」合成进图片——**预览与烘焙共用的唯一实现**。

    ⚠️ 返回类型刻意标成 ``Any``（**多形态返回值**，见下）：
    ``grow=False`` 返 ``QImage``、``grow=True`` 返 ``(QImage, (ox, oy))``。
    标成联合类型会让 ``image, _origin = compose_transform(..., grow=True)``
    这种解包报错（联合里含 QImage，QImage 不可迭代）。

    ``interpolation`` 是统一变换面板的「插值」档位（``nohalo`` / ``linear`` /
    ``cubic`` / ``nearest`` / ``smooth``），交给 :func:`warp_placement` 的
    逐像素反向重采样档位。

    ``progress(done, total)``（可选）用于**后台烘焙**报进度；返回 ``False``
    表示用户取消，这时本函数返回 ``None``（整步作废，绝不交付半张图）。
    预览调用不传它（前端只要快）。

    ``grow=False``：画布尺寸不变——先把**原区域**填"空色"（内容被搬走了；
    源图有真透明就填透明、否则填白，见 :func:`_empty_fill`），再把变换后的
    选区内容画到它该在的位置。

    ``grow=True``：**不截**超出的部分——新画布 = 「变换后内容的完整外框」
    （见 :func:`transform_region`）。返回 ``(QImage, (ox, oy))``，
    ``(ox, oy)`` = 新画布左上角在原坐标系里的位置。

    这套几何是画布预览的**同一份**：``_ensure_transform_preview`` 直接调它
    拿底图，所以"松手之后图变成什么样"在按下拖动的第一帧就已经定死了。
    """
    # ⚠️ `xf` 的输入是**选区局部坐标**：先平移到选区在图片里的位置。这里用
    #    `T * xf`（先平移到选区原位、再套累计矩阵）而不是把 rect 塞进
    #    drawImage——后者正是上面那段漂移 bug 的来源。
    placed = QTransform().translate(rect.x(), rect.y()) * xf
    warped = warp_placement(region, placed, interpolation, progress)
    if warped is None:
        return None                         # 用户取消
    warped, wx, wy = warped
    # ⚠️ 空处填色只有一种口径（_empty_fill）：源图真有透明像素 ⇒ 透明，
    #    否则白。下面三处（clip 的原位、grow 的底图与原位）必须同一色，
    #    否则透明源图会被某一条白填底染回白背景（2026-10-10 报障）。
    empty = _empty_fill(image)
    # ⚠️ 透明色在 SourceOver 下 fillRect 是**空操作**（alpha 0 盖不住任何
    #    东西）：clip 档的底图是 ``image.copy()``，原位残留的旧内容必须真
    #    清掉（否则内容搬走了原地还留个 ghost）——透明档要切 Clear 模式。
    clearing = empty.alpha() == 0
    if not grow:
        result = image.copy()
        painter = QPainter(result)
        if clearing:
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(rect, empty)
        if clearing:
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawImage(QPointF(wx, wy), warped)
        painter.end()
        return result
    # grow：新画布 = 内容外框 ∪ 原图边界（原选区已被搬走、填空色，不再算进
    # 外框，否则整体平移会凭空多出一条填色边）。
    # ⚠️ drawImage 画的是**整张原图**（含选区里的旧内容）：白档靠下面的
    #    fillRect 盖掉它；透明档 SourceOver 盖不住 ⇒ 同样切 Clear 真清除，
    #    否则内容搬走了原地还留个 ghost（2026-10-10）。
    ox, oy, width, height = transform_region(image, rect, placed)
    base = QImage(width, height, QImage.Format.Format_ARGB32)
    base.fill(empty)
    painter = QPainter(base)
    painter.drawImage(QPointF(-ox, -oy), image)
    if clearing:
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
    painter.fillRect(rect.translated(-ox, -oy), empty)
    if clearing:
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.drawImage(QPointF(wx - ox, wy - oy), warped)
    painter.end()
    # ⚠️ 透明档**内容收紧**：外框是按画布矩形四角算的，二次编辑再旋转时
    #    会把上一轮的四角空白也当内容扩进来（越转越大，见
    #    :func:`_trim_transparent_edges`）。裁到非透明像素的真实外框，
    #    原点平移量必须跟着裁剪量走（origin 语义 = 新画布左上角在原坐标系）。
    if clearing:
        trimmed = _trim_transparent_edges(base)
        if trimmed is not None:
            base, tx, ty = trimmed
            ox, oy = ox + tx, oy + ty
    return base, (ox, oy)


def bake_transform(image: QImage, rect: QRectF, xf: QTransform,
                   region: QImage, grow: bool = False,
                   interpolation: str = "smooth") -> Any:
    """旧名保留：等价于 :func:`compose_transform`（对外 API 不变）。"""
    return compose_transform(image, rect, xf, region, grow, interpolation)
def _image_has_alpha(image: QImage) -> bool:
    """源图是否**真有透明像素**（决定 grow 底图填透明还是填白）。见画布同款。

    不能用 ``hasAlphaChannel()`` 单判——ARGB32 格式"有通道"不代表真有透明
    像素（整幅全不透明时填透明会在 Windows 上显成黑）。
    """
    if image.isNull():
        return False
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    raw = bytes(rgba.constBits())
    step = rgba.width() * 4
    for y in range(rgba.height()):
        row = raw[y * step:(y + 1) * step]
        if row[3::4].count(255) != rgba.width():
            return True
    return False


def transform_region(image: QImage, rect: QRectF, xf: QTransform):
    """``grow`` 模式的目标画布：``(ox, oy, width, height)``。

    用户口径（2026-10-02）：「一切以新图为准，新图什么样就什么样，老图不要了」
    ——最终图 = **变换后内容的完整外框**，而不是"原图 ∪ 变换后"。

    内容 = ①变换后的选区（仿射把矩形映成平行四边形，落在四角外接框内）
    ∪ ②**选区之外**原本就留着的那部分原图（选区整体移走时这块为空）。
    选区原位被移走、内容被填白，所以**不再算进外框**——若按"原图边界"取并，
    整体平移就会凭空多出一条填白边（用户要的正是把它去掉）。
    """
    corners = [rect.topLeft(), rect.topRight(),
               rect.bottomRight(), rect.bottomLeft()]
    mapped = [xf.map(point) for point in corners]
    xs = [point.x() for point in mapped]
    ys = [point.y() for point in mapped]
    # ⚠️ 透视（投影）变换在 w→0 时会把角甩到无穷远，近共线时又会给出百万倍
    #    放大的"可逆"矩阵（外框实测 1e9）——两种都让画布尺寸变成天文数字。
    #    统一过 :func:`mapped_bounds` 这道闸，过不了就退回"原图边界"，
    #    让这一步不产生新画布（旧版只查非有限，漏了后者 ⇒ ``QImage(1e9, …)``
    #    溢出崩溃）。
    if mapped_bounds(xf, rect) is None:
        return 0, 0, max(1, image.width()), max(1, image.height())
    # ⚠️ 用 `round` 而不是 `floor/ceil`：拖拽平移量是**浮点**（鼠标到像素的
    # 映射会带小数点，实测 −30.048465），floor(−30.048)=−31、ceil(169.952)
    # =170 ⇒ 凭空多出 1px 画布。四舍五入到最近像素才是"内容真正占了几列"，
    # 因为渲染时半像素会被夹到边界上、不会多出可分辨的一列。
    x0 = round(min(xs))
    y0 = round(min(ys))
    x1 = round(max(xs))
    y1 = round(max(ys))
    # 选区之外的原图内容仍存在（部分选区变换时）：把"原图 − 选中矩形"的
    # 四块残余内容并进来。注意：残余是**未变换的原图矩形**，按内容真实占用
    # 取整——用 `floor/ceil` 向外扩一列，原图的边界列才不会被切掉；这里
    # 不用 `round`（`round` 是给变换后坐标用的，见上）。
    sel = rect.normalized()
    for bx0, by0, bx1, by1 in (
        (0.0, 0.0, sel.left(), image.height()),        # 左残条
        (sel.right(), 0.0, image.width(), image.height()),  # 右残条
        (sel.left(), 0.0, sel.right(), sel.top()),     # 上残条
        (sel.left(), sel.bottom(), sel.right(), image.height()),  # 下残条
    ):
        if bx1 - bx0 <= 0 or by1 - by0 <= 0:
            continue
        x0 = min(x0, math.floor(bx0))
        y0 = min(y0, math.floor(by0))
        x1 = max(x1, math.ceil(bx1))
        y1 = max(y1, math.ceil(by1))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def draw_text(image: QImage, pos: QPointF, text: str, px: int,
              color: QColor, family: str | None = None) -> QImage:
    """在 ``pos``（文字块左上角）画文字（可多行，行距 1.25 倍）；空文本原样返回。

    ``family`` 缺省用主题字体；文字块（就地编辑）烧进图片时传块当时的
    family，保证"所见即所得"。
    """
    if not text.strip():
        return image
    result = image.copy()
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont(family or T.FONT_FAMILY)
    font.setPixelSize(max(1, int(px)))
    painter.setFont(font)
    painter.setPen(QPen(color))
    metrics = QFontMetrics(font)
    step = max(1, int(px * 1.25))
    for row, line_text in enumerate(text.splitlines() or [""]):
        # drawText(QPointF) 的 y 是**基线**：pos 约定为文字块左上角，
        # 每行要往下挪一个 ascent（多行再叠 1.25 倍行距）
        baseline = pos + QPointF(0, row * step + metrics.ascent())
        painter.drawText(baseline, line_text)
    painter.end()
    return result


def _project_on_segment(p: QPointF, a: QPointF, b: QPointF):
    """``p`` 在线段 ``ab`` 上的**投影点**与参数 ``t``（0=起点、1=终点）。"""
    ab = b - a
    length_sq = ab.x() * ab.x() + ab.y() * ab.y()
    if length_sq < 1e-12:
        return (QPointF(a), 0.0)
    t = max(0.0, min(1.0, (
        (p.x() - a.x()) * ab.x() + (p.y() - a.y()) * ab.y()) / length_sq))
    return (a + ab * t, t)


def _segment_hit(p: QPointF, a: QPointF, b: QPointF) -> tuple[float, float]:
    """点到线段的**最短距离**与**落点参数** ``t``（0=起点、1=终点）。"""
    point, t = _project_on_segment(p, a, b)
    return (QLineF(p, point).length(), t)


def _dist_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
    """点到线段的最短距离（视图像素口径的边命中带用）。"""
    return _segment_hit(p, a, b)[0]
