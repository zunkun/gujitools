# -*- coding: utf-8 -*-
"""操控变形（puppet warp）：图钉 + 三角网格 + **尽可能保刚** 的形变。

口径（2026-10-01 用户定：GIMP 变换笼做不好就改用 PS 的方案）
------------------------------------------------------------
对齐 Photoshop 的 **操控变形 Puppet Warp**：在图上钉几个图钉（pin），拖某个
图钉时**图钉附近的内容跟着走、离得越远动得越少、没被钉又被钉住的区域基本不动**
（"像扯弹簧"/"像揉面团"）。**不是** PS 的「变形 Warp」（那是有规则网格控制点的
拉伸），也**不是** GIMP 的变换笼。

⚠️ 为什么换掉变换笼（Green 坐标）
--------------------------------
前一版按 GIMP 变换笼实现（Green 坐标闭式系数），**数学逐字对得上 GIMP 源码**
（`green_coefs` 与 `gimpoperationcagecoefcalc.c` 一致，`Σφ≡1`、恒等复现、
相似复现三条性质实测误差均为 0），但有两个绕不过去的问题：

1. 它的形变是**全局**的：拖一个把手，**笼内每个点都在动**，位移缓慢衰减却
   从不归零（实测 100 → 59 → 35 → 16 px）。用户看到的就是"整页歪掉、
   两个弯把图片干得稀碎"。GIMP 里能用是因为**笼只圈一小块**，而本项目的
   默认笼是**贴图边的矩形**（覆盖整幅）⇒ 全局形变作用在整页上。
2. 落地实现里还要做"从形变后位置反解源位置"的**反演**，而正向场只在
   源笼内有定义，反演极易陷入"源笼外位移为零"的假不动点（实测拖 100px
   只有 0.4% 像素变化，即"拖了没反应"）。

**这两条在 Green 坐标路线里是结构性的，不是调参能修的。**
ARAP（As-Rigid-As-Possible）恰好相反：能量函数直接惩罚"每个三角形偏离
刚体旋转"的量，未约束处的解由**拉普拉斯型线性系统**给出，天然是"近处大、
远处衰减"的**局部**形变，且不需要反演（直接用正向解的网格做三角形内插）。

算法：ARAP 表面建模（Sorkine & Alexa, SGP 2007）
----------------------------------------------
1. **建网格**：把图片按 `mesh_cell` 像素切成一格一格的**规则三角网格**
   （每格两个三角形，对角线方向交替以避开规则偏置）。
   顶点 = 网格交点，初始位置 = 图片像素坐标。
2. **图钉**：每个图钉把某个原始网格顶点**钉到**一个新位置（用户拖到的地方）。
   钉住处是**硬约束**（狄利克雷边界），解方程时不参与求解。
3. **能量**：
   ``E = Σ_i Σ_{j∈N(i)} w_ij · ‖(p'_i − p'_j) − R_i (p_i − p_j)‖²``
   其中 ``R_i`` 取"让顶点 i 的 1-邻域最贴合某个旋转"的最优旋转矩阵，
   ``w_ij = (cot α + cot β)/2``（网格是正的三角剖分，余切权重恒正）。
4. **local-global 迭代**（论文口径，交替最小化）：
   - **local**：固定当前顶点位置，对每个顶点 i 由
     ``S_i = Σ_j w_ij (p_i − p_j)(p'_i − p'_j)ᵀ`` 做 **SVD**，
     ``R_i = V Uᵀ``（含翻转修正，见 :func:`_best_rotation`）。
   - **global**：固定所有 ``R_i``，对能量求导得**稀疏对称正定线性系统**
     ``L P' = b``（L = 余切拉普拉斯），解出新的顶点位置。
     钉住处按行替换成单位方程（硬约束），所以"钉在哪就精确在哪"。
   迭代十几次即收敛（残差单调下降），实测整页 4000px 网格只需毫秒级。
5. **取样**：网格只解出**顶点**位移；输出像素落在哪个三角形里，就用该
   三角形的**重心坐标**插值出源坐标，再双线性采样原图。

三条性质是"手感"与"可断言"的关键（自测钉死）：

1. **不乱动**：所有图钉都没挪 ⇒ 网格恒等 ⇒ 输出**逐字节**等于原图。
2. **钉住就准**：图钉落在网格顶点上，硬约束保证该顶点**精确**到位。
3. **衰减 + 局部**：远离被拖图钉方向的位移单调变小；把**被拖图钉周围的
   邻域钉死**（PS 的用法：关节两侧都钉）后，那些钉住处**一动都不动**——
   这正是"近处动得多、远处几乎不动"的可量化版本。

性能
----
**瓶颈在逐像素重采样，不在解方程。**（2026-10-02 全面实测，结论与数量级都
已钉死，改前先读这段，免得重复走弯路。）

1. **重采样 ≈ 0.7 µs/像素**（内存带宽受限，已到 numpy 下界）。1200×900
   (1.08M 像素) 拆开实测：纯双线性采样 336ms、纯重心坐标 101ms、固定开销
   仅 7ms。任何"再优化一点"的尝试（float32 顶点、融合光栅化+采样、扫描线、
   格张量）都只拿到 -15%~+5%，还引入正确性回归 —— **本条路已走到底**。
   ⇒ 唯一的杠杆是**降分辨率预览**（成本随像素数近线性：8 万像素 43ms、
   12 万 72ms、20 万 140ms）。形变场是低频的，预览图再由 Qt 平滑放大，
   肉眼看不出差别。

2. **ARAP 不是局部的**（像素级确认）：拖**一个**图钉 100px，改动区域
   :func:`mesh_region` 仍是整图的 **96~98%**（位移场缓慢衰减但永不归零）。
   ⇒ **"只重算图钉附近"做不到，裁剪 :func:`mesh_region` 也没收益（只省 ~4%）。**

3. **求解耗时随顶点数超线性**：7676 顶点 2.1s、1989 顶点 0.26s、520 顶点
   0.07s。拖动时用 :func:`drag_cell` 给出的**粗网格**（两道约束：相对倍数
   :data:`MESH_DRAG_COARSEN` + 顶点数绝对上限 :data:`MESH_DRAG_MAX_VERTICES`），
   松手 / 应用时才回精网格。⚠️ 只卡"倍数"不够：最密档 20px 在 4000×3000
   下有 3 万顶点，×4 后仍剩 1989 顶点 ≈ 单次求解 103ms，照样卡。

桌面侧的完整降本链见 `image_editor._refresh_deform_preview`（粗网格解 +
按整幅图面积限预算的降分辨率 + 节流）。

几何约定
--------
- 全部用**图片像素坐标**，y 向下（与 QImage 一致）。
- numpy 一律**延迟导入**：桌面主进程要 import 本模块（只为拿函数引用），
  启动路径不能因此背上 numpy 的成本。
"""
from __future__ import annotations

