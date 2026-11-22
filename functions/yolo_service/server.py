# -*- coding: utf-8 -*-
"""常驻服务进程：监听回环端口、处理请求、写发现文件。"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback

import utils

from functions.yolo_service.common import (
    _fingerprint,
    _log,
    _rotate_log_if_huge,
    _ttl_seconds,
    log_file,
    service_file,
)
from functions.yolo_service.priority import _boost_priority


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
    """服务侧执行一次检测，返回 `(PageBoxes, model_load_seconds)`。

    ⚠️ 走的是与本进程内**完全相同**的入口 `functions.detect.detect_page_content`，
    并且用同一个 `utils.load_yolo_model()` 单例——服务化只改"模型住在哪个
    进程"，不改算法（含互斥消解），因此服务算出的框与本进程算出的必然一致。

    `page.full` 是整幅内容（fullcontent）的框；`page.notes` 带出互斥消解
    触发的规则说明（要回给客户端打日志）。

    `model_load_seconds` 只有**本次调用真的把模型加载起来**时才 > 0。调用方
    据此在日志里打出「加载 YOLO 模型完成: 用时 X s」——服务进程自己没有
    控制台，这行是唯一能让用户看到"模型确实加载了一次、之后都在复用"的途径。

    这里**必须**函数内延迟导入：`functions/detect.py` 在模块级 import 本模块的
    客户端，模块级互相 import 会成环。
    """
    from functions.detect import detect_page_content  # noqa: PLC0415

    img = utils.imread(image_path)
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")
    already = utils.is_model_loaded()
    started = time.perf_counter()
    model = utils.load_yolo_model()
    load_seconds = 0.0 if already else time.perf_counter() - started
    page = detect_page_content(img, model)
    return page, load_seconds


def _dispatch(request: dict, state: _ServiceState, fp: str) -> dict:
    """处理一条请求，返回应答字典。"""
    cmd = request.get("cmd")
    if cmd == "hello":
        if request.get("fp") != fp:
            # 指纹不匹配：多半是升级后残留的旧服务。只拒绝，**不自杀**——
            # 两个版本（开发版+正式版）可能同时开着，互相驱逐会打成死循环；
            # 旧服务就让它常驻（指纹不符没人连它，无害），想清走手动处理。
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
        # 真检测 = 用户在等结果：先把自己升回正常优先级再干活（见
        # _boost_priority；预热/空闲期的 BELOW_NORMAL 只影响加载与等待）
        _boost_priority()
        state.enter()
        try:
            page, load_seconds = _detect_file(str(request.get("image") or ""))
            return {
                "ok": True,
                "left": list(page.left) if page.left else None,
                "right": list(page.right) if page.right else None,
                "full": list(page.full) if page.full else None,
                # 互斥消解触发的规则说明（人读），客户端拿去打日志
                "notes": list(page.notes),
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
        _rotate_log_if_huge()  # 服务启动时轮转一次，避免日志无界增长
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
    """服务主循环：绑定回环端口、写发现文件、**默认常驻**（TTL 仅在显式
    设了 `GUJI_YOLO_TTL` 时生效）。返回进程退出码。"""
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
    ttl_text = "常驻" if ttl is None else f"{ttl:.0f}s"
    _log(f"服务已启动 port={port} pid={os.getpid()} ttl={ttl_text} fp={fp}")
    server.settimeout(1.0)
    stop = threading.Event()
    try:
        while not stop.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                # ⚠️ 默认 ttl=None＝常驻：模型加载一次就不再释放（用户口径），
                #    只有显式给了 GUJI_YOLO_TTL 才按空闲退出。
                if ttl is not None and state.idle_seconds() > ttl:
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
