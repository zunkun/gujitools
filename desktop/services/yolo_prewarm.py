# -*- coding: utf-8 -*-
"""YOLO 预加载：进任务详情页时，趁用户逗把常驻服务的模型在后台热好。

## 为什么

「检测文本框」真正执行时，常驻 YOLO 服务若还没载模型，第一页要白等约 5 秒
（frozen 下 `import torch` + 首次 `YOLO(weights)`）。用户点「执行」之前通常
已经进过详情页、在页面里停留了一阵——这段时间足够后台把模型热好，等他真点
「执行」时服务里早就是现成的。

## 设计口径（用户 2026-10-13）

1. **加载条件**：本任务的流程图里有「检测文本框」节点，**且**这一步从没
   执行过（跑过一次就不预载——要么模型已就绪、要么用户根本不走这条路）。
   判定收在纯函数 :func:`detect_pending` 里，可脱离页面单测。
2. **全局只加载一次**：本会话只做一次真正的预热（:func:`claim_prewarm_slot`
   的槽位语义）；之后每次进任务详情只做一次**轻量探测**（向服务发一条
   ``status``，不拉起、不加载）。
3. **不影响主线程 / 让出 CPU**：
   - 主线程只做毫秒级的条件判定与 ``QTimer.singleShot`` 排程；
   - 重活（拉起服务、torch 导入、载模型）全部发生在**常驻服务子进程**里，
     而那个进程被降到「低于正常」优先级（见
     ``functions/yolo_service._set_process_priority``），界面渲染一路先行，
     真检测开始时服务端自己升回正常；
   - 调度线程只是 socket 收发，OS 阻塞等待，不占 CPU。
4. **失败无声**：预加载是体验优化，任何失败（服务起不来、权重缺失、Qt
   环境缺失）都只写服务日志，绝不影响进页面，也绝不回落到 GUI 主进程内
   加载模型（那会违反「GUI 主进程禁重依赖」）。

⚠️ 与常驻服务生命周期的关系（2026-10-13 用户口径更新）：服务**默认常驻不
退出**（"yolo 加载到内存全局，会只加载一次，不要释放"）——预加载热好的
模型整个会话都在，跨 app 重启也命中；只有显式设 `GUJI_YOLO_TTL` 才有
空闲自退（测试/排障用）。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QTimer

#: 进详情页后延迟多久再动手（毫秒）。这段时间让页面渲染、清单刷新、
#: 缩略图加载先跑完——「在其他界面逗留的时候」的空闲档口。
PREWARM_DELAY_MS = 2000

#: 探测（二次进入）同样延迟：反正不加载，晚点问也无妨
PROBE_DELAY_MS = PREWARM_DELAY_MS

#: 排程槽位锁与「本会话是否已排过真正预热」的标记
_slot_lock = threading.Lock()
_prewarm_claimed = False


# ---------------------------------------------------------------- 条件判定
def detect_pending(slots, detect_state: dict | None) -> bool:
    """预加载条件：流程里有「检测文本框」节点，且这一步没执行过。

    ``slots``：本任务流程的槽位表（``store.task_slots`` / 页面 ``flow_slots``，
    元素带 ``step`` 属性——鸭子类型访问，不 import 页面层的东西）；
    ``detect_state``：``store.stage_states(task_id)["detect"]``（无记录时
    传 ``None`` 或让页面直接取，``stage_states`` 的静态键永远存在）。

    「没执行过」= runs.json 里没有这一步的任何记录（status 停在 pending、
    done/total 为 0、completed 为 False）。执行过哪怕失败/中断都算执行过
    ——那时模型多半已经就绪，或用户在走整页兜底，都轮不到预加载。
    """
    has_node = any(
        getattr(slot, "step", None) == "detect" for slot in (slots or ())
    )
    if not has_node:
        return False
    if not detect_state:
        return True
    return not (
        detect_state.get("completed")
        or detect_state.get("total")
        or detect_state.get("status", "pending") != "pending"
    )


# ---------------------------------------------------------------- 排程槽位
def claim_prewarm_slot() -> str | None:
    """领取本会话的排程槽位：第一次 ``"prewarm"``，之后 ``"probe"``。

    纯逻辑、锁内一次判定，调用方据此决定起哪条后台线（自测直接驱动它
    验证「全局只加载一次、二次只检测」）。返回 ``None`` 不会发生——每次
    进入详情页至少值得探测一次；将来若要限频在这里改。
    """
    global _prewarm_claimed
    with _slot_lock:
        if not _prewarm_claimed:
            _prewarm_claimed = True
            return "prewarm"
        return "probe"


def _reset_for_tests() -> None:
    """清掉会话级标记（仅自测用）。"""
    global _prewarm_claimed
    with _slot_lock:
        _prewarm_claimed = False


# ---------------------------------------------------------------- 主线程入口
def request_prewarm(delay_ms: int = PREWARM_DELAY_MS) -> None:
    """进任务详情页时调用（**主线程**，条件已由页面核过）。

    第一次：延迟 ``delay_ms`` 后在后台线程做真正的预热；之后：只做轻量
    探测。没有 Qt 环境（CLI / 无 QApplication 的场景）时静默放弃——预加载
    本来就不属于 CLI。
    """
    mode = claim_prewarm_slot()
    try:
        QTimer.singleShot(
            max(0, delay_ms),
            lambda: _launch(mode),
        )
    except Exception:  # noqa: BLE001 - 排程失败不影响进页面
        client_log("YOLO 预加载排程失败（无 Qt 环境？），本次放弃")


def _launch(mode: str) -> None:
    """把工作甩给 daemon 线程：线程里绝不碰任何 Qt 对象。"""
    target = _prewarm_worker if mode == "prewarm" else _probe_worker
    threading.Thread(target=target, name=f"yolo-{mode}", daemon=True).start()


# ---------------------------------------------------------------- 后台线程
def _prewarm_worker() -> None:
    """真正的预热：拉起/复用常驻服务并载模型（重活在服务子进程里）。"""
    from functions import yolo_service as ys

    # 服务被显式关掉（GUJI_YOLO_SERVICE=0）时不预载——用户/环境明确不要它
    if not ys._service_enabled():
        return
    # 权重缺失：服务即使拉起来也永远载不了模型，预热必然白跑
    try:
        import utils

        utils.model_path()
    except Exception as exc:  # noqa: BLE001
        ys.client_log(f"YOLO 预加载跳过：{exc}")
        return
    backend, seconds = ys.warm_up_service_only()
    if backend == "service":
        ys.client_log(
            f"YOLO 预加载完成（模型在常驻服务里就绪，"
            f"本次加载 {seconds:.1f}s，服务进程低优先级让出 CPU）"
        )
    else:
        ys.client_log(f"YOLO 预加载未走成（backend={backend}），检测时再按需加载")


def _probe_worker() -> None:
    """二次进入：只查一次「模型是否已加载」，不拉起、不加载。"""
    from functions import yolo_service as ys

    loaded = ys.service_model_loaded()
    if loaded is True:
        ys.client_log("YOLO 预加载探测：模型已就绪（复用常驻服务，不重复加载）")
    elif loaded is False:
        ys.client_log(
            "YOLO 预加载探测：服务在但模型未就绪"
            "（本会话已预热过，按「全局只加载一次」口径不再加载）"
        )
    else:
        ys.client_log("YOLO 预加载探测：暂无常驻服务（本会话已预热过，不再拉起）")
