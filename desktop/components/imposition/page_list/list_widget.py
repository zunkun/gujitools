# -*- coding: utf-8 -*-
"""左列拼版页清单（``ImpositionPageList``）主类骨架：信号 / 构造 / 数据 / 视口。

拆包后的职责划分：条目与「＋ 选择拼版」见 :mod:`.entries`，批量悬浮框见
:mod:`.select_bar`，右键菜单见 :mod:`.menu`，勾选批量见 :mod:`.selection`，
拖动排序见 :mod:`.drag`。
"""

from __future__ import annotations

from functools import partial

from desktop.components.imposition.page_list._qt import (
    QFrame,
    QPoint,
    QPropertyAnimation,
    QScrollArea,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)
from desktop.components.imposition.page_list.drag import _DragMixin
from desktop.components.imposition.page_list.entries import _AddEntry, _PageEntry
from desktop.components.imposition.page_list.menu import _MenuMixin
from desktop.components.imposition.page_list.select_bar import _SelectBar
from desktop.components.imposition.page_list.selection import _SelectionMixin
from desktop.ui import theme as T


class ImpositionPageList(_DragMixin, _MenuMixin, _SelectionMixin, QWidget):
    """左列拼版页清单：滚动的页条目 + 底部固定的虚线「＋ 选择拼版」。

    只认文案：``set_pages(captions)`` 灌入每页的副标题（两张源图名），
    条目数即页数；当前页高亮由 ``set_current`` 控制。勾选了页，一条悬浮
    操作框（``_SelectBar``）悬在页码栏右侧中部（可拖动），提供
    「取消选择 / 批量删除」。

    页条目支持**按住上下拖动排序**，交互口径（用户 2026-09-30 三稿：拖动
    中清单不留空档）：按下后**本体留在原位置灰**，一张等大的「幽灵卡」
    跟着光标走，主色细线指示松手后落到哪——清单全程一动不动。**松手**
    后幽灵卡滑进落点槽位、这才真正换位，随后发
    ``reorder_requested(from, target)``——``target`` 是**拖走之后**的插入
    下标（调用方据此 pop/insert），拖回原位则不发。
    """

    #: 点了某一页
    page_selected = Signal(int)
    #: 点了虚线「＋ 选择拼版」
    add_requested = Signal()
    #: 拖动某页松手：``from`` 移到 ``target``（都是移除前的口径）
    reorder_requested = Signal(int, int)
    #: 右键「上移 / 下移」：``index`` 页上移(-1)/下移(+1) 一位
    move_requested = Signal(int, int)
    #: 右键「向前插入拼版 / 向后插入拼版」：``index`` 页之前/之后插入新页
    #: （``position`` 是 ``"before"`` / ``"after"``，由控制器弹窗选图）
    insert_requested = Signal(int, str)
    #: 点了某页右侧的「✕」：释放该页图片回未选择列表
    remove_requested = Signal(int)
    #: 勾选集合变了（含「取消选择」一键清空；控制器一般不用接）
    check_changed = Signal()
    #: 点了悬浮框「批量删除」
    batch_delete_requested = Signal()
    #: **可见页范围变了**（滚动/翻页/换任务/窗口缩放）。控制器据此只给看得见
    #: 的那几页生成缩略图（见 ``page_thumb.PageThumbManager.set_window_provider``）。
    viewport_changed = Signal()

    #: 拖动期间轮询光标的间隔（毫秒）
    _POLL_MS = 16
    #: 落位动画时长（毫秒）——短促跟手，不拖泥带水
    _ANIM_MS = 140
    #: 落点指示线的厚度（像素）
    _INDICATOR_H = 3
    #: 拖到滚动区上/下边缘这个距离内开始自动滚动（像素）
    _EDGE_PX = 24
    #: 自动滚动每轮步长（像素）
    _EDGE_STEP = 6
    #: 可见范围变化的**合并窗口**（毫秒）：滚动条每滚一格都会发 valueChanged，
    #: 立刻回调会让控制器反复取窗口；等手停下来一拍再报一次就够。
    _VIEWPORT_DEBOUNCE_MS = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[_PageEntry] = []
        self._current = -1
        self._drag_from = -1
        self._drag_drop = -1
        self._drag_entry: _PageEntry | None = None   # 被拖的本体（留在原位）
        self._ghost: _PageEntry | None = None        # 跟着光标的幽灵卡
        self._flow: list[_PageEntry] = []            # 拖动中除本体外的东西
        self._anims: list[QPropertyAnimation] = []
        self._grab_dy = 0                     # 光标到卡片顶缘的抓取偏移
        self._drag_x = 0                      # 拖动横坐标（只上下拖，不横移）
        self._committing = False              # 松手落位动画进行中
        #: 待办的"把第几页滚进视口"（-1 = 没有）。布局还没跑时记下来补做，
        #: 见 :meth:`ensure_visible` / :meth:`_apply_pending_visible`。
        self._visible_pending = -1
        #: 补做还剩几拍（布局一般一两拍就跑完，别无限重试）
        self._visible_retries = 0

        # 滚不动时也不挤压右侧画布
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFixedWidth(150)
        self.list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.list_box = QVBoxLayout(container)
        self.list_box.setContentsMargins(0, 0, 0, 0)
        self.list_box.setSpacing(T.SPACE_SM)
        # 弹性空白垫在最底下：条目少时它们靠上排，不被摊开
        self.list_box.addStretch(1)
        self.list_scroll.setWidget(container)

        # 拖动排序的落点指示线（画在条目之间，指示松手后落到哪）
        self._indicator = QWidget(container)
        self._indicator.setFixedHeight(self._INDICATOR_H)
        self._indicator.setStyleSheet(
            f"background-color: {T.ACCENT}; border-radius: 1px;"
        )
        self._indicator.hide()

        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(self._POLL_MS)
        self._drag_timer.timeout.connect(self._poll_drag)
        #: 最近一次弹出的右键菜单（非阻塞 ``exec`` 不回收；下一次右键先销毁它，
        #: 否则每右键一次就残留一个窗口）
        self._context_menu = None

        row = QVBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)
        row.addWidget(self.list_scroll, 1)
        # 「＋ 选择拼版」钉在左列最底部（用户 2026-09-30：不跟在页码下面，
        # 页再多/再少它都钉在底部一格），从滚动区里拿出来，永远看得见
        self.add_entry = _AddEntry(self)
        self.add_entry.clicked.connect(self.add_requested)
        row.addWidget(self.add_entry)

        # 多选悬浮框：浮在滚动区下沿（盖住条目），勾选数归零自动收起
        self.select_bar = _SelectBar(self)
        self.select_bar.clear_requested.connect(self._clear_selection)
        self.select_bar.delete_requested.connect(self.batch_delete_requested)
        self.select_bar.hide()

        # 可见范围变化的合并上报（滚动、窗口缩放、换任务清单都会触发）
        self._viewport_timer = QTimer(self)
        self._viewport_timer.setSingleShot(True)
        self._viewport_timer.setInterval(self._VIEWPORT_DEBOUNCE_MS)
        self._viewport_timer.timeout.connect(self.viewport_changed.emit)
        self.list_scroll.verticalScrollBar().valueChanged.connect(
            lambda *_: self._viewport_timer.start()
        )
        # 滚动条**范围**变了（条目增删/布局终于跑完）→ 有待办的当前页就补滚一次。
        # ⚠️ 这是 `ensure_visible` 的兜底触发：刚 `set_pages` 出来的那几拍里
        #    几何还是默认值（滚不动），等布局真正算完范围才会变——那时才知道
        #    该滚到哪儿（见 ensure_visible 的说明）。
        self.list_scroll.verticalScrollBar().rangeChanged.connect(
            self._on_scroll_range_changed
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.select_bar.isVisible() and not self.select_bar._user_moved:
            self._place_select_bar()
        # 窗口一高一矮，可见页数就变了：让宿主重算一次窗口
        self._viewport_timer.start()

    def set_float_host(self, host) -> None:
        """把悬浮框的宿主换成外部装配层（拼版视图整体）。

        页码栏只有 150px 宽，框要「浮在页码栏**右侧**」就得允许它超出本列、
        悬到右边画布上——挂到视图底下才行。``view.py`` 装配时调用；不设置
        则兜底贴在清单内右缘、垂直居中。
        """
        self.select_bar.setParent(host)
        self.select_bar.hide()

    # ------------------------------------------------------------------ 数据
    def entries(self) -> list[_PageEntry]:
        return list(self._entries)

    def release_thumbs(self) -> None:
        """丢掉每条已贴的缩略图位图（页码/副标题/勾选/当前页都不动）。

        离开「图片拼版」步骤时调：一本 2000 页的书左列贴着的位图是几百 MB。
        回来时 ``set_pages`` 重建条目、宿主按缩略图管理者重新读盘贴回。
        """
        for entry in self._entries:
            entry.set_thumb(None)

    def set_pages(self, captions: list[str], current: int = -1) -> None:
        """按页数重建清单（``captions[i]`` 是第 i 页的副标题）。

        勾选集合**按副标题跨重建保留**：拖动排序/加页不丢勾选；页被删掉
        （副标题不在了）自然落选——批量删除自己就是靠这次重建清空的。

        ⚠️ **清单没变就只切当前页、不重建条目**（2026-11-21）：离开再回到
        拼版步骤时宿主每次都调这里（``_refresh_imposition_view``），而一本
        91 页的书重建 91 个 ``_PageEntry``（各自带 QLabel/QCheckBox/缩略图）
        纯属白费——位图已经在离开时释放，条目对象没必要跟着换一遍。
        """
        self._cancel_drag()
        captions = list(captions)
        if captions == [entry.caption for entry in self._entries]:
            self.set_current(current)
            self._update_select_bar()
            if 0 <= current < len(self._entries):
                self.ensure_visible(current)
            return
        keep_checked = {e.caption for e in self._entries if e.is_checked()}
        for entry in self._entries:
            self.list_box.removeWidget(entry)
            entry.deleteLater()
        self._entries = []
        for index, caption in enumerate(captions):
            entry = _PageEntry(index, caption, self.list_scroll.widget())
            entry.clicked.connect(self._on_entry_clicked)
            entry.drag_started.connect(self._on_drag_started)
            entry.remove_clicked.connect(self.remove_requested)
            entry.check_toggled.connect(self._on_entry_check_toggled)
            entry.customContextMenuRequested.connect(
                partial(self._on_entry_context_menu, entry)
            )
            entry.set_checked(caption in keep_checked)
            self.list_box.insertWidget(index, entry)
            self._entries.append(entry)
        self.set_current(current)
        self._update_select_bar()
        # 重建后当前页多半落在视口外（滚到第 20 页改一下版面就必然如此），
        # 必须把它滚进来——否则用户只看到清单回到顶部、正在编辑的那页不见
        # （用户 2026-11-21 报的正是这个）。布局还没跑，ensure_visible 自己会
        # 下一拍补做，见其说明。
        if 0 <= current < len(self._entries):
            self.ensure_visible(current)
        # 清单重建后可见范围必然变了（页数/顺序/滚动位置都可能不同）。延到
        # 下一拍：那时布局才把条目几何算出来，否则取到的是全 0 的旧几何。
        QTimer.singleShot(0, self._viewport_timer.start)

    def ensure_visible(self, index: int) -> None:
        """把第 ``index`` 页滚进视口（当前页切换 / 清单重建后都要走这里）。

        只在那一页**完全看不见**时才滚（滚动条位置按"整条刚露出来"算），
        已经在视口里就一点不动——键盘翻页时左列跟着走，但不会因为切页把
        用户手动滚好的位置顶掉。

        ⚠️ **布局还没跑时必须补做**（用户 2026-11-21 报「方向键翻到超出可视
        范围的那页，左列不跟着滚、那一页根本看不见」）：``set_pages`` 重建
        条目后的**那一拍**里，条目几何还是 QWidget 默认值（高 30px、滚动条
        max 还是 0）——照几何算出来"已经在视口里"或"滚不动"，于是什么都不做；
        等布局算完范围变了也没人再问一次，当前页就永远停在视口外。现在的做法：
        记进 ``_visible_pending``，由 :meth:`_apply_pending_visible` 在下一拍
        补做，另有滚动条 ``rangeChanged`` 兜底（见 ``__init__``）。
        """
        if not (0 <= index < len(self._entries)):
            self._visible_pending = -1
            return
        self._visible_pending = index
        self._visible_retries = self._VISIBLE_RETRIES
        self._apply_pending_visible()

    #: 布局没跑完时最多补做几拍。实测（离屏 40 页）布局要约 4 拍才把滚动条
    #: 范围算全，这里给到 8 拍；再多就是真滚不动了（条目少 / 视口还没显示）。
    _VISIBLE_RETRIES = 8

    def _entry_laid_out(self, index: int) -> bool:
        """第 ``index`` 条的几何是否已经由布局算出来。

        判据是"实际高度已经长到 sizeHint 高度"：本清单的条目由
        ``QVBoxLayout`` 按 sizeHint 摆，布局没跑时高度停在 QWidget 的默认值
        （30px，比 sizeHint 的 ~156px 小）。⚠️ 不用"滚动条 max > 0"当判据：
        条目少到不用滚时 max 本来就是 0，那是**正常**状态，不是没布局。
        """
        if not (0 <= index < len(self._entries)):
            return False
        entry = self._entries[index]
        hint = entry.sizeHint().height()
        return entry.height() > 0 and entry.height() >= max(1, hint)

    def _on_scroll_range_changed(self, *_args) -> None:
        """滚动条范围变了：有待办的当前页就补滚一次（布局终于算完了）。"""
        if self._visible_pending >= 0:
            self._apply_pending_visible()

    def _apply_pending_visible(self) -> None:
        """按待办把当前页滚进视口；布局还没就绪时下一拍再来（有次数上限）。

        ⚠️ **滚完不等于做完**：滚动条范围/视口高度在接下来一两拍里还可能变
        （``set_pages`` 刚重建完，配套的提示行、外层布局也在同时定型——实测
        视口从 547 掉到 533，前一拍"刚好放下"的条目就又被切掉 14px）。所以
        只要这一拍**动过滚动条**就留待办、下一拍复核，直到"确实整条都看得见"
        才收工。
        """
        index = self._visible_pending
        if not (0 <= index < len(self._entries)):
            self._visible_pending = -1
            return
        viewport = self.list_scroll.viewport()
        if (
            viewport is None
            or viewport.height() <= 0
            or not self._entry_laid_out(index)
        ):
            self._retry_pending_visible()
            return
        entry = self._entries[index]
        bar = self.list_scroll.verticalScrollBar()
        top = entry.mapTo(viewport, QPoint(0, 0)).y()
        bottom = top + entry.height()
        if top >= 0 and bottom <= viewport.height():
            self._visible_pending = -1  # 整条都在视口里：收工
            return
        if top < 0:
            bar.setValue(max(bar.minimum(), bar.value() + top - T.SPACE_SM))
        else:
            bar.setValue(
                min(bar.maximum(), bar.value() + bottom - viewport.height()
                    + T.SPACE_SM)
            )
        self._retry_pending_visible()  # 下一拍复核（范围可能还没算全）

    def _retry_pending_visible(self) -> None:
        """待办还没做成：下一拍再试（次数用完就作废，别留个永不结束的定时器）。"""
        if self._visible_retries > 0:
            self._visible_retries -= 1
            QTimer.singleShot(0, self._apply_pending_visible)
            return
        self._visible_pending = -1

    def visible_index_range(self, margin: int = 3) -> tuple[int, int] | None:
        """左列**当前看得见**的页号闭区间（上下各多算 ``margin`` 条余量）。

        宿主的缩略图生成按这个范围筛（只给看得见的页生成实体）。只有
        **还没有条目**（空清单）才给 ``None``——调用方据此退化成"不筛"。

        ⚠️ **布局还没跑时要给"第一屏"而不是整列**（2026-11-21 实测坑）：刚
        ``set_pages`` 出来的条目几何全是同一个默认值（都叠在 0 处），照几何
        判"看得见"会把**整列 30 页**都算进窗口——首屏照样一次排满，改法就白
        做了。判据是"条目高度还是 0"或"多个条目纵向位置完全一样"，那时一律
        返回 ``0 .. margin*2+1``（宁可多生成一屏，也不排整本）；真正的范围
        等布局完成后由 ``viewport_changed`` 再报一次。视口高度为 0（页面从没
        显示过）同样按第一屏处理——"算不出来"绝不等于"整本都要"。
        """
        if not self._entries:
            return None
        first_screen = (0, min(len(self._entries) - 1, margin * 2 + 1))
        viewport = self.list_scroll.viewport()
        if viewport is None or viewport.height() <= 0:
            return first_screen
        tops = [entry.mapTo(viewport, QPoint(0, 0)).y() for entry in self._entries]
        if any(entry.height() <= 0 for entry in self._entries):
            return first_screen  # 还没布局：条目高度都没算出来
        if len(tops) > 1 and len(set(tops)) == 1:
            return first_screen  # 还没布局：条目全叠在同一个 y 上
        bottom_limit = viewport.height()
        hits = [
            index for index, top in enumerate(tops)
            if top + self._entries[index].height() >= 0 and top <= bottom_limit
        ]
        if not hits:
            return first_screen
        first = max(0, hits[0] - margin)
        last = min(len(self._entries) - 1, hits[-1] + margin)
        return (first, last)

    def set_current(self, index: int) -> None:
        """高亮当前页（-1 = 无页）。"""
        self._current = index if index >= 0 else -1
        for entry in self._entries:
            entry.set_current(entry.index == self._current)

    def set_page_thumbs(self, thumbs: list) -> None:
        """给每页条目灌缩略图（``thumbs[i]`` 是第 i 页的 ``QImage``/``QPixmap``，
        ``None`` 表示还没渲好）。

        用户 2026-10-03：所有独立任务左栏都显示缩略图。**本方法只管贴图**，
        解码/缓存/异步在宿主那边做（拼图模块页用
        :class:`~desktop.workers.thumb_cache_worker.ImageThumbCacheWorker`，
        与其余四个独立任务页同一份缓存与同一份逻辑）。

        ⚠️ 下标要**按条目自己的 index** 灌而不是按参数位置：``set_pages`` 重建
        后条目的 index 是重建时的下标，两者一致；但拖动排序后条目的 index
        仍是它创建时的下标，而 ``_entries`` 的**列表位置**才是当前页序——
        所以这里遍历 ``_entries`` 并用 ``entry.index`` 取图。
        """
        by_index = {
            i: t for i, t in enumerate(thumbs or []) if t is not None
        }
        for entry in self._entries:
            entry.set_thumb(by_index.get(entry.index))

    def set_thumb_at(self, index: int, image) -> None:
        """只给**指定条目**贴缩略图（``index`` 是它在当前清单里的位置）。

        ⚠️ **"一张张到齐"的回填必须用它，不要用** :meth:`set_page_thumbs`：那个
        方法会遍历**全部**条目逐个 ``set_thumb``，于是"380 张缩略图陆续到达"
        变成 380 × 380 ≈ **7.2 万次** ``set_thumb``；而 ``set_thumb`` 每次都要
        重跑一次 ``pixmap.scaled(SmoothTransformation)``（现在有"同一张图早退"，
        但已贴过的那 379 条仍要走一遍字典查表 + 早退判断）。

        实测（离屏，380 页拼版）：整列重灌 = **主线程连续占住 27.5 秒**，
        用户看到的就是"程序卡死"；只贴单条 = **~0.03 秒**。

        ⚠️ 这里用**位置**（``_entries`` 的下标）而不是 ``entry.index``：调用方
        传的是"清单里的第几页"（与页面清单同序），拖动排序后两者会分叉
        ——那种情况下贴错一条比不贴更难查。

        无此条目（清单变短了/下标越界）时**静默忽略**：那是"用户正在翻页或
        删页"，不该让一个迟到的缩略图把异常抛到事件循环外面。
        """
        if not (0 <= index < len(self._entries)):
            return
        self._entries[index].set_thumb(image)

    def current(self) -> int:
        return self._current

    def _on_entry_clicked(self, index: int) -> None:
        self.set_current(index)
        self.page_selected.emit(index)
