"""
File: utils/box_draw.py
在图片上绘制检测框标注（供 CLI `detect --save` 与 GUI 预览共用）。

**为什么放在 utils**：CLI 的 `guji detect --save` 要把内容框画到图片上落地，
GUI 的预览控件也要画同样的框。配色与命名必须一致，否则「命令行看到的」
和「界面看到的」是两套东西。因此视觉约定集中在这里：

- 左框 `#21c178`（绿）、右框 `#3b82f6`（蓝）、合并框 `#f59e0b`（琥珀）；
- 整幅内容框（fullcontent，单框整页）`#4F46E5`（靛蓝）——深蓝紫，压在米黄
  纸页上醒目；与前三色区分干净（2026-09-29 用户选定，此前朱砂红被否）。
- 标注文字为「左框 (x1,y1,x2,y2)」。

**中文字体**：OpenCV 的 `putText` 不支持中文（会画成 `????`），因此文字用
PIL 绘制。字体候选路径来自 `utils.fonts`（Windows/Linux/macOS 三份候选 +
`GUJI_CJK_FONT` 逃生口，见那里的说明——**别在本文件再写一遍**）；全部缺失
时退化为 ASCII 标签（`L` / `R` / `U`），保证任何环境下都不会崩。
"""

from pathlib import Path
from typing import Optional, Sequence, Tuple

# ⚠️ 配色/命名的**唯一事实来源就是本文件**：CLI 的 `detect --save` 标注图与
# GUI 预览必须是同一套视觉，否则「命令行看到的」和「界面看到的」是两个东西。
# `desktop/components/viewers/image_view.py` 直接 import 下面的常量，**不再抄
# 一份**（只靠注释对齐的重复定义迟早漂移）。
#
# 以 **RGB** 为准（GUI 的 `QColor` 要它），**BGR 由 RGB 推导**（OpenCV 要它）——
# 手写两份、靠人眼保证「B=蓝、R=红」对齐是不必要的风险。
BOX_COLORS_RGB: Tuple[Tuple[int, int, int], ...] = (
    (0x21, 0xC1, 0x78),  # 左框（绿）
    (0x3B, 0x82, 0xF6),  # 右框（蓝）
    (0xF5, 0x9E, 0x0B),  # 合并框（琥珀）
    (0x4F, 0x46, 0xE5),  # 整幅（靛蓝；fullcontent 单框整页）
)
BOX_COLORS_BGR: Tuple[Tuple[int, int, int], ...] = tuple(
    (b, g, r) for r, g, b in BOX_COLORS_RGB
)
BOX_NAMES: Tuple[str, ...] = ("左框", "右框", "合并框", "整幅")
# 无中文字体时的 ASCII 兜底标签（与 BOX_NAMES 一一对应，长度必须一致）
BOX_NAMES_ASCII: Tuple[str, ...] = ("L", "R", "U", "F")

#: **框类型键 → 在 BOX_NAMES / BOX_COLORS 里的下标**。
#:
#: 类型键（``"left"`` / ``"right"`` / ``"full"``）是**跨层协议**：第二步面板的
#: 类型按钮、宿主的人工干预逻辑、GUI 预览的标签/配色都按它取值——各层各自
#: 记下标迟早会错位，所以映射只在这里写一份。
BOX_KIND_INDEX = {
    "left": BOX_NAMES.index("左框"),
    "right": BOX_NAMES.index("右框"),
    "full": BOX_NAMES.index("整幅"),
}


def box_kind_name(kind: str) -> str:
    """类型键 → 中文名称（``"left"`` → 「左框」）；未知键原样返回。"""
    index = BOX_KIND_INDEX.get(kind)
    return BOX_NAMES[index] if index is not None else str(kind)


#: 整幅内容框（fullcontent）的专用色/名：它**不是**左框也不是合并框，
#: 单独一个颜色，免得标注图上把整页内容误读成某一栏。
BOX_COLOR_FULL_BGR: Tuple[int, int, int] = BOX_COLORS_BGR[3]  # 整幅（靛蓝 #4F46E5）
BOX_NAME_FULL = "整幅"

