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
    QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QTransform,
)

from desktop.ui import theme as T
from utils.puppet_warp import puppet_warp_qimage

from .consts import DEFORM_PREVIEW_PIXELS

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


def bake_transform(image: QImage, rect: QRectF, xf: QTransform,
                   region: QImage, grow: bool = False) -> Any:
    """把「选区内容经 ``xf`` 变换」烘焙进图片。

    ⚠️ 返回类型刻意标成 ``Any``（**多形态返回值**，见下）：
    ``grow=False`` 返 ``QImage``、``grow=True`` 返 ``(QImage, (ox, oy))``。
    标成联合类型会让 ``image, _origin = bake_transform(..., grow=True)``
    这种解包报错（联合里含 QImage，QImage 不可迭代）。

    ``grow=False``（旧行为）：画布尺寸不变——先把**原区域**填白（内容被挪走/
    变形后空出来的地方），再在 ``xf`` 变换下把选区快照画回去。古籍整页白底，
    填白视觉上最干净。

    ``grow=True``（用户 2026-10-02）：「图片倾斜后一部分区域超出原本边界，
    现在会被截掉」——**不截**。最终画布 = 「原图边界 ∪ 变换后选区的外框」
    （:func:`transform_region`）。返回 ``(QImage, (ox, oy))``，``(ox, oy)`` =
    新画布左上角在原坐标系里的位置（可为负）。
    """
    if not grow:
        result = image.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(rect, QColor("#ffffff"))
        painter.setTransform(xf)
        painter.drawImage(rect, region)
        painter.end()
        return result
    # grow：新画布 = 原图 ∪ 变换后选区外框
    ox, oy, width, height = transform_region(image, rect, xf)
    # 底图：不透明图填白（与旧行为一致：古籍白纸），带 alpha 的图填透明
    transparent = image.hasAlphaChannel() and _image_has_alpha(image)
    base = QImage(width, height, QImage.Format.Format_ARGB32)
    base.fill(QColor(0, 0, 0, 0) if transparent else QColor("#ffffff"))
    painter = QPainter(base)
    painter.drawImage(-ox, -oy, image)
    painter.end()
    painter = QPainter(base)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    # 原选区在新画布里的位置：先填白（把被挪走的原内容擦掉），再画变换结果
    painter.translate(-ox, -oy)
    painter.fillRect(rect, QColor("#ffffff"))
    painter.setTransform(xf, True)
    painter.drawImage(rect, region)
    painter.end()
    return base, (ox, oy)


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


def bake_puppet(image: QImage, vertices_rest, vertices_moved,
                triangles, grow=False, progress=None) -> Any:
    """把「网格 ``vertices_rest`` → ``vertices_moved``」的形变烘焙进图片。

    ⚠️ 返回 ``Any``：多形态返回（``QImage`` / ``(QImage, (ox, oy))`` / ``None``），
    同 :func:`bake_transform` 的理由——标联合类型会让调用点的解包报错。

    与 :func:`bake_transform` 同口径：**没动过的网格区域**逐字节不动，只是
    这里不是仿射矩阵，而是 ARAP 三角网格逐像素重映射（PS 操控变形口径，
    见 ``utils.puppet_warp``）。
    ⚠️ **保留 alpha**：桌面侧编辑的常常是第三步产物「白底透明 PNG」，
    丢掉 alpha 会让整片透明背景变成不透明黑（用户 2026-10-01 报过）。

    ``grow=True``：图钉拖出原边界时不裁，画布放大，返回 ``(QImage, (ox, oy))``
    （用户 2026-10-02：「超出原本区域的不要截，最终结果按最后图片的范围」）。

    ``progress`` 透传（见 ``utils.puppet_warp.puppet_warp``）；被中止时
    返回 ``None``。
    """
    return puppet_warp_qimage(image, vertices_rest, vertices_moved, triangles,
                              grow=grow, progress=progress)


def cage_preview_scale(span_x: float, span_y: float,
                       on_screen: float = 1.0,
                       budget_pixels: float = DEFORM_PREVIEW_PIXELS) -> float:
    """拖动预览的降采样倍率：清晰度与成本的**取小**。

    两个约束：

    1. **清晰度**：``on_screen`` = 场景 1 单位对应多少**设备像素**
       （= 当前缩放 × dpr）。预览取到这个倍率时，预览图上的 1 像素正好
       落在屏幕 1 设备像素上——看着与原图一样清楚，再取大就是纯浪费。
    2. **成本**：处理面积不超过 ``budget_pixels``。

    缩到 1/3 看整页时清晰度约束直接给出 1/3：比按成本算还省 9 倍工作量，
    而且屏幕上看不出区别（这正是"预览"该有的样子）。

    ``budget_pixels`` 由调用方按场合给：拖动中给
    :data:`DEFORM_PREVIEW_PIXELS`（要跟手），松手后给
    :data:`DEFORM_PREVIEW_SETTLE_PIXELS`（停下来看结果，宁可慢一点也要清楚）。
    """
    area = max(1.0, float(span_x) * float(span_y))
    budget = math.sqrt(float(budget_pixels) / area)
    return max(1e-3, min(1.0, float(on_screen), budget))


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
