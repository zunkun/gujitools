"""内容四角节点（quad）sidecar：「统一变换」的可编辑区域随图片落盘。

用户口径（2026-10-10）：图片四顶点 (p1..p4) 经一系列变换变成 (p11..p41)，
保存时把节点数据一起写到旁路文件；二次编辑时读回来，「统一变换」的可编辑
区域就是这四个顶点组成的四边形——**区域之外都是无意义的空白**。这样无论
旋转、保存、再编辑多少轮，编辑的主体永远是内容本身，而不是扩版后的画布。

表示：**(rect0, V)**

- ``rect0``：内容**摆正**（upright）时的矩形（编辑器工作画布，QRectF）；
- ``V``：upright 坐标 → 呈现坐标 的**纯**变换矩阵（不含落盘裁剪的原点
  平移）。落盘文件 = V×rect0 外框的裁剪，原点 o = :func:`quad_frame` 给出，
  所以从文件反推 upright 用 T = V⁻¹∘translate(o)（:func:`upright_image`）。

sidecar 路径 = ``<图片文件>.quad.json``。任何几何语义变化（裁剪、镜像、
clip/aspect 档、历史跳转）都整组作废——**宁可不恢复，也不能错恢复**。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QTransform

SIDECAR_SUFFIX = ".quad.json"
_VERSION = 1


def quad_path(path: str | Path) -> Path:
    """图片文件的 sidecar 路径：``<图片>.quad.json``（同目录伴随）。"""
    return Path(str(path) + SIDECAR_SUFFIX)


def quad_frame(xf: QTransform, rect: QRectF) -> tuple[int, int, int, int]:
    """V 把 upright 矩形映出去后的整数外框 ``(ox, oy, w, h)``。

    ⚠️ 取整口径必须与 ``geometry.transform_region`` 的变换部分**一致**
    （对变换后坐标用 ``round``，拖拽平移的浮点尾巴才不会凭空多出一列）。
    """
    corners = (rect.topLeft(), rect.topRight(),
               rect.bottomRight(), rect.bottomLeft())
    points = [xf.map(point) for point in corners]
    xs = [point.x() for point in points]
    ys = [point.y() for point in points]
    if not all(math.isfinite(value) for value in (*xs, *ys)):
        return 0, 0, max(1, int(rect.width())), max(1, int(rect.height()))
    x0, y0 = round(min(xs)), round(min(ys))
    x1, y1 = round(max(xs)), round(max(ys))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def read_quad(path: str | Path) -> tuple[QRectF, QTransform] | None:
    """读 sidecar，返回 ``(rect0, V)``；不存在/损坏/病态一律 ``None``。"""
    sidecar = quad_path(path)
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:                      # noqa: BLE001（不存在/坏 JSON）
        return None
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        return None
    rect_values = data.get("rect")
    matrix_values = data.get("matrix")
    if (not isinstance(rect_values, list) or len(rect_values) != 4
            or not isinstance(matrix_values, list)
            or len(matrix_values) != 9):
        return None
    try:
        values = [float(value) for value in matrix_values]
        if not all(math.isfinite(value) for value in values):
            return None
        xf = QTransform(*values)
        rect = QRectF(*[float(value) for value in rect_values])
    except Exception:                      # noqa: BLE001（字段类型不对）
        return None
    if rect.isEmpty() or not xf.isInvertible():
        return None
    return rect, xf


def write_quad(path: str | Path, rect: QRectF, xf: QTransform) -> None:
    """把 ``(rect0, V)`` 写进 sidecar；写失败静默（节点是增强，不是关键数据）。"""
    values = (xf.m11(), xf.m12(), xf.m13(), xf.m21(), xf.m22(), xf.m23(),
              xf.m31(), xf.m32(), xf.m33())
    data = {
        "version": _VERSION,
        "rect": [rect.x(), rect.y(), rect.width(), rect.height()],
        "matrix": list(values),
    }
    try:
        sidecar = quad_path(path)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(data), encoding="utf-8")
    except Exception:                      # noqa: BLE001（sidecar 不许绊倒保存）
        pass


def clear_quad(path: str | Path) -> None:
    """删 sidecar（几何语义已变，节点作废）；不存在即无事。"""
    try:
        quad_path(path).unlink(missing_ok=True)
    except Exception:                      # noqa: BLE001
        pass


def upright_image(image, rect: QRectF, xf: QTransform,
                  interpolation: str = "linear", progress=None,
                  origin_shift: tuple[float, float] = (0.0, 0.0)):
    """把落盘文件反变换回**摆正的内容**（upright，rect0 大小）。

    文件像素 p 对应 upright 坐标 u = V⁻¹(p + o)（o = :func:`quad_frame` 的
    原点），所以 source(file)→dest(upright) 的矩阵 = ``V⁻¹ * translate(o)``。

    ``origin_shift``＝**入口收紧偏移** t（``dialog.__init__`` 装图时裁掉的
    透明边宽）：传进来的 ``image`` 是收紧后的 PB1（文件平移 -t），而 o 以
    未收紧文件为基准，所以实际原点＝o + t。``rect`` 一律传 rect0 本身
    （upright 坐标）。反变换走 ``geometry.warp_region`` 的逐像素反向重采样
    （与烘焙同一条数学）；失败/退化返回 ``None``，调用方退回"无节点"模式。

    ⚠️⚠️ 矩阵是 ``shift * inverse``（**先平移、后逆旋转**，Qt 行向量
    "A*B＝先A后B"）：u = V⁻¹(p + o + t) 里的 ``+（o+t)`` 发生在 V⁻¹
    **内部**。旧版写成 ``inverse * shift``＝先逆旋转、后平移 ⇒ 摆正结果
    整体位移 o − V⁻¹(o)（45° 时实测绿块 4 角采样错 3 个、内容顶被推出
    rect0 裁掉——用户报的「PA1 顶部被削去一段」正是它）。
    """
    from .geometry import warp_region

    if image is None or image.isNull() or rect.isEmpty() or not xf.isInvertible():
        return None
    inverse, ok = xf.inverted()
    if not ok:
        return None
    ox, oy, _width, _height = quad_frame(xf, rect)
    shift = QTransform().translate(ox + origin_shift[0],
                                   oy + origin_shift[1])
    produced = warp_region(image, shift * inverse, interpolation, progress)
    if produced is None:
        return None
    warped, bx, by = produced
    x = int(round(rect.left())) - bx
    y = int(round(rect.top())) - by
    width = max(1, int(round(rect.width())))
    height = max(1, int(round(rect.height())))
    box = QRectF(x, y, width, height).toRect().intersected(warped.rect())
    if box.isEmpty():
        return None
    cropped = warped.copy(box)
    return None if cropped.isNull() else cropped


def sync_content_quad(path: str | Path, editor) -> None:
    """宿主覆盖图片文件后调用：按编辑器的内容节点状态写/清 sidecar。

    ``editor.content_state()`` 返回 ``(rect0, V)`` 或 None；sidecar 任何
    异常都**不许**绊倒图片保存本身（节点是增强，不是关键数据）。
    """
    try:
        state = editor.content_state()
    except Exception:                      # noqa: BLE001（替身/旧接口）
        state = None
    if state is None:
        clear_quad(path)
    else:
        write_quad(path, state[0], state[1])
