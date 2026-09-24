# -*- coding: utf-8 -*-
"""area/border 几何的统一性自测。

背景：CLI（functions/text_region.py，numpy 渲染）与 GUI
（desktop/workers/preview_worker.py，QImage 渲染）各自实现过一遍 area/border
的画布尺寸与粘贴落点，两处都硬编码了同一个 `SYMMETRIC_GAP_MM = 10`。
两份实现漂移后产生过一个真实 bug：`area=3 + 双框 + border=None` 时，
规格要求「并集 ROI **写回原位置**」（docs/functions/cropremove.md:57），
CLI 做对了，GUI 却把内容搬到了画布左上角 (0,0)。

现在几何收敛到 `utils.box_geometry` 的布局层（build_output_layout /
build_symmetric_layout），两侧只负责「把布局画出来」。本模块守住两件事：

1. 布局层与规格逐组合一致（含上面那个曾出 bug 的组合）；
2. CLI 与 GUI 两个渲染后端消费同一布局，落点不再各自推导。
"""

from pathlib import Path

NAME = "box_geometry"
DEPENDS: list[str] = []
TITLE = "area/border 几何统一"

# 画布参考尺寸
W = H = 600
TWO = [(100, 100, 200, 200), (300, 100, 500, 300)]
ONE = [(100, 100, 200, 200)]


def _spec_reference(boxes_in, area_mode, border_padding, symmetric=False):
    """按规格独立推导 [(source, ox, oy)], (w, h)。

    这是**规格的直译**，不是任何一侧实现的复刻 —— 因此它当真值用。
    规格见 docs/functions/cropremove.md 的 area 表：
      area=1：每框单独输出，画布 = 框 + border；
      area=2：每框 ROI 写回原位置，border=None 时输出原尺寸整页；
      area=3：左右框并集为整体，单图，ROI 写回原位置。
    另有对称输出（symmetric=True）：实际框 + 空白镜像 + 10mm 间隔。
    """
    boxes = [tuple(b) for b in boxes_in]
    cx1, cy1, cx2, cy2 = (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )

    # 对称输出：本框 + 空白镜像 + 间隔（与框数无关，由调用方显式选择）
    if symmetric and border_padding is not None:
        x1, y1, x2, y2 = boxes[0]
        top, right, bottom, left = border_padding
        gap = round(10 * 300 / 25.4)  # SYMMETRIC_GAP_MM=10 @300dpi
        bw, bh = x2 - x1, y2 - y1
        return (
            [((x1, y1, x2, y2), left, top)],
            (left + bw * 2 + gap + right, top + bh + bottom),
        )

    # area=1：每框一张画布，画布 = 框 + border
    if area_mode == 1:
        t, r, b, l = border_padding or [0, 0, 0, 0]
        x1, y1, x2, y2 = boxes[0]
        return [((x1, y1, x2, y2), l, t)], ((x2 - x1) + l + r, (y2 - y1) + t + b)

    # border=None：整页画布，内容写回原位置
    if border_padding is None:
        if area_mode == 3:
            return [((cx1, cy1, cx2, cy2), cx1, cy1)], (W, H)
        return [(b, b[0], b[1]) for b in boxes], (W, H)

    # 普通单框：画布 = 框 + 四周 border
    if len(boxes) == 1:
        x1, y1, x2, y2 = boxes[0]
        t, r, b, l = border_padding
        return [((x1, y1, x2, y2), l, t)], ((x2 - x1) + l + r, (y2 - y1) + t + b)

    # area=2/3 + border：并集裁剪成一块，内容相对并集左上角偏移 border
    t, r, b, l = border_padding
    canvas = ((cx2 - cx1) + l + r, (cy2 - cy1) + t + b)
    if area_mode == 3:
        return [((cx1, cy1, cx2, cy2), l, t)], canvas
    return [((bx1, by1, bx2, by2), bx1 - cx1 + l, by1 - cy1 + t)
            for bx1, by1, bx2, by2 in boxes], canvas


