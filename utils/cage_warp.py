# -*- coding: utf-8 -*-
"""变换笼（cage transform）：拖笼上的把手 → **局部**光滑形变。

口径（2026-10-01 用户定）
------------------------
- 笼是一圈**把手**（节点）。拖哪个把手，只有它**附近**的像素跟着走，
  远处的像素**逐字节一动不动**。
- 影响随距离平滑衰减到 0（"像扯弹簧"：作用点变化大，远端几乎不动），
  而且是 **C² 光滑**的——不会沿笼边拉出生硬的折痕。
- 向内拖＝压缩，向外拖＝拉伸，两个方向都行。
- ⚠️ 与 GIMP 原版的差别：GIMP 的笼是"**笼内整体一起走**"（全局 Green
  Coordinates / MVC），拖一个角会把整笼带动、从其余顶点拉出折痕。本项目
  按用户要求改成**局部**影响（2026-10-01 用户反馈："选择一点向内拖会从
  其他节点生出折线……应该尽可能影响局部，尽量少影响距离远的节点"）。

算法：紧支撑 RBF 位移场
----------------------
把每个**被拖过的**把手当作一个约束点：目标位置 ``mᵢ`` 处的像素要取源位置
``hᵢ`` 的像素，即位移 ``qᵢ = hᵢ − mᵢ``。取 **Wendland** 核

    φ(r) = (1 − r)⁴ (4r + 1)   (r < 1)，  核外恒为 0

插值：``s(p) = p + Σⱼ wⱼ φ(|p − mⱼ| / R)``，``w`` 由 ``Φw = q`` 解出
（``Φᵢⱼ = φ(|mᵢ − mⱼ|/R)``，把手数 ≤ 十几个，小线性方程组微秒级）。

四条性质是"手感"与"可断言"的关键，都有自测钉死：

1. **精确插值**：``s(mᵢ) = hᵢ``——把手处的像素严格跟着把手走。
2. **紧支撑 ⇒ 局部**：``|p − mⱼ| ≥ R`` 时 ``φ ≡ 0``，于是 ``s(p) = p``，
   影响半径外**逐字节等于原图**。这就是"拖一个点只动附近"的来源。
3. **只有被拖过的把手进方程组**：没动过的把手（含"在笼线上新加的点"）
   不构成约束，所以**加点仍然逐字节中性**。
4. **恒等即原图**：所有把手都没动 ⇒ 直接 return 原数组的副本。

``R``（影响半径）由 :func:`influence_radius` 决定：取用户给的半径，再抬到
**保证位移场不折叠**的下限——位移场梯度量级是 ``|φ'|max·Σ|wⱼ| / R``，超过 1
就会自交（实测表现为"漩涡"）。半径过小 + 拖得过远必然自交，这条下限把
它挡在门外；越界的请求会被**自动放宽半径**，宁可影响大一点也不能出乱纹。

性能
----
与全局 MVC 不同，**工作区域只有影响半径那么大**：整页 4000×3000 的图拖一个
把手，也只算 ``(2R)²`` 那一小块。瓶颈始终是**逐像素重采样**，不是求场
（稀格求场恒在毫秒级）——实测拆解（本机 2026-10-01，整页 4000×3000）：

=================  ==========
源坐标场（稀格）      <5ms
场采样到全分辨率     1.2s
双线性取样           1.9s
**合计**            **3.1s**
=================  ==========

所以桌面侧仍然**降分辨率出预览**（``CAGE_PREVIEW_SCALE``）、只在落地时走
全分辨率；而局部影响让"要算的面积"从整幅缩到半径平方，预览几乎必然跟手。

几何约定
--------
- 全部用**图片像素坐标**，y 向下（与 QImage 一致）；像素中心取整数坐标。
- ``cage_src`` = 把手原位，``cage_dst`` = 把手当前位置；两序列**一一对应**，
  闭合顺序，顺/逆时针都可以。

⚠️ numpy 一律**延迟导入**：桌面主进程要 import 本模块（只为拿函数引用），
启动路径不能因此背上 numpy 的加载成本。
"""
from __future__ import annotations

import math

