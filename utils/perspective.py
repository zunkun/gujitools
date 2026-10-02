# -*- coding: utf-8 -*-
"""四点透视校正（古籍拍摄角度 / 页面倾斜的快速摆正）。

## 口径（2026-10-01 用户定：独立入口）

「变形」（:mod:`utils.puppet_warp`）是**局部**微调（褶皱、小面积抽动），
本模块是**整页**的快速摆正：古籍翻拍常见的"梯形/倾斜"——书页四条边不是
矩形（拍摄角度导致），或整页微微斜着（装订线倾斜）。做法是拉四个角点，
把**源四边形**映到**目标矩形**（单应变换 / 透视变换），一次摆正整页。

- 与「变形」的分工：褶皱用变形（局部、图钉、逐点），页形/角度用本模块
  （整页、四个角、一次到位）。两者都落在同一套编辑器与撤销栈里。
- 与「变换」的分工：变换是**仿射**（平行线还是平行线），本模块是**透视**
  （平行线可以交于一点），这才是"角度"该有的数学。

## 算法：四点 DLT 解单应矩阵 + 逆向采样

1. **单应**：``H`` 3×3 使 ``dst ~ H·src``（齐次坐标，共 8 个自由度）。
   四点对应给出 8 个线性方程，解 8×8 线性组（:func:`homography`）。
2. **采样**：对**目标**矩形里每个像素 ``(x', y')``，用 ``H⁻¹`` 反算它来自
   源图的哪个点，双线性采样（**逆向映射**——正向映射会在目标上留空洞）。
   越界处填 ``fill``（白纸口径填白）。

numpy 延迟导入（桌面主进程 import 本模块时不加载）。
"""
from __future__ import annotations

import math

#: 越界填充（三通道）。古籍白纸口径填白。
FILL = (255, 255, 255)
#: 越界填充（四通道，白 + 透明）。白底透明 PNG 产物走这条。
FILL_CLEAR = (255, 255, 255, 0)
#: 单次光栅化的像素上限（内存护栏；超过就分块）。
BLOCK_PIXELS = 1 << 18
#: 判定"四边形退化"的最小面积（平方像素）——四点几乎共线时直接放弃。
MIN_AREA = 1e-3


def _numpy():
    """延迟导入 numpy（见模块文档：主进程 import 本模块时不加载）。"""
    import numpy as np

    return np


# ------------------------------------------------------------------ 单应
def homography(src, dst):
    """解四点对应的单应矩阵 ``H``（3×3，``dst ~ H·src``）。

    ``src``/``dst`` 各是 4 个 ``(x, y)``。用 DLT：每个对应点给两行方程，
    8 个方程解 8 个未知量（令 ``h33 = 1``）。四点共线（退化）时抛
    :class:`ValueError`——调用方应先在 UI 上拦住，而不是解出垃圾。
    """
    np = _numpy()
    src = np.asarray(src, dtype=np.float64).reshape(4, 2)
    dst = np.asarray(dst, dtype=np.float64).reshape(4, 2)
    A = np.zeros((8, 8), dtype=np.float64)
    b = np.zeros(8, dtype=np.float64)
    for i in range(4):
        x, y = src[i]
        u, v = dst[i]
        A[2 * i] = [x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y]
        A[2 * i + 1] = [0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y]
        b[2 * i] = u
        b[2 * i + 1] = v
    try:
        h = np.linalg.solve(A, b)
    except np.linalg.LinAlgError as exc:
        raise ValueError("四点退化（近似共线），无法解单应矩阵") from exc
    H = np.array([[h[0], h[1], h[2]],
                  [h[3], h[4], h[5]],
                  [h[6], h[7], 1.0]], dtype=np.float64)
    return H


def invert(H):
    """单应矩阵求逆（正变换 ``src→dst``，采样要用逆 ``dst→src``）。"""
    np = _numpy()
    return np.linalg.inv(np.asarray(H, dtype=np.float64))


def apply_homography(H, points):
    """把 ``H`` 作用到 ``points``（``(N, 2)`` 或 ``(2,)``），返回同形状。"""
    np = _numpy()
    H = np.asarray(H, dtype=np.float64)
    pts = np.asarray(points, dtype=np.float64)
    single = pts.ndim == 1
    pts = np.atleast_2d(pts)
    ones = np.ones((pts.shape[0], 1), dtype=np.float64)
    homo = np.hstack([pts, ones]) @ H.T
    w = homo[:, 2:3]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    out = homo[:, :2] / w
    return out[0] if single else out


