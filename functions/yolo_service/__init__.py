# -*- coding: utf-8 -*-
"""常驻 YOLO 服务：**desktop 侧**多次检测共用同一份已加载的模型。

## 归属：只属于 desktop，CLI 不用

原则（用户定）：**cli 与 desktop 是两套系统，内存不互通**。

- **desktop**：GUI 每点一次「检测」都是新的 worker 子进程，进程一退模型就没了，
  下一次又从头付一遍——所以模型放进这里这个常驻进程，desktop 的多次执行共用。
  **常驻不退出**（用户 2026-10-13 口径："yolo 加载到内存全局，会只加载一次，
  不要释放"——约 350MB 换每一轮会话都零加载等待，且跨 app 重启仍命中）。
  `desktop.py` 会把 ``GUJI_YOLO_SERVICE`` 置 ``1`` 并传给它派生的全部 worker。
- **CLI**：一次性任务，模型在本进程内加载、进程退出即释放，**不占常驻内存**。
  `cli.py` 显式把 ``GUJI_YOLO_SERVICE`` 置 ``0``，因此 CLI 的 crop/detect/cropremove
  完全不经过本模块（直接走 `functions.detect.detect_page_boxes` 的进程内路径），
  行为与本模块引入之前完全一致。

## 为什么需要它

frozen 打包下 `import torch` + 首次 `YOLO(weights)` 要 **约 5.4 秒**，desktop 侧
不常驻的话，每次点「检测」都要重付。把模型搬进独立常驻进程，desktop 的多次
执行只加载一次。

## 两个关键设计

1. **过 socket 的是路径，不是像素**。检测只需要路径，服务自己读图。既省掉把
   几十 MB 图像编码/解码两趟的开销，也让调用方在只做检测时**根本不必解码**
   （比原来还少一次 `imread`）。一条请求一行 JSON，开销约 1ms，相对单页推理的
   一两百毫秒可忽略。
2. **失败一律回落**。连不上 / 握手失败 / 超时 / 协议错 / 服务报错 → 客户端返回
   `None`，调用方在本进程内加载模型继续做（见 `functions/detect.py::
   detect_page_boxes_by_path`）。**任何情况下检测都不会不可用**，最坏就是慢那
   5 秒——与引入本模块之前完全一致。

## 发现与生命周期

服务把 `{port, fp, pid}` 写进 ``%TEMP%/guji-yolo-service.json``，客户端读它来
连接；``fp`` 是**身份指纹**（版本 + 权重路径 + 权重大小/修改时间），不一致就
（多半是升级后残留的旧服务）忽略并另起一个——**不做互相驱逐**，免得两个
版本互相杀。⚠️ 默认已无常驻 TTL（见下），升级残留的旧服务不会再"自灭"：
它无害（指纹不符没人连它），只是白占一份内存，手动清掉或重启后想清可用
环境变量 `GUJI_YOLO_TTL` 给新服务加空闲上限。

服务端**允许并发连接**（每个客户端线程一条）：desktop 的批量检测本来就是
多线程共享一个模型并发推理，服务里也必须保持同样的并发度，否则等于把并行度
砍成 1。模型加载本身仍然只做一次（双重检查锁在 `yolo_utils` 里）。

子模块（按职责）::

    constants   发现文件名 / 超时 / 日志上限 / 优先级常量
    common      服务开关、发现文件与日志路径、身份指纹
    priority    服务进程优先级
    server      服务端主循环与请求处理
    __main__    `python -m functions.yolo_service` 入口

客户端（连接缓存、拉起服务、检测/预热/状态查询）住在本文件——它与
``_given_up`` / ``_local`` 这些**进程内可变状态**同处一个命名空间，
``yolo_service._given_up = False`` 这类外部重置才能照旧生效。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from typing import NamedTuple

import utils

from functions.yolo_service.common import (
    _all_service_files,
    _client_log,
    _fingerprint,
    _log,
    _project_root,
    _rotate_log_if_huge,
    _service_enabled,
    _ttl_seconds,
    log_file,
    model_fingerprint,
    require_service,
    service_file,
    sweep_stale_service_files,
)
from functions.yolo_service.constants import (
    CONNECT_TIMEOUT,
    DEFAULT_TTL_SECONDS,
    DETECT_TIMEOUT,
    LOG_MAX_BYTES,
    SERVICE_FILE_PREFIX,
    SPAWN_WAIT,
    _BELOW_NORMAL_PRIORITY_CLASS,
    _NORMAL_PRIORITY_CLASS,
)
from functions.yolo_service.priority import (
    _boost_priority,
    _priority_boosted,
    _set_process_priority,
)
from functions.yolo_service.server import (
    _ServiceState,
    _detect_file,
    _dispatch,
    _redirect_stdio_to_log,
    _remove_service_file,
    _serve_connection,
    _write_json_line,
    _write_service_file,
    serve,
)

#: 直连成功后的连接缓存：**按线程**存。CLI 的 detect 用 8 个线程并发推理，
#: 若共用一个连接就会被客户端串行化，等于把并行度砍掉。
_local = threading.local()
_spawn_lock = threading.Lock()
#: 本进程内已确认服务不可用 —— 之后不再尝试（避免每次检测都白等一次超时）
_given_up = False

#: 拉起过的服务进程句柄：保留引用以便回收（见 _spawn_service）。
#: 不留引用的话 Popen 对象会被立刻 GC，服务退出后没人 wait → POSIX 上留僵尸。
_SERVICE_PROCS: list = []


# --------------------------------------------------------------------- 客户端
class _Client:
    """一条到服务的连接。**每个线程各持一条**（见 `_local` 的说明）。"""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._reader = sock.makefile("r", encoding="utf-8", newline="\n")
        self._writer = sock.makefile("w", encoding="utf-8", newline="\n")

    def request(self, payload: dict, timeout: float = DETECT_TIMEOUT) -> dict:
        self._sock.settimeout(timeout)
        self._writer.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._writer.flush()
        line = self._reader.readline()
        if not line:
            raise ConnectionError("服务已关闭连接")
        return json.loads(line)

    def close(self) -> None:
        for closer in (self._reader.close, self._writer.close, self._sock.close):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass


def _read_service_file(fp: str):
    """读本构建的发现文件，返回 (port, fp) 或 None。"""
    try:
        data = json.loads(service_file(fp).read_text(encoding="utf-8"))
        return int(data["port"]), str(data.get("fp", ""))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _try_connect(port: int, fp: str):
    """连上并握手；指纹不符/异常一律返回 None。"""
    sock = None
    try:
        sock = socket.create_connection(("127.0.0.1", int(port)), timeout=CONNECT_TIMEOUT)
        client = _Client(sock)
        resp = client.request({"cmd": "hello", "fp": fp, "pid": os.getpid()},
                              timeout=CONNECT_TIMEOUT)
        if resp.get("ok"):
            return client
        _client_log(f"握手被拒：{resp.get('error')}")
    except Exception as exc:  # noqa: BLE001 - 连不上属正常情况（没服务/被 TTL 收走）
        _client_log(f"连接 {port} 失败：{type(exc).__name__}: {exc}")
    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass
    return None


def _service_command():
    """拉起服务的命令行。

    frozen 走 `--yolo-service` 开关（两个入口都认，见 cli.py / desktop.py）；
    源码模式走 `-m`，工作目录设成项目根以保证 `functions` 能导入。
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--yolo-service"]
    return [sys.executable, "-m", "functions.yolo_service"]


