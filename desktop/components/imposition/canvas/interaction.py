# -*- coding: utf-8 -*-
"""拼版画布的**鼠标 / 右键菜单 / 滚轮缩放**（``_InteractionMixin``）。

Mixin 只在运行期与 ``ImpositionCanvas`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``widget``，避免循环导入。
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from qfluentwidgets import Action, RoundMenu
from qfluentwidgets import FluentIcon as FIF

from desktop.components.imposition.canvas._qt import QPointF, Qt
from desktop.components.imposition.canvas.constants import (
    _EDGE_BY_HANDLE,
    _HANDLE_CURSORS,
    MIN_RECT,
    SNAP_DEGREES,
    WHEEL_ZOOM_STEP,
    ZOOM_MAX,
    ZOOM_MIN,
)

if TYPE_CHECKING:
    from desktop.components.imposition.canvas._host import CanvasHost as _Host
else:
    _Host = object


class _InteractionMixin(_Host):
    """鼠标按下/拖动/松手、右键菜单与滚轮缩放。"""

    # ------------------------------------------------------------------ 鼠标
    def invalidate_image(self, path: str) -> None:
        """某个源图文件被外部覆盖（编辑器「完成」回写）后：丢掉它的解码
        缓存并重绘——不丢的话画布会一直显示覆盖前的旧图。

        ⚠️⚠️ 命中判据必须**规范化**（``normpath`` + ``normcase``），不能拿
        字符串直接比：缓存键是 ``item["file"]`` 原样存进来的，而调用方给的
        路径可能来自 ``Path(...)``（Windows 上斜杠会被翻成 ``\\``）、
        ``QFileDialog``（给的是 ``/``）或带大小写差异——只要有一处形态不同，
        ``pop`` 就落空、画布**静默地继续显示旧图**（用户 2026-10-08 报：
        从预览弹窗里编辑完，关掉弹窗拼版页还是老图）。这里把"同一路径的
        各种写法"一并清掉，调用方传哪种形态都能命中。
        """
        text = str(path)
        self._images.pop(text, None)
        want = os.path.normcase(os.path.normpath(text))
        stale = [
            key for key in self._images
            if os.path.normcase(os.path.normpath(key)) == want
        ]
        for key in stale:
            self._images.pop(key, None)
        # 贴图底图缓存同源作废（键是 (路径, 档位)，按同一套路径归一判据清）
        for key in [
            cache_key for cache_key in self._display_cache
            if os.path.normcase(os.path.normpath(cache_key[0])) == want
        ]:
            self._display_cache.pop(key, None)
        self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键菜单：**预览图片 / 编辑图片**。

        「预览图片」仍按命中对象预览单张或整页组合；「编辑图片」统一编辑
        整页组合，不再提供单张源图编辑。右键图片时仍先选中该图。
        空画布没有菜单（没有可预览/可编辑的东西）。
        """
        if not self._items:
            return super().contextMenuEvent(event)
        index = self._item_at(QPointF(event.pos()))
        if index >= 0 and index != self._selected:
            self._selected = index
            self.selection_changed.emit(self._selected)
            self.update()
        menu = RoundMenu(parent=self)
        for text, icon, slot in (
            ("预览图片", FIF.PHOTO, lambda: self._emit_context(index, False)),
            ("编辑图片", FIF.EDIT,
             lambda: self._emit_context(index, True)),
        ):
            action = Action(icon, text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        # 「定位图片资源」（2026-10-11 用户）：只在**图上**给——右键的那张
        # 子图有真实源文件可定位；空白处的整页组合是虚拟图（合成物），没有
        # 对应的"那一个文件"，不给死按钮。
        if index >= 0:
            action = Action(FIF.FOLDER, "定位图片资源", menu)
            action.triggered.connect(
                lambda: self._locate_item_file(index)
            )
            menu.addAction(action)
        menu.exec(event.globalPos())
        event.accept()

    def set_locate_resolver(self, resolver: Callable[[int], list] | None) -> None:
        """宿主给出「定位图片资源」要定位的目标（``(index) -> list[Path]``，按优先级）。

        ⚠️ **拼版这一步必须给**（用户 2026-10-18）：画布上那张图是**输入源图**
        （如 ``stages/input``），而拼版的"图片资源"是**实时重合成出来的成品**
        （``stages/imposition[~<节点>]``）。不设时退回旧口径——定位画布上那张
        源图文件（其余步骤/独立页没有"实时产物"的说法，行为不变）。
        """
        self._locate_resolver = resolver

    def _locate_item_file(self, index: int) -> None:
        """右键「定位图片资源」：资源管理器定位第 ``index`` 张子图**对应的资源**。

        ⚠️ 目标由 :meth:`set_locate_resolver` 给出（拼版 → 成品页/成品目录；
        不设 → 这张源图文件）。**按优先级逐个试**：拼版成品可能还没合成出来，
        那时退到成品目录，至少让用户到"这一批产物的跟前"。

        ⚠️ 定位的**就是被右键的那一张**（``_item_at`` 已按旋转后的矩形命中，
        且选中项优先），不要另算"左右槽"——两图并排时错一格就是"定位错了"。

        ⚠️ 全都定位不成不静默：说清原因（静默什么都不发生，用户只会以为
        定位到了错误的资源——用户 2026-10-17 报障）。
        """
        if not (0 <= index < len(self._items)):
            return
        from desktop.utils.files import reveal_in_explorer

        file_text = str(self._items[index].get("file") or "")
        candidates: list[Path] = []
        if self._locate_resolver is not None:
            try:
                candidates = [
                    Path(p) for p in (self._locate_resolver(index) or []) if p
                ]
            except Exception:  # noqa: BLE001 - 解析坏了也不该把右键卡住
                candidates = []
        # ⚠️ 没给解析器（或它返回空）时才回落到"画布上这张源图"——拼版这一步
        #    给了解析器就不该再退到输入图（用户明确说那不是它的图片资源）。
        if not candidates and file_text:
            candidates.append(Path(file_text))
        for candidate in candidates:
            if reveal_in_explorer(candidate):
                return
        if not candidates:
            self.locate_failed.emit("这张图没有可定位的文件。")
            return
        first = candidates[0]
        parent = first.parent
        if parent.is_dir():
            reveal_in_explorer(parent)
            self.locate_failed.emit(f"资源已不存在，已打开所在目录：{parent}")
        else:
            self.locate_failed.emit(f"找不到文件（所在目录也不存在）：{first}")

    def _emit_context(self, index: int, edit: bool) -> None:
        """右键菜单按命中的图层发出预览或整页编辑请求。"""
        if index >= 0:
            if edit:
                self.item_edit_requested.emit(index)
            else:
                self.item_preview_requested.emit(index)
        else:
            (self.spread_edit_requested if edit
             else self.spread_double_clicked).emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击图片编辑整页组合；双击空白预览整页组合。

        ⚠️ 处理了就 ``accept``：Qt 对未接受的双击会**再补一个 mousePress**，
        那会走进 ``mousePressEvent`` 把编辑手势带起来（用户双击预览、松手时
        画布却以为刚拖动过一下）。
        """
        if event.button() != Qt.MouseButton.LeftButton or not self._items:
            return super().mouseDoubleClickEvent(event)
        index = self._item_at(event.position())
        if index >= 0:
            self.item_edit_requested.emit(index)
        else:
            self.spread_double_clicked.emit()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._items or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        # 按住期间才画框线/手柄（松手即消失，见模块 docstring）
        self._pressed = True
        # 选中项的手柄优先（它可能被另一张图压住）
        if self._selected >= 0:
            handle = self._hit_handle(self._selected, event.position())
            if handle is not None:
                self._begin_edit(handle, event)
                return
        index = self._item_at(event.position())
        if index >= 0:
            if index != self._selected:
                self._selected = index
                self.selection_changed.emit(self._selected)
                self.update()
            self._begin_edit(-1, event)
            return
        # 点在纸上空白处：取消选中
        if self._selected != -1:
            self._selected = -1
            self.selection_changed.emit(-1)
        self.update()
        return super().mousePressEvent(event)

    def _begin_edit(self, handle: int, event) -> None:
        """开始一次编辑手势（handle=-1 表示移动）。"""
        item = self._items[self._selected]
        self._grab_rect = list(item["rect"])
        self._grab_rotation = float(item.get("rotation") or 0.0)
        if handle == 8:
            self._mode = "rotate"
            center = self._rect_px(self._selected).center()
            mx, my = event.position().x(), event.position().y()
            self._grab_angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
        elif handle >= 0:
            self._mode = "resize"
            self._handle = handle
            self._grab_center = self._rect_px(self._selected).center()
        else:
            self._mode = "move"
            mx, my = self._to_units(event.position())
            self._grab_x = mx - item["rect"][0]
            self._grab_y = my - item["rect"][1]
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._dirty = False
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "move":
            item = self._items[self._selected]
            mx, my = self._to_units(event.position())
            item["rect"][0] = mx - self._grab_x
            item["rect"][1] = my - self._grab_y
            self._dirty = True
            self.update()
            return
        if self._mode == "resize":
            self._items[self._selected]["rect"] = self._resize_from_handle(
                event, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            )
            self._dirty = True
            self.update()
            return
        if self._mode == "rotate":
            item = self._items[self._selected]
            center = self._rect_px(self._selected).center()
            mx, my = event.position().x(), event.position().y()
            angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
            item["rotation"] = (self._grab_rotation + angle - self._grab_angle) % 360.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                item["rotation"] = (
                    round(item["rotation"] / SNAP_DEGREES) * SNAP_DEGREES
                ) % 360.0
            self._dirty = True
            self.update()
            return
        # 悬停光标提示
        if self._items:
            index = self._selected if self._selected >= 0 else self._item_at(
                event.position()
            )
            if index >= 0:
                handle = self._hit_handle(index, event.position())
                if handle == 8:
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    return
                if handle is not None:
                    self.setCursor(_HANDLE_CURSORS[handle])
                    return
                if self._item_contains_px(index, event.position()):
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                    return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        return super().mouseMoveEvent(event)

    def _resize_from_handle(self, event, keep_ratio: bool) -> list[float]:
        """按当前手柄算出新框（合成像素）。

        - 四边手柄：只改受影响的那个维度（自由拉伸，能改比例）；
        - 四角手柄：默认自由拉伸；按住 Shift 以**对角为锚点**等比缩放
          （比例取自拖拽起点框，避免逐帧累积偏差）。

        ⚠️ 鼠标先反转该图的旋转角（绕**手势起点**的 rect 中心）再落到
        图坐标——手柄跟着框转了，光标也得换到局部系里读。
        """
        pos = event.position()
        c = self._grab_center
        angle = math.radians(
            float(self._items[self._selected].get("rotation") or 0.0)
        )
        cos_v, sin_v = math.cos(-angle), math.sin(-angle)
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        # 局部控件像素（原点 = 手势起点中心）→ 图坐标（单位 = 源图像素）
        local = QPointF(dx * cos_v - dy * sin_v, dx * sin_v + dy * cos_v)
        gx, gy = self._to_units(c)
        mx = gx + local.x() / self._px_per_unit
        my = gy + local.y() / self._px_per_unit
        gx, gy, gw, gh = self._grab_rect
        edge = _EDGE_BY_HANDLE.get(self._handle)
        if edge is not None:
            x, y, w, h = self._grab_rect
            if edge == "top":
                top = min(my, y + h - MIN_RECT)
                return [x, top, w, y + h - top]
            if edge == "bottom":
                bottom = max(my, y + MIN_RECT)
                return [x, y, w, bottom - y]
            if edge == "left":
                left = min(mx, x + w - MIN_RECT)
                return [left, y, x + w - left, h]
            right = max(mx, x + MIN_RECT)
            return [x, y, right - x, h]
        # ---- 四角 ----
        ax, ay = {
            0: (gx + gw, gy + gh), 1: (gx, gy + gh),
            2: (gx, gy), 3: (gx + gw, gy),
        }[self._handle]
        if not keep_ratio or gw <= 0 or gh <= 0:
            nx1, ny1 = min(ax, mx), min(ay, my)
            nx2, ny2 = max(ax, mx), max(ay, my)
            return [nx1, ny1, max(nx2 - nx1, MIN_RECT),
                    max(ny2 - ny1, MIN_RECT)]
        ratio = gh / gw
        scale = min(
            abs(mx - ax) / gw if gw else 0.0,
            abs(my - ay) / gh if gh else 0.0,
        )
        new_w = max(MIN_RECT, gw * scale)
        new_h = max(MIN_RECT, new_w * ratio)
        nx = ax - new_w if self._handle in (0, 3) else ax
        ny = ay - new_h if self._handle in (0, 1) else ay
        return [nx, ny, new_w, new_h]

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode is not None or self._pressed:
            self._mode = None
            self._pressed = False      # 松手 → 框线/手柄立即消失
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._dirty:
                self._emit_changed()
            else:
                self.update()
            return
        return super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """指针离开画布：按下状态收不到 release 时也别留着框线。"""
        if self._pressed:
            self._pressed = False
            self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ 滚轮缩放
    def wheelEvent(self, event) -> None:  # noqa: N802
        """滚轮缩放视图（以光标为锚点）；**重绘按帧合并**（减渲染的关键）。

        缩放本身只是 ``_zoom_at`` 里几个乘法——不解码、不重排、不碰图缓存。
        真正贵的是重绘：两张几千像素见方的原图 + 平滑采样。高分滚轮/触控板
        一秒能吐上百个 wheel 事件，若每个事件都 ``update()``，重绘就被拉到
        事件率。所以这里**不直接要重绘**：

        - 启动帧窗口定时器（``WHEEL_REPAINT_MS``），窗口内再来滚动只置
          ``_wheel_paint_pending``；
        - 窗口到期画一帧（``_on_wheel_frame``）；窗口内还有滚动就滚到下一帧，
          没有就关掉快速档、补一帧带平滑的高质量重绘收尾。

        连发期间 paintEvent 走**快速档**（不做 ``SmoothPixmapTransform``，
        大图缩放的重头开销在这）——反正下一滚就整帧重画，糊一帧没人看得出。
        """
        delta = event.angleDelta().y()
        if not self._items or delta == 0:
            return super().wheelEvent(event)
        event.accept()
        self._zoom_at(event.position(), WHEEL_ZOOM_STEP ** (delta / 120.0))
        self._wheel_burst = True
        if self._wheel_timer.isActive():
            self._wheel_paint_pending = True
        else:
            self._wheel_timer.start()

    def _zoom_at(self, pos: QPointF, factor: float) -> None:
        """以控件点 ``pos`` 为锚缩放 ``factor`` 倍（只改几何，不重绘）。

        锚点不动 = 光标指着的图上的点缩放前后还在光标底下。倍率钳在
        ``ZOOM_MIN``/``ZOOM_MAX``（相对适配基准），缩到头就不再动。
        """
        if not self._items or factor <= 0.0 or math.isclose(factor, 1.0):
            return
        new_zoom = min(ZOOM_MAX, max(ZOOM_MIN, self._zoom * factor))
        if math.isclose(new_zoom, self._zoom):
            return
        ratio = new_zoom / self._zoom
        self._zoom = new_zoom
        self._px_per_unit = self._fit_ppu * self._zoom
        self._off_x = pos.x() - (pos.x() - self._off_x) * ratio
        self._off_y = pos.y() - (pos.y() - self._off_y) * ratio

    def _on_wheel_frame(self) -> None:
        """帧窗口到期（定时器线程安全，主线程回调）：画一帧 + 收尾判定。"""
        self.update()
        if self._wheel_paint_pending:
            self._wheel_paint_pending = False
            self._wheel_timer.start()  # 窗口内还有滚动：并到下一帧
            return
        # 滚动停稳：关快速档，补一帧带平滑的高质量重绘
        self._wheel_burst = False
        self.update()
