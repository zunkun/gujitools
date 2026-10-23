# -*- coding: utf-8 -*-
"""border 几何的唯一性自测（2026-10-22 起没有 area）。

背景：CLI（functions/text_region.py，numpy 渲染）与 GUI
（desktop/workers/preview_worker.py，QImage 渲染）各自实现过一遍几何。
现在几何收敛到 `utils.box_geometry.build_output_layout`：
**每个检测框各自一张画布（框 + border）**，两侧只负责「把布局画出来」。

本模块守住两件事：
1. 布局层逐组合正确（单框/双框/无框/带 border/不带 border）；
2. CLI 与 GUI 两个渲染后端消费同一布局，落点不再各自推导。
"""

from pathlib import Path

NAME = "box_geometry"
DEPENDS: list[str] = []
TITLE = "border 几何统一（无 area）"

# 画布参考尺寸
W = H = 600
TWO = [(100, 100, 200, 200), (300, 100, 500, 300)]
ONE = [(100, 100, 200, 200)]


def run(ctx) -> None:
    from tests.selftests._context import ok

    from utils.box_geometry import build_output_layout, parse_border_mm

    # ---- 1. border 解析 ----
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

    # ---- 1b. 检测框的**槽位约定**只有一份实现（2026-10-02 收敛）----
    # 半幅恒 2 槽、整幅恒 1 槽是共享契约：下游 rembg / 布局靠槽数分辨形态。
    # 规则本体在 utils.box_geometry.page_box_slots，两个调用方（任务流程第二步
    # 的 page_boxes 事件、独立「检测文本框」模块页）都走它。
    from utils.box_geometry import page_box_slots, page_box_slots_from_event
    from functions.detect import PageBoxes

    ok("槽位：左右任一有值 → 2 槽（缺失侧 None）",
       page_box_slots((1, 2, 3, 4), None, None) == [(1, 2, 3, 4), None],
       str(page_box_slots((1, 2, 3, 4), None, None)))
    ok("槽位：只有整幅 → 1 槽",
       page_box_slots(None, None, (5, 6, 7, 8)) == [(5, 6, 7, 8)],
       str(page_box_slots(None, None, (5, 6, 7, 8))))
    ok("槽位：三类全空 → 空表", page_box_slots(None, None, None) == [])
    ok("槽位：半幅与整幅并存时按半幅（既有明文规则）",
       page_box_slots((1, 2, 3, 4), None, (5, 6, 7, 8)) == [(1, 2, 3, 4), None],
       str(page_box_slots((1, 2, 3, 4), None, (5, 6, 7, 8))))

    # PageBoxes.slots() 必须是**同一条规则**（委托），不是各写一遍
    ok("PageBoxes.slots() 与 page_box_slots 结论一致（同一条规则）",
       PageBoxes(left=(1, 2, 3, 4), right=(5, 6, 7, 8)).slots()
       == page_box_slots((1, 2, 3, 4), (5, 6, 7, 8), None)
       == [(1, 2, 3, 4), (5, 6, 7, 8)]
       and PageBoxes(full=(9, 9, 9, 9)).slots() == page_box_slots(None, None, (9, 9, 9, 9))
       and PageBoxes().slots() == [],
       f"{PageBoxes().slots()}")

    # 事件负载 → 槽位：这是任务流程与独立检测页共用的那条路
    cases = [
        ({"left": [1, 2, 3, 4], "right": [5, 6, 7, 8]}, [[1, 2, 3, 4], [5, 6, 7, 8]], "半幅双框"),
        ({"left": [1, 2, 3, 4], "right": None}, [[1, 2, 3, 4], None], "半幅单左"),
        ({"left": None, "right": [5, 6, 7, 8]}, [None, [5, 6, 7, 8]], "半幅单右"),
        ({"full": [0, 0, 600, 600]}, [[0, 0, 600, 600]], "整幅"),
        ({"left": None, "right": None, "full": None}, [], "无框"),
        ({}, [], "键全缺（旧存档/异常负载）"),
        ({"left": ["1", "2", "3", "4"]}, [[1, 2, 3, 4], None], "字符串坐标要转 int"),
    ]
    bad = [
        f"{name}: {page_box_slots_from_event(payload)}"
        for payload, want, name in cases if page_box_slots_from_event(payload) != want
    ]
    ok("事件负载 → 槽位逐例正确（含坐标转 int 与缺键）", not bad, "；".join(bad))

    # ⚠️ utils 层不许 import functions（含**函数内**延迟导入）：规则要两个调用方
    #    都能便宜地导入，靠的是它只依赖 dataclass/typing，而不是把 functions
    #    拖进来——一旦拖进来，GUI 主进程 import 本模块就会连带加载 cv2。
    #    这里必须走 AST：本文件自己的说明文字里就有「不 import functions」这句。
    from tests.selftests._context import imported_modules

    geo_src = (
        Path(__file__).resolve().parents[2] / "utils" / "box_geometry.py"
    ).read_text(encoding="utf-8")
    pulled = sorted(
        name for name in imported_modules(geo_src)
        if name.split(".")[0] in ("functions", "desktop")
    )
    ok("utils/box_geometry 不 import functions/desktop（否则主进程被拖进重依赖）",
       not pulled, str(pulled))

    # ---- 2. 布局层：每个框各自一张画布 ----
    cases = [
        (ONE, None, "单框 border=None（紧裁）"),
        (ONE, [118] * 4, "单框 border=10"),
        (ONE, [0, 0, 0, 0], "单框 border=0"),
        (TWO, None, "双框 border=None（各裁各的）"),
        (TWO, [118] * 4, "双框 border=10"),
        (TWO, [0, 0, 0, 0], "双框 border=0"),
        (TWO, [59, 71, 83, 94], "双框 非对称 border"),
    ]
    for boxes, border, label in cases:
        layout = build_output_layout(boxes, border, (W, H))
        pad = border or [0, 0, 0, 0]
        t, r, b, l = pad
        want = [
            (
                (bx2 - bx1 + l + r, by2 - by1 + t + b),
                ((bx1, by1, bx2, by2), l, t),
            )
            for bx1, by1, bx2, by2 in boxes
        ]
        got = [((c.size), (tuple(c.sources[0][0]), c.sources[0][1], c.sources[0][2]))
               for c in layout.canvases]
        ok(f"{label}：每框一张画布，落点在 border 内", got == want,
           f"\n        规格 {want}\n        实现 {got}")

    # 无框 → 整页透传
    layout = build_output_layout([], "0", (W, H))
    ok("无框 → 整页画布（full_page）",
       layout.full_page is True and layout.canvases[0].size == (W, H),
       str(layout))

    # 侧别后缀：与 boxes 对齐，只影响文件名
    layout = build_output_layout(TWO, [0, 0, 0, 0], (W, H), sides=["left", "right"])
    ok("sides 对齐给后缀：-l / -r",
       [c.suffix for c in layout.canvases] == ["-l", "-r"],
       str([c.suffix for c in layout.canvases]))

    # ---- 3. 两个渲染后端消费同一布局（结构性保证）----
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
    ok("CLI 侧复用 build_output_layout",
       "build_output_layout" in cli_src, "CLI 仍在自行推导几何")
    ok("两侧都不再有 area/对称布局",
       "build_symmetric_layout" not in gui_src
       and "build_symmetric_layout" not in cli_src
       and "area_mode" not in gui_src and "area_mode" not in cli_src)

    # ---- 7. 提交阶段：名称预计算 + 并行合成 ----
    # ⚠️ 2026-10-22：按 area 裁图的提交从**第三步**搬到了**第二步**
    #    （去底色的提交只把白底转透明，不碰几何）。所以这组源码守卫跟着搬——
    #    "名称预计算必须走 region_canvas_specs（规则只有一份）"这条不能丢。
    from desktop.stages import detect_stage, rembg_stage

    stage_src = inspect.getsource(detect_stage)
    ok("检测提交阶段用线程池并行合成（PNG 编码是瓶颈）",
       "ThreadPoolExecutor" in stage_src, "提交合成退回了串行")
    # 名称预计算必须走 ``plan_submit_job``（它内部用 region_canvas_specs 算画布
    # 张数），不许在阶段里自己数张数——那会和合成结果脱节。
    ok("输出名称预计算走 plan_submit_job（内部即 region_canvas_specs）",
       "plan_submit_job" in stage_src, "提交阶段自行推导几何张数")
    rembg_src = inspect.getsource(rembg_stage)
    ok("去底色提交不再做几何合成（整图去底色）",
       "region_canvas_specs" not in rembg_src
       and "compose_region_output" not in rembg_src,
       "第三步提交又在裁图了")
    ok("并行 worker 数有上限（内存约束：每 worker ~200MB 位图；2026-09-27 起上限与函数层一致为 8）",
       detect_stage.SUBMIT_WORKERS <= 8, str(detect_stage.SUBMIT_WORKERS))

    # ---- 8. 人工干预的槽位运算（用户 2026-10-03：模块页也要手绘 + 标类型）----
    # 独立「检测文本框」模块页新增了手绘/改类型/删框，规则必须与任务流程
    # 第二步**同一份**——所以两边都调这里，测试也就钉在这里。
    from utils.box_draw import slot_names_colors
    from utils.box_geometry import (
        drop_box,
        is_full_content,
        present_boxes,
        set_box_full,
        set_box_half,
    )

    SIZE = (1000, 800)
    L = [40, 100, 460, 700]
    R = [540, 100, 960, 700]
    F = [20, 40, 980, 760]

    ok("present_boxes 滤掉空槽（半幅缺左侧时槽位 1 才是右框）",
       present_boxes([None, R]) == [R], str(present_boxes([None, R])))

    # 半幅 → 整幅：只留当前框，**恒 1 槽**（形态由槽数编码）
    ok("设整幅：半幅两框 → 只留当前框的 1 槽",
       set_box_full([L, R], 0) == [L], str(set_box_full([L, R], 0)))
    ok("设整幅后确实是整幅形态", is_full_content(set_box_full([L, R], 0)))
    ok("设整幅：下标越界 → 原样不动（不崩、不清空）",
       set_box_full([L, R], 5) == [L, R], str(set_box_full([L, R], 5)))
    ok("设整幅：空表 → 空表", set_box_full([], 0) == [])

    # 整幅 → 半幅：无损，按中心位置定左右
    # ⚠️ F 的中心 x=500 正好落在 SIZE/2=500 上，而 half_sides 用的是
    #    `cx < mid_x` → 严格小于才算左，所以它判**右**。这里刻意用它验
    #    "按位置判定"这条规则真的在生效（换个框就该换边）。
    ok("整幅切半幅：中心在中线右侧 → [None, 右]",
       set_box_half([F], 0, SIZE) == [None, F], str(set_box_half([F], 0, SIZE)))
    ok("整幅切半幅后不再是整幅形态",
       is_full_content(set_box_half([F], 0, SIZE)) is False)
    ok("整幅切半幅：框在左半 → [左, None]（按中心位置，不按整幅身份）",
       set_box_half([L], 0, SIZE) == [L, None], str(set_box_half([L], 0, SIZE)))

    # 删框：半幅恒 2 槽（这是用户报过的"删掉整幅框后另一个自动变整幅"的根因）
    ok("半幅删左框 → 仍 2 槽，剩下的是右框",
       drop_box([L, R], 0, SIZE) == [None, R], str(drop_box([L, R], 0, SIZE)))
    ok("半幅删剩一个后形态仍是半幅（不变成整幅）",
       is_full_content(drop_box([L, R], 0, SIZE)) is False)
    ok("半幅删光 → 空表", drop_box([L, R], 0, SIZE) is not None
       and drop_box([L], 0, SIZE) == [], str(drop_box([L], 0, SIZE)))
    ok("删框：下标越界 → 原样不动", drop_box([L, R], 9, SIZE) == [L, R])
    ok("整幅删框 → 空表（只有 1 槽，删了没别的可剩）",
       drop_box([F], 0, SIZE) == [], str(drop_box([F], 0, SIZE)))

    # 标注外观按**槽位**给，不按"第几个框"（只检出一侧时仍标左框）
    ok("半幅缺右侧 → 名/色仍按槽位给（左框绿、右框蓝）",
       (lambda nc: nc[0] == ["左框", "右框"])(
           slot_names_colors([L, None])),
       str(slot_names_colors([L, None])))
    ok("整幅 1 槽 → 名为「整幅」且用靛蓝",
       (lambda nc: nc[0] == ["整幅"]
        and nc[1][0] == (0xE5, 0x46, 0x4F))(slot_names_colors([F])),
       str(slot_names_colors([F])))
    ok("畸形存档（>2 槽）不炸：退回按序号给",
       len(slot_names_colors([L, R, L])[0]) == 3,
       str(slot_names_colors([L, R, L])))
