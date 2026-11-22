# -*- coding: utf-8 -*-
"""检测文本框独立页的源变化、事件回调与框类型交互（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

from desktop.components.box_kinds import BoxKindEditor
from desktop.services.yolo_prewarm import request_prewarm
from utils.book_layout import is_single_wide_half
from utils.box_geometry import is_full_content, page_box_slots_from_event


class ViewMixin:
    """换源、逐页事件、结果回填与框类型人工干预。"""

    # ------------------------------------------------------------------ 回调
    def _on_source_changed(self, source) -> None:
        """换了源：**清空上一批的框**，再走基类那套显隐与副标题。

        ⚠️ 先清框再调 ``super()``：基类会 ``source_summary()`` → ``source_images()``
        并把结果灌进标题，清框必须排在前面，否则标题里的张数还是上一批的。
        """
        self._boxes.clear()
        self._origins.clear()
        self._sides.clear()           # 人工指定左右跟着换源作废
        self._widths.clear()          # 页宽缓存跟着换源作废
        self._half_width_median = None  # 全书半幅宽度基线跟着换源作废
        self._refresh_layout_now()    # 新的一批 = 新的整本书判定，别留上一批结论
        self._sync_export_buttons()
        self.viewer.select_box(-1)
        self._sync_box_kind()
        # 预览跟着换源走：检测页的左栏要**立刻**显示这批待检测的图片，
        # 缩略图走 singletask 缓存（清单仍是真实图片——画框按 stem 取键）。
        self.show_images(self.source_images())
        super()._on_source_changed(source)
        if source is None:
            return
        # 让常驻 YOLO 服务趁用户逗留时把模型先备好（重活都在服务子进程里，
        # 主线程只排个程——见 desktop.services.yolo_prewarm 的设计口径）。
        request_prewarm()

    def source_summary(self, source) -> str:
        """在共用的 ``<源> → <输出>`` 之外，**补上待检测张数**。"""
        images = self.source_images()
        tail = f"{len(images)} 张图片" if images else "未找到图片"
        return f"{source}（{tail}） → {self.control.output()}"

    def edit_effect_note(self, path: Path) -> str:
        """编辑器改了待检测的图片：框坐标以**图片原始像素**为基准。

        改了尺寸就必须重跑检测（旧框还按旧图的坐标系画，会整体偏移）；只改
        像素不改尺寸时旧框仍然对得上，所以提示里区分这两种情况而不是一律要求
        重跑。
        """
        return (
            f"已更新「{path.name}」；框坐标以图片原始像素为基准，"
            "改过尺寸请重新执行检测后再导出坐标。"
        )

    def _on_page_changed(self, index: int, path_text: str) -> None:
        """切页：先按「沿用上一页标注」补框，再把这一页的框画到大图上。

        ⚠️ ``_last_page_key`` 恒在补框**之前**更新到本页：连续切过两页都没框
        时，第三页不应该拿到第一页的框（参照页就是紧邻的上一页）。
        """
        self._carry_prev_boxes(path_text)
        self._last_page_key = Path(path_text).stem
        self._apply_boxes(path_text)

    def _on_step_event(self, name: str, payload) -> None:
        """接住 ``page_boxes``：把这一页的框收进内存（人工框优先，不被覆盖）。

        ⚠️ 事件名与任务流程第二步完全相同（``functions.detect`` 只发这一个），
        所以这里不需要认得别的名字；别的步骤将来报自己的事件也走同一条通道。
        """
        if name != "page_boxes":
            return
        key = str(payload.get("image", ""))
        slots = page_box_slots_from_event(payload)
        if not any(slots):
            return
        if self._origins.get(key) == "manual":
            return  # 人工框优先：重跑检测不许把用户改过的框冲掉
        self._boxes[key] = slots
        self._origins[key] = "auto"
        # 增量检测（逐张返回）也要重算整本书判定：它随页数累积而变化，
        # 等全部跑完再算的话，中途看到的标注会一直是左/右框。
        # ⚠️ 但**不能**每页都全表重算（O(N²)，1000 张就是主线程被拖死）——
        #    置脏 + 300ms 节流，到期重算并回填当前页（见 _flush_layout_ui）。
        self._mark_layout_dirty()

    def _on_boxes_edited(self, path_text: str, boxes) -> None:
        """用户在图上改完框：换算成槽位存下（origin=manual），并重画归一化后的形态。"""
        key = Path(path_text).stem
        slots = self._manual_slots(
            boxes, self._image_size(path_text), full=self.viewer.box_full_mode()
        )
        self._boxes[key] = slots
        self._origins[key] = "manual"
        self._sync_export_buttons()
        # 人工改动可能改变整本书的判定（如把一页的宽框缩窄）→ 先重算再重画，
        # 否则这一帧仍按旧结论标「半幅」。
        # ⚠️ 用户动作必须**立即**算（不走节流）：他正盯着这一页看结果。
        self._refresh_layout_now()
        self._apply_boxes(path_text, selected=self.viewer.selected_index())
        self._sync_box_kind()

    def on_result(self, out_dir: Path, _result: dict) -> None:
        """检测跑完：重画当前页，并把「检出几页 / 几页无框」写到状态行。

        ``out_dir`` 是输出目录（``detect`` 默认不落盘，这里只是共用控件回传的
        那个路径），导出按钮会用到它。
        """
        # 整本书的框都齐了 → 重算形态判定（决定「半幅」标注）再重画当前页
        # ⚠️ 收尾必须**立即**算：节流那次可能还没到点，而检测已经结束。
        self._refresh_layout_now()
        self._apply_boxes(
            str(self.viewer.current_path() or ""), selected=self.viewer.selected_index()
        )
        self._sync_export_buttons()
        self._sync_box_kind()
        total = len(self.source_images())
        hit = sum(1 for slots in self._boxes.values() if any(slots))
        if not hit:
            self.toast(
                "warning",
                "没有检测到内容框",
                "可能这批图不是正文页；也可以在图上手动画框后导出。",
            )
            self.status(f"共 {total} 张，都没有检出内容框", "warning")
            return
        self.status(f"共 {total} 张，{hit} 张检出内容框（可手绘修正后导出）", "success")
        self.toast("success", "检测完成", f"{hit} / {total} 张检出内容框。")

    # ------------------------------------------------- 框类型（人工干预）
    #
    # 与任务流程第二步**同一套规则**，且"怎么问用户"也只有一份——交互顺序、
    # 确认框与提示文案在 `desktop/components/box_kinds.py::BoxKindEditor`
    # （结果计算在 `utils.box_geometry` 纯函数里）；本页只提供宿主协议。

    def _current_slots(self) -> tuple[str, list]:
        """当前页的 ``(图片路径, 槽位)``；没有页时路径为空串。"""
        path = str(self.viewer.current_path() or "")
        return path, (self._boxes.get(Path(path).stem, []) if path else [])

    def _on_selection_changed(self, index: int) -> None:
        """查看器里选中态变了 → 回填「选中框类型」与删除按钮。"""
        self._sync_box_kind()

    def _sync_box_kind(self) -> None:
        """按当前选中框回填类型控件与删除按钮（无选中时三段都不高亮）。

        回填统一走共享面板的 :meth:`DetectPanel.set_box_selection`：它内部就是
        "程序化切换不发信号"的写法（不会自我递归），并且与任务详情页回填是
        **同一段实现**——面板侧怎么改，两边一起变。
        """
        index = self.viewer.selected_index()
        kinds = self.viewer.box_kinds()
        kind = kinds[index] if 0 <= index < len(kinds) else ""
        self.control.panel.set_box_selection(index, kind)

    def _on_box_kind_changed(self, kind: str) -> None:
        """用户点了「左框 / 右框 / 整幅」（交互实现委托共享 BoxKindEditor）。"""
        path_text, _slots = self._current_slots()
        if not path_text:
            return
        self._box_editor().set_kind(path_text, self.viewer.selected_index(), kind)

    # ---- BoxKindHost 协议（box_ 前缀，避免与页面其他成员撞名）----
    def _box_editor(self) -> BoxKindEditor:
        """共享交互器（无状态，按需构造）。"""
        return BoxKindEditor(self)

    def box_viewer(self):
        return self.viewer

    def box_toast(self, kind: str, title: str, content: str) -> None:
        self.toast(kind, title, content)

    def box_raw_slots(self, path_text: str) -> list:
        return list(self._boxes.get(Path(path_text).stem, []))

    def box_page_is_full(self, path_text: str) -> bool:
        return bool(is_full_content(self._boxes.get(Path(path_text).stem, [])))

    def box_image_size(self, path_text: str):
        return self._image_size(path_text) or None

    def box_commit(self, path_text: str, slots: list, select_box=None,
                   side="keep") -> None:
        """落库 + 重画；``side`` 按需写入/清除这页的人工左右指定。

        ⚠️ **先写 side、再上屏**（同任务流程那份）：``_store_slots`` →
        ``_apply_boxes`` 要读 ``_sides`` 决定标签与面板高亮。先上屏后写的话
        第一次点击读到的还是旧值 ⇒ 界面不动、得点第二次（用户 2026-10-17 报）。
        """
        if side != "keep":
            key = Path(path_text).stem
            if side in ("left", "right"):
                self._sides[key] = side
            else:
                self._sides.pop(key, None)
        self._store_slots(path_text, slots, select=select_box)

    def box_page_half_candidate(self, path_text: str) -> bool:
        """这页是否**够「半幅」**（只有一个横跨整页的框）——为真时
        左/右可由用户指定（中心压在中线上，位置判定没意义）。

        ⚠️ 页级判据（用户 2026-10-23，任务 0004）：不要求整本书是单栏书。
        """
        slots = self._boxes.get(Path(path_text).stem, [])
        return is_single_wide_half(slots, self._page_width(path_text))

    def box_confirm(self, title: str, body: str, yes_text: str, cancel_text: str) -> bool:
        # ⚠️ 延迟导入必须留在方法体内：自测靠替换 qfluentwidgets.MessageBox
        #    记录/否决确认（离屏跑弹真模态会把整个用例挂住）
        from qfluentwidgets import MessageBox  # noqa: PLC0415 - 延迟导入便于自测替换

        box = MessageBox(title, body, self.window())
        box.yesButton.setText(yes_text)
        box.cancelButton.setText(cancel_text)
        return bool(box.exec())

    def box_resync_kind(self, _index: int) -> None:
        """按现值回填类型控件高亮（类型操作结束后必调，别停在假位置）。"""
        self._sync_box_kind()

    def box_current_path_text(self) -> str:
        return str(self.viewer.current_path() or "")

    def _select_box_of_kind(self, kind: str) -> None:
        """没有选中框时，点类型＝选中该类框；该类型不存在则提示。"""
        self._box_editor().select_box_of_kind(kind)

    def _make_box_full(self, path_text: str, index: int) -> None:
        """把第 index 个框设为「整幅」（整幅与半幅互斥、一页只能一个框）。"""
        self._box_editor().make_full(path_text, index)

    def _make_box_half(self, path_text: str, index: int, kind: str) -> None:
        """把第 index 个框改成半幅（左/右）。"""
        self._box_editor().make_half(path_text, index, kind)

    def _delete_selected_box(self) -> None:
        """删除当前选中的文本框（与 Delete 键同一条路径）。"""
        self._box_editor().delete_selected()

    # ---------------------------------------------------- 「编辑」菜单（删框）
    def can_edit_delete_selected(self) -> bool:
        """「编辑 → 删除选中」：本页的“选中”指**文本框**（用户 2026-11-01 定）。

        与右栏「删除选中框」同一判据（``delete_box`` 只在有选中框时启用），
        不把整页删除混进来——本页源是用户图片清单，删页是另一套语义。
        """
        return self.delete_box.isEnabled()

    def edit_delete_selected(self) -> None:
        self._delete_selected_box()

    def _store_slots(self, path_text: str, slots: list, select=None) -> None:
        """把槽位结果写进内存表 + 重画，并同步类型控件与导出按钮。

        ``select`` 给定某个框时，重新上屏后仍选中**同一个框**（按坐标找回）
        ——切换类型/删框会改变框在列表里的次序，按下标保持会选错框。
        """
        key = Path(path_text).stem
        self._boxes[key] = slots
        self._origins[key] = "manual"
        self._sync_export_buttons()
        shown = [b for b in slots if b]
        index = -1
        if select is not None:
            target = list(select)
            index = next(
                (i for i, b in enumerate(shown) if list(b) == target), -1
            )
        self._apply_boxes(path_text, selected=index)
        self._sync_box_kind()
