# -*- coding: utf-8 -*-
"""``ImpositionBaseMixin`` 的**成员面声明**——只在类型检查期参与继承。

拆分后每个分片都是独立类，类型检查器看不到兄弟分片 / 宿主页面上的成员。
这里把「宿主 + 兄弟分片」的成员集中声明一次（类级注解、无赋值），各分片在
类型检查期以它为基类，运行期退化成 ``object``（MRO 与行为零改动）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from PySide6.QtWidgets import QStackedWidget, QWidget
    from desktop.components.detect_stats import DetectStatsWidget
    from desktop.components.step_bar import StepBar
    from desktop.store.store import TaskStore


class ImpositionBaseHost:
    """拼版共享基元的成员面：宿主 TaskDetailPage + 各分片提供的方法。"""

    # 宿主 TaskDetailPage 提供的属性/方法
    store: TaskStore
    task_id: str | None
    step_bar: StepBar
    control_stack: QStackedWidget
    preview_stack: QStackedWidget
    action_row: QWidget
    detect_stats: DetectStatsWidget
    history_block: QWidget
    bar_index_of_step: Callable[[str], int | None]
    node_of_stage: Callable[[str], str | None]
    #: 「去底色成品目录是否已提交」闸门（PrintListMixin 提供，见 print_list）
    rembg_source_committed: Callable[..., bool]
    #: 步骤条**格序** → 该格对应的**节点实例 id**（B 方案：逐节点刷状态用）
    node_at_index: Callable[[int], str | None]
    _node_scope: Callable[..., dict]
    _stage_primary: dict[str, str | None]
    step_at_index: Callable[[int], str | None]
    _rembg_step_index: Callable[[], int]
    _select_stage: Callable[[int], None]
    _set_stage_status: Callable[..., None]
    _apply_control_width: Callable[[], None]
    _refresh_stage_views: Callable[[], None]
    _refresh_stale_notices: Callable[[], None]
    _load_imposition_enabled: Callable[[], bool]
    _save_imposition_enabled: Callable[[bool], None]
    _schedule_imposition_compose: Callable[[], None]
    _refresh_imposition_page_thumbs: Callable[..., None]
    _drop_imposition_source_thumb: Callable[[str], None]
    _update_imposition_status: Callable[[int], None]
    close_imposition_zoom_popup: Callable[[], None]
    _current_print_pdf_path: Callable[[], Any]
    #: 右下方「下载 PDF」行的显隐同步（DetailViewMixin 提供，见 view）
    _sync_download_print_button: Callable[..., None]
    _print_entries: Callable[[], tuple]
    # ⚠️ 返回值是 LazyPanelHost 或真面板（属性转发、鸭子类型），用 Any 承接
    panel_host_of_step: Callable[[str], Any]
    stack_index_of_step: Callable[[str], int | None]
    imposition_enabled_checkbox: Any
    imposition_view: Any
    print_preview: Any
    _page_thumb_mgr: Any

    # 各分片之间互相调用的方法
    _imposition_node_visible: Callable[[], bool]
    _imposition_switch_state: Callable[[], tuple[bool, str]]
    imposition_effective: Callable[[], bool]
    _sync_imposition_step_bar: Callable[[], None]
    _sync_imposition_nodes: Callable[[], None]
    _imposition_has_pages_of: Callable[[str | None], bool]
    _sync_imposition_switch: Callable[..., None]
    _refresh_imposition_node: Callable[[], None]
    _imposition_doc: Callable[[], dict]
    _imposition_pages: Callable[..., list[dict]]
    _save_imposition_pages: Callable[[list[dict]], None]
    _set_imposition_checked: Callable[[bool], None]
    _imposition_scope: Callable[[], dict]
    _imposition_flag_scope: Callable[[], dict]
    _imposition_output_dir: Callable[[], Any]
    imposition_source_files: Callable[[], list]
    _upstream_detect_node: Callable[[], str | None]
    imposition_role_map: Callable[[], dict[str, str]]
    imposition_active: Callable[[], bool]
    imposition_has_pages: Callable[[], bool]
    print_source_dir: Callable[[], Any]
    _refresh_imposition_view: Callable[[], None]
    _select_imposition_detail: Callable[[], None]
    _reset_imposition_state: Callable[[], None]
    _print_source_mark: Callable[[], tuple]
    _print_source_mark_text: Callable[[], str]
    _refresh_print_source: Callable[..., None]

    # 各分片读写的状态属性
    _print_source_cache: Any
