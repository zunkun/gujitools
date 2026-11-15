# -*- coding: utf-8 -*-
"""拼版页键盘翻页（用户 2026-11-15）。

> 图片拼版页面，可以通过上下左右键切换上一页下一页

守护五件事：

1. **键位**：← / ↑ 上一页、→ / ↓ 下一页；其它键一概不动（`page_step_for_key`
   是唯一映射）；
2. **边界**：首页按 ← 、末页按 → **不循环**，且越界时**不消费按键**
   （`event.isAccepted()` 为假 → 交上层，详情页的 ←/→ 切步骤还能用）；
3. **快捷键**：注册 4 个 ``QShortcut``，作用域必须是**子树级**
   （``WidgetWithChildrenShortcut``）——窗口级会把别处输入框的方向键一起吞掉；
4. **同一路径**：键盘 / 翻页按钮 / ``navigate()`` 都走 ``_step_page``
   （切页 + 发 ``page_selected``），翻页前先 ``flush_pending``；
5. **能收到按键**：视图与画布都是 ``ClickFocus``（点了画布按键才进得来）。

⚠️ **DEPENDS 为空、自建控件**（与 ``module_imposition_page`` 同款）：页数据
**全虚拟**（`page_source_stems` 只取文件名，不需要真图），因此不 show 也不解码。
"""

from __future__ import annotations

NAME = "imposition_keynav"
DEPENDS: list[str] = []
TITLE = "拼版页键盘翻页（←/↑ 上一页 · →/↓ 下一页）"


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_keys(ctx, ok)
    _check_shortcuts(ctx, ok)


# ------------------------------------------------------------------ 工具
def _page(*stems: str) -> dict:
    """一页拼版（**虚拟**：只要文件名与 rect，不读盘）。"""
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


def _view(pages: int = 3):
    """建一个三页的拼版视图（当前在第一页）。"""
    from desktop.components.imposition.view import ImpositionViewWidget

    view = ImpositionViewWidget()
    view.set_pages(
        [_page(f"{i}-r", f"{i}-l") for i in range(1, pages + 1)], current=0,
    )
    return view


