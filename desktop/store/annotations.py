# -*- coding: utf-8 -*-
"""页面标注数据：boxes.json（检测框）与 sizes.json（页面图片原始尺寸）。

坐标均为原始图片像素坐标 [x1, y1, x2, y2]，按阅读顺序存 [左框, 右框]。
image_key 取页面文件名去后缀（stem），workset 副本与 extract 清单里的
同名页面共享同一份数据。
"""

from __future__ import annotations

import time
from pathlib import Path

from desktop.store.json_io import read_json, write_json


class AnnotationMixin:
    """boxes.json / sizes.json 读写。"""

    def _load_json(self, path: Path) -> dict:
        data = read_json(path, {})
        return data if isinstance(data, dict) else {}

    def _save_json(self, path: Path, data: dict) -> None:
        if not path.parent.exists():
            return
        write_json(path, data)

    # ---------- 检测框 boxes.json ----------
    def boxes_path(self, task_id: str) -> Path:
        """检测框存储文件：任务目录下的 boxes.json。"""
        return self.task_dir(task_id) / "boxes.json"

    def detect_boxes_entry(self, task_id: str, image_key: str) -> tuple[list, str] | None:
        """返回 (boxes, origin)；无记录时返回 None。origin: 'auto' | 'manual'。"""
        data = self._load_json(self.boxes_path(task_id))
        entry = data.get(image_key)
        if not entry:
            return None
        return entry.get("boxes", []), entry.get("origin", "auto")

    def save_detect_boxes(
        self, task_id: str, image_key: str, boxes: list, origin: str = "auto"
    ) -> None:
        """写入某页的检测框及其来源标记（auto=自动检测，manual=人工编辑）。"""
        path = self.boxes_path(task_id)
        data = self._load_json(path)
        data[image_key] = {
            "boxes": boxes,
            "origin": origin,
            "updated_at": time.time(),
        }
        self._save_json(path, data)

    # ---------- 页面尺寸 sizes.json ----------
    def sizes_path(self, task_id: str) -> Path:
        """页面原始尺寸文件：任务目录下的 sizes.json。"""
        return self.task_dir(task_id) / "sizes.json"

    def save_image_size(self, task_id: str, image_key: str, width: int, height: int) -> None:
        """记录某页图片的原始像素尺寸，作为框坐标与预览映射的坐标系基准。"""
        path = self.sizes_path(task_id)
        data = self._load_json(path)
        data[image_key] = [int(width), int(height)]
        self._save_json(path, data)

    def image_size(self, task_id: str, image_key: str) -> tuple[int, int] | None:
        """返回某页原始像素尺寸 (width, height)；无记录时返回 None。"""
        data = self._load_json(self.sizes_path(task_id))
        entry = data.get(image_key)
        if not entry:
            return None
        return int(entry[0]), int(entry[1])
