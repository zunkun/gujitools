# -*- coding: utf-8 -*-
"""窗口尺寸适配：默认尺寸夹进屏幕可用区域、最小尺寸跟着夹、外框不越界。

来源（2026-10-01 用户报障）：「不最大化就显示不完整 / 被任务栏遮挡」。
根因是窗口尺寸一直是**逻辑像素的固定值**：主窗口 1440×920，而 1920×1080
@125% 的机器逻辑屏只有 1536×864、减掉任务栏的可用高只剩 824 —— 920 > 824，
窗口底部（日志状态条、第四步按钮）永远压在任务栏后面；而 "最小 1080×720"
在更高缩放（150% → 可用 1280×680）下比可用区域还大，用户连拖小都做不到。

本模块同时守两条线：

- **纯函数边界**：``fit_sizes`` 在不同可用区域下的精确结果（含极窄屏、
  拿不到屏幕信息两种退化情形）；
- **真窗口**：真的把主窗口/编辑弹窗建出来，断言"含标题栏的外框"完全落在
  屏幕可用区域内 —— 只断言客户端尺寸会漏掉标题栏那 30 逻辑像素。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize

from tests.selftests._context import ok

NAME = "window_size"
TITLE = "窗口尺寸适配"
DEPENDS: tuple[str, ...] = ()
TEARDOWN = False

#: 用户真实机器：1920×1080 @125%，逻辑可用区 1536×824。
#: 这是本次报障的现场，作为固定用例钉在护栏里。
USER_SCREEN_AREA = QRect(0, 0, 1536, 824)


def run(ctx) -> None:
    from desktop.app import WINDOW_MIN_SIZE, WINDOW_SIZE, MainWindow
    from desktop.ui.window_size import (
        FRAME_ALLOWANCE, FIT_RATIO, apply_window_size, available_area, fit_sizes,
    )

    # ---- 1. 纯函数：屏幕够大时逐像素不变（只夹不涨） ----
    size, minimum = fit_sizes(WINDOW_SIZE, WINDOW_MIN_SIZE, QRect(0, 0, 2560, 1400))
    ok("大屏：期望尺寸与最小尺寸原样保留（只夹不涨）",
       (size.width(), size.height()) == (WINDOW_SIZE.width(), WINDOW_SIZE.height())
       and (minimum.width(), minimum.height())
       == (WINDOW_MIN_SIZE.width(), WINDOW_MIN_SIZE.height()),
       f"size={size.width()}x{size.height()} min={minimum.width()}x{minimum.height()}")

    # ---- 2. 纯函数：用户现场（1536×824），高度必须让位于任务栏 ----
    size, minimum = fit_sizes(WINDOW_SIZE, WINDOW_MIN_SIZE, USER_SCREEN_AREA)
    cap_h = int((USER_SCREEN_AREA.height() - FRAME_ALLOWANCE.height()) * FIT_RATIO)
    ok("1920×1080@125%（可用 1536×824）：高被夹住，外框仍放得下",
       size.height() == cap_h and size.height() + FRAME_ALLOWANCE.height()
       <= USER_SCREEN_AREA.height()
       and size.width() == WINDOW_SIZE.width(),
       f"size={size.width()}x{size.height()} 期望高={cap_h} "
       f"min={minimum.width()}x{minimum.height()}")
    ok("1920×1080@125%：最小高没有被误伤（720 仍可拖到）",
       minimum.height() == WINDOW_MIN_SIZE.height(),
       f"min={minimum.width()}x{minimum.height()}")

    # ---- 3. 纯函数：极窄屏 —— 最小尺寸也要跟着降，否则用户被卡死 ----
    tiny = QRect(0, 0, 1092, 574)   # 1366×768 @125%
    size, minimum = fit_sizes(WINDOW_SIZE, WINDOW_MIN_SIZE, tiny)
    ok("1366×768@125%（可用 1092×574）：最小尺寸跟着夹到窗口尺寸",
       minimum.width() == size.width() and minimum.height() == size.height()
       and size.width() <= tiny.width() and size.height() <= tiny.height(),
       f"size={size.width()}x{size.height()} min={minimum.width()}x{minimum.height()}")

    # ---- 4. 纯函数：拿不到屏幕信息时原样返回，不猜 ----
    size, minimum = fit_sizes(WINDOW_SIZE, WINDOW_MIN_SIZE, None)
    ok("无屏幕信息：原样返回，不做任何缩水",
       size == WINDOW_SIZE and minimum == WINDOW_MIN_SIZE, f"size={size.toTuple()}")

    # ---- 5. 真窗口：含标题栏的外框必须完全落在可用区域内 ----
    area = available_area()
    ok("离屏环境下拿得到可用区域", area is not None and not area.isEmpty(),
       f"area={area.getRect() if area else None}")

    window = MainWindow()
    window.show()
    for _ in range(6):
        ctx.app.processEvents()
    frame = window.frameGeometry()
    ok("主窗口：外框完全落在屏幕可用区域内（不再被任务栏遮挡）",
       frame.left() >= area.left() and frame.top() >= area.top()
       and frame.right() <= area.right() and frame.bottom() <= area.bottom(),
       f"frame={frame.getRect()} area={area.getRect()}")
    ok("主窗口：最小尺寸不超过落地尺寸（拖不到更小就不是尺寸问题）",
       window.minimumWidth() <= window.width()
       and window.minimumHeight() <= window.height(),
       f"min={window.minimumWidth()}x{window.minimumHeight()} "
       f"size={window.width()}x{window.height()}")
    window.close()

    from desktop.components.viewers.image_editor import ImageEditorDialog

    dialog = ImageEditorDialog(None, None)
    dialog.show()
    for _ in range(6):
        ctx.app.processEvents()
    frame = dialog.frameGeometry()
    ok("图片编辑弹窗：外框也在可用区域内",
       frame.left() >= area.left() and frame.top() >= area.top()
       and frame.right() <= area.right() and frame.bottom() <= area.bottom(),
       f"frame={frame.getRect()} area={area.getRect()}")
    dialog.close()

    # ---- 6. 期望尺寸远超屏幕时，尺寸与位置同时被收住 ----
    area = available_area()
    expected = fit_sizes(QSize(10_000, 10_000), None, area)[0]
    probe = MainWindow()
    apply_window_size(probe, QSize(10_000, 10_000))
    probe.show()
    for _ in range(4):
        ctx.app.processEvents()
    frame = probe.frameGeometry()
    ok("超大期望尺寸：夹进可用区域且外框不出界",
       probe.width() == expected.width() and probe.height() == expected.height()
       and frame.left() >= area.left() and frame.right() <= area.right()
       and frame.bottom() <= area.bottom(),
       f"size={probe.width()}x{probe.height()} "
       f"期望={expected.width()}x{expected.height()} frame={frame.getRect()}")
    probe.close()

    # ---- 7. 默认最大化（用户 2026-10-01：「默认就占满屏幕吧」） ----
    from desktop.app import WINDOW_START_MAXIMIZED

    ok("主窗口默认最大化（1920 屏上默认宽度已占可用宽 94%，留边无意义）",
       WINDOW_START_MAXIMIZED is True, f"{WINDOW_START_MAXIMIZED=}")

    maximized = MainWindow()
    maximized.showMaximized()
    for _ in range(6):
        ctx.app.processEvents()
    ok("最大化：窗口状态真的是最大化，且客户端铺满工作区（不吃任务栏）",
       maximized.isMaximized()
       and maximized.width() >= area.width() - FRAME_ALLOWANCE.width()
       and maximized.height() >= area.height() - FRAME_ALLOWANCE.height(),
       f"isMaximized={maximized.isMaximized()} "
       f"client={maximized.width()}x{maximized.height()} "
       f"可用区={area.width()}x{area.height()}")
    # ⚠️ 最大化**不**断言外框落在可用区域内：Windows 最大化窗口的
    #    frameGeometry 会连 DWM 的不可见缩放边框一起报（实测 y=-7、高 831
    #    对可用高 824），可见区域本身正好等于工作区。
    maximized.showNormal()
    for _ in range(6):
        ctx.app.processEvents()
    restored_w, restored_h = fit_sizes(WINDOW_SIZE, None, area)[0].toTuple()
    ok("还原：回到夹紧后的默认尺寸（最大化不等于把窗口定死）",
       (maximized.width(), maximized.height()) == (restored_w, restored_h),
       f"还原后={maximized.width()}x{maximized.height()} 期望={restored_w}x{restored_h}")
    maximized.close()
