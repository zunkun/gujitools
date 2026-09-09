"""图像处理核心工具：Otsu 阈值计算、红色印章提取、区域/整图去底、border 参数解析。

此模块是去底色（rembg / cropremove）功能的核心算法层，提供以下能力：

1. **阈值计算** (`calculate_auto_threshold`)
   手写实现的大津法（Otsu），遍历 0~255 所有可能阈值，找到使前景/背景类间方差最大的阈值。

2. **红色印章提取** (`extract_red_seal`)
   基于 HSV 色域双区间匹配红色像素（H∈[0,10]∪[162,180]），经形态学清理和连通域过滤后，
   返回红色掩码和是否存在"合格印章"的标志。印章合格性由面积、纵横比、填充率三个指标判定。

3. **区域/整图去底** (`apply_otsu_to_region` / `apply_otsu_whole`)
   对给定阈值将灰度图分为文本（< threshold）和背景（≥ threshold）两类，生成白底黑字输出。
   支持 3 种输出类型：二值图(type=1)、1bit 单色位图(type=2)、灰度图(type=3)。
   当启用 seal_color 且存在印章时，输出 RGB 彩色图，保留印章原色。

4. **border 参数解析** (`parse_border` / `parse_border_mm`)
   将 CSS 风格的 1~4 值边距写法展开为 [top, right, bottom, left] 四元组。
   `parse_border_mm` 额外按 DPI 将毫米转换为像素。
"""

import numpy as np
import cv2
from typing import Optional, List, Tuple


# ---------- 阈值计算 ----------
def calculate_auto_threshold(pixels: np.ndarray) -> int:
    """大津法（Otsu）计算最佳阈值。

    算法原理：遍历所有可能阈值 t (0~255)，将像素分为前景(≤t)和背景(>t)两类，
    计算类间方差 σ² = w_b·w_f·(m_b - m_f)²，使 σ² 最大的 t 即为最佳阈值。

    参数:
        pixels: 一维 uint8 像素数组（通常为非白像素子集）。

    返回:
        0~255 范围内的整数阈值。

    实现细节:
    - 使用直方图代替逐像素遍历，复杂度 O(256) 而非 O(N)；
    - sum_total 预算所有像素值之和，避免重复求和；
    - 当前景或背景像素数为 0 时跳过该阈值。
    """
    hist, _ = np.histogram(pixels, bins=256, range=[0, 256])
    total = pixels.size
    sum_total = np.dot(np.arange(256), hist)  # 所有像素灰度值之和
    sum_b = 0      # 前景像素灰度值累计和
    w_b = 0        # 前景像素数
    max_var = 0
    best_t = 128   # 默认阈值
    for t in range(256):
        w_b += hist[t]             # 将灰度值 t 归入前景类
        if w_b == 0:
            continue
        w_f = total - w_b          # 背景像素数
        if w_f == 0:
            break                  # 前景已包含所有像素
        sum_b += t * hist[t]       # 前景灰度值累计
        m_b = sum_b / w_b          # 前景平均灰度
        m_f = (sum_total - sum_b) / w_f  # 背景平均灰度
        var_between = w_b * w_f * (m_b - m_f) ** 2  # 类间方差
        if var_between > max_var:
            max_var = var_between
            best_t = t
    return best_t


