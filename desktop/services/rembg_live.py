# -*- coding: utf-8 -*-
"""去底色参数实时调整的**单页重算**：只写预览草稿。

用户口径（2026-11-04）：

> 去底色没执行、只是切缩略图/改参数时算出来的图，**只能在去底色这一步查看**；
> 下一步不该看到它（上一步执行，下一步才有数据）。

所以算出来的结果只落 ``tasks/<任务号>/preview/rembg[~节点]/<页名>.png``
（草稿目录，见 ``store.rembg_preview_dir``）：第三步查看器优先显示它，
拼版 / 第四步按阶段产物目录取图，看不到它。用户点「执行去底色」时，
正式阶段会把全部页写进 ``stages/rembg[~节点]``，草稿随即清空。

计算口径与正式阶段同源（``utils.rembg_page`` + ``utils.save_white_as_transparent``）。
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from desktop.utils.files import THUMBNAIL_EDGE
from utils.file_utils import write_bytes_atomic


def _rgb_of(final_arr):
    """去底结果 → ``(H, W, 3)`` RGB 数组（透明 PNG 编码的输入形状）。"""
    import numpy as np

    if final_arr.ndim == 3:
        return final_arr[:, :, :3]
    return np.repeat(final_arr[:, :, None], 3, axis=2)


def _save_thumb(rgb, name: str, thumb_dir: Path) -> None:
    """顺手刷新第四步缩略条用的小图（256px JPEG，白底）。

    与 ``desktop.stages.rembg_stage._save_thumb`` 同一规格（第四步的
    ``_print_thumb_provider`` 按 ``mtime 不旧于成品图`` 判有效，不刷新的话它
    会回落整幅解码）。失败**静默跳过**：缩略图是纯加速件。
    """
    from PIL import Image

    try:
        small = Image.fromarray(rgb, "RGB")
        small.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
        buf = BytesIO()
        small.save(buf, format="JPEG", quality=80)
        write_bytes_atomic(thumb_dir / f"{name}.jpg", buf.getvalue())
    except Exception:  # noqa: BLE001 - 加速件不许拖垮主流程
        pass


def render_page(image_path: str, args: dict, out_dir: str | Path,
                thumb_dir: str | Path | None = None) -> str:
    """单页整图去底色 → 写草稿（``out_dir``），返回结果路径。

    ⚠️ 写入走「同目录 ``.part`` + ``os.replace``」：草稿会被当前查看器读到，
    直接 ``Image.save`` 会让人读到半截 PNG。``.part`` 后缀不在
    ``IMAGE_SUFFIXES`` 里，也不会被当成一页。

    ``thumb_dir``：仅正式产物目录才传（第四步缩略图属于下游数据，草稿不写）；
    ``rembg_methods`` 侧车同理——草稿目录不是 ``stages/`` 下的目录，
    ``rembg_methods_path`` 返回 None，天然不写。
    """
    import utils
    from functions.rembg import load_rgb_and_gray

    out_path_dir = Path(out_dir)
    out_path_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(image_path)
    algorithm = str(args.get("algorithm", "otsu"))
    offset = int(args.get("offset", 0))
    img_arr, gray_arr = load_rgb_and_gray(input_path)
    threshold = _shared_threshold_for(input_path, gray_arr, algorithm, args)
    final_arr = utils.rembg_page(
        img_arr,
        gray_arr,
        algorithm=algorithm,
        offset=offset,
        window=int(args.get("window", 25)),
        k=float(args.get("k", 0.2)),
        threshold=threshold,
        img_type=int(args.get("type", 1)),
        enable_seal=bool(args.get("seal", False)),
        seal_color=bool(args.get("sealcolor", False)),
        seal_area=int(args.get("sealarea", 80)),
        seal_min_sat=int(args.get("sealmin_sat", 50)),
    )
    rgb = _rgb_of(final_arr)
    out_path = out_path_dir / f"{Path(image_path).stem}.png"
    part = out_path.with_name(out_path.name + ".part")
    utils.save_white_as_transparent(rgb, part)
    os.replace(part, out_path)
    if thumb_dir:
        _save_thumb(rgb, Path(image_path).stem, Path(thumb_dir))
    _record_method(out_path_dir, Path(image_path).stem, str(args.get("algorithm", "otsu")))
    return str(out_path)


def _shared_threshold_for(image_path: Path, gray, algorithm: str,
                          args: dict) -> int | None:
    """实时预览的**同页共享阈值**；不适用（无上游 detect / 局部算法 / 单图）返回 None。

    与全量执行同一规则：最近上游 detect 的 ``boxes.json`` 提交计划里同一源页的
    左右裁图合成一组，非占位成员合并统计；占位图不参与统计，但用组阈值出图。
    """
    boxes_path = args.get("_boxes_path")
    if not boxes_path:
        return None
    from desktop.services.rembg_groups import group_of
    from utils.rembg_algorithms import (
        LOCAL_ALGORITHM_KEYS,
        THRESHOLD_MAX,
        THRESHOLD_MIN,
        get_algorithm,
    )

    if algorithm in LOCAL_ALGORITHM_KEYS:
        return None
    import utils

    try:
        files = utils.collect_image_files(image_path.parent, False)
    except Exception:  # noqa: BLE001 - 读目录失败就退回逐图
        return None
    group = group_of(files, image_path, boxes_path)
    if len(group) < 2:
        return None

    algorithms = {
        str(key): str(value)
        for key, value in (args.get("algorithms") or {}).items()
    }

    def algo_of(member) -> str:
        return str(algorithms.get(member.label, algorithm))

    current = next((m for m in group if Path(m.path) == image_path), None)
    # 占位图不套用组阈值：它自己单独计算（用户 2026-10-25）。
    if current is None or current.placeholder or algo_of(current) != algorithm:
        return None
    real = [m for m in group if not m.placeholder]
    keys = {algo_of(m) for m in real}
    if len(keys) != 1:
        return None
    shared_algorithm = next(iter(keys))
    if shared_algorithm != algorithm or shared_algorithm in LOCAL_ALGORITHM_KEYS:
        return None

    grays = []
    for member in real:
        if Path(member.path) == image_path:
            grays.append(gray)
            continue
        try:
            from functions.rembg import load_rgb_and_gray

            _image, sibling_gray = load_rgb_and_gray(Path(member.path))
            grays.append(sibling_gray)
        except Exception:  # noqa: BLE001 - 对侧读不到就只用现有成员
            continue
    if not grays:
        return None
    try:
        base = get_algorithm(shared_algorithm).shared_threshold(grays)
    except Exception:  # noqa: BLE001 - 合并失败退回逐图
        return None
    if base is None:
        return None
    offset = int(args.get("offset", 0))
    return min(max(int(base) + offset, THRESHOLD_MIN), THRESHOLD_MAX)


def _record_method(out_dir: Path, stem: str, algorithm: str) -> None:
    """把这一页实际使用的算法写进 ``rembg_methods`` 侧车（失败静默）。

    ⚠️ 只对**正式产物目录**有效：``rembg_methods_path`` 只认 ``stages/`` 下的
    目录，草稿目录（``tasks/<任务号>/preview/...``）返回 None ⇒ 预览不会冒充
    "正式执行记录"（用户 2026-11-04）。
    """
    try:
        from desktop.steps.ports import rembg_methods_path
        from desktop.store.json_io import read_json, write_json

        path = rembg_methods_path(out_dir)
        if path is None:
            return
        data = read_json(path, {})
        if not isinstance(data, dict):
            data = {}
        data[str(stem)] = str(algorithm)
        write_json(path, data)
    except Exception:  # noqa: BLE001 - 记录不是主流程
        pass
