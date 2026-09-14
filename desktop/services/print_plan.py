# -*- coding: utf-8 -*-
"""打印/提取条目的派生规则（纯函数，无 Qt 依赖，便于独立测试）。

这里的规则是 GUI 各阶段共享的「单一事实来源」：
- 提取缺页     → 续跑 extract 时的 pages 参数；
- 提交条目     → rembg「提交本次任务」的最终图片派生；
- 打印效果     → print 阶段在 worker 内实时合成的规格；
- 待打印列表   → 第四步左侧列表的默认排序与持久化合并。
"""

from __future__ import annotations

from pathlib import Path


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
    start = prev = None
    for n in missing:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            parts.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = prev = n
    if start is not None:
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
    - area=2/3 双框：取双框并集，单条输出；
    - 单框：area=2/3 走对称画布（parea=2），area=1 按普通框；
    - 无框：整页预览图透传。
    最终按 CLI natural sort 排序（同页 r 在 l 前）。
    """
    from utils.sort_utils import pdf_custom_sort_key

    entries: list[dict] = []
    for path in manifest_paths:
        result = result_path_for(path.stem)
        if result is None:
            continue  # 该页尚未生成预览
        boxes = [b for b in (boxes_for(str(path)) or []) if b]
        stem = path.stem
        if area == 1 and len(boxes) == 2:
            entries.append(
                {"file": str(result), "label": f"{stem}-r",
                 "box": boxes[1], "parea": 1}
            )
            entries.append(
                {"file": str(result), "label": f"{stem}-l",
                 "box": boxes[0], "parea": 1}
            )
        elif area in (2, 3) and len(boxes) == 2:
            union = [
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            ]
            entries.append(
                {"file": str(result), "label": stem,
                 "box": union, "parea": 1}
            )
        elif len(boxes) == 1:
            entries.append(
                {"file": str(result), "label": stem, "box": boxes[0],
                 "parea": 2 if area in (2, 3) else 1}
            )
        else:
            entries.append(
                {"file": str(result), "label": stem,
                 "box": None, "parea": 1}
            )
    entries.sort(key=lambda e: pdf_custom_sort_key(e["label"]))
    return entries


def entry_to_effect_spec(entry: dict, border) -> dict:
    """提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。"""
    return {
        "file": entry["file"],
        "label": entry.get("label"),
        "effect": (
            {
                "boxes": [entry["box"]],
                "area": entry.get("parea", 1),
                "border": border,
            }
            if entry.get("box")
            else None
        ),
    }


# ---------------------------------------------------------------- print 效果规格
def plan_print_effects(
    list_entries: list[dict],
    composed: list[dict],
    rembg_dir: Path,
    submitted_labels: set[str],
    border,
) -> list[dict]:
    """第四步列表 + 第三步当前 area/border → worker 合成规格。

    与「提交本次任务」复用同一套派生规则（plan_rembg_submit_entries）：
    源图为 stages/rembgpreview 去底图，effect 携带检测框/area/border，
    由 run_print_stage 在子进程内实时合成后再排版为 PDF。

    与用户在第四步保存的列表（拖动排序/删除/外部插入）按 label 对齐：
    - 命中当前 area 派生集合的条目，按用户列表顺序输出合成规格；
    - 用户插入的外部图片（不在 stages/rembg 目录）整图透传；
    - area 模式切换后已失效的旧提交图（如旧 82-r/82-l 被新 82 取代）
      丢弃，当前集合中新派生的条目按默认顺序补在末尾，避免漏页或重复。
    """
    dmap = {c["label"]: c for c in composed}
    effects: list[dict] = []
    used: set[str] = set()
    for e in list_entries:
        label = e.get("label") or Path(e["file"]).stem
        spec = dmap.get(label)
        if spec is not None:
            effects.append(entry_to_effect_spec(spec, border))
            used.add(label)
        elif Path(e["file"]).parent != rembg_dir:
            # 用户手动插入的外部图片：不做区域合成，整页参与排版
            effects.append({"file": e["file"], "effect": None})
    # 仅补「当前 area 派生出、但提交产物里尚不存在」的条目（area 模式
    # 切换后的新结构页）；已存在提交图却不在用户列表的，属于用户主动
    # 删除，不得补回。
    for spec in composed:
        if spec["label"] not in used and spec["label"] not in submitted_labels:
            effects.append(entry_to_effect_spec(spec, border))
    return effects


# ---------------------------------------------------------------- 待打印列表
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
            out.append({"file": file_text,
                        "label": p.get("label") or Path(file_text).stem})
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