import math

#: 采样越界时填的底色（不透明源图：古籍白纸）
FILL = (255, 255, 255)
#: 采样越界时填的底色（**带透明的源图**：白 + 全透明）。
#: ⚠️ 桌面侧编辑的常常是第三步的"白底透明 PNG"产物：这里若填不透明色，
#:    整片背景会变成一块实心色（用户 2026-10-01 报的"图片变成黑色"）。
FILL_CLEAR = (255, 255, 255, 0)
#: 网格边长（图片像素）的**默认档**。网格越密，形变越细腻、解方程越慢；
#: 4000px 的页面上 40px 一格 = 100×75 格 = 1.5 万顶点，毫秒级。
#: 档位由桌面侧给（见 ``image_editor.MESH_DENSITY_CHOICES``）。
MESH_CELL_DEFAULT = 40.0
#: 网格顶点数的上限：超了就把格距按 ``√(面积/上限)`` 自适应放大。
#: 这不是"精度上限"而是**内存/耗时护栏**——用户在超大图上选最密档时兜底。
MESH_MAX_VERTICES = 200_000
#: ARAP 交替迭代轮数。实测 10 轮位移场已收敛到亚像素（残差单调降），
#: 再多是浪费；局部拖动时 6~8 轮就够了。
ARAP_ITERATIONS = 12
#: **拖动中**用的迭代轮数（精度换速度）。拖动只要"跟手的手感"，几轮就够
#: 看出形变趋势；松手时才用 :data:`ARAP_ITERATIONS` 解到收敛。
ARAP_DRAG_ITERATIONS = 4
#: 迭代早停阈值：位移场相邻两轮的最大变化（像素）小于它就收工。
ARAP_TOLERANCE = 1e-3
#: **拖动中**的早停阈值（宽松些，早停得更早，更跟手）。
ARAP_DRAG_TOLERANCE = 5e-3
#: 拖动预览的网格**放大倍数**：拖动时把格距乘它（网格变粗 ⇒ 顶点少 4 倍
#: ⇒ 解算快约 16 倍）。松手/应用时用原格距解到精细。
#: ⚠️ 这是解决"拖动卡死"的关键手段：ARAP 的解算耗时随顶点数**超线性**
#: 增长（实测 7676 顶点 2.1s、1989 顶点 0.26s、520 顶点 0.07s），而拖动
#: 每次鼠标移动都要重解 —— 大图上用精细网格根本不可能跟手。粗网格解出的
#: 形变在视觉上是同一根"趋势"，停下后立刻用精网格重解，用户只看到最后
#: 那一帧是精细的。
MESH_DRAG_COARSEN = 4.0
#: **拖动中**允许的网格顶点数上限。:data:`MESH_DRAG_COARSEN` 是"相对原格距
#: 放大几倍"，但原格距本身可以很密（用户选最密档 = 20px，4000×3000 下有
#: 3 万顶点；乘 4 之后仍有 1989 顶点，实测单次求解 **103ms**，拖动照样卡）。
#: 所以再叠一道**绝对上限**：顶点数超过它就继续放大格距，直到压到上限内。
#: 600 顶点实测单次求解 ~10ms 量级，配合降分辨率预览，帧时间才稳在 50ms 内。
#: 拖动只求"跟手的手感"，粗到这个程度视觉上仍是同一根形变趋势。
MESH_DRAG_MAX_VERTICES = 600
#: 每批处理的像素上限：不分批的话大图一次要吃掉几 GB。
BLOCK_PIXELS = 1 << 18
#: 判定"图钉重合"的距离阈值（图片像素）。
COINCIDENT = 1e-6


def _numpy():
    """延迟导入 numpy（见模块文档：主进程 import 本模块时不加载）。"""
    import numpy as np

    return np


# ------------------------------------------------------------------ 网格构造
def grid_cell(width: int, height: int, cell: float | None = None) -> float:
    """按图片尺寸与目标格距算出**实际格距**（夹在护栏内）。

    ``cell`` 缺省用 :data:`MESH_CELL_DEFAULT`；顶点数超过
    :data:`MESH_MAX_VERTICES` 时自动放大格距（超大图兜底，不让内存爆掉）。
    """
    width = max(1, int(width))
    height = max(1, int(height))
    cell = float(MESH_CELL_DEFAULT if cell is None else cell)
    cell = max(2.0, cell)
    # 顶点数 ≈ (w/cell+1)(h/cell+1)；超限就放大 cell
    cols = width / cell + 1.0
    rows = height / cell + 1.0
    if cols * rows > MESH_MAX_VERTICES:
        scale = math.sqrt(cols * rows / MESH_MAX_VERTICES)
        cell *= scale
    return cell


