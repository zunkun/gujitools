# -*- coding: utf-8 -*-
"""文本框几何规则：border 解析与最终裁剪框计算。

本模块无重依赖（不导入 cv2/numpy），供 CLI functions、desktop worker 与
GUI 主进程共用，保证 detect 预览画出的"最终大框"与 crop 实际切割区域
完全一致。

坐标系均为原始图片像素坐标 [x1, y1, x2, y2]。
"""

from typing import List, Optional


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
    mm_to_px = dpi / 25.4
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
