"""
自然排序工具：支持封面/菜单优先与数字感知排序。

用于文件列表排序，使 "page2, page10" 按数值 2 < 10 排序而非字典序 "10" < "2"。
"""

import re
import os


def natural_sort_key(filename: str) -> tuple:
    """生成自然排序键，封面和菜单排在最前。

    排序规则:
    1. 优先级：cover*.png 和 menu.png 排在所有文件之前（priority=0）；
    2. 数字感知：将文件名拆分为 [文字, 数字, 文字, ...] 序列，
       数字部分按整数值比较而非字符串比较。

    参数:
        filename: 文件名（含扩展名）。

    返回:
        (priority, natural_key) 元组，可直接用于 sort/sorted 的 key 参数。

    示例:
        >>> files = sorted(["page10.png", "page2.png", "cover.png", "page3.png"],
        ...                key=natural_sort_key)
        >>> [f.name for f in files]
        ['cover.png', 'page2.png', 'page3.png', 'page10.png']
    """
    lower_name = filename.lower()
    # 封面和菜单文件优先级最高
    is_cover = lower_name.startswith("cover") and lower_name.endswith(".png")
    is_menu = lower_name == "menu.png"
    priority = 0 if (is_cover or is_menu) else 1

    # 将文件名按数字/非数字片段拆分，数字转为 int 用于数值比较
    # 例如 "page10.png" → ["page", 10, ".png"]
    natural_key = [
        int(part) if part.isdigit() else part for part in re.split(r"(\d+)", filename)
    ]
    # ⚠️ 末尾追加**原文件名**做兜底键（2026-09-26 审计）：`page1.png` 与
    #    `page01.png` 的自然键完全相同（都是 ('page', 1, '.png')），而输入来自
    #    顺序不确定的 `iterdir()` → 两次运行可能给出不同页序（破坏幂等）。
    #    加原名后排序是全序，结果稳定。
    return (priority, natural_key, filename)


def pdf_custom_sort_key(file_path: str) -> tuple:
    """生成 PDF 页面排序键（古籍双页扫描件的阅读顺序）。

    分级规则，逐级比较：

    1. ``cover*`` 优先，编号小的在前；
    2. ``menu`` 次之；
    3. 形如 ``<页号>`` / ``<页号>-l`` / ``<页号>-r``（``_`` 亦可）的图片：
       先按页号数值，再按侧边 ``r → l → 无后缀``——双页扫描件右侧页先读；
    4. 其余文件按文件名排在最后。

    参数:
        file_path: 文件路径或文件名，内部只取 basename。

    返回:
        ``(优先级, 页号, 侧边)`` 或 ``(999, 0, 文件名)`` 元组。
    """
    filename = os.path.basename(file_path)
    name = os.path.splitext(filename)[0]
    lower = name.lower()
    if lower.startswith("cover"):
        suffix = lower[5:]
        num = int(suffix) if suffix.isdigit() else 0
        return (0, num, 0)
    if lower == "menu":
        return (1, 0, 0)
    match = re.fullmatch(r"(\d+)(?:[_-](l|r))?", lower)
    if match:
        page = int(match.group(1))
        suffix = match.group(2)
        # 同一编号内按 r、l、无后缀排列，满足双页图片的阅读顺序。
        side = {"r": 0, "l": 1, None: 2}[suffix]
        return (2, page, side)
    return (999, 0, name)
