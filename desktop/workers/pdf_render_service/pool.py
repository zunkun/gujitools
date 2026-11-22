# -*- coding: utf-8 -*-
"""子进程池管理、运行计数与收尾（``pdf_render_service`` 的状态中心）。"""

from __future__ import annotations

import os
import threading
from typing import Any

from .constants import (
    CALL_TIMEOUT_S,
    ENV_MODE,
    EXTRACT_WORKERS,
    MAX_WORKERS,
    POOL_FAILURE_LIMIT,
)

_LOCK = threading.Lock()
_pool: Any = None
#: 单页提取专用池（见 ``EXTRACT_WORKERS``）：**绝不与缩略图/预览共用**
_extract_pool: Any = None
#: 连续失败次数（成功一次即清零）。到 ``POOL_FAILURE_LIMIT`` 才永久降级。
_pool_failures = 0
_disabled = False
#: 正在收尾（``shutdown()`` 之后）：不再建池、也不再刷"降级"日志
_closing = False
_stats = {"renders": 0, "extracts": 0, "page_counts": 0, "fallbacks": 0}


def _worker_count() -> int:
    """池大小：按 CPU 数给 2~3 个（见 ``MAX_WORKERS`` 的说明）。"""
    cpu = os.cpu_count() or 2
    return max(1, min(MAX_WORKERS, cpu - 2 if cpu > 4 else 2))


def _mode() -> str:
    """当前模式：``proc`` / ``inproc``。"""
    if _disabled:
        return "inproc"
    if (os.environ.get(ENV_MODE) or "").strip().lower() in ("inproc", "0", "off"):
        return "inproc"
    return "proc"


def offloaded() -> bool:
    """渲染是否**真的**在子进程里做（宿主据此决定要不要"让出 GIL"的 sleep）。"""
    return _mode() == "proc" and _pool is not None


def workers() -> int:
    """池大小（批量路径按它决定一批渲几页）。"""
    return _worker_count()


def _pool_or_none(kind: str = "render"):
    """惰性建池；失败返回 None。

    ``kind``：``render``（缩略图/大图，共用 ``_pool``）或 ``extract``
    （单页提取，独立 ``_extract_pool``——见 ``EXTRACT_WORKERS`` 的说明）。
    """
    global _pool, _extract_pool, _disabled
    if _closing or _mode() != "proc":
        return None
    with _LOCK:
        current = _pool if kind == "render" else _extract_pool
        if current is not None:
            return current
        if _disabled:
            return None
        try:
            from concurrent.futures import ProcessPoolExecutor

            size = _worker_count() if kind == "render" else EXTRACT_WORKERS
            current = ProcessPoolExecutor(max_workers=size)
        except Exception as exc:  # noqa: BLE001 - 起不来就降级，绝不抛给界面
            _disabled = True
            print(f"[渲染服务] 子进程池启动失败，退回进程内渲染：{exc}")
            return None
        if kind == "render":
            _pool = current
        else:
            _extract_pool = current
        return current


def _drop_pool(kind: str, exc: BaseException) -> None:
    """池出问题：关掉它、下次请求重建；**连续**失败到阈值才永久退回进程内。

    超时/被杀/OOM 都会让 ``ProcessPoolExecutor`` 进入不可用状态，继续往上
    submit 只会继续抛异常，所以先丢掉重建。只有反复失败（启动就坏）才认定
    环境不支持子进程。
    """
    global _pool, _extract_pool, _pool_failures, _disabled
    with _LOCK:
        pool = _pool if kind == "render" else _extract_pool
        if kind == "render":
            _pool = None
        else:
            _extract_pool = None
        _pool_failures += 1
        give_up = _pool_failures >= POOL_FAILURE_LIMIT
        if give_up:
            _disabled = True
    if pool is not None:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001 - 收尾尽力而为
            pass
    if not _closing and not _silent_failure(exc):
        tail = "（已永久退回进程内渲染）" if give_up else "（下次请求会重建子进程池）"
        what = "提取" if kind == "extract" else "渲染"
        print(f"[渲染服务] 子进程{what}失败{tail}：{type(exc).__name__}: {exc}")


def _note_success() -> None:
    """一次子进程调用成功了：清零连续失败计数（只清不清零都无所谓，别每页抢锁）。"""
    global _pool_failures
    if _pool_failures:
        with _LOCK:
            _pool_failures = 0


def _call(fn, *args, kind: str = "render"):
    """把一次调用交给子进程；任何异常都降级为进程内（并留下可观测日志）。"""
    pool = _pool_or_none(kind)
    if pool is None:
        raise _NoPool()
    try:
        result = pool.submit(fn, *args).result(timeout=CALL_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - 池崩了（OOM/被杀/超时）
        _drop_pool(kind, exc)
        raise _NoPool() from exc
    _note_success()
    return result


class _NoPool(Exception):
    """内部信号：没有可用的子进程池 → 走进程内。"""


def _silent_failure(exc: BaseException) -> bool:
    """这次失败要不要**不吭声**（只回落）。

    情形：解释器正在退出——``concurrent.futures`` 的 atexit 已经把池关掉，
    还在跑的后台线程再 submit 就会拿到 ``RuntimeError: cannot schedule new
    futures after shutdown``。那不是 bug，是收尾顺序；刷一行红字只会吓人。
    """
    return "after shutdown" in str(exc).lower()


def _fallback_count() -> None:
    _stats["fallbacks"] += 1


def stats() -> dict:
    """运行计数（自测断言用）：``renders`` / ``extracts`` / ``page_counts`` /
    ``fallbacks`` / ``mode`` / ``workers`` / ``pool_failures``。"""
    return {
        **_stats,
        "mode": _mode(),
        "workers": _worker_count(),
        "extract_workers": EXTRACT_WORKERS,
        "pool_failures": _pool_failures,
        "offloaded": offloaded(),
    }


def reset_stats() -> None:
    """清零计数（自测用；不动池）。"""
    global _pool_failures
    for key in _stats:
        _stats[key] = 0
    _pool_failures = 0


def shutdown() -> None:
    """收掉子进程池（关程序/单测收尾）。

    ⚠️ 置 ``_closing`` 之后**不再建池**：关程序时还可能有后台线程在渲，
    它会安静地退回进程内（≤1s 一页）而不是刷一条"子进程渲染失败"的日志。
    """
    global _pool, _extract_pool, _closing
    _closing = True
    with _LOCK:
        pools = [_pool, _extract_pool]
        _pool = None
        _extract_pool = None
    for pool in pools:
        if pool is None:
            continue
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001 - 收尾尽力而为
            pass
