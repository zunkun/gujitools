# -*- coding: utf-8 -*-
"""图片扭曲变换的像素级算法：**位移场累积 + 区域重采样**。

## 为什么不再"逐落点重采样"

GIMP 风格笔刷扭曲沿鼠标轨迹落下密集的笔刷。旧实现是**每个落点都把整个
笔刷圆盘重采样一遍**，而落点间距只有笔刷直径的 ~1/10 ⇒ 相邻圆盘重叠 ~90%，
同一片像素被反复重采样。实测（3000×4000 扫描件、笔刷 117、拖 30 秒）：

- 单次落点重采样 **9.7 ms**，一笔累计 ~3600 个落点 ⇒ 松手后要 **66 秒** 才出结果；
- 计算量正比于**拖动时长**，越拖越慢，最后把程序顶死（用户报的"崩溃"）。

## 现在：两段式

1. :func:`plan_stroke_stamps` 把鼠标轨迹重采样成等距落点（**唯一一份**，
   预览与提交共用）；
2. :class:`StrokeField` 把每个落点的**作用**（位移量 / 混合量）**累加**进场：
   纯加减法，实测 **0.08 ms/落点**，比逐点重采样快两个数量级；
3. :func:`render_field_region` 把场作用到笔划起点图上，**只重采样非零区域**
   并分块处理。

于是松手提交的成本只跟"这一笔覆盖了多大面积"有关，**与拖动时长解耦**：
拖 3 秒和拖 3 分钟一样快。同一次 30 秒拖动实测 66 s → **~1 s**。

## 语义

位移场是"逐落点重采样"在落点间距趋于 0 时的极限，也正是 GIMP/PS 变形笔刷
的标准做法：叠加的是**位移**，而不是反复重采样已经变形的像素——因此不会像
旧实现那样在软笔刷下越拖越"漂"。**单落点**没有叠加，结果与旧实现逐像素一致
（:func:`apply_distortion_stamp` 即"只含一个落点的笔划"）。

NumPy 是项目已有依赖，延迟到首次用到时导入，避免打开编辑器时增加启动开销。
"""
from __future__ import annotations

import math
from typing import Any

from PySide6.QtGui import QImage

#: 位移场的像素预算：场分辨率按此封顶。位移场是**平滑量**，大图上在场里
#: 降一点采样既不伤结果又省内存；预算以内的图 1:1，逐像素精确。
DISTORT_FIELD_PIXELS = 2_000_000

#: 一次重采样最多处理多少目标像素。分块是为了限制临时内存：立方插值每个
#: 目标像素要展开 16 个采样点，整幅 12 MP 一次算需要几百 MB。
RENDER_CHUNK_PIXELS = 400_000

#: 几何类模式（累加位移）；其余是混合类（累加混合量）。
_GEOMETRIC_MODES = ("move", "grow", "shrink", "swirl_cw", "swirl_ccw")
_MIX_MODES = ("smooth", "restore")
_CATMULL_OFFSETS = (-1, 0, 1, 2)


def _mode_kind(mode: str) -> str:
    """把持久化/未来模式收敛到已知行为：认不出的一律当 ``move``。"""
    if mode in _GEOMETRIC_MODES or mode in _MIX_MODES:
        return mode
    return "move"


def _pixel_view(image: QImage, np: Any, writable: bool) -> Any:
    """Return a strided ``(height, width, 4)`` view of an ARGB32 QImage."""
    bits = image.bits() if writable else image.constBits()
    raw = np.frombuffer(
        bits, dtype=np.uint8, count=image.bytesPerLine() * image.height())
    rows = raw.reshape(image.height(), image.bytesPerLine())
    return rows[:, :image.width() * 4].reshape(image.height(), image.width(), 4)


def plan_stroke_stamps(
    points: list[tuple[float, float]], size: int, spacing: int,
) -> list[tuple[float, float, float, float]]:
    """把整条鼠标轨迹重采样成等距落点，返回 ``[(cx, cy, dx, dy), ...]``。

    一次性入口；拖动过程中用的是 :class:`StrokeSampler`（同一个算法，
    落点一边拖一边攒，不必在松手时回放整条路径）。
    """
    if not points:
        return []
    sampler = StrokeSampler(size, spacing)
    stamps = sampler.start(points[0])
    for point in points[1:]:
        stamps.extend(sampler.extend(point))
    stamps.extend(sampler.flush())
    return stamps


