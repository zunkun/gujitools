# -*- coding: utf-8 -*-
"""任务详情页的页面清单控制器：manifest 维护、缩略图/尺寸提供、页面增删。"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QUrl, QSize
from PySide6.QtGui import QDesktopServices, QImageReader
from PySide6.QtWidgets import QFileDialog


class PageListMixin:
    """依赖宿主页面提供的属性：store/task_id、pages、pdf_page_count、
    preview_stack、detect_viewer、extract_result_viewer、log_view、_toast()。"""

    # ------------------------------------------------------------------ 清单
    def _refresh_manifest(self) -> None:
        if not self.task_id:
            return
        self.pages = self.store.load_pages(self.task_id)

    def _manifest_paths(self) -> list[Path]:
        return [Path(p["file"]) for p in self.pages if Path(p["file"]).exists()]

    def _page_thumb_for(self, path_text: str, box=None, parea: int = 1,
                        border_mm=None, boxes=None):
        """extract/rembg 数字页名 → 预生成页缩略图。

        box（原始像素坐标）非空时，返回在缩略图上按 area/border 规则
        合成的效果图参数（坐标/边距按缩略图比例缩放）。返回：
        - {"path": 缩略图路径, "effect": {boxes, area, border, dpi} | None}
        - None：无可用缩略图，调用方回退真图

        ⚠️ ``boxes`` 优先：合成必须拿**原始检测框列表**而不是并集单框——
        双框 + area=2/3 若只给并集框，``compose_region_output`` 会误判为
        「单框 → 对称画布」（凭空多出一半空白镜像），与真实产出不符。
        """
        p = Path(path_text)
        if not p.stem.isdigit() or not self.task_id:
            return None
        allowed = {
            self.store.extract_output_dir(self.task_id),
            self.store.rembg_preview_output_dir(self.task_id),
            self.store.rembg_output_dir(self.task_id),
        }
        if p.parent not in allowed:
            return None
        total = self.pdf_page_count or 0
        n = int(p.stem)
        if total and n > total:
            return None
        thumb = self.store.source_thumbnails_dir(self.task_id) / f"{n:04d}.jpg"
        if not thumb.exists():
            return None
        raw = [b for b in (boxes or []) if b] or ([box] if box else [])
        if not raw:
            return {"path": str(thumb), "effect": None}
        meta = self.store.image_size(self.task_id, p.stem)
        if not meta:
            return {"path": str(thumb), "effect": None}
        ts = QImageReader(str(thumb)).size()
        if not ts.isValid() or not meta[0] or not meta[1]:
            return {"path": str(thumb), "effect": None}
        sx, sy = ts.width() / meta[0], ts.height() / meta[1]
        scaled = [
            [b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy] for b in raw
        ]
        return {
            "path": str(thumb),
            "effect": {
                "boxes": scaled,
                "area": parea,
                "border": border_mm,
                "dpi": 300 * sx,  # border 像素随缩略图比例缩放
            },
        }

    def _pdf_page_count_ready(self, count: int) -> None:
        self.pdf_page_count = count

    def _original_image_size(self, path_text: str) -> QSize | None:
        """页面图片的原始像素尺寸：优先 extract 阶段写入 sizes.json 的记录。"""
        if self.task_id:
            meta = self.store.image_size(self.task_id, Path(path_text).stem)
            if meta:
                return QSize(meta[0], meta[1])
        size = QImageReader(path_text).size()
        return size if size.isValid() else None

    # ------------------------------------------------------------------ 增删
    def _active_page_viewer(self):
        """当前预览阶段对应的可编辑查看器（detect 或 extract）。"""
        return (
            self.detect_viewer if self.preview_stack.currentIndex() == 1
            else self.extract_result_viewer
        )

    def _viewer_index_to_manifest_index(self, viewer, row: int) -> int:
        """把预览区的行号换算成页面清单里的下标。

        预览区展示的是"文件确实存在"的那部分页面（``_manifest_paths``），
        清单里可能有条目对应的图片已被外部删除，两者行号会错位——直接拿
        行号去 pop/insert 会删错页、插错位置。这里按路径反查。
        """
        paths = self._manifest_paths()
        if row < 0 or row >= len(paths):
            return -1
        target = str(paths[row])
        for index, page in enumerate(self.pages):
            if str(page.get("file")) == target:
                return index
        return -1

    def delete_selected_page(self) -> None:
        """删除当前选中的页面：按路径反查 manifest 下标后落盘。

        预览行号不能直接用于删除——文件缺失会导致查看器行号与清单下标错位；
        故先经 _viewer_index_to_manifest_index 按路径反查真实下标再 pop，
        删除后刷新预览并同步 detect/extract 两侧。
        """
        if not self.task_id:
            return
        viewer = self._active_page_viewer()
        row = viewer.strip.currentRow()
        if row < 0:
            self._toast("warning", "提示", "请先选择要删除的页面。")
            return
        index = self._viewer_index_to_manifest_index(viewer, row)
        if index < 0:
            self._toast("warning", "提示", "该页面已不在清单中，请刷新后重试。")
            return
        removed = self.pages.pop(index)
        self.store.save_pages(self.task_id, self.pages)
        self.log_view.append(f"已删除页面：{removed.get('label')}")
        self._refresh_preview()
        if self.preview_stack.currentIndex() == 0:
            self._refresh_preview(1)

    def insert_pages(self) -> None:
        """插入图片到清单：按路径反查锚点下标，避免行号错位插错位置。

        弹文件框选图后复制到 extract 输出目录，再用当前选中行经路径反查得到
        manifest 插入锚点；文件缺失时查看器行号与清单下标会错位，必须用路径。
        """
        if not self.task_id:
            return
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if not filenames:
            return
        # 手动插入的图片直接放入 stages/extract，与提取结果同目录
        target_dir = self.store.extract_output_dir(self.task_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        viewer = self._active_page_viewer()
        row = viewer.strip.currentRow()
        anchor = self._viewer_index_to_manifest_index(viewer, row)
        insert_at = anchor + 1 if anchor >= 0 else len(self.pages)
        for filename in filenames:
            source = Path(filename)
            target = target_dir / source.name
            counter = 1
            while target.exists():
                target = target_dir / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            shutil.copy2(source, target)
            self.pages.insert(insert_at, {"file": str(target), "label": target.stem})
            insert_at += 1
        self.store.save_pages(self.task_id, self.pages)
        self.log_view.append(f"已插入 {len(filenames)} 张图片。")
        self._refresh_preview()
        if self.preview_stack.currentIndex() == 0:
            self._refresh_preview(1)

    # ------------------------------------------------------------------ 杂项
    def _image_selected(self, index: int, path_text: str) -> None:
        pass  # 预览组件内部已渲染大图，此处留作扩展

    def _open_task_dir(self) -> None:
        if self.task_id:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.store.task_dir(self.task_id)))
            )
