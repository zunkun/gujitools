# -*- coding: utf-8 -*-
"""窗口尺寸适配：把「默认尺寸」夹进当前屏幕的可用区域，并摆到合适位置。

背景（2026-10-01 用户报障「不最大化就显示不完整 / 被任务栏遮挡」）：
窗口尺寸一直是**逻辑像素的固定值**（主窗口 1440×920），既不看屏幕、也不看
系统缩放。实测这台机器 1920×1080 @125% → 逻辑屏 1536×864，减去任务栏后
**可用高度只有 824**：920 > 824，窗口底部（日志状态条、第四步按钮）永远
压在任务栏后面，非最大化下够不着。1366×768 或 150%/175% 缩放的机器更紧，
可用区域甚至**小于窗口的最小尺寸**——那种情况下用户连拖小都做不到。

规则（**只夹不涨**，屏幕够大时与改动前逐像素一致）：

1. 期望宽高先扣掉**窗口边框预留**（标题栏那 30 逻辑像素不算在客户端尺寸里，
   不扣就会出现"客户端刚好等于屏幕、却仍被标题栏顶出去"），再各夹到可用区域的
   :data:`FIT_RATIO`；
2. 最小宽高**跟着夹**——否则"可用高 672 < 最小高 720"时窗口被卡死，
   用户没有任何办法把它缩进屏幕；
3. 位置也一并摆好：有可见父窗口的弹窗居中到父窗口（Qt 的默认观感，这里
   显式写出来才夹得住），顶层窗口居中到屏幕可用区域；居中与夹紧都按**含边框**
   的外框尺寸算，最后再把外框夹回可用区域，免得 1440 宽的窗口在 1536 宽的屏
   上被系统摆出半截。

⚠️ 两个必须守住的边界：

- **只在构造那一刻算一次**，不做持续约束（不装事件过滤器、不重写
  ``resizeEvent``）。自测与截图脚本会显式 ``resize()`` 到指定尺寸
  （``tests/gui_shot.py``、``tests/selftests/_context.py``），持续夹紧会让
  它们拿到别的尺寸，护栏随即失真。
- 拿不到屏幕信息时**原样返回、不做任何猜测**：宁可维持旧行为，也不要凭空
  给一个尺寸（离屏/无头环境下 ``primaryScreen()`` 可能为空）。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize

#: 窗口最多占可用区域的这个比例，四周留出呼吸空间（阴影、贴边不好看）。
FIT_RATIO = 0.95

#: 窗口边框预留（宽, 高，逻辑像素）。客户端尺寸**不含**标题栏：实测这台机器
#: 125% 缩放下客户端 782 高的窗口 ``frameGeometry`` 是 812（标题栏 30 逻辑
#: 像素 = 物理 39），100% 与更高缩放下量级相同。不预留的话，"客户端尺寸刚好
#: 等于可用区域"仍会被标题栏顶出屏幕；宽度在 Win10/11 实测为 0，留 16 只是
#: 为了兼容有可见边框的主题。
FRAME_ALLOWANCE = QSize(16, 32)


def _screen_for(reference=None):
    """取参考控件所在的屏幕；拿不到就退回主屏（可能为 None）。

    优先级：自己的 ``windowHandle``（已显示的窗口） → **可见父窗口**的句柄
    （弹窗的常见情形：父窗口早就显示了，而自己还是"没上屏"的状态） →
    按自身几何中心 ``screenAt`` → 主屏。多显示器下这几步决定了弹窗落在
    用户眼前那块屏上，而不是永远跑到主屏去。
    """
    from PySide6.QtGui import QGuiApplication

    if reference is None:
        return QGuiApplication.primaryScreen()

    candidates = []
    try:
        candidates.append(reference)
        parent = reference.parentWidget()
        if parent is not None:
            candidates.append(parent)
    except AttributeError:
        pass  # 传进来的不是 QWidget（比如直接传了 screen），忽略

    for widget in candidates:
        try:
            handle = widget.windowHandle()
        except RuntimeError:
            continue  # 底层 C++ 对象已销毁
        if handle is not None and handle.screen() is not None:
            return handle.screen()

    try:
        screen = QGuiApplication.screenAt(reference.frameGeometry().center())
    except (AttributeError, RuntimeError):
        screen = None
    return screen or QGuiApplication.primaryScreen()


def available_area(reference=None) -> QRect | None:
    """参考控件所在屏幕的**可用区域**（已扣除任务栏）；拿不到返回 None。"""
    screen = _screen_for(reference)
    return screen.availableGeometry() if screen is not None else None


def fit_sizes(preferred: QSize, minimum: QSize | None,
              area: QRect | None) -> tuple[QSize, QSize | None]:
    """把期望尺寸与最小尺寸夹进 ``area``，返回 (客户端尺寸, 最小尺寸)。

    纯函数（不碰 Qt 控件），便于直接断言边界；``area`` 为空时原样返回。
    """
    if area is None or area.isEmpty():
        return preferred, minimum

    cap_w = max(1, int((area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
    cap_h = max(1, int((area.height() - FRAME_ALLOWANCE.height()) * FIT_RATIO))
    size = QSize(min(preferred.width(), cap_w), min(preferred.height(), cap_h))
    if minimum is None:
        return size, None
    fit_min = QSize(
        min(minimum.width(), size.width()),
        min(minimum.height(), size.height()),
    )
    return size, fit_min


def _anchor_rect(window, area: QRect) -> QRect:
    """居中参照物：可见父窗口的屏幕矩形；没有父窗口就用屏幕可用区域。"""
    try:
        parent = window.parentWidget()
    except AttributeError:
        parent = None
    if parent is not None and parent.isVisible():
        rect = parent.frameGeometry()
        if not rect.isEmpty():
            return rect
    return area


def apply_window_size(window, preferred: QSize, minimum: QSize | None = None) -> QSize:
    """把 ``window`` 设成「期望尺寸夹进屏幕可用区域」的样子，返回最终尺寸。

    调用点全是各窗口 ``__init__`` 里原本写 ``resize()`` / ``setMinimumSize()``
    的位置，一行换一行。
    """
    area = available_area(window)
    size, min_size = fit_sizes(preferred, minimum, area)
    if min_size is not None:
        window.setMinimumSize(min_size)
    window.resize(size)

    if area is None or area.isEmpty():
        return size

    anchor = _anchor_rect(window, area)
    # ⚠️ 居中与夹紧都要按**含标题栏的外框**算：``move()`` 在 Windows 上定的是
    # 外框左上角（实测），只按客户端尺寸居中会整体偏下半个标题栏高度。
    frame_h = size.height() + FRAME_ALLOWANCE.height()
    x = anchor.center().x() - size.width() // 2
    y = anchor.center().y() - frame_h // 2
    # 夹回可用区域：布局的最小尺寸可能仍然大于窗口尺寸（那时 x/y 落到边界上，
    # 不做二次夹紧的话窗口会跑到屏幕外面去）
    x = max(area.left(), min(x, area.right() + 1 - size.width()))
    y = max(area.top(), min(y, area.bottom() + 1 - frame_h))
    window.move(x, y)
    return size
