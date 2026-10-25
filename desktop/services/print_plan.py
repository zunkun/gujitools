# -*- coding: utf-8 -*-
"""打印/提取条目的派生规则（纯函数，无 Qt 依赖，便于独立测试）。

这里的规则是 GUI 各阶段共享的「单一事实来源」：
- 提取缺页     → 续跑 extract 时的 pages 参数；
- 提交条目     → 「提交本次任务」的裁图条目派生；
- 待打印列表   → 第四步左侧列表的默认排序与持久化合并。

⚠️ 第四步**没有**"按当前参数临时合成"的规则：print 只排版前面步骤落盘的
成品图（检测提交裁好的图 + 去底色成品），见
``taskdetail.submit.SubmitMixin._build_print_effects``。
"""

from __future__ import annotations

from pathlib import Path

from utils.book_layout import (
    is_narrow_page,
    narrow_page_slots,
    page_single_wide_slots,
    typical_page_width,
)
from utils.box_geometry import (
    PAGE_CLASS_EMPTY,
    box_has_area,
    describe_page_slots,
    is_full_content,
)


#: 提交产物角色（写进 ``boxes.json`` 的提交计划，供拼版配对使用）。
#:
#: ⚠️ 与文件名后缀**不是**同一件事：``half-unsided`` 的产物**没有** ``-l``/``-r``
#: 后缀（单栏书 / 窄页归一化的结果），拼版必须靠计划里的角色才能把它当半幅。
ROLE_FULL = "full"                # 整幅 / 整页透传：单独一页
ROLE_HALF_LEFT = "half-left"      # 左半幅：产物名 <页>-l
ROLE_HALF_RIGHT = "half-right"    # 右半幅：产物名 <页>-r
ROLE_HALF_UNSIDED = "half-unsided"  # 半幅但侧别被归一化掉：产物名 <页>，可配对


# ---------------------------------------------------------------- extract 缺页
def missing_extract_pages_spec(output_dir: Path, total: int) -> str | None:
    """提取输出目录中缺失的页码，压缩为 CLI pages 参数（如 "3,7-9"）。

    页文件名以数字开头（0001.jpg / 0002.jpg …）。无缺失或 total 为 0
    时返回 None（无需续跑）。
    """
    present: set[int] = set()
    if output_dir.exists():
        for f in output_dir.iterdir():
            digits = ""
            for ch in f.stem:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if digits:
                present.add(int(digits))
    missing = [n for n in range(1, total + 1) if n not in present]
    if not missing or not total:
        return None
    parts: list[str] = []
    start: int | None = None
    prev: int | None = None
    for n in missing:
        if start is None:
            start = prev = n
        elif prev is not None and n == prev + 1:
            prev = n
        else:
            assert prev is not None
            parts.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = prev = n
    if start is not None:
        assert prev is not None
        parts.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ",".join(parts)


# ---------------------------------------------------------------- rembg 提交条目
def _valid_slots(slots) -> list:
    """槽位里的**零面积框**换成 ``None``（保留槽数，形态不变）。

    ⚠️ 保留槽数是关键：半幅恒 2 槽（`is_full_content` 靠槽数判整幅），
    ``[零宽框, 真框]`` 清理后必须仍是 ``[None, 真框]``，否则这一页会被当成
    整幅页。槽位约定见 ``utils.box_geometry``。
    """
    return [b if box_has_area(b) else None for b in (slots or [])]


def _average_size(boxes) -> tuple[int, int] | None:
    """一组框的**平均宽高**（像素，至少 1）；无有效框时 ``None``。

    占位图只用它定**尺寸**；落点用户 2026-10-23 追加为「**从中间截取**」，
    见 :func:`_center_box`。
    """
    sizes: list[tuple[int, int]] = [
        (int(b[2]) - int(b[0]), int(b[3]) - int(b[1]))
        for b in boxes or []
        if box_has_area(b)
    ]
    if not sizes:
        return None
    count = len(sizes)
    return (
        max(1, round(sum(w for w, _h in sizes) / count)),
        max(1, round(sum(h for _w, h in sizes) / count)),
    )


def _center_box(size, page_width, page_height, center_x=None) -> list[int] | None:
    """按**页面中心**（或指定的横向中心）截取给定尺寸的区域。

    用户 2026-10-23：「占位图原则**从中间截取**」——空白页没有框，落点不再
    抄别页的平均坐标（容易偏），直接取这一页正中的一块；双栏页的左右两张
    则各取**本半页的中心**（``center_x`` 传页宽 1/4、3/4）。

    页尺寸未知时退化为左上角起（宽已知则水平居中），并把尺寸夹进页面。
    """
    if not size:
        return None
    try:
        width, height = int(size[0]), int(size[1])
    except (TypeError, ValueError, IndexError):
        return None
    if width <= 0 or height <= 0:
        return None
    try:
        page_w = int(page_width or 0)
    except (TypeError, ValueError):
        page_w = 0
    try:
        page_h = int(page_height or 0)
    except (TypeError, ValueError):
        page_h = 0
    if page_w > 0:
        width = min(width, page_w)
    if page_h > 0:
        height = min(height, page_h)
    if center_x is not None:
        center = center_x
    elif page_w > 0:
        center = page_w / 2.0
    else:
        center = None
    x1 = 0 if center is None else round(center - width / 2.0)
    y1 = 0 if page_h <= 0 else round(page_h / 2.0 - height / 2.0)
    x1 = max(0, x1)
    if page_w > 0:
        x1 = min(x1, page_w - width)
    y1 = max(0, y1)
    return [x1, y1, x1 + width, y1 + height]


