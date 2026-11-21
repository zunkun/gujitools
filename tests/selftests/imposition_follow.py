# -*- coding: utf-8 -*-
"""左列缩略图**跟随当前页**（用户 2026-11-21）。

> 左側縮略圖，現在可以根據箭頭方向上下切換了，但是切換頁面如果超出當前空間
> 範圍，沒有跟著顯示在視圖裡面，檢查所有步驟左側縮略圖

现象：方向键把**右侧预览**切到第 25 页了，左侧清单还停在开头——当前页在
清单里根本看不见（缩略图也因此永远不进"可见窗口"，看起来像没生成）。

两处根因，本用例各守一条：

1. **拼版左列（``ImpositionPageList``）**：``set_pages`` 重建条目后的那一拍里
   几何还是默认值（高 30px、滚动条 max 0），``ensure_visible`` 照几何算出来
   "已经在视口里/滚不动"就什么都不做；等布局算完范围，也没人再问一次。
   而且 ``set_pages`` 重建时压根没调 ``ensure_visible``（``view.set_current``
   因为页号没变也不会调）。改法：重建后必调 + 布局没就绪时下一拍补做/复核。
2. **四步共用的缩略图条（``ThumbStrip``）**：换当前行的唯一信号里显式
   ``scrollToItem(EnsureVisible)``（提取/检测/去底色/打印都用它）。

另外守"不许乱动"：当前页**已经整条看得见**时，滚动条一格都不许挪——否则
用户手动滚着翻看，一切页就被拽回去。
"""

from __future__ import annotations

NAME = "imposition_follow"
DEPENDS: list[str] = []
TITLE = "左列缩略图跟随当前页（方向键/清单重建后都滚进视口）"

#: 页面数：足够多，当前页必然落在首屏之外
PAGES = 40


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_imposition_view(ctx, ok)
    _check_thumb_strip(ctx, ok)


# ------------------------------------------------------------------ 工具
def _page(*stems: str) -> dict:
    """一页拼版（**虚拟**：只要文件名与 rect，不读盘、不解码）。"""
    return {
        "items": [
            {
                "file": f"C:/guji_fake/{stem}.png",
                "rect": [0.0, 0.0, 100.0, 200.0],
                "rotation": 0.0,
            }
            for stem in stems
        ]
    }


def _pages(count: int) -> list[dict]:
    return [_page(f"{i}-r", f"{i}-l") for i in range(1, count + 1)]


def _build_view(ctx, pages: int = PAGES, current: int = 0):
    """建一个真显示出来的拼版视图（要几何，所以必须 show + 跑布局）。"""
    from desktop.components.imposition.view import ImpositionViewWidget

    view = ImpositionViewWidget()
    view.resize(900, 620)
    view.show()
    view.set_pages(_pages(pages), current=current)
    _settle(ctx)
    return view


def _settle(ctx, times: int = 12) -> None:
    """跑够事件循环：布局、补做滚动、可见范围上报都要落地。"""
    from tests.selftests._context import pump

    pump(ctx.app, times=times, interval=0.01)


def _entry_box(page_list, index: int) -> tuple[int, int, int]:
    """第 index 页在**视口坐标系**里的 (top, bottom, 视口高)。"""
    from PySide6.QtCore import QPoint

    viewport = page_list.list_scroll.viewport()
    entry = page_list.entries()[index]
    top = entry.mapTo(viewport, QPoint(0, 0)).y()
    return top, top + entry.height(), viewport.height()


def _fully_visible(page_list, index: int) -> bool:
    """第 index 页是否**整条**都在左列视口里。"""
    top, bottom, height = _entry_box(page_list, index)
    return 0 <= top and bottom <= height


def _detail(page_list, index: int) -> str:
    top, bottom, height = _entry_box(page_list, index)
    bar = page_list.list_scroll.verticalScrollBar()
    return (f"top={top} bottom={bottom} vp_h={height} "
            f"bar={bar.value()}/{bar.maximum()}")


