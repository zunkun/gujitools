# -*- coding: utf-8 -*-
"""画布 Mixin：**统一变换**（GIMP「Unified Transform」口径）。

从 ``EditorCanvas`` 拆出（2026-10-07）。2026-10-08 按 GIMP 统一变换重做：
手柄从"8 个方向缩放方块"扩成 **角方框(双轴缩放) / 角内小菱形(透视) /
边中方框(单轴缩放) / 边上菱形(切变)** 四类，并接上 GIMP 的选项
（方向 / 插值 / 剪裁 / 预览不透明度 / 参考线 / 限制 / 从轴心 / 轴心吸附锁定）。

手柄词汇表与理由见 ``consts.py`` 里那一段长注释——**方框=缩放、菱形=切变、
角上的小菱形=透视**，位置全部由 :meth:`TransformMixin._transform_local_handles`
从 ``_xf_rect`` 的参数坐标算出来，绘制与命中用的是**同一份**结果
（:meth:`TransformMixin._transform_handle_points`），不会再出现"画在这里、
却要点那里"。

⚠️ 累计矩阵 ``_xf`` 的复合约定（与 ``geometry.py`` 同一条）：``(A * B)``
= **先 A 后 B**。于是
  * 在**原图坐标**里发生的操作（缩放/切变/翻转）写成 ``局部操作 * _xf``；
  * 在**画布坐标**里发生的操作（透视把四角重映射）写成 ``_xf * 步骤``。
搞反的话表现是"拖动方向对、但位置整体偏掉"，很难看出来。

⚠️⚠️ **视觉矩阵**（2026-10-09 修「方向=校正，图片和操作框方向相反」）：
屏幕上真正呈现的矩阵是 :meth:`_visual_xf`——正向 = ``_xf`` 本身，
**校正（向后）= ``_xf`` 的逆**（``_preview_xf``，与浮层内容、烘焙同口径）。
覆盖层（四边形框/手柄/参考线/轴心）与拖拽数学一律吃**视觉矩阵**，
算完经 :meth:`_apply_visual` 落账回 ``_xf``。旧版框画的是 ``_xf``、
内容走的是 ``_preview_xf``，校正模式下两套口径各动各的 ⇒ 图往左转、
框往右转。语义入口（``transform_*``）同理：先在视觉空间里叠操作。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor, QImage, QPainter, QPainterPath, QPixmap, QPolygonF, QTransform,
)
from PySide6.QtWidgets import QApplication, QGraphicsPixmapItem

from ..consts import (
    CLIPPINGS, CORNER_HANDLES, CORNER_HIT_VIEW_PX, CORNER_VIEW_PX, DIRECTIONS,
    EDGE_BAND_VIEW_PX, EDGE_HANDLE_MIN_VIEW_PX, GUIDE_RATIOS, GUIDES,
    HANDLE_HIT_VIEW_PX, INTERPOLATIONS, PERSP_HANDLES, PERSP_HIT_VIEW_PX,
    PERSP_INSET_VIEW_PX, PERSP_VIEW_PX, PIVOT_VIEW_PX, ROTATE_SNAP_DEG,
    SHEAR_AT, SHEAR_HANDLES, SHEAR_HIT_VIEW_PX, SHEAR_VIEW_PX, SIDE_HANDLES,
    SIDE_VIEW_PX, TRANSFORM_PREVIEW_PIXELS,
)
from ..geometry import (
    _dist_to_segment, clamp_rect, flip_transform, mapped_bounds, quad_point,
    quad_to_quad_transform, rotate_about, scale_about, shear_about,
    transform_region, warp_placement,
)
from .overlay import _style_node
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


#: 角的参数坐标（u/v ∈ [0, 1]，原点 = 选区左上角）——手柄位置唯一来源
_CORNER_UV = {"tl": (0.0, 0.0), "tr": (1.0, 0.0),
              "br": (1.0, 1.0), "bl": (0.0, 1.0)}
#: 边的参数化：沿线比例 s（0 = 起点角、1 = 终点角）→ (u, v)
_EDGE_UV = {
    "t": lambda s: (s, 0.0),
    "b": lambda s: (s, 1.0),
    "l": lambda s: (0.0, s),
    "r": lambda s: (1.0, s),
}
#: 边 → 两端的角（命中带与切变方向用）
_EDGE_CORNERS = {"t": ("tl", "tr"), "r": ("tr", "br"),
                 "b": ("br", "bl"), "l": ("bl", "tl")}
#: 角的两个相邻角——透视小菱形沿"框内对角线"偏置
_CORNER_NEIGHBOURS = {"tl": ("tr", "bl"), "tr": ("tl", "br"),
                      "br": ("tr", "bl"), "bl": ("tl", "br")}
#: 单轴缩放的锚点：抓某条边时**对边**不动（在选区局部坐标里）
_SIDE_ANCHOR = {
    "l": lambda rect: QPointF(rect.right(), rect.center().y()),
    "r": lambda rect: QPointF(rect.left(), rect.center().y()),
    "t": lambda rect: QPointF(rect.center().x(), rect.bottom()),
    "b": lambda rect: QPointF(rect.center().x(), rect.top()),
}

#: 「从轴心 (Ctrl)」可用的动作；「限制 (Shift)」可用的动作
_PIVOT_KEYS = ("scale", "shear", "perspective")
_CONSTRAIN_KEYS = ("move", "scale", "rotate", "shear", "perspective")

#: 算"节点"的命中名（悬停/点选都高亮它们；整条边带与框内不算节点）
_HANDLE_HITS = frozenset(
    CORNER_HANDLES + SIDE_HANDLES + SHEAR_HANDLES + PERSP_HANDLES)


def _axis_ratio(current: float, origin: float, anchor: float) -> float:
    """一维缩放比：``anchor`` 不动，``origin`` 跟到 ``current`` 时的倍率。

    ``|origin - anchor|`` 太小时给 1.0（抓在锚点上没法定义倍率）；
    倍率夹在 ±1e-3 之外——放到 0 会让矩阵不可逆，预览与烘焙一起消失。
    """
    span = origin - anchor
    if abs(span) < 1e-6:
        return 1.0
    ratio = (current - anchor) / span
    if abs(ratio) < 1e-3:
        return 1e-3 if ratio >= 0 else -1e-3
    return ratio


def _snap_45(delta: QPointF) -> QPointF:
    """把位移吸附到 45° 的整数倍（「限制」里的移动约束）。"""
    length = math.hypot(delta.x(), delta.y())
    if length < 1e-6:
        return delta
    angle = math.degrees(math.atan2(delta.y(), delta.x()))
    snapped = round(angle / 45.0) * 45.0
    radians = math.radians(snapped)
    return QPointF(length * math.cos(radians), length * math.sin(radians))


def _blank_image() -> QImage:
    """1×1 的**全透明**图 —— 「整幅选区」的底图就是这么一片"空"。

    配 ``_xf_base_scale`` 用图元缩放拉成目标大小：换尺寸只是改个矩阵，
    不会为了每个新尺寸新建一张 12 MP 的白图（那正是"旋转卡"的来源之一）。

    ⚠️ 它**曾经是纯白**的：整幅选区时它就是那张"白纸"，也就是用户 2026-10-09
    报的「旋转后白底一直涨、还在漂」。现在整幅选区 = 内容整块被搬走 = 原位**空**，
    所以填透明，露出的画布条纹格才说得通（口径：不再有任何白色区域）。
    """
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    return image


def _center_crop_rect(rect: QRectF, width: int, height: int) -> QRectF:
    """:func:`geometry.center_crop_aspect` 的**矩形版**（预览与烘焙裁同一块）。

    取整必须与那边一致（``int(round(...))`` + ``//2``），否则预览的"纸"和
    烘焙出来的画布会差一两个像素，边缘看着像抖了一下。
    """
    if rect.isEmpty() or width <= 0 or height <= 0:
        return rect
    target = width / height
    if rect.width() / rect.height() > target:
        new_w = float(max(1, min(int(round(rect.height() * target)),
                                 int(rect.width()))))
        return QRectF(rect.x() + math.floor((rect.width() - new_w) / 2),
                      rect.y(), new_w, rect.height())
    new_h = float(max(1, min(int(round(rect.width() / target)),
                             int(rect.height()))))
    return QRectF(rect.x(),
                  rect.y() + math.floor((rect.height() - new_h) / 2),
                  rect.width(), new_h)


def _on_diagonal(quad: list[QPointF], index: int, target: QPointF) -> QPointF:
    """把 ``target`` 拉到"对角 → 本角"这条直线上（透视的 Shift 约束）。

    GIMP 口径：勾了「限制 · 透视」时手柄**只能沿边或对角线走**，于是拖动
    只会改变单方向的透视强度，不会同时把两条边一起拽歪。
    """
    opposite = quad[(index + 2) % 4]
    origin = quad[index]
    span = QPointF(origin.x() - opposite.x(), origin.y() - opposite.y())
    length_sq = span.x() * span.x() + span.y() * span.y()
    if length_sq < 1e-9:
        return target
    step = QPointF(target.x() - opposite.x(), target.y() - opposite.y())
    ratio = max(0.05, (step.x() * span.x() + step.y() * span.y()) / length_sq)
    return QPointF(opposite.x() + span.x() * ratio,
                   opposite.y() + span.y() * ratio)


def _perspective_step(xf_start: QTransform, quad: list[QPointF], index: int,
                      target: QPointF, rect: QRectF) -> QTransform | None:
    """"把 ``quad`` 的第 ``index`` 个角挪到 ``target``"这一步的矩阵。

    **病态的一步返回 ``None``**（调用方当"这一步没发生"，手柄就此停住——
    同 GIMP：透视手柄拖不过对角）。

    ⚠️⚠️ 旧版只靠 ``quad_to_quad_transform`` 拦"四点**共线**"，可**近**共线
    （把 tl 拖到 br 附近、或拖成自交的蝴蝶结）时 ``quadToQuad`` 照样返回一个
    "可逆"的矩阵——它把内容放大百万倍以上，外框实测 4.8e17。后果是
    ``warp_region`` 拒绝（>40 MP）后预览**回落到 QPainter 兜底**，
    ``QImage(2.18e9, 1.49e9)`` 直接 OverflowError，整个编辑器崩掉
    （用户 2026-10-09 报的正是这个）。所以这里补一道**几何合理性**判据：
    这一步算完，选区必须还被映在一个"人能用"的外框里
    （``geometry.mapped_bounds``，与重采样同一道闸）。
    """
    new_quad = list(quad)
    new_quad[index] = QPointF(target)
    step = quad_to_quad_transform(quad, new_quad)
    if step is None:
        return None                        # 四点共线 / 重合：本来就不动
    if mapped_bounds(xf_start * step, rect) is None:
        return None                        # 自交 / 塌陷 ⇒ 外框天文数字：不动
    return step


class TransformMixin(CanvasHost):
    """统一变换：手柄几何与命中、变换应用、实时预览与覆盖层。"""

    # ------------------------------------------------------------ 选项
    def set_transform_options(self, **options) -> None:
        """改统一变换的选项；认不出的键直接忽略（同 ``set_distortion_options``）。

        可用的键与取值范围见 ``consts.py``：``interpolation`` / ``clipping`` /
        ``direction`` / ``guide`` / ``show_preview`` / ``compose_preview`` /
        ``opacity``（0–100）/ ``constrain``+``value`` / ``pivot_op``+``value`` /
        ``snap_pivot`` / ``lock_pivot``。
        """
        interpolation = options.get("interpolation")
        if interpolation in {value for _label, value in INTERPOLATIONS}:
            self._xf_interpolation = interpolation
        clipping = options.get("clipping")
        if clipping in {value for _label, value in CLIPPINGS}:
            self._xf_clipping = clipping
        direction = options.get("direction")
        if direction in {value for _label, value in DIRECTIONS}:
            self._xf_direction = direction
        guide = options.get("guide")
        if guide in {value for _label, value in GUIDES}:
            self._xf_guide = guide
        if "show_preview" in options:
            self._xf_show_preview = bool(options["show_preview"])
        if "compose_preview" in options:
            self._xf_compose_preview = bool(options["compose_preview"])
        if "opacity" in options:
            self._xf_preview_opacity = max(
                0, min(100, int(options["opacity"])))
        if "snap_pivot" in options:
            self._xf_snap_pivot = bool(options["snap_pivot"])
        if "lock_pivot" in options:
            self._xf_lock_pivot = bool(options["lock_pivot"])
        op = options.get("constrain")
        if op in _CONSTRAIN_KEYS:
            self._xf_constraints[op] = bool(options.get("value", True))
        op = options.get("pivot_op")
        if op in _PIVOT_KEYS:
            self._xf_pivot_ops[op] = bool(options.get("value", True))
        self._sync_float()
        self._sync_overlay()

    def set_transform_about_pivot(self, about: bool) -> None:
        """「从轴心」总开关：三个动作（缩放/切变/透视）一起切。

        保留旧入口（自测与老调用方在用它）；面板上是**三个独立复选框**，
        走 :meth:`set_transform_pivot_op`。
        """
        self._xf_about_pivot = bool(about)
        if about:
            for op in _PIVOT_KEYS:
                self._xf_pivot_ops[op] = True

    def set_transform_pivot_op(self, op: str, on: bool) -> None:
        """「从轴心 (Ctrl)」单个动作：勾上后该动作以轴心为锚。"""
        if op in _PIVOT_KEYS:
            self._xf_pivot_ops[op] = bool(on)

    def set_transform_constraint(self, op: str, on: bool) -> None:
        """「限制 (Shift)」单个动作：移动 45° / 缩放等比 / 旋转 15° /
        切变贴边 / 透视沿对角线。"""
        if op in _CONSTRAIN_KEYS:
            self._xf_constraints[op] = bool(on)

    def set_transform_reshape(self, on: bool) -> None:
        """「调整范围」模式：拖手柄/边 = 收小变换区域，而不是缩放内容。

        进入时必须丢掉未应用的变换预览——浮层与填白底都是按**旧区域**
        快照做的，区域一变它们就与画布对不上了。退出（收边完成/取消
        勾选）后保留收小的区域，下一次拖动即以它为变换对象。
        """
        on = bool(on)
        if on and (self._xf_touched or self._float_item is not None):
            self._clear_transform_preview()
            self._xf = QTransform()
            self._xf_touched = False
        self._xf_reshape = on
        self._sync_overlay()
        self._sync_cursor()

    # ------------------------------------------------------------ 手柄几何
    def _transform_local_rect(self) -> QRectF | None:
        """变换对象矩形（原图坐标）：拖起来之后是锁定快照，之前是当前选区。"""
        rect = self._xf_rect if self._xf_rect is not None else self._rect
        return None if rect is None else rect.normalized()

    def _transform_local_corners(self) -> list[QPointF]:
        """四个角在**原图坐标**里的位置，顺序 = ``tl/tr/br/bl``。"""
        rect = self._transform_local_rect()
        assert rect is not None          # 调用方都已判过选区非空
        return [rect.topLeft(), rect.topRight(),
                rect.bottomRight(), rect.bottomLeft()]

    def _transform_local_handles(self) -> dict[str, QPointF]:
        """全部手柄在**原图坐标**里的位置（透视小菱形不含偏置，见下）。"""
        rect = self._transform_local_rect()
        assert rect is not None
        width, height = rect.width(), rect.height()

        def at(u: float, v: float) -> QPointF:
            return QPointF(rect.x() + width * u, rect.y() + height * v)

        points = {name: at(*uv) for name, uv in _CORNER_UV.items()}
        for name, (u, v) in (("t", (0.5, 0.0)), ("b", (0.5, 1.0)),
                             ("l", (0.0, 0.5)), ("r", (1.0, 0.5))):
            points[name] = at(u, v)
        # 每边 1 个切变菱形，参数化起点 = 该边"顺时针那侧"的角（见 consts.SHEAR_AT）
        for edge, param in _EDGE_UV.items():
            points[f"s_{edge}"] = at(*param(SHEAR_AT))
        return points

    def _transform_handle_points(self) -> dict[str, QPointF]:
        """全部手柄的**场景坐标**（= 原图坐标经 ``_xf``）。

        透视小菱形按 ``PERSP_INSET_VIEW_PX`` 沿"框内对角线"偏置——现在是
        **0（与角方框同心）**，用户 2026-10-09 口径：「四个边角的菱形要在方块
        正中心」。偏置量除以当前倍率，缩放到任何倍率下视觉大小都一致。
        """
        world = {name: self._visual_xf().map(point)
                 for name, point in self._transform_local_handles().items()}
        if PERSP_INSET_VIEW_PX > 0.0:
            # 只有需要微调偏心时才走这段（见 consts 该常量的说明）；同心时
            # 菱形中心直接就是角点，不绕这一圈。
            inset = PERSP_INSET_VIEW_PX / max(self._zoom, 1e-6)
            for key in CORNER_HANDLES:
                corner = world[key]
                direction = QPointF(0.0, 0.0)
                for neighbour in _CORNER_NEIGHBOURS[key]:
                    step = world[neighbour] - corner
                    length = math.hypot(step.x(), step.y())
                    if length > 1e-6:
                        direction += QPointF(step.x() / length, step.y() / length)
                length = math.hypot(direction.x(), direction.y())
                if length > 1e-9:
                    direction = QPointF(direction.x() / length,
                                        direction.y() / length) * inset
                world[f"p_{key}"] = corner + direction
        else:
            for key in CORNER_HANDLES:
                world[f"p_{key}"] = world[key]
        return world

    def _edge_handles_active(self, corners: dict[str, QPointF] | None = None
                             ) -> bool:
        """边上的方框/菱形这份要不要"接管"命中（框太小就只留角手柄）。

        框在屏幕上比手柄还小时，4 个缩放方框 + 8 个切变菱形会糊成一团，
        随便一按就把内容斜掉——那种情况下只保留角手柄 + 框内移动。
        """
        if corners is None:
            corners = self._transform_quad()
        view = [QPointF(self.mapFromScene(corners[key]))
                for key in CORNER_HANDLES]
        lengths = [QLineF(view[index], view[(index + 1) % 4]).length()
                   for index in range(4)]
        return min(lengths) >= EDGE_HANDLE_MIN_VIEW_PX

    def _transform_quad(self) -> dict[str, QPointF]:
        """变换后选区四角（图片坐标）：手柄几何与命中测试的几何来源。

        ⚠️ 用**视觉矩阵**（:meth:`_visual_xf`）而不是 ``_xf``：校正（向后）
        模式下框必须跟浮层内容同向（内容走 ``_preview_xf``），否则
        「图片和操作框方向相反」。
        """
        rect = self._transform_local_rect()
        assert rect is not None
        xf = self._visual_xf()
        return {
            "tl": xf.map(rect.topLeft()), "tr": xf.map(rect.topRight()),
            "br": xf.map(rect.bottomRight()), "bl": xf.map(rect.bottomLeft()),
        }

    # ------------------------------------------------------------ 节点高亮
    def _set_handle_focus(self, name: str | None) -> None:
        """把"当前节点"换成 ``name``（``None`` = 谁都不亮）。

        这是"点哪个节点、哪个节点亮"的唯一入口：悬停（``_update_hover_cursor``）
        与按下（``_begin_transform_drag``）都走它，所以**悬停与激活是同一套
        状态**，不会出现"按下了却高亮在别处"。变的时候才推一次覆盖层。
        """
        if name == self._focus_handle:
            return
        self._focus_handle = name
        if self._tool == "transform" and not self._xf_reshape:
            self._sync_overlay()

    # ------------------------------------------------------------ 预览
    def _preview_xf(self, source: QTransform) -> QTransform:
        """把「源帧」变换换算成**预览帧**变换（= 真正会被烘焙的那个）。

        ``方向 = 校正（向后）`` 时烘焙用的是**反向**矩阵（GIMP 的 Corrective
        口径：框摆到歪掉的那一块上，出来的是被掰正的），预览必须跟着取逆，
        否则"看到的内容落在哪儿"和"松手之后落在哪儿"是两回事。正向直接原样。
        """
        if self._xf_direction != "backward":
            return QTransform(source)
        inverse, ok = source.inverted()
        return inverse if ok else QTransform(source)

    def _visual_xf(self) -> QTransform:
        """累计矩阵的**视觉版**：屏幕上"框与内容"真正呈现的那个矩阵。

        正向 = ``_xf`` 本身；**校正（向后）= ``_xf`` 的逆**（与浮层内容、
        烘焙同口径，见 :meth:`_preview_xf`）。覆盖层（四边形框 / 手柄 /
        参考线 / 轴心）与拖拽数学都吃它——旧版框画的是 ``_xf``、内容走的
        是 ``_preview_xf``，校正模式下两套口径各动各的 ⇒「图片和操作框
        方向相反」（用户 2026-10-09 报障）。
        """
        return self._preview_xf(self._xf)

    def _apply_visual(self, visual: QTransform) -> None:
        """把**视觉空间**里算好的矩阵落账回 :attr:`_xf`（唯一写入口）。

        校正（向后）时 ``_xf`` 存的是视觉矩阵的**逆**（烘焙用反向矩阵，
        见 ``_commit_transform`` / ``compose_transform``），所以这里按方向
        取逆；正向原样存。所有变换操作（拖拽与 ``transform_*`` 语义入口）
        都改成"先在视觉空间叠矩阵，再交给这里落账"——矩阵不可逆的病态
        （理论上到不了，透视那边已挡）退回恒等，绝不存一个炸矩阵。
        """
        if self._xf_direction == "backward":
            inverse, ok = visual.inverted()
            self._xf = inverse if ok else QTransform()
        else:
            self._xf = QTransform(visual)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()

    def _ensure_transform_preview(self) -> None:
        """锁定选区并搭起实时预览：底图（"纸"）+ 选区内容浮层。

        只在第一次真正抓取时做一次（拿两张快照），后续拖动只改 ``_xf``、
        重新渲染浮层像素、改浮层的图元变换，不动真图。

        两层的分工（2026-10-09 重定，修"只旋转也画错"）：

        * **底图 = 原图矩形那块的"残余"**：原图里**选区之外**的部分照旧，选区
          那块**擦成透明**（用户 2026-10-09：「图片旋转不再有白色的区域」），
          范围**恒定**＝原图矩形、不跟变换走（见 :meth:`_base_target_rect`）。
          ⚠️ 旧版正向留着**整张原图**，于是"图转过来了、原来的图还在原地"
          叠着看——用户报的正是这个；再往后一版又把底图跟着旋转外框长大，
          成了"白底一路涨、看着在漂"（同一用户的下一轮报障）。
        * **浮层 = 变换后的选区内容**：拖动中由图元做变换（
          :meth:`_apply_float_fast`，亚毫秒级），松手 / 首次走逐像素重采样
          （:meth:`_render_float_plane`）。旧版把矩阵在"渲染像素"和"图元变换"
          里各套了一次 ⇒ 内容被转了两遍、还被画布边界裁掉一半（用户报的
          "图片不完整显示"）。
        """
        if self._float_item is not None or self._image is None \
                or self._rect is None:
            return
        # ⚠️ 延迟供像素（2026-10-10「切换卡顿」）：恢复会话进工具时只挂了
        #    矩阵和框，upright 反变换（秒级重活）被推迟到这一刻才算——第一
        #    次真正需要像素（建预览 = 第一次拖动/语义入口）时发信号让弹窗
        #    补（带进度框）。补不上（无数据/失败/取消）就整组放弃，退回
        #    普通会话，本方法继续走"从画布选区拍快照"那条路。
        if self._xf_restore_pending:
            if self._xf_restore_region is None:
                self.restore_pixels_requested.emit()
                if self._xf_restore_region is None:
                    self.abort_content_restore()
            self._xf_restore_pending = False
        # ⚠️ 内容节点恢复会话（2026-10-10）：浮层像素源＝sidecar 反变换出的
        #    upright 内容，选区局部矩形＝rect0（upright 整幅）——**画布不动**，
        #    不像普通会话那样从 ``_image`` 拍快照（用户口径「PB1 作为画布，
        #    PA1 作为可操作区域恢复」）。
        restore = self._xf_restore_region
        if restore is not None:
            rect = QRectF(0, 0, restore.width(), restore.height())
            self._xf_region = QImage(restore)
        else:
            rect = self._rect.normalized()
            self._xf_region = self._image.copy(rect.toRect())
        self._xf_rect = QRectF(rect)
        # 预览降采样：浮层像素按预算缩一版（``TRANSFORM_PREVIEW_PIXELS``）。
        # 拖动中这一版**直接**当浮层画布用（不重采样，见 ``_float_fast_plane``），
        # 所以它同时也是"拖动中看到的清晰度"；松手后它是精确档的采样源。
        area = max(1, self._xf_region.width() * self._xf_region.height())
        self._xf_preview_scale = min(
            1.0, math.sqrt(TRANSFORM_PREVIEW_PIXELS / area))
        if self._xf_preview_scale < 0.999:
            self._xf_preview_region = self._xf_region.scaled(
                max(1, int(round(self._xf_region.width()
                                 * self._xf_preview_scale))),
                max(1, int(round(self._xf_region.height()
                                 * self._xf_preview_scale))),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        else:
            self._xf_preview_region = self._xf_region
        self._xf_preview_direction = self._xf_direction
        # 底图＝原图矩形那块的残余（选区擦透明）；范围恒定，不跟变换走
        self._rebuild_backdrop()
        assert self._item is not None
        self._float_item = QGraphicsPixmapItem()
        self._float_item.setTransformationMode(
            Qt.TransformationMode.SmoothTransformation)
        self._float_item.setZValue(5)
        self._scene.addItem(self._float_item)
        self._sync_float()

    def _set_base_pixmap(self) -> None:
        """把 ``_paint_image`` 贴到底图图元上，按 ``_xf_base_origin`` 摆位。

        ``_xf_base_scale`` 非空时额外套一层缩放——整幅选区时底图是**一片空**
        （选区整块被搬走，没有残余可画），用 1×1 透明图拉大即可，不必为每个
        新尺寸新建一张 12 MP 的图。
        """
        assert self._item is not None
        self._item.setPixmap(QPixmap.fromImage(self._paint_image))
        self._item.setPos(self._xf_base_origin)
        scale = self._xf_base_scale
        self._item.setTransform(
            QTransform() if scale is None
            else QTransform().scale(scale.x(), scale.y()))
        self._item.setVisible(True)

    def make_transform_pending(self) -> None:
        """**挂起**这次变换：松手后保留预览，等离开工具再烘焙（GIMP 口径）。

        ⚠️ 这是"能不能实时预览"的关键（用户 2026-10-09 报障）：原来松手就把
        整幅重采样一遍（12 MP 约 11 秒），所以只能"最后才看到结果"。现在松手
        只是**记下"有东西没应用"**，内容继续由画布上的浮层实时显示——拖动中
        连像素都不重采样（见 :meth:`_apply_float_fast`），随便转多少圈都不用等。

        **例外**：选区的预览版大到连一帧都出不来时（:meth:`_realtime_budget`）
        就退回"松手即烘焙"——宁可慢一次，也不要拖不动的假实时。
        """
        if self.transform_pending() is None:
            return
        if not self._realtime_budget():
            self.transform_committed.emit()
            return
        self._xf_pending = True

    def has_pending_transform(self) -> bool:
        """有"已预览但还没烘焙"的变换？（弹窗据此在切工具/完成时收尾）"""
        return self._xf_pending and self.transform_pending() is not None

    def reset_transform_preview_flags(self) -> None:
        """取消"挂起"标记（松手后不烘焙那一支走这里），矩阵与预览都留着。"""
        self._xf_pending = False

    def _realtime_budget(self) -> bool:
        """选区（预览版）够不够小到能实时出画面？够 = 可以挂起不烘焙。

        ⚠️ 拖动本身已经不受这条约束了（拖动中不重采样，见
        :meth:`_apply_float_fast`）；它现在管的是**松手那一帧**的精确重采样
        成本——预览版按 ``TRANSFORM_PREVIEW_PIXELS`` 缩过，所以正常恒为真，
        留作"预算被改小 / 选区异常大"时的兜底。
        """
        if self._xf_preview_region is None:
            return False
        pixels = (self._xf_preview_region.width()
                  * self._xf_preview_region.height())
        return pixels <= TRANSFORM_PREVIEW_PIXELS * 1.05

    def _placed_xf(self) -> QTransform:
        """烘焙矩阵的**摆位部分**：选区局部坐标 → 图片坐标。

        就是 ``geometry.compose_transform`` 里的 ``placed``（
        ``translate(选区左上角) * 真正会被烘焙的那个矩阵``），预览的底图范围、
        精确浮层的像素矩阵、拖动中的图元矩阵全部从它派生——**一处定义**，
        免得三个地方各写一遍 ``translate * preview_xf`` 而其中一处忘了跟方向走。
        """
        rect = self._xf_rect
        assert rect is not None
        return (QTransform().translate(rect.x(), rect.y())
                * self._preview_xf(self._xf))

    def _bake_canvas_rect(self) -> QRectF:
        """**烘焙画布**的矩形 = 提交后那张图占多大（与 ``compose_transform`` 同块）。

        ⚠️ 它现在**只**用来决定"越界内容裁到哪"（:meth:`_plane_clip_rect`），
        **不再**是预览底图的范围（底图已恒定，见 :meth:`_base_target_rect`）。
        ``geometry.transform_region`` 给出的正是「调整」档烘焙结果的外框（变换后
        内容的外框 ∪ 选区之外的原图残余）；「裁剪到原画布」保持原尺寸；「裁剪到
        原比例」是先长再居中裁回原始长宽比（与 ``center_crop_aspect`` 同一套取整）。
        """
        if self._xf_rect is None or self._image is None:
            return QRectF()
        if self._xf_clipping == "clip":
            return QRectF(self.image_rect())
        x0, y0, width, height = transform_region(
            self._image, self._xf_rect.normalized(), self._placed_xf())
        grown = QRectF(x0, y0, width, height)
        if self._xf_clipping == "aspect":
            return _center_crop_rect(grown, self._image.width(),
                                     self._image.height())
        return grown

    def _base_target_rect(self) -> QRectF:
        """底图覆盖的矩形 = **原图矩形，恒定不动**。

        ⚠️ 用户 2026-10-09 口径：「白底不应该扩大，应该是图片初始位置和大小」
        ——旧版把它跟着**旋转外框**（= 烘焙画布，见 :meth:`_bake_canvas_rect`）
        每帧重算：整幅旋转 30° 就涨到 920×992、原点还跑到 (-160,-96)，再叠上
        ``setSceneRect`` 一起变 ⇒ 看着就是"白底和图片位置一直在漂"。

        现在它**恒定**：旋转只换上方浮层的内容，底下这块"地盘"永远钉在图片当初
        的位置和尺寸上（也不再外扩余量——不会长大就不需要余量）。
        """
        if self._image is None:
            return QRectF()
        return QRectF(self.image_rect())

    def _plane_clip_rect(self) -> QRectF | None:
        """浮层内容要按哪块裁（图片坐标）；``None`` = 不裁（「调整」档）。

        烘焙在 ``clip`` 档是"保持原画布、超出的内容裁掉"，``aspect`` 档是
        "先长再居中裁回原比例"——两种都会把越界内容切掉，预览不跟着切就是
        "预览比烘焙多出一块"。
        """
        if self._xf_clipping == "adjust":
            return None
        return self._bake_canvas_rect()

    def _base_current_rect(self) -> QRectF:
        """底图图元**此刻**盖住的矩形（图片坐标；含 1×1 空图的缩放）。"""
        if self._paint_image is None:
            return QRectF()
        scale = self._xf_base_scale
        if scale is None:
            size = QSizeF(self._paint_image.width(), self._paint_image.height())
        else:
            size = QSizeF(self._paint_image.width() * scale.x(),
                          self._paint_image.height() * scale.y())
        return QRectF(self._xf_base_origin, size)

    def _backdrop_needs_resize(self) -> bool:
        """底图还要不要再铺一次？—— 拖动中**恒为 False**。

        ⚠️ 底图范围已**恒定**＝原图矩形（见 :meth:`_base_target_rect`），旋转不再
        让它长大，所以拖动中一次都不用重铺——这正是"白底不再漂"的来源；旧版
        每帧拿旋转外框比一次、涨出余量就重铺 12 MP，既是卡顿来源也是漂移来源。

        留这个判断只为兜住"选区被换掉"这一种情形：整幅 ↔ 局部会切换"1×1 空图"
        那条捷径，残影必须按新选区重画。拖动期间 ``_xf_rect`` 是冻住的，不会走到。
        """
        if self._paint_image is None or self._xf_rect is None:
            return True
        return (self._xf_base_scale is not None) != self._backdrop_is_whole()

    def _backdrop_is_whole(self) -> bool:
        """选区是不是整幅（此时没有任何"原图残余"要画，纸就是纯白）？"""
        if self._image is None or self._xf_rect is None:
            return False
        if self._xf_restore_region is not None:
            # 恢复会话：整个画布的内容（PA1）都被"搬上浮层"了，纸＝纯透明。
            # PB1 的四角本来就是透明的，视觉与打开时完全一致（零跳变）。
            return True
        rect = self._xf_rect.normalized()
        return (abs(rect.left()) < 0.5 and abs(rect.top()) < 0.5
                and abs(rect.width() - self._image.width()) < 0.5
                and abs(rect.height() - self._image.height()) < 0.5)

    def _rebuild_backdrop(self) -> None:
        """重铺底图：内容被搬走的选区那块**擦成透明**，选区之外保留原图。

        **两个方向共用这一套**：「校正（向后）」那边 ``_preview_xf`` 给的是
        **反向**矩阵，底图与内容的位置自动跟着反向走。

        范围**恒定**＝原图矩形（:meth:`_base_target_rect`，不再外扩余量、也不跟
        变换走）。整幅选区时"选区之外"为空 ⇒ 底下什么都没有，用一张 1×1 透明图
        + 图元缩放表示：换尺寸只是改个矩阵，12 MP 上也是零成本。

        ⚠️ 与 ``_ensure_transform_preview`` 的区别是**不重建浮层**：只换底图像素。
        """
        assert self._image is not None and self._xf_rect is not None
        target = self._base_target_rect().toAlignedRect()
        self._xf_base_origin = QPointF(target.x(), target.y())
        if self._backdrop_is_whole():
            self._paint_image = _blank_image()
            self._xf_base_scale = QPointF(float(target.width()),
                                          float(target.height()))
        else:
            self._paint_image = self._paper_image(target)
            self._xf_base_scale = None
        self._set_base_pixmap()

    def _paper_image(self, target: QRect) -> QImage:
        """底图：**原图残余**（选区那块擦成透明），画布 = ``target``（图片坐标）。

        ⚠️ 擦除必须走 ``CompositionMode_Clear``：直接"填一个透明色"只是盖上一层
        全透明像素、底下的原图照旧（``SourceOver`` 不会替换），选区那块就擦不掉。
        擦完露出下层画布条纹格 —— 那就是"这里已经空了"。
        """
        assert self._image is not None and self._xf_rect is not None
        frame = QImage(target.size(), QImage.Format.Format_ARGB32)
        frame.fill(QColor(0, 0, 0, 0))
        painter = QPainter(frame)
        painter.drawImage(QPointF(-target.x(), -target.y()), self._image)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self._xf_rect.normalized().translated(
            -target.x(), -target.y()), QColor(0, 0, 0, 0))
        painter.end()
        return frame

    def _preview_placement_xf(self) -> QTransform:
        """浮层像素矩阵：**预览尺度选区局部坐标 → 预览尺度图片坐标**。

        就是烘焙矩阵（``选区局部坐标 → 图片坐标``，见 ``compose_transform``
        里的 ``placed``）的降采样版本：``S(k) ∘ placed ∘ S(1/k)``。两边的
        ``S`` 一个都不能少——只缩结果的话，``warp_placement`` 里的目标外框
        按未缩放的尺度算，12 MP 时每帧都要重采样整幅（实测 1756 ms/帧）。

        ``warp_placement`` 用它算出来的 ``(x0, y0)`` = 变换后选区的外框左上角
        （在预览图片坐标里），浮层据此摆位（见 :meth:`_float_placement`）。

        ⚠️⚠️ **Qt 的 ``A * B`` 是"先 A 后 B"**（行向量约定），所以"先降采样、
        再套变换、最后放大回预览尺度"要写成 ``S(1/k) * placed * S(k)``。旧版写
        成了 ``S(k) * placed * S(1/k)``——数学记号里 ``S(k) ∘ placed ∘ S(1/k)``
        是对的，但落到 QTransform 上左右正好颠倒，于是矩阵整体变成
        ``placed(k·u)/k``：**平移量被多除了一个 k**。k=1（选区 ≤0.5 MP）时
        看不出来，图一大（k≈0.6）内容就整体偏 ``t·(1/k−1)``——用户报的
        「操作框跟图片分离、格子跟图片相互远离」正是它（600×800 只有 0.48 MP，
        所以旧自测一直是绿的 ⇒ 判据必须用**大于预览预算**的图）。

        ⚠️ 这个矩阵**只用来渲染浮层像素**（即松手后的精确档）。旧版又拿它当
        浮层图元的 transform 用了一遍 ⇒ 内容被转两遍、还被固定大小的画布裁掉
        一半（用户报的"旋转后图片不完整显示"）。拖动中的图元矩阵是另一条
        （见 :meth:`_float_fast_xf`），两者的口径**故意不同**。
        """
        scale = max(self._xf_preview_scale, 1e-6)
        return (QTransform().scale(1.0 / scale, 1.0 / scale)
                * self._placed_xf()
                * QTransform().scale(scale, scale))

    def _float_placement(self) -> QTransform:
        """浮层图元的变换：预览尺度像素 → 图片坐标（**纯缩放 + 平移**）。

        浮层像素活在"图片坐标 ÷ ``_xf_preview_scale``"里、左上角在
        ``_xf_preview_origin``，所以这里只需"挪回原位、再放大回去"。变换本身
        已经在像素里烘好了，这里**再套一次就是双重变换**。

        ⚠️ 这是**精确档**（松手 / 首次）的口径；拖动中像素没有烘过，变换必须
        由图元承担 ⇒ 那时用 :meth:`_float_fast_xf`（带旋转/切变/透视）。
        """
        scale = max(self._xf_preview_scale, 1e-6)
        origin = self._xf_preview_origin
        return (QTransform().scale(1.0 / scale, 1.0 / scale)
                * QTransform().translate(origin.x(), origin.y()))

    def _float_fast_xf(self) -> QTransform:
        """**拖动中**浮层图元的变换：预览缩放的**区域局部坐标** → 图片坐标。

        ``_xf_preview_region`` 是选区原图按 ``_xf_preview_scale`` 缩出来的，
        它的像素 ``u`` 对应选区局部的 ``u / k``，所以"区域局部 → 图片"= 先
        ``S(1/k)`` 再 ``placed``（见 :meth:`_placed_xf`）。

        ⚠️⚠️ 同样要按 Qt 的"**先左后右**"来写：``S(1/k) * placed``。旧版写成
        ``placed * S(1/k)`` ⇒ 变成 ``placed(u)/k``，平移量被多除一个 k，拖动中
        的内容同样偏出去（与 :meth:`_preview_placement_xf` 是同一个错，两处
        必须一起改，否则松手会跳）。

        ⚠️ 与 :meth:`_float_placement` 的区别就是**它自带变换本身**（旋转/切变/
        透视都在里面）：那边像素烘过了、图元只能缩放平移；这边像素是原图、
        变换必须由图元做。混用 = 内容被转两遍或被原地不动。
        """
        scale = max(self._xf_preview_scale, 1e-6)
        return (QTransform().scale(1.0 / scale, 1.0 / scale)
                * self._placed_xf())

    def _float_fast_plane(self) -> QImage:
        """**拖动中**的浮层像素：预览缩放的选区**原图**，越界部分按裁剪掩膜。

        ⚠️ 为什么不再逐像素重采样（见 :meth:`_render_float_plane`）：那是
        150–450 ms/帧 的量级（实测 12 MP 选区 `linear` 158 ms、`nohalo` 442 ms），
        拖动根本跟不上——用户报的"旋转不能实时"就是这个。改成"像素不重采样、
        变换交给图元"之后由 Qt 光栅器做，**实测 0.4–1.5 ms/帧**；而且只重采样
        一趟（不再"缩小→再放大"），**画面反而比逐像素预览更清晰**。

        代价是插值只能用 Qt 的平滑档（双线性），吃不到用户的 `nohalo/cubic`
        选项——所以松手那一帧仍然走精确档，"预览 == 烘焙"的判据一点没松
        （见 :meth:`finish_transform_drag`）。

        裁剪（``clip`` / ``aspect`` 档）在拖动中同样要生效，否则内容会溢出
        到画布外、松手一瞬间又"跳"回去。拖动的图元矩阵是仿射/投影，
        把裁剪矩形**逆映射回区域局部坐标**会得到一个平行四边形，用
        ``QPainterPath`` 掩膜即可（实测 +0.5–1 ms/帧）。
        """
        region = (self._xf_preview_region if self._xf_preview_region is not None
                  else self._xf_region)
        if region is None or region.isNull():
            return region
        clip = self._plane_clip_rect()
        if clip is None:
            return region
        local, ok = self._float_fast_xf().inverted()
        if not ok:                                # 病态矩阵：宁可不裁
            return region
        path = QPainterPath()
        path.addRect(clip)
        # ⚠️ 要清掉的是**裁剪矩形之外**的部分。``setClipPath`` 是把笔限制在
        #    路径**之内**，直接配 ``CompositionMode_Clear`` 会清反（实测
        #    "该留的透明、该清的留着"，画面看着像内容整块消失）——所以先取
        #    补集路径再清，与 :meth:`_cut_plane` 的四块补集同一个意思。
        outside = QPainterPath()
        outside.addRect(QRectF(region.rect()))
        masked = region.copy()
        painter = QPainter(masked)
        painter.setClipPath(outside.subtracted(local.map(path)),
                            Qt.ClipOperation.ReplaceClip)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(QRectF(masked.rect()), QColor(0, 0, 0, 0))
        painter.end()
        return masked

    def _apply_float_fast(self) -> None:
        """拖动中的浮层：换像素 + 让图元承担变换，**不做逐像素重采样**。

        ⚠️ 最后必须把"已重采样"的判据 :attr:`_xf_preview_keyframe` 清掉：
        拖动一结束（``_xf_dragging`` 变 False）:meth:`_sync_float` 就会看到
        判据为空、重出一帧**精确**结果。不清的话会留着这张"原图 + 图元变换"
        的快照，而图元矩阵下一秒被换成 :meth:`_float_placement`（坐标口径
        完全不同）⇒ 画面跳变。
        """
        assert self._float_item is not None
        self._float_item.setPixmap(QPixmap.fromImage(self._float_fast_plane()))
        self._float_item.setTransform(self._float_fast_xf())
        self._xf_preview_keyframe = None

    def _render_float_plane(self) -> None:
        """（重）画浮层：**变换后的选区内容**（空白处透明）。—— **精确档**。

        ⚠️ 只在这里碰"浮层的像素"，别在 ``_sync_float`` 里画整幅变换——
        ``_sync_float`` 每次鼠标移动都会被调到，而逐像素重采样是大头。
        画布取 ``warp_placement`` 给的外框，所以内容搬到画外也**不会被裁**。

        ⚠️ 本方法只在**非拖动**时被调用（``_sync_float`` 拖动中走
        :meth:`_apply_float_fast`）：逐像素重采样一帧 150–450 ms，拖动根本
        跟不上。所以这里直接用用户选的插值出**与烘焙同一套数学**的结果，
        不存在"拖动中先用轻量档垫一下"的分支了。
        """
        if self._float_item is None or self._xf_rect is None \
                or self._xf_region is None:
            return
        region = (self._xf_preview_region if self._xf_preview_region is not None
                  else self._xf_region)
        warp = warp_placement(
            region, self._preview_placement_xf(), self._xf_interpolation)
        if warp is None:                      # 取消 / 病态矩阵：不画内容
            warp = (QImage(), 0, 0)
        image, x0, y0 = warp
        # ⚠️ ``warp_placement`` 回来的 ``(x0, y0)`` 在**预览尺度**坐标里（矩阵的
        #    输出系），而 :attr:`_xf_preview_origin` 与 :meth:`_float_placement`、
        #    :meth:`_cut_plane` 的口径都是**图片坐标** ⇒ 这里除一次降采样倍率。
        #    不除的话浮层会被挪走 ``x0·(1−1/k)`` 那么多（图越大偏得越狠）。
        self._xf_preview_origin = QPointF(
            x0 / max(self._xf_preview_scale, 1e-6),
            y0 / max(self._xf_preview_scale, 1e-6))
        image = self._cut_plane(image)
        self._float_item.setPixmap(QPixmap.fromImage(image))
        self._xf_preview_keyframe = self._preview_placement_xf()

    def _cut_plane(self, image: QImage) -> QImage:
        """按 :meth:`_plane_clip_rect` 把浮层越界的内容抹成透明（同烘焙）。

        浮层像素坐标 ``p`` 与图片坐标 ``i`` 的关系是 ``i = (p + 原点) / 倍率``
        （见 :meth:`_float_placement`），所以"画布矩形"换算到浮层里就是
        ``倍率 × 画布 − 原点``；四块补集各清一次，不必引 QPainterPath。
        """
        clip = self._plane_clip_rect()
        if clip is None or image.isNull() or self._image is None:
            return image
        scale = max(self._xf_preview_scale, 1e-6)
        origin = self._xf_preview_origin
        keep = QRectF(scale * clip.x() - origin.x(),
                      scale * clip.y() - origin.y(),
                      scale * clip.width(), scale * clip.height())
        inside = keep.intersected(QRectF(image.rect()))
        if inside == keep:
            return image
        bounds = QRectF(image.rect())
        cut = image.copy()
        painter = QPainter(cut)
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear)
        for part in (
            QRectF(bounds.left(), bounds.top(),
                   bounds.width(), inside.top() - bounds.top()),
            QRectF(bounds.left(), inside.bottom(),
                   bounds.width(), bounds.bottom() - inside.bottom()),
            QRectF(bounds.left(), inside.top(),
                   inside.left() - bounds.left(), inside.height()),
            QRectF(inside.right(), inside.top(),
                   bounds.right() - inside.right(), inside.height()),
        ):
            if part.width() > 0 and part.height() > 0:
                painter.fillRect(part, QColor(0, 0, 0, 0))
        painter.end()
        return cut

    def finish_transform_drag(self) -> None:
        """松手：把预览从"拖动快档"升回**精确档**（与烘焙同一套数学）。

        拖动中像素不重采样、变换交给图元（亚毫秒级，见
        :meth:`_apply_float_fast`）；松手瞬间图不再动，这一次重采样只做一遍
        （用户看不到卡），于是**松手后看到的预览就是烘焙结果**——"预览 ==
        烘焙"的判据一点没松。
        """
        if not self._xf_dragging:
            return
        self._xf_dragging = False
        # 拖动中是"原图 + 图元变换"，松手要重出一帧精确结果 ⇒ 判据清零
        self._xf_preview_keyframe = None
        self._sync_float()

    def _sync_float(self) -> None:
        """浮层跟随累计矩阵 + 预览开关（不透明度 / 显示预览 / 合成预览）。

        两条**故意不同**的路（用户 2026-10-09 报障「只旋转不能实时渲染」）：
        ``_xf_dragging`` 为真 = 拖动中 ⇒ :meth:`_apply_float_fast`（像素不重采样、
        变换交给图元，亚毫秒级）；为假 = 首次 / 松手后 ⇒ :meth:`_render_float_plane`
        出**与烘焙同一套数学**的精确结果。松手时 :meth:`finish_transform_drag`
        会把 ``_xf_dragging`` 关掉并让判据失效，于是立刻补上精确那一帧。

        方向切换时底图会失效（它按"那一刻的矩阵"画好了结果），所以这里发
        现方向与建预览时不一致就整块重建——否则画面会停在旧方向上骗人。
        ⚠️ 恢复会话的浮层源（upright）要**跨重建保留**：重建只是换方向，
        不是结束恢复。
        """
        if self._float_item is None or self._xf_rect is None:
            return
        if self._xf_preview_direction != self._xf_direction:
            restore = self._xf_restore_region
            self._clear_transform_preview()
            self._xf_restore_region = restore
            self._ensure_transform_preview()
            return
        # 底图范围恒定（= 原图矩形），拖动中不会长大 ⇒ 这里几乎恒不触发；
        # 只有"选区被换掉"（整幅 ↔ 局部）时才要重铺残影
        if self._backdrop_needs_resize():
            self._rebuild_backdrop()
        if self._xf_dragging:
            self._apply_float_fast()
        else:
            # ⚠️ 只有**重采样结果**真变了才重算像素（判据 = 那个矩阵，含降采样）；
            #    没变就只挪图元，省掉一次逐像素重采样。
            if self._xf_preview_keyframe != self._preview_placement_xf():
                self._render_float_plane()
            # ⚠️ 图元只做**摆位**（缩放 + 平移）：变换已经在像素里烘好了
            self._float_item.setTransform(self._float_placement())
        self._float_item.setOpacity(
            max(0.0, min(1.0, self._xf_preview_opacity / 100.0)))
        self._float_item.setVisible(bool(self._xf_show_preview))
        # 「合成预览」关掉 = 只看变形的那一块，「纸」也一并藏起来
        if self._item is not None:
            self._item.setVisible(bool(self._xf_compose_preview))
        # 变换把选区送出原边界时，浮层会跑到图片外——扩场景矩形才看得见
        self._sync_scene_rect()

    def _clear_transform_preview(self) -> None:
        """撤掉预览浮层并把底图恢复成真像素（矩阵不动，见 reset_transform）。"""
        if self._float_item is not None:
            self._scene.removeItem(self._float_item)
            self._float_item = None
        if self._paint_image is not None:
            self._paint_image = None
            self._xf_region = None
            self._xf_preview_region = None
            self._xf_preview_scale = 1.0
            self._xf_preview_keyframe = None
            self._xf_rect = None
            self.refresh()
        self._xf_restore_region = None   # 恢复会话一并结束（换图/换工具/重置）
        self._xf_restore_pending = False  # 延迟供像素的"挂起"也一样结束
        if self._item is not None:
            self._item.setVisible(True)   # 「合成预览」关掉过的话要还回来
            self._item.setPos(0.0, 0.0)   # 向后预览的底图被挪过位置，要还回来
            self._item.setTransform(QTransform())   # 1×1 空底的拉伸也要还
        self._xf_base_origin = QPointF(0.0, 0.0)
        self._xf_base_scale = None
        self._xf_preview_origin = QPointF(0.0, 0.0)
        # 浮层没了 → 场景矩形收回图片边界（变换曾把浮层送出图外时扩过）
        self._sync_scene_rect()

    def reset_transform(self) -> None:
        """「重置」：丢弃未应用的变换，选区回到整幅、轴心回到中心。"""
        self._clear_transform_preview()
        self._xf = QTransform()
        self._xf_touched = False
        self._xf_pivot_saved = None      # 重置连轴心一起归位
        if not self.image_rect().isNull():
            self._rect = QRectF(self.image_rect())
            self._xf_pivot = self._rect.center()
        self._sync_overlay()

    def transform_pending(self) -> tuple[QRectF, QTransform, QImage] | None:
        """未应用的变换 ``(选区, 矩阵, 选区像素快照)``；没有则 None。"""
        if (not self._xf_touched or self._xf_rect is None
                or self._xf_region is None):
            return None
        return (QRectF(self._xf_rect), QTransform(self._xf),
                QImage(self._xf_region))

    # ---- 内容节点恢复（二次编辑，2026-10-10） ----
    def consume_content_restore(self) -> None:
        """标记 sidecar 恢复已处理（无数据/失败/完成）：本会话不再触发。"""
        self._content_restore_done = True

    def begin_restored_transform(self, xf: QTransform,
                                 region: QImage | None = None,
                                 rect0: QRectF | None = None) -> None:
        """把恢复出来的矩阵挂成**未触摸**的待定变换（画布保持文件原样）。

        用户 2026-10-10 口径：「编辑 PB1 图片的时候，正常显示的是 PB1；
        执行统一形变的时候，PB1 要作为画布，PA1 要作为可操作的区域恢复」：

        * **画布（``_image``）一个像素都不换**：仍是落盘文件 PB1（内容四边形
          PA1 已烘焙在内、四角透明）；
        * ``region``（upright 内容，sidecar 反变换产物）成为浮层像素源，
          选区局部矩形＝rect0（upright 整幅）；纸面清空，浮层正好盖在 PB1
          里已烘焙的内容上——视觉与打开时完全一致（零跳变）；
        * 矩阵 ``xf``＝**画布系**总量矩阵（弹窗已把 sidecar 的文件系 V 平移
          到 PB1 坐标）：框/手柄/轴心立刻落在 PA1 四边形上（＝上次保存前
          的操作状态）；
        * ⚠️ ``_xf_touched`` **保持 False**：用户不再动就没有任何烘焙（切
          工具/「完成」都不重采样，零代次损失）；一旦拖动，走正常挂起→
          烘焙链，烘焙输入＝upright、矩阵＝总量 ⇒ 每次保存只损失一次
          重采样代次。

        ⚠️⚠️ **延迟供像素**（2026-10-10「切换卡顿」）：``region`` 为 ``None``
        时**只**挂矩阵、框（``rect0``＝sidecar 里的 rect0，必传）和轴心——
        **不**建预览、**不**算 upright 反变换（那是秒级重活，之前每次进
        变换工具都要等它，用户报的正是这个）。像素推迟到第一次建预览
        （＝第一次拖动）时由 :meth:`_ensure_transform_preview` 经
        ``restore_pixels_requested`` 向弹窗要。之前把反变换算好再调
        ``begin_restored_transform(seed, upright)`` 的旧入口原样可用。
        """
        if self._tool != "transform" or self._image is None:
            return
        if region is None:
            if rect0 is None or rect0.isEmpty():
                return
            self._xf_restore_pending = True
            self._xf_restore_region = None
            self._xf_rect = QRectF(rect0)
            self._xf = QTransform(xf)
            self._xf_pivot = self._xf_rect.center()
            self._sync_overlay()
            return
        if not region.isNull():
            self._xf_restore_region = QImage(region)
        self._xf_restore_pending = False
        self._ensure_transform_preview()
        self._xf = QTransform(xf)
        if self._xf_rect is not None:
            # 轴心跟着换到 rect0（upright 局部坐标）中心：视觉上＝内容四边形
            # 中心，旋转/缩放的语义与"保存前那一刻"一致。
            self._xf_pivot = self._xf_rect.center()
        self._sync_float()
        self._sync_overlay()

    # ---- 变换操作（拖拽处理器与自测共用的语义级入口） ----
    def transform_move(self, dx: float, dy: float) -> None:
        """整体平移 ``dx, dy``（图片像素，**视觉方向**）。"""
        self._ensure_transform_preview()
        # 先已有的变换，再平移：(T * Move) 先 T 后 Move
        self._apply_visual(
            self._visual_xf() * QTransform().translate(dx, dy))

    def transform_rotate(self, degrees: float) -> None:
        """绕**轴心当前视觉位置**旋转（轴心保持不动）。

        ⚠️ 在**视觉空间**里叠旋转：校正（向后）模式下内容与框也同向转
        （旧版直接转 ``_xf`` ⇒ 图片和操作框方向相反，用户 2026-10-09 报障）。
        """
        self._ensure_transform_preview()
        visual = self._visual_xf()
        center = visual.map(self._xf_pivot)
        self._apply_visual(visual * rotate_about(center, degrees))

    def transform_scale(self, sx: float, sy: float,
                        anchor: QPointF | None = None) -> None:
        """缩放（局部空间，锚点缺省=轴心；sx/sy 是相对当前内容的倍率）。"""
        self._ensure_transform_preview()
        point = QPointF(anchor) if anchor is not None else self._xf_pivot
        sx = sx if abs(sx) > 1e-6 else 1.0
        sy = sy if abs(sy) > 1e-6 else 1.0
        # 局部操作发生在视觉矩阵**之前**：(S * V) 先 S 后 V
        self._apply_visual(scale_about(point, sx, sy) * self._visual_xf())

    def transform_scale_axis(self, edge: str, factor: float,
                             anchor: QPointF | None = None) -> None:
        """**单轴**缩放：抓 ``edge``（l/r/t/b）方向的边，只改这一个轴。

        这是统一变换相对"只能整体放大缩小"的关键补充：横拉左边=只改宽度、
        竖拉上边=只改高度。锚点缺省 = 对边中点（拖动时锚在轴心）。
        """
        rect = self._transform_local_rect()
        if rect is None:
            return
        if edge not in _SIDE_ANCHOR:
            edge = "r"
        point = (QPointF(anchor) if anchor is not None
                 else _SIDE_ANCHOR[edge](rect))
        factor = factor if abs(factor) > 1e-3 else 1e-3
        if edge in ("l", "r"):
            self.transform_scale(factor, 1.0, point)
        else:
            self.transform_scale(1.0, factor, point)

    def transform_shear(self, edge: str, k: float) -> None:
        """拖边切变：``edge`` 是被抓的边（l/r/t/b），``k`` 是切变系数，
        对边为锚（抓右边往下拖 = 内容随 x 增大而下斜）。"""
        self._ensure_transform_preview()
        self._apply_visual(self._apply_shear(
            edge, k, self._visual_xf(),
            self._pivot_ops().get("shear", False)))

    def transform_perspective(self, corner: str, point: QPointF) -> None:
        """把 ``corner`` 这个角拖到 ``point``（图片坐标）——投影（透视）。

        四个角各自可动 ⇒ 平面不再是平行四边形：扫描件拍歪、书页中间鼓起
        这类"四条边对不上"的情况靠它掰正（GIMP 的透视手柄同款）。

        ⚠️ 拖成自交 / 塌陷（把角推到对角附近）的那一步会被
        :func:`_perspective_step` 判为病态并**丢弃**——保持原样，绝不把
        "把内容放大百万倍"的矩阵交给重采样（那会崩，见该函数）。
        """
        self._ensure_transform_preview()
        if self._xf_rect is None or corner not in CORNER_HANDLES:
            return
        visual = self._visual_xf()
        quad = [visual.map(p) for p in self._transform_local_corners()]
        index = CORNER_HANDLES.index(corner)
        step = _perspective_step(visual, quad, index, QPointF(point),
                                 self._xf_rect)
        if step is None:
            return
        # 投影重映射发生在**画布坐标**里：先视觉矩阵，再补这一步 A ⇒ `visual * A`
        self._apply_visual(visual * step)

    def transform_flip(self, horizontal: bool = True) -> None:
        """绕选区中心翻转（内容镜像；提交时由弹窗烘焙成一步）。

        ⚠️ 在**视觉空间**里叠镜像（``F * 视觉矩阵``）：正向与旧版完全一致；
        校正（向后）模式下旧版直接叠 ``_xf``，视觉上变成"先转再绕**原位**
        中心镜像"，与拖拽/旋转的视觉口径不一致。
        """
        self._ensure_transform_preview()
        rect = self._transform_local_rect()
        if rect is None:
            return
        self._apply_visual(
            flip_transform(rect, horizontal) * self._visual_xf())

    def _pivot_ops(self) -> dict[str, bool]:
        """「从轴心」的三个开关（含旧的 ``_xf_about_pivot`` 总开关）。"""
        ops = dict(self._xf_pivot_ops)
        if self._xf_about_pivot:
            for op in _PIVOT_KEYS:
                ops[op] = True
        return ops

    def _constrain(self, op: str, modifiers) -> bool:
        """「限制」是否生效：勾选态 **异或** 按着 Shift（GIMP 口径）。

        GIMP 原文是"按住 Shift = 把没勾的勾上、勾了的取消"，所以这里必须
        用异或而不是"或"——勾了「缩放等比」时按住 Shift 反而要自由缩放。
        """
        return bool(self._xf_constraints.get(op, False)) != bool(
            modifiers & Qt.KeyboardModifier.ShiftModifier)

    def _from_pivot(self, op: str, modifiers) -> bool:
        """「从轴心」是否生效（Ctrl 同理：异或 ⇒ Ctrl 是临时取反）。"""
        return self._pivot_ops().get(op, False) != bool(
            modifiers & Qt.KeyboardModifier.ControlModifier)

    def _transform_side_anchor(self, edge: str) -> QPointF:
        """抓某条边做**单轴缩放**时的锚点 = 对边中点（选区局部坐标）。"""
        rect = self._transform_local_rect()
        assert rect is not None
        return _SIDE_ANCHOR[edge if edge in _SIDE_ANCHOR else "r"](rect)

    def _shear_anchor(self, edge: str) -> QPointF:
        """抓某条边上的**切变菱形**时的不动点（选区局部坐标）。

        正好对应用户给的切变口径「被抓的边不离开原边线」：抓左边时**右边整条
        不动**、抓上边时**下边整条不动**（GIMP 默认那档）。锚点取对边的
        **起点角一侧**——与 ``_EDGE_UV`` 的参数化起点同侧，菱形往哪边偏都
        不会让锚点跟着漂（锚点只由 "对边 + 该边起点角" 决定）。
        """
        rect = self._transform_local_rect()
        assert rect is not None
        if edge in ("l", "r"):
            anchor_x = rect.right() if edge == "l" else rect.left()
            return QPointF(anchor_x, rect.top())
        anchor_y = rect.bottom() if edge == "t" else rect.top()
        return QPointF(rect.left(), anchor_y)

    def _snap_pivot(self, point: QPointF) -> QPointF:
        """轴心吸附（「轴心 · 吸附」）：靠近中心/四角就贴上去。

        阈值按**视图像素**折算——缩得越小越容易吸附，与"眼睛看着差不多
        就吸上去"的直觉一致。
        """
        rect = self._xf_rect.normalized()
        threshold = PIVOT_VIEW_PX / max(self._zoom, 1e-6) * 1.5
        targets = [rect.center(), rect.topLeft(), rect.topRight(),
                   rect.bottomRight(), rect.bottomLeft()]
        nearest = min(targets, key=lambda t: QLineF(t, point).length())
        if QLineF(nearest, point).length() <= threshold:
            return QPointF(nearest)
        return point

    # ---- 拖拽状态机（交互 Mixin 调用；都返回/更新 self._mode 的形状） ----
    def _begin_transform_drag(self, hit: str, pos: QPointF,
                              modifiers) -> tuple | None:
        """按命中结果进入一次统一变换拖拽；返回 ``_mode`` 元组（None = 不拖）。

        锚点、起始点一律取**按下瞬间的快照**：拖动过程中每次都从快照重算
        （而不是在上一帧结果上叠加），所以来回甩鼠标不会累积误差，松手回到
        原位也能精确复原。
        """
        # ⚠️ 延迟供像素的那次等待里有模态进度框（processEvents），用户可能
        #    已经松开了左键——那个 release 被进度框的事件循环吃掉了，画布
        #    永远等不到；不查的话"拖动"会一直挂着，鼠标移动就跟着变形。
        #    ⚠️ 只在**这次按下真的经历了等待**时才查（ waited）：测试用裸
        #    构造的 QMouseEvent 不经过 Qt 的按钮状态机，一律查会把它们误杀。
        waited_for_restore = (self._xf_restore_pending
                              and self._xf_restore_region is None)
        self._ensure_transform_preview()
        if self._float_item is None or self._xf_rect is None:
            return None
        if waited_for_restore and not (
                QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            return None
        # 按下的节点立刻成为"激活节点"（高亮跟随），不冒泡到移动/旋转
        self._set_handle_focus(hit if hit in _HANDLE_HITS else None)
        self._xf_dragging = True
        rect = self._xf_rect.normalized()
        # ⚠️ 拖拽数学全程在**视觉空间**里做（快照 = 视觉矩阵）：鼠标逆映射、
        #    透视四角、旋转中心全按屏幕上看到的框算；落账时经
        #    :meth:`_apply_visual` 按方向存回 ``_xf``。旧版快照 ``_xf``、
        #    框画的是 ``_preview_xf``，校正模式下鼠标和框各走各的。
        v_start = self._visual_xf()
        inverse, _ = v_start.inverted()
        if hit == "pivot":
            if self._xf_lock_pivot:
                return None
            return ("xf_pivot", inverse)
        if hit in PERSP_HANDLES:
            quad = [v_start.map(point)
                    for point in self._transform_local_corners()]
            return ("xf_persp", v_start, quad,
                    CORNER_HANDLES.index(hit[2:]))
        if hit in CORNER_HANDLES:
            opposite = {"tl": rect.bottomRight(), "tr": rect.bottomLeft(),
                        "bl": rect.topRight(), "br": rect.topLeft()}[hit]
            anchor = (self._xf_pivot if self._from_pivot("scale", modifiers)
                      else QPointF(opposite))
            return ("xf_scale", v_start, inverse.map(pos), anchor, hit)
        if hit in SIDE_HANDLES:
            anchor = (self._xf_pivot if self._from_pivot("scale", modifiers)
                      else self._transform_side_anchor(hit))
            return ("xf_scale1", v_start, inverse.map(pos), anchor, hit)
        if hit in SHEAR_HANDLES:
            # 切变按"光标总共挪了多远"算，所以快照**光标点**（不是菱形中心）：
            # 菱形只占边的 ¾ 处一小块，用户抓的其实是整条边，被抓的那一点
            # 必须跟着光标走——否则鼠标在菱形上按下后一移，边会跳一下。
            # ⚠️ 存进 mode 的点必须是**选区局部坐标**（过一次视觉矩阵的逆），
            #    否则拖动时"局部位移"会把矩阵的平移量一起算进去（实测抓
            #    ¾ 处的菱形拖 60px，被抓的边跑了 560px）。
            return ("xf_shear", v_start, inverse.map(pos), hit[2])
        if hit in ("inside", "center"):
            return ("xf_move", v_start, pos)
        center = v_start.map(self._xf_pivot)            # 框外 = 绕轴心旋转
        angle0 = math.degrees(math.atan2(
            pos.y() - center.y(), pos.x() - center.x()))
        return ("xf_rotate", v_start, center, angle0)

    def _apply_transform_drag(self, mode: tuple, pos: QPointF,
                              modifiers) -> None:
        """把一次拖拽应用到**视觉矩阵**（每种模式都从"按下快照"重算）。

        各分支先在视觉空间里算出 ``visual``，末尾统一经
        :meth:`_apply_visual` 按方向落账回 ``_xf``——正向行为与旧版逐位
        一致（视觉矩阵 = ``_xf``），校正（向后）模式从此框随鼠标走。
        """
        kind = mode[0]
        if kind == "xf_pivot":
            inverse = mode[1]
            assert self._xf_rect is not None
            point = clamp_rect(
                QRectF(inverse.map(pos), QSizeF(0, 0)),
                self._xf_rect.normalized()).topLeft()
            self._xf_pivot = self._snap_pivot(point) if self._xf_snap_pivot \
                else point
            # 记进"用户摆过的轴心"：提交/换工具/换图后仍然绕它转
            # （``core._xf_pivot_saved``——不这样，反复旋转会越转越小）
            self._xf_pivot_saved = QPointF(self._xf_pivot)
            # 拖轴心**不改矩阵**（浮层原样），只把轴心圆点挪过去
            self._sync_overlay()
            return
        v_start, visual = mode[1], None
        if kind == "xf_move":
            start = mode[2]
            delta = pos - start
            if self._constrain("move", modifiers):
                delta = _snap_45(delta)
            visual = v_start * QTransform().translate(delta.x(), delta.y())
        elif kind == "xf_rotate":
            _, v_start, center, angle0 = mode
            angle = math.degrees(math.atan2(
                pos.y() - center.y(), pos.x() - center.x()))
            delta = (angle - angle0 + 180.0) % 360.0 - 180.0
            if self._constrain("rotate", modifiers):
                delta = round(delta / ROTATE_SNAP_DEG) * ROTATE_SNAP_DEG
            # 旋转发生在视觉矩阵之后（轴心是视觉位置）：(V * R) 先 V 后 R
            visual = v_start * rotate_about(center, delta)
        elif kind in ("xf_scale", "xf_scale1"):
            _, v_start, p0_local, anchor, hit = mode
            inverse, _ = v_start.inverted()
            current = inverse.map(pos)
            sx = _axis_ratio(current.x(), p0_local.x(), anchor.x())
            sy = _axis_ratio(current.y(), p0_local.y(), anchor.y())
            if kind == "xf_scale1":
                # 单轴：只有垂直于被抓那条边的那个轴动，另一个轴锁死
                if hit in ("l", "r"):
                    sy = 1.0
                else:
                    sx = 1.0
            elif self._constrain("scale", modifiers):
                sx = sy = (sx + sy) / 2.0            # 等比（GIMP 的 Scale 约束）
            # 局部操作发生在视觉矩阵**之前**：(S * V) 先 S 后 V
            visual = scale_about(anchor, sx, sy) * v_start
        elif kind == "xf_shear":
            _, v_start, start_local, edge = mode
            inverse, _ = v_start.inverted()
            # ``start_local`` 与 ``pos`` 都换到**选区局部坐标**再作差：这样得到的
            # 是"光标在框内走了多远"，与边本身当前被摆到哪里无关。
            delta = inverse.map(pos) - start_local
            assert self._xf_rect is not None
            rect = self._xf_rect.normalized()
            # 系数 = 光标沿边方向的位移 ÷ **这条边自身的方向跨度**。
            # 抓右/左边是**水平切变**（y' = y + sh·x）：要让右缘整条下移 d，
            # sh 必须是 d/**宽度**（用高度算的话右缘只会挪 d·w/h，跟手差一截）。
            # 抓上/下边同理用**高度**（x' = x + sv·y）。
            k = (delta.y() / rect.width() if edge in ("l", "r")
                 else delta.x() / rect.height())
            visual = self._apply_shear(
                edge, k, v_start, self._from_pivot("shear", modifiers))
        elif kind == "xf_persp":
            _, v_start, quad, index = mode
            target = QPointF(pos)
            if self._constrain("perspective", modifiers):
                target = _on_diagonal(quad, index, target)
            assert self._xf_rect is not None
            step = _perspective_step(v_start, quad, index, target,
                                     self._xf_rect)
            if step is not None:                     # 退化 / 病态：这一步不动
                visual = v_start * step
        if visual is None:
            return
        self._apply_visual(visual)

    def _apply_shear(self, edge: str, k: float, x_start: QTransform,
                     from_pivot: bool = False) -> QTransform:
        """在 ``x_start`` 基础上叠一次切变，**返回新矩阵**（不直接落账）。

        调用方（语义入口/拖拽）拿到结果后经 :meth:`_apply_visual` 按方向
        写回 ``_xf``。``x_start`` 一律传**视觉矩阵**。

        ``from_pivot=False``（GIMP 默认）：**对边固定**，抓的这条边整条平移；
        ``from_pivot=True``：绕轴心切变，两边反向各走一半。
        """
        assert self._xf_rect is not None
        if from_pivot:
            pivot = QPointF(self._xf_pivot)
            if edge in ("l", "r"):
                return shear_about(
                    pivot, 0.0, k if edge == "r" else -k) * x_start
            return shear_about(
                pivot, k if edge == "b" else -k, 0.0) * x_start
        anchor = self._shear_anchor(edge)      # 对边整条不动
        if edge in ("l", "r"):
            sv = -k if edge == "l" else k
            return shear_about(anchor, 0.0, sv) * x_start
        sh = -k if edge == "t" else k
        return shear_about(anchor, sh, 0.0) * x_start

    # ------------------------------------------------------------ 命中
    def _hit_transform(self, view_pos: QPointF) -> str:
        """统一变换的命中测试（视图像素口径，不随缩放变）。

        **节点优先、绝不冒泡**（用户 2026-10-09 明确要求：点节点就必须是那个
        节点，不能掉进"移动图片"或"旋转"）。优先级：

        轴心 → **透视小菱形** → **四角大方框** → **四边中方框** →
        **切变菱形** → 整条边（顺手抓边＝单轴缩放）→ 框内（移动）→ 框外（旋转）。

        ⚠️ 两个"必须"：
        1. 透视小菱形排在角方框**之前**——它嵌在角方框里。两类手柄**同心**
           （用户 2026-10-09 口径：「四个边角的菱形要在方块正中心」）之后，
           "角点归谁"改由**半径**分：离角点 ≤ ``PERSP_HIT_VIEW_PX`` ⇒ 透视，
           再往外到 ``CORNER_HIT_VIEW_PX`` 的方形环带 ⇒ 双轴缩放（方框描边
           那一圈仍点得着缩放，两类手柄互不抢）；
        2. 切变菱形排在**整条边命中带之前**——边带是 8px 的带状区域，菱形正好
           落在带内，顺序反了切变就永远点不着。
        """
        if self._rect is None:
            return "outside"
        corners = self._transform_quad()
        pivot_view = QPointF(self.mapFromScene(
            self._visual_xf().map(self._xf_pivot)))
        if QLineF(view_pos, pivot_view).length() <= PIVOT_VIEW_PX / 2.0 + 3.0:
            return "pivot"
        if not self._xf_reshape:
            points = self._transform_handle_points()
            keys = {name: QPointF(self.mapFromScene(point))
                    for name, point in points.items()}
            radius = HANDLE_HIT_VIEW_PX
            for name in PERSP_HANDLES:
                if QLineF(view_pos, keys[name]).length() <= PERSP_HIT_VIEW_PX:
                    return name
            for name in CORNER_HANDLES:
                point = keys[name]
                if abs(view_pos.x() - point.x()) <= CORNER_HIT_VIEW_PX \
                        and abs(view_pos.y() - point.y()) <= CORNER_HIT_VIEW_PX:
                    return name
            if self._edge_handles_active(corners):
                for name in SIDE_HANDLES:
                    if QLineF(view_pos, keys[name]).length() <= radius + 2.0:
                        return name
                for name in SHEAR_HANDLES:      # 必须先于下面的整条边命中带
                    if QLineF(view_pos, keys[name]).length() \
                            <= SHEAR_HIT_VIEW_PX:
                        return name
                # 整条边都在命中带里（抓边 = 单轴缩放，与裁剪的手感一致）
                for name, (a, b) in _EDGE_CORNERS.items():
                    if _dist_to_segment(view_pos, keys[a], keys[b]) \
                            <= EDGE_BAND_VIEW_PX:
                        return name
        scene = self.mapToScene(view_pos.toPoint())
        quad = QPolygonF([corners["tl"], corners["tr"],
                          corners["br"], corners["bl"]])
        if quad.containsPoint(scene, Qt.FillRule.OddEvenFill):
            return "inside"
        return "outside"

    # ------------------------------------------------------------ 覆盖层
    def _sync_transform_overlay(self) -> None:
        """变换工具的覆盖层：四边形选框 + 四类手柄（跟随矩阵变形）+ 轴心。

        ⚠️ 虚线框**只有一个**：跟着内容转的 ``_quad``。固定在原位的 ``_border``
        保留、但画成**细实线**（见 ``core._border_pen``）——它是"这张纸的边界"，
        不再是第二条虚线（用户 2026-10-09 报障「同时存在两个框的虚线、颜色还不
        一样」）。
        """
        for item in self._mask:
            item.setVisible(False)
        self._sel_border.setVisible(False)
        for item in self._edge_lines.values():
            item.setVisible(False)
        corners = self._transform_quad()
        quad = QPolygonF([corners["tl"], corners["tr"],
                          corners["br"], corners["bl"], corners["tl"]])
        self._quad.setPolygon(quad)
        self._quad.setVisible(True)
        zoom = max(self._zoom, 1e-6)
        points = self._transform_handle_points()
        square = CORNER_VIEW_PX / zoom
        for name in CORNER_HANDLES:
            point = points[name]
            self._handles[name].setRect(
                QRectF(point.x() - square / 2, point.y() - square / 2,
                       square, square))
            self._handles[name].setVisible(True)
        active = self._edge_handles_active(corners)
        side = SIDE_VIEW_PX / zoom
        for name in SIDE_HANDLES:
            point = points[name]
            self._handles[name].setRect(
                QRectF(point.x() - side / 2, point.y() - side / 2, side, side))
            self._handles[name].setVisible(active)
        shear = SHEAR_VIEW_PX / 2.0 / zoom
        for name in SHEAR_HANDLES:
            self._diamonds[name].setPolygon(_diamond(points[name], shear))
            self._diamonds[name].setVisible(active)
        persp = PERSP_VIEW_PX / 2.0 / zoom
        for name in PERSP_HANDLES:
            self._persp[name].setPolygon(_diamond(points[name], persp))
            self._persp[name].setVisible(True)
        # 节点底色：**默认中空，只有"当前节点"实心**（用户 2026-10-09：「操作
        # 节点未选中不要有背景色，拉伸方块不要用绿色，而是中空的」）。四类节点
        # 共用一套配色，形状才是语义（方框=缩放、菱形=切变/透视）。
        # ⚠️ 透视小菱形与角方框**同心**（``PERSP_INSET_VIEW_PX == 0``），两者
        # 是"同一个角"的两张脸 ⇒ 焦点在角（``tl``）或菱形（``p_tl``）上时
        # **一起实心**，否则"点亮了角、嵌在角里的菱形还是空的"看着像两个东西。
        focus = self._focus_handle
        focus_key = focus[2:] if focus and focus.startswith("p_") else focus
        for group in (self._handles, self._diamonds, self._persp):
            for name, item in group.items():
                key = name[2:] if name.startswith("p_") else name
                _style_node(item, focus_key is not None and key == focus_key)
        self._sync_focus_ring(points, active, zoom)
        pivot = self._visual_xf().map(self._xf_pivot)
        radius = PIVOT_VIEW_PX / 2.0 / zoom
        self._pivot_item.setRect(
            QRectF(pivot.x() - radius, pivot.y() - radius,
                   radius * 2, radius * 2))
        self._pivot_item.setVisible(True)
        self._sync_transform_guides(corners)

    def _sync_focus_ring(self, points: dict[str, QPointF], edges_active: bool,
                         zoom: float) -> None:
        """把"激活节点"的高亮环套到当前节点上（没激活就藏起来）。

        环按**节点自己的形状**留出余量：方框套方环（比它大一圈）、菱形/透视
        小菱形也套方环（菱形外接框再放宽一点），轴心圆点套小方环。这样无论
        哪类节点被点中都看得见"亮的是它"。
        """
        name = self._focus_handle
        if not name:
            self._focus_ring.setVisible(False)
            return
        margin = 5.0 / zoom
        if name in CORNER_HANDLES:
            size = CORNER_VIEW_PX
        elif name in SIDE_HANDLES:
            if not edges_active:
                self._focus_ring.setVisible(False)
                return
            size = SIDE_VIEW_PX
        elif name in SHEAR_HANDLES:
            if not edges_active:
                self._focus_ring.setVisible(False)
                return
            size = SHEAR_VIEW_PX
        elif name in PERSP_HANDLES:
            size = PERSP_VIEW_PX
        elif name == "pivot":
            size = PIVOT_VIEW_PX
        else:
            self._focus_ring.setVisible(False)
            return
        half = (size / max(zoom, 1e-6)) / 2.0 + margin
        point = (self._visual_xf().map(self._xf_pivot) if name == "pivot"
                 else points.get(name))
        if point is None:
            self._focus_ring.setVisible(False)
            return
        self._focus_ring.setRect(
            QRectF(point.x() - half, point.y() - half, half * 2, half * 2))
        self._focus_ring.setVisible(True)

    def _sync_transform_guides(self, corners: dict[str, QPointF]) -> None:
        """按选项画构图参考线（三分/五分/黄金分割/对角线）——跟着框一起变形。"""
        for item in self._guides:
            item.setVisible(False)
        ratios = GUIDE_RATIOS.get(self._xf_guide)
        if ratios:
            entries = ([("h", ratio) for ratio in ratios]
                       + [("v", ratio) for ratio in ratios])
        elif self._xf_guide == "diagonal":
            entries = [("d", 0.0), ("d", 1.0)]
        else:
            return
        for item, (kind, ratio) in zip(self._guides, entries):
            if kind == "h":
                start, end = (quad_point(corners, 0.0, ratio),
                              quad_point(corners, 1.0, ratio))
            elif kind == "v":
                start, end = (quad_point(corners, ratio, 0.0),
                              quad_point(corners, ratio, 1.0))
            else:
                start, end = (quad_point(corners, 0.0, ratio),
                              quad_point(corners, 1.0, 1.0 - ratio))
            item.setLine(QLineF(start, end))
            item.setVisible(True)


def _diamond(center: QPointF, radius: float) -> QPolygonF:
    """以 ``center`` 为中心、半对角线为 ``radius`` 的菱形（切变/透视手柄）。"""
    return QPolygonF([
        QPointF(center.x(), center.y() - radius),
        QPointF(center.x() + radius, center.y()),
        QPointF(center.x(), center.y() + radius),
        QPointF(center.x() - radius, center.y()),
    ])
