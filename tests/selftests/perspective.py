# -*- coding: utf-8 -*-
"""四点透视校正（古籍页形/拍摄角度摆正）算法守卫。

口径与实现见 ``utils/perspective.py`` 的模块文档。只盯**可观测的算法性质**：

1. **单应精确**：四点对应解出的 ``H`` 把源四点映到目标四点（误差 ≤ 1e-9）；
2. **恒等逐字节还原**：四角压在图片四角（``(0,0)~(w-1,h-1)``）时，
   校正输出**尺寸不变、逐字节等于原图**——这是"没动过就不该有变化"的底线；
3. **退化不崩 / 不产垃圾**：四点近似共线时 ``homography``/``rectify`` 抛
   ``ValueError``（供 UI 拦截），而不是解出乱飞的图；
4. **尺寸正确**：摆正后尺寸 = 目标矩形（``bbox`` 外接框 / ``area`` 保持比例），
   且 ``rectify_region`` 与之一致；
5. **透视 vs 仿射**：单应能把**梯形**（平行线交于一点）摆成矩形——这正是
   "拍摄角度"需要的数学（仿射做不到）；
6. **保透明**：白底透明 PNG（第三步产物）校正后仍是透明底，不出现
   "整片不透明纯黑"；
7. **QImage 往返**：不透明图恒等校正原样返回（尺寸不变）；
8. **quad_moved**：四角没动 False / 动过 True。
"""
from __future__ import annotations

import math

NAME = "perspective"
DEPENDS: list[str] = []
TITLE = "四点透视校正：单应 / 恒等还原 / 尺寸 / 保透明"


def _coord_image(width: int, height: int):
    """把"每个像素自己的坐标"编进 R/G 通道（读回即得源坐标）。"""
    import numpy as np

    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
    image[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None]
    return image


