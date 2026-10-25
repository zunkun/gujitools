# -*- coding: utf-8 -*-
"""去底色参数实时调整的**单页重算**：直接覆盖正式成品。

用户口径（2026-10-22，任务 0014 报障）：

> 「在去底色步骤设置了 offset，没有能够传给下一步……图片任务目录下面要替换掉
>  rembg 下的图片」

所以这里**没有**"临时预览目录"：改 offset/type/印章或翻页时，当前页立刻按键入
参数重算，结果**覆盖** ``stages/rembg[~节点]/<页名>.png``（透明底 PNG，与
「执行去底色」的产物同规格），并顺带刷新第四步缩略图——不落进任务目录的话，
下一步「图片拼版 / PDF排版」拿到的还是旧图。

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
    """单页整图去底色 → **覆盖**正式成品（并刷新第四步缩略图），返回成品路径。

    ⚠️ 覆盖走「同目录 ``.part`` + ``os.replace``」：这份成品随时会被第四步查看器
    或拼版合成读到，直接 ``Image.save`` 会让人读到半截 PNG。``.part`` 后缀不在
    ``IMAGE_SUFFIXES`` 里，也不会被当成一页。
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

    实时调整会**覆盖正式成品**，所以执行记录也要跟着改：否则页面看着是
    Sauvola 的结果，侧车里还写着上一轮全量的 Otsu。
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
