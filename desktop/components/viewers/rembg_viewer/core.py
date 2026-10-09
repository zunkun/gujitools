# -*- coding: utf-8 -*-
"""``RembgPreviewWidget``：**装配点 + 基座 + 展示主路径**。

从 ``rembg_viewer.py`` 拆出（2026-10-07）。本文件放类头（信号/类属性）、
``__init__``、源切换与当前页展示、宿主协议（``_zoom_*``）；条目构建与缩略图
缓存在兄弟模块的 Mixin 里。方法体逐字未改。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel
from desktop.workers import PreviewWorker, connect_queued
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin
from desktop.ui.widgets import SegmentedToggle

from .entries import EntriesMixin
from .thumbs import ThumbsCacheMixin


class RembgPreviewWidget(
    EntriesMixin,
    ThumbsCacheMixin,
    QWidget,
    ThumbsMixin,
    ZoomPopupMixin,
):
    """去底色预览：左侧输出条目列表 + 右侧单视图（去底色结果 / 原图切换）。"""

    current_changed = Signal(int, str)
    #: 编辑器在放大弹窗里覆盖了某个文件 ``image_saved(path, edited)``：
    #: 宿主据此刷新尺寸记录/缩略图/各处显示（真实文件才可能发出）
    image_saved = Signal(str, object)

    def __init__(
        self,
        empty_hint: str = "暂无图片",
        image_editable: bool = True,
        parent=None,
    ):
        """构建缩略图条与「去底色结果 / 原图」切换行，默认显示去底色结果。

        ``image_editable``：**是否可以编辑图片**（对外接口参数，2026-10-09
        用户）。False 时本控件只许预览——预览区右键不给「编辑图片」、放大
        弹窗不给「编辑」按钮（图片去底色阶段两处入口都传 False）。
        """
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
        #: 宿主渲好的**整页缓存小图**：真实图路径 → 缓存路径。优先级高于
        #: ``_thumb_provider``（见 :meth:`set_cached_thumbs`）。
        self._cached_thumbs: dict[str, str] = {}
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
        # 双击大图 → 图片预览弹窗（与主预览同一份区域规则，见 _resolve_source）
        self._init_zoom_popup(self.view, editable=image_editable)
        self._sync_toggle(False)


    # ------------------------------------------------------------------ API
    def set_images(
        self,
        paths: list[Path | str],
        rembg_dir: Path | None,
        boxes_provider=None,
        region_params_provider=None,
        thumb_provider=None,
    ) -> None:
        """设置图片清单与去底色目录，重建输出条目并加载显示。

        ``paths`` 为源图，元素允许是 ``str``（统一转 ``Path``，同
        :meth:`desktop.components.viewers.ImageViewerWidget.set_images`）；
        ``rembg_dir`` 为去底色结果目录（存在才显示结果）；
        各 provider 给出检测框 / 区域参数 / 缩略图来源。清单变化时重建
        缩略图条，否则按最新区域重加载当前显示。
        """
        self._boxes_provider = boxes_provider  # (path_text) -> list[检测框]
        self._region_params_provider = region_params_provider  # () -> (area, border)
        self._border_mm = None
        self._thumb_provider = thumb_provider
        self._rembg_dir = rembg_dir
        resolved = [Path(p) for p in paths]
        paths_changed = resolved != self._paths
        self._paths = resolved
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


    def navigate(self, forward: bool) -> None:
        """方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。"""
        self.strip.navigate(forward)


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
            self.close_zoom_popup()  # 弹窗里那页是切换前的形态
            self._load_display()


    def _load_display(self) -> None:
        entry = self._current_entry()
        if not entry:
            self.view.clear_image("暂无图片")
            return
        source, effect, has_result, error = self._resolve_source(entry)
        if source is None:
            self.view.clear_image(error)
            return
        show_result = self._mode == "result" and has_result
        self.view.clear_image("正在加载...")
        self.toggle_caption.setText(
            "去底色结果 · 显示范围为步骤二的检测框与「区域模式 / 边距」"
            if show_result
            else ("原图（尚未生成去底色结果）" if not has_result else "原图")
        )
        self._sync_toggle(has_result)
        token = self._load_token = object()
        # ⚠️ 渲染密度在 GUI 线程先算好（worker 线程不得碰 QWidget）
        edge = self.view.preview_edge()
        self.run_worker(
            lambda: PreviewWorker(source, longest_edge=edge, effect=effect),
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


    def refresh_page(self, path_text: str) -> None:
        """某文件被覆盖后刷新本查看器：受影响条目图标 + 当前大图。

        由宿主在缩略图重生成完毕后调用；路径与本查看器无关时是空操作。
        """
        rows = [
            i for i, entry in enumerate(self._entries)
            if entry["path"] == path_text
        ]
        entry = self._current_entry()
        if entry is not None and (
            entry["path"] == path_text
            or str(self._result_full_image(entry) or "") == str(
                Path(path_text)
            )
        ):
            self._load_display()  # 大图按新文件重载（异步、令牌保护）
        if rows:
            self._load_page_thumbs(
                [self._entries[i] for i in rows], rows=rows
            )


    # -------------------------------------------------------------- 图片预览
    def _zoom_index(self) -> int:
        """放大弹窗当前条目 = 缩略图条的当前行（条目与行号 1:1）。"""
        return max(self.strip.currentRow(), 0)


    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 条的图片预览来源；与主预览共用 :meth:`_resolve_source`。

        ``save_path`` 只在 ``effect is None``（显示内容就是这个文件的全部
        像素）时给：区域合成（area/border 裁一块、拼画布）是虚拟图，把它
        写回会把整张文件覆盖成一小块。

        ``edit_path`` 是**编辑要回写的真实文件**（用户 2026-10-01：编辑要串起
        各步、最终落到 PDF）：
        - 「原图」形态 → 源图文件（第一步产出）；
        - 「去底色结果」形态 → **正式**结果文件（``stages/rembgpreview``，
          提交后即喂给第四步）；
        - 显示的是**实时暂存**结果（参数已改、尚未「生成预览」）→ 不给编辑：
          写回临时文件会被下次实时预览覆盖、也不进提交产物。
        """
        if not (0 <= index < len(self._entries)):
            return None
        entry = self._entries[index]
        source, effect, _has_result, _error = self._resolve_source(entry)
        if source is None:
            return None
        source_path = Path(str(entry["path"]))
        edit_path = None
        if Path(source) == source_path:
            edit_path = source_path
        else:
            formal = self._result_full_image(entry, include_live=False)
            if formal is not None and Path(source) == formal:
                edit_path = formal
        return ZoomTarget(
            render=lambda edge: PreviewWorker(
                source, longest_edge=edge, effect=effect
            ),
            note=f"第 {index + 1}/{len(self._entries)} 条 · {source.name}",
            stem=source.stem,
            count=len(self._entries),
            save_path=source if effect is None else None,
            edit_path=edit_path,
        )


    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """弹窗里覆盖了文件：转发给宿主（同步尺寸/缩略图并刷新显示）。"""
        self.image_saved.emit(path_text, image)
