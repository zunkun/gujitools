# -*- coding: utf-8 -*-
"""页面清单按 stem 对齐到目录里的实际文件（独立任务页复用）。"""

from __future__ import annotations

import os
from pathlib import Path
from desktop.utils.files import IMAGE_SUFFIXES
from typing import TYPE_CHECKING, Any, Callable, cast


def reconcile_page_files(pages: list[dict], directory: Path) -> tuple[list[dict], int]:
    """把页面清单按 **stem** 对齐到目录里的实际文件（jpg/png 等格式都支持）。

    - 清单里的路径还在 → 原样保留；
    - 路径不在、但有同 stem 的其它格式（png ↔ jpg）→ 换成实际存在的那个；
    - 同 stem 同时有多个格式 → 优先保留原后缀，否则取目录里排序后的第一个；
    - 完全找不到同 stem → 原样保留（由 ``_manifest_paths`` 过滤），不清空清单。

    返回 ``(新清单, 对上的页数)``。对上的页数为 0 表示上游整批换了产物，
    调用方应整表重建；目录读不了时返回 ``-1``，调用方保持原样（不误清空）。
    """
    if not pages:
        return list(pages), 0
    by_stem: dict[str, list[Path]] = {}
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                suffix = Path(entry.name).suffix.lower()
                if suffix not in IMAGE_SUFFIXES:
                    continue
                path = Path(entry.path)
                by_stem.setdefault(path.stem, []).append(path)
    except OSError:
        return list(pages), -1
    for options in by_stem.values():
        options.sort(key=lambda path: path.name)

    kept: list[dict] = []
    resolved = 0
    for page in pages:
        text = str(page.get("file") or "")
        if not text:
            kept.append(page)
            continue
        current = Path(text)
        options = by_stem.get(current.stem) or []
        if not options:
            kept.append(page)
            continue
        resolved += 1
        if current in options:
            kept.append(page)
            continue
        chosen = next(
            (path for path in options if path.suffix.lower() == current.suffix.lower()),
            options[0],
        )
        updated = dict(page)
        updated["file"] = str(chosen)
        kept.append(updated)
    return kept, resolved

