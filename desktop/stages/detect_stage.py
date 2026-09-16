# -*- coding: utf-8 -*-
"""detect 阶段执行器：单图检测 + 批量检测（重依赖只在本子进程加载）。"""

from __future__ import annotations

import sys
from pathlib import Path

from desktop.stages.events import ProgressStream, emit, _real_stdout


def run_detect(config: dict) -> int:
    """检测单张图片的左右文本框，返回像素坐标（重依赖只在本子进程加载）。"""
    image_path = config["image"]
    emit({"type": "detect_started", "image": image_path})
    try:
        import utils
        from functions.detect import detect_page_boxes

        img = utils.imread(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")
        left_box, right_box = detect_page_boxes(img)
        emit(
            {
                "type": "boxes",
                "image": image_path,
                "left": list(left_box) if left_box else None,
                "right": list(right_box) if right_box else None,
            }
        )
        return 0
    except Exception as exc:
        emit({"type": "detect_error", "image": image_path, "message": str(exc)})
        return 1


def run_detect_stage(config: dict) -> int:
    """detect 阶段：逐图检测左右文本框并上报坐标，不切割、不生成任何文件。

    检测算法复用 `functions.detect.detect_page_boxes`（与 CLI crop /
    cropremove 同源），最终裁剪框由 GUI 按同一套规则
    （utils.box_geometry.compute_final_boxes）从检测框实时推导，用于预览标注。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    # 拦截 stdout：YOLO/ultralytics 会直接 print（如「加载 YOLO 模型: …」），
    # 不拦住就会混进 stdout 破坏 JSON Lines 协议（GUI 只能靠解析失败兜底当日志）。
    interceptor = ProgressStream(_real_stdout(), context)
    original_stdout = sys.stdout
    sys.stdout = interceptor
    try:
        import utils
        from functions.detect import detect_page_boxes

        files = utils.collect_image_files(Path(args.get("input", ".")), is_file=False)
        total = len(files)
        if not total:
            emit({"type": "error", **context, "message": "输入目录中没有图片"})
            return 1
        model = utils.load_yolo_model()
        done = 0
        for path in files:
            img = utils.imread(path)
            if img is None:
                emit({"type": "log", **context, "message": f"无法读取图片: {path}"})
            else:
                left_box, right_box = detect_page_boxes(img, model)
                emit(
                    {
                        "type": "page_boxes",
                        **context,
                        "image": path.stem,
                        "left": list(left_box) if left_box else None,
                        "right": list(right_box) if right_box else None,
                    }
                )
            done += 1
            emit({"type": "progress", **context, "done": done, "total": total})
        emit({"type": "finished", **context, "done": done, "total": total, "result": None, "output": None})
        return 0
    except KeyboardInterrupt:
        emit({"type": "cancelled", **context})
        return 130
    except Exception as exc:
        emit({"type": "error", **context, "message": str(exc)})
        return 1
    finally:
        sys.stdout = original_stdout
        # 冲刷残留的库输出，避免最后一行被吞
        if interceptor.buffer.strip():
            interceptor._consume(interceptor.buffer.strip())
