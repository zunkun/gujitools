# -*- coding: utf-8 -*-
"""页名解析、标题切换节点与逐页左右侧。"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


# ---------------------------------------------------------------- 页名解析
def image_name_parts(path) -> Tuple[Optional[int], Optional[str]]:
    """解析数字页名，返回 (页名数字, side)；side 可能为空。"""
    import os
    import re

    name = os.path.splitext(os.path.basename(str(path)))[0].lower()
    match = re.fullmatch(r"(\d+)(?:[_-](l|r))?", name)
    if not match:
        return None, None
    return int(match.group(1)), match.group(2)


def resolve_title_nodes(
    image_files: Sequence, title_switch_nodes: Sequence
) -> List[Tuple[int, Tuple[str, str]]]:
    """把配置里的 [页名, 标题, side] 解析为「图片下标 → (标题, 侧别)」。

    ``页名`` 是**原始页码**（如 ``5`` / ``5-r``），不是列表下标——用户填
    「15」想的是原书第 15 页，即使该页被拖到别处，标题切换仍要跟着它。
    """
    resolved = {}
    for node in title_switch_nodes or []:
        if len(node) < 2:
            continue
        anchor_spec = str(node[0]).strip()
        title = node[1]
        requested_side = str(node[2]).lower() if len(node) > 2 else "left"
        page, node_side = image_name_parts(anchor_spec)
        if page is None and anchor_spec.isdigit():
            page, node_side = int(anchor_spec), None
        if page is None:
            continue
        candidates = []
        for index, path in enumerate(image_files):
            file_page, file_side = image_name_parts(path)
            if file_page != page:
                continue
            if node_side and file_side != node_side:
                continue
            candidates.append((index, file_side))
        if not candidates:
            continue
        if requested_side in ("left", "right"):
            matching = [
                index for index, side in candidates if side == requested_side[0]
            ]
            if not matching:
                matching = [index for index, side in candidates if side is None]
            anchor = matching[0] if matching else candidates[0][0]
        else:
            anchor = candidates[0][0]
        resolved[anchor] = (title, requested_side)
    return sorted(resolved.items())


def sides_for_pages(
    total: int, sorted_nodes: Sequence, page_number_start_page: int
) -> List[str]:
    """逐页给出标题/页码所在侧（left / right）。

    从起始标注页（或最近的章节节点）开始按图片序号交替左右。
    """
    sides: List[str] = []
    # ⚠️ 起始页夹进 [1, total]（2026-09-26 第二轮审计）：校验层只保证 >=1，
    #    `start_page=50、图片 30 张` 时 anchor 永远匹配不到任何页，offset 全为
    #    负数 → Python 负数取模让**每一页**的奇偶性整体翻转（页码/标题左右
    #    反侧），且无提示。夹到最后一张 = "从末页起排"，与直觉一致。
    anchor_start = min(max(int(page_number_start_page or 1), 1), max(1, total)) - 1
    for image_index in range(total):
        anchor_index = anchor_start
        anchor_side = "left"
        for node_index, (_title, node_side) in sorted_nodes:
            if anchor_index <= node_index <= image_index and node_side in (
                "left",
                "right",
            ):
                anchor_index = node_index
                anchor_side = node_side
        offset = image_index - anchor_index
        sides.append(
            anchor_side
            if offset % 2 == 0
            else ("right" if anchor_side == "left" else "left")
        )
    return sides


# ---------------------------------------------------------------- 跳过页
def _page_skipped(skip_pages, current_page: int, image_name) -> bool:
    """本页是否命中 skip_pages（与 functions/print.py 的解析规则一致）。

    纯数字按**最终清单序号**（1 起）匹配；带侧别的写法（``5-r``）按同名回查。
    """
    for spec in skip_pages or []:
        text = str(spec).strip()
        if text.isdigit():
            if int(text) == current_page:
                return True
            continue
        page, side = image_name_parts(text)
        if page is None or not image_name:
            continue
        file_page, file_side = image_name_parts(image_name)
        if file_page == page and (side is None or file_side == side):
            return True
    return False