def drag_cell(width: int, height: int, cell: float | None = None) -> float:
    """**拖动中**用的格距：在 :func:`grid_cell` 基础上再粗化到顶点数上限内。

    两道约束叠加（取更粗的那个）：

    1. **相对粗化**：``cell × MESH_DRAG_COARSEN``——保住"粗网格解出的形变
       趋势与精网格一致"这一点；
    2. **绝对上限**：顶点数不超过 :data:`MESH_DRAG_MAX_VERTICES`——挡住
       "原格距本就很密"的情形（最密档 20px 在 4000×3000 下有 3 万顶点，
       乘 4 仍剩 1989，单次求解 103ms）。

    ⚠️ 这是"拖动卡死"的第二道关键手段（第一道是降分辨率预览）。ARAP 求解
    耗时随顶点数**超线性**增长，只控倍数不控绝对量，最密档照样卡。
    """
    width = max(1, int(width))
    height = max(1, int(height))
    coarse = grid_cell(width, height, cell) * MESH_DRAG_COARSEN
    # ⚠️ 顶点数要按 build_mesh 的**实际**算法算：cols = ceil((w-1)/cell)、
    #    顶点数 = (cols+1)(rows+1)。按 w/cell+1 估会偏小，导致"以为压到 600
    #    其实出了 638"（自测逮到过）。取整带来的偏差用**留白系数**吸收：
    #    直接按目标 0.9 倍顶点数解格距，再验一次，不够就再放大一档。
    target = MESH_DRAG_MAX_VERTICES * 0.9
    cols = int(math.ceil((width - 1) / coarse)) + 1
    rows = int(math.ceil((height - 1) / coarse)) + 1
    if cols * rows > target:
        coarse *= math.sqrt(cols * rows / target)
        while True:
            cols = int(math.ceil((width - 1) / coarse)) + 1
            rows = int(math.ceil((height - 1) / coarse)) + 1
            if cols * rows <= MESH_DRAG_MAX_VERTICES:
                break
            coarse *= 1.05
    return coarse


def build_mesh(width: int, height: int, cell: float | None = None):
    """建规则三角网格：返回 ``(vertices, triangles, cols, rows, cell)``。

    - ``vertices``：``(N, 2)`` 网格交点（图片像素坐标）。
    - ``triangles``：``(M, 3)`` 三角形顶点下标，每格两个三角，
      **对角线交替**（棋盘式翻转）——全用同一方向的对角线会让网格在
      某个方向偏硬，交替后各向同性得多（这是标准做法）。
    - ``cols``/``rows``：**格数**（顶点数各 +1）。
    - ``cell``：实际格距。

    网格严格覆盖 ``[0, width-1] × [0, height-1]``（末行/末列贴到图边），
    所以"图片四角"永远是网格顶点——用户在图角钉钉时能钉到。
    """
    np = _numpy()
    width = max(1, int(width))
    height = max(1, int(height))
    cell = grid_cell(width, height, cell)
    # 格数向上取整，保证网格覆盖到图边；再把末行/末列精确贴到 width-1/height-1
    cols = max(1, int(math.ceil((width - 1) / cell)))
    rows = max(1, int(math.ceil((height - 1) / cell)))
    xs = np.linspace(0.0, float(width - 1), cols + 1)
    ys = np.linspace(0.0, float(height - 1), rows + 1)
    grid_x, grid_y = np.meshgrid(xs, ys)
    vertices = np.stack([grid_x.ravel(), grid_y.ravel()], axis=1)

    def vid(r: int, c: int) -> int:
        return r * (cols + 1) + c

    tris: list[tuple[int, int, int]] = []
    for r in range(rows):
        for c in range(cols):
            tl, tr = vid(r, c), vid(r, c + 1)
            bl, br = vid(r + 1, c), vid(r + 1, c + 1)
            # ⚠️ 顶点顺序统一为**逆时针**（本项目的 y 轴向下的坐标系里，
            #    tl→tr→br 的 shoelace 为正）。前一版按"顺/逆"随意排列，
            #    导致一半三角形是 CW、一半是 CCW，余切权重符号跟着绕向翻，
            #    是整个 ARAP 求解爆炸的根源之一（见 :func:`cotangent_weights`）。
            if (r + c) % 2 == 0:      # 对角线 tl–br
                tris.append((tl, tr, br))
                tris.append((tl, br, bl))
            else:                     # 对角线 tr–bl
                tris.append((tl, tr, bl))
                tris.append((tr, br, bl))
    triangles = np.asarray(tris, dtype=np.intp)
    return vertices, triangles, cols, rows, cell


def nearest_vertex(vertices, point) -> int:
    """离 ``point`` 最近的网格顶点下标（图钉吸附到网格顶点用）。"""
    np = _numpy()
    vertices = np.asarray(vertices, dtype=np.float64)
    px, py = float(point[0]), float(point[1])
    dist = (vertices[:, 0] - px) ** 2 + (vertices[:, 1] - py) ** 2
    return int(np.argmin(dist))


# ------------------------------------------------------------------ 余切权重
def cotangent_weights(vertices, triangles):
    """三角网格上的**余切权重**：``(edge_i, edge_j, weights)`` 三个等长数组。

    每条**无向边只出现一次**（``i < j``），权重 ``w_ij = (cot α + cot β)/2``
    （α/β 是该边两侧三角形在**对角顶点处**的内角）。

    ⚠️ **本函数返回的权重恒为正**，这是 ARAP 能量的前提（能量
    ``Σ w_ij‖·‖²`` 要求 ``w_ij > 0``，否则最小化会退化）。做法是取
    ``cot = dot / |cross|``：``|cross|`` 抹掉了三角形**
    绕向**（CW/CCW）带来的符号，只留下几何意义上的余切。规则网格的对角
    不超过 45°，两对角之和 < 90°，故 ``cot α + cot β > 0`` 恒成立。

    ⚠️ 前一版用 ``cross``（带符号）作分母，遇到 :func:`build_mesh` 里
    ``(r+c)%2==0`` 那一支产出的 **CW 三角形**时，全部 ``cot`` 变负、
    ``degree`` 变负，归一化时除以 ``sqrt(负×负)`` 后放大到 **1e12**，
    右端项直接爆成 4e13 —— 解出来就是"整页平移 167px"（探针实测）。
    **符号必须在这里就地掐掉。**

    同一条边被两个三角形共享时权重**累加**（先收集再按边 key 归并）。
    """
    np = _numpy()
    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.intp)
    # 三条有向边 (u,v) 及其对角顶点 w 的三元组：a→b→c→a
    u = np.concatenate([triangles[:, 0], triangles[:, 1], triangles[:, 2]])
    v = np.concatenate([triangles[:, 1], triangles[:, 2], triangles[:, 0]])
    w = np.concatenate([triangles[:, 2], triangles[:, 0], triangles[:, 1]])
    pu, pv, pw = vertices[u], vertices[v], vertices[w]
    e1 = pu - pw
    e2 = pv - pw
    cross = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    abs_cross = np.abs(cross)
    valid = abs_cross > 1e-12
    u, v = u[valid], v[valid]
    e1, e2 = e1[valid], e2[valid]
    abs_cross = abs_cross[valid]
    if u.size == 0:
        return (np.zeros(0, dtype=np.intp), np.zeros(0, dtype=np.intp),
                np.zeros(0, dtype=np.float64))
    dot = e1[:, 0] * e2[:, 0] + e1[:, 1] * e2[:, 1]
    # cot(对角) = dot / |cross|   —— 恒正（见上文 docstring）
    weights = 0.5 * dot / abs_cross
    ei = np.minimum(u, v).astype(np.intp)
    ej = np.maximum(u, v).astype(np.intp)
    # 合并重复边（同一对顶点被两个三角形各贡献一次 → 权重相加）
    key = ei.astype(np.int64) * (int(ej.max()) + 2) + ej
    order = np.argsort(key, kind="stable")
    ei, ej, weights, key = ei[order], ej[order], weights[order], key[order]
    uniq, start = np.unique(key, return_index=True)
    sums = np.add.reduceat(weights, start)
    return ei[start], ej[start], sums


