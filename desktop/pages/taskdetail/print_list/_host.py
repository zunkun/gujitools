# -*- coding: utf-8 -*-
"""``PrintListMixin`` 拆分后的宿主成员面——仅供类型检查，运行期从不加载。

拆分后每个 Mixin 都是独立类，类型检查器看不到兄弟 Mixin / 宿主页面上的
成员。这里集中声明一次，各 Mixin 在**类型检查期**以 ``PrintListHost`` 为
基类继承进来，运行期退化成 ``object``（MRO 与行为零改动）。
"""

from __future__ import annotations

from typing import Any, Callable


class PrintListHost:
    """宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法面。"""

    store: Any
    task_id: str | None
    print_preview: Any
    log_view: Any
    _toast: Any
    run_worker: Any
    print_source_dir: Any
    imposition_effective: Any
    node_of_stage: Any
    current_stage: Any
    current_node: Any
    _node_scope: Any
    _stage_input_visible: Any
    _on_print_page_edited: Any
    _on_print_delete_requested: Any
    _on_print_export_requested: Any
    _on_print_download_requested: Any
    _print_doc_snapshot: Any
    _print_thumb_paths: Any
    _print_warm_pending: list[str]
    _print_thumb_warmed: Any
    _logged_stale_rects: Any
    _download_busy: bool
    _export_target: Any
