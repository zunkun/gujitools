# -*- coding: utf-8 -*-
"""PDF/图片渲染：整页大图、页缩略图（带磁盘缓存）与去底色效果合成。

区域合成（rembg 预览）在本线程内完成，避免主线程处理原始分辨率大图导致卡顿。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QImage, QPainter

from utils.box_geometry import parse_border_mm
from desktop.utils.files import THUMBNAIL_EDGE

SYMMETRIC_GAP_MM = 10  # 与 functions/text_region.py 一致


def compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int = 300) -> list:
    """按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

    与 functions/text_region.py 的输出几何完全一致：
    - area=1：每个文本框各一张（框 + border，border 缺省为 0）；
    - area=2 双框：并集画布 + border，两框内容按原位置粘贴，
      **框之间的内容丢弃（留白）**；
    - area=3 双框：并集区域**整块**作为一个 ROI 取出（框间内容保留）+ border；
    - area=2/3 单框：对称画布（框宽×2 + 10mm 间隔，内容在一侧）；
    - area=2/3 border 未填：整页尺寸画布，仅框内（area=3 为并集内）保留内容。
    """
    present = [list(b) for b in boxes if b]
    W, H = image.width(), image.height()

    def blank(w: int, h: int) -> QImage:
        canvas = QImage(max(w, 1), max(h, 1), QImage.Format_RGB32)
        canvas.fill(Qt.white)
        return canvas

    def paste_source(canvas: QImage, box, ox: int, oy: int) -> None:
        x1, y1, x2, y2 = box
        sx1, sy1 = max(0, x1), max(0, y1)
        sx2, sy2 = min(W, x2), min(H, y2)
        if sx2 > sx1 and sy2 > sy1:
            painter = QPainter(canvas)
            painter.drawImage(
                ox + sx1 - x1, oy + sy1 - y1, image, sx1, sy1, sx2 - sx1, sy2 - sy1
            )
            painter.end()

    padding = parse_border_mm(border_mm, dpi)

    if area == 1:
        t, r, btm, l = padding or [0, 0, 0, 0]
        outputs = []
        for b in present:
            canvas = blank((b[2] - b[0]) + l + r, (b[3] - b[1]) + t + btm)
            paste_source(canvas, b, l, t)
            outputs.append(canvas)
        return outputs

    if len(present) == 2:
        ux1 = min(b[0] for b in present)
        uy1 = min(b[1] for b in present)
        ux2 = max(b[2] for b in present)
        uy2 = max(b[3] for b in present)
        if padding is None:
            canvas = blank(W, H)
            if area == 3:
                paste_source(canvas, [ux1, uy1, ux2, uy2], 0, 0)
            else:
                for b in present:
                    paste_source(canvas, b, b[0], b[1])
            return [canvas]
        t, r, btm, l = padding
        canvas = blank((ux2 - ux1) + l + r, (uy2 - uy1) + t + btm)
        if area == 3:
            paste_source(canvas, [ux1, uy1, ux2, uy2], l, t)
        else:
            for b in present:
                paste_source(canvas, b, l + (b[0] - ux1), t + (b[1] - uy1))
        return [canvas]

    if not present:
        return [blank(W, H)]

    # area=2/3 单框：对称输出
    single = present[0]
    if padding is None:
        canvas = blank(W, H)
        paste_source(canvas, single, single[0], single[1])
        return [canvas]
    t, r, btm, l = padding
    gap = round(SYMMETRIC_GAP_MM * dpi / 25.4)
    bw = single[2] - single[0]
    bh = single[3] - single[1]
    canvas = blank(l + bw * 2 + gap + r, t + bh + btm)
    paste_source(canvas, single, l, t)  # 内容置于左半，右半为空白镜像
    return [canvas]


def compose_outputs_horizontal(outputs: list, gap: int = 12) -> QImage:
    """多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。"""
    if not outputs:
        return QImage()
    if len(outputs) == 1:
        return outputs[0]
    height = max(c.height() for c in outputs)
    total_w = sum(c.width() for c in outputs) + gap * (len(outputs) - 1)
    out = QImage(total_w, height, QImage.Format_RGB32)
    out.fill(Qt.darkGray)
    painter = QPainter(out)
    offset_x = 0
    for crop in outputs:
        painter.drawImage(offset_x, (height - crop.height()) // 2, crop)
        offset_x += crop.width() + gap
    painter.end()
    return out


class PreviewWorker(QObject):
    """渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。"""

    finished = Signal(int, QImage, str)
    metadata = Signal(int, str)
    thumbnail_ready = Signal(int, QImage)
    completed = Signal()
    failed = Signal(int, str)

    def __init__(
        self,
        path: Path,
        page: int = 0,
        longest_edge: int | None = 1200,
        thumbnails: bool = False,
        cache_dir: Path | None = None,
        effect: dict | None = None,
    ):
        """构造预览渲染 worker。

        PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
        thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
        effect 为去底色合成参数 {boxes, area, border}，仅对单图生效。
        """
        super().__init__()
        self.path = path
        self.page = page
        self.longest_edge = longest_edge
        self.thumbnail_edge = THUMBNAIL_EDGE
        self.thumbnails = thumbnails
        self.cache_dir = Path(cache_dir) if cache_dir else None
        # 去底色效果合成参数：{"boxes": [[x1,y1,x2,y2],...], "area": int, "border": str|None}
        self.effect = effect

    @Slot()
    def run(self) -> None:
        """按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。"""
        try:
            if self.path.suffix.lower() == ".pdf" and self.thumbnails:
                self._render_all_thumbnails()
                return
            if self.path.suffix.lower() == ".pdf":
                image = self._render_pdf_page()
            else:
                image = self._load_image()
            self.finished.emit(self.page, image, str(self.path))
        except Exception as exc:
            self.failed.emit(self.page, str(exc))
            if self.thumbnails:
                self.completed.emit()

    def _render_pdf_page(self) -> QImage:
        import fitz

        document = fitz.open(str(self.path))
        try:
            self.metadata.emit(document.page_count, str(self.path))
            page = document.load_page(self.page)
            rect = page.rect
            scale = self.longest_edge / max(rect.width, rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return QImage.fromData(pixmap.tobytes("jpg", jpg_quality=80))
        finally:
            document.close()

    def _render_all_thumbnails(self) -> None:
        import fitz

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / ".meta").write_text(str(self.thumbnail_edge))
        document = fitz.open(str(self.path))
        try:
            self.metadata.emit(document.page_count, str(self.path))
            for page_number in range(document.page_count):
                image = None
                # 命名与导入缩略图一致：1 起始、四位补零（0001.jpg），自然排序
                cache_file = (
                    self.cache_dir / f"{page_number + 1:04d}.jpg"
                    if self.cache_dir
                    else None
                )
                if cache_file and cache_file.exists():
                    image = QImage(str(cache_file))
                if image is None or image.isNull():
                    page = document.load_page(page_number)
                    rect = page.rect
                    scale = self.thumbnail_edge / max(rect.width, rect.height)
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale), alpha=False
                    )
                    data = pixmap.tobytes("jpg", jpg_quality=70)
                    image = QImage.fromData(data)
                    if cache_file:
                        cache_file.write_bytes(data)
                self.thumbnail_ready.emit(page_number, image)
        finally:
            document.close()
        self.completed.emit()

    def _load_image(self) -> QImage:
        image = QImage(str(self.path))
        if image.isNull():
            raise ValueError("无法读取图片")
        if self.effect:
            outputs = compose_region_output(
                image,
                self.effect.get("boxes", []),
                int(self.effect.get("area", 1)),
                self.effect.get("border"),
            )
            image = compose_outputs_horizontal(outputs)
        if not self.longest_edge:
            return image  # 不缩放：调用方需要原始分辨率
        return image.scaled(
            self.longest_edge,
            self.longest_edge,
            aspectMode=Qt.KeepAspectRatio,
            mode=Qt.SmoothTransformation,
        )
