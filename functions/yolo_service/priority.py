# -*- coding: utf-8 -*-
"""服务进程的优先级控制（空闲让出 CPU、真检测升回正常）。"""

from __future__ import annotations

import sys

from functions.yolo_service.common import _log
from functions.yolo_service.constants import _NORMAL_PRIORITY_CLASS

#: 服务端是否已把自身优先级升回正常（一次性；真检测开始时触发）
_priority_boosted = False


def _set_process_priority(proc, priority_class: int) -> None:
    """设置刚拉起的服务进程优先级（仅 Windows；其他平台无事可做）。

    服务的两种生活状态：
    - **空闲/预热**（大多数时候）：预加载（见 desktop/services/yolo_prewarm）
      会在用户正在翻界面时后台导入 torch、载模型——同优先级会跟 GUI 抢 CPU
      造成页面卡顿。降到 BELOW_NORMAL 后调度器让所有正常优先级的活儿先行，
      页面渲染、参数面板、缩略图一律不吃亏（用户 2026-10-13「让出 CPU」）。
    - **真检测**：服务端收到第一条 ``detect`` 请求时自己升回 NORMAL
      （见 :func:`_boost_priority`），批量推理不吃亏。
    """
    if sys.platform != "win32":
        return
    handle = getattr(proc, "handle", None)
    if not handle:
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetPriorityClass(handle, priority_class)
    except Exception:  # noqa: BLE001 - 优先级是锦上添花，失败绝不影响拉起
        pass


def _boost_priority() -> None:
    """服务端：真检测开始时把自己升回**正常**优先级（一次性）。

    空闲/预热期服务是 BELOW_NORMAL（见 _set_process_priority 的说明）；
    一旦有真实的检测请求进来，说明用户正在等结果——批量推理不该再让路。
    SetPriorityClass 是微秒级调用，每条请求调一次也无妨，这里仍用一次性
    标记避免日志噪音。
    """
    global _priority_boosted
    if _priority_boosted or sys.platform != "win32":
        return
    _priority_boosted = True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(
            kernel32.GetCurrentProcess(), _NORMAL_PRIORITY_CLASS)
        _log("检测开始，服务优先级升回正常（NORMAL_PRIORITY_CLASS）")
    except Exception:  # noqa: BLE001
        pass