def _normalize_weights(edge_i, edge_j, weights, n_vertices):
    """每条边的权重除以两端的加权度，得到对称归一化的 ``w_ij``。

    ⚠️ 归一化是为了让余切拉普拉斯**条件数可控**：未归一化的余切权重在
    不均匀网格上会让远处收敛变慢、残差下不去（实测迭代 12 轮仍有可见残差；
    归一化后 8 轮就亚像素）。归一化不改变"能量最小"的几何含义——
    纯粹是数值手段（这也是 ARAP 实现里的常规做法）。
    """
    np = _numpy()
    degree = np.zeros(n_vertices, dtype=np.float64)
    np.add.at(degree, edge_i, weights)
    np.add.at(degree, edge_j, weights)
    degree = np.maximum(degree, 1e-12)
    scale = 1.0 / np.sqrt(degree[edge_i] * degree[edge_j])
    return weights * scale


# ------------------------------------------------------------------ 拉普拉斯
def build_laplacian(edge_i, edge_j, weights, n_vertices):
    """余切拉普拉斯矩阵 ``L``（稀疏 CSR）：``L[i,i] = Σ_j w_ij``，
    ``L[i,j] = −w_ij``（对称）。

    求解时钉住处按行替换成单位方程（见 :func:`solve_arap`），所以这里
    返回**未加约束**的矩阵，由调用方按需改行。
    """
    import scipy.sparse as sp

    np = _numpy()
    rows = np.concatenate([edge_i, edge_j, np.arange(n_vertices)])
    cols = np.concatenate([edge_j, edge_i, np.arange(n_vertices)])
    vals = np.concatenate([-weights, -weights,
                           np.bincount(edge_i, weights=weights,
                                       minlength=n_vertices)
                           + np.bincount(edge_j, weights=weights,
                                         minlength=n_vertices)])
    # 对角项若被上面的 add 覆盖，用 COO→CSR 时相加即可（对角只出现一次）
    L = sp.coo_matrix((vals, (rows, cols)),
                      shape=(n_vertices, n_vertices)).tocsr()
    return L


def _best_rotation(cov):
    """由协方差 ``S_i`` 求最优旋转矩阵 ``R_i = V Uᵀ``（含翻转修正）。

    ``cov`` 为 2×2。SVD 得 ``S = U Σ Vᵀ``，取 ``R = V Uᵀ``；
    若 ``det(R) < 0``（镜像），把 ``V`` 的最后一列取反再乘——ARAP 论文
    的标准修正，防止"翻面"。返回 2×2。

    ⚠️ 逐顶点调用本函数是纯 Python 循环，大图要几十万次 —— 批量路径请用
    :func:`_best_rotations`（整表一次 SVD）。
    """
    np = _numpy()
    U, _s, Vt = np.linalg.svd(cov)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0.0:
        Vt = Vt.copy()
        Vt[-1, :] *= -1.0
        R = Vt.T @ U.T
    return R


def _best_rotations(cov):
    """向量化版 :func:`_best_rotation`：``cov`` 为 ``(n,2,2)`` → ``(n,2,2)``。

    ⚠️ 为什么不是"闭式手算角度"：2×2 的 SVD 确实有解析解，但特征向量的
    180° 歧义要靠符号定朝向，手推易错（本函数第一版就推错过、实测与 SVD
    差 7.3，是靠反例探针抓出来的）。而 **numpy 对"整表 2×2"的 SVD 是真正
    批量实现的**（实测 3 万个 2×2 只要 0.07s，对比逐点 Python 循环 1.27s，
    约 18 倍），既快又和参考实现逐位一致——所以这里直接用批量 SVD，
    不与 SVD 争"等价"，而是直接**调用**它。
    """
    np = _numpy()
    cov = np.asarray(cov, dtype=np.float64)
    U, _s, Vt = np.linalg.svd(cov)
    R = np.transpose(Vt, (0, 2, 1)) @ np.transpose(U, (0, 2, 1))
    # det(R) < 0 的整表翻最后一列（ARAP 标准修正，防镜像）
    det = R[:, 0, 0] * R[:, 1, 1] - R[:, 0, 1] * R[:, 1, 0]
    flip = det < 0.0
    if flip.any():
        Vt = Vt.copy()
        Vt[flip, -1, :] *= -1.0
        R[flip] = np.transpose(Vt[flip], (0, 2, 1)) \
            @ np.transpose(U[flip], (0, 2, 1))
    return R


