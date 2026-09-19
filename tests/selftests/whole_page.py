# -*- coding: utf-8 -*-
"""整页模式（area=4）自测：不调用 YOLO，整页即唯一文本框。

动机：处理的不是双栏古籍（普通 PDF），或古籍检测失败时，用户要的是
「整页去底色 → 打印」，而不是先让 YOLO 猜左右栏。area=4 把「整页」从
「没有框」的副作用升级为**一个显式、可编辑的框**。

守住四件事：
1. 参数层放行 area=4（`CROP_AREAS`），越界值仍被拒；
2. 检测层真的不加载 YOLO（worker 直接发整页框）；
3. 几何层整页框 = 整页画布，border 只加留白、**不做对称镜像**；
4. 派生层（提交条目/预览条目）按整页单条输出，不拆 -r/-l。

界面联动（第二步「整页模式」开关 ↔ 第三步 area）在 `rembg` 模块断言。
"""

NAME = "whole_page"
DEPENDS: list[str] = []
TITLE = "整页模式 area=4"


def run(ctx) -> None:
    import inspect
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from tests.selftests._context import ok

    # ---- 1. 参数层：area=4 放行，5 仍被拒 ----
    from core.command_spec import CROP_AREAS, WHOLE_PAGE_AREA, _validate_cropremove

    ok("WHOLE_PAGE_AREA 就是 4", WHOLE_PAGE_AREA == 4, str(WHOLE_PAGE_AREA))
    ok("CROP_AREAS 含 4（crop/cropremove 校验放行）", 4 in CROP_AREAS, str(CROP_AREAS))
    base = {"area": 1, "type": 1, "sealarea": 80, "sealmin_sat": 50, "border": None}
    _validate_cropremove(dict(base, area=4))  # 不抛即通过
    ok("cropremove area=4 通过校验", True)
    try:
        _validate_cropremove(dict(base, area=5))
        ok("area=5 仍被拒绝", False, "校验没有抛错")
    except ValueError:
        ok("area=5 仍被拒绝", True)

    # ---- 2. 检测层：整页模式不加载 YOLO，直接发整页框 ----
    import desktop.stages.detect_stage as ds

    tmp = Path(tempfile.mkdtemp(prefix="guji_whole_page_"))
    page = tmp / "0001.png"
    W, H = 120, 160
    canvas = QImage(W, H, QImage.Format_RGB32)
    canvas.fill(Qt.white)
    ok("样例页写入成功（检测断言前提）", canvas.save(str(page)))

    collected: list = []
    original_emit = ds.emit
    ds.emit = lambda payload, stream=None: collected.append(payload)
    try:
        code = ds.run_detect({"image": str(page), "area": 4})
    finally:
        ds.emit = original_emit
    ok("整页模式单图检测返回 0", code == 0, str(code))
    boxes_events = [e for e in collected if e.get("type") == "boxes"]
    ok("整页模式直接给出整页框",
       boxes_events and boxes_events[0].get("left") == [0, 0, W, H],
       str(boxes_events))
    ok("整页模式不产出右框（不拆左右页）",
       boxes_events and boxes_events[0].get("right") is None, str(boxes_events))

    # 批量阶段：不加载模型，也不往 boxes.json 写自动框（无 page_boxes 事件）
    collected.clear()
    ds.emit = lambda payload, stream=None: collected.append(payload)
    try:
        code = ds.run_detect_stage(
            {
                "task_id": "t", "stage": "detect", "run_id": "r",
                "args": {"input": str(tmp), "area": 4},
            }
        )
    finally:
        ds.emit = original_emit
    ok("整页模式批量检测返回 0", code == 0, str(code))
    ok("批量整页检测不产出任何检测框",
       not [e for e in collected if e.get("type") == "page_boxes"],
       str(collected))
    ok("批量整页检测日志说明跳过 YOLO",
       any(e.get("type") == "log" and "跳过 YOLO" in str(e.get("message"))
           for e in collected),
       str(collected))
    finished = [e for e in collected if e.get("type") == "finished"]
    ok("批量整页检测进度走满",
       finished and finished[0].get("done") == finished[0].get("total") == 1,
       str(finished))

    # ---- 3. 几何层：整页框 = 整页画布，border 只加留白、不镜像 ----
    from desktop.workers.preview_worker import compose_region_output

    outputs = compose_region_output(canvas, [[0, 0, W, H]], 4, None)
    ok("整页框无 border → 输出仍是一张整页",
       len(outputs) == 1 and outputs[0].size() == canvas.size(),
       f"{len(outputs)} 张 / {outputs[0].size() if outputs else None}")
    padded = compose_region_output(canvas, [[0, 0, W, H]], 4, "10")
    gap_px = round(10 * 300 / 25.4)  # 10mm @300dpi
    ok("整页框 + border → 四周留白而非对称镜像",
       len(padded) == 1
       and padded[0].width() == W + gap_px * 2
       and padded[0].height() == H + gap_px * 2,
       f"{padded[0].size() if padded else None} 期望 {(W + gap_px * 2, H + gap_px * 2)}")

    # ---- 4. 派生层：整页单条，不拆 -r/-l ----
    from desktop.services.print_plan import plan_rembg_submit_entries

    def _entries(boxes, area):
        return plan_rembg_submit_entries(
            manifest_paths=[Path("0001.png")],
            result_path_for=lambda stem: Path(f"{stem}.png"),
            boxes_for=lambda _p: boxes,
            area=area,
        )

    # ⚠️ parea 必须是**原始 area**（4），不能被降级成 1：area=1 的语义是
    # 「紧裁成框」，而整页模式要的是整页——降级会让产物与预览不符。
    one = _entries([[0, 0, W, H]], 4)
    ok("整页模式单框 → 单条，parea 保留原始 area=4（非对称、非紧裁）",
       len(one) == 1 and one[0]["box"] == [0, 0, W, H]
       and one[0]["parea"] == 4
       and one[0]["boxes"] == [[0, 0, W, H]],
       str(one))
    two = _entries([[0, 0, 50, H], [60, 0, W, H]], 4)
    ok("整页模式多框 → 并集单条，不拆 -r/-l，且携带原始双框",
       len(two) == 1 and two[0]["box"] == [0, 0, W, H]
       and two[0]["parea"] == 4
       and len(two[0]["boxes"]) == 2,
       str(two))
    none = _entries([], 4)
    ok("整页模式无框 → 整页透传（兜底）",
       len(none) == 1 and none[0]["box"] is None, str(none))

    # 预览条目（第三步左侧缩略图条）与提交条目同规则
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget

    viewer = RembgPreviewWidget()
    viewer._paths = [Path("0001.png")]
    viewer._boxes_provider = lambda _p: [[0, 0, W, H]]
    viewer._region_params_provider = lambda: (4, None)
    built = viewer._build_entries()
    ok("预览条目：整页模式单条、带整页框，parea 同样保留原始 area",
       len(built) == 1 and built[0]["box"] == [0, 0, W, H]
       and built[0]["parea"] == 4,
       str(built))

    # ---- 5. CLI 层：area=4 在检测之前分流（源码守卫）----
    from functions.text_region import TextRegionProcessor

    src = inspect.getsource(TextRegionProcessor._process_single_image)
    ok("CLI 侧 area=4 在调用检测之前分流",
       "if area_mode == 4:" in src and src.index("if area_mode == 4:") < src.index(
           "detect_page_boxes"),
       "整页分支缺失或未挡在检测之前")
    ok("整页模式不预加载 YOLO 模型（改为按需加载）",
       TextRegionProcessor.__init__.__doc__ is not None
       and "延迟" in TextRegionProcessor.__init__.__doc__
       and "detect_page_boxes(img_bgr, self._model)" not in src,
       "模型仍在构造期加载或整页路径仍直接取 self._model")
