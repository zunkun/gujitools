# utils/string_utils.py
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