# ------------------------------------------------------------------ 用例 1
def _check_imposition_view(ctx, ok) -> None:
    """拼版左列：清单重建 / 方向键翻页之后，当前页都在视口里。"""
    from PySide6.QtCore import Qt

    from desktop.components.imposition.view import ImpositionViewWidget

    # ---- 1. 重建清单 + 当前页在末尾之外：布局跑完后必须滚到那一页 ----
    view = _build_view(ctx, current=PAGES - 1)
    try:
        ok(
            "拼版左列：重建清单后，当前页被滚进视口（不再停在开头）",
            _fully_visible(view.page_list, view.current_index()),
            _detail(view.page_list, view.current_index()),
        )
        ok(
            "拼版左列：滚动后「可见窗口」也覆盖当前页（缩略图才会跟着生成）",
            _covers(view.visible_page_range(), view.current_index()),
            f"{view.visible_page_range()} current={view.current_index()}",
        )

        # ---- 2. 已经看得见时不许乱动（用户手动滚的位置不能被顶掉）----
        bar = view.page_list.list_scroll.verticalScrollBar()
        before = bar.value()
        view.page_list.ensure_visible(view.current_index())
        _settle(ctx, times=4)
        ok(
            "拼版左列：当前页已可见时 ensure_visible 一格都不滚",
            bar.value() == before,
            f"before={before} after={bar.value()}",
        )
    finally:
        view.deleteLater()
        _settle(ctx, times=4)

    # ---- 3. 方向键逐页翻到视口外（往下、再往回）----
    view = _build_view(ctx, current=0)
    view.setFocus(Qt.FocusReason.MouseFocusReason)
    try:
        for _ in range(PAGES - 2):
            view.navigate(True)
        _settle(ctx)
        cur = view.current_index()
        ok(
            "拼版左列：方向键往下翻 38 页，当前页仍整条可见（左列跟着滚）",
            cur == PAGES - 2 and _fully_visible(view.page_list, cur),
            f"current={cur} " + _detail(view.page_list, cur),
        )

        for _ in range(PAGES - 3):
            view.navigate(False)
        _settle(ctx)
        cur = view.current_index()
        ok(
            "拼版左列：方向键往回翻 37 页，当前页仍整条可见（往上也跟）",
            cur == 1 and _fully_visible(view.page_list, cur),
            f"current={cur} " + _detail(view.page_list, cur),
        )

        # ---- 4. 重建（每次落盘后控制器都这么做）不打断跟随 ----
        for target in (2, 11, 27):
            view.set_pages(_pages(PAGES), current=target)
            _settle(ctx)
            ok(
                f"拼版左列：重建到第 {target + 1} 页后，那一页仍整条可见",
                view.current_index() == target
                and _fully_visible(view.page_list, target),
                _detail(view.page_list, target),
            )
        ok(
            "拼版左列：跟随当前页的逻辑只有一份实现（set_pages 与 set_current 共用）",
            ImpositionViewWidget.set_current.__doc__ is not None
            and "ensure_visible" in _src(ImpositionViewWidget.set_current),
        )
    finally:
        view.deleteLater()
        _settle(ctx, times=4)


def _covers(rng, index: int) -> bool:
    """可见范围（可空）是否覆盖 index。"""
    if rng is None:
        return False
    return rng[0] <= index <= rng[1]


def _src(func) -> str:
    """函数源码（静态契约断言用）。"""
    import inspect

    return inspect.getsource(func)


