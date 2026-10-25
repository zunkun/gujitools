# -*- coding: utf-8 -*-
"""``RembgPreviewWidget`` Mixin：**条目构建**。

把「原图 + 结果」拼成条目（从 ``rembg_viewer.py`` 拆出，2026-10-07）。
2026-10-22 起没有 area：检测出几个框就是几条条目，每条对应一张裁好的图。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from desktop.components.viewers.thumb_strip import ThumbStrip
from utils.book_layout import full_to_half_slots, half_width_median, page_single_wide_slots
from utils.box_geometry import is_full_content
from utils.sort_utils import natural_sort_key
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import RembgViewerHost
else:
    RembgViewerHost = object


class EntriesMixin(RembgViewerHost):
    """把「原图 + 结果」拼成条目（含尺寸键、检测框）。"""

    def _book_slots(self, path_text: str, boxes: list) -> list:
        """**页级**归一化本页槽位（单个宽框＝半幅，按整幅语义命名）。

        ⚠️ 规则本体在 ``utils.book_layout.page_single_wide_slots``——**预览与
        提交派生必须用同一个函数**，否则第三步显示 ``0007-l``、成品却叫
        ``0007.png``，用户改参数重提交时完全无从判断哪边对。

        ⚠️ 用户 2026-10-23（任务 0004）：判据是**页级**的，不再依赖整本书是不是
        单栏书——一页只有一个 ``harfcontent``、框宽 >60% 时中心位置没有鉴别力，
        必然是半幅，按位置拆 ``-l``/``-r`` 基本是随机的。

        ⚠️ **用户指定过左右**的页不归一化：那是在说"这页其实是某一边"
        （半幅中心压在中线上，位置判定没意义），命名要按 ``-l``/``-r`` 走。
        """
        if not boxes:
            return boxes
        if self._side_for is not None:
            try:
                if self._side_for(path_text):
                    return boxes
            except Exception:  # noqa: BLE001 - 读不到指定就按常规归一化
                pass
        width = None
        if self._page_width_provider is not None:
            try:
                width = self._page_width_provider(path_text)
            except Exception:  # noqa: BLE001 - 取不到页宽＝保守不改写
                width = None
        return page_single_wide_slots(boxes, width)

    def _demoted_slots(self) -> dict:
        """全书统计修正：整幅框几何像半幅的页 → 改写后的 2 槽槽位。

        与提交派生用**同一个函数**（``full_to_half_slots``），否则预览会显示
        ``0007``、成品却是半幅身份，两边对不上。没有 boxes/页宽提供者时
        直接返回空（如第三步：查看器按"一张输入图 = 一个条目"显示整图）。
        """
        if not self._paths or not self._boxes_provider or not self._page_width_provider:
            return {}
        pages = []
        for path in self._paths:
            text = str(path)
            try:
                width = self._page_width_provider(text)
            except Exception:  # noqa: BLE001 - 取不到页宽＝该页不参与基线
                width = None
            try:
                boxes = list(self._boxes_provider(text) or [])
            except Exception:  # noqa: BLE001 - 取不到框＝该页不参与
                boxes = []
            pages.append((Path(text).stem, boxes, width))
        baseline = half_width_median(pages)
        if baseline is None:
            return {}
        demoted: dict = {}
        for stem, boxes, width in pages:
            corrected = full_to_half_slots(boxes, width, baseline)
            if corrected != boxes:
                demoted[stem] = corrected
        return demoted

    # ------------------------------------------------------------------ 条目
    def _build_entries(self) -> list[dict]:
        """manifest 路径 → 输出条目：**每个检测框一条**。

        左右身份来自存储的 [左框, 右框] 列表（缺失为 null）；
        全部条目最终按 CLI 规范（utils.sort_utils.natural_sort_key）排序：
        同页编号 r 在 l 前，页码数字感知排序。

        ``full`` 标记整幅内容(fullcontent)的**单槽**条目——label 用页名，
        不带 ``-l``/``-r`` 后缀。
        """
        entries: list[dict] = []
        demoted = self._demoted_slots()
        for path in self._paths:
            path_text = str(path)
            stem = path.stem
            page_entries = None
            if self._boxes_provider:
                try:
                    raw_boxes = self._boxes_provider(path_text) or []
                    if stem in demoted:
                        raw_boxes = demoted[stem]
                    boxes = self._book_slots(path_text, raw_boxes)
                    valid = [b for b in boxes if b]
                    full = is_full_content(boxes)
                    if len(valid) == 2:
                        # 右框在前（古籍阅读顺序：r → l）
                        page_entries = [
                            {"label": f"{stem}-r", "path": path_text,
                             "box": valid[1], "boxes": [valid[1]], "full": False},
                            {"label": f"{stem}-l", "path": path_text,
                             "box": valid[0], "boxes": [valid[0]], "full": False},
                        ]
                    elif len(valid) == 1:
                        # 半幅漏检一侧：label 同样带 -l/-r（看原始槽位，与提交
                        # 产物命名一致，见 print_plan.plan_detect_submit_entries）；
                        # 整幅(full)单槽不带后缀。
                        single_label = stem
                        if not full and len(boxes) == 2:
                            single_label = f"{stem}-l" if boxes[0] else f"{stem}-r"
                        page_entries = [
                            {"label": single_label, "path": path_text, "box": valid[0],
                             "full": full}
                        ]
                except Exception:
                    page_entries = None
            if not page_entries:
                page_entries = [{"label": stem, "path": path_text, "box": None,
                                 "full": False}]
            entries.extend(page_entries)
        entries.sort(key=lambda e: natural_sort_key(e["label"]))
        return entries

    def _rebuild_entries(self, force_strip: bool = False) -> None:
        entries = self._build_entries()
        # 标题 = 排序后的序号（1,2,3…）；原 label 保留用于选中恢复
        for index, entry in enumerate(entries):
            entry["title"] = str(index + 1)
        keep_label = None
        current = self._current_entry()
        if current:
            keep_label = current.get("label")
        labels_changed = [e["label"] for e in entries] != [
            e["label"] for e in self._entries
        ]
        self._entries = entries
        if not (labels_changed or force_strip):
            return
        # 条目集合/身份变了：弹窗按"打开时的条目"取源，留着就是旧数据/错位
        self.close_zoom_popup()
        self.strip.clear()
        if not entries:
            self.strip.add_placeholder("暂无图片")
            return
        for entry in entries:
            self.strip.add_page_item(entry["title"], entry["path"])
        self._load_page_thumbs(entries)
        # 尽量保持原选中条目（按原始 label 匹配）
        if keep_label:
            for row in range(self.strip.count()):
                if self._entries[row].get("label") == keep_label:
                    self.strip.setCurrentRow(row)
                    break

    @staticmethod
    def _fill_icon(image: QImage) -> QImage:
        """覆盖填充到条目图标尺寸：等比放大至铺满，再居中裁掉多余部分。"""
        target = ThumbStrip.ICON_SIZE
        if image.width() >= target.width() and image.height() >= target.height():
            scaled = image
        else:
            scale = max(
                target.width() / image.width(),
                target.height() / image.height(),
            )
            scaled = image.scaled(
                round(image.width() * scale),
                round(image.height() * scale),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        x = (scaled.width() - target.width()) // 2
        y = (scaled.height() - target.height()) // 2
        return scaled.copy(max(x, 0), max(y, 0), target.width(), target.height())

    def _result_full_image(self, entry: dict | None = None) -> Path | None:
        """某条目的去底色结果图（正式成品目录 ``stages/rembg[~节点]``）。

        ⚠️ 改参数时的实时去底色**直接覆盖这份成品**（见
        ``desktop.pages.taskdetail.rembg_live``），所以这里只有一个来源，
        不存在"临时结果比成品新"的分叉。
        """
        entry = entry if entry is not None else self._current_entry()
        base = self._rembg_dir
        if not entry or not base:
            return None
        stem = Path(entry["path"]).stem
        for ext in ("png", "jpg", "jpeg"):
            candidate = base / f"{stem}.{ext}"
            if candidate.exists():
                return candidate
        return None

    def _resolve_source(self, entry: dict) -> tuple:
        """条目 → (显示源, 区域合成参数, 是否有去底色结果, 错误文案)。

        ⚠️ 主预览（:meth:`_load_display`）与放大弹窗（:meth:`_zoom_target`）**共用
        这一份**：区域规则只写一次，两处各写一份必然漂移，用户就会看到
        "弹窗里和预览里不是同一块"。
        """
        path_text = entry["path"]
        effect = None
        border = None
        if self._border_provider:
            try:
                border = self._border_provider()
            except Exception as exc:  # 参数计算失败时退化为整图显示
                return None, None, False, f"区域计算失败：{exc}"
        if entry.get("box") is not None:
            # 单框条目：显示"该文本框 + border"区域。
            effect = {"boxes": [entry["box"]], "border": border}
        result_img = self._result_full_image(entry)
        show_result = self._mode == "result" and result_img is not None
        # show_result 已蕴含 result_img 非 None，这里再判一次让类型收窄到 Path
        source = result_img if (show_result and result_img is not None) else Path(path_text)
        if not source.exists():
            return None, None, result_img is not None, "暂无图片"
        return source, effect, result_img is not None, ""