def _fit_box(box, page_width) -> list[int] | None:
    """占位框按**页宽**夹紧（水平方向）；无效/越界到零面积时返回 ``None``。

    平均框来自别的页，页宽可能略有出入（不同扫描批次）。超出页宽的框直接
    交给合成端会被裁掉一部分、剩下白边；先夹紧位置，截到的才是"原图内容"。
    高度不夹——规划层拿不到页高，合成端会按真实图高裁切。
    """
    if not box_has_area(box):
        return None
    x1, y1, x2, y2 = (int(v) for v in box)
    try:
        width = int(page_width)
    except (TypeError, ValueError):
        width = 0
    if width <= 0:
        return [x1, y1, x2, y2]
    x1 = max(0, min(x1, width - 1))
    x2 = min(width, max(x2, x1 + 1))
    if x2 <= x1:
        return None
    return [x1, y1, x2, y2]


def _mirror_box(box, page_width) -> list[int] | None:
    """把框以**页中线**为轴镜像——缺一侧时占位图的落点（用户 2026-10-23）。

    左右双栏页只有右栏时，左栏占位要截"对应位置"的原图内容：以页宽中线
    镜像右框，得到同样的尺寸、对称的位置。没有页宽时位置不动（至少尺寸对）。
    """
    if not box_has_area(box):
        return None
    x1, y1, x2, y2 = (int(v) for v in box)
    try:
        width = int(page_width)
    except (TypeError, ValueError):
        width = 0
    if width <= 0:
        return [x1, y1, x2, y2]
    return _fit_box([width - x2, y1, width - x1, y2], width)


def _placeholder_entries(stem: str, file_text: str, descriptors,
                         page_class: str = PAGE_CLASS_EMPTY) -> list[dict]:
    """占位描述 → 提交条目：**从该页原图的对应区域截一张**。

    ``descriptors`` 形如 ``[{"side": "left"|"right"|None, "box": [x1,y1,x2,y2],
    "role": "..."}]`` — ``box`` 是该页源图上的裁切区域（已按页宽夹紧）。
    条目与普通裁图条目同形（``file`` 仍是源页、``boxes`` 只有一个框），只多一个
    ``placeholder=True`` 标记：执行端照常裁剪，日志与统计据此区分"占位"与"真检测框"。

    ``role`` 缺省按 ``side`` 推：left/right → 半幅，无侧别 → 整幅。**单栏书 /
    窄页**的空白占位由调用方显式给 ``half-unsided``——它产物名不带后缀，但拼版
    要按半幅配对（见 :data:`ROLE_HALF_UNSIDED`）。
    """
    entries: list[dict] = []
    for item in descriptors or []:
        box = item.get("box")
        if not box_has_area(box):
            continue
        side = item.get("side")
        role = item.get("role")
        if role is None:
            role = (
                ROLE_HALF_LEFT if side == "left"
                else ROLE_HALF_RIGHT if side == "right"
                else ROLE_FULL
            )
        if side == "left":
            label = f"{stem}-l"
        elif side == "right":
            label = f"{stem}-r"
        else:
            label = stem
        entries.append({
            "file": file_text, "label": label, "box": list(box),
            "boxes": [list(box)], "full": side is None, "placeholder": True,
            "role": role, "page_class": page_class,
        })
    return entries


