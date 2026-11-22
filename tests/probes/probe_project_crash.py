# -*- coding: utf-8 -*-
"""完整项目崩溃探针：启动源码、源码构建、安装版，并跑全量 GUI 自测。

用法::

    python tests/probes/probe_project_crash.py
    python tests/probes/probe_project_crash.py --quick
    python tests/probes/probe_project_crash.py --runs 5 --timeout 15

脚本只做证据收集，不把超时和正常结束混成崩溃：
1. 安装版/产物/源码各启动多次；
2. 原生崩溃报告目录里是否新增 crash*.txt/.dmp；
3. crash.log 是否新增 Windows fatal exception 或看门狗 [stall]；
4. 默认再跑一次 GUI 全量自测；
5. --with-smoke 再跑 dist 冒烟测试（真实 CLI + GUI）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
LOG_DIR: Path = Path.home() / "Documents" / "guji" / "logs"
PYTHON: Path = Path(sys.executable)


def snapshot_crashes() -> tuple[set[Path], int]:
    if not LOG_DIR.is_dir():
        return set(), 0
    reports = {
        path for pattern in ("crash_*.txt", "crash_*.dmp")
        for path in LOG_DIR.glob(pattern)
    }
    log = LOG_DIR / "crash.log"
    try:
        size = log.stat().st_size
    except OSError:
        size = 0
    return reports, size


def changed_crashes(
    before_reports: set[Path],
    before_size: int,
) -> tuple[list[Path], str]:
    new_reports = []
    if LOG_DIR.is_dir():
        reports = {
            path for pattern in ("crash_*.txt", "crash_*.dmp")
            for path in LOG_DIR.glob(pattern)
        }
        new_reports = sorted(reports - before_reports)

    log = LOG_DIR / "crash.log"
    tail = ""
    try:
        if log.stat().st_size >= before_size:
            with log.open("rb") as stream:
                stream.seek(before_size)
                tail = stream.read().decode("utf-8", "replace")
    except OSError:
        pass
    return new_reports, tail


def run_process(
    label: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout_s: float,
) -> tuple[str, int | None, str]:
    before_reports, before_size = snapshot_crashes()
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=10)
    elapsed = time.monotonic() - started
    new_reports, log_tail = changed_crashes(before_reports, before_size)
    combined = (stdout or b"").decode("utf-8", "replace") + \
        (stderr or b"").decode("utf-8", "replace")

    native_crash = (
        proc.returncode in (-1073741819, -1073740791, 3221225477)
        or bool(new_reports)
        or "Windows fatal exception" in log_tail
        or "[stall]" in log_tail
    )
    if timed_out:
        state = "超时后已终止（不是崩溃）"
    elif native_crash:
        state = "疑似原生崩溃"
    else:
        state = "正常退出"
    print(
        f"  [{state}] {label} "
        f"退出码={proc.returncode} 耗时={elapsed:.1f}s "
        f"新增现场={len(new_reports)}"
    )
    if new_reports:
        for path in new_reports:
            print(f"    现场：{path}")
    return state, proc.returncode, combined


def source_gui_command() -> list[str]:
    return [str(PYTHON), str(PROJECT_ROOT / "desktop.py")]


def installed_candidates() -> list[tuple[str, Path]]:
    candidates = []
    dist = PROJECT_ROOT / "dist" / "guji" / "guji-desktop.exe"
    installed = Path.home() / "AppData" / "Local" / "Programs" / "guji" / "guji-desktop.exe"
    if dist.is_file():
        candidates.append(("dist 产物", dist))
    if installed.is_file():
        candidates.append(("本地安装版", installed))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--with-smoke", action="store_true")
    args = parser.parse_args()

    runs = max(1, args.runs)
    failures: list[str] = []
    print("== 项目崩溃探针 ==")
    print(f"项目版本：{PROJECT_ROOT / 'config.py'}")
    print(f"崩溃现场目录：{LOG_DIR}")

    print("\n== 多次启动 ==")
    for run_index in range(1, runs + 1):
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONUTF8"] = "1"
        env["GUJI_GUI_SELFTEST"] = "1"

        state, code, output = run_process(
            f"源码 #{run_index}",
            source_gui_command(),
            PROJECT_ROOT,
            env,
            args.timeout,
        )
        if state != "正常退出":
            failures.append(f"源码启动 #{run_index}: {state}, exit={code}")

        for label, exe in installed_candidates():
            state, code, output = run_process(
                f"{label} #{run_index}",
                [str(exe)],
                PROJECT_ROOT,
                env,
                args.timeout,
            )
            if state != "正常退出":
                failures.append(f"{label} #{run_index}: {state}, exit={code}")

    if not args.quick:
        print("\n== 全量 GUI 自测 ==")
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONUTF8"] = "1"
        before_reports, before_size = snapshot_crashes()
        proc = subprocess.run(
            [str(PYTHON), str(PROJECT_ROOT / "tests" / "gui_selftest.py")],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1200,
        )
        new_reports, log_tail = changed_crashes(before_reports, before_size)
        suite_ok = proc.returncode == 0 and not new_reports and \
            "Windows fatal exception" not in log_tail and "[stall]" not in log_tail
        print(f"  [{'PASS' if suite_ok else 'FAIL'}] 全量 GUI 自测 exit={proc.returncode}")
        if new_reports:
            print("  新增原生现场：")
            for path in new_reports:
                print(f"    {path}")
        if not suite_ok:
            tail = (proc.stdout or "")[-2000:] + "\n" + (proc.stderr or "")[-2000:]
            failures.append("全量 GUI 自测失败")
            print(tail)

    if args.with_smoke:
        print("\n== frozen 产物冒烟 ==")
        proc = subprocess.run(
            [str(PYTHON), str(PROJECT_ROOT / "tools" / "smoke_frozen.py")],
            cwd=str(PROJECT_ROOT),
            env=dict(os.environ, PYTHONUTF8="1"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1200,
        )
        print(f"  [{'PASS' if proc.returncode == 0 else 'FAIL'}] smoke_frozen exit={proc.returncode}")
        if proc.returncode != 0:
            failures.append("frozen 产物冒烟失败")
            print(((proc.stdout or "")[-4000:] + "\n" + (proc.stderr or "")[-2000:]))

    print("\n== 结论 ==")
    if failures:
        for failure in failures:
            print(f"  [FAIL] {failure}")
        print("本轮未证明安全：请检查新增 crash*.txt/.dmp 和 crash.log。")
        return 1
    print("  [PASS] 未检测到原生崩溃或多启动失败")
    print("  说明：这不能证明所有人工交互都安全；还应执行拼版、切任务、息屏唤醒压力。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