def solve_arap(vertices, triangles, pins, *, iterations: int = ARAP_ITERATIONS,
               tolerance: float = ARAP_TOLERANCE):
    """解 ARAP：``pins`` = ``[(顶点下标, (x, y)), ...]`` 硬约束 → 返回新顶点。

    没给任何图钉（或图钉位置与初始一致）时直接返回 ``vertices`` 的副本——
    恒等形变**不做任何计算**（自测钉死"逐字节还原"）。

    local-global 交替：
    - **local**：``R_i`` 取 :func:`_best_rotation` ``S_i`` 的 SVD 最优旋转，
      ``S_i = Σ_j w_ij (p_i−p_j)(p'_i−p'_j)ᵀ``；
    - **global**：解 ``L P' = b``，``b_i = Σ_j (w_ij/2)(R_i+R_j)(p_i−p_j)``。

    ⚠️ **硬约束的正确消元**（前一版错在这里，症状是"钉了不动也整页乱飞"）：
    钉住顶点的未知量要**同时**做两件事——① 在自由顶点的方程里把 ``L[i,k]·t_k``
    挪到右端；② **把该列从矩阵里清成 0**（再用单位行覆盖钉住行）。
    前一版只做了 ① 没做 ②，于是 ``A[i,k]`` 仍留着 ``−w_ik``，与右端里已经
    挪走的 ``t_k`` **重复计入**，等价于把约束位置算了两次 —— 实测"两个图钉
    都不挪"竟解出 202px 的整页位移（正确解应是 0）。
    """
    np = _numpy()
    from scipy.sparse.linalg import spsolve

    vertices = np.asarray(vertices, dtype=np.float64).copy()
    n = len(vertices)
    pins = [(int(k), (float(p[0]), float(p[1])))
            for k, p in pins if 0 <= int(k) < n]
    if not pins:
        return vertices

    edge_i, edge_j, weights = cotangent_weights(vertices, triangles)
    if weights.size == 0:
        return vertices
    weights = _normalize_weights(edge_i, edge_j, weights, n)
    L = build_laplacian(edge_i, edge_j, weights, n).tocsr()

    pin_index = np.array([k for k, _ in pins], dtype=np.intp)
    pin_target = np.array([p for _, p in pins], dtype=np.float64)

    # 有向边表（ARAP 的 local/global 都在有向边上求和）
    di = np.concatenate([edge_i, edge_j])
    dj = np.concatenate([edge_j, edge_i])
    dw = np.concatenate([weights, weights])
    d_rest = vertices[di] - vertices[dj]              # (E,2) 参考边向量

    # ---- 约束矩阵：把钉住列清 0、钉住行换成单位行。只需构造一次 ----
    # ① 删掉"落在钉住列上"的所有项（自由行里的 L[i,k]）——这些量已挪到右端；
    # ② 再删掉"钉住行本身"的所有项——该行要整行换成单位方程。
    # ⚠️ 两步缺一不可。只做 ① 的话，钉住行会残留 `−w_kj` 的邻居项，行方程
    #    变成 `1.0·p'_k + Σ(−w_kj)·p'_j = t_k`，解出来根本不到 t_k
    #    （探针实测钉住点误差 118px）。前一版连列都没清，双重计错。
    coo = L.tocoo()
    is_pin_col = np.isin(coo.col, pin_index)
    is_pin_row = np.isin(coo.row, pin_index)
    keep_entry = ~(is_pin_col | is_pin_row)
    rows = coo.row[keep_entry]
    cols = coo.col[keep_entry]
    vals = coo.data[keep_entry]
    # 补上钉住行的单位方程
    rows = np.concatenate([rows, pin_index])
    cols = np.concatenate([cols, pin_index])
    vals = np.concatenate([vals, np.ones(len(pin_index))])
    import scipy.sparse as sp
    A = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()

    pos = vertices.copy()
    prev = pos.copy()
    # ⚠️ 约束列子矩阵只取一次：`L[:, k]` 是 CSR 的列切片，scipy 每次要
    #    重建结构（实测 2124 次切片共 0.29s，画像里排第三）。图钉不动，
    #    所以这里提前把 `L[:, pin_index]` 稠密化，迭代里只做一次矩阵乘。
    L_pin_cols = np.asarray(L[:, pin_index].todense(), dtype=np.float64) \
        if len(pin_index) else np.zeros((n, 0), dtype=np.float64)
    for _ in range(max(1, int(iterations))):
        # ---- local：每个顶点的最优旋转 ----
        d_cur = pos[di] - pos[dj]                     # (E,2) 当前边向量
        outer = dw[:, None, None] * d_rest[:, :, None] * d_cur[:, None, :]
        cov = np.zeros((n, 2, 2), dtype=np.float64)
        np.add.at(cov, di, outer)
        R = _best_rotations(cov)   # (n,2,2) 一次性向量化，见函数说明
        # ---- global：解 L P' = b ----
        Rp = R[di] @ d_rest[:, :, None]
        Rq = R[dj] @ d_rest[:, :, None]
        contrib = 0.5 * dw[:, None] * (Rp[:, :, 0] + Rq[:, :, 0])
        b = np.zeros((n, 2), dtype=np.float64)
        np.add.at(b, di, contrib)
        # 把约束位置的贡献挪到右端（矩阵里该列已清 0，所以这里做完整减法）
        # 等价于原来的 `for k: b -= L[:,k] * t_k`，但整表一次乘完
        if len(pin_index):
            b -= L_pin_cols @ pin_target
            # 钉住行右端 = 目标位置（自由行 b 已消元；钉住行直接覆盖）
            b[pin_index, 0] = pin_target[:, 0]
            b[pin_index, 1] = pin_target[:, 1]
        new_x = spsolve(A, b[:, 0])
        new_y = spsolve(A, b[:, 1])
        pos = np.stack([new_x, new_y], axis=1)
        if np.abs(pos - prev).max() < tolerance:
            break
        prev = pos.copy()
    return pos


def border_vertices(vertices, width: int, height: int):
    """贴图片四边的网格顶点下标（**隐式锚点**，见 :func:`solve_puppet`）。

    ⚠️ 这条是 Puppet Warp 能"稳住"的关键，必须理解：
    ARAP 能量只惩罚"三角形偏离刚体旋转"，**对整体平移/旋转不变**。所以只钉
    一个图钉时，整张网格可以靠"一起平移"来满足它 —— 实测（400×300，格距
    40）只钉一个图钉拖 37px，**每个顶点都平移 14.269px**，完全是"整页漂移"。
    Photoshop 的做法是默认把**画布边界**视为固定：拖内部图钉时边框被拉住，
    形变才收敛成"近处大、远处为零"。

    返回贴住 ``x∈{0, width-1}`` 或 ``y∈{0, height-1}`` 的顶点下标数组。
    """
    np = _numpy()
    vertices = np.asarray(vertices, dtype=np.float64)
    eps = 1e-6
    edge = ((vertices[:, 0] <= eps)
            | (vertices[:, 0] >= width - 1 - eps)
            | (vertices[:, 1] <= eps)
            | (vertices[:, 1] >= height - 1 - eps))
    return np.nonzero(edge)[0]


