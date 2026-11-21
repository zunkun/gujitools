# -*- coding: utf-8 -*-
"""崩溃转储：进程自己把现场写下来（**仅 Windows**）。

和 :mod:`utils.crash_log` 的分工：那边管「日志 + faulthandler（Python 栈）」，
这边管「原生栈 + 一份 minidump」。为什么自己做：这台机器上 WER ``LocalDumps``
实测不落盘（配好了也不出文件），而崩溃发生在 Qt 的 C++ 里——光有 Python 栈
不够，必须知道**掉在哪个模块的哪个偏移、调用链上有谁**。

做法（全部 ctypes，不引第三方库）：

1. ``SetUnhandledExceptionFilter`` 挂一个顶层异常过滤器；
2. 过滤器里读异常码 / 出错地址 / ``Rip`` ``Rsp`` ``Rcx``，把地址换算成
   ``模块名+偏移``（枚举模块 + 大小）；再从栈顶往下扫若干 KB，把落在模块里的
   返回地址挑出来，依次换算 —— 这就是一份**不带符号的原生调用链**，配合导出表
   就能查（``tools/`` 里那个 PE 解析脚本干的就是这事）；
3. ``MiniDumpWriteDump`` 落一份 ``MiniDumpNormal | WithThreadInfo`` 的小 dump；
4. 最后把过滤器链交给**上一个**过滤器（= faulthandler），所以 Python 各线程的
   栈照旧会写进 ``crash.log``。

⚠️ 安装顺序有讲究：先 :func:`utils.crash_log.install`（faulthandler），再调
本模块。反过来的话 faulthandler 覆盖掉过滤器、且不会回调我们，dump 就没了。
⚠️ 过滤器里**只做读写文件**这类安全动作，任何异常都吞掉并返回
``EXCEPTION_CONTINUE_SEARCH``，绝不能因为它自己再崩一次。
"""

from __future__ import annotations

import ctypes
import os
import struct
import sys
import time
from ctypes import wintypes
from pathlib import Path

from utils.crash_log import log

#: 栈扫描上限：够了（正常调用深度几百字节，Qt 回调链偶尔几 KB）
STACK_SCAN_BYTES = 256 * 1024
#: 报告里最多列多少层返回地址
MAX_FRAMES = 48

_EXCEPTION_CONTINUE_SEARCH = 1

_busy = False
_filter_ref = None
_prev_filter = None
_out_dir: Path | None = None

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi")
_dbghelp = None  # 懒加载：只有真要写 dump 时才碰它


class _EXCEPTION_RECORD(ctypes.Structure):
    _fields_ = [
        ("ExceptionCode", wintypes.DWORD),
        ("ExceptionFlags", wintypes.DWORD),
        ("ExceptionRecord", ctypes.c_void_p),
        ("ExceptionAddress", ctypes.c_void_p),
        ("NumberParameters", wintypes.DWORD),
        ("ExceptionInformation", ctypes.c_uint64 * 15),
    ]


class _EXCEPTION_POINTERS(ctypes.Structure):
    _fields_ = [
        ("ExceptionRecord", ctypes.POINTER(_EXCEPTION_RECORD)),
        ("ContextRecord", ctypes.c_void_p),
    ]


class _MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


# ⚠️ 句柄与指针必须显式声明 argtypes/restype：默认按 ``int`` 传会把 64 位句柄
#    截成 32 位（``GetCurrentProcess()`` 返回 -1，截断后 EnumProcessModules 直接
#    失败、模块枚举恒为空）。这里一次性写清楚，别靠猜。
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
_k32.ReadProcessMemory.restype = wintypes.BOOL
_psapi.EnumProcessModules.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
_psapi.EnumProcessModules.restype = wintypes.BOOL
_psapi.GetModuleInformation.argtypes = [
    wintypes.HANDLE, wintypes.HMODULE, ctypes.POINTER(_MODULEINFO),
    wintypes.DWORD,
]
_psapi.GetModuleInformation.restype = wintypes.BOOL
_psapi.GetModuleFileNameExW.argtypes = [
    wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD,
]
_psapi.GetModuleFileNameExW.restype = wintypes.DWORD


#: x64 ``CONTEXT`` 里我们关心的字段偏移（结构体太大，只按偏移取值）
_CTX_RCX = 128
_CTX_RSP = 152
_CTX_RBP = 160
_CTX_RIP = 248

_FILTER = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.c_void_p)


