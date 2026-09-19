# -*- coding: utf-8 -*-
"""合成规格必须携带「原始检测框 + 原始 area」（纯函数层守卫）。

背景（用户实测反馈）：第三步 area=2、第四步预览也是 area=2，生成的 PDF 却是
"area=1 那种紧裁"的观感。根因是派生层把双框 area=2/3 记成了「并集框 +
parea=1」，而 ``utils.box_geometry.build_output_layout`` 在 border 为空时：

- area=2/3（多框）→ full_page：整页画布，各框**写回原位置**；
- area=1          → 紧裁成「框 + border」的小画布。

两条分支不等价，于是预览整页、成品紧裁。这里把不变量钉在最便宜的一层：
派生出的条目 → effect 规格，必须原样保留原始框与原始 area，且**合成结果与
「原始框 + 原始 area」这条预览语义完全一致**。
"""

NAME = "print_area_semantics"
DEPENDS: list[str] = []
TITLE = "area/border 合成规格不降级"

W, H = 1000, 1400
LEFT = [80, 200, 480, 1200]
RIGHT = [520, 200, 920, 1200]


def run(ctx) -> None:
    import os
    import sys

    from tests.selftests._context import ok

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from pathlib import Path

    from PySide6.QtGui import QColor, QImage, QPainter

    from desktop.services.print_plan import (
        entry_to_effect_spec, plan_rembg_submit_entries,
    )
    from desktop.workers.preview_worker import compose_region_output

    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    for box, color in ((LEFT, QColor("#8899aa")), (RIGHT, QColor("#aa9988"))):
        p.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1], color)
    p.end()
    ok("（前置）合成用的样图可用", not img.isNull())

    def entries_for(boxes, area):
        return plan_rembg_submit_entries(
            manifest_paths=[Path("0001.png")],
            result_path_for=lambda stem: Path(f"{stem}.png"),
            boxes_for=lambda _p: boxes,
            area=area,
        )

    def render(effect):
        if effect is None or not [b for b in (effect.get("boxes") or []) if b]:
            return [(W, H)]
        return [(o.width(), o.height())
                for o in compose_region_output(
                    img, effect["boxes"], effect["area"], effect["border"])]

    bad = []
    combos = 0
    for name, boxes in (("双框", [LEFT, RIGHT]), ("单框", [LEFT])):
        for area in (1, 2, 3, 4):
            for border in (None, "0", "30"):
                combos += 1
                ents = entries_for(boxes, area)
                got: list[tuple[int, int]] = []
                for e in ents:
                    got += render(entry_to_effect_spec(e, border)["effect"])
                # 预览语义：area=1 逐框，其余「原始框 + 原始 area」
                if area == 1:
                    ref: list[tuple[int, int]] = []
                    for b in [b for b in boxes if b]:
                        ref += [(o.width(), o.height())
                                for o in compose_region_output(
                                    img, [b], 1, border)]
                else:
                    ref = [(o.width(), o.height())
                           for o in compose_region_output(
                               img, boxes, area, border)]
                if sorted(got) != sorted(ref):
                    bad.append(f"{name}/area={area}/border={border!r} "
                               f"got={got} ref={ref}")

    ok(f"全部 {combos} 种组合：提交/PDF 的合成结果与第三步预览一致",
       not bad, "; ".join(bad[:3]))

    # ---- 关键形态：双框 area=2/3 必须保留两个原始框与原始 area ----
    for area in (2, 3):
        ents = entries_for([LEFT, RIGHT], area)
        eff = entry_to_effect_spec(ents[0], None)["effect"]
        ok(f"双框 area={area} → 单条，且 effect 携带两个原始框 + 原始 area",
           len(ents) == 1 and eff["area"] == area
           and eff["boxes"] == [LEFT, RIGHT],
           f"{len(ents)} 条 area={eff['area']} boxes={eff['boxes']}")

    # ---- 紧裁陷阱：双框 area=2 无 border 必须是整页，不是并集紧裁 ----
    eff = entry_to_effect_spec(entries_for([LEFT, RIGHT], 2)[0], None)["effect"]
    out = compose_region_output(img, eff["boxes"], eff["area"], eff["border"])
    union_w = max(LEFT[2], RIGHT[2]) - min(LEFT[0], RIGHT[0])
    ok("双框 area=2 无 border → 整页画布（宽 == 原图宽，不是并集紧裁）",
       len(out) == 1 and out[0].width() == W and out[0].width() > union_w,
       f"画布宽={out[0].width()} 原图宽={W} 并集宽={union_w}")

    # ---- 单框 area=2/3 + border 仍走对称画布（不能被降成 area=1）----
    eff = entry_to_effect_spec(entries_for([LEFT], 2)[0], "30")["effect"]
    out = compose_region_output(img, eff["boxes"], eff["area"], eff["border"])
    plain = compose_region_output(img, [LEFT], 1, "30")
    ok("单框 area=2 + border → 对称画布（比 area=1 多出镜像半幅）",
       eff["area"] == 2 and len(out) == 1
       and out[0].width() > plain[0].width(),
       f"area={eff['area']} 宽={out[0].width()} vs area=1 宽={plain[0].width()}")

    del sys