def solve_puppet(vertices, triangles, pins, *, width: int | None = None,
                 height: int | None = None, anchor_border: bool = True,
                 iterations: int = ARAP_ITERATIONS,
                 tolerance: float = ARAP_TOLERANCE):
    """**面向交互**的入口：把图钉 + 隐式边框锚点合起来解 ARAP。

    - ``anchor_border=True``（默认，PS 口径）时自动把
      :func:`border_vertices` 里的顶点按**原位**钉住，作为边界约束；
      否则一个图钉会让整页一起平移（见 :func:`border_vertices` 的说明）。
    - ``width``/``height`` 缺省时由 ``vertices`` 的包围盒推出（网格严格覆盖
      ``[0, w-1]×[0, h-1]``）。
    - 用户图钉与边框锚点若有重合，以**用户图钉**为准（后者被覆盖，避免
      同一顶点两个目标位置）。

    返回新的顶点数组。``pins`` 为空且 ``anchor_border=False`` 时原样返回。
    """
    np = _numpy()
    vertices = np.asarray(vertices, dtype=np.float64)
    if width is None:
        width = int(round(float(vertices[:, 0].max()))) + 1
    if height is None:
        height = int(round(float(vertices[:, 1].max()))) + 1

    merged = [(int(k), (float(p[0]), float(p[1]))) for k, p in pins]
    if anchor_border:
        used = {k for k, _ in merged}
        for i in border_vertices(vertices, width, height):
            k = int(i)
            if k not in used:
                merged.append((k, (float(vertices[k, 0]),
                                   float(vertices[k, 1]))))
    return solve_arap(vertices, triangles, merged,
                      iterations=iterations, tolerance=tolerance)


def _normalize_signed_area(vertices, triangles):
    """确保三角形统一逆时针（y 向下时 shoelace 同号），供重心坐标判定用。"""
    np = _numpy()
    tri = triangles.copy()
    p0 = vertices[tri[:, 0]]
    p1 = vertices[tri[:, 1]]
    p2 = vertices[tri[:, 2]]
    area = ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
            - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))
    flip = area < 0.0
    tri[flip, 1], tri[flip, 2] = tri[flip, 2], tri[flip, 1].copy()
    return tri


# ------------------------------------------------------------------ 形变
#: 逐像素重映射时，**单个三角形包围盒内的像素数**上限（超过就跳过该三角形，
#: 视为退化）。正常网格三角形的 bbox 只有 cell×cell 级，这个护栏只为挡住
#: "某个三角形被拉得极大"的病态情形，避免一次性分配过大的临时数组。
WARP_BBOX_LIMIT = 200_000


