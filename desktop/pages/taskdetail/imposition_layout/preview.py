# -*- coding: utf-8 -*-
"""模块二「拼版操作」的**预览与编辑**分片：整页预览、定位、右键编辑回写。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.services.imposition import (
    apply_editor_layout, cn_page_label, page_source_stems, product_path,
    refresh_rects_for_edited_source,
)

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_layout._host import (
        ImpositionLayoutHost,
    )
else:
    ImpositionLayoutHost = object


class PreviewMixin(ImpositionLayoutHost):
    """画布双击预览、右键「预览/编辑图片」与编辑回写的生效链。"""

    # ------------------------------------------------------------- 双击预览
    def _open_imposition_item_preview(self, _slot: int) -> None:
        """画布右键「预览图片」：预览**本页拼版后的图片**（整页成品组合）。

        用户 2026-10-18：拼版这一步的"图片"是**拼版后的图片**（会实时重合成
        产出新图），不是画布上那张输入源图；「编辑图片」才是作用于两张源图
        （编辑后重新合成，保持不变）。
        """
        self._open_imposition_spread_preview()

    def _open_imposition_spread_preview(self) -> None:
        """画布**双击空白处/右键图片「预览图片」**：预览整页左右组合（按产出口径）。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        current = view.current_index()
        self._open_imposition_zoom(
            lambda _index: self._imposition_spread_target(current), 0
        )

    def _open_imposition_zoom(self, factory, index: int) -> None:
        """打开（或复用）拼版预览弹窗；开头没有可预览的页就静默返回。"""
        from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

        if factory(index) is None:
            return
        if getattr(self, "_imposition_zoom_dialog", None) is None:
            self._imposition_zoom_dialog = dialog = ImageZoomDialog(
                self.window() or self, factory=factory
            )
            # 弹窗里「编辑」覆盖了真实文件 → 生效链（与各步骤预览区同一套）
            dialog.image_saved.connect(self._on_imposition_zoom_image_saved)
        dialog = self._imposition_zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        # （ImageZoomDialog 渲染走自己的 worker 线程，不占界面）
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(factory=factory, index=index)

    def _imposition_locate_targets(self, _slot: int) -> list[Path]:
        """画布右键「定位图片资源」的落点：**本页拼版成品** → **本节点成品目录**。

        用户 2026-10-18：拼版这一步的"图片资源"是**拼版后的图片**——它由合成
        worker 实时重合成，产出的是 ``stages/imposition[~<节点>]/NNNN.png``；
        画布上那张是**输入源图**（如 ``stages/input``），不是这一步的产物，不能
        拿它当「定位图片资源」的目标（其他步骤定位到自己的输入图是合理的，拼版
        不是）。

        成品页还没合成出来时退到**成品目录**，让用户至少到"这一批产物跟前"；
        两者都不在时由画布按"定位失败"说明原因（不静默）。

        ⚠️ ``_slot`` 只是画布解析器契约的形参（``(index) -> list[Path]``）：
        目标是**整页成品**，与右键的是哪一张子图无关。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or not getattr(self, "task_id", None):
            return []
        output = self._imposition_output_dir()
        if not output.parts:
            return []
        index = view.current_index()
        targets: list[Path] = []
        pages = self._imposition_pages()
        if 0 <= index < len(pages):
            targets.append(product_path(output, index, pages[index]))
        targets.append(output)
        return targets

    def _imposition_spread_target(self, page_index: int) -> "object | None":
        """弹窗「整页左右组合」来源：构造时快照版面，合成在 worker 线程。"""
        from desktop.workers import ImpositionPagePreviewWorker
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget

        pages = self._imposition_pages()
        if not 0 <= page_index < len(pages):
            return None
        items = [dict(item) for item in pages[page_index].get("items") or []]
        if not items:
            return None
        stems = page_source_stems(pages[page_index])
        right = stems[0] if stems else ""
        left = stems[1] if len(stems) > 1 else ""
        edit_path = None
        task_id = getattr(self, "task_id", None)
        output = product_path(
            self._imposition_output_dir(), page_index, pages[page_index]
        )
        if task_id and not getattr(self, "_imposition_dirty", False) and output.is_file():
            edit_path = output
        # ⚠️ 定位**独立于编辑**：整页组合是虚拟图（合成物），
        #    - 成品已落盘 → 定位成品页（这就是这一页产出的那个文件）；
        #    - 还没合成/有未落盘改动 → 退到**源图所在目录**，让用户至少能到
        #      那一批源图跟前；都没有就不给菜单（不弹死按钮）。
        locate_path = None
        if output.is_file():
            locate_path = output
        else:
            first = Path(str(items[0].get("file") or ""))
            if first.parent.is_dir():
                locate_path = first.parent
        return ZoomTarget(
            render=lambda edge,
            page={"items": items}: ImpositionPagePreviewWorker(page, edge),
            note=f"{cn_page_label(page_index)} 左右组合（左「{left}」+ 右「{right}」）",
            stem=f"imposition-{page_index + 1:02d}",
            count=1,
            save_path=edit_path,
            edit_path=edit_path,
            locate_path=locate_path,
            edit_label="编辑图片",
            show_text_tool=False,
        )

    def close_imposition_zoom_popup(self) -> None:
        """关掉拼版预览弹窗（内容失效时调：切任务等）。"""
        dialog = getattr(self, "_imposition_zoom_dialog", None)
        if dialog is not None:
            dialog.close()

    # ------------------------------------------------------------- 右键直接编辑
    def _on_imposition_source_edited(self, path_text: str, edited) -> None:
        """拼版源图被覆盖（画布右键或预览弹窗）：统一的生效链。

        ① 画布丢掉这张图的解码缓存并重绘；② **左列该页的缩略图**也要丢掉
        重渲（它按路径缓存在内存里，不清就永远停在旧图——用户 2026-10-08
        报"预览弹窗里编辑完，拼版页还是老图"就是漏了这一步）；③ 主页面
        ``_on_page_image_saved`` 刷新各查看器（rembg 输出无坐标基准，走其
        "按文件刷新"分支）；④ 重新防抖合成——拼版成品里嵌着这张源图，
        不重合成就白改了。
        """
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.canvas.invalidate_image(path_text)
        # ⚠️⚠️ 源图尺寸可能变了（编辑器里旋转/裁剪后覆盖回**同一文件**）：
        #    版面 rect 是按旧图尺寸记的，不刷新的话 compose_page 会把新图
        #    硬 resize 回旧宽高 ⇒ 旋转 90° 的图被横向压扁（形变 + 清晰度
        #    下降，用户 2026-10-10 报障）。先把引用它的 rect 刷成新尺寸
        #    （绕中心保持位置）并落盘，缩略图/画布/重合成用的才是新几何。
        pages = self._imposition_pages()
        if refresh_rects_for_edited_source({"pages": pages}, path_text):
            self._save_imposition_pages(pages)
        self._drop_imposition_source_thumb(path_text)
        self._on_page_image_saved(path_text, edited)
        self._schedule_imposition_compose()
        self.log_view.append(
            f"已编辑拼版源图「{Path(path_text).stem}」并覆盖原图"
            f"（{edited.width()}×{edited.height()} px），拼版成品将重新合成。"
        )

    def _open_imposition_spread_edit(self) -> None:
        """「编辑图片」：同一画布显示整页源图并切换活动图片。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        view.flush_pending()  # 拖住没松手的改动先落定，快照才是最新的
        items = [dict(item) for item in view.current_items()]
        if not items:
            return
        from PySide6.QtGui import QImage
        from desktop.components.viewers.image_editor import ImageEditorDialog

        for item in items:
            path = Path(str(item.get("file") or ""))
            image = QImage(str(path)) if path.is_file() else QImage()
            if image.isNull():
                self._toast(
                    "warning", "无法编辑",
                    f"读不到拼版源图：{path.name}（文件可能已被移动或删除）。",
                )
                return
            item["image"] = image

        editor = ImageEditorDialog(
            self.window() or self, items[0]["image"], save_back=True,
        )
        set_tool_visible = getattr(editor, "set_tool_visible", None)
        if callable(set_tool_visible):
            set_tool_visible("text", False)
        editor.configure_multiple_images(items)
        editor.multi_image_saved.connect(self._on_imposition_source_edited)
        page_index = view.current_index()
        editor.multi_layout_saved.connect(
            lambda updates, index=page_index:
                self._on_imposition_spread_layout_saved(index, updates)
        )
        editor.exec()
        editor.release_buffers()

    def _on_imposition_spread_layout_saved(
        self, page_index: int, updates: list[dict],
    ) -> None:
        """把编辑弹窗中的双图相对位置/尺寸保存回任务版面。"""
        pages = self._imposition_pages()
        if not 0 <= page_index < len(pages):
            return
        items = pages[page_index].get("items") or []
        if apply_editor_layout(items, updates):
            self._save_imposition_pages(pages)

    def _on_imposition_zoom_image_saved(self, path_text: str,
                                        image=None) -> None:
        """预览弹窗里「编辑」覆盖了真实文件（``image_saved``）：按落点接链。

        回写目标由 ``ZoomTarget.edit_path`` 给（2026-10-07 用户定：预览弹窗里
        的编辑也要生效）——落点只有两种：

        - **拼版成品**（整页组合编辑）：挂着的防抖合成必须取消（定时器停 +
          清脏标记），否则旧合成跑完会把刚覆盖的手改冲掉；版面没变不需要
          再合成，刷新打印源即可。与画布右键空白编辑同一套善后。
        - **拼版源图**（单张原图编辑）：走 :meth:`_on_imposition_source_edited`
          与画布右键完全相同的生效链。
        """
        if image is None or image.isNull():
            return
        path = Path(path_text)
        task_id = getattr(self, "task_id", None)
        if task_id and path.parent == self._imposition_output_dir():
            timer = getattr(self, "_imposition_timer", None)
            if timer is not None:
                timer.stop()
            self._imposition_dirty = False
            self._refresh_print_source()
            self.log_view.append(
                f"已编辑整页组合并覆盖拼版成品「{path.name}」"
                f"（{image.width()}×{image.height()} px，PDF排版用这张）；"
                "再次调整该页版面会重新合成、覆盖这次编辑。"
            )
            return
        self._on_imposition_source_edited(path_text, image)
