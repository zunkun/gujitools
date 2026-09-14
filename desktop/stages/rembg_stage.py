# -*- coding: utf-8 -*-
"""rembg_submit 阶段执行器：把「生成预览」产出的整页去底图合成为最终交付图片。"""

from __future__ import annotations

import shutil
from pathlib import Path

from desktop.stages.events import emit


def run_rembg_submit_stage(config: dict) -> int:
    """rembg 提交：把「生成预览」产出的整页去底图，按 area/border + 检测框
    合成为真正想要的最终图片，写入任务 output 目录。

    与 run_print_stage 的效果合成复用同一套几何规则
    （desktop/workers/preview_worker.compose_region_output），
    但结果是持久化的交付图片而非临时 workset，且不再生成 PDF。

    args["_effects"] = [
        {"file": 预览结果路径, "label": 输出文件名(无扩展名),
         "effect": {"boxes": [[x1,y1,x2,y2]], "area": int, "border": str|None} | None},
        …
    ]
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = dict(config["args"])
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        effects = args.pop("_effects", None) or []
        out_dir = Path(args["output"])
        if args.get("clean") and out_dir.exists():
            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)

        from PySide6.QtGui import QImage

        from desktop.workers.preview_worker import compose_region_output

        total = len(effects)
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
                # 无检测框/无区域参数：整页预览图原样交付
                outputs = [image]
            label = str(spec.get("label") or Path(spec["file"]).stem)
            names = (
                [f"{label}.png"]
                if len(outputs) == 1
                else [f"{label}-{i + 1}.png" for i in range(len(outputs))]
            )
            for out, name in zip(outputs, names):
                dst = out_dir / name
                if out.save(str(dst), "PNG"):
                    saved += 1
                else:
                    emit({"type": "log", **context, "message": f"写入失败: {dst}"})
        emit({"type": "progress", **context, "done": total, "total": total})
        emit(
            {"type": "log", **context,
             "message": f"最终图片已生成（{saved} 张）：{out_dir}"}
        )
        if not saved:
            emit(
                {"type": "error", **context,
                 "message": "没有生成任何图片，请先执行「生成预览」。"}
            )
            return 1
        emit(
            {
                "type": "finished", **context,
                "done": saved, "total": total,
                "result": None, "output": str(out_dir),
            }
        )
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
