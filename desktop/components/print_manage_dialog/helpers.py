# -*- coding: utf-8 -*-
"""「管理图片」弹窗的纯几何/缩略图辅助（无 Qt 控件状态）。"""

from __future__ import annotations

from typing import Callable

from desktop.components.print_manage_dialog._qt import (
    QIcon,
    QImageReader,
    QPixmap,
    QRect,
    QSize,
    Qt,
)

from desktop.components.print_manage_dialog.constants import (
    CHECK_SIZE,
    CLOSE_SIZE,
    THUMB_SIZE,
)
from desktop.services.imposition import cn_page_label


def page_label(row: int) -> str:
    """条目名称 = **页码**（列表当前位置，写法与图片拼版一致）。

    用户 2026-11-02：显示「第一页」「第十二页」这种中文页码，不再用四位补零；
    文件名会误导（拖动/删除后它跟 PDF 页序对不上）。中文页码的唯一来源是
    ``services.imposition.cn_page_label``，这里只是借来用。
    """
    return cn_page_label(row)


def _image_rect(cell: QRect, shown: QSize, box: QSize | None = None) -> QRect:
    """缩略图在网格单元里的落点（水平居中、顶部留 6px）。"""
    box = box or THUMB_SIZE
    if shown.width() <= 0 or shown.height() <= 0:
        shown = box
    fitted = shown.scaled(box, Qt.AspectRatioMode.KeepAspectRatio)
    return QRect(
        cell.left() + (cell.width() - fitted.width()) // 2,
        cell.top() + 6,
        fitted.width(),
        fitted.height(),
    )


def _typical_thumb_height(heights: list[int]) -> int:
    """从缩略图实际高度里取一个**稳健的典型值**当格子高度（用户 2026-11-02）。

    同一本书的正文页长宽比基本一致，夹几张扉页/插图（特别高或特别矮）会把
    取最大值/平均值的口径带偏。这里：

    1. 取中位数 ``m``（不受极端值影响）；
    2. 算平均绝对偏差 ``dev = mean(|h - m|)``；
    3. 偏离 ``m`` 超过 ``2 * dev``（且至少 4px）的当作离群页，**不参与**；
    4. 内点取均值（四舍五入）返回。

    ``dev`` 为 0（几乎都一样）时所有页都参与；全被滤掉时退回中位数。
    """
    if not heights:
        return THUMB_SIZE.height()
    ordered = sorted(heights)
    count = len(ordered)
    mid = count // 2
    median = (
        ordered[mid]
        if count % 2
        else (ordered[mid - 1] + ordered[mid]) / 2
    )
    deviation = sum(abs(h - median) for h in heights) / count
    limit = max(2 * deviation, 4)
    inliers = [h for h in heights if abs(h - median) <= limit] or heights
    return max(1, round(sum(inliers) / len(inliers)))


def _close_rect(image: QRect) -> QRect:
    """图片右上角 x 的命中区（完全落在图片内）。"""
    return QRect(
        image.right() - CLOSE_SIZE - 3,
        image.top() + 3,
        CLOSE_SIZE,
        CLOSE_SIZE,
    )


def _check_rect(image: QRect) -> QRect:
    """图片左上角多选框的命中区（与 x 对称）。"""
    return QRect(image.left() + 3, image.top() + 3, CHECK_SIZE, CHECK_SIZE)


def _icon_and_size(
    file_text: str, thumb_for: Callable[[str], object] | None, size: QSize,
    *, allow_original: bool = True,
) -> tuple[QIcon, QSize]:
    """按目标尺寸**缩放解码**缩略图，并返回图标的实际显示尺寸。

    ``allow_original=False``：有 ``thumb_for`` 但拿不到小图时**不再回落到原图
    解码**——任务里的图由宿主预先生成到 ``thumbnails/print_manage/``，缺失只
    说明后台还没渲完（用户 2026-11-02「弹窗打开慢」：85 张原图同步解码）。
    """
    source = file_text
    if thumb_for is not None:
        try:
            provided = thumb_for(file_text)
        except Exception:  # noqa: BLE001 - 小图来源坏了就当没有
            provided = None
        if provided:
            source = str(provided)
        elif not allow_original:
            return QIcon(), QSize()
    try:
        reader = QImageReader(source)
        image_size = reader.size()
        if image_size.isValid():
            reader.setScaledSize(
                image_size.scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
            )
        image = reader.read()
        if image.isNull():
            return QIcon(), QSize()
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return QIcon(), QSize()
        return QIcon(pixmap), pixmap.size()
    except Exception:  # noqa: BLE001 - 坏图/占用：留空图标，不打断弹窗
        return QIcon(), QSize()
