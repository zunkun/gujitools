# -*- coding: utf-8 -*-
"""变换笼（**局部**光滑形变）算法守卫。

口径与实现见 ``utils/cage_warp.py`` 的模块文档。本模块只盯**可观测的算法
性质**（改实现不怕，性质破了就是坏了）：

1. **把手的构造**：``perimeter_cage`` 只取周长上的点（1 → 四角、2 → 四角 +
   四边中点），一圈"绳子上的结"均匀分布；
2. **Wendland 核**：``φ(0)=1``、``φ(1)=0``、核外恒 0、单调不增——
   "紧支撑"是局部性成立的全部依据，这条塌了下面全塌；
3. **只把真的动过的把手当约束**：没动过的把手不进方程组（于是"点笼线加个
   把手"是逐字节中性的）；
4. **精确插值**：把手处的像素严格跟着把手走（``s(mᵢ) = hᵢ``）；
5. **恒等笼逐字节还原**：``deform(img, cage, cage) == img``；
6. **局部性**（用户 2026-10-01 报的核心问题）：被改动的像素**全部落在**
   影响半径内；拖一个把手时，**远处把手周围逐字节不动**——不是"变化小"，
   是"完全不动"；
7. **不自交**：位移场的雅可比行列式处处 > 0（半径下限真的在拦"漩涡"）；
8. **近处大、远处小**：沿拖动方向位移单调不增（用户描述的"像扯弹簧"）；
9. **往外拖＝拉伸**：把手能拖到图外，角落内容被放大，远端不受影响；
10. **保透明**：白底透明 PNG（第三步产物）形变后**不能变成不透明黑**
    （用户 2026-10-01 报的"图片变成黑色"）；
11. **降本机制还在**：稀格步长按 ``FIELD_MAX`` 自适应。外面再套一条墙钟兜底。
"""
from __future__ import annotations

import math
import time

NAME = "cage_warp"
DEPENDS: list[str] = []
TITLE = "变换笼：局部光滑形变 / 恒等还原 / 保透明"


