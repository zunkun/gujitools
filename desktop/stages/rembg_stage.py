# -*- coding: utf-8 -*-
"""rembg_submit 阶段执行器：把「生成预览」产出的整页去底图合成为最终交付图片。"""

from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from desktop.stages.events import emit
from core.args import machine_worker_budget  # noqa: E402  (预算与函数层同一份)
from desktop.utils.files import THUMBNAIL_EDGE  # noqa: E402
from utils.file_utils import write_bytes_atomic  # noqa: E402

#: 提交合成的并行 worker 数。瓶颈在 **PNG 编码**（实测单张 6000×5475 约
#: 0.65s，占整页 85%；Qt 的读写/绘制在 PySide6 里释放 GIL，线程并行实测
#: 4 线程 3.47×）。每个 worker 同时持有整页位图（~130MB）+ 输出画布，
#: 峰值内存随线程数线性涨。
#: ⚠️ 上限与 `core.args.machine_worker_budget()`（函数层动态预算）保持一致
#: （同一个内存预算下的两个入口，改一处要想另一处）；环境变量是用户的
#: 显式选择，可越过预算但受绝对封顶 8 约束。
SUBMIT_WORKERS = max(
    1,
    min(
        8,
        int(os.environ.get("GUJI_SUBMIT_WORKERS") or 0)
        or min(8, machine_worker_budget(), os.cpu_count() or 1),
    ),
)


def _save_step4_thumb(image, name: str, thumb_dir: Path) -> None:
    """提交落盘最终图后**顺手**生成第四步缩略条用的小图。

    第四步左侧缩略条原先对每条目现解码 6000px 的原图（QImageReader 缩放
    解码也要数百 ms/张），换成预生成 256px JPEG 后查看器零解码直接上屏
    （2026-09-27 用户反馈「第四步缩略图渲染慢」）。

    - 失败**静默跳过**：缩略图是纯加速件，查看器对缺失的页回落原图解码，
      绝不能因为缩略图写失败把成功的提交报成失败；
    - **原子写**：截断的缩略图 mtime 必然比最终图新，会被查看器的
      mtime 新鲜度判据永久当成有效缓存（与源缩略图同一套道理）。
    """
    from PySide6.QtCore import QBuffer, QIODevice, Qt

    try:
        small = image.scaled(
            THUMBNAIL_EDGE, THUMBNAIL_EDGE,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        small.save(buf, "JPG", quality=80)
        write_bytes_atomic(thumb_dir / f"{Path(name).stem}.jpg", bytes(buf.data()))
    except Exception:  # noqa: BLE001 - 加速件不许拖垮主流程
        pass


def run_rembg_submit_stage(config: dict) -> int:
    """rembg 提交：把「生成预览」产出的整页去底图，按 area/border + 检测框
    合成为真正想要的最终图片，写入任务 output 目录。

    与 run_print_stage 的效果合成复用同一套几何规则
    （desktop/workers/preview_worker.compose_region_output），
    但结果是持久化的交付图片而非一次性暂存，且不再生成 PDF。

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
        # 第四步缩略图缓存（与 store.rembg_thumbnails_dir 同一份目录布局：
        # <task>/thumbnails/print；worker 侧拿不到 store，按任务目录布局推导）。
        # 提交时**整目录重建**：最终图变了/页数变了，旧缩略图全部作废，
        # 不留孤儿文件。
        thumb_dir = out_dir.parent.parent / "thumbnails" / "print"
        shutil.rmtree(thumb_dir, ignore_errors=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        from PySide6.QtGui import QImage, QImageReader

        from desktop.workers.preview_worker import (
            compose_region_output, region_canvas_specs,
        )

        # ---- 阶段一（主线程）：预计算每页的输出文件名 --------------------
        # 只用 QImageReader 读文件头拿尺寸（不解码位图），几何张数由
        # region_canvas_specs 给出（与合成共用同一份规则，零漂移）。
        # area=1 时每页产左右两张，总张数 = 2×页数，进度按**张**计。
        jobs: list[dict] = []
        for spec in effects:
            reader = QImageReader(str(spec["file"]))
            size = reader.size()
            effect = spec.get("effect")
            has_boxes = bool(effect and any(effect.get("boxes") or []))
            label = str(spec.get("label") or Path(spec["file"]).stem)
            if size.isEmpty():
                jobs.append({
                    "file": str(spec["file"]), "compose": False,
                    "boxes": [], "area": 1, "border": None,
                    "names": [], "label": label,
                })
                continue
            if has_boxes:
                boxes = list(effect.get("boxes") or [])
                area = int(effect.get("area", 1))
                border = effect.get("border")
                full = bool(effect.get("full"))
                canvas_specs = region_canvas_specs(
                    (size.width(), size.height()), boxes, area, border, full=full,
                )
            else:
                # 无检测框/无区域参数：整页预览图原样交付
                boxes, area, border, full = [], 1, None, False
                canvas_specs = [((size.width(), size.height()), [])]
            names = (
                [f"{label}.png"]
                if len(canvas_specs) == 1
                else [f"{label}-{i + 1}.png" for i in range(len(canvas_specs))]
            )
            jobs.append({
                "file": str(spec["file"]), "compose": has_boxes,
                "boxes": boxes, "area": area, "border": border, "full": full,
                "names": names, "label": label,
            })

        total = sum(len(j["names"]) for j in jobs)  # 输出**张数**

        # ---- 阶段二（线程池）：并行 读图 → 合成 → 写 PNG ------------------
        # ⚠️ emit 只在主线程调（worker 线程往 stdout 写 JSON 行会交错）。
        def _process(job: dict):
            saved_names: list[str] = []
            errors: list[str] = []
            if not job["names"]:
                return saved_names, [f"无法读取图片: {job['file']}"]
            image = QImage(job["file"])
            if image.isNull():
                return saved_names, [f"无法读取图片: {job['file']}"]
            if job["compose"]:
                outputs = compose_region_output(
                    image, job["boxes"], job["area"], job["border"],
                    full=bool(job.get("full")),
                )
            else:
                outputs = [image]
            names = job["names"]
            if len(outputs) != len(names):
                # 几何结果与预计算不一致（理论上不可能）：按张数现算，
                # 命名规则不变，避免静默丢页
                names = (
                    [f"{job['label']}.png"]
                    if len(outputs) == 1
                    else [f"{job['label']}-{i + 1}.png"
                          for i in range(len(outputs))]
                )
            for out, name in zip(outputs, names):
                dst = out_dir / name
                if out.save(str(dst), "PNG"):
                    saved_names.append(name)
                    _save_step4_thumb(out, name, thumb_dir)
                else:
                    errors.append(f"写入失败: {dst}")
            return saved_names, errors

        done = 0
        saved = 0
        executor = ThreadPoolExecutor(max_workers=SUBMIT_WORKERS)
        try:
            future_jobs = {
                executor.submit(_process, job): job for job in jobs
            }
            for future in as_completed(future_jobs):
                job = future_jobs[future]
                saved_names, errors = future.result()
                saved += len(saved_names)
                done += len(saved_names) + len(errors)
                emit({"type": "progress", **context, "done": done, "total": total})
                # 每页一条处理记录：与 extract 等阶段的逐页日志同密度。
                # ⚠️ progress 事件只动进度条不进日志（runner 只收 log 事件），
                # 缺了这行整个提交过程在执行日志里就是空白。
                emit({
                    "type": "log", **context,
                    "message": f"提交处理 {done}/{total}：{job['label']} → "
                               + ("、".join(saved_names) if saved_names else "无输出"),
                })
                for message in errors:
                    emit({"type": "log", **context, "message": message})
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
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
