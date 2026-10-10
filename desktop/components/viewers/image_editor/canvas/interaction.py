# -*- coding: utf-8 -*-
"""画布 Mixin：**鼠标/键盘交互**（缩放平移、工具分流、命中与光标）。

从 ``EditorCanvas`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QTransform

from ..consts import (
    CORNER_HANDLES, EDGE_BAND_VIEW_PX, HOVER_CURSORS, MIN_RECT_EDGE,
    PERSP_HANDLES, SHEAR_HANDLES, SIDE_HANDLES, WHEEL_STEP,
)
from ..geometry import clamp_rect
from ..text_item import TextBlockItem
from .overlay import _style_node
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object


#: 统一变换里算"节点"的命中名（悬停/点选都要高亮它们；边带与框内不算）
_HANDLE_HITS = frozenset(
    CORNER_HANDLES + SIDE_HANDLES + SHEAR_HANDLES + PERSP_HANDLES)


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
        # 手柄底色：同统一变换那套——**默认中空，当前那个实心**（用户 2026-10-09
        # 「操作节点未选中不要有背景色」）。⚠️ 那 8 个方框是**同一批图元**，变换
        # （非收边）时由 ``transform._sync_transform_overlay`` 按 ``_focus_handle``
        # 上色，两条路各自负责自己那种工具，不会互相覆盖。
        for name, item in self._handles.items():
            _style_node(item, name == self._hover_handle)


    def _update_hover_cursor(self, view_pos: QPointF) -> None:
        """未拖拽时的悬停反馈：命中手柄给语义光标 + 该手柄高亮（边线随动）。

        ⚠️ 统一变换下悬停**不写** ``_hover_handle``（那是裁剪/收边的整边线
        高亮用的）：变换的工具是"**节点**"，高亮由 ``_focus_handle`` 管，
        见 :meth:`_set_handle_focus`。这样"点节点 → 节点亮"与"悬停边线亮"
        两套反馈不会互相覆盖。
        """
        if self._tool == "transform" and not self._xf_reshape \
                and self._item is not None:
            hit = self._hit_transform(view_pos)
            self._set_handle_focus(hit if hit in _HANDLE_HITS else None)
            if hit in HOVER_CURSORS:
                cursor = HOVER_CURSORS[hit]  # 角/边/菱形：语义光标
            elif hit in ("pivot", "inside"):
                cursor = Qt.CursorShape.SizeAllCursor
            elif hit == "outside":
                cursor = Qt.CursorShape.CrossCursor  # 框外拖 = 旋转
            else:
                cursor = Qt.CursorShape.ArrowCursor
            self.viewport().setCursor(cursor)
            return
        self._set_handle_focus(None)
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
        if self._tool in ("erase", "distort"):
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
        位置都能抓着拖（用户 20:18 定："四边大部分区域都可以移动裁剪线"）。
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
            # 裁剪不做"拖拽画框"（那是截图的交互）：默认全选，只能拖边/移动。
            # 拖边**双向**都行 —— 画布在待定期间一直是原图，往外拖回去就是
            # 把刚才变暗的区域重新放出来（见 dialog_commit._preview_crop）。
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
            # ⚠️ 拖拽状态机在 TransformMixin（手柄语义与变换应用是同一件事），
            #    这里只负责"按下了、按在哪儿、按着什么修饰键"。
            self._mode = self._begin_transform_drag(
                hit, pos, event.modifiers())
            event.accept()
            return
        if self._tool == "distort":
            self._begin_distortion_stroke(pos)
            if self._distort_stroke_origin is not None:
                self._mode = ("distort", pos)
                self._move_eraser_ring(pos)
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
            if self._tool in ("erase", "distort") and self._item is not None:
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
        if kind.startswith("xf_"):
            # 统一变换的七种拖拽（移动/旋转/双轴缩放/单轴缩放/切变/透视/轴心）
            # 全在 TransformMixin 里，这里只转发位置与修饰键
            self._apply_transform_drag(self._mode, pos, event.modifiers())
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
        elif kind == "distort":
            self._distort_segment(self._mode[1], pos)
            self._move_eraser_ring(pos)
            self._mode = ("distort", pos)
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
            # move/handle 只在裁剪与变换「调整范围」下出现
            was_reshape = self._tool == "transform" and self._xf_reshape
            was_crop = self._tool == "crop"
            self._mode = None
            if was_reshape:
                self._xf_reshape = False
                # 轴心跟随新区域中心：后续旋转/缩放绕"褶皱那块"的中心
                assert self._rect is not None  # move/handle 模式下恒有选区
                self._xf_pivot = self._rect.normalized().center()
                self.reshape_finished.emit()  # 弹窗取消勾选，回到变换
                self._sync_overlay()
                self.fit_selection()
            elif was_crop:
                # ⚠️ 裁剪是**非破坏性**的：松手只把选区告诉弹窗记下来，**不动
                #    像素**。画布上画的始终是原图，选区外的遮罩（4 块半透明黑）
                #    每帧按选区重算 ⇒ 向外拖时被变暗的那块立刻重新露出来，
                #    裁剪线在整段编辑里都能来回推。真正的 ``QImage.copy`` 在
                #    切走裁剪工具 / 点「完成」时才做（``_commit_crop``）。
                #    选区没被改动过（点一下/拖回原位）时弹窗侧会自己清掉待定
                #    裁剪，不产生空撤销步。
                self._sync_overlay()
                if self.selection() is not None:
                    self.crop_selection_changed.emit()
            else:
                self._sync_overlay()
                self.fit_selection()
            event.accept()
            return
        if self._mode and self._mode[0] == "draw":
            self._mode = None
            event.accept()
            return
        if self._mode and self._mode[0] == "distort":
            end = self.mapToScene(event.position().toPoint())
            self._distort_segment(self._mode[1], end)
            self._finish_distortion_stroke()
            self._mode = None
            event.accept()
            return
        if self._mode and self._mode[0].startswith("xf_"):
            # ⚠️⚠️ **松手不烘焙**（用户 2026-10-09 报障："仍然不能实时预览，
            #    而是最后才预览"）。原来的"松手即应用"= 每次松手都把整幅重采样
            #    一遍（12 MP 要 11 秒），所以只能"最后才看到结果"。
            #    现在改成 GIMP 口径：**松手保持预览**，继续拖/滚轮继续改
            #    （都是便宜的画布变换），离开工具/点「完成」时才真正烘焙一次。
            kind = self._mode[0]
            self._mode = None
            # 先把预览升回精确档（拖动中像素不重采样、变换由图元做，
            # 松手这一帧才按烘焙那套数学重算一次）
            self.finish_transform_drag()
            if kind != "xf_pivot" and self.transform_pending() is not None:
                self.make_transform_pending()
            event.accept()
            return
        super().mouseReleaseEvent(event)


    def _resize_rect(self, handle: str, pos: QPointF) -> None:
        """拖手柄改选区（对边/对角锚定不动），夹进画布、保住最小边。

        ⚠️ 夹取上界是 ``image_rect()``＝**当前原图**。因为裁剪是非破坏性的
        （松手不换图），这块画布在整个裁剪工具会话里一直是原图，所以往外拖
        能一路拉回原图的边界、被遮住的老区域同步重新显出来。
        """
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
