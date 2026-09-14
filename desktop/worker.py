"""Process entry for one GUI stage task.

The worker emits JSON Lines on stdout so the GUI remains independent from heavy libraries.
While the stage function runs, sys.stdout is intercepted so that:
- progress messages produced by functions/* (处理完成 / 进度: d/t / 写入进度 等)
  are converted into {"type": "progress"} events;
- every other text line is forwarded as {"type": "log"} events for the GUI log view.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# 各功能模块的进度输出模式 → (done, total)
_PROGRESS_PAIR = re.compile(r"(?:进度|图片加载进度|写入进度)\s*[:：]?\s*(\d+)\s*/\s*(\d+)")
# base.py 引擎：先输出总数，再逐文件输出 完成/失败
_TOTAL_ONLY = re.compile(r"图片总数\s*[:：]\s*(\d+)")
_DONE_ONE = re.compile(r"处理(?:完成|失败)\s*[:：]")
# text_region 检测到的文本框坐标行：[boxes] 0001 left=10,20,300,400 right=none
_BOXES_LINE = re.compile(r"^\[boxes\]\s+(\S+)\s+left=(\S+)\s+right=(\S+)\s*$")
# extract 渲染的页面图片尺寸行：[imgsize] 1 2481,3508
_IMG_SIZE_LINE = re.compile(r"^\[imgsize\]\s+(\S+)\s+(\d+),(\d+)\s*$")


def _parse_box(text: str):
    if text == "none":
        return None
    try:
        return [int(v) for v in text.split(",")]
    except ValueError:
        return None


def _real_stdout():
    """窗口化打包运行时 sys.stdout 可能为 None，尝试 fd 1 兜底。"""
    for candidate in (sys.__stdout__, sys.stdout):
        if candidate is not None:
            return candidate
    import os

    return os.fdopen(1, "w", encoding="utf-8", closefd=False)


def emit(payload: dict, stream=None) -> None:
    target = stream if stream is not None else _real_stdout()
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")
    target.flush()


class ProgressStream(io.TextIOBase):
    """拦截功能模块的 print 输出，解析进度并转发日志。"""

    def __init__(self, real_stdout, context: dict):
        self.real = real_stdout
        self.context = context  # {"task_id", "stage", "run_id"}
        self.buffer = ""
        self.done = 0
        self.total = 0

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        self.buffer += text
        # 以换行或回车作为一条输出边界（print.py 使用 end="" + \r 输出进度）
        while True:
            idx = min(
                (i for i in (self.buffer.find("\n"), self.buffer.find("\r")) if i >= 0),
                default=-1,
            )
            if idx < 0:
                break
            line = self.buffer[: idx + 1].strip()
            self.buffer = self.buffer[idx + 1 :]
            if line:
                self._consume(line)
        return len(text)

    def flush(self) -> None:
        pass

    def _consume(self, line: str) -> None:
        match = _BOXES_LINE.match(line)
        if match:
            # 框坐标是结构化数据，转发为独立事件，不进日志视图
            emit(
                {
                    "type": "page_boxes",
                    **self.context,
                    "image": match.group(1),
                    "left": _parse_box(match.group(2)),
                    "right": _parse_box(match.group(3)),
                },
                stream=self.real,
            )
            return
        match = _IMG_SIZE_LINE.match(line)
        if match:
            emit(
                {
                    "type": "page_size",
                    **self.context,
                    "image": match.group(1),
                    "width": int(match.group(2)),
                    "height": int(match.group(3)),
                },
                stream=self.real,
            )
            return
        emit(
            {"type": "log", **self.context, "message": line},
            stream=self.real,
        )
        changed = False
        match = _PROGRESS_PAIR.search(line)
        if match:
            self.done, self.total = int(match.group(1)), int(match.group(2))
            changed = True
        else:
            match = _TOTAL_ONLY.search(line)
            if match and not self.total:
                self.total = int(match.group(1))
                changed = True
            elif _DONE_ONE.search(line):
                self.done += 1
                changed = True
        if changed:
            emit(
                {
                    "type": "progress",
                    **self.context,
                    "done": self.done,
                    "total": self.total,
                },
                stream=self.real,
            )


def run_detect(config: dict) -> int:
    """检测单张图片的左右文本框，返回像素坐标（重依赖只在本子进程加载）。"""
    image_path = config["image"]
    emit({"type": "detect_started", "image": image_path})
    try:
        import cv2
        import utils

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")
        model = utils.load_yolo_model()
        left_boxes, right_boxes = utils.detect_left_right_boxes(img, model)
        emit(
            {
                "type": "boxes",
                "image": image_path,
                "left": [int(v) for v in left_boxes[0][:4]] if left_boxes else None,
                "right": [int(v) for v in right_boxes[0][:4]] if right_boxes else None,
            }
        )
        return 0
    except Exception as exc:
        emit({"type": "detect_error", "image": image_path, "message": str(exc)})
        return 1


def run_detect_stage(config: dict) -> int:
    """detect 阶段：逐图检测左右文本框并上报坐标，不切割、不生成任何文件。

    最终裁剪框由 GUI 按同一套规则（utils.box_geometry.compute_final_boxes）
    从检测框实时推导，用于预览标注。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        import cv2
        import utils

        files = utils.collect_image_files(Path(args.get("input", ".")), is_file=False)
        total = len(files)
        if not total:
            emit({"type": "error", **context, "message": "输入目录中没有图片"})
            return 1
        model = utils.load_yolo_model()
        done = 0
        for path in files:
            img = cv2.imread(str(path))
            if img is None:
                emit({"type": "log", **context, "message": f"无法读取图片: {path}"})
            else:
                left_boxes, right_boxes = utils.detect_left_right_boxes(img, model)
                emit(
                    {
                        "type": "page_boxes",
                        **context,
                        "image": path.stem,
                        "left": [int(v) for v in left_boxes[0][:4]] if left_boxes else None,
                        "right": [int(v) for v in right_boxes[0][:4]] if right_boxes else None,
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


def run_stage(config: dict) -> int:
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        from cli.command_args import CommandArgs
        from functions import get_function

        command = stage
        command_args = CommandArgs(command=command, **args)
        interceptor = ProgressStream(_real_stdout(), context)
        original_stdout = sys.stdout
        sys.stdout = interceptor
        try:
            function = get_function(command, command_args)
            if function is None:
                raise ValueError(f"未知阶段: {stage}")
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
                "done": interceptor.done,
                "total": interceptor.total,
                "result": result,
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
    """extract 阶段：直接把 PDF 渲染到任务目录 stages/extract/（无嵌套布局）。

    复用 utils.pdf_utils.process_page_batch 的渲染/并发实现，
    但不走 CLI 的 <out_root>/<pdf名>/images 输出规则。
    """
    task_id = config["task_id"]
    stage = config["stage"]
    run_id = config["run_id"]
    args = config["args"]
    context = {"task_id": task_id, "stage": stage, "run_id": run_id}
    emit({"type": "started", **context})
    try:
        import pymupdf as fitz
        from utils.pdf_utils import parse_pages, process_page_batch

        pdf_path = Path(args["input"])
        out_dir = Path(args["output"])
        out_dir.mkdir(parents=True, exist_ok=True)
        document = fitz.open(str(pdf_path))
        total_pages = document.page_count
        document.close()

        pages_str = args.get("pages")
        try:
            page_indices = (
                [n - 1 for n in parse_pages(pages_str, total_pages)]
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

        # 进度输出经 ProgressStream 拦截后转为 progress/log 事件
        interceptor = ProgressStream(_real_stdout(), context)
        original_stdout = sys.stdout
        sys.stdout = interceptor
        try:
            process_page_batch(
                str(pdf_path),
                page_indices,
                str(out_dir),
                zoom=float(args.get("zoom", 1)),
                ext=args.get("ext", "jpg"),
                quick=bool(args.get("quick", False)),
                progress={"lock": __import__("threading").Lock(), "done": 0,
                          "total": len(page_indices)},
            )
        finally:
            sys.stdout = original_stdout
            if interceptor.buffer.strip():
                interceptor._consume(interceptor.buffer.strip())
        emit(
            {
                "type": "log",
                **context,
                "message": f"🎉 处理完成！ 成功: {interceptor.done}/{len(page_indices)} 页",
            }
        )
        emit(
            {
                "type": "finished",
                **context,
                "done": interceptor.done,
                "total": interceptor.total,
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

        from .workers.preview_worker import compose_region_output

        workset = Path(args["input"])
        if workset.exists():
            import shutil

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


def main() -> int:
    import faulthandler
    faulthandler.dump_traceback_later(20, exit=True)  # DIAGNOSTIC
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
    return run_stage(config)


if __name__ == "__main__":
    sys.exit(main())