class StrokeSampler:
    """把鼠标轨迹**增量**重采样成等距落点（间距 = 笔刷直径 × ``spacing%``）。

    第一条落点位移恒为 ``(0, 0)``：径向/旋涡类模式落笔就要生效（``move``
    因为位移为零自然没有影响）。``carry`` 跨段累计，所以分段喂和一次喂
    得到的落点序列完全一样。
    """

    __slots__ = ("step", "_carry", "_last", "_emitted")

    def __init__(self, size: int, spacing: int) -> None:
        self.step = max(1.0, size * spacing / 100.0)
        self._carry = 0.0
        self._last: tuple[float, float] | None = None
        self._emitted: tuple[float, float] | None = None

    def start(self, point: Any) -> list[tuple[float, float, float, float]]:
        """落笔：记录起点并给出第一个落点（零位移）。"""
        self._last = (float(point[0]), float(point[1]))
        self._emitted = self._last
        self._carry = 0.0
        return [(self._last[0], self._last[1], 0.0, 0.0)]

    def extend(self, point: Any) -> list[tuple[float, float, float, float]]:
        """接过鼠标新位置，返回这一段新产生的落点。

        ``_carry`` 是**距上一个落点已经走过的距离**（0 ≤ carry < step），
        跨段累计，所以分段喂和一次喂得到的落点序列完全一样。

        ⚠️ 这里的记账必须写成 ``carry = length - (needed - step)``：``needed``
        是本段内"下一个落点距段首的距离"。旧写法把已经用掉的旧 ``carry``
        又加回一次，于是 ``carry`` 随每一段**单调增长**；一旦 ``carry > step``，
        ``step - carry`` 变负、循环每段空转 ``carry/step`` 次，抛出成百个
        远在天边的假落点（实测拖 30 秒后每段 184 个、脏区 2000 图像 px）——
        这正是"拖得越久越卡、最后崩溃"的机制性原因。
        """
        if self._last is None:
            return self.start(point)
        start, end = self._last, (float(point[0]), float(point[1]))
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        out: list[tuple[float, float, float, float]] = []
        if length > 0.0:
            needed = self.step - self._carry   # 距段首多远落下一个点
            while needed <= length:
                ratio = needed / length
                cx = start[0] + dx * ratio
                cy = start[1] + dy * ratio
                assert self._emitted is not None  # start() 之后恒成立
                px, py = self._emitted
                out.append((cx, cy, cx - px, cy - py))
                self._emitted = (cx, cy)
                needed += self.step
            # 下一个落点还没到：记下已经走掉的那一截
            self._carry = length - (needed - self.step)
        self._last = end
        return out

    def flush(self) -> list[tuple[float, float, float, float]]:
        """收笔：把最后一个鼠标位置补成落点（没走出去就不补）。"""
        if self._last is None or self._emitted == self._last:
            return []
        assert self._emitted is not None
        px, py = self._emitted
        out = [(self._last[0], self._last[1],
                self._last[0] - px, self._last[1] - py)]
        self._emitted = self._last
        return out