def _rasterize_source_coords(p0, p1, p2, denom, rest, tri, width, height,
                             offset_x: int = 0, offset_y: int = 0):
    """把"形变后网格"光栅化成**每像素对应的源坐标**表。

    返回 ``(src_x, src_y, cov)`：
    - ``src_x``/``src_y``：``(height, width)`` float64，源（形变前）坐标；
      未被任何三角形覆盖处为 ``NaN``；
    - ``cov``：``(height, width)`` bool，是否被网格覆盖。

    ``offset_x``/``offset_y``：输出画布相对源图坐标系的原点偏移（``grow``
    模式用）。表坐标 ``(tx, ty)`` 对应源坐标系的 ``(tx + offset_x,
    ty + offset_y)``；三角形用**源坐标系**坐标给定，判定落在画布内的方式
    随之平移。

    ⚠️ **核心性能设计：整表一次向量化，不用逐三角形 Python 循环。**
    做法是把每个三角形的包围盒"摊平"成一个大的一维数组（``np.repeat`` 按
    每个盒子的像素数展开），于是所有盒子的重心权重可以**一次算完**；再用
    命中掩码写回整表。

    为什么不能逐三角形循环：numpy 每次调用的固定开销是微秒级，而密网格有
    上万个三角形 —— 实测 1.5 万三角形、20 万像素要 2.7s，其中 96% 是往返
    开销（与像素数无关）。摊平后同一算例只要 0.085s（30 倍）。

    ⚠️ 摊平数组的大小 = ``Σ (三角形 bbox 像素数)``，对规则网格约为
    ``1.5 × 输出像素数``（三角形 bbox 有重叠），完全可控；只有病态拉伸的
    三角形才会失控，用 :data:`WARP_BBOX_LIMIT` 兜底。
    """
    np = _numpy()
    src_x = np.full((height, width), np.nan, dtype=np.float64)
    src_y = np.full((height, width), np.nan, dtype=np.float64)
    cov = np.zeros((height, width), dtype=bool)

    # 三角形在**输出画布**坐标里的包围盒（减掉 offset），夹进 [0, out) 内
    tri_x0 = np.minimum(np.minimum(p0[:, 0], p1[:, 0]), p2[:, 0]) - offset_x
    tri_x1 = np.maximum(np.maximum(p0[:, 0], p1[:, 0]), p2[:, 0]) - offset_x
    tri_y0 = np.minimum(np.minimum(p0[:, 1], p1[:, 1]), p2[:, 1]) - offset_y
    tri_y1 = np.maximum(np.maximum(p0[:, 1], p1[:, 1]), p2[:, 1]) - offset_y
    xmin = np.maximum(0, np.floor(tri_x0).astype(np.int64))
    xmax = np.minimum(width - 1, np.ceil(tri_x1).astype(np.int64))
    ymin = np.maximum(0, np.floor(tri_y0).astype(np.int64))
    ymax = np.minimum(height - 1, np.ceil(tri_y1).astype(np.int64))
    nx = np.maximum(0, xmax - xmin + 1)
    ny = np.maximum(0, ymax - ymin + 1)
    cnt = nx * ny
    # 病态三角形（bbox 过大 = 被拉到极端）直接丢掉，避免临时数组爆掉
    cnt = np.where(cnt > WARP_BBOX_LIMIT, 0, cnt)
    total = int(cnt.sum())
    if total == 0:
        return src_x, src_y, cov

    # ---- 摊平：把"每个三角形的每个盒内像素"展成一维 ----
    # ⚠️ 摊平数组 = Σ(bbox 像素数)。规则网格的三角形 bbox 是正方形、而三角形
    #    只填其中一半，所以摊平量约为输出像素数的 **2.4 倍**（实测）。
    #    整表运算都吃这个放大系数，所以这里：
    #    · 全程 float32（坐标精度到 1e-3 像素就够，省一半内存带宽）；
    #    · 行列偏移一次算好（每个盒子一小段），不做整表取模；
    #    · 命中掩码只算一次、复用于两次 gather。
    tri_id = np.repeat(np.arange(len(cnt)), cnt)
    nx_rep = np.maximum(nx, 1)
    starts = np.concatenate([[0], np.cumsum(cnt)[:-1]])
    local = np.arange(total, dtype=np.int64) - np.repeat(starts, cnt)
    nx_rep_full = np.repeat(nx_rep, cnt)
    # 盒内 (dy, dx) → 输出画布坐标 (x, y)；重心判定用**源坐标系**（三角形
    # 坐标就是源坐标系），故加上 offset 再比。索引仍用输出画布坐标。
    dx = (local % nx_rep_full).astype(np.float32)
    dy = (local // nx_rep_full).astype(np.float32)
    px = np.repeat(xmin, cnt).astype(np.float32) + dx + 0.5
    py = np.repeat(ymin, cnt).astype(np.float32) + dy + 0.5
    sx_px = px + float(offset_x)
    sy_py = py + float(offset_y)

    ax = p0[tri_id, 0].astype(np.float32)
    ay = p0[tri_id, 1].astype(np.float32)
    bx = p1[tri_id, 0].astype(np.float32)
    by = p1[tri_id, 1].astype(np.float32)
    cx = p2[tri_id, 0].astype(np.float32)
    cy = p2[tri_id, 1].astype(np.float32)
    d = denom[tri_id].astype(np.float32)
    w0 = ((bx - sx_px) * (cy - sy_py) - (cx - sx_px) * (by - sy_py)) / d
    w1 = ((cx - sx_px) * (ay - sy_py) - (ax - sx_px) * (cy - sy_py)) / d
    ins = (w0 >= -1e-4) & (w1 >= -1e-4) & ((1.0 - w0 - w1) >= -1e-4)
    if not ins.any():
        return src_x, src_y, cov

    ti = tri_id[ins]
    w0i, w1i = w0[ins], w1[ins]
    w2i = 1.0 - w0i - w1i
    i0, i1, i2 = tri[ti, 0], tri[ti, 1], tri[ti, 2]
    sx = w0i * rest[i0, 0] + w1i * rest[i1, 0] + w2i * rest[i2, 0]
    sy = w0i * rest[i0, 1] + w1i * rest[i1, 1] + w2i * rest[i2, 1]
    tx = px[ins].astype(np.int64)
    ty = py[ins].astype(np.int64)
    src_x[ty, tx] = sx
    src_y[ty, tx] = sy
    cov[ty, tx] = True
    return src_x, src_y, cov


def puppet_warp(src, vertices_rest, vertices_moved, triangles,
                *, fill=FILL, block: int = BLOCK_PIXELS, grow: bool = False,
                progress=None):
    """把 ``vertices_rest → vertices_moved`` 的网格形变应用到 ``src``。

    逐像素重映射（**正向解网格 + 三角形重心插值**，不做反演）：
    对每个输出像素，找到它落在**形变后网格**的哪个三角形里 ⇒ 用该三角形的
    重心坐标在**形变前网格**上插值出源坐标 ⇒ 双线性采样。

    ``src`` 支持 (H, W) 与 (H, W, C)。网格没动过时**逐字节**返回原图。
    ``block`` 保留仅为兼容旧调用（现实现不再分块）。

    ``grow=True``：网格顶点被拖出原边界时**不裁**，画布放大到
    「原图 ∪ 形变后网格外接框」（用户 2026-10-02：「超出原本区域的不要截，
    最终结果按最后图片的范围」）。返回 ``(out, (ox, oy))``，``(ox, oy)`` =
    新画布左上角在原坐标系里的位置（可为负）。

    ``progress`` 给定时在**三个粗阶段**回调 ``progress(stage, 3)``
    （扫描线栅格化 → 双线性采样 → 完成）；返回 ``False`` 则中止并返回
    ``None``。这里只在粗粒度上报（实现是整表向量化，没有可切分的分块循环，
    见 ``utils.puppet_warp`` 的「性能」）——只为让画布侧的长任务有进度可示、
    可被取消。
    """
    np = _numpy()

    src = np.asarray(src)
    if src.ndim not in (2, 3):
        raise ValueError(f"src 应为 2 或 3 维，实际 {src.ndim} 维")
    height, width = src.shape[0], src.shape[1]

    rest = np.asarray(vertices_rest, dtype=np.float64)
    moved = np.asarray(vertices_moved, dtype=np.float64)
    if rest.shape != moved.shape or not np.any(np.abs(rest - moved) > COINCIDENT):
        return (src.copy(), (0, 0)) if grow else src.copy()  # 网格没动

    tri = _normalize_signed_area(moved, np.asarray(triangles, dtype=np.intp))
    if np.isscalar(fill):
        clip_fill = np.full(src.shape[2] if src.ndim == 3 else 1,
                            fill, dtype=np.float32)
    else:
        clip_fill = np.asarray(fill, dtype=np.float32)

    # ---- 输出画布 ----
    if grow:
        ox, oy, out_w, out_h = _grow_box(moved, width, height)
        out = np.empty((out_h, out_w, src.shape[2] if src.ndim == 3 else 1),
                       dtype=src.dtype)
        out.reshape(-1, out.shape[2])[:] = clip_fill.astype(src.dtype)
        # 先把原图整体按偏移贴进去（网格外区域逐字节不动，必须保留）
        px0, py0 = -ox, -oy
        px1, py1 = px0 + width, py0 + height
        bx0, by0 = max(0, px0), max(0, py0)
        bx1, by1 = min(out_w, px1), min(out_h, py1)
        if bx1 > bx0 and by1 > by0:
            shaped = src.reshape(height, width, -1)
            out[by0:by1, bx0:bx1] = shaped[by0 - py0:by1 - py0,
                                           bx0 - px0:bx1 - px0]
    else:
        out = src.copy()
        ox, oy, out_w, out_h = 0, 0, width, height

    origin = src.reshape(height, width, -1)
    canvas = out.reshape(out_h, out_w, -1)

    p0 = moved[tri[:, 0]]
    p1 = moved[tri[:, 1]]
    p2 = moved[tri[:, 2]]
    denom = ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
             - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))
    keep = np.abs(denom) > 1e-12
    if not keep.any():
        return (out, (ox, oy)) if grow else out
    tri, p0, p1, p2, denom = (tri[keep], p0[keep], p1[keep], p2[keep],
                              denom[keep])

    if progress is not None and progress(1, 3) is False:
        return None
    # ⚠️ 网格三角形只覆盖形变后的网格范围；grow 时把输出表放大到 out 尺寸，
    #    并把 offset 传进去，三角形才有机会覆盖到原边界外的那块。
    src_x, src_y, cov = _rasterize_source_coords(p0, p1, p2, denom, rest, tri,
                                                 out_w, out_h,
                                                 offset_x=ox, offset_y=oy)
    if not cov.any():
        return (out, (ox, oy)) if grow else out
    if progress is not None and progress(2, 3) is False:
        return None
    # ---- 一次双线性采样（自写 _bilinear：整表算，无需 scipy）----
    ry, rx = np.nonzero(cov)
    sampled = _bilinear(origin, src_x[ry, rx], src_y[ry, rx], clip_fill)
    canvas[ry, rx] = sampled
    if progress is not None:
        progress(3, 3)
    return (out, (ox, oy)) if grow else out


