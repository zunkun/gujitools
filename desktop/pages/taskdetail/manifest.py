# -*- coding: utf-8 -*-
"""任务详情页的页面清单控制器：manifest 维护、缩略图/尺寸提供、页面增删。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, QSize
from PySide6.QtGui import QDesktopServices, QImageReader
from PySide6.QtWidgets import QFileDialog


class PageListMixin:
    """依赖宿主页面提供的属性：store/task_id、pages、pdf_page_count、
    preview_stack、detect_viewer、extract_result_viewer、log_view、_toast()。"""

    #: 页缩略图的**图头尺寸**缓存（审计 D9）：键 = (路径, mtime)。
    #: 清单每次增删/重排都会重建，对 320 个条目逐个 `QImageReader.size()`
    #: 虽然只读文件头，主线程累计也有几十~几百毫秒；同一会话里缩略图
    #: 基本不变，缓存后重建清单是零读盘。（实例属性，惰性建——见 __init__）
    _thumb_size_cache: dict | None = None

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
        try:
            cache_key = (str(thumb), thumb.stat().st_mtime)
        except OSError:
            cache_key = None
        # Mixin 宿主可能绕过 __init__（测试探针）：缓存字典惰性建
        cache = self.__dict__.get("_thumb_size_cache")
        if cache is None:
            cache = self._thumb_size_cache = {}
        if cache_key is not None and cache_key in cache:
            ts = cache[cache_key]
        else:
            ts = QImageReader(str(thumb)).size()
            if cache_key is not None:
                cache[cache_key] = ts
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
        # 主线程只算好 (源, 目标) 对（含重名避让）；复制进后台线程（审计 D2：
        # 大图逐张 copy2 在主线程会把界面冻住整个复制时长）。插入锚点在复制
        # 完成后按**当时的**选中行反查（_on_pages_copied）——用户在复制期间
        # 可能已经点了别的行。
        jobs: list[tuple[Path, Path]] = []
        for filename in filenames:
            source = Path(filename)
            target = target_dir / source.name
            counter = 1
            while target.exists():
                target = target_dir / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            jobs.append((source, target))
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker(jobs)
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self, w.finished, self._on_pages_copied, thread
                ),
                connect_queued(
                    self, w.failed,
                    lambda msg: self._toast("error", "插入图片失败", msg), thread,
                ),
                w.finished.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_pages_copied(self, done: list, errors: list) -> None:
        """后台复制完成后：把成功对插入清单、保存并刷新（主线程）。"""
        if not self.task_id or not done:
            if errors:
                self._toast("error", "插入图片失败", errors[0][1])
            return
        viewer = self._active_page_viewer()
        row = viewer.strip.currentRow()
        anchor = self._viewer_index_to_manifest_index(viewer, row)
        insert_at = anchor + 1 if anchor >= 0 else len(self.pages)
        for _source, target in done:
            target_path = Path(target)
            self.pages.insert(
                insert_at, {"file": target, "label": target_path.stem}
            )
            insert_at += 1
        self.store.save_pages(self.task_id, self.pages)
        note = f"已插入 {len(done)} 张图片。"
        if errors:
            note += f"（{len(errors)} 张失败：{errors[0][1]}）"
            self._toast("warning", "部分图片插入失败", errors[0][1])
        self.log_view.append(note)
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
