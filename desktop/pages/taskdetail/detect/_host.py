# -*- coding: utf-8 -*-
"""``DetectMixin`` 拆分后的宿主成员面——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，类型检查器看不到兄弟 Mixin / 宿主页面上的
成员。这里集中声明一次，各 Mixin 在**类型检查期**以 ``DetectHost`` 为基类
继承进来，运行期退化成 ``object``（MRO 与行为零改动）。
"""

from __future__ import annotations

from typing import Any


class DetectHost:
    """宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法面。"""

    store: Any
    task_id: str | None
    source_path: Any
    detect_cache: dict[str, Any]
    detect_process: Any
    detect_viewer: Any
    rembg_viewer: Any
    yolo_export_card: Any
    yolo_export_button: Any
    log_view: Any
    detect_stats: Any
    step_bar: Any
    running_stage: Any
    _toast: Any
    _acquire_run: Any
    _release_run: Any
    _mark_run_launched: Any
    _read_worker_error: Any
    _worker_env: Any
    _manifest_paths: Any
    _stage_input_visible: Any
    _refresh_stats_now: Any
    current_stage: Any
    current_node: Any
    node_of_stage: Any
    _node_scope: Any
    _size_node_for: Any
    _scope_of: Any
    imposition_effective: Any
    window: Any
    sender: Any
    panel_host_of_step: Any
    _half_width_median: Any
    _manual_stems: Any
    _page_width_cache: Any
    _detect_prev_path: Any
    _inherit_done: Any
    _detect_out_buffer: str
    _boxes_map_cache: Any
    _detect_boxes_editable: bool
    _yolo_kernel: Any
    _yolo_summary: dict
