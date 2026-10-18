# -*- coding: utf-8 -*-
"""打印/提取条目的派生规则（纯函数，无 Qt 依赖，便于独立测试）。

这里的规则是 GUI 各阶段共享的「单一事实来源」：
- 提取缺页     → 续跑 extract 时的 pages 参数；
- 提交条目     → rembg「提交本次任务」的最终图片派生；
- 待打印列表   → 第四步左侧列表的默认排序与持久化合并。

⚠️ 第四步**没有**「按当前参数临时合成」的规则（2026-10-01 用户口径：
去底色那一步必须提交才能传给下一步）：print 只排版「提交本次任务」落盘的
成品图，见 ``taskdetail.submit.SubmitMixin._build_print_effects``。
"""

from __future__ import annotations

from pathlib import Path

from core.command_spec import WHOLE_PAGE_AREA
from utils.book_layout import single_column_slots
from utils.box_geometry import is_full_content


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
def plan_rembg_submit_entries(
    manifest_paths: list[Path],
    result_path_for,
    boxes_for,
    area: int,
    single_column_book: bool = False,
    page_width_for=None,
    side_for=None,
) -> list[dict]:
    """预览结果 + 检测框 + area/border → 最终图片条目。

    参数
    ----
    manifest_paths   : 页面清单路径（stages/extract 内的页图片）
    result_path_for  : (stem) -> Path|None，某页对应的「生成预览」去底结果
    boxes_for        : (path_str) -> list，某页的检测框 [左框, 右框]
    area             : 区域模式（1=左右分页，2/3=并集/对称画布）
    single_column_book: 整本书是否已判定为**单栏书**（``utils.book_layout``
        的全书统计结论，见 :func:`~utils.book_layout.profile_book`）。为真时
        「单个宽框」的半幅页按**整幅**处理。
    page_width_for   : (path_str) -> 页宽像素，用于算单宽框（``None``/0 时
        该页不会被判成单宽框）。只在 ``single_column_book`` 为真时才被调用。
    side_for         : (path_str) -> ``"left"``/``"right"``/None，用户在
        **半框页**上指定的左右。给了指定就**不做**单栏归一化——那是用户在说
        「这页其实是某一边」（用户 2026-10-17），命名/拼版都要按左/右走。

    派生规则与 rembg 预览条目、print 待打印列表完全一致：
    - **单栏书**（用户 2026-10-17）：整本书只有一栏，页里不会有左页+右页，
      于是「单个宽框（≥80% 页宽）的半幅页」被退化成**单槽**，直接继承整幅的
      全部下游语义——``label`` 就是页名（``7.png``，不拆 ``-l``/``-r``）、
      ``full=True`` 因而不做对称镜像、拼版也不会把它当左半幅去找右半幅配对。
      ⚠️ 这是**有证据的形态改写**（整本书 ≥90% 有框页都这样），与
      :func:`utils.book_layout.suspicious_summary` 报的「整幅书里冒出半幅」
      相反——那种只警告、不改。
    - area=1 双框：拆 <页>-r / <页>-l 两条（古籍阅读顺序 r 在前）；
    - area=1 半幅漏检一侧：单条也保留左右身份（<页>-l / <页>-r，按缺失侧
      所在槽位判定）——否则产物叫 <页>.png，第四步拼版按文件名后缀判
      左右半幅时会把这页误当整幅（用户 2026-10-01 报）；
    - area=2/3 双框：合成一条（不再分栏）；
    - 单框：area=2/3 走对称画布（整页形态，不带后缀），其余按普通框；
    - 无框：整页预览图透传。
    最终按 CLI natural sort 排序（同页 r 在 l 前）。

    ⚠️ ``parea`` 是**原始 area**（不是"降级"后的合成 area），``boxes`` 是
    **原始检测框**（不是并集后的单框）——两者必须原样交给
    ``compose_region_output``。原因见 ``entry_to_effect_spec``：并集框 +
    area=1 与「双框 + area=2/3」在 border 为空时**不等价**，曾导致第三步
    预览是整页、而提交产物与 PDF 被紧裁（用户报的「PDF 成了 area=1 效果」）。
    """
    from utils.sort_utils import natural_sort_key

    entries: list[dict] = []
    for path in manifest_paths:
        result = result_path_for(path.stem)
        if result is None:
            continue  # 该页尚未生成预览
        # ⚠️ 用**原始槽位**判断是否整幅内容：半幅固定 2 槽 [左,右]（可能含 null），
        #    整幅只占 1 槽。过滤 null 后两者都可能只剩 1 个框，届时无法区分——
        #    整幅页 area=1/2/3 统一按合并语义走单框布局（框原样下传），area=4
        #    才归一整页（见 entry_to_effect_spec 与 preview_worker 的 full 语义）。
        raw_boxes = list(boxes_for(str(path)) or [])
        # ⚠️ 单栏书：把「单个宽框」的半幅页**退化成单槽**（规则本体在
        #    ``utils.book_layout.single_column_slots``，第三步预览也调它），
        #    之后所有分支自动按整幅语义走——绝不能只在某个分支里改 label。
        # ⚠️ 但**用户指定过左右**的页不归一化：那是在说"这页其实是某一边"
        #    （半框的中心压在中线上，位置判定没意义，所以由用户声明）。
        if side_for is not None and side_for(str(path)):
            pass  # 保持 2 槽 → 走 area=1 的 -l/-r 分支，下游按左右处理
        else:
            raw_boxes = single_column_slots(
                raw_boxes, single_column_book,
                page_width_for(str(path)) if page_width_for is not None else None,
            )
        full = is_full_content(raw_boxes)
        boxes = [b for b in raw_boxes if b]
        stem = path.stem
        if area == 1 and len(boxes) == 2:
            entries.append(
                {"file": str(result), "label": f"{stem}-r",
                 "box": boxes[1], "boxes": [boxes[1]], "parea": 1, "full": False}
            )
            entries.append(
                {"file": str(result), "label": f"{stem}-l",
                 "box": boxes[0], "boxes": [boxes[0]], "parea": 1, "full": False}
            )
        elif area in (2, 3) and len(boxes) == 2:
            union = [
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            ]
            entries.append(
                {"file": str(result), "label": stem,
                 "box": union, "boxes": list(boxes), "parea": area, "full": False}
            )
        elif area == WHOLE_PAGE_AREA and len(boxes) >= 2:
            # 整页模式：整页（或用户手画的多个框）合成一个整体，不拆左右页
            union = [
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            ]
            entries.append(
                {"file": str(result), "label": stem, "box": union,
                 "boxes": list(boxes), "parea": area, "full": False}
            )
        elif len(boxes) == 1:
            label = stem
            if area == 1 and not full and len(raw_boxes) == 2:
                # 半幅(harfcontent)漏检一侧：单条也要保住 -l/-r 身份。
                # ⚠️ 判左右只能看**槽位**（半幅恒 2 槽 [左, 右]，见 half_slots），
                # 不能看框的中心——这里拿到的就是原始槽位。area=2/3 的单框是
                # 对称整页输出（与 CLI 一致），不带后缀。
                label = f"{stem}-l" if raw_boxes[0] else f"{stem}-r"
            entries.append(
                {"file": str(result), "label": label, "box": boxes[0],
                 "boxes": [boxes[0]], "parea": area, "full": full}
            )
        else:
            entries.append(
                {"file": str(result), "label": stem,
                 "box": None, "boxes": [], "parea": area, "full": False}
            )
    entries.sort(key=lambda e: natural_sort_key(e["label"]))
    return entries


