# -*- coding: utf-8 -*-
"""缩略图条**滚轮步长**自测：一格滚轮 = 5 个条目。

起因是用户反馈：「缩略图滚动一次翻动十几页太快了，我觉得 5 页比较好」。
根因是 QListView 在 IconMode 下按滚动条 ``singleStep`` / 系统"每次滚动行数"
推步长（``ThumbStrip`` 原本没有自己的 wheelEvent），一格翻 3 个条目、系统
行数设大或条目矮时就更夸张。

断言线（都不看实现细节，只看"翻了几条"）：

1. 一格滚轮（120）恰好翻 ``WHEEL_STEP_ITEMS`` 个条目，**连滚两格是 10**；
2. 条目**高矮不一**时步长不变（逐条 sizeHint 累计，不能按 singleStep 推）；
3. 一格的**反方向**退回同样条数；
4. 触控板/高分辨率滚轮的小 delta（40+40+40）攒够一格才翻一次，不会连翻；
5. 两端夹住：滚到底不会越界，回滚能回到第一条。
"""

from __future__ import annotations

NAME = "thumb_wheel"
DEPENDS: list[str] = []
TITLE = "缩略图滚轮步长"


def run(ctx) -> None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from desktop.components.viewers.thumb_strip import ThumbStrip
    from tests.selftests._context import ok

    app = ctx.app
    host = QWidget()
    host.resize(180, 600)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    strip = ThumbStrip()
    layout.addWidget(strip)
    host.show()
    app.processEvents()

    count = 40
    for index in range(count):
        strip.add_page_item(str(index + 1), f"/x/{index + 1}.jpg")
        # ⚠️ 故意做成**高矮不一**：按 singleStep 推步长的实现会在这里露馅
        strip.item(index).setSizeHint(
            strip._item_hint(156 if index % 3 else 56)
        )
    strip.scheduleDelayedItemsLayout()
    for _ in range(6):
        app.processEvents()

    def first_row() -> int:
        """真实可见的最上面一条（用 visualItemRect 独立观测，不走被测的换算）。"""
        for row in range(strip.count()):
            if strip.visualItemRect(strip.item(row)).bottom() > 0:
                return row
        return -1

    def notch(dy: int) -> None:
        pos = QPointF(strip.viewport().width() / 2, strip.viewport().height() / 2)
        app.sendEvent(
            strip.viewport(),
            QWheelEvent(
                pos, strip.viewport().mapToGlobal(pos.toPoint()),
                QPoint(0, 0), QPoint(0, dy),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate, False,
            ),
        )
        for _ in range(2):
            app.processEvents()

    try:
        step = ThumbStrip.WHEEL_STEP_ITEMS
        ok("起始停在第一条", first_row() == 0, f"first={first_row()}")

        # ---- 1. 一格 5 条，连滚两格 10 条 ----
        notch(-120)
        ok(f"一格滚轮翻 {step} 个条目", first_row() == step, f"first={first_row()}")
        notch(-120)
        ok(f"连滚两格翻 {2 * step} 个条目", first_row() == 2 * step, f"first={first_row()}")

        # ---- 3. 反方向同样条数 ----
        notch(120)
        ok(f"回滚一格退回 {step} 个条目", first_row() == step, f"first={first_row()}")

        # ---- 4. 小 delta 攒够一格才翻（触控板）----
        base = first_row()
        notch(-40)
        notch(-40)
        ok("不足一格的 delta 不翻页", first_row() == base, f"first={first_row()}")
        notch(-40)
        ok(f"攒满一格才翻（{base} → {base + step}）",
           first_row() == base + step, f"first={first_row()}")

        # ---- 5. 两端夹住 ----
        for _ in range(20):
            notch(-120)
        bottom = first_row()
        last = strip.item(count - 1)
        ok("滚到底时最后一条可见", strip.visualItemRect(last).top() < strip.viewport().height(),
           f"first={bottom} last_rect={strip.visualItemRect(last)}")
        for _ in range(3):
            notch(-120)
        ok("到底后再滚不再移动（不越界）", first_row() == bottom, f"first={first_row()}")
        for _ in range(30):
            notch(120)
        ok("回滚到顶停在第一条", first_row() == 0, f"first={first_row()}")
        for _ in range(3):
            notch(120)
        ok("到顶后再滚不再移动", first_row() == 0, f"first={first_row()}")
    finally:
        strip.deleteLater()
        host.deleteLater()
