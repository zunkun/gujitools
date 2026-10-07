# -*- coding: utf-8 -*-
"""内容类别自测：harfcontent（半幅）/ fullcontent（整幅）在下游的落地行为。

新模型 `weights/bookcontent.pt` 是**两类**：harfcontent（半幅，原 bookcontent
改名）与 fullcontent（整幅，整页单一内容区），两类对一页互斥。本模块守住
「整幅」这条新增语义在三处的行为（都不需要真的跑 YOLO，纯规则断言）：

1. **整幅框原样下传**（用户 2026-09-29 晚改定，推翻旧的"整幅＝整页"）：
   整幅框本质是"大一点的单独内容框"，区域随框走——area=1/2/3 统一按
   **area=3 的合并语义**走单框布局（不拆 ``-l``/``-r``、不做对称镜像；
   border 空 → 整页画布写回原位置、框外白，给 border → 紧裁「框 + border」）；
   只有 **area=4 保留框外内容**（框归一整页）。半幅的既有行为一律不变。
2. **派生条目**：整幅单槽在 area=1/2/3 下都是一条，且 ``full`` 标记随条目/
   effect 透传到合成层（合成层据此把内容区当整页）。
3. 槽位约定（半幅 2 槽 / 整幅 1 槽）是整条链路的唯一判据。
4. **互斥消解**三条规则（窄整幅剔除 / 双半幅压制整幅 / 单半幅比置信度）与
   参考实现 `gujitrain/test/predict_bookcontent.py` 同规则，消解后两类互斥，
   且"剔了框"必须对用户可见。
"""

from __future__ import annotations

