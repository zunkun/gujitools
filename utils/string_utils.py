"""数字转中文等字符串辅助工具。

当前提供：

- ``num_to_chinese``：整数转中文数字（支持万以内）；
- ``num_to_ganzhi``：整数转**干支**（六十甲子，古籍册次/卷次常用）；
- ``format_page_number``：按「样式 + 前缀 + 后缀」拼出页码文本——第四步
  页码样式的**唯一组装处**（PDF 与预览共用同一份）。
"""

def num_to_chinese(num: int) -> str:
    """将整数转换为中文数字（支持万以内）。"""
    digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    units = ["", "十", "百", "千", "萬"]
    if num < 0:
        return "負" + num_to_chinese(-num)
    if num == 0:
        return "零"
    if 1 <= num <= 99:
        if num < 10:
            return digits[num]
        if num == 10:
            return "十"
        if 11 <= num <= 19:
            return "十" + digits[num % 10]
        shi, ge = divmod(num, 10)
        if ge == 0:
            return digits[shi] + "十"
        return digits[shi] + "十" + digits[ge]
    # 100以上简化转换（仅支持到万）
    result = ""
    num_str = str(num)
    length = len(num_str)
    for i, ch in enumerate(num_str):
        digit = int(ch)
        if digit == 0:
            if i < length - 1 and int(num_str[i + 1]) != 0:
                result += "零"
            continue
        pos = length - i - 1
        if pos >= len(units):
            return str(num)
        result += digits[digit] + units[pos]
    if result.startswith("一十"):
        result = result[1:]
    if result.endswith("零"):
        result = result[:-1]
    return result if result else str(num)


#: 十天干
_HEAVENLY_STEMS = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
#: 十二地支
_EARTHLY_BRANCHES = (
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
)


def num_to_ganzhi(num: int) -> str:
    """将整数转换为干支纪序（六十甲子）：1 → 甲子，2 → 乙丑，61 → 甲子。

    古籍的册次/卷次常用干支编号。天干 10 与地支 12 的最小公倍数是 60，
    所以序号按 60 循环（超过 60 从头再来，不会越界）。非正整数退化为
    阿拉伯数字，保证任何输入都有可打印的结果。
    """
    try:
        value = int(num)
    except (TypeError, ValueError):
        return str(num)
    if value <= 0:
        return str(num)
    index = (value - 1) % 60
    return _HEAVENLY_STEMS[index % 10] + _EARTHLY_BRANCHES[index % 12]


def format_page_number(
    num: int,
    style: str = "chinese",
    prefix: str = "",
    suffix: str = "",
) -> str:
    """按「样式 + 前缀 + 后缀」拼出页码文本（第四步页码的唯一组装处）。

    - ``chinese``：中文数字（五），``num_to_chinese``；
    - ``arabic``：阿拉伯数字（5）；
    - ``ganzhi``：干支（甲子，60 循环）；
    - 认不出的样式按中文数字处理——老配置里可能存着别的值，回落成中文
      比抛异常或印出空串都好。

    前缀/后缀是**原样拼接**的（不做空格补全）：想排「第 5 页」就把前缀写成
    ``"第 "``。空前缀/后缀表示只要数字本身。
    """
    text_style = str(style or "chinese").strip().lower()
    if text_style == "arabic":
        body = str(int(num)) if str(num).lstrip("-").isdigit() else str(num)
    elif text_style == "ganzhi":
        body = num_to_ganzhi(num)
    else:
        body = num_to_chinese(num)
    return f"{prefix or ''}{body}{suffix or ''}"
