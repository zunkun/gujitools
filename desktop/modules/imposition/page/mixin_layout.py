# -*- coding: utf-8 -*-
"""独立拼图页的版面改动、旋转提交与面板回填（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from desktop.services.imposition import cn_page_label, page_source_stems


class LayoutMixin:
    """画布版面写回、缩略图脏页、旋转防抖与面板状态同步。"""

    # ------------------------------------------------------------------ 版面
    def _on_items_changed(self, index: int, items: list) -> None:
        """画布改了当前页版面：写回文档（内存态）+ 攒一拍单页缩略图重合成。

        ⚠️ 顺带**作废这一页的手改记录**（``edited_file``）：版面一变，导出时
        会按新版面重新合成，手改的那张图已经不代表这一页了。

        缩略图（用户 2026-10-09）：拖动/缩放/旋转停手后，左列那条缩略图
        不能停在旧版面——页号攒进 ``_thumb_dirty_pages``，防抖
        (:data:`THUMB_REFRESH_DEBOUNCE_MS`) 到期单页重合成（拖动中签名
        每帧都在变，等真的停手了再合成一次就够）。
        """
        pages = self._doc.get("pages") or []
        if 0 <= index < len(pages):
            pages[index]["items"] = list(items)
            self._drop_page_override(index)
            self._thumb_dirty_pages.add(int(index))
            self._thumb_timer.start()
        self._refresh_panel()  # 拖动/旋转落定后回填面板角度与按钮显隐

    def _refresh_dirty_page_thumbs(self) -> None:
        """防抖到期：把攒下的那几页**单页**重生成缩略图实体并贴回左列。"""
        dirty, self._thumb_dirty_pages = self._thumb_dirty_pages, set()
        if not dirty:
            return
        pages = self._doc.get("pages") or []
        self._page_thumb_manager().invalidate(sorted(dirty), pages)

    def _drop_page_override(self, index: int, reason: str = "版面已改动") -> None:
        """丢掉第 ``index`` 页的整页手改记录（有的话写一句日志）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        if pages[index].pop("edited_file", None) is not None:
            self.log(
                f"{cn_page_label(index)}{reason}，之前对整页组合的手工修饰作废；"
                "导出时按当前版面重新合成。"
            )

    def _on_whole_rotate(self, delta: float) -> None:
        """「整体旋转」组件吐了增量：绕两图公共中心转（停手后统一提交）。

        与任务流程的 ``_on_imposition_whole_rotate`` 同口径：滑块连续吐增量
        期间只重绘不上报（``rotate_whole`` 只标脏），由
        :data:`_rotate_commit_timer` 在停手后 flush + 重适配 + 回填面板。
        """
        if self.view.current_index() < 0 or not self.view.canvas.has_items():
            return
        self.view.canvas.rotate_whole(delta)
        self._rotate_commit_timer.start()

    def _commit_rotation_edit(self) -> None:
        """旋转组件停手到期：把画布改动补报出去 + 重适配 + 回填面板。"""
        self.view.canvas.flush_pending()  # → items_changed → 写回文档+缩略图防抖
        # 整版转过后外接框变了：重新适配可视区（与任务流程同一行为）
        self.view.canvas.refit()
        self._refresh_panel()

    def _on_item_rotate(self, angle: float) -> None:
        """把**当前编辑目标**设为绝对旋转角（顺时针，度；停手后统一提交）。

        面板的旋转控件随画布选择状态切换目标：未选中时发整版增量
        （``_on_whole_rotate``），选中某张图后发该图的绝对角度（本方法）。
        """
        if self.view.current_index() < 0 or self.view.selected_slot() < 0:
            return  # 没有选中图时面板处于整版模式，不会走到这里；防御一下
        self.view.canvas.set_item_rotation(angle)
        self._rotate_commit_timer.start()

    def _refresh_panel(self) -> None:
        """把画布当前状态回填到右侧面板（状态文案 + 旋转组件 + 按钮显隐）。

        与任务流程的 ``_sync_imposition_rotation_ui`` + 单图页判定同口径：
        整版角度=平均角；**选中某张图后同一组旋转控件切换到该图**并回填
        其角度（未选中则恢复整版），「删除选中图片」随选中显隐；单图页才
        露出「新增图片」。回填走 blockSignals 语义（panel 内部挡信号），
        不会把同步误当成用户输入。
        """
        panel = self.panel
        label = panel.status_label
        pages = self._doc.get("pages") or []
        index = self.view.current_index()
        canvas = self.view.canvas
        if not pages or index < 0 or not canvas.has_items():
            panel.set_page_available(False)
            panel.set_whole_angle(0.0)
            panel.set_item_rotation(None)
            panel.set_single_page(False)
            if not pages or index < 0:
                label.setText("还没有拼版页")
            return
        panel.set_page_available(True)
        panel.set_whole_angle(canvas.spread_rotation() or 0.0)
        panel.set_item_rotation(
            canvas.selected_rotation() if canvas.selected() >= 0 else None
        )
        stems = page_source_stems(pages[index])
        panel.set_single_page(len(stems) == 1)
        if len(stems) == 1:
            label.setText(f"{cn_page_label(index)}　·　整幅「{stems[0]}」")
        else:
            label.setText(
                f"{cn_page_label(index)}　·　右「{stems[0]}」　左「{stems[1]}」"
            )