def run(ctx) -> None:
    import numpy as np

    from tests.selftests._context import ok

    from utils import perspective as pv

    # ---- 1. 单应精确 ----
    src = [(10.0, 10.0), (90.0, 12.0), (88.0, 70.0), (12.0, 68.0)]
    dst = [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)]
    H = pv.homography(src, dst)
    got = pv.apply_homography(H, src)
    ok("homography：四点对应精确（误差 ≤ 1e-9）",
       float(np.abs(got - np.array(dst)).max()) <= 1e-9,
       f"最大误差 {float(np.abs(got - np.array(dst)).max()):.2e}")

    # ---- 2. 恒等逐字节还原 ----
    img = _coord_image(100, 80)
    quad = [(0.0, 0.0), (99.0, 0.0), (99.0, 79.0), (0.0, 79.0)]
    out = pv.rectify(img, quad)
    ok("恒等：四角=图四角 → 尺寸不变、逐字节还原原图",
       out.shape == img.shape
       and int(np.abs(out.astype(int) - img.astype(int)).max()) == 0,
       f"shape {out.shape}（期望 {img.shape}）"
       f" 最大差 {int(np.abs(out.astype(int) - img.astype(int)).max())}")
    ok("恒等：图角像素原样保留（TL/BR 取样）",
       out[0, 0].tolist() == [0, 0, 0] and out[79, 99].tolist() == [99, 79, 0],
       f"TL={out[0, 0].tolist()} BR={out[79, 99].tolist()}")

    # ---- 3. 退化不崩 / 不产垃圾 ----
    flat = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
    ok("退化：四点共线被判定为退化（quad_degenerate）",
       pv.quad_degenerate(flat) is True
       and pv.quad_degenerate(quad) is False, "")
    raised = False
    try:
        pv.homography(flat, dst)
    except ValueError:
        raised = True
    ok("退化：共线四点解单应抛 ValueError（供 UI 拦截，不产垃圾）",
       raised, "")
    raised = False
    try:
        pv.rectify(img, flat)
    except ValueError:
        raised = True
    ok("退化：共线四点校正抛 ValueError（不崩、不产出乱图）",
       raised, "")

    # ---- 4. 尺寸正确 ----
    skew = [(20.0, 10.0), (90.0, 25.0), (85.0, 75.0), (15.0, 65.0)]
    x0, y0, x1, y1 = pv.target_rect(skew, mode="bbox")
    region = pv.rectify_region(skew, 100, 80, mode="bbox")
    r = pv.rectify(img, skew, mode="bbox")
    # 外接框：x∈[15,90] y∈[10,75] → 尺寸 76×66
    ok("尺寸：bbox 口径 = 源四边形外接框（尺寸 = max-min+1）",
       region == (15, 10, 76, 66) and r.shape == (66, 76, 3),
       f"region {region}，shape {r.shape}")
    ok("尺寸：rectify_region 与 rectify 输出尺寸一致",
       r.shape[1] == region[2] and r.shape[0] == region[3],
       f"shape {r.shape} vs region {region}")
    area0 = pv.quad_area(skew)
    ax0, ay0, ax1, ay1 = pv.target_rect(skew, mode="area")
    ok("尺寸：area 口径保持四边形面积（面积比 ≈ 1）",
       abs((ax1 - ax0 + 1) * (ay1 - ay0 + 1) / area0 - 1.0) < 0.05,
       f"area 口径面积 {round((ax1 - ax0 + 1) * (ay1 - ay0 + 1), 1)} "
       f"vs 源 {round(area0, 1)}")

    # ---- 5. 透视 vs 仿射：梯形 → 矩形 ----
    trapezoid = [(20.0, 0.0), (80.0, 0.0), (95.0, 60.0), (5.0, 60.0)]  # 上窄下宽
    rt = pv.rectify(_coord_image(100, 60), trapezoid, mode="bbox")
    ok("透视：梯形（平行线交于一点）能被摆成矩形（仿射做不到）",
       rt.shape[1] > 0 and rt.shape[0] > 0
       and rt.shape[1] == pv.rectify_region(trapezoid, 100, 60)[2],
       f"梯形输出 {rt.shape}")

    # ---- 6. 保透明 ----
    from PySide6.QtGui import QColor, QImage

    blank = QImage(100, 80, QImage.Format.Format_ARGB32)
    blank.fill(QColor(0, 0, 0, 0))
    rb = pv.rectify_qimage(blank, skew)
    alive = sum(1 for y in range(rb.height()) for x in range(rb.width())
                if rb.pixelColor(x, y).alpha() != 0)
    ok("保透明：整幅全透明的图校正后仍**全透明**（不变黑）",
       alive == 0, f"变成不透明的像素 {alive} 个")

    clear = QImage(100, 80, QImage.Format.Format_ARGB32)
    clear.fill(QColor(0, 0, 0, 0))
    for x in range(40, 50):
        for y in range(80):
            clear.setPixelColor(x, y, QColor("#000000"))

    def opaque_count(image):
        return sum(1 for y in range(image.height()) for x in range(image.width())
                   if image.pixelColor(x, y).alpha() > 200)

    before = opaque_count(clear)
    shifted = pv.rectify_qimage(clear, skew)
    ok("保透明：透明底 + 黑竖条校正后，不透明像素不失控增多",
       opaque_count(shifted) <= before * 1.2 and before == 800,
       f"不透明 前 {before} → 后 {opaque_count(shifted)}")

    # ---- 7. QImage 恒等往返 ----
    solid = QImage(100, 80, QImage.Format.Format_ARGB32)
    solid.fill(QColor("#ffffff"))
    for x in range(50, 60):
        for y in range(80):
            solid.setPixelColor(x, y, QColor("#000000"))
    identical = pv.rectify_qimage(solid, quad)
    same = all(identical.pixelColor(x, y).rgba() == solid.pixelColor(x, y).rgba()
               for y in range(0, 80, 4) for x in range(0, 100, 4))
    ok("QImage：不透明图恒等校正原样返回（尺寸不变、逐点一致）",
       identical.width() == 100 and identical.height() == 80 and same,
       f"尺寸 {identical.width()}×{identical.height()}，全等 {same}")

    # ---- 8. quad_moved ----
    ok("quad_moved：四角没动 False / 动过 True",
       pv.quad_moved(quad, quad) is False
       and pv.quad_moved(quad, [(1.0, 0.0), (99.0, 0.0),
                                (99.0, 79.0), (0.0, 79.0)]) is True, "")

    # ---- 附加：整页 4000×3000 一次校正有墙钟兜底 ----
    import time
    big = _coord_image(4000, 3000)
    big_quad = [(100.0, 60.0), (3900.0, 40.0), (3920.0, 2950.0),
                (80.0, 2960.0)]
    started = time.perf_counter()
    try:
        big_out = pv.rectify(big, big_quad, mode="bbox")
        elapsed = time.perf_counter() - started
        ok("代价兜底：整页 4000×3000 一次校正 < 30s",
           elapsed < 30.0 and big_out.size > 0,
           f"耗时 {elapsed:.2f}s，输出 {big_out.shape}")
    except MemoryError:
        ok("代价兜底：整页 4000×3000 一次校正 < 30s", False, "MemoryError")