def run(ctx) -> None:
    from tests.selftests._context import ok

    from utils.box_geometry import (
        SYMMETRIC_GAP_MM,
        build_output_layout,
        build_symmetric_layout,
        parse_border_mm,
    )

    # ---- 1. 常量与 border 解析 ----
    ok("SYMMETRIC_GAP_MM 定义在 utils 层", SYMMETRIC_GAP_MM == 10, str(SYMMETRIC_GAP_MM))
    # 10mm @300dpi ≈ 118px；border 是 CSS 风格的 1-4 个值
    ok("border 单值展开为四边", parse_border_mm(10) == [118] * 4, str(parse_border_mm(10)))
    ok("border 两值展开为 [上下, 左右]",
       parse_border_mm("5,10") == [59, 118, 59, 118], str(parse_border_mm("5,10")))
    ok("border 三值展开为 [上, 左右, 下]",
       parse_border_mm("5,10,15") == [59, 118, 177, 118], str(parse_border_mm("5,10,15")))
    ok("border 四值原样（上右下左）",
       parse_border_mm("5,6,7,8") == [59, 71, 83, 94], str(parse_border_mm("5,6,7,8")))
    ok("border=None → None", parse_border_mm(None) is None, str(parse_border_mm(None)))
    ok("border=0 → 全零", parse_border_mm(0) == [0, 0, 0, 0], str(parse_border_mm(0)))

    # ---- 2. 布局层与规格逐组合一致（核心回归）----
    # 元组末位 = 是否走对称输出（对称只由调用方显式选择，布局层不猜）
    cases = [
        (ONE, 1, None, False, "area1 单框 border=None"),
        (ONE, 1, [118] * 4, False, "area1 单框 border=10"),
        (ONE, 2, None, False, "area2 单框 border=None"),
        (ONE, 2, [118] * 4, True, "area2 单框 border=10（对称）"),
        (ONE, 3, None, False, "area3 单框 border=None"),
        (ONE, 3, [118] * 4, True, "area3 单框 border=10（对称）"),
        (ONE, 2, [118] * 4, False, "area2 单框 border=10（非对称）"),
        (ONE, 3, [118] * 4, False, "area3 单框 border=10（非对称）"),
        (TWO, 1, None, False, "area1 双框 border=None"),
        (TWO, 1, [118] * 4, False, "area1 双框 border=10"),
        (TWO, 2, None, False, "area2 双框 border=None"),
        (TWO, 2, [118] * 4, False, "area2 双框 border=10"),
        (TWO, 3, None, False, "area3 双框 border=None ← 曾出 bug"),
        (TWO, 3, [118] * 4, False, "area3 双框 border=10"),
        (TWO, 2, [59, 71, 83, 94], False, "area2 双框 非对称 border"),
        (TWO, 3, [59, 71, 83, 94], False, "area3 双框 非对称 border"),
    ]
    for boxes, area, border, sym, label in cases:
        if area == 1 and len(boxes) > 1:
            continue  # area=1 多框每框一张画布，本节的单画布断言不适用
        layout = build_output_layout(boxes, area, border, (W, H), symmetric=sym)
        if len(layout.canvases) != 1:
            ok(f"{label}：只产出一张画布", False, f"{len(layout.canvases)} 张")
            continue
        canvas = layout.canvases[0]
        ref_sources, ref_size = _spec_reference(boxes, area, border, sym)
        got = sorted((tuple(s), ox, oy) for s, ox, oy in canvas.sources)
        want = sorted((tuple(s), ox, oy) for s, ox, oy in ref_sources)
        same = got == want and tuple(canvas.size) == tuple(ref_size)
        ok(f"{label}：落点与画布符合规格", same,
           f"\n        规格 {want} size={ref_size}\n        实现 {got} size={canvas.size}")

    # ---- 3. 那个曾出 bug 的组合，单独钉死语义 ----
    layout = build_output_layout(TWO, 3, None, (W, H))
    canvas = layout.canvases[0]
    (src, ox, oy), = canvas.sources
    ok("area=3+双框+border=None：取并集",
       tuple(src) == (100, 100, 500, 300), str(src))
    ok("area=3+双框+border=None：并集写回原位置（不是左上角）",
       (ox, oy) == (100, 100), f"实际 ({ox},{oy})，bug 版本是 (0,0)")
    ok("area=3+双框+border=None：整页画布", canvas.size == (W, H), str(canvas.size))
    ok("area=3+双框+border=None：标记为 full_page", layout.full_page is True)

    # ---- 4. 普通单框不得误用对称布局 ----
    # 回归：曾把「area=3 合并后的单框」也走对称分支，产出 220x938 这种尺寸
    layout = build_output_layout([(100, 100, 500, 300)], 3, [118] * 4, (W, H))
    canvas = layout.canvases[0]
    ok("合并后单框走普通布局而非对称",
       canvas.size == (400 + 118 * 2, 200 + 118 * 2), str(canvas.size))

    # ---- 5. 对称布局显式可调 ----
    sym = build_symmetric_layout(
        box=ONE[0], border_padding=[118] * 4, image_size=(W, H),
        is_left=True, dpi=300,
    )
    canvas = sym.canvases[0]
    # 宽 = left + 框宽*2 + gap + right；高 = top + 框高 + bottom
    gap = round(SYMMETRIC_GAP_MM * 300 / 25.4)
    ok("对称布局宽度含镜像与间隔",
       canvas.size[0] == 118 + 100 * 2 + gap + 118, str(canvas.size))
    ok("对称布局高度 = 框高 + 上下 border",
       canvas.size[1] == 118 + 100 + 118, str(canvas.size))
    ok("对称布局落点在 border 内", canvas.sources[0][1:] == (118, 118),
       str(canvas.sources[0]))

    # ---- 6. 两个渲染后端消费同一布局（结构性保证）----
    import inspect

    from desktop.workers import preview_worker
    from functions import text_region

    # ⚠️ 几何调用在 region_canvas_specs（纯几何），compose_region_output 只负责
    # 用位图把它画出来——两个函数合起来才是 GUI 后端的全部，缺一不可。
    gui_src = (inspect.getsource(preview_worker.compose_region_output)
               + inspect.getsource(preview_worker.region_canvas_specs))
    cli_src = inspect.getsource(text_region)
    ok("GUI 侧复用 build_output_layout",
       "build_output_layout" in gui_src, "GUI 仍在自行推导几何")
    ok("GUI 侧复用 build_symmetric_layout",
       "build_symmetric_layout" in gui_src, "GUI 缺少对称布局调用")
    ok("CLI 侧复用 build_output_layout",
       "build_output_layout" in cli_src, "CLI 仍在自行推导几何")
    ok("CLI 侧复用 build_symmetric_layout", "build_symmetric_layout" in cli_src)
    # 两侧都不得再自带那份魔数
    ok("GUI 侧不再硬编码 SYMMETRIC_GAP_MM",
       "SYMMETRIC_GAP_MM = " not in gui_src, "GUI 仍自带间隔常数")
    ok("CLI 侧不再硬编码 SYMMETRIC_GAP_MM",
       "SYMMETRIC_GAP_MM = " not in cli_src, "CLI 仍自带间隔常数")

    # ---- 7. 第三步提交：名称预计算 + 并行合成（2026-09-24 提速改造）----
    # 预计算输出名称必须走 region_canvas_specs（与合成同一份几何规则）；
    # 若有人绕开它手写张数规则，area=1 时预计算的 total 会与实际产出脱节。
    from desktop.stages import rembg_stage

    stage_src = inspect.getsource(rembg_stage)
    ok("提交阶段用线程池并行合成（PNG 编码占 85%，实测 4 线程 3.1×）",
       "ThreadPoolExecutor" in stage_src, "提交合成退回了串行")
    ok("输出名称预计算走 region_canvas_specs（规则只有一份）",
       "region_canvas_specs" in stage_src, "提交阶段自行推导几何张数")
    ok("并行 worker 数有上限（内存约束：每 worker ~200MB 位图）",
       rembg_stage.SUBMIT_WORKERS <= 4, str(rembg_stage.SUBMIT_WORKERS))
