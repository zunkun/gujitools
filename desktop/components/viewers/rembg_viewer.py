# -*- coding: utf-8 -*-
"""去底色预览：单视图显示，去底色结果优先，顶部用分段开关切换原图。

左侧缩略图条按"输出条目"组织：
- area=1：每个文本框一条（标签 <页>-l / <页>-r），右侧显示该框 + border 区域；
- area=2/3：每页一条，右侧显示按 crop/cropremove 规则合成的效果区域。

区域合成在 worker 线程完成，不生成文件；通过请求令牌避免快速切换串台。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel

from desktop.workers import ImageListWorker, PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from core.command_spec import WHOLE_PAGE_AREA
from desktop.ui.widgets import SegmentedToggle
from utils.sort_utils import pdf_custom_sort_key


def _union_box(valid: list) -> list:
    """多个框的外接矩形（整页模式下把用户画的多个框合成一个整体）。"""
    return [
        min(b[0] for b in valid), min(b[1] for b in valid),
        max(b[2] for b in valid), max(b[3] for b in valid),
    ]


class RembgPreviewWidget(QWidget, ThumbsMixin):
    """去底色预览：左侧输出条目列表 + 右侧单视图（去底色结果 / 原图切换）。"""

    current_changed = Signal(int, str)

    def __init__(self, empty_hint: str = "暂无图片", parent=None):
        """构建缩略图条与「去底色结果 / 原图」切换行，默认显示去底色结果。"""
        super().__init__(parent)
        self._init_thumbs()
        self._paths: list[Path] = []
        self._entries: list[dict] = []  # [{label, path, box}]; box=None 表示整页规则
        self._rembg_dir: Path | None = None
        # 实时预览暂存目录（第三步改参数后按**当前页**现算的结果）。查找时优先于
        # _rembg_dir：它才是"此刻参数下"的样子，而正式产物可能已经过期。
        self._live_dir: Path | None = None
        self._boxes_provider = None  # (path_text) -> list[检测框]
        self._region_params_provider = None  # () -> (area, border)
        self._thumb_provider = None  # (path_text) -> Path | None
        self._mode = "result"  # result / original
        self._load_token = None  # 请求令牌：仅最新一次加载生效
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        left_col = QVBoxLayout()
        self.strip = ThumbStrip()
        self.strip.current_path_changed.connect(self._select_image)
        left_col.addWidget(self.strip, 1)
        layout.addLayout(left_col)

        right = QVBoxLayout()
        toggle_row = QHBoxLayout()
        self.toggle = SegmentedToggle(
            [("result", "去底色结果"), ("original", "原图")]
        )
        self.toggle.current_changed.connect(self._set_mode)
        toggle_row.addWidget(self.toggle)
        toggle_row.addStretch()
        right.addLayout(toggle_row)
        self.toggle_caption = CaptionLabel("")
        right.addWidget(self.toggle_caption)
        self.view = ImageView(empty_hint)
        right.addWidget(self.view, 1)
        layout.addLayout(right, 1)
        self._sync_toggle(False)

    # ------------------------------------------------------------------ API
    def set_images(
        self,
        paths: list[Path],
        rembg_dir: Path | None,
        boxes_provider=None,
        region_params_provider=None,
        thumb_provider=None,
    ) -> None:
        """设置图片清单与去底色目录，重建输出条目并加载显示。

        paths 为源图；rembg_dir 为去底色结果目录（存在才显示结果）；
        各 provider 给出检测框 / 区域参数 / 缩略图来源。清单变化时重建
        缩略图条，否则按最新区域重加载当前显示。
        """
        self._boxes_provider = boxes_provider  # (path_text) -> list[检测框]
        self._region_params_provider = region_params_provider  # () -> (area, border)
        self._border_mm = None
        self._thumb_provider = thumb_provider
        self._rembg_dir = rembg_dir
        paths_changed = list(paths) != self._paths
        self._paths = list(paths)
        self._rebuild_entries(force_strip=paths_changed)
        if not self._entries:
            self.view.clear_image("暂无图片")
            self.toggle_caption.setText("")
            return
        if paths_changed or self.strip.currentRow() < 0:
            self._select_entry(0)
        else:
            self._load_display()  # 检测框/参数可能已更新，按最新区域重载

    def refresh_display(self) -> None:
        """detect 框/area/border 变化后，重建输出条目并按新区域重新加载。"""
        self._rebuild_entries()
        self._load_display()

    def set_live_dir(self, path: Path | None) -> None:
        """设置（或传 None 清除）「实时预览」暂存目录。

        非 None 时结果图优先从这里取：它是按**此刻**面板参数现算的当前页；
        而 ``_rembg_dir``（stages/rembgpreview）是上一次「生成预览」的全量产物，
        参数可能已经改过。
        """
        self._live_dir = Path(path) if path else None

    @property
    def live_dir(self) -> Path | None:
        """当前生效的实时预览暂存目录（未启用为 None）。"""
        return self._live_dir

    def current_entry_path(self) -> str | None:
        """当前选中条目的源图路径（无条目时为 None）。"""
        entry = self._current_entry()
        return entry["path"] if entry else None

    def show_live_pending(self) -> None:
        """实时预览正在计算：先给个即时反馈，别让界面看起来没反应。"""
        self.view.clear_image("正在按新参数去底色…")

    # ------------------------------------------------------------------ 条目
    def _build_entries(self) -> list[dict]:
        """manifest 路径 → 输出条目。

        area=1 时每框一条（左右身份来自存储的 [左框, 右框] 列表，缺失为 null）；
        全部条目最终按 CLI 规范（utils/sort_utils.pdf_custom_sort_key）排序：
        同页编号 r 在 l 前，页码数字感知排序。
        """
        entries: list[dict] = []
        for path in self._paths:
            path_text = str(path)
            stem = path.stem
            page_entries = None
            if self._boxes_provider and self._region_params_provider:
                try:
                    boxes = self._boxes_provider(path_text) or []
                    area, _border = self._region_params_provider()
                    valid = [b for b in boxes if b]
                    if area == 1 and len(valid) == 2:
                        # 右框在前（古籍阅读顺序：r → l）
                        page_entries = [
                            {"label": f"{stem}-r", "path": path_text,
                             "box": valid[1], "boxes": [valid[1]], "parea": 1},
                            {"label": f"{stem}-l", "path": path_text,
                             "box": valid[0], "boxes": [valid[0]], "parea": 1},
                        ]
                    elif area == 1 and len(valid) == 1:
                        page_entries = [
                            {"label": f"{stem}", "path": path_text, "box": valid[0], "parea": 1}
                        ]
                    elif area in (2, 3) and len(valid) == 2:
                        union = [min(b[0] for b in valid), min(b[1] for b in valid),
                                 max(b[2] for b in valid), max(b[3] for b in valid)]
                        # ⚠️ parea 必须是**原始 area**、boxes 必须是**原始框**：
                        # 只给并集框 + area=1 会在 border 为空时把整页画布
                        # （area=2/3 的语义）退化成紧裁，与预览不一致。
                        page_entries = [
                            {"label": stem, "path": path_text, "box": union,
                             "boxes": list(valid), "parea": area}
                        ]
                    elif area in (2, 3) and len(valid) == 1:
                        # 对称画布
                        page_entries = [
                            {"label": stem, "path": path_text, "box": valid[0],
                             "boxes": list(valid), "parea": area}
                        ]
                    elif area == WHOLE_PAGE_AREA and valid:
                        # 整页模式：整页（或用户手画的框）作为一个整体，不拆左右页
                        page_entries = [
                            {"label": stem, "path": path_text,
                             "box": _union_box(valid), "boxes": list(valid),
                             "parea": area}
                        ]
                except Exception:
                    page_entries = None
            if not page_entries:
                page_entries = [{"label": stem, "path": path_text, "box": None}]
            entries.extend(page_entries)
        entries.sort(key=lambda e: pdf_custom_sort_key(e["label"]))
        return entries

    def _rebuild_entries(self, force_strip: bool = False) -> None:
        entries = self._build_entries()
        # 标题 = 排序后的序号（1,2,3…）；原 label 保留用于选中恢复
        for index, entry in enumerate(entries):
            entry["title"] = str(index + 1)
        keep_label = None
        current = self._current_entry()
        if current:
            keep_label = current.get("label")
        labels_changed = [e["label"] for e in entries] != [
            e["label"] for e in self._entries
        ]
        self._entries = entries
        if not (labels_changed or force_strip):
            return
        self.strip.clear()
        if not entries:
            self.strip.add_placeholder("暂无图片")
            return
        for entry in entries:
            self.strip.add_page_item(entry["title"], entry["path"])
        self._load_page_thumbs(entries)
        # 尽量保持原选中条目（按原始 label 匹配）
        if keep_label:
            for row in range(self.strip.count()):
                if self._entries[row].get("label") == keep_label:
                    self.strip.setCurrentRow(row)
                    break

    def _load_page_thumbs(self, entries: list[dict]) -> None:
        """加载各条目缩略图：按检测框 + area/border 合成，只显示所属部分。

        条目缩略图不是整页缩略图——area=1 时要显示"该条目那半页"，
        所以这里必须把 ``_page_thumb_for`` 返回的 ``effect`` 交给
        ``ImageListWorker`` 走 ``compose_region_output`` 合成，而不是
        传像素裁剪框 ``crops``（那会整页原样显示）。

        合成后的图按"覆盖填充"放大到条目图标尺寸并居中裁切，
        保证占满整个图标宽度（避免半幅图旁边留白）。
        """
        thumb_paths = []
        effects = []
        labels = []
        border_mm = None
        if self._region_params_provider:
            try:
                _, border_mm = self._region_params_provider()
            except Exception:
                border_mm = None
        for entry in entries:
            real = entry["path"]
            spec = None
            if self._thumb_provider:
                spec = self._thumb_provider(
                    real, entry.get("box"), entry.get("parea", 1), border_mm,
                    boxes=entry.get("boxes"),
                )
            if isinstance(spec, dict):
                thumb_paths.append(Path(spec["path"]))
                effects.append(spec.get("effect"))
            elif spec:
                thumb_paths.append(Path(spec))
                effects.append(None)
            else:
                thumb_paths.append(Path(real))
                effects.append(None)
            labels.append(entry["title"])
        self._load_thumbs_chunked(
            len(thumb_paths),
            make_worker=lambda start, end: ImageListWorker(
                thumb_paths[start:end],
                edge=ThumbStrip.DECODE_EDGE,
                effects=effects[start:end],
            ),
            sink=lambda index, image, _path: self.strip.set_item_icon(
                index, self._fill_icon(image), "", labels[index]
            ),
        )

    @staticmethod
    def _fill_icon(image: QImage) -> QImage:
        """覆盖填充到条目图标尺寸：等比放大至铺满，再居中裁掉多余部分。"""
        target = ThumbStrip.ICON_SIZE
        if image.width() >= target.width() and image.height() >= target.height():
            scaled = image
        else:
            scale = max(
                target.width() / image.width(),
                target.height() / image.height(),
            )
            scaled = image.scaled(
                round(image.width() * scale),
                round(image.height() * scale),
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )
        x = (scaled.width() - target.width()) // 2
        y = (scaled.height() - target.height()) // 2
        return scaled.copy(max(x, 0), max(y, 0), target.width(), target.height())

    def _current_entry(self) -> dict | None:
        row = self.strip.currentRow()
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return self._entries[0] if self._entries else None

    # ------------------------------------------------------------------ 加载
    def _select_image(self, index: int, _path: str) -> None:
        if not self._entries or index >= len(self._entries):
            return
        self.strip.setCurrentRow(index)
        self._load_display()
        self.current_changed.emit(index, self._entries[index]["path"])

    def _select_entry(self, index: int) -> None:
        if not self._entries or index >= len(self._entries):
            return
        self.strip.setCurrentRow(index)
        self._load_display()

    def _set_mode(self, mode: str) -> None:
        """用户切换显示形态（分段开关回调，仅在点击时到达）。"""
        if self._mode != mode:
            self._mode = mode
            self._load_display()

    def _result_full_image(self) -> Path | None:
        """当前页的去底色结果图：**实时暂存优先**，其次「生成预览」的正式产物。"""
        entry = self._current_entry()
        if not entry:
            return None
        stem = Path(entry["path"]).stem
        for base in (self._live_dir, self._rembg_dir):
            if not base:
                continue
            for ext in ("png", "jpg", "jpeg"):
                candidate = base / f"{stem}.{ext}"
                if candidate.exists():
                    return candidate
        return None

    def _load_display(self) -> None:
        entry = self._current_entry()
        if not entry:
            self.view.clear_image("暂无图片")
            return
        path_text = entry["path"]
        effect = None
        if self._boxes_provider and self._region_params_provider:
            try:
                area, border = self._region_params_provider()
                if entry.get("box") is not None and area == 1:
                    # area=1 单框条目：显示"该文本框 + border"区域
                    effect = {"boxes": [entry["box"]], "area": 1, "border": border}
                else:
                    effect = {
                        "boxes": self._boxes_provider(path_text) or [],
                        "area": area,
                        "border": border,
                    }
            except Exception as exc:  # 参数计算失败时退化为整图显示
                self.view.clear_image(f"区域计算失败：{exc}")
                return
        result_img = self._result_full_image()
        show_result = self._mode == "result" and result_img is not None
        source = result_img if show_result else Path(path_text)
        if not source.exists():
            self.view.clear_image("暂无图片")
            return
        self.view.clear_image("正在加载...")
        self.toggle_caption.setText(
            "去底色结果 · 显示范围为步骤二的检测框与「区域模式 / 边距」"
            if show_result
            else ("原图（尚未生成去底色结果）" if not result_img else "原图")
        )
        self._sync_toggle(result_img is not None)
        token = self._load_token = object()
        self.run_worker(
            lambda: PreviewWorker(source, longest_edge=1600, effect=effect),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda _p, image, _s, t=token: self._display(t, image),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg, t=token: self._load_failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _load_failed(self, token, msg: str) -> None:
        if token is not self._load_token:
            return
        self.view.clear_image(f"加载失败：{msg}")

    def _display(self, token, image) -> None:
        if token is not self._load_token:
            return
        self.view.set_image(image, image_size=image.size())

    def _sync_toggle(self, has_result: bool) -> None:
        """刷新分段开关：无去底色结果时禁用「去底色结果」项并停在「原图」。

        ``_mode`` 只记用户偏好，不因缺少结果被改写——所以结果一生成，
        开关会自动回到用户原来选的那一项。
        """
        self.toggle.set_item_enabled("result", has_result)
        self.toggle.set_current(
            self._mode if (self._mode == "original" or has_result) else "original"
        )