#: 半幅两槽的固定名/色（``[左, 右]`` 槽位顺序，缺失侧为 ``None``）。
#:
#: ⚠️ 与 :func:`slot_names_colors` 配套：**按槽位**给标注，不是按"框的序号"。
#: 槽数就是形态（半幅 2 槽 / 整幅 1 槽，见 ``utils.box_geometry``），所以
#: "只检出一侧"时画出来的仍是左框而不是"第 1 号框"。
SLOT_NAMES_HALF: Tuple[str, str] = (BOX_NAMES[BOX_KIND_INDEX["left"]],
                                    BOX_NAMES[BOX_KIND_INDEX["right"]])
SLOT_COLORS_HALF: Tuple[Tuple[int, int, int], Tuple[int, int, int]] = (
    BOX_COLORS_BGR[BOX_KIND_INDEX["left"]],
    BOX_COLORS_BGR[BOX_KIND_INDEX["right"]],
)

_font_cache: dict = {}


def reset_font_cache() -> None:
    """清空字体探测缓存（`GUJI_CJK_FONT` 改指向后需要重探测）。"""
    _font_cache.clear()


def find_cjk_font() -> Optional[str]:
    """返回可用的中文字体路径；都没有则返回 None。结果会缓存。"""
    if "path" not in _font_cache:
        from utils.fonts import first_existing_cjk_font

        _font_cache["path"] = first_existing_cjk_font()
    return _font_cache["path"]


def _load_font(size: int):
    """按字号取 PIL 字体对象；无中文字体时返回 None。"""
    path = find_cjk_font()
    if path is None:
        return None
    key = (path, size)
    if key not in _font_cache:
        from PIL import ImageFont

        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except Exception:
            _font_cache[key] = None
    return _font_cache[key]


def box_color(index: int) -> Tuple[int, int, int]:
    """按框序号取 BGR 颜色。"""
    return BOX_COLORS_BGR[index % len(BOX_COLORS_BGR)]


def box_name(index: int) -> str:
    """按框序号取中文名（左框/右框/合并框）。"""
    return BOX_NAMES[min(index, len(BOX_NAMES) - 1)]


