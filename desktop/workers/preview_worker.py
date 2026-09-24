# -*- coding: utf-8 -*-
"""PDF/图片渲染：整页大图、页缩略图（带磁盘缓存）与去底色效果合成。

区域合成（rembg 预览）在本线程内完成，避免主线程处理原始分辨率大图导致卡顿。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QFontMetrics, QPainter

from utils.box_geometry import (
    build_output_layout,
    build_symmetric_layout,
    parse_border_mm,
)
from desktop.utils.files import THUMBNAIL_EDGE


def compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int = 300) -> list:
    """按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

    **几何规则来自 utils.box_geometry**（与 functions/text_region.py 的 CLI
    输出共用同一份实现），本函数只负责用 QImage 把布局画出来——这样规则
    不会因数像素后端不同而被复制成两份。

    与原实现的一处行为修正：area=3 + 双框 + border=None 时，并集区域现在
    **写回原位置**（此前被搬到画布左上角）。规格见
    docs/functions/cropremove.md:57「area=3 → 单图，ROI 写回原位置」。
    """
    W, H = image.width(), image.height()
    padding = parse_border_mm(border_mm, dpi)
    present = [list(b) for b in boxes if b]

    def blank(w: int, h: int) -> QImage:
        canvas = QImage(max(w, 1), max(h, 1), QImage.Format_RGB32)
        canvas.fill(Qt.white)
        return canvas

    def render(layout) -> list:
        result = []
        for canvas_spec in layout.canvases:
            canvas = blank(canvas_spec.size[0], canvas_spec.size[1])
            for source, ox, oy in canvas_spec.sources:
                x1, y1, x2, y2 = source
                sx1, sy1 = max(0, x1), max(0, y1)
                sx2, sy2 = min(W, x2), min(H, y2)
                if sx2 > sx1 and sy2 > sy1:
                    painter = QPainter(canvas)
                    painter.drawImage(
                        ox + sx1 - x1,
                        oy + sy1 - y1,
                        image,
                        sx1,
                        sy1,
                        sx2 - sx1,
                        sy2 - sy1,
                    )
                    painter.end()
            result.append(canvas)
        return result

    # 无检测框：整页原图
    if not present:
        return [blank(W, H)]

    # 单框 + border + area=2/3：对称输出（实际框 + 空白镜像）
    if len(present) == 1 and padding is not None and area in (2, 3):
        return render(
            build_symmetric_layout(
                box=present[0],
                border_padding=padding,
                image_size=(W, H),
                is_left=True,  # 内容置于左半，右半为空白镜像
                dpi=dpi,
            )
        )

    return render(
        build_output_layout(
            boxes=present,
            area=area,
            border_padding=padding,
            image_size=(W, H),
            dpi=dpi,
        )
    )


# 打印效果预览的基准分辨率：让整页落在 ~1600px 长边，既能看清标题/页码
# 又不至于为一张预览图分配几十 MB
PRINT_PREVIEW_TARGET_EDGE = 1600
PRINT_PREVIEW_MIN_PX_PER_MM = 2.0
PRINT_PREVIEW_MAX_PX_PER_MM = 8.0


def preview_px_per_mm(page_w_mm: float, page_h_mm: float,
                      target_edge: int = PRINT_PREVIEW_TARGET_EDGE) -> float:
    """按纸张尺寸给出效果预览的像素密度（px/mm）。"""
    longest = max(float(page_w_mm), float(page_h_mm))
    if longest <= 0:
        return PRINT_PREVIEW_MIN_PX_PER_MM
    value = target_edge / longest
    return max(PRINT_PREVIEW_MIN_PX_PER_MM,
               min(PRINT_PREVIEW_MAX_PX_PER_MM, value))


def _pick_font(candidates, point_size: float) -> QFont:
    """从给定族名候选里挑第一个系统真装了的；都没命中则交给 Qt 兜底。

    ⚠️ 别用裸 `QFont()`：它落到平台的 generic "Sans Serif" 上，在离屏
    （`QT_QPA_PLATFORM=offscreen`）或字体缺失的环境里中文会渲染成空心
    方框；而且它的字宽度量恰好等于字号，横向文字的占宽会被严重高估。
    """
    from PySide6.QtGui import QFontDatabase

    available = set(QFontDatabase.families())
    for candidate in candidates:
        if candidate in available:
            font = QFont(candidate)
            break
    else:
        font = QFont()
    font.setPointSizeF(max(1.0, float(point_size)))
    return font


def _pick_preview_font(point_size: float) -> QFont:
    """**界面**文字（效果预览的边距标注等）用的字体：走界面族名候选。"""
    from utils.fonts import cjk_font_families

    return _pick_font(cjk_font_families(), point_size)


#: 字体文件 → Qt 族名的缓存。``addApplicationFont`` 每次调用都会再占一个
#: 字体 id，重复加载同一个文件纯属浪费；而且 worker 线程每次都去加载会让
#: 预览刷新明显变卡。
_QT_FONT_FILES: dict[str, str | None] = {}


def qt_family_for_file(path: str) -> str | None:
    """按**字体文件**加载并取回 Qt 族名；失败返回 None。

    为什么要按文件而不是按族名：PDF 侧（`utils.pdf_draw.build_font_chain`）
    也是按文件注册字体的，两边用同一个文件才能保证「预览 = 成品」。按族名
    查表在离屏/精简环境下会落空（那时 `QFontDatabase.families()` 几乎是
    空的），预览就退回默认字体，与成品对不上。
    """
    key = str(path)
    if key in _QT_FONT_FILES:
        return _QT_FONT_FILES[key]
    family: str | None = None
    try:
        from PySide6.QtGui import QFontDatabase

        font_id = QFontDatabase.addApplicationFont(key)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    except Exception:
        family = None
    _QT_FONT_FILES[key] = family
    return family


def _pick_content_font(point_size: float, preferred=None) -> QFont:
    """**PDF 内容**（标题 / 页码）用的字体：**仿宋优先**，可被指定覆盖。

    ``preferred`` 是用户选的字体（显示名 / 路径 / 文件名），能解析到真实文件
    时按**该文件**加载——与 PDF 侧同一个文件，预览与成品才对得上；解析不到
    （本机没这个字体）就回落到自动候选，不会因为一条配置失效而预览不出来。

    必须与 `pdf_draw.register_fonts` 实际选中的字体对齐——那一侧按**文件路径**
    取（Windows 上命中 simfang.ttf = 仿宋），这一侧若按界面候选（雅黑打头）
    取，就会出现「预览是雅黑、导出是仿宋」，所见即所得直接破掉。
    """
    from utils.fonts import content_font_families, resolve_chain

    # ⚠️ 一律**按文件**加载，与 PDF 侧 `build_font_chain` 的链首是同一个
    # 文件——这是「预览 = 成品」唯一可靠的保证。早先默认走族名查表
    # （content_font_families），离屏/精简环境下 `QFontDatabase.families()`
    # 里根本没有那些族，QFont 静默落到 "Sans Serif"，预览与成品对不上。
    chain = resolve_chain(preferred)
    if chain:
        family = qt_family_for_file(chain[0].path)
        if family:
            font = QFont(family)
            font.setPointSizeF(max(1.0, float(point_size)))
            return font
    return _pick_font(content_font_families(), point_size)


#: 1pt = 25.4/72 mm。字体像素大小必须走「pt → mm → px」这条换算，
#: 不能直接用 setPointSizeF——见 ``preview_text_font`` 的说明。
MM_PER_PT = 25.4 / 72.0


def preview_text_font(spec, px_per_mm: float) -> QFont:
    """按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。

    字体族走 ``_pick_content_font``（内容是标题 / 页码，仿宋优先）——与
    ``pdf_draw.register_fonts`` 取到的字体同一种，预览与成品才对得上。

    ⚠️ 不能直接用 ``setPointSizeF(spec.font_size_pt)``：那是固定像素大小，
    而逐字步进是 ``char_h_mm × px_per_mm``（随密度缩放）。两处口径不同时，
    密度一变小（第四步版面编辑画布把整页缩到可视区，≈2 px/mm，远小于效果
    预览的 ≈5.4 px/mm），字仍是原大小、步进却按比例缩小 → **字叠在一起**。

    统一口径后：字高 = 字号(mm) × 密度，与步进同源，任何密度下都不重叠，
    且与成品 PDF 的真实字号（pt → mm）一致。

    ``spec.font`` 是用户为这段文字（标题 / 页码各自独立）指定的字体，
    能解析到文件就按文件加载——与成品 PDF 用同一个字体文件。
    """
    font = _pick_content_font(float(spec.font_size_pt), getattr(spec, "font", None))
    font.setPixelSize(
        max(1, int(round(float(spec.font_size_pt) * MM_PER_PT * px_per_mm)))
    )
    return font


def _draw_print_text(painter: QPainter, spec, px_per_mm: float) -> None:
    """按 PrintTextSpec 画一段文字（竖排逐字、横排整串）。

    坐标与 ``functions/print.py`` 的 fpdf 调用一一对应：fpdf 的
    ``pdf.text(x, y, ch)`` 与 QPainter 的 ``drawText(QPointF)`` 都以
    **基线**为 y，所以这里可以直接复用同一批毫米数——这也是效果预览
    与成品 PDF 不会漂移的原因。

    竖排的分段来自 `utils.page_layout.vertical_runs`（与 fpdf 那边同一份）：
    宽字符一字一格，ASCII 段**整体旋转 90°**（`Happiness` 不会拆成九格）。
    """
    from utils.page_layout import vertical_chunk_advance_mm, vertical_runs

    painter.setFont(preview_text_font(spec, px_per_mm))
    color = spec.color or (0, 0, 0)
    painter.setPen(QColor(int(color[0]), int(color[1]), int(color[2])))
    x = spec.x_mm * px_per_mm
    if spec.vertical:
        char_h_mm = float(spec.char_h_mm)
        step = char_h_mm * px_per_mm
        metrics = QFontMetrics(painter.font())
        y = spec.y_start_mm * px_per_mm
        for chunk, rotated in vertical_runs(spec.text):
            if rotated:
                # 以列位置为基线旋转 90°（Qt 的 rotate 正角即顺时针），
                # 与 fpdf 的 `pdf.rotation(90, x, y)` 同义：字头朝右、自上而下
                painter.save()
                painter.translate(x, y)
                painter.rotate(90)
                painter.drawText(QPointF(0.0, 0.0), chunk)
                painter.restore()
                # ⚠️ 旋转段步进用当前字体实测串宽（与 fpdf 的
                # get_string_width 同一口径，见 utils/pdf_draw.py）：
                # LATIN_ADVANCE_RATIO 估算对数字/下划线长段会高估约
                # 1 个字高，旋转段与后续汉字之间出现空隙。
                latin_width_mm = metrics.horizontalAdvance(chunk) / px_per_mm
            else:
                for index, char in enumerate(chunk):
                    painter.drawText(QPointF(x, y + index * step), char)
                latin_width_mm = None
            y += (
                vertical_chunk_advance_mm(
                    chunk, char_h_mm, rotated, latin_width_mm
                )
                * px_per_mm
            )
        return
    baseline = spec.baseline_mm
    if baseline is None:  # 兜底：无基线时按"顶部 + 1 字高"处理
        baseline = spec.y_start_mm + spec.char_h_mm
    painter.drawText(QPointF(x, baseline * px_per_mm), spec.text)


def compose_print_page(
    image: QImage,
    plan,
    px_per_mm: float | None = None,
) -> QImage:
    """按 ``utils.page_layout.PrintPagePlan`` 合成"打印效果"位图。

    **只画内存位图，不写任何文件**——第四步的效果预览就是它；真正生成
    PDF 仍要走「生成 PDF」按钮（functions/print.py）。

    几何全部取自 ``plan``，而 ``plan`` 由 PDF 生成与预览共用，所以用户
    按预览调好的边距/纸张/标题，与最终 PDF 必然一致。
    """
    density = px_per_mm or preview_px_per_mm(plan.page_w_mm, plan.page_h_mm)
    page_w = max(1, round(plan.page_w_mm * density))
    page_h = max(1, round(plan.page_h_mm * density))
    page = QImage(page_w, page_h, QImage.Format_RGB32)
    if plan.skipped:
        # 命中 skip_pages：成品里没有这一页，预览给一张留白的灰页，
        # 明确告诉用户"这页不会输出"
        page.fill(QColor("#eceff3"))
        painter = QPainter(page)
        painter.setPen(QColor("#98a2b3"))
        painter.setFont(_pick_preview_font(14))
        painter.drawText(page.rect(), Qt.AlignCenter, "该页已跳过，不会输出到 PDF")
        painter.end()
        return page
    page.fill(Qt.white)
    painter = QPainter(page)
    x_mm, y_mm, w_mm, h_mm = plan.image
    target_w = max(1, round(w_mm * density))
    target_h = max(1, round(h_mm * density))
    if target_w > 0 and target_h > 0 and not image.isNull():
        scaled = image.scaled(
            target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        painter.drawImage(round(x_mm * density), round(y_mm * density), scaled)
    for spec in (plan.title, plan.page_number):
        if spec is not None:
            _draw_print_text(painter, spec, density)
    painter.end()
    return page


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
        print_spec: dict | None = None,
    ):
        """构造预览渲染 worker。

        PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
        thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
        effect 为去底色合成参数 {boxes, area, border}，仅对单图生效。
        print_spec 为第四步「打印效果」参数
        {"args": print 参数, "index": 0-based 页序, "total": 总页数, "name": 文件名}，
        非空时把图片按 utils.page_layout 的几何排进一张纸（仅内存，不落盘）；
        另可给 "target_edge"（放大弹窗用）：按该边长反推像素密度**重新排版**，
        标题/页码是重新绘制的，放到 4000px 依然锐利。
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
        self.print_spec = print_spec

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
        if self.print_spec:
            # 打印效果：几何由 utils.page_layout 计算（PDF 生成也是同一份）
            from utils.page_layout import plan_print_page

            plan = plan_print_page(
                (image.width(), image.height()),
                self.print_spec.get("args") or {},
                int(self.print_spec.get("index", 0)),
                int(self.print_spec.get("total", 1)),
                image_name=self.print_spec.get("name"),
                image_rect=self.print_spec.get("rect"),
            )
            # target_edge（放大弹窗用）：按目标边长**反推像素密度**重新排版。
            # ⚠️ 不能只把 compose_print_page 的产物放大了事——它内部固定按
            # preview_px_per_mm（目标 1600px 长边）合成，放大只会糊；按密度
            # 重排则标题/页码是**重新绘制**的，放到 4000px 依然锐利。
            density = None
            target_edge = self.print_spec.get("target_edge")
            if target_edge:
                longest_mm = max(plan.page_w_mm, plan.page_h_mm)
                if longest_mm > 0:
                    density = float(target_edge) / longest_mm
            image = compose_print_page(image, plan, density)
        if not self.longest_edge:
            return image  # 不缩放：调用方需要原始分辨率
        return image.scaled(
            self.longest_edge,
            self.longest_edge,
            aspectMode=Qt.KeepAspectRatio,
            mode=Qt.SmoothTransformation,
        )