def _spawn_service() -> bool:
    """分离地拉起服务进程。返回是否成功提交了启动请求。"""
    command = _service_command()
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(_project_root()),
        "close_fds": True,
    }
    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：脱离父进程的控制台与进程组，
        # 否则 GUI 一退、或用户在终端 Ctrl+C，会把服务一起带走。
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    try:
        # ⚠️ 保留 Popen 引用并顺手回收已退出的服务：
        #    - 不留引用的话对象会被立刻 GC，服务退出后没人 wait → POSIX 上变僵尸
        #      进程（GUI 可能开几小时，反复拉起会累积）；
        #    - 记着它还能顺手做「日志轮转」的判据。
        proc = subprocess.Popen(command, **kwargs)
        _SERVICE_PROCS.append(proc)
        for done in [p for p in _SERVICE_PROCS if p.poll() is not None]:
            _SERVICE_PROCS.remove(done)
        # 预加载/预热期的服务让出 CPU：降到 BELOW_NORMAL，真检测开始时
        # 服务端自己升回（见 _boost_priority 与 _set_process_priority 说明）
        _set_process_priority(proc, _BELOW_NORMAL_PRIORITY_CLASS)
        _client_log(f"已拉起服务（低于正常优先级）：{' '.join(command)}")
        return True
    except OSError as exc:
        _client_log(f"拉起服务失败：{type(exc).__name__}: {exc}")
        return False


