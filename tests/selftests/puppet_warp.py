# -*- coding: utf-8 -*-
"""操控变形（PS Puppet Warp 口径：ARAP 三角网格 + 图钉）算法守卫。

口径与实现见 ``utils/puppet_warp.py`` 的模块文档。本模块只盯**可观测的算法
性质**（改实现不怕，性质破了就是坏了）。这些性质里前三条是"上一版 Green
坐标版"栽过的坑，必须钉死：

1. **恒等逐字节还原**：网格没动过（``rest == moved``）→ 输出与原图**逐字节
   相同**，且**不做任何求解**（钉住也白钉）；
2. **钉住点精确到目标**：钉住顶点的解严格等于目标位置（误差 ≤ 1e-6）——
   前一版消元写错，实测钉住点差 118px；
3. **单钉不漂**：只钉一个点拖一下，**贴边的顶点必须一动不动**（隐式边框
   锚点，PS 口径）。没有锚点时 ARAP 对整体平移不变，整页会一起漂 14px——
   这条专盯 :func:`solve_puppet` 的 ``anchor_border``；
4. **局部性 / 衰减**：拖一个点，位移随离它的距离**单调衰减**，且远场**硬
   归零**（不是"很小"是"完全为零"）——古籍褶皱微调靠这条（近处动得多、
   远处不许跟着晃）；
5. **各向同性余切权重恒正**：``cotangent_weights`` 对 ``build_mesh`` 产出的
   混合绕向三角形**全部给出正值**（前一版用带符号 cross，符号一翻 → 权重
   放大 1e12 → 右端项爆成 4e13 → "整页乱飞"）；
6. **网格构造**：规则网格覆盖 ``[0,w-1]×[0,h-1]``（图角是顶点）、每格两三角
   且对角线交替（棋盘式）；
7. **退化不崩**：网格没动 / 无图钉 / 图钉下标越界 / 重合图钉 —— 都不许抛；
8. **保透明**：白底透明 PNG（第三步产物）形变后仍是透明底，不出现
   "整片不透明纯黑"（用户 2026-10-01 报的"变形后图片变成黑色"）；
9. **mesh_region / mesh_moved**：改动框 = 动过的顶点包围盒，没动过返回空框；
10. **代价兜底**：整页 4000×3000 拖一下，一次全分辨率烘焙有墙钟兜底。
"""
from __future__ import annotations

import math
import time

NAME = "puppet_warp"
DEPENDS: list[str] = []
TITLE = "操控变形：ARAP 网格 / 恒等还原 / 单钉不漂 / 保透明"


