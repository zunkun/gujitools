# -*- coding: utf-8 -*-
"""打印/提取条目的派生规则（纯函数，无 Qt 依赖，便于独立测试）。

这里的规则是 GUI 各阶段共享的「单一事实来源」：
- 提取缺页     → 续跑 extract 时的 pages 参数；
- 提交条目     → rembg「提交本次任务」的最终图片派生；
- 待打印列表   → 第四步左侧列表的默认排序与持久化合并。

⚠️ 第四步**没有**「按当前参数临时合成」的规则（2026-10-01 用户口径：
去底色那一步必须提交才能传给下一步）：print 只排版「提交本次任务」落盘的
成品图，见 ``taskdetail.submit.SubmitMixin._build_print_effects``。
"""

from __future__ import annotations

from pathlib import Path

from core.command_spec import WHOLE_PAGE_AREA
from utils.box_geometry import is_full_content


# ---------------------------------------------------------------- extract 缺页
def missing_extract_pages_spec(output_dir: Path, total: int) -> str | None:
    """提取输出目录中缺失的页码，压缩为 CLI pages 参数（如 "3,7-9"）。

    页文件名以数字开头（0001.jpg / 0002.jpg …）。无缺失或 total 为 0
    时返回 None（无需续跑）。
    """
    present: set[int] = set()
    if output_dir.exists():
        for f in output_dir.iterdir():
            digits = ""
            for ch in f.stem:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                present.add(int(digits))
    missing = [n for n in range(1, total + 1) if n not in present]
    if not missing or not total:
        return None
    parts: list[str] = []
    start: int | None = None
    prev: int | None = None
    for n in missing:
        if start is None:
            start = prev = n
        elif prev is not None and n == prev + 1:
            prev = n
        else:
            assert prev is not None
            parts.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = prev = n
    if start is not None:
        assert prev is not None
        parts.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ",".join(parts)


