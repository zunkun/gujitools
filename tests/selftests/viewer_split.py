# -*- coding: utf-8 -*-
"""``viewer`` 四个查看器拆成**子包**后的不变量守卫（2026-10-07）。

``desktop/components/viewers/`` 下四个大文件按**职责**拆成子包：

```text
image_view/       666 行 → styles / render(RenderMixin) / edit(EditMixin) / core
image_viewer/     781 行 → thumbs / pdf / boxes + core
rembg_viewer/     625 行 → entries / thumbs + core
print_preview/    904 行 → thumbs / layout / export + widget
```

（``image_editor`` 与 ``image_zoom_dialog`` 另有各自的守卫。）

拆分前提是「**只挪位置，不改行为**」，而 Mixin 靠 ``self._xxx`` 共享状态——
挪错一个方法不会报错，只会让某个功能悄悄失效（例如把 ``_rerender`` 挪进
EditMixin 就与 RenderMixin 同名、被 MRO 静默遮蔽）。这里对**每个**子包钉住：

1. **子包结构真的存在**，且旧的单文件已删（防止"两份实现"漂移）；
2. **成员归属**：每个成员仍在拆分时指定的那个类里（改落点必须同步改
   ``home``——让"挪动"变成一次显式决定）；
3. **无同名成员**：本包内的类之间不许重名（重名 = MRO 静默遮蔽 = 改了行为）；
4. **跨 Mixin 依赖在白名单内**：Mixin 调别的 Mixin 是允许的（正是 Mixin 的
   用法），但得是登记过的——新增没登记的隐式契约说明边界被捅穿；
5. **对外 API 不变**：外部（生产代码 + 测试）从包名导入的名字照旧可导入；
6. **运行时装配完整**：类真能看到全部成员（MRO 装配没漏），且模块级函数
   （如 ``rembg_viewer._union_box``）仍在包命名空间里。
"""

import ast
from pathlib import Path

NAME = "viewer_split"
DEPENDS: list[str] = []
TITLE = "查看器拆分（image_view / image_viewer / rembg_viewer / print_preview 子包）"

_VIEWERS = (
    Path(__file__).resolve().parents[2] / "desktop" / "components" / "viewers"
)

