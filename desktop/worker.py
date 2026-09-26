"""Process entry for one GUI stage task (worker 子进程统一入口)。

The worker emits JSON Lines on stdout so the GUI remains independent from
heavy libraries. 阶段执行器按职责拆分在 desktop/stages/ 包：

- desktop.stages.events        事件输出 + print 拦截/进度解析
- desktop.stages.detect_stage  detect（YOLO 文本框检测）
- desktop.stages.generic_stage 通用 CLI 阶段 + extract 渲染
- desktop.stages.print_stage   print（效果图合成 + 生成 PDF）
- desktop.stages.rembg_stage   rembg_submit（最终图片合成）

本文件只负责进程初始化与阶段路由。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 阶段执行器重导出：保持 `from desktop.worker import run_stage` 等旧引用可用。
#
# ⚠️ 为什么要包一层（2026-09-26 审计）：**import 期**失败（缺 DLL、依赖没打进产物、
#    PySide6 插件缺失、torch 加载不了）会让进程在"做任何事之前"就死掉——stdout 一条
#    事件都没有，GUI 只能显示「退出码 1」，用户与我们都无从查起。这里先把异常记下来，
#    由 main() 转成 error 事件 + stderr 堆栈（_emit_fatal 只依赖 stdlib 与延迟导入的
#    events.emit，所以它自己不会因为同一批依赖挂掉）。
try:
    from desktop.stages import (  # noqa: F401
        run_detect,
        run_detect_stage,
        run_extract_stage,
        run_print_stage,
        run_rembg_submit_stage,
        run_stage,
    )
except BaseException as _exc:  # noqa: BLE001 - 连 import 失败都要能被看见
    _IMPORT_ERROR: BaseException | None = _exc
else:
    _IMPORT_ERROR = None


def _emit_fatal(exc: BaseException) -> None:
    """把「还没进到任何阶段就崩了」也变成一个 GUI 能看见的 error 事件。

    ⚠️ 为什么必须做（2026-09-26 审计）
        worker 的数据通道是 stdout 上的 JSON Lines 事件。而 `--config` 读不到、
        JSON 解析失败、config 不是 dict（`config.get` AttributeError）、argparse
        报错、stage 路由函数在自己 try 之前抛异常 —— 这些都发生在**任何阶段函数
        之前**，于是 stdout 一条事件都没有：GUI 只能显示「退出码 1」，用户完全
        不知道出了什么事，历史记录里连原因都没有。
        更要命的是 frozen 且窗口化时 `sys.stderr` 可能是 `None`，Python 默认
        excepthook 写的 traceback 会被**静默丢弃**。

        所以兜两层：① 尽力发一条 error 事件（走 events.emit 的 fd 兜底）；
        ② 尽力把 traceback 写进 stderr，让 GUI 的 `[stderr]` 通道也能看到。
    """
    import traceback

    detail = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    message = f"子任务进程启动失败：{type(exc).__name__}: {exc}"
    try:
        from desktop.stages.events import emit

        emit({"type": "error", "message": message})
    except BaseException:  # noqa: BLE001 - 连事件都发不出去就只能靠 stderr
        pass
    for stream in (getattr(sys, "__stderr__", None), sys.stderr):
        if stream is None:
            continue
        try:
            stream.write(detail)
            stream.flush()
            break
        except BaseException:  # noqa: BLE001
            continue


def _prepare_process() -> None:
    """进程级初始化：faulthandler + 统一 UTF-8。"""
    import faulthandler

    # 仅在进程真正崩溃（段错误等）时转储堆栈；
    # 不使用 dump_traceback_later —— print 等长任务合法运行时间可能远超 20s，
    # 定时退出会误杀正常子进程。
    faulthandler.enable()
    # Windows 下子进程默认继承 GBK 控制台编码，统一为 UTF-8，
    # 保证与 GUI 的 JSON Lines 协议一致，并兼容 CLI 输出中的 emoji。
    for stream in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _run() -> int:
    """读 --config 并按阶段路由执行（main 的 except 负责兜住启动期异常）。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help="GUI 子进程入口标记")
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args()
    config = json.loads(options.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"worker 配置必须是 JSON 对象，实际是 {type(config).__name__}")
    if config.get("mode") == "detect":
        return run_detect(config)
    if config.get("stage") == "detect":
        return run_detect_stage(config)
    if config.get("stage") == "extract":
        return run_extract_stage(config)
    if config.get("stage") == "print":
        return run_print_stage(config)
    if config.get("stage") == "rembg_submit":
        return run_rembg_submit_stage(config)
    return run_stage(config)


def main() -> int:
    """GUI worker 子进程入口：读取 --config 并按阶段路由执行。

    --config 为必填，指向一个 JSON 文件路径，解析后按 mode/stage 字段分派到
    对应阶段执行器（detect/extract/print/rembg_submit 等，未匹配则走通用
    run_stage）。进程启动即启用 faulthandler 并统一 stdout/stderr 为 UTF-8，
    以输出 JSON Lines 进度供 GUI 解析。返回阶段执行器的退出码。

    ⚠️ 启动期（读配置 / 解析 JSON / 路由之前）的异常一律转成 error 事件
    + stderr 堆栈，绝不让它变成"静默的退出码 1"（见 `_emit_fatal`）。
    SystemExit 放行（argparse 的用法错误已经写到 stderr 了）。
    """
    _prepare_process()
    try:
        if _IMPORT_ERROR is not None:
            # 依赖/插件层面的 import 失败：连阶段模块都没加载进来
            raise RuntimeError(
                f"worker 依赖加载失败（import 期异常）：{_IMPORT_ERROR}"
            ) from _IMPORT_ERROR
        return _run()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - 启动期任何异常都要可见
        _emit_fatal(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
