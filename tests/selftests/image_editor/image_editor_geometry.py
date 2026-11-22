# -*- coding: utf-8 -*-
"""图片编辑器·纯算法（不开弹窗）：几何/变换数学/文字绘制/扭曲笔刷。

断言线（全部是**纯函数**，不依赖 GUI 布局，所以拆出来跑得又快又稳）：

1. **clamp_rect**：界内原样、越界先平移夹回、比画布还大的缩到画布；
1b. **变换数学**：绕点旋转/缩放/切变（轴心不动、方向与系数钉死）——
   Qt 的 ``A * B`` 是**先 A 后 B**，与数学记号相反，这条钉死它；
1c. **病态投影的尺寸闸门**（2026-10-09 崩溃回归）：透视角拖到对角附近时
   ``quadToQuad`` 会给出"可逆但放大百万倍"的矩阵，外框撑到 4.8e17 ⇒
   ``QImage(2.18e9)`` OverflowError。闸门统一在 ``geometry.mapped_bounds``，
   这里把闸门本身、QPainter 兜底、grow 档烘焙三处各钉一条；
2. **draw_text**：非空文本在落点附近留下深色像素、空白文本不改动图片；
3. **扭曲算法**：七种笔刷模式 × 三种插值都能改变笔刷区域、恢复原状
   模式回到笔划起点图像；
4. **落点重采样**（2026-10-08 报障"拖得越久越卡、最后崩溃"）：旧 ``extend``
   把已用掉的 carry 又加回一次 ⇒ ``_carry`` 单调增长、抛出成百个远在天边
   的假落点。这里钉死"分段喂 == 一次喂""carry 恒小于间距""位移恒等于
   一个间距"，别再写成累加式记账。

（其余主题：弹窗外壳见 ``image_editor.py``、裁剪见 ``image_editor_crop.py``、
擦除/扭曲/历史见 ``image_editor_history.py``、文字见 ``image_editor_text.py``、
变换见 ``image_editor_transform*.py``。）
"""

from __future__ import annotations

NAME = "image_editor_geometry"
DEPENDS: list[str] = []
TITLE = "图片编辑器·纯算法（几何/文字/扭曲采样）"


