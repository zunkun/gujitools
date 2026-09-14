# -*- coding: utf-8 -*-
"""页面清单（pages.json）：当前任务参与处理的页集合。"""

from __future__ import annotations

from pathlib import Path

from desktop.utils.files import IMAGE_SUFFIXES, natural_key
from desktop.store.json_io import read_json, write_json


class PageManifestMixin:
    """pages.json 的读写与按阶段输出目录重建。"""

    def pages_path(self, task_id: str) -> Path:
        """当前任务的页面清单文件：任务目录下的 pages.json。"""
        return self.task_dir(task_id) / "pages.json"

    def load_pages(self, task_id: str) -> list[dict]:
        """读取页面清单；文件缺失或格式异常时返回空列表。"""
        data = read_json(self.pages_path(task_id), [])
        return data if isinstance(data, list) else []

    def save_pages(self, task_id: str, pages: list[dict]) -> None:
        """写回页面清单；任务目录已删除时跳过（不重建目录）。"""
        if not self.task_dir(task_id).exists():
            return
        write_json(self.pages_path(task_id), pages)

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
        """待打印列表文件：任务目录下的 print.json。"""
        return self.task_dir(task_id) / "print.json"

    def load_print_doc(self, task_id: str) -> dict | None:
        """读取 print.json 全文（含 area/border/pages）；缺失或非字典时返回 None。"""
        data = read_json(self.print_pages_path(task_id), None)
        return data if isinstance(data, dict) and "pages" in data else None

    def save_print_doc(self, task_id: str, doc: dict) -> None:
        """写回 print.json；任务目录已被删除时静默跳过（不重建目录）。"""
        if not self.task_dir(task_id).exists():
            return
        write_json(self.print_pages_path(task_id), doc)

    def load_print_pages(self, task_id: str) -> list[dict]:
        """只取 print.json 的 pages 列表；无文档时返回空列表。"""
        doc = self.load_print_doc(task_id)
        return doc.get("pages", []) if doc else []

    def save_print_pages(self, task_id: str, entries: list[dict]) -> None:
        """只替换 print.json 的 pages 字段，保留 area/border 等其它配置。"""
        doc = self.load_print_doc(task_id) or {"area": 1, "border": None, "pages": []}
        doc["pages"] = entries
        self.save_print_doc(task_id, doc)
