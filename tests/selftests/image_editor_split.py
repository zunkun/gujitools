# -*- coding: utf-8 -*-
"""图片编辑器拆分的不变量守卫。

``desktop/components/viewers/image_editor.py``（4095 行）已拆成**子包**
（2026-10-07）：

```text
image_editor/
├── consts.py      常量           geometry.py  纯几何/变换数学
├── bake.py        后台线程       text_item.py 就地编辑文字块
├── canvas/        EditorCanvas（基座 + 工具交互 Mixin）
├── dialog.py      ImageEditorDialog（基座 + 收尾）+ 弹窗尺寸常量
└── dialog_*.py    弹窗的 4 个 Mixin：工具栏 / 选项页 / 撤销栈 / 工具提交
```

（2026-10-08 起画布拆分并按需扩展；早前的 PS 操控变形/变换笼/校正/微调
Mixin 已删除，GIMP 风格笔刷扭曲由独立 ``DistortionMixin`` 提供。）

拆分前提是「**只挪位置，不改行为**」，而 Mixin 靠 ``self._xxx`` 共享状态，
挪错一个方法不会报错、只会让某个工具悄悄失效。这里把四个不变量钉死：

1. **成员归属**：``EditorCanvas`` / ``ImageEditorDialog`` 的每个成员仍在拆分
   时指定的那个 Mixin 里（改落点必须同步改 ``_EXPECTED_HOME`` /
   ``_DIALOG_EXPECTED_HOME``——让"挪动"变成一次显式决定）；
2. **无同名成员**：Mixin 之间同名会被 MRO 静默遮蔽（排在前的赢）= 改了行为；
3. **跨 Mixin 依赖在白名单内**：Mixin 调别的 Mixin 的方法是允许的（正是
   Mixin 的用法），但**得是登记过的**——新增没登记的隐式契约说明边界被捅穿；
4. **对外 API 不变**：外部（生产代码 + 测试）从 ``image_editor`` 导入的名字
   必须照旧可导入，且 ``from ...image_editor import X`` 与模块属性打桩
   （``editor_mod.ImageEditorDialog = ...``）都还能用。
"""

import ast
from pathlib import Path

NAME = "image_editor_split"
DEPENDS: list[str] = []
TITLE = "图片编辑器拆分（画布 Mixin / 子包）"

_ROOT = Path(__file__).resolve().parents[2]
_PKG = _ROOT / "desktop" / "components" / "viewers" / "image_editor"
_CANVAS = _PKG / "canvas"

#: 拆分后的画布类（模块文件 → 类名）。顺序 = MRO 顺序。
_MODULES = [
    ("core.py", "EditorCanvas"),
    ("interaction.py", "InteractionMixin"),
    ("overlay.py", "OverlayMixin"),
    ("text.py", "TextMixin"),
    ("transform.py", "TransformMixin"),
    ("distortion.py", "DistortionMixin"),
]