def target_rect(src, *, mode: str = "bbox"):
    """给源四边形算一个"摆正后"的目标矩形（图片坐标，**像素闭区间**）。

    - ``mode="bbox"``：目标 = 源四边形的**轴对齐外接框**（尺寸与图幅同）；
    - ``mode="area"``：目标 = 与源四边形**等面积**的矩形，宽高比取源四边形
      对边平均长之比（摆正后不变形，内容不拉胖/压扁）。

    ⚠️ 四角是**像素坐标**（含端点），所以尺寸按 ``max - min + 1`` 取：
    四角正好压在图片四角（``(0,0)~(w-1,h-1)``）时目标尺寸 = ``(w, h)``，
    校正**逐字节还原原图**（自测钉死）。写成 ``max - min`` 会差 1 像素、
    反而把没动的整页缩掉一行一列。

    返回 ``(x0, y0, x1, y1)``（闭区间；尺寸 = ``x1-x0+1``）。
    """
    np = _numpy()
    src = np.asarray(src, dtype=np.float64).reshape(4, 2)
    x0, y0 = float(src[:, 0].min()), float(src[:, 1].min())
    x1, y1 = float(src[:, 0].max()), float(src[:, 1].max())
    if mode != "area":
        return (x0, y0, x1, y1)
    # 对边平均长 → 目标宽高（保持长宽比），再把尺寸缩到与源等面积
    top = float(np.hypot(*(src[1] - src[0])))
    bottom = float(np.hypot(*(src[3] - src[2])))
    left = float(np.hypot(*(src[3] - src[0])))
    right = float(np.hypot(*(src[2] - src[1])))
    width = 0.5 * (top + bottom)
    height = 0.5 * (left + right)
    if width < 1e-6 or height < 1e-6:
        return (x0, y0, x1, y1)
    return (x0, y0, x0 + width - 1.0, y0 + height - 1.0)


def quad_area(quad) -> float:
    """四边形（按序）的面积（shoelace，恒为非负）。"""
    np = _numpy()
    q = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    x = q[:, 0]
    y = q[:, 1]
    return float(0.5 * abs(
        float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))))


def quad_degenerate(quad) -> bool:
    """四边形是否退化（面积过小）——退化时不校正，直接放弃。"""
    try:
        return quad_area(quad) <= MIN_AREA
    except Exception:      # noqa: BLE001
        return True


# ------------------------------------------------------------------ 重采样
def _bilinear(src, x, y, fill):
    """按浮点坐标 ``x``/``y`` 双线性采样 ``src``(H,W,C)；越界处填 ``fill``。"""
    np = _numpy()
    height, width = src.shape[0], src.shape[1]
    channels = src.shape[2]
    tol = 1e-6
    ok = ((x >= -tol) & (x <= width - 1.0 + tol)
          & (y >= -tol) & (y <= height - 1.0 + tol))
    cx = np.clip(x, 0.0, width - 1.0)
    cy = np.clip(y, 0.0, height - 1.0)
    x0 = np.floor(cx).astype(np.intp)
    y0 = np.floor(cy).astype(np.intp)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    fx = (cx - x0).astype(np.float32)[:, None]
    fy = (cy - y0).astype(np.float32)[:, None]
    flat = src.reshape(-1, channels)
    row0 = y0 * width
    row1 = y1 * width
    c00 = np.take(flat, row0 + x0, axis=0).astype(np.float32)
    c10 = np.take(flat, row0 + x1, axis=0).astype(np.float32)
    c01 = np.take(flat, row1 + x0, axis=0).astype(np.float32)
    c11 = np.take(flat, row1 + x1, axis=0).astype(np.float32)
    top = c00 + (c10 - c00) * fx
    bottom = c01 + (c11 - c01) * fx
    result = top + (bottom - top) * fy
    if not ok.all():
        result[~ok] = np.asarray(fill, dtype=np.float32)
    return np.rint(result).astype(src.dtype)


