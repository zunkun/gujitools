# -*- coding: utf-8 -*-
"""逐页旋转角归一与外接框计算（预览 / 版面编辑 / 单页导出 / PDF 共用）。"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple


def normalize_page_rotation(value) -> float:
    """逐页图片旋转角归一为 **(-180, 180]** 的浮点角度（顺时针为正）。

    版面编辑器的旋转钮可以拖任意角度（与「图片拼版」同一款组件），不再限定
    90° 步进；这里只负责把任意输入收敛到同一区间。「预览 / 版面编辑 / 单页
    导出 / 生成 PDF」四条链路共用这一个口径：谁都不许自己取整，否则同一份
    ``print.json`` 在四处转出四个方向。
    """
    try:
        degrees = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(degrees):
        return 0.0
    degrees = math.fmod(degrees, 360.0)
    if degrees > 180.0:
        degrees -= 360.0
    elif degrees <= -180.0:
        degrees += 360.0
    return round(degrees, 2) + 0.0


def rotated_bbox_size(width: float, height: float, degrees) -> Tuple[float, float]:
    """``width × height`` 的矩形绕中心顺时针转 ``degrees`` 后的**外接框**尺寸。

    旋转后的图片按外接框占位（PDF ``pdf.image`` 也只能给轴对齐的 w/h），
    预览 / 画布 / 成品都拿这个函数算，三者才会得出同一个框。
    """
    angle = math.radians(normalize_page_rotation(degrees))
    cos_v, sin_v = abs(math.cos(angle)), abs(math.sin(angle))
    return (
        float(width) * cos_v + float(height) * sin_v,
        float(width) * sin_v + float(height) * cos_v,
    )


def fit_rotated_rect(
    rect: Sequence[float], image_size: Sequence[float], degrees
) -> List[float]:
    """把旋转后的图**等比**放进 ``rect`` 并居中，返回它在页面上的外接框。

    ``rect`` 是用户在版面编辑器里拖出来的图片槽（页面 mm；画布以像素为
    单位调用，单位无关）。旋转不改变这个槽，图片按旋转后的外接框等比缩放
    后**完整地**放进去——不裁剪、不拉伸，所以预览与 PDF 的落点一致。
    """
    try:
        x, y, box_w, box_h = (float(v) for v in rect[:4])
        img_w, img_h = (float(v) for v in image_size[:2])
    except (TypeError, ValueError, IndexError):
        return [float(v) for v in rect[:4]]
    if img_w <= 0 or img_h <= 0 or box_w <= 0 or box_h <= 0:
        return [x, y, box_w, box_h]
    bbox_w, bbox_h = rotated_bbox_size(img_w, img_h, degrees)
    scale = min(box_w / bbox_w, box_h / bbox_h)
    placed_w, placed_h = bbox_w * scale, bbox_h * scale
    return [
        x + (box_w - placed_w) / 2.0,
        y + (box_h - placed_h) / 2.0,
        placed_w,
        placed_h,
    ]
