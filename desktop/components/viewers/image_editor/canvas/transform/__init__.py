# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布 Mixin：**统一变换**（GIMP「Unified Transform」口径）。

（本文件已拆成子包 ``transform/``，仍按原模块路径 ``canvas.transform``
对外导出 ``TransformMixin`` 与全部模块级名字。）
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...consts import (
    CLIPPINGS, CORNER_HANDLES, CORNER_HIT_VIEW_PX, CORNER_VIEW_PX, DIRECTIONS,
    EDGE_BAND_VIEW_PX, EDGE_HANDLE_MIN_VIEW_PX, GUIDE_RATIOS, GUIDES,
    HANDLE_HIT_VIEW_PX, INTERPOLATIONS, PERSP_HANDLES, PERSP_HIT_VIEW_PX,
    PERSP_INSET_VIEW_PX, PERSP_VIEW_PX, PIVOT_VIEW_PX, ROTATE_SNAP_DEG,
    SHEAR_AT, SHEAR_HANDLES, SHEAR_HIT_VIEW_PX, SHEAR_VIEW_PX, SIDE_HANDLES,
    SIDE_VIEW_PX, TRANSFORM_PREVIEW_PIXELS,
)
from ...geometry import (
    _dist_to_segment, clamp_rect, flip_transform, mapped_bounds, quad_point,
    quad_to_quad_transform, rotate_about, scale_about, shear_about,
    transform_region, warp_placement,
)
from ..overlay import _style_node
from .backdrop import TransformBackdropMixin
from .constants import (
    _CONSTRAIN_KEYS, _CORNER_NEIGHBOURS, _CORNER_UV, _EDGE_CORNERS, _EDGE_UV,
    _HANDLE_HITS, _PIVOT_KEYS, _SIDE_ANCHOR,
)
from .drag import TransformDragMixin
from .float_preview import TransformFloatMixin
from .guides import TransformGuidesMixin
from .handles import TransformHandlesMixin
from .helpers import (
    _axis_ratio, _blank_image, _center_crop_rect, _diamond, _on_diagonal,
    _perspective_step, _snap_45,
)
from .hit import TransformHitMixin
from .operations import TransformOperationsMixin
from .options import TransformOptionsMixin
from .pivot import TransformPivotMixin
from .preview import TransformPreviewMixin
from .restore import TransformRestoreMixin
from .state import TransformStateMixin

if TYPE_CHECKING:
    from .._host import CanvasHost
else:
    CanvasHost = object


class TransformMixin(
    TransformOptionsMixin,
    TransformHandlesMixin,
    TransformPreviewMixin,
    TransformStateMixin,
    TransformBackdropMixin,
    TransformFloatMixin,
    TransformRestoreMixin,
    TransformOperationsMixin,
    TransformPivotMixin,
    TransformDragMixin,
    TransformHitMixin,
    TransformGuidesMixin,
    CanvasHost,
):
    """按 GIMP 统一变换口径实现的变换 Mixin（实现分散在同包各子模块）。"""


__all__ = [
    "TransformMixin",
    "_CONSTRAIN_KEYS", "_CORNER_NEIGHBOURS", "_CORNER_UV", "_EDGE_CORNERS",
    "_EDGE_UV", "_HANDLE_HITS", "_PIVOT_KEYS", "_SIDE_ANCHOR",
    "_axis_ratio", "_blank_image", "_center_crop_rect", "_diamond",
    "_on_diagonal", "_perspective_step", "_snap_45",
]