def rectify(src, quad, *, out_size=None, mode: str = "bbox",
            fill=FILL, block: int = BLOCK_PIXELS):
    """把 ``src`` 里 ``quad`` 围的区域透视摆正到目标矩形，返回新数组。

    - ``src``：``(H, W)`` 或 ``(H, W, C)``。
    - ``quad``：源四边形四个角，顺序 ``[左上, 右上, 右下, 左下]``。
    - ``out_size``：目标尺寸 ``(宽度, 高度)``；缺省按 :func:`target_rect`
      的 ``mode`` 推。
    - 输出**尺寸 = 目标矩形尺寸**（就地摆正，不是原尺寸上的贴块）。
    """
    np = _numpy()
    src = np.asarray(src)
    if src.ndim not in (2, 3):
        raise ValueError(f"src 应为 2 或 3 维，实际 {src.ndim} 维")
    quad = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    if quad_degenerate(quad):
        raise ValueError("四边形退化（面积过小），无法校正")
    if out_size is None:
        x0, y0, x1, y1 = target_rect(quad, mode=mode)
        out_w = max(1, int(round(x1 - x0)) + 1)
        out_h = max(1, int(round(y1 - y0)) + 1)
    else:
        out_w = max(1, int(round(out_size[0])))
        out_h = max(1, int(round(out_size[1])))

    # 目标四角（左上→右上→右下→左下），坐标为**像素下标**（0 … out-1）
    target = np.array([[0.0, 0.0], [out_w - 1.0, 0.0],
                       [out_w - 1.0, out_h - 1.0], [0.0, out_h - 1.0]])
    H = homography(target, quad)          # 目标 → 源（直接拿逆映射）
    channels = 1 if src.ndim == 2 else src.shape[2]
    source = src.reshape(src.shape[0], src.shape[1], channels)
    clip_fill = np.asarray(fill, dtype=np.float32)

    out = np.empty((out_h, out_w, channels), dtype=src.dtype)
    # 分块光栅化（内存护栏）：逐块算源坐标并采样
    # ⚠️ 采样点用**像素下标**（不是 +0.5 的中心）：H 是按像素下标定的
    #    （四角 0…out-1 ↔ quad），所以下标 i 映到的源点就是"该取哪个像素"，
    #    恒等时 H=I ⇒ 源坐标 = i ⇒ _bilinear 取回原像素（逐字节还原）。
    step = max(1, int(math.sqrt(max(1, block))))
    for y_start in range(0, out_h, step):
        y_end = min(out_h, y_start + step)
        for x_start in range(0, out_w, step):
            x_end = min(out_w, x_start + step)
            xs = np.arange(x_start, x_end, dtype=np.float64)
            ys = np.arange(y_start, y_end, dtype=np.float64)
            gx, gy = np.meshgrid(xs, ys)
            pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
            mapped = apply_homography(H, pts)
            out[y_start:y_end, x_start:x_end] = _bilinear(
                source, mapped[:, 0], mapped[:, 1],
                clip_fill).reshape(y_end - y_start, x_end - x_start, channels)
    return out if channels > 1 else out[:, :, 0]


# ------------------------------------------------------------------ QImage
def qimage_to_rgba(image):
    """QImage → ``(H, W, 4)`` uint8 **RGBA**（保留 alpha，见 puppet_warp）。"""
    np = _numpy()
    from PySide6.QtGui import QImage

    source = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = source.width(), source.height()
    raw = np.frombuffer(source.constBits(), dtype=np.uint8,
                        count=source.sizeInBytes())
    raw = raw.reshape(height, source.bytesPerLine())[:, :width * 4]
    return raw.reshape(height, width, 4)[:, :, [2, 1, 0, 3]].copy()


def array_to_qimage(rgb):
    """``(H, W, 3|4)`` uint8 → QImage（ARGB32）；3 通道按不透明处理。"""
    np = _numpy()
    from PySide6.QtGui import QImage

    height, width = rgb.shape[0], rgb.shape[1]
    buffer = np.empty((height, width, 4), dtype=np.uint8)
    buffer[:, :, 0] = rgb[:, :, 2]
    buffer[:, :, 1] = rgb[:, :, 1]
    buffer[:, :, 2] = rgb[:, :, 0]
    buffer[:, :, 3] = 255 if rgb.shape[2] == 3 else rgb[:, :, 3]
    image = QImage(buffer.tobytes(), width, height, width * 4,
                   QImage.Format.Format_ARGB32)
    return image.copy()


def rectify_qimage(image, quad, *, out_size=None, mode: str = "bbox",
                   fill=None):
    """QImage 版 :func:`rectify`（保留 alpha；带 alpha 的图越界填透明白）。"""
    np = _numpy()
    rgba = qimage_to_rgba(image)
    opaque = bool(rgba[:, :, 3].min() == 255)
    if opaque:
        done = rectify(np.ascontiguousarray(rgba[:, :, :3]), quad,
                       out_size=out_size, mode=mode,
                       fill=FILL if fill is None else tuple(fill)[:3])
    else:
        done = rectify(rgba, quad, out_size=out_size, mode=mode,
                       fill=FILL_CLEAR if fill is None else fill)
    return array_to_qimage(np.ascontiguousarray(done))


def rectify_region(quad, width: int, height: int, *,
                   mode: str = "bbox"):
    """这次校正的目标矩形 ``(x0, y0, w, h)``（画布预览贴框用）。"""
    x0, y0, x1, y1 = target_rect(quad, mode=mode)
    w = max(1, int(round(x1 - x0)) + 1)
    h = max(1, int(round(y1 - y0)) + 1)
    return (int(round(x0)), int(round(y0)), w, h)


def quad_moved(src_quad, dst_quad, epsilon: float = 1e-6) -> bool:
    """四角是否真的动过（区分"全选没动"与"要校正"）。"""
    np = _numpy()
    a = np.asarray(src_quad, dtype=np.float64)
    b = np.asarray(dst_quad, dtype=np.float64)
    if a.shape != b.shape:
        return True
    return bool(np.max(np.abs(a - b)) > epsilon)
