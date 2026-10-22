# -*- coding: utf-8 -*-
"""内容类别自测：harfcontent（半幅）/ fullcontent（整幅）在下游的落地行为。

新模型 `static/weights/bookcontent.pt` 是**两类**：harfcontent（半幅，原 bookcontent
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

    # ---- 1. 逐框输出清单（半幅：-l/-r；整幅：页名无后缀）----
    left, right = (1, 2, 3, 4), (5, 6, 7, 8)
    outs = TextRegionProcessor._box_outputs(left, right, False, None)
    ok("半幅 → 左/右两条（-l/-r）",
       outs == [(left, "-l"), (right, "-r")], str(outs))
    outs = TextRegionProcessor._box_outputs(None, right, False, None)
    ok("半幅只检出一侧 → 只一条（另一侧 None 被跳过）",
       outs == [(right, "-r")], str(outs))
    outs = TextRegionProcessor._box_outputs(None, None, True, (9, 9, 99, 99))
    ok("整幅 → 一条、后缀为空（页名输出）",
       outs == [((9, 9, 99, 99), "")], str(outs))

    # ---- 2. 逐框裁剪：每个框各自一张图，不再有整页/并集/对称 ----
    from desktop.workers.preview_worker import region_canvas_specs

    W, H = 1000, 800
    _pad_px = parse_border_mm("10", 300)          # 10mm @300dpi
    assert _pad_px is not None
    pad = _pad_px[0]
    detected_full = [40, 30, 960, 770]            # 检测到的整幅框（略小于整页）

    ok("整幅框 border=0 → 紧裁「框 + border」，不是整页",
       region_canvas_specs((W, H), [detected_full], "0")
       == [((960 - 40, 770 - 30), ((tuple(detected_full), 0, 0),))],
       str(region_canvas_specs((W, H), [detected_full], "0")))
    ok("border=None 也不再整页铺满（同样紧裁到框）",
       region_canvas_specs((W, H), [detected_full], None)
       == [((960 - 40, 770 - 30), ((tuple(detected_full), 0, 0),))],
       str(region_canvas_specs((W, H), [detected_full], None)))
    ok("显式给 border 时画布 = 框 + 四周留白",
       region_canvas_specs((W, H), [detected_full], "10")[0][0]
       == (960 - 40 + pad * 2, 770 - 30 + pad * 2),
       str(region_canvas_specs((W, H), [detected_full], "10")))
    ok("无检测框 → 整页原图一张",
       region_canvas_specs((W, H), [], "0") == [((W, H), [])])

    # 两个框各自一张（顺序即传入顺序）
    two_boxes = [[0, 0, 200, 100], [800, 0, 1000, 100]]
    pair = region_canvas_specs((W, H), two_boxes, "0")
    ok("双框 → 两条独立画布（每个框一张）",
       len(pair) == 2 and all(s[0] == (200, 100) for s in pair), str(pair))

    # CLI 侧同一套语义
    import inspect

    tr_src = inspect.getsource(TextRegionProcessor._process_single_image)
    ok("CLI 整幅框原样下传（boxes = [full_box]，不归一整页）",
       "boxes = [full_box]" in tr_src, "整幅仍被换成整页框")
    ok("CLI 逐框循环输出（_box_outputs）",
       "_box_outputs" in tr_src and "for box, suffix in" in tr_src)
    ok("CLI 源码里不再有 area 分支", "area_mode" not in tr_src)
    ok("GUI 合成层不再有整页/对称分支",
       "whole_page_box" not in inspect.getsource(region_canvas_specs)
       and "build_symmetric_layout" not in inspect.getsource(region_canvas_specs))

    # ---- 3. 派生条目：每个检测框一条 ----
    from desktop.services.print_plan import (
        entry_to_effect_spec, plan_rembg_submit_entries,
    )

    def _entries(boxes_for):
        return plan_rembg_submit_entries(
            manifest_paths=[Path("0001.png")],
            result_path_for=lambda stem: Path(f"{stem}.png"),
            boxes_for=boxes_for,
        )

    # 整幅：单槽 [full]
    one = _entries(lambda _p: [[0, 0, W, H]])
    ok("整幅单槽 → 派出一条，full 标记为真",
       len(one) == 1 and one[0]["full"] is True and one[0]["label"] == "0001",
       str(one))
    eff = entry_to_effect_spec(one[0], "0")["effect"]
    ok("effect 只带 boxes/border（没有 area/full）",
       set(eff) == {"boxes", "border"}, str(eff))

    # 半幅：两槽（含 null）——即便只剩一个有效框，也**不能**当整幅
    half_single = _entries(lambda _p: [[0, 0, 100, 100], None])
    ok("半幅两槽只检出一侧 → full 为假且 label 带 -l",
       len(half_single) == 1 and half_single[0]["full"] is False
       and half_single[0]["label"] == "0001-l", str(half_single))

    # 半幅双框：拆 -r/-l 两条
    split = _entries(lambda _p: [[0, 0, 100, 100], [200, 0, 300, 100]])
    ok("半幅双框 → 拆 -r/-l 两条（full 假）",
       len(split) == 2 and {e["label"] for e in split} == {"0001-r", "0001-l"}
       and all(e["full"] is False for e in split), str(split))

    # 半幅漏检一侧：label 必须带 -l/-r（用户 2026-10-01 报：
    # 只有一个左文本框时产物叫 3.png，拼版按后缀判左右会把它误当整幅）
    side_right = _entries(lambda _p: [None, [200, 0, 300, 100]])
    ok("半幅只检出右框 → label 0001-r",
       len(side_right) == 1 and side_right[0]["label"] == "0001-r", str(side_right))
    ok("无框 → 一条整页透传（label 为页名、不带 effect）",
       len(_entries(lambda _p: [])) == 1
       and entry_to_effect_spec(_entries(lambda _p: [])[0], "0")["effect"] is None)

    # 端到端：整幅框裁剪出来（不是整页），每个框各一张。
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from desktop.workers.preview_worker import compose_region_output

    src = QImage(400, 300, QImage.Format.Format_RGB32)
    src.fill(Qt.GlobalColor.darkGray)
    full_entry = _entries(lambda _p: [[40, 30, 360, 270]])[0]
    eff = entry_to_effect_spec(full_entry, "0")["effect"]
    outs = compose_region_output(src, eff["boxes"], eff["border"])
    ok("整幅页合成产物 = 该框的紧裁尺寸（不再整页）",
       len(outs) == 1 and outs[0].size().width() == 320
       and outs[0].size().height() == 240, str(outs[0].size()))
    ok("框内是内容（整幅框原样裁剪）",
       outs[0].pixelColor(160, 120) != Qt.GlobalColor.white,
       outs[0].pixelColor(160, 120).name())
    pair_src = QImage(400, 300, QImage.Format.Format_RGB32)
    pair_src.fill(Qt.GlobalColor.darkGray)
    pair_out = compose_region_output(
        pair_src, [[0, 0, 100, 100], [200, 0, 300, 100]], "0")
    ok("双框合成 → 两张图，各是框的尺寸",
       len(pair_out) == 2 and all(o.size().width() == 100 for o in pair_out),
       str([o.size() for o in pair_out]))

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
       "utils.model_path()" in tool_src and "bookcontent.pt" not in tool_src,
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