#: 每个画布成员**应当**归属的类（成员名 → 类名）。
_EXPECTED_HOME = {
    "__init__": "EditorCanvas",
    "_sync_scene_rect": "EditorCanvas",
    "crop_committed": "EditorCanvas",
    "fit": "EditorCanvas",
    "fit_selection": "EditorCanvas",
    "image": "EditorCanvas",
    "image_rect": "EditorCanvas",
    "refresh": "EditorCanvas",
    "replace_image": "EditorCanvas",
    "reshape_finished": "EditorCanvas",
    "selection": "EditorCanvas",
    "set_eraser": "EditorCanvas",
    "set_fit_ratio": "EditorCanvas",
    "set_image": "EditorCanvas",
    "set_tool": "EditorCanvas",
    "set_zoom": "EditorCanvas",
    "stroke_started": "EditorCanvas",
    "text_requested": "EditorCanvas",
    "tool": "EditorCanvas",
    "transform_committed": "EditorCanvas",
    "zoom_in": "EditorCanvas",
    "zoom_out": "EditorCanvas",
    "_apply_hover_highlight": "InteractionMixin",
    "_erase_at": "InteractionMixin",
    "_hit_handle": "InteractionMixin",
    "_resize_rect": "InteractionMixin",
    "_sync_cursor": "InteractionMixin",
    "_update_hover_cursor": "InteractionMixin",
    "keyPressEvent": "InteractionMixin",
    "leaveEvent": "InteractionMixin",
    "mouseMoveEvent": "InteractionMixin",
    "mousePressEvent": "InteractionMixin",
    "mouseReleaseEvent": "InteractionMixin",
    "resizeEvent": "InteractionMixin",
    "wheelEvent": "InteractionMixin",
    "_build_overlay": "OverlayMixin",
    "_handle_boxes": "OverlayMixin",
    "_hide_eraser_ring": "OverlayMixin",
    "_move_eraser_ring": "OverlayMixin",
    "_sync_overlay": "OverlayMixin",
    "_hide_text_outline": "TextMixin",
    "_move_text_outline": "TextMixin",
    "_text_block_at": "TextMixin",
    "add_text_block": "TextMixin",
    "clear_text_blocks": "TextMixin",
    "focus_text_block": "TextMixin",
    "focused_text_block": "TextMixin",
    "style_target_block": "TextMixin",
    "text_blocks": "TextMixin",
    "_apply_shear": "TransformMixin",
    "_accumulate": "DistortionMixin",
    "_apply_distortion_segment": "DistortionMixin",
    "_begin_distortion_stroke": "DistortionMixin",
    "_clear_distortion_preview": "DistortionMixin",
    "_create_distortion_preview": "DistortionMixin",
    "_distort_preview_filter": "DistortionMixin",
    "_distort_segment": "DistortionMixin",
    "_finish_distortion_stroke": "DistortionMixin",
    "_render_distortion_field": "DistortionMixin",
    "_report_distortion_failure": "DistortionMixin",
    "_start_distortion_field": "DistortionMixin",
    "_upload_distortion_tiles": "DistortionMixin",
    "_queue_distortion_preview": "DistortionMixin",
    "_flush_distortion_preview": "DistortionMixin",
    "_on_distortion_preview_tick": "DistortionMixin",
    "set_distortion_options": "DistortionMixin",
    "_clear_transform_preview": "TransformMixin",
    "_ensure_transform_preview": "TransformMixin",
    "_hit_transform": "TransformMixin",
    "_sync_float": "TransformMixin",
    "_sync_transform_overlay": "TransformMixin",
    "_transform_quad": "TransformMixin",
    "reset_transform": "TransformMixin",
    "set_transform_about_pivot": "TransformMixin",
    "set_transform_reshape": "TransformMixin",
    "transform_move": "TransformMixin",
    "transform_pending": "TransformMixin",
    "transform_rotate": "TransformMixin",
    "transform_scale": "TransformMixin",
    "transform_shear": "TransformMixin",
}

#: Mixin 调用**别的 Mixin/基座**的成员 —— 登记的隐式契约。
_CROSS_METHOD_DEPS = {
    "EditorCanvas": {
        "_build_overlay",
        "_clear_distortion_preview", "_clear_transform_preview",
        "_finish_distortion_stroke",
        "_hide_eraser_ring", "_hide_text_outline",
        "_move_eraser_ring", "_sync_cursor",
        "_sync_overlay", "clear_text_blocks",
    },
    "InteractionMixin": {
        "_apply_shear",
        "_begin_distortion_stroke", "_distort_segment",
        "_finish_distortion_stroke",
        "_ensure_transform_preview",
        "_hide_eraser_ring",
        "_hide_text_outline", "_hit_transform",
        "_move_eraser_ring",
        "_move_text_outline",
        "_sync_float",
        "_sync_overlay",
        "_text_block_at", "crop_committed", "fit",
        "fit_selection", "image_rect", "refresh", "reshape_finished",
        "selection", "set_zoom", "stroke_started", "text_requested",
        "transform_committed",
    },
    "OverlayMixin": {
        "_apply_hover_highlight",
        "_sync_transform_overlay", "image_rect",
    },
    "TextMixin": set(),
    "TransformMixin": {
        "_sync_cursor", "_sync_overlay", "_sync_scene_rect",
        "image_rect", "refresh",
    },
    "DistortionMixin": {
        "_move_eraser_ring", "image_rect", "refresh", "stroke_started",
    },
}

#: 拆分后的**弹窗**类（模块文件 → 类名）。顺序 = MRO 顺序。
_DIALOG_MODULES = [
    ("dialog.py", "ImageEditorDialog"),
    ("dialog_toolbar.py", "ToolbarMixin"),
    ("dialog_pages.py", "ToolPagesMixin"),
    ("dialog_undo.py", "UndoMixin"),
    ("dialog_commit.py", "CommitMixin"),
]

