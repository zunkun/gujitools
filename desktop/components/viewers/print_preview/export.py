# -*- coding: utf-8 -*-
"""print 预览 Mixin：**导出与打印**。

把当前页导出为 A4 效果图 / 直接打印。（从 ``print_preview.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog
from desktop.workers import PreviewWorker, connect_queued
from desktop.components.viewers.image_zoom_dialog import save_image
from utils.page_layout import print_page_size_mm
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import PrintPreviewHost
else:
    PrintPreviewHost = object


class PrintExportMixin(PrintPreviewHost):
    """把当前页导出为 A4 效果图 / 直接打印。"""

    def export_current_effect(self, target: str | Path) -> None:
        """把**当前页**排进纸面后的 A4 效果图按 300dpi 写到 ``target``。

        单页、不生成 PDF。走 worker 合成（与预览同一条 ``compose_print_page``
        链路），所以"下载的图 = 屏幕上看到的效果"，只是精度与 PDF 同级而非
        受屏幕像素限制。参数不合法/无条目时发 :attr:`export_failed`。
        """
        index = self._current_index()
        if not (0 <= index < len(self._entries_cache)):
            self.export_failed.emit("没有可导出的页面")
            return
        path = Path(str(self._entries_cache[index]["file"]))
        if not path.exists():
            self.export_failed.emit(f"图片不存在：{path.name}")
            return
        spec, note = self._print_spec(index, path)
        if spec is None:
            self.export_failed.emit(note or "打印参数不合法")
            return
        target = Path(target)
        edge = self._export_edge()
        token = self._export_token = object()
        self.run_worker(
            lambda: PreviewWorker(
                path, longest_edge=0,
                print_spec={**spec, "target_edge": edge},
            ),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda _p, image, _s, t=token: self._write_export(
                        t, image, target
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    lambda _p, msg, t=token: self._export_failed(t, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )


    def _export_edge(self) -> int:
        """导出密度（= 与 PDF 同级的 300dpi）对应的**最长边**像素数。"""
        args: dict = {}
        if self._params_provider is not None:
            try:
                args = self._params_provider() or {}
            except Exception:
                args = {}  # 参数半填状态：按默认纸张算，别挡住导出
        w_mm, h_mm = print_page_size_mm(
            args.get("paper_size") or "A4",
            args.get("orientation") or "landscape",
        )
        return max(1, round(max(w_mm, h_mm) / 25.4 * self.EXPORT_IMAGE_DPI))


    def _write_export(self, token, image, target: Path) -> None:
        """在主线程落盘（``save_image`` 按后缀选 PNG/JPEG）。"""
        if token is not self._export_token:
            return
        if not save_image(image, target):
            self.export_failed.emit(f"写入失败：{target}")
            return
        self.export_finished.emit(str(target))


    def _export_failed(self, token, message: str) -> None:
        if token is not self._export_token:
            return
        self.export_failed.emit(str(message))


    # -------------------------------------------------------------- 单页打印
    def _capture_print_image(self, _page, image, _path: str) -> None:
        """同步打印渲染的接收槽：与 worker **同线程**直连是安全的（run() 是
        普通方法、在本线程立即执行完），无需 connect_queued。"""
        self._print_capture = image


    def _render_current_effect_sync(self):
        """同步渲染当前页的 A4 效果图 → (QImage, 错误文案)。

        与导出/预览同一条 `compose_print_page` 链路、同 300dpi 精度；
        同步执行（A4 合成约几十毫秒，打印对话框弹出前完成，不打断操作流）。
        """
        index = self._current_index()
        if not (0 <= index < len(self._entries_cache)):
            return None, "没有可打印的页面"
        path = Path(str(self._entries_cache[index]["file"]))
        if not path.exists():
            return None, f"图片不存在：{path.name}"
        spec, note = self._print_spec(index, path)
        if spec is None:
            return None, note or "打印参数不合法"
        worker = PreviewWorker(
            path, longest_edge=0,
            print_spec={**spec, "target_edge": self._export_edge()},
        )
        self._print_capture = None
        worker.finished.connect(self._capture_print_image)
        worker.run()  # 同线程直跑（run() 是普通方法），免异步等待
        image = self._print_capture
        if image is None or image.isNull():
            return None, "渲染失败"
        return image, ""


    def _print_current(self) -> None:
        """把当前页的 A4 效果图送到打印机（对话框里选打印机/份数）。

        纸张与方向**按右侧参数**设置——效果图就是按它排版的，纸面与预览
        一致；对话框里仍可换打印机/份数/逐份打印。
        """
        from PySide6.QtGui import QPageLayout

        image, err = self._render_current_effect_sync()
        if image is None:
            self.print_failed.emit(err)
            return
        args: dict = {}
        if self._params_provider is not None:
            try:
                args = self._params_provider() or {}
            except Exception:
                args = {}
        paper = str(args.get("paper_size") or "A4").upper()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(
            self._PAPER_TO_QPAGE.get(paper, QPageSize.PageSizeId.A4)
        ))
        landscape = str(args.get("orientation") or "landscape").lower() in (
            "l", "landscape"
        )
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape if landscape
            else QPageLayout.Orientation.Portrait
        )
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(f"打印当前页（{paper} "
                              f"{'横版' if landscape else '竖版'}）")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        # 效果图与纸张**同比例**（plan 按纸面排版）→ 等比铺满可打印区
        # 就是整页还原，不会变形；页边留白由打印机驱动自己保守处理
        painter.drawImage(printer.pageRect(QPrinter.Unit.DevicePixel), image)
        painter.end()
        self.print_finished.emit(printer.printerName())