class StrokeField:
    """一笔形变累积出来的场（图像坐标，可降采样）。

    - 几何模式累加 ``disp_x`` / ``disp_y``（采样点该往哪偏多少像素）；
    - 混合模式累加 ``mix``（0~1，把多少比例的"笔划起点内容"混回来）。

    ``x0/y0/x1/y1`` 是**非零区域**（图像坐标）：渲染只看这一块——这正是
    "提交成本与拖动时长解耦"的关键。
    """

    __slots__ = ("scale", "fw", "fh", "kind", "disp_x", "disp_y", "mix",
                 "x0", "y0", "x1", "y1")

    def __init__(self, width: int, height: int, mode: str, np: Any = None,
                 budget: int = DISTORT_FIELD_PIXELS) -> None:
        if np is None:                      # 延迟导入：打开编辑器时不为它买单
            import numpy as np
        self.scale = min(1.0, math.sqrt(budget / max(1.0, width * height)))
        self.fw = max(1, int(math.ceil(width * self.scale)))
        self.fh = max(1, int(math.ceil(height * self.scale)))
        self.kind = _mode_kind(mode)
        if self.kind in _MIX_MODES:
            self.disp_x = None
            self.disp_y = None
            self.mix = np.zeros((self.fh, self.fw), dtype=np.float32)
        else:
            self.disp_x = np.zeros((self.fh, self.fw), dtype=np.float32)
            self.disp_y = np.zeros((self.fh, self.fw), dtype=np.float32)
            self.mix = None
        self.x0 = self.y0 = math.inf
        self.x1 = self.y1 = -math.inf

    @property
    def empty(self) -> bool:
        """这一笔有没有真落过笔（没落过就不必渲染）。"""
        return self.x0 > self.x1

    def add_stamp(self, cx: float, cy: float, dx: float, dy: float,
                  size: int, hardness: int, strength: int) -> None:
        """把一个笔刷落点的作用累加进场（纯加减法，笔刷外补零）。"""
        import numpy as np

        radius = max(0.5, float(size) / 2.0)
        strength_ratio = max(0.0, min(100.0, float(strength))) / 100.0
        if strength_ratio <= 0.0:
            return
        scale = self.scale
        fx, fy = cx * scale, cy * scale
        rf = radius * scale
        i0 = max(0, int(math.floor(fx - rf - 1.0)))
        i1 = min(self.fw, int(math.ceil(fx + rf + 1.0)) + 1)
        j0 = max(0, int(math.floor(fy - rf - 1.0)))
        j1 = min(self.fh, int(math.ceil(fy + rf + 1.0)) + 1)
        if i1 <= i0 or j1 <= j0:
            return
        # 场像素 → 图像坐标偏移（相对落点中心）
        rx = (np.arange(i0, i1, dtype=np.float32) - fx) / scale
        ry = (np.arange(j0, j1, dtype=np.float32) - fy) / scale
        distance = np.sqrt(rx[None, :] ** 2 + ry[:, None] ** 2)
        if not bool((distance <= radius).any()):
            return

        hard_edge = max(0.0, min(1.0, float(hardness) / 100.0))
        inner = radius * hard_edge
        if inner >= radius - 1e-6:
            amount = np.full(distance.shape, strength_ratio, dtype=np.float32)
        else:
            t = np.clip((distance - inner) / max(1e-6, radius - inner), 0.0, 1.0)
            amount = ((1.0 - (t * t * (3.0 - 2.0 * t))) * strength_ratio
                      ).astype(np.float32)
        amount[distance > radius] = 0.0

        kind = self.kind
        if kind == "move":
            self.disp_x[j0:j1, i0:i1] -= float(dx) * amount
            self.disp_y[j0:j1, i0:i1] -= float(dy) * amount
        elif kind in ("grow", "shrink"):
            # 采样点向中心收 = 内容放大；向外扩 = 内容缩小
            sign = -0.35 if kind == "grow" else 0.35
            scaled = (sign * amount).astype(np.float32)
            self.disp_x[j0:j1, i0:i1] += rx[None, :] * scaled
            self.disp_y[j0:j1, i0:i1] += ry[:, None] * scaled
        elif kind in ("swirl_cw", "swirl_ccw"):
            sign = 1.0 if kind == "swirl_cw" else -1.0
            angle = (sign * amount * np.deg2rad(24.0)).astype(np.float32)
            cosine, sine = np.cos(angle), np.sin(angle)
            # 反向映射：图像顺时针转 = 从逆时针方向采样
            self.disp_x[j0:j1, i0:i1] += (rx[None, :] * (cosine - 1.0)
                                          + ry[:, None] * sine)
            self.disp_y[j0:j1, i0:i1] += (-rx[None, :] * sine
                                          + ry[:, None] * (cosine - 1.0))
        else:
            block = self.mix[j0:j1, i0:i1]
            np.add(block, amount, out=block)
            np.clip(block, 0.0, 1.0, out=block)

        self.x0 = min(self.x0, cx - radius)
        self.y0 = min(self.y0, cy - radius)
        self.x1 = max(self.x1, cx + radius)
        self.y1 = max(self.y1, cy + radius)

    def active_rect(self, width: int, height: int) -> tuple[int, int, int, int] | None:
        """非零区域换算回图像像素矩形（外扩 2 px 兜住跨边界的取样点）。"""
        if self.empty:
            return None
        left = max(0, int(math.floor(self.x0)) - 2)
        top = max(0, int(math.floor(self.y0)) - 2)
        right = min(width, int(math.ceil(self.x1)) + 3)
        bottom = min(height, int(math.ceil(self.y1)) + 3)
        if right <= left or bottom <= top:
            return None
        return (left, top, right, bottom)