#: 每个弹窗成员**应当**归属的类（成员名 → 类名）。
_DIALOG_EXPECTED_HOME = {
    # dialog.py -> ImageEditorDialog（6 个）
    "__init__": "ImageEditorDialog",
    "_confirm_overwrite": "ImageEditorDialog",
    "_escape": "ImageEditorDialog",
    "_finish": "ImageEditorDialog",
    "closeEvent": "ImageEditorDialog",
    "result_image": "ImageEditorDialog",
    # dialog_toolbar.py -> ToolbarMixin（7 个）
    "_build_side_panel": "ToolbarMixin",
    "_build_status": "ToolbarMixin",
    "_build_toolbar_row": "ToolbarMixin",
    "_hint": "ToolbarMixin",
    "_refresh_size_label": "ToolbarMixin",
    "_set_tool": "ToolbarMixin",
    "_swap_option_page": "ToolbarMixin",
    # dialog_pages.py -> ToolPagesMixin（7 个）
    "_labeled": "ToolPagesMixin",
    "_page_crop": "ToolPagesMixin",
    "_page_distort": "ToolPagesMixin",
    "_page_erase": "ToolPagesMixin",
    "_page_text": "ToolPagesMixin",
    "_page_transform": "ToolPagesMixin",
    "_slider_group": "ToolPagesMixin",
    # dialog_undo.py -> UndoMixin（9 个）
    "_history_cursor": "UndoMixin",
    "_history_nodes": "UndoMixin",
    "_on_history_row": "UndoMixin",
    "_push_undo": "UndoMixin",
    "_redo_now": "UndoMixin",
    "_reset_all": "UndoMixin",
    "_sync_history": "UndoMixin",
    "_sync_undo_buttons": "UndoMixin",
    "_undo_now": "UndoMixin",
    # dialog_commit.py -> CommitMixin（6 个）
    "_apply_crop": "CommitMixin",
    "_commit_text_blocks": "CommitMixin",
    "_commit_transform": "CommitMixin",
    "_on_stroke_started": "CommitMixin",
    "_selection": "CommitMixin",
    "_spawn_text_block": "CommitMixin",
}

#: 弹窗 Mixin 调用**别的 Mixin/基座**的成员 —— 登记的隐式契约。
_DIALOG_CROSS_DEPS = {
    "ImageEditorDialog": {
        "_apply_crop", "_build_side_panel", "_build_status",
        "_build_toolbar_row",
        "_commit_text_blocks", "_commit_transform",
        "_on_stroke_started",
        "_push_undo", "_redo_now", "_spawn_text_block", "_sync_history",
        "_undo_now",
    },
    "ToolbarMixin": {
        "_commit_text_blocks", "_commit_transform",
        "_finish", "_on_history_row", "_page_crop", "_page_distort",
        "_page_erase",
        "_page_text", "_page_transform", "_redo_now",
        "_reset_all",
        "_undo_now",
    },
    "ToolPagesMixin": {"_hint"},
    "UndoMixin": {"_refresh_size_label"},
    "CommitMixin": {"_push_undo", "_refresh_size_label"},
}

#: 子包必须存在的模块（拆分是真的、不是把文件改名了事）。
_REQUIRED_FILES = [
    "__init__.py", "consts.py", "geometry.py", "distortion.py",
    "bake.py", "text_item.py",
    "dialog.py", "canvas/__init__.py",
    "canvas/core.py", "canvas/interaction.py", "canvas/overlay.py",
    "canvas/text.py", "canvas/transform.py", "canvas/distortion.py",
    # 2026-10-07 二次拆分：894 行的 ImageEditorDialog 再按职责拆 4 个 Mixin
    "dialog_toolbar.py", "dialog_pages.py", "dialog_undo.py",
    "dialog_commit.py",
    # 类型检查期宿主面（拆分后 pyright 看不到兄弟 Mixin 的成员，见
    # ``tests/selftests/_context.py::check_type_only_host``）
    "_host.py", "canvas/_host.py",
]

#: 对外 API：外部（生产代码 + 测试）实际导入的名字，一个都不能少。
_PUBLIC_API = [
    "EDIT_FIT_RATIO", "ERASER_DEFAULT", "EditorCanvas", "ImageEditorDialog",
    "EDITOR_MIN_SIZE", "EDITOR_SIZE",
    "TEXT_SWATCHES", "TextBlockItem", "_BakeWorker",
    "bake_transform", "clamp_rect", "draw_text",
    "rotate_about", "run_with_progress", "scale_about", "shear_about",
]


def _load_classes(modules, base: Path) -> dict[str, ast.ClassDef]:
    out: dict[str, ast.ClassDef] = {}
    for fname, cname in modules:
        tree = ast.parse((base / fname).read_text(encoding="utf-8"))
        out[cname] = next(
            n for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == cname
        )
    return out