#: 四个子包的拆分事实（每个 :func:`_check` 一遍）。
_SPECS: list[dict] = [
    {
        "pkg": "image_view",
        "host": "ImageViewHost",
        "host_bases": ["QLabel"],
        "main": "ImageView",
        "modules": [
            ("core.py", "ImageView"),
            ("render.py", "RenderMixin"),
            ("edit.py", "EditMixin"),
        ],
        "public_api": [
            "BOX_COLORS", "BOX_NAMES", "FULL_BOX_COLOR", "FULL_BOX_NAME",
            "FULL_INDEX", "HANDLE_RADIUS", "ImageView", "REFERENCE_COLOR",
            "SIDE_INDEX", "box_names", "box_styles",
        ],
        "module_funcs": [],
        "home": {
            # core.py -> ImageView（22 个）
            "MAX_PREVIEW_EDGE": "ImageView",
            "MIN_PREVIEW_EDGE": "ImageView",
            "__init__": "ImageView",
            "_select": "ImageView",
            "_update_mapping": "ImageView",
            "box_kinds": "ImageView",
            "boxes_edited": "ImageView",
            "clear_image": "ImageView",
            "context_menu_requested": "ImageView",
            "double_clicked": "ImageView",
            "edit_rejected": "ImageView",
            "full_mode": "ImageView",
            "has_image": "ImageView",
            "max_boxes": "ImageView",
            "preview_edge": "ImageView",
            "select_box": "ImageView",
            "selected_index": "ImageView",
            "selection_changed": "ImageView",
            "set_boxes": "ImageView",
            "set_boxes_editable": "ImageView",
            "set_image": "ImageView",
            "set_reference_boxes": "ImageView",
            # render.py -> RenderMixin（6 个）
            "_draw_boxes": "RenderMixin",
            "_draw_reference_boxes": "RenderMixin",
            "_pen_width": "RenderMixin",
            "_rerender": "RenderMixin",
            "event": "RenderMixin",
            "resizeEvent": "RenderMixin",
            # edit.py -> EditMixin（13 个）
            "_commit_edit": "EditMixin",
            "_handle_rects": "EditMixin",
            "_hit_box": "EditMixin",
            "_hit_handle": "EditMixin",
            "_limit_message": "EditMixin",
            "_normalize": "EditMixin",
            "_to_image_coords": "EditMixin",
            "contextMenuEvent": "EditMixin",
            "keyPressEvent": "EditMixin",
            "mouseDoubleClickEvent": "EditMixin",
            "mouseMoveEvent": "EditMixin",
            "mousePressEvent": "EditMixin",
            "mouseReleaseEvent": "EditMixin",
        },
        "cross": {
            "ImageView": ["_rerender"],
            "RenderMixin": ["_handle_rects", "_update_mapping"],
            "EditMixin": [
                "_rerender", "_select", "boxes_edited",
                "context_menu_requested", "double_clicked", "edit_rejected",
                "max_boxes",
            ],
        },
    },
    {
        "pkg": "image_viewer",
        "host": "ImageViewerHost",
        "host_bases": ["QWidget", "ThumbsMixin", "ZoomPopupMixin"],
        "main": "ImageViewerWidget",
        "modules": [
            ("core.py", "ImageViewerWidget"),
            ("thumbs.py", "ThumbsCacheMixin"),
            ("pdf.py", "PdfSourceMixin"),
            ("boxes.py", "BoxesMixin"),
        ],
        "public_api": ["ImageViewerWidget"],
        "module_funcs": [],
        "home": {
            # core.py -> ImageViewerWidget（28 个）
            "__init__": "ImageViewerWidget",
            "_image_ready": "ImageViewerWidget",
            "_image_ready_if_current": "ImageViewerWidget",
            "_load_failed_if_current": "ImageViewerWidget",
            "_load_thumbs": "ImageViewerWidget",
            "_on_zoom_image_saved": "ImageViewerWidget",
            "_original_size": "ImageViewerWidget",
            "_select_image": "ImageViewerWidget",
            "_thumb_for": "ImageViewerWidget",
            "_zoom_index": "ImageViewerWidget",
            "_zoom_target": "ImageViewerWidget",
            "apply_edited_image": "ImageViewerWidget",
            "box_edit_rejected": "ImageViewerWidget",
            "boxes_edited": "ImageViewerWidget",
            "current_changed": "ImageViewerWidget",
            "current_path": "ImageViewerWidget",
            "delete_requested": "ImageViewerWidget",
            "image_saved": "ImageViewerWidget",
            "insert_folder_requested": "ImageViewerWidget",
            "insert_requested": "ImageViewerWidget",
            "navigate": "ImageViewerWidget",
            "paths": "ImageViewerWidget",
            "refresh_page": "ImageViewerWidget",
            "reload_thumb": "ImageViewerWidget",
            "selection_changed": "ImageViewerWidget",
            "set_empty_hint": "ImageViewerWidget",
            "set_images": "ImageViewerWidget",
            "set_insert_visible": "ImageViewerWidget",
            # thumbs.py -> ThumbsCacheMixin（5 个）
            "_lookup_thumb_path": "ThumbsCacheMixin",
            "_on_thumb_cached": "ThumbsCacheMixin",
            "_start_thumb_cache": "ThumbsCacheMixin",
            "_thumb_cache_target": "ThumbsCacheMixin",
            "set_thumb_source": "ThumbsCacheMixin",
            # pdf.py -> PdfSourceMixin（7 个）
            "_clear_page_source": "PdfSourceMixin",
            "_pdf_page_failed": "PdfSourceMixin",
            "_pdf_page_ready": "PdfSourceMixin",
            "_select_pdf_page": "PdfSourceMixin",
            "begin_pdf_pages": "PdfSourceMixin",
            "set_pdf_source": "PdfSourceMixin",
            "set_pdf_thumb": "PdfSourceMixin",
            # boxes.py -> BoxesMixin（7 个）
            "_boxes_edited": "BoxesMixin",
            "apply_boxes": "BoxesMixin",
            "box_full_mode": "BoxesMixin",
            "box_kinds": "BoxesMixin",
            "select_box": "BoxesMixin",
            "selected_index": "BoxesMixin",
            "set_reference_boxes": "BoxesMixin",
        },
        "cross": {
            "ImageViewerWidget": [
                "_boxes_edited", "_clear_page_source", "_select_pdf_page",
            ],
            "ThumbsCacheMixin": ["set_images"],
            "PdfSourceMixin": ["current_changed"],
            "BoxesMixin": ["boxes_edited", "current_path"],
        },
    },
    {
        "pkg": "rembg_viewer",
        "host": "RembgViewerHost",
        "host_bases": ["QWidget", "ThumbsMixin", "ZoomPopupMixin"],
        "main": "RembgPreviewWidget",
        "modules": [
            ("core.py", "RembgPreviewWidget"),
            ("entries.py", "EntriesMixin"),
            ("thumbs.py", "ThumbsCacheMixin"),
        ],
        "public_api": ["RembgPreviewWidget", "_union_box"],
        #: 模块级函数必须仍在**包**命名空间里（``rembg_viewer._union_box``）。
        "module_funcs": ["_union_box"],
        "home": {
            # core.py -> RembgPreviewWidget（22 个）
            "__init__": "RembgPreviewWidget",
            "_current_entry": "RembgPreviewWidget",
            "_display": "RembgPreviewWidget",
            "_load_display": "RembgPreviewWidget",
            "_load_failed": "RembgPreviewWidget",
            "_on_zoom_image_saved": "RembgPreviewWidget",
            "_select_entry": "RembgPreviewWidget",
            "_select_image": "RembgPreviewWidget",
            "_set_mode": "RembgPreviewWidget",
            "_sync_toggle": "RembgPreviewWidget",
            "_zoom_index": "RembgPreviewWidget",
            "_zoom_target": "RembgPreviewWidget",
            "current_changed": "RembgPreviewWidget",
            "current_entry_path": "RembgPreviewWidget",
            "image_saved": "RembgPreviewWidget",
            "live_dir": "RembgPreviewWidget",
            "navigate": "RembgPreviewWidget",
            "refresh_display": "RembgPreviewWidget",
            "refresh_page": "RembgPreviewWidget",
            "set_images": "RembgPreviewWidget",
            "set_live_dir": "RembgPreviewWidget",
            "show_live_pending": "RembgPreviewWidget",
            # entries.py -> EntriesMixin（5 个）
            "_build_entries": "EntriesMixin",
            "_fill_icon": "EntriesMixin",
            "_rebuild_entries": "EntriesMixin",
            "_resolve_source": "EntriesMixin",
            "_result_full_image": "EntriesMixin",
            # thumbs.py -> ThumbsCacheMixin（4 个）
            "_load_page_thumbs": "ThumbsCacheMixin",
            "reload_thumb": "ThumbsCacheMixin",
            "set_cached_thumb": "ThumbsCacheMixin",
            "set_cached_thumbs": "ThumbsCacheMixin",
        },
        "cross": {
            "RembgPreviewWidget": [
                "_load_page_thumbs", "_rebuild_entries", "_resolve_source",
                "_result_full_image",
            ],
            "EntriesMixin": ["_current_entry", "_load_page_thumbs"],
            "ThumbsCacheMixin": ["_fill_icon", "refresh_page"],
        },
    },
    {
        "pkg": "print_preview",
        "host": "PrintPreviewHost",
        "host_bases": ["QWidget", "ThumbsMixin", "ZoomPopupMixin"],
        "main": "PrintPreviewWidget",
        "modules": [
            ("widget.py", "PrintPreviewWidget"),
            ("thumbs.py", "PrintThumbsMixin"),
            ("layout.py", "PrintLayoutMixin"),
            ("export.py", "PrintExportMixin"),
        ],
        "public_api": ["PrintPreviewWidget"],
        "module_funcs": [],
        "home": {
            # widget.py -> PrintPreviewWidget（37 个）
            "EXPORT_IMAGE_DPI": "PrintPreviewWidget",
            "THUMB_EDGE": "PrintPreviewWidget",
            "_PAPER_TO_QPAGE": "PrintPreviewWidget",
            "__init__": "PrintPreviewWidget",
            "_build_toolbar": "PrintPreviewWidget",
            "_current_index": "PrintPreviewWidget",
            "_display": "PrintPreviewWidget",
            "_load_display": "PrintPreviewWidget",
            "_load_failed": "PrintPreviewWidget",
            "_on_zoom_image_saved": "PrintPreviewWidget",
            "_refresh_zoom_popup_if_open": "PrintPreviewWidget",
            "_select_entry": "PrintPreviewWidget",
            "_select_image": "PrintPreviewWidget",
            "_set_mode": "PrintPreviewWidget",
            "_stop_worker": "PrintPreviewWidget",
            "_sync_export_button": "PrintPreviewWidget",
            "_zoom_index": "PrintPreviewWidget",
            "_zoom_target": "PrintPreviewWidget",
            "count": "PrintPreviewWidget",
            "download_requested": "PrintPreviewWidget",
            "entries": "PrintPreviewWidget",
            "export_default_name": "PrintPreviewWidget",
            "export_failed": "PrintPreviewWidget",
            "export_finished": "PrintPreviewWidget",
            "export_image_requested": "PrintPreviewWidget",
            "hint": "PrintPreviewWidget",
            "image_saved": "PrintPreviewWidget",
            "insert_requested": "PrintPreviewWidget",
            "layout_changed": "PrintPreviewWidget",
            "navigate": "PrintPreviewWidget",
            "order_changed": "PrintPreviewWidget",
            "print_failed": "PrintPreviewWidget",
            "print_finished": "PrintPreviewWidget",
            "refresh_display": "PrintPreviewWidget",
            "remove_selected": "PrintPreviewWidget",
            "set_entries": "PrintPreviewWidget",
            "set_pdf_path": "PrintPreviewWidget",
            # thumbs.py -> PrintThumbsMixin（6 个）
            "_apply_page_thumb": "PrintThumbsMixin",
            "_emit_order_changed": "PrintThumbsMixin",
            "_load_page_thumbs": "PrintThumbsMixin",
            "_on_strip_order_changed": "PrintThumbsMixin",
            "_sync_cache_order": "PrintThumbsMixin",
            "_thumb_path_for": "PrintThumbsMixin",
            # layout.py -> PrintLayoutMixin（7 个）
            "_on_canvas_rect": "PrintLayoutMixin",
            "_page_size_mm": "PrintLayoutMixin",
            "_plan_for": "PrintLayoutMixin",
            "_print_spec": "PrintLayoutMixin",
            "_resolved_nodes": "PrintLayoutMixin",
            "_show_layout": "PrintLayoutMixin",
            "refresh_layout": "PrintLayoutMixin",
            # export.py -> PrintExportMixin（7 个）
            "_capture_print_image": "PrintExportMixin",
            "_export_edge": "PrintExportMixin",
            "_export_failed": "PrintExportMixin",
            "_print_current": "PrintExportMixin",
            "_render_current_effect_sync": "PrintExportMixin",
            "_write_export": "PrintExportMixin",
            "export_current_effect": "PrintExportMixin",
        },
        "cross": {
            "PrintPreviewWidget": [
                "_emit_order_changed", "_load_page_thumbs", "_on_canvas_rect",
                "_on_strip_order_changed", "_print_current", "_print_spec",
                "_show_layout", "_sync_cache_order", "refresh_layout",
            ],
            "PrintThumbsMixin": ["THUMB_EDGE", "order_changed"],
            "PrintLayoutMixin": ["_current_index", "layout_changed"],
            "PrintExportMixin": [
                "EXPORT_IMAGE_DPI", "_PAPER_TO_QPAGE", "_current_index",
                "_print_spec", "export_failed", "export_finished",
                "print_failed", "print_finished",
            ],
        },
    },
]


