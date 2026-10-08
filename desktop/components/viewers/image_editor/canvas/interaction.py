# -*- coding: utf-8 -*-
"""画布 Mixin：**鼠标/键盘交互**（缩放平移、工具分流、命中与光标）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QTransform

from ..consts import (
    EDGE_BAND_VIEW_PX, HOVER_CURSORS, MIN_RECT_EDGE, ROTATE_SNAP_DEG, WHEEL_STEP,
)
from ..geometry import clamp_rect, rotate_about, scale_about
from ..text_item import TextBlockItem
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


class InteractionMixin(CanvasHost):
    """交互：滚轮/拖拽/悬停光标/命中测试/擦除/裁剪收边。"""

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._user_zoomed:
            self.fit()  # 用户没动过缩放：窗口怎么变都保持整图可见


    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if not delta or self._item is None:
            return super().wheelEvent(event)
        self.set_zoom(self._zoom * (WHEEL_STEP ** (delta / 120.0)),
                      event.position())
        event.accept()


    # ------------------------------------------------------------ 交互
    def _apply_hover_highlight(self) -> None:
        """悬停/拖动中的边高亮：命中角手柄时相邻两条边一起亮。"""
        active = (
            self._tool in ("crop", "transform")
            and self._rect is not None
            and self._hover_handle is not None
            and (self._tool == "crop" or self._xf_reshape)
        )
        for name, item in self._edge_lines.items():
            # 名字包含判断对单边/角手柄都成立："tl" 含 "t""l"、"bl" 含 "b""l"
            # active 已蕴含 _hover_handle 非 None，这里再显式判一次让类型收窄。
            item.setVisible(
                active and self._hover_handle is not None
                and name in self._hover_handle)


    def _update_hover_cursor(self, view_pos: QPointF) -> None:
        """未拖拽时的悬停反馈：命中边缘给方向缩放光标 + 边界高亮。"""
        if self._tool == "transform" and not self._xf_reshape \
                and self._item is not None:
            hit = self._hit_transform(view_pos)
            if hit in HOVER_CURSORS:
                cursor = HOVER_CURSORS[hit]  # 角/边：方向光标
            elif hit in ("pivot", "inside"):
                cursor = Qt.CursorShape.SizeAllCursor
            elif hit == "outside":
                cursor = Qt.CursorShape.CrossCursor  # 框外拖 = 旋转
            else:
                cursor = Qt.CursorShape.ArrowCursor
            self.viewport().setCursor(cursor)
            return
        if self._tool not in ("crop", "transform") or self._item is None:
            if self._hover_handle is not None:
                self._hover_handle = None
                self._apply_hover_highlight()
            self._sync_cursor()
            return
        handle = self._hit_handle(view_pos)
        if handle != self._hover_handle:
            self._hover_handle = handle
            self._apply_hover_highlight()
        if handle is not None:
            cursor = HOVER_CURSORS.get(handle, Qt.CursorShape.ArrowCursor)
        elif self._rect is not None and \
                self._rect.normalized().contains(
                    self.mapToScene(view_pos.toPoint())):
            cursor = Qt.CursorShape.OpenHandCursor  # 框内 = 可拖动整体
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(cursor)


    def _sync_cursor(self) -> None:
        """按工具换光标：擦除藏系统光标——实圈就是光标（直径=擦除直径）。"""
        if self._tool == "erase":
            self.viewport().setCursor(Qt.CursorShape.BlankCursor)
            return
        cursor = {
            # 裁剪默认有框：箭头（手柄收边/框内移动），不是"准备画框"的十字
            "crop": Qt.CursorShape.ArrowCursor,
            "text": Qt.CursorShape.IBeamCursor,
        }.get(self._tool, Qt.CursorShape.ArrowCursor)
        self.viewport().setCursor(cursor)


    def _hit_handle(self, view_pos: QPointF) -> str | None:
        """手柄/边缘命中测试（全部按视图像素，不随缩放变）。

        不只认 8 个小方块：**整条边**都在命中带内（带宽 EDGE_BAND_VIEW_PX，
        以边线为中心向内外各半），四角的双边交叠区是角手柄——沿边任意
        位置都能抓着向内拖（用户 20:18 定："四边大部分区域都可以向内移动"）。
        """
        if self._rect is None:
            return None
        rect = self.mapFromScene(self._rect.normalized()).boundingRect()
        band = EDGE_BAND_VIEW_PX
        x, y = view_pos.x(), view_pos.y()
        h = ("l" if abs(x - rect.left()) <= band
             else ("r" if abs(x - rect.right()) <= band else ""))
        v = ("t" if abs(y - rect.top()) <= band
             else ("b" if abs(y - rect.bottom()) <= band else ""))
        if h and v:
            return v + h  # tl / tr / bl / br（与手柄命名一致）
        if h and rect.top() - band <= y <= rect.bottom() + band:
            return h
        if v and rect.left() - band <= x <= rect.right() + band:
            return v
        return None


    def mousePressEvent(self, event) -> None:  # noqa: N802
        button = event.button()
        if button in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._mode = ("pan", event.position())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if button != Qt.MouseButton.LeftButton or self._item is None:
            return super().mousePressEvent(event)
        pos = self.mapToScene(event.position().toPoint())
        inside = self.image_rect()
        if self._tool == "crop":
            # 裁剪不做"拖拽画框"（那是截图的交互）：默认全选，只能收边/移动
            handle = self._hit_handle(event.position())
            self._hover_handle = handle
            self._apply_hover_highlight()
            if handle is not None:
                self._mode = ("handle", handle)
            elif self._rect is not None and \
                    self._rect.normalized().contains(pos):
                self._mode = ("move", pos, QPointF(self._rect.topLeft()))
            # 图外/遮罩上按下：不响应（想调框请拖手柄或框内）
            self._sync_overlay()
            event.accept()
            return
        if self._tool == "transform":
            if self._xf_reshape:
                # 「调整范围」：交互与裁剪同款（整条边命中带 + 框内移动），
                # 只是松手后不应用，区域留给变换用
                handle = self._hit_handle(event.position())
                self._hover_handle = handle
                self._apply_hover_highlight()
                if handle is not None:
                    self._mode = ("handle", handle)
                elif self._rect is not None and \
                        self._rect.normalized().contains(pos):
                    self._mode = ("move", pos, QPointF(self._rect.topLeft()))
                self._sync_overlay()
                event.accept()
                return
            hit = self._hit_transform(event.position())
            if hit == "outside":
                # 松手前没建过预览的话，这次按下也不产生任何变换
                self._ensure_transform_preview()
                if self._float_item is None:
                    event.accept()
                    return
                center = self._xf.map(self._xf_pivot)
                angle0 = math.degrees(math.atan2(
                    pos.y() - center.y(), pos.x() - center.x()))
                self._mode = ("xf_rotate", self._xf, center, angle0)
            elif hit == "pivot":
                # ⚠️ 轴心拖动也要先建预览：刚进变换工具就抓轴心时预览还没建，
                #    直接进 xf_pivot 的话随后 mouseMove 里 `assert _xf_rect`
                #    必炸（用户 2026-10-08 报的 AssertionError 刷屏）——拖动
                #    轴心本身不改矩阵，但预览三件套是拖动状态机的前提。
                self._ensure_transform_preview()
                if self._float_item is None:
                    event.accept()
                    return
                inv, _ = self._xf.inverted()
                self._mode = ("xf_pivot", inv)
            else:
                self._ensure_transform_preview()
                if self._float_item is None:
                    event.accept()
                    return
                if hit in ("tl", "tr", "bl", "br"):
                    # ⚠️ _ensure_transform_preview 成功 ⇒ _xf_rect 必已建立
                    #    （它就是在那儿建的），这里显式收窄给类型检查器看。
                    assert self._xf_rect is not None
                    rect = self._xf_rect.normalized()
                    opposite = {"tl": rect.bottomRight(),
                                "tr": rect.bottomLeft(),
                                "bl": rect.topRight(),
                                "br": rect.topLeft()}[hit]
                    anchor = (self._xf_pivot if self._xf_about_pivot
                              else QPointF(opposite))
                    inv, _ = self._xf.inverted()
                    self._mode = (
                        "xf_scale", self._xf, inv.map(pos), QPointF(anchor))
                elif hit in ("t", "b", "l", "r"):
                    self._mode = ("xf_shear", self._xf, pos, hit)
                else:  # 框内 = 移动
                    self._mode = ("xf_move", self._xf, pos)
            event.accept()
            return
        if self._tool == "erase":
            self.stroke_started.emit()
            self._erase_at(pos, pos)
            self._move_eraser_ring(pos)
            self._mode = ("draw", pos)
            event.accept()
            return
        if self._tool == "text":
            hit = self._scene.itemAt(pos, QTransform())
            if isinstance(hit, TextBlockItem):
                # 点在已有文字块上：交给场景路由（放光标/选字/按住拖动）——
                # 每次点击都新建块的话，旧块就永远进不了编辑态（用户报
                # 「文字不能编辑」，2026-10-01）
                super().mousePressEvent(event)
                return
            clamped = QPointF(
                max(inside.left(), min(pos.x(), inside.right())),
                max(inside.top(), min(pos.y(), inside.bottom())),
            )
            self.text_requested.emit(clamped)
            event.accept()
            return
        super().mousePressEvent(event)


    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode is None:
            if self._scene.mouseGrabberItem() is not None:
                # 文字块拖拽中（按下时已把事件送进场景、块抓住了鼠标）：
                # move 必须继续转发给场景——在这里当悬停消费掉的话，块
                # 永远收不到 move，"按住拖动"就是死的（用户报「鼠标放在
                # 文字上面可以移动」，2026-10-01）
                super().mouseMoveEvent(event)
                event.accept()
                return
            # 未拖拽：橡皮擦圈/文字边界框跟随鼠标 + 悬停反馈（需要 mouseTracking）
            if self._tool == "erase" and self._item is not None:
                self._move_eraser_ring(
                    self.mapToScene(event.position().toPoint()))
            elif self._tool == "text" and self._item is not None:
                block = self._text_block_at(
                    self.mapToScene(event.position().toPoint()))
                if block is not None:
                    self._move_text_outline(block)
                else:
                    self._hide_text_outline()
            self._update_hover_cursor(event.position())
            event.accept()
            return
        kind = self._mode[0]
        if kind == "pan":
            delta = event.position() - self._mode[1]
            self._mode = ("pan", event.position())
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        pos = self.mapToScene(event.position().toPoint())
        inside = self.image_rect()
        if kind == "xf_move":
            _, x_start, start = self._mode
            delta = pos - start
            self._xf = x_start * QTransform().translate(delta.x(), delta.y())
            self._xf_touched = True
        elif kind == "xf_rotate":
            _, x_start, center, angle0 = self._mode
            angle = math.degrees(math.atan2(
                pos.y() - center.y(), pos.x() - center.x()))
            delta = (angle - angle0 + 180.0) % 360.0 - 180.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                delta = round(delta / ROTATE_SNAP_DEG) * ROTATE_SNAP_DEG
            # 旋转发生在累计矩阵之后（轴心是视觉位置）：(T * R) 先 T 后 R
            self._xf = x_start * rotate_about(center, delta)
            self._xf_touched = True
        elif kind == "xf_scale":
            _, x_start, p0_local, anchor = self._mode
            inv, _ = x_start.inverted()
            cur = inv.map(pos)
            sx = ((cur.x() - anchor.x()) / (p0_local.x() - anchor.x())
                  if abs(p0_local.x() - anchor.x()) > 1e-6 else 1.0)
            sy = ((cur.y() - anchor.y()) / (p0_local.y() - anchor.y())
                  if abs(p0_local.y() - anchor.y()) > 1e-6 else 1.0)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                sx = sy = (sx + sy) / 2.0  # 等比
            self._xf = scale_about(anchor, sx, sy) * x_start
            self._xf_touched = True
        elif kind == "xf_shear":
            _, x_start, start, edge = self._mode
            inv, _ = x_start.inverted()
            delta = inv.map(pos) - inv.map(start)
            # xf_shear 只在变换预览（_ensure_transform_preview）建立后才会进入，
            # 这里显式收窄给类型检查器看；运行时是纯空操作。
            assert self._xf_rect is not None
            rect = self._xf_rect.normalized()
            if edge in ("l", "r"):
                k = delta.y() / rect.width()
            else:
                k = delta.x() / rect.height()
            self._apply_shear(edge, k, x_start)
            self._xf_touched = True
        elif kind == "xf_pivot":
            inv = self._mode[1]
            # 同上：变换预览建立后 _xf_rect 才有值（运行时纯空操作）。
            assert self._xf_rect is not None
            self._xf_pivot = clamp_rect(
                QRectF(inv.map(pos), QSizeF(0, 0)),
                self._xf_rect.normalized()).topLeft()
        elif kind == "move":
            start, origin = self._mode[1], self._mode[2]
            delta = pos - start
            # move 模式只在选区已建立时才可能被 mousePressEvent 置上
            # （运行时纯空操作）。
            assert self._rect is not None
            moved = self._rect.normalized().translated(delta)
            moved.moveTopLeft(clamp_rect(moved, inside).topLeft())
            self._rect = moved
        elif kind == "handle":
            assert self._rect is not None  # 拖手柄时必有选区
            self._resize_rect(self._mode[1], pos)
        elif kind == "draw":
            self._erase_at(self._mode[1], pos)
            self._move_eraser_ring(pos)
            self._mode = ("draw", pos)
        self._sync_float()
        self._sync_overlay()
        event.accept()


    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode and self._mode[0] == "pan":
            self._mode = None
            self._sync_cursor()
            event.accept()
            return
        if self._mode and self._mode[0] in ("move", "handle"):
            # move/handle 只在裁剪与变换「调整范围」下出现；两者松手都
            # 把视图适配到新选区（变小就放大，修褶皱要对准那一小块）
            was_reshape = self._tool == "transform" and self._xf_reshape
            self._mode = None
            if was_reshape:
                self._xf_reshape = False
                # 轴心跟随新区域中心：后续旋转/缩放绕"褶皱那块"的中心
                assert self._rect is not None  # move/handle 模式下恒有选区
                self._xf_pivot = self._rect.normalized().center()
                self.reshape_finished.emit()  # 弹窗取消勾选，回到变换
            self._sync_overlay()
            self.fit_selection()
            event.accept()
            return
        if self._mode and self._mode[0] == "draw":
            self._mode = None
            event.accept()
            return
        if self._mode and self._mode[0].startswith("xf_"):
            self._mode = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


    def _resize_rect(self, handle: str, pos: QPointF) -> None:
        """拖手柄改选区（对边/对角锚定不动），夹进画布、保住最小边。"""
        assert self._rect is not None  # 拖手柄时必有选区
        rect = QRectF(self._rect.normalized())
        inside = self.image_rect()
        if "l" in handle:
            rect.setLeft(max(
                inside.left(), min(pos.x(), rect.right() - MIN_RECT_EDGE)))
        if "r" in handle:
            rect.setRight(min(
                inside.right(), max(pos.x(), rect.left() + MIN_RECT_EDGE)))
        if "t" in handle:
            rect.setTop(max(
                inside.top(), min(pos.y(), rect.bottom() - MIN_RECT_EDGE)))
        if "b" in handle:
            rect.setBottom(min(
                inside.bottom(), max(pos.y(), rect.top() + MIN_RECT_EDGE)))
        self._rect = rect


    def _erase_at(self, start: QPointF, end: QPointF) -> None:
        """橡皮擦在图上就地擦一段（涂白；古籍页面去污点=涂白），刷新显示。"""
        if self._image is None:
            return
        painter = QPainter(self._image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor("#ffffff"), float(self._erase_size))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if start == end:
            painter.drawPoint(start)
        else:
            painter.drawLine(start, end)
        painter.end()
        self.refresh()


    def leaveEvent(self, event) -> None:  # noqa: N802
        # 鼠标离开画布：高亮熄灭、橡皮擦圈/文字边界框隐藏、光标回默认
        self._hover_handle = None
        self._hide_eraser_ring()
        self._hide_text_outline()
        self._apply_hover_highlight()
        self._sync_cursor()
        super().leaveEvent(event)


    def keyPressEvent(self, event) -> None:  # noqa: N802
        # 就地编辑文字时按键（含 ←/→ 移光标）全部给文本编辑，不走翻页
        if isinstance(self._scene.focusItem(), TextBlockItem):
            super().keyPressEvent(event)
            return
        # ←/→ 别拿去滚动画布，交还弹窗（与预览弹窗一致：方向键是翻页）
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)
