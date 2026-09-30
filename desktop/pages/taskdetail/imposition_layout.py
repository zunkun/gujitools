# -*- coding: utf-8 -*-
"""**模块二「拼版操作」控制器**：画布版面操作与拼版合成落盘。

对应 UI 模块二（``desktop/components/imposition/canvas.py`` +
``panel.py``）：
- 画布里拖动 / 缩放拉伸 / 旋转 → ``items_changed`` → 落盘 + 防抖合成；
- **双击预览**（用户 2026-09-30）：双击某张图 → 弹窗预览这张原图；
  双击两图之外的空白处 → 弹窗预览整页左右组合（按产出口径合成）；
- 面板的**整体旋转**（滑块/输入框增量）、复位本页版面（对当前页或
  选中槽位做版面变换）、**删除选中图片**（2026-09-30 用户定：选中哪张
  就能删哪张，页保留、图回未选择列表）；
- 状态行（当前页 / 选中槽位 / 拼版是否生效 / 单图页显隐「新增图片」）；
- **后台防抖合成**（``stages/imposition/``，列表顺序即页序）与生成 PDF 前
  的同步兜底合成。

只通过 ``self`` 依赖共享基元（``imposition.ImpositionBaseMixin``）与宿主
页面（``store``、``log_view``、``run_worker``、``_toast``），本文件
**不 import** 其它拼版控制器模块。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

from desktop.services.imposition import (
    cn_page_label, default_items, page_source_stems, single_items,
)
#: 版面改动 → 后台重新合成落盘的防抖（拖动会连续改版面）
COMPOSE_DEBOUNCE_MS = 500
#: 旋转组件（滑块/输入框）连续吐增量 → 停顿多久算"改完了"再统一落盘
EDIT_COMMIT_DEBOUNCE_MS = 250


class ImpositionLayoutMixin:
    """拼版版面操作（模块二）：旋转/复位、版面落盘、防抖后台合成。"""

    # ------------------------------------------------------------- 版面操作
    def _on_imposition_whole_rotate(self, delta: float) -> None:
        """面板的**整版旋转**组件吐了增量：画布即时转，停顿后统一落盘。

        滑块拖动会连续吐增量（每格 0.5°），不能每格都走一遍
        ``set_page`` + 落盘 + 合成——``rotate_whole`` 只原地改 items 重绘
        （顺带把待落盘标脏），由 ``_imposition_edit_timer`` 在用户停手后
        统一 ``flush_pending``（→ items_changed → 落盘 + 防抖合成）。
        之前积压的任何未上报编辑也由这同一个计时器一并补发。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0 or not view.canvas.has_items():
            return
        view.canvas.rotate_whole(delta)
        self._start_imposition_edit_commit()

    def _on_imposition_item_rotate(self, angle: float) -> None:
        """面板的**选中图旋转**组件设了绝对角度：即时转，停顿后统一落盘。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        if view.selected_slot() < 0:
            return  # 组件没选中时本来就该禁用；防御一下
        view.canvas.set_item_rotation(angle)
        self._start_imposition_edit_commit()

    def _start_imposition_edit_commit(self) -> None:
        """旋转组件改了画布但还没上报：启动停顿计时器（没建就立刻兜底提交）。"""
        timer = getattr(self, "_imposition_edit_timer", None)
        if timer is None:
            view = getattr(self, "imposition_view", None)
            if view is not None:
                view.canvas.flush_pending()
            return
        timer.start()

    def _commit_imposition_edit(self) -> None:
        """旋转组件停顿到期：把画布上的改动补报出去 + 回填面板角度。"""
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        view.canvas.flush_pending()  # → items_changed → 落盘 + 防抖合成
        # 整版转过后外接框变了：重新适配可视区（拖动画布时有意不适配，这里
        # 是组件操作，落定后一次适配是期望行为）
        view.canvas.refit()
        self._sync_imposition_rotation_ui()

    def _sync_imposition_rotation_ui(self) -> None:
        """把画布当前的角度回填到面板旋转组件（整体=平均角，单图=选中角）。

        回填走 blockSignals 语义（panel 内部挡信号），不会把同步误当成用户
        输入再转一次。没有页时两组组件都禁用。
        """
        panel = getattr(self, "imposition_panel", None)
        view = getattr(self, "imposition_view", None)
        if panel is None or view is None:
            return
        canvas = view.canvas
        if view.current_index() < 0 or not canvas.has_items():
            panel.set_page_available(False)
            panel.set_whole_angle(0.0)
            panel.set_item_rotation(None)
            return
        panel.set_page_available(True)
        panel.set_whole_angle(canvas.spread_rotation() or 0.0)
        panel.set_item_rotation(
            canvas.selected_rotation()
            if canvas.selected() >= 0 else None
        )

    def _on_imposition_reset_layout(self) -> None:
        """把本页版面复位成**刚拼好时的样子**（两张并排、原始尺寸、无旋转）。

        没有纸张之后，"复位"只能以**两张图的原始尺寸**为基准：重新按
        ``default_items`` 摆一遍（右槽在左槽右边、顶部对齐）。这样用户把图拖得
        乱七八糟之后一键就能回到干净的并排版面。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            self._toast("info", "没有拼版页", "请先点左侧的拼版页，或添加一页拼版。")
            return
        view.flush_pending()
        index = view.current_index()
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = pages[index].get("items") or []
        files = [item.get("file") for item in items]
        # 单图页（整幅/落单）只有一项：复位 = 原始尺寸、归零位（没有"并排"）
        reset = single_items(files[0]) if len(files) == 1 else default_items(files)
        if reset is None:
            self._toast(
                "error", "无法复位",
                "读不到源图尺寸（文件可能已被移动或删除）。",
            )
            return
        pages[index] = {**pages[index], "items": reset}
        if not self.task_id:
            return
        doc = self.store.load_imposition_doc(self.task_id)
        doc["pages"] = pages
        self.store.save_imposition_doc(self.task_id, doc)
        view.update_current_items(reset)
        self._schedule_imposition_compose()
        self._update_imposition_status(index)
        self.log_view.append(f"第 {index + 1} 页拼版已复位为默认并排版面。")

    def _on_imposition_delete_item(self) -> None:
        """「删除选中图片」（面板）：把画布里选中的那张图从本页删掉。

        **页保留**——剩一张时面板会自动出现「新增图片」可以再补一张；**删到
        最后一张则整页移除**（空页没有意义，与左列「✕」释放同款语义——全部
        页删光即视为未生效，取图回退去底色；2026-09-30 用户定：整页移除前
        要弹确认框）。被删的图不再被任何页引用，
        即自动回到「未选择列表」（下次「选择拼版」或「新增图片」都能再选它）。
        落盘走 ``_save_imposition_pages``：画布重灌会清空选中，「当前图片样式」
        区随之灰掉。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            self._toast("info", "没有拼版页", "请先点左侧的拼版页，或添加一页拼版。")
            return
        view.flush_pending()
        index = view.current_index()
        slot = view.selected_slot()
        if slot < 0:
            self._toast("info", "没有选中的图片", "先在画布里点选要删除的图片。")
            return
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = [dict(item) for item in pages[index].get("items") or []]
        if not 0 <= slot < len(items):
            return
        removed = items.pop(slot)
        if not items:
            # 本页最后一张：页会跟着一起删（2026-09-30 用户定：要确认）。
            # 此刻还没动任何状态（items 是副本），取消直接返回即可。
            from qfluentwidgets import Dialog

            dialog = Dialog(
                "删除图片",
                f"「{Path(removed['file']).stem}」是本页最后一张图片，"
                "删除后整页拼版将一并移除。\n是否继续？",
                self.window(),
            )
            dialog.yesButton.setText("删除")
            dialog.cancelButton.setText("取消")
            if not dialog.exec():
                return
        if items:
            pages[index] = {**pages[index], "items": items}
        else:
            # 单图页删掉最后一张：页一并删除（空页没有意义），与左列
            # 「✕」释放同款语义——视为未生效，取图来源回退去底色
            pages.pop(index)
        self._save_imposition_pages(pages)
        view.set_current(min(index, len(pages) - 1))
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )
        if items:
            self.log_view.append(
                f"已删除{cn_page_label(index)}选中的图片"
                f"「{Path(removed['file']).stem}」，回到未选择列表。"
            )
        else:
            self.log_view.append(
                f"已删除{cn_page_label(index)}最后一张图片"
                f"「{Path(removed['file']).stem}」，本页没有图了，整页移除"
                f"（源图回到未选择列表）。"
            )

    # ------------------------------------------------------------- 双击预览
    def _open_imposition_item_preview(self, slot: int) -> None:
        """画布**双击某张图**：弹窗预览这张原图（弹窗里 ←/→ 可翻本页另一张）。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        current = view.current_index()
        self._open_imposition_zoom(
            lambda index: self._imposition_item_target(current, index), slot
        )

    def _open_imposition_spread_preview(self) -> None:
        """画布**双击空白处**：弹窗预览整页左右组合（按产出口径合成的效果）。"""
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
            self._imposition_zoom_dialog = ImageZoomDialog(
                self.window() or self, factory=factory
            )
        dialog = self._imposition_zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        # （ImageZoomDialog 渲染走自己的 worker 线程，不占界面）
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(factory=factory, index=index)

    def _imposition_item_target(self, page_index: int,
                                slot: int) -> "object | None":
        """弹窗「**单张原图**」来源：``slot`` 即弹窗页码（0 右槽 / 1 左槽）。"""
        from desktop.workers import PreviewWorker
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget

        pages = self._imposition_pages()
        if not 0 <= page_index < len(pages):
            return None
        items = pages[page_index].get("items") or []
        if not 0 <= slot < len(items):
            return None
        path = Path(str(items[slot].get("file") or ""))
        if not path.exists():
            return None
        side = "右侧" if slot == 0 else "左侧"
        return ZoomTarget(
            render=lambda edge, p=path: PreviewWorker(p, longest_edge=edge),
            note=f"{cn_page_label(page_index)} · {side}「{path.name}」",
            stem=path.stem,
            count=len(items),
        )

    def _imposition_spread_target(self, page_index: int) -> "object | None":
        """弹窗「**整页左右组合**」来源：构造时快照版面，合成在 worker 线程。"""
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
        return ZoomTarget(
            render=lambda edge,
            page={"items": items}: ImpositionPagePreviewWorker(page, edge),
            note=f"{cn_page_label(page_index)} 左右组合（左「{left}」+ 右「{right}」）",
            stem=f"imposition-{page_index + 1:02d}",
            count=1,
        )

    def close_imposition_zoom_popup(self) -> None:
        """关掉拼版预览弹窗（内容失效时调：切任务等）。"""
        dialog = getattr(self, "_imposition_zoom_dialog", None)
        if dialog is not None:
            dialog.close()

    # ------------------------------------------------------------- 版面落盘
    def _on_imposition_slot_selected(self, _slot: int) -> None:
        """画布里选中了右槽/左槽/无：刷新状态行。"""
        view = getattr(self, "imposition_view", None)
        if view is not None:
            self._update_imposition_status(view.current_index())

    def _on_imposition_items_changed(self, index: int, items: list) -> None:
        """版面被拖动/缩放/旋转：落盘 + 重新合成（防抖）。"""
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        pages[index] = {**pages[index], "items": [dict(item) for item in items]}
        if not self.task_id:
            return
        doc = self.store.load_imposition_doc(self.task_id)
        doc["pages"] = pages
        self.store.save_imposition_doc(self.task_id, doc)
        self._schedule_imposition_compose()
        self._update_imposition_status(index)

    def _update_imposition_status(self, index: int) -> None:
        """状态行：当前页 + 选中槽位 + 生效与否。"""
        label = getattr(self, "imposition_panel_status", None)
        if label is None:
            return
        pages = self._imposition_pages()
        # 「新增图片」只在单图页出现（2026-09-30 用户定）——面板按钮显隐
        # 搭状态行这趟车一起同步（状态行是"当前页变了"的汇聚点）
        panel = getattr(self, "imposition_panel", None)
        if panel is not None:
            single = (
                0 <= index < len(pages)
                and len(pages[index].get("items") or []) == 1
            )
            panel.set_single_page(single)
        if not pages:
            text = "尚未添加拼版页"
        else:
            view = getattr(self, "imposition_view", None)
            slot = view.selected_slot() if view is not None else -1
            slot_text = {0: "（选中：右侧）", 1: "（选中：左侧）"}.get(slot, "")
            text = f"{cn_page_label(index)} / 共 {len(pages)} 页{slot_text}"
        if self.imposition_active():
            text += "　·　拼版已生效：生成 PDF 用拼版结果"
        elif pages:
            text += "　·　拼版未生效：勾选下方开关后生成 PDF 才会用拼版结果"
        label.setText(text)
        # 状态行是所有"当前页/选中变了"路径的汇聚点，旋转组件的回填搭这趟车
        self._sync_imposition_rotation_ui()

    # ------------------------------------------------------------- 合成落盘
    def _schedule_imposition_compose(self) -> None:
        """版面/页数变化 → 防抖后**后台**把拼版页重写到 stages/imposition。"""
        if not getattr(self, "task_id", None):
            return
        self._imposition_dirty = True
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            timer.start()
        else:
            # 定时器还没建（视图未初始化）：直接同步兜底，别让改动悬着
            self._compose_imposition_now()

    def _init_imposition_compose(self) -> None:
        """建防抖定时器（页面构造期一次）。"""
        self._imposition_dirty = False
        self._imposition_composing = False
        self._imposition_timer = QTimer(self)
        self._imposition_timer.setSingleShot(True)
        self._imposition_timer.setInterval(COMPOSE_DEBOUNCE_MS)
        self._imposition_timer.timeout.connect(self._compose_imposition_async)
        # 旋转组件的停顿提交计时器（滑块连续吐增量期间只转画布，停手才落盘）
        self._imposition_edit_timer = QTimer(self)
        self._imposition_edit_timer.setSingleShot(True)
        self._imposition_edit_timer.setInterval(EDIT_COMMIT_DEBOUNCE_MS)
        self._imposition_edit_timer.timeout.connect(self._commit_imposition_edit)

    def _compose_imposition_async(self) -> None:
        """后台合成（不阻塞界面）：拖动版面时会被反复触发。"""
        if not self.task_id:
            return
        if self._imposition_composing:
            return  # 上一批还在跑；跑完会看 _imposition_dirty 再补一次
        doc = self._imposition_doc()
        out_dir = self.store.imposition_output_dir(self.task_id)
        self._imposition_dirty = False
        self._imposition_composing = True
        from desktop.workers import ImpositionComposeWorker, connect_queued

        self.run_worker(
            lambda: ImpositionComposeWorker(doc, out_dir),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished, self._on_imposition_composed, thread
                ),
                connect_queued(
                    self, worker.failed, self._on_imposition_compose_failed, thread
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_imposition_composed(self, _out_dir: str, _count: int) -> None:
        """后台合成完成（主线程）：解除忙标记，必要时补一轮。"""
        self._imposition_composing = False
        if self._imposition_dirty:
            self._imposition_timer.start()
            return
        self._refresh_print_source()

    def _on_imposition_compose_failed(self, message: str) -> None:
        self._imposition_composing = False
        self.log_view.append(f"拼版合成失败：{message}")
        self._toast("error", "拼版合成失败", message)

    def _compose_imposition_now(self) -> None:
        """同步合成（**只在生成 PDF 前调用**：保证 PDF 用的一定是最新版面）。

        平时走后台防抖合成；用户在拼版页改完立刻去第四步点「生成 PDF」时，
        后台那一轮可能还没跑完/还没触发——这里补一次同步的，宁可等一下也不能
        让 PDF 用旧版面。
        """
        if not self.task_id or not self.imposition_active():
            return
        from desktop.services.imposition import compose_doc

        try:
            compose_doc(
                self._imposition_doc(),
                self.store.imposition_output_dir(self.task_id),
            )
        except Exception as exc:  # noqa: BLE001 - 合成失败不该拦住后续提示
            self.log_view.append(f"拼版合成失败：{exc}")
        self._imposition_dirty = False