NAME = "content_classes"
DEPENDS: list[str] = []
TITLE = "内容类别（harfcontent 半幅 / fullcontent 整幅）"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok

    from functions.detect import PageBoxes
    from functions.text_region import TextRegionProcessor
    from utils.box_geometry import parse_border_mm

    # ---- 1. area=1 输出清单（半幅：-l/-r）----
    # ⚠️ 整幅页不走这条路：它按整页单图输出（见第 2 节），因此这里不需要、
    #    也不该再为「整幅要不要拆左右」留分支。
    left, right = (1, 2, 3, 4), (5, 6, 7, 8)
    outs = TextRegionProcessor._area1_outputs(left, right)
    ok("半幅 area=1 → 左/右两条（-l/-r）",
       outs == [(left, "-l"), (right, "-r")], str(outs))
    outs = TextRegionProcessor._area1_outputs(None, right)
    ok("半幅只检出一侧 area=1 → 只一条（另一侧 None 被跳过）",
       outs == [(None, "-l"), (right, "-r")], str(outs))

    # ---- 2. 整幅页：框原样下传；area 1/2/3 统一合并语义，area=4 保留整页 ----
    # （用户 2026-09-29 改定，推翻旧的"整幅＝整页"：整幅框本质是"大一点的
    #   单独内容框"，区域随框走；只有 area=4 保留框外内容。）
    from core.command_spec import WHOLE_PAGE_AREA, effective_border_default
    from desktop.workers.preview_worker import region_canvas_specs
    from utils.box_geometry import SYMMETRIC_GAP_MM, whole_page_box
    from utils.units import mm_to_px

    W, H = 1000, 800
    _pad_px = parse_border_mm("10", 300)          # 10mm @300dpi
    assert _pad_px is not None
    pad = _pad_px[0]
    gap = round(mm_to_px(SYMMETRIC_GAP_MM, 300))  # 对称输出的中间间隔
    detected_full = [40, 30, 960, 770]            # 检测到的整幅框（略小于整页）
    page_box = whole_page_box((W, H))
    ok("整页框只有一处定义 whole_page_box = [0,0,W,H]",
       page_box == [0, 0, W, H], str(page_box))

    full_specs = {
        a: region_canvas_specs((W, H), [detected_full], a, "0", full=True)
        for a in (1, 2, 3)
    }
    ok("整幅页 area=1/2/3 的画布完全相同（统一按合并语义）",
       len({repr(v) for v in full_specs.values()}) == 1, str(full_specs))
    ok("整幅页 area=1/2/3 + border → 紧裁「整幅框 + border」（不是整页）",
       full_specs[1] == [((960 - 40, 770 - 30), ((tuple(detected_full), 0, 0),))],
       str(full_specs[1]))
    ok("整幅页 area=1/2/3 border 空 → 整页画布、框内容写回原位置（框外白）",
       region_canvas_specs((W, H), [detected_full], 2, None, full=True)
       == [((W, H), ((tuple(detected_full), 40, 30),))],
       str(region_canvas_specs((W, H), [detected_full], 2, None, full=True)))
    ok("整幅页 area=4 → 归一整页（保留框外内容）",
       region_canvas_specs((W, H), [detected_full], 4, None, full=True)
       == [((W, H), ((tuple(page_box), 0, 0),))],
       str(region_canvas_specs((W, H), [detected_full], 4, None, full=True)))
    ok("整幅页 area=4 显式给 border → 整页 + 白边",
       region_canvas_specs((W, H), [detected_full], 4, "10", full=True)[0][0]
       == (W + pad * 2, H + pad * 2),
       str(region_canvas_specs((W, H), [detected_full], 4, "10", full=True)))
    ok("整幅页的 border 默认跟随所选 area（不再强取 area=4 的 None）",
       effective_border_default(1) == "0"
       and effective_border_default(WHOLE_PAGE_AREA) is None)

    # 半幅既有行为一律不变
    half_single = region_canvas_specs((W, H), [[0, 0, 200, 100]], 2, "10", full=False)
    ok("半幅单框 area=2 仍是「框 + 空白镜像 + 间隔」的对称画布",
       half_single[0][0] == (pad + 200 * 2 + gap + pad, pad + 100 + pad)
       and half_single[0][1][0][1] == pad, str(half_single))
    half_pair = region_canvas_specs(
        (W, H), [[0, 0, 200, 100], [800, 0, 1000, 100]], 1, "0", full=False)
    ok("半幅双框 area=1 仍是两条（-l/-r）",
       len(half_pair) == 2 and all(s[0] == (200, 100) for s in half_pair),
       str(half_pair))
    ok("半幅单框 area=3 也仍是对称画布",
       region_canvas_specs((W, H), [[0, 0, 200, 100]], 3, "10", full=False)[0][0]
       == (pad + 200 * 2 + gap + pad, pad + 100 + pad))

    # CLI 侧同一套语义：整幅框原样下传、且 area=1 不拆整幅
    import inspect

    tr_src = inspect.getsource(TextRegionProcessor._process_single_image)
    ok("CLI 整幅框原样下传（boxes = [full_box]，不再归一整页）",
       "boxes = [full_box]" in tr_src, "整幅仍被换成整页框")
    ok("CLI 整幅页不走 area=1 的 -l/-r 拆分",
       "if area_mode == 1 and not is_full" in tr_src, "整幅仍会被拆左右")
    ok("CLI 整幅页 border 默认跟随所选 area（不再按整页取 None）",
       "effective_border_default(area_mode)" in tr_src
       and "or is_full" not in tr_src, "border 默认仍被 area=4 劫持")
    ok("GUI 整幅页 area=4 同样复用 whole_page_box（CLI/GUI 不各写一套）",
       "whole_page_box" in inspect.getsource(region_canvas_specs),
       "GUI 自写了一套整页归一")

    # ---- 3. 派生条目：整幅单条 + full 标记透传 ----
    from desktop.services.print_plan import (
        entry_to_effect_spec, plan_rembg_submit_entries,
    )

    def _entries(boxes_for, area: int):
        return plan_rembg_submit_entries(
            manifest_paths=[Path("0001.png")],
            result_path_for=lambda stem: Path(f"{stem}.png"),
            boxes_for=boxes_for,
            area=area,
        )

    # 整幅：单槽 [full]
    one = _entries(lambda _p: [[0, 0, W, H]], 2)
    ok("整幅单槽 → area=2 派生一条，full 标记为真",
       len(one) == 1 and one[0]["full"] is True, str(one))
    eff = entry_to_effect_spec(one[0], None)["effect"]
    ok("整幅的 full 透传到 effect（合成层据此抑制镜像、area=4 归一整页）",
       eff.get("full") is True, str(eff))

    # 半幅：两槽（含 null）——即便只剩一个有效框，也**不能**当整幅
    half_single = _entries(lambda _p: [[0, 0, 100, 100], None], 2)
    ok("半幅两槽只检出一侧 → full 为假（保留镜像语义）",
       len(half_single) == 1 and half_single[0]["full"] is False,
       str(half_single))

    # area=1 双框半幅：拆 -r/-l 两条，full 均为假
    split = _entries(lambda _p: [[0, 0, 100, 100], [200, 0, 300, 100]], 1)
    ok("半幅 area=1 → 拆 -r/-l 两条（full 假）",
       len(split) == 2 and {e["label"] for e in split} == {"0001-r", "0001-l"}
       and all(e["full"] is False for e in split), str(split))

    # 整幅 area=1：只一条、label 就是页名（不拆）
    full_area1 = _entries(lambda _p: [[0, 0, W, H]], 1)
    ok("整幅 area=1 → 只一条，label 为页名（不拆 -r/-l）",
       len(full_area1) == 1 and full_area1[0]["label"] == "0001"
       and full_area1[0]["full"] is True, str(full_area1))

    # 半幅 area=1 漏检一侧：label 必须带 -l/-r（用户 2026-10-01 报：
    # 只有一个左文本框时产物叫 3.png，拼版按后缀判左右会把它误当整幅）
    side_left = _entries(lambda _p: [[0, 0, 100, 100], None], 1)
    ok("半幅 area=1 只检出左框 → label 0001-l（保留左右身份）",
       len(side_left) == 1 and side_left[0]["label"] == "0001-l"
       and side_left[0]["full"] is False, str(side_left))
    side_right = _entries(lambda _p: [None, [200, 0, 300, 100]], 1)
    ok("半幅 area=1 只检出右框 → label 0001-r",
       len(side_right) == 1 and side_right[0]["label"] == "0001-r", str(side_right))
    ok("半幅 area=2/3 单侧仍是对称整页输出（label 不带后缀，与 CLI 一致）",
       all(
           _entries(lambda _p: [[0, 0, 100, 100], None], a)[0]["label"] == "0001"
           for a in (2, 3)
       ))

    # 端到端（用户报的「area=1 显示的是整个页面，而不是 fullcontent 所在区域」）：
    # 整幅框原样下传——border 空时整页画布、框内容写回原位置（框外白）；
    # area=4 才保留框外内容（整页原图）。
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from desktop.workers.preview_worker import compose_region_output

    src = QImage(400, 300, QImage.Format.Format_RGB32)
    src.fill(Qt.GlobalColor.darkGray)
    full_entry = _entries(lambda _p: [[40, 30, 360, 270]], 2)[0]
    eff = entry_to_effect_spec(full_entry, None)["effect"]
    outs = compose_region_output(
        src, eff["boxes"], eff["area"], eff["border"], full=eff["full"])
    ok("整幅页 area=2（border 空）合成产物＝整页尺寸、框内容写回原位置",
       len(outs) == 1 and outs[0].size() == src.size(), str(outs[0].size()))
    ok("整幅页框外留白、框内是内容（区域随整幅框走，不再整页铺满）",
       outs[0].pixelColor(0, 0) == Qt.GlobalColor.white
       and outs[0].pixelColor(200, 150) != Qt.GlobalColor.white,
       f"角落 {outs[0].pixelColor(0, 0).name()} 中心 {outs[0].pixelColor(200, 150).name()}")
    ok("整幅页 area=1/2/3 合成产物完全一致",
       all(
           compose_region_output(
               src, eff["boxes"], a, eff["border"], full=eff["full"])[0]
           .size() == outs[0].size()
           for a in (1, 3)
       ))
    _e4 = {"boxes": [[40, 30, 360, 270]], "area": 4, "border": None, "full": True}
    out4 = compose_region_output(src, _e4["boxes"], 4, None, full=True)[0]
    ok("整幅页 area=4 保留框外内容（四角都是原图内容）",
       out4.size() == src.size()
       and all(out4.pixelColor(x, y) != Qt.GlobalColor.white
               for x, y in ((0, 0), (399, 0), (0, 299), (399, 299))),
       f"{out4.pixelColor(0, 0).name()} {out4.pixelColor(399, 299).name()}")

    # ---- 4. PageBoxes 槽位约定与派生一致 ----
    ok("整幅 PageBoxes.slots() 与 print_plan 判据一致（都是 1 槽）",
       len(PageBoxes(full=(0, 0, W, H)).slots()) == 1
       and len(PageBoxes(left=(0, 0, 100, 100), right=None).slots()) == 2)

    # ---- 5. 互斥消解（resolve_content_boxes）三条规则 ----
    # 与参考实现 gujitrain/test/predict_bookcontent.py 同规则：
    #   1. 窄整幅剔除（宽 ≤70% 的整幅框视为失败检测）
    #   2. 半幅 ≥2 个 → 整幅框全删
    #   3. 半幅恰好 1 个 → 与置信度最高的整幅比，整幅**严格更高**才留整幅
    # 消解后互斥被强制成立。
    from functions.detect import resolution_note
    from utils.yolo_utils import (
        FULL_MIN_WIDTH_RATIO, resolve_content_boxes,
    )

    ok("窄整幅阈值 = 0.70（与参考实现一致）",
       abs(FULL_MIN_WIDTH_RATIO - 0.70) < 1e-9, str(FULL_MIN_WIDTH_RATIO))

    IW = 1000.0
    HARF, FULL = 0, 1

    def _raw(*items):
        """items: (cls, conf, x1, x2) → 原始框（y 随便给，规则不看高度）"""
        return [(c, cf, x1, 0.0, x2, 500.0) for c, cf, x1, x2 in items]

    # 规则1：整幅框宽 600/1000=60% ≤70% → 剔除；800/1000=80% → 保留
    left, right, full, notes = resolve_content_boxes(
        _raw((FULL, 0.9, 100, 700)), IW, HARF, FULL)
    ok("规则1：窄整幅(60%)被剔除，且给出说明",
       bool(full == [] and notes and "整幅" in notes[0]), f"{full} {notes}")
    left, right, full, notes = resolve_content_boxes(
        _raw((FULL, 0.9, 50, 850)), IW, HARF, FULL)
    ok("规则1：够宽(80%)的整幅保留，无说明",
       len(full) == 1 and notes == (), f"{full} {notes}")

    # 规则2：两个半幅（左右各一）+ 有效整幅 → 整幅全删
    left, right, full, notes = resolve_content_boxes(
        _raw((HARF, 0.9, 20, 460), (HARF, 0.9, 540, 980), (FULL, 0.99, 10, 900)),
        IW, HARF, FULL)
    ok("规则2：两个半幅 → 整幅被剔除（即使整幅置信度更高）",
       bool(full == [] and left and right and any("冲突" in n for n in notes)),
       f"left={len(left)} right={len(right)} full={full} {notes}")

    # 规则3a：单半幅(<整幅置信度) → 剔半幅、留整幅
    left, right, full, notes = resolve_content_boxes(
        _raw((HARF, 0.50, 20, 460), (FULL, 0.80, 10, 900)), IW, HARF, FULL)
    ok("规则3：单半幅置信度更低 → 半幅被剔除、整幅保留",
       left == [] and right == [] and len(full) == 1
       and any("半幅" in n for n in notes), f"{left} {right} {full} {notes}")

    # 规则3b：单半幅(>整幅置信度) → 保留半幅、剔整幅
    left, right, full, notes = resolve_content_boxes(
        _raw((HARF, 0.90, 20, 460), (FULL, 0.80, 10, 900)), IW, HARF, FULL)
    ok("规则3：单半幅置信度更高 → 半幅保留、整幅被剔除",
       len(left) == 1 and right == [] and full == []
       and any("整幅" in n for n in notes), f"{left} {right} {full} {notes}")

    # 规则3c：平局 → 留半幅（整幅须**严格**更高）
    left, right, full, notes = resolve_content_boxes(
        _raw((HARF, 0.80, 20, 460), (FULL, 0.80, 10, 900)), IW, HARF, FULL)
    ok("规则3：置信度平局 → 留半幅（整幅须严格更高）",
       len(left) == 1 and full == [], f"{left} {full} {notes}")

    # 无半幅 → 整幅原样保留
    left, right, full, notes = resolve_content_boxes(
        _raw((FULL, 0.9, 10, 900)), IW, HARF, FULL)
    ok("无半幅时整幅原样保留", len(full) == 1 and notes == (), f"{full} {notes}")

    # 消解结果必然互斥 + 半幅按中线分左右
    left, right, full, _n = resolve_content_boxes(
        _raw((HARF, 0.9, 20, 460), (HARF, 0.9, 540, 980)), IW, HARF, FULL)
    ok("消解结果保持互斥（半幅与整幅不同时非空）",
       not (full and (left or right)))
    ok("半幅按中线分左右（cx<500 归左）",
       len(left) == 1 and len(right) == 1
       and (left[0][0] + left[0][2]) / 2 < 500 <= (right[0][0] + right[0][2]) / 2)
    ok("框元组带置信度（第 6 位），供规则3 比较",
       [b[5] for b in left] == [0.9] and left[0][4] == (460 - 20) * 500)
    # unknown 类别（将来新增）按半幅兜底，且不参与规则2/3 的计数与比置信度
    left, right, full, notes = resolve_content_boxes(
        [(2, 0.9, 20.0, 0.0, 460.0, 500.0), (FULL, 0.9, 10.0, 0.0, 900.0, 500.0)],
        IW, HARF, FULL)
    ok("未知类别按半幅兜底（不丢框、也不压制整幅）",
       len(left) == 1 and len(full) == 1, f"{left} {full}")

    # ---- 5b. 消解说明必须对用户可见（CLI + GUI 共四处）----
    ok("无消解时不产生说明行", resolution_note(PageBoxes(left=(1, 1, 2, 2))) is None)
    _page = PageBoxes(left=(1, 1, 2, 2), notes=("剔除1个整幅框(宽≤70%)",))
    _page_note = resolution_note(_page)
    assert _page_note is not None
    ok("有消解时给出可读说明行",
       isinstance(_page_note, str) and "整幅" in _page_note,
       str(_page_note))
    # 防御：绕过消解、两类并存时也要说清（slots 仍按半幅优先）
    _bad = PageBoxes(left=(1, 1, 2, 2), full=(0, 0, 9, 9))
    ok("未消解的两类并存仍会被指出来",
       _bad.conflict is True and "未消解" in (resolution_note(_bad) or ""),
       str(resolution_note(_bad)))
    ok("未消解时按半幅处理（整幅被忽略，harf 行为不变）",
       _bad.slots() == [(1, 1, 2, 2), None])

    import inspect

    from functions.detect import DetectFunction

    ok("CLI detect 会打出消解说明",
       "resolution_note" in inspect.getsource(DetectFunction._report_boxes),
       "DetectFunction 未接说明")
    ok("crop/cropremove 会打出消解说明",
       "resolution_note" in inspect.getsource(
           TextRegionProcessor._process_single_image),
       "TextRegionProcessor 未接说明")
    from desktop.stages import detect_stage

    ok("GUI detect 单页/批量两个路径都会打出消解说明",
       inspect.getsource(detect_stage).count("resolution_note") >= 3,
       "GUI 未在两个检测路径上都接说明")

    # ---- 6. 排查工具 tools/dump_detect.py：用项目权重、只读 ----
    tool_src = (
        Path(__file__).resolve().parents[2] / "tools" / "dump_detect.py"
    ).read_text(encoding="utf-8")
    ok("诊断工具用项目权重解析（不写死权重路径）",
       "utils.model_path()" in tool_src and "weights/bookcontent.pt" not in tool_src,
       "工具绕开了 utils.model_path")
    ok("诊断工具不写配置/不改状态（只可选另存标注图）",
       "write_text" not in tool_src and "json.dump" not in tool_src
       and "os.replace" not in tool_src, "工具产生了写盘副作用")

    # ---- 7. 规则阈值只有一处（不许在别处再抄一个 0.70）----
    root = Path(__file__).resolve().parents[2]
    dup = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if not ({"dist", "build", "__pycache__", "tests"} & set(p.parts))
        and p.name != "yolo_utils.py"
        and "FULL_MIN_WIDTH_RATIO" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    ok("窄整幅阈值只有一处定义（utils/yolo_utils.py）", dup == [], f"重复定义: {dup}")
