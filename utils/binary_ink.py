# -*- coding: utf-8 -*-
"""「二值稿」的判据与那一刀阈值化——**唯一实现**。

什么叫二值稿
------------
去底色产物（``rembg``）的像素只有两态：**有墨**（``alpha = 255``）与**无墨**
（``alpha = 0``）。RGB 也恒为同一个墨色（去底色是纯黑）。

为什么需要"一刀"
----------------
任何几何变换（``resize`` / ``rotate`` / 透视 / 编辑器里的统一变换）都是插值，
会把硬边抹成一圈半透明灰边。实测（任务 0006）：

===============================  =========  ==============
一张 1650×2208 的二值页          体积        像素组合
===============================  =========  ==============
原样（1 位调色板 + tRNS）           83 KB     2
旋转 0.5° 后（8 位 RGBA）          732 KB     260
旋转 0.5° 后**阈值化**              85 KB     2
===============================  =========  ==============

**哪怕只差 1 像素**也会跳变（1623→1624 宽就从 2 色变 256 色），因为插值在每条
笔画边缘都造出了新颜色。这些中间值 **100% 是插值发明的假细节**，不是原稿信息
——源图本来只有"有墨/无墨"。所以把它压回 0/255 不是降质，是**还原**。

代价只有一条：斜边/拉伸边出现 1 像素台阶（打印 300DPI 下 0.085mm）。

谁在用（两处，输入形态不同，但规则必须是同一条）
------------------------------------------------
- ``services.imposition._looks_binary``：PIL 图，拼版合成**前**判源图；
- ``image_zoom_dialog.io.is_binary_image``：QImage，编辑器烘焙**前**判源图。

⚠️ 两边都刻意**不用** ``np.unique`` 判：8MP 页排序一次要几百毫秒，而
"只统计用过的取值"用直方图（``bincount`` / ``Image.getcolors``）是 O(n) 一趟。
本模块只提供**规则**（让两个适配器算完直方图后共用同一句判断），不替它们做转换。
"""

from __future__ import annotations

#: 二值稿 alpha 的全部取值（有墨 / 无墨）。
INK_LEVELS = (0, 255)

#: 阈值化分界：``>= HARDEN_THRESHOLD`` 视为有墨。
HARDEN_THRESHOLD = 128


def ink_only_levels(used) -> bool:
    """用过的 alpha 取值**恰好**是 ``{0, 255}`` ⇒ 二值稿。

    ``used`` 是**升序去重**的取值序列（``Image.getcolors`` 的 color 段、
    ``np.nonzero(np.bincount(...))[0]`` 都天然满足）。只出现一种（全透明 /
    全不透明）**不算**：全不透明的扫描件没有"无墨"这一态，压它没有意义。
    """
    return list(used) == list(INK_LEVELS)


def ink_color(array):
    """``(H, W, 4)`` RGBA 数组是**二值墨**图 ⇒ 返回墨色 ``(r, g, b)``；否则 ``None``。

    判据两条，缺一不可：
    1. alpha 只有 0 / 255（:func:`ink_only_levels`）；
    2. **不透明像素的颜色完全一致**（同一个墨色）。

    第 2 条不是多余的：alpha 二值但"墨"有两种颜色的图（比如手绘的红+黑），
    压 alpha 会把它们并成一种颜色——那不是"还原"，是改画。
    """
    import numpy as np

    alpha = array[:, :, 3]
    used = np.nonzero(np.bincount(alpha.reshape(-1), minlength=256))[0]
    if not ink_only_levels(used.tolist()):
        return None
    opaque = alpha == 255
    if not opaque.any():
        return None
    colors = array[:, :, :3][opaque]
    first = colors[0]
    if not bool((colors == first).all()):
        return None                        # 墨色不止一种 ⇒ 不是二值墨
    return tuple(int(value) for value in first)


def harden_alpha(array, ink) -> None:
    """把一张**二值墨**图压回"两种像素"，``(H, W, 4)`` RGBA 数组**原地**改。

    ``ink``：墨色（:func:`ink_color` 的返回值），来自**变换前**的源图。

    ⚠️⚠️ **必须连墨色一起归一，只压 alpha 是不够的**（2026-11-15 实测）：
    Qt 的合成是**非预乘**的——黑墨(0,0,0,255) 和"白色透明"(255,255,255,0)
    混出来的中间像素是 **RGB 灰 + 半透明**；只把 alpha 压成 255，它就成了
    **灰色的墨**。实测编辑器里旋转 0.5° 的页：只压 alpha 仍有 257 种组合、
    写回 594KB；连墨色一起归一后回到 2 种、85KB。（PIL 的 ``alpha_composite``
    是预乘的，所以拼版那条路不会出这个问题——但两边都归一是更稳的口径。）

    ⚠️ 透明区统一写成**白**(255,255,255)——与去底色产物同形。写成黑的话，
    任何"不带 alpha 的压白"实现（如 ``convert("RGB")``）都会把空白印成黑底
    （``functions.print._load_image`` 踩过同一类坑）。
    """
    import numpy as np

    alpha = array[:, :, 3]
    on = alpha >= HARDEN_THRESHOLD
    rgb = array[:, :, :3]
    rgb[on] = ink
    rgb[~on] = 255
    alpha[...] = np.where(on, 255, 0)
