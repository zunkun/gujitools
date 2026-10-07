# -*- coding: utf-8 -*-
"""``RembgPreviewWidget`` Mixin：**条目构建**。

把「原图 + 结果 + 实时合成」拼成条目（含尺寸键、联合框）。（从 ``rembg_viewer.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from desktop.components.viewers.thumb_strip import ThumbStrip
from core.command_spec import WHOLE_PAGE_AREA
from utils.box_geometry import is_full_content
from utils.sort_utils import pdf_custom_sort_key
from typing import TYPE_CHECKING


def _union_box(valid: list) -> list:
    """多个框的外接矩形（整页模式下把用户画的多个框合成一个整体）。"""
    return [
        min(b[0] for b in valid), min(b[1] for b in valid),
        max(b[2] for b in valid), max(b[3] for b in valid),
    ]


if TYPE_CHECKING:
    from ._host import RembgViewerHost
else:
    RembgViewerHost = object


class EntriesMixin(RembgViewerHost):
    """把「原图 + 结果 + 实时合成」拼成条目（含尺寸键、联合框）。"""

    # ------------------------------------------------------------------ 条目
    def _build_entries(self) -> list[dict]:
        """manifest 路径 → 输出条目。

        area=1 时每框一条（左右身份来自存储的 [左框, 右框] 列表，缺失为 null）；
        全部条目最终按 CLI 规范（utils/sort_utils.pdf_custom_sort_key）排序：
        同页编号 r 在 l 前，页码数字感知排序。

        ``full`` 标记整幅内容(fullcontent)的**单槽**条目——框原样下传
        （area=4 保留整页、1/2/3 统一合并语义，见
        utils.box_geometry.whole_page_box 与 preview_worker 的 full 语义）。
        """
        entries: list[dict] = []
        for path in self._paths:
            path_text = str(path)
            stem = path.stem
            page_entries = None
            if self._boxes_provider and self._region_params_provider:
                try:
                    boxes = self._boxes_provider(path_text) or []
                    area, _border = self._region_params_provider()
                    valid = [b for b in boxes if b]
                    full = is_full_content(boxes)
                    if area == 1 and len(valid) == 2:
                        # 右框在前（古籍阅读顺序：r → l）
                        page_entries = [
                            {"label": f"{stem}-r", "path": path_text,
                             "box": valid[1], "boxes": [valid[1]], "parea": 1,
                             "full": False},
                            {"label": f"{stem}-l", "path": path_text,
                             "box": valid[0], "boxes": [valid[0]], "parea": 1,
                             "full": False},
                        ]
                    elif area == 1 and len(valid) == 1:
                        # 半幅漏检一侧：label 同样带 -l/-r（看原始槽位，与提交
                        # 产物命名一致，见 print_plan.plan_rembg_submit_entries）；
                        # 整幅(full)单槽不带后缀。
                        single_label = stem
                        if not full and len(boxes) == 2:
                            single_label = f"{stem}-l" if boxes[0] else f"{stem}-r"
                        page_entries = [
                            {"label": single_label, "path": path_text, "box": valid[0],
                             "parea": 1, "full": full}
                        ]
                    elif area in (2, 3) and len(valid) == 2:
                        union = [min(b[0] for b in valid), min(b[1] for b in valid),
                                 max(b[2] for b in valid), max(b[3] for b in valid)]
                        # ⚠️ parea 必须是**原始 area**、boxes 必须是**原始框**：
                        # 只给并集框 + area=1 会在 border 为空时把整页画布
                        # （area=2/3 的语义）退化成紧裁，与预览不一致。
                        page_entries = [
                            {"label": stem, "path": path_text, "box": union,
                             "boxes": list(valid), "parea": area, "full": False}
                        ]
                    elif area in (2, 3) and len(valid) == 1:
                        # 单框：半幅→对称画布；整幅(full)→框原样下传（合并语义、不镜像）
                        page_entries = [
                            {"label": stem, "path": path_text, "box": valid[0],
                             "boxes": list(valid), "parea": area, "full": full}
                        ]
                    elif area == WHOLE_PAGE_AREA and valid:
                        # 整页模式：整页（或用户手画的框）作为一个整体，不拆左右页
                        page_entries = [
                            {"label": stem, "path": path_text,
                             "box": _union_box(valid), "boxes": list(valid),
                             "parea": area, "full": False}
                        ]
                except Exception:
                    page_entries = None
            if not page_entries:
                page_entries = [{"label": stem, "path": path_text, "box": None,
                                 "full": False}]
            entries.extend(page_entries)
        entries.sort(key=lambda e: pdf_custom_sort_key(e["label"]))
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


    def _result_full_image(self, entry: dict | None = None,
                           include_live: bool = True) -> Path | None:
        """某条目的去底色结果图。

        ``include_live=True``（默认，**显示口径**）：**实时暂存优先**，其次
        「生成预览」的正式产物——实时暂存才是"此刻参数下"的样子。
        ``include_live=False``（**编辑回写口径**）：只认正式产物
        （``stages/rembgpreview``）——实时暂存是系统临时文件，改了会被下一次
        实时预览覆盖，也不进「提交本次任务」，写回它等于"改了不生效"。
        """
        entry = entry if entry is not None else self._current_entry()
        if not entry:
            return None
        stem = Path(entry["path"]).stem
        bases = (self._live_dir, self._rembg_dir) if include_live else (
            self._rembg_dir,
        )
        for base in bases:
            if not base:
                continue
            for ext in ("png", "jpg", "jpeg"):
                candidate = base / f"{stem}.{ext}"
                if candidate.exists():
                    return candidate
        return None


    def _resolve_source(self, entry: dict) -> tuple:
        """条目 → (显示源, 区域合成参数, 是否有去底色结果, 错误文案)。

        ⚠️ 主预览（:meth:`_load_display`）与放大弹窗（:meth:`_zoom_target`）**共用
        这一份**：区域规则（area/border/单框/整页 + 实时暂存优先）只写一次，
        两处各写一份必然漂移，用户就会看到"弹窗里和预览里不是同一块"。
        """
        path_text = entry["path"]
        effect = None
        if self._boxes_provider and self._region_params_provider:
            try:
                area, border = self._region_params_provider()
                if entry.get("box") is not None and area == 1:
                    # area=1 单框条目：显示"该文本框 + border"区域。
                    # ⚠️ full 必须原样带上：整幅框不镜像（合成层的唯一特殊
                    #    行为），漏了它半幅镜像规则会误作用到整幅框上。
                    effect = {"boxes": [entry["box"]], "area": 1,
                              "border": border,
                              "full": bool(entry.get("full"))}
                else:
                    raw = self._boxes_provider(path_text) or []
                    effect = {
                        "boxes": raw,
                        "area": area,
                        "border": border,
                        # 整幅框原样下传（area=4 才归一整页）
                        "full": is_full_content(raw),
                    }
            except Exception as exc:  # 参数计算失败时退化为整图显示
                return None, None, False, f"区域计算失败：{exc}"
        result_img = self._result_full_image(entry)
        show_result = self._mode == "result" and result_img is not None
        # show_result 已蕴含 result_img 非 None，这里再判一次让类型收窄到 Path
        source = result_img if (show_result and result_img is not None) else Path(path_text)
        if not source.exists():
            return None, None, result_img is not None, "暂无图片"
        return source, effect, result_img is not None, ""