# ---------------------------------------------------------------- rembg 提交条目
def plan_rembg_submit_entries(
    manifest_paths: list[Path],
    result_path_for,
    boxes_for,
    area: int,
) -> list[dict]:
    """预览结果 + 检测框 + area/border → 最终图片条目。

    参数
    ----
    manifest_paths   : 页面清单路径（stages/extract 内的页图片）
    result_path_for  : (stem) -> Path|None，某页对应的「生成预览」去底结果
    boxes_for        : (path_str) -> list，某页的检测框 [左框, 右框]
    area             : 区域模式（1=左右分页，2/3=并集/对称画布）

    派生规则与 rembg 预览条目、print 待打印列表完全一致：
    - area=1 双框：拆 <页>-r / <页>-l 两条（古籍阅读顺序 r 在前）；
    - area=1 半幅漏检一侧：单条也保留左右身份（<页>-l / <页>-r，按缺失侧
      所在槽位判定）——否则产物叫 <页>.png，第四步拼版按文件名后缀判
      左右半幅时会把这页误当整幅（用户 2026-10-01 报）；
    - area=2/3 双框：合成一条（不再分栏）；
    - 单框：area=2/3 走对称画布（整页形态，不带后缀），其余按普通框；
    - 无框：整页预览图透传。
    最终按 CLI natural sort 排序（同页 r 在 l 前）。

    ⚠️ ``parea`` 是**原始 area**（不是"降级"后的合成 area），``boxes`` 是
    **原始检测框**（不是并集后的单框）——两者必须原样交给
    ``compose_region_output``。原因见 ``entry_to_effect_spec``：并集框 +
    area=1 与「双框 + area=2/3」在 border 为空时**不等价**，曾导致第三步
    预览是整页、而提交产物与 PDF 被紧裁（用户报的「PDF 成了 area=1 效果」）。
    """
    from utils.sort_utils import pdf_custom_sort_key

    entries: list[dict] = []
    for path in manifest_paths:
        result = result_path_for(path.stem)
        if result is None:
            continue  # 该页尚未生成预览
        # ⚠️ 用**原始槽位**判断是否整幅内容：半幅固定 2 槽 [左,右]（可能含 null），
        #    整幅只占 1 槽。过滤 null 后两者都可能只剩 1 个框，届时无法区分——
        #    整幅页 area=1/2/3 统一按合并语义走单框布局（框原样下传），area=4
        #    才归一整页（见 entry_to_effect_spec 与 preview_worker 的 full 语义）。
        raw_boxes = list(boxes_for(str(path)) or [])
        full = is_full_content(raw_boxes)
        boxes = [b for b in raw_boxes if b]
        stem = path.stem
        if area == 1 and len(boxes) == 2:
            entries.append(
                {"file": str(result), "label": f"{stem}-r",
                 "box": boxes[1], "boxes": [boxes[1]], "parea": 1, "full": False}
            )
            entries.append(
                {"file": str(result), "label": f"{stem}-l",
                 "box": boxes[0], "boxes": [boxes[0]], "parea": 1, "full": False}
            )
        elif area in (2, 3) and len(boxes) == 2:
            union = [
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            ]
            entries.append(
                {"file": str(result), "label": stem,
                 "box": union, "boxes": list(boxes), "parea": area, "full": False}
            )
        elif area == WHOLE_PAGE_AREA and len(boxes) >= 2:
            # 整页模式：整页（或用户手画的多个框）合成一个整体，不拆左右页
            union = [
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            ]
            entries.append(
                {"file": str(result), "label": stem, "box": union,
                 "boxes": list(boxes), "parea": area, "full": False}
            )
        elif len(boxes) == 1:
            label = stem
            if area == 1 and not full and len(raw_boxes) == 2:
                # 半幅(harfcontent)漏检一侧：单条也要保住 -l/-r 身份。
                # ⚠️ 判左右只能看**槽位**（半幅恒 2 槽 [左, 右]，见 half_slots），
                # 不能看框的中心——这里拿到的就是原始槽位。area=2/3 的单框是
                # 对称整页输出（与 CLI 一致），不带后缀。
                label = f"{stem}-l" if raw_boxes[0] else f"{stem}-r"
            entries.append(
                {"file": str(result), "label": label, "box": boxes[0],
                 "boxes": [boxes[0]], "parea": area, "full": full}
            )
        else:
            entries.append(
                {"file": str(result), "label": stem,
                 "box": None, "boxes": [], "parea": area, "full": False}
            )
    entries.sort(key=lambda e: pdf_custom_sort_key(e["label"]))
    return entries


def entry_to_effect_spec(entry: dict, border) -> dict:
    """提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。

    ⚠️ 必须把**原始检测框 + 原始 area** 交给 ``compose_region_output``，
    不能擅自"化简"成并集框 + area=1。``utils.box_geometry.build_output_layout``
    在 border 为空（padding=None）时两条分支并不等价：

    - area=2/3（含多框）→ ``full_page=True``：整页画布，各框**写回原位置**；
    - area=1            → 紧裁成「框 + border」的小画布。

    此前双框 area=2/3 被记成"并集框 + parea=1"，于是第三步预览（用原始框
    + 原始 area）显示整页、提交产物与 PDF 却是紧裁——用户报的「第三步 area=2、
    预览也是 area=2，生成的 PDF 却是 area=1 的效果」就是这么来的（紧裁观感
    与 area=1 的半页裁剪一致）。

    ``full`` 原样透传给合成层：整幅(fullcontent)页的框**原样下传**——
    area=4 保留整页内容、area 1/2/3 统一按合并语义走单框布局（不拆
    ``-l``/``-r``、不镜像）——见 ``desktop.workers.preview_worker.region_canvas_specs``。
    """
    raw = [b for b in (entry.get("boxes") or []) if b]
    if not raw and entry.get("box"):
        raw = [entry["box"]]  # 兼容只带 box 的旧条目/手写条目
    return {
        "file": entry["file"],
        "label": entry.get("label"),
        "effect": (
            {
                "boxes": raw,
                "area": int(entry.get("parea", 1) or 1),
                "border": border,
                "full": bool(entry.get("full")),
            }
            if raw
            else None
        ),
    }


