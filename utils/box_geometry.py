# -*- coding: utf-8 -*-
"""文本框几何规则：border 解析、最终裁剪框计算与输出画布布局。

本模块无重依赖（不导入 cv2/numpy/Qt），供 CLI functions、desktop worker 与
GUI 主进程共用，保证 detect 预览画出的"最终大框"与 crop 实际切割区域
完全一致。

坐标系均为原始图片像素坐标 [x1, y1, x2, y2]。

**布局层（build_output_layout / build_symmetric_layout）** 是 area/border
规则的唯一实现：它只做纯整数算术（画布多大、每块内容贴在哪），把结果表达为
`OutputLayout`。渲染后端由调用方决定——CLI 侧用 numpy 画，GUI 侧用 QImage 画。
这样同一套规则不会因数像素后端不同而被复制成两份。

⚠️ 曾有一处真实分歧：GUI 侧在 area=3 + 双框 + border=None 时把并集区域
搬到了画布左上角，而规格要求"ROI 写回原位置"（见
docs/functions/cropremove.md:57）。布局层统一后该分歧由本模块消除。
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from utils.units import MM_PER_INCH, mm_to_px

# 单框对称输出时，实际框与空白镜像之间的间隔（mm）
SYMMETRIC_GAP_MM = 10


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
    boxes, area: int, border_mm, dpi: int = 300
) -> List[List[int]]:
    """按 crop 命令的 area/border 规则计算最终切割框（原始图片坐标）。

    与 functions/text_region.py 的切割逻辑一致：
    - area=1：每个框各自外扩 border，输出多张图（-l/-r）；
    - area=2/3：两框取并集后外扩 border，输出一张大图；
      单框时为对称输出，实际内容区域即该框外扩 border。

    参数 boxes 为检测框列表（[左框, 右框]，缺失的已剔除）。
    """
    present = [b for b in boxes if b]
    if not present:
        return []
    padding = parse_border_mm(border_mm, dpi) or [0, 0, 0, 0]
    if area == 1:
        return [_expand(b, padding) for b in present]
    if len(present) == 2:
        union = [
            min(b[0] for b in present),
            min(b[1] for b in present),
            max(b[2] for b in present),
            max(b[3] for b in present),
        ]
        return [_expand(union, padding)]
    return [_expand(present[0], padding)]


# ==================================================================== 布局层
#
# 以下为 area/border 输出布局的唯一实现。算法与 functions/text_region.py
# 的 _process_single_image + _build_output/_build_symmetric_output 逐步等价，
# 但剥离了全部图像操作，只输出「画布尺寸 + 每块内容贴在哪」。


@dataclass(frozen=True)
class Canvas:
    """一张输出画布及其内容落点。

    属性:
        size: (宽, 高)，画布像素尺寸。
        sources: [(源框, 目标x, 目标y), …]。源框用原始图片坐标
            (x1, y1, x2, y2)；目标坐标是它在画布中的左上角落点。
            源框与目标框尺寸相同（1:1 粘贴，不缩放）。
        suffix: 文件名后缀（area=1 逐框输出时为 "-l"/"-r"，否则空串）。
    """

    size: Tuple[int, int]
    sources: Tuple[Tuple[Tuple[int, int, int, int], int, int], ...] = ()
    suffix: str = ""


@dataclass(frozen=True)
class OutputLayout:
    """一次处理的完整输出布局。

    属性:
        canvases: 按输出顺序排列的画布列表。
        full_page: 是否使用整页尺寸画布（无 border 时）。调用方据此决定
            画布底色以外的处理方式。
    """

    canvases: Tuple[Canvas, ...]
    full_page: bool = False


def _merge_union(boxes: Sequence[Sequence[int]]) -> Tuple[int, int, int, int]:
    """两框（或多框）的并集外边界。"""
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _normalize_padding(border_padding) -> Optional[List[int]]:
    """统一 padding 表示：None 保持 None，否则转为 [t, r, b, l] 整数列表。"""
    if border_padding is None:
        return None
    return [int(v) for v in border_padding]


def build_output_layout(
    boxes: Sequence[Sequence[int]],
    area: int,
    border_padding,
    image_size: Tuple[int, int],
    dpi: int = 300,
    sides: Optional[Sequence[Optional[str]]] = None,
    symmetric: bool = False,
) -> OutputLayout:
    """按 area/border 规则计算输出画布布局（area=1 / 2 / 3）。

    与 functions/text_region.py 的 `_build_output` 及
    desktop/workers/preview_worker.compose_region_output 的几何完全等价，
    差异已在本模块内统一（area=3 + border=None 一律"写回原位置"）。

    参数:
        boxes: 检测框列表（原始图片坐标）。area=3 且两框齐全时内部自动取并集。
        area: 区域模式 1/2/3。
        border_padding: [top, right, bottom, left] 像素，或 None。
        image_size: 原图 (宽, 高)，无 border 时画布取其尺寸。
        dpi: 边框换算 DPI（仅用于对称输出的 gap）。
        sides: area=1 时每个框的来源侧（"left"/"right"/None），用于生成
            "-l"/"-r" 后缀与保持输出顺序。
        symmetric: 单框 + border 时是否走**对称输出**（实际框 + 空白镜像）。
            True 对应 `_build_symmetric_output`（area=2/3 且检测到单框）；
            False 表示普通单框布局（含 area=3 合并后的单框）——此时画布
            就是「框 + border」，不做镜像。

    返回:
        OutputLayout。调用方按 canvases 顺序渲染并保存。
    """
    present = [tuple(int(v) for v in b) for b in boxes if b]
    if not present:
        return OutputLayout(canvases=(Canvas(size=image_size),), full_page=True)

    padding = _normalize_padding(border_padding)
    W, H = int(image_size[0]), int(image_size[1])

    # ---------------- area=1：逐框独立输出 ----------------
    if area == 1:
        t, r, b, l = padding if padding is not None else (0, 0, 0, 0)
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

    # ---------------- 单框 ----------------
    if len(present) == 1:
        single = present[0]
        x1, y1, x2, y2 = single
        if padding is None:
            # 整页画布，内容写回原位置
            return OutputLayout(
                canvases=(Canvas(size=(W, H), sources=((single, x1, y1),)),),
                full_page=True,
            )
        t, r, b, l = padding
        bw, bh = x2 - x1, y2 - y1
        if symmetric:
            # 对称输出：实际框 + 空白镜像 + 中间间隔
            gap_px = round(mm_to_px(SYMMETRIC_GAP_MM, dpi))
            size = (l + bw * 2 + gap_px + r, t + bh + b)
        else:
            # 普通单框：画布 = 框 + 四周 border
            size = (bw + l + r, bh + t + b)
        return OutputLayout(
            canvases=(Canvas(size=size, sources=((single, l, t),)),)
        )

    # ---------------- area=2/3 双框 ----------------
    union = _merge_union(present)
    ux1, uy1, ux2, uy2 = union

    if padding is None:
        # 整页画布；area=3 取并集整块写回原位置，area=2 各框分别写回原位置
        if area == 3:
            sources = ((union, ux1, uy1),)
        else:
            sources = tuple((b, b[0], b[1]) for b in present)
        return OutputLayout(
            canvases=(Canvas(size=(W, H), sources=sources),),
            full_page=True,
        )

    t, r, b, l = padding
    canvas_size = ((ux2 - ux1) + l + r, (uy2 - uy1) + t + b)
    if area == 3:
        sources = ((union, l, t),)
    else:
        sources = tuple((b, b[0] - ux1 + l, b[1] - uy1 + t) for b in present)
    return OutputLayout(canvases=(Canvas(size=canvas_size, sources=sources),))


def build_symmetric_layout(
    box: Sequence[int],
    border_padding,
    image_size: Tuple[int, int],
    is_left: bool = True,
    dpi: int = 300,
) -> OutputLayout:
    """单框对称输出布局：实际框 + 空白镜像 + 中间间隔。

    与 `build_output_layout` 的单框分支同规则，区别是显式给出实际框在左
    还是在右（`is_left=False` 时内容置于右半）。

    参数:
        box: 实际检测框（原始图片坐标）。
        border_padding: [top, right, bottom, left] 像素（不可为 None）。
        image_size: 原图 (宽, 高)，仅用于无 padding 时的兜底。
        is_left: 实际框位于左半（True）还是右半（False）。
        dpi: gap 换算 DPI。

    返回:
        OutputLayout（单一画布）。
    """
    x1, y1, x2, y2 = (int(v) for v in box)
    W, H = int(image_size[0]), int(image_size[1])

    if border_padding is None:
        return OutputLayout(
            canvases=(Canvas(size=(W, H), sources=((tuple(box), x1, y1),)),),
            full_page=True,
        )

    t, r, b, l = (int(v) for v in border_padding)
    gap_px = round(mm_to_px(SYMMETRIC_GAP_MM, dpi))
    bw, bh = x2 - x1, y2 - y1
    # 实际框在左 -> 落点 left；在右 -> 跳过镜像宽度与间隔
    ox = l if is_left else l + bw + gap_px
    return OutputLayout(
        canvases=(
            Canvas(
                size=(l + bw * 2 + gap_px + r, t + bh + b),
                sources=((tuple(box), ox, t),),
            ),
        )
    )
