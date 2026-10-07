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

所以桌面侧仍然**降分辨率出预览**（``image_editor.cage_preview_scale``）、
只在落地时走全分辨率；而局部影响让"要算的面积"从整幅缩到半径平方，
预览几乎必然跟手。

落地（全分辨率）这一步在**大图上仍是秒级到分钟级**，直接同步跑会把 GUI
主线程钉死（用户 2026-10-01 报"卡死/崩溃"）。为此：

- :func:`deform` / :func:`deform_qimage` 支持 ``bounds``（只算影响框、返回
  裁好的图，框外逐字节不动 ⇒ 画布直接透底图）与 ``progress``（每个分块回调
  ``progress(done, total)``，返回 ``False`` 即中止、函数返回 ``None``）；
- 画布侧（``image_editor.run_with_progress``）把落地丢进**后台线程**并显示
  进度对话框，主线程保持响应、可取消。

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
from typing import Any

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
#: 判定"两个把手位于同一处"的容差（图片像素）。去重时用
#: （:func:`_drop_coincident`）：位置重合会让 RBF 矩阵奇异。
#:
#: ⚠️ **不能只用 1e-6**（实测踩过）：两个把手相距 0.5px 时矩阵只是
#: **近**奇异，`solve` 不抛异常而是回��权重爆炸到 1e14，随后的半径
#: 迭代（``need = |φ'|max·Σ|w|``）跟着发散，第三轮直接 LinAlgError。
#: ⇒ 判据取"相对间距"：把手间距小于其**目标位移**的 1e-3 时，在数值上
#: 已经无法把两个约束区分开，合并成一个是**正确**的（位移取平均，
#: 两者本就几乎同向）；1e-3 远小于任何真实拖拽的分辨率。
_COINCIDENT_REL = 1e-3
#: Wendland 核梯度的上界：``|φ'(r)|`` 在 ``r = 1/4`` 处取到 ``135/64 ≈ 2.11``。
#: 位移场梯度量级 ``≤ |φ'|max·Σ|wⱼ| / R``——拿它当作"会不会自交"的判据。
_WENDLAND_GRAD = 135.0 / 64.0
#: 影响半径的**起始**下限倍率（再按上面的梯度判据迭代抬高）。
_RADIUS_FLOOR = 2.5
#: 半径迭代的**发散上限**（相对 ``reach``，即最大位移）。超过就判定这次
#: 拖动不可解、退化为恒等。
#:
#: ⚠️ 半径迭代 ``radius ← 1.1·|φ'|max·Σ|wⱼ|`` 在**位移互相抵消**时不收敛
#: 而是爆炸：实测两个把手反向拖时半径逐轮 212 → 1099 → 23027 → 9.6e6
#: → 1.7e12，条件数从 1.2e1 涨到 ``inf``，最后一轮 LinAlgError（这是既有
#: 缺陷，本修改前就会崩）。取 1e4：比任何合理的形变范围（几个图宽）都大，
#: 又远小于发散时那种量级，所以既能放过正常拖动、又能截住发散。
_RADIUS_DIVERGE = 1e4


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
    """解 ``Φw = shift``（``Φᵢⱼ = φ(|mᵢ−mⱼ|/R)``），返回每个把手的分量权重。

    ⚠️ 奇异（把手重合）时抛 ``numpy.linalg.LinAlgError``。调用方
    :func:`moved_handles` 已经把重合项去重，正常路径不该到这里；
    这里的异常仍要能安全冒泡给上层（桌面侧有兜底）。
    """
    np = _numpy()
    gap = np.linalg.norm(centres[:, None, :] - centres[None, :, :], axis=-1)
    return np.linalg.solve(wendland(gap / radius), shift)