def build_stroke_field(
    width: int, height: int, stamps: list[tuple[float, float, float, float]],
    size: int, hardness: int, strength: int, mode: str,
    budget: int = DISTORT_FIELD_PIXELS,
) -> StrokeField:
    """按等距落点建出整笔的形变场（纯计算，可安全放进工作线程）。"""
    import numpy as np

    field = StrokeField(width, height, mode, np, budget)
    for cx, cy, dx, dy in stamps:
        field.add_stamp(cx, cy, dx, dy, size, hardness, strength)
    return field


def _catmull_weights(t: Any, np: Any) -> Any:
    """Catmull-Rom (a = -0.5) 的 4 个权重，``t`` 形状 ``(*shape, 1)``。"""
    t2 = t * t
    t3 = t2 * t
    return np.stack((-0.5 * t + t2 - 0.5 * t3,
                     1.0 - 2.5 * t2 + 1.5 * t3,
                     0.5 * t + 2.0 * t2 - 1.5 * t3,
                     -0.5 * t2 + 0.5 * t3))


def _gather(flat: Any, win_w: int, win_h: int, x: Any, y: Any,
            interpolation: str, np: Any) -> Any:
    """从扁平化的 ``(N, 4)`` 缓冲里按浮点坐标取色。

    ``x`` / ``y`` 是**缓冲自己的像素坐标**（已含原点偏移）。索引展平成一维
    再取：二维 fancy-indexing 比一维慢一倍以上，而这里每个像素要取 4~16 个点。
    """
    x = np.clip(x, 0.0, win_w - 1.0)
    y = np.clip(y, 0.0, win_h - 1.0)
    if interpolation == "nearest":
        ix = np.minimum(np.floor(x + 0.5), win_w - 1).astype(np.int32)
        iy = np.minimum(np.floor(y + 0.5), win_h - 1).astype(np.int32)
        return flat[iy * win_w + ix].astype(np.float32)

    x0 = x.astype(np.int32)
    y0 = y.astype(np.int32)
    tx = (x - x0).astype(np.float32)[..., None]
    ty = (y - y0).astype(np.float32)[..., None]
    x1 = np.minimum(x0 + 1, win_w - 1)
    y1 = np.minimum(y0 + 1, win_h - 1)
    if interpolation == "linear":
        stacked = np.stack([y0 * win_w + x0, y0 * win_w + x1,
                            y1 * win_w + x0, y1 * win_w + x1])
        taps = flat[stacked].astype(np.float32)
        # 与旧实现逐字同形：乘法次序不同会带来 ±1 的舍入差
        one_x = 1.0 - tx
        one_y = 1.0 - ty
        top = taps[0] * one_x + taps[1] * tx
        bottom = taps[2] * one_x + taps[3] * tx
        return top * one_y + bottom * ty

    # 立方：x 方向 4 个权重先在行内合成，再按 y 的 4 个权重叠加（可分离）
    wx = _catmull_weights(tx, np).astype(np.float32)
    wy = _catmull_weights(ty, np).astype(np.float32)
    columns = []
    for ox in _CATMULL_OFFSETS:
        ix = np.clip(x0 + ox, 0, win_w - 1)
        columns.append(ix)
    result = None
    for index, oy in enumerate(_CATMULL_OFFSETS):
        iy = np.clip(y0 + oy, 0, win_h - 1) * win_w
        taps = flat[np.stack([iy + ix for ix in columns])].astype(np.float32)
        row = (taps * wx).sum(axis=0)
        term = row * wy[index]
        result = term if result is None else result + term
    return result