def plan_rembg_submit_entries(
    manifest_paths: list[Path],
    result_path_for,
    boxes_for,
    page_width_for=None,
    side_for=None,
    placeholder_for=None,
    narrow_for=None,
) -> list[dict]:
    """预览结果 + 检测框 + border → 最终图片条目（**逐框一张**）。

    参数
    ----
    manifest_paths   : 页面清单路径（stages/extract 内的页图片）
    result_path_for  : (stem) -> Path|None，某页对应的源图
    boxes_for        : (path_str) -> list，某页的检测框 [左框, 右框]
    page_width_for   : (path_str) -> 页宽像素，用于算单宽框（``None``/0 时
        该页不会被判成单宽框）。
    side_for         : (path_str) -> ``"left"``/``"right"``/None，用户在
        **半幅页**上指定的左右。给了指定就**不做**单栏归一化——那是用户在说
        「这页其实是某一边」（用户 2026-10-17），命名/拼版都要按左/右走。
    placeholder_for  : (path_str) -> list[dict]，该页缺图的**原图占位**描述
        ``[{"side": "left"|"right"|None, "box": [x1,y1,x2,y2]}]``（框是该页源图
        上的裁切区域）。只有「检测文本框 → 提交」会传它（用户 2026-10-23 的
        占位规则）；预览侧默认 ``None``，行为与改造前一字不变。
    narrow_for       : (path_str) -> bool，该页是否**窄于全书**（单页扫描）。
        为真且只检出一个框时退化成**单槽**（不拆 ``-l``/``-r``、不补另一栏），
        见 :func:`utils.book_layout.narrow_page_slots`。默认 ``None``＝不判断。

    派生规则（2026-10-22 起没有 area：**检测出几个框就裁几张图**）：
    - 双框：拆 <页>-r / <页>-l 两条（古籍阅读顺序 r 在前）；
    - 半幅漏检一侧：单条也保留左右身份（<页>-l / <页>-r，按缺失侧
      所在槽位判定）——否则产物叫 <页>.png，第四步拼版按文件名后缀判
      左右半幅时会把这页误当整幅（用户 2026-10-01 报）；
    - 整幅内容(fullcontent)：单槽单框，label 就是页名（不拆），框原样裁剪；
    - 单栏书：整本书只有一栏，页里不会有左页+右页，于是「单个宽框（≥60%
      页宽）的半幅页」被退化成**单槽**，直接继承整幅的语义；
    - 无框：整页原图透传（条目不带 effect）；**若有占位描述则改为占位条目**
      （空白页不再透传原图，见用户 2026-10-23 规则一~四）。
    最终按 CLI natural sort 排序（同页 r 在 l 前）。

    每条条目额外带 ``role`` / ``page_class``（**提交计划**，用户 2026-10-23）：
    ``role`` 是产物在拼版里的身份，``page_class`` 是**归一化前**的检测形态。
    ⚠️ 单栏书/窄页把半幅退化成单槽后，产物名不带 ``-l``/``-r``，但
    ``role`` 仍记 ``half-unsided``——拼版据此识别"无后缀但可配对"的图。
    """
    from utils.sort_utils import natural_sort_key

    entries: list[dict] = []
    for path in manifest_paths:
        result = result_path_for(path.stem)
        if result is None:
            continue  # 该页没有可用源图
        # ⚠️ 用**原始槽位**判断是否整幅内容：半幅固定 2 槽 [左,右]（可能含 null），
        #    整幅只占 1 槽。过滤 null 后两者都可能只剩 1 个框，届时无法区分——
        #    整幅页与「半幅漏检一侧」只能靠槽数区分。
        # ⚠️ 零面积框（1px 宽/高）**必须先剔掉再判形态**：它既不该多裁一张
        #    空白图，也不该让这页被当成「双栏页」而躲过单栏归一化
        #    （任务 0009 页码错位的根因，见 box_has_area）。
        pre_slots = _valid_slots(list(boxes_for(str(path)) or []))
        page_class = describe_page_slots(pre_slots)
        raw_boxes = list(pre_slots)
        # ⚠️ 单栏书：把「单个宽框」的半幅页**退化成单槽**（规则本体在
        #    ``utils.book_layout.single_column_slots``，第三步预览也调它），
        #    之后所有分支自动按整幅语义走——绝不能只在某个分支里改 label。
        # ⚠️ 用户指定过左右**优先于**一切归一化：那是在说"这页其实是某一边"。
        side_override = side_for(str(path)) if side_for is not None else None
        if side_override:
            pass  # 保持 2 槽 → 走 -l/-r 分支，下游按左右处理
        else:
            # ⚠️ **页级判据**（用户 2026-10-23，任务 0004）：单个宽框（≥60% 页宽）
            #    的半幅页直接退化成单槽，**不再要求整本书被判成单栏书**。
            #    一页只有一个 harfcontent 且框宽 >60% 时，中心位置没有鉴别力，
            #    按位置拆 -l/-r 基本是随机的。
            raw_boxes = page_single_wide_slots(
                raw_boxes,
                page_width_for(str(path)) if page_width_for is not None else None,
            )
            # ⚠️ 窄页（单页扫描，用户 2026-10-23）：只检出一个框时退化成单槽，
            #    不拆 -l/-r、也不补"另一栏"——那栏在这张图上根本放不下。
            if narrow_for is not None and narrow_for(str(path)):
                raw_boxes = narrow_page_slots(raw_boxes, True)
        full = is_full_content(raw_boxes)
        # 归一化前是「2 槽半幅」→ 即便产物名无后缀，也记成可配对的半幅。
        was_half = len(pre_slots) == 2 and any(pre_slots)
        boxes = [b for b in raw_boxes if b]
        extra = (
            _placeholder_entries(
                path.stem, str(result), placeholder_for(str(path)), page_class,
            )
            if placeholder_for is not None and len(boxes) < 2
            else []
        )
        if len(boxes) == 2:
            entries.append(
                {"file": str(result), "label": f"{path.stem}-r",
                 "box": boxes[1], "boxes": [boxes[1]], "full": False,
                 "role": ROLE_HALF_RIGHT, "page_class": page_class}
            )
            entries.append(
                {"file": str(result), "label": f"{path.stem}-l",
                 "box": boxes[0], "boxes": [boxes[0]], "full": False,
                 "role": ROLE_HALF_LEFT, "page_class": page_class}
            )
        elif len(boxes) == 1:
            label = path.stem
            role = ROLE_HALF_UNSIDED if (full and was_half) else ROLE_FULL
            if not full and len(raw_boxes) == 2:
                # 半幅(harfcontent)漏检一侧：单条也要保住 -l/-r 身份。
                # ⚠️ 判左右只能看**槽位**（半幅恒 2 槽 [左, 右]，见 half_slots），
                # 不能看框的中心——这里拿到的就是原始槽位。
                if raw_boxes[0]:
                    label, role = f"{path.stem}-l", ROLE_HALF_LEFT
                else:
                    label, role = f"{path.stem}-r", ROLE_HALF_RIGHT
            entries.append(
                {"file": str(result), "label": label, "box": boxes[0],
                 "boxes": [boxes[0]], "full": full,
                 "role": role, "page_class": page_class}
            )
        elif not extra:
            entries.append(
                {"file": str(result), "label": path.stem,
                 "box": None, "boxes": [], "full": False,
                 "role": ROLE_FULL, "page_class": page_class}
            )
        entries.extend(extra)
    entries.sort(key=lambda e: natural_sort_key(e["label"]))
    return entries


