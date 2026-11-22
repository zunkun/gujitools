# -*- coding: utf-8 -*-
"""去底色算法族自测：7 种算法、Otsu 向后兼容、分块计算等价、面板参数。

用户 2026-10-24 口径：去底色要有算法下拉，默认 Otsu；选算法后能实时预览；
局部算法（Niblack / Sauvola / Bernsen / Wolf-Jolion）要固定一套入口/出口。

本模块钉住四件事：

1. **注册表与命令规格同源**：算法 key 集合 == CLI/校验用的 ``REMBG_ALGORITHMS``；
2. **Otsu 与旧实现逐像素一致**（历史任务默认算法，不能悄悄改结果）；
3. **局部算法分块计算与整页计算等价**（halo/BORDER_REPLICATE 没写错）；
4. **面板默认值/置灰逻辑/参数收集**（算法下拉、窗口、k）。
"""

NAME = "rembg_algorithms"
DEPENDS: list[str] = []
TITLE = "去底色算法族"

import numpy as np


def _synthetic_page() -> np.ndarray:
    """一张 700×900 的合成页（跨两个分块，含暗块/亮块/渐变噪声）。"""
    rng = np.random.default_rng(7)
    gray = (rng.random((700, 900)) * 255).astype(np.uint8)
    gray[100:200, 100:400] = 30
    gray[300:450, 500:850] = 200
    return gray


def _rgb(gray: np.ndarray) -> np.ndarray:
    return np.repeat(gray[:, :, None], 3, axis=2)


def _reference_thresholds(gray: np.ndarray, window: int, k: float) -> dict:
    """整页（不分块）计算的阈值图，用来验分块版本没有边界误差。"""
    import cv2

    from utils.rembg_algorithms import _to_u8

    values = gray.astype(np.float32)
    mean = cv2.boxFilter(
        values, cv2.CV_32F, (window, window),
        normalize=True, borderType=cv2.BORDER_REPLICATE,
    )
    squared = cv2.boxFilter(
        values * values, cv2.CV_32F, (window, window),
        normalize=True, borderType=cv2.BORDER_REPLICATE,
    )
    std = np.sqrt(np.maximum(squared - mean * mean, 0.0))
    darkest = float(gray.min())
    refs = {
        "niblack": _to_u8(mean - abs(k) * std),
        "sauvola": _to_u8(mean * (1.0 + abs(k) * (std / 128.0 - 1.0))),
        "wolf": _to_u8(
            mean - abs(k) * (mean - darkest) * (1.0 - std / 128.0)
        ),
    }
    kernel = np.ones((window, window), np.uint8)
    low = cv2.erode(gray, kernel, borderType=cv2.BORDER_REPLICATE)
    high = cv2.dilate(gray, kernel, borderType=cv2.BORDER_REPLICATE)
    contrast = high.astype(np.int16) - low.astype(np.int16)
    middle = (low.astype(np.int16) + high.astype(np.int16)) // 2
    flat = np.where(middle < 128, 255, 0)
    refs["bernsen"] = _to_u8(np.where(contrast >= 15, middle, flat))
    return refs