#: 采样越界时填的底色（不透明源图：古籍白纸）
FILL = (255, 255, 255)
#: 采样越界时填的底色（**带透明的源图**：白 + 全透明）。
#: ⚠️ 桌面侧编辑的常常是第三步的"白底透明 PNG"产物：这里若填不透明色，
#:    整片背景会变成一块实心色（用户 2026-10-01 报的"图片变成黑色"）。
FILL_CLEAR = (255, 255, 255, 0)
#: 源坐标场的采样格点数上限（见模块文档「性能」）。
FIELD_MAX = 40000
#: 每批处理的像素上限：不分批的话大图一次要吃掉几 GB。
BLOCK_PIXELS = 1 << 18
#: 判定"把手动过 / 两点重合"的距离阈值（图片像素）。
COINCIDENT = 1e-6
#: Wendland 核梯度的上界：``|φ'(r)|`` 在 ``r = 1/4`` 处取到 ``135/64 ≈ 2.11``。
#: 位移场梯度量级 ``≤ |φ'|max·Σ|wⱼ| / R``——拿它当作"会不会自交"的判据。
_WENDLAND_GRAD = 135.0 / 64.0
#: 影响半径的**起始**下限倍率（再按上面的梯度判据迭代抬高）。
_RADIUS_FLOOR = 2.5


def _numpy():
    """延迟导入 numpy（见模块文档：主进程 import 本模块时不加载）。"""
    import numpy as np

    return np


# ------------------------------------------------------------------ 笼的构造
def perimeter_cage(rect, per_side: int = 2):
    """矩形 ``rect`` = ``(x0, y0, x1, y1)`` → **沿周长均匀取样**的闭合把手序列。

    ``per_side`` = 每条边分成几段。1 → 只有四个角；2 → 四角 + 四边中点（8 点）。

    沿周长取样是为了得到一圈"绳子"上均匀的**结**：把手只在周长上，拖动
    某个结时它的邻居距离一致，手感均匀。内部再多铺点也不会算错（算法只用
    把手位置，不看多边形形状），只是没必要。
    """
    x0, y0, x1, y1 = (float(rect[0]), float(rect[1]),
                      float(rect[2]), float(rect[3]))
    per_side = max(1, int(per_side))
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    points: list[tuple[float, float]] = []
    for index in range(4):
        ax, ay = corners[index]
        bx, by = corners[(index + 1) % 4]
        for step in range(per_side):
            t = step / per_side
            points.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    return points


def _lattice(start: float, stop_exclusive: float, step: int):
    """``[start, stop_exclusive)`` 上步长 ``step`` 的格点，**保证覆盖到右端**。

    返回长度 ≥ 2 的一维数组（末点不小于 ``stop_exclusive - 1``）。
    """
    np = _numpy()
    last = float(stop_exclusive) - 1.0
    if last <= start:
        return np.array([start, start + 1.0], dtype=np.float64)
    count = int(math.ceil((last - start) / step)) + 1
    grid = start + np.arange(count, dtype=np.float64) * step
    if grid[-1] > last:
        grid[-1] = last
    if grid.size < 2:
        grid = np.array([start, last], dtype=np.float64)
    return grid


# ------------------------------------------------------------------ 数学
def wendland(r):
    """Wendland **C²** 紧支撑核：``r < 1`` 时 ``(1−r)⁴(4r+1)``，否则 ``0``。

    选它而不是高斯：高斯处处非零（影响永远不为 0，"局部"就成了近似），
    紧支撑才让"半径外逐字节不动"成为**可断言**的性质；而多项式形式没有
    指数运算，在几十万格点上比高斯还便宜。
    """
    np = _numpy()
    r = np.asarray(r, dtype=np.float64)
    out = np.zeros(r.shape, dtype=np.float64)
    inside = r < 1.0
    if inside.any():
        t = 1.0 - r[inside]
        out[inside] = t ** 4 * (4.0 * r[inside] + 1.0)
    return out


def _solve_rbf(centres, shift, radius: float):
    """解 ``Φw = shift``（``Φᵢⱼ = φ(|mᵢ−mⱼ|/R)``），返回每个把手的分量权重。"""
    np = _numpy()
    gap = np.linalg.norm(centres[:, None, :] - centres[None, :, :], axis=-1)
    return np.linalg.solve(wendland(gap / radius), shift)


def influence_radius(cage_src, cage_dst, influence=None) -> float:
    """当前这组拖动需要的**影响半径**（用户下限 + 防自交下限），没动过则 0。

    单独暴露出来是为了让画布知道"该重算多大一块"——省得为了拿一个数字
    把整张图跑一遍。
    """
    handles = moved_handles(cage_src, cage_dst, influence)
    return 0.0 if handles is None else handles[2]