def _press(widget, key) -> object:
    """把一个 KeyPress 直接投给控件，返回事件本体（好判 ``isAccepted``）。

    ⚠️ 不用 ``QTest.keyClick``：它会走平台层的按键投递（offscreen 下与
    ShortcutOverride 的交互不稳定），这里要的是**确定**地落在
    ``keyPressEvent`` 上。
    """
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    event = QKeyEvent(
        QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(widget, event)
    return event


def _shortcut(view, key):
    """按 QKeySequence 找出视图上注册的那条快捷键（找不到返回 None）。"""
    from PySide6.QtGui import QKeySequence, QShortcut

    target = QKeySequence(key)
    for shortcut in view.findChildren(QShortcut):
        if shortcut.key() == target:
            return shortcut
    return None


def _pump(ctx, times: int = 2) -> None:
    """跑几拍事件循环，让 deleteLater 真的生效。"""
    from tests.selftests._context import pump

    pump(ctx.app, times=times)


# ------------------------------------------------------------------ 用例
def _check_keys(ctx, ok) -> None:
    """键位映射 + 边界 + 不消费越界按键 + 翻页前 flush。"""
    from PySide6.QtCore import Qt

    view = _view(3)
    try:
        ok(
            "拼版页键盘：视图与画布都是「点击即聚焦」（按键才进得了这棵子树）",
            view.focusPolicy() == Qt.FocusPolicy.ClickFocus
            and view.canvas.focusPolicy() == Qt.FocusPolicy.ClickFocus,
            f"view={view.focusPolicy()} canvas={view.canvas.focusPolicy()}",
        )

        seen: list[int] = []
        view.page_selected.connect(seen.append)

        _press(view, Qt.Key.Key_Right)
        ok(
            "拼版页键盘：→ 翻到下一页",
            view.current_index() == 1 and seen == [1],
            f"current={view.current_index()} seen={seen}",
        )
        _press(view, Qt.Key.Key_Down)
        ok(
            "拼版页键盘：↓ 同样翻到下一页",
            view.current_index() == 2 and seen == [1, 2],
            f"current={view.current_index()} seen={seen}",
        )

        # 末页按 →：不循环、也不吃掉这次按键（上层还有 ←/→ 的路由）
        event = _press(view, Qt.Key.Key_Right)
        ok(
            "拼版页键盘：末页按 → 不越界（不循环回首页）",
            view.current_index() == 2 and seen == [1, 2],
            f"current={view.current_index()} seen={seen}",
        )
        ok(
            "拼版页键盘：末页越界的那次按键不被消费（交上层继续处理）",
            not event.isAccepted(),
            f"accepted={event.isAccepted()}",
        )

        _press(view, Qt.Key.Key_Left)
        ok(
            "拼版页键盘：← 翻回上一页",
            view.current_index() == 1 and seen[-1] == 1,
            f"current={view.current_index()} seen={seen}",
        )
        _press(view, Qt.Key.Key_Up)
        ok(
            "拼版页键盘：↑ 同样翻回上一页",
            view.current_index() == 0 and seen[-1] == 0,
            f"current={view.current_index()} seen={seen}",
        )
        event = _press(view, Qt.Key.Key_Left)
        ok(
            "拼版页键盘：首页按 ← 不越界（不循环到末页）",
            view.current_index() == 0 and not event.isAccepted(),
            f"current={view.current_index()} accepted={event.isAccepted()}",
        )

        # 非方向键：一个字都不能动
        _press(view, Qt.Key.Key_A)
        _press(view, Qt.Key.Key_PageDown)
        ok(
            "拼版页键盘：非方向键不翻页（A / PageDown 无效）",
            view.current_index() == 0,
            f"current={view.current_index()}",
        )

        # 翻页前先 flush：拖住图没松手就按键，这一下改动不能丢
        calls: list[int] = []
        view.canvas.flush_pending = lambda: calls.append(1)
        try:
            _press(view, Qt.Key.Key_Right)
        finally:
            del view.canvas.flush_pending
        ok(
            "拼版页键盘：翻页前先 flush_pending（拖住的改动不丢）",
            calls == [1] and view.current_index() == 1,
            f"calls={len(calls)} current={view.current_index()}",
        )
        view.page_selected.disconnect(seen.append)
    finally:
        view.deleteLater()
        _pump(ctx)


def _check_shortcuts(ctx, ok) -> None:
    """快捷键：数量/作用域/激活效果；navigate 与按钮同一条路径；提示文案。"""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QShortcut

    view = _view(3)
    try:
        shortcuts = view.findChildren(QShortcut)
        ok(
            "拼版页键盘：注册了 4 个方向键快捷键（← ↑ → ↓）",
            len(shortcuts) == 4,
            f"[{', '.join(s.key().toString() for s in shortcuts)}]",
        )
        ok(
            "拼版页键盘：快捷键是**子树级**作用域（不吞别处输入框的方向键）",
            all(
                s.context() == Qt.ShortcutContext.WidgetWithChildrenShortcut
                for s in shortcuts
            ),
            f"{[s.context() for s in shortcuts]}",
        )
        ok(
            "拼版页键盘：快捷键默认允许长按连翻（autoRepeat）",
            all(s.autoRepeat() for s in shortcuts),
        )

        seen: list[int] = []
        view.page_selected.connect(seen.append)
        for key, want in (
            (Qt.Key.Key_Right, 1),
            (Qt.Key.Key_Down, 2),
            (Qt.Key.Key_Left, 1),
            (Qt.Key.Key_Up, 0),
        ):
            shortcut = _shortcut(view, key)
            assert shortcut is not None, f"缺少 {key} 的快捷键"
            shortcut.activated.emit()
            ok(
                f"拼版页键盘：快捷键 {shortcut.key().toString()} 与点翻页按钮同路径",
                view.current_index() == want and seen[-1] == want,
                f"current={view.current_index()} seen={seen}",
            )

        # navigate()：详情页 ←/→ 转发的入口（返回"是否真的切了"）
        ok(
            "拼版页键盘：navigate(True) 切下一页、返回 True",
            view.navigate(True) is True and view.current_index() == 1,
            f"current={view.current_index()}",
        )
        view.set_current(2)
        ok(
            "拼版页键盘：末页 navigate(True) 返回 False（上层据此决定接管）",
            view.navigate(True) is False and view.current_index() == 2,
            f"current={view.current_index()}",
        )
        ok(
            "拼版页键盘：navigate(False) 切上一页",
            view.navigate(False) is True and view.current_index() == 1,
            f"current={view.current_index()}",
        )
        view.page_selected.disconnect(seen.append)

        ok(
            "拼版页键盘：提示条写明了键位（←/↑ 上一页 · →/↓ 下一页）",
            "←/↑ 上一页" in view.hint.text()
            and "→/↓ 下一页" in view.hint.text(),
            view.hint.text()[:60],
        )
        ok(
            "拼版页键盘：翻页按钮的悬停提示带上键位",
            "← / ↑" in view.prev_button.toolTip()
            and "→ / ↓" in view.next_button.toolTip(),
            f"{view.prev_button.toolTip()} / {view.next_button.toolTip()}",
        )
    finally:
        view.deleteLater()
        _pump(ctx)
