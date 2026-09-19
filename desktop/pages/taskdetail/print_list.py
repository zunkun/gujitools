# -*- coding: utf-8 -*-
"""任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from desktop.services.print_plan import plan_print_entries
from desktop.utils.files import list_stage_images
from utils.sort_utils import pdf_custom_sort_key


class PrintListMixin:
    """依赖宿主页面提供的属性：store/task_id、print_preview、log_view、
    _toast()。"""

    def _print_entries(self) -> tuple[list[dict], dict]:
        """第四步待打印图片列表（规则见 services/print_plan.plan_print_entries）。"""
        rembg_files = sorted(
            list_stage_images(self.store.rembg_output_dir(self.task_id)),
            key=lambda p: pdf_custom_sort_key(p.name),
        )
        doc = self.store.load_print_doc(self.task_id)
        entries, new_doc = plan_print_entries(rembg_files, doc)
        self._print_doc_snapshot = new_doc
        if not doc or set(doc.get("rembg_snapshot") or []) != set(new_doc["rembg_snapshot"]):
            self.store.save_print_doc(self.task_id, new_doc)
        return entries, new_doc

    def _save_print_order(self, silent: bool = False) -> None:
        """列表拖动/删除后持久化顺序。

        ``silent=True`` 供版面编辑器复用：拖拽会频繁落盘，若每次都打一条
        「列表已更新」日志会淹没「第 N 页版面已更新」这条真正有用的信息。
        """
        if not self.task_id:
            return
        entries = self.print_preview.entries()
        doc = getattr(self, "_print_doc_snapshot", None) or {
            "rembg_snapshot": [], "pages": [],
        }
        doc["pages"] = [
            (
                {"file": e.get("file"), "label": e.get("label"),
                 "rect": e["rect"]}
                if e.get("rect") is not None
                else {"file": e.get("file"), "label": e.get("label")}
            )
            for e in entries
        ]
        self.store.save_print_doc(self.task_id, doc)
        if not silent:
            self.log_view.append(
                f"待打印列表已更新（{self.print_preview.count()} 页）。"
            )

    def _insert_print_images(self) -> None:
        """插入外部图片到待打印列表末尾。"""
        if not self.task_id:
            return
        filenames, _ = QFileDialog.getOpenFileNames(
            self, "插入图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if not filenames:
            return
        entries = self.print_preview.entries()
        for filename in filenames:
            source = Path(filename)
            entries.append({"file": str(source), "label": source.stem})
        self.store.save_print_pages(self.task_id, entries)
        self.print_preview.set_entries(self._print_entries())
        self.log_view.append(f"已插入 {len(filenames)} 张图片到待打印列表。")

    def _latest_print_pdf_path(self) -> Path | None:
        """最近一次 print 执行产出的 PDF 路径（按 YAML pdf_name 解析）。"""
        if not self.task_id:
            return None
        pdf_name = "print.pdf"
        history = self.store.list_stage_runs(self.task_id, "print")
        if history:
            params = history[0].get("parameters", {})
            if params.get("pdf_name"):
                pdf_name = str(params["pdf_name"])
        out_dir = self.store.stage_dir(self.task_id, "print")
        candidate = out_dir / pdf_name
        if candidate.exists():
            return candidate
        # 兜底：目录下任意 pdf
        for cand in out_dir.glob("*.pdf"):
            return cand
        return None

    def _download_print_pdf(self) -> None:
        """将已生成的 PDF 另存到用户选择的位置（默认下载目录、同名文件）。"""
        if not self.task_id:
            return
        # 优先用下载按钮当前绑定的 PDF；否则按最近一次 print 参数解析
        source = getattr(self.print_preview, "_pdf_path", None)
        if source is None or not Path(source).exists():
            source = self._latest_print_pdf_path()
        if source is None or not Path(source).exists():
            self._toast("warning", "无可下载 PDF", "请先执行「生成 PDF」。")
            return
        source = Path(source)
        # 默认保存到系统「下载」目录，文件名与生成的 PDF 一致
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self, "下载 PDF", str(default_dir / source.name), "PDF 文件 (*.pdf)",
        )
        if not target:
            return
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            self._toast("error", "下载失败", str(exc))
            return
        self._toast("success", "下载完成", f"已保存到：{target}")
        self.log_view.append(f"PDF 已下载到：{target}")
