"""
File: utils/box_draw.py
在图片上绘制检测框标注（供 CLI `detect --save` 与 GUI 预览共用）。

**为什么放在 utils**：CLI 的 `guji detect --save` 要把左右框画到图片上落地，
GUI 的预览控件也要画同样的框。配色与命名必须一致，否则「命令行看到的」
和「界面看到的」是两套东西。因此视觉约定集中在这里：

- 左框 `#21c178`（绿）、右框 `#3b82f6`（蓝）、合并框 `#f59e0b`（橙）；
- 标注文字为「左框 (x1,y1,x2,y2)」。

**中文字体**：OpenCV 的 `putText` 不支持中文（会画成 `????`），因此文字用
PIL 绘制。字体按 `utils.pdf_utils.register_fonts` 相同的候选顺序探测
Windows 系统中文字体；全部缺失时退化为 ASCII 标签（`L` / `R` / `U`），
保证任何环境下都不会崩。
"""

from pathlib import Path
from typing import Optional, Sequence, Tuple

# 与 desktop/components/viewers/image_view.py 的 BOX_COLORS / BOX_NAMES 对齐。
# 值为 BGR（OpenCV/PIL 转换用），注释里是 GUI 侧的十六进制 RGB。
BOX_COLORS_BGR: Tuple[Tuple[int, int, int], ...] = (
    (0x78, 0xC1, 0x21),  # 左框 #21c178
    (0xF6, 0x82, 0x3B),  # 右框 #3b82f6
    (0x0B, 0x9E, 0xF5),  # 合并框 #f59e0b
)
BOX_NAMES: Tuple[str, ...] = ("左框", "右框", "合并框")
# 无中文字体时的 ASCII 兜底标签
BOX_NAMES_ASCII: Tuple[str, ...] = ("L", "R", "U")

# 中文字体候选路径，与 utils/pdf_utils.register_fonts 保持一致
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\fsgb2312.ttf",
    r"C:\Windows\Fonts\simfang.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
)

_font_cache: dict = {}


def find_cjk_font() -> Optional[str]:
    """返回可用的中文字体路径；都没有则返回 None。结果会缓存。"""
    if "path" not in _font_cache:
        found = next(
            (p for p in _FONT_CANDIDATES if Path(p).exists()), None
        )
        _font_cache["path"] = found
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
        bgr = color if color is not None else box_color(index)
        cv2.rectangle(out, (x1, y1), (x2, y2), tuple(int(c) for c in bgr), line_w)
        if not show_label:
            continue
        label = f"{box_name(index)} ({x1},{y1},{x2},{y2})"
        out = _draw_label(out, label, x1, y1, bgr, font_scale)
    return out


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