def entry_to_effect_spec(entry: dict, border) -> dict:
    """提交条目 → worker 效果合成规格（run_print_stage/run_detect_submit_stage 用）。

    ``effect`` 里只有 ``boxes`` 与 ``border``——2026-10-22 起没有 area，几何
    恒为「每个检测框各自剪一张图」（见 ``utils.box_geometry.build_output_layout``）。

    **占位条目**（``placeholder``，用户 2026-10-23）就是"该页原图上按占位框
    裁一张"——走**同一条** effect 路径，只多带一个 ``placeholder=True`` 标记
    供日志/统计区分（不再画纯白图）。
    """
    raw = [b for b in (entry.get("boxes") or []) if b]
    if not raw and entry.get("box"):
        raw = [entry["box"]]  # 兼容只带 box 的旧条目/手写条目
    spec = {
        "file": entry["file"],
        "label": entry.get("label"),
        "effect": (
            {"boxes": raw, "border": border}
            if raw
            else None
        ),
    }
    if entry.get("placeholder"):
        spec["placeholder"] = True
    return spec


def plan_submit_job(spec: dict, size: tuple[int, int] | None) -> dict:
    """一条效果规格 → 单条合成作业（输出文件名 + 合成参数）。

    ``size`` 是该条目图片的像素尺寸；``None`` 表示读不到文件头（坏图/被占用），
    该作业记 ``names=[]``——执行端据此报「无法读取图片」，不静默丢页。

    ⚠️ 输出文件名规则（``{label}.jpg``；多画布 ``{label}-N.jpg``）**只在这里
    一份**：检测提交裁图端（``desktop.stages.detect_stage``）与 worker 合成端
    （``desktop.workers.preview_worker``）共用它，命名不会两处各写一套而漂移。

    ⚠️ ``region_canvas_specs`` 走**函数内延迟导入**：本模块整体是不依赖 Qt 的
    纯逻辑（见模块 docstring），只有真要算输出张数时才拉进那份 Qt 几何实现。
    """
    from desktop.workers.preview_worker import region_canvas_specs

    label = str(spec.get("label") or Path(spec["file"]).stem)
    if size is None:
        return {
            "file": str(spec["file"]), "compose": False, "boxes": [],
            "border": None, "names": [], "label": label,
        }
    effect = spec.get("effect")
    if effect and any(effect.get("boxes") or []):
        boxes = list(effect.get("boxes") or [])
        border = effect.get("border")
        canvases = len(region_canvas_specs(size, boxes, border))
        has_boxes = True
    else:
        # 无检测框/无区域参数：整页预览图原样交付
        boxes, border = [], None
        canvases = 1
        has_boxes = False
    names = (
        [f"{label}.jpg"] if canvases == 1
        else [f"{label}-{i + 1}.jpg" for i in range(canvases)]
    )
    job = {
        "file": str(spec["file"]), "compose": has_boxes,
        "boxes": boxes, "border": border,
        "names": names, "label": label,
    }
    if spec.get("placeholder"):
        job["placeholder"] = True
    return job


