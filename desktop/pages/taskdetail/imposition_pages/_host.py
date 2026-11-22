# -*- coding: utf-8 -*-
"""``ImpositionPagesMixin`` 的**成员面声明**——只在类型检查期参与继承。

拆分后每个分片都是独立类，类型检查器看不到兄弟分片 / 宿主页面上的成员。
这里把「宿主 + 兄弟分片」的成员集中声明一次（类级注解、无赋值），各分片在
类型检查期以它为基类，运行期退化成 ``object``（MRO 与行为零改动）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from desktop.store.store import TaskStore


class ImpositionPagesHost:
    """拼版页管理控制器的成员面：宿主 TaskDetailPage + 各分片提供的方法。"""

    # 宿主 TaskDetailPage 提供的属性（store/task_id/log_view/run_worker/window）
    store: TaskStore
    task_id: str | None
    log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
    run_worker: Callable[..., Any]
    window: Callable[[], Any]
    imposition_view: Any
    _page_thumb_mgr: Any

    # 同级 Mixin（imposition.ImpositionBaseMixin）共享的基元
    _toast: Callable[..., None]
    _imposition_pages: Callable[[], list]
    _imposition_doc: Callable[[], dict[str, Any]]
    _imposition_scope: Callable[[], dict]
    _imposition_flag_scope: Callable[[], dict]
    _refresh_print_source: Callable[..., None]
    _save_imposition_pages: Callable[..., None]
    _schedule_imposition_compose: Callable[..., None]
    _set_imposition_checked: Callable[..., None]
    _sync_imposition_step_bar: Callable[..., None]
    _update_imposition_status: Callable[..., None]
    imposition_source_files: Callable[[], list]
    # 上游检测节点的提交计划（``{产物 label: role}``，同级 Mixin 提供）
    imposition_role_map: Callable[[], dict[str, str]]
    # 当前格的节点实例 id（页面宿主提供）：缩略图实体目录按它分节点
    node_of_stage: Callable[[str], str | None]
    # 候选图的预生成小图来源（同级 Mixin 提供）：入口图片/去底色成品小图与
    # 源 PDF 页缩略图，见 :meth:`_imposition_picker_thumb`。
    _print_thumb_provider: Callable[[str], Any]
    _page_thumb_for: Callable[..., Any]

    # 各分片之间互相调用的方法
    _load_imposition_enabled: Callable[[], bool]
    _save_imposition_enabled: Callable[[bool], None]
    _on_imposition_enabled_toggled: Callable[[bool], None]
    _imposition_picker_thumb: Callable[[str], Any]
    _imposition_insert_dir: Callable[[], Any]
    _imposition_candidate_pool: Callable[[dict], list]
    _resolve_chosen: Callable[[list[dict]], list]
    _on_imposition_add_requested: Callable[[], None]
    _pages_from_chosen: Callable[[list[dict]], tuple[list[dict], list]]
    _on_imposition_add_image: Callable[[], None]
    _on_imposition_page_selected: Callable[[int], None]
    _on_imposition_batch_delete: Callable[[], None]
    _on_imposition_page_reorder: Callable[[int, int], None]
    _on_imposition_page_move: Callable[[int, int], None]
    _on_imposition_page_insert: Callable[[int, str], None]
    _on_imposition_release_page: Callable[[int], None]
    _on_imposition_clear: Callable[[], None]
    _imposition_thumb_window: Callable[[], Any]
    _on_imposition_viewport_changed: Callable[[], None]
    _imposition_page_thumb_manager: Callable[[], Any]
    _on_imposition_page_thumb_ready: Callable[..., None]
    _refresh_imposition_page_thumbs: Callable[[list], None]
    _drop_imposition_source_thumb: Callable[[str], None]
