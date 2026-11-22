# -*- coding: utf-8 -*-
"""识别方式（自动 / 人工标注）与「沿用上一页标注」（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.pages.taskdetail.detect._host import DetectHost
else:
    DetectHost = object


class DetectModesMixin(DetectHost):
    """面板参数读取、识别方式切换落盘、上一页框的沿用。"""
    # ------------------------------------------------ 识别方式（本任务参数）
    #
    # 两个参数（``mode`` / ``reuse_prev``）都在面板上，宿主只读不存；用户改动的
    # 落盘与界面联动在 ``_on_detect_mode_changed`` / ``_on_reuse_prev_changed``。
    # ⚠️ 读面板一律走 ``peek()``：``panel_host_of_step("detect")`` 拿到的是
    # ``LazyPanelHost``，直接取属性会**立刻把面板构造出来**（惰性就白做了）。

    def _detect_panel_peek(self):
        """detect 面板现值（可能还没构造 ⇒ ``None``）。"""
        host = self.panel_host_of_step("detect")
        peek = getattr(host, "peek", None)
        return peek() if callable(peek) else host

    def _detect_arg(self, key: str, fallback):
        """读面板当前参数；面板没建/替身没有 ``get_args`` → 回落 ``fallback``。"""
        panel = self._detect_panel_peek()
        if panel is None:
            return fallback
        try:
            args = panel.get_args()
        except Exception:  # noqa: BLE001 - 取不到就按默认（自动识别）
            return fallback
        value = args.get(key)
        return fallback if value is None else value

    def _panel_is_applying(self) -> bool:
        """面板正在**程序化回填**吗（不是用户点击）。

        用来决定"这个改动要不要落盘"：回填的值本来就来自记录/历史，再写回去
        只会多一次落盘，还会在"先复位再回填"的时序里短暂写错一次。
        取不到就按 False（当用户改动处理——宁可多写一次，也别丢用户的点击）。
        """
        panel = self._detect_panel_peek()
        getter = getattr(panel, "is_applying", None)
        if not callable(getter):
            return False
        try:
            return bool(getter())
        except Exception:  # noqa: BLE001 - 取不到就按"用户改动"
            return False

    def _detect_manual(self) -> bool:
        """当前是否「人工标注」模式（面板没建 ⇒ 按默认「自动识别」处理）。"""
        return str(self._detect_arg("mode", "auto")) == "manual"

    def _reuse_prev_on(self) -> bool:
        """「自动使用上一个文本框标注」是否勾选（默认勾选）。"""
        return bool(self._detect_arg("reuse_prev", True))

    def _on_detect_mode_changed(self, mode: str) -> None:
        """用户切换识别方式 → 记住（任务级）+ 刷新底部按钮与画布提示。

        ⚠️ 切换**不动任何框**：``boxes.json`` 一个字节都不改（两种方式画的框
        在文件里同构）。人工标注只是"不再调 YOLO"，不是"清空检测结果"。
        """
        if self.task_id and not self._panel_is_applying():
            saver = getattr(self.store, "save_detect_mode", None)
            if callable(saver):
                saver(self.task_id, mode if mode in ("auto", "manual") else "auto")
        # 底部「检测文本框」显不显示由视图层按 mode 决定（它才知道那颗按钮）
        sync = getattr(self, "_sync_detect_mode_ui", None)
        if callable(sync):
            sync()
        path = self.detect_viewer.current_path()
        if path is not None:
            self._sync_box_hint(self._raw_boxes_for(str(path)))
        updater = getattr(self, "_update_submit_button", None)
        if callable(updater):
            updater(getattr(self, "running_stage", None) is not None)

    def _on_reuse_prev_changed(self, value: bool) -> None:
        """「自动使用上一个文本框标注」被切换 → 记住（任务级），无需重绘。"""
        if not self.task_id or self._panel_is_applying():
            return
        saver = getattr(self.store, "save_detect_reuse_prev", None)
        if callable(saver):
            saver(self.task_id, bool(value))

    def _inherit_boxes_from_prev(self, key: str, prev: str | None) -> bool:
        """把**上一页**的框带到本页（人工标注 + 勾选了沿用选项时）。

        三条门槛缺一不可（用户 2026-11-16）：

        1. 当前是**人工标注**且「自动使用上一个文本框标注」勾着；
        2. **上一页有标注**（至少一个真框）；
        3. **本页没有任何标注**——用户原话「不影响已经标注过的页面」，所以
           只要本页有一条框就整页跳过，**不做合并**（合并会让"删掉的框"自动
           长回来）。

        ⚠️ 同一次会话里同一页**最多带一次**（``_inherit_done``）：本页的框被
        用户删光后翻走再翻回，不该又被带一遍——否则"这一页永远删不干净"。
        换任务时这份集合在 ``set_task`` 里清空（两个任务的页名天然重复）。

        返回是否真的带过来了（调用方据此决定要不要再走一遍普通上屏）。
        """
        if not self.task_id or not prev or prev == key:
            return False
        if not self._detect_manual() or not self._reuse_prev_on():
            return False
        done = self.__dict__.get("_inherit_done")
        if done is None:
            done = self._inherit_done = set()
        if key in done:
            return False
        if self.detect_cache.get(key, []) is None:
            # 这页正在检测（占位是 None）：别抢在检测结果之前塞一份"上一页的框"，
            # 那样用户会看到画面上先冒出旧框、随后又被检测结果替换。
            return False
        if self._valid_boxes(self._raw_boxes_for(key)):
            return False
        source = self._raw_boxes_for(prev)
        if not self._valid_boxes(source):
            return False
        done.add(key)
        # origin=manual：带过来的是"用户画的框"，不能被下一次自动重检当成
        # 自动结果、也不该参与「整幅→半幅」的自动修正。
        self._store_slots(key, list(source), "manual")
        self.log_view.append(
            f"人工标注：本页没有标注，已沿用上一页（{Path(prev).stem}）的文本框"
        )
        return True
    def _unlabeled_pages(self) -> list[Path]:
        """**没画任何框**的页面清单（人工标注模式提交前查漏用，按页序）。

        ⚠️ 走 ``_boxes_map_all()`` 一次读齐：逐页 ``boxes_entry_at`` 是
        "读整份 boxes.json"×页数（320 页会把主线程卡住）。
        """
        boxes = self._boxes_map_all()
        return [
            path for path in self._manifest_paths()
            if not self._valid_boxes(boxes.get(path.stem) or [])
        ]
