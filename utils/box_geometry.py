# -*- coding: utf-8 -*-
"""文本框几何规则：border 解析、最终裁剪框计算与输出画布布局。

本模块无重依赖（不导入 cv2/numpy/Qt），供 CLI functions、desktop worker 与
GUI 主进程共用，保证 detect 预览画出的"最终大框"与 crop 实际切割区域
完全一致。

坐标系均为原始图片像素坐标 [x1, y1, x2, y2]。

**布局层（build_output_layout）** 是 border 规则的唯一实现：**每个检测框各自
独立裁剪成一张输出图**（框 + border），后缀由侧别（``-l``/``-r``）决定。
2026-10-22 起 area 概念彻底移除——不再有「整页 / 并集 / 对称画布」那些模式，
检测出几个框就裁几张图。渲染后端由调用方决定——CLI 侧用 numpy 画，GUI 侧用
QImage 画。这样同一套规则不会因数像素后端不同而被复制成两份。
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from utils.units import MM_PER_INCH, mm_to_px


def is_full_content(boxes) -> bool:
    """``boxes`` 是否为「整幅内容」(fullcontent) 的**槽位表示**。

    槽位约定见 `functions/detect.PageBoxes`：
    - 半幅（harfcontent）固定 2 槽 ``[左, 右]``，缺失一侧为 None；
    - 整幅（fullcontent）只占 **1 槽** ``[整幅]``。

    据此判断单槽页是「整幅内容」（不带 ``-l``/``-r`` 后缀）还是
    「半幅漏检一侧」（仍按原始槽位带 ``-l``/``-r`` 后缀）——两者都只剩一个框，
    只能靠槽数区分。

    ⚠️ 槽数**不是**"有几个框"，而是**形态**：半幅恒 2 槽（`half_slots` 保证），
    整幅恒 1 槽。半幅删剩一侧后仍然写回 2 槽（另一侧 None），否则会被误判成整幅。
    """
    return len(list(boxes or [])) == 1


def page_box_slots(left, right, full) -> List[Optional[list]]:
    """三类框 → **槽位表示**（槽位约定的**唯一实现**）。

    半幅优先于整幅：只要有左或右就按半幅出 **2 槽** ``[左, 右]``（缺失侧
    ``None``）；否则整幅只占 **1 槽** ``[整幅]``；都没有则空表。

    半幅优先是既有明文规则（原 ``PageBoxes.slots``）：万一两类同时存在
    （互斥消解失灵 / 手工构造的防御场景），按半幅处理——保证 harfcontent 逻辑
    与原来完全一致，整幅不会把已检出的半幅挤掉。正常数据下两者不可兼得
    （见 ``functions.detect.PageBoxes.conflict``）。

    调用方两处，共用本函数以免"同一件事两处定义"而漂移：
    ``functions.detect.PageBoxes.slots``（对象侧）与
    :func:`page_box_slots_from_event`（事件侧）。
    """
    if left is not None or right is not None:
        return [left, right]
    if full is not None:
        return [full]
    return []


def page_box_slots_from_event(payload) -> List[Optional[list]]:
    """``page_boxes`` 事件负载 → **槽位表示**（坐标一律转 int）。

    ``page_boxes`` 是检测结果跨进程 / 跨线程回传的**唯一通道**，负载形如::

        {"image": stem, "left": [...] | None,
         "right": [...] | None, "full": [...] | None}

    （见 ``functions.detect.DetectFunction._report_boxes``）。任务流程第二步与
    独立「检测文本框」模块页都从这里还原形态，不再各写一遍槽位拼装。

    ⚠️ 本模块（utils）**不 import functions**——分层是单向的
    ``utils ← core ← {cli, functions, desktop}``，反过来引用会被
    ``tests/selftests/layering.py`` 判违规。所以这里只按负载里的三个键出槽位，
    不去构造 ``functions.detect.PageBoxes``：两侧共用的是**规则**
    （:func:`page_box_slots`），不是类型。
    """
    def _box(value):
        """一槽坐标：空 / ``None`` 归 ``None``，否则逐值转 int（长度原样保留）。"""
        if not value:
            return None
        return [int(v) for v in value]

    return page_box_slots(
        _box(payload.get("left")),
        _box(payload.get("right")),
        _box(payload.get("full")),
    )


#: 页形态分类键（`classify_page_slots` 的返回值）：与检测模型的两类内容
#: （fullcontent / harfcontent）同名的两个键是跨层文案，GUI 统计直接展示。
PAGE_CLASS_FULLCONTENT = "fullcontent"   # 整幅：单槽（整页唯一内容区）
PAGE_CLASS_HARFCONTENT = "harfcontent"   # 半幅：左右两栏齐全
PAGE_CLASS_SINGLE = "single"             # 单独页：半幅只检出一栏（左或右）
PAGE_CLASS_EMPTY = "empty"               # 无文本框

#: **YOLO 训练数据集**的类别顺序（用户 2026-10-16 给定，与训练侧
#: ``data.yaml`` 的 ``names: ["harfcontent", "fullcontent"]`` 一字不差）。
#:
#: ⚠️ **类别编号 = 列表下标，顺序不可调整**——0 号已经训练过（现有权重按
#: 「0 = 半幅」产出），改动顺序等于让已有权重与标注整体错位。
#:
#: 映射规则（导出 YOLO 标签时用）：
#:
#: - **左框、右框都归 0 号 ``harfcontent``**——它是"一栏"这个语义，
#:   数据集里不分左右（左右是下游 crop 的事，与训练无关）；
#: - 整幅框归 1 号 ``fullcontent``。
YOLO_CLASS_NAMES: Tuple[str, str] = (PAGE_CLASS_HARFCONTENT, PAGE_CLASS_FULLCONTENT)

#: 半幅 / 整幅的类别编号——从 :data:`YOLO_CLASS_NAMES` **派生**，不另写数字。
YOLO_CLASS_ID_HARF: int = YOLO_CLASS_NAMES.index(PAGE_CLASS_HARFCONTENT)
YOLO_CLASS_ID_FULL: int = YOLO_CLASS_NAMES.index(PAGE_CLASS_FULLCONTENT)


def classify_page_slots(slots) -> str:
    """页的**槽位**表示 → 页形态分类键（四类见 `PAGE_CLASS_*` 常量）。

    分类依据是槽位形态（与 `is_full_content` 同一条约定）：
    - 无任何框 → 无文本框；
    - 单槽且非空 → 整幅(fullcontent)；
    - 双槽全有 → 半幅(harfcontent)；双槽缺一侧 → 单独页（半幅单栏）。

    ⚠️ 参数必须是**槽位**表示（半幅恒 2 槽、整幅 1 槽，见 `half_slots`），
    不是"过滤掉 None 后还剩几个框"——过滤后单独页会误判成整幅。
    """
    raw = list(slots or [])
    present = [b for b in raw if b]
    if not present:
        return PAGE_CLASS_EMPTY
    if len(raw) == 1:
        return PAGE_CLASS_FULLCONTENT
    if len(raw) == 2:
        return PAGE_CLASS_HARFCONTENT if len(present) == 2 else PAGE_CLASS_SINGLE
    # 防御畸形存档（>2 槽）：只要有框就按半幅计，不丢页
    return PAGE_CLASS_HARFCONTENT


def half_sides(boxes, image_size) -> List[str]:
    """半幅(harfcontent)页的框 → 每个框的侧别 ``"left"`` / ``"right"``。

    规则（用户 2026-09-29 定）**只在本函数实现一处**，GUI 预览的命名/配色与
    入库的槽位组装都调它：

    - 只有 1 个框：中心 ``cx < 图宽/2`` → 左，否则 → 右（按**位置**判，不看大小）；
    - 多个框：按中心 ``cx`` 升序，**最靠左的那个归左**，其余归右——这样把框
      拖过中线时两侧身份自然互换，也不会出现"两个框都想要左槽"。

    ⚠️ **半幅的左右是位置决定的**（移动/缩放后会重新判定）；与位置无关的显式
    类型只有整幅(fullcontent)，由用户在第二步「选中框类型」里选择——那条路
    **不经过本函数**（见 :func:`is_full_content`）。

    参数:
        boxes: 框列表（原始图片坐标）；空项自动跳过。
        image_size: 原图 (宽, 高)，用于取中线。

    返回:
        与 ``boxes``（去掉空项后）等长的侧别字符串列表。
    """
    present = [tuple(b) for b in (boxes or []) if b]
    if not present:
        return []
    mid_x = (int(image_size[0]) if image_size else 0) / 2.0
    if len(present) == 1:
        cx = (present[0][0] + present[0][2]) / 2.0
        return ["left" if cx < mid_x else "right"]
    order = sorted(range(len(present)), key=lambda i: present[i][0] + present[i][2])
    sides = ["right"] * len(present)
    sides[order[0]] = "left"
    return sides


def half_slots(boxes, image_size) -> List[Optional[list]]:
    """半幅页的框 → **2 槽** ``[左, 右]``（缺失侧 ``None``）。

    ⚠️ 恒为 2 槽是**关键**：``is_full_content`` 靠槽数区分两种形态（整幅 = 1 槽）。
    半幅只要漏检/删剩一侧就退化成 1 槽，那个框就会被当成「整幅」——这正是
    "删掉整幅框后，右边的框自动变成了整幅" 的根因（用户 2026-09-29 报）。
    """
    present = [list(b) for b in (boxes or []) if b]
    left = right = None
    for box, side in zip(present, half_sides(present, image_size)):
        if side == "left":
            if left is None:
                left = box
        elif right is None:
            right = box
    return [left, right]


def parse_border_mm(border_value, dpi: int = 300) -> Optional[List[int]]:
    """解析 border 参数（毫米单位），按 DPI 转换为像素。

    与 `parse_border` 的写法规则相同，但最终值经过 mm→px 换算。
    换算公式: px = mm × dpi / 25.4（25.4mm = 1inch）。

    返回 [top, right, bottom, left] 像素列表，或 None。
    """
    if border_value is None:
        return None
    if isinstance(border_value, int):
        values = [border_value] * 4
    elif isinstance(border_value, str):
        parts = [p.strip() for p in border_value.split(",") if p.strip()]
        if not parts:
            return None
        values = [int(p) for p in parts]
        if len(values) == 1:
            values = [values[0]] * 4
        elif len(values) == 2:
            values = [values[0], values[1], values[0], values[1]]
        elif len(values) == 3:
            values = [values[0], values[1], values[2], values[1]]
        elif len(values) == 4:
            pass
        else:
            raise ValueError("border 格式错误，支持1~4个逗号分隔整数")
    else:
        raise ValueError("border 必须为整数或字符串")
    mm_to_px = dpi / MM_PER_INCH
    return [int(round(v * mm_to_px)) for v in values]


def _expand(box, padding) -> List[int]:
    """框按 [top, right, bottom, left] 像素外扩（可越出图片边界）。"""
    x1, y1, x2, y2 = box
    top, right, bottom, left = padding
    return [x1 - left, y1 - top, x2 + right, y2 + bottom]


def compute_final_boxes(
    boxes, border_mm, dpi: int = 300
) -> List[List[int]]:
    """按 border 规则计算最终切割框（原始图片坐标）。

    **每个检测框各自外扩 border → 各自输出一张图**。2026-10-22 起不再有
    area 参数：检测出几个文本框就裁几张图（无框时不裁剪，由调用方透传原图）。

    参数 boxes 为检测框列表（[左框, 右框]，缺失的已剔除）。
    """
    present = [b for b in boxes if b]
    padding = parse_border_mm(border_mm, dpi) or [0, 0, 0, 0]
    return [_expand(b, padding) for b in present]


# ==================================================================== 布局层
#
# 以下为输出布局的唯一实现：**每个检测框 = 一张独立输出画布**（框 + border）。
# 剥离了全部图像操作，只输出「画布尺寸 + 每块内容贴在哪」，CLI 与 GUI 共用。


@dataclass(frozen=True)
class Canvas:
    """一张输出画布及其内容落点。

    属性:
        size: (宽, 高)，画布像素尺寸。
        sources: [(源框, 目标x, 目标y), …]。源框用原始图片坐标
            (x1, y1, x2, y2)；目标坐标是它在画布中的左上角落点。
            源框与目标框尺寸相同（1:1 粘贴，不缩放）。
        suffix: 文件名后缀（半幅页的框为 "-l"/"-r"，整幅/无侧别为空串）。
    """

    size: Tuple[int, int]
    sources: Tuple[Tuple[Tuple[int, int, int, int], int, int], ...] = ()
    suffix: str = ""


@dataclass(frozen=True)
class OutputLayout:
    """一次处理的完整输出布局。

    属性:
        canvases: 按输出顺序排列的画布列表。
        full_page: 是否使用整页尺寸画布（无检测框、原图透传时）。
    """

    canvases: Tuple[Canvas, ...]
    full_page: bool = False


def _normalize_padding(border_padding) -> Optional[List[int]]:
    """统一 padding 表示：None 保持 None，否则转为 [t, r, b, l] 整数列表。"""
    if border_padding is None:
        return None
    return [int(v) for v in border_padding]


def build_output_layout(
    boxes: Sequence[Sequence[int]],
    border_padding,
    image_size: Tuple[int, int],
    sides: Optional[Sequence[Optional[str]]] = None,
) -> OutputLayout:
    """按 border 规则计算输出画布布局：**每个检测框各自一张图**。

    与 functions/text_region.py 的 `_build_output` 及
    desktop/workers/preview_worker.compose_region_output 的几何完全等价。

    参数:
        boxes: 检测框列表（原始图片坐标）。空框自动跳过。
        border_padding: [top, right, bottom, left] 像素，或 None（按无处不在处理）。
        image_size: 原图 (宽, 高)，**仅在没有任何框时**作为整页透传画布。
        sides: 与 boxes 对齐的来源侧（"left"/"right"/None），用于生成
            "-l"/"-r" 后缀与保持输出顺序。

    返回:
        OutputLayout。调用方按 canvases 顺序渲染并保存。
    """
    # ⚠️ 逐个解包成 4 元组：`tuple(int(v) for v in b)` 推出来是长度不定的
    # ``tuple[int, ...]``，与 Canvas.sources 声明的 ``(x1,y1,x2,y2)`` 不匹配。
    # 解包同时起到「必须正好 4 个数」的校验作用（畸形存档会当场炸，而不是
    # 悄悄把长度不对的框贴出去）。
    present: List[Tuple[int, int, int, int]] = []
    for b in boxes:
        if not b:
            continue
        x1, y1, x2, y2 = (int(v) for v in b)
        present.append((x1, y1, x2, y2))
    if not present:
        return OutputLayout(canvases=(Canvas(size=image_size),), full_page=True)

    t, r, b, l = _normalize_padding(border_padding) or (0, 0, 0, 0)
    canvases = []
    for index, box in enumerate(present):
        x1, y1, x2, y2 = box
        suffix = ""
        if sides is not None and index < len(sides) and sides[index]:
            suffix = "-l" if sides[index] == "left" else "-r"
        canvases.append(
            Canvas(
                size=((x2 - x1) + l + r, (y2 - y1) + t + b),
                sources=((box, l, t),),
                suffix=suffix,
            )
        )
    return OutputLayout(canvases=tuple(canvases))


# ================================================================== 人工干预
#
# 「把某个框改成左框/右框/整幅」「删掉某个框」的结果计算。**纯函数**（不碰
# Qt、不碰存储），所以任务流程第二步（`desktop/pages/taskdetail/detect.py`）
# 与独立「检测文本框」模块页（`desktop/modules/detect/page.py`）走**同一条**
# 规则，不会各写一遍慢慢漂移。
#
# ⚠️ 三条不变式（用户 2026-09-29 定的 6 条规则里最要紧的三条）：
#   1. 类型存在**槽位**里（半幅 2 槽 / 整幅 1 槽），不按"还剩几个框"推；
#   2. 半幅的左右由**中心位置**决定（`half_sides`），所以左/右之间切不动；
#   3. 整幅与半幅**互斥**、整幅一页只能一个框 —— 转换时别的框要么被保留
#      （整幅→半幅）、要么被删（半幅→整幅，调用方须先与用户确认）。

def present_boxes(slots) -> List[list]:
    """槽位 → **非空**框列表（保留顺序）。

    下游所有"第 index 个框"都按这个列表的下标算：界面上的框列表、命中检测、
    选中下标全都是过滤后的口径，混用槽位下标会选错框（半幅缺左侧时，
    槽位 0 是 ``None``、槽位 1 才是右框）。
    """
    return [list(b) for b in (slots or []) if b]


def set_box_full(slots, index: int) -> List[Optional[list]]:
    """把第 ``index`` 个框设为「整幅」→ **单槽** ``[整幅]``，其余框丢弃。

    ⚠️ 整幅与半幅互斥、一页只能一个框，所以这个转换**必然丢掉其它框**。
    调用方**必须先与用户确认**（任务流程第二步弹 Dialog，模块页弹确认框），
    不要静默调用。

    ``index`` 越界时原样返回（空表则返回空表）——非法输入不该让界面崩。
    """
    boxes = present_boxes(slots)
    if not 0 <= index < len(boxes):
        return list(slots or [])
    return [boxes[index]]


def set_box_half(slots, index: int, image_size) -> List[Optional[list]]:
    """把第 ``index`` 个框设为「半幅」→ **2 槽** ``[左, 右]``（按中心定左右）。

    整幅页的框也能是半幅（漏检一侧的情形），所以这个方向**无损**：一个框
    照样按它自己的中心位置落进左槽或右槽，另一侧留 ``None``。
    """
    boxes = present_boxes(slots)
    if not 0 <= index < len(boxes):
        return list(slots or [])
    return half_slots([boxes[index]], image_size)


def set_box_side(slots, index: int, side: str) -> List[Optional[list]]:
    """把第 ``index`` 个框**强制**放到指定侧 → 2 槽 ``[左, 右]``。

    与 :func:`set_box_half` 的唯一区别：**不按中心位置判**，直接听调用方的。
    用于「半幅」页——那种框横跨整页，中心几乎总在中线上，按位置判出来的
    左右是**没有意义的**（用户 2026-10-17：「半幅的情况，用户可以指定是左框
    还是右框」）。

    ``side`` 只认 ``"left"`` / ``"right"``；其它值原样返回（不猜）。
    """
    if side not in ("left", "right"):
        return list(slots or [])
    boxes = present_boxes(slots)
    if not 0 <= index < len(boxes):
        return list(slots or [])
    box = boxes[index]
    return [box, None] if side == "left" else [None, box]


def drop_box(slots, index: int, image_size) -> List[Optional[list]]:
    """删掉第 ``index`` 个框后的**新槽位**。

    - 半幅页：仍写回 **2 槽**（缺失侧 ``None``）——删到只剩一个框时形态不会
      从半幅变成整幅，这正是用户报过的"删掉整幅框后右边的框自动变成整幅"；
    - 整幅页 / 删光了：空表（整幅只有 1 槽，删掉没有"别的框"可剩）。
    """
    boxes = present_boxes(slots)
    if not 0 <= index < len(boxes):
        return list(slots or [])
    del boxes[index]
    if not boxes:
        return []
    return half_slots(boxes, image_size)