def _members(cls: ast.ClassDef) -> set[str]:
    out: set[str] = set()
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _check_assembly(label: str, main: str, classes: dict[str, ast.ClassDef],
                    expected_home: dict[str, str],
                    cross_deps: dict[str, set[str]],
                    min_members: int) -> None:
    """钉住一组 Mixin 装配的四条不变量（画布与弹窗各跑一遍）。

    ``label`` 只用于断言文案（"画布" / "弹窗"），两条路径的判据完全一致——
    这正是把 894 行的弹窗拆成 Mixin 之后**必须**共用的守卫：任何一条漏了，
    重名方法就会在 MRO 里静默遮蔽，工具会悄悄失灵而不是报错。
    """
    from tests.selftests._context import ok

    # ---- 1. 成员归属 ----
    home_of: dict[str, str] = {}
    for cname, cls in classes.items():
        for name in _members(cls):
            home_of.setdefault(name, cname)

    ok(f"守卫覆盖了{label}全部成员（不是空跑）",
       len(expected_home) >= min_members,
       f"只登记了 {len(expected_home)} 个")

    wrong = {
        n: (expected_home[n], home_of.get(n))
        for n in expected_home
        if home_of.get(n) != expected_home[n]
    }
    ok(f"{label}的每个成员都停在拆分时指定的 Mixin 里",
       not wrong, f"落点漂移={wrong}")

    lost = sorted(set(expected_home) - set(home_of))
    ok(f"{label}没有成员在拆分中丢失", not lost, f"丢失={lost}")

    # ---- 2. Mixin 之间无同名成员 ----
    overlap: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for cname, cls in classes.items():
        for name in _members(cls):
            if name in seen:
                overlap.setdefault(name, [seen[name]]).append(cname)
            else:
                seen[name] = cname
    ok(f"{label}的 Mixin 之间没有同名成员（否则 MRO 会静默遮蔽）",
       not overlap, f"重叠={overlap}")

    # ---- 3. 跨 Mixin 依赖在白名单内 ----
    bad: dict[str, list[str]] = {}
    for cname, cls in classes.items():
        own = _members(cls)
        allowed = cross_deps.get(cname, set())
        # 只关心"别处也定义了的成员"（即跨 Mixin 的方法调用）；
        # 实例属性（self._xxx = ...）与 Qt 自带方法不在此列。
        others = set().union(*(
            _members(other) for other_name, other in classes.items()
            if other_name != cname
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
    ok(f"{label}的跨 Mixin 方法调用全部登记在案",
       not bad, f"未登记的隐式契约={bad}")

    # ---- 4. 运行时：主类能看到全部成员 ----
    import desktop.components.viewers.image_editor as mod

    cls_obj = getattr(mod, main)
    invisible = [n for n in expected_home if not hasattr(cls_obj, n)]
    ok(f"{main} 仍能看到{label}全部成员（MRO 装配完整）",
       not invisible, f"看不到={invisible}")


def run(ctx) -> None:
    from tests.selftests._context import check_type_only_host, ok

    # ---- 0. 拆分是真的：子包与各模块都在 ----
    missing_files = [p for p in _REQUIRED_FILES if not (_PKG / p).is_file()]
    ok("image_editor 已是子包，且各拆分模块都在",
       not missing_files, f"缺={missing_files}")

    # ---- 1~4. 画布与弹窗各钉一遍 ----
    _check_assembly(
        "画布", "EditorCanvas", _load_classes(_MODULES, _CANVAS),
        _EXPECTED_HOME, _CROSS_METHOD_DEPS, min_members=45,
    )
    _check_assembly(
        "弹窗", "ImageEditorDialog", _load_classes(_DIALOG_MODULES, _PKG),
        _DIALOG_EXPECTED_HOME, _DIALOG_CROSS_DEPS, min_members=25,
    )

    # ---- 4b. 类型检查期宿主面（拆分后 pyright 看不到兄弟 Mixin 的成员）----
    check_type_only_host(
        ok, label="画布",
        root=_ROOT,
        pkg_rel="desktop/components/viewers/image_editor/canvas",
        host_file="_host.py", host_cls="CanvasHost",
        main_file="core.py", main_cls="EditorCanvas",
        mixin_modules=_MODULES[1:],
        expected_bases=["QGraphicsView"],
    )
    check_type_only_host(
        ok, label="弹窗",
        root=_ROOT,
        pkg_rel="desktop/components/viewers/image_editor",
        host_file="_host.py", host_cls="DialogHost",
        main_file="dialog.py", main_cls="ImageEditorDialog",
        mixin_modules=_DIALOG_MODULES[1:],
        expected_bases=["QDialog"],
    )

    # ---- 5. 对外 API 不变 ----
    import desktop.components.viewers.image_editor as mod

    absent = [n for n in _PUBLIC_API if not hasattr(mod, n)]
    ok("对外 API 名字照旧可导入（含模块属性打桩）",
       not absent, f"缺失={absent}")

    # 模块属性可写（测试靠 editor_mod.ImageEditorDialog = ... 打桩）
    original = mod.ImageEditorDialog
    try:
        mod.ImageEditorDialog = object
        patchable = mod.ImageEditorDialog is object
    finally:
        mod.ImageEditorDialog = original
    ok("ImageEditorDialog 是模块属性、可被打桩替换", patchable, "打桩不生效")