def _drop_coincident(centres, wanted):
    """合并**数值上无法区分**的把手，返回合并后的 ``(centres, wanted)``。

    为什么必须做：Wendland 核 ``φ(0) = 1``，两个位置重合的把手会让矩阵
    第 i、j 行**完全相同** ⇒ 严格奇异 ⇒ ``np.linalg.solve`` 抛
    ``LinAlgError``。这是随手可做的操作（把两个把手拖到同一处，命中半径
    12 视图像素），异常一旦冒到 Qt 槽函数就是崩溃。

    判据是**相对**的（:data:`_COINCIDENT_REL`）而不是绝对容差：严格重合要
    去重，"几乎重合"更要——后者矩阵只是**近**奇异，``solve`` 不抛异常而是
    回��爆炸的权重（实测相距 0.5px、位移 85px 时 ``|w|`` 冲到 1e14），
    再把半径迭代（``need = |φ'|max·Σ|w|``）带进发散、第三轮 LinAlgError。
    合并时目标位移取**算术平均**：相距 ≪1px 时两个位移在像素级本就不可分。

    返回的 ``centres`` 保留每组的**第一个**原位置（位置是绘制与取半径的
    依据，两者在容差内，取谁都行）。
    """
    np = _numpy()
    if centres.shape[0] < 2:
        return centres, wanted
    keep: list[int] = []                 # 每组的代表下标（进 centres）
    acc: list[list[float]] = []           # 每组已累加的位移与
    count: list[int] = []                 # 每组的成员数
    for i in range(centres.shape[0]):
        gap_tol = max(float(np.linalg.norm(wanted[i])) * _COINCIDENT_REL,
                      COINCIDENT)
        hit = -1
        for slot, j in enumerate(keep):
            if float(np.linalg.norm(centres[i] - centres[j])) <= gap_tol:
                hit = slot
                break
        if hit < 0:
            keep.append(i)
            acc.append([float(wanted[i][0]), float(wanted[i][1])])
            count.append(1)
        else:
            acc[hit][0] += float(wanted[i][0])
            acc[hit][1] += float(wanted[i][1])
            count[hit] += 1
    if len(keep) == centres.shape[0]:
        return centres, wanted             # 没合并任何一项，原样返回
    index = np.asarray(keep, dtype=np.intp)
    merged = np.asarray(acc, dtype=np.float64) / \
        np.asarray(count, dtype=np.float64)[:, None]
    return centres[index], merged


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

    ⚠️ **退化一律退化为恒等**（返回 ``None``），绝不把异常抛给调用方：
    方程组在把手重合等退化配置下无解（见 :func:`_drop_coincident`），
    异常一旦冒到 Qt 槽函数就是崩溃——而"这一帧不变形"完全可接受
    （用户下次把把手分开一点就行）。口径与 ``solve_puppet`` 的
    "解算失败退化为恒等"一致。
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
    # ⚠️ 先去重再解方程组：位置重合 ⇒ 矩阵严格奇异 ⇒ 无解
    centres, wanted = _drop_coincident(centres, wanted)
    if centres.shape[0] == 0:
        return None

    reach = float(np.linalg.norm(wanted, axis=1).max())
    radius = max(float(influence or 0.0), _RADIUS_FLOOR * reach)
    # ⚠️ 方程组无解/退化时**一律退化为恒等**（返回 None），绝不把异常抛给
    #   调用方——它会一路冒到 Qt 槽函数成为崩溃，而"这一帧不变形"完全
    #   可接受（用户把把手分开一点再试）。口径与 ``solve_puppet`` 一致。
    #
    # ⚠️ **必须显式检测发散**（这是既有的算法坑，不是新引入的）：半径迭代
    #   ``radius ← 1.1·|φ'|max·Σ|wⱼ|`` 在**位移互相抵消**时不收敛而是
    #   **爆炸**——实测两个把手反向拖（(60,60) 拖出 (−60,−60)、(90,60)
    #   拖出 (+10,−60)）时半径逐轮 212 → 1099 → 23027 → 9.6e6 → 1.7e12，
    #   矩阵条件数从 1.2e1 一路涨到 ``inf``，最后一轮 LinAlgError。
    #   单靠 `for _ in range(8)` 兜不住：第 8 轮的重解照样抛。
    #   ⇒ 每轮检查半径是否已"大得没有意义"（超过影响盘的合理上界），
    #   一旦发散立即返回 None。
    span = float(max(1.0, reach)) * _RADIUS_DIVERGE
    try:
        weights = None
        for _ in range(8):
            weights = _solve_rbf(centres, wanted, radius)
            need = _WENDLAND_GRAD * float(np.linalg.norm(weights, axis=1).sum())
            if need <= radius:
                break
            if not math.isfinite(need) or need > span:
                return None           # 发散：退化为恒等
            radius = need * 1.1
        else:
            # 迭代到上限还没收敛（把手挤在一起又拖得很远）：按最后的半径重解，
            # 保证返回的权重与半径自洽。
            weights = _solve_rbf(centres, wanted, radius)
    except np.linalg.LinAlgError:
        return None
    if weights is None:
        return None
    # 解出来的权重含非有限值（近似奇异时 solve 不抛异常、只回垃圾）——
    # 同样退化为恒等：NaN 一旦流进位移场，后面逐像素采样会越界。
    if not np.all(np.isfinite(weights)) or not math.isfinite(radius):
        return None
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


