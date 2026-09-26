# -*- coding: utf-8 -*-
"""print 阶段执行器：合成效果图后按**有序清单**生成 PDF。

页序完全由 ``args["files"]``（GUI 第四步列表顺序）决定，不再依赖文件名
排序——因此不再需要把顺序「烧」进文件名的 workset 目录。合成结果写入
一次性临时目录，交给 print 时同时给出有序清单，执行结束即随临时目录删除。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from desktop.stages.events import emit
from desktop.stages.generic_stage import run_stage

#: 效果图暂存目录的固定根（`%TEMP%/guji-print-staging/<task>-<run>/`）。
#:
#: ⚠️ 为什么不用 `tempfile.TemporaryDirectory`（2026-09-26 审计）
#:    中断「生成 PDF」走的是 `QProcess.kill()`，在 Windows 上是
#:    `TerminateProcess` —— **不会**执行 `with` 的 `__exit__`，也不会跑
#:    `except KeyboardInterrupt`（kill 不产生 SIGINT，那段分支实际不可达）。
#:    于是每次取消都在 %TEMP% 留下一个装满整页 PNG 的目录（几百 MB ~ GB），
#:    反复取消能撑爆磁盘。
#:    改成固定根 + 目录里写「属主 pid」：每次开始新的 print 就顺手扫掉
#:    「属主已死」的旧目录；正常结束时仍然自己删。kill 导致的残留最多留到
#:    下一次生成 PDF，不会无界累积。
_STAGING_ROOT_NAME = "guji-print-staging"

#: 属主标记文件名（内容为 pid）
_OWNER_FILE = "owner.pid"


def staging_root() -> Path:
    """所有效果图暂存目录的固定根。"""
    return Path(tempfile.gettempdir()) / _STAGING_ROOT_NAME


def _pid_alive(pid: int) -> bool:
    """pid 是否还活着（实现见 utils/proc_utils.pid_alive，这里只做转发）。"""
    from utils.proc_utils import pid_alive

    return pid_alive(pid)


def sweep_orphan_staging(exclude: Path | None = None) -> int:
    """删掉「属主进程已死」的暂存目录，返回删除个数。

    `exclude` 传自己正在用的目录（绝不删自己）。
    """
    root = staging_root()
    if not root.is_dir():
        return 0
    removed = 0
    for entry in root.iterdir():
        if not entry.is_dir() or (exclude is not None and entry == exclude):
            continue
        try:
            owner = int((entry / _OWNER_FILE).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            # 没有属主标记：可能是刚建好还没写，也可能是残缺目录。
            # 只在它明显"放了一段时间"时才删，避免误删正在跑的另一个任务。
            try:
                age = os.path.getmtime(entry)
            except OSError:
                continue
            import time as _time

            if _time.time() - age > 3600:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
            continue
        if not _pid_alive(owner):
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed


def run_print_stage(config: dict) -> int:
    """print 阶段：把 rembg 结果按 area/border 合成为效果图，再生成 PDF。

    效果合成放在子进程而非 GUI 线程：既不阻塞界面，也避免 GUI 侧
    QProcess 从回调链启动时 Windows 下通知丢失的问题。

    args["_effects"] = [
        {"file": 源图路径, "label": 输出条目名,
         "effect": {"boxes": [[x1,y1,x2,y2]], "area": int, "border": str|None}},
        …
    ]

    合成结果按**列表顺序**以 ``0001.png`` 命名写入临时暂存目录，并把
    ``args["files"]`` 设为这份有序清单——CLI 侧不再读目录、不再解析
    文件名，页序与第四步列表严格一致（拖拽重排无需任何物理文件改动）。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = dict(config["args"])
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    staging: Path | None = None
    try:
        effects = args.pop("_effects", None) or []
        from PySide6.QtGui import QImage

        from desktop.workers.preview_worker import compose_region_output

        total = len(effects)
        counter = 1
        saved = 0
        files: list[str] = []
        # 固定暂存目录 + 属主标记：被 kill 也不会留下永久垃圾（见模块文档）
        staging = staging_root() / f"{task_id}-{run_id}"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / _OWNER_FILE).write_text(str(os.getpid()), encoding="utf-8")
        sweep_orphan_staging(exclude=staging)
        for index, spec in enumerate(effects):
            # ⚠️ 合成阶段**不发 progress 事件**：整个 print 阶段只有一条进度条，
            # 唯一来源是 CLI 侧的「已写入页数」（functions/print.py 走 reporter）。
            # 这里再发一份，进度条就会先跑完合成、再由写入**从 0 重跑**，
            # 用户看到的是"顶部 197/198、底部 160/198 两个数字对不上"
            # （实测症状）。合成很快（每页约 25ms），用日志给反馈就够。
            if index % 10 == 0 or index + 1 == total:
                emit({"type": "log", **context,
                      "message": f"合成效果图 {index + 1}/{total}"})
            image = QImage(spec["file"])
            if image.isNull():
                emit({"type": "log", **context,
                      "message": f"无法读取图片: {spec['file']}"})
                continue
            effect = spec.get("effect")
            if effect and any(effect.get("boxes") or []):
                outputs = compose_region_output(
                    image,
                    effect.get("boxes", []),
                    int(effect.get("area", 1)),
                    effect.get("border"),
                )
            else:
                outputs = [image]
            for out in outputs:
                dst = staging / f"{counter:04d}.png"
                if out.save(str(dst)):
                    files.append(str(dst))
                    counter += 1
                    saved += 1
                else:
                    emit({"type": "log", **context,
                          "message": f"写入失败: {dst}"})
        emit({"type": "log", **context, "message": f"效果图就绪（{saved} 张）"})
        if not saved:
            emit({"type": "error", **context, "message": "没有可用的效果图输入"})
            return 1
        args["input"] = str(staging)
        args["files"] = files  # 有序清单 = 页序，CLI 不再按文件名排序
        inner = dict(config)
        inner["args"] = args
        return run_stage(inner)
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
