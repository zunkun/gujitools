# -*- coding: utf-8 -*-
"""执行日志浮层的 × 必须**真的点得动**（z 序/遮挡问题）。

背景（2026-10-16 用户报障）
    任务详情页底部「执行日志」浮层右上角的 × 点不动、关不掉。
    代码链本身没问题（``close_button.clicked → set_expanded(False) → overlay.hide()``），
    问题在**命中**：浮层是详情页的**子控件**，而页面里随时会有别的兄弟控件被
    ``show()/raise_()`` 抬到它上面（预览卡刷新、懒加载面板构造、hover 时被
    raise_ 的工具列、透明遮罩……）。浮层被压下去后，× 那块地方**画得出来、
    点击却落在压它的控件上**；更糟的是原来判"点在不在浮层里"只看几何
    （``rect().contains``），于是这段点击既到不了 ×、又因为"几何上在浮层里"而
    触发不了"点浮层外收起"的兜底 ⇒ 用户看到的就是"点了没反应"。

本模块的契约
    1. **走真实命中链**点 ×（先算出该点最上层的控件，再往它发点击——离屏环境
       下 QTest 只是"把事件发给指定控件"，不自己做命中测试）；
    2. 浮层**被兄弟控件压住**时，点那块区域要按"点在浮层外"**收起**，而不是
       无声吞掉；
    3. 日志每刷一行都要把浮层**摁回最上层**，运行期不会再被压住。
"""

NAME = "log_overlay"
DEPENDS: list[str] = []
TITLE = "执行日志浮层 × 的命中（z 序/遮挡）"

#: 迷你宿主的尺寸与状态条高度（和详情页一个量级，几何断言才有意义）
HOST_W, HOST_H = 900, 600
BAR_H = 34


def run(ctx) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget

    from desktop.components.log_panel import BAR_HEIGHT, LogPanel
    from tests.selftests._context import ok, pump

    app = ctx.app

    host = QWidget()
    host.setFixedSize(HOST_W, HOST_H)
    panel = LogPanel(host)
    panel.setGeometry(0, HOST_H - BAR_H, HOST_W, BAR_HEIGHT)
    panel.log_view.append("detect 31 页 ...")
    host.show()
    pump(app, times=6)

    overlay = panel._overlay
    button = overlay.close_button

    def press_through_chain() -> str:
        """**按真实命中链**把左键点击发给"该点最上层的控件"，返回它是谁。

        离屏下 ``QTest.mouseClick(控件)`` 是直接发给该控件、不做命中测试——所以
        这里自己走一遍 :meth:`childAt`，模拟窗口系统"把点击给最上层控件"的路由。
        """
        centre = button.mapToGlobal(button.rect().center())
        target = host
        while True:
            child = target.childAt(target.mapFromGlobal(centre))
            if child is None:
                break
            target = child
        QTest.mouseClick(
            target, Qt.MouseButton.LeftButton,
            pos=target.mapFromGlobal(centre),
        )
        return type(target).__name__

    # ---- 1. 正常：× 在最上层，点得动 ----
    panel.set_expanded(True)
    pump(app, times=6)
    ok("展开后浮层确实显示出来", panel._expanded and overlay.isVisible(),
       f"expanded={panel._expanded} visible={overlay.isVisible()}")
    hit = host.childAt(host.mapFromGlobal(button.mapToGlobal(button.rect().center())))
    ok("× 处在最上层（没被兄弟控件挡住）", hit is button,
       f"该点最上层={type(hit).__name__ if hit is not None else None}")
    ok("点 ×（走真实命中链）能收起浮层",
       press_through_chain() == "ToolButton"
       and not panel._expanded and not overlay.isVisible(),
       f"expanded={panel._expanded} visible={overlay.isVisible()}")

    # ---- 2. 被兄弟控件压住：几何还在浮层里，但命中已不在 ----
    panel.set_expanded(True)
    pump(app, times=6)
    blocker = QWidget(host)                 # 模拟"运行期被抬上来的兄弟控件"
    blocker.setGeometry(0, 0, HOST_W, HOST_H)
    blocker.show()
    blocker.raise_()
    pump(app, times=6)
    centre = button.mapToGlobal(button.rect().center())
    ok("被压住时：几何仍算在浮层内，但 **z 序**判定为未命中（这就是 × 点不动的根因）",
       LogPanel._hit(overlay, centre) and not LogPanel._overlay_hit(overlay, centre),
       f"几何={LogPanel._hit(overlay, centre)} "
       f"z序={LogPanel._overlay_hit(overlay, centre)}")
    ok("被压住时点那块区域：按「点在浮层外」**收起**，而不是无声吞掉",
       press_through_chain() == "QWidget" and not panel._expanded,
       f"expanded={panel._expanded}")

    # ---- 3. 日志每刷一行就把浮层摁回最上层（运行期不会再被压住）----
    panel.set_expanded(True)
    pump(app, times=6)
    blocker.raise_()                        # 又被抬上来
    pump(app, times=4)
    ok("先模拟被抬起：此刻确实被压住",
       not LogPanel._overlay_hit(overlay, centre), "")
    panel.log_view.append("detect 32 页 ...")   # 日志来一行
    pump(app, times=6)
    ok("日志刷一行 → 浮层被摁回最上层（× 重新点得动）",
       LogPanel._overlay_hit(overlay, centre)
       and host.childAt(host.mapFromGlobal(centre)) is button,
       f"z序={LogPanel._overlay_hit(overlay, centre)}")
    ok("摁回最上层后，点 × 正常收起", press_through_chain() == "ToolButton"
       and not panel._expanded, f"expanded={panel._expanded}")

    # ---- 4. Esc 兜底（不依赖命中）----
    panel.set_expanded(True)
    pump(app, times=4)
    QTest.keyClick(host, Qt.Key.Key_Escape)
    pump(app, times=4)
    ok("Esc 也能收起（不依赖命中，用户兜底手段）", not panel._expanded, "")

    # ---- 5. 点状态条仍能开关（这条走 LogPanel.mouseReleaseEvent）----
    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=panel.rect().center())
    pump(app, times=4)
    ok("点状态条空白处：展开", panel._expanded, "")
    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=panel.rect().center())
    pump(app, times=4)
    ok("再点一次：收起", not panel._expanded, "")