# ---------------------------------------------------------------- print 效果规格
# ---------------------------------------------------------------- 待打印列表
def drop_foreign_stage_pages(
    pages: list[dict] | None, source_dir: Path, stages_root: Path,
) -> list[dict]:
    """从待打印清单里剔除「属于本任务**别的阶段**产物」的条目。

    ⚠️ 为什么必须剔（2026-09-30 引入「图片拼版」时暴露）：``plan_print_entries``
    的规则是「不在当前来源目录里的条目 = 用户手动插入的外部图片，原样保留」。
    可第四步的来源会**切换**——拼版生效时用 ``stages/imposition``，否则用
    ``stages/rembg``。切过去之后，原先那一批还留在 ``print.json`` 里、又不在
    新来源目录下，就会被当成"用户插入的图"**追加到列表末尾**：出 PDF 时
    新旧两套整页全打进去（实测 2 页拼版 + 4 页去底色 = 6 页）。

    判据写死在"路径是否落在本任务的 ``stages/`` 下"：同任务其它阶段的产物
    永远是**上一轮来源**的残留，绝不可能是用户从磁盘上手动挑来的外部图片。
    真正的外部图片（桌面/下载目录…）一律保留。
    """
    if not pages:
        return list(pages or [])
    source = Path(source_dir)
    root = Path(stages_root)
    kept: list[dict] = []
    for page in pages:
        file_text = str(page.get("file") or "")
        if not file_text:
            kept.append(page)
            continue
        candidate = Path(file_text)
        if candidate.parent == source:
            kept.append(page)
            continue
        try:
            if candidate.parent.is_relative_to(root):
                continue  # 本任务别的阶段的产物 → 上一轮来源的残留
        except (TypeError, ValueError):
            pass
        kept.append(page)  # 真正的外部图片：保留用户的插入
    return kept


def plan_print_entries(rembg_files: list[Path], doc: dict | None) -> tuple[list[dict], dict]:
    """第四步待打印图片列表的规划。

    直接使用第三步「提交本次任务」产出的 stages/rembg 最终图片
    （已按 area/border 合成），按古籍阅读顺序（cover/menu 优先、
    同编号 r→l、数字自然序）排列。

    列表不再使用源 PDF 缩略图，直接显示 rembg 最终图片本身；
    print.json 仅持久化用户的拖动/删除/插入顺序。

    返回 (entries, doc)。
    """
    rembg_names = [str(p) for p in rembg_files]
    current_set = set(rembg_names)
    snapshot = set(doc.get("rembg_snapshot") or []) if doc else set()

    def _existing(pages) -> list[dict]:
        out, seen = [], set()
        for p in pages or []:
            file_text = p.get("file")
            if not file_text or file_text in seen or not Path(file_text).exists():
                continue
            entry = {"file": file_text,
                     "label": p.get("label") or Path(file_text).stem}
            # 第四步「版面编辑器」逐图坐标：存在则随条目保留（与 file/label 同级）
            rect = p.get("rect")
            if rect is not None:
                entry["rect"] = list(rect)
            out.append(entry)
            seen.add(file_text)
        return out

    if doc and snapshot == current_set and current_set:
        # rembg 产物未变化：沿用用户保存的顺序（拖动/删除/插入结果）
        entries = _existing(doc.get("pages"))
    else:
        # 首次进入，或重新提交后 rembg 产物集合变化：
        # rembg 最终图按阅读顺序排列；旧列表中用户插入的外部图片
        # （不在 rembg 目录）按原顺序追加在末尾
        external = [
            e for e in _existing(doc.get("pages") if doc else None)
            if e["file"] not in current_set
        ]
        entries = [{"file": str(p), "label": p.stem} for p in rembg_files]
        entries.extend(external)
    new_doc = {"rembg_snapshot": rembg_names, "pages": entries}
    return list(entries), new_doc