def _members(cls: ast.ClassDef) -> set[str]:
    """类体里的成员名（方法 + 类属性赋值）。"""
    out: set[str] = set()
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _load(spec: dict) -> dict[str, ast.ClassDef]:
    base = _VIEWERS / spec["pkg"]
    out: dict[str, ast.ClassDef] = {}
    for fname, cname in spec["modules"]:
        tree = ast.parse((base / fname).read_text(encoding="utf-8"))
        out[cname] = next(
            n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == cname
        )
    return out


def _check(spec: dict) -> None:
    from tests.selftests._context import ok

    pkg, main = spec["pkg"], spec["main"]
    base = _VIEWERS / pkg

    # ---- 1. 拆分是真的：子包与各模块都在，旧单文件已删 ----
    missing = [f for f, _ in spec["modules"] if not (base / f).is_file()]
    ok(f"{pkg}：已是子包，且各拆分模块都在（含 __init__.py）",
       not missing and (base / "__init__.py").is_file(), f"缺={missing}")

    ok(f"{pkg}：旧的单文件 {pkg}.py 已不存在（避免两份实现）",
       not (_VIEWERS / f"{pkg}.py").exists(), "旧文件又出现了")

    classes = _load(spec)
    home = spec["home"]

    # ---- 2. 成员归属 ----
    home_of: dict[str, str] = {}
    for cname, cls in classes.items():
        for name in _members(cls):
            home_of.setdefault(name, cname)

    # 元守卫：登记表不许空跑（拆分后成员数只会多不会少）
    ok(f"{pkg}：守卫登记了全部成员（不是空跑）",
       len(home) >= 20 and len(home_of) >= len(home),
       f"登记 {len(home)}、实际 {len(home_of)}")

    wrong = {
        n: (home[n], home_of.get(n))
        for n in home
        if home_of.get(n) != home[n]
    }
    ok(f"{pkg}：每个成员都停在拆分时指定的类里",
       not wrong, f"落点漂移={wrong}")

    lost = sorted(set(home) - set(home_of))
    ok(f"{pkg}：没有成员在拆分中丢失", not lost, f"丢失={lost}")

    # ---- 3. 本包内的类之间无同名成员（否则 MRO 静默遮蔽）----
    overlap: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for cname, cls in classes.items():
        for name in _members(cls):
            if name in seen:
                overlap.setdefault(name, [seen[name]]).append(cname)
            else:
                seen[name] = cname
    ok(f"{pkg}：包内各 Mixin 之间没有同名成员（否则 MRO 会静默遮蔽）",
       not overlap, f"重叠={overlap}")

    # ---- 4. 跨 Mixin 依赖在白名单内 ----
    allowed_map = spec["cross"]
    bad: dict[str, list[str]] = {}
    for cname, cls in classes.items():
        own = _members(cls)
        allowed = set(allowed_map.get(cname, []))
        others = set().union(*(
            _members(other) for name_, other in classes.items()
            if name_ != cname
        ))
        foreign: set[str] = set()
        for node in ast.walk(cls):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"):
                foreign.add(node.attr)
        unknown = sorted((foreign & others) - own - allowed)
        if unknown:
            bad[cname] = unknown
    ok(f"{pkg}：跨 Mixin 的方法调用全部登记在案",
       not bad, f"未登记的隐式契约={bad}")

    # ---- 5. 运行时：类能看到全部成员 + 对外 API 不变 ----
    import importlib

    mod = importlib.import_module(f"desktop.components.viewers.{pkg}")
    cls = getattr(mod, main)

    invisible = [n for n in home if not hasattr(cls, n)]
    ok(f"{pkg}：{main} 仍能看到全部成员（MRO 装配完整）",
       not invisible, f"看不到={invisible}")

    absent = [n for n in spec["public_api"] if not hasattr(mod, n)]
    ok(f"{pkg}：对外 API 名字照旧可导入（含模块属性打桩）",
       not absent, f"缺失={absent}")

    lost_funcs = [n for n in spec["module_funcs"] if not hasattr(mod, n)]
    ok(f"{pkg}：模块级函数仍在包命名空间里", not lost_funcs,
       f"缺失={lost_funcs}")


def run(ctx) -> None:
    from tests.selftests._context import check_type_only_host, ok

    # 元守卫：四个子包一个都不能漏（漏了 = 有子包没人守）
    ok("守卫覆盖了四个拆分子包",
       len(_SPECS) == 4 and {s["pkg"] for s in _SPECS} == {
           "image_view", "image_viewer", "rembg_viewer", "print_preview",
       }, str([s["pkg"] for s in _SPECS]))

    for spec in _SPECS:
        _check(spec)
        check_type_only_host(
            ok,
            label=spec["pkg"],
            root=_VIEWERS.parents[2],
            pkg_rel=f"desktop/components/viewers/{spec['pkg']}",
            host_file="_host.py",
            host_cls=spec["host"],
            main_file=spec["modules"][0][0],
            main_cls=spec["main"],
            mixin_modules=spec["modules"][1:],
            expected_bases=spec["host_bases"],
        )