def run(ctx) -> None:
    import math

    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QImage, QTransform

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import is_dark, make_image

    from desktop.components.viewers.image_editor import (
        clamp_rect, compose_transform, draw_text,
        rotate_about, scale_about, shear_about, transform_region,
        warp_placement,
    )

    # ---- 1. clamp_rect ----
    bounds = QRectF(0, 0, 100, 80)
    ok("clamp_rect：界内矩形原样保留",
       clamp_rect(QRectF(10, 10, 30, 20), bounds) == QRectF(10, 10, 30, 20), "")
    ok("clamp_rect：越界矩形先平移夹回",
       clamp_rect(QRectF(90, 70, 30, 20), bounds) == QRectF(70, 60, 30, 20), "")
    ok("clamp_rect：比画布还大的矩形缩到画布",
       clamp_rect(QRectF(-10, -10, 200, 160), bounds) == bounds, "")

    # ---- 1b. 变换数学（QTransform 复合约定在这里钉死） ----
    center = QPointF(100, 60)
    rotated = rotate_about(center, 90).map(QPointF(0, 0))
    expected = center + QPointF(60, -100)  # (0,0) 绕中心顺时针 90°
    ok("变换数学：绕点旋转（轴心不动、角点落到顺时针 90° 位置）",
       (rotated - expected).manhattanLength() < 1e-6
       and (rotate_about(center, 90).map(center) - center).manhattanLength()
       < 1e-6,
       f"rotated={rotated} expected={expected}")
    scaled = scale_about(QPointF(200, 120), 2.0, 2.0).map(QPointF(0, 0))
    ok("变换数学：绕锚点缩放",
       (scaled - QPointF(-200, -120)).manhattanLength() < 1e-6,
       f"scaled={scaled}")
    sheared = shear_about(QPointF(0, 0), 0.0, 0.5).map(QPointF(200, 0))
    ok("变换数学：绕锚点切变（y 随 x 斜切）",
       (sheared - QPointF(200, 100)).manhattanLength() < 1e-6,
       f"sheared={sheared}")

    # ---- 1c. 病态投影的"尺寸闸门"（2026-10-09 崩溃回归）----
    # ⚠️⚠️ 用户报障：统一变换里把**透视角拖到对角附近**，整个编辑器崩掉——
    #    `geometry.py:311 QImage(width, height)` 拿到 2.18e9 × 1.49e9 直接
    #    OverflowError（同一句先连出 3 次"Paint device returned engine == 0"，
    #    那是 QImage 已失效、QPainter 画不上去）。根因有两层，缺一不可：
    #    ① 近共线的四点让 `quadToQuad` 给出一个"**可逆**但把内容放大百万倍"
    #       的矩阵（外框坐标实测 1e9、面积 4.8e17）——所以"查共线 + 查可逆"
    #       挡不住它；
    #    ② `warp_region` 已经**正确**地拒绝了（超 WARP_MAX_PIXELS），但
    #       `warp_placement` 的 QPainter 兜底**没挡**，硬拿天文数字去建 QImage。
    #    现在闸门统一在 `geometry.mapped_bounds`（非有限 / >ABSURD_COORD /
    #    超 WARP_MAX_PIXELS 一律 None），四个入口共用：重采样、兜底、烘焙画布、
    #    透视步进。下面把闸门本身、兜底、烘焙三处各钉一条。
    from desktop.components.viewers.image_editor import geometry as editor_geometry
    from desktop.components.viewers.image_editor.geometry import (
        ABSURD_COORD, mapped_bounds,
    )

    bad_xf = QTransform(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1e-9)
    ok("几何：病态投影的外框被判为不可用（闸门就是崩溃的解药）",
       mapped_bounds(bad_xf, QRectF(0, 0, 600, 800)) is None
       and mapped_bounds(QTransform(), QRectF(0, 0, 600, 800))
       == (0, 0, 600, 800)
       and ABSURD_COORD >= 1e6,
       f"bad={mapped_bounds(bad_xf, QRectF(0, 0, 600, 800))} "
       f"identity={mapped_bounds(QTransform(), QRectF(0, 0, 600, 800))}")

    plane = make_image(60, 40)
    plane_rect = QRectF(0, 0, 60, 40)
    ok("几何：transform_region 遇病态投影退回原图边界（不造天文数字画布）",
       transform_region(plane, plane_rect, bad_xf) == (0, 0, 60, 40),
       f"{transform_region(plane, plane_rect, bad_xf)}")

    # 让 `warp_region` 返回 None（模拟"取不到 numpy"）⇒ 逼真地走到 QPainter
    # 兜底那条路。⚠️ 必须 try/finally 还原（`warp_placement` 是在**模块全局**
    # 里找 `warp_region` 的，打桩即改全局）。
    _real_warp_region = editor_geometry.warp_region
    editor_geometry.warp_region = lambda *args, **kwargs: None
    try:
        bad_out = warp_placement(plane, bad_xf, "linear")
        good_out = warp_placement(plane, QTransform(), "linear")
    finally:
        editor_geometry.warp_region = _real_warp_region
    ok("几何：兜底路径遇病态投影返回空图（不再 QImage(2e9) 崩溃）",
       isinstance(bad_out, tuple) and bad_out[0].isNull()
       and bad_out[1:] == (0, 0)
       and good_out is not None and not good_out[0].isNull()
       # ⚠️ 外框是"含两端"的口径 ⇒ 恒比区域大 1 像素（两档一致的老约定）
       and (good_out[0].width(), good_out[0].height()) == (61, 41),
       f"bad={bad_out if bad_out is None else (bad_out[0].size(), bad_out[1:])} "
       f"good={None if good_out is None else good_out[0].size()}")

    grew = compose_transform(make_image(600, 800), QRectF(0, 0, 600, 800),
                             bad_xf, plane, grow=True)
    ok("几何：grow 档烘焙遇病态投影也不炸（画布退回原图尺寸）",
       grew is not None and grew[0].width() == 600 and grew[0].height() == 800,
       f"grew={None if grew is None else grew[0].size()}")

    # ---- 4. draw_text ----
    text_base = make_image(400, 120)
    written = draw_text(text_base, QPointF(20, 20), "测试", 64, QColor("#000000"))
    has_dark = any(
        is_dark(written.pixelColor(x, y))
        for y in range(20, 90, 2) for x in range(20, 160, 2)
    )
    ok("文字：非空文本在落点附近留下深色像素", has_dark, "")
    untouched = draw_text(text_base, QPointF(20, 20), "  ", 64, QColor("#000000"))
    same = all(
        untouched.pixelColor(x, y).rgba() == text_base.pixelColor(x, y).rgba()
        for y in range(0, 120, 7) for x in range(0, 400, 7)
    )
    ok("文字：空白文本不改动图片", same, "")

    from desktop.components.viewers.image_editor.distortion import (
        apply_distortion_stamp,
    )

    warp = make_image(80, 40)
    for x in range(30, 33):
        for y in range(18, 23):
            warp.setPixel(x, y, 0xFF000000)
    apply_distortion_stamp(
        warp, 32.0, 20.0, 4.0, 0.0, 32, 100, 100,
        "move", "nearest")
    ok("扭曲算法：移动像素沿笔划方向移动，笔刷外区域不变",
       is_dark(warp.pixelColor(34, 20))
       and warp.pixelColor(30, 20).value() > 230
       and warp.pixelColor(5, 5).value() > 230,
       f"moved={warp.pixelColor(34, 20).value()} "
       f"old={warp.pixelColor(30, 20).value()}")

    pattern = make_image(80, 80)
    for x in range(44, 49):
        for y in range(38, 43):
            pattern.setPixel(x, y, 0xFF000000)
    for mode in ("grow", "shrink", "swirl_cw", "swirl_ccw", "smooth"):
        candidate = pattern.copy()
        apply_distortion_stamp(
            candidate, 40.0, 40.0, 3.0, 0.0, 40, 60, 100,
            mode, "cubic")
        ok(f"扭曲算法：{mode}模式可改变笔刷区域", candidate != pattern, "")
    restored = pattern.copy()
    restored.setPixel(40, 40, 0xFF000000)
    apply_distortion_stamp(
        restored, 40.0, 40.0, 0.0, 0.0, 40, 100, 100,
        "restore", "linear", pattern)
    ok("扭曲算法：恢复原状模式回到笔划起点图像",
       restored == pattern, "")
    for interpolation in ("nearest", "linear", "cubic"):
        candidate = pattern.copy()
        apply_distortion_stamp(
            candidate, 40.0, 40.0, 3.5, 0.0, 40, 60, 100,
            "move", interpolation)
        ok(f"扭曲算法：{interpolation}插值可用", candidate != pattern, "")

    # ---- 2c. 落点重采样（扭曲笔划的"粒度"唯一来源）----
    # ⚠️ 回归（2026-10-08 用户报"拖动越久越卡、最后崩溃"）：旧 `extend` 把
    #    **已经用掉的旧 carry 又加回一次**，于是 `_carry` 每段单调增长；一旦
    #    `carry > step`，`step - carry` 变负、循环每段空转 `carry/step` 次，
    #    抛出成百个远在天边的假落点（实测拖 30 秒后每段 184 个、脏区 2000
    #    图像 px、每帧 56 ms）。下面三条把机制钉死，别再写成"累加式记账"。
    from desktop.components.viewers.image_editor.distortion import (
        StrokeSampler, plan_stroke_stamps,
    )

    path = [(0.0, 0.0), (37.0, 11.0), (91.0, 40.0), (60.0, 120.0), (10.0, 200.0)]
    one_shot = plan_stroke_stamps(path, 30, 20)      # step = 30×20% = 6
    sampler = StrokeSampler(30, 20)
    fed = list(sampler.start(path[0]))
    for point in path[1:]:
        fed.extend(sampler.extend(point))
    fed.extend(sampler.flush())
    ok("扭曲采样：分段喂与一次喂得到同一条落点序列",
       fed == one_shot, f"fed={len(fed)} one_shot={len(one_shot)}")

    sampler = StrokeSampler(30, 20)                  # step = 6
    sampler.start((0.0, 0.0))
    stamps: list[tuple[float, float, float, float]] = []
    carry_max = 0.0
    travelled = 0.0
    for i in range(1, 2001):                         # 2000 段小步 ≈ 长时间拖动
        point = (i * 1.3, i * 0.7)
        travelled += math.hypot(point[0] - (i - 1) * 1.3,
                                point[1] - (i - 1) * 0.7)
        stamps.extend(sampler.extend(point))
        carry_max = max(carry_max, sampler._carry)
    step = sampler.step
    max_delta = max(math.hypot(s[2], s[3]) for s in stamps)
    ok("扭曲采样：carry 恒小于落点间距（旧实现会单调增长）",
       carry_max < step, f"carry_max={carry_max} step={step}")
    ok("扭曲采样：落点只落在路径上、位移恒等于一个间距（不出现飞点）",
       max_delta <= step + 1e-6
       and len(stamps) <= travelled / step + 1,
       f"max_delta={max_delta} stamps={len(stamps)} 上限={travelled / step + 1:.0f}")