def _region_unclamped(centres, radius: float):
    """影响盘的并集外接框，**不夹进画布**（可为负坐标）。

    与 :func:`_deform_region` 同构，只是不裁到 ``[0, W]×[0, H]``——``grow``
    模式要算的正是"被拖到原边界外"的那块，裁掉就白做了。
    """
    xs = centres[:, 0]
    ys = centres[:, 1]
    x0 = int(math.floor(float(xs.min()) - radius))
    y0 = int(math.floor(float(ys.min()) - radius))
    x1 = int(math.ceil(float(xs.max()) + radius)) + 1
    y1 = int(math.ceil(float(ys.max()) + radius)) + 1
    return (x0, y0, x1, y1)


def content_region(cage_src, cage_dst, influence=None, *, width: int, height: int):
    """形变后**内容占用的矩形范围**（图片坐标，开区间右端）——**不夹进画布**。

    用户 2026-10-02 报：「图片倾斜后一部分区域超出原本边界，现在会被截掉，
    不对；超出原本区域的**不要截**，最终结果要按最后图片的范围。」

    口径（用户同日的补充）：「一切以新图为准，新图什么样就什么样，老图不要
    了」——最终画布 = **形变后内容的完整外框**，不是"原图 ∪ 形变后"的松散
    并集。对变换笼来说，"内容"分两块：

    ① **没碰到的内容**：RBF 是紧支撑的，影响半径外的像素逐字节不变，仍老实
       待在 ``[0, W] × [0, H]`` 里——这块必须原样留全（它**就是**结果的一
       部分，不是"老图残留"）；
    ② **被拖走的把手附近的源内容**：它跟着把手走。位移场是后向的，所以不能
       正推落点，但 ``s(mᵢ) = hᵢ``（把手处内容严格跟着把手），于是把手落点
       ``mᵢ`` 就是这块内容的"锚点"。

    因此画布 = ``[0, W] × [0, H]`` ∪ ``bbox(被拖把手的落点)``。

    ⚠️ **不要**再叠加影响半径 ``R``：``R`` 是 RBF 解算出来的**位移场**尺度
    （可能远大于实际位移），不是"内容向外铺开的距离"。把 ``mᵢ ± R`` 并进
    来会让**向内**拖把手也凭空外扩几十像素（实测拖 25px 却外扩 64px），
    画布白白变大、四边多出一圈空白——正是用户要消掉的"老图残留"。

    返回 ``(x0, y0, x1, y1)``；没动过 → 原图边界 ``(0, 0, W, H)``。
    """
    handles = moved_handles(cage_src, cage_dst, influence)
    if handles is None:
        return (0, 0, int(width), int(height))
    centres, _weights, _radius = handles
    xs, ys = centres[:, 0], centres[:, 1]
    # 内容外框 = 原图边界 ∪ 被拖把手落点（不叠影响半径，见 docstring）
    x0 = min(0, int(math.floor(float(xs.min()))))
    y0 = min(0, int(math.floor(float(ys.min()))))
    x1 = max(int(width), int(math.ceil(float(xs.max()))) + 1)
    y1 = max(int(height), int(math.ceil(float(ys.max()))) + 1)
    return (x0, y0, x1, y1)



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
           step: int | None = None, block: int = BLOCK_PIXELS, bounds=None,
           grow: bool = False, progress=None):
    """按「把手 ``cage_src`` → 把手 ``cage_dst``」形变 ``src``。

    **默认**（``grow=False``）返回**同尺寸**新数组；``grow=True`` 返回
    **放大后**的新数组 + 其原点偏移，让"被拖出原边界的内容"**不被截掉**
    （见 :func:`deform_qimage` 的返回值说明与用户 2026-10-02 报障）。

    逐像素语义：

    1. 落在**影响半径内** → 按位移场反查源坐标、双线性采样（内容跟着把手走）；
    2. 半径外 → **原样不动**（位移场在那里恒等于 0，见模块文档「算法」）；
    3. 采样点超出**源图** → 填 ``fill``（小端 RGBA 时给 4 元组）。
       ⚠️ 与 ``grow`` 无关：填的是"源图之外"，不是"原边界之外"——内容被
       拖到原边界外时，它的**源坐标仍在源图内**，所以照常取到真实像素。

    ``src`` 支持 (H, W) 与 (H, W, C)。``influence`` 是影响半径（图片像素，
    缺省由位移量自动定，见 :func:`moved_handles`）；``step`` 是位移场的格距
    （缺省按 :data:`FIELD_MAX` 自适应）；``bounds`` 可显式指定处理范围。

    ``progress`` 给定时在**每个分块**后回调 ``progress(done, total)``
    （``total`` = 要处理的像素总数）；返回 ``False`` 则**提前中止**并返回
    ``None``（让长任务能被打断，见画布侧的大图烘焙）。

    返回：``grow=False`` → ``out``（同尺寸 ndarray）；``grow=True`` →
    ``(out, (ox, oy))``（``out`` 是新画布，``(ox, oy)`` = 新画布左上角在
    旧坐标系里的位置，可为负）。
    """
    np = _numpy()
    src = np.asarray(src)
    if src.ndim not in (2, 3):
        raise ValueError(f"src 应为 2 或 3 维，实际 {src.ndim} 维")
    height, width = src.shape[0], src.shape[1]
    channels = 1 if src.ndim == 2 else src.shape[2]

    handles = moved_handles(cage_src, cage_dst, influence)
    if handles is None:
        return (src.copy(), (0, 0)) if grow else src.copy()  # 没动过

    centres, weights, radius = handles
    if bounds is None:
        if grow:
            # 受影响块 = 影响盘的并集外接框（**不夹进画布**：内容可能被拖到
            # 原边界外，那块也属于"要重算"的区域）。
            bounds = _region_unclamped(centres, radius)
        else:
            bounds = _deform_region(centres, radius, width, height)
    x0, y0, x1, y1 = (int(bounds[0]), int(bounds[1]),
                      int(bounds[2]), int(bounds[3]))
    if x1 <= x0 or y1 <= y0:
        return (src.copy(), (0, 0)) if grow else src.copy()  # 影响盘在画布外

    clip_fill = np.full(channels, fill, dtype=np.float32) \
        if np.isscalar(fill) else np.asarray(fill, dtype=np.float32)
    if clip_fill.shape != (channels,):
        raise ValueError(f"fill 长度应为 {channels}，实际 {clip_fill.shape}")

    # ---- 输出画布 ----
    # grow=False：输出=同尺寸原图副本，处理块写回原位（与老实现逐字节一致）。
    # grow=True ：输出=「内容外接框 ∪ 原图边界」；先把**原图整体**按偏移贴进去
    #             （影响半径外的像素逐字节不动，必须保留），再对受影响块重采样。
    if grow:
        cx0, cy0, cx1, cy1 = content_region(cage_src, cage_dst, influence,
                                            width=width, height=height)
        out_w, out_h = cx1 - cx0, cy1 - cy0
        out = np.empty((out_h, out_w, channels), dtype=src.dtype)
        out.reshape(-1, channels)[:] = clip_fill.astype(src.dtype)
        origin_x, origin_y = cx0, cy0
        # 原图在新画布里的位置（grow 时 origin 可为负 ⇒ 原图整体右移/下移）
        px0, py0 = -origin_x, -origin_y
        px1, py1 = px0 + width, py0 + height
        # 夹进输出画布后贴入原图（影响圈外的部分靠这一步"原样保留"）
        bx0, by0 = max(0, px0), max(0, py0)
        bx1, by1 = min(out_w, px1), min(out_h, py1)
        if bx1 > bx0 and by1 > by0:
            out[by0:by1, bx0:bx1] = src[by0 - py0:by1 - py0,
                                        bx0 - px0:bx1 - px0]
    else:
        out = src.copy()
        out_w, out_h = width, height
        origin_x, origin_y = 0, 0
    # 处理框在输出画布里的坐标（grow 时整体平移 -origin）
    ax0, ay0 = x0 - origin_x, y0 - origin_y
    ax1, ay1 = x1 - origin_x, y1 - origin_y
    ax0, ay0 = max(0, ax0), max(0, ay0)
    ax1, ay1 = min(out_w, ax1), min(out_h, ay1)
    if ax1 <= ax0 or ay1 <= ay0:
        return (out, (origin_x, origin_y)) if grow else out

    span_x, span_y = ax1 - ax0, ay1 - ay0
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
    canvas = out.reshape(out_h, out_w, channels)
    rows = max(1, int(block) // max(1, span_x))

    total = span_x * span_y
    done = 0
    for start in range(ay0, ay1, rows):
        stop = min(start + rows, ay1)
        # 输出画布坐标；源坐标 = 输出坐标 + origin（grow 时 origin 可为负）
        coords_x = np.arange(ax0 + origin_x, ax1 + origin_x, dtype=np.float64)
        coords_y = np.arange(start + origin_y, stop + origin_y,
                             dtype=np.float64)
        shift_x = _sample_lattice(field_x, float(x0), float(y0), step,
                                  coords_x, coords_y)
        shift_y = _sample_lattice(field_y, float(x0), float(y0), step,
                                  coords_x, coords_y)
        shape = (stop - start, span_x, channels)
        source_x = (coords_x[None, :] + shift_x).reshape(-1)
        source_y = (coords_y[:, None] + shift_y).reshape(-1)
        canvas[start:stop, ax0:ax1] = _bilinear(
            origin, source_x, source_y, clip_fill).reshape(shape)
        if progress is not None:
            done += span_x * (stop - start)
            if progress(done, total) is False:
                return None
    return (out, (origin_x, origin_y)) if grow else out


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


def deform_qimage(image, cage_src, cage_dst, *, influence=None, fill=None,
                  bounds=None, grow=False, progress=None):
    """QImage 版 :func:`deform`（**保留 alpha 通道**）。

    ⚠️ 返回类型是**多形态**的（``None`` / ``QImage`` / ``(QImage, (ox, oy))``），
    刻意不加注解：不加时类型检查器只会看到 Unknown，调用点解包不会报错；
    一旦标成联合类型，``preview, origin = deform_qimage(...)`` 这种解包就会因
    "QImage 不可迭代"而报错。见 image_editor.bake_transform 的同款说明。

    不透明图走 3 通道（比 4 通道少 1/4 的采样量）；带 alpha 的图走 4 通道，
    越界填充取 :data:`FILL_CLEAR`（白 + 透明），免得透明底变实心。

    ``bounds`` = ``(x0, y0, x1, y1)``（图片坐标，开区间右端）时**只算这块**
    并返回**裁剪后的图**（左上角 = 框左上角）——画布侧预览就靠它把工作量
    从整幅缩到影响框（框外逐字节等于原图，直接透底图即可）。``None``（默认）
    返回整幅同尺寸结果。``bounds`` 与 ``grow=True`` 同时给：``bounds`` 仍
    作为"要重算哪块"的提示，最终返回的是**放大的整幅**（不裁剪）。

    ``grow=True``：用户 2026-10-02 报障的修复——内容被拖出原边界时**不截**，
    按 :func:`content_region` 放大画布，返回 ``(QImage, (ox, oy))``，
    ``(ox, oy)`` = 新图左上角在原图坐标系里的位置（可为负）。``grow=False``
    （默认）返回单个 ``QImage``，与原行为逐字节一致。

    ``progress`` 透传给 :func:`deform`（每个分块回调一次，返回 ``False``
    则中止并返回 ``None``）。
    """
    np = _numpy()

    rgba = qimage_to_rgba(image)
    opaque = bool(rgba[:, :, 3].min() == 255)
    common: dict[str, Any] = dict(influence=influence, bounds=bounds, grow=grow,
                                  progress=progress)
    if opaque:
        warped = deform(np.ascontiguousarray(rgba[:, :, :3]),
                        cage_src, cage_dst,
                        fill=FILL if fill is None else tuple(fill)[:3],
                        **common)
    else:
        warped = deform(rgba, cage_src, cage_dst,
                        fill=FILL_CLEAR if fill is None else fill,
                        **common)
    if warped is None:
        return None  # 被 progress 中止
    if grow:
        array, origin = warped
        return array_to_qimage(np.ascontiguousarray(array)), origin
    # grow=False 时 deform 返回同尺寸 ndarray（grow 分支已在上方 return）
    assert not isinstance(warped, tuple)
    if bounds is not None:
        x0, y0, x1, y1 = (int(bounds[0]), int(bounds[1]),
                          int(bounds[2]), int(bounds[3]))
        if x1 > x0 and y1 > y0:
            warped = warped[y0:y1, x0:x1]
    return array_to_qimage(np.ascontiguousarray(warped))
