# -*- coding: utf-8 -*-
"""页清单的**拖动排序**：幽灵卡 + 落点指示线 + 落位动画（``_DragMixin``）。

Mixin 只在运行期与 ``ImpositionPageList`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``list_widget``，避免循环导入。
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from desktop.components.imposition.page_list._qt import (
    QAbstractAnimation,
    QApplication,
    QCursor,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
)
from desktop.components.imposition.page_list.entries import _PageEntry
from desktop.ui import theme as T

if TYPE_CHECKING:
    from desktop.components.imposition.page_list._host import PageListHost as _Host
else:
    _Host = object


class _DragMixin(_Host):
    """按住条目上下拖动的排序交互。"""

    # ------------------------------------------------------------- 拖动排序
    def _on_drag_started(self, index: int) -> None:
        """某页被按住拖动了：**本体留在原位**（置灰），一张等大的「幽灵卡」
        跟着光标走，细线指示落点——清单全程不留空档（用户 2026-09-30
        三稿：占位块空档太大、原位置空着不像话）。
        """
        if self._committing or not (0 <= index < len(self._entries)):
            return
        entry = self._entries[index]
        self._drag_from = index
        self._drag_drop = index
        self._drag_entry = entry
        self._flow = [e for e in self._entries if e is not entry]
        entry.set_dimmed(True)
        container = self.list_scroll.widget()
        if container is None:  # 滚动区没内容 ⇒ 没有可拖的列表，收手
            return
        self._ghost = _PageEntry(index, entry.caption, container)
        self._ghost.set_drag_active(True)
        self._ghost.setGeometry(entry.geometry())
        self._ghost.raise_()
        self._ghost.show()
        self._drag_x = entry.x()
        self._grab_dy = container.mapFromGlobal(QCursor.pos()).y() - entry.y()
        self._drag_timer.start()
        self._poll_drag()

    def _poll_drag(self) -> None:
        """拖动中：幽灵卡贴着光标走；光标越过哪页中线，落点细线就移到那里。"""
        if QApplication.mouseButtons() != Qt.MouseButton.LeftButton:
            self._finish_drag()
            return
        if self._ghost is None:
            return
        container = self.list_scroll.widget()
        # ⚠️ list_scroll.widget() 的注解是 QWidget | None：理论上滚动区没装
        #     内容时会是 None（那就没列表可拖，直接收手）。
        if container is None:
            return
        pos = container.mapFromGlobal(QCursor.pos())
        y = max(0, min(pos.y() - self._grab_dy,
                       container.height() - self._ghost.height()))
        self._ghost.move(self._drag_x, y)
        self._auto_scroll()
        drop = len(self._flow)
        for i, entry in enumerate(self._flow):
            if pos.y() < entry.geometry().center().y():
                drop = i
                break
        if drop != self._drag_drop:
            self._drag_drop = drop
            self._place_indicator()

    def _place_indicator(self) -> None:
        """落点指示线：画在落点条目的上缘（末尾则最后条目下缘）；拖回
        原位（``drop == _drag_from``）藏线——表示松手不会换位。"""
        drop = self._drag_drop
        if self._ghost is None or not self._flow or drop == self._drag_from:
            self._indicator.hide()
            return
        if drop < len(self._flow):
            anchor = self._flow[drop].geometry()
            y = anchor.top() - (T.SPACE_SM + self._INDICATOR_H) // 2
        else:
            anchor = self._flow[-1].geometry()
            y = anchor.bottom() + (T.SPACE_SM - self._INDICATOR_H) // 2
        self._indicator.setGeometry(
            anchor.x(), max(0, y), anchor.width(), self._INDICATOR_H
        )
        self._indicator.show()
        self._indicator.raise_()

    def _register_anim(self, anim: QPropertyAnimation) -> None:
        """登记动画；它结束时自己从 ``_anims`` 摘除（finished 信号在
        C++ 对象销毁前发出，之后 deleteLater，避免留悬挂引用）。"""
        self._anims.append(anim)
        # ⚠️ 动画的 finished 在主线程发出，直连安全；但护栏静态扫描按信号名
        # 拦「worker 信号直连 lambda」，这里用 partial + 绑定方法保持同款写法
        anim.finished.connect(partial(self._forget_anim, anim))
        anim.finished.connect(anim.deleteLater)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _forget_anim(self, anim: QPropertyAnimation) -> None:
        if anim in self._anims:
            self._anims.remove(anim)

    def _auto_scroll(self) -> None:
        """光标贴近滚动区上/下边缘时慢慢滚，长清单拖远程不用分两把。"""
        bar = self.list_scroll.verticalScrollBar()
        vp = self.list_scroll.viewport().mapFromGlobal(QCursor.pos())
        if vp.y() < self._EDGE_PX:
            bar.setValue(bar.value() - self._EDGE_STEP)
        elif vp.y() > self.list_scroll.viewport().height() - self._EDGE_PX:
            bar.setValue(bar.value() + self._EDGE_STEP)

    def _slot_y(self, drop: int) -> int:
        """落点 ``drop`` 处的槽位纵坐标（清单从未被撑开，直接读邻条目）。"""
        if 0 <= drop < len(self._flow):
            return self._flow[drop].y()
        if self._flow:
            last = self._flow[-1]
            return last.y() + last.height() + T.SPACE_SM
        return 0

    def _finish_drag(self) -> None:
        """松手：幽灵卡滑进落点槽位**这才真正换位**，动画走完通知控制器。

        拖回原位（``drop == _drag_from``）不发信号，幽灵卡就地消散。
        ``_drag_entry`` 为 None 时（护栏合成驱动，只设 ``_drag_from``/
        ``_drag_drop``）走旧口径直接发信号，不做动画。
        """
        if self._committing:
            return
        entry = self._drag_entry
        if entry is None:
            source, drop = self._drag_from, self._drag_drop
            self._cancel_drag()
            if not (0 <= source < len(self._entries)):
                return
            target = drop - 1 if drop > source else drop
            if not (0 <= target <= len(self._entries)) or target == source:
                return
            self.reorder_requested.emit(source, target)
            return
        source, drop = self._drag_from, self._drag_drop
        self._drag_timer.stop()
        entry.set_dimmed(False)
        self._drag_entry = None
        self._drag_from = -1
        self._drag_drop = -1
        self._indicator.hide()
        ghost, self._ghost = self._ghost, None
        if ghost is None:
            self._flow = []
            return
        if drop == source:
            # 放回原位：幽灵卡就地消散，清单本来就一动没动
            self._flow = []
            ghost.deleteLater()
            return
        # 落位动画结束后才发信号：控制器据此 pop(source)/insert(drop) 落盘
        # （finished 在主线程发出；partial 写法见 _register_anim 的说明）
        target = drop
        self._committing = True
        anim = QPropertyAnimation(ghost, b"pos", self)
        anim.setDuration(self._ANIM_MS)
        anim.setStartValue(ghost.pos())
        anim.setEndValue(QPoint(self._drag_x, self._slot_y(drop)))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(
            partial(self._emit_reorder, source, target, ghost))
        self._register_anim(anim)

    def _emit_reorder(self, source: int, target: int, ghost) -> None:
        """落位动画走完：幽灵卡消散、通知控制器落盘（``_committing`` 解除）。"""
        self._committing = False
        self._flow = []
        if ghost is not None:
            ghost.deleteLater()
        self.reorder_requested.emit(source, target)

    def _cancel_drag(self) -> None:
        self._drag_timer.stop()
        self._drag_from = -1
        self._drag_drop = -1
        self._committing = False
        if self._drag_entry is not None:
            self._drag_entry.set_dimmed(False)
            self._drag_entry = None
        if self._ghost is not None:
            self._ghost.deleteLater()
            self._ghost = None
        self._indicator.hide()
        self._flow = []
        # 动画一并停掉：set_pages 重建清单前会走到这里，
        # 别让 QPropertyAnimation 追着 deleteLater 的控件跑
        for anim in list(self._anims):
            anim.stop()
        self._anims = []
