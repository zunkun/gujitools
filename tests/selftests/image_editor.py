# -*- coding: utf-8 -*-
"""图片编辑弹窗自测：工具的纯逻辑 + 撤销栈 + 预览弹窗接线。

断言线（只看可观测行为）：

1. **裁剪**：进入工具**默认选中整幅图**、只许拖边/框内移动，不做
   截图式"拖拽画框"；**非破坏性**——松手只记下待定裁剪（像素不动、可
   继续向外拖把变暗的区域拉回来），切走工具/「完成」才落定成"画布尺寸 =
   选区尺寸"；落定后换图重新默认全选；待定不进历史（Ctrl+Z 先退它）；
1b. **变换数学**：绕点旋转/缩放/切变（轴心不动、方向与系数钉死）；
1c. **变换**：默认全选、框内拖=移动、按下即实时预览（底图=原图矩形那块的
   残余、选区擦成透明；范围**恒定**不跟变换走）、应用烘焙（原位置填白、
   内容落位）、切走工具自动烘焙、从轴心缩放、
   重置、命中测试；「调整范围」收边进入小区域（自动退出+轴心跟随）、
   局部烘焙后**区域外像素一动不动**；
2. **擦除**：橡皮擦涂过的污点被擦成白底；一笔开始就压撤销点
   （``stroke_started`` → ``_push_undo`` 已接线）；悬停时空白光标 +
   实圈指示，圈直径恒等于橡皮擦直径（所见即所擦）；
3. **文字**：落点生成就地编辑的文字块（文本交互开启）、**键盘输入直达
   文字块**（焦点路由：画布 StrongFocus → 场景焦点项）、按住拖动超过
   阈值移动整块、「插入文字」写入图片并压撤销点、切走工具自动写入；
   空白文本不动图；字体下拉**以中文字体为主**（西文只留几个常用）；
   颜色是**一个按钮**，常用色块收在它弹出的面板里（不再散在选项行上）；
3b. **回归（2026-10-01 用户报障"文字大小不生效"）**：选项行控件抢走画布
   键盘焦点后，改字号/颜色仍必须作用在当前文字块上（样式走"当前样式块"
   而不是场景焦点项；字号滑杆另设 NoFocus 保住光标）；
2b. **变形（PS 操控变形）**：进入工具建网格（无图钉、无待应用形变）；
   点图放钉（吸附最近顶点、同一顶点不重复）、拖动图钉→附近内容跟着走、
   远场逐字节不动（ARAP 局部 + 边框锚点）、松手/应用/切走工具都烘焙、
   应用后图钉留在原地、重置/右键删除、改网格疏密清空图钉；
2c. **扭曲笔刷**：落点重采样分段喂 == 一次喂、`carry` 恒小于落点间距、
   落点位移恒等于一个间距（不会再出现"拖得越久飞点越多"，2026-10-08 报障）；
   拖动时只刷新邻近脏区、单帧渲染量有像素预算、大图预览自动降采样；
4. **撤销/重做/还原**：状态按步回退/前进，还原可撤销，栈深 ≤ 12；
5. **选区门槛**：小于 4px 的选区视为没有（误点不产生 1px 裁剪）；
6. **初始自适应**：窗口就位/改变大小后画布自动适应窗口（没手动缩放过时），
   修复"打开时图片缩成指甲盖"（fit 在布局前算到脏尺寸）；
7. **两行工具栏**：撤销/还原/缩放按钮都在窗口内（单行时会被挤出左上角），
   工具选项行在主工具栏下方；
8. **窗口旗标**：最小化/最大化/关闭按钮齐备（缺 CloseButtonHint 时
   Windows 上关闭按钮失效，用户报障过）；
9. **预览弹窗接线**：有「编辑」按钮、宽度取满（理想 1360，超出屏幕时夹进
   可用区域）、无图禁用/有图可用、``_open_editor`` 拿到画布整图；
10. **编辑结果写回画布**：``_edit_image`` 走的通道（set_image）会替换画布图。
"""
from __future__ import annotations

NAME = "image_editor"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗（裁剪/变换/扭曲/擦除/文字）"


def make_image(width: int, height: int):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    return image


def is_dark(color) -> bool:
    """足够深的像素（文字/黑笔刷落点，抗锯齿边缘不算）。"""
    return color.red() < 100 and color.green() < 100 and color.blue() < 100


def plane_diff(a, b) -> float:
    """两张**同尺寸**图的平均通道差（隔点采样，够用又便宜）。

    用于"画布预览 == 烘焙结果"的像素级对照：同一条数学算出来的两张图，
    差别只该来自抗锯齿（实测 1–2），差到几十就是"内容落在别处/被裁掉"。
    """
    if a.size() != b.size():
        return 999.0
    total = 0
    count = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += (abs(ca.red() - cb.red()) + abs(ca.green() - cb.green())
                      + abs(ca.blue() - cb.blue()))
            count += 3
    return total / max(1, count)


def canvas_img(canvas):
    """取画布当前图（``canvas.image`` 声明为可空，但本文件用例都在有图态访问）。"""
    img = canvas.image
    assert img is not None  # 编辑过程中画布必有图
    return img


def history_labels(dialog) -> str:
    """右侧「编辑历史」每一格的文案，拼成一行放进断言信息里。

    ⚠️ **不要写成 f-string 里的多行推导式**（``f"{[x.text() for x in
    lst\\n ...]}"``）：替换字段里出现物理换行是 **Python 3.12+（PEP 701）
    才有的语法**，仓库跑 conda py310 ⇒ 那会让**整个自测模块 import 失败**
    （`gui_selftest.discover_modules` 直接崩，整个套件都跑不了）。
    2026-10-08 那次布局调整就是这么把本文件写坏的，到 2026-10-10 才发现。
    """
    return str([dialog.history_list.item(i).text()
                for i in range(dialog.history_list.count())])


