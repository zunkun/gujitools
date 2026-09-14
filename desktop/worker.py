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

# 阶段执行器重导出：保持 `from desktop.worker import run_stage` 等旧引用可用
from desktop.stages import (  # noqa: F401
    run_detect,
    run_detect_stage,
    run_extract_stage,
    run_print_stage,
    run_rembg_submit_stage,
    run_stage,
)


def main() -> int:
    """GUI worker 子进程入口：读取 --config 并按阶段路由执行。

    --config 为必填，指向一个 JSON 文件路径，解析后按 mode/stage 字段分派到
    对应阶段执行器（detect/extract/print/rembg_submit 等，未匹配则走通用
    run_stage）。进程启动即启用 faulthandler 并统一 stdout/stderr 为 UTF-8，
    以输出 JSON Lines 进度供 GUI 解析。返回阶段执行器的退出码。
    """
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true", help="GUI 子进程入口标记")
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args()
    config = json.loads(options.config.read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    sys.exit(main())