def plan_detect_submit_entries(
    manifest_paths: list[Path],
    boxes_for,
    single_column_book: bool = False,
    page_width_for=None,
    side_for=None,
    book_profile=None,
    page_size_for=None,
) -> list[dict]:
    """「检测文本框 → 提交本次任务」的裁图条目（含**回溯占位**）。

    与 :func:`plan_rembg_submit_entries` **同一条规则**，只有两个区别：

    1. 合成源就是**源页图自己**（这一步不产生中间结果图），所以 ``file``
       直接是那一页的路径。**每个检测框各自裁成一张图**——没有 area；
    2. 它额外算「回溯占位」：漏检/空白页按**全书形态**补图，避免下游丢页
       或拼版错配（用户 2026-10-23 的四条规则）。

    **占位图不是纯白，而是从该页原图截对应区域**（用户 2026-10-23 追加），
    空白页的落点**以页面中心为准**（「占位图原则从中间截取」）：

    - **左右双栏书**：一页只有一侧框 → 缺失侧按**页中线镜像**已有那一侧，
      截同样大小的区域（规则一.1）；整页无框 → 截 **左、右两张**，各自以
      **本半页的中心**截取，尺寸取全书左右框各自的平均（规则一.2）；
    - **单栏书（半幅单宽框）**：整页无框 → 以**页面中心**截 **一张**，
      尺寸取全书半幅框平均（规则二）；
    - **整幅书**：整页无框 → 以**页面中心**截 **一张**，尺寸取全书整幅框
      平均（规则三）；
    - **混排书**（三种极端都不成立）：整页无框 → **完全跟随前一页**的产物
      形态（前页双框 → 补左右两张；前页单侧 → 补同侧一张；前页整幅/单栏 →
      补一张）；只有一侧框的页，前页是双框时才补缺失侧（规则四）。
      首页就空白（没有前一页）→ 向前找最近的有框页；全书都空白则不补。
    - **窄页**（页宽明显小于全书典型页宽＝单页扫描）**优先于以上全部**：
      这张图放不下第二栏，所以整页无框只补**一张**、只检出一个框也**不补**
      另一侧，命名也不带 ``-l``/``-r``（用户 2026-10-23，任务 0001 第 1 页）。

    ⚠️ 占位条目 ``file`` 仍是源页、``boxes`` 只有一个"占位框"，
    ``placeholder=True`` 只作日志/统计标记——执行端走与真框完全相同的裁剪
    路径（不画白图）。预览侧不会传 ``placeholder_for``，命名/条数保持原样。
    """
    from utils.book_layout import (
        BOOK_FORM_DOUBLE, BOOK_FORM_FULL, BOOK_FORM_MIXED, BOOK_FORM_SINGLE,
        book_form, profile_book,
    )
    from utils.box_geometry import (
        PAGE_CLASS_EMPTY, PAGE_CLASS_FULLCONTENT, PAGE_CLASS_HARFCONTENT,
        classify_page_slots,
    )

    by_stem = {path.stem: path for path in manifest_paths}
    # ⚠️ 先剔掉零面积框（保留槽数）：它会让单栏页被统计成「双栏页」，
    #    空白页的占位就会从 1 张错成 2 张（任务 0009）。
    raw_slots = {
        path.stem: _valid_slots(boxes_for(str(path)) or [])
        for path in manifest_paths
    }
    sizes: dict[str, tuple[int, int] | None] = {
        path.stem: (
            page_size_for(str(path)) if page_size_for is not None else None
        )
        for path in manifest_paths
    }

    def _page_width(stem: str):
        if page_width_for is not None:
            return page_width_for(str(by_stem[stem]))
        size = sizes.get(stem)
        return size[0] if size else None

    widths = {stem: _page_width(stem) for stem in by_stem}
    # 「窄页」= 单页扫描（页宽明显小于全书典型页宽，用户 2026-10-23）：
    # 这种页最多只有一栏，空白页只补一张、单框页不补另一侧。
    typical_width = typical_page_width(widths.values())
    narrow_pages = {
        stem: is_narrow_page(widths.get(stem), typical_width) for stem in by_stem
    }
    profile = book_profile or profile_book(
        [(stem, raw_slots[stem], widths[stem]) for stem in by_stem]
    )
    single = bool(single_column_book) or profile.single_column_book
    form = BOOK_FORM_SINGLE if single else book_form(profile)

    # 平均**尺寸**按原始槽位分组（半幅整体 / 左槽 / 右槽 / 整幅）：
    # 单栏书的归一化只是"身份改写"，不该把它的宽框混进整幅组。
    half_boxes = [
        b for slots in raw_slots.values() if len(slots) == 2 for b in slots if b
    ]
    left_boxes = [
        slots[0] for slots in raw_slots.values()
        if len(slots) == 2 and slots[0]
    ]
    right_boxes = [
        slots[1] for slots in raw_slots.values()
        if len(slots) == 2 and slots[1]
    ]
    full_boxes = [
        b for slots in raw_slots.values() if len(slots) == 1 for b in slots if b
    ]
    half_size = _average_size(half_boxes)
    left_size = _average_size(left_boxes) or half_size
    right_size = _average_size(right_boxes) or half_size
    full_size = _average_size(full_boxes) or half_size

    def _normalized(stem: str, boxes) -> list:
        """页级单宽归一化（用户指定过左右的页不归一化，与提交命名同一口径）。"""
        if side_for is not None and side_for(str(by_stem[stem])):
            return list(boxes)
        slots = page_single_wide_slots(boxes, widths[stem])
        return narrow_page_slots(slots, narrow_pages.get(stem, False))

    normalized = {stem: _normalized(stem, raw_slots[stem]) for stem in by_stem}

    # 每页的**产物形态**：double / half-left / half-right / full / column。
    # 只用于「混排书空白页跟随前一页」；空白页记 None。
    shapes: dict[str, str | None] = {}
    for stem, slots in normalized.items():
        kind = classify_page_slots(slots)
        if kind == PAGE_CLASS_EMPTY:
            shapes[stem] = None
        elif kind == PAGE_CLASS_FULLCONTENT:
            shapes[stem] = "column" if len(raw_slots[stem]) == 2 else "full"
        elif kind == PAGE_CLASS_HARFCONTENT:
            shapes[stem] = "double"
        else:
            shapes[stem] = "half-left" if slots[0] else "half-right"

    def _nearby_shape(index: int) -> str | None:
        """混排书里空白页的形态：先向前找，再向后找，全空白返回 None。"""
        for j in range(index - 1, -1, -1):
            shape = shapes.get(manifest_paths[j].stem)
            if shape:
                return shape
        for j in range(index + 1, len(manifest_paths)):
            shape = shapes.get(manifest_paths[j].stem)
            if shape:
                return shape
        return None

    def _shape_placeholders(shape: str | None, stem: str) -> list[dict]:
        """产物形态 → 占位描述（尺寸取全书同类框平均，落点取页面中心）。"""
        page_w = widths.get(stem) or 0
        page_size = sizes.get(stem)
        page_h = page_size[1] if page_size else 0
        items: list[dict] = []
        if shape == "double":
            # 双栏空白页：左右各取**本半页的中心**（页宽 1/4、3/4）
            for side, size, center in (
                ("left", left_size, page_w / 4.0 if page_w else None),
                ("right", right_size, page_w * 0.75 if page_w else None),
            ):
                box = _center_box(size, page_w, page_h, center_x=center)
                if box:
                    items.append({"side": side, "box": box})
        elif shape in ("half-left", "half-right"):
            side = shape.split("-", 1)[1]
            box = _center_box(
                left_size if side == "left" else right_size, page_w, page_h
            )
            if box:
                items.append({"side": side, "box": box})
        elif shape == "full":
            box = _center_box(full_size, page_w, page_h)
            if box:
                items.append({"side": None, "box": box})
        elif shape == "column":
            box = _center_box(half_size, page_w, page_h)
            if box:
                # 单栏书 / 窄页：产物名不带后缀，但它是"无侧半幅"——
                # 拼版要靠这个角色才能与相邻页配对（见 ROLE_HALF_UNSIDED）。
                items.append(
                    {"side": None, "box": box, "role": ROLE_HALF_UNSIDED}
                )
        return items

    placeholders: dict[str, list[dict]] = {}
    for index, path in enumerate(manifest_paths):
        stem = path.stem
        slots = normalized[stem]
        present = [b for b in slots if b]
        kind = classify_page_slots(slots)
        if kind == PAGE_CLASS_EMPTY:
            if narrow_pages.get(stem):
                # 单页扫描（窄于全书）：这张图最多一栏，只补一张
                shape = "column"
            elif form == BOOK_FORM_DOUBLE:
                shape = "double"
            elif form == BOOK_FORM_FULL:
                shape = "full"
            elif form == BOOK_FORM_SINGLE:
                shape = "column"
            else:
                shape = _nearby_shape(index)
            items = _shape_placeholders(shape, stem)
        elif len(slots) == 2 and len(present) == 1:
            # 缺一侧：只有双栏书（或混排时前一页是双框）才补缺失侧。
            # 落点 = 已有那一侧以页中线镜像，尺寸天然相同（规则一.1）。
            needed = form == BOOK_FORM_DOUBLE
            if form == BOOK_FORM_MIXED:
                prev_shape = None
                for j in range(index - 1, -1, -1):
                    prev_shape = shapes.get(manifest_paths[j].stem)
                    if prev_shape:
                        break
                needed = prev_shape == "double"
            items = []
            if needed:
                missing = "right" if slots[0] else "left"
                mirrored = _mirror_box(present[0], widths[stem])
                if mirrored:
                    items = [{"side": missing, "box": mirrored}]
        else:
            items = []
        if items:
            placeholders[stem] = items

    def placeholder_for(path_text: str) -> list[dict]:
        return placeholders.get(Path(path_text).stem, [])

    return plan_rembg_submit_entries(
        manifest_paths=manifest_paths,
        result_path_for=lambda stem: by_stem.get(stem),
        boxes_for=boxes_for,
        page_width_for=page_width_for,
        side_for=side_for,
        placeholder_for=placeholder_for,
        narrow_for=lambda text: narrow_pages.get(Path(text).stem, False),
    )