def run(ctx) -> None:
    import math

    from PySide6.QtCore import QPointF, QRectF, QSize, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QTransform

    from tests.selftests._context import ok

    from desktop.components.viewers.image_editor import (
        EDIT_FIT_RATIO, ERASER_DEFAULT,
        ImageEditorDialog, TextBlockItem,
        center_crop_aspect, clamp_rect, compose_transform, draw_text,
        rotate_about, scale_about, shear_about, transform_region,
        warp_placement,
    )
    from desktop.components.viewers.image_editor.consts import (
        CANVAS_OUTSIDE, CHECKER_DARK, CHECKER_LIGHT, CORNER_HIT_VIEW_PX,
        PERSP_HIT_VIEW_PX, PERSP_VIEW_PX,
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

    # ---- 3/5/6. 弹窗级：擦除、撤销、选区门槛 ----
    app = ctx.app
    img = make_image(200, 120)
    dialog = ImageEditorDialog(None, img)
    try:
        ok("弹窗：编辑画布装入了整图",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120, "")

        # ---- 弹窗开大 + 最小化/最大化/关闭按钮 + 工具按钮选中高亮 ----
        # ⚠️ 期望 1440×940 只是**上限**：落地尺寸会被 apply_window_size 夹进
        #    屏幕可用区域（1920×1080 @125% 的机器可用高只有 824）。这里按同
        #    一个公式算期望值，既守住"默认开大"，也守住"不许顶出屏幕"。
        from desktop.components.viewers.image_editor import (
            EDITOR_MIN_SIZE, EDITOR_SIZE,
        )
        from desktop.ui.window_size import (
            FRAME_ALLOWANCE, FIT_RATIO, available_area,
        )

        area = available_area(dialog)
        assert area is not None  # 离屏环境下可用区域总能取到
        expect_w = min(EDITOR_SIZE.width(),
                       int((area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        expect_h = min(EDITOR_SIZE.height(),
                       int((area.height() - FRAME_ALLOWANCE.height()) * FIT_RATIO))
        ok("弹窗：默认开大（1440×940，超出屏幕时夹进可用区域）并带"
           "最小化/最大化/关闭按钮",
           dialog.width() == expect_w and dialog.height() == expect_h
           and dialog.width() <= area.width()
           and dialog.height() + FRAME_ALLOWANCE.height() <= area.height()
           and bool(dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint),
           f"size={dialog.width()}x{dialog.height()} 期望={expect_w}x{expect_h} "
           f"可用区={area.width()}x{area.height()} "
           f"flags={hex(int(dialog.windowFlags()))}")
        ok("弹窗：最小尺寸也被夹进可用区域（小屏上仍能拖到放得下）",
           dialog.minimumWidth() <= min(EDITOR_MIN_SIZE.width(), dialog.width())
           and dialog.minimumHeight() <= min(EDITOR_MIN_SIZE.height(), dialog.height()),
           f"min={dialog.minimumWidth()}x{dialog.minimumHeight()}")
        ok("工具栏：工具按钮是 ToggleButton（选中态有主色高亮），"
           "裁剪/变换/扭曲/擦除/文字五个",
           all(type(dialog._tool_buttons[k]).__name__ == "ToggleButton"
               for k in dialog._tool_buttons)
           and set(dialog._tool_buttons) == {"crop", "transform", "distort",
                                             "erase", "text"}
           and dialog._tool_buttons["crop"].isChecked()
           and not dialog._tool_buttons["erase"].isChecked()
           and dialog._tool_buttons["distort"].iconSize() == QSize(14, 14),
           f"tools={sorted(dialog._tool_buttons)} "
           f"crop={dialog._tool_buttons['crop'].isChecked()} "
           f"erase={dialog._tool_buttons['erase'].isChecked()}")

        dialog._set_tool("distort")
        from qfluentwidgets import CheckBox as FluentCheckBox
        from qfluentwidgets import Slider as FluentSlider
        from qfluentwidgets import ComboBox as FluentComboBox

        distortion_page = dialog._option_page
        assert distortion_page is not None
        distortion_combos = distortion_page.findChildren(FluentComboBox)
        distortion_sliders = distortion_page.findChildren(FluentSlider)
        distortion_checks = distortion_page.findChildren(FluentCheckBox)
        ok("扭曲工具：参数面板提供七种笔刷模式、三种插值、大小/硬度/强度/间距和预览开关",
           dialog.canvas._tool == "distort"
           and {combo.currentData() for combo in distortion_combos}
           == {"move", "cubic"}
           and sorted(slider.value() for slider in distortion_sliders)
           == [10, 50, 50, 117]
           and len(distortion_checks) == 2
           and any(check.text() == "实时预览" and check.isChecked()
                   for check in distortion_checks)
           and any(check.text() == "高质量预览" and check.isChecked()
                   for check in distortion_checks),
           f"combos={[c.currentData() for c in distortion_combos]} "
           f"sliders={[s.value() for s in distortion_sliders]} "
           f"checks={len(distortion_checks)}")
        dialog._set_tool("crop")

        # ---- 裁剪交互（2026-09-30 用户定）：默认全选 + 手柄内收，不做画框 ----
        full = dialog.canvas.image_rect()
        ok("裁剪：进入工具默认选中整幅图",
           dialog.canvas._tool == "crop"
           and dialog.canvas.selection() == full,
           f"sel={dialog.canvas.selection()} full={full}")
        dialog.canvas._resize_rect("tl", QPointF(20, 15))
        ok("裁剪：拖左上手柄向内收边",
           dialog.canvas.selection()
           == QRectF(20, 15, full.width() - 20, full.height() - 15),
           f"sel={dialog.canvas.selection()}")
        dialog.canvas.set_tool("crop")
        ok("裁剪：重新进入工具恢复默认全选",
           dialog.canvas.selection() == full, "")
        # 截图式画框必须不存在：图外远处按下不产生橡皮筋选区
        # （⚠️ 用远处：手柄有视觉尺寸+3px 容差，图外太近会命中角手柄）
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent

        outside = QPointF(dialog.canvas.mapFromScene(QPointF(-300, -300)))
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress, outside,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier)
        dialog.canvas.mousePressEvent(press)
        ok("裁剪：图外按下不产生新选区（不支持截图式拖拽画框）",
           dialog.canvas._mode is None and dialog.canvas.selection() == full,
           f"mode={dialog.canvas._mode}")
        dialog.canvas.set_tool("crop")

        # ---- 初始自适应 + 两行工具栏（需要真实布局几何，先显示） ----
        dialog.show()
        app.processEvents()
        dialog.resize(1000, 720)
        app.processEvents()
        app.processEvents()
        canvas = dialog.canvas
        vw, vh = canvas.viewport().width(), canvas.viewport().height()
        # 图片占视口 EDIT_FIT_RATIO（缺省不铺满，四周留白，用户 2026-10-02 定）
        expected = EDIT_FIT_RATIO * min(vw / 200, vh / 120)
        ok("画布：窗口就位后自动适应窗口（修复初始过小，四周留白）",
           abs(canvas.transform().m11() - expected) <= expected * 0.05
           and canvas._user_zoomed is False,
           f"m11={canvas.transform().m11():.3f} expected={expected:.3f} "
           f"viewport={vw}x{vh}")
        # 手柄视觉尺寸 = 视图像素(12) ÷ 倍率 × 倍率 ≈ 12px：fit() 换倍率后
        # 必须重算覆盖层，否则 set_image 时脏 viewport 算的小倍率会留下巨型手柄
        tl_view = canvas.mapFromScene(
            canvas._handle_boxes(canvas.image_rect())["tl"]).boundingRect()
        ok("画布：手柄视觉尺寸 ≈ 12px（fit 换倍率后覆盖层已重算）",
           7 <= tl_view.width() <= 20 and 7 <= tl_view.height() <= 20,
           f"tl_view={tl_view.width():.1f}x{tl_view.height():.1f}")

        # 画布配色（用户 2026-10-09 追加：「背景灰色太突兀」）：图外必须是**浅**底，
        # 同时又得和图内棋盘格拉开明度，才既柔和不抢戏、又分得清"哪块是图的地盘"。
        # ⚠️ 这条挡住"为了好看把底色改深/改到和格子一样"的回归——两者是矛盾的，
        #    改动时必须同时满足（底色浅 ⇒ 格子的暗格要跟着压深，见 consts 注释）。
        ok("画布：图外底色够浅、且与棋盘格仍有明度反差（不突兀也分得清）",
           CANVAS_OUTSIDE.lightness() >= 220
           and CHECKER_LIGHT.lightness() - CHECKER_DARK.lightness() >= 12
           and abs(CANVAS_OUTSIDE.lightness() - CHECKER_DARK.lightness()) >= 12,
           f"outside={CANVAS_OUTSIDE.lightness()} "
           f"light={CHECKER_LIGHT.lightness()} dark={CHECKER_DARK.lightness()}")

        # ---- 「适应窗口」按钮：**真点一次**（clicked 会塞 checked=False 进来）----
        # 回归（2026-10-08 用户报「使用窗口，图片立马变得非常小」）：此前是
        # ``fit_btn.clicked.connect(self.canvas.fit)``，fit(ratio) 收到
        # checked=False ⇒ float(False)=0.0 被夹成下限 0.2，图缩成视口的 1/4。
        canvas.zoom_in()
        canvas.zoom_in()
        zoomed = canvas.transform().m11()
        assert zoomed > expected * 1.05  # 先确认真的偏离了 fit 值，否则下条是假绿
        dialog.fit_btn.click()
        app.processEvents()
        fit_m11 = canvas.transform().m11()
        ok("「适应窗口」按钮：点一下回到 fit 倍率（不再被 clicked 的 False 缩成 1/4）",
           abs(fit_m11 - expected) <= expected * 0.05,
           f"点前 {zoomed:.3f} 点后 {fit_m11:.3f} expected={expected:.3f}")
        ok("「适应窗口」按钮：直接喂一个 bool 也不会缩水（兜底）",
           (canvas.fit(False), app.processEvents())[1] is None
           and abs(canvas.transform().m11() - expected) <= expected * 0.05,
           f"m11={canvas.transform().m11():.3f} expected={expected:.3f}")

        # ---- 边缘命中带 + 松手视图适配新选区（用户 20:18 定） ----
        def mouse_event(kind: str, view_pos: QPointF,
                        button: Qt.MouseButton = Qt.MouseButton.LeftButton):
            types = {
                "press": QEvent.Type.MouseButtonPress,
                "move": QEvent.Type.MouseMove,
                "release": QEvent.Type.MouseButtonRelease,
            }
            buttons = (Qt.MouseButton.NoButton if kind == "move"
                       else button)
            return QMouseEvent(types[kind], view_pos,
                               button, buttons,
                               Qt.KeyboardModifier.NoModifier)

        left_mid = QPointF(canvas.mapFromScene(QPointF(-1.0, 60)))
        ok("裁剪：整条边都是命中带（左边缘中点、远离小方块）",
           canvas._hit_handle(left_mid) == "l",
           f"hit={canvas._hit_handle(left_mid)}")
        corner = QPointF(canvas.mapFromScene(QPointF(-1.0, -1.0)))
        ok("裁剪：角部双边交叠命中角手柄",
           canvas._hit_handle(corner) == "tl",
           f"hit={canvas._hit_handle(corner)}")
        middle = QPointF(canvas.mapFromScene(QPointF(100, 60)))
        ok("裁剪：远离边缘的框内不命中手柄（那是移动）",
           canvas._hit_handle(middle) is None,
           f"hit={canvas._hit_handle(middle)}")

        def mask_area(cv) -> float:
            """选区外那 4 块遮罩的总面积（= 被"藏起来"的像素数）。"""
            return sum(max(0.0, it.rect().width()) * max(0.0, it.rect().height())
                       for it in cv._mask)

        zoom_before = canvas._zoom
        undo_before = len(dialog._undo)
        history_before = dialog.history_list.count()
        canvas.mousePressEvent(mouse_event("press", corner))
        ok("裁剪：角部按下进入收边状态",
           canvas._mode is not None and canvas._mode[0] == "handle"
           and canvas._mode[1] == "tl", f"mode={canvas._mode}")
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(60, 30)))))
        ok("裁剪：拖动过程中图仍是整幅（松手也不切像素）",
           canvas_img(canvas).width() == 200
           and canvas.selection() is not None
           and abs(canvas.selection().left() - 60) < 1,
           f"w={canvas_img(canvas).width()} sel={canvas.selection()}")
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(60, 30)))))
        sel_now2 = canvas.selection()
        masked_in = mask_area(canvas)
        ok("裁剪：松手**不落定**＝画布仍是原图、选区留着、不进历史",
           canvas_img(canvas).width() == 200
           and canvas_img(canvas).height() == 120
           and sel_now2 is not None
           and abs(sel_now2.left() - 60) < 1
           and dialog._pending_crop is not None
           and len(dialog._undo) == undo_before
           and dialog.history_list.count() == history_before,
           f"w={canvas_img(canvas).width()} sel={sel_now2} "
           f"待定={dialog._pending_crop} undo={len(dialog._undo)}")
        ok("裁剪：待定期间右下角并排写出「裁完是多大」",
           "裁剪后 140 × 90 px" in dialog.size_label.text(),
           f"label={dialog.size_label.text()!r}")
        ok("裁剪：待定期间视图不跳（画面不动，用户才好继续推拉）",
           canvas._zoom == zoom_before,
           f"zoom {zoom_before:.2f} -> {canvas._zoom:.2f}")

        # ---- 回归（用户 2026-10-10 报障）：裁剪线要能向外拖回去 ----
        # 旧版松手即 QImage.copy，把图裁小、选区重置成新图整幅 ⇒ 第二次拖动
        # 时手柄已经压在边界上，向外无处可拖；现在待定状态下画布始终是原图，
        # 往外拖时被遮罩盖住的区域会重新露出来。
        tl_now = QPointF(canvas.mapFromScene(QPointF(60, 30)))
        canvas.mousePressEvent(mouse_event("press", tl_now))
        ok("裁剪：收小后角手柄仍可再抓（没有换图把手柄顶到新边界上）",
           canvas._mode is not None and canvas._mode[0] == "handle"
           and canvas._mode[1] == "tl", f"mode={canvas._mode}")
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(10, 8)))))
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(10, 8)))))
        sel_out = canvas.selection()
        masked_out = mask_area(canvas)
        ok("裁剪：向外拖回去＝原本被隐藏的区域重新显示（遮罩显著缩小）",
           sel_out is not None
           and abs(sel_out.left() - 10) < 1 and abs(sel_out.top() - 8) < 1
           and abs(sel_out.width() - 190) < 1
           and masked_out < masked_in / 2
           and canvas_img(canvas).width() == 200,
           f"sel={sel_out} 遮罩 {masked_in:.0f} -> {masked_out:.0f} "
           f"w={canvas_img(canvas).width()}")
        ok("裁剪：反复推拉期间图一直是原图、历史一步都不增",
           canvas_img(canvas).height() == 120
           and dialog._pending_crop is not None
           and len(dialog._undo) == undo_before
           and dialog.history_list.count() == history_before,
           f"待定={dialog._pending_crop} undo={len(dialog._undo)}")
        # 再拖一次回到整幅：这一下等于"没裁"，待定就该自己消失
        tl_out = QPointF(canvas.mapFromScene(QPointF(10, 8)))
        canvas.mousePressEvent(mouse_event("press", tl_out))
        canvas.mouseMoveEvent(mouse_event(
            "move", QPointF(canvas.mapFromScene(QPointF(0, 0)))))
        canvas.mouseReleaseEvent(mouse_event(
            "release", QPointF(canvas.mapFromScene(QPointF(0, 0)))))
        ok("裁剪：一路拖回整幅＝当成没裁（待定清空、历史不增）",
           canvas.selection() == canvas.image_rect()
           and dialog._pending_crop is None
           and len(dialog._undo) == undo_before
           and dialog.history_list.count() == history_before,
           f"sel={canvas.selection()} 待定={dialog._pending_crop} "
           f"undo={len(dialog._undo)}")

        # 再收小一次，然后**切走裁剪工具**才真正落定（GIMP 口径）
        canvas._rect = QRectF(60, 30, 140, 90)
        dialog._preview_crop()
        ok("裁剪：切走工具前仍是原图（待定没落定）",
           canvas_img(canvas).width() == 200, "")
        dialog._set_tool("erase")
        cropped = canvas_img(canvas)
        ok("裁剪：切走裁剪工具＝确认这次裁剪（画布尺寸 = 选区尺寸）",
           abs(cropped.width() - 140) < 1 and abs(cropped.height() - 90) < 1,
           f"size={cropped.width()}x{cropped.height()}")
        ok("裁剪：落定后待定状态清空（不会二次落定）",
           dialog._pending_crop is None, f"待定={dialog._pending_crop}")
        ok("裁剪：落定是一步撤销点，历史多一格「裁剪」且光标停在那儿",
           len(dialog._undo) == undo_before + 1
           and dialog.history_list.count() == history_before + 1
           and dialog.history_list.item(
               dialog.history_list.count() - 1).text() == "裁剪"
           and dialog.history_list.currentRow()
           == dialog.history_list.count() - 1,
           f"undo={len(dialog._undo)} 行={dialog.history_list.currentRow()} "
           f"历史={history_labels(dialog)}")
        # 回到裁剪工具：换图后选区重新默认全选新图
        dialog._set_tool("crop")
        ok("裁剪：落定后选区重新默认全选新图",
           canvas.selection() == canvas.image_rect(),
           f"sel={canvas.selection()} full={canvas.image_rect()}")
        ok("裁剪：落定后视图重新适应新图（形状变了，倍率随之重算）",
           canvas._zoom > zoom_before,
           f"zoom {zoom_before:.2f} -> {canvas._zoom:.2f}")
        sel_sel = canvas.selection()
        assert sel_sel is not None  # 裁剪态必有选区
        sel_view = canvas.mapFromScene(sel_sel).boundingRect()
        vp = canvas.viewport().rect()
        ok("裁剪：适应后四周留白（图约占 80% 视口，不顶边）",
           sel_view.width() < vp.width() and sel_view.height() < vp.height(),
           f"sel_view={sel_view.width():.0f}x{sel_view.height():.0f} "
           f"viewport={vp.width()}x{vp.height()}")
        # 撤销/重做把裁剪整段退回去又前进回来（历史光标跟着走）
        dialog._undo_now()
        ok("裁剪：撤销把裁剪完整回退（图回 200×120、历史光标回第 0 格）",
           canvas_img(canvas).width() == 200
           and dialog.history_list.currentRow() == 0,
           f"w={canvas_img(canvas).width()} "
           f"行={dialog.history_list.currentRow()}")
        dialog._redo_now()
        ok("裁剪：重做回到裁后 140×90、历史光标回末格",
           canvas_img(canvas).width() == 140
           and dialog.history_list.currentRow()
           == dialog.history_list.count() - 1, "")
        # 待定裁剪不进历史：Ctrl+Z 要先退掉它（框弹回整幅），再按一次才撤真步骤
        dialog._redo_now()          # 先把重做链走空，保证下面按一次就能撤到 140
        canvas.set_tool("crop")
        canvas._rect = QRectF(10, 10, 120, 70)      # 当前图已是 140×90
        dialog._preview_crop()
        steps_now = len(dialog._undo)
        dialog._undo_now()
        ok("裁剪：待定时 Ctrl+Z 先退掉裁剪框（图不动、历史不撤）",
           dialog._pending_crop is None
           and canvas.selection() == canvas.image_rect()
           and len(dialog._undo) == steps_now
           and canvas_img(canvas).width() == 140,
           f"待定={dialog._pending_crop} sel={canvas.selection()} "
           f"undo={len(dialog._undo)} before={steps_now} "
           f"w={canvas_img(canvas).width()}")
        # 选区没变（点一下手柄但不拖）时松手：不许白压一个空撤销步
        steps_now = len(dialog._undo)
        handle_top = QPointF(canvas.mapFromScene(
            canvas.image_rect().topLeft()))
        canvas.mousePressEvent(mouse_event("press", handle_top))
        canvas.mouseReleaseEvent(mouse_event("release", handle_top))
        ok("裁剪：选区没变时松手不产生空撤销步（点一下不算一步）",
           len(dialog._undo) == steps_now
           and dialog._pending_crop is None
           and canvas_img(canvas).width() == 140,
           f"undo={len(dialog._undo)} before={steps_now}")

        # ---- 悬停反馈：光标形态 + 边界高亮（用户 20:28 定） ----
        app.processEvents()
        sel_now = canvas.selection()
        assert sel_now is not None  # 裁剪态必有选区
        hover_l = QPointF(canvas.mapFromScene(QPointF(
            sel_now.left() - 1.0, sel_now.center().y())))
        canvas.mouseMoveEvent(mouse_event("move", hover_l))
        ok("悬停：左边缘上光标变左右缩放、该边高亮",
           canvas.viewport().cursor().shape() == Qt.CursorShape.SizeHorCursor
           and canvas._edge_lines["l"].isVisible()
           and not canvas._edge_lines["t"].isVisible(),
           f"cursor={canvas.viewport().cursor().shape()} "
           f"l={canvas._edge_lines['l'].isVisible()}")
        hover_tl = QPointF(canvas.mapFromScene(QPointF(
            sel_now.left() - 1.0, sel_now.top() - 1.0)))
        canvas.mouseMoveEvent(mouse_event("move", hover_tl))
        ok("悬停：左上角光标变对角缩放、相邻两边都高亮",
           canvas.viewport().cursor().shape() == Qt.CursorShape.SizeFDiagCursor
           and canvas._edge_lines["l"].isVisible()
           and canvas._edge_lines["t"].isVisible(),
           f"cursor={canvas.viewport().cursor().shape()}")
        hover_mid = QPointF(canvas.mapFromScene(sel_now.center()))
        canvas.mouseMoveEvent(mouse_event("move", hover_mid))
        ok("悬停：框内是抓手光标、高亮熄灭",
           canvas.viewport().cursor().shape() == Qt.CursorShape.OpenHandCursor
           and not any(i.isVisible() for i in canvas._edge_lines.values()),
           f"cursor={canvas.viewport().cursor().shape()}")
        canvas.set_tool("erase")
        canvas.mouseMoveEvent(mouse_event("move", hover_mid))
        ring = canvas._eraser_ring[0].rect()
        ring_center = canvas.mapFromScene(ring.center())
        ok("悬停：擦除是空白光标 + 实圈指示（直径=橡皮擦大小、圈心=光标）",
           canvas.viewport().cursor().shape() == Qt.CursorShape.BlankCursor
           and all(i.isVisible() for i in canvas._eraser_ring)
           and abs(ring.width() - ERASER_DEFAULT) < 1e-6
           and (QPointF(ring_center) - hover_mid).manhattanLength() < 2.0
           and not any(i.isVisible() for i in canvas._edge_lines.values()),
           f"cursor={canvas.viewport().cursor().shape()} "
           f"ring={ring.width():.1f} vs {ERASER_DEFAULT}")
        canvas.set_tool("crop")
        ok("工具栏：撤销/还原/完成按钮都在窗口内（不再被挤出）",
           dialog.undo_btn.x() >= 0
           and dialog.reset_btn.geometry().right() < dialog.width()
           and dialog.done_btn.geometry().right() <= dialog.width(),
           f"undo.x={dialog.undo_btn.x()} "
           f"done.right={dialog.done_btn.geometry().right()} "
           f"win={dialog.width()}")
        ok("工具栏：缩放按钮进了顶部动作行（在「还原」右侧、有宽度）",
           all(
               getattr(dialog, n).x() > dialog.reset_btn.x()
               and getattr(dialog, n).width() > 0
               for n in ("zoom_in_btn", "zoom_out_btn", "fit_btn")
           ),
           f"reset.x={dialog.reset_btn.x()} "
           f"zoom.x={[getattr(dialog, n).x() for n in ('zoom_in_btn', 'zoom_out_btn', 'fit_btn')]}")
        # ---- 布局（2026-10-08 重排）：顶部功能选择 + 右侧参数面板 ----
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QAbstractButton

        header_bottom = dialog.undo_btn.y() + dialog.undo_btn.height()
        tools_at = dialog._tool_buttons["crop"].mapTo(dialog, QPoint(0, 0))
        page_at = dialog._option_page.mapTo(dialog, QPoint(0, 0))
        ok("布局：功能选择条在顶部（动作行下方），五个工具都在窗口内",
           tools_at.y() >= header_bottom
           and all(
               dialog._tool_buttons[k].mapTo(dialog, QPoint(0, 0)).x() >= 0
               and dialog._tool_buttons[k].geometry().right()
               <= dialog.width()
               for k in dialog._tool_buttons
           ),
           f"tools@{tools_at} header.bottom={header_bottom}")
        ok("布局：参数面板在画布右侧（不在工具栏那一行里）",
           page_at.x() >= dialog.canvas.geometry().right()
           and page_at.y() >= header_bottom,
           f"page@{page_at} canvas.right={dialog.canvas.geometry().right()}")
        ok("布局：右侧面板有「编辑历史」列表（第 0 格是打开时的状态）",
           dialog.history_list.isVisible()
           and dialog.history_list.count() >= 1
           and dialog.history_list.item(0).text() == "打开"
           and dialog.history_list.currentRow()
           == dialog.history_list.count() - 1,
           f"n={dialog.history_list.count()} "
           f"行={dialog.history_list.currentRow()}")
        banned = {"应用裁剪", "应用变换", "插入文字"}
        leftovers = [b.text() for b in dialog.findChildren(QAbstractButton)
                     if b.text() in banned]
        ok("布局：三个单步确认按钮已全部删除（编辑改为实时生效）",
           not leftovers, f"残留={leftovers}")
        # 回归（2026-09-30 用户截图）：__init__ 里 _set_tool 被调两次，
        # 被遗弃的旧选项页以默认几何 (0,0,100,30) 悬在左上角盖住撤销按钮
        # （deleteLater 在构造期不生效）。所有可见直儿子都不许落在 (0,0)。
        from PySide6.QtWidgets import QWidget as _QW

        strays = [
            c for c in dialog.findChildren(_QW)
            if c.parent() is dialog and c.isVisible()
            and c.x() == 0 and c.y() == 0
        ]
        ok("工具栏：没有游离控件压在左上角（旧选项页不会盖住撤销按钮）",
           not strays,
           f"strays={[f'{type(c).__name__}@{c.geometry().getRect()}' for c in strays]}")
        app.processEvents()

        # 选区门槛：< 4px 视为没有
        dialog.canvas.set_tool("crop")
        dialog.canvas._rect = QRectF(10, 10, 3, 60)
        ok("选区：小于 4px 的选区视为没有", dialog.canvas.selection() is None, "")
        dialog.canvas._rect = QRectF(10, 10, 3, 3)
        ok("选区：小于 4px 的方块也视为没有",
           dialog.canvas.selection() is None, "")

        # 裁剪 + 撤销 + 重做 + 还原
        dialog._reset_all()          # 前面的用例已把图裁成 140×90，先回 200×120
        dialog.canvas._rect = QRectF(0, 0, 100, 120)
        dialog._preview_crop()
        ok("裁剪：松手只记下待定裁剪、像素一个都没动",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120
           and dialog._pending_crop is not None, "")
        dialog._commit_crop()
        ok("裁剪：落定后画布尺寸 = 选区尺寸",
           canvas_img(dialog.canvas).width() == 100
           and canvas_img(dialog.canvas).height() == 120, "")
        ok("裁剪：落定（换图）后裁剪区重新默认全选新图",
           dialog.canvas.selection() == dialog.canvas.image_rect(),
           f"sel={dialog.canvas.selection()}")
        dialog._undo_now()
        ok("撤销：裁剪被完整回退",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120, "")
        dialog._redo_now()
        ok("重做：裁剪被重新应用", canvas_img(dialog.canvas).width() == 100, "")
        dialog._reset_all()
        ok("还原：回到打开时的图", canvas_img(dialog.canvas).width() == 200, "")
        dialog._undo_now()
        ok("还原本身可撤销：回到还原前的裁剪结果",
           canvas_img(dialog.canvas).width() == 100, "")

        # 栈深上限
        for _ in range(20):
            dialog._push_undo()
        ok("撤销栈：深度被夹在 12 以内", len(dialog._undo) <= 12,
           f"depth={len(dialog._undo)}")
        ok("撤销栈：步骤名与快照一一对齐（截断后序号也不漂移）",
           len(dialog._labels) == len(dialog._undo) + len(dialog._redo)
           and dialog._origin_label != "打开",
           f"labels={len(dialog._labels)} undo={len(dialog._undo)} "
           f"redo={len(dialog._redo)} origin={dialog._origin_label!r}")

        # ---- 步骤历史面板：记录步骤数据 + 点选跳转（2026-10-08 用户定）----
        hist_img = make_image(120, 80)
        dialog_h = ImageEditorDialog(None, hist_img)
        try:
            cvh = dialog_h.canvas
            ctrl = dialog_h.history_list
            ok("步骤历史：初始一格「打开」、光标停在它上面",
               ctrl.count() == 1 and ctrl.item(0).text() == "打开"
               and ctrl.currentRow() == 0,
               f"n={ctrl.count()} row={ctrl.currentRow()}")
            # 三步真实动作：擦除一笔 / 裁剪 / 写入文字
            cvh.set_eraser(16)
            cvh.set_tool("erase")
            cvh.stroke_started.emit()
            cvh._erase_at(QPointF(20, 40), QPointF(40, 40))
            dialog_h._set_tool("crop")
            cvh._rect = QRectF(0, 0, 60, 80)
            dialog_h._preview_crop()
            dialog_h._set_tool("text")
            block = cvh.add_text_block(
                QPointF(6, 6), 24, QColor("#000000"), "SimSun")
            block.setPlainText("历")
            dialog_h._commit_text_blocks()
            labels = [ctrl.item(i).text() for i in range(ctrl.count())]
            ok("步骤历史：三步各记一格、名字按功能取（打开/擦除/裁剪/文字）",
               labels == ["打开", "擦除", "裁剪", "文字"]
               and ctrl.currentRow() == 3,
               f"labels={labels} row={ctrl.currentRow()}")
            ok("步骤历史：三步走完图是 60×80",
               canvas_img(cvh).width() == 60
               and canvas_img(cvh).height() == 80,
               f"size={canvas_img(cvh).width()}x{canvas_img(cvh).height()}")
            ctrl.setCurrentRow(0)
            app.processEvents()
            ok("步骤历史：点第 0 格 → 图回到打开时（120×80）、三步进重做",
               canvas_img(cvh).width() == 120 and len(dialog_h._redo) == 3
               and ctrl.currentRow() == 0,
               f"w={canvas_img(cvh).width()} redo={len(dialog_h._redo)} "
               f"row={ctrl.currentRow()}")
            ctrl.setCurrentRow(2)
            app.processEvents()
            ok("步骤历史：点第 2 格 → 前进到「裁剪」那一步（60×80）",
               canvas_img(cvh).width() == 60 and ctrl.currentRow() == 2,
               f"w={canvas_img(cvh).width()} row={ctrl.currentRow()}")
            # 在历史中间做新动作 ⇒ 后面那格作废（重做链被截断）
            dialog_h._set_tool("crop")
            cvh._rect = QRectF(0, 0, 30, 80)
            dialog_h._preview_crop()
            dialog_h._commit_crop()
            labels = [ctrl.item(i).text() for i in range(ctrl.count())]
            ok("步骤历史：跳回中间后再改动 ⇒ 后面的「文字」那格作废",
               labels == ["打开", "擦除", "裁剪", "裁剪"]
               and ctrl.currentRow() == 3
               and canvas_img(cvh).width() == 30,
               f"labels={labels} row={ctrl.currentRow()} "
               f"w={canvas_img(cvh).width()}")
        finally:
            dialog_h.deleteLater()

        # 擦除：橡皮擦涂过的地方污点被擦成白底（白 → 黑 → 白）
        white_img = make_image(200, 120)
        for x in range(95, 105):  # 黑污点 x∈[95,105) × y∈[55,65)
            for y in range(55, 65):
                white_img.setPixel(x, y, 0xFF000000)
        dialog2 = ImageEditorDialog(None, white_img)
        try:
            dialog2.canvas.set_eraser(20)
            dialog2.canvas.set_tool("erase")
            # 真实一笔 = 先发 stroke_started（压撤销点）再擦
            dialog2.canvas.stroke_started.emit()
            dialog2.canvas._erase_at(QPointF(100, 60), QPointF(120, 60))
            wiped = canvas_img(dialog2.canvas).pixelColor(100, 60)
            ok("擦除：橡皮擦涂过的污点被擦成白底", wiped.value() > 230,
               f"pixel={wiped.value()}")
            ok("擦除：一笔开始压了撤销点（stroke_started 接线）",
               len(dialog2._undo) == 1, f"undo={len(dialog2._undo)}")
        finally:
            dialog2.deleteLater()

        # 扭曲：一笔一个撤销点；非实时预览在松手时回放完整笔划
        distort_img = make_image(200, 120)
        for x in range(70, 73):
            for y in range(58, 63):
                distort_img.setPixel(x, y, 0xFF000000)
        dialog_distort = ImageEditorDialog(None, distort_img)
        try:
            distort_canvas = dialog_distort.canvas
            dialog_distort.show()
            app.processEvents()
            distort_canvas.set_tool("distort")
            distort_canvas.set_distortion_options(
                size=40, hardness=100, strength=100, spacing=25,
                mode="move", interpolation="nearest",
                high_quality_preview=True, realtime=True)
            start = QPointF(70, 60)
            end = QPointF(80, 60)
            start_view = QPointF(distort_canvas.mapFromScene(start))
            end_view = QPointF(distort_canvas.mapFromScene(end))
            distort_canvas.mousePressEvent(mouse_event("press", start_view))
            preview_before_move = distort_canvas._distort_preview_image.copy()
            distort_canvas.mouseMoveEvent(mouse_event("move", end_view))
            ok("扭曲：鼠标事件先合并，预览计算由 16ms 节流器统一调度",
               distort_canvas._distort_preview_pending_end is not None
               and distort_canvas._distort_preview_image == preview_before_move
               and distort_canvas._distort_preview_timer is not None
               and distort_canvas._distort_preview_timer.isActive(),
               "")
            distort_canvas._on_distortion_preview_tick()
            ok("扭曲：拖动时只刷新邻近瓦片，原始全分辨率图保持不变",
               bool(distort_canvas._distort_preview_items)
               and not distort_canvas._distort_preview_dirty_tiles
               and is_dark(canvas_img(distort_canvas).pixelColor(70, 60))
               and canvas_img(distort_canvas).pixelColor(80, 60).value() > 230,
               f"tiles={len(distort_canvas._distort_preview_items)}")
            distort_canvas.mouseReleaseEvent(mouse_event("release", end_view))
            ok("扭曲：松开后提交整笔并清除预览瓦片",
               not distort_canvas._distort_preview_items,
               "")
            result_after_stroke = dialog_distort.result_image()
            ok("扭曲：实时笔划移动像素、同步返回图像并压入一个撤销点",
               is_dark(canvas_img(distort_canvas).pixelColor(80, 60))
               and canvas_img(distort_canvas).pixelColor(70, 60).value() > 230
               and result_after_stroke is not None
               and is_dark(result_after_stroke.pixelColor(80, 60))
               and len(dialog_distort._undo) == 1,
               f"target={canvas_img(distort_canvas).pixelColor(80, 60).value()} "
               f"undo={len(dialog_distort._undo)}")
            dialog_distort._undo_now()
            ok("扭曲：撤销整笔恢复原图",
               is_dark(canvas_img(distort_canvas).pixelColor(70, 60))
               and canvas_img(distort_canvas).pixelColor(80, 60).value() > 230,
               "")

            distort_canvas.set_distortion_options(realtime=False)
            distort_canvas.mousePressEvent(mouse_event("press", start_view))
            distort_canvas.mouseMoveEvent(mouse_event("move", end_view))
            ok("扭曲：关闭实时预览时拖动暂不改像素",
               is_dark(canvas_img(distort_canvas).pixelColor(70, 60))
               and canvas_img(distort_canvas).pixelColor(80, 60).value() > 230,
               "")
            distort_canvas.mouseReleaseEvent(mouse_event("release", end_view))
            ok("扭曲：关闭实时预览后松手应用完整笔划",
               is_dark(canvas_img(distort_canvas).pixelColor(80, 60))
               and canvas_img(distort_canvas).pixelColor(70, 60).value() > 230,
               "")

            distort_canvas.set_image(make_image(2400, 1400))
            distort_canvas.set_distortion_options(realtime=True)
            distort_canvas._begin_distortion_stroke(QPointF(1200, 700))
            preview = distort_canvas._distort_preview_image
            ok("扭曲：大图实时预览自动降采样至 200 万像素预算",
               preview is not None
               and preview.width() * preview.height() <= 2_000_000
               and preview.width() * preview.height() < 2400 * 1400,
               f"preview={preview.size() if preview is not None else None}")
            distort_canvas._finish_distortion_stroke()

            # ⚠️ 单帧渲染量必须有预算：鼠标猛地一跳（或系统把一串 move 并成
            #    一个事件）时脏区能横跨上千像素，一次渲染完就是一次卡顿。
            #    超预算的部分**整段挂回脏矩形**留给下一次 tick，且节流器不许停。
            import desktop.components.viewers.image_editor.canvas.distortion \
                as canvas_distortion_mod
            original_budget = canvas_distortion_mod.DISTORT_PREVIEW_RENDER_PIXELS
            real_render = canvas_distortion_mod.render_rect_into
            rendered: list[tuple[int, int, int, int]] = []

            def spy_render(image, origin, field, scale, rect, interpolation):
                rendered.append(rect)
                return real_render(image, origin, field, scale, rect,
                                   interpolation)

            canvas_distortion_mod.DISTORT_PREVIEW_RENDER_PIXELS = 4096
            canvas_distortion_mod.render_rect_into = spy_render
            try:
                distort_canvas.set_distortion_options(
                    size=200, hardness=50, strength=50, spacing=5,
                    mode="move", interpolation="nearest", realtime=True)
                jump_start = QPointF(600, 700)
                jump_end = QPointF(1800, 700)
                distort_canvas.mousePressEvent(mouse_event(
                    "press", QPointF(distort_canvas.mapFromScene(jump_start))))
                distort_canvas.mouseMoveEvent(mouse_event(
                    "move", QPointF(distort_canvas.mapFromScene(jump_end))))
                distort_canvas._on_distortion_preview_tick()
                pending = distort_canvas._distort_preview_dirty_rect
                budget_rows = 4096 // max(1, rendered[0][2] - rendered[0][0]) \
                    if rendered else 0
                ok("扭曲预览：单帧渲染量受像素预算约束，超出的脏区挂给下一帧",
                   len(rendered) == 1
                   and rendered[0][3] - rendered[0][1] <= budget_rows
                   and pending is not None
                   and pending[3] - pending[1] > rendered[0][3] - rendered[0][1]
                   and distort_canvas._distort_preview_timer is not None
                   and distort_canvas._distort_preview_timer.isActive(),
                   f"rendered={rendered} 预算行={budget_rows} pending={pending}")
                distort_canvas.mouseReleaseEvent(mouse_event(
                    "release", QPointF(distort_canvas.mapFromScene(jump_end))))
            finally:
                canvas_distortion_mod.DISTORT_PREVIEW_RENDER_PIXELS = original_budget
                canvas_distortion_mod.render_rect_into = real_render
        finally:
            dialog_distort.deleteLater()

        # 文字：就地文字块（编辑态 + 拖拽移动 + 插入写图 + 切工具自动写入）
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent
        from qfluentwidgets import ComboBox

        dialog3 = ImageEditorDialog(None, make_image(400, 200))
        try:
            canvas3 = dialog3.canvas
            canvas3.set_tool("text")
            item = canvas3.add_text_block(
                QPointF(30, 30), 48, QColor("#000000"), "SimSun")
            ok("文字：落点生成文字块、开启就地编辑（文本交互）",
               isinstance(item, TextBlockItem)
               and bool(item.textInteractionFlags()
                        & Qt.TextInteractionFlag.TextEditorInteraction),
               f"type={type(item).__name__} "
               f"flags={item.textInteractionFlags()}")

            # 焦点路由：键盘输入必须能到达就地文字块（2026-10-01 回归：
            # 画布 NoFocus 时打字全部落空，用户报「输入没效果」）
            from PySide6.QtTest import QTest

            typing = canvas3.add_text_block(
                QPointF(100, 100), 48, QColor("#000000"), "SimSun")
            QTest.keyClicks(canvas3, "Ab")
            ok("文字：键盘输入直达就地文字块（视图→场景焦点项）",
               typing.toPlainText() == "Ab",
               f"text={typing.toPlainText()!r}")

            def item_mouse(kind: str, item, scene_pos: QPointF):
                types = {
                    "press": QEvent.Type.GraphicsSceneMousePress,
                    "move": QEvent.Type.GraphicsSceneMouseMove,
                    "release": QEvent.Type.GraphicsSceneMouseRelease,
                }
                ev = QGraphicsSceneMouseEvent(types[kind])
                ev.setButton(
                    Qt.MouseButton.LeftButton if kind != "move"
                    else Qt.MouseButton.NoButton)
                # move：拖拽进行中（按住左键）；release：左键已松开
                ev.setButtons(
                    Qt.MouseButton.LeftButton if kind != "release"
                    else Qt.MouseButton.NoButton)
                ev.setScenePos(scene_pos)
                ev.setPos(item.mapFromScene(scene_pos))
                return ev

            item.setPlainText("测试")
            item.mousePressEvent(item_mouse(
                "press", item, QPointF(30, 30)))
            item.mouseMoveEvent(item_mouse(
                "move", item, QPointF(80, 95)))
            item.mouseReleaseEvent(item_mouse(
                "release", item, QPointF(80, 95)))
            ok("文字：按住拖动移动文字块（单击放光标不受影响）",
               (item.pos() - QPointF(80, 95)).manhattanLength() < 1e-6,
               f"pos={item.pos()}")

            undo_before = len(dialog3._undo)
            dialog3._commit_text_blocks()
            burned = canvas_img(dialog3.canvas)
            has_dark = any(
                is_dark(burned.pixelColor(x, y))
                for y in range(40, 130, 3) for x in range(60, 200, 3)
            )
            ok("文字：「插入文字」把文字块写进图片（落点附近出现深色像素）",
               has_dark, "")
            ok("文字：插入压了撤销点",
               len(dialog3._undo) == undo_before + 1,
               f"undo={len(dialog3._undo)} before={undo_before}")
            ok("文字：插入后画布上的文字块清空",
               canvas3.text_blocks() == [], "")

            # 切走工具：未插入的非空文字块自动写入
            item2 = canvas3.add_text_block(
                QPointF(250, 30), 48, QColor("#000000"), "SimSun")
            item2.setPlainText("自动")
            undo_before = len(dialog3._undo)
            dialog3._set_tool("crop")
            ok("文字：切走工具时未插入的文字自动写入",
               canvas3.text_blocks() == []
               and len(dialog3._undo) == undo_before + 1,
               f"undo={len(dialog3._undo)} before={undo_before}")
            # 空块（点了落点没打字）失焦自删、不产生撤销点
            dialog3._set_tool("text")
            canvas3.add_text_block(
                QPointF(60, 60), 48, QColor("#000000"), "SimSun")
            undo_before = len(dialog3._undo)
            dialog3._set_tool("crop")
            ok("文字：空文字块既不写入也不压撤销点",
               len(dialog3._undo) == undo_before, "")
            # ---- 选项行：字体下拉（中文为主 + 几个常用西文） ----
            from desktop.ui.fonts import LATIN_TEXT_FONTS, text_font_families

            dialog3._set_tool("text")
            _op3 = dialog3._option_page
            assert _op3 is not None  # 文字工具的选项行必然已建
            combo = _op3.findChild(ComboBox)
            texts = ([combo.itemText(i) for i in range(combo.count())]
                     if combo is not None else [])
            latin_here = [t for t in texts if t in LATIN_TEXT_FONTS]
            first_latin = (texts.index(latin_here[0]) if latin_here
                           else len(texts))
            ok("文字：选项行有字体下拉，且用的是「中文为主」的清单"
               "（不是系统全量字体）",
               combo is not None and texts == text_font_families()
               and len(texts) > 0,
               f"n={len(texts)} first={texts[:3]}")
            ok("文字：西文只留几个常用、且全排在中文字体之后",
               len(latin_here) <= len(LATIN_TEXT_FONTS)
               and all(t not in LATIN_TEXT_FONTS for t in texts[:first_latin]),
               f"latin={latin_here} first_latin={first_latin}")

            # ---- 颜色：一个按钮 + 面板里的常用色块 + 整块样式（手机作图口径） ----
            from desktop.ui.color_picker import (
                ColorPickerButton as GujiColorPicker,
            )
            from desktop.ui.color_picker import SwatchButton

            from desktop.components.viewers.image_editor import TEXT_SWATCHES

            picker = _op3.findChild(GujiColorPicker)
            ok("文字：选项行是一个颜色按钮（色点 + 十六进制 + 下拉）",
               picker is not None
               and picker.color().name() == dialog3._text_color,
               f"picker={picker}")
            assert picker is not None  # 上一条 ok 已断言颜色按钮存在
            ok("文字：常用色块不再散在选项行上（已搬进选择器面板）",
               _op3.findChildren(SwatchButton) == [], "")
            styled = canvas3.add_text_block(
                QPointF(150, 110), 48, QColor("#000000"), "SimSun")
            styled.setPlainText("样式块")
            ok("文字：新块即焦点块", canvas3.focused_text_block() is styled, "")
            picker._open_popup()
            app.processEvents()
            panel = picker.popup()
            swatches = list(panel._swatches) if panel is not None else []
            ok("文字：面板里有全部常用色块（黑墨/白粉/朱批/藏蓝/赭黄/黛绿）",
               panel is not None and len(swatches) == len(TEXT_SWATCHES)
               and all(s.toolTip() for s in swatches),
               f"n={len(swatches)}")
            assert panel is not None  # 上一条 ok 已断言面板存在
            zhu = next(s for s in swatches
                       if s.color().name().lower() == "#d32f2f")
            dialog3._text_color = "#000000"
            zhu.click()
            app.processEvents()
            ok("文字：面板里点常用色块 → 整块即时换色并收起面板",
               styled.defaultTextColor().name() == "#d32f2f"
               and dialog3._text_color == "#d32f2f"
               and not panel.isVisible(),
               f"color={styled.defaultTextColor().name()} "
               f"visible={panel.isVisible()}")
            picker.colorChanged.emit(QColor("#1976d2"))
            ok("文字：选择器换色对整块即时生效",
               styled.defaultTextColor().name() == "#1976d2"
               and dialog3._text_color == "#1976d2",
               f"color={styled.defaultTextColor().name()}")
            # ⚠️ 别硬编码 "Arial"：离屏环境若注册过内置字体，QFontDatabase
            # 就非空但只剩那一种族（如 FangSong），Arial 根本不在下拉里
            # （findData 落到 -1 → 换成下标 0，断言就假红了）。护栏的本意
            # 是"换字体对整块生效"：能挑到与当前不同的族（优先 Arial）
            # 才切换验证；整个下拉只有当前一种族的环境越过。
            target_family = ("Arial" if "Arial" in texts
                             else (latin_here[0] if latin_here else None))
            if target_family is None or target_family == "SimSun":
                others = [t for t in texts if t != "SimSun"]
                target_family = others[-1] if others else None
            assert combo is not None  # 上一条 ok 已断言字体下拉存在
            combo.setCurrentIndex(max(0, combo.findData(target_family)))
            app.processEvents()
            ok("文字：换字体对整块即时生效（整体切换，非逐字；"
               "下拉只有当前一种族的环境越过）",
               len(texts) < 2
               or (target_family is not None
                   and styled.font().family().lower() == target_family.lower()),
               f"want={target_family} got={styled.font().family()} "
               f"texts={texts[:4]}")

            # ---- 回归（2026-10-01 用户报障「文字大小不生效」）----
            # 根因：选项行控件抢走画布键盘焦点 → 场景焦点项变 None → 按焦点项
            # 找块的样式改动全部落空。样式现在走"当前样式块"，与焦点解耦。
            from qfluentwidgets import Slider as FluentSlider

            _op3b = dialog3._option_page
            assert _op3b is not None  # 文字工具的选项行必然已建
            size_slider = _op3b.findChild(FluentSlider)
            ok("回归：字号滑杆是 NoFocus（拖动不抢画布焦点、光标不丢）",
               size_slider is not None
               and size_slider.focusPolicy() == Qt.FocusPolicy.NoFocus,
               f"policy={size_slider.focusPolicy() if size_slider else None}")
            assert size_slider is not None  # 上一条 ok 已断言滑杆存在
            # ⚠️ 必须真显示弹窗：控件焦点只在真窗口里才生效（不显示时
            #    setFocus 是空操作，场景焦点项也不会被清）
            dialog3.show()
            app.processEvents()
            app.processEvents()
            canvas3.setFocus()
            styled.setFocus()
            app.processEvents()
            ok("回归：文字块拿着场景焦点", canvas3.focused_text_block() is styled,
               "")
            # 工具栏「完成」按钮是可聚焦控件，点它（或任何选项行控件）就会把
            # 键盘焦点从画布抢走——正是用户报障的触发动作
            dialog3.done_btn.setFocus()
            app.processEvents()
            ok("回归：焦点被抢走后场景焦点项为空",
               canvas3.focused_text_block() is None, "")
            size_slider.setValue(96)
            app.processEvents()
            ok("回归：焦点被抢后改字号仍作用在当前文字块上（不再落空）",
               styled.font().pixelSize() == 96 and dialog3._text_size == 96,
               f"px={styled.font().pixelSize()} size={dialog3._text_size}")
            picker.colorChanged.emit(QColor("#2e7d32"))
            ok("回归：焦点被抢后换颜色同样落在当前文字块上",
               styled.defaultTextColor().name() == "#2e7d32",
               f"color={styled.defaultTextColor().name()}")
            canvas3.setFocus()
            styled.setFocus()
            app.processEvents()

            # ---- 悬停边界虚线框：悬停显示 / 拖动跟随 / 松手消失 ----
            # ⚠️ 事件走 **viewport 事件管线**（与真实鼠标一致）；直接调
            # canvas.mousePressEvent 不经 viewportEvent，场景收不到
            dialog3.show()
            app.processEvents()
            app.processEvents()

            def post(kind: str, pos: QPointF,
                     drag: bool = False) -> None:
                types = {
                    "press": QEvent.Type.MouseButtonPress,
                    "move": QEvent.Type.MouseMove,
                    "release": QEvent.Type.MouseButtonRelease,
                }
                app.sendEvent(canvas3.viewport(), QMouseEvent(
                    types[kind], pos,
                    Qt.MouseButton.LeftButton if kind == "press"
                    else Qt.MouseButton.NoButton,
                    Qt.MouseButton.LeftButton
                    if kind == "press" or drag
                    else Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier))
                app.processEvents()

            block_center = QPointF(
                canvas3.mapFromScene(styled.mapToScene(
                    styled.boundingRect().center())))
            # 悬停：虚线框出现且框住块身
            post("move", block_center)
            hover_rect = canvas3._text_outline.rect()
            expect_rect = styled.mapRectToScene(styled.boundingRect())
            ok("文字：悬停文字出现边界虚线框（范围=块身）",
               canvas3._text_outline.isVisible()
               and (hover_rect.center() - expect_rect.center())
               .manhattanLength() < 2.0
               and abs(hover_rect.width() - expect_rect.width()) < 2.0,
               f"rect={hover_rect} expect={expect_rect}")
            # 拖动（画布→场景→块的真实链路）：框跟随、块整体移动。
            # ⚠️ 按下必须走 QTest（合成 sendEvent 的 press 场景不受理），
            #    移动/松手 sendEvent 即可（块已抓住鼠标，画布只做转发）
            from PySide6.QtTest import QTest

            QTest.mousePress(
                canvas3.viewport(), Qt.MouseButton.LeftButton,
                pos=block_center.toPoint())
            post("move", block_center + QPointF(60, 30), drag=True)
            moved_rect = canvas3._text_outline.rect()
            moved_expect = styled.mapRectToScene(styled.boundingRect())
            ok("文字：按住拖动整块移动、虚线框跟随",
               styled.scenePos() != QPointF(150, 110)
               and canvas3._text_outline.isVisible()
               and (moved_rect.center() - moved_expect.center())
               .manhattanLength() < 1.0
               and abs(moved_rect.width() - moved_expect.width()) < 1.0,
               f"pos={styled.scenePos()} rect={moved_rect} "
               f"expect={moved_expect}")
            # ⚠️ 松手同样必须走 QTest：合成 sendEvent 的 release 场景不受理
            QTest.mouseRelease(
                canvas3.viewport(), Qt.MouseButton.LeftButton,
                pos=(block_center + QPointF(60, 30)).toPoint())
            ok("文字：松手落位、虚线框消失",
               not canvas3._text_outline.isVisible()
               and canvas3._scene.mouseGrabberItem() is None,
               f"visible={canvas3._text_outline.isVisible()}")
            # 悬停离开块：虚线框隐藏
            post("move", QPointF(5, 5))
            ok("文字：悬停离开文字块，虚线框隐藏",
               not canvas3._text_outline.isVisible(), "")
            canvas3.clear_text_blocks()
        finally:
            dialog3.deleteLater()

        # ---- 变换：统一变换（移动/旋转/切变/缩放 + 实时预览 + 烘焙） ----
        timg = make_image(200, 120)
        for x in range(150, 170):  # 黑块 x∈[150,170) × y∈[50,70)
            for y in range(50, 70):
                timg.setPixel(x, y, 0xFF000000)
        dialog4 = ImageEditorDialog(None, timg)
        try:
            canvas4 = dialog4.canvas
            canvas4.set_tool("transform")
            ok("变换：进入工具默认全选、无待应用变换",
               canvas4.selection() == canvas4.image_rect()
               and canvas4.transform_pending() is None, "")

            def vpos(scene: QPointF) -> QPointF:
                return QPointF(canvas4.mapFromScene(scene))

            # 框内拖 = 移动（真实鼠标事件走一遍）；**松手只挂起、离开工具才烘焙**
            dialog4.show()
            app.processEvents()
            app.processEvents()
            undo_before = len(dialog4._undo)
            canvas4.mousePressEvent(mouse_event("press", vpos(QPointF(160, 60))))
            _paint = canvas4._paint_image
            _base = canvas4._image
            assert _paint is not None and _base is not None  # 进入预览态后浮层/底图必有
            ok("变换：按下即进入实时预览（浮层出现、真像素未动）",
               canvas4._mode is not None and canvas4._mode[0] == "xf_move"
               and canvas4._float_item is not None
               and _base.pixelColor(160, 60).value() < 128,
               f"mode={canvas4._mode} "
               f"base={_base.pixelColor(160, 60).value()}")
            canvas4.mouseMoveEvent(mouse_event("move", vpos(QPointF(130, 60))))
            canvas4.mouseReleaseEvent(mouse_event(
                "release", vpos(QPointF(130, 60))))
            # ⚠️ 2026-10-09 起**松手不烘焙**（用户报"不能实时预览、最后才预览"）：
            #    松手只是把这次变换挂起，画布上的浮层继续实时显示；整幅重采样
            #    推迟到离开变换工具/点「完成」——所以此刻像素、撤销点都没动。
            ok("变换：松手只挂起预览（像素与撤销栈都没动）",
               canvas4.has_pending_transform()
               and len(dialog4._undo) == undo_before
               and canvas_img(canvas4).pixelColor(160, 60).value() < 128,
               f"pending={canvas4.has_pending_transform()} "
               f"undo={len(dialog4._undo)} before={undo_before}")
            # 离开变换工具 → 此刻才烘焙，且一步一个撤销点
            dialog4._set_tool("erase")
            baked = canvas_img(canvas4)
            # grow：整幅选区左移 30 ⇒ 新画布 = 原图 ∪ 移位后内容，左上角在
            # 原坐标 (−30, 0)，尺寸不变（移位量正好等于外扩量）。新画布里的
            # 坐标 = 原坐标 − origin = 原坐标 + 30。
            ok("变换：切走工具才烘焙（−30,0 平移已落地，画布尺寸不变）",
               baked.width() == 200 and baked.height() == 120
               and canvas4.transform_pending() is None,
               f"size={baked.width()}x{baked.height()} "
               f"pending={canvas4.transform_pending()}")
            ok("变换：烘焙后内容平移、原位置填白（烘焙与预览一致）",
               baked.pixelColor(125 + 30, 60).value() < 128
               and baked.pixelColor(160 + 30, 60).value() > 230,
               f"dark={baked.pixelColor(155, 60).value()} "
               f"white={baked.pixelColor(190, 60).value()}")
            ok("变换：一步一个撤销点、历史多一格「变换」",
               len(dialog4._undo) == undo_before + 1
               and dialog4.history_list.item(
                   dialog4.history_list.count() - 1).text() == "变换"
               and dialog4.history_list.currentRow()
               == dialog4.history_list.count() - 1,
               f"undo={len(dialog4._undo)} before={undo_before} "
               f"历史={history_labels(dialog4)}")

            # ---- 「完成」直接收尾：挂起的变换必须落到实体图（2026-10-10 报障） ----
            # 松手只挂起（上面的用例刚验过），此后**不切工具**、直接点「完成」：
            # _finish 里的 _commit_transform 不带 force 的话会被"挂起跳过"分支
            # 原样退回，烘焙整个被跳过 ⇒ 结果图还是原图（用户报的正是它）。
            from PySide6.QtWidgets import QDialog

            dialogF = ImageEditorDialog(None, timg)
            try:
                canvasF = dialogF.canvas
                canvasF.set_tool("transform")
                canvasF.transform_rotate(90)
                canvasF.make_transform_pending()   # 模拟真实拖动松手后的挂起态
                ok("变换：挂起态直接点「完成」前像素未动",
                   canvasF.has_pending_transform()
                   and canvas_img(canvasF).size() == timg.size(), "")
                dialogF._finish()
                done = dialogF.result_image()
                ok("变换：「完成」直接收尾也烘焙（结果 = 旋转后 120×200）",
                   dialogF.result() == QDialog.DialogCode.Accepted
                   and done is not None
                   and (done.width(), done.height()) == (120, 200)
                   and canvasF.transform_pending() is None,
                   f"result={dialogF.result()} size="
                   + ("None" if done is None
                      else f"{done.width()}x{done.height()}"))
            finally:
                dialogF.deleteLater()

            # ---- 透明源图：烘焙后空出来的地方保持透明（2026-10-10 报障） ----
            # 去底色产物整幅旋转：画布预览（10-09 起）空处透明，烘焙却留着
            # 两处硬编码填白（原位 fillRect + grow 底图）⇒ 存盘变白底。
            # 空处填色统一为 _empty_fill：源图真有 alpha ⇒ 透明，否则白。
            # 内容铺满整幅（只留一个透明孔）：内容收紧（_trim_transparent_edges）
            # 对"贴边内容"是 no-op，90° 互换的尺寸口径不变。
            from PySide6.QtGui import QColor as _QC

            timgA = make_image(200, 120)
            timgA.fill(_QC(255, 0, 0, 255))
            for x in range(96, 104):            # 中央 8×8 透明孔
                for y in range(56, 64):
                    timgA.setPixel(x, y, 0x00000000)
            dialogA = ImageEditorDialog(None, timgA)
            try:
                canvasA = dialogA.canvas
                canvasA.set_tool("transform")
                canvasA.transform_rotate(90)
                dialogA._commit_transform(force=True)
                got = canvas_img(canvasA)
                ok("变换：透明源图烘焙不染白（尺寸 90° 互换、中心孔保持透明）",
                   abs(got.width() - 120) <= 1 and abs(got.height() - 200) <= 1
                   and got.pixelColor(60, 100).alpha() == 0,
                   f"size={got.width()}x{got.height()} "
                   f"hole_a={got.pixelColor(60, 100).alpha()}")
                _reds = [
                    (x, y)
                    for x in range(0, got.width(), 2)
                    for y in range(0, got.height(), 2)
                    if got.pixelColor(x, y).alpha() > 200
                    and got.pixelColor(x, y).red() > 150
                    and got.pixelColor(x, y).green() < 100
                ]
                ok("变换：透明源图烘焙后红块完好（内容没被垫底吃掉）",
                   len(_reds) >= 5000
                   and got.pixelColor(2, 2).red() > 150,
                   f"红块采样点={len(_reds)} "
                   f"角={got.pixelColor(2, 2).name()}")
                # clip 档：画布尺寸不变，原位必须真清除（Clear）——
                # 透明色 SourceOver 盖不住，会留 ghost + 白底双重 bug。
                # ⚠️ 入口内容提取后主体＝内容块本身（20×20），转 90° 会铺满
                #    整幅、没有空处可验 ghost ⇒ 转 45°，四角空出来。
                timgC = make_image(200, 120)
                timgC.fill(_QC(0, 0, 0, 0))
                for x in range(150, 170):
                    for y in range(50, 70):
                        timgC.setPixel(x, y, 0xFFFF0000)
                timgC.setPixel(169, 69, 0x00000000)   # 缺角 ⇒ 真有 alpha
                timgC.setPixel(168, 69, 0x00000000)
                timgC.setPixel(169, 68, 0x00000000)
                dialogC = ImageEditorDialog(None, timgC)
                try:
                    canvasC = dialogC.canvas
                    gotC = canvas_img(canvasC)
                    ok("编辑入口内容提取：打开带空白边的透明图，主体＝内容外框",
                       (gotC.width(), gotC.height()) == (20, 20)
                       and gotC.pixelColor(10, 10).alpha() > 200,
                       f"size={gotC.width()}x{gotC.height()}")
                    canvasC.set_tool("transform")
                    canvasC._xf_clipping = "clip"
                    canvasC.transform_rotate(45)
                    dialogC._commit_transform(force=True)
                    got2 = canvas_img(canvasC)
                    _reds2 = [
                        (x, y)
                        for x in range(0, got2.width(), 2)
                        for y in range(0, got2.height(), 2)
                        if got2.pixelColor(x, y).alpha() > 200
                        and got2.pixelColor(x, y).red() > 150
                        and got2.pixelColor(x, y).green() < 100
                    ]
                    ok("变换：透明源图 clip 档不染白、原位不留 ghost（红块只有一份）",
                       abs(got2.width() - 20) <= 1
                       and abs(got2.height() - 20) <= 1
                       and got2.pixelColor(2, 2).alpha() == 0
                       and 20 <= len(_reds2) <= 90,
                       f"size={got2.width()}x{got2.height()} "
                       f"corner_a={got2.pixelColor(2, 2).alpha()} "
                       f"红块采样点={len(_reds2)}")
                finally:
                    dialogC.deleteLater()

                # 入口提取**不碰**不透明图：白边可能是"纸"的内容。
                dialogO = ImageEditorDialog(None, make_image(200, 120))
                try:
                    gotO = canvas_img(dialogO.canvas)
                    ok("编辑入口不裁不透明图（白边可能是纸的内容）",
                       (gotO.width(), gotO.height()) == (200, 120),
                       f"size={gotO.width()}x{gotO.height()}")
                finally:
                    dialogO.deleteLater()
            finally:
                dialogA.deleteLater()

            # ---- 透明源图「旋转→保存→再旋转」不再越滚越大（2026-10-10） ----
            # 旧版外框按**画布矩形四角**算：A(200×120, 内容 100×60) 转 45° →
            # 外框 ≈114²（恰＝内容外框，暂无多余边）；存盘后二次编辑的主体
            # 变成 A1（含四角空白），再转 45° 外框按 A1 四角又扩 √2 倍 ≈161²，
            # 内容占比每转一次缩一截。内容收紧后：烘焙结果裁到**非透明像素**
            # 的真实外框，二次旋转回到内容本身的 90° 外框 ≈62×102。
            timgB = make_image(200, 120)
            timgB.fill(_QC(0, 0, 0, 0))
            for x in range(50, 150):
                for y in range(30, 90):
                    timgB.setPixel(x, y, 0xFF00FF00)   # 居中绿块 100×60
            for x in range(96, 104):            # 中央 8×8 透明孔：去底色
                for y in range(56, 64):         # 产物 bbox 内总有透明像素
                    timgB.setPixel(x, y, 0x00000000)
            dialogB = ImageEditorDialog(None, timgB)
            try:
                canvasB = dialogB.canvas
                canvasB.set_tool("transform")
                canvasB.transform_rotate(45)
                dialogB._commit_transform(force=True)
                r1 = canvas_img(canvasB)
                ok("变换：透明图转 45° 外框＝内容外框（≈114²，无多余边）",
                   106 <= r1.width() <= 122 and 106 <= r1.height() <= 122,
                   f"r1={r1.width()}x{r1.height()}")
                canvasB.set_tool("transform")
                canvasB.transform_rotate(45)
                dialogB._commit_transform(force=True)
                r2 = canvas_img(canvasB)
                _area1, _area2 = r1.width() * r1.height(), \
                    r2.width() * r2.height()
                ok("变换：再转 45° 内容收紧回 90° 外框（≈62×102，不按 √2 滚大）",
                   54 <= r2.width() <= 72 and 94 <= r2.height() <= 112
                   and _area2 < _area1 * 0.6,
                   f"r2={r2.width()}x{r2.height()} "
                   f"面积比={_area2 / _area1:.2f}")
            finally:
                dialogB.deleteLater()

            # ---- 内容四角节点：sidecar 落盘 + 二次编辑恢复（2026-10-10） ----
            # 用户口径：p1..p4 旋转后变成 p11..p41，节点数据随图片一起保存；
            # 二次编辑时读回来，「统一变换」的可编辑区域＝内容四边形本身，
            # 框/手柄恢复到"没保存时"的状态，区域外都是无意义空白。
            from pathlib import Path as _Path

            from desktop.components.viewers.image_editor import (
                quad_path, read_quad, sync_content_quad, upright_image,
                write_quad,
            )
            from tests.tmpdir import temp_dir as _temp_dir

            _qdir = _temp_dir("quad_")
            _qpath = _qdir / "page.png"
            baseA = make_image(200, 120)
            # ⚠️ 打一个色块标记：纯白图查不出"反变换位移"（旧回归只查尺寸，
            #    矩阵顺序错了照样绿——2026-10-10「PA1 顶部被削一段」漏网）。
            for _mx in range(30, 50):
                for _my in range(15, 35):
                    baseA.setPixel(_mx, _my, 0xFF0000FF)   # 蓝块 20×20
            rect0 = QRectF(0, 0, 200, 120)
            v45 = rotate_about(QPointF(100, 60), 45.0)
            look = compose_transform(
                baseA, rect0, v45, baseA.copy(), grow=True)[0]
            look.save(str(_qpath), "PNG")
            write_quad(_qpath, rect0, v45)
            _rq = read_quad(_qpath)
            ok("内容节点：sidecar 写读回环（rect0/V 保真）",
               _rq is not None and _rq[0] == rect0 and _rq[1] == v45,
               f"rect={None if _rq is None else _rq[0]}")
            up = upright_image(look, rect0, v45, "linear")
            _up_ok = up is not None and (up.width(), up.height()) == (200, 120)
            _mark = [
                (36, 21), (44, 29), (40, 25),   # 蓝块内点：原位才算恢复对
                (100, 60),                       # 中心（rotate_about 的轴心）
            ]
            _mark_hits = [
                _up_ok
                and up.pixelColor(x, y).alpha() > 200
                and up.pixelColor(x, y).blue() > 150
                and up.pixelColor(x, y).red() < 100
                for x, y in _mark[:3]]
            ok("内容节点：反变换回 upright（尺寸回到 rect0）",
               _up_ok,
               "size=" + ("None" if up is None
                          else f"{up.width()}x{up.height()}"))
            ok("内容节点：反变换内容**原位**（蓝块 3 内点全中，矩阵顺序正确）",
               all(_mark_hits),
               f"hits={_mark_hits} center={_up_ok and up.pixelColor(100, 60).name()}")

            editorQ = ImageEditorDialog(None, look, save_back=True)
            try:
                editorQ.source_path = str(_qpath)
                # 进变换工具 ⇒ 触发 sidecar 恢复（小图走同步档，无进度框）
                editorQ.canvas.set_tool("transform")
                gotQ = canvas_img(editorQ.canvas)

                from desktop.components.viewers.image_editor.content_quad \
                    import quad_frame as _quad_frame
                from PySide6.QtGui import QTransform as _QTx

                _ox, _oy, _fw, _fh = _quad_frame(v45, rect0)
                seedQ = _QTx(v45) * _QTx().translate(-_ox, -_oy)
                ok("内容节点：PB1 作画布不换图（画布＝文件原样、恢复已武装）",
                   (gotQ.width(), gotQ.height())
                   == (look.width(), look.height())
                   and gotQ == look
                   and editorQ.canvas._xf_restore_region is None
                   and editorQ.canvas._xf_restore_pending
                   and editorQ._content_restored,
                   f"size={gotQ.width()}x{gotQ.height()} "
                   f"restored={editorQ._content_restored} "
                   f"pending={editorQ.canvas._xf_restore_pending}")
                # ⚠️ 2026-10-10「切换卡顿」：upright 反变换**延迟**到第一次
                #    建预览才算——进工具后浮层还没像素（restore_region None），
                #    但框/矩阵已经挂好；第一次建预览后像素必须到位。
                editorQ.canvas._ensure_transform_preview()
                ok("内容节点：首次预览补齐 upright 像素（延迟反变换到位）",
                   editorQ.canvas._xf_restore_region is not None
                   and not editorQ.canvas._xf_restore_pending
                   and editorQ.canvas._float_item is not None, "")
                quadQ = editorQ.canvas._transform_quad()
                wantQ = {
                    "tl": seedQ.map(rect0.topLeft()),
                    "tr": seedQ.map(rect0.topRight()),
                    "br": seedQ.map(rect0.bottomRight()),
                    "bl": seedQ.map(rect0.bottomLeft()),
                }
                ok("内容节点：PB1 作画布、PA1 恢复为可操作四边形（框在内容节点上）",
                   all((quadQ[k] - wantQ[k]).manhattanLength() < 2.5
                       for k in wantQ),
                   f"tl={quadQ['tl']} want_tl={wantQ['tl']}")
                _xfq = editorQ.canvas._xf
                ok("内容节点：矩阵挂回画布系种子 V（未触摸、零烘焙）",
                   _xfq == seedQ and not editorQ.canvas._xf_touched,
                   f"touched={editorQ.canvas._xf_touched}")
                # 恢复态继续转 45° ⇒ 总量 90°，烘焙＝从 upright 单次重采样
                editorQ.canvas.transform_rotate(45)
                editorQ._commit_transform(force=True)
                doneQ = canvas_img(editorQ.canvas)
                ok("内容节点：恢复态再转 45° ⇒ 总量 90°（120×200，单次代次）",
                   abs(doneQ.width() - 120) <= 1
                   and abs(doneQ.height() - 200) <= 1,
                   f"size={doneQ.width()}x{doneQ.height()}")
                _st = editorQ.content_state()
                sync_content_quad(str(_qpath), editorQ)
                _rq2 = read_quad(_qpath)
                ok("内容节点：烘焙后 V=总量矩阵并已写回 sidecar",
                   _st is not None and _st[0] == rect0 and _rq2 is not None
                   and _rq2[1] == _st[1],
                   "state=" + ("None" if _st is None else "ok"))
            finally:
                editorQ.deleteLater()

            editorR = ImageEditorDialog(None, look, save_back=True)
            try:
                editorR.source_path = str(_qpath)
                editorR.canvas.set_tool("transform")   # 恢复（PB1 画布＋种子矩阵）
                # 什么都没拖就切走：真实路径先 _commit_transform（无待定 ⇒
                # 退回文件原样），画布不许把 upright 当结果
                editorR._commit_transform()
                editorR.canvas.set_tool("erase")
                gotR = canvas_img(editorR.canvas)
                ok("内容节点：未拖动退出恢复会话 ⇒ 画布回文件原样",
                   (gotR.width(), gotR.height())
                   == (look.width(), look.height()),
                   f"size={gotR.width()}x{gotR.height()} "
                   f"expect={look.width()}x{look.height()}")
            finally:
                editorR.deleteLater()

            # ---- 延迟恢复 + 拖动守卫（2026-10-10「切换卡顿」） ----
            # 等待恢复像素的那次等待里有模态进度框（processEvents），用户的
            # 左键可能已在等待中松开——那个 release 被进度框吃掉，画布永远
            # 等不到；不守卫的话"拖动"一直挂着，鼠标一动内容就跟着跑。
            # 离屏环境没有真实按键 ⇒ mouseButtons() 恒空 ⇒ 恰好走进守卫。
            editorD = ImageEditorDialog(None, look, save_back=True)
            try:
                editorD.source_path = str(_qpath)
                editorD.canvas.set_tool("transform")
                ok("内容节点：延迟武装（进工具零反变换、框已就位）",
                   editorD.canvas._xf_restore_pending
                   and editorD.canvas._xf_restore_region is None
                   and editorD.canvas._xf_rect is not None, "")
                modeD = editorD.canvas._begin_transform_drag(
                    "inside", QPointF(100, 60), Qt.KeyboardModifier.NoModifier)
                ok("内容节点：等待像素期间左键已松 ⇒ 取消本次拖拽（防挂死）",
                   modeD is None
                   and editorD.canvas._xf_restore_region is not None
                   and not editorD.canvas._xf_restore_pending, "")
            finally:
                editorD.deleteLater()

            # 旋转：绕轴心（轴心不动）；切走工具自动烘焙
            canvas4.set_tool("transform")
            undo_before = len(dialog4._undo)
            canvas4.transform_rotate(90)
            pivot = canvas4.image_rect().center()
            ok("变换：绕轴心旋转 90°（轴心视觉位置不动）",
               (canvas4._xf.map(pivot) - pivot).manhattanLength() < 1e-6
               and canvas4.transform_pending() is not None, "")
            dialog4._set_tool("erase")
            ok("变换：切走工具自动烘焙（压撤销点）",
               len(dialog4._undo) == undo_before + 1
               and canvas4.transform_pending() is None,
               f"undo={len(dialog4._undo)} before={undo_before}")
            # grow：200×120 全选旋转 90°，内容真占了 120×200 那一整块 ⇒
            # 画布按**内容外框**收成 120×200（不是"原图 ∪ 内容"=200×200）。
            # 老图不要了：旋转后原位早被填白，没理由留着 200×200 的空白。
            _rotated = canvas_img(canvas4)
            ok("变换：非正方图旋转 90° ⇒ 画布按内容外框收成 120×200",
               (_rotated.width(), _rotated.height()) == (120, 200),
               f"size={_rotated.width()}x{_rotated.height()}")

            # 切变：右缘下斜、左缘锚定（尺寸随轮转后的图走，不写死 200×120）
            # 语义见「变换数学：绕锚点切变」——绕 ``rect.top()`` 做 y 随 x 斜切：
            # ``y' = y + k·x``。拖右边整条，左缘 (x=0) 不动；右缘下移 k·w。
            canvas4.set_tool("transform")
            w = canvas4.image_rect().width()
            h = canvas4.image_rect().height()
            canvas4.transform_shear("r", 0.5)
            xf = canvas4._xf
            ok("变换：拖边切变（右缘下移 k·w、左缘锚定）",
               (xf.map(QPointF(w, h / 2)) - QPointF(w, h / 2 + 0.5 * w))
               .manhattanLength() < 1e-6
               and (xf.map(QPointF(0, h / 2)) - QPointF(0, h / 2))
               .manhattanLength() < 1e-6,
               f"right={xf.map(QPointF(w, h / 2))} "
               f"left={xf.map(QPointF(0, h / 2))}")

            # 缩放：从轴心（轴心不动、内容向轴心收缩）
            canvas4.set_tool("transform")
            canvas4.set_transform_about_pivot(True)
            canvas4.transform_scale(0.5, 0.5)
            pivot = canvas4.image_rect().center()
            ok("变换：从轴心缩放 50%（轴心不动）",
               (canvas4._xf.map(QPointF(0, 0)) - pivot / 2)
               .manhattanLength() < 1e-6
               and (canvas4._xf.map(pivot) - pivot).manhattanLength() < 1e-6,
               f"tl={canvas4._xf.map(QPointF(0, 0))} pivot={pivot}")
            canvas4.set_transform_about_pivot(False)
            canvas4.reset_transform()
            ok("变换：重置清掉待应用变换、选区回到整幅",
               canvas4.transform_pending() is None
               and canvas4.selection() == canvas4.image_rect(), "")

            # 命中测试：角点**中心** = 透视小菱形、方框描边那圈 = 角缩放、框外 = 旋转。
            # ⚠️ 2026-10-09 起菱形与角方框**同心**（用户口径「四个边角的菱形要在
            #    方块正中心」），所以"角点归谁"改由**半径**分：≤ PERSP_HIT(8) 是
            #    透视，往外到 CORNER_HIT(13) 的方形环带仍是缩放。
            _pts = canvas4._transform_handle_points()
            ok("变换：透视小菱形与角方框同心（不再向框内偏置）",
               _pts["p_tl"] == _pts["tl"] and _pts["p_br"] == _pts["br"]
               and _pts["p_tr"] == _pts["tr"] and _pts["p_bl"] == _pts["bl"],
               f"p_tl={_pts['p_tl']} tl={_pts['tl']}")
            tl_view = vpos(_pts["tl"])
            # 沿 tl→tr 走 10 视图像素：出了透视半径(8)、仍在角方框方形判定(13)内
            _dir = vpos(_pts["tr"]) - tl_view
            _len = math.hypot(_dir.x(), _dir.y())
            edge_view = tl_view + _dir / _len * 10.0
            far_view = vpos(QPointF(-60, -60))
            ok("变换：命中测试（角心=透视、方框边=缩放、远处=框外旋转）",
               canvas4._hit_transform(tl_view) == "p_tl"
               and canvas4._hit_transform(edge_view) == "tl"
               and canvas4._hit_transform(far_view) == "outside",
               f"center={canvas4._hit_transform(tl_view)} "
               f"edge={canvas4._hit_transform(edge_view)} "
               f"far={canvas4._hit_transform(far_view)}")

            # 手柄**尺寸**（用户 2026-10-09：「菱形大一些，四边中间的拉伸方块
            # 也大一些」）：四类节点里的菱形现在**一样大**，边中方框也长到同尺寸。
            # ⚠️ 读的是**画出来的多边形/矩形**（场景单位）再乘回倍率 ⇒ 断言的是
            #    视图像素，不是常量本身，改常量漏改绘制也照样红。
            canvas4._sync_overlay()
            _zoom = max(canvas4._zoom, 1e-6)
            _persp_px = (canvas4._persp["p_tl"].polygon().boundingRect().width()
                         * _zoom)
            _shear_px = (canvas4._diamonds["s_t"].polygon().boundingRect().width()
                         * _zoom)
            _side_px = canvas4._handles["t"].rect().width() * _zoom
            _corner_px = canvas4._handles["tl"].rect().width() * _zoom
            ok("变换：菱形放大到 16、边中方框也 16、角方框 28（视图像素）",
               abs(_persp_px - 16.0) < 0.6 and abs(_shear_px - 16.0) < 0.6
               and abs(_side_px - 16.0) < 0.6 and abs(_corner_px - 28.0) < 0.6,
               f"透视={_persp_px:.1f} 切变={_shear_px:.1f} "
               f"边中={_side_px:.1f} 角={_corner_px:.1f}")

            # 命中半径必须**正好**是菱形的视觉半径：小了 ⇒ 画出来的菱形点不着，
            # 大了 ⇒ 抢掉角方框的缩放。同时仍要小于角方框的方形判定。
            ok("变换：透视命中半径 = 菱形视觉半径，且仍小于角方框判定",
               abs(PERSP_HIT_VIEW_PX - PERSP_VIEW_PX / 2.0) < 1e-9
               and PERSP_HIT_VIEW_PX < CORNER_HIT_VIEW_PX,
               f"hit={PERSP_HIT_VIEW_PX} 视觉半径={PERSP_VIEW_PX / 2.0} "
               f"角判定={CORNER_HIT_VIEW_PX}")

            # 节点**底色**（用户 2026-10-09：「操作节点未选中，不要有背景色——
            # 拉伸方块不要用绿色，而是中空的」）：默认一律中空，**只有"当前
            # 节点"实心**。方框与菱形共用一套配色（形状才是语义）。
            canvas4._set_handle_focus("tl")
            ok("变换：未选中的节点中空、当前节点实心（不再是清一色绿块）",
               canvas4._handles["tl"].brush().style()
               == Qt.BrushStyle.SolidPattern
               and canvas4._handles["tr"].brush().style()
               == Qt.BrushStyle.NoBrush
               and canvas4._handles["t"].brush().style()
               == Qt.BrushStyle.NoBrush
               and canvas4._persp["p_tl"].brush().style()
               == Qt.BrushStyle.SolidPattern
               and canvas4._persp["p_tr"].brush().style()
               == Qt.BrushStyle.NoBrush,
               f"tl={canvas4._handles['tl'].brush().style()} "
               f"tr={canvas4._handles['tr'].brush().style()} "
               f"p_tl={canvas4._persp['p_tl'].brush().style()}")
            canvas4._set_handle_focus(None)
            ok("变换：焦点清掉后所有节点都回到中空",
               all(item.brush().style() == Qt.BrushStyle.NoBrush
                   for item in (*canvas4._handles.values(),
                                *canvas4._diamonds.values(),
                                *canvas4._persp.values())),
               f"{[item.brush().style() for item in canvas4._handles.values()]}")

            # 裁剪/收边下是**同一批方框**，反馈改由悬停那个承担——不能变成
            # "全是空的、没有任何反馈"。
            canvas4._hover_handle = "bl"
            canvas4._apply_hover_highlight()
            ok("裁剪：悬停的方框实心、其余中空（与变换共用同一批图元）",
               canvas4._handles["bl"].brush().style()
               == Qt.BrushStyle.SolidPattern
               and canvas4._handles["br"].brush().style()
               == Qt.BrushStyle.NoBrush,
               f"bl={canvas4._handles['bl'].brush().style()} "
               f"br={canvas4._handles['br'].brush().style()}")
            canvas4._hover_handle = None
            canvas4._apply_hover_highlight()

            # ⚠️⚠️ 崩溃回归（用户 2026-10-09）：把透视角拖到**对角附近** ⇒
            # `quadToQuad` 给出"可逆但放大百万倍"的矩阵（外框 4.8e17）⇒ 预览
            # 重采样/烘焙画布全被撑爆（QImage(2.18e9) OverflowError）。现在这
            # 一步被判病态并**丢弃**：手柄停住、矩阵保持不变。
            canvas4.reset_transform()
            _paper = canvas4.image_rect()
            _before_xf = QTransform(canvas4._xf)
            canvas4.transform_perspective(
                "tl", _paper.bottomRight() - QPointF(1, 1))
            _sel = canvas4._xf_rect
            ok("变换：透视拖到对角附近被拒（矩阵不变形、不再算出天文数字外框）",
               QTransform(canvas4._xf) == _before_xf
               and _sel is not None
               and mapped_bounds(canvas4._xf, _sel) is not None,
               f"xf={canvas4._xf} bounds="
               f"{None if _sel is None else mapped_bounds(canvas4._xf, _sel)}")
            canvas4.transform_perspective("tl", _paper.topLeft() - QPointF(48, 36))
            ok("变换：正常透视仍然生效（只挡自交/塌陷的那一步）",
               QTransform(canvas4._xf) != _before_xf,
               f"xf={canvas4._xf}")

            # ⚠️⚠️ 回归（2026-10-09 用户报障「统一变换只旋转也有 bug」）：
            # ①"原本图片底还在"——旧版把整幅原图钉在 (0,0) 当底图，于是图转过
            #   来了、原来的图还在原地叠着看；②"旋转后图片不完整显示"——旧版把
            #   变换矩阵在"渲染浮层像素"和"浮层图元的 transform"里各套了一遍，
            #   内容被转两遍、还被固定大小的画布裁掉一半。
            # 这里把"预览 == 烘焙"钉成一条**像素级**断言：预览渲染成图，与
            # compose_transform（烘焙唯一实现）逐像素比。
            def scene_shot(canvas, rect: QRectF) -> QImage:
                """把场景按 ``rect``（图片坐标、1:1）渲染成一张图。

                ⚠️ 垫底用**白**：画布上"空"的那块（选区被搬走之后）现在是
                **透明**的（用户 2026-10-09：「图片旋转不再有白色的区域」），
                而烘焙产物那边仍是白底——这里比的是"内容落在纸上"，垫纸色再比
                才对得上。
                ⚠️ 构图参考线默认**五分**（2026-10-09）：它是纯 UI 叠加、烘焙
                里没有，拍进画面会把"预览 == 烘焙"的像素差顶过阈值——拍摄前
                先藏、拍完还原（四边形框/手柄一直都在画面里，阈值本来就有
                它们的余量，不动）。
                """
                guides = [item for item in canvas._guides if item.isVisible()]
                for item in guides:
                    item.setVisible(False)
                shot = QImage(max(1, int(rect.width())),
                              max(1, int(rect.height())),
                              QImage.Format.Format_ARGB32)
                shot.fill(QColor("#ffffff"))
                painter = QPainter(shot)
                painter.setRenderHint(
                    QPainter.RenderHint.SmoothPixmapTransform, True)
                canvas._scene.render(painter, QRectF(shot.rect()), rect)
                painter.end()
                for item in guides:
                    item.setVisible(True)
                return shot

            def check_parity(canvas, label: str) -> None:
                pending = canvas.transform_pending()
                assert pending is not None  # 用例里必已发生一次变换
                sel, xf, region = pending
                if getattr(canvas, "_xf_direction", "forward") == "backward":
                    inverse, ok_inv = xf.inverted()
                    if ok_inv:
                        xf = inverse
                clipping = getattr(canvas, "_xf_clipping", "adjust")
                grow = clipping != "clip"
                bake = compose_transform(
                    canvas_img(canvas), sel, xf, region, grow=grow,
                    interpolation="linear")
                origin = (0.0, 0.0)
                if grow:
                    bake, origin = bake
                if clipping == "aspect":
                    crop = center_crop_aspect(
                        bake, canvas_img(canvas).width(),
                        canvas_img(canvas).height())
                    origin = (origin[0] + (bake.width() - crop.width()) // 2,
                              origin[1] + (bake.height() - crop.height()) // 2)
                    bake = crop
                shot = scene_shot(canvas, QRectF(
                    origin[0], origin[1], bake.width(), bake.height()))
                value = plane_diff(shot, bake)
                ok(f"变换：{label}的预览 == 烘焙（逐像素平均通道差 < 6）",
                   value < 6.0, f"diff={value:.2f} "
                   f"bake={bake.width()}x{bake.height()}@{origin}")

            canvas4.set_tool("transform")
            undo_live = len(dialog4._undo)
            canvas4.transform_rotate(30)
            frame_before = canvas4._float_item.pixmap().cacheKey()
            pose_before = QTransform(canvas4._float_item.transform())
            canvas4.transform_rotate(15)
            ok("变换：只旋转就实时出画面（浮层像素与摆位都跟着变、像素没落地）",
               canvas4._float_item.pixmap().cacheKey() != frame_before
               and canvas4._float_item.transform() != pose_before
               and canvas_img(canvas4) is canvas4._image
               and len(dialog4._undo) == undo_live,
               f"key={canvas4._float_item.pixmap().cacheKey()} "
               f"before={frame_before} undo={len(dialog4._undo)} "
               f"expect={undo_live}")
            placement = canvas4._float_item.transform()
            ok("变换：浮层图元只做摆位（不带旋转 ⇒ 内容不会被转两次）",
               abs(placement.m12()) < 1e-9 and abs(placement.m21()) < 1e-9,
               f"transform={placement}")
            quad = canvas4._transform_quad()
            xs = [point.x() for point in quad.values()]
            ys = [point.y() for point in quad.values()]
            expect = QRectF(min(xs), min(ys),
                            max(xs) - min(xs), max(ys) - min(ys))
            got = canvas4._float_item.sceneBoundingRect()
            # ⚠️ 判据是"**盖住**内容外框"而不是"尺寸相等"：``warp_placement``
            #    取外框时向下取整/向上取整各留半像素，正好比精确外框大一点。
            ok("变换：浮层画布覆盖变换后内容的完整外框（不会裁掉一块）",
               got.contains(expect)
               and abs(got.width() - expect.width()) <= 3.0
               and abs(got.height() - expect.height()) <= 3.0,
               f"float={got} expect={expect}")
            # ⚠️⚠️ 用户第二轮报障（2026-10-09）：「白底和当前图片位置总是变化
            #   漂移……白底不应该扩大，应该是图片初始位置和大小」。旧版底图跟着
            #   旋转外框每帧重算：整幅转 30° 就涨到 920×992、原点跑到 (-160,-96)，
            #   再叠上 setSceneRect 一起变 ⇒ 看着就是"白底和图片一直在漂"。
            #   现在钉死：**恒定 = 原图矩形**。
            paper = QRectF(canvas4.image_rect())
            ok("变换：底图（纸）恒定 = 原图矩形，不随旋转长大（不再漂移）",
               canvas4._paint_image is not canvas4._image
               and canvas4._base_current_rect() == paper
               and canvas4._base_target_rect() == paper
               and canvas4._xf_base_origin == QPointF(0.0, 0.0),
               f"base={canvas4._base_current_rect()} "
               f"target={canvas4._base_target_rect()} "
               f"origin={canvas4._xf_base_origin} expect={paper}")
            # 「图片旋转不再有白色的区域」：整幅选区时底图整块**透明**
            #   （1×1 空图被缩放矩阵拉成原图矩形），露出来的画布条纹格才说得通。
            plane = canvas4._paint_image
            ok("变换：底图不再有白色区域（整幅选区时整块透明）",
               plane is not None and plane.width() == 1
               and plane.height() == 1 and plane.pixelColor(0, 0).alpha() == 0,
               f"paint={None if plane is None else (plane.width(), plane.height(), plane.pixelColor(0, 0).alpha())}")
            # 两个虚线框合成一个：固定在原位的纸边框改成**细实线**，
            #   虚线只留给跟着内容转的 _quad（用户截图里指出"两个框的虚线、
            #   颜色还不一样"）。
            ok("变换：只剩一个虚线框（原位那条已改成细实线）",
               canvas4._border is not None
               and canvas4._border.pen().style() != Qt.PenStyle.DashLine
               and canvas4._quad.pen().style() == Qt.PenStyle.DashLine,
               f"border={canvas4._border.pen().style() if canvas4._border else None} "
               f"quad={canvas4._quad.pen().style()}")
            check_parity(canvas4, "整幅旋转")
            # 校正（向后）走同一条路：反向矩阵同样要"预览 == 烘焙"
            canvas4.set_transform_options(direction="backward")
            check_parity(canvas4, "整幅校正（向后）")
            canvas4.set_transform_options(direction="forward")
            # 裁剪档：内容越出画布的部分要按画布边界切掉（与烘焙一致）
            canvas4.set_transform_options(clipping="clip")
            check_parity(canvas4, "裁剪到原画布")
            canvas4.set_transform_options(clipping="adjust")

            # ⚠️⚠️ 拖动中必须**实时**（2026-10-09 用户报障「只旋转不能实时渲染」）：
            # 精确档一帧要逐像素重采样整块选区（实测 12 MP `linear` 158 ms、
            # `nohalo` 442 ms），拖动根本跟不上。拖动中改成"像素不重采样、
            # 变换交给图元"（Qt 光栅器，实测 0.6–2.2 ms/帧），松手那一帧再回
            # 精确档——"预览 == 烘焙"的判据一点没松。这里把两条都钉死。
            canvas4.reset_transform()
            canvas4.set_tool("transform")
            canvas4.transform_rotate(25)
            resample_calls = []
            original_plane = canvas4._render_float_plane

            def counting_plane():
                resample_calls.append(1)
                return original_plane()

            canvas4._render_float_plane = counting_plane
            try:
                canvas4._xf_dragging = True
                for _ in range(5):
                    canvas4.transform_rotate(1.0)
                fast_pose = QTransform(canvas4._float_item.transform())
                ok("变换：拖动中不逐像素重采样（每帧只改图元 ⇒ 才是实时）",
                   not resample_calls, f"重采样次数={len(resample_calls)}")
                ok("变换：拖动中由浮层图元承担变换本身"
                   "（与松手后的纯摆位不同口径）",
                   fast_pose == canvas4._float_fast_xf()
                   and (abs(fast_pose.m12()) > 1e-6
                        or abs(fast_pose.m21()) > 1e-6),
                   f"transform={fast_pose}")
                ok("变换：拖动中的浮层画布 = 预览缩放的选区原图"
                   "（不是重采样后的外框）",
                   canvas4._float_item.pixmap().size()
                   == canvas4._float_fast_plane().size(),
                   f"pixmap={canvas4._float_item.pixmap().size()} "
                   f"plane={canvas4._float_fast_plane().size()}")

                # 快档 vs 精确档：**同一处内容**（只差插值），取景框固定成
                # "图片 ∪ 变换后选区外框"，免得两边的 sceneRect 取整差把判据带偏
                quad_fast = canvas4._transform_quad()
                xs_fast = [point.x() for point in quad_fast.values()]
                ys_fast = [point.y() for point in quad_fast.values()]
                frame = QRectF(canvas4.image_rect()).united(
                    QRectF(min(xs_fast), min(ys_fast),
                           max(xs_fast) - min(xs_fast),
                           max(ys_fast) - min(ys_fast))
                ).adjusted(-40, -40, 40, 40)
                fast_shot = scene_shot(canvas4, frame)
                canvas4.finish_transform_drag()
                exact_shot = scene_shot(canvas4, frame)
                settled_pose = QTransform(canvas4._float_item.transform())
            finally:
                del canvas4._render_float_plane
            fast_vs_exact = plane_diff(fast_shot, exact_shot)
            ok("变换：拖动中的快预览与松手后的精确预览逐像素一致（只差插值）",
               fast_vs_exact < 6.0, f"diff={fast_vs_exact:.2f}")
            ok("变换：松手立刻回到精确档（重新逐像素重采样 + 图元回到纯摆位）",
               resample_calls == [1]
               and abs(settled_pose.m12()) < 1e-9
               and abs(settled_pose.m21()) < 1e-9,
               f"重采样={len(resample_calls)} transform={settled_pose}")

            # ⚠️ 拖动中的裁剪掩膜方向（踩过的坑）：``setClipPath`` 是把笔限制在
            #    路径**之内**，配 ``CompositionMode_Clear`` 必须传**补集**——
            #    传原集会清反（该留的透明、该清的留着，画面像内容整块消失）。
            canvas4.set_transform_options(clipping="clip")
            canvas4._xf_dragging = True
            canvas4._sync_float()
            mask_plane = canvas4._float_fast_plane()
            mask_mid = mask_plane.pixelColor(mask_plane.width() // 2,
                                             mask_plane.height() // 2).alpha()
            # 全幅选区 + 旋转 ⇒ 区域局部坐标里"图片矩形"是一个被转过的平行
            # 四边形，四角必然落在画布外 ⇒ 必须被清成透明
            mask_corner = mask_plane.pixelColor(1, 1).alpha()
            ok("变换：拖动中的裁剪掩膜方向正确（中间留内容、画布外清透明）",
               mask_mid > 200 and mask_corner == 0,
               f"mid_alpha={mask_mid} corner_alpha={mask_corner}")
            canvas4._xf_dragging = False
            canvas4._xf_preview_keyframe = None
            canvas4._sync_float()
            canvas4.set_transform_options(clipping="adjust")
            canvas4.reset_transform()
        finally:
            dialog4.deleteLater()

        # ⚠️⚠️ 回归（2026-10-09 第三轮用户报障）：「图片边框那些操作框也应该
        #   跟着图片移动旋转，现在是分离了」「格子区域块跟图片相互远离」
        #   「画布画面是不变的」。
        #   根因是 ``QTransform`` 的复合顺序：``A * B`` 是**先 A 后 B**（行向量
        #   约定），而 ``S(k) ∘ placed ∘ S(1/k)`` 那种数学记号是**先右后左**。
        #   旧版按记号直译成 ``S(k) * placed * S(1/k)`` ⇒ 矩阵成了
        #   ``placed(k·u)/k``，**平移量被多除一个 k**，内容整体偏 ``t·(1/k−1)``
        #   （k=0.6 时 100px 的位移能偏出 66px）。
        #   ⚠️ 600×800 只有 0.48 MP，`_xf_preview_scale` 恒为 1 ⇒ 这个错**完全
        #   测不出来**，旧自测全绿。所以这条用例必须用**大于预览预算**的图。
        img6 = QImage(1000, 1400, QImage.Format.Format_ARGB32)
        img6.fill(QColor("#f2ecdd"))
        dialog6 = ImageEditorDialog(None, img6)
        try:
            canvas6 = dialog6.canvas
            canvas6.set_tool("transform")
            dialog6.show()
            app.processEvents()
            app.processEvents()
            canvas6.fit()
            app.processEvents()
            # ⚠️ 锚点在**动手之前**取：用户说的是"画布画面是不变的"——从操作前
            #   到操作后整幅画面都不能动，而不只是"转两次之间别动"。
            anchor6 = canvas6.mapFromScene(QPointF(0, 0))
            scene6 = QRectF(canvas6.sceneRect())
            # ⚠️ 先**平移**再转：绕中心的旋转外框是对称的、并集中心几乎不动，
            #   旧实现那点漂移会被"看不出来"；平移之后并集一边倒，旧实现就会
            #   把整幅画面推走（实测同样是"转+移"，用户截图里就是这么偏的）。
            canvas6.transform_move(160, -110)
            canvas6.transform_rotate(20)
            region6 = canvas6._xf_region
            ok("变换（大图）：选区大于预览预算 ⇒ 真的走降采样档（k<1）",
               canvas6._xf_preview_scale < 0.9,
               f"k={canvas6._xf_preview_scale:.3f} 区域="
               + (f"{region6.width()}x{region6.height()}"
                  if region6 is not None else "未建预览"))
            placed6 = canvas6._placed_xf()
            ok("变换（大图）：拖动档把区域像素**原样**映到图片坐标"
               "（不再多除一个 k）",
               (canvas6._float_fast_xf().map(QPointF(0, 0))
                - placed6.map(QPointF(0, 0))).manhattanLength() < 1e-6,
               f"fast={canvas6._float_fast_xf().map(QPointF(0, 0))} "
               f"placed={placed6.map(QPointF(0, 0))}")
            quad6 = canvas6._transform_quad()
            xs6 = [point.x() for point in quad6.values()]
            ys6 = [point.y() for point in quad6.values()]
            expect6 = QRectF(min(xs6), min(ys6),
                             max(xs6) - min(xs6), max(ys6) - min(ys6))
            got6 = canvas6._float_item.sceneBoundingRect()
            ok("变换（大图）：浮层内容落在变换框上（框与内容不再分离）",
               got6.contains(expect6)
               and abs(got6.width() - expect6.width()) <= 8.0
               and abs(got6.height() - expect6.height()) <= 8.0,
               f"float={got6} expect={expect6}")
            pivot6 = canvas6._xf.map(canvas6._xf_pivot)
            center6 = QPointF((got6.left() + got6.right()) / 2,
                              (got6.top() + got6.bottom()) / 2)
            ok("变换（大图）：内容中心恒在轴心上（绕轴心变换，不跑位）",
               (center6 - pivot6).manhattanLength() < 6.0,
               f"center={center6} pivot={pivot6}")
            for _ in range(4):
                canvas6.transform_rotate(9)
            ok("变换（大图）：转多少圈画布画面都不动（视图锚点恒定）",
               canvas6.mapFromScene(QPointF(0, 0)) == anchor6,
               f"anchor={canvas6.mapFromScene(QPointF(0, 0))} vs {anchor6}")
            ok("变换（大图）：场景矩形恒定（不跟变换长大）",
               QRectF(canvas6.sceneRect()) == scene6,
               f"sceneRect={canvas6.sceneRect()} vs {scene6}")
            paper6 = QRectF(canvas6.image_rect())
            ok("变换（大图）：底图（纸）仍恒定 = 原图矩形（不跟变换长）",
               canvas6._base_target_rect() == paper6
               and canvas6._base_current_rect() == paper6,
               f"target={canvas6._base_target_rect()} "
               f"base={canvas6._base_current_rect()} expect={paper6}")
            canvas6.reset_transform()
        finally:
            dialog6.deleteLater()

        # ⚠️⚠️ 回归（2026-10-09 用户报障三项）：①「统一变换参考线不显眼，
        #   太细了看不清，默认 5 分构图」②「方向：校正，图片和操作框方向
        #   相反」③「水平翻转、垂直翻转卡顿，太慢」。
        img7 = make_image(300, 200)
        for x in range(200, 230):  # 黑块 x∈[200,230)×y∈[80,110)（翻转方向用）
            for y in range(80, 110):
                img7.setPixel(x, y, 0xFF000000)
        dialog7 = ImageEditorDialog(None, img7)
        try:
            canvas7 = dialog7.canvas
            canvas7.set_tool("transform")
            dialog7.show()
            app.processEvents()
            app.processEvents()

            # ---- ① 参考线：默认五分 + 2 设备像素虚线（cosmetic 不随缩放变细）
            visible7 = sum(1 for item in canvas7._guides if item.isVisible())
            ok("变换：参考线默认五分构图（8 根全显示）",
               canvas7._xf_guide == "fifths" and visible7 == 8,
               f"guide={canvas7._xf_guide} visible={visible7}")
            gpen = canvas7._guides[0].pen()
            ok("变换：参考线加粗为 2 设备像素虚线（cosmetic，缩放不变细）",
               gpen.isCosmetic() and gpen.widthF() >= 2.0
               and gpen.style() == Qt.PenStyle.DashLine,
               f"cosmetic={gpen.isCosmetic()} width={gpen.widthF()} "
               f"style={gpen.style()}")

            # ---- ② 校正（向后）：框与内容同向
            #   旧 bug：框画 ``_xf``、内容走 ``_preview_xf``（=逆），平移时
            #   内容往 −x 跑、框往 +x 跑。现在两者统一吃视觉矩阵。
            canvas7.set_transform_options(direction="backward")
            canvas7.reset_transform()
            canvas7.transform_move(40, 0)
            quad7 = canvas7._transform_quad()
            float7 = canvas7._float_item.sceneBoundingRect()
            ok("变换（校正）：平移后框与内容同向（都向 +x 40，不再相反）",
               abs(quad7["tl"].x() - 40.0) < 1e-6
               and abs(float7.left() - 40.0) <= 2.0,
               f"quad_tl={quad7['tl']} float_left={float7.left()}")
            # 旋转同理：校正模式下的视觉框必须与正向**同一操作**一致
            # （旧 bug：框用正向矩阵画 ⇒ 与浮层内容反向转）
            canvas7.set_transform_options(direction="forward")
            canvas7.reset_transform()
            canvas7.transform_rotate(90)
            quad_fwd = dict(canvas7._transform_quad())
            canvas7.set_transform_options(direction="backward")
            canvas7.reset_transform()
            canvas7.transform_rotate(90)
            quad_bwd = dict(canvas7._transform_quad())
            ok("变换（校正）：旋转后框的视觉位置与正向一致（跟随内容）",
               all((quad_fwd[k] - quad_bwd[k]).manhattanLength() < 1e-6
                   for k in quad_fwd),
               f"fwd_tl={quad_fwd['tl']} bwd_tl={quad_bwd['tl']}")

            # ---- ③ 翻转快路径：纯镜像不走逐像素重采样（12MP 曾 ~11 秒）
            #   ⚠️ 别用 _set_tool 离开变换——切工具会把挂起变换**烘焙**掉
            #   （这里要的是丢弃）；reset_transform 才是"丢弃不烘焙"。
            canvas7.set_transform_options(direction="forward")
            canvas7.reset_transform()
            before7 = canvas_img(canvas7).copy()
            undo7 = len(dialog7._undo)
            # 快路径判据：纯镜像**不该**触发整幅重采样（compose_transform），
            # 也不该建预览浮层——打桩计数，旧实现（全走烘焙通道）会红。
            import desktop.components.viewers.image_editor.dialog_commit \
                as commit_mod
            real_compose = commit_mod.compose_transform
            compose_calls: list[int] = []

            def _counting_compose(*args, **kwargs):
                compose_calls.append(1)
                return real_compose(*args, **kwargs)

            commit_mod.compose_transform = _counting_compose
            try:
                dialog7._flip_transform(True)
            finally:
                commit_mod.compose_transform = real_compose
            flipped7 = canvas_img(canvas7)
            ok("翻转：纯镜像走快路径（零整幅重采样、不留预览浮层）",
               not compose_calls and canvas7._float_item is None,
               f"compose={len(compose_calls)} float={canvas7._float_item}")
            ok("翻转：水平翻转 = 整幅镜像（黑块从 [200,230) 到 [70,100)，尺寸不变）",
               flipped7.size() == before7.size()
               and canvas7.transform_pending() is None
               and all(flipped7.pixelColor(x, 90).value() < 128
                       for x in (75, 85, 95))
               and all(flipped7.pixelColor(x, 90).value() > 230
                       for x in (205, 215, 225)),
               f"size={flipped7.width()}x{flipped7.height()} "
               f"pending={canvas7.transform_pending()}")
            ok("翻转：一步一个撤销点、名字记「翻转」",
               len(dialog7._undo) == undo7 + 1
               and dialog7.history_list.item(
                   dialog7.history_list.count() - 1).text() == "翻转",
               f"undo={len(dialog7._undo)} before={undo7}")
            dialog7._flip_transform(True)      # 再翻一次 = 回到原图
            ok("翻转：翻两次精确复原（像素级一致，快路径产物与烘焙一致）",
               plane_diff(canvas_img(canvas7), before7) < 1.0, "")
        finally:
            dialog7.deleteLater()

        # ---- 调整范围 + 局部变换（小范围修褶皱的核心路径） ----
        img5 = make_image(200, 120)
        for x in range(150, 170):  # 区域内的"褶皱"块 x∈[150,170)×y∈[50,70)
            for y in range(50, 70):
                img5.setPixel(x, y, 0xFF000000)
        for x in range(185, 195):  # 区域**外**的标记块（烘焙后必须原样）
            for y in range(50, 70):
                img5.setPixel(x, y, 0xFF000000)
        dialog5 = ImageEditorDialog(None, img5)
        try:
            canvas5 = dialog5.canvas
            canvas5.set_tool("transform")
            dialog5.show()
            app.processEvents()
            app.processEvents()

            def vpos5(scene: QPointF) -> QPointF:
                return QPointF(canvas5.mapFromScene(scene))

            finished: list[int] = []
            canvas5.reshape_finished.connect(lambda: finished.append(1))
            ok("调整范围：默认关闭（拖手柄 = 缩放内容）",
               canvas5._xf_reshape is False, "")

            canvas5.set_transform_reshape(True)
            canvas5.mousePressEvent(mouse_event("press", vpos5(QPointF(201, 60))))
            ok("调整范围：右缘按下进入收边（而非缩放）",
               canvas5._mode is not None and canvas5._mode[0] == "handle"
               and canvas5._mode[1] == "r", f"mode={canvas5._mode}")
            canvas5.mouseMoveEvent(mouse_event(
                "move", vpos5(QPointF(179, 60))))
            canvas5.mouseReleaseEvent(mouse_event(
                "release", vpos5(QPointF(179, 60))))
            sel5 = canvas5.selection()
            ok("调整范围：区域收小到 x<180、自动退出该模式并回告弹窗",
               sel5 is not None and abs(sel5.right() - 180) < 1.5
               and canvas5._xf_reshape is False and finished == [1],
               f"sel={sel5} flag={canvas5._xf_reshape} finished={finished}")
            ok("调整范围：轴心跟随新区域中心（≈90,60）",
               (canvas5._xf_pivot - QPointF(90, 60)).manhattanLength() < 1.5,
               f"pivot={canvas5._xf_pivot}")

            undo_before = len(dialog5._undo)
            canvas5.transform_scale(0.5, 0.5)  # 区域内容向轴心收缩一半
            dialog5._commit_transform()
            baked5 = canvas_img(canvas5)
            # grow：区域 x∈[0,180) 收缩到 x∈[45,135)（×0.5 绕轴心 90）⇒ 画布
            # 按**内容外框**重裁，左上角落在原坐标 (45, 0)、尺寸 155×120。
            # 新画布坐标 = 原坐标 − 45。折叠块原 150→新 0.5·150=75 处；
            # 原 160 处（新 0.5·160=80）被收走 ⇒ 空白；区域外标记块
            # 原 185→新 140 处原样。
            ok("局部变换：非全幅变换后画布按内容外框重裁（155×120，左上角 45,0）",
               (baked5.width(), baked5.height()) == (155, 120),
               f"size={baked5.width()}x{baked5.height()}")
            ok("局部变换：区域内内容缩向轴心（黑块 150→75 处）",
               baked5.pixelColor(75, 60).value() < 128
               and baked5.pixelColor(105, 60).value() > 230,
               f"dark={baked5.pixelColor(75, 60).value()} "
               f"white={baked5.pixelColor(105, 60).value()}")
            ok("局部变换：区域外像素一动不动（标记块 185→140 处原样）",
               baked5.pixelColor(140, 60).value() < 128,
               f"outside={baked5.pixelColor(140, 60).value()}")
            ok("局部变换：一批一个撤销点",
               len(dialog5._undo) == undo_before + 1,
               f"undo={len(dialog5._undo)} before={undo_before}")

            # 回归（2026-10-08 用户报障）：刚进变换工具就抓轴心拖，
            # 预览还没建——以前这里直接进 xf_pivot，第一个 move 事件就
            # 撞 `assert _xf_rect`，拖动全程刷屏 AssertionError。
            dialog5._set_tool("transform")
            pivot_before = QPointF(canvas5._xf_pivot)
            pivot_view = vpos5(canvas5._xf.map(pivot_before))
            canvas5.mousePressEvent(mouse_event("press", pivot_view))
            ok("变换：第一个动作就是拖轴心也能进拖动（先建预览，不炸断言）",
               canvas5._mode is not None and canvas5._mode[0] == "xf_pivot"
               and canvas5._xf_rect is not None, f"mode={canvas5._mode}")
            moved_view = vpos5(canvas5._xf.map(pivot_before)
                               + QPointF(20, 10))
            canvas5.mouseMoveEvent(mouse_event("move", moved_view))
            canvas5.mouseReleaseEvent(mouse_event("release", moved_view))
            ok("变换：轴心拖动全程无异常、轴心跟到新位置、松手复位",
               canvas5._mode is None
               and (canvas5._xf_pivot - (pivot_before + QPointF(20, 10)))
               .manhattanLength() < 2.0,
               f"pivot={canvas5._xf_pivot} mode={canvas5._mode}")

            # 回归（2026-10-08 用户报障）：「调整范围」复选框的信号连接
            # 随选项页重建而泄漏——旧页销毁后下一次 reshape 完成就调到
            # 已销毁的 CheckBox 上抛 RuntimeError 刷屏。
            dialog5._set_tool("transform")
            app.processEvents()
            dialog5._set_tool("crop")
            app.processEvents()  # 旧选项页 deleteLater 在此真正销毁
            dialog5._set_tool("transform")
            app.processEvents()
            try:
                canvas5.reshape_finished.emit()
                reshape_ok = True
            except RuntimeError:
                reshape_ok = False
            ok("变换：选项页重建后 reshape 信号不再打到已销毁的复选框",
               reshape_ok, "")
        finally:
            dialog5.deleteLater()
    finally:
        dialog.deleteLater()

    # ---- 7/8. 预览弹窗接线 ----
    from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

    zoom = ImageZoomDialog(None)
    try:
        ok("预览弹窗：工具条上有「编辑」按钮",
           getattr(zoom, "edit_btn", None) is not None, "")
        # 期望 1360 宽（一行摆得下缩放/朝向/翻页/打印/下载/编辑），但落地尺寸
        # 会先被夹进屏幕可用区域——按同一个公式算期望值，别写死 1280。
        from desktop.components.viewers.image_zoom_dialog import ZOOM_DIALOG_SIZE
        from desktop.ui.window_size import (
            FRAME_ALLOWANCE, FIT_RATIO, available_area,
        )

        zoom_area = available_area(zoom)
        assert zoom_area is not None  # 离屏环境下可用区域总能取到
        zoom_w = min(ZOOM_DIALOG_SIZE.width(),
                     int((zoom_area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        ok("预览弹窗：宽度取满（理想 1360，超出屏幕时夹进可用区域）",
           zoom.width() == zoom_w and zoom.width() <= zoom_area.width(),
           f"width={zoom.width()} 期望={zoom_w} 可用区={zoom_area.width()}")
        ok("预览弹窗：无图时编辑按钮禁用", not zoom.edit_btn.isEnabled(), "")
        zoom.canvas.set_image(make_image(64, 48))
        zoom._sync_controls()
        ok("预览弹窗：有图时编辑按钮可用", zoom.edit_btn.isEnabled(), "")
        source = zoom.canvas.export_image()
        assert source is not None  # 刚 set 过图，导出必有
        editor = zoom._open_editor(source)
        ok("预览弹窗：_open_editor 拿到画布整图",
           editor is not None
           and editor.canvas.image is not None
           and editor.canvas.image.width() == source.width()
           and editor.canvas.image.height() == source.height(), "")
        assert editor is not None  # 上一条 ok 已断言编辑器打开成功
        ok("预览弹窗：编辑器以弹窗为父（生命周期跟随）",
           editor.parent() is zoom, "")
        editor.deleteLater()

        # 编辑结果写回：set_image 通道替换画布图（_edit_image 内同款调用）
        edited = make_image(30, 20)
        zoom.canvas.set_image(edited)
        _written_back = zoom.canvas.export_image()
        assert _written_back is not None  # 刚 set 过图，导出必有
        ok("预览弹窗：编辑结果写回后画布就是新图",
           _written_back.width() == 30, "")
        zoom._sync_controls()
    finally:
        zoom.deleteLater()
        zoom.shutdown_workers()
    app.processEvents()

    # ---- 崩溃守卫（2026-10-02）：后台线程的异常/取消/收尾 ----
    # 这几条守的都是用户报过的"程序崩溃 / 点了没反应"，且都**实测复现过**。
    from desktop.components.viewers.image_editor import (
        ImageEditorDialog as _Ed, _BakeWorker, run_with_progress)

    def _drain(w):
        from PySide6.QtWidgets import QApplication as _QA
        while not w.wait(20):
            _QA.processEvents()

    # 1. worker 里抛的异常必须被**捕获**（原来它逃出 QThread.run，
    #    result 停在 None、cancelled 是 False，被上层当成"用户取消"）
    def _boom(_params, _progress):
        raise MemoryError("模拟大图内存不足")

    w = _BakeWorker(_boom, {})
    w.start()
    _drain(w)
    ok("崩溃守卫：worker 捕获工作函数异常（不是让它逃出 QThread.run）",
       isinstance(w.error, MemoryError),
       f"→ error={type(w.error).__name__ if w.error else None}")
    ok("崩溃守卫：异常时线程正常结束（不留孤儿）", w.isFinished(), "")

    # 2. run_with_progress 必须**重抛**，让上层能区分"失败"与"用户取消"
    host = _Ed()
    try:
        run_with_progress(host, "t", "l", _boom, {})
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", False, "没有抛")
    except MemoryError:
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", True, "")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", False,
           f"抛了别的 {type(exc).__name__}")

    # 3. 正常完成仍要拿到结果（别被收尾的 cancel() 误标成"取消"）
    ok("崩溃守卫：正常完成返回结果（收尾 cancel 不污染语义）",
       run_with_progress(host, "t", "l",
                         lambda p, pr: (pr(1, 2), "结果图")[1], {}) == "结果图", "")

    # 4. progress 的取消信号：工作函数要能看见
    wc = _BakeWorker(lambda p, pr: None, {})
    a1 = wc.progress(1, 10)
    wc.cancelled = True
    a2 = wc.progress(2, 10)
    wc.cancelled = False
    ok("崩溃守卫：progress 取消信号（未取消 True / 取消 False）",
       a1 is True and a2 is False, f"→ {a1}, {a2}")

    # 5. closeEvent 存在且关窗不炸（缺它 ⇒ 线程在飞时析构 ⇒
    #    QThread: Destroyed while thread is still running ⇒ abort）
    ok("崩溃守卫：编辑器有 closeEvent（关窗时收尾在飞线程）",
       hasattr(_Ed, "closeEvent"), "")
    try:
        host.close()
        ok("崩溃守卫：关窗正常（不 abort）", True, "")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：关窗正常（不 abort）", False, repr(exc))

    # 6. 「完成」整体防重入（三个 busy 标志只挡同名方法，挡不住整体重入）
    ed2 = _Ed()
    calls = []
    for name in ("_commit_transform", "_commit_text_blocks"):
        # ⚠️ *a, **k：_commit_transform 现在带 force 关键字（「完成」收尾用），
        #    桩只管记账，别绑死签名。
        setattr(ed2, name,
                (lambda n: lambda *a, **k: calls.append(n))(name))
    ed2._finish()
    first = list(calls)
    ed2._finishing = True            # 模拟烘焙中 processEvents 派发第二次点击
    ed2._finish()
    ok("崩溃守卫：双击「完成」不重入（_finishing 挡住）",
       calls == first, f"→ 实际 {len(calls)} 次调用")
    ed2._finishing = False
    ed2.deleteLater()

    host.deleteLater()
    app.processEvents()
