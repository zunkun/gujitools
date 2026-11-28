# -*- coding: utf-8 -*-
"""盯住「主线程还活着、输入却被吞掉」的那一类假死。

为什么需要它（用户 2026-11-28「页面卡顿，python 也没有反应」）：
``utils.crash_log`` 的卡顿看门狗只能发现**主线程不转**。但实测到的另一种
假死是主线程照常转——心跳正常、单实例探活 10ms 应答、定时器照跑——用户却
点哪儿都没反应，日志里一个字都没有。这种场面**在 Python 栈上什么也看不到**：
执行权停在 Qt 的 C++ 事件循环里，从 Python 侧看就是"空闲"。

真正能被观测的是 Qt 自己的输入状态：

* ``QApplication.activeModalWidget()``：有模态窗在吃输入。最阴的一类是
  **它没能显示出来**（``isVisible()`` 为假，或几何落在所有屏幕之外）——
  用户看到的是"点了没反应"，而进程一切正常；
* ``activePopupWidget`` / ``mouseGrabber`` / ``keyboardGrabber``：谁攥着输入；
* **最后一次真实输入事件的时间**：有它才能区分两种完全不同的病因——
  「事件根本没送到进程」（窗口/合成器层）与「送到了被模态层吃掉」（Qt 层）。

⚠️ 只读快照，不改任何界面行为；写日志走 ``utils.crash_log.log``，同一状态
只报一次（状态变化或恢复时才再写），不会刷屏。
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

#: 判定"输入被占"的静置时长：模态窗正常用十几秒很常见，短了会误报。
QUIET_S = 45.0

#: 探针自查心跳（证明它自己没死），间隔够长以免污染日志。
ALIVE_EVERY_S = 1800.0

_INPUT_TYPES = frozenset({
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease,
    QEvent.Type.MouseButtonDblClick,
    QEvent.Type.KeyPress,
    QEvent.Type.Wheel,
    QEvent.Type.TouchBegin,
})

_KIND_NAMES = {
    QEvent.Type.MouseButtonPress: "鼠标按下",
    QEvent.Type.MouseButtonRelease: "鼠标松开",
    QEvent.Type.MouseButtonDblClick: "鼠标双击",
    QEvent.Type.KeyPress: "按键",
    QEvent.Type.Wheel: "滚轮",
    QEvent.Type.TouchBegin: "触摸",
}


def _name(widget) -> str:  # noqa: ANN001 - None/QWidget 都可能
    if widget is None:
        return "None"
    try:
        cls = type(widget).__name__
        title = widget.windowTitle() or ""
        return f"{cls}「{title}」" if title else cls
    except Exception:  # noqa: BLE001 - 对象可能已在析构
        return "?"


def _geom_text(widget) -> str:  # noqa: ANN001
    try:
        g = widget.frameGeometry()
        return f"{g.width()}x{g.height()}@{g.x()},{g.y()}"
    except Exception:  # noqa: BLE001
        return "?"


def _on_any_screen(widget) -> bool:  # noqa: ANN001
    """窗口还在不在某块屏幕的可见范围内（被挪出屏外同样点不到）。"""
    try:
        geo = widget.frameGeometry()
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(geo):
                return True
        return False
    except Exception:  # noqa: BLE001
        return True  # 判不了就别误报


class InputWatch(QObject):
    """每 ``poll_ms`` 快照一次输入占用状态，异常写 ``[input]`` 日志。"""

    def __init__(self, app: QApplication, poll_ms: int = 1000) -> None:
        super().__init__(app)
        self._app = app
        self._poll_ms = max(200, int(poll_ms))
        self._last_input = time.monotonic()
        self._last_kind = "（本次会话还没有输入）"
        self._last_report: tuple[str, str] | None = None
        self._last_label = ""
        self._last_alive = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ 接口
    def start(self) -> "InputWatch":
        self._app.installEventFilter(self)
        self._timer.start()
        return self

    def stop(self) -> None:
        self._timer.stop()
        try:
            self._app.removeEventFilter(self)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 事件过滤
    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001 - Qt 签名
        try:
            if event.type() in _INPUT_TYPES:
                self._last_input = time.monotonic()
                self._last_kind = _KIND_NAMES.get(event.type(), str(event.type()))
        except Exception:  # noqa: BLE001 - 过滤器里绝不能抛
            pass
        return False  # 只看不拦

    # ---------------------------------------------------------------- 内部
    def _tick(self) -> None:
        try:
            self._check()
        except Exception:  # noqa: BLE001 - 监护自己不该拖垮界面
            pass

    def _check(self) -> None:
        from utils.crash_log import log

        now = time.monotonic()
        idle = now - self._last_input
        modal = QApplication.activeModalWidget()
        popup = QApplication.activePopupWidget()
        mouse_grab = QWidget.mouseGrabber()
        kbd_grab = QWidget.keyboardGrabber()
        holder = modal or popup or mouse_grab or kbd_grab

        problem: str | None = None
        #: 状态签名（不含"已 N 秒"这类每跳都变的量），用来去重
        key: tuple[str, str] | None = None
        if modal is not None and not modal.isVisible():
            # 最可疑：模态在吃输入，却没显示出来。
            problem = (f"**不可见**的模态窗 {_name(modal)}"
                       f"（geom={_geom_text(modal)}）")
            key = ("invisible_modal", type(modal).__name__)
        elif modal is not None and not _on_any_screen(modal):
            problem = (f"模态窗在屏幕可见范围之外 {_name(modal)}"
                       f"（geom={_geom_text(modal)}）")
            key = ("offscreen_modal", type(modal).__name__)
        elif holder is not None and idle >= QUIET_S:
            problem = (f"{_name(holder)} 占着输入已 {idle:.0f}s"
                       f"（可见={holder.isVisible()}）")
            key = ("holder", type(holder).__name__)

        if problem is None:
            if self._last_report is not None:
                log(f"[input] 输入占用已恢复（此前：{self._last_label}）")
                self._last_report = None
                self._last_label = ""
            elif now - self._last_alive >= ALIVE_EVERY_S:
                self._last_alive = now
                log(f"[input] 输入探针在跑：最近输入＝{self._last_kind}"
                    f"（{idle:.0f}s 前），无占用")
            return

        # 同一状态只报一次；状态变了（换了个窗口/变成另一种问题）再报。
        if key == self._last_report:
            return
        first = self._last_report is None
        self._last_report = key
        self._last_label = problem
        detail = (
            f"[input] ⚠️ 主线程在转，但输入被占：{problem}；"
            f"最近一次输入＝{self._last_kind}（{idle:.0f}s 前）；"
            f"modal={_name(modal)}, popup={_name(popup)}, "
            f"mouseGrabber={_name(mouse_grab)}, "
            f"keyboardGrabber={_name(kbd_grab)}"
        )
        log(detail)
        if not first:
            return  # 只是"换了个占输入的窗口"，栈没必要再抓一遍
        # 顺手把所有线程的栈钉进日志：这类现场只看 Qt 状态还不够，
        # 得知道是哪个 Python 调用把模态开起来的。
        try:
            from utils.crash_log import dump_stacks

            dump_stacks("[input] 输入被占时的线程栈")
        except Exception:  # noqa: BLE001
            pass


def install(app: QApplication, poll_ms: int = 1000) -> InputWatch:
    """装上（幂等：已装则复用）。"""
    existing = getattr(app, "_input_watch", None)
    if isinstance(existing, InputWatch):
        existing.start()
        return existing
    watch = InputWatch(app, poll_ms).start()
    setattr(app, "_input_watch", watch)
    return watch