def moved_handles(cage_src, cage_dst, influence=None):
    """把"被拖过的把手"整理成 ``(把手当前位置, RBF 权重, 影响半径)``。

    没动过（或两个笼形状不一致）→ ``None``。**只有真的动过的把手**进方程
    组，所以"在笼线上加一个点"不会改变形变（自测有这个断言）。
    """
    np = _numpy()
    home = np.asarray(cage_src, dtype=np.float64)
    current = np.asarray(cage_dst, dtype=np.float64)
    if home.ndim != 2 or home.shape[1] != 2:
        raise ValueError(f"把手形状应为 (n, 2)，实际 {home.shape}")
    if home.shape != current.shape:
        raise ValueError(f"两个笼的把手数必须一致：{home.shape} vs {current.shape}")
    shift = home - current          # 目标像素 m 要取源像素 h
    moved = np.linalg.norm(shift, axis=1) > COINCIDENT
    if not moved.any():
        return None
    centres = current[moved]
    wanted = shift[moved]

    reach = float(np.linalg.norm(wanted, axis=1).max())
    radius = max(float(influence or 0.0), _RADIUS_FLOOR * reach)
    for _ in range(8):
        weights = _solve_rbf(centres, wanted, radius)
        need = _WENDLAND_GRAD * float(np.linalg.norm(weights, axis=1).sum())
        if need <= radius:
            break
        radius = need * 1.1
    else:
        # 迭代到上限还没收敛（把手挤在一起又拖得很远）：按最后的半径重解，
        # 保证返回的权重与半径自洽。
        weights = _solve_rbf(centres, wanted, radius)
    return centres, weights, radius


def _deform_region(centres, radius: float, width: int, height: int):
    """影响盘的并集外接框，夹进画布；返回 ``(x0, y0, x1, y1)``（开区间右端）。

    完全落在画布外 → ``(0, 0, 0, 0)``。
    """
    xs = centres[:, 0]
    ys = centres[:, 1]
    x0 = max(0, int(math.floor(float(xs.min()) - radius)))
    y0 = max(0, int(math.floor(float(ys.min()) - radius)))
    x1 = min(int(width), int(math.ceil(float(xs.max()) + radius)) + 1)
    y1 = min(int(height), int(math.ceil(float(ys.max()) + radius)) + 1)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0, 0)
    return (x0, y0, x1, y1)


def warp_region(cage_src, cage_dst, influence=None, *, width: int, height: int):
    """这次拖动**实际会改动的矩形区域**（图片坐标，开区间右端）。

    画布侧的预览浮层就贴在这个框上（框外逐字节等于原图，直接透出底图即可，
    既不浪费也不会有接缝）。纯 Python + numpy 基础运算，不加载重型依赖。
    """
    handles = moved_handles(cage_src, cage_dst, influence)
    if handles is None:
        return (0, 0, 0, 0)
    return _deform_region(handles[0], handles[2], width, height)


def cage_moved(cage_src, cage_dst, epsilon: float = 1e-6) -> bool:
    """两个笼是否有实质差别（区分"真变形"与"动过手但没挪"）。"""
    np = _numpy()
    a = np.asarray(cage_src, dtype=np.float64)
    b = np.asarray(cage_dst, dtype=np.float64)
    if a.shape != b.shape:
        return True
    return bool(np.max(np.abs(a - b)) > epsilon)


def _lattice_field(centres, weights, radius: float, grid_x, grid_y):
    """稀格上的**位移场** ``(dx, dy)``，形状各 ``(len(grid_y), len(grid_x))``。"""
    np = _numpy()
    mesh_x, mesh_y = np.meshgrid(grid_x, grid_y)
    lattice = np.stack([mesh_x.ravel(), mesh_y.ravel()], axis=1)
    gap = np.linalg.norm(lattice[:, None, :] - centres[None, :, :], axis=-1)
    disp = wendland(gap / radius) @ weights
    shape = (len(grid_y), len(grid_x))
    return disp[:, 0].reshape(shape), disp[:, 1].reshape(shape)


