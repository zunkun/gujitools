# -*- coding: utf-8 -*-
"""任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。"""

from __future__ import annotations

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
        try:
            self.store.save_print_doc(self.task_id, doc)
        except OSError as exc:
            # ⚠️ 落盘失败必须让用户看见（2026-09-26 审计）：任务目录被外部删除 /
            #    磁盘满时，原先这个异常会**直接从 Qt 槽里抛出去**（排序、拖动版面
            #    都是槽），只打印到控制台，用户看到的是"拖了没反应"且毫无原因。
            message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "列表未保存", message)
            return
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
        # ⚠️ 复制进后台线程（审计 D2）：几百 MB 的 PDF 用主线程 copy2 会把
        # 界面冻住整个复制时长；复制期间不禁按钮但用标志防重入。
        if getattr(self, "_download_busy", False):
            self._toast("warning", "正在下载", "上一次下载还没完成。")
            return
        self._download_busy = True
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker([(source, Path(target))])
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self, w.finished, self._on_download_done, thread
                ),
                connect_queued(
                    self, w.failed,
                    lambda msg: self._on_download_done([], [(str(source), msg)]),
                    thread,
                ),
                w.finished.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_download_done(self, done: list, errors: list) -> None:
        """后台下载完成（主线程）：播报结果并解除防重入。"""
        self._download_busy = False
        if errors:
            self._toast("error", "下载失败", errors[0][1])
            return
        if not done:
            return
        target = done[0][1]
        self._toast("success", "下载完成", f"已保存到：{target}")
        self.log_view.append(f"PDF 已下载到：{target}")

    def _export_print_image(self) -> None:
        """把**当前页**的 A4 效果图另存为图片（单页；精度与 PDF 同级 300dpi）。

        渲染交给 ``print_preview``（它才懂排版口径），这里只负责对话框与提示：
        与「下载 PDF」保持同一套交互（默认下载目录、toast、写日志）。
        """
        default_name = self.print_preview.export_default_name()
        if not default_name:
            self._toast("warning", "无可导出页面", "请先在第四步添加要打印的图片。")
            return
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self, "下载本页图片", str(default_dir / default_name),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg)",
        )
        if not target:
            return
        self._export_target = target
        self.print_preview.export_current_effect(target)

    def _on_export_finished(self, target: str) -> None:
        self._toast("success", "已导出本页图片", f"已保存到：{target}")
        self.log_view.append(f"本页图片已导出：{target}")

    def _on_export_failed(self, message: str) -> None:
        self._toast("error", "导出失败", message)
        self.log_view.append(f"导出本页图片失败：{message}")

    def _on_print_finished(self, printer_name: str) -> None:
        self._toast("success", "已发送打印", f"打印机：{printer_name}")
        self.log_view.append(f"本页已发送打印机：{printer_name}")

    def _on_print_failed(self, message: str) -> None:
        self._toast("error", "打印失败", message)
        self.log_view.append(f"打印本页失败：{message}")
