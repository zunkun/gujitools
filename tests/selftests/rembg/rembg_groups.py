# -*- coding: utf-8 -*-
"""去底色全局阈值的**同页左右裁图合并**自测。

用户 2026-10-25 口径：

1. YOLO 认出左右双栏、两张都真实存在 → 合在一起算阈值，应用到这两张；
2. 占位图不参与合并，自己单独计算阈值；
3. 半幅/整幅单张图各自计算；
4. 没有文本框的整页图按整图计算。

数据来源必须是**当前去底色节点上游最近的 detect 节点**的 ``boxes.json``
提交计划（``plan.outputs[].placeholder``），不靠文件名猜。本模块直接调
``run_rembg_stage`` 跑一个小任务，用产物反推实际用的阈值。
"""

NAME = "rembg_groups"
DEPENDS: list[str] = []
TITLE = "去底色同页阈值合并"

import numpy as np


def _page(value: int, width: int = 160, height: int = 120) -> np.ndarray:
    """白底 + 一块 ``value`` 灰度文字（非白像素 > 500，Otsu 不会退化成 128）。"""
    gray = np.full((height, width), 255, np.uint8)
    gray[20:100, 20:120] = value
    return gray


def _save_png(path, gray: np.ndarray) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.repeat(gray[:, :, None], 3, axis=2), "RGB").save(path)


def run(ctx) -> None:
    import json
    from pathlib import Path

    from PIL import Image

    from desktop.services.rembg_groups import group_files
    from tests.selftests._context import ok
    from utils.rembg_algorithms import get_algorithm

    tmp = Path(ctx.tmp)
    input_dir = tmp / "groups_input"
    out_dir = tmp / "groups_task" / "stages" / "rembg"
    boxes_path = tmp / "groups_task" / "boxes.json"
    boxes_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 1. 分组：计划里同源页的 l/r 合一组；占位标记随组带出 ----
    plan = {
        "35": {"page_class": "harfcontent", "outputs": [
            {"label": "35-l", "role": "half-left", "placeholder": False},
            {"label": "35-r", "role": "half-right", "placeholder": False},
        ]},
        "36": {"page_class": "harfcontent", "outputs": [
            {"label": "36-l", "role": "half-left", "placeholder": True},
            {"label": "36-r", "role": "half-right", "placeholder": False},
        ]},
        "37": {"page_class": "fullcontent", "outputs": [
            {"label": "37", "role": "full", "placeholder": False},
        ]},
    }
    boxes_path.write_text(json.dumps({k: {"plan": v} for k, v in plan.items()}),
                          encoding="utf-8")
    files = [
        input_dir / "35-l.png", input_dir / "35-r.png",
        input_dir / "36-l.png", input_dir / "36-r.png",
        input_dir / "37.png",
    ]
    groups = group_files(files, boxes_path)
    by_label = {m.label: m for group in groups for m in group}
    ok("同页 35-l / 35-r 落进同一组",
       any({m.label for m in g} == {"35-l", "35-r"} for g in groups),
       str([[m.label for m in g] for g in groups]))
    ok("36-l 被标记为占位、36-r 不是",
       by_label["36-l"].placeholder and not by_label["36-r"].placeholder)
    ok("整页 37 单独成组",
       any([m.label for m in g] == ["37"] for g in groups))
    ok("没有 boxes.json 时逐图分组（不猜左右）",
       all(len(g) == 1 for g in group_files(files, None)))

    # ---- 2. 合并阈值：单图与逐图一致；双图=直方图相加 ----
    grays = [_page(40), _page(120)]
    otsu = get_algorithm("otsu")
    ok("Otsu 单图的 shared_threshold == 逐图 thresholds",
       otsu.shared_threshold([grays[0]]) == otsu.thresholds(grays[0]))
    shared = otsu.shared_threshold(grays)
    pixels = np.concatenate([g[g < 250] for g in grays])
    from utils.image_utils import calculate_auto_threshold

    ok("Otsu 双图合并 == 合并非白像素后重新算",
       shared == calculate_auto_threshold(pixels),
       f"{shared} vs {calculate_auto_threshold(pixels)}")

    # ---- 3. 集成：真实跑一遍阶段，验证产物用的阈值 ----
    values = {"35-l": 40, "35-r": 120, "36-l": 60, "36-r": 130, "37": 90}
    for name, value in values.items():
        _save_png(input_dir / f"{name}.png", _page(value))

    from desktop.stages.rembg_stage import run_rembg_stage

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    code = run_rembg_stage({
        "task_id": "groups_task",
        "stage": "rembg",
        "run_id": "test",
        "args": {
            "input": str(input_dir),
            "_outpath": str(out_dir),
            "_boxes_path": str(boxes_path),
            "algorithm": "otsu",
            "offset": 0,
            "window": 25,
            "k": 0.2,
            "type": 1,
            "seal": False,
            "sealcolor": False,
            "sealarea": 80,
            "sealmin_sat": 50,
            "offsets": {},
            "algorithms": {},
            "clean": True,
        },
    })
    ok("阶段执行成功", code == 0, str(code))

    from functions.rembg import load_rgb_and_gray

    gray_l = load_rgb_and_gray(input_dir / "35-l.png")[1]
    gray_r = load_rgb_and_gray(input_dir / "35-r.png")[1]
    shared = get_algorithm("otsu").shared_threshold([gray_l, gray_r])
    own_l = get_algorithm("otsu").thresholds(gray_l)
    own_r = get_algorithm("otsu").thresholds(gray_r)
    ok("构造的样例确实能区分「共享」与「各算各的」",
       shared != own_l and shared != own_r,
       f"shared={shared} own_l={own_l} own_r={own_r}")

    def ink(path):
        with Image.open(path) as image:
            rgba = np.array(image.convert("RGBA"))
        return rgba[:, :, 3] > 0

    ok("35-l 用的是合并阈值",
       np.array_equal(ink(out_dir / "35-l.png"), gray_l < shared))
    ok("35-r 用的是同一个合并阈值",
       np.array_equal(ink(out_dir / "35-r.png"), gray_r < shared))

    gray_pl = load_rgb_and_gray(input_dir / "36-l.png")[1]
    ok("占位图 36-l 自己单独算阈值（不套用 36-r 的组阈值）",
       np.array_equal(
           ink(out_dir / "36-l.png"),
           gray_pl < get_algorithm("otsu").thresholds(gray_pl),
       ))
    gray_full = load_rgb_and_gray(input_dir / "37.png")[1]
    ok("整页 37 按整图计算阈值",
       np.array_equal(
           ink(out_dir / "37.png"),
           gray_full < get_algorithm("otsu").thresholds(gray_full),
       ))

    from desktop.store.json_io import read_json

    methods = read_json(boxes_path.parent / "rembg_methods.json", {})
    ok("执行记录侧车按页写下算法",
       set(methods) == set(values) and set(methods.values()) == {"otsu"},
       str(methods))
