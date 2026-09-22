# -*- coding: utf-8 -*-
"""常驻 YOLO 服务：**desktop 侧**多次检测共用同一份已加载的模型。

## 归属：只属于 desktop，CLI 不用

原则（用户定）：**cli 与 desktop 是两套系统，内存不互通**。

- **desktop**：GUI 每点一次「检测」都是新的 worker 子进程，进程一退模型就没了，
  下一次又从头付一遍——所以模型放进这里这个常驻进程，desktop 的多次执行共用，
  空闲 `TTL`（默认 5 分钟）没人用就自行退出、把约 350MB 还给系统。
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
（多半是升级后残留的旧服务）忽略并另起一个，旧的靠 TTL 自灭——**不做互相驱逐**，
免得两个版本互相杀。

服务端**允许并发连接**（每个客户端线程一条）：desktop 的批量检测本来就是
多线程共享一个模型并发推理，服务里也必须保持同样的并发度，否则等于把并行度
砍成 1。模型加载本身仍然只做一次（双重检查锁在 `yolo_utils` 里）。
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import NamedTuple

import utils

#: 服务发现文件（按用户临时目录）。⚠️ 文件名带**指纹**：
#: 开发版与正式版可能在同一台机器上同时跑（单例按构建区分），两者的权重路径
#: 不同 → 指纹不同 → 各用各的发现文件，互不覆盖。否则两边会互相改写同一个
#: 文件，另一方读到的端口不是自己的服务，就被迫重拉一个新服务、无限往复。
SERVICE_FILE_PREFIX = "guji-yolo-service-"

#: 空闲多久没人用就退出（秒）。可用环境变量覆盖——测试用一个很小的值来验。
DEFAULT_TTL_SECONDS = 300.0

#: 建连与握手超时（秒）
CONNECT_TIMEOUT = 3.0
#: 单次检测的等待上限（秒）。首张图要等 torch 导入 + 载模型（约 5.5s），
#: 之后每张一两百毫秒；给足余量避免大图/慢机器上误判超时。
DETECT_TIMEOUT = 300.0
#: 拉起服务后，最多等它多久可用（秒）
SPAWN_WAIT = 25.0

#: 直连成功后的连接缓存：**按线程**存。CLI 的 detect 用 8 个线程并发推理，
#: 若共用一个连接就会被客户端串行化，等于把并行度砍掉。
_local = threading.local()
_spawn_lock = threading.Lock()
#: 本进程内已确认服务不可用 —— 之后不再尝试（避免每次检测都白等一次超时）
_given_up = False


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


def _ttl_seconds() -> float:
    """空闲 TTL（秒）。环境变量 `GUJI_YOLO_TTL` 可覆盖，下限 5 秒。"""
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
    return Path(__file__).resolve().parents[1]


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


def _log(message: str) -> None:
    """追加一行到服务日志（服务进程专用；失败不抛）。"""
    try:
        with open(log_file(), "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def _client_log(message: str) -> None:
    """客户端侧的诊断信息也写同一份日志，便于把两侧串起来看。"""
    _log(f"[client {os.getpid()}] {message}")


# --------------------------------------------------------------------- 服务端
class _ServiceState:
    """服务运行状态：空闲判定与外发统计。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()
        self._inflight = 0
        self.served = 0

    def touch(self) -> None:
        with self._lock:
            self._last_activity = time.monotonic()

    def enter(self) -> None:
        with self._lock:
            self._inflight += 1
            self._last_activity = time.monotonic()

    def exit(self) -> None:
        with self._lock:
            self._inflight -= 1
            self._last_activity = time.monotonic()
            self.served += 1

    def idle_seconds(self) -> float:
        with self._lock:
            if self._inflight > 0:
                return 0.0
            return time.monotonic() - self._last_activity


