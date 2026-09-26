# -*- coding: utf-8 -*-
"""JSON 持久化的原子性与健壮性（2026-09-26 审计发现两处）。

1. **临时文件名固定**（`x.json.tmp`）→ 两个进程同时写会互相截断
   单例守卫是**按构建目录**判定的，开发版与安装版会同时运行、共用
   `~/Documents/guji`（`desktop/single_instance.py` 的注释明说了）。固定名会让
   A 在 fsync 后、replace 前被 B 截断，`os.replace` 把**半截 JSON** 换成正式文件
   → 下次读取判为损坏、改名进 `*.corrupt-*` 并返回默认值 → 用户看到任务全没了。

2. **非法 UTF-8 没被当成损坏**：`read_json` 只捕获 `OSError` +
   `JSONDecodeError`，而 `UnicodeDecodeError` 是 `ValueError` 的子类、不是
   `OSError`，会一路穿透到调用它的 Qt 槽里（在事件处理中抛异常比"备份后返回
   默认值"糟糕得多）。
"""

NAME = "store_atomic"
DEPENDS: list[str] = []
TITLE = "JSON 持久化原子性"


def run(ctx) -> None:
    import json
    import os
    import threading
    from pathlib import Path

    from desktop.store.json_io import _tmp_path, read_json, write_json
    from tests.selftests._context import ok

    work = ctx.tmp / "store_atomic"
    work.mkdir(parents=True, exist_ok=True)

    # ---- 1. 临时文件名必须带 pid 与线程号 ----
    target = work / "tasks.json"
    name = _tmp_path(target).name
    ok("临时文件名带本进程 pid", str(os.getpid()) in name, name)
    ok("临时文件名带线程号", str(threading.get_ident()) in name, name)
    ok("临时文件与目标同目录（os.replace 才能原子）",
       _tmp_path(target).parent == target.parent, str(_tmp_path(target)))

    def other_pid_name() -> str:
        real = os.getpid
        try:
            os.getpid = lambda: real() + 1  # type: ignore[assignment]
            return _tmp_path(target).name
        finally:
            os.getpid = real  # type: ignore[assignment]

    ok("不同 pid 得到不同的临时文件名", other_pid_name() != name,
       f"{name} vs {other_pid_name()}")

    # ---- 2. 多线程并发写同一文件：落盘结果永远是可解析的完整 JSON ----
    payloads = [{"seq": i, "pad": "x" * 5000} for i in range(8)]
    stop = threading.Event()
    errors: list[str] = []

    def writer(payload):
        while not stop.is_set():
            try:
                write_json(target, payload)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")
                return

    threads = [threading.Thread(target=writer, args=(p,), daemon=True) for p in payloads]
    for t in threads:
        t.start()
    for _ in range(60):
        try:
            read_json(target, None)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"读崩了 {type(exc).__name__}: {exc}")
            break
    stop.set()
    for t in threads:
        t.join(timeout=2)
    ok("并发写期间不抛异常", not errors, str(errors[:2]))
    final = read_json(target, None)
    ok("并发写之后文件仍是完整 JSON（不是半截）",
       isinstance(final, dict) and final.get("seq") in range(8), repr(final)[:80])
    ok("没有把正式文件判成损坏（没有 *.corrupt-*）",
       not list(work.glob("*.corrupt-*")), str(list(work.glob("*.corrupt-*"))))

    # ---- 3. 非法 UTF-8 按损坏处理：备份 + 返回默认值，不抛异常 ----
    broken = work / "broken.json"
    broken.write_bytes(b'{"a": "\xff\xfe\xfd"}')
    try:
        got = read_json(broken, {"fallback": True})
    except Exception as exc:  # noqa: BLE001
        ok("非法 UTF-8 不抛异常（按损坏处理）", False, f"{type(exc).__name__}: {exc}")
    else:
        ok("非法 UTF-8 不抛异常（按损坏处理）", got == {"fallback": True}, repr(got))
        backups = list(work.glob("broken.json.corrupt-*"))
        ok("非法 UTF-8 的现场被备份保留", len(backups) == 1, str(backups))

    # ---- 4. 正常读写仍是幂等的 ----
    write_json(target, {"ok": 1})
    ok("普通写入后能原样读回", read_json(target, None) == {"ok": 1})
    ok("父目录不存在时拒绝写入（不越界造目录）",
       _rejects(write_json, work / "nope" / "x.json", {"a": 1}))


def _rejects(fn, *args) -> bool:
    try:
        fn(*args)
    except FileNotFoundError:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False
