# -*- coding: utf-8 -*-
"""页面清单（pages.json）：当前任务参与处理的页集合。"""

from __future__ import annotations

import json
from pathlib import Path

from ..utils.files import IMAGE_SUFFIXES, natural_key


class PageManifestMixin:
    """pages.json 的读写与按阶段输出目录重建。"""

    def pages_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "pages.json"

    def load_pages(self, task_id: str) -> list[dict]:
        path = self.pages_path(task_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def save_pages(self, task_id: str, pages: list[dict]) -> None:
        self.pages_path(task_id).write_text(
            json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def refresh_pages_from_dir(self, task_id: str, directory: Path) -> list[dict]:
        """用某阶段输出目录重建页面清单（大任务当前的页集合）。"""
        pages = []
        if directory.exists():
            files = sorted(
                (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
                key=lambda f: natural_key(f.name),
            )
            pages = [{"file": str(f), "label": f.stem} for f in files]
        self.save_pages(task_id, pages)
        return pages

    # ---------- print 页面列表 print.json ----------
    # 文档格式：{"area": int, "border": str|null, "pages": [{file,label,box,parea}]}
    # box 为该条目的效果区域（原始像素坐标），parea 为合成用 area 语义
    # （1=普通框+border 裁剪，2=对称画布）；None 表示整页透传。

    def print_pages_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / "print.json"

    def load_print_doc(self, task_id: str) -> dict | None:
        path = self.print_pages_path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) and "pages" in data else None

    def save_print_doc(self, task_id: str, doc: dict) -> None:
        self.print_pages_path(task_id).write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def load_print_pages(self, task_id: str) -> list[dict]:
        doc = self.load_print_doc(task_id)
        return doc.get("pages", []) if doc else []

    def save_print_pages(self, task_id: str, entries: list[dict]) -> None:
        doc = self.load_print_doc(task_id) or {"area": 1, "border": None, "pages": []}
        doc["pages"] = entries
        self.save_print_doc(task_id, doc)