def _grow_box(vertices_moved, width: int, height: int):
    """``grow`` 模式的输出画布：``(ox, oy, out_w, out_h)``。

    取「原图边界 ∪ 形变后网格顶点外接框」——网格顶点之外没有三角形覆盖，
    那部分保持原图/填充；顶点外接框足以框住"被拖出去的内容"。
    """
    np = _numpy()
    moved = np.asarray(vertices_moved, dtype=np.float64)
    x0 = min(0, int(np.floor(float(moved[:, 0].min()))))
    y0 = min(0, int(np.floor(float(moved[:, 1].min()))))
    x1 = max(int(width), int(np.ceil(float(moved[:, 0].max()))) + 1)
    y1 = max(int(height), int(np.ceil(float(moved[:, 1].max()))) + 1)
    return (x0, y0, x1 - x0, y1 - y0)


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


def puppet_warp_qimage(image, vertices_rest, vertices_moved, triangles,
                       *, fill=None, grow=False, progress=None):
    """QImage 版 :func:`puppet_warp`（**保留 alpha 通道**）。

    不透明图走 3 通道（比 4 通道少 1/4 的采样量）；带 alpha 的图走 4 通道，
    越界填充取 :data:`FILL_CLEAR`（白 + 透明），免得透明底变实心。

    ``grow=True``：网格被拖出原边界时不裁，画布放大，返回
    ``(QImage, (ox, oy))``（见 :func:`puppet_warp`）。``grow=False``（默认）
    返回单个 ``QImage``，与原行为逐字节一致。

    ``progress`` 透传给 :func:`puppet_warp`（粗阶段回调，返回 ``False``
    则中止并返回 ``None``）。
    """
    np = _numpy()

    rgba = qimage_to_rgba(image)
    opaque = bool(rgba[:, :, 3].min() == 255)
    if opaque:
        warped = puppet_warp(np.ascontiguousarray(rgba[:, :, :3]),
                             vertices_rest, vertices_moved, triangles,
                             fill=FILL if fill is None else tuple(fill)[:3],
                             grow=grow, progress=progress)
    else:
        warped = puppet_warp(rgba, vertices_rest, vertices_moved, triangles,
                             fill=FILL_CLEAR if fill is None else fill,
                             grow=grow, progress=progress)
    if warped is None:
        return None  # 被 progress 中止
    if grow:
        array, origin = warped
        return array_to_qimage(np.ascontiguousarray(array)), origin
    return array_to_qimage(np.ascontiguousarray(warped))


def mesh_region(vertices_rest, vertices_moved, width: int, height: int):
    """这次形变**实际会改动的矩形区域**（图片坐标，开区间右端）。

    取"移动过的网格顶点"的包围盒——网格没动的部分逐字节等于原图，
    画布侧的预览浮层贴在框外也不会留接缝。返回 ``(x0, y0, x1, y1)``；
    没动过返回 ``(0, 0, 0, 0)``。
    """
    np = _numpy()
    rest = np.asarray(vertices_rest, dtype=np.float64)
    moved = np.asarray(vertices_moved, dtype=np.float64)
    delta = np.abs(moved - rest).max(axis=1)
    idx = np.nonzero(delta > COINCIDENT)[0]
    if idx.size == 0:
        return (0, 0, 0, 0)
    pts = np.vstack([rest[idx], moved[idx]])
    x0 = max(0, int(math.floor(float(pts[:, 0].min()))))
    y0 = max(0, int(math.floor(float(pts[:, 1].min()))))
    x1 = min(int(width), int(math.ceil(float(pts[:, 0].max()))) + 1)
    y1 = min(int(height), int(math.ceil(float(pts[:, 1].max()))) + 1)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, 0, 0)
    return (x0, y0, x1, y1)


def mesh_moved(vertices_rest, vertices_moved, epsilon: float = 1e-6) -> bool:
    """网格是否有实质变化（区分"钉过但没挪"与"真变形"）。"""
    np = _numpy()
    a = np.asarray(vertices_rest, dtype=np.float64)
    b = np.asarray(vertices_moved, dtype=np.float64)
    if a.shape != b.shape:
        return True
    return bool(np.max(np.abs(a - b)) > epsilon)
