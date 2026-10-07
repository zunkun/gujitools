# -*- coding: utf-8 -*-
"""print 预览 Mixin：**版面规划与画布**。

把打印参数解成版面计划并交给版面画布显示。（从 ``print_preview.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QImage
from utils.page_layout import plan_print_page, print_page_size_mm, resolve_title_nodes
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import PrintPreviewHost
else:
    PrintPreviewHost = object


class PrintLayoutMixin(PrintPreviewHost):
    """把打印参数解成版面计划并交给版面画布显示。"""

    # ------------------------------------------------------------------ 加载
    def _print_spec(self, index: int, path: Path) -> tuple[dict | None, str]:
        """返回 (print_spec, 提示文案)；参数非法时 spec 为 None。"""
        if self._params_provider is None:
            return None, "未接入打印参数，已显示原图"
        try:
            args = self._params_provider()
        except Exception as exc:  # 颜色/边距填了一半：不阻塞预览
            return None, f"参数暂不合法：{exc}"
        if not isinstance(args, dict):
            return None, "未接入打印参数，已显示原图"
        return (
            {
                "args": args,
                "index": index,
                "total": len(self._entries_cache),
                "name": path.stem,
                # 逐图坐标覆盖：有则预览/成品都按此框排（与 plan_print_page
                # 同源）。宿主可能在没有条目时先取 spec 校验接线，故越界给 None。
                "rect": (
                    self._entries_cache[index].get("rect")
                    if 0 <= index < len(self._entries_cache) else None
                ),
                # 解析好的标题切换节点（见 _resolved_nodes）：worker 线程
                # 拿不到条目清单，必须在这里解析好再传过去
                "nodes": self._resolved_nodes(args),
            },
            "",
        )


    # ------------------------------------------------------------------ 版面编辑
    def _page_size_mm(self) -> tuple[float, float]:
        """当前纸张尺寸（mm），由打印参数推导；非法时回落 A4 横版。"""
        provider = self._params_provider
        try:
            args = (provider() if provider is not None else None) or {}
        except Exception:
            args = {}
        return print_page_size_mm(
            args.get("paper_size", "A4"),
            args.get("orientation", "landscape"),
        )


    def _resolved_nodes(self, args: dict) -> list:
        """按 **PDF 页序（列表位置，1 起）** 解析标题切换节点（三处预览共用）。

        ⚠️ 两个都不能指望 ``plan_print_page`` 的内部兜底：它拿不到条目清单，
        用**空列表**解析节点——任何页名都匹配不到，节点永远不生效（2026-09-29
        用户实测「添加动态节点没有自动生效」）。

        ⚠️ 匹配必须用**列表位置**，不能用条目页名：rembg 条目的页名是
        extract 的原始页码，可能不从 1 起、可能有缺口（任务 0020 实测
        ``3.png..63.png``），用户填「1」想的是 **PDF 第 1 页**，按页名匹配
        永远落空 → 预览整本都是主标题（同日用户实测）。执行层
        （``run_print_stage``）把合成图按列表顺序写成 ``0001..N`` 再解析，
        语义同样是位置序号——这里必须同口径，预览与 PDF 才一致。
        """
        try:
            nodes = args.get("title_switch_nodes") or []
            if not nodes:
                return []
            stems = [str(i + 1) for i in range(len(self._entries_cache))]
            return resolve_title_nodes(stems, nodes)
        except Exception:
            return []  # 参数没填好不阻塞预览（与 _print_spec 的容错同口径）


    def _plan_for(self, index: int, path: Path, rect=None):
        """该页的完整排版几何（含标题/页码/跳过态）。

        ``rect`` 为已存的逐图坐标：传进去才能让**标题/页码也按同一份覆盖**
        算出来（它们的落点只取决于 page_margins，但 skipped/side 等仍需
        plan 给出）。返回 ``(plan, image)``，读图失败时为 ``(None, None)``。
        """
        provider = self._params_provider
        try:
            args = (provider() if provider is not None else None) or {}
        except Exception:
            args = {}
        image = QImage(str(path))
        if image.isNull():
            return None, None
        plan = plan_print_page(
            (image.width(), image.height()), args, index,
            len(self._entries_cache), image_name=path.stem,
            image_rect=rect,
            sorted_nodes=self._resolved_nodes(args),
        )
        return plan, image


    def _show_layout(self, index: int) -> None:
        """在画布上编辑第 index 页：纸 + 图片 + 标题/页码，框可拖可缩放。"""
        self.view.hide()
        self.canvas.show()
        # 「原比例缩放」决定画布手感（四角等比 vs 四角+四边自由拉伸）。
        # ⚠️ 参数可能填了一半（provider 抛 ValueError）：兜底 True，别挡住编辑。
        keep_ratio = True
        if self._params_provider is not None:
            try:
                keep_ratio = bool(
                    (self._params_provider() or {}).get("keep_ratio", True)
                )
            except Exception:
                keep_ratio = True
        if index < 0 or index >= len(self._entries_cache):
            self.canvas.set_page(*self._page_size_mm(), None,
                                 [0.0, 0.0, 0.0, 0.0], keep_ratio=keep_ratio)
            return
        self._canvas_index = index
        entry = self._entries_cache[index]
        path = Path(str(entry["file"]))
        total = len(self._entries_cache)
        pw, ph = self._page_size_mm()
        if not path.exists():
            self.canvas.set_page(pw, ph, None, [0.0, 0.0, 0.0, 0.0],
                                 keep_ratio=keep_ratio)
            self.caption.setText(f"图片不存在：{path.name}")
            return
        # 已存坐标优先；否则用当前自动排版作为初始位置（用户再微调）。
        # 两种情况都要拿到完整 plan——标题/页码属于版面，编辑器必须画出来。
        rect = entry.get("rect")
        plan, image = self._plan_for(index, path, rect)
        if plan is None:
            self.canvas.set_page(pw, ph, None, [0.0, 0.0, 0.0, 0.0],
                                 keep_ratio=keep_ratio)
            self.caption.setText(f"图片无法读取：{path.name}")
            return
        if rect is None:
            rect = list(plan.image)
        self.canvas.set_page(pw, ph, image, rect, plan, keep_ratio=keep_ratio)
        handle_hint = (
            "拖四角等比缩放，拖四边拉伸宽/高"
            if keep_ratio else
            "拖四角/四边拉伸（可改变比例）"
        )
        self.caption.setText(
            f"版面编辑 · 第 {index + 1}/{total} 页 · 拖动移动，{handle_hint}，"
            f"双击放大预览"
        )


    def _on_canvas_rect(self, rect: list) -> None:
        """画布拖拽/缩放结束：写回条目并通知宿主（落盘 + 标脏）。"""
        index = self._canvas_index
        if 0 <= index < len(self._entries_cache):
            self._entries_cache[index]["rect"] = list(rect)
        self.layout_changed.emit(index, list(rect))


    def refresh_layout(self) -> None:
        """参数（纸张/方向）变化后刷新画布：保留已存坐标，仅重算页面尺寸。"""
        if self._mode == "layout":
            self._show_layout(self._current_index())