def _sample(field_pixels: Any, origin: tuple[float, float], scale: float,
            x: Any, y: Any, interpolation: str, np: Any) -> Any:
    """按**图像坐标** ``x/y`` 采样（缓冲原点 ``origin``、尺度 ``scale``）。"""
    height, width = field_pixels.shape[:2]
    flat = np.ascontiguousarray(field_pixels.reshape(-1, 4))
    return _gather(flat, width, height,
                   (x - origin[0]) * scale, (y - origin[1]) * scale,
                   interpolation, np)


def _field_grid(field: StrokeField, x: Any, y: Any,
                np: Any) -> tuple[Any, Any, Any, Any, Any, Any]:
    """把图像坐标 ``x`` / ``y`` 广播成同形，并给出场的双线性取样四角。"""
    # ⚠️ x / y 常常是「行向量」与「列向量」（分块渲染），必须先广播成同形，
    #    否则 ``fx`` 与 ``field.mix[iy, ix]`` 的形状对不上、直接抛错。
    gx, gy = np.broadcast_arrays(
        np.clip(x * field.scale, 0.0, field.fw - 1.0),
        np.clip(y * field.scale, 0.0, field.fh - 1.0))
    ix = gx.astype(np.int32)
    iy = gy.astype(np.int32)
    return gx, gy, ix, iy, np.minimum(ix + 1, field.fw - 1), \
        np.minimum(iy + 1, field.fh - 1)


def _field_disp(field: StrokeField, x: Any, y: Any, np: Any) -> tuple[Any, Any]:
    """在图像坐标上双线性采样位移场（图像单位）。"""
    if field.scale == 1.0:
        ix = np.clip(x.astype(np.int32), 0, field.fw - 1)
        iy = np.clip(y.astype(np.int32), 0, field.fh - 1)
        return field.disp_x[iy, ix], field.disp_y[iy, ix]
    gx, gy, ix, iy, ix1, iy1 = _field_grid(field, x, y, np)
    # 位移场是单通道 2D，权重不加尾轴（加了与 2D 取样结果广播不上）
    fx = gx - ix
    fy = gy - iy
    out = []
    for source in (field.disp_x, field.disp_y):
        top = source[iy, ix] + (source[iy, ix1] - source[iy, ix]) * fx
        bottom = source[iy1, ix] + (source[iy1, ix1] - source[iy1, ix]) * fx
        out.append(top + (bottom - top) * fy)
    return out[0], out[1]


def _field_mix(field: StrokeField, x: Any, y: Any, np: Any) -> Any:
    """在图像坐标上双线性采样混合量场。"""
    if field.scale == 1.0:
        ix = np.clip(x.astype(np.int32), 0, field.fw - 1)
        iy = np.clip(y.astype(np.int32), 0, field.fh - 1)
        return field.mix[iy, ix]
    gx, gy, ix, iy, ix1, iy1 = _field_grid(field, x, y, np)
    fx = gx - ix
    fy = gy - iy
    mix = field.mix
    top = mix[iy, ix] + (mix[iy, ix1] - mix[iy, ix]) * fx
    bottom = mix[iy1, ix] + (mix[iy1, ix1] - mix[iy1, ix]) * fx
    return top + (bottom - top) * fy


