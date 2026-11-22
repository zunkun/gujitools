# -*- coding: utf-8 -*-
"""独立拼图页的预览弹窗与编辑生效链（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

import PySide6.QtGui as QtGui

from desktop.services.imposition import (
    WHITE_BACKGROUND,
    apply_editor_layout,
    cn_page_label,
    page_has_file,
    page_source_stems,
    refresh_rects_for_edited_source,
)

from .paths import edited_page_dir


class PreviewMixin:
    """双击/右键预览、整页编辑与编辑回写后的刷新链。"""

    # -------------------------------------------------------------- 预览与编辑
    #
    # 用户 2026-10-03：「**独立步骤，图片也可以编辑生效**」。这四条此前在独立
    # 拼图页**整个没接线**——画布的右键菜单弹得出来、双击也会发信号，但点了
    # 什么都不会发生（信号发出去没人接）。语义与任务流程的拼版步骤逐条对齐：
    # 双击图 = 编辑整页组合；双击空白 = 预览整页左右组合；
    # 右键「编辑图片」无论图上/空白都编辑整页组合。

    def _open_item_preview(self, slot: int) -> None:
        """右键「预览图片」命中子图时：预览这张原图（可缩放、下载）。"""
        index = self.view.current_index()
        self._open_zoom(lambda _i: self._item_target(index, slot), 0)

    def _open_spread_preview(self) -> None:
        """画布**双击两图之外的空白**：预览整页左右组合（按导出口径合成）。"""
        index = self.view.current_index()
        self._open_zoom(lambda _i: self._spread_target(index), 0)

    def _open_zoom(self, factory, index: int) -> None:
        """打开（或复用）预览弹窗；没有可预览的页时静默返回。"""
        from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

        if factory(index) is None:
            return
        if self._zoom_dialog is None:
            self._zoom_dialog = dialog = ImageZoomDialog(
                self.window() or self, factory=factory
            )
            # 弹窗里「编辑」覆盖了真实文件 → 生效链（与各步骤预览区同一套）
            dialog.image_saved.connect(self._on_zoom_image_saved)
        dialog = self._zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(factory=factory, index=index)

    def close_zoom_dialog(self) -> None:
        """关掉预览弹窗（内容失效时调：换源 / 清空）。"""
        if self._zoom_dialog is not None:
            self._zoom_dialog.close()

    def _item_target(self, page_index: int, slot: int):
        """弹窗「**单张原图**」来源：``slot`` 即弹窗页码（0 右槽 / 1 左槽）。

        ``edit_path`` = 这张源图文件：弹窗里「编辑」「完成」后原子覆盖回源图，
        由 :meth:`_on_zoom_image_saved` 接生效链（2026-10-07 用户定：预览弹窗
        里的编辑也要生效，不再只读——与任务流程的拼版步骤保持一致）。
        """
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget
        from desktop.workers import PreviewWorker

        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return None
        items = pages[page_index].get("items") or []
        if not (0 <= slot < len(items)):
            return None
        path = Path(str(items[slot].get("file") or ""))
        if not path.is_file():
            return None
        side = "右侧" if slot == 0 else "左侧"
        return ZoomTarget(
            render=lambda edge, p=path: PreviewWorker(p, longest_edge=edge),
            note=f"{cn_page_label(page_index)} · {side}「{path.name}」",
            stem=path.stem,
            count=len(items),
            # ⚠️ 只给「定位」，不给 edit_path：拼版不提供单张源图编辑（编辑统一
            #    作用于整页）。绑在 edit_path 上会让这张原图没有定位菜单。
            locate_path=path,
        )

    def _spread_target(self, page_index: int):
        """弹窗「整页左右组合」来源：构造时快照版面，合成在 worker 线程。"""
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget
        from desktop.workers import ImpositionPagePreviewWorker

        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return None
        items = [dict(item) for item in pages[page_index].get("items") or []]
        if not items:
            return None
        stems = page_source_stems(pages[page_index])
        right = stems[0] if stems else ""
        left = stems[1] if len(stems) > 1 else ""
        edited = pages[page_index].get("edited_file")
        edit_path = Path(edited) if edited and Path(edited).is_file() else None
        # ⚠️ 定位独立于编辑：整页组合是虚拟图——有成品定位成品，没有就退到
        #    源图所在目录（至少能到那一批源图跟前），别因为没有成品就不给菜单。
        locate_path = edit_path
        if locate_path is None:
            first = Path(str(items[0].get("file") or ""))
            if first.parent.is_dir():
                locate_path = first.parent
        return ZoomTarget(
            render=lambda edge, page={"items": items}: (
                # ⚠️ 白底（与「导出成品」同口径）：singletask 的整页组合预览
                #    和编辑基底都要长得跟导出的 PNG 一样（2026-10-13 用户）。
                ImpositionPagePreviewWorker(page, edge, WHITE_BACKGROUND)
            ),
            note=f"{cn_page_label(page_index)} 左右组合（左「{left}」+ 右「{right}」）",
            stem=f"imposition-{page_index + 1:02d}",
            count=1,
            save_path=edit_path,
            edit_path=edit_path,
            locate_path=locate_path,
            edit_label="编辑图片",
            show_text_tool=False,
        )

    def _after_source_edited(
        self, file_text: str, edited,
    ) -> None:
        """拼版源图编辑生效后的**刷新链**（同步/后台应用两条路共用）。"""
        self.view.canvas.invalidate_image(file_text)
        # ⚠️⚠️ 源图尺寸可能变了（编辑器里旋转/裁剪后覆盖回同一文件）：版面
        #    rect 还按旧尺寸记着，合成时 compose_page 会把新图硬 resize 回
        #    旧宽高 ⇒ 形变 + 清晰度下降（2026-10-10 报障）。先刷新 rect 再
        #    刷视图，画布/缩略图/导出用的才是新几何。
        if refresh_rects_for_edited_source(self._doc, file_text):
            self._refresh_view()
        self._invalidate_page_thumbs_for(file_text)  # 含它的页重生成实体
        self.log(
            f"已编辑拼版源图「{Path(file_text).name}」并覆盖原图"
            f"（{edited.width()}×{edited.height()} px）；"
            "点「导出成品」即用上这次修改。"
        )

    def _open_spread_edit(self) -> None:
        """「编辑图片」：同一画布显示整页源图并切换活动图片。"""
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        self.view.flush_pending()  # 拖住没松手的改动先落定，快照才是最新的
        items = [dict(item) for item in self.view.current_items()]
        if not items:
            return
        from desktop.components.viewers.image_editor import ImageEditorDialog

        for item in items:
            path = Path(str(item.get("file") or ""))
            image = QtGui.QImage(str(path)) if path.is_file() else QtGui.QImage()
            if image.isNull():
                self.toast(
                    "warning", "无法编辑",
                    f"读不到拼版源图：{path.name}（文件可能已被移动或删除）。",
                )
                return
            item["image"] = image

        editor = ImageEditorDialog(self, items[0]["image"], save_back=True)
        set_tool_visible = getattr(editor, "set_tool_visible", None)
        if callable(set_tool_visible):
            set_tool_visible("text", False)
        editor.configure_multiple_images(items)
        editor.multi_image_saved.connect(self._after_source_edited)
        editor.multi_layout_saved.connect(
            lambda updates, page_index=index:
                self._after_spread_layout_edited(page_index, updates)
        )
        editor.exec()
        editor.release_buffers()

    def _after_spread_layout_edited(
        self, page_index: int, updates: list[dict],
    ) -> None:
        """把弹窗中的双图相对位置/尺寸应用到当前拼版页。"""
        pages = self._doc.get("pages") or []
        if not 0 <= page_index < len(pages):
            return
        items = pages[page_index].get("items") or []
        changed = apply_editor_layout(items, updates)
        if not changed:
            return
        self._refresh_view()
        for path in changed:
            self._invalidate_page_thumbs_for(path)

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """预览弹窗里「编辑」覆盖了真实文件（``image_saved``）：按落点接链。

        回写目标由 ``ZoomTarget.edit_path`` 给（2026-10-07 用户定：预览弹窗里
        的编辑也要生效）——落点只有两种：

        - **源图**（整页编辑器中编辑某张图）：走统一善后——画布丢解码缓存、
          左列缩略图重渲、日志说明「导出成品」时生效。
        - **整页组合的手改缓存**（``edited/``）：给 ``edit_path`` 的前提就是
          doc 的 ``edited_file`` 本来指着它，文件已被覆盖成最新，补一句日志。

        ⚠️⚠️ **先无条件把画布那张图的解码缓存丢掉，再去认它属于哪一页**：
        认页靠路径比较，而缓存键是 ``item["file"]`` 原样字符串、``path_text``
        来自 ``Path(...)``——两边只要有一处形态不同（Windows 分隔符、大小写、
        相对/绝对），比较就落空，旧代码于是**整段 return 什么都不做**，
        用户看到的就是"从预览弹窗里编辑完，关掉弹窗拼版页还是老图"
        （2026-10-08 报障）。丢缓存本身按路径规范化命中、对不属于本页的
        路径也无害，所以放在判断之前；认页只用来决定"打哪句日志、刷哪条
        缩略图"。
        """
        if image is None or image.isNull():
            return
        path = Path(path_text)
        self.view.canvas.invalidate_image(path_text)
        pages = self._doc.get("pages") or []
        hits = [
            index for index, page in enumerate(pages)
            if page_has_file(page, path_text)
        ]
        if hits:
            # ⚠️ 同 _open_item_edit：源图尺寸可能变了，先刷 rect 再刷视图
            #    （否则 compose_page 把新图硬 resize 回旧宽高 ⇒ 压扁变形）。
            if refresh_rects_for_edited_source(self._doc, path_text):
                self._refresh_view()
            self._invalidate_page_thumbs_for(path_text, hits)
            self.log(
                f"已编辑拼版源图「{path.stem}」并覆盖原图"
                f"（{image.width()}×{image.height()} px）；"
                "点「导出成品」即用上这次修改。"
            )
            return
        if path.parent == edited_page_dir():
            self.log(
                f"已编辑整页组合「{path.name}」"
                f"（{image.width()}×{image.height()} px）；"
                "点「导出成品」时这一页用手改图。"
            )
