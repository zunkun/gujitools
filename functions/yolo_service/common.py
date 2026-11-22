# -*- coding: utf-8 -*-
"""服务开关、发现文件/日志路径与身份指纹（客户端与服务端共用）。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import utils

from functions.yolo_service.constants import (
    DEFAULT_TTL_SECONDS,
    LOG_MAX_BYTES,
    SERVICE_FILE_PREFIX,
)


# --------------------------------------------------------------------- 小工具
def _service_enabled() -> bool:
    """服务开关。

    由**入口层**决定归属：desktop 的 `desktop.py` 置 ``1``（并传给它的 worker），
    CLI 的 `cli.py` 置 ``0``（一次性任务，进程退出即释放）。外部显式设 0 可整体
    关掉（排障用）。
    """
    raw = os.environ.get("GUJI_YOLO_SERVICE")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


def require_service() -> bool:
    """是否**禁止**回落到本进程内加载模型（默认否 ⇒ CLI 行为不变）。

    置 ``GUJI_YOLO_REQUIRE_SERVICE=1`` 的进程里，一旦"这次没走成服务"就报错，
    而不是自己 `import torch` 载模型。给 GUI 主进程用——它不许进重依赖
    （torch/ultralytics 约 350MB，见 AGENTS.md 分层守卫）。

    与 :func:`_service_enabled` 同款真假解析（``0/false/no/off`` 为假）。
    """
    raw = os.environ.get("GUJI_YOLO_REQUIRE_SERVICE")
    if raw is None:
        return False
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _ttl_seconds() -> float | None:
    """空闲 TTL（秒）；**None＝常驻**（默认）。环境变量 `GUJI_YOLO_TTL`
    可显式覆盖成有限值，下限 5 秒——仅测试/排障用。"""
    raw = os.environ.get("GUJI_YOLO_TTL")
    if raw:
        try:
            return max(5.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_TTL_SECONDS


def service_file(fp: str) -> Path:
    """发现文件的完整路径（**按指纹区分**，开发版与正式版各用各的）。"""
    tag = hashlib.md5(fp.encode("utf-8")).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"{SERVICE_FILE_PREFIX}{tag}.json"


def _all_service_files() -> list[Path]:
    """临时目录里现存的全部发现文件（排障/收尾用，跨指纹）。"""
    return sorted(Path(tempfile.gettempdir()).glob(f"{SERVICE_FILE_PREFIX}*.json"))


def log_file() -> Path:
    """服务日志路径（服务是分离进程、没有控制台，日志必须落文件才可诊断）。"""
    return Path(tempfile.gettempdir()) / "guji-yolo-service.log"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fingerprint() -> str:
    """服务身份指纹：版本 + 权重路径 + 权重大小/修改时间。

    三者任一变化（升级、换权重、重新打包）都必须视为"不是同一个服务"，
    否则会拿旧权重/旧代码的结果当新结果用。
    """
    try:
        from config import VERSION
    except Exception:  # noqa: BLE001 - 指纹算不出来就退化成路径，不该因此失败
        VERSION = "?"
    try:
        weights = utils.model_path()
    except Exception:  # noqa: BLE001 - 权重缺失（安装损坏）时退化，别让服务起不来
        return f"{VERSION}|<no-weights>"
    try:
        stat = weights.stat()
        stamp = f"{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        stamp = "?"
    return f"{VERSION}|{weights}|{stamp}"


def model_fingerprint() -> str:
    """服务身份指纹（公开版；供日志/诊断读取，不参与内部决策）。

    内容与 :func:`_fingerprint` 完全一致——版本 + 权重路径 + 权重大小/修改时间。
    """
    return _fingerprint()


def _log(message: str) -> None:
    """追加一行到服务日志（服务进程专用；失败不抛）。"""
    try:
        with open(log_file(), "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def _rotate_log_if_huge() -> None:
    """日志过大就删掉重开（服务启动时调一次）。

    ⚠️ 原先这份日志**永久追加、从不轮转**（2026-09-26 审计）：每次拉起服务都追加
    若干行、`print` 拦截后的库输出也全在里面，长期使用会涨到几十上百 MB。
    这里做最简单的轮转——超上限就换一份新的：保留最近一次运行的记录足够诊断，
    真需要历史用户会自己备份。
    """
    try:
        path = log_file()
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            path.unlink()
    except OSError:
        pass


def sweep_stale_service_files() -> int:
    """删掉「属主进程已死」的发现文件，返回删除个数。

    ⚠️ 发现文件只在服务**正常退出**时清（`_remove_service_file`）；被 kill、崩溃、
    断电都会留下它，而且它是**按指纹分文件**的——换权重、升级版本各留一份、
    从不回收（2026-09-26 审计）。留着不只是垃圾：客户端扫到陈旧文件会去连一个
    已经不存在的端口，白等一轮建连超时。
    """
    from utils.proc_utils import pid_alive

    removed = 0
    for path in _all_service_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = int(data.get("pid", -1))
        except (OSError, ValueError, json.JSONDecodeError):
            pid = -1  # 读不出来（损坏/半截）→ 它已经没用了，一并清掉
        if pid_alive(pid):
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _client_log(message: str) -> None:
    """客户端侧的诊断信息也写同一份日志，便于把两侧串起来看。"""
    _log(f"[client {os.getpid()}] {message}")
