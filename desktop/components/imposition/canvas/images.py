# -*- coding: utf-8 -*-
"""画布显示用的图像辅助：裁掉四周纯透明的边（与合成侧同口径）。"""

from __future__ import annotations

from desktop.components.imposition.canvas._qt import QImage


def _trim_transparent_border(image: QImage) -> QImage:
    """裁掉 QImage 四周**纯透明**的边；无透明边（或全透明）时原样返回。

    ⚠️ 与 ``services.imposition._trim_to_content`` 同一口径（那边是 PIL 版），
    两边必须一致：画布显示与成品合成都按"可见内容"摆版，裁剪移动留在像素图
    里的透明边距只是位移的编码，不该占版面（用户 2026-10-14 报障）。

    整幅不透明时 ``alpha`` 全非零、包围盒＝整张 ⇒ 直接返回原图对象，
    零拷贝、不改既有行为；缺 numpy（``_transparent_content_bounds`` 返回
    None）时同样原样返回——宁可画大一点，也不能把内容裁掉。
    """
    try:
        from desktop.components.viewers.image_editor.geometry import (
            _transparent_content_bounds,
        )
    except Exception:  # noqa: BLE001 - 取不到就按整张处理
        return image
    bounds = _transparent_content_bounds(image)
    if bounds is None:
        return image
    x, y, width, height = bounds
    if x == 0 and y == 0 and width == image.width() \
            and height == image.height():
        return image                        # 四边都贴着内容：无需裁
    return image.copy(x, y, width, height)
