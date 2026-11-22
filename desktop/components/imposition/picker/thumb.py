# -*- coding: utf-8 -*-
"""源图 → 固定尺寸缩略图（整幅解码 + 平滑缩放）。"""

from __future__ import annotations

from desktop.components.imposition.picker._qt import (
    QColor,
    QImageReader,
    QPainter,
    QPixmap,
    QPoint,
    Qt,
)
from desktop.components.imposition.picker.constants import THUMB_H, THUMB_W
from desktop.ui import theme as T
from desktop.utils.image_scaling import smooth_downscale


def _source_thumb_pixmap(path) -> QPixmap:
    """源图 → **固定尺寸**的缩略图（白底居中、按比例缩进 ``THUMB_W×THUMB_H``）。

    ⚠️ 必须**整幅解码再自己缩**，不要走 ``QImageReader.setScaledSize``：
    去底成品是「1bit 调色板 + tRNS」的透明 PNG，解码器的缩放读取在这种图上
    会给出尺寸异常的图，缩略图就变成一小条（用户实测：卡片里只有一段残图）。
    固定尺寸还有一个好处：不管源图多大，卡片格子永远一样大、图不会被拉变形。
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        return QPixmap()
    canvas = QPixmap(THUMB_W, THUMB_H)
    canvas.fill(QColor(T.SURFACE))
    # 分档折半 + 平滑收尾：源图动辄几千像素，一次缩到 96px 会跳采样。
    scaled = smooth_downscale(image, max(THUMB_W, THUMB_H)).scaled(
        THUMB_W, THUMB_H, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(canvas)
    painter.drawImage(
        QPoint((THUMB_W - scaled.width()) // 2, (THUMB_H - scaled.height()) // 2),
        scaled,
    )
    painter.end()
    return canvas