def draw_boxes(
    img_bgr,
    boxes: Sequence[Optional[Sequence[int]]],
    thickness: int = 4,
    show_label: bool = True,
    color=None,
    names: Optional[Sequence[str]] = None,
    colors: Optional[Sequence[Tuple[int, int, int]]] = None,
):
    """在图像上绘制一组框（原地绘制并返回新图，不修改入参）。

    参数:
        img_bgr: BGR 图像数组。
        boxes: 框列表，每项为 ``(x1, y1, x2, y2)``；``None`` 项被跳过
            （用于「只检出一侧」的常见情形，保持左右序号不串位）。
        thickness: 线宽（像素）。会随图像尺寸自适应放大，避免大扫描图上
            细线看不清。
        show_label: 是否绘制「左框 (x1,y1,x2,y2)」这类标注。
        color: 指定线条颜色 (B,G,R)；None 时按框序号取默认色。
        names: 与 boxes 按序号对齐的名称覆盖；``None`` 项回退到默认名。
            用于把整幅内容框标成「整幅」而不是「左框」。
        colors: 与 boxes 按序号对齐的颜色覆盖；``None`` 项回退到默认色。
            优先于 ``color``（`color` 是"全部同色"的简写）。

    返回:
        绘制后的 BGR 图像（新数组）。
    """
    import cv2
    import numpy as np

    out = np.ascontiguousarray(img_bgr.copy())
    h, w = out.shape[:2]
    # 线宽自适应：短边每 500px 约 1px，下限 2，上限 10
    base = int(round(min(h, w) / 500.0)) or 1
    line_w = max(2, min(10, thickness * base // 2 or thickness))
    font_scale = max(0.6, min(2.5, min(h, w) / 900.0))

    for index, box in enumerate(boxes):
        if box is None:
            continue
        x1, y1, x2, y2 = (int(v) for v in box[:4])
        bgr = _pick(colors, index) or (color if color is not None else box_color(index))
        cv2.rectangle(out, (x1, y1), (x2, y2), tuple(int(c) for c in bgr), line_w)
        if not show_label:
            continue
        name = _pick(names, index) or box_name(index)
        label = f"{name} ({x1},{y1},{x2},{y2})"
        out = _draw_label(out, label, x1, y1, bgr, font_scale)
    return out


def slot_names_colors(slots):
    """**槽位**表示 → 与 ``slots`` 等长的 ``(names, colors)``（BGR）。

    这是"槽位 → 标注外观"的**唯一实现**，两处调用方共用：

    - ``functions.detect`` 的 ``--save`` 标注图；
    - 独立「检测文本框」模块页的「导出标注图」。

    ⚠️ 规则按**槽位**给，不按"过滤掉空项后的第几个框"：槽数就是形态
    （半幅恒 2 槽 ``[左, 右]``、整幅 1 槽 ``[整幅]``，见
    :mod:`utils.box_geometry`）。按序号给会让"只检出一侧"的那一页把左框
    标成"第 1 号框"，也会把整幅标成左框。

    ``None`` 项原样占位（``draw_boxes`` 会跳过它，GUI 侧则按位置对齐），
    这样"哪一侧缺失"的信息不丢。
    """
    slots = list(slots or [])
    if len(slots) == 1:
        return [BOX_NAME_FULL] * len(slots), [BOX_COLOR_FULL_BGR] * len(slots)
    if len(slots) == 2:
        return list(SLOT_NAMES_HALF), list(SLOT_COLORS_HALF)
    # 防御畸形存档（>2 槽）：退回按序号给，别让调用方炸掉
    return [box_name(i) for i in range(len(slots))], [
        box_color(i) for i in range(len(slots))
    ]


def draw_slots(img_bgr, slots, thickness: int = 4, show_label: bool = True):
    """在图像上绘制**槽位**表示的框（标注外观由 :func:`slot_names_colors` 定）。

    与 :func:`draw_boxes` 的区别只有一处，但很关键：调用方手上是**槽位**
    （可能含 ``None``、长度 1 或 2，形态信息就在里面），不该自己拆成
    ``[left, right, full]`` 再逐个传名/配色——那份拆法在
    ``functions/detect`` 与 desktop 之间各写过一次，已经漂移过一次。

    返回绘制后的 BGR 图像（新数组，不修改入参）。
    """
    names, colors = slot_names_colors(slots)
    return draw_boxes(
        img_bgr,
        list(slots or []),
        thickness=thickness,
        show_label=show_label,
        names=names,
        colors=colors,
    )


def _pick(seq, index):
    """按序号取覆盖项；越界或该项为 None 时返回 None（表示用默认）。"""
    if not seq or index >= len(seq):
        return None
    return seq[index]


def _draw_label(img_bgr, text: str, x: int, y: int, bgr, font_scale: float):
    """在 (x, y) 上方绘制标注文字；中文走 PIL，无字体时退化为 ASCII。"""
    import cv2
    import numpy as np

    font = _load_font(max(14, int(20 * font_scale)))
    if font is None:
        # 无中文字体：用 ASCII 兜底（cv2.putText 不支持中文）
        ascii_text = _ascii_label(text)
        (tw, th), baseline = cv2.getTextSize(
            ascii_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2
        )
        ty = max(th + 4, y - 6)
        cv2.rectangle(
            img_bgr, (x, ty - th - 2), (x + tw + 6, ty + baseline), (255, 255, 255), -1
        )
        cv2.putText(
            img_bgr, ascii_text, (x + 3, ty),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, tuple(int(c) for c in bgr), 2,
            cv2.LINE_AA,
        )
        return img_bgr

    from PIL import Image, ImageDraw

    # BGR -> RGB 交给 PIL 画文字，再转回 BGR
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    ty = max(0, y - th - 10)
    # 白底衬底，保证任何底色上都可读
    draw.rectangle([x, ty, x + tw + 8, ty + th + 8], fill=(255, 255, 255))
    draw.text(
        (x + 4, ty + 4 - bbox[1]),
        text,
        font=font,
        fill=(int(bgr[2]), int(bgr[1]), int(bgr[0])),
    )
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def _ascii_label(text: str) -> str:
    """把「左框 (1,2,3,4)」转成 ASCII 标签「L (1,2,3,4)」。"""
    for idx, name in enumerate(BOX_NAMES):
        if text.startswith(name):
            return BOX_NAMES_ASCII[idx] + text[len(name):]
    return text
