# -*- coding: utf-8 -*-
"""拼版页装配控件：左列拼版页清单（模块一）+ 右区操作画布（模块二）。

本文件是**两个模块的缝合处**，只做组合与转发，不含业务：

- **模块一（选择拼版）**：左列 ``ImpositionPageList`` 与
  ``ImpositionPickerDialog``（``picker.py``）——选哪两张、拼几页；
- **模块二（拼版操作）**：``ImpositionCanvas``（``canvas.py``）——
  拖动 / 缩放拉伸 / 旋转，以及右侧 ``ImpositionPanel``（``panel.py``）。

落盘 / 合成 / 与第四步取图切换由 ``desktop/pages/taskdetail/`` 下的
拼版控制器负责（``imposition.py`` 共享基元 + 模块一/二各自的 Mixin）。
"""

from __future__ import annotations

import html
import math

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import PushButton
from qfluentwidgets import FluentIcon as FIF

from desktop.components.imposition.canvas import (
    CROP_COLOR,
    ImpositionCanvas,
    SPINE_COLOR,
)
from desktop.components.imposition.page_list import ImpositionPageList
from desktop.services.imposition import cn_page_label, page_source_stems
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to


class _EmptyGuideOverlay(QWidget):
    """空态引导层（用户 2026-10-13）：还没有任何拼版页时，画布区一片空白，
    唯一的入口是**左下角**的虚线「＋ 选择拼版」——太不显眼了。

    本层盖在整个拼版视图上，画三样东西：

    1. 画布区居中的**大字提示**：「从左下角「＋ 选择拼版」开始拼版」；
    2. 一支**红色箭头**，从提示文字弯向左下角的按钮；
    3. 按钮**外围的红色线框**（用户点名：选择拼版用红色线框框起来）。

    ⚠️ **全程鼠标穿透**（``WA_TransparentForMouseEvents``）：红框只是"圈"，
    按钮本体必须照常可点；层里没有任何可交互元素。
    ⚠️ 按钮几何**每次绘制现取**（``paintEvent`` 里映射）：窗口缩放/左列
    宽度变化后下一帧自动跟手，不需要维护位置缓存。
    """

    #: 引导红：与「批量删除」/画布红色对齐线同一族的项目危险色
    _RED = QColor(T.DANGER)
    #: 主提示行字号（介于正文 13 与页标题 22 之间的强调档）
    _MAIN_PX = 18

    def __init__(self, view: "ImpositionViewWidget"):
        super().__init__(view)
        self._view = view
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def _button_rect(self) -> QRect:
        """「＋ 选择拼版」在本层坐标系里的几何（现取，不缓存）。

        ⚠️ 用 ``button.mapTo(view, …)``（按钮→视图是合法祖先链），**不能**
        ``self.mapFrom(page_list, …)``——page_list 是本层的**兄弟**不是祖先，
        Qt 会拒绝映射（警告 ``mapFrom(): parent must be in parent hierarchy``）
        并返回错位坐标（红框悬到清单半腰，2026-10-13 用户截图报的正是它）。
        本层 geometry == view.rect()，视图坐标即本层坐标。
        """
        button = self._view.page_list.add_entry
        top_left = button.mapTo(self._view, QPoint(0, 0))
        return QRect(top_left, button.size())

    def paintEvent(self, _event) -> None:  # noqa: N802
        button_rect = self._button_rect()
        if button_rect.width() <= 0:
            return
        # 引导文字画在**右侧画布区**的中央（左列被红框占了，别叠上去）
        list_right = self._view.page_list.geometry().right()
        center_x = list_right + (self.width() - list_right) // 2
        center_y = self.height() // 2 - 30

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ---- 1. 大字提示 + 次行说明（居中两行） ----
        main_font = QFont(self.font())
        main_font.setPixelSize(self._MAIN_PX)
        main_font.setBold(True)
        sub_font = QFont(self.font())
        sub_font.setPixelSize(T.SIZE_CAPTION)
        main_text = "从左下角「＋ 选择拼版」开始拼版"
        sub_text = "点击后从候选图片里勾选（不限张数），每两张图片拼成一页"
        painter.setFont(main_font)
        painter.setPen(QPen(QColor(T.INK)))
        main_width = painter.fontMetrics().horizontalAdvance(main_text)
        painter.drawText(
            center_x - main_width // 2, center_y, main_text
        )
        painter.setFont(sub_font)
        painter.setPen(QPen(QColor(T.INK_FAINT)))
        sub_width = painter.fontMetrics().horizontalAdvance(sub_text)
        painter.drawText(
            center_x - sub_width // 2, center_y + T.SIZE_BODY + 10, sub_text
        )

        # ---- 2. 红色箭头：从提示文字下缘弯向按钮右上角 ----
        start = QPoint(center_x - main_width // 2 + 20, center_y + 26)
        end = QPoint(
            min(button_rect.right() + 30, center_x - 40),
            button_rect.top() - 14,
        )
        path = QPainterPath(start)
        # 控制点把曲线往左下压：先垂后横的"拐杖"弧，避免直线斜穿清单
        control = QPoint(start.x() - (start.x() - end.x()) // 3, end.y())
        path.quadTo(control, end)
        # ⚠️ **虚线**（2026-10-13 用户：引导线不要实线）；箭头三角仍是实心，
        #    否则小尺寸下虚线三角根本看不出形状
        painter.setPen(QPen(self._RED, 2.2, Qt.PenStyle.DashLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        # 箭头三角：按曲线末端切线方向摆
        tangent = end - control
        angle = math.atan2(tangent.y(), tangent.x())
        head, size = end, 11
        painter.setBrush(self._RED)
        painter.setPen(Qt.PenStyle.NoPen)
        arrow = QPainterPath(head)
        arrow.lineTo(
            head.x() - size * math.cos(angle - 0.42),
            head.y() - size * math.sin(angle - 0.42),
        )
        arrow.lineTo(
            head.x() - size * math.cos(angle + 0.42),
            head.y() - size * math.sin(angle + 0.42),
        )
        arrow.closeSubpath()
        painter.drawPath(arrow)

        # ---- 3. 按钮外围的红色线框（圈大 5px，虚线本体看得清红框） ----
        frame = button_rect.adjusted(-5, -5, 5, 5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._RED, 2.0, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(frame, T.RADIUS_MD, T.RADIUS_MD)
        painter.end()


class ImpositionViewWidget(QWidget):
    """拼版页面：左列拼版页清单 + 右区操作画布。"""

    #: 左列点了某一页（-1 = 没有页）
    page_selected = Signal(int)
    #: 左列点了虚线「＋ 选择拼版」
    add_requested = Signal()
    #: 左列拖动排序松手：``from`` 移到 ``target``（移除后口径）
    page_reorder_requested = Signal(int, int)
    #: 左列某页的「✕」：释放该页图片回未选择列表
    page_remove_requested = Signal(int)
    #: 左列悬浮框「批量删除」（勾选页后浮出）
    pages_batch_delete_requested = Signal()
    #: 当前页版面被拖动/缩放/旋转（合成像素坐标）
    items_changed = Signal(int, list)
    #: 画布内选中了某张图（0 右槽 / 1 左槽 / -1）
    slot_selected = Signal(int)
    #: 画布内右键预览了某张图（0 右槽 / 1 左槽）
    item_preview_requested = Signal(int)
    #: 画布内双击了图片之外的空白处：请求预览整页左右组合
    spread_preview_requested = Signal()
    #: 画布双击图片或右键菜单「编辑图片」（0 右槽 / 1 左槽）：编辑整页组合
    item_edit_requested = Signal(int)
    #: 画布右键菜单在空白处选了「编辑图片」：编辑整页组合
    spread_edit_requested = Signal()
    #: 「定位图片资源」没定位成（文件已不存在等）：一行人读说明
    locate_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[dict] = []
        self._current = -1

        row = QHBoxLayout(self)
        row.setContentsMargins(T.SPACE_SM, T.SPACE_SM, T.SPACE_SM, T.SPACE_SM)
        row.setSpacing(T.SPACE_MD)

        # ---- 模块一：左列拼版页清单 ----
        self.page_list = ImpositionPageList()
        # 悬浮批量框的宿主换成整个视图：它要浮出页码栏、悬在右侧画布上
        # （页码栏自身 150px 宽，挂在自己底下会被裁剪）
        self.page_list.set_float_host(self)
        self.page_list.page_selected.connect(self._on_page_selected)
        self.page_list.add_requested.connect(self.add_requested)
        self.page_list.reorder_requested.connect(self.page_reorder_requested)
        self.page_list.remove_requested.connect(self.page_remove_requested)
        self.page_list.batch_delete_requested.connect(self.pages_batch_delete_requested)
        row.addWidget(self.page_list)

        # ---- 模块二：操作画布（底部一行：左侧提示语 + 右侧翻页按钮）----
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(T.SPACE_SM)
        self.canvas = ImpositionCanvas()
        self.canvas.items_changed.connect(self._on_items_changed)
        self.canvas.selection_changed.connect(self.slot_selected)
        self.canvas.item_preview_requested.connect(self.item_preview_requested)
        # 双击图片和右键图上编辑都进入整页编辑。
        self.canvas.spread_double_clicked.connect(self.spread_preview_requested)
        # 右键「编辑图片」不经预览弹窗，编辑入口归控制器管
        self.canvas.item_edit_requested.connect(self.item_edit_requested)
        self.canvas.spread_edit_requested.connect(self.spread_edit_requested)
        self.canvas.locate_failed.connect(self.locate_failed)
        right.addWidget(self.canvas, 1)
        bottom = QHBoxLayout()
        bottom.setSpacing(T.SPACE_SM)
        # 底部提示条分两级（用户 2026-09-30：一长串浅灰小字主次不清）：
        # - 主行（hint_main）：第几页 + 左右两张图各是哪张 —— 正文色、稍大，
        #   图名用画布对齐线同款红色加粗标注（一眼看出这页是哪两张图）；
        # - 次行（hint）：操作说明 —— 辅助色小字；「红色虚线」「灰色虚线框」
        #   两个词按画布里 SPINE_COLOR / CROP_COLOR 的真实颜色着色，
        #   文字与画布标注颜色一一对应，不再靠脑补。
        self.hint_main = QLabel("", self)
        self.hint_main.setWordWrap(True)
        self.hint_main.setTextFormat(Qt.TextFormat.RichText)
        apply_to(self.hint_main, T.SIZE_BODY, color=T.INK)
        self.hint = QLabel("", self)
        self.hint.setWordWrap(True)
        self.hint.setTextFormat(Qt.TextFormat.RichText)
        apply_to(self.hint, T.SIZE_CAPTION, color=T.INK_FAINT)
        hints = QVBoxLayout()
        hints.setContentsMargins(0, 0, 0, 0)
        hints.setSpacing(2)
        hints.addWidget(self.hint_main)
        hints.addWidget(self.hint)
        bottom.addLayout(hints, 1)
        # 翻页（用户 2026-09-30：页码切换不放右侧面板，放中间编辑区底部右侧；
        # 页序调整在左列拖动，这里只负责「看哪一页」）
        self.prev_button = PushButton(FIF.PAGE_LEFT, "上一页")
        self.prev_button.setToolTip("切到上一页拼版")
        self.prev_button.clicked.connect(lambda: self._step_page(-1))
        bottom.addWidget(self.prev_button)
        self.next_button = PushButton(FIF.PAGE_RIGHT, "下一页")
        self.next_button.setToolTip("切到下一页拼版")
        self.next_button.clicked.connect(lambda: self._step_page(1))
        bottom.addWidget(self.next_button)
        right.addLayout(bottom)
        row.addLayout(right, 1)

        # ---- 空态引导层（用户 2026-10-13）：还没有拼版页时，提示去点
        #      左下角「＋ 选择拼版」（红框圈住按钮 + 箭头指向它）。鼠标
        #      全程穿透，按钮本体照常可点；显隐只由 _update_hint 驱动。
        self.empty_guide = _EmptyGuideOverlay(self)
        self.empty_guide.setGeometry(self.rect())

        self._update_hint()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # 引导层跟着视图拉伸（红框/箭头几何 paintEvent 现取，无需额外处理）
        self.empty_guide.setGeometry(self.rect())

    # ------------------------------------------------------------------ 数据
    def set_pages(self, pages: list[dict], current: int = -1) -> None:
        """整批灌入拼版页；``current`` 是当前显示的下标。"""
        self._pages = list(pages or [])
        self.page_list.set_pages(
            [" · ".join(page_source_stems(page)) for page in self._pages],
            current=min(current, len(self._pages) - 1),
        )
        self.set_current(min(current, len(self._pages) - 1))

    def set_page_thumbs(self, thumbs: list) -> None:
        """把左列每页的缩略图贴上去（``thumbs[i]`` 对应第 i 页，可为 ``None``）。

        转交给 :meth:`ImpositionPageList.set_page_thumbs`——本控件只做装配，
        不自己碰条目（页条目是 ``page_list`` 的私产）。
        """
        self.page_list.set_page_thumbs(thumbs)

    def set_thumb_at(self, index: int, image) -> None:
        """只给**第 ``index`` 页**贴缩略图（"一张张到齐"的回填走这里）。

        ⚠️ 别用 :meth:`set_page_thumbs` 做批量回填：它会遍历**全部**条目，
        而每条都要重跑一次缩放——380 张陆续到达就是 7.2 万次（用户
        2026-10-06 报"拼版阶段程序卡死"）。转发见
        :meth:`ImpositionPageList.set_thumb_at`。
        """
        self.page_list.set_thumb_at(index, image)

    def pages(self) -> list[dict]:
        return list(self._pages)

    def set_current(self, index: int) -> None:
        """切到某一页（-1 = 无页，画布清空）。"""
        if index >= len(self._pages):
            index = len(self._pages) - 1
        self._current = index if index >= 0 else -1
        self.page_list.set_current(self._current)
        if self._current < 0:
            self.canvas.clear_page()
        elif not self._canvas_shows_current():
            self.canvas.set_page(self._pages[self._current].get("items") or [])
        self._update_hint()

    def _canvas_shows_current(self) -> bool:
        """画布现在画的是不是就是当前页这份版面（数值一致即可）。

        一致就**不重灌**：``canvas.set_page`` 会清空选中并丢掉图缓存——
        拖动/旋转落盘后的回灌（``_refresh_imposition_view``）带着**同一份**
        数据走到这里，重灌一次等于把用户刚选中的图弹掉、再把两张大图白解码
        一遍。只有版面真的变了（切到别的页、复位、增删页）才重灌。
        """
        current = self.canvas.items()
        items = self._pages[self._current].get("items") or []
        if len(current) != len(items):
            return False
        for got, want in zip(current, items):
            if got["file"] != str(want.get("file") or ""):
                return False
            rect = [float(v) for v in (want.get("rect") or ())]
            if len(rect) != 4 or any(
                abs(a - b) > 0.01 for a, b in zip(got["rect"], rect)
            ):
                return False
            if abs(got["rotation"] - float(want.get("rotation") or 0.0)) > 0.01:
                return False
        return True

    def current_index(self) -> int:
        return self._current

    def checked_pages(self) -> list[int]:
        """左列勾选了的页下标（升序）——批量操作用。"""
        return self.page_list.checked_indexes()

    def current_items(self) -> list[dict]:
        return self.canvas.items()

    def selected_slot(self) -> int:
        return self.canvas.selected()

    def update_current_items(self, items: list[dict]) -> None:
        """把外部（面板按钮）改过的版面写回当前页并重画画布。"""
        if self._current < 0:
            return
        self._pages[self._current]["items"] = list(items)
        page = self._pages[self._current]
        self.canvas.set_page(page.get("items") or [])

    def flush_pending(self) -> None:
        """离开页面前的补发（拖住未松手就切走时别丢改动）。"""
        self.canvas.flush_pending()

    # ------------------------------------------------------------------ 内部
    def _step_page(self, delta: int) -> None:
        """「上一页/下一页」：与左列点选同一条路径（切页 + 发 page_selected）。

        先 ``flush_pending``：拖住图没松手就点翻页时，这一下改动不能丢。
        """
        target = self._current + delta
        if not (0 <= target < len(self._pages)):
            return
        self.canvas.flush_pending()
        self._on_page_selected(target)

    def _on_page_selected(self, index: int) -> None:
        self.set_current(index)
        self.page_selected.emit(index)

    def _on_items_changed(self, items: list) -> None:
        if self._current < 0:
            return
        self._pages[self._current]["items"] = list(items)
        self.items_changed.emit(self._current, list(items))

    def _update_hint(self) -> None:
        # 翻页按钮跟着当前页走：首页没有「上一页」，末页没有「下一页」
        self.prev_button.setEnabled(self._current > 0)
        self.next_button.setEnabled(0 <= self._current < len(self._pages) - 1)
        # 空态引导层：**只看"有没有页"**（独立页首轮自动拼版传 current=-1，
        # 页已存在却还没选中——那一刻引导层也必须收起，否则红框悬在满列
        # 页条目上撒谎）。显隐驱动只有这一处。
        self.empty_guide.setVisible(not self._pages)
        if self.empty_guide.isVisible():
            self.empty_guide.raise_()
        if self._current < 0:
            self.hint_main.setText("还没有拼版页")
            self.hint.setText(
                "点左侧虚线「＋ 选择拼版」，从剩余未被选择拼版的图片里勾选"
                "（不限张数），开始拼版每两张一页。"
            )
            return
        stems = page_source_stems(self._pages[self._current])
        # 单图页（自动拼版里整幅/落单图单独成的那页）：没有左右槽，只报整幅名
        if len(stems) == 1:
            self.hint_main.setText(
                f"{cn_page_label(self._current)}　·　整幅"
                f'<b><font color="{SPINE_COLOR.name()}">「{html.escape(stems[0])}」</font></b>'
            )
            return
        right = html.escape(stems[0])
        left = html.escape(stems[1])
        # 颜色只引画布常量（SPINE_COLOR / CROP_COLOR），不许再抄一份色值：
        # 画布标注换了色，文字里的词必须跟着变，否则文字就在撒谎。
        spine = SPINE_COLOR.name()
        crop = CROP_COLOR.name()
        self.hint_main.setText(
            f"{cn_page_label(self._current)}　·　右侧"
            f'<b><font color="{spine}">「{right}」</font></b>'
            f'　·　左侧<b><font color="{spine}">「{left}」</font></b>'
        )
        self.hint.setText(
            "拖动移动　·　四角/四边缩放拉伸　·　框上方圆钮旋转　·　滚轮缩放视图　｜　"
            "双击图片编辑整页　·　双击空白处预览成品组合　｜　"
            "右键图片/空白处可预览或编辑（编辑统一作用于整页）　｜　"
            "点击图片选中后可在右侧「当前图片样式」里调整"
            f'（<font color="{spine}">红色虚线</font>为两图公共中心线，'
            f'<font color="{crop}">灰色虚线框</font>为成品截图范围）。'
        )