# ---------- 红色印章提取 ----------
def extract_red_seal(rgb_img: np.ndarray, min_seal_area: int, min_saturation: int) -> Tuple[np.ndarray, bool]:
    """从 RGB 图像中提取红色印章掩码。

    算法流程:
    1. RGB → HSV 色域转换；
    2. 双区间 inRange 匹配红色像素（HSV 中红色分布在色环两端）；
    3. 形态学开运算去孤立噪点，膨胀修补断裂；
    4. findContours 提取连通域，逐个做面积/纵横比/填充率过滤；
    5. 分离出 red_mask（所有红色像素）和 valid_seal_mask（仅合格印章）。

    参数:
        rgb_img: RGB 格式图像数组 (H, W, 3)。
        min_seal_area: 印章最小连通域像素面积，低于此值的红色区域不视为印章。
        min_saturation: HSV 中 S 通道下限，过滤浅红色噪声（默认 50）。

    返回:
        (red_mask, has_valid_seal):
        - red_mask: bool 数组 (H, W)，True = 红色像素（用于去底时排除）；
        - has_valid_seal: bool，是否存在合格印章（用于决定是否输出彩色图）。
    """
    hsv = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2HSV)

    # HSV 红色分布在色环两端：低区间 [0,10]，高区间 [162,180]
    # V 下限 55 过滤过暗像素，S 下限由 min_saturation 控制
    lower_red1 = np.array([0, min_saturation, 55])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([162, min_saturation, 55])
    upper_red2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_raw = mask1 + mask2

    # 形态学清理：先开运算去孤立点，再膨胀修补断裂
    kernel_clean = np.ones((2, 2), np.uint8)
    red_clean = cv2.morphologyEx(red_raw, cv2.MORPH_OPEN, kernel_clean, iterations=1)
    kernel_dilate = np.ones((1, 1), np.uint8)
    red_clean = cv2.morphologyEx(red_clean, cv2.MORPH_DILATE, kernel_dilate, iterations=1)

    contours, _ = cv2.findContours(red_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    red_mask = np.zeros_like(red_clean, dtype=np.uint8)       # 所有红色像素
    valid_seal_mask = np.zeros_like(red_clean, dtype=np.uint8)  # 仅合格印章

    # 连通域过滤参数
    min_noise_area = 25          # 低于此面积的连通域视为噪声，不写入 red_mask
    max_aspect_ratio = 2.8       # 印章纵横比上限（排除细长条状噪声）
    min_solidity = 0.35          # 填充率下限：连通域面积 / 外接矩形面积
    valid_seal_cnt = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_noise_area:
            continue
        # 写入 red_mask（用于去底时排除所有红色像素，防止印章被误判为文字）
        cv2.drawContours(red_mask, [cnt], -1, 255, -1)

        # 判断是否为合格印章（面积 + 纵横比 + 填充率三重判定）
        x, y, w, h = cv2.boundingRect(cnt)
        aspect = max(w, h) / min(w, h) if min(w, h) > 0 else 0
        rect_area = w * h
        solidity = area / rect_area if rect_area > 0 else 0
        if area >= min_seal_area and aspect <= max_aspect_ratio and solidity >= min_solidity:
            cv2.drawContours(valid_seal_mask, [cnt], -1, 255, -1)
            valid_seal_cnt += 1

    return (red_mask > 0), (valid_seal_cnt > 0)


# ---------- 区域去底 ----------
def apply_otsu_to_region(
    img_rgb: np.ndarray,
    gray: np.ndarray,
    roi_box: tuple,
    threshold: int,
    enable_seal: bool,
    seal_color: bool,
    red_mask: Optional[np.ndarray],
    img_type: int = 1
) -> np.ndarray:
    """对图像中指定矩形区域执行去底色处理，返回 ROI 大小的结果数组。

    参数:
        img_rgb: 全图 RGB 数组 (H, W, 3)。
        gray: 全图灰度数组 (H, W)。
        roi_box: (x1, y1, x2, y2) 区域坐标。
        threshold: 二值化阈值（由 calculate_auto_threshold 计算）。
        enable_seal: 是否启用了印章检测（影响 red_mask 的使用）。
        seal_color: 是否要求彩色印章输出。
        red_mask: 全图红色印章掩码（None 表示未检测印章）。
        img_type: 输出类型 1=二值 / 2=1bit / 3=灰度。

    返回:
        ROI 大小的数组：
        - seal_color 模式且存在印章 → (h, w, 3) RGB，白底 + 红色印章原色 + 黑色文字；
        - 其他 → (h, w) 单通道，type=3 保留原灰度值，type=1/2 文字为 0（黑）背景为 255（白）。
    """
    x1, y1, x2, y2 = roi_box
    # 裁剪到图像边界内，防止越界
    x1 = max(0, x1); y1 = max(0, y1); x2 = min(gray.shape[1], x2); y2 = min(gray.shape[0], y2)
    roi_rgb = img_rgb[y1:y2, x1:x2]
    roi_gray = gray[y1:y2, x1:x2]

    # 裁剪红色掩码到当前 ROI
    red_mask_roi = None
    has_seal = False
    if enable_seal and red_mask is not None:
        red_mask_roi = red_mask[y1:y2, x1:x2]
        has_seal = np.any(red_mask_roi)

    # 文本掩码：灰度低于阈值的像素 = 文字
    text_mask = roi_gray < threshold
    if red_mask_roi is not None:
        # 从文本掩码中排除红色印章像素，防止印章被误判为文字
        text_mask = text_mask & (~red_mask_roi)

    # 形态学去噪：开运算去除孤立噪点，闭运算填充文字内部孔洞
    mask_u8 = (text_mask * 255).astype(np.uint8)
    kernel = np.ones((1, 1), np.uint8)
    mask_opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel, iterations=1)
    final_text_mask = mask_closed > 0

    if enable_seal and seal_color and has_seal:
        # 彩色输出模式：白底 + 红色印章原色 + 黑色文字
        roi_out = np.full((y2 - y1, x2 - x1, 3), 255, dtype=np.uint8)
        roi_out[red_mask_roi] = roi_rgb[red_mask_roi]     # 保留印章原色
        roi_out[final_text_mask] = 0                       # 文字置黑
    else:
        # 单通道输出：白底 + 文字（黑或灰）
        roi_out = np.full((y2 - y1, x2 - x1), 255, dtype=np.uint8)
        if img_type == 3:
            # 灰度模式：文字保留原灰度值（层次更丰富）
            roi_out[final_text_mask] = roi_gray[final_text_mask]
        else:
            # 二值模式：文字置黑
            roi_out[final_text_mask] = 0
    return roi_out


