# -*- coding: utf-8 -*-
"""版面项：默认并排/单图版面、编辑器回传写回、单图页加图。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）：纯几何与文档改写，
不读像素尺寸以外的东西（尺寸见 ``images``）。
"""

from __future__ import annotations

import math
from pathlib import Path

from desktop.services.imposition.constants import ITEMS_PER_PAGE, SOURCE_LEFT
from desktop.services.imposition.images import image_size
from desktop.services.imposition.sources import classify_source, same_path


def apply_editor_layout(items: list[dict], updates: list[dict]) -> set[str]:
    """把双图编辑器回传的画布位置/尺寸写回对应页面项。

    编辑器用当前图像素系记录新画布原点，并以入口版面比例换算到页面
    ``rect``。更新携带源项序号与路径，避免页面或源清单变化时误改其他项。
    """
    changed: set[str] = set()
    for update in updates:
        index = update.get("index")
        if not isinstance(index, int) or not 0 <= index < len(items):
            continue
        item = items[index]
        path = str(update.get("file") or "")
        if not path or not same_path(item.get("file"), path):
            continue
        rect = [float(value) for value in update.get("rect", ())]
        if len(rect) != 4 or not all(math.isfinite(value) for value in rect):
            raise ValueError("双图编辑回传的拼版区域无效")
        if rect[2] <= 0 or rect[3] <= 0:
            raise ValueError("双图编辑回传的拼版区域无效")
        current = [float(value) for value in item.get("rect", ())]
        if len(current) == 4 and all(
            abs(old - new) < 0.01 for old, new in zip(current, rect)
        ):
            continue
        item["rect"] = rect
        changed.add(path)
    return changed

def page_has_file(page: dict, path_text: str) -> bool:
    """这一页的某张源图是否就是这个文件（形态无关比较）。"""
    return any(
        same_path(item.get("file"), path_text)
        for item in (page or {}).get("items") or []
    )


def pages_having_file(pages: list, path_text: str) -> list[int]:
    """哪些页用了这个源文件（页号列表）。"""
    return [
        index for index, page in enumerate(pages or [])
        if page_has_file(page, path_text)
    ]


def default_items(files: list) -> list[dict] | None:
    """两张源图 → **默认并排版面**（各按原始像素，不改动用户的图）。

    ``files`` 顺序即槽位顺序 ``[右槽, 左槽]``：左槽贴 x=0，右槽紧挨在它右边，
    两者顶部对齐。古籍一页的两半通常同尺寸，摆出来就是标准对开。

    尺寸读不到 / 少于两张时返回 None（调用方负责提示）。
    """
    if len(files) < ITEMS_PER_PAGE:
        return None
    sizes = [image_size(f) for f in files[:ITEMS_PER_PAGE]]
    if any(w <= 0 or h <= 0 for w, h in sizes):
        return None
    right_file, left_file = str(files[0]), str(files[1])
    (right_w, right_h), (left_w, left_h) = sizes
    return [
        # 右槽：序号在前 → 排在左侧那张的右边
        {"file": right_file, "rect": [float(left_w), 0.0, float(right_w),
                                      float(right_h)], "rotation": 0.0},
        # 左槽：序号在后 → 贴最左
        {"file": left_file, "rect": [0.0, 0.0, float(left_w), float(left_h)],
         "rotation": 0.0},
    ]


def make_page(sources: list) -> dict | None:
    """按**源清单顺序**取两张图造一页拼版版面。

    ``sources`` 顺序即源清单顺序（序号小在前）；本函数把 ``sources[0]``
    放进**右槽**、``sources[1]`` 放进**左槽**——这就是用户的口径
    「序号排前面的在右侧，序号大的在左侧」。版面本身见 ``default_items``。
    """
    items = default_items(sources)
    if items is None:
        return None
    return {"items": items}


def single_items(file) -> list[dict] | None:
    """一张源图 → **单图版面**（整幅图 / 落单图专用：原始像素、不旋转）。

    尺寸读不到返回 None（调用方负责跳过 / 提示）。
    """
    width, height = image_size(file)
    if width <= 0 or height <= 0:
        return None
    return [{"file": str(file), "rect": [0.0, 0.0, float(width), float(height)],
             "rotation": 0.0}]


def make_single_page(file) -> dict | None:
    """一张源图**自成一页**（整幅不拼、落单）：版面里只有一项。"""
    items = single_items(file)
    if items is None:
        return None
    return {"items": items}


def append_item_to_page(items: list[dict], file) -> list[dict] | None:
    """单图页「新增图片」：把 ``file`` 并进当前页，返回**新的 items**。

    槽位与摆放口径（用户 2026-09-30：单图页可以再导一张图拼成对页）：

    - 原图是**左半幅**（文件名 ``-l``/``_l`` 结尾）→ 新图进**右槽**
      （``items[0]``），摆在原图**右边**；
    - 其余（右半幅 / 整幅 / 无后缀）→ 新图进**左槽**（``items[1]``），
      摆在原图**左边**；
    - 新图按**原始像素**进版面、顶边与原图对齐、紧贴原图边缘（用户可再
      拖动/缩放）；原图的版面（位置/大小/旋转）**原样保留**，不重排。

    ``items`` 不是恰好一项（只有单图页能加图）或尺寸读不到时返回 None，
    调用方负责提示。
    """
    if len(items) != 1:
        return None
    existing = dict(items[0])
    ex_x, ex_y, ex_w, _ex_h = (float(v) for v in existing["rect"])
    fresh = single_items(file)
    if fresh is None:
        return None
    new_w, new_h = fresh[0]["rect"][2], fresh[0]["rect"][3]
    new_item = {
        "file": str(file),
        "rect": [0.0, ex_y, float(new_w), float(new_h)],
        "rotation": 0.0,
    }
    if classify_source(existing["file"]) == SOURCE_LEFT:
        # 原图是左半幅：新图进右槽，贴在原图右边
        new_item["rect"][0] = ex_x + ex_w
        return [new_item, existing]
    # 其余：新图进左槽，贴在原图左边
    new_item["rect"][0] = ex_x - new_w
    return [existing, new_item]
