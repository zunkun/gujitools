# -*- coding: utf-8 -*-
"""第三步「图片去底色」的实时预览：计算 + **增量落盘**。

分工（2026-10-18 调整）
------------------------
- **「生成预览」**：全量正式产物，写 ``stages/rembgpreview``，会被「提交本次
  任务」读取。参数一变它就过期（见 ``services/submit_state`` 的 PREVIEW_STALE）。
- **「提交本次任务」**：读 ``stages/rembgpreview``，按 area/border 合成为最终
  交付图写 ``stages/rembg``；它是第四步唯一认可的成品来源。
- **本模块（实时预览）**：只算用户当前看着的**那一页**，并**增量落盘**——
  ①该页去底色结果写 ``stages/rembgpreview[~节点]/{stem}.png``；
  ②按 area/border 合成的「应用图」写 ``stages/rembg[~节点]/…``。

⚠️ **新不变量（旧的"绝不碰 rembgpreview/rembg"已被用户 2026-10-18 明确推翻）**：
两个正式目录允许**不完整**（用户预览了哪一页，那一页才有产物）。由此两条铁律：

1. ``stages/rembg`` 里出现零星文件**不等于本步已提交**。增量落盘前会先往该目录
   写 ``.draft`` 哨兵，第四步只有在该哨兵不存在（＝最近一次是**提交**产物）时
   才认这个目录（见 ``desktop.store.tasks.rembg_submit_committed``）。用户原话：
   > 虽然可能 rembg 会有零星图片，但是并不表明，当前步骤已经提交，
   > 必须执行提交，下一步才能使用当前步骤的图片。
2. 各页可能在不同参数下算出来（用户中途改了参数）：这只是**临时可观**的中间态，
   权威产物仍由全量的「生成预览 + 提交」重建（二者都会 clean 整目录）。

计算入口统一走 ``utils.rembg_page``，与 CLI 产物逐像素同源（``functions.rembg``
用的是同一个函数）；「应用图」的几何/编码/命名与提交**完全复用同一批函数**
（``print_plan.plan_submit_job`` + ``preview_worker.compose_region_output``
+ ``rembg_stage.save_transparent_png``），零漂移。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def live_dir(task_id: str) -> Path:
    """该任务的实时预览暂存目录（系统临时目录下，按 task_id 隔离）。"""
    return Path(tempfile.gettempdir()) / "guji_live_preview" / str(task_id)


def reset(task_id: str) -> None:
    """清空该任务的实时暂存（参数回到「生成预览」状态时调用）。"""
    target = live_dir(task_id)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def render_page(image_path: str, args: dict, out_dir: str | Path) -> str:
    """对单页执行去底色并写入 ``out_dir``，返回结果文件路径。

    ⚠️ 重依赖（numpy / PIL，以及 ``utils.image_utils`` 背后的 cv2）在这里
    **延迟导入**：GUI 主进程只有在用户真的动了参数时才付出这点加载成本，
    启动路径不受影响。

    PNG 用 ``compress_level=1``：这是**临时预览**，编码速度比压缩率重要
    （正式产物走 ``functions.rembg``，那里仍是 level=9）。
    """
    import numpy as np
    from PIL import Image

    import utils

    out_path_dir = Path(out_dir)
    out_path_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as img:
        img.load()
        # ⚠️ EXIF 方向转正（与 functions.rembg 同口径：cv2/Qt 都转正，PIL
        #    不转的话实时预览与最终产物方向不一致）。先查标签避免无谓整图复制
        if img.getexif().get(274, 1) != 1:
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img)
        # 与 functions.rembg 一致：RGBA 先合到白底，避免 alpha 干扰阈值
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img_arr = np.array(img)
        gray_arr = np.array(img.convert("L"))

    img_type = int(args.get("type", 1))
    final_arr = utils.rembg_page(
        img_arr,
        gray_arr,
        offset=int(args.get("offset", 0)),
        img_type=img_type,
        enable_seal=bool(args.get("seal", False)),
        seal_color=bool(args.get("sealcolor", False)),
        seal_area=int(args.get("sealarea", 80)),
        seal_min_sat=int(args.get("sealmin_sat", 50)),
    )

    out_path = out_path_dir / f"{Path(image_path).stem}.png"
    if final_arr.ndim == 3:
        Image.fromarray(final_arr, "RGB").save(
            out_path, format="PNG", compress_level=1
        )
    else:
        out_img = Image.fromarray(final_arr, "L")
        if img_type == 2:
            out_img = out_img.convert("1")  # 1bit 单色位图
        out_img.save(out_path, format="PNG", compress_level=1)
    return str(out_path)


def apply_effects(
    preview_path: str | Path, jobs: list[dict], out_dir: str | Path,
) -> tuple[list[str], list[str]]:
    """把某页的去底色结果按**提交规则**合成「应用图」，写 ``out_dir``。

    ``jobs`` 由 ``desktop.services.print_plan.plan_submit_job`` 给出（含 boxes /
    area / border / full 与输出文件名）。与「提交本次任务」逐像素同源：几何走
    ``compose_region_output``、编码走 ``rembg_stage.save_transparent_png``。

    返回 ``(写出的文件名, 错误信息)``；**单条失败不拖垮整批**（与提交阶段同款
    容错）。⚠️ 重依赖同样延迟导入（QtGui / numpy / PIL 不进启动路径）。
    """
    saved: list[str] = []
    errors: list[str] = []
    if not jobs:
        return saved, errors
    from PySide6.QtGui import QImage

    from desktop.stages.rembg_stage import save_transparent_png
    from desktop.workers.preview_worker import compose_region_output

    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    image = QImage(str(preview_path))
    if image.isNull():
        return saved, [f"无法读取图片: {preview_path}"]
    for job in jobs:
        names = list(job.get("names") or [])
        if not names:
            errors.append(f"无法读取图片: {job.get('file')}")
            continue
        label = str(job.get("label") or Path(str(job.get("file"))).stem)
        if job.get("compose"):
            outputs = compose_region_output(
                image, list(job.get("boxes") or []), int(job.get("area", 1)),
                job.get("border"), full=bool(job.get("full")),
            )
        else:
            outputs = [image]
        if len(outputs) != len(names):
            # 几何结果与预计算不一致（理论上不可能）：按张数现算，命名规则
            # 不变，避免静默丢页（与提交阶段的兜底同一处理）。
            names = (
                [f"{label}.png"] if len(outputs) == 1
                else [f"{label}-{i + 1}.png" for i in range(len(outputs))]
            )
        for out, name in zip(outputs, names):
            dst = target / name
            try:
                save_transparent_png(out, dst)
            except Exception as exc:  # noqa: BLE001 - 单张失败不许拖垮整批
                errors.append(f"写入失败: {dst}（{exc}）")
                continue
            saved.append(name)
    return saved, errors