def run(ctx) -> None:
    from core.command_spec import COMMAND_SPECS, REMBG_ALGORITHMS
    from tests.selftests._context import ok, pump
    from utils import image_utils
    from utils.rembg_algorithms import (
        ALGORITHM_KEYS,
        ALGORITHMS,
        LOCAL_ALGORITHM_KEYS,
        get_algorithm,
    )

    # ---- 1. 注册表同源 ----
    ok("算法 key 与命令规格枚举一致",
       ALGORITHM_KEYS == REMBG_ALGORITHMS,
       f"{ALGORITHM_KEYS} vs {REMBG_ALGORITHMS}")
    ok("默认算法是 otsu，默认窗口/k 已登记",
       COMMAND_SPECS["rembg"].defaults.get("algorithm") == "otsu"
       and COMMAND_SPECS["rembg"].defaults.get("window") == 25
       and COMMAND_SPECS["rembg"].defaults.get("k") == 0.2,
       str(COMMAND_SPECS["rembg"].defaults))
    ok("每种算法都有非空中文文案",
       all(item.label and item.description for item in ALGORITHMS),
       str([item.key for item in ALGORITHMS]))

    gray = _synthetic_page()
    rgb = _rgb(gray)

    # ---- 2. Otsu 与旧实现逐像素一致 ----
    non_white = gray < 250
    threshold = image_utils.calculate_auto_threshold(gray[non_white])
    threshold = min(max(threshold, 30), 240)
    legacy = image_utils.apply_otsu_whole(rgb, gray, threshold, None, False, 1)
    current = image_utils.rembg_page(rgb, gray, algorithm="otsu")
    ok("Otsu 默认算法与旧 apply_otsu_whole 逐像素一致",
       np.array_equal(legacy, current),
       f"diff={int((legacy != current).sum())}")
    ok("默认算法不传 algorithm 时仍走 Otsu",
       np.array_equal(image_utils.rembg_page(rgb, gray), current))

    # ---- 3. 每种算法都能出掩码，且结果彼此不同 ----
    counts: dict[str, int] = {}
    for key in ALGORITHM_KEYS:
        result = image_utils.rembg_page(rgb, gray, algorithm=key)
        mask = get_algorithm(key).text_mask(gray)
        ok(f"{key} 输出尺寸正确", result.shape == gray.shape, str(result.shape))
        ok(f"{key} 掩码为 bool 且非空非满",
           mask.dtype == np.bool_ and 0 < int(mask.sum()) < mask.size,
           f"sum={int(mask.sum())}/{mask.size}")
        counts[key] = int((result == 0).sum())
    ok("切换算法会改变去底色结果（不是永远走同一条分支）",
       len(set(counts.values())) > 1, str(counts))

    # ---- 3b. 阈值偏移只对全局算法生效 ----
    local_with = image_utils.rembg_page(rgb, gray, algorithm="sauvola", offset=50)
    local_without = image_utils.rembg_page(rgb, gray, algorithm="sauvola", offset=0)
    ok("局部算法忽略 offset（逐像素阈值上叠全局常量无意义）",
       np.array_equal(local_with, local_without),
       f"差异={int((local_with != local_without).sum())}")
    global_with = image_utils.rembg_page(rgb, gray, algorithm="fixed", offset=40)
    global_without = image_utils.rembg_page(rgb, gray, algorithm="fixed", offset=0)
    ok("全局算法仍然使用 offset",
       not np.array_equal(global_with, global_without),
       f"差异={int((global_with != global_without).sum())}")

    # ---- 4. 分块计算 == 整页计算（跨块边界也不能差） ----
    window, k = 25, 0.2
    refs = _reference_thresholds(gray, window, k)
    for key, thresholds in refs.items():
        mask = get_algorithm(key).text_mask(
            gray, offset=0, window=window, k=k
        )
        reference = gray < thresholds
        ok(f"{key} 分块计算与整页计算逐像素一致",
           np.array_equal(mask, reference),
           f"{key} 差异={int((mask != reference).sum())}")
        ok(f"{key} 属于局部算法集合", key in LOCAL_ALGORITHM_KEYS, key)

    # ---- 5. 未知算法直接报错，不静默回落 ----
    raised = ""
    try:
        image_utils.rembg_page(rgb, gray, algorithm="not-an-algorithm")
    except ValueError as exc:
        raised = str(exc)
    ok("未知算法抛出 ValueError 并列出可选值",
       "otsu" in raised and "sauvola" in raised, raised)

    # ---- 6. 面板：默认值 / 置灰 / 参数收集 ----
    from desktop.components.panels.rembg_panel import RembgPanel

    panel = RembgPanel()
    ok("面板默认算法为 Otsu",
       panel._combo_value(panel.algorithm) == "otsu",
       str(panel._combo_value(panel.algorithm)))
    ok("面板默认窗口 25 / k 0.2",
       panel.local_window.value() == 25 and abs(panel.k.value() - 0.2) < 1e-9,
       f"{panel.local_window.value()} / {panel.k.value()}")
    ok("全局算法时窗口/k 置灰",
       not panel.local_window.isEnabled() and not panel.k.isEnabled())

    edited: list[int] = []
    algorithm_edited: list[int] = []
    panel.param_edited.connect(lambda: edited.append(1))
    panel.algorithm_edited.connect(lambda: algorithm_edited.append(1))
    index = panel.algorithm.findData("sauvola")
    panel.algorithm.setCurrentIndex(index)
    pump(ctx.app, times=1)
    args = panel.get_args()
    ok("切到 Sauvola 后窗口/k 可用",
       panel.local_window.isEnabled() and panel.k.isEnabled())
    ok("get_args 收集 algorithm/window/k",
       args.get("algorithm") == "sauvola"
       and args.get("window") == 25 and abs(float(args["k"]) - 0.2) < 1e-9,
       str({key: args.get(key) for key in ("algorithm", "window", "k")}))
    ok("用户改算法会触发 param_edited 与 algorithm_edited",
       len(edited) == 1 and len(algorithm_edited) == 1,
       f"param={edited} algorithm={algorithm_edited}")

    # 改窗口/k 只算普通参数改动：不能把当前页的算法"钉死"（否则以后换全局
    # 算法时这张图不会跟随）。
    panel.local_window.setValue(31)
    pump(ctx.app, times=1)
    ok("改窗口不触发 algorithm_edited（逐张算法只在真的切算法时记录）",
       len(edited) == 2 and len(algorithm_edited) == 1,
       f"param={edited} algorithm={algorithm_edited}")
    panel.local_window.setValue(25)

    # 阈值偏移与窗口/k 对称置灰：局部算法不用 offset（逐像素阈值），
    # 且切到局部算法时必须把偏移归零，避免把上一轮的全局偏移带进去。
    ok("局部算法时阈值偏移置灰并归零",
       not panel.offset.isEnabled() and not panel.offset_input.isEnabled()
       and panel.offset.value() == 0
       and abs(panel._offset_effect.opacity() - 0.36) < 1e-6,
       f"enabled={panel.offset.isEnabled()} value={panel.offset.value()} "
       f"opacity={panel._offset_effect.opacity()}")
    panel.algorithm.setCurrentIndex(panel.algorithm.findData("otsu"))
    pump(ctx.app, times=1)
    panel.offset.setValue(12)
    pump(ctx.app, times=1)
    ok("全局算法下阈值偏移可用且可设值",
       panel.offset.isEnabled() and panel.offset_input.isEnabled()
       and panel.offset.value() == 12
       and abs(panel._offset_effect.opacity() - 1.0) < 1e-6,
       f"enabled={panel.offset.isEnabled()} value={panel.offset.value()} "
       f"opacity={panel._offset_effect.opacity()}")
    panel.algorithm.setCurrentIndex(index)
    pump(ctx.app, times=1)
    ok("切到局部算法：阈值偏移置灰并归零（含可见的不透明度）",
       not panel.offset.isEnabled() and not panel.offset_input.isEnabled()
       and panel.offset.value() == 0
       and abs(panel._offset_effect.opacity() - 0.36) < 1e-6,
       f"enabled={panel.offset.isEnabled()} value={panel.offset.value()} "
       f"opacity={panel._offset_effect.opacity()}")

    _edited_before_apply = len(edited)
    _algorithm_before_apply = len(algorithm_edited)

    panel.apply_args({"algorithm": "fixed", "window": 31, "k": 0.35})
    ok("历史参数回填算法/窗口/k 且不算用户改动",
       panel._combo_value(panel.algorithm) == "fixed"
       and panel.local_window.value() == 31
       and abs(panel.k.value() - 0.35) < 1e-9
       and len(edited) == _edited_before_apply
       and len(algorithm_edited) == _algorithm_before_apply,
       f"{panel._combo_value(panel.algorithm)} / {panel.local_window.value()} / {panel.k.value()}")
    ok("回填全局算法后窗口/k 再次置灰",
       not panel.local_window.isEnabled() and not panel.k.isEnabled())
    panel.deleteLater()

    # ---- 7. 侧车落点只认任务目录 ----
    from pathlib import Path

    from desktop.steps.ports import rembg_methods_path

    ok("模块页/自测的临时目录不生成 rembg_methods 侧车",
       rembg_methods_path(Path(ctx.tmp) / "rembg_out") is None)
    task_layout = Path(ctx.tmp) / "task" / "stages" / "rembg"
    ok("任务目录的侧车落在任务根目录",
       rembg_methods_path(task_layout) == Path(ctx.tmp) / "task" / "rembg_methods.json",
       str(rembg_methods_path(task_layout)))
    node_layout = Path(ctx.tmp) / "task" / "stages" / "rembg~Node_2"
    ok("副本节点的侧车带节点后缀",
       rembg_methods_path(node_layout)
       == Path(ctx.tmp) / "task" / "rembg_methods~Node_2.json",
       str(rembg_methods_path(node_layout)))
