# -*- coding: utf-8 -*-
"""4c. 无纸张 + 不限制图片位置/大小（用户 2026-09-30） / 5. 左列结构与选择弹窗 / 勾选多选 + 悬浮批量操作框（用户 2026-09-30） / 悬浮框摆位与拖动（用户 2026-09-30：页码栏右侧中部、可拖） / 选中态（用户 2026-09-30：点图才有选中；切页后图片操作区不激活） / 拖动排序（2026-09-30 三稿口径：拖动中清单一动不动、不留空档"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import RED, _count_near, _count_non_white, _names
    from desktop.components.imposition.canvas import ImpositionCanvas
    from desktop.components.imposition.picker import (
        DIALOG_H,
        DIALOG_W,
        THUMB_H,
        THUMB_W,
        ImpositionPickerDialog,
    )
    from desktop.components.imposition.view import ImpositionViewWidget
    from PySide6.QtCore import QEvent
    from PySide6.QtCore import QPointF, QSize, Qt
    from desktop.services import imposition as S
    from desktop.components.imposition.page_list import _AddEntry, _PageEntry
    from tests.selftests._context import make_pdf, ok, pump
    outside = ImpositionCanvas()
    outside.resize(600, 600)
    far = [{"file": str(st.a), "rect": [700.0, 0.0, 400.0, 600.0], "rotation": 0.0}]
    outside.set_page(far)
    scene = outside._scene_rect()
    ok(
        "可视范围就是图的外接框（没有纸张框着）",
        abs(scene.x() - 700.0) < 0.01 and abs(scene.width() - 400.0) < 0.01,
        f"x={scene.x():.0f} w={scene.width():.0f}",
    )
    ok(
        "摆到很远的图**照常画出来**（不再被裁掉）",
        _count_near(outside.grab().toImage(), RED) > 50,
        f"红色采样={_count_near(outside.grab().toImage(), RED)}",
    )

    # 拖动没有任何范围夹取：拖多远就停多远
    outside.select(0)
    start = outside._rect_px(0).center()
    outside.mousePressEvent(
        st._mouse(QEvent.Type.MouseButtonPress, (start.x(), start.y()))
    )
    outside.mouseMoveEvent(
        st._mouse(QEvent.Type.MouseMove, (start.x() + 200, start.y() + 120))
    )
    outside.mouseReleaseEvent(
        st._mouse(QEvent.Type.MouseButtonRelease, (start.x() + 200, start.y() + 120))
    )
    moved = outside.items()[0]["rect"]
    ok(
        "拖动不设范围限制（拖多远就停多远）",
        moved[0] > 900.0 and moved[1] > 100.0,
        f"x={moved[0]:.0f} y={moved[1]:.0f}",
    )

    # 缩放/拉伸同样不设上限
    outside._items[0]["rect"] = [0.0, 0.0, 400.0, 600.0]
    outside._grab_rect = [0.0, 0.0, 400.0, 600.0]
    outside._handle = 5  # 右边
    big = outside._resize_from_handle(
        st._mouse(QEvent.Type.MouseMove, (1400.0, 300.0)), False
    )
    ok("缩放不设上限（想拉多宽就多宽）", big[2] > 1000.0, f"宽={big[2]:.0f}")
    outside.deleteLater()
    st.canvas.deleteLater()
    st.view = ImpositionViewWidget()
    st.view.resize(900, 600)
    st.view.set_pages([st.made, st.made])
    ok(
        "左列 = 每页一个条目",
        len(st.view.page_list.entries()) == 2
        and all(isinstance(e, _PageEntry) for e in st.view.page_list.entries()),
    )
    ok(
        "左列条目是中文页码",
        [e.title_label.text() for e in st.view.page_list.entries()]
        == ["第一页", "第二页"],
    )
    ok("末格是虚线「＋ 选择拼版」", isinstance(st.view.page_list.add_entry, _AddEntry))
    # 「＋ 选择拼版」钉在左列最底部（滚动区之外，页多页少都看得见）
    _pl_layout = st.view.page_list.layout()
    assert _pl_layout is not None
    _last_item = _pl_layout.itemAt(_pl_layout.count() - 1)
    ok(
        "虚线格钉在左列最底部（滚动区之外、列内最后一格）",
        _last_item is not None
        and _last_item.widget() is st.view.page_list.add_entry
        and st.view.page_list.add_entry.parent() is st.view.page_list
        and st.view.page_list.list_box.indexOf(st.view.page_list.add_entry) == -1,
    )
    st.view.show()
    pump(st.ctx.app, times=6)

    # 「✕」只在当前页右侧显示；点它发 remove_requested（释放该页图片）
    st.view.set_current(1)
    ok(
        "「✕」只在当前页右侧显示",
        not st.view.page_list.entries()[0].remove_button.isVisibleTo(st.view.page_list)
        and st.view.page_list.entries()[1].remove_button.isVisibleTo(st.view.page_list),
    )
    removed = []
    st.view.page_remove_requested.connect(removed.append)
    st.view.page_list.entries()[1].remove_button.click()
    ok("点「✕」发 remove_requested(该页下标)", removed == [1], str(removed))
    st.entries = st.view.page_list.entries()
    ok(
        "条目左上有勾选框（缩略图在上、文字在下、勾选框贴左上角）",
        all(e.checkbox.isVisibleTo(e) for e in st.entries)
        and all(e.checkbox.x() < e.width() // 2 for e in st.entries)
        and all(e.checkbox.y() < e.thumb.y() for e in st.entries)
        and all(
            e.thumb.y() < e.title_label.y() <= e.caption_label.y() for e in st.entries
        ),
        str(
            [
                (e.checkbox.x(), e.checkbox.y(), e.thumb.y(), e.title_label.y())
                for e in st.entries
            ]
        ),
    )
    ok(
        "没勾选 → 悬浮批量条收起",
        not st.view.page_list.select_bar.isVisibleTo(st.view.page_list),
    )
    clicks = []
    st.view.page_selected.connect(clicks.append)
    st.entries[0].checkbox.click()
    ok("点勾选框不触发切页", clicks == [], str(clicks))
    ok(
        "勾 1 页 → 悬浮条浮出、计数正确",
        st.view.page_list.checked_indexes() == [0]
        and st.view.page_list.select_bar.isVisibleTo(st.view.page_list)
        and st.view.page_list.select_bar.count_label.text() == "已选 1 页",
        st.view.page_list.select_bar.count_label.text(),
    )
    st.entries[1].checkbox.setChecked(True)
    ok(
        "第二个也勾上 → 升序两页",
        st.view.page_list.checked_indexes() == [0, 1]
        and st.view.page_list.select_bar.count_label.text() == "已选 2 页",
        st.view.page_list.select_bar.count_label.text(),
    )
    st.view.page_list.set_pages(
        [" · ".join(S.page_source_stems(p)) for p in (st.made, st.made)],
        current=0,
    )  # 同样两页重建（caption 不变）→ 勾选跨重建保留
    ok(
        "重建清单后勾选保留（拖动排序不丢勾）",
        st.view.page_list.checked_indexes() == [0, 1]
        and st.view.page_list.select_bar.isVisibleTo(st.view.page_list),
        str(st.view.page_list.checked_indexes()),
    )
    st.view.page_list.set_pages(["甲右 · 甲左", "乙右 · 乙左"], current=0)
    # 两页副标题都换了 → 保留集合里没有它们的 caption → 全部落选
    ok(
        "重建后只保留仍在的勾选（悬浮条随之收起）",
        st.view.page_list.checked_indexes() == []
        and not st.view.page_list.select_bar.isVisibleTo(st.view.page_list),
        str(st.view.page_list.checked_indexes()),
    )
    st.entries = st.view.page_list.entries()
    batches = []
    st.view.pages_batch_delete_requested.connect(lambda: batches.append(1))
    st.entries[0].checkbox.setChecked(True)
    st.view.page_list.select_bar.delete_button.click()
    ok(
        "点悬浮条「批量删除」发批量删除信号",
        batches == [1] and st.view.page_list.checked_indexes() == [0],
        str(batches),
    )
    st.view.page_list.select_bar.clear_button.click()
    ok(
        "点「取消选择」清空勾选、悬浮条收起",
        st.view.page_list.checked_indexes() == []
        and not st.view.page_list.select_bar.isVisibleTo(st.view.page_list),
        str(st.view.page_list.checked_indexes()),
    )
    bar = st.view.page_list.select_bar
    st.entries[0].checkbox.setChecked(True)
    col = st.view.page_list.geometry()  # 页码栏在视图坐标系里的位置
    geo = bar.geometry()
    ok(
        "悬浮框悬在页码栏右缘（浮到右侧画布上，不压底部）",
        geo.x() + geo.width() > col.right() - 12
        and geo.y() + geo.height() < col.bottom(),
        f"bar={geo} col={col}",
    )
    ok(
        "悬浮框垂直居中于页码栏",
        abs(geo.center().y() - col.center().y()) <= 2,
        f"{geo.center().y()} vs {col.center().y()}",
    )
    ok(
        "「批量删除」红底高亮、「取消选择」主色标记",
        "#E02020" in bar.delete_button.styleSheet()
        and "#E6F2F4" in bar.clear_button.styleSheet(),
    )
    # 合成鼠标拖一下：光标全局位置走 mapToGlobal 口径，delta 可预期
    bar.mousePressEvent(st._mouse(QEvent.Type.MouseButtonPress, (5, 5)))
    bar.mouseMoveEvent(st._mouse(QEvent.Type.MouseMove, (5, 65)))
    bar.mouseReleaseEvent(st._mouse(QEvent.Type.MouseButtonRelease, (5, 65)))
    ok(
        "按住可拖动悬浮框（拖过就不再自动摆位）",
        bar._user_moved and bar.geometry().y() == geo.y() + 60,
        str(bar.geometry()),
    )
    bar.clear_button.click()
    ok(
        "拖动后「取消选择」照常清空并收起",
        st.view.page_list.checked_indexes() == []
        and not bar.isVisibleTo(st.view.page_list),
        str(st.view.page_list.checked_indexes()),
    )

    # 拖动排序：按住移动进入拖动态、松手不算单击；落点换算口径（移除后）
    selection = []
    st.view.page_selected.connect(selection.append)
    entry = st.view.page_list.entries()[0]
    entry.mousePressEvent(st._mouse(QEvent.Type.MouseButtonPress, (10, 10)))
    entry.mouseMoveEvent(st._mouse(QEvent.Type.MouseMove, (10, 60)))
    ok("按住上下拖进入拖动态", entry._dragging)
    entry.mouseReleaseEvent(st._mouse(QEvent.Type.MouseButtonRelease, (10, 60)))
    ok("拖动松手不算单击切页", selection == [], str(selection))
    reorders = []
    st.view.page_reorder_requested.connect(lambda a, b: reorders.append((a, b)))
    st.view.page_list._drag_from = 0
    st.view.page_list._drag_drop = 2
    st.view.page_list._finish_drag()
    ok("拖动排序：0 拖到末尾 → (0, 1)", reorders == [(0, 1)], str(reorders))
    st.view.page_list._drag_from = 1
    st.view.page_list._drag_drop = 0
    st.view.page_list._finish_drag()
    ok("拖动排序：1 拖到最前 → (1, 0)", reorders == [(0, 1), (1, 0)], str(reorders))
    st.view.page_list._drag_from = 1
    st.view.page_list._drag_drop = 2  # 落回原位（自己后面一格也是原位）
    st.view.page_list._finish_drag()
    ok("落回原位不发排序信号", len(reorders) == 2, str(reorders))
    st.made2 = S.make_page([st.c, st.d])
    assert st.made2 is not None
    st.view.set_pages([st.made, st.made2], current=0)
    ok(
        "载页后默认不选中",
        st.view.canvas.selected() == -1,
        str(st.view.canvas.selected()),
    )
    st.view.canvas.select(1)
    st.view.set_pages([st.made, st.made2], current=0)
    ok(
        "同页数据回灌不清选中（拖动落盘后的刷新不掉选中态）",
        st.view.canvas.selected() == 1,
        str(st.view.canvas.selected()),
    )
    st.view.set_current(1)
    ok(
        "切到另一页后选中清空",
        st.view.canvas.selected() == -1,
        str(st.view.canvas.selected()),
    )
    st.view.set_pages([st.made, st.made2], current=0)
    pl = st.view.page_list
    live = []
    st.view.page_reorder_requested.connect(lambda a, b: live.append((a, b)))
    drag = pl.entries()[0]
    other = pl.entries()[1]
    y_drag, y_other = drag.y(), other.y()
    # 合成环境没有真实按住的鼠标键，先把轮询架空（否则 _poll_drag
    # 检测到无按键立刻收尾），只验证状态流转本身
    pl._poll_drag = lambda: None
    pl._on_drag_started(0)
    del pl._poll_drag
    ok(
        "拖动开始：本体置灰留原位、幽灵卡跟进（不是本体自己动）",
        drag._dimmed
        and not drag._drag_active
        and pl._ghost is not None
        and pl._ghost is not drag
        and pl._ghost._drag_active
        and pl._flow == [other],
        f"ghost={pl._ghost}",
    )
    ok(
        "清单纹丝不动、无空档（原位置不被空出来）",
        drag.y() == y_drag and other.y() == y_other,
        f"drag.y={drag.y()} vs {y_drag} other.y={other.y()} vs {y_other}",
    )
    ok("落点还在原位 → 指示线藏着", not pl._indicator.isVisible())
    pl._drag_drop = 1
    pl._place_indicator()
    ok(
        "落点变了 → 指示线画在落点条目下缘",
        pl._indicator.isVisible() and pl._indicator.y() > other.y(),
        f"y={pl._indicator.y()} other.y={other.y()}",
    )
    pl._finish_drag()  # 幽灵卡滑进落点的动画启动，动画走完才发信号
    ok("松手瞬间未发信号（先滑进落点）", live == [], str(live))
    ok("落位动画进行中", pl._committing)
    pump(st.ctx.app, times=6, interval=0.05)  # 等落位动画走完（140ms）
    ok("落位完成发信号 (0,1)", live == [(0, 1)], str(live))
    ok(
        "收尾干净：幽灵卡消散、本体回亮、流程态清零",
        not drag._dimmed
        and pl._ghost is None
        and not pl._committing
        and pl._flow == [],
        f"dim={drag._dimmed} ghost={pl._ghost} committing={pl._committing}",
    )

    # 拖回原位：不发信号、无残留
    pl._poll_drag = lambda: None
    pl._on_drag_started(1)
    del pl._poll_drag
    pl._finish_drag()  # drop 仍是原位 → 幽灵卡就地消散，不发信号
    pump(st.ctx.app, times=4, interval=0.05)
    ok(
        "拖回原位不发信号、无残留",
        len(live) == 1
        and pl._ghost is None
        and not pl._committing
        and pl._drag_entry is None
        and not other._dimmed,
        f"live={live} ghost={pl._ghost}",
    )

    st.view.hide()
    st.view.deleteLater()

    st.dialog = ImpositionPickerDialog([st.c, st.d])
    ok(
        "弹窗列出两张候选",
        st.dialog.count() == 2 and st.dialog.cards[0].path.name == "2-r.png",
        f"count={st.dialog.count()}",
    )
    # 「选择图片采用 GRID 模式或者 flex 模式，一行好几个，选框宽一些」
    st.dialog.resize(820, 640)
    st.dialog.show()
    pump(st.ctx.app, times=10)
    ok(
        "卡片网格按宽度自动排成多列（flex 换行）",
        st.dialog.body.columns() >= 3,
        f"列数={st.dialog.body.columns()}",
    )
    ok(
        "卡片够宽够高（≥ 180×240）",
        st.dialog.cards[0].width() >= 180 and st.dialog.cards[0].height() >= 240,
        f"{st.dialog.cards[0].width()}x{st.dialog.cards[0].height()}",
    )
    ok("弹窗够宽（≥ 760px）", st.dialog.width() >= 760, str(st.dialog.width()))
    # 用户截图报过「图片没有正常显示、也没有文字」：缩略图必须是**固定尺寸**
    # 且真的画进了内容（不是空白小条），名字标签必须有文字。
    pump(st.ctx.app, times=20)
    card = st.dialog.cards[0]
    ok(
        "缩略图是固定尺寸的图（不是一小条）",
        card.thumb.size() == QSize(THUMB_W, THUMB_H),
        f"{card.thumb.size()}",
    )
    ok(
        "缩略图真的画上了内容（不是全白/空图）",
        card._pixmap.width() == THUMB_W
        and card._pixmap.height() == THUMB_H
        and _count_non_white(card._pixmap.toImage()) > 0,
        f"pixmap={card._pixmap.size()} 非白像素={_count_non_white(card._pixmap.toImage())}",
    )
    ok(
        "卡片有名字文字（用户报过『没有显示文字』）",
        card.name.text() == "2-r.png".removesuffix(".png")
        and not card.name.isHidden(),
        f"{card.name.text()!r}",
    )
    ok("没勾选时「开始拼版」不可点", not st.dialog.ok_button.isEnabled())
    # 「只有三种可选形态」（用户 2026-09-30）：1 张单独成页 / 2 张拼一页 /
    # 1 张半幅 + 自动拼版
    st.dialog.cards[0].toggle()
    ok(
        "只勾 1 张：「开始拼版」可点（单张单独成页），提示单独成一页",
        st.dialog.ok_button.isEnabled() and "单独成一页" in st.dialog.status.text(),
        st.dialog.status.text(),
    )
    st.dialog.cards[1].toggle()
    ok(
        "勾满两张：「开始拼版」可点，提示拼成一页",
        st.dialog.ok_button.isEnabled() and "拼成一页" in st.dialog.status.text(),
        st.dialog.status.text(),
    )
    ok(
        "点卡片即可勾选（整张卡片都是热区）",
        st.dialog.cards[0].is_checked() and st.dialog.cards[1].is_checked(),
    )
    ok(
        "勾选结果按**源清单顺序**返回（不是点击顺序）",
        _names(st.dialog.picked_files()) == ["2-r.png", "2-l.png"],
        str(_names(st.dialog.picked_files())),
    )
    st.dialog.cards[0].toggle()
    ok(
        "取消勾选回到 1 张 → 仍可点（单张单独成页）",
        not st.dialog.cards[0].is_checked() and st.dialog.ok_button.isEnabled(),
    )
    st.dialog.cards[1].toggle()
    ok(
        "两张都取消 → 「开始拼版」变灰",
        not st.dialog.cards[1].is_checked() and not st.dialog.ok_button.isEnabled(),
    )
    st.dialog.cards[0].toggle()
    ok("勾中的卡片进入选中态（浅底 + 对勾）", st.dialog.cards[0].is_checked())