# ---------------------------------------------------------------- print 效果规格
# ---------------------------------------------------------------- 待打印列表
def drop_foreign_stage_pages(
    pages: list[dict] | None, source_dir: Path, stages_root: Path,
) -> list[dict]:
    """从待打印清单里剔除「属于本任务**别的阶段**产物」的条目。

    ⚠️ 为什么必须剔（2026-09-30 引入「图片拼版」时暴露）：``plan_print_entries``
    的规则是「不在当前来源目录里的条目 = 用户手动插入的外部图片，原样保留」。
    可第四步的来源会**切换**——拼版生效时用 ``stages/imposition``，否则用
    ``stages/rembg``。切过去之后，原先那一批还留在 ``print.json`` 里、又不在
    新来源目录下，就会被当成"用户插入的图"**追加到列表末尾**：出 PDF 时
    新旧两套整页全打进去（实测 2 页拼版 + 4 页去底色 = 6 页）。

    判据写死在"路径是否落在本任务的 ``stages/`` 下"：同任务其它阶段的产物
    永远是**上一轮来源**的残留，绝不可能是用户从磁盘上手动挑来的外部图片。
    真正的外部图片（桌面/下载目录…）一律保留。
    """
    if not pages:
        return list(pages or [])
    source = Path(source_dir)
    root = Path(stages_root)
    kept: list[dict] = []
    for page in pages:
        file_text = str(page.get("file") or "")
        if not file_text:
            kept.append(page)
            continue
        candidate = Path(file_text)
        if candidate.parent == source:
            kept.append(page)
            continue
        try:
            if candidate.parent.is_relative_to(root):
                continue  # 本任务别的阶段的产物 → 上一轮来源的残留
        except (TypeError, ValueError):
            pass
        kept.append(page)  # 真正的外部图片：保留用户的插入
    return kept