def _coord_image(width: int, height: int):
    """把"每个像素自己的坐标"编进 R/G 通道：形变后读 R/G 即得**源坐标**。

    这是能直接量出位移场的探针图——比"看某处颜色变没变"强得多。
    """
    import numpy as np

    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
    image[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    return image


def run(ctx) -> None:
    import numpy as np

    from tests.selftests._context import ok

    from utils import cage_warp as cw

    # ---- 1. 把手的构造：只有周长，没有内部网格 ----
    square = cw.perimeter_cage((0.0, 0.0, 10.0, 10.0), 1)
    ok("perimeter_cage：每边 1 段 = 四个角（按周长顺序）",
       square == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
       f"取到 {square}")
    eight = cw.perimeter_cage((0.0, 0.0, 10.0, 10.0), 2)
    ok("perimeter_cage：每边 2 段 = 8 点（四角 + 四边中点）",
       len(eight) == 8 and (5.0, 0.0) in eight and (10.0, 5.0) in eight,
       f"取到 {len(eight)} 点：{eight}")
    interior = [point for point in eight
                if 0.0 < point[0] < 10.0 and 0.0 < point[1] < 10.0]
    ok("perimeter_cage：只取周长（一圈绳上的结，内部不铺点）",
       not interior, f"内部点：{interior}")

    # ---- 2. Wendland 核：紧支撑是局部性的全部依据 ----
    probe = np.array([0.0, 0.25, 0.5, 0.75, 0.999, 1.0, 1.5, 10.0])
    values = cw.wendland(probe)
    ok("wendland：φ(0)=1、φ(1)=0、核外恒 0（紧支撑）",
       abs(values[0] - 1.0) < 1e-12 and abs(values[5]) < 1e-12
       and bool((values[6:] == 0.0).all()),
       f"φ = {np.round(values, 6)}")
    ok("wendland：在 [0,1) 上单调不增（影响随距离衰减）",
       bool(np.all(np.diff(values[:6]) <= 1e-12)),
       f"φ = {np.round(values[:6], 6)}")

    # ---- 3. 只把真的动过的把手当约束 ----
    home = cw.perimeter_cage((0.0, 0.0, 99.0, 79.0), 2)
    ok("moved_handles：一个都没动 → None（不白算一遍）",
       cw.moved_handles(home, home) is None, "")
    one_moved = list(home)
    one_moved[0] = (12.0, 8.0)
    handles = cw.moved_handles(home, one_moved)
    ok("moved_handles：只把动过的把手收进约束集（8 点里动 1 个 → 1 个约束）",
       handles is not None and handles[0].shape == (1, 2)
       and tuple(np.round(handles[0][0], 6)) == (12.0, 8.0),
       f"约束集 {None if handles is None else handles[0].shape}")

    # ---- 4. 影响半径：用户下限 + 防自交下限 ----
    drag = math.hypot(12.0, 8.0)
    ok("影响半径：默认 = 拖动距离 × 2.5（用户下限）",
       abs(handles[2] - 2.5 * drag) < 1e-6,
       f"半径 {handles[2]:.3f} vs 2.5×{drag:.3f}")
    tight = cw.moved_handles(home, one_moved, influence=1.0)
    ok("影响半径：给得再小也会被防自交下限顶上去",
       tight is not None and tight[2] >= 2.5 * drag - 1e-9,
       f"要 1.0，实得 {None if tight is None else tight[2]:.3f}")
    wide = cw.moved_handles(home, one_moved, influence=400.0)
    ok("影响半径：用户给得比下限大就听用户的（「影响范围」控件靠它）",
       wide is not None and abs(wide[2] - 400.0) < 1e-9,
       f"要 400，实得 {None if wide is None else wide[2]:.3f}")

    # ---- 5. 精确插值 + 局部性（坐标编码探针图） ----
    width, height = 100, 80
    probe_img = _coord_image(width, height)
    pulled = list(home)
    pulled[0] = (12.0, 8.0)
    out = cw.deform(probe_img, home, pulled)
    # out[y, x] 的 R/G 就是"该像素取自原图哪个坐标"
    src_x = out[:, :, 0].astype(float)
    src_y = out[:, :, 1].astype(float)
    ok("精确插值：被拖的把手处，像素取自它的**原位**（12,8 处取到 0,0）",
       abs(src_x[8, 12] - 0.0) < 0.6 and abs(src_y[8, 12] - 0.0) < 0.6,
       f"(12,8) 取到 ({src_x[8, 12]:.1f}, {src_y[8, 12]:.1f})")

    radius = handles[2]
    coords_x, coords_y = np.meshgrid(np.arange(width, dtype=float),
                                     np.arange(height, dtype=float))
    far = np.hypot(coords_x - 12.0, coords_y - 8.0) > radius + 1.0
    changed = (out != probe_img).any(axis=2)
    outside_changed = int(changed[far].sum())
    ok("局部性：被改动的像素**全部落在影响半径内**（半径外逐字节原样）",
       outside_changed == 0 and int(changed.sum()) > 100,
       f"半径外改动 {outside_changed} 像素 / 半径外共 {int(far.sum())} 像素，"
       f"半径内改动 {int(changed.sum())} 像素")

    # 用户原话：「选择一点向内拖，会从其他节点生出折线」——这次影响半径外的
    # 把手四周必须**完全不动**，不是"变化小"。逐个没动过的把手，看它 5×5
    # 邻域：只有"整个邻域都在半径外"的那些才有资格要求零改动（贴着半径边界
    # 的把手本来就在影响范围内，动是对的）。
    far_handles = {}
    skipped = 0
    for index in range(1, len(home)):
        cx, cy = int(home[index][0]), int(home[index][1])
        x0, x1 = max(0, cx - 2), min(width, cx + 3)
        y0, y1 = max(0, cy - 2), min(height, cy + 3)
        window = np.s_[y0:y1, x0:x1]
        if bool(far[window].all()):
            far_handles[index] = int(changed[window].sum())
        else:
            skipped += 1
    ok("局部性：影响半径外的把手四周**逐字节不动**（不再从别的节点拉出折线）",
       not any(far_handles.values()) and len(far_handles) >= 3,
       f"半径外把手邻域改动 {far_handles}（另有 {skipped} 个把手落在半径内）")

    # ---- 6. 不自交：雅可比行列式处处 > 0 ----
    def min_det(cage_home, cage_dst, box_w, box_h):
        """位移场的雅可比行列式最小值（≤ 0 就是折了/漩涡了）。"""
        got = cw.moved_handles(cage_home, cage_dst)
        if got is None:
            return 1.0
        centres, weights, reach = got
        xs = np.arange(box_w, dtype=float)
        ys = np.arange(box_h, dtype=float)
        shift_x, shift_y = cw._lattice_field(centres, weights, reach, xs, ys)
        map_x = xs[None, :] + shift_x
        map_y = ys[:, None] + shift_y
        du = [np.gradient(map_x, axis=1), np.gradient(map_x, axis=0),
              np.gradient(map_y, axis=1), np.gradient(map_y, axis=0)]
        return float((du[0] * du[3] - du[1] * du[2]).min())

    dets = {}
    for tag, move in (("小拖", (6.0, 4.0)), ("中拖", (12.0, 8.0)),
                      ("大拖", (35.0, 26.0)), ("往外拖", (-30.0, -22.0))):
        target = list(home)
        target[0] = move
        dets[tag] = round(min_det(home, target, width, height), 3)
    ok("不自交：各种幅度（含往外拖）位移场雅可比行列式处处 > 0（无漩涡）",
       all(value > 0.0 for value in dets.values()),
       f"各情形最小行列式 {dets}")

    # ---- 7. 近处大、远处小 ----
    # ⚠️ 位移要从**场**上量，不能从图上读：靠近顶边的目标像素会去图上外采样
    #    （内容被拉出画布 → 填白），读回来是 255，量出来是假位移。
    axis_x = np.arange(width, dtype=float)
    axis_y = np.arange(height, dtype=float)
    shift_x, shift_y = cw._lattice_field(
        handles[0], handles[1], handles[2], axis_x, axis_y)
    mag = np.hypot(shift_x, shift_y)
    column = mag[8:, 12]              # 从被拖的把手出发，沿 +y 往外
    ok("近处大、远处小：把手处位移 = 拖动距离（φ(0)=1）",
       abs(mag[8, 12] - drag) < 1e-6,
       f"把手处 {mag[8, 12]:.3f}px vs 拖动 {drag:.3f}px")
    ok("近处大、远处小：沿被拖的方向位移单调不增、半径外归零（「像扯弹簧」）",
       bool(np.all(np.diff(column) <= 1e-9)) and column[-1] == 0.0,
       f"位移序列 {np.round(column[::10], 2)} …末值 {column[-1]}")
    ok("近处大、远处小：把手附近位移 > 远端",
       column[0] > column[-2] + 3.0,
       f"把手处 {column[0]:.2f}px vs 远端 {column[-2]:.2f}px")

    # ---- 8. 往外拖＝拉伸（用户报过"只能向内，不能向外"） ----
    out_drag = list(home)
    out_drag[0] = (-30.0, -22.0)
    out_handles = cw.moved_handles(home, out_drag)
    far_out = np.hypot(coords_x + 30.0, coords_y + 22.0) > out_handles[2] + 1.0
    stretched = cw.deform(probe_img, home, out_drag)
    ok("往外拖：图片正常产出（没黑没空），且影响半径外逐字节原样",
       stretched.dtype == np.uint8 and stretched.shape == probe_img.shape
       and bool((stretched[far_out] == probe_img[far_out]).all()),
       f"半径外改动 {int((stretched != probe_img).any(axis=2)[far_out].sum())} 像素")
    # 往外拉＝放大：角落采样到的源坐标被推向图内（s(p) > p）
    ok("往外拖：角落内容被**放大**（采样源坐标被推向图内）",
       float(stretched[5, 5, 0]) > 5.0 and float(stretched[5, 5, 1]) > 5.0,
       f"(5,5) 取到源坐标 ({stretched[5, 5, 0]}, {stretched[5, 5, 1]})")

    # ---- 9. 恒等笼逐字节还原 + 加点中性 ----
    rng = np.random.default_rng(7)
    noisy = rng.integers(0, 255, (40, 51, 3), dtype=np.uint8)
    exact = {}
    for per_side in (1, 2, 3):
        cage_n = cw.perimeter_cage((0.0, 0.0, 50.0, 40.0), per_side)
        same = cw.deform(noisy, cage_n, cage_n)
        exact[f"矩形{per_side}"] = int(
            np.abs(same.astype(int) - noisy.astype(int)).max())
    odd = [(2.0, 3.0), (45.0, 7.0), (30.0, 37.0)]
    same = cw.deform(noisy, odd, odd)
    exact["三角形"] = int(np.abs(same.astype(int) - noisy.astype(int)).max())
    ok("恒等笼逐字节还原原图（矩形 3 种疏密 + 三角形非矩形笼）",
       not any(exact.values()), f"最大差 {exact}")

    extra_home = list(home)
    extra_dst = list(pulled)
    extra_spot = ((home[0][0] + home[1][0]) / 2.0,
                  (home[0][1] + home[1][1]) / 2.0)
    extra_home.insert(1, extra_spot)      # 原位与当前位置**同一个坐标**
    extra_dst.insert(1, extra_spot)
    with_extra = cw.deform(probe_img, extra_home, extra_dst)
    ok("加点中性：在笼上插一个把手（原位=当前位置）形变逐字节不变",
       bool((with_extra == out).all()),
       f"加点前后差异 {int((with_extra != out).any(axis=2).sum())} 像素")

    # ---- 10. 影响范围与 warp_region 一致 ----
    region = cw.warp_region(home, pulled, None, width=width, height=height)
    x0, y0, x1, y1 = region
    inside_region = int(changed[y0:y1, x0:x1].sum())
    ok("warp_region：改动像素全部落在它给的框里（画布预览就贴这个框）",
       inside_region == int(changed.sum()) and x1 > x0 and y1 > y0,
       f"框 {region} 内改动 {inside_region} / 共 {int(changed.sum())}")
    ok("warp_region：没动过 → 空框 (0,0,0,0)（直接跳过，不重算）",
       cw.warp_region(home, home, None, width=width, height=height)
       == (0, 0, 0, 0)
       and cw.warp_region(home, home, None, width=width, height=height)
       == cw.warp_region([(0.0, 0.0)], [(0.0, 0.0)], None,
                         width=width, height=height),
       "")
    ok("influence_radius：与 moved_handles 给的一致",
       abs(cw.influence_radius(home, pulled) - radius) < 1e-9
       and cw.influence_radius(home, home) == 0.0,
       f"{cw.influence_radius(home, pulled):.3f} vs {radius:.3f}")

    # ---- 11. 降本机制（稀格 + 步长自适应） ----
    span = 4000 * 3000
    step = max(1, int(math.ceil(math.sqrt(span / cw.FIELD_MAX))))
    grid_x = cw._lattice(0.0, 4000.0, step)
    grid_y = cw._lattice(0.0, 3000.0, step)
    points = grid_x.size * grid_y.size
    ok("稀格求场：整页 4000×3000 的位移场格点数 ≤ FIELD_MAX（1.2 倍容差）",
       points <= cw.FIELD_MAX * 1.2,
       f"步长 {step}，格点 {grid_x.size}×{grid_y.size} = {points}")
    ok("稀格求场：格点覆盖到区间右端（末点 = 右端 - 1）",
       abs(float(grid_x[-1]) - 3999.0) < 1e-9
       and abs(float(grid_y[-1]) - 2999.0) < 1e-9,
       f"末点 ({grid_x[-1]}, {grid_y[-1]})")
    ok("cage_moved：没动过 → False；动过 → True",
       cw.cage_moved(home, home) is False
       and cw.cage_moved(home, pulled) is True, "")

    # ---- 12. 实际代价：局部 = 只算一小块 ----
    # 整页 4000×3000 上拖 60px：影响半径 188px → 只算 249×234，
    # 不应把整幅都重采样一遍（那是 3.1s）。
    big = np.zeros((3000, 4000, 3), dtype=np.uint8)
    big[::40, :, :] = 255
    big[:, ::40, :] = 255
    big_home = cw.perimeter_cage((0.0, 0.0, 4000.0, 3000.0), 2)
    big_dst = list(big_home)
    big_dst[0] = (60.0, 45.0)
    started = time.perf_counter()
    warped = cw.deform(big, big_home, big_dst)
    elapsed = time.perf_counter() - started
    ok("局部性⇒代价：整页图上拖 60px 只重采样影响半径那一块（< 1.5s）",
       elapsed < 1.5 and warped.shape == big.shape
       and int((warped != big).any(axis=2).sum()) > 0,
       f"耗时 {elapsed:.3f}s，改动像素 "
       f"{int((warped != big).any(axis=2).sum())}")

    # ---- 13. QImage 版（编辑器实际调用的一层）：保透明是硬要求 ----
    from PySide6.QtGui import QColor, QImage

    qimage = QImage(60, 40, QImage.Format.Format_ARGB32)
    qimage.fill(QColor("#ffffff"))
    for x in range(40, 50):          # 白色背景上一根 10px 宽的黑竖条
        for y in range(40):
            qimage.setPixelColor(x, y, QColor("#000000"))
    same_cage = cw.perimeter_cage((0.0, 0.0, 59.0, 39.0), 1)
    identical = cw.deform_qimage(qimage, same_cage, same_cage)
    unchanged = all(
        identical.pixelColor(x, y).rgba() == qimage.pixelColor(x, y).rgba()
        for y in range(0, 40, 5) for x in range(0, 60, 5))
    ok("deform_qimage：恒等笼原样返回（ARGB32、尺寸不变）",
       identical.width() == 60 and identical.height() == 40 and unchanged,
       f"尺寸 {identical.width()}×{identical.height()}，全等 {unchanged}")

    # 黑竖条在 x=40~49；把笼的左边界往右挪 → 竖条跟着往右走
    dragged = cw.deform_qimage(
        qimage, same_cage,
        [(0.0, 0.0), (59.0, 0.0), (59.0, 39.0), (0.0, 39.0)])
    ok("deform_qimage：没拖动就是原样（把手全在原位）",
       all(dragged.pixelColor(x, 20).rgba() == qimage.pixelColor(x, 20).rgba()
           for x in range(60)),
       "整行比对")

    # ⚠️ 用户报的"变形后图片变成黑色"：白底透明 PNG 走一圈必须**仍然是透明的**，
    #    绝不能出现大片不透明纯黑。这两条专盯 alpha 往返。
    def opaque_count(img):
        return sum(1 for y in range(40) for x in range(60)
                   if img.pixelColor(x, y).alpha() > 200)

    # ⚠️ 只拖**一个**把手：拖两个会触发防自交下限把半径抬到 46px，竖条就被
    #    合法地影响了（那是算错，不是 bug）。这里要的是"远处一根毛都不动"。
    left_pull = [(8.0, 3.0), (59.0, 0.0), (59.0, 39.0), (0.0, 39.0)]

    # 形态 A：整幅全透明（"这一页没去底色产物残留"的极端形态）。
    # 老实现会把它整片变成不透明纯黑——这是"变黑"最狠的复现。
    blank = QImage(60, 40, QImage.Format.Format_ARGB32)
    blank.fill(QColor(0, 0, 0, 0))
    massaged = cw.deform_qimage(blank, same_cage, left_pull)
    alive = [(x, y) for y in range(40) for x in range(60)
             if massaged.pixelColor(x, y).alpha() != 0]
    ok("deform_qimage：整幅全透明的图变形后仍**全透明**（最狠的变黑复现）",
       not alive, f"变成不透明的像素 {len(alive)} 个，样本 {alive[:3]}")

    # 形态 B：透明底 + 一根不透明黑竖条（第三步产物的真实形态）。
    # 拖左边缘向右 10px，只该影响左侧一小块：不透明像素总数必须**一个不多**
    # （老实现会把 2400 个像素全变成不透明）。
    clear = QImage(60, 40, QImage.Format.Format_ARGB32)
    clear.fill(QColor(0, 0, 0, 0))
    for x in range(40, 50):
        for y in range(40):
            clear.setPixelColor(x, y, QColor("#000000"))
    before_opaque = opaque_count(clear)
    shifted = cw.deform_qimage(clear, same_cage, left_pull)
    ok("deform_qimage：**透明底保持透明**（不透明像素不许变多）",
       opaque_count(shifted) == before_opaque and before_opaque == 400,
       f"不透明像素 形变前 {before_opaque} → 形变后 {opaque_count(shifted)}"
       f"（全幅共 2400；老实现会变成 2400）")
    ok("deform_qimage：透明图上内容原样保留（alpha 与颜色都不被动）",
       all(shifted.pixelColor(x, y).alpha() == 255
           and shifted.pixelColor(x, y).value() < 20
           for y in range(0, 40, 4) for x in range(40, 50, 2))
       and all(shifted.pixelColor(x, y).alpha() == 0
               for y in range(0, 40, 4) for x in range(55, 60)),
       f"竖条 (44,20) a={shifted.pixelColor(44, 20).alpha()} "
       f"v={shifted.pixelColor(44, 20).value()} / "
       f"远背景 (57,20) a={shifted.pixelColor(57, 20).alpha()}")

    # ---- progress 回调：分块上报 + 可中止（大图烘焙的"进度/取消"基础） ----
    # ⚠️ 直接测 ``deform`` 并显式给小 ``block``：形变只处理影响框（RBF 是局部
    #    的），框内像素常常不够一个默认分块(262144) ⇒ 一次就完事，"分块上报"
    #    这条根本测不到。给个小 block 才能稳定拿到多次回调。
    import numpy as _np

    canvas_arr = _np.full((120, 160, 3), 255, dtype=_np.uint8)
    canvas_arr[20:50, 60:90] = 0            # 一块黑
    box_cage = cw.perimeter_cage((0.0, 0.0, 159.0, 119.0), 2)
    pull = list(box_cage)
    pull[0] = (30.0, 20.0)                  # 拖左上角，制造形变
    ticks = []
    done = cw.deform(canvas_arr, box_cage, pull, block=1024,
                     progress=lambda d, t: ticks.append((d, t)))
    ok("deform：progress 分块上报（多次回调、总量一致、最后到满）",
       done is not None and len(ticks) >= 3
       and all(t == ticks[0][1] for _, t in ticks)
       and ticks[-1][0] == ticks[-1][1]
       and all(ticks[i][0] <= ticks[i + 1][0] for i in range(len(ticks) - 1)),
       f"回调 {len(ticks)} 次，样本 {ticks[:1]}…{ticks[-1:]}")

    aborted = cw.deform(canvas_arr, box_cage, pull, block=1024,
                        progress=lambda d, t: False)
    ok("deform：progress 返回 False 即中止（返回 None，不落地半成品）",
       aborted is None, f"aborted={aborted!r}")

    partial = []
    cw.deform(canvas_arr, box_cage, pull, block=1024,
              progress=lambda d, t: partial.append((d, t)) or False)
    ok("deform：中止发生在第一次回调之后（取消能立刻生效）",
       len(partial) == 1, f"回调 {len(partial)} 次：{partial}")

    # ---- grow：最终画布 = 形变后**内容外框**（用户 2026-10-02 的约束 2）----
    # 用户口径：「不要截掉超出原边界的内容」「一切以新图为准，老图不要了」。
    # 变换笼是**局部**形变：影响半径外的像素逐字节不动、仍占 [0,W]×[0,H]，
    # 所以它是结果的一部分，必须留全 ⇒ 外框 = 原图边界 ∪ 被拖把手落点。
    box_cr = cw.perimeter_cage((0.0, 0.0, 199.0, 119.0), 2)
    inside = list(box_cr)
    inside[0] = (40.0, 30.0)               # 左上角把手**向内**拖
    ok("content_region：向内拖把手不外扩（内容没跑出去，仍是原图边界）",
       cw.content_region(box_cr, inside, None, width=200, height=120)
       == (0, 0, 200, 120),
       f"{cw.content_region(box_cr, inside, None, width=200, height=120)}")

    outward = list(box_cr)
    outward[0] = (-25.0, -18.0)            # 左上角把手**向外**拖
    reg_out = cw.content_region(box_cr, outward, None, width=200, height=120)
    ok("content_region：向外拖把手按落点外扩（含负坐标，不夹画布）",
       reg_out[0] <= -25 and reg_out[1] <= -18
       and reg_out[2] == 200 and reg_out[3] == 120,
       f"{reg_out}")
    ok("content_region：不叠影响半径（拖 25px 不许外扩 60px）",
       reg_out[0] >= -26 and reg_out[1] >= -19,
       f"左上 {reg_out[:2]}（若叠了 RBF 影响半径会到 −40 以下）")

    ok("content_region：没动过 → 原图边界（恒等笼不改变画布）",
       cw.content_region(box_cr, list(box_cr), None, width=200, height=120)
       == (0, 0, 200, 120), "")

    # deform(grow=True)：返回 (结果, origin)，尺寸 = 外框，且图外那块真的画进去了
    arr_g = _np.full((120, 200, 3), 255, dtype=_np.uint8)
    arr_g[0:20, 0:20] = 0                  # 左上角一块黑（会被拖出去）
    grown, origin_g = cw.deform(arr_g, box_cr, outward, grow=True)
    ok("deform(grow=True)：返回 (结果, origin)，画布按内容外框放大",
       grown is not None and origin_g == (reg_out[0], reg_out[1])
       and grown.shape[0] == reg_out[3] - reg_out[1]
       and grown.shape[1] == reg_out[2] - reg_out[0],
       f"origin={origin_g} shape={None if grown is None else grown.shape}")
    ok("deform(grow=True)：原图内容整体按 -origin 平移贴入新画布",
       grown is not None
       and int(grown[-origin_g[1] + 100, -origin_g[0] + 100, 0]) == 255,
       "远场像素（原图 100,100）应落在新画布 (100-ox, 100-oy) 且仍为白")

    ident_g, ident_o = cw.deform(arr_g, box_cr, list(box_cr), grow=True)
    ok("deform(grow=True)：恒等笼 → origin (0,0)、尺寸不变、逐字节还原",
       ident_g is not None and ident_o == (0, 0)
       and ident_g.shape == arr_g.shape
       and bool((ident_g == arr_g).all()),
       f"origin={ident_o} shape={None if ident_g is None else ident_g.shape}")
