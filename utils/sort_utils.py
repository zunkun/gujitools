"""自然排序工具（唯一排序键）：cover/menu 优先 + 数字感知页序。

用于文件/条目列表排序：``page2, page10`` 按数值 2 < 10 而非字典序；
古籍双页扫描件的 ``N-l``/``N-r`` 按"右侧页先读"配对。

2026-10-11 合并：原来这里有 ``natural_sort_key``（通用数字感知）与
``pdf_custom_sort_key``（古籍页序约定）两个键，语义重叠、实现两份。
现只保留一个 ``natural_sort_key``＝后者的分级骨架 + 前者的数字感知兜底，
**垫底的非页号文件也按数字自然序**排（``page10`` 不再排到 ``page2`` 前）。
"""


import re
import os


def natural_sort_key(file_path: str) -> tuple:
    """生成自然排序键：cover/menu 优先，页号数值序，其余数字感知垫底。

    参数:
        file_path: 文件路径或文件名（含扩展名），内部只取 basename。

    返回:
        ``(优先级, ...)`` 元组，可直接用于 sort/sorted 的 key 参数：

        1. ``(0, 封面编号, 0, 文件名)`` —— ``cover*``（编号数字序，无编号=0）；
        2. ``(1, 0, 0, 文件名)`` —— ``menu``；
        3. ``(2, 页号, 侧边, 文件名)`` —— 形如 ``<页号>`` / ``<页号>-l`` /
           ``<页号>-r``（``_`` 亦可）：先按页号数值，再按侧边 ``r → l → 无后缀``
           （双页扫描件右侧页先读）；
        4. ``(999, 数字感知分段, 文件名)`` —— 其余文件：按文件名里的数字
           **数值**比较（``page2`` < ``page10``），垫在页号文件之后。

    兜底键：
        每级末尾都追加**原文件名**（2026-10-11，沿 2026-09-26 审计结论）：
        ``page1.png`` 与 ``page01.png``、``1.png`` 与 ``01.png`` 的主键完全
        相同，而输入常来自顺序不确定的 ``iterdir()`` → 不加原名则两次运行
        可能给出不同页序（破坏幂等）。加原名后排序是全序，结果稳定。

    示例:
        >>> files = sorted(["10.png", "2.png", "2-l.png", "2-r.png",
        ...                 "cover.png", "page10.png", "page2.png"],
        ...                key=natural_sort_key)
        >>> [f for f in files]
        ['cover.png', '2-r.png', '2-l.png', '2.png', '10.png',
         'page2.png', 'page10.png']
    """
    filename = os.path.basename(file_path)
    name = os.path.splitext(filename)[0]
    lower = name.lower()
    # 封面优先：cover*.png（编号按数值，无编号排最前）
    if lower.startswith("cover"):
        suffix = lower[5:]
        num = int(suffix) if suffix.isdigit() else 0
        return (0, num, 0, filename)
    if lower == "menu":
        return (1, 0, 0, filename)
    match = re.fullmatch(r"(\d+)(?:[_-](l|r))?", lower)
    if match:
        page = int(match.group(1))
        suffix = match.group(2)
        # 同一编号内按 r、l、无后缀排列，满足双页图片的阅读顺序。
        side = {"r": 0, "l": 1, None: 2}[suffix]
        return (2, page, side, filename)
    # 其余文件垫底，但按文件名里的数字**数值**排序（数字感知），
    # 数字/非数字片段交替出现 ⇒ 逐元素比较不会 int 撞 str（分段结构保证）。
    tokens = [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", filename)]
    return (999, tokens, filename)
