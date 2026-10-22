# -*- coding: utf-8 -*-
"""rembg_submit 阶段执行器：把「生成预览」产出的整页去底图合成为最终交付图片。

产物一律是**白底透明**的 PNG（规则与编码形态的唯一实现在
``utils/transparent_png.py``）：用户 2026-09-30 定的「无论 type 是什么，
提交产物都把黑字白底里的白底改成透明」。
"""

from __future__ import annotations

import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import utils
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


def _qimage_rgb_array(image):
    """QImage → ``(H, W, 3)`` 的 RGB 数组（``uint8``，独立于 QImage 生命周期）。

    ⚠️ 三个坑，逐条都是踩过的：
    1. ``constBits()`` 的内存布局是 **B,G,R,A**（Format_RGB32），直接当 RGB 用
       会让整页偏色——必须反序取通道。
    2. **必须复制一份出来**（``np.ascontiguousarray``）。numpy 的 ``frombuffer``
       只是**引用** Qt 的缓冲区，而内存归 QImage 对象所有：一旦那个 QImage 被
       回收，数组就变成悬垂指针。非 RGB32 的输入（预览图模式 "1"/"L" 且该页
       无检测框、走整图透传那条分支）恰恰要先 ``convertToFormat`` 出一个
       **临时对象**，它在下面几行之后就被回收——实测症状是产物里混进随机彩色
       像素（``[156,233,32]`` 之类，那些是别人的内存），重则直接段错误。
       一整份 RGB 拷贝是 3 字节/像素（22MP 页 66MB），换掉这类静默错误值得。
    3. ``convertToFormat`` 在格式已一致时会返回浅拷贝；这里只在格式不同时调用。
    """
    import numpy as np
    from PySide6.QtGui import QImage

    if image.format() != QImage.Format.Format_RGB32:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    height, width = image.height(), image.width()
    stride = image.bytesPerLine()
    buffer = np.frombuffer(image.constBits(), np.uint8)
    rows = buffer[: stride * height].reshape(height, stride)
    # RGB32 每行 32 位对齐，stride 恒等于 width*4（这里仍取 width*4 切一刀，
    # 不依赖该前提）；切片后恒为连续视图，reshape 不会悄悄复制。
    pixels = rows[:, : width * 4].reshape(height, width, 4)
    return np.ascontiguousarray(pixels[:, :, 2::-1])


def save_transparent_png(image, dst: Path) -> None:
    """把合成结果落盘为**白底透明** PNG（编码规则见 ``utils.transparent_png``）。

    ⚠️ 不许绕过这个函数直接 ``image.save(dst, "PNG")``：那样写出的白底图会和
    透明底产物混在一批里（护栏 tests/selftests/rembg_transparent.py 会盯着）。

    ⚠️ 2026-10-18 起对外公开（原 ``_save_transparent_png``）：第三步「实时预览
    增量落盘」也走它——两份产物（提交 / 预览）必须逐像素同一套编码。
    """
    utils.save_white_as_transparent(_qimage_rgb_array(image), dst)


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
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        small.save(buf, "JPG", quality=80)
        write_bytes_atomic(thumb_dir / f"{Path(name).stem}.jpg", bytes(buf.data().data()))
    except Exception:  # noqa: BLE001 - 加速件不许拖垮主流程
        pass


def run_rembg_submit_stage(config: dict) -> int:
    """rembg 提交：把整页去底图的白底转成透明，写入任务 output 目录。

    用户 2026-10-22：

    > 去底色步骤的 area 和 border 参数去除，去底色直接输入图片是怎样的，
    > 直接整个图片去底色

    所以这里**不做任何几何合成**：一条输入（「生成预览」的结果）对应一条输出
    （同名的透明底 PNG）。按框裁图在第二步「提交本次任务」已经做完，进来的
    图本来就是该交出去的形状。

    args["_effects"] = [
        {"file": 预览结果路径, "label": 输出文件名(无扩展名)}, …
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
        # 兼容旧调用方（{"file":…, "effect": {…}} 的形态）：只取文件与文件名。
        entries = [
            {"file": str(spec.get("file")), "label": str(spec.get("label") or "")}
            for spec in effects
            if spec.get("file")
        ]
        out_dir = Path(args["output"])
        if args.get("clean") and out_dir.exists():
            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
        out_dir.mkdir(parents=True, exist_ok=True)
        # 第四步缩略图缓存（与 store.rembg_thumbnails_dir 同一份目录布局：
        # <task>/thumbnails/print[~<节点>]；worker 侧拿不到 store，按任务目录
        # 布局 + **产物目录名里的节点后缀**推导——同一步骤多个「图片去底色」
        # 节点时各自的缩略图不许互相覆盖，用户 2026-10-17）。
        # 提交时**整目录重建**：最终图变了/页数变了，旧缩略图全部作废，
        # 不留孤儿文件。
        from desktop.steps.ports import node_scope_from_output_dir

        thumb_dir = (
            out_dir.parent.parent
            / "thumbnails"
            / f"print{node_scope_from_output_dir(out_dir.name)}"
        )
        shutil.rmtree(thumb_dir, ignore_errors=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        from PySide6.QtGui import QImage

        total = len(entries)

        def _process(entry: dict):
            """一条：读预览图 → 白底转透明 → 写 PNG（+ 第四步缩略图）。"""
            name = f"{entry['label'] or Path(entry['file']).stem}.png"
            image = QImage(entry["file"])
            if image.isNull():
                return "", f"无法读取图片: {entry['file']}"
            dst = out_dir / name
            try:
                save_transparent_png(image, dst)
            except Exception as exc:  # noqa: BLE001 - 单张失败不许拖垮整批
                return "", f"写入失败: {dst}（{exc}）"
            # 缩略图从**合成位图**（白底）生成：JPEG 没有 α 通道，从白底图
            # 直接缩放的结果与"先转透明再合成"逐字节一致，省一轮解码。
            _save_step4_thumb(image, name, thumb_dir)
            return name, ""

        done = 0
        saved = 0
        errors: list[str] = []
        executor = ThreadPoolExecutor(max_workers=SUBMIT_WORKERS)
        try:
            future_jobs = {
                executor.submit(_process, entry): entry for entry in entries
            }
            for future in as_completed(future_jobs):
                entry = future_jobs[future]
                name, error = future.result()
                done += 1
                if name:
                    saved += 1
                elif error:
                    errors.append(error)
                emit({"type": "progress", **context, "done": done, "total": total})
                label = entry.get("label") or Path(entry["file"]).stem
                emit({
                    "type": "log", **context,
                    "message": f"提交处理 {done}/{total}：{label} → "
                               + (name or "无输出"),
                })
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        for message in errors:
            emit({"type": "log", **context, "message": message})
        emit({"type": "progress", **context, "done": total, "total": total})
        emit(
            {"type": "log", **context,
             "message": f"最终图片已生成（{saved} 张，白底已转透明）：{out_dir}"}
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