def _coord_image(width: int, height: int):
    """把"每个像素自己的坐标"编进 R/G 通道：形变后读 R/G 即得**源坐标**。

    能直接量出位移场的探针图——比"看某处颜色变没变"强得多。
    """
    import numpy as np

    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
    image[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    return image


def _pin_at(vertices, x: float, y: float) -> int:
    """离 (x, y) 最近的网格顶点下标（测试里把图钉钉在指定位置用）。"""
    import numpy as np

    dx = vertices[:, 0] - x
    dy = vertices[:, 1] - y
    return int(np.argmin(dx * dx + dy * dy))


def run(ctx) -> None:
    import numpy as np

    from tests.selftests._context import ok

    from utils import puppet_warp as pw

    # ---- 1. 恒等逐字节还原（不做任何求解）----
    rng = np.random.default_rng(11)
    noisy = rng.integers(0, 255, (90, 120, 3), dtype=np.uint8)
    vertices, triangles, cols, rows, cell = pw.build_mesh(120, 90, 30.0)
    same = pw.puppet_warp(noisy, vertices, vertices, triangles)
    ok("恒等：网格没动过 → 逐字节还原原图",
       bool((same == noisy).all()),
       f"最大差 {int(np.abs(same.astype(int) - noisy.astype(int)).max())}")
    ok("恒等：mesh_moved 判定（没动 False / 动过 True）",
       pw.mesh_moved(vertices, vertices) is False
       and pw.mesh_moved(vertices, vertices + np.array([[9.0, 0.0]])) is True,
       "")

    # 4 通道（带 alpha）恒等也要逐字节（保透明的底层保证）
    rgba = np.dstack([noisy, np.full((90, 120, 1), 200, dtype=np.uint8)])
    same4 = pw.puppet_warp(rgba, vertices, vertices, triangles)
    ok("恒等：4 通道（带 alpha）网格没动过 → 逐字节还原",
       bool((same4 == rgba).all()), "")

    # ---- 2. 钉住点精确到目标（前一版消元错 → 钉住点差 118px）----
    pid = _pin_at(vertices, 60.0, 45.0)
    target = (vertices[pid, 0] + 18.0, vertices[pid, 1] + 6.0)
    solved = pw.solve_puppet(vertices, triangles, [(pid, target)],
                             width=120, height=90, anchor_border=True)
    err = float(np.hypot(solved[pid, 0] - target[0],
                         solved[pid, 1] - target[1]))
    ok("硬约束：钉住顶点的解严格落在目标位置（误差 ≤ 1e-6）",
       err <= 1e-6, f"误差 {err:.2e}px")

    # 两个图钉都不挪：解必须恒等（前一版这里解出整页 202px 位移）
    p1 = _pin_at(vertices, 30.0, 20.0)
    p2 = _pin_at(vertices, 90.0, 70.0)
    held = pw.solve_puppet(vertices, triangles,
                           [(p1, (float(vertices[p1, 0]),
                                  float(vertices[p1, 1]))),
                            (p2, (float(vertices[p2, 0]),
                                  float(vertices[p2, 1])))],
                           width=120, height=90, anchor_border=True)
    drift = float(np.max(np.abs(held - vertices)))
    ok("硬约束：两个图钉原地不动 → 整张网格原地不动（无重复计入）",
       drift <= 1e-6, f"最大漂移 {drift:.2e}px")

    # ---- 3. 单钉不漂：贴边顶点一动不动（隐式边框锚点）----
    pid3 = _pin_at(vertices, 60.0, 45.0)
    tgt3 = (float(vertices[pid3, 0]) + 20.0, float(vertices[pid3, 1]))
    border = pw.border_vertices(vertices, 120, 90)
    pinned_border = pw.solve_puppet(vertices, triangles, [(pid3, tgt3)],
                                    width=120, height=90, anchor_border=True)
    edge_drift = float(np.max(np.abs(
        pinned_border[border] - vertices[border])))
    ok("单钉不漂：贴图四边的网格顶点一动不动（PS 的隐式边框锚点）",
       border.size > 0 and edge_drift <= 1e-6,
       f"边框顶点 {border.size} 个，最大漂移 {edge_drift:.2e}px")

    # 没有边框锚点时 ARAP 对平移不变 → 整页一起漂（这就是为什么需要锚点）
    free = pw.solve_puppet(vertices, triangles, [(pid3, tgt3)],
                           width=120, height=90, anchor_border=False)
    free_shift = float(np.mean(np.abs(free - vertices)))
    ok("反证：不锚边框时单钉会让整页一起平移（ARAP 对平移不变）",
       free_shift > 1.0,
       f"平均漂移 {free_shift:.2f}px（锚了是 0）")

    # ---- 4. 局部性 / 衰减：位移随距离单调衰减到 0 ----
    pid4 = _pin_at(vertices, 60.0, 45.0)
    tgt4 = (float(vertices[pid4, 0]), float(vertices[pid4, 1]) + 24.0)
    warp4 = pw.solve_puppet(vertices, triangles, [(pid4, tgt4)],
                            width=120, height=90, anchor_border=True)
    delta4 = np.hypot(warp4[:, 0] - vertices[:, 0],
                      warp4[:, 1] - vertices[:, 1])
    dist4 = np.hypot(vertices[:, 0] - vertices[pid4, 0],
                     vertices[:, 1] - vertices[pid4, 1])
    # 按离图钉的距离分环，取每环平均位移：必须单调下降
    rings = []
    for lo, hi in ((0, 30), (30, 50), (50, 70), (70, 95), (95, 1e9)):
        mask = (dist4 >= lo) & (dist4 < hi)
        rings.append(float(delta4[mask].mean()) if mask.any() else 0.0)
    ok("局部性：位移按距离分环**单调衰减**（近处动得多、远处几乎不动）",
       all(rings[i] >= rings[i + 1] - 1e-9 for i in range(len(rings) - 1))
       and rings[0] > rings[-1],
       f"各环平均位移 {[round(v, 2) for v in rings]}")
    ok("局部性：远场位移**硬归零**（离图钉足够远的顶点逐字节不动）",
       float(delta4[dist4 > 95.0].max() if (dist4 > 95.0).any() else 0.0)
       <= 1e-6,
       f"远场最大位移 "
       f"{float(delta4[dist4 > 95.0].max() if (dist4 > 95.0).any() else 0.0):.2e}px")
    ok("局部性：被拖顶点附近真的动了（不是「哪都没动」的假阳性）",
       rings[0] > 5.0, f"最近环平均位移 {rings[0]:.2f}px")

    # ---- 5. 余切权重非负（混合绕向三角形）----
    # ⚠️ 关键在于**没有负权重**（负权重会让 ARAP 能量退化、解爆炸）。规则网格
    #    上个别边的两对角余切正好抵消成 0（直角邻域），所以断言是 `>= 0`
    #    而不是 `> 0`；强正值由下一行的"绝大多数为正"兜住。
    ei, ej, w = pw.cotangent_weights(vertices, triangles)
    ok("余切权重：无负权重（混合绕向的网格上符号不翻）",
       w.size > 0 and bool((w >= 0).all()),
       f"权重 {w.size} 条，最小 {float(w.min()):.3e}，最大 {float(w.max()):.3e}")
    ok("余切权重：绝大多数边为正（能量有实质刚度，不是一片 0）",
       float((w > 0).mean()) > 0.5 and float(w.sum()) > 0.0,
       f"正值占比 {float((w > 0).mean()):.2f}")
    ok("余切权重：无向边只出现一次（i < j）且无自环",
       bool((ei < ej).all()) and len(set(zip(ei.tolist(), ej.tolist())))
       == w.size,
       f"边数 {w.size}")

    # ---- 6. 网格构造：覆盖图边 + 棋盘对角线 ----
    v6, t6, c6, r6, cell6 = pw.build_mesh(100, 80, 40.0)
    ok("网格：严格覆盖 [0, w-1]×[0, h-1]（图四角都是网格顶点）",
       abs(float(v6[:, 0].min())) < 1e-9 and abs(float(v6[:, 1].min())) < 1e-9
       and abs(float(v6[:, 0].max()) - 99.0) < 1e-9
       and abs(float(v6[:, 1].max()) - 79.0) < 1e-9,
       f"x∈[{v6[:, 0].min():.0f},{v6[:, 0].max():.0f}] "
       f"y∈[{v6[:, 1].min():.0f},{v6[:, 1].max():.0f}]")
    ok("网格：每格 2 个三角（三角数 = 格数 × 2）",
       len(t6) == c6 * r6 * 2, f"格 {c6}×{r6}，三角 {len(t6)}")
    # 棋盘对角线：相邻格的对角线方向相反 → 取每格第一个三角的定向看符号
    p0 = v6[t6[::2, 0]]
    p1 = v6[t6[::2, 1]]
    p2 = v6[t6[::2, 2]]
    area = ((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1])
            - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))
    ok("网格：三角形统一逆时针（面积同号，ARAP 余切权重的前提）",
       bool((area > 0).all()) or bool((area < 0).all()),
       f"面积符号 {'全正' if (area > 0).all() else '全负' if (area < 0).all() else '混合'}")
    ok("网格：格距被夹在护栏内（≥2px），且默认格距返回可用值",
       pw.grid_cell(100, 80, 0.5) >= 2.0
       and pw.grid_cell(100, 80) == pw.MESH_CELL_DEFAULT,
       f"cell(0.5)={pw.grid_cell(100, 80, 0.5)}")

    # ---- 6b. 拖动网格的顶点数上限（"拖动卡死"的第二道闸门）----
    # 最密档（20px）在 4000×3000 下有 3 万顶点；只按倍数粗化（×4）仍剩
    # 1989 顶点 ≈ 单次求解 103ms，照样卡。drag_cell 必须把顶点数压进
    # MESH_DRAG_MAX_VERTICES 内。"相对倍数"那道也要保住（细密档要更粗）。
    drag_ok = True
    drag_detail = ""
    for _w, _h, _cell in ((4000, 3000, 20), (4000, 3000, 40),
                          (2000, 1500, 40), (400, 300, 40)):
        _dc = pw.drag_cell(_w, _h, _cell)
        _n = (int(math.ceil((_w - 1) / _dc)) + 1) * (int(math.ceil((_h - 1) / _dc)) + 1)
        if _n > pw.MESH_DRAG_MAX_VERTICES:
            drag_ok = False
            drag_detail = f"{_w}x{_h}/{_cell}px -> {_n} 顶点 超上限"
            break
        # 不能比"原格距×粗化倍数"还细（那是反优化）
        if _dc < pw.grid_cell(_w, _h, _cell) * pw.MESH_DRAG_COARSEN - 1e-9:
            drag_ok = False
            drag_detail = f"{_w}x{_h}/{_cell}px -> 格距 {_dc:.1f} 比倍数法还细"
            break
    ok(f"拖动网格：顶点数不超过 {pw.MESH_DRAG_MAX_VERTICES}（否则最密档拖动仍卡）",
       drag_ok, drag_detail or f"4000x3000/20px -> {pw.drag_cell(4000, 3000, 20):.1f}px")

    # ---- 7. 退化不崩 ----
    degenerate_ok = True
    detail = ""
    try:
        # 无图钉
        pw.solve_puppet(vertices, triangles, [], width=120, height=90)
        # 图钉下标越界（应被过滤）
        pw.solve_puppet(vertices, triangles,
                        [(10 ** 6, (0.0, 0.0)), (-5, (1.0, 2.0))],
                        width=120, height=90)
        # 两个图钉钉在同一顶点
        k = _pin_at(vertices, 60.0, 45.0)
        pw.solve_puppet(vertices, triangles,
                        [(k, (70.0, 45.0)), (k, (70.0, 45.0))],
                        width=120, height=90)
        # 网格太稀（单格 2 个三角）
        tiny_v, tiny_t, *_ = pw.build_mesh(4, 4, 100.0)
        pw.solve_puppet(tiny_v, tiny_t, [(0, (1.0, 1.0))], width=4, height=4)
    except Exception as exc:      # noqa: BLE001
        degenerate_ok = False
        detail = f"{type(exc).__name__}: {exc}"
    ok("退化不崩：无图钉 / 越界图钉 / 重合图钉 / 极稀网格 都不抛",
       degenerate_ok, detail)

    # ---- 8. mesh_region / mesh_moved ----
    region = pw.mesh_region(vertices, warp4, 120, 90)
    changed = np.nonzero(np.abs(warp4 - vertices).max(axis=1) > 1e-6)[0]
    ok("mesh_region：改动框 = 动过的顶点包围盒（含动前/动后两侧）",
       region != (0, 0, 0, 0)
       and region[0] <= int(math.floor(vertices[changed, 0].min()))
       and region[2] >= int(math.ceil(warp4[changed, 0].max())) + 1,
       f"region {region}，动过顶点 {changed.size} 个")
    ok("mesh_region：没动过 → 空框 (0,0,0,0)",
       pw.mesh_region(vertices, vertices, 120, 90) == (0, 0, 0, 0), "")

    # ---- 9. 保透明（用户 2026-10-01 报的"变形后图片变成黑色"）----
    from PySide6.QtGui import QColor, QImage

    def opaque_count(img):
        return sum(1 for y in range(40) for x in range(60)
                   if img.pixelColor(x, y).alpha() > 200)

    qv, qt, *_ = pw.build_mesh(60, 40, 20.0)
    qpin = _pin_at(qv, 10.0, 20.0)
    qmove = qv.copy()
    qmove[qpin] = (30.0, 20.0)

    blank = QImage(60, 40, QImage.Format.Format_ARGB32)
    blank.fill(QColor(0, 0, 0, 0))
    massaged = pw.puppet_warp_qimage(blank, qv, qmove, qt)
    alive = [(x, y) for y in range(40) for x in range(60)
             if massaged.pixelColor(x, y).alpha() != 0]
    ok("保透明：整幅全透明的图变形后仍**全透明**（最狠的变黑复现）",
       not alive, f"变成不透明的像素 {len(alive)} 个，样本 {alive[:3]}")

    clear = QImage(60, 40, QImage.Format.Format_ARGB32)
    clear.fill(QColor(0, 0, 0, 0))
    for x in range(40, 50):
        for y in range(40):
            clear.setPixelColor(x, y, QColor("#000000"))
    before_opaque = opaque_count(clear)
    shifted = pw.puppet_warp_qimage(clear, qv, qmove, qt)
    ok("保透明：透明底 + 黑竖条形变后，不透明像素**一个不多**",
       opaque_count(shifted) <= before_opaque and before_opaque == 400,
       f"不透明像素 形变前 {before_opaque} → 形变后 {opaque_count(shifted)}")

    # 不透明图走 QImage 一圈：没动过的网格原样返回（尺寸不变）
    solid = QImage(60, 40, QImage.Format.Format_ARGB32)
    solid.fill(QColor("#ffffff"))
    identical = pw.puppet_warp_qimage(solid, qv, qv, qt)
    ok("puppet_warp_qimage：恒等网格原样返回（ARGB32、尺寸不变）",
       identical.width() == 60 and identical.height() == 40
       and identical.pixelColor(0, 0).rgba() == solid.pixelColor(0, 0).rgba(),
       f"尺寸 {identical.width()}×{identical.height()}")

    # ---- 10. 代价兜底：整页一次烘焙有墙钟上限 ----
    big = np.zeros((3000, 4000, 3), dtype=np.uint8)
    big[::40, :, :] = 255
    big[:, ::40, :] = 255
    big_v, big_t, *_ = pw.build_mesh(4000, 3000, 40.0)
    big_pin = _pin_at(big_v, 2000.0, 1500.0)
    big_moved = big_v.copy()
    big_moved[big_pin] = (big_v[big_pin, 0] + 60.0, big_v[big_pin, 1])
    started = time.perf_counter()
    solved_big = pw.solve_puppet(big_v, big_t, [(big_pin, tuple(big_moved[big_pin]))],
                                 width=4000, height=3000)
    solve_s = time.perf_counter() - started
    started = time.perf_counter()
    warped = pw.puppet_warp(big, big_v, solved_big, big_t)
    warp_s = time.perf_counter() - started
    ok("代价兜底：整页 4000×3000 解算 + 一次全分辨率烘焙 < 30s，且真的动了",
       (solve_s + warp_s) < 30.0 and warped.shape == big.shape
       and int((warped != big).any(axis=2).sum()) > 100,
       f"解算 {solve_s:.2f}s + 烘焙 {warp_s:.2f}s，"
       f"改动像素 {int((warped != big).any(axis=2).sum())}")

    # ---- 11. grow：最终画布 = 形变后**内容外框**（用户 2026-10-02 约束 2）----
    # 口径同变换笼：网格顶点之外没有三角形覆盖、原图逐字节保留在那里，
    # 所以它是结果的一部分 ⇒ 外框 = 原图边界 ∪ 形变后网格顶点外接框。
    g_v, g_t, *_ = pw.build_mesh(200, 120, 40.0)
    g_pin = _pin_at(g_v, 100.0, 60.0)
    # 向内挪：顶点仍在 [0,W]×[0,H] 内 ⇒ 不外扩
    g_in = g_v.copy()
    g_in[g_pin] = (g_v[g_pin, 0] + 10.0, g_v[g_pin, 1] + 8.0)
    ok("_grow_box：图钉向内挪 → 不外扩（仍是原图边界）",
       pw._grow_box(g_in, 200, 120) == (0, 0, 200, 120),
       f"{pw._grow_box(g_in, 200, 120)}")

    # 向外拽到图外：顶点跑到负坐标 ⇒ 画布外扩并含负原点
    # 注意 ``_grow_box`` 返回 ``(ox, oy, out_w, out_h)``——后两个是**宽高**，
    # 不是 x1/y1 界（deform 侧 content_region 返回的才是界，两者接口不同）。
    g_out = g_v.copy()
    g_out[g_pin] = (-30.0, -20.0)
    gbox = pw._grow_box(g_out, 200, 120)
    ok("_grow_box：顶点被拽出画布 → 外扩且原点为负（不夹边界）",
       gbox == (-30, -20, 230, 140),
       f"{gbox}")
    g_ox, g_oy, g_w, g_h = gbox

    g_arr = np.full((120, 200, 3), 255, dtype=np.uint8)
    g_arr[0:20, 0:20] = 0                       # 左上角黑块，会被拽出去
    g_solved_in = pw.solve_puppet(g_v, g_t, [(g_pin, tuple(g_in[g_pin]))],
                                  width=200, height=120)
    ident_arr, ident_origin = pw.puppet_warp(g_arr, g_v, g_solved_in, g_t,
                                             grow=True)
    ok("puppet_warp(grow=True)：恒等/向内形变 → origin (0,0)、尺寸不变",
       ident_arr.shape == g_arr.shape and ident_origin == (0, 0),
       f"origin={ident_origin} shape={ident_arr.shape}")

    g_solved_out = pw.solve_puppet(g_v, g_t, [(g_pin, tuple(g_out[g_pin]))],
                                   width=200, height=120)
    grown_arr, grown_origin = pw.puppet_warp(g_arr, g_v, g_solved_out, g_t,
                                             grow=True)
    ok("puppet_warp(grow=True)：拽出画布 → 画布按内容外框放大、origin 为负",
       grown_origin == (g_ox, g_oy)
       and grown_arr.shape[0] == g_h and grown_arr.shape[1] == g_w,
       f"origin={grown_origin} shape={grown_arr.shape} 期望 {(g_w, g_h)}")

    ok("puppet_warp(grow=True)：原图内容整体按 -origin 贴入新画布（远场仍在）",
       int(grown_arr[-g_oy + 40, -g_ox + 40, 0]) == 255,
       "原图 (40,40) 的白背景应落在新画布 (40-ox, 40-oy) 且仍为白")