def entry_to_effect_spec(entry: dict, border) -> dict:
    """提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。

    ⚠️ 必须把**原始检测框 + 原始 area** 交给 ``compose_region_output``，
    不能擅自"化简"成并集框 + area=1。``utils.box_geometry.build_output_layout``
    在 border 为空（padding=None）时两条分支并不等价：

    - area=2/3（含多框）→ ``full_page=True``：整页画布，各框**写回原位置**；
    - area=1            → 紧裁成「框 + border」的小画布。

    此前双框 area=2/3 被记成"并集框 + parea=1"，于是第三步预览（用原始框
    + 原始 area）显示整页、提交产物与 PDF 却是紧裁——用户报的「第三步 area=2、
    预览也是 area=2，生成的 PDF 却是 area=1 的效果」就是这么来的（紧裁观感
    与 area=1 的半页裁剪一致）。

    ``full`` 原样透传给合成层：整幅(fullcontent)页的框**原样下传**——
    area=4 保留整页内容、area 1/2/3 统一按合并语义走单框布局（不拆
    ``-l``/``-r``、不镜像）——见 ``desktop.workers.preview_worker.region_canvas_specs``。
    """
    raw = [b for b in (entry.get("boxes") or []) if b]
    if not raw and entry.get("box"):
        raw = [entry["box"]]  # 兼容只带 box 的旧条目/手写条目
    return {
        "file": entry["file"],
        "label": entry.get("label"),
        "effect": (
            {
                "boxes": raw,
                "area": int(entry.get("parea", 1) or 1),
                "border": border,
                "full": bool(entry.get("full")),
            }
            if raw
            else None
        ),
    }


def plan_submit_job(spec: dict, size: tuple[int, int] | None) -> dict:
    """一条效果规格 → 单条合成作业（输出文件名 + 合成参数）。

    ``size`` 是该条目图片的像素尺寸；``None`` 表示读不到文件头（坏图/被占用），
    该作业记 ``names=[]``——执行端据此报「无法读取图片」，不静默丢页。

    ⚠️ 输出文件名规则（``{label}.png``；多画布 ``{label}-N.png``）**只在这里
    一份**：执行端（``desktop.stages.rembg_stage``）与第三步「实时预览增量落盘」
    （``desktop.services.rembg_live``）共用它，命名不会两处各写一套而漂移。

    ⚠️ ``region_canvas_specs`` 走**函数内延迟导入**：本模块整体是不依赖 Qt 的
    纯逻辑（见模块 docstring），只有真要算输出张数时才拉进那份 Qt 几何实现。
    """
    from desktop.workers.preview_worker import region_canvas_specs

    label = str(spec.get("label") or Path(spec["file"]).stem)
    if size is None:
        return {
            "file": str(spec["file"]), "compose": False, "boxes": [],
            "area": 1, "border": None, "full": False, "names": [], "label": label,
        }
    effect = spec.get("effect")
    if effect and any(effect.get("boxes") or []):
        boxes = list(effect.get("boxes") or [])
        area = int(effect.get("area", 1))
        border = effect.get("border")
        full = bool(effect.get("full"))
        canvases = len(region_canvas_specs(size, boxes, area, border, full=full))
        has_boxes = True
    else:
        # 无检测框/无区域参数：整页预览图原样交付
        boxes, area, border, full = [], 1, None, False
        canvases = 1
        has_boxes = False
    names = (
        [f"{label}.png"] if canvases == 1
        else [f"{label}-{i + 1}.png" for i in range(canvases)]
    )
    return {
        "file": str(spec["file"]), "compose": has_boxes,
        "boxes": boxes, "area": area, "border": border, "full": full,
        "names": names, "label": label,
    }


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