def render_field_region(
    dest_pixels: Any,
    dest_rect: tuple[int, int, int, int],
    src_pixels: Any,
    src_origin: tuple[float, float],
    field: StrokeField,
    scale: float,
    interpolation: str,
    np: Any,
    restore_pixels: Any = None,
    restore_origin: tuple[float, float] = (0.0, 0.0),
    progress: Any = None,
) -> None:
    """把场作用到 ``src_pixels``，只写 ``dest_pixels`` 的 ``dest_rect`` 区域。

    ``dest_rect`` 是**目标缓冲自己的像素下标**；``scale`` = 目标像素 / 图像
    像素（预览用缩小图 < 1，全分辨率提交 = 1）。``src_pixels`` 与目标同尺度，
    ``src_origin`` 是它左上角对应的图像坐标。只重采样非零区域，且按
    :data:`RENDER_CHUNK_PIXELS` 分块，临时内存有界。
    """
    left, top, right, bottom = dest_rect
    if right <= left or bottom <= top:
        return
    mix_only = field.kind in _MIX_MODES
    width = right - left
    rows_per_chunk = max(1, RENDER_CHUNK_PIXELS // max(1, width))
    total = bottom - top
    done = 0
    for row0 in range(top, bottom, rows_per_chunk):
        row1 = min(bottom, row0 + rows_per_chunk)
        xs = (np.arange(left, right, dtype=np.float32) / scale)[None, :]
        ys = (np.arange(row0, row1, dtype=np.float32) / scale)[:, None]
        shape = (row1 - row0, width)
        if mix_only:
            sample_x = np.broadcast_to(xs, shape)
            sample_y = np.broadcast_to(ys, shape)
        else:
            offset_x, offset_y = _field_disp(field, xs, ys, np)
            sample_x, sample_y = xs + offset_x, ys + offset_y
        out = _sample(src_pixels, src_origin, scale, sample_x, sample_y,
                      interpolation, np)
        if mix_only:
            mix = _field_mix(field, xs, ys, np)[..., None]
            if field.kind == "smooth":
                target = _blur(src_pixels, src_origin, scale, sample_x,
                               sample_y, np)
            elif restore_pixels is not None:
                target = _sample(restore_pixels, restore_origin, scale,
                                 sample_x, sample_y, "nearest", np)
            else:
                target = out
            out = out * (1.0 - mix) + target * mix
        block = dest_pixels[row0:row1, left:right]
        block[...] = np.clip(np.rint(out), 0.0, 255.0).astype(np.uint8)
        done = row1 - top
        if progress is not None and not progress(done, total):
            return


def _blur(src_pixels: Any, origin: tuple[float, float], scale: float,
          x: Any, y: Any, np: Any) -> Any:
    """``smooth`` 模式用的 3×3 加权均值（中心 4、四邻各 1，除以 8）。"""
    center = _sample(src_pixels, origin, scale, x, y, "nearest", np)
    total = center * 4.0
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        total = total + _sample(src_pixels, origin, scale, x + dx, y + dy,
                                "nearest", np)
    return total / 8.0


def render_stroke_field(
    image: QImage, field: StrokeField, interpolation: str,
    restore_image: QImage | None = None, progress: Any = None,
) -> QImage:
    """把场作用到 ``image`` 上，返回新图（非零区域之外逐像素不变）。

    纯计算入口，可安全放进工作线程；``progress(done, total)`` 返回 ``False``
    即中止（已写的分块保留，调用方按需丢弃）。
    """
    import numpy as np

    result = image.copy()
    rect = field.active_rect(image.width(), image.height())
    if rect is None:
        return result
    source = _pixel_view(image, np, writable=False)
    dest = _pixel_view(result, np, writable=True)
    restore = (_pixel_view(restore_image, np, writable=False)
               if restore_image is not None and not restore_image.isNull()
               else None)
    render_field_region(dest, rect, source, (0.0, 0.0), field, 1.0,
                        interpolation, np, restore_pixels=restore,
                        progress=progress)
    return result


def render_rect_into(
    image: QImage, origin: QImage, field: StrokeField, scale: float,
    rect: tuple[int, int, int, int], interpolation: str,
) -> None:
    """把 ``rect``（预览图自己的像素下标）按场重渲染进 ``image``（实时预览用）。

    ``image`` 是降采样的预览图、``origin`` 是笔划起点图（同尺度）。**每次都
    从起点图重算整片**，所以同一片区域被后续落点反复覆盖也不会累积出错
    ——旧实现"就地改预览像素"在重叠区域会越描越花。

    ⚠️ 按**精确脏矩形**渲染，不要改成"先凑成整块 128×128 瓦片再渲染"：
    一次落点的脏区通常只有 ~50×60 px，按瓦片渲染等于多算 10 倍（实测每帧
    10 ms 里有 9 ms 是这么浪费掉的）。
    """
    import numpy as np

    left, top, right, bottom = rect
    if right <= left or bottom <= top:
        return
    source = _pixel_view(origin, np, writable=False)
    dest = _pixel_view(image, np, writable=True)
    restore = source if field.kind == "restore" else None
    render_field_region(dest, (left, top, right, bottom), source, (0.0, 0.0),
                        field, scale, interpolation, np, restore_pixels=restore)


def apply_distortion_stamp(
    image: QImage,
    center_x: float,
    center_y: float,
    delta_x: float,
    delta_y: float,
    size: int,
    hardness: int,
    strength: int,
    mode: str,
    interpolation: str,
    restore_image: QImage | None = None,
) -> None:
    """原地应用一次笔刷采样（= 只含一个落点的笔划）。

    单落点没有叠加，结果与"逐落点重采样"的旧实现**逐像素一致**；只读写
    笔刷圆盘那一小块，因此可以在一笔里反复调用而不用整图拷贝。
    """
    if image.isNull() or size <= 0 or strength <= 0:
        return
    if image.format() != QImage.Format.Format_ARGB32:
        raise ValueError("扭曲画布必须使用 ARGB32 图像")

    import numpy as np

    width, height = image.width(), image.height()
    # 单落点：场就按 1:1 建，逐像素精确（预算 = 整图，避免降采样改变结果）
    field = build_stroke_field(
        width, height, [(float(center_x), float(center_y),
                         float(delta_x), float(delta_y))],
        size, hardness, strength, mode, budget=max(1, width * height))
    rect = field.active_rect(width, height)
    if rect is None:
        return
    radius = max(0.5, float(size) / 2.0)
    # 取样点最远偏出去多远（够小，只拷这一圈，不做整图拷贝）
    reach = max(radius * 1.65, radius + math.hypot(delta_x, delta_y) + 3.0)
    win_left = max(0, int(math.floor(rect[0] - reach)))
    win_top = max(0, int(math.floor(rect[1] - reach)))
    win_right = min(width, int(math.ceil(rect[2] + reach)))
    win_bottom = min(height, int(math.ceil(rect[3] + reach)))
    if win_right <= win_left or win_bottom <= win_top:
        return
    pixels = _pixel_view(image, np, writable=True)
    source = pixels[win_top:win_bottom, win_left:win_right].copy()
    restore = (_pixel_view(restore_image, np, writable=False)
               if restore_image is not None and not restore_image.isNull()
               else None)
    render_field_region(pixels, rect, source, (win_left, win_top), field, 1.0,
                        interpolation, np, restore_pixels=restore)


def _apply_distortion_path(
    image: QImage,
    points: list[tuple[float, float]],
    size: int,
    hardness: int,
    strength: int,
    spacing: int,
    mode: str,
    interpolation: str,
    restore_image: QImage | None = None,
    progress: Any = None,
) -> QImage | None:
    """按采样路径应用一笔扭曲（一次性入口）；纯计算，可放进工作线程。

    返回新图（非零区域之外与 ``image`` 逐像素相同）；被 ``progress`` 取消时
    返回 ``None``。拖动手感由画布侧的 :class:`StrokeSampler` 负责，这里是
    "手上只有一条现成轨迹"时的便捷入口。
    """
    if image.isNull() or not points:
        return image.copy()
    stamps = plan_stroke_stamps(points, size, spacing)
    field = build_stroke_field(image.width(), image.height(), stamps, size,
                               hardness, strength, mode)
    return render_stroke_field(image, field, interpolation, restore_image,
                               progress)


__all__ = [
    "DISTORT_FIELD_PIXELS",
    "RENDER_CHUNK_PIXELS",
    "StrokeField",
    "StrokeSampler",
    "apply_distortion_stamp",
    "build_stroke_field",
    "plan_stroke_stamps",
    "render_field_region",
    "render_rect_into",
    "render_stroke_field",
]
