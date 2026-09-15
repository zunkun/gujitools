# -*- coding: utf-8 -*-
"""print 阶段执行器：合成效果图后按**有序清单**生成 PDF。

页序完全由 ``args["files"]``（GUI 第四步列表顺序）决定，不再依赖文件名
排序——因此不再需要把顺序「烧」进文件名的 workset 目录。合成结果写入
一次性临时目录，交给 print 时同时给出有序清单，执行结束即随临时目录删除。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from desktop.stages.events import emit
from desktop.stages.generic_stage import run_stage


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
    try:
        effects = args.pop("_effects", None) or []
        from PySide6.QtGui import QImage

        from desktop.workers.preview_worker import compose_region_output

        total = len(effects)
        counter = 1
        saved = 0
        files: list[str] = []
        with tempfile.TemporaryDirectory(prefix="guji_print_") as tmp:
            staging = Path(tmp)
            os.makedirs(staging, exist_ok=True)
            for index, spec in enumerate(effects):
                emit({"type": "progress", **context, "done": index, "total": total})
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