# ------------------------------------------------------------------ 用例 2
def _check_thumb_strip(ctx, ok) -> None:
    """四步共用的缩略图条：换当前行就把它滚进视口。"""
    from desktop.components.viewers.thumb_strip import ThumbStrip

    strip = ThumbStrip()
    strip.resize(ThumbStrip.STRIP_WIDTH, 300)
    strip.show()
    try:
        for i in range(PAGES):
            strip.add_page_item(f"第 {i + 1} 页", str(i))
        strip.setCurrentRow(0)
        _settle(ctx, times=6)

        for _ in range(25):
            strip.navigate(True)
        _settle(ctx, times=6)
        ok(
            "缩略图条：方向键往下翻 25 页，当前行滚进视口",
            strip.currentRow() == 25 and strip.is_row_visible(strip.currentRow()),
            f"row={strip.currentRow()} range={strip.visible_row_range()} "
            f"bar={strip.verticalScrollBar().value()}"
            f"/{strip.verticalScrollBar().maximum()}",
        )

        for _ in range(20):
            strip.navigate(False)
        _settle(ctx, times=6)
        ok(
            "缩略图条：往回翻 20 页，当前行同样滚进视口",
            strip.currentRow() == 5 and strip.is_row_visible(strip.currentRow()),
            f"row={strip.currentRow()} range={strip.visible_row_range()}",
        )

        # 程序化跳行（打印列表恢复上次停留页、检测统计点页码都这么走）
        strip.setCurrentRow(PAGES - 1)
        _settle(ctx, times=6)
        ok(
            "缩略图条：程序化 setCurrentRow 到末页也会滚进视口",
            strip.is_row_visible(strip.currentRow()),
            f"row={strip.currentRow()} range={strip.visible_row_range()}",
        )

        ok(
            "缩略图条：跟随当前行的实现只有一份（当前行变化信号里滚）",
            "ensure_row_visible" in _src(ThumbStrip._on_current_row_changed),
        )
    finally:
        strip.deleteLater()
        _settle(ctx, times=4)

    _check_strip_resize_drift(ctx, ok)


def _check_strip_resize_drift(ctx, ok) -> None:
    """缩略图到货把**上方条目**变矮时，当前行不能被挤出视口。

    占位条目按满框高 182，真实缩略图按比例缩短（宽页只剩 ~80）。上方那几条
    一变矮，后面所有条目在像素上整体上移，而滚动条的值是像素——当前行会跑到
    视口上面去（2026-11-21 实测第 51 条直接从视口消失，滚动条还已到 max）。
    """
    from PySide6.QtGui import QColor, QImage

    from desktop.components.viewers.thumb_strip import ThumbStrip

    def wide() -> QImage:
        """宽图（300×120）：放进 116×156 框后条目高度掉到最小档。"""
        image = QImage(300, 120, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        return image

    strip = ThumbStrip()
    strip.resize(ThumbStrip.STRIP_WIDTH, 300)
    strip.show()
    try:
        for i in range(PAGES):
            strip.add_page_item(f"第 {i + 1} 页", str(i))
        _settle(ctx, times=6)
        strip.setCurrentRow(PAGES - 10)
        _settle(ctx, times=6)
        ok(
            "缩略图条：跳行到后段，当前行先滚进视口",
            strip.is_row_visible(strip.currentRow()),
            f"row={strip.currentRow()} range={strip.visible_row_range()}",
        )

        # 上方 51 条缩略图陆续到货、条目变矮
        for i in range(PAGES - 9):
            strip.set_item_icon(i, wide(), str(i), f"第 {i + 1} 页")
        _settle(ctx, times=8)
        ok(
            "缩略图条：上方条目变矮后，当前行没被挤出视口（不漂走）",
            strip.is_row_visible(strip.currentRow()),
            f"row={strip.currentRow()} range={strip.visible_row_range()} "
            f"bar={strip.verticalScrollBar().value()}"
            f"/{strip.verticalScrollBar().maximum()}",
        )

        # 用户自己滚走看别处 → 迟到的缩略图不许把他拽回来
        strip.setCurrentRow(3)
        _settle(ctx, times=4)
        bar = strip.verticalScrollBar()
        bar.setValue(bar.maximum())
        _settle(ctx, times=4)
        ok("缩略图条：用户滚走时当前行确实不在视口里（反例前提）",
           not strip.is_row_visible(strip.currentRow()),
           f"row={strip.currentRow()} range={strip.visible_row_range()}")
        for i in range(PAGES - 9):
            strip.set_item_icon(i, wide(), str(i), f"第 {i + 1} 页")
        _settle(ctx, times=8)
        ok(
            "缩略图条：用户已滚走时，缩略图到货不把当前行硬拽回视口",
            not strip.is_row_visible(strip.currentRow()),
            f"row={strip.currentRow()} range={strip.visible_row_range()} "
            f"bar={bar.value()}/{bar.maximum()}",
        )
    finally:
        strip.deleteLater()
        _settle(ctx, times=4)
