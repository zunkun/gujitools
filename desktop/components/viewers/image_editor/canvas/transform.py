# -*- coding: utf-8 -*-
"""画布 Mixin：**统一变换**（GIMP 口径：缩放/切变/旋转/移动 + 调整范围）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsPixmapItem

from ..consts import EDGE_BAND_VIEW_PX, HANDLE_VIEW_PX, PIVOT_VIEW_PX
from ..geometry import _dist_to_segment, rotate_about, scale_about, shear_about
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class TransformMixin(CanvasHost):
    """变换工具：实时预览浮层 + 变换矩阵 + 变换框覆盖层。"""

    # ------------------------------------------------------------ 变换
    def set_transform_about_pivot(self, about: bool) -> None:
        """「从轴心」：缩放/切变以轴心为锚（旋转永远绕轴心）。"""
        self._xf_about_pivot = bool(about)


    def set_transform_reshape(self, on: bool) -> None:
        """「调整范围」模式：拖手柄/边=收小变换区域，而不是缩放内容。

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


    def _ensure_transform_preview(self) -> None:
        """锁定选区并搭起实时预览：底图填白 + 选区快照浮层。

        只在第一次真正抓取时做一次（拿两张整图快照），后续拖动只改
        ``_xf`` 与浮层的 transform，不再碰像素。
        """
        if self._float_item is not None or self._image is None \
                or self._rect is None:
            return
        rect = self._rect.normalized()
        self._xf_rect = QRectF(rect)
        self._xf_region = self._image.copy(rect.toRect())
        self._paint_image = self._image.copy()
        painter = QPainter(self._paint_image)
        painter.fillRect(rect, QColor("#ffffff"))
        painter.end()
        # ⚠️ _item 是 QGraphicsRectItem | None；上面那道判空判的是 _image/_rect。
        #    走到这里说明预览确实搭起来了（_sync_float 也这么用），显式收窄。
        assert self._item is not None
        self._item.setPixmap(QPixmap.fromImage(self._paint_image))
        self._float_item = QGraphicsPixmapItem(
            QPixmap.fromImage(self._xf_region))
        self._float_item.setZValue(5)
        self._scene.addItem(self._float_item)
        self._sync_float()


    def _sync_float(self) -> None:
        """浮层跟随累计矩阵：选区像素 (u,v) → 原图坐标 → 画布位置。"""
        if self._float_item is None or self._xf_rect is None:
            return
        tl = self._xf_rect.topLeft()
        # (A*B) 先 A 后 B：先平移到选区原位，再套累计矩阵
        self._float_item.setTransform(
            QTransform().translate(tl.x(), tl.y()) * self._xf)
        # 变换把选区送出原边界时，浮层会跑到图片外——扩场景矩形才看得见
        # （用户 2026-10-02：超出原边界的内容不能丢）
        self._sync_scene_rect()


    def _clear_transform_preview(self) -> None:
        """撤掉预览浮层并把底图恢复成真像素（矩阵不动，见 reset_transform）。"""
        if self._float_item is not None:
            self._scene.removeItem(self._float_item)
            self._float_item = None
        if self._paint_image is not None:
            self._paint_image = None
            self._xf_region = None
            self._xf_rect = None
            self.refresh()
        # 浮层没了 → 场景矩形收回图片边界（变换曾把浮层送出图外时扩过）
        self._sync_scene_rect()


    def reset_transform(self) -> None:
        """「重置」：丢弃未应用的变换，选区回到整幅、轴心回到中心。"""
        self._clear_transform_preview()
        self._xf = QTransform()
        self._xf_touched = False
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


    # ---- 变换操作（拖拽处理器与自测共用的语义级入口） ----
    def transform_move(self, dx: float, dy: float) -> None:
        """整体平移 ``dx, dy``（图片像素）。"""
        self._ensure_transform_preview()
        # 先已有的变换，再平移：(T * Move) 先 T 后 Move
        self._xf = self._xf * QTransform().translate(dx, dy)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()


    def transform_rotate(self, degrees: float) -> None:
        """绕**轴心当前视觉位置**旋转（轴心保持不动）。"""
        self._ensure_transform_preview()
        center = self._xf.map(self._xf_pivot)
        self._xf = self._xf * rotate_about(center, degrees)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()


    def transform_scale(self, sx: float, sy: float,
                        anchor: QPointF | None = None) -> None:
        """缩放（局部空间，锚点缺省=轴心；sx/sy 是相对当前内容的倍率）。"""
        self._ensure_transform_preview()
        point = QPointF(anchor) if anchor is not None else self._xf_pivot
        sx = sx if abs(sx) > 1e-6 else 1.0
        sy = sy if abs(sy) > 1e-6 else 1.0
        # 局部操作发生在累计矩阵**之前**：(S * T) 先 S 后 T
        self._xf = scale_about(point, sx, sy) * self._xf
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()


    def transform_shear(self, edge: str, k: float) -> None:
        """拖边切变：``edge`` 是被抓的边（l/r/t/b），``k`` 是切变系数，
        对边为锚（抓右边往下拖 = 内容随 x 增大而下斜）。"""
        self._ensure_transform_preview()
        self._apply_shear(edge, k, self._xf)
        self._xf_touched = True
        self._sync_float()
        self._sync_overlay()


    def _apply_shear(self, edge: str, k: float, x_start: QTransform) -> None:
        """在 ``x_start`` 基础上叠一次切变（拖拽中按拖动起点取绝对量）。"""
        # ⚠️ 调用方（transform_shear / 拖拽分支）都先 _ensure_transform_preview，
        #    也就是 _xf_rect 已建立；这里显式收窄（运行时同原行为）。
        assert self._xf_rect is not None
        rect = self._xf_rect.normalized()
        if edge in ("l", "r"):
            anchor_x = rect.right() if edge == "l" else rect.left()
            sv = -k if edge == "l" else k
            self._xf = shear_about(
                QPointF(anchor_x, rect.top()), 0.0, sv) * x_start
        else:
            anchor_y = rect.bottom() if edge == "t" else rect.top()
            sh = -k if edge == "t" else k
            self._xf = shear_about(
                QPointF(rect.left(), anchor_y), sh, 0.0) * x_start


    def _transform_quad(self) -> dict[str, QPointF]:
        """变换后选区四角（图片坐标）：8 手柄与命中测试的几何来源。

        ⚠️ 两个调用方（``_sync_overlay`` / ``_hit_transform``）都已在调用前
        判过 ``self._rect is not None``，这里再显式收窄一次：``_xf_rect or
        _rect`` 在两者皆 None 时会 AttributeError（与原运行时行为一致）。
        """
        rect = (self._xf_rect or self._rect)
        assert rect is not None
        rect = rect.normalized()
        xf = self._xf
        return {
            "tl": xf.map(rect.topLeft()), "tr": xf.map(rect.topRight()),
            "br": xf.map(rect.bottomRight()), "bl": xf.map(rect.bottomLeft()),
        }


    def _sync_transform_overlay(self) -> None:
        """变换工具的覆盖层：四边形选框 + 8 手柄（跟随矩阵变形）+ 轴心。"""
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
        hs = HANDLE_VIEW_PX / max(self._zoom, 1e-6)
        points = {
            "tl": corners["tl"], "tr": corners["tr"],
            "bl": corners["bl"], "br": corners["br"],
            "t": QPointF((corners["tl"].x() + corners["tr"].x()) / 2,
                         (corners["tl"].y() + corners["tr"].y()) / 2),
            "b": QPointF((corners["bl"].x() + corners["br"].x()) / 2,
                         (corners["bl"].y() + corners["br"].y()) / 2),
            "l": QPointF((corners["tl"].x() + corners["bl"].x()) / 2,
                         (corners["tl"].y() + corners["bl"].y()) / 2),
            "r": QPointF((corners["tr"].x() + corners["br"].x()) / 2,
                         (corners["tr"].y() + corners["br"].y()) / 2),
        }
        for name, point in points.items():
            self._handles[name].setRect(
                QRectF(point.x() - hs / 2, point.y() - hs / 2, hs, hs))
            self._handles[name].setVisible(True)
        pivot = self._xf.map(self._xf_pivot)
        pr = PIVOT_VIEW_PX / 2.0 / max(self._zoom, 1e-6)
        self._pivot_item.setRect(
            QRectF(pivot.x() - pr, pivot.y() - pr, pr * 2, pr * 2))
        self._pivot_item.setVisible(True)


    def _hit_transform(self, view_pos: QPointF) -> str:
        """变换工具命中测试（视图像素口径，不随缩放变）。

        优先级：轴心 → 角手柄 → 边手柄 → 框内（移动）→ 框外（旋转）。
        """
        if self._rect is None:
            return "outside"
        corners = self._transform_quad()
        pivot = self._xf.map(self._xf_pivot)
        pivot_v = self.mapFromScene(pivot)
        if (QLineF(view_pos, QPointF(pivot_v)).length()
                <= PIVOT_VIEW_PX / 2.0 + 3.0):
            return "pivot"
        view = {name: QPointF(self.mapFromScene(pt))
                for name, pt in corners.items()}
        # 角：方形盒；边：中线点盒 + 整条边的距离带（拖着顺手）
        box = HANDLE_VIEW_PX * 0.9
        for name, pt in view.items():
            if abs(view_pos.x() - pt.x()) <= box \
                    and abs(view_pos.y() - pt.y()) <= box:
                return name
        edges = {
            "t": (view["tl"], view["tr"]), "r": (view["tr"], view["br"]),
            "b": (view["br"], view["bl"]), "l": (view["bl"], view["tl"]),
        }
        for name, (a, b) in edges.items():
            mid = (a + b) / 2.0
            if (QLineF(view_pos, mid).length()
                    <= HANDLE_VIEW_PX * 0.9):
                return name
        for name, (a, b) in edges.items():
            if _dist_to_segment(view_pos, a, b) <= EDGE_BAND_VIEW_PX:
                return name
        scene = self.mapToScene(view_pos.toPoint())
        if QPolygonF([corners["tl"], corners["tr"],
                      corners["br"], corners["bl"]]).containsPoint(
                scene, Qt.FillRule.OddEvenFill):
            return "inside"
        return "outside"