def _wait_for_service(timeout: float = SPAWN_WAIT):
    """等刚拉起的服务可用：轮询发现文件 + 握手。"""
    fp = _fingerprint()
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = _read_service_file(fp)
        if found is not None and found[1] == fp:
            client = _try_connect(*found)
            if client is not None:
                return client
        time.sleep(0.2)
    return None


def _thread_client():
    """取本线程的连接：没有就发现/拉起一个。失败返回 None（由调用方回落）。"""
    global _given_up
    conn = getattr(_local, "client", None)
    if conn is not None:
        return conn
    if _given_up:
        return None

    fp = _fingerprint()
    found = _read_service_file(fp)
    if found is not None:
        conn = _try_connect(*found)
    if conn is None:
        with _spawn_lock:
            # 双检：等锁期间别的线程可能已经拉起来了
            found = _read_service_file(fp)
            conn = _try_connect(*found) if found else None
            if conn is None:
                if not _spawn_service():
                    _given_up = True
                    return None
                conn = _wait_for_service()
                if conn is None:
                    _client_log("等服务就绪超时，本次回落到本进程内加载模型")
                    _given_up = True
                    return None
    _local.client = conn
    return conn


def _drop_thread_client() -> None:
    conn = getattr(_local, "client", None)
    if conn is not None:
        conn.close()
        _local.client = None


def _as_box(raw):
    if not raw:
        return None
    return tuple(int(v) for v in raw[:4])


class ServiceDetect(NamedTuple):
    """一次「经服务完成」的检测结果。

    `model_load_seconds > 0` 表示**这一张**把模型加载起来了（服务刚被拉起、
    或刚被 TTL 收走后又拉起）；为 0 表示服务里已有模型、直接复用。

    `full` 是整幅内容（fullcontent）的框（与 left/right 互斥，互斥由检测侧的
    消解规则保证）；`notes` 是消解触发的规则说明，客户端据此打日志。
    """

    left: tuple | None
    right: tuple | None
    full: tuple | None
    notes: tuple
    model_load_seconds: float


def service_in_use() -> bool:
    """本线程是否已经在用常驻服务（日志里说明"模型住在哪"用）。"""
    return getattr(_local, "client", None) is not None


def detect_boxes_via_service(image_path) -> ServiceDetect | None:
    """把一张图交给常驻服务检测，返回 :class:`ServiceDetect`。

    **`None` 表示"这次没走成服务"**（服务关着、拉不起来、连不上、协议错、
    服务端报错都算），调用方应当回落到本进程内加载模型。注意它与"服务算完
    但没检到框"不同——后者返回 ``ServiceDetect(None, None, 0.0)``。
    """
    if not _service_enabled():
        return None
    conn = _thread_client()
    if conn is None:
        return None
    try:
        resp = conn.request({"cmd": "detect", "image": str(image_path)})
    except Exception as exc:  # noqa: BLE001
        _client_log(f"请求失败，丢弃连接：{type(exc).__name__}: {exc}")
        _drop_thread_client()
        return None
    if not resp.get("ok"):
        _client_log(f"服务返回失败：{resp.get('error')}")
        return None
    return ServiceDetect(
        left=_as_box(resp.get("left")),
        right=_as_box(resp.get("right")),
        full=_as_box(resp.get("full")),
        notes=tuple(str(n) for n in (resp.get("notes") or ())),
        model_load_seconds=float(resp.get("model_load_seconds") or 0.0),
    )


def warm_up() -> tuple[str, float]:
    """确保模型就绪，返回 ``(backend, 本次加载耗时秒)``。

    **单独成一步**的意义：模型加载（frozen 下约 5 秒）必须被单独计时、单独报出，
    否则会落到"第一张图"的耗时里，看起来像某一张特别慢。

    backend 为 ``"service"``（常驻服务里就绪）或 ``"in-process"``（服务不可用，
    本进程内加载）。耗时 0.0 表示模型本来就绪、这次没花时间——正常复用时的样子。
    """
    global _given_up
    if _service_enabled():
        # 顺手清掉「属主已死」的旧发现文件（否则客户端会去连不存在的端口、
        # 白等一轮建连超时；见 sweep_stale_service_files）
        try:
            sweep_stale_service_files()
        except Exception:  # noqa: BLE001 - 清理是尽力而为，不能影响预热
            pass
        conn = _thread_client()
        if conn is not None:
            try:
                resp = conn.request({"cmd": "warmup"}, timeout=DETECT_TIMEOUT)
                if resp.get("ok"):
                    return "service", float(resp.get("model_load_seconds") or 0.0)
                _client_log(f"预热被拒：{resp.get('error')}")
            except Exception as exc:  # noqa: BLE001
                _client_log(f"预热请求失败：{type(exc).__name__}: {exc}")
                _drop_thread_client()
        # 服务这条路已经试过且不通：标记本进程不再尝试，免得后面每张图都白等
        # 一次建连超时（CLI 的 detect 是 8 线程并发，那会成倍放大）。
        _given_up = True

    already = utils.is_model_loaded()
    utils.load_yolo_model()
    return "in-process", 0.0 if already else utils.load_seconds_used()


