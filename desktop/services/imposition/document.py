# -*- coding: utf-8 -*-
"""拼版文档（页/项）的收敛、命名与页级查询。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）：只管文档结构与
页级纯查询，不碰像素。
"""

from __future__ import annotations

from pathlib import Path

from desktop.services.imposition.constants import (
    JPG_SUFFIX,
    PNG_SUFFIX,
    _CN_DIGITS,
    _JPG_SUFFIXES,
    _PRODUCT_SUFFIXES,
)

def page_product_suffix(page: dict) -> str:
    """一页成品的**输出后缀**：源图全是 jpg/jpeg ⇒ ``.jpg``，否则 ``.png``。

    用户 2026-10-17：「图片拼版，输入图片是 png，就输出 png，输入是 jpg，
    输出也是 jpg」。

    ⚠️ 一页可能混着两种源图 ⇒ **任一张不是 jpg/jpeg 就出 png**：只有 png 带
    alpha，而 jpg 成品必须白底压平（见 :func:`_save_page_atomic`），会把上游
    「去底色」产物的透明底**抹掉**。宁可体积大一点，也不悄悄丢透明。
    """
    for item in page.get("items") or []:
        if not isinstance(item, dict):
            continue
        if Path(str(item.get("file") or "")).suffix.lower() not in _JPG_SUFFIXES:
            return PNG_SUFFIX
    return JPG_SUFFIX


def product_path(dest_dir: Path | str, index: int, page: dict) -> Path:
    """第 ``index``（0 基）页成品的落盘路径：``dest/0001.png`` / ``dest/0001.jpg``。"""
    return Path(dest_dir) / f"{index + 1:04d}{page_product_suffix(page)}"


def is_product_file(candidate: Path | str) -> bool:
    """这个文件是不是**拼版成品页**（``NNNN.png`` / ``NNNN.jpg``，4 位数字名）。

    ⚠️ 后缀认**两种**（用户 2026-10-17 起成品后缀随源图走）：只认 ``.png``
    的话，"格式切换后上一轮多出来的页"会留在盘上，被第四步当成一页打进 PDF。
    清扫（:func:`_sweep_stale`）与新鲜度判据都走这一个函数，别各写一套。
    """
    path = Path(candidate)
    return (
        path.suffix.lower() in _PRODUCT_SUFFIXES
        and len(path.stem) == 4
        and path.stem.isdigit()
    )


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _rect(value) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return [_num(v) for v in value]


def normalize_page(page) -> dict | None:
    """把任意来源的一页拼版收敛成合法形状；不可修复时返回 None。

    ⚠️ 校验必须严：``rect`` 会直接喂给合成函数当落点，坏值（缺字段、0 宽、
    非数字）会让合成抛异常或产出空图，而这份文档在用户的文档目录里、可被
    外部编辑写坏。

    ⚠️ 老版本存过 ``"sheet": [w, h]``（有纸张的时代）。现在**忽略它**：
    版面以两张图为准，纸张已经不存在了，读老任务照样能合成。
    """
    if not isinstance(page, dict):
        return None
    raw_items = page.get("items")
    if not isinstance(raw_items, (list, tuple)):
        return None
    items: list[dict] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        file_text = str(raw.get("file") or "").strip()
        rect = _rect(raw.get("rect"))
        if not file_text or rect is None or rect[2] <= 0 or rect[3] <= 0:
            continue
        items.append(
            {"file": file_text, "rect": rect,
             "rotation": _num(raw.get("rotation"))}
        )
    if not items:
        return None
    return {"items": items}


def normalize_doc(doc) -> dict:
    """整份文档收敛：``{"enabled", "pages", "removed"}``（永不为 None）。

    ``removed`` 是**旧版黑名单**（曾经在「选择拼版」弹窗里「删除图片」移出的图，
    软删——文件不动，只是不再进入候选范围）。⚠️ **2026-11-16 起弹窗不再写它**
    （两个页签连同「删除图片」一起取消，候选 = 所有没被页引用的图）：这里仍
    原样保留，老任务读进来不丢数据，`:func:`remaining_files` 的行为也不变。
    存字符串路径列表，去重保序；读老任务没有这个键时为空列表。
    """
    if not isinstance(doc, dict):
        return {"enabled": False, "pages": [], "removed": []}
    pages = []
    for page in doc.get("pages") or []:
        normalized = normalize_page(page)
        if normalized is not None:
            pages.append(normalized)
    removed: list[str] = []
    seen: set[str] = set()
    raw_removed = doc.get("removed")
    for entry in raw_removed if isinstance(raw_removed, (list, tuple)) else ():
        text = str(entry or "").strip()
        if text and text not in seen:
            seen.add(text)
            removed.append(text)
    return {"enabled": bool(doc.get("enabled")), "pages": pages,
            "removed": removed}


def cn_page_label(index: int) -> str:
    """页序（0 起）→ 中文页码标签：``第一页`` / ``第十二页`` / ``第100页``。

    只覆盖 1~99 的中文写法（古籍拼版页数够用），超出退回阿拉伯数字——
    这里只是**界面文案**，不参与任何匹配，宁可难看也不要写错数字。
    """
    number = int(index) + 1
    if number < 1:
        return f"第{number}页"
    if number > 99:
        return f"第{number}页"
    if number < 10:
        return f"第{_CN_DIGITS[number]}页"
    tens, ones = divmod(number, 10)
    text = ("十" if tens == 1 else f"{_CN_DIGITS[tens]}十")
    if ones:
        text += _CN_DIGITS[ones]
    return f"第{text}页"


def used_source_files(doc: dict) -> set[str]:
    """已被任何一页拼版引用的源图（用于算「剩余未被选择拼版的图片」）。"""
    used: set[str] = set()
    for page in (doc or {}).get("pages") or []:
        for item in page.get("items") or []:
            file_text = str(item.get("file") or "")
            if file_text:
                used.add(file_text)
    return used


def remaining_files(files: list, doc: dict) -> list:
    """源清单里**还没被任何拼版页用过、也没被删除**的图片（顺序沿用源清单）。

    「删除」是黑名单（``removed``，弹窗里用户主动移出选择范围的图），
    不是删文件——恢复后重新回到候选范围。
    """
    used = used_source_files(doc) | removed_source_files(doc)
    return [f for f in files if str(f) not in used]


def removed_source_files(doc: dict) -> set[str]:
    """被用户「删除图片」移出选择范围的源图路径集合（软删除黑名单）。"""
    raw = (doc or {}).get("removed")
    if not isinstance(raw, (list, tuple)):
        return set()
    return {str(entry) for entry in raw if str(entry).strip()}


def excluded_files(files: list, doc: dict) -> list:
    """源清单里被删除的图（**按源清单顺序**）——给弹窗的「已删除」视图展示。"""
    removed = removed_source_files(doc)
    return [f for f in files if str(f) in removed]


def page_source_stems(page: dict) -> list[str]:
    """一页拼版两张源图的名字（去扩展名），按槽位顺序（右、左）。"""
    return [
        Path(str(item.get("file") or "")).stem
        for item in (page or {}).get("items") or []
    ]