def _sample_lattice(field, x0: float, y0: float, step: int, xs, ys):
    """把二维稀格场 ``field``(ny, nx) 双线性插值到 ``ys × xs`` 网格。

    ``field`` 的格点是 ``x0 + i*step`` / ``y0 + j*step``（见 :func:`_lattice`，
    末点被拉到区间右端，所以坐标映射后一定落在 ``[0, 边数-1]`` 内）。
    """
    np = _numpy()
    ny, nx = field.shape
    position_x = (xs - x0) / step
    position_y = (ys - y0) / step
    ix = np.clip(np.floor(position_x).astype(np.intp), 0, nx - 2)
    iy = np.clip(np.floor(position_y).astype(np.intp), 0, ny - 2)
    fx = (position_x - ix).astype(np.float32)[None, :]
    fy = (position_y - iy).astype(np.float32)[:, None]
    # 走扁平索引（``iy*nx + ix``）而不是 ``field[iy][:, ix]``：链式高级索引会
    # 先物化一个 (行, nx) 的中间数组，整页下是白白多一倍内存带宽。
    flat = field.reshape(-1)
    base = iy * nx
    c00 = flat[base[:, None] + ix]
    c10 = flat[base[:, None] + ix + 1]
    base1 = (iy + 1) * nx
    c01 = flat[base1[:, None] + ix]
    c11 = flat[base1[:, None] + ix + 1]
    top = c00 + (c10 - c00) * fx
    bottom = c01 + (c11 - c01) * fx
    return top + (bottom - top) * fy


def _bilinear(src, x, y, fill):
    """按浮点坐标 ``x``/``y`` 双线性采样 ``src``(H,W,C)；越界处填 ``fill``。

    走**扁平索引**（``y*W + x``）而不是 ``src[y0, x0]``：后者在 numpy 里是
    「两个索引数组」的高级索引，会退化到很慢的分支。
    """
    np = _numpy()
    height, width = src.shape[0], src.shape[1]
    channels = src.shape[2]
    # ⚠️ 越界判定必须留**数值噪声级**的容差：权重是浮点的，贴着边界的采样点
    #    常算成 39.000000000025，硬判 "> height-1" 会把它当图外填白——整行
    #    冒出白条（恒等笼都还原不了原图）。1e-6 像素肉眼不可见；真的被拖出
    #    画布的采样点偏差远大于它，照样填白。
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
    # ⚠️ 四个角必须先 astype(float32) 再做差：``uint8 - uint8`` 在 numpy 里
    #    仍是 uint8，会**按 256 回绕**（实测最大错 255/255）。
    # 用 ``np.take`` 而不是 ``flat[idx]``：语义相同，但实测快 ~15%
    # （整页 12M 像素下 2.0s → 1.7s），而这一步是整个形变的瓶颈。
    c00 = np.take(flat, row0 + x0, axis=0).astype(np.float32)
    c10 = np.take(flat, row0 + x1, axis=0).astype(np.float32)
    c01 = np.take(flat, row1 + x0, axis=0).astype(np.float32)
    c11 = np.take(flat, row1 + x1, axis=0).astype(np.float32)
    top = c00 + (c10 - c00) * fx
    bottom = c01 + (c11 - c01) * fx
    out = top + (bottom - top) * fy
    if not ok.all():
        out[~ok] = np.asarray(fill, dtype=np.float32)
    return np.rint(out).astype(src.dtype)