# ---------------------------------------------------------------- 待打印列表
#: 逐图 rect 与当前图像**宽高比**的最大相对偏差（老数据没记像素尺寸时的兜底判据）
RECT_ASPECT_TOLERANCE = 0.02


def rect_fits_image(rect, image_size_px, rect_size_px=None) -> bool:
    """这条逐页 rect 是否**还适用于当前这张图**（判据唯一处）。

    背景（用户 2026-10-18）：「上一步的输出归上一步，当前步 PDF排版，页面效果都
    要按相关参数来调整」。逐页 rect 是**用户在 A4 纸上摆出来的坐标**，它是按
    **画它时那张图的几何**量出来的：图像一换（拼版成品重合成、去底色重提交、
    编辑器回写），像素尺寸/宽高比就变了，再把旧框套上去 = 把新图**拉伸**进旧框
    ——A4 上的宽度与比例都是错的，本步参数（纸张/方向/边距/原比例）没起作用。

    判据分两档（新数据优先）：

    - ``rect_size_px``（画框时图像的像素尺寸，存在 ``pages[].rect_size`` 里）：
      **必须完全相等**。像素尺寸变了 ⇒ 页面 mm 与像素的换算比例已不同，旧框
      不再表达用户的意图（宽高比即使凑巧相同也不行）；
    - 没有记录（老数据）：退到**宽高比**容差（:data:`RECT_ASPECT_TOLERANCE`）。
      宽高比一致 = 还是"同一张尺寸的图"；不一致 = 这张图已经换了（半页 →
      对开页之类），旧框不再有效。

    读不到图像尺寸（文件刚被删/坏）时返回 ``True``（无从判断，保留用户排版）。
    """
    try:
        rect_w, rect_h = float(rect[2]), float(rect[3])
        img_w, img_h = float(image_size_px[0]), float(image_size_px[1])
    except (TypeError, ValueError, IndexError):
        return True
    if rect_w <= 0 or rect_h <= 0 or img_w <= 0 or img_h <= 0:
        return True
    if rect_size_px is not None:
        try:
            px_w, px_h = int(rect_size_px[0]), int(rect_size_px[1])
        except (TypeError, ValueError, IndexError):
            px_w = px_h = 0
        if px_w > 0 and px_h > 0:
            return (px_w, px_h) == (int(img_w), int(img_h))
    img_ratio = img_w / img_h
    return abs(rect_w / rect_h - img_ratio) <= RECT_ASPECT_TOLERANCE * img_ratio


def stale_rect_pages(pages, size_for) -> list[dict]:
    """``pages`` 里**图像已换、旧 rect 不再适用**的那几条（``[]`` = 全都还适用）。

    ``size_for``：``(路径文本) -> (宽, 高) | None``；为 ``None``（调用方拿不到
    尺寸，如 CLI）时一律返回空表——绝不能"读不到尺寸就当过期"，那会把用户
    精心调过的版面全部误清。

    返回项形如 ``{"file": …, "image": (宽, 高), "rect": [...]}``：调用方据此
    写**"上一步更新了哪些图片"的记录**（日志/界面提示），并据此失效这些页的
    缓存（旧版面、缩略图）。
    """
    if size_for is None or not pages:
        return []
    stale: list[dict] = []
    for page in pages:
        rect = page.get("rect")
        file_text = page.get("file")
        if rect is None or not file_text:
            continue
        try:
            size = size_for(str(file_text))
        except Exception:  # noqa: BLE001 - 读尺寸失败不该拦住建表
            size = None
        if size is None or not size[0] or not size[1]:
            continue
        if not rect_fits_image(rect, size, page.get("rect_size")):
            stale.append({
                "file": str(file_text),
                "image": (int(size[0]), int(size[1])),
                "rect": list(rect),
            })
    return stale


