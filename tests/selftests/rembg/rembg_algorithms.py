# -*- coding: utf-8 -*-
"""去底色算法族自测：11 种算法（含 6 种扩展）、Otsu 向后兼容、分块计算等价、面板参数。

用户 2026-10-24 口径：去底色要有算法下拉，默认 Otsu；选算法后能实时预览；
局部算法（Niblack / Sauvola / Bernsen / Wolf-Jolion）要固定一套入口/出口。
用户 2026-11-23 口径：去掉「固定阈值(fixed)」与「全局均值(mean)」；补 6 种
扩展算法（NICK / Feng / Parker 对比度 / Gatos / Howe / Su）；名称后不带
「试验/实验」字样，且每种算法给一套推荐默认参数（选中即带上）。

本模块钉住六件事：

1. **注册表与命令规格同源**：算法 key 集合 == CLI/校验用的 ``REMBG_ALGORITHMS``，
   已下线的 fixed/mean 不在候选里，算法名称不带「试验/实验」；
2. **Otsu 与旧实现逐像素一致**（历史任务默认算法，不能悄悄改结果）；
3. **局部算法分块计算与整页计算等价**（halo/BORDER_REPLICATE 没写错；对
   背景估计类扩展算法，缩小块大小后也必须逐像素一致，否则会在块缝处出接缝）；
4. **扩展算法能出「能看的」结果**：笔画实心（不是空心描边）、纸面不成片变黑、
   字腔不被暗洞回填吞掉——这三条用「纸 + 笔画」合成页量化；
5. **推荐参数三层一致**：``recommended_params`` ↔ 面板切算法自动回填 ↔ CLI
   没给 ``--window/--k`` 时的注入，口径必须相同；且推荐值本身要达标；
6. **面板默认值/置灰逻辑/参数收集**（算法下拉、窗口、k）。
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


def _stroke_page() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """「纸 + 笔画」合成页：纸面 205 带渐变与噪声、笔画 60、含一个「口」形环。

    钉住扩展算法的三件事（都对应真实页面上已经犯过的错）：

    * 笔画要**实心**——Parker / Howe 的判据只看「比邻域更暗」，直接落地是
      空心描边，笔画召回率会掉到 0.5；
    * 纸面不能成片变黑——Parker 把 D 空间判据映射回灰度阈值后，阈值正好压在
      纸面灰度上（干净纸面误判 51%）；
    * 字腔（口/日中间的空白）不能被回填吞掉。

    返回 ``(灰度页, 笔画掩码, 字腔掩码)``。
    """
    rng = np.random.default_rng(11)
    height, width = 600, 900
    rows, cols = np.mgrid[0:height, 0:width]
    paper = 205.0 - 0.03 * cols + 0.01 * rows + rng.normal(0, 6.0, (height, width))
    stroke = np.zeros((height, width), bool)
    for x in range(60, 860, 60):
        if 396 <= x <= 524:  # 「口」所在列留白，免得竖笔画扎进字腔
            continue
        stroke[80:520, x:x + 12] = True
    ring = np.zeros((height, width), bool)
    ring[240:360, 400:520] = True
    ring[252:348, 412:508] = False
    stroke |= ring
    gray = np.clip(
        np.where(stroke, 60.0, paper) + rng.normal(0, 3.0, (height, width)), 0, 255
    )
    cavity = np.zeros((height, width), bool)
    cavity[252:348, 412:508] = True
    return gray.astype(np.uint8), stroke, cavity


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
        ALGORITHM_CATEGORIES,
        ALGORITHM_KEYS,
        ALGORITHMS,
        EXPERIMENTAL_ALGORITHM_KEYS,
        LOCAL_ALGORITHM_KEYS,
        algorithm_groups,
        get_algorithm,
        recommended_params,
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
    ok("已下线的 fixed/mean 不在候选与注册表里",
       "fixed" not in ALGORITHM_KEYS and "mean" not in ALGORITHM_KEYS,
       str(ALGORITHM_KEYS))
    ok("6 种扩展算法已登记，且名称里不带「试验/实验」字样",
       set(EXPERIMENTAL_ALGORITHM_KEYS) <= set(ALGORITHM_KEYS)
       and len(EXPERIMENTAL_ALGORITHM_KEYS) == 6
       and not any(
           "试验" in item.label or "实验" in item.label
           for item in ALGORITHMS
       ),
       str([item.label for item in ALGORITHMS]))

    # ---- 1b. 算法分类（下拉分组标题的唯一来源）----
    groups = algorithm_groups()
    ok("算法按 4 类分组，成员不重不漏且覆盖全部算法",
       [name for name, _ in groups]
       == [c for c in ALGORITHM_CATEGORIES
           if any(item.category == c for item in ALGORITHMS)]
       and sum(len(members) for _, members in groups) == len(ALGORITHMS)
       and [item.key for _, members in groups for item in members]
       == list(ALGORITHM_KEYS),
       str([(name, [i.key for i in members]) for name, members in groups]))
    # 面板是「按分类顺序插组标题」画的，候选表里同一分类必须相邻。
    seen_out: set[str] = set()
    last_category = ""
    contiguous = True
    for item in ALGORITHMS:
        if item.category != last_category:
            if item.category in seen_out:
                contiguous = False
                break
            seen_out.add(last_category)
            last_category = item.category
    ok("候选表里同一分类连续（下拉按分类插标题的前提）",
       contiguous and all(item.category in ALGORITHM_CATEGORIES for item in ALGORITHMS),
       str([(item.key, item.category) for item in ALGORITHMS]))
    ok("「全局阈值」组只有 Otsu，且只有它不吃窗口/灵敏度",
       [i.key for _, members in groups for i in members
        if i.category == ALGORITHM_CATEGORIES[0]] == ["otsu"]
       and all(
           (item.key not in LOCAL_ALGORITHM_KEYS)
           == (item.category == ALGORITHM_CATEGORIES[0])
           for item in ALGORITHMS
       ))

    # ---- 1c. 每种算法一套推荐默认参数（唯一来源：ALGORITHMS / recommended_params）----
    for item in ALGORITHMS:
        rec = recommended_params(item.key)
        ok(f"{item.key} 推荐参数在合法范围内",
           3 <= rec["window"] <= 201 and 0.0 <= rec["k"] <= 1.0,
           str(rec))
    ok("Otsu 推荐参数 = 阶段默认（25 / 0.2）",
       recommended_params("otsu") == {"window": 25, "k": 0.2},
       str(recommended_params("otsu")))
    ok("NICK 保持文献 k=0.20（Niblack 推荐 0.40）",
       recommended_params("nick")["k"] == 0.2
       and recommended_params("niblack")["k"] == 0.40,
       f"nick={recommended_params('nick')} niblack={recommended_params('niblack')}")
    ok("未知/已下线算法回落阶段默认（回填路径不能抛错）",
       recommended_params("fixed") == {"window": 25, "k": 0.2}
       and recommended_params(None) == {"window": 25, "k": 0.2},
       str(recommended_params("fixed")))

    # ---- 1c. CLI 不给 --window/--k 时按算法取推荐值 ----
    from core.args import CommandArgs

    cli_su = CommandArgs(command="rembg", input=".", algorithm="su")
    ok("CLI 不给参数时取算法推荐值（Su → 21 / 0.30）",
       cli_su.get("window") == 21 and abs(float(cli_su.get("k")) - 0.30) < 1e-9,
       f"{cli_su.get('window')} / {cli_su.get('k')}")
    cli_mixed = CommandArgs(command="rembg", input=".", algorithm="su", window=31)
    ok("CLI 显式给的键不被推荐值顶掉（只补没给的 k）",
       cli_mixed.get("window") == 31
       and abs(float(cli_mixed.get("k")) - 0.30) < 1e-9,
       f"{cli_mixed.get('window')} / {cli_mixed.get('k')}")
    cli_otsu = CommandArgs(command="rembg", input=".")
    ok("CLI 不指定算法仍是 Otsu + 25 / 0.2",
       cli_otsu.get("algorithm") == "otsu"
       and cli_otsu.get("window") == 25
       and abs(float(cli_otsu.get("k")) - 0.2) < 1e-9,
       f"{cli_otsu.get('algorithm')} / {cli_otsu.get('window')} / {cli_otsu.get('k')}")

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
    global_with = image_utils.rembg_page(rgb, gray, algorithm="otsu", offset=40)
    global_without = image_utils.rembg_page(rgb, gray, algorithm="otsu", offset=0)
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

    # ---- 4b. 全部局部算法：缩小块大小不能出现块缝 ----
    # 扩展算法里有「先估背景/梯度再做窗口统计」的两级滤波（Gatos/Parker），
    # halo 少一行就会在块边界留下竖直接缝；这里不重写公式，直接把块行数压小，
    # 要求与默认块大小逐像素一致。
    from utils import rembg_algorithms as rembg_module

    original_rows = rembg_module._BLOCK_ROWS
    try:
        for key in sorted(LOCAL_ALGORITHM_KEYS):
            algorithm = get_algorithm(key)
            whole = algorithm.text_mask(gray)
            rembg_module._BLOCK_ROWS = 64
            try:
                blocked = algorithm.text_mask(gray)
            finally:
                rembg_module._BLOCK_ROWS = original_rows
            ok(f"{key} 缩小块大小后逐像素一致（无块缝）",
               np.array_equal(whole, blocked),
               f"{key} 差异={int((whole != blocked).sum())}")
    finally:
        rembg_module._BLOCK_ROWS = original_rows

    # ---- 4c. 扩展算法质量门槛：实心笔画 / 纸面不成片变黑 / 字腔不被吞 ----
    # 只看「掩码非空非满」抓不到真问题：这几种算法第一次落地时全部通过尺寸与
    # 非空断言，实际出来的是空心描边 + 整页噪点。这里用「纸 + 笔画」的合成页
    # 量化三件事（见 _stroke_page 的说明）。
    page, stroke_pixels, cavity = _stroke_page()
    paper_pixels = (~stroke_pixels) & (~cavity)
    # nick 与 niblack 数学等价，平坦区出噪点是 Niblack 族的固有行为，不设纸面
    # 门槛（单独断言它俩逐像素一致）。
    for key in sorted(EXPERIMENTAL_ALGORITHM_KEYS - {"nick"}):
        mask = get_algorithm(key).text_mask(page)
        recall = float(mask[stroke_pixels].mean())
        false_ink = float(mask[paper_pixels].mean())
        cavity_ink = float(mask[cavity].mean())
        ok(f"{key} 笔画实心（召回 ≥ 0.95）", recall >= 0.95,
           f"{key} 召回={recall:.3f}")
        ok(f"{key} 纸面不成片变黑（≤ 5%）", false_ink <= 0.05,
           f"{key} 纸面误判={false_ink:.3f}")
        ok(f"{key} 字腔不被暗洞回填吞掉（≤ 10%）", cavity_ink <= 0.10,
           f"{key} 字腔={cavity_ink:.3f}")
    ok("nick 与 niblack 逐像素等价（同一公式，k 取负）",
       np.array_equal(
           get_algorithm("nick").text_mask(page),
           get_algorithm("niblack").text_mask(page),
       ))

    # ---- 4d. 推荐参数本身也要达标（别把"最优"调成只剩噪点或吃掉笔画）----
    for key in sorted(EXPERIMENTAL_ALGORITHM_KEYS - {"nick"}):
        rec = recommended_params(key)
        mask = get_algorithm(key).text_mask(
            page, window=rec["window"], k=rec["k"]
        )
        recall = float(mask[stroke_pixels].mean())
        false_ink = float(mask[paper_pixels].mean())
        ok(f"{key} 按其推荐参数（win={rec['window']} / k={rec['k']:.2f}）仍达标",
           recall >= 0.95 and false_ink <= 0.05,
           f"召回={recall:.3f} 纸面误判={false_ink:.3f}")

    # ---- 5. 未知算法直接报错，不静默回落 ----
    raised = ""
    try:
        image_utils.rembg_page(rgb, gray, algorithm="not-an-algorithm")
    except ValueError as exc:
        raised = str(exc)
    ok("未知算法抛出 ValueError 并列出可选值",
       "otsu" in raised and "sauvola" in raised, raised)

    # ---- 6. 面板：默认值 / 置灰 / 参数收集 ----
    from pathlib import Path as _Path

    from desktop.components.panels import rembg_params_memory as param_memory
    from desktop.components.panels.rembg_panel import RembgPanel

    # ⚠️ 面板构造会读「每种算法手调过的值」（数据根 ``ui.json``）。测试必须先把
    #    落点指到临时目录，否则一面读用户的真实偏好、一面把测试值写进用户数据。
    #    补丁打在**使用方**（记忆模块的 ``ui_path``），面板调 ``load()`` 时才解析。
    memory_file = _Path(ctx.tmp) / "ui_memory" / "ui.json"
    param_memory.ui_path = lambda: memory_file
    param_memory.clear_all()

    panel = RembgPanel()
    ok("面板默认算法为 Otsu",
       panel._combo_value(panel.algorithm) == "otsu",
       str(panel._combo_value(panel.algorithm)))
    ok("面板默认窗口 25 / k 0.2",
       panel.local_window.value() == 25
       and abs(panel.get_args()["k"] - 0.2) < 1e-9,
       f"{panel.local_window.value()} / {panel.get_args()['k']}")
    ok("全局算法时窗口/k 置灰",
       not panel.local_window.isEnabled() and not panel.k.isEnabled())

    # 下拉按分类分组：4 个灰显组标题 + 11 个算法项。
    header_indexes = sorted(panel._group_header_indexes)
    ok("下拉含 4 个分组标题、共 15 项",
       len(header_indexes) == 4 and panel.algorithm.count() == 15,
       f"headers={header_indexes} count={panel.algorithm.count()}")
    ok("分组标题的 itemData 为空（不会与算法 key 混淆）",
       all(panel.algorithm.itemData(i) is None for i in header_indexes),
       str([panel.algorithm.itemData(i) for i in header_indexes]))
    ok("可选算法顺序 = ALGORITHM_KEYS（同一分类相邻）",
       [panel.algorithm.itemData(i) for i in range(panel.algorithm.count())
        if i not in panel._group_header_indexes] == list(ALGORITHM_KEYS),
       str([panel.algorithm.itemData(i) for i in range(panel.algorithm.count())
            if i not in panel._group_header_indexes]))
    ok("分组标题文案与 ALGORITHM_CATEGORIES 一致",
       [panel.algorithm.itemText(i) for i in header_indexes]
       == list(ALGORITHM_CATEGORIES),
       str([panel.algorithm.itemText(i) for i in header_indexes]))
    panel.algorithm.setCurrentIndex(header_indexes[0])  # 强行落到组标题
    ok("落到分组标题时按阶段默认算法取值（组名不会当算法）",
       panel._combo_value(panel.algorithm) == "otsu",
       str(panel._combo_value(panel.algorithm)))
    panel.algorithm.setCurrentIndex(panel.algorithm.findData("otsu"))

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

    panel.apply_args({"algorithm": "otsu", "window": 31, "k": 0.35})
    ok("历史参数回填算法/窗口/k 且不算用户改动",
       panel._combo_value(panel.algorithm) == "otsu"
       and panel.local_window.value() == 31
       and abs(panel.get_args()["k"] - 0.35) < 1e-9
       and len(edited) == _edited_before_apply
       and len(algorithm_edited) == _algorithm_before_apply,
       f"{panel._combo_value(panel.algorithm)} / {panel.local_window.value()} / {panel.get_args()['k']}")
    ok("回填全局算法后窗口/k 再次置灰",
       not panel.local_window.isEnabled() and not panel.k.isEnabled())

    # 老任务 ui.json 里可能还留着已下线的 fixed/mean：面板回落到第一项（Otsu），
    # 不能崩，也不能把非法 key 再交出去。
    panel.apply_args({"algorithm": "fixed", "window": 25, "k": 0.2})
    ok("历史参数里的已下线算法回落到 Otsu",
       panel._combo_value(panel.algorithm) == "otsu"
       and panel.get_args()["algorithm"] == "otsu",
       str(panel.get_args().get("algorithm")))
    panel.deleteLater()

    # ---- 6b. 推荐参数回填（用独立面板，别打乱上面那组计数断言）----
    rec_panel = RembgPanel()
    rec_edited: list[int] = []
    rec_algorithm_edited: list[int] = []
    rec_panel.param_edited.connect(lambda: rec_edited.append(1))
    rec_panel.algorithm_edited.connect(lambda: rec_algorithm_edited.append(1))
    rec_panel.algorithm.setCurrentIndex(rec_panel.algorithm.findData("parker"))
    pump(ctx.app, times=1)
    parker_args = rec_panel.get_args()
    ok("切到 Parker 自动带上推荐参数（41 / 0.20）",
       parker_args["window"] == 41 and abs(float(parker_args["k"]) - 0.20) < 1e-9,
       f"{parker_args['window']} / {parker_args['k']}")
    ok("自动回填推荐参数不算用户改动（只记 1 次 param_edited，来自算法本身）",
       len(rec_edited) == 1 and len(rec_algorithm_edited) == 1,
       f"param={rec_edited} algorithm={rec_algorithm_edited}")

    rec_panel.local_window.setValue(61)  # 用户手改窗口与灵敏度
    rec_panel.k.setValue(55)
    pump(ctx.app, times=1)
    rec_panel.algorithm.setCurrentIndex(rec_panel.algorithm.findData("howe"))
    pump(ctx.app, times=1)
    howe_args = rec_panel.get_args()
    ok("切算法无条件换成新算法的最优值（覆盖手改的 61 / 0.55）",
       howe_args["window"] == 25 and abs(float(howe_args["k"]) - 0.30) < 1e-9,
       f"{howe_args['window']} / {howe_args['k']}")

    # 用户 2026-11-24 报的场景：任务详情页里参数已回填（含手改值）之后切算法，
    # 最优值也必须跟着切。
    rec_panel.apply_args({"algorithm": "otsu", "window": 31, "k": 0.35})
    rec_panel.algorithm.setCurrentIndex(rec_panel.algorithm.findData("niblack"))
    pump(ctx.app, times=1)
    switch_args = rec_panel.get_args()
    ok("回填过手改值后切算法，仍换成新算法最优值（Niblack 41 / 0.40）",
       switch_args["window"] == 41 and abs(float(switch_args["k"]) - 0.40) < 1e-9,
       f"{switch_args['window']} / {switch_args['k']}")

    rec_panel.apply_args({"algorithm": "su"})
    stored = rec_panel.get_args()
    ok("历史参数缺窗口/灵敏度时用该算法的推荐值（Su → 21 / 0.30）",
       stored["window"] == 21 and abs(float(stored["k"]) - 0.30) < 1e-9,
       f"{stored['window']} / {stored['k']}")
    rec_panel.apply_args({"algorithm": "su", "window": 33, "k": 0.15})
    stored = rec_panel.get_args()
    ok("历史参数里有窗口/灵敏度时原样回填（老任务按原参数复现）",
       stored["window"] == 33 and abs(float(stored["k"]) - 0.15) < 1e-9,
       f"{stored['window']} / {stored['k']}")
    rec_panel.reset_to_default()
    reset_args = rec_panel.get_args()
    ok("reset_to_default 回阶段默认（Otsu + 25 / 0.2）",
       reset_args["algorithm"] == "otsu"
       and reset_args["window"] == 25
       and abs(float(reset_args["k"]) - 0.2) < 1e-9,
       str({key: reset_args[key] for key in ("algorithm", "window", "k")}))
    rec_panel.deleteLater()

    # ---- 6c. 「自己调过的值」按算法记账：切回时恢复、重开程序后还在 ----
    param_memory.clear_all()
    # ⚠️ 回归：切算法本身**不能**记账。曾经挂在 param_edited 上，切算法时那个
    #    信号先到、面板还没换值 ⇒ 把上一个算法的窗口/灵敏度记到新算法名下
    #    （实测 su=115、gatos k=0.96 这种脏条目）。
    switch_only = RembgPanel()
    switch_only.algorithm.setCurrentIndex(switch_only.algorithm.findData("su"))
    switch_only.algorithm.setCurrentIndex(switch_only.algorithm.findData("gatos"))
    pump(ctx.app, times=1)
    ok("只切算法不产生记忆（必须是窗口/灵敏度真的被改过）",
       param_memory.load() == {},
       str(param_memory.load()))
    switch_only.deleteLater()

    mem_panel = RembgPanel()
    mem_panel.algorithm.setCurrentIndex(mem_panel.algorithm.findData("su"))
    pump(ctx.app, times=1)
    mem_args = mem_panel.get_args()
    ok("没有记忆时切到 Su 用推荐值（21 / 0.30）",
       mem_args["window"] == 21 and abs(float(mem_args["k"]) - 0.30) < 1e-9,
       f"{mem_args['window']} / {mem_args['k']}")

    mem_panel.local_window.setValue(45)
    mem_panel.k.setValue(45)  # 0.45
    pump(ctx.app, times=1)
    ok("手调后立即记下（ui.json 的 rembg_algorithm_params）",
       param_memory.load().get("su") == {"window": 45, "k": 0.45},
       str(param_memory.load()))

    mem_panel.algorithm.setCurrentIndex(mem_panel.algorithm.findData("howe"))
    pump(ctx.app, times=1)
    howe_mem = mem_panel.get_args()
    ok("切到没记忆的 Howe 仍用它的推荐值（25 / 0.30）",
       howe_mem["window"] == 25 and abs(float(howe_mem["k"]) - 0.30) < 1e-9,
       f"{howe_mem['window']} / {howe_mem['k']}")
    mem_panel.algorithm.setCurrentIndex(mem_panel.algorithm.findData("su"))
    pump(ctx.app, times=1)
    back_args = mem_panel.get_args()
    ok("切回 Su 用自己调过的 45 / 0.45（不是推荐值）",
       back_args["window"] == 45 and abs(float(back_args["k"]) - 0.45) < 1e-9,
       f"{back_args['window']} / {back_args['k']}")
    mem_panel.deleteLater()

    reopened = RembgPanel()  # 等价于重开程序：只靠 ui.json 恢复
    reopened.algorithm.setCurrentIndex(reopened.algorithm.findData("su"))
    pump(ctx.app, times=1)
    reopened_args = reopened.get_args()
    ok("新面板（重开程序）也能恢复手调值",
       reopened_args["window"] == 45 and abs(float(reopened_args["k"]) - 0.45) < 1e-9,
       f"{reopened_args['window']} / {reopened_args['k']}")

    # 调回推荐值 ⇒ 记忆删除（否则会把"默认值"当成用户最优一直带着）
    reopened.local_window.setValue(21)
    reopened.k.setValue(30)
    pump(ctx.app, times=1)
    ok("调回推荐值后删除该算法的记忆",
       "su" not in param_memory.load(),
       str(param_memory.load()))
    reopened.algorithm.setCurrentIndex(reopened.algorithm.findData("howe"))
    reopened.algorithm.setCurrentIndex(reopened.algorithm.findData("su"))
    pump(ctx.app, times=1)
    cleared_args = reopened.get_args()
    ok("记忆清掉后再切回 Su 回到推荐值（21 / 0.30）",
       cleared_args["window"] == 21 and abs(float(cleared_args["k"]) - 0.30) < 1e-9,
       f"{cleared_args['window']} / {cleared_args['k']}")
    reopened.deleteLater()

    # 重开程序后面板初值也要认记忆（默认算法是 Otsu）
    param_memory.remember("otsu", {"window": 31, "k": 0.35})
    fresh = RembgPanel()
    fresh_args = fresh.get_args()
    ok("重开后面板初值用该算法的手调值（Otsu 31 / 0.35）",
       fresh_args["window"] == 31 and abs(float(fresh_args["k"]) - 0.35) < 1e-9,
       f"{fresh_args['window']} / {fresh_args['k']}")
    fresh.deleteLater()
    param_memory.clear_all()

    # 坏文件 / 脏值 / 不碰别的键
    import json as _json

    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text("{ not json", encoding="utf-8")
    ok("ui.json 写坏时返回空记忆、不抛错", param_memory.load() == {})
    memory_file.write_text(
        _json.dumps(
            {
                "last_task": "0012",
                "rembg_algorithm_params": {
                    "su": {"window": 1, "k": 9},           # 越界 → 丢弃
                    "not-an-algorithm": {"window": 25, "k": 0.2},  # 未登记 → 丢弃
                    "niblack": {"window": 45, "k": 0.35},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ok("越界值/未登记算法被丢弃，合法条目保留",
       param_memory.load() == {"niblack": {"window": 45, "k": 0.35}},
       str(param_memory.load()))
    param_memory.remember("parker", {"window": 51, "k": 0.25})
    kept = _json.loads(memory_file.read_text(encoding="utf-8"))
    ok("写记忆不动 ui.json 的其它键（last_task 原样保留）",
       kept.get("last_task") == "0012"
       and kept["rembg_algorithm_params"].get("parker") == {"window": 51, "k": 0.25},
       str(kept))
    param_memory.clear_all()

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
