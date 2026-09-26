# -*- coding: utf-8 -*-
"""通用阶段执行器：CLI 功能阶段（run_stage）+ PDF 渲染阶段（run_extract_stage）。"""

from __future__ import annotations

import sys
from pathlib import Path

from desktop.stages.events import JsonLinesReporter, ProgressStream, emit, _real_stdout
from utils.units import DEFAULT_RENDER_DPI


def _json_safe(value):
    """把 execute() 的返回值收拾成**一定能 json 序列化**的形状。

    ⚠️ 为什么（2026-09-26 审计）：`emit({"type": "finished", "result": result})`
    在同一个 `try` 里，一旦某个命令以后返回了 `Path`/`ndarray`/自定义对象，
    `json.dumps` 会抛异常、被外层 `except Exception` 捕获 →
    **把一个已经成功的阶段报成失败（退出码 1），而产物其实已经落盘**。
    这里只保留 JSON 原生类型，其余一律 `str()`（result 只用于展示，GUI 不解析它）。
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def run_stage(config: dict) -> int:
    """在子进程中执行一个 CLI 功能阶段，返回进程退出码（0/130/1）。

    config 需含 task_id/stage/run_id/args。结构与人类日志走两条通道：

    - **结构化**：`JsonLinesReporter` 注入给功能模块，进度 / 检测框 / 页尺寸
      直接以字典写成 JSON Lines（不再靠正则解析中文提示）；
    - **人读日志**：ProgressStream 仍拦截 stdout 转发为 log 事件，保证日志
      视图一行不漏（含第三方库的输出）。

    通过 args['_outpath'] 可覆盖功能模块计算出的输出目录。异常以 error 事件
    回报，不抛到上层。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        # ⚠️ 走 core.args，不要用 cli.command_args（那是 deprecated 转发壳）——
        # 否则 desktop 阶段执行器会反向依赖命令行入口，GUI 就没法脱离 CLI 单独演进。
        from core.args import CommandArgs
        from functions import get_function

        command = stage
        command_args = CommandArgs(command=command, **args)
        interceptor = ProgressStream(_real_stdout(), context)
        reporter = JsonLinesReporter(context, stream=_real_stdout())
        original_stdout = sys.stdout
        sys.stdout = interceptor
        try:
            function = get_function(command, command_args, reporter)
            if function is None:
                raise ValueError(f"未知阶段: {stage}")
            # GUI 精确输出目录：rembg CLI 默认会在 output 后再追加 "rembg"
            # 子目录，步骤三的「生成预览」需要直接写入 stages/rembgpreview，
            # 故由调用方通过 _outpath 覆盖功能模块计算出的 outpath。
            out_override = args.get("_outpath")
            if out_override:
                function.outpath = Path(out_override)
            result = function.execute()
        finally:
            sys.stdout = original_stdout
            if interceptor.buffer.strip():
                interceptor._consume(interceptor.buffer.strip())
        output = result.get("output") if isinstance(result, dict) else None
        emit(
            {
                "type": "finished",
                **context,
                "result": _json_safe(result),
                "output": output,
            }
        )
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1


def run_extract_stage(config: dict) -> int:
    """extract 阶段：直接把 PDF 提取到任务目录 stages/extract/（无嵌套布局）。

    复用 utils.pdf_extract.render_pages_parallel 的提取/并发实现（与 CLI 同一份），
    但不走 CLI 的 <out_root>/<pdf名>/images 输出规则。

    ⚠️ 这里曾经直接调 process_page_batch(全部页码) —— 那是**串行**的，
    GUI 提取因此比 CLI 慢数倍。并发逻辑在 render_pages_parallel 里。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        import threading

        import pymupdf as fitz
        from core.args import default_workers
        from utils.pdf_extract import parse_pages, render_pages_parallel

        pdf_path = Path(args["input"])
        out_dir = Path(args["output"])
        out_dir.mkdir(parents=True, exist_ok=True)
        document = fitz.open(str(pdf_path))
        total_pages = document.page_count
        document.close()

        pages_str = args.get("pages")
        try:
            # ⚠️ parse_pages 返回的**已经是 0-based** 页码（见其文档字符串），
            # GUI 侧不许再减一：再减会让整段页码前移一页——缺失页里的最后一页
            # 永远提取不出来，而前一页会被重做（2026-09-23 修）。
            page_indices = (
                parse_pages(pages_str, total_pages)
                if pages_str
                else list(range(total_pages))
            )
        except ValueError as exc:
            raise ValueError(f"页面参数错误: {exc}") from exc
        if args.get("clean"):
            import shutil

            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()

        # 结构化汇报直接交给 utils：进度 + 每页尺寸（GUI 据此写 sizes.json，
        # 那是框坐标的坐标系基准）。人类日志经 ProgressStream 转发。
        reporter = JsonLinesReporter(context, stream=_real_stdout())
        interceptor = ProgressStream(_real_stdout(), context)
        original_stdout = sys.stdout
        sys.stdout = interceptor
        try:
            # quick 默认与 CLI 一致为 True（自适应降级，见 _embedded_page_image）
            #
            # ⚠️ 兜底必须走 core.args.default_workers()，不许再写 os.cpu_count()：
            # 界面的参数表单不暴露 workers（EXCLUDED_KEYS），所以这里的兜底就是
            # **用户实际拿到的并发数**。原先写 cpu_count() → 12 个线程同时
            # fitz 渲染 6000px 大页，峰值内存与抢核把整机拖死（832MB/320 页的
            # 《长短经》实测就是如此）。真源只有一处：core/args.py。
            workers = int(args.get("workers") or 0) or default_workers()
            render_pages_parallel(
                str(pdf_path),
                page_indices,
                str(out_dir),
                zoom=float(args.get("zoom", 1)),
                ext=args.get("ext", "jpg"),
                quick=bool(args.get("quick", True)),
                workers=workers,
                progress={"lock": threading.Lock(), "done": 0,
                          "total": len(page_indices)},
                reporter=reporter,
                dpi=float(args.get("dpi") or DEFAULT_RENDER_DPI),
            )
        finally:
            sys.stdout = original_stdout
            if interceptor.buffer.strip():
                interceptor._consume(interceptor.buffer.strip())
        emit(
            {
                "type": "log",
                **context,
                "message": f"🎉 处理完成！ 成功: {len(page_indices)} 页",
            }
        )
        emit(
            {
                "type": "finished",
                **context,
                "result": None,
                "output": str(out_dir),
            }
        )
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
