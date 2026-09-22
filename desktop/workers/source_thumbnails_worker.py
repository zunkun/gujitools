# -*- coding: utf-8 -*-
"""导入 PDF 后逐页渲染缩略图，落盘到任务目录的 thumbnails/source/。

命名与 PDF 预览查看器的页缩略图缓存一致（{page}.jpg，0 起始），
预览打开时直接命中缓存，不再重复渲染；该目录永不清理。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from desktop.utils.files import THUMBNAIL_EDGE


class SourceThumbnailsWorker(QObject):
    """导入 PDF 后渲染全部页面缩略图（256px，与预览查看器缓存一致）。"""

    finished = Signal(str)  # 缩略图目录路径
    failed = Signal(str)

    def __init__(self, pdf_path: Path, out_dir: Path, edge: int = THUMBNAIL_EDGE):
        """构造源 PDF 页缩略图 worker。

        pdf_path 为源文件；out_dir 为 thumbnails/source/；edge 最长边
        （默认 256）。缩略图命名 {page+1:04d}.jpg，与预览缓存一致。
        """
        super().__init__()
        self.pdf_path = pdf_path
        self.out_dir = out_dir
        self.edge = edge

    @Slot()
    def run(self) -> None:
        """逐页渲染缩略图落盘；任务目录被删时中止并报 failed。

        ⚠️ **每页先查缓存**：命名与预览查看器的缓存一致（``0001.jpg``），
        已存在且不比源 PDF 旧的直接跳过。否则重复导入同一份 PDF（或把任务
        目录复制过来）时，80 页的书要白渲染 80 页——用户看到的正是「明明
        已经有缩略图了还在重新生成」。
        """
        try:
            import fitz

            try:
                pdf_mtime = self.pdf_path.stat().st_mtime
            except OSError:
                pdf_mtime = 0.0
            document = fitz.open(str(self.pdf_path))
            try:
                if document.page_count == 0:
                    raise ValueError("PDF 没有任何页面")
                self.out_dir.mkdir(parents=True, exist_ok=True)
                (self.out_dir / ".meta").write_text(str(self.edge))
                for page_number in range(document.page_count):
                    # 任务可能中途被删除，此时停止写盘，避免残留目录
                    if not self.out_dir.parent.parent.is_dir():
                        raise FileNotFoundError("任务目录已不存在，中止缩略图生成")
                    # 1 起始、四位补零：与预览查看器缓存命名一致，资源管理器自然排序
                    target = self.out_dir / f"{page_number + 1:04d}.jpg"
                    if target.exists():
                        try:
                            if target.stat().st_mtime >= pdf_mtime:
                                continue  # 缓存可用，跳过渲染
                        except OSError:
                            pass
                    page = document.load_page(page_number)
                    rect = page.rect
                    scale = self.edge / max(rect.width, rect.height)
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale), alpha=False
                    )
                    data = pixmap.tobytes("jpg", jpg_quality=80)
                    target.write_bytes(data)
            finally:
                document.close()
            self.finished.emit(str(self.out_dir))
        except Exception as exc:
            self.failed.emit(str(exc))
