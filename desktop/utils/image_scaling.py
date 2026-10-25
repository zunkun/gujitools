# -*- coding: utf-8 -*-
"""预览降采样：**分档折半 + 末档平滑**（界面里所有"大图缩成小图显示"共用）。

⚠️ 为什么不能一次缩到底：``QImage`` 的 ``SmoothTransformation`` 是双线性
采样，一次 8~10 倍缩小只取到目标像素附近的几个源像素，绝大多数源像素被
跳过——古籍扫描的细笔画、淡墨、飞白因此发虚/断笔，用户看到的就是
「原图放大看还行，预览页却糊」（2026-10-24 报障，PDF 排版页直接命中）。

分档做法：先每档只缩 2 倍（等效核接近箱式滤波，把细节"平均"下来而不是
跳采样），剩到目标 2 倍以内再做一次平滑收尾。代价是几十毫秒/张，只在
**换图/换档**时付一次（各调用方都各自带缓存）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage


def smooth_downscale(image: QImage, longest_edge: int) -> QImage:
    """把 ``image`` 等比降到**最长边 ≤ longest_edge**（只缩不放）。

    - ``longest_edge <= 0`` 或空图：原样返回（调用方语义：不缩放）；
    - 本来就比目标小：原样返回（绝不放大——放大只会更糊）；
    - 否则分档折半到 2 倍以内，最后一次平滑缩到目标边长。
    """
    if image is None or image.isNull() or longest_edge <= 0:
        return image
    longest = max(image.width(), image.height())
    if longest <= longest_edge:
        return image
    current = image
    while longest > longest_edge * 2:
        current = current.scaled(
            max(1, current.width() // 2),
            max(1, current.height() // 2),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        longest = max(current.width(), current.height())
    return current.scaled(
        longest_edge,
        longest_edge,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