def _detect_file(image_path: str):
    """服务侧执行一次检测，返回 `(left, right, model_load_seconds)`。

    ⚠️ 走的是与本进程内**完全相同**的入口 `functions.detect.detect_page_boxes`，
    并且用同一个 `utils.load_yolo_model()` 单例——服务化只改"模型住在哪个
    进程"，不改算法，因此服务算出的框与本进程算出的必然一致。

    `model_load_seconds` 只有**本次调用真的把模型加载起来**时才 > 0。调用方
    据此在日志里打出「加载 YOLO 模型完成: 用时 X s」——服务进程自己没有
    控制台，这行是唯一能让用户看到"模型确实加载了一次、之后都在复用"的途径。

    这里**必须**函数内延迟导入：`functions/detect.py` 在模块级 import 本模块的
    客户端，模块级互相 import 会成环。
    """
    from functions.detect import detect_page_boxes  # noqa: PLC0415

    img = utils.imread(image_path)
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")
    already = utils.is_model_loaded()
    started = time.perf_counter()
    model = utils.load_yolo_model()
    load_seconds = 0.0 if already else time.perf_counter() - started
    left, right = detect_page_boxes(img, model)
    return left, right, load_seconds


def _dispatch(request: dict, state: _ServiceState, fp: str) -> dict:
    """处理一条请求，返回应答字典。"""
    cmd = request.get("cmd")
    if cmd == "hello":
        if request.get("fp") != fp:
            # 指纹不匹配：多半是升级后残留的旧服务。只拒绝，**不自杀**——
            # 两个版本互相驱逐会打成死循环，让 TTL 自然收走它。
            return {
                "ok": False,
                "error": "fingerprint-mismatch",
                "fp": fp,
                "service_pid": os.getpid(),
            }
        return {
            "ok": True,
            "fp": fp,
            "service_pid": os.getpid(),
            "model_loaded": utils.is_model_loaded(),
        }
    if cmd == "warmup":
        # 把「确保模型就绪」做成独立的一步，好让这笔开销被**单独计时**。
        # 否则它会落在"第一张图"的耗时里，看起来像某一张特别慢（用户提过这点）。
        was_loaded = utils.is_model_loaded()
        utils.load_yolo_model()
        seconds = 0.0 if was_loaded else utils.load_seconds_used()
        return {
            "ok": True,
            "backend": "service",
            "model_load_seconds": round(seconds, 3),
            "model_loaded": True,
        }
    if cmd == "status":
        return {
            "ok": True,
            "fp": fp,
            "service_pid": os.getpid(),
            "model_loaded": utils.is_model_loaded(),
            "served": state.served,
            "idle": round(state.idle_seconds(), 1),
        }
    if cmd == "detect":
        state.enter()
        try:
            left, right, load_seconds = _detect_file(str(request.get("image") or ""))
            return {
                "ok": True,
                "left": list(left) if left else None,
                "right": list(right) if right else None,
                "model_loaded": utils.is_model_loaded(),
                "model_load_seconds": round(load_seconds, 3),
            }
        except Exception as exc:  # noqa: BLE001 - 回报给客户端，由它决定回落
            # 服务是分离进程、没有控制台，只记一行 message 会让偶发失败无从排查；
            # 完整堆栈进服务日志（`%TEMP%/guji-yolo-service.log`）。
            _log(
                f"检测失败 image={request.get('image')!r}: "
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            )
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            state.exit()
    if cmd == "shutdown":
        return {"ok": True}
    return {"ok": False, "error": f"未知指令: {cmd}"}


def _write_json_line(writer, payload: dict) -> None:
    writer.write(json.dumps(payload, ensure_ascii=False) + "\n")
    writer.flush()