# ---------- 整图去底 ----------
def apply_otsu_whole(
    img_rgb: np.ndarray,
    gray: np.ndarray,
    threshold: int,
    red_mask: Optional[np.ndarray],
    seal_color: bool,
    img_type: int = 1
) -> np.ndarray:
    """对整张图执行去底色处理，返回与输入同尺寸的结果数组。

    与 `apply_otsu_to_region` 逻辑一致，但作用于整图而非局部 ROI，
    用于未检测到文本框时的 fallback 路径（整图 Otsu）。

    参数:
        img_rgb: RGB 图像数组 (H, W, 3)。
        gray: 灰度数组 (H, W)。
        threshold: 二值化阈值。
        red_mask: 红色印章掩码（None = 无印章）。
        seal_color: 是否输出彩色印章。
        img_type: 1=二值 / 2=1bit / 3=灰度。

    返回:
        (H, W, 3) 彩色 或 (H, W) 单通道数组。
    """
    H, W = gray.shape
    # 文本掩码：灰度低于阈值 = 文字
    text_mask = gray < threshold
    if red_mask is not None:
        # 排除印章区域，防止红色被误判为文字
        text_mask = text_mask & (~red_mask)

    # 形态学去噪
    mask_u8 = (text_mask * 255).astype(np.uint8)
    kernel = np.ones((1, 1), np.uint8)
    mask_opened = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel, iterations=1)
    mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel, iterations=1)
    final_text_mask = mask_closed > 0

    has_seal = red_mask is not None and np.any(red_mask) if red_mask is not None else False

    if seal_color and has_seal and red_mask is not None:
        # 彩色输出：白底 + 印章原色 + 黑色文字
        out_arr = np.full((H, W, 3), 255, dtype=np.uint8)
        out_arr[red_mask] = img_rgb[red_mask]
        out_arr[final_text_mask] = 0
    else:
        # 单通道输出
        out_arr = np.full((H, W), 255, dtype=np.uint8)
        if img_type == 3:
            out_arr[final_text_mask] = gray[final_text_mask]
        else:
            out_arr[final_text_mask] = 0
    return out_arr


# ---------- border 参数解析 ----------
def parse_border(border_value) -> Optional[List[int]]:
    """解析 border 参数（像素单位），支持 CSS 风格 1~4 值写法。

    写法规则（与 CSS margin 一致）:
    - 单值 30       → [30, 30, 30, 30]  (上右下左)
    - 两值 20,30    → [20, 30, 20, 30]  (上下, 左右)
    - 三值 20,30,25 → [20, 30, 25, 30]  (上, 左右, 下)
    - 四值 10,20,30,40 → [10, 20, 30, 40]  (上, 右, 下, 左)

    参数:
        border_value: None / int / 逗号分隔字符串。

    返回:
        [top, right, bottom, left] 像素列表，或 None。
    """
    if border_value is None:
        return None
    if isinstance(border_value, int):
        return [border_value] * 4
    if isinstance(border_value, str):
        parts = [part.strip() for part in border_value.split(",") if part.strip() != ""]
        values = [int(part) for part in parts]
        if len(values) == 1:
            return [values[0]] * 4
        if len(values) == 2:
            return [values[0], values[1], values[0], values[1]]
        if len(values) == 3:
            return [values[0], values[1], values[2], values[1]]
        if len(values) == 4:
            return values
    raise ValueError("border 参数格式不正确，支持 1~4 个英文逗号分隔整数")


def parse_border_mm(border_value, dpi: int = 300) -> Optional[List[int]]:
    """解析 border 参数（毫米单位），按 DPI 转换为像素。

    与 `parse_border` 的写法规则相同，但最终值经过 mm→px 换算。
    换算公式: px = mm × dpi / 25.4（25.4mm = 1inch）。

    参数:
        border_value: None / int / 逗号分隔字符串（单位 mm）。
        dpi: 扫描分辨率，默认 300（古籍扫描常用值）。

    返回:
        [top, right, bottom, left] 像素列表，或 None。
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
    # mm → px 换算：25.4mm = 1 英寸
    mm_to_px = dpi / 25.4
    return [int(round(v * mm_to_px)) for v in values]
