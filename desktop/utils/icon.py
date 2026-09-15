# -*- coding: utf-8 -*-
"""窗口图标的圆角渲染。

图标的**形状由像素决定**——窗口标题栏/任务栏/Alt-Tab 都是 Windows 拿
Qt 给的位图去画，Qt 管不了圆不圆角。所以要在交给 ``setWindowIcon`` 之前
把源图裁成圆角，这样：

* 源图（``desktop/static/icon.png``）保持直角原图，**换图标不用手工修图**；
* 圆角比例只有一处定义（``ICON_RADIUS_RATIO``），与打包用的
  ``tools/make_icon.py::DEFAULT_RADIUS_PCT`` 保持一致；
* 同时往 QIcon 里塞多个尺寸帧——Windows 会按场景挑帧，避免它自己把
  295px 缩到 16px 时把圆角外的透明平均成半透明（浅色标题栏上会显出一圈淡边）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPainterPath, QPixmap

# 与 tools/make_icon.py::DEFAULT_RADIUS_PCT 一致：修改时两边一起改
ICON_RADIUS_RATIO = 0.08
# 与 tools/make_icon.py::MIN_CORNER_PX 一致：小尺寸下固定比例的圆角不到
# 1 像素，角像素仍落在图形内 → 四角不透明。半径至少 MIN_CORNER_PX 像素。
MIN_CORNER_PX = 2.0


def effective_ratio(size: int, ratio: float = ICON_RADIUS_RATIO) -> float:
    """按帧尺寸自适应圆角比例（16px 需 ~12.5% 才能真正裁掉四角）。"""
    return max(ratio, MIN_CORNER_PX / size)

# Windows 各场景会按需要挑选帧；小帧单独做 alpha 阈值处理（见 _binarize_alpha）
ICON_FRAME_SIZES = (16, 32, 48, 64, 128, 256)
_ALPHA_CUT = 140


def rounded_pixmap(source: QPixmap, size: int,
                   ratio: float = ICON_RADIUS_RATIO) -> QPixmap:
    """把源图等比居中裁成 ``size × size`` 的圆角图（圆角外透明）。"""
    scaled = source.scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    r = size * effective_ratio(size, ratio)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), r, r)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return out


def _binarize_alpha(pixmap: QPixmap, cut: int = _ALPHA_CUT) -> QPixmap:
    """把小尺寸帧边缘的半透明像素压成全透明。

    缩到 16px 时圆角外的透明会和图形颜色平均成半透明（实测红章四角
    alpha=137），叠在浅色标题栏上就是一圈淡色晕边。这里低于阈值的直接
    归零，其余按比例拉回不透明。
    """
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            alpha = image.pixelColor(x, y).alpha()
            if alpha < cut:
                image.setPixelColor(x, y, Qt.GlobalColor.transparent)
            elif alpha < 255:
                color = image.pixelColor(x, y)
                color.setAlpha(255)
                image.setPixelColor(x, y, color)
    return QPixmap.fromImage(image)


def rounded_window_icon(path: Path | str,
                        ratio: float = ICON_RADIUS_RATIO) -> QIcon | None:
    """读取图片并生成圆角窗口图标；读取失败返回 None。

    返回的 QIcon 内含 16~256 多帧，小帧已做 alpha 二值化。
    """
    source = QPixmap(str(path))
    if source.isNull():
        return None
    icon = QIcon()
    for size in ICON_FRAME_SIZES:
        frame = rounded_pixmap(source, size, ratio)
        if size <= 32:  # 只有小帧需要消除半透明晕边
            frame = _binarize_alpha(frame)
        icon.addPixmap(frame)
    if source.width() not in ICON_FRAME_SIZES:  # 保留原始尺寸，避免大图被降采样
        icon.addPixmap(rounded_pixmap(source, source.width(), ratio))
    return icon
