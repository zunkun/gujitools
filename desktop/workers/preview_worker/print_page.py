# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
"""打印效果页合成：按 ``utils.page_layout.PrintPagePlan`` 画整页位图（内存，不落盘）。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor, QFontMetricsF, QImage, QPainter,
)

from desktop.utils.image_scaling import smooth_downscale

from .constants import (
    PRINT_PREVIEW_MAX_PX_PER_MM,
    PRINT_PREVIEW_MIN_PX_PER_MM,
    PRINT_PREVIEW_TARGET_EDGE,
)
from .fonts import _pick_preview_font, preview_text_font


def preview_px_per_mm(page_w_mm: float, page_h_mm: float,
                      target_edge: int = PRINT_PREVIEW_TARGET_EDGE) -> float:
    """按纸张尺寸给出效果预览的像素密度（px/mm）。"""
    longest = max(float(page_w_mm), float(page_h_mm))
    if longest <= 0:
        return PRINT_PREVIEW_MIN_PX_PER_MM
    value = target_edge / longest
    return max(PRINT_PREVIEW_MIN_PX_PER_MM,
               min(PRINT_PREVIEW_MAX_PX_PER_MM, value))


def _draw_print_text(painter: QPainter, spec, px_per_mm: float) -> None:
    """按 PrintTextSpec 画一段文字（竖排逐字、横排整串）。

    坐标与 ``functions/print.py`` 的 fpdf 调用一一对应：fpdf 的
    ``pdf.text(x, y, ch)`` 与 QPainter 的 ``drawText(QPointF)`` 都以
    **基线**为 y，所以这里可以直接复用同一批毫米数——这也是效果预览
    与成品 PDF 不会漂移的原因。

    竖排的分段来自 `utils.page_layout.vertical_runs`（与 fpdf 那边同一份）：
    宽字符一字一格，ASCII 段**整体旋转 90°**（`Happiness` 不会拆成九格）。
    """
    from utils.page_layout import (
        rotated_run_offset_mm, vertical_chunk_advance_mm, vertical_runs,
    )

    painter.setFont(preview_text_font(spec, px_per_mm))
    color = spec.color or (0, 0, 0)
    painter.setPen(QColor(int(color[0]), int(color[1]), int(color[2])))
    x = spec.x_mm * px_per_mm
    if spec.vertical:
        char_h_mm = float(spec.char_h_mm)
        step = char_h_mm * px_per_mm
        metrics = QFontMetricsF(painter.font())
        # 旋转段的对齐补偿（与 fpdf 侧同一份规则，见 rotated_run_offset_mm）：
        # 汉字以基线为底向上长，旋转段从串首向下排，不补偿就会与前后汉字
        # 之间各空出/压住约一个字的高度。
        dx_mm, dy_mm = rotated_run_offset_mm(
            metrics.ascent() / px_per_mm, metrics.descent() / px_per_mm
        )
        y = spec.y_start_mm * px_per_mm
        for chunk, rotated in vertical_runs(spec.text):
            if rotated:
                # 以列位置为基线旋转 90°（Qt 的 rotate 正角即顺时针），
                # 与 fpdf 的 `pdf.rotation(90, x, y)` 同义：字头朝右、自上而下
                painter.save()
                painter.translate(x + dx_mm * px_per_mm, y + dy_mm * px_per_mm)
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
    PDF 仍要走「生成PDF」按钮（functions/print.py）。

    几何全部取自 ``plan``，而 ``plan`` 由 PDF 生成与预览共用，所以用户
    按预览调好的边距/纸张/标题，与最终 PDF 必然一致。
    """
    density = px_per_mm or preview_px_per_mm(plan.page_w_mm, plan.page_h_mm)
    img_w_mm, img_h_mm = plan.image[2], plan.image[3]
    if not image.isNull() and img_w_mm > 0 and img_h_mm > 0:
        # 密度**不得超过源图原生密度**：再往上就是把源图凭空放大（只会更糊），
        # 还白占内存。宿主会给很大的 target_edge（弹窗 4000），小图（1200px
        # 的扫描件）必须在这里被夹住。
        density = min(
            density, image.width() / img_w_mm, image.height() / img_h_mm
        )
    page_w = max(1, round(plan.page_w_mm * density))
    page_h = max(1, round(plan.page_h_mm * density))
    page = QImage(page_w, page_h, QImage.Format.Format_RGB32)
    if plan.skipped:
        # 命中 skip_pages：成品里没有这一页，预览给一张留白的灰页，
        # 明确告诉用户"这页不会输出"
        page.fill(QColor("#eceff3"))
        painter = QPainter(page)
        painter.setPen(QColor("#98a2b3"))
        painter.setFont(_pick_preview_font(14))
        painter.drawText(page.rect(), Qt.AlignmentFlag.AlignCenter, "该页已跳过，不会输出到 PDF")
        painter.end()
        return page
    page.fill(Qt.GlobalColor.white)
    painter = QPainter(page)
    x_mm, y_mm, w_mm, h_mm = plan.image
    target_w = max(1, round(w_mm * density))
    target_h = max(1, round(h_mm * density))
    if target_w > 0 and target_h > 0 and not image.isNull():
        # 源图像素可能远多于纸面所需（一张 2900px 的半页图排进 130mm 只要
        # ~1500px）：先分档降到 2 倍以内，再按纸面框精确拉伸。一步缩到底会
        # 跳采样，细笔画/淡墨发虚（用户 2026-10-24 报「排版页不清晰」）。
        if image.width() > target_w * 2 or image.height() > target_h * 2:
            image = smooth_downscale(image, 2 * max(target_w, target_h))
        scaled = image.scaled(
            target_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        painter.drawImage(round(x_mm * density), round(y_mm * density), scaled)
    for spec in (plan.title, plan.page_number):
        if spec is not None:
            _draw_print_text(painter, spec, density)
    painter.end()
    return page
