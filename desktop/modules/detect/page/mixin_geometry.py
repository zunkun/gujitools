# -*- coding: utf-8 -*-
"""检测文本框独立页的尺寸、整本书判定与画框（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

import PySide6.QtCore as QtCore
import PySide6.QtGui as QtGui

from desktop.components.box_kinds import manual_hint_text
from desktop.components.viewers.image_view import box_names
from utils.book_layout import full_to_half_slots, profile_book
from utils.box_geometry import half_slots, is_full_content


class GeometryMixin:
    """图片尺寸/页宽缓存、整本书形态判定与查看器画框。"""

    # ------------------------------------------------------------------ 画框
    def _image_size(self, path_text: str) -> tuple[int, int]:
        """图片**原始**尺寸 (w, h)。

        ⚠️ 必须是原始像素尺寸，不是预览里被降采样后的尺寸——框坐标以原始像素为
        基准，给错基准框就会整体偏移（``ImageView._update_mapping`` 的注释同此）。
        ``QImageReader.size()`` 只读图片头，不解码，够快。
        """
        size = QtGui.QImageReader(str(path_text)).size()
        if size.isValid() and size.width() > 0:
            return size.width(), size.height()
        return 0, 0

    def _page_width(self, path_text: str) -> int:
        """该页原始像素宽度（整本书判据用）；取不到给 0＝不参与单宽框判定。

        结果按 stem 缓存：``_image_size`` 每次都要 ``QImageReader`` 读文件头，
        而整本书判定要遍历全部页面，反复读纯属浪费。
        """
        key = Path(path_text).stem
        if key in self._widths:
            return self._widths[key]
        try:
            width = int(self._image_size(path_text)[0])
        except Exception:  # noqa: BLE001 - 取不到宽度按"无页宽"保守处理
            width = 0
        self._widths[key] = width
        return width

    def _corrected_slots_map(self) -> dict:
        """**显示/导出**用的槽位表：整幅其实像半幅的页按半幅（人工框原样）。

        与 :meth:`_apply_boxes` 的判据同源（``full_to_half_slots`` + 全书宽度
        基线）。导出坐标/标注图必须用它，否则会出现"屏幕上是半幅、导出的
        boxes.json 却是整幅"的两套口径。
        """
        half_width = getattr(self, "_half_width_median", None)
        if half_width is None:
            return dict(self._boxes)
        out: dict[str, list] = {}
        for stem, slots in self._boxes.items():
            if self._origins.get(stem, "auto") == "manual":
                out[stem] = list(slots)
                continue
            width = self._widths.get(stem, 0)
            if width:
                corrected = full_to_half_slots(slots, width, half_width)
                out[stem] = corrected if corrected != slots else list(slots)
            else:
                out[stem] = list(slots)
        return out

    def _refresh_book_layout(self) -> None:
        """重算**整本书**的形态判定，并同步给预览控件（决定「半幅」标注）。

        ⚠️ 判据本体在 ``utils/book_layout.profile_book``：它要的是"整本书长什么
        样"——单页分不出「一栏横跨整页」与「真双栏书漏检一侧」。本方法只负责
        取数（每页槽位 + 页宽）与转发。
        """
        paths = {Path(p).stem: str(p) for p in self.source_images()}
        pages = [
            (stem, slots, self._page_width(paths.get(stem, stem)))
            for stem, slots in self._boxes.items()
        ]
        profile = profile_book(pages)
        # 「整幅其实像半幅」的显示修正要用整本书的宽度基线（见 _apply_boxes）。
        self._half_width_median = profile.half_width_median
        setter = getattr(self.viewer, "set_single_column", None)
        if callable(setter):
            setter(bool(profile.single_column_book))

    def _mark_layout_dirty(self) -> None:
        """把"整本书判定"标脏并起一次节流（到期重算 + 回填当前页）。

        ⚠️ 只用于**增量检测期间**的逐页事件：整本书判定随页数累积而变，但每来
        一页就全表重算一次是 O(N²)（见 ``_LAYOUT_UI_MS``）。
        """
        self._layout_dirty = True
        self._layout_timer.start(self._LAYOUT_UI_MS)

    def _refresh_layout_now(self) -> None:
        """**立即**重算整本书判定（不走节流）。

        "错一拍就是错的"的时刻用它：用户改框（要当场看到标注变成左/右/整幅）、
        检测收尾、换源。
        """
        if self._layout_timer.isActive():
            self._layout_timer.stop()
        self._layout_dirty = False
        self._refresh_book_layout()

    def _flush_layout_ui(self) -> None:
        """节流到期：重算整本书判定，并把当前页重画一遍。

        ⚠️ 必须重画当前页：判定结论（``single_column``）变了，同一页的框标注
        会跟着从「左框/右框」变成「半幅」（或反过来），不重画屏幕就停在旧标签上
        （见 ``_apply_boxes`` 里的 ``box_names``）。
        """
        if not self._layout_dirty:
            return
        self._refresh_layout_now()
        self._apply_boxes(
            str(self.viewer.current_path() or ""),
            selected=self.viewer.selected_index(),
        )

    def _apply_boxes(self, path_text: str, selected: int = -1) -> None:
        """把某一页的槽位结果画到查看器上（命名/配色由控件按位置现算）。"""
        if not path_text:
            return
        size = self._image_size(path_text)
        key = Path(path_text).stem
        slots = self._boxes.get(key, [])
        # 全书统计判定「这页的整幅其实像半幅」→ 按半幅显示（用户 2026-10-26，
        # 任务 0023）；人工框不参与，避免用户显式改的类型被自动翻回去。
        half_width = getattr(self, "_half_width_median", None)
        if (
            half_width is not None
            and size
            and size[0] > 0
            and self._origins.get(key, "auto") != "manual"
        ):
            corrected = full_to_half_slots(slots, size[0], half_width)
            if corrected != slots:
                slots = corrected
        shown = [b for b in slots if b]
        full = is_full_content(slots)
        # ⚠️ 单栏书里横跨整页的那个框叫「半幅」，不是左框/右框——整本书的结论
        #    来自 _refresh_book_layout（见 profile_book）。用户在半幅页上指定过
        #    左右时用指定值（优先级见 box_styles）。
        side = self._sides.get(Path(path_text).stem)
        setter = getattr(self.viewer, "set_side_override", None)
        if callable(setter):
            setter(side)
        names = box_names(
            shown, size, full, self.viewer.single_column(), side
        )
        if not shown:
            info = "未检测到文本框"
        else:
            info = "  ｜  ".join(
                f"{names[i]}({b[0]},{b[1]},{b[2]},{b[3]})"
                for i, b in enumerate(shown)
            )
        self.viewer.apply_boxes(
            shown, QtCore.QSize(size[0], size[1]), info, full=full, selected=selected
        )
        # 顶部红框提示（用户 2026-11-12，"能手动改框"的可发现性）：文案与任务
        # 流程第二步共用 ``box_kinds.manual_hint_text``。本页是"单机版检测"，
        # 一直走自动识别口径（``manual=False``）。
        setter = getattr(self.viewer, "set_hint_banner", None)
        if callable(setter):
            setter(manual_hint_text(has_boxes=bool(shown)))

    @staticmethod
    def _manual_slots(boxes, size, full: bool) -> list:
        """用户画出来的扁平框列表 → **槽位表示**（与任务流程第二步同规则）。

        规则本体在 ``utils.box_geometry``：整幅恒 1 槽、半幅恒 2 槽（``half_slots``）。
        ⚠️ 单独抽出成静态方法纯粹为了可测：它不碰任何控件状态。

        ``full`` 是查看器当前的「整幅」标志（用户显式选的类型，不靠框个数推断）。
        半幅情境下即使只剩 1 个框也走 ``half_slots`` 补成 2 槽——否则那个框会被
        ``is_full_content`` 当成整幅，正是用户报过的"删掉整幅框后右边的框自动变成
        整幅"。整幅却拿到多个框（不该发生，控件侧按 max_boxes 拦过）时同样按半幅
        存：宁可形态变半幅，也不能悄悄丢掉用户画出来的框。
        """
        normalized = [[int(round(float(v))) for v in box] for box in boxes]
        if not normalized:
            return []
        if full and len(normalized) == 1:
            return [normalized[0]]
        return half_slots(normalized, size)
