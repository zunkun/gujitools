# -*- coding: utf-8 -*-
"""9. 右键菜单：预览单图或整页，编辑统一打开整页编辑器"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import EDIT_ITEM_COLOR, _qimage_pixel, _solid_qimage
    from desktop.components.imposition.canvas import ImpositionCanvas
    from desktop.components.imposition.view import ImpositionViewWidget
    from pathlib import Path
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QDialog
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPointF, QSize, Qt
    from qfluentwidgets.components.widgets.menu import RoundMenu
    from desktop.services import imposition as S
    import desktop.utils.files as _files_mod
    import desktop.components.viewers.image_editor as _ied
    from tests.selftests._context import make_pdf, ok, pump
    from desktop.services.imposition import same_path
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QDialog
    from qfluentwidgets.components.widgets.menu import RoundMenu

    from tests.selftests._context import wait_until

    _menu: dict = {}

    def _fake_menu_exec(self, pos, ani=True, aniType=None):
        _menu["actions"] = self.actions()
        return None

    _real_menu_exec = RoundMenu.exec
    RoundMenu.exec = _fake_menu_exec

    def _ctx(cv, x, y):
        return QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            QPoint(int(x), int(y)),
            QPoint(int(x), int(y)),
        )

    def _pick(choice: int):
        """点菜单里的第 choice 项（0=预览图片 1=编辑图片）。"""
        _menu["actions"][choice].trigger()

    try:
        # ---- 画布层：菜单两项 + 目标分流 ----
        canvas4 = ImpositionCanvas()
        canvas4.resize(600, 600)
        canvas4.set_page(S.default_items([str(st.a), str(st.b)]))
        canvas4.show()
        st.ctx.app.processEvents()

        hits: dict = {
            "preview_item": [],
            "preview_spread": 0,
            "edit_item": [],
            "edit_spread": 0,
        }
        canvas4.item_preview_requested.connect(
            lambda i: hits["preview_item"].append(i)
        )
        canvas4.spread_double_clicked.connect(
            lambda: hits.__setitem__("preview_spread", hits["preview_spread"] + 1)
        )
        canvas4.item_edit_requested.connect(
            lambda i: hits.__setitem__("edit_item", hits["edit_item"] + [i])
        )
        canvas4.spread_edit_requested.connect(
            lambda: hits.__setitem__("edit_spread", hits["edit_spread"] + 1)
        )
        selections: list[int] = []
        canvas4.selection_changed.connect(selections.append)

        ix, iy = st._item_pt(canvas4, 0)
        canvas4.contextMenuEvent(_ctx(canvas4, ix, iy))
        ok(
            "右键图上弹出菜单：「预览图片 / 编辑图片 / 定位图片资源」",
            [act.text() for act in _menu.get("actions", [])]
            == ["预览图片", "编辑图片", "定位图片资源"],
            str([act.text() for act in _menu.get("actions", [])]),
        )
        ok(
            "右键即选中那张图（与左键点击同款语义）",
            canvas4.selected() == 0 and selections == [0],
            f"selected={canvas4.selected()} selections={selections}",
        )
        _pick(0)
        ok(
            "右键图上点「预览图片」→ 预览这张原图",
            hits["preview_item"] == [0] and hits["preview_spread"] == 0,
            str(hits),
        )
        _pick(1)
        ok(
            "右键图上点「编辑图片」→ 发整页编辑请求（携带命中槽位）",
            hits["edit_item"] == [0] and hits["edit_spread"] == 0,
            str(hits),
        )
        # 定位图片资源（2026-10-11 用户）：资源管理器定位那张子图的源文件
        import desktop.utils.files as _files_mod

        _located: list = []
        _real_reveal = _files_mod.reveal_in_explorer
        _files_mod.reveal_in_explorer = lambda p: _located.append(Path(p)) or True
        try:
            _pick(2)
        finally:
            _files_mod.reveal_in_explorer = _real_reveal
        item_file = Path(str(canvas4._items[0]["file"]))
        ok(
            "右键图上点「定位图片资源」→ 资源管理器定位该子图源文件",
            _located == [item_file],
            f"located={_located}",
        )

        bx, by = st._blank_pt(canvas4)
        canvas4.contextMenuEvent(_ctx(canvas4, bx, by))
        ok(
            "右键空白处菜单：编辑项文案同为「编辑图片」",
            [act.text() for act in _menu.get("actions", [])]
            == ["预览图片", "编辑图片"],
            str([act.text() for act in _menu.get("actions", [])]),
        )
        _pick(0)
        _pick(1)
        ok(
            "右键空白处：预览走 spread 信号、编辑走 spread_edit 信号",
            hits["preview_spread"] == 1
            and hits["edit_spread"] == 1
            and hits["edit_item"] == [0],
            str(hits),
        )
        canvas4.deleteLater()

        _menu.clear()
        empty_hits: list[int] = []
        empty_canvas = ImpositionCanvas()
        empty_canvas.item_edit_requested.connect(empty_hits.append)
        empty_canvas.contextMenuEvent(_ctx(empty_canvas, 30, 30))
        ok("空画布右键没有菜单", not _menu.get("actions"), str(_menu))
        empty_canvas.deleteLater()

        # ---- 视图层：编辑信号也直连转发 + 提示语提到右键 ----
        view3 = ImpositionViewWidget()
        view3.set_pages([{"items": S.default_items([str(st.a), str(st.b)])}], current=0)
        edit_forward: list[str] = []
        view3.item_edit_requested.connect(
            lambda i: edit_forward.append(f"item:{i}")
        )
        view3.spread_edit_requested.connect(lambda: edit_forward.append("spread"))
        view3.canvas.item_edit_requested.emit(1)
        view3.canvas.spread_edit_requested.emit()
        ok(
            "视图把两种右键编辑都转发给控制器（item:槽位 / spread）",
            edit_forward == ["item:1", "spread"],
            str(edit_forward),
        )
        ok(
            "底部提示语写明右键可编辑",
            "右键" in view3.hint.text() and "编辑" in view3.hint.text(),
            view3.hint.text(),
        )
        view3.deleteLater()

        # ---- 控制器层：点击单张图编辑时，仍打开包含左右两图的整页编辑器 ----
        import desktop.components.viewers.image_editor as _ied

        _edit_seen: dict = {}
        _edited = _solid_qimage(EDIT_ITEM_COLOR, 64, 48)

        class _FakeSignal:
            def connect(self, _callback):
                pass

        class _FakeEditorDialog:
            def __init__(self, parent, image, save_back=False):
                _edit_seen["save_back"] = save_back
                self.multi_image_saved = _FakeSignal()
                self.multi_layout_saved = _FakeSignal()

            def set_tool_visible(self, tool, visible):
                _edit_seen["tool_visibility"] = (tool, visible)

            def configure_multiple_images(self, items):
                _edit_seen["files"] = [item["file"] for item in items]

            def release_buffers(self):
                _edit_seen["released"] = True

            def exec(self):
                _edit_seen["exec"] = _edit_seen.get("mode", "ok")
                return QDialog.DialogCode.Accepted

        _real_editor_cls = _ied.ImageEditorDialog
        _ied.ImageEditorDialog = _FakeEditorDialog

        from desktop.components.viewers.image_zoom_dialog import (
            ZoomTarget,
        )

        def _pixel_of(path: Path):
            return _qimage_pixel(path, 2, 2)

        try:
            item_path = Path(st.page._imposition_pages()[0]["items"][0]["file"])
            ok("准备：拼版源图存在", item_path.exists())
            st.page._imposition_timer.stop()
            st.page._imposition_dirty = False
            # 预热画布解码缓存，确认打开编辑器本身不会丢缓存
            st.page.imposition_view.canvas._image(str(item_path))
            ok(
                "准备：画布缓存里已有这张图",
                str(item_path) in st.page.imposition_view.canvas._images,
            )

            _edit_seen.clear()
            st.page.imposition_view.item_edit_requested.emit(0)
            ok(
                "单张入口打开整页编辑器并配置两张图片",
                _edit_seen.get("save_back") is True
                and _edit_seen.get("exec") == "ok"
                and len(_edit_seen.get("files", [])) == 2
                and _edit_seen.get("released") is True,
                str(_edit_seen),
            )
            ok(
                "整页编辑入口隐藏文字工具且不改写单张源图",
                _edit_seen.get("tool_visibility") == ("text", False)
                and _pixel_of(item_path) != EDIT_ITEM_COLOR,
                f"tool={_edit_seen.get('tool_visibility')} "
                f"item_pixel={_pixel_of(item_path)}",
            )
            ok(
                "打开编辑器不会丢弃画布缓存或触发拼版重合成",
                str(item_path) in st.page.imposition_view.canvas._images
                and not st.page._imposition_dirty,
                f"cached={str(item_path) in st.page.imposition_view.canvas._images} "
                f"dirty={st.page._imposition_dirty}",
            )

            # 预览弹窗里「编辑」也落盘：image_saved → 生效链（2026-10-07）
            st.page.imposition_view.canvas._image(str(item_path))
            st.page._on_imposition_zoom_image_saved(str(item_path), _edited)
            ok(
                "弹窗编辑源图：画布缓存被丢 + 重新防抖合成已挂上",
                str(item_path) not in st.page.imposition_view.canvas._images
                and st.page._imposition_dirty,
                f"cached={str(item_path) in st.page.imposition_view.canvas._images} "
                f"dirty={st.page._imposition_dirty}",
            )
            st.page._imposition_timer.stop()
            st.page._imposition_dirty = False

            # ---- 编辑生效链：**左列该页缩略图**也必须跟上（2026-10-08/09）----
            # 用户报：预览弹窗里编辑完，关掉弹窗拼版页还是老图。实体口径下
            # 签名带**源图文件指纹**，覆盖后指纹变 ⇒ 含它的页排进重生成
            # 批次。这里钉住"必须把那页排进队列"。
            rep = str(item_path)
            st.page._on_imposition_source_edited(rep, _edited)
            _mgr_ed = getattr(st.page, "_page_thumb_mgr", None)
            _hit_pages = set(_mgr_ed._pending) if _mgr_ed is not None else set()
            ok(
                "编辑源图后：含它的页排进缩略图重生成批次（实体签名失效）",
                bool(_hit_pages),
                f"pending={_hit_pages}",
            )
            st.page._imposition_timer.stop()
            st.page._imposition_dirty = False

            # ---- 路径**形态**不同也要命中（分隔符/大小写）----
            from desktop.services.imposition import same_path

            ok(
                "路径比较：分隔符/大小写不同的同一路径判为同一处",
                same_path(rep, rep.replace("\\", "/"))
                and same_path(rep, rep.upper())
                and not same_path(rep, rep + "x")
                and not same_path("", rep),
                f"rep={rep}",
            )

            st.page.imposition_view.canvas._image(rep)
            st.page.imposition_view.canvas.invalidate_image(rep.replace("\\", "/"))
            ok(
                "画布失效：用另一种斜杠形态也能丢中解码缓存",
                rep not in st.page.imposition_view.canvas._images,
                str(list(st.page.imposition_view.canvas._images)),
            )

            if _mgr_ed is not None:
                _mgr_ed._pending.clear()
            st.page._drop_imposition_source_thumb(rep.replace("\\", "/"))
            ok(
                "左列缩略图失效：用另一种斜杠形态也能丢中（排进重生成批次）",
                _mgr_ed is not None and bool(_mgr_ed._pending),
                str(set(_mgr_ed._pending) if _mgr_ed is not None else set()),
            )

            # 取消编辑：不覆盖
            _edit_seen.clear()
            _edit_seen["mode"] = "reject"

            class _RejectEditor(_FakeEditorDialog):
                def exec(self):
                    return QDialog.DialogCode.Rejected

            _ied.ImageEditorDialog = _RejectEditor
            before = _pixel_of(item_path)
            st.page.imposition_view.item_edit_requested.emit(0)
            ok(
                "取消整页编辑不覆盖任何单张源图",
                _pixel_of(item_path) == before,
                f"before={before} after={_pixel_of(item_path)}",
            )
            _ied.ImageEditorDialog = _FakeEditorDialog
        finally:
            _ied.ImageEditorDialog = _real_editor_cls

        # ---- 空白处「编辑图片」在同一画布显示两张，可切换 active ----
        source_items = st.page._imposition_pages()[0]["items"]
        source_items = sorted(
            source_items,
            key=lambda item: item["rect"][0] + item["rect"][2] / 2,
        )
        source_paths = [Path(item["file"]) for item in source_items]
        before_pixels = [_pixel_of(path) for path in source_paths]
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtTest import QTest

        def _make_spread_editor():
            editor = _real_editor_cls(None, QImage(str(source_paths[0])))
            editor.configure_multiple_images([
                {
                    **item,
                    "image": QImage(str(Path(item["file"]))),
                }
                for item in source_items
            ])
            editor._confirm_overwrite = lambda: True
            return editor

        single_editor = _real_editor_cls(None, QImage(str(source_paths[0])))
        single_editor.configure_multiple_images([{
            **source_items[0],
            "image": QImage(str(source_paths[0])),
        }])
        ok(
            "单图拼版仍可通过整图入口打开，且不显示虚假副图",
            single_editor.canvas._context_item is None,
        )
        single_editor.release_buffers()

        editor = _make_spread_editor()
        editor._image.fill(QColor(*EDIT_ITEM_COLOR))
        editor.reject()
        ok(
            "关闭双图编辑器会放弃修改且不覆盖任何源图",
            [_pixel_of(path) for path in source_paths] == before_pixels,
        )
        editor.release_buffers()

        editor = _make_spread_editor()
        first_active = editor.source_path
        editor.show()
        pump(st.ctx.app, times=3)
        inactive_center = editor.canvas._context_item.sceneBoundingRect().center()
        QTest.mouseClick(
            editor.canvas.viewport(), Qt.MouseButton.LeftButton,
            pos=editor.canvas.mapFromScene(inactive_center),
        )
        second_active = editor.source_path
        ok(
            "整幅编辑同一画布同时显示左右图片，点击另一张切换 active",
            editor.canvas._context_item is not None
            and first_active == str(source_paths[0])
            and second_active == str(source_paths[1]),
            f"first={first_active} second={second_active}",
        )
        editor._image.fill(QColor(*EDIT_ITEM_COLOR))
        editor.canvas.replace_image(editor._image)
        editor._finish()
        after_pixels = [_pixel_of(path) for path in source_paths]
        ok(
            "切换后仅保存修改过的图片，未修改图片保持原样",
            after_pixels[0] == before_pixels[0]
            and after_pixels[1] == EDIT_ITEM_COLOR,
            f"before={before_pixels} after={after_pixels}",
        )
        editor.release_buffers()

        before_pixels = [_pixel_of(path) for path in source_paths]
        # 切换活动图片时，另一层的挂起变换既不烘焙也不丢失。
        editor = _make_spread_editor()
        editor._set_tool("transform")
        editor.canvas.transform_rotate(12)
        editor.canvas.make_transform_pending()
        pending_before = editor.canvas.transform_pending()
        transform_commits = []
        preview_renders = []
        editor._commit_transform = lambda **kwargs: (
            transform_commits.append(kwargs) or False
        )
        editor.canvas._render_float_plane = (
            lambda: preview_renders.append(True)
        )
        editor.show()
        pump(st.ctx.app, times=3)
        inactive_center = editor.canvas._context_item.sceneBoundingRect().center()
        QTest.mouseClick(
            editor.canvas.viewport(), Qt.MouseButton.LeftButton,
            pos=editor.canvas.mapFromScene(inactive_center),
        )
        switched_pending = editor.canvas.transform_pending()
        active_center = editor.canvas._context_item.sceneBoundingRect().center()
        QTest.mouseClick(
            editor.canvas.viewport(), Qt.MouseButton.LeftButton,
            pos=editor.canvas.mapFromScene(active_center),
        )
        restored_pending = editor.canvas.transform_pending()
        ok(
            "切换双图只切 active，挂起变换不烘焙且切回后仍保留",
            pending_before is not None
            and switched_pending is None
            and restored_pending is not None
            and restored_pending[1] == pending_before[1]
            and not transform_commits
            and not preview_renders,
            f"before={pending_before is not None} "
            f"restored={restored_pending is not None} "
            f"commits={len(transform_commits)} "
            f"preview_renders={len(preview_renders)}",
        )
        editor.reject()
        editor.release_buffers()

        # 右图统一变换后向右移，切回左图时右图的 ghost 必须仍占据
        # 相同的视口范围，且完整落在可滚动场景内。
        editor = _make_spread_editor()
        editor.show()
        pump(st.ctx.app, times=3)
        editor._set_tool("transform")
        editor._activate_layer(1)
        editor.canvas.transform_move(200, 0)
        editor.canvas.make_transform_pending()
        right_bounds = editor.canvas._display_bounds()
        editor._activate_layer(0)
        context_item = editor.canvas._context_item
        context_bounds = context_item.sceneBoundingRect()
        scene_bounds = editor.canvas.sceneRect()
        ok(
            "右图统一变换右移 200px 后切回左图，右图显示不截断",
            context_item is not None
            # 允许 2px 浮点/像素取整误差（Qt 场景坐标是 float）
            and scene_bounds.adjusted(-2, -2, 2, 2).contains(context_bounds)
            and right_bounds.width() > 0
            and context_bounds.width() > 0,
            f"scene={scene_bounds}, right={right_bounds}, context={context_bounds}",
        )
        editor.reject()
        editor.release_buffers()

        editor = _make_spread_editor()
        editor.show()
        pump(st.ctx.app, times=3)
        editor._image.fill(QColor(230, 80, 40))
        editor.canvas.replace_image(editor._image)
        inactive_center = editor.canvas._context_item.sceneBoundingRect().center()
        QTest.mouseClick(
            editor.canvas.viewport(), Qt.MouseButton.LeftButton,
            pos=editor.canvas.mapFromScene(inactive_center),
        )
        editor._image.fill(QColor(60, 90, 230))
        editor.canvas.replace_image(editor._image)
        editor._finish()
        after_pixels = [_pixel_of(path) for path in source_paths]
        ok(
            "两张图分别编辑后均保存回各自源文件",
            after_pixels == [(230, 80, 40), (60, 90, 230)],
            f"before={before_pixels} after={after_pixels}",
        )
        editor.release_buffers()

        ok(
            "编辑整幅不会把合成图写回成品文件",
            not st.page._imposition_pages()[0].get("edited_file"),
        )
    finally:
        RoundMenu.exec = _real_menu_exec