# ------------------------------------------------------------------ 形变
def deform(src, cage_src, cage_dst, *, influence=None, fill=FILL,
           step: int | None = None, block: int = BLOCK_PIXELS, bounds=None):
    """按「把手 ``cage_src`` → 把手 ``cage_dst``」形变 ``src``，返回**同尺寸**新数组。

    逐像素语义：

    1. 落在**影响半径内** → 按位移场反查源坐标、双线性采样（内容跟着把手走）；
    2. 半径外 → **原样不动**（位移场在那里恒等于 0，见模块文档「算法」）；
    3. 采样点被拉到**画布外** → 填 ``fill``（小端 RGBA 时给 4 元组）。

    ``src`` 支持 (H, W) 与 (H, W, C)。``influence`` 是影响半径（图片像素，
    缺省由位移量自动定，见 :func:`moved_handles`）；``step`` 是位移场的格距
    （缺省按 :data:`FIELD_MAX` 自适应）；``bounds`` 可显式指定处理范围。
    """
    np = _numpy()
    src = np.asarray(src)
    if src.ndim not in (2, 3):
        raise ValueError(f"src 应为 2 或 3 维，实际 {src.ndim} 维")
    height, width = src.shape[0], src.shape[1]
    channels = 1 if src.ndim == 2 else src.shape[2]

    out = src.copy()
    handles = moved_handles(cage_src, cage_dst, influence)
    if handles is None:
        return out  # 没动过（或笼不匹配）：原样返回
    centres, weights, radius = handles
    if bounds is None:
        bounds = _deform_region(centres, radius, width, height)
    x0, y0, x1, y1 = (int(bounds[0]), int(bounds[1]),
                      int(bounds[2]), int(bounds[3]))
    if x1 <= x0 or y1 <= y0:
        return out  # 影响盘整体在画布外：什么都没变

    clip_fill = np.full(channels, fill, dtype=np.float32) \
        if np.isscalar(fill) else np.asarray(fill, dtype=np.float32)
    if clip_fill.shape != (channels,):
        raise ValueError(f"fill 长度应为 {channels}，实际 {clip_fill.shape}")

    span_x, span_y = x1 - x0, y1 - y0
    if step is None:
        step = max(1, int(math.ceil(math.sqrt(span_x * span_y / FIELD_MAX))))
    step = max(1, int(step))
    grid_x = _lattice(x0, x1, step)
    grid_y = _lattice(y0, y1, step)
    field_x, field_y = _lattice_field(centres, weights, radius, grid_x, grid_y)

    # ⚠️ 读写的**两个视图必须分开**：形变是"每个输出像素去别处取源像素"的重
    #    映射，若就地读同一块缓冲，先算完的块会被后算的块当成源数据取走
    #    （反馈式污染）。``origin`` 是只读的原图视图，``canvas`` 是输出视图。
    origin = src.reshape(height, width, channels)
    canvas = out.reshape(height, width, channels)
    rows = max(1, int(block) // max(1, span_x))

    for start in range(y0, y1, rows):
        stop = min(start + rows, y1)
        coords_x = np.arange(x0, x1, dtype=np.float64)
        coords_y = np.arange(start, stop, dtype=np.float64)
        shift_x = _sample_lattice(field_x, float(x0), float(y0), step,
                                  coords_x, coords_y)
        shift_y = _sample_lattice(field_y, float(x0), float(y0), step,
                                  coords_x, coords_y)
        shape = (stop - start, span_x, channels)
        source_x = (coords_x[None, :] + shift_x).reshape(-1)
        source_y = (coords_y[:, None] + shift_y).reshape(-1)
        canvas[start:stop, x0:x1] = _bilinear(
            origin, source_x, source_y, clip_fill).reshape(shape)
    return out


# ------------------------------------------------------------------ QImage
def qimage_to_rgba(image):
    """QImage → ``(H, W, 4)`` uint8 **RGBA**（ARGB32 在小端机器上是 B,G,R,A）。

    ⚠️ 必须把 alpha 带上。桌面侧编辑的常常是第三步产物"**白底透明 PNG**"：
    透明像素的 RGB 分量存的是 0，一旦只取 RGB 丢掉 alpha，整片背景就读成
    **黑色**（用户 2026-10-01 报的"变形后图片变成黑色"就是这个）。
    """
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
    return image.copy()  # copy 后不再依赖上面那块临时缓冲


def deform_qimage(image, cage_src, cage_dst, *, influence=None, fill=None):
    """QImage 版 :func:`deform`（整幅同尺寸，**保留 alpha 通道**）。

    不透明图走 3 通道（比 4 通道少 1/4 的采样量）；带 alpha 的图走 4 通道，
    越界填充取 :data:`FILL_CLEAR`（白 + 透明），免得透明底变实心。
    """
    np = _numpy()

    rgba = qimage_to_rgba(image)
    opaque = bool(rgba[:, :, 3].min() == 255)
    if opaque:
        warped = deform(np.ascontiguousarray(rgba[:, :, :3]),
                        cage_src, cage_dst, influence=influence,
                        fill=FILL if fill is None else tuple(fill)[:3])
    else:
        warped = deform(rgba, cage_src, cage_dst, influence=influence,
                        fill=FILL_CLEAR if fill is None else fill)
    return array_to_qimage(np.ascontiguousarray(warped))