def _u64(raw: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", raw, offset)[0]


def _read_mem(addr: int, size: int) -> bytes:
    """读自己进程的内存，**分小块读**，读到栈顶就停。

    ⚠️ 两个坑（2026-11-21 实测）：
    ① 整段一次读会**整段失败**——从 ``rsp`` 往上 256KB 早就越过栈顶了，Windows
       直接拒绝，返回空 ⇒ 一个返回地址都扫不到；
    ② 块也不能大：栈顶附近可读窗口常常只有 1~3KB（浅栈就是几帧），块开 4KB
       同样整块失败。用 1KB 一块、遇到读不动就收工，拿到的部分就是**调用链所在
       的那段栈**。
    """
    if not addr or size <= 0:
        return b""
    handle = _k32.GetCurrentProcess()
    out = bytearray()
    chunk = 1024
    while len(out) < size:
        want = min(chunk, size - len(out))
        buf = ctypes.create_string_buffer(want)
        got = ctypes.c_size_t(0)
        ok = _k32.ReadProcessMemory(
            handle, ctypes.c_void_p(addr + len(out)),
            buf, want, ctypes.byref(got))
        if not ok or got.value == 0:
            break
        out.extend(buf.raw[:got.value])
        if got.value < want:
            break
    return bytes(out)


def _modules() -> list[tuple[int, int, str]]:
    """``[(基址, 大小, 文件名)]``，按基址排序。"""
    handle = _k32.GetCurrentProcess()
    needed = wintypes.DWORD(0)
    arr = (wintypes.HMODULE * 1024)()
    if not _psapi.EnumProcessModules(handle, arr, ctypes.sizeof(arr),
                                     ctypes.byref(needed)):
        return []
    count = min(len(arr), needed.value // ctypes.sizeof(ctypes.c_void_p))
    out: list[tuple[int, int, str]] = []
    for i in range(count):
        mod = arr[i]
        info = _MODULEINFO()
        if not _psapi.GetModuleInformation(handle, mod, ctypes.byref(info),
                                           ctypes.sizeof(info)):
            continue
        buf = ctypes.create_unicode_buffer(512)
        _psapi.GetModuleFileNameExW(handle, mod, buf, len(buf))
        base = int(info.lpBaseOfDll or 0)
        out.append((base, int(info.SizeOfImage), os.path.basename(buf.value)))
    out.sort()
    return out


def _where(modules: list[tuple[int, int, str]], addr: int) -> str:
    """地址 → ``模块+0x偏移``（查不到就原样给十六进制）。"""
    if not addr:
        return "0x0"
    for base, size, name in modules:
        if base <= addr < base + size:
            return f"{name}+0x{addr - base:x}"
    return f"0x{addr:x}（不属于任何已加载模块）"


def _scan_stack(modules: list[tuple[int, int, str]], rsp: int,
                skip: tuple[int, ...] = ()) -> tuple[list[str], int]:
    """扫栈：返回 ``(调用链候选, 实际读到的字节数)``。

    只挑「落在某个已加载模块里」的值当返回地址——不引符号表，但配合导出表
    （``工具: _scratch/pe_rva.py`` 那类解析）足以把崩溃从"Qt6Gui+0x…"推进到
    "谁调了它"。读到的字节数一并返回：为 0 说明连栈都没读到，别误以为没调用链。
    """
    frames: list[str] = []
    seen: set[int] = set(skip)
    raw = _read_mem(rsp, STACK_SCAN_BYTES)
    for offset in range(0, len(raw) - 8, 8):
        value = _u64(raw, offset)
        if value in seen:
            continue
        for base, size, name in modules:
            if base <= value < base + size:
                seen.add(value)
                frames.append(f"  [栈 +0x{offset:05x}] "
                              f"{name}+0x{value - base:x}")
                break
        if len(frames) >= MAX_FRAMES:
            break
    return frames, len(raw)


def _stack_frames(modules: list[tuple[int, int, str]], rsp: int,
                  skip: tuple[int, ...] = ()) -> list[str]:
    """只要调用链候选（报告与自测用；诊断需要的字节数见 :func:`_scan_stack`）。"""
    return _scan_stack(modules, rsp, skip)[0]


def _write_minidump(path: Path, exc_ptr: int) -> str:
    """落一份小 dump；返回一句结果说明（失败不抛）。"""
    global _dbghelp
    try:
        if _dbghelp is None:
            _dbghelp = ctypes.WinDLL("dbghelp")
            # 句柄一律走 wintypes.HANDLE：不声明 argtypes 的话 64 位句柄会被
            # 按 int 传（实测 MiniDumpWriteDump 因此返回失败、文件 0 字节）。
            _dbghelp.MiniDumpWriteDump.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ]
            _dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL
        import msvcrt

        # 先写到临时名，成功再改名：失败时别在目录里留一个 0 字节的假 dump
        temp = path.with_suffix(path.suffix + ".part")
        with open(temp, "wb") as fh:
            handle = msvcrt.get_osfhandle(fh.fileno())
            ok = _dbghelp.MiniDumpWriteDump(
                _k32.GetCurrentProcess(), os.getpid(),
                wintypes.HANDLE(handle),
                0x00000000 | 0x00001000,  # MiniDumpNormal | MiniDumpWithThreadInfo
                None, None, None)
            if not ok:
                err = ctypes.get_last_error()
                fh.close()
                try:
                    temp.unlink()
                except OSError:
                    pass
                return f"MiniDumpWriteDump 失败（err={err}）"
        os.replace(temp, path)
        return f"已写入 {path.name}（{path.stat().st_size} 字节）"
    except Exception as exc:  # noqa: BLE001 - 转储失败也要把报告写完
        return f"MiniDumpWriteDump 异常：{exc}"


def _on_exception(exc_ptr) -> int:  # noqa: ANN001 - Windows 过滤器签名
    global _busy
    if _busy:  # 自己再崩就直接让系统接手，不做递归
        return _EXCEPTION_CONTINUE_SEARCH
    _busy = True
    try:
        pointers = ctypes.cast(exc_ptr, ctypes.POINTER(_EXCEPTION_POINTERS))
        record = pointers.contents.ExceptionRecord.contents
        code = int(record.ExceptionCode)
        fault = int(record.ExceptionAddress or 0)
        raw_ctx = _read_mem(int(pointers.contents.ContextRecord or 0), 256)
        rip = _u64(raw_ctx, _CTX_RIP) if len(raw_ctx) >= _CTX_RIP + 8 else 0
        rsp = _u64(raw_ctx, _CTX_RSP) if len(raw_ctx) >= _CTX_RSP + 8 else 0
        rbp = _u64(raw_ctx, _CTX_RBP) if len(raw_ctx) >= _CTX_RBP + 8 else 0
        rcx = _u64(raw_ctx, _CTX_RCX) if len(raw_ctx) >= _CTX_RCX + 8 else 0

        modules = _modules()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        stem = f"crash_{stamp}_pid{os.getpid()}"
        target_dir = _out_dir or Path(".")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        lines = [
            f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"进程：pid={os.getpid()}  exe={sys.executable}",
            f"异常：0x{code:08x}（{_explain(code)}）",
            f"出错地址：{_where(modules, fault)}  rip={_where(modules, rip)}",
            f"寄存器：rsp=0x{rsp:x} rbp=0x{rbp:x} rcx=0x{rcx:x}",
            "",
            "调用链候选（从栈顶往上扫，只挑落在模块里的值：",
            "第一个通常就是出错函数，往后是它的调用者）：",
        ]
        frames, scanned = _scan_stack(modules, rsp, skip=(rip,))
        lines.append(f"（栈扫了 {scanned} 字节；0 表示栈都读不到，"
                     f"不是「没有调用链」）")
        lines.extend(frames)
        try:
            from utils.crash_log import tail

            last = tail(40)
            if last:
                lines.extend(["", "—— crash.log 末尾 ——", last])
        except Exception:  # noqa: BLE001
            pass

        report = target_dir / f"{stem}.txt"
        try:
            report.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log(f"崩溃现场已写盘：{report.name}")
        except OSError as exc:
            log(f"崩溃报告写不进（{report}）：{exc}")

        dump_note = _write_minidump(target_dir / f"{stem}.dmp", exc_ptr)
        log(f"崩溃转储：{dump_note}")
    except Exception as exc:  # noqa: BLE001 - 过滤器里绝不能再炸
        try:
            log(f"崩溃取证自身出错：{exc}")
        except Exception:  # noqa: BLE001
            pass
    finally:
        _busy = False

    # 交给上一个过滤器（= faulthandler），让 Python 各线程的栈也写进日志
    if _prev_filter is not None:
        try:
            return _prev_filter(exc_ptr)
        except Exception:  # noqa: BLE001
            pass
    return _EXCEPTION_CONTINUE_SEARCH


def _explain(code: int) -> str:
    return {
        0xC0000005: "访问违例（空指针/野指针/已释放内存）",
        0xC000001D: "非法指令",
        0xC0000094: "整数除零",
        0xC00000FD: "栈溢出",
        0xC0000409: "快速失败（__fastfail）",
        0xC000041D: "用户回调中的未处理异常",
        0xC0000374: "堆损坏",
    }.get(code, "未知")


def install(directory: str | Path) -> bool:
    """挂上异常过滤器，返回是否成功（**绝不抛**，失败只记日志）。

    ⚠️ 必须在 :func:`utils.crash_log.install` **之后**调用：本模块会把上一个
    过滤器串在末尾，顺序反了就拿不到 Python 栈。
    """
    global _filter_ref, _prev_filter, _out_dir

    if sys.platform != "win32":
        return False
    if _filter_ref is not None:
        return True  # 幂等

    try:
        _out_dir = Path(directory).expanduser()
        _out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"崩溃转储目录不可用（{directory}）：{exc}")
        return False

    try:
        _filter_ref = _FILTER(_on_exception)
        previous = _k32.SetUnhandledExceptionFilter(_filter_ref)
        _prev_filter = ctypes.cast(previous, _FILTER) if previous else None
        log(f"崩溃转储已就位（目录 {_out_dir}）")
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"崩溃转储挂钩失败：{exc}")
        _filter_ref = None
        return False