def warm_up_service_only() -> tuple[str, float]:
    """预加载专用：**只走常驻服务**，绝不回落本进程内加载。

    与 :func:`warm_up` 的唯一区别是失败语义：服务连不上/拉不起时返回
    ``("unavailable", 0.0)``，而**不会**在调用进程里 `load_yolo_model()`。
    这是给 GUI 主进程（desktop 侧预加载）用的——GUI 主进程禁重依赖
    （torch/ultralytics 不许进主进程，见 AGENTS.md 分层守卫），回落加载
    等于把约 350MB 的 torch 拽进界面进程。

    返回 ``(backend, 加载耗时秒)``：backend 为 ``"service"``（服务里就绪）、
    ``"disabled"``（GUJI_YOLO_SERVICE 关闭）或 ``"unavailable"``（服务没走成）。
    耗时 0.0 表示模型本来就绪或没有加载发生。
    """
    if not _service_enabled():
        return "disabled", 0.0
    # 顺手清掉「属主已死」的旧发现文件（同 warm_up；见 sweep_stale_service_files）
    try:
        sweep_stale_service_files()
    except Exception:  # noqa: BLE001 - 清理是尽力而为，不能影响预热
        pass
    conn = _thread_client()
    if conn is None:
        # 注意：**不**置 _given_up——预加载失败不该替真正的检测放弃服务路，
        # worker 子进程各有各的客户端状态，这里只影响 GUI 主进程自己。
        return "unavailable", 0.0
    try:
        resp = conn.request({"cmd": "warmup"}, timeout=DETECT_TIMEOUT)
        if resp.get("ok"):
            return "service", float(resp.get("model_load_seconds") or 0.0)
        _client_log(f"预热被拒：{resp.get('error')}")
    except Exception as exc:  # noqa: BLE001
        _client_log(f"预热请求失败：{type(exc).__name__}: {exc}")
        _drop_thread_client()
    return "unavailable", 0.0


def service_model_loaded(timeout: float = CONNECT_TIMEOUT) -> bool | None:
    """轻量探测：常驻服务里模型是否**已经**就绪（不拉起、不加载）。

    预加载调度的「二次进入只检测是否加载」用：只发一条 ``status`` 指令，
    没有服务时直接 ``None``，绝不 spawn、绝不触发模型加载。
    """
    status = service_status(timeout=timeout)
    if not status:
        return None
    return bool(status.get("model_loaded"))


def client_log(message: str) -> None:
    """客户端侧诊断写服务日志（公开入口；GUI 侧预加载调度也用它）。"""
    _client_log(message)


def service_status(timeout: float = CONNECT_TIMEOUT):
    """查询当前服务的状态（测试与排障用）；没有服务返回 None。"""
    found = _read_service_file(_fingerprint())
    if found is None:
        return None
    conn = _try_connect(*found)
    if conn is None:
        return None
    try:
        return conn.request({"cmd": "status"}, timeout=timeout)
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def shutdown_service(timeout: float = CONNECT_TIMEOUT) -> bool:
    """让**本构建**的服务退出（desktop 关闭时调用；测试收尾也用它）。

    只动自己指纹的服务——开发版与正式版可同时存在，互不驱逐。
    """
    found = _read_service_file(_fingerprint())
    if found is None:
        return False
    conn = _try_connect(*found)
    if conn is None:
        return False
    try:
        resp = conn.request({"cmd": "shutdown"}, timeout=timeout)
        return bool(resp.get("ok"))
    except Exception:  # noqa: BLE001
        return False
    finally:
        conn.close()


def _main() -> int:
    """`python -m functions.yolo_service` 入口。"""
    return serve()


if __name__ == "__main__":
    sys.exit(_main())
