# -*- coding: utf-8 -*-
"""print 阶段执行器：先在子进程内合成效果图（顺序编号），再用 CLI print 生成 PDF。"""

from __future__ import annotations

import shutil
from pathlib import Path

from desktop.stages.events import emit, _real_stdout
from desktop.stages.generic_stage import run_stage


def run_print_stage(config: dict) -> int:
    """print 阶段：先在子进程内把 rembg 结果按 area/border 合成为
    效果图（顺序编号），再用 CLI print 生成 PDF。

    效果合成放在子进程而非 GUI 线程：既不阻塞界面，也避免
    GUI 侧 QProcess 从回调链启动时 Windows 下通知丢失的问题。
    args["_effects"] = [{"file": rembg结果, "effect": {boxes,area,border}|None}, …]
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = dict(config["args"])
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        effects = args.pop("_effects", None) or []
        from PySide6.QtGui import QImage

        from desktop.workers.preview_worker import compose_region_output

        workset = Path(args["input"])
        if workset.exists():
            shutil.rmtree(workset)
        workset.mkdir(parents=True, exist_ok=True)
        total = len(effects)
        counter = 1
        saved = 0
        for index, spec in enumerate(effects):
            emit({"type": "progress", **context, "done": index, "total": total})
            image = QImage(spec["file"])
            if image.isNull():
                emit({"type": "log", **context, "message": f"无法读取图片: {spec['file']}"})
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
                dst = workset / f"{counter:04d}.png"
                if out.save(str(dst)):
                    counter += 1
                    saved += 1
                else:
                    emit({"type": "log", **context, "message": f"写入失败: {dst}"})
        emit({"type": "log", **context, "message": f"效果图就绪（{saved} 张）"})
        if not saved:
            emit({"type": "error", **context, "message": "没有可用的效果图输入"})
            return 1
        args["input"] = str(workset)
        inner = dict(config)
        inner["args"] = args
        return run_stage(inner)
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
