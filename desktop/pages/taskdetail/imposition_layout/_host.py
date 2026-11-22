# -*- coding: utf-8 -*-
"""``ImpositionLayoutMixin`` 的**成员面声明**——只在类型检查期参与继承。

拆分后每个分片都是独立类，类型检查器看不到兄弟分片 / 宿主页面上的成员。
这里把「宿主 + 兄弟分片」的成员集中声明一次（类级注解、无赋值），各分片在
类型检查期以它为基类，运行期退化成 ``object``（MRO 与行为零改动）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from desktop.store.store import TaskStore


class ImpositionLayoutHost:
    """拼版版面控制器的成员面：宿主 TaskDetailPage + 各分片提供的方法。"""

    # 宿主 TaskDetailPage 提供的属性（store/task_id/log_view/run_worker/window）
    store: TaskStore
    task_id: str | None
    log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
    run_worker: Callable[..., Any]
    window: Callable[[], Any]
    imposition_view: Any
    imposition_panel: Any
    imposition_panel_status: Any
    _page_thumb_mgr: Any

    # 同级 Mixin（imposition.ImpositionBaseMixin）共享的基元
    _toast: Callable[..., None]
    _imposition_pages: Callable[[], list]
    _imposition_doc: Callable[[], dict[str, Any]]
    _imposition_scope: Callable[[], dict]
    _imposition_output_dir: Callable[[], Any]
    _imposition_switch_state: Any  # 拼版启用开关控件
    _set_stage_status: Callable[..., None]
    _refresh_print_source: Callable[..., None]
    _save_imposition_pages: Callable[..., None]
    _on_page_image_saved: Callable[..., None]
    _imposition_page_thumb_manager: Callable[..., Any]
    _drop_imposition_source_thumb: Callable[[str], None]
    imposition_active: Callable[[], bool]
    imposition_effective: Callable[[], bool]
    imposition_has_pages: Callable[[], bool]

    # 各分片之间互相调用的方法
    _start_imposition_edit_commit: Callable[[], None]
    _sync_imposition_rotation_ui: Callable[[], None]
    _schedule_imposition_compose: Callable[[], None]
    _schedule_imposition_page_thumb: Callable[[int], None]
    _update_imposition_status: Callable[[int], None]
    _open_imposition_spread_preview: Callable[[], None]
    _imposition_locate_targets: Callable[[int], list]
    _imposition_spread_target: Callable[[int], Any]
    _on_imposition_source_edited: Callable[[str, Any], None]
    _on_imposition_spread_layout_saved: Callable[[int, list], None]
    _on_imposition_zoom_image_saved: Callable[..., None]
    _refresh_imposition_dirty_page_thumbs: Callable[[], None]
    _composed_sigs_path: Callable[[], Any]
    _composed_sigs: Callable[..., dict[int, str]]
    _stale_imposition_pages: Callable[[], list[int]]
    _defer_compose_for_thumbs: Callable[[], bool]
    _compose_imposition_async: Callable[..., None]
    _record_composed_pages: Callable[[], None]
    _imposition_products_fresh: Callable[[], bool]
    _compose_imposition_now: Callable[[], None]

    # 各分片读写的状态属性
    _imposition_dirty: bool
    _imposition_composing: bool
    _imposition_page_sigs: dict[int, str]
    _composed_sigs_cache: dict[str, dict[int, str]]
    _imposition_compose_doc: Any
    _imposition_compose_out_dir: Any
    _imposition_compose_sigs_path: Any
    _imposition_compose_doc_path: Any
    _imposition_compose_doc_mtime: Any
    _imposition_composed_pages: list[int]
    _imposition_compose_deferred_at: Any
    _imposition_timer: Any
    _imposition_edit_timer: Any
    _imposition_thumb_dirty: set[int]
    _imposition_thumb_timer: Any
    _imposition_zoom_dialog: Any