def ordered_page_record(entry: dict) -> dict:
    """待打印条目 → ``print.json`` 的 ``pages[]`` 记录（顺序/标签 + 有则带逐页版面）。

    字段：

    - ``file`` / ``label``：条目身份（顺序就是列表顺序，拖动即改这里）；
    - ``rect``：用户在 A4 纸上摆出来的坐标（mm），**有才写**（没有就走自动排版）；
    - ``rect_size``：**画这个框时那张图的像素尺寸**。它是"这张图的版面是按哪张图
      量的"的唯一凭据：图像后来被上游换掉（拼版成品重合成、去底色重提交）时，
      靠它判定旧框失效、改按当前 PDF排版参数重排（见 :func:`rect_fits_image`）。

    ⚠️ 落盘口径必须**唯一**：`print_list._save_print_order`（拖拽/删除后）与
    `runner`（生成 PDF 前）都写这份记录，两处各拼一份字段迟早漂移——改了这里
    两处跟着改。
    """
    page: dict = {"file": entry.get("file"), "label": entry.get("label")}
    if entry.get("rect") is not None:
        page["rect"] = list(entry["rect"])
        if entry.get("rect_size") is not None:
            page["rect_size"] = [int(v) for v in entry["rect_size"][:2]]
    return page


def plan_print_entries(
    rembg_files: list[Path], doc: dict | None, size_for=None,
) -> tuple[list[dict], dict]:
    """第四步待打印图片列表的规划。

    直接使用第三步「提交本次任务」产出的 stages/rembg 最终图片
    （已按 area/border 合成），按古籍阅读顺序（cover/menu 优先、
    同编号 r→l、数字自然序）排列。

    列表不再使用源 PDF 缩略图，直接显示 rembg 最终图片本身；
    print.json 仅持久化用户的拖动/删除/插入顺序。

    ``size_for``（可选）：``(路径文本) -> (宽, 高) | None``，读**当前**图片的
    像素尺寸。给了它，逐页 rect 会先过一遍 :func:`rect_fits_image`——**这张图
    已经不是画那个框时的那张**（被重合成/重提交换掉了）就不再套用旧框，让
    ``plan_print_page`` 按**当前参数**重新自动排版（用户 2026-10-18：
    「上一步的输出归上一步，当前步 PDF排版要按相关参数来调整」）。
    不给（默认）= 原样透传 rect，CLI/老调用方与既有往返语义一字不变。

    返回 (entries, doc)。
    """
    rembg_names = [str(p) for p in rembg_files]
    current_set = set(rembg_names)
    snapshot = set(doc.get("rembg_snapshot") or []) if doc else set()
    stale = {
        str(page["file"])
        for page in stale_rect_pages(doc.get("pages") if doc else None, size_for)
    }

    def _existing(pages) -> list[dict]:
        out, seen = [], set()
        for p in pages or []:
            file_text = p.get("file")
            if not file_text or file_text in seen or not Path(file_text).exists():
                continue
            entry = {"file": file_text,
                     "label": p.get("label") or Path(file_text).stem}
            # 第四步「版面编辑器」逐图坐标：存在则随条目保留（与 file/label 同级）。
            # ⚠️ 图像已经换了的那几页**不带 rect**：旧框是按旧图的像素尺寸/宽高比
            #    量出来的，套到新图上就是把图拉成错的宽高（见 :func:`rect_fits_image`）。
            rect = p.get("rect")
            if rect is not None and str(file_text) not in stale:
                entry["rect"] = list(rect)
                if p.get("rect_size") is not None:
                    entry["rect_size"] = list(p["rect_size"])
            out.append(entry)
            seen.add(file_text)
        return out

    if doc and snapshot == current_set and current_set:
        # rembg 产物未变化：沿用用户保存的顺序（拖动/删除/插入结果）
        entries = _existing(doc.get("pages"))
    else:
        # 首次进入，或重新提交后 rembg 产物集合变化：
        # rembg 最终图按阅读顺序排列；旧列表中用户插入的外部图片
        # （不在 rembg 目录）按原顺序追加在末尾
        external = [
            e for e in _existing(doc.get("pages") if doc else None)
            if e["file"] not in current_set
        ]
        entries = [{"file": str(p), "label": p.stem} for p in rembg_files]
        entries.extend(external)
    new_doc = {"rembg_snapshot": rembg_names, "pages": entries}
    return list(entries), new_doc