def _serve_connection(conn: socket.socket, state: _ServiceState, fp: str,
                      stop: threading.Event) -> None:
    """一条客户端连接：逐行读请求、逐行回应答，直到对端关闭或要求停服。"""
    try:
        conn.settimeout(None)
        reader = conn.makefile("r", encoding="utf-8", newline="\n")
        writer = conn.makefile("w", encoding="utf-8", newline="\n")
        try:
            for line in reader:
                line = line.strip()
                if not line:
                    continue
                state.touch()
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    _write_json_line(writer, {"ok": False, "error": "无法解析的请求"})
                    continue
                _write_json_line(writer, _dispatch(request, state, fp))
                if request.get("cmd") == "shutdown":
                    stop.set()
                    break
        finally:
            try:
                reader.close()
                writer.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001 - 单条连接出错不该拖垮服务
        _log(f"连接处理异常：{type(exc).__name__}: {exc}")
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _redirect_stdio_to_log() -> None:
    """把服务的 stdout/stderr 重定向到日志文件。

    服务是分离进程、没有控制台（且可能由 console 版 exe 启动），`print` 既没处
    去、又可能因 `sys.stdout is None` 直接抛异常。重定向后 `load_yolo_model()`
    那行「加载 YOLO 模型: …」正好成为"服务侧只加载一次"的证据。
    """
    try:
        fh = open(log_file(), "a", encoding="utf-8", buffering=1)
    except OSError:
        try:
            fh = open(os.devnull, "w", encoding="utf-8")
        except OSError:
            return
    for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
        try:
            setattr(sys, name, fh)
        except Exception:  # noqa: BLE001
            pass


def serve() -> int:
    """服务主循环：绑定回环端口、写发现文件、按 TTL 空闲自退。返回进程退出码。"""
    _redirect_stdio_to_log()
    state = _ServiceState()
    fp = _fingerprint()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(16)
    except OSError as exc:
        _log(f"启动失败（无法绑定回环端口）：{exc}")
        return 1

    port = server.getsockname()[1]
    _write_service_file(port, fp)
    ttl = _ttl_seconds()
    _log(f"服务已启动 port={port} pid={os.getpid()} ttl={ttl:.0f}s fp={fp}")
    server.settimeout(1.0)
    stop = threading.Event()
    try:
        while not stop.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                if state.idle_seconds() > ttl:
                    _log(f"空闲 {state.idle_seconds():.0f}s 超过 TTL {ttl:.0f}s，退出释放内存")
                    break
                continue
            except OSError:
                break
            state.touch()
            threading.Thread(
                target=_serve_connection,
                args=(conn, state, fp, stop),
                daemon=True,
            ).start()
    finally:
        try:
            server.close()
        finally:
            _remove_service_file(port, fp)
            _log("服务已退出")
    return 0


def _write_service_file(port: int, fp: str) -> None:
    """原子写发现文件（先写临时文件再替换，避免客户端读到半截 JSON）。"""
    payload = {"port": int(port), "fp": fp, "pid": os.getpid()}
    target = service_file(fp)
    try:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        _log(f"写发现文件失败：{exc}")


def _remove_service_file(port: int, fp: str) -> None:
    """退出时清掉发现文件 —— 只清**还指向自己**的那份，别误删别的构建的。"""
    target = service_file(fp)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if int(data.get("port", -1)) == int(port):
        try:
            target.unlink()
        except OSError:
            pass


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
        subprocess.Popen(command, **kwargs)
        _client_log(f"已拉起服务：{' '.join(command)}")
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
    """

    left: tuple | None
    right: tuple | None
    model_load_seconds: float


def service_in_use() -> bool:
    """本线程是否已经在用常驻服务（日志里说明"模型住在哪"用）。"""
    return getattr(_local, "client", None) is not None


def detect_boxes_via_service(image_path, area: int = 1) -> ServiceDetect | None:
    """把一张图交给常驻服务检测，返回 :class:`ServiceDetect`。

    **`None` 表示"这次没走成服务"**（服务关着、拉不起来、连不上、协议错、
    服务端报错都算），调用方应当回落到本进程内加载模型。注意它与"服务算完
    但没检到框"不同——后者返回 ``ServiceDetect(None, None, 0.0)``。

    `area` 只为兼容调用方签名保留：整页模式（area=4）在上层就已分流、根本不会
    走到这里，因此服务协议里不带它。
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
