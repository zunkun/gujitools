# -*- coding: utf-8 -*-
"""整页去底色的**阈值算法族**：统一入口/出口 + 7 种实现。

为什么单独一个模块
------------------
去底色原先只有一条「全局 Otsu」路径，阈值计算散在 ``utils/image_utils.py`` 里。
用户 2026-10-24 要求把固定阈值、全局均值、Otsu、Niblack、Sauvola、Bernsen、
Wolf-Jolion 都做成可选算法，并把「入口 / 出口」抽象成一套面向对象接口——这样
加一种算法只需加一个子类，而不是在 ``rembg_page`` 里再长一条 ``if`` 分支。

三条硬约定
----------
1. **入口 = 灰度图，出口 = 文本掩码**。
   :meth:`RembgAlgorithm.text_mask` 吃 ``(H, W)`` 的 ``uint8`` 灰度数组，返回
   ``(H, W)`` 的 ``bool`` 掩码（``True`` = 文字）。印章排除、形态学去噪与输出
   类型（二值/1bit/灰度/彩色）都不属于算法本身，留在
   :func:`utils.image_utils.rembg_page` 的公共收尾里。
2. **Otsu 必须与旧实现逐像素一致**（默认算法，历史任务都按它出图）：
   非白像素 > 500 时用「非白子集 + offset」，否则固定 128，最后夹到 [30, 240]。
3. **本模块可被 GUI 主进程导入**：顶部不 import numpy/cv2，重依赖全部在函数内
   延迟导入。桌面面板只取 :data:`ALGORITHMS` 里的 key/label，不会因此把 cv2
   拉进主进程（域内规矩见 ``AGENTS.md``）。

局部算法（Niblack / Sauvola / Bernsen / Wolf-Jolion）按**行分块**计算：一整页
5000×4400 的 float32 中间数组约 88MB，整页算会乘上并发数；分块后峰值只与
块宽有关，产物仍与整页计算等价（块上下各留 ``window // 2`` 行 halo，
边界用 ``BORDER_REPLICATE``，与整页滤波一致）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class AlgorithmInfo:
    """一种阈值算法的元数据（下拉框与帮助文案的唯一来源）。"""

    key: str
    label: str
    description: str


#: 算法候选表（顺序即下拉框顺序）。key 是命令行/JSON 里的值，label 是界面文案。
ALGORITHMS: tuple[AlgorithmInfo, ...] = (
    AlgorithmInfo("otsu", "Otsu 大津法", "全局类间方差最大，默认算法，适合直方图近似双峰的页"),
    AlgorithmInfo("fixed", "固定阈值 (Fixed)", "使用预设固定值，极快但完全不适应图像变化"),
    AlgorithmInfo("mean", "全局均值 (Mean)", "用整页平均灰度作阈值，对前景/背景比例敏感"),
    AlgorithmInfo("niblack", "Niblack", "局部均值与标准差，适应光照变化，平坦区易出噪点"),
    AlgorithmInfo("sauvola", "Sauvola", "Niblack + 动态范围抑制噪声，古籍文档效果最好"),
    AlgorithmInfo("bernsen", "Bernsen", "局部最大/最小对比度，对背景灰度渐变鲁棒"),
    AlgorithmInfo("wolf", "Wolf-Jolion", "局部统计 + 全局极值归一化，适合低对比度/光照不均"),
)

#: 算法 key 的合法集合（CLI choices / 参数校验共用）。
ALGORITHM_KEYS: tuple[str, ...] = tuple(item.key for item in ALGORITHMS)

#: 需要局部窗口的算法（面板据此决定「窗口/k」控件是否可用）。
LOCAL_ALGORITHM_KEYS: frozenset[str] = frozenset(
    {"niblack", "sauvola", "bernsen", "wolf"}
)

#: 默认算法（用户口径：默认仍是 Otsu）。
REMBG_DEFAULT_ALGORITHM = "otsu"
#: 局部窗口边长默认值（奇数更常见；偶数也支持）。
REMBG_DEFAULT_WINDOW = 25
#: 局部算法灵敏度默认值（0~1，Niblack 内部取负号，Bernsen 映射为对比度下限）。
REMBG_DEFAULT_K = 0.2

#: 全局阈值的夹紧范围（与旧 Otsu 实现完全一致）。
THRESHOLD_MIN = 30
THRESHOLD_MAX = 240

#: 局部算法的分块行数：控制 float32 中间数组的峰值内存。
_BLOCK_ROWS = 512

#: Sauvola / Wolf-Jolion 公式里的动态范围常数。
_DYNAMIC_RANGE = 128.0

#: Bernsen 的对比度下限换算：k × 该系数（默认 k=0.2 → 15）。
_BERNSEN_CONTRAST_SCALE = 75.0


def clamp_global_threshold(value: float) -> int:
    """全局阈值夹到 [30, 240]（避免极端 offset 把整页推成全黑/全白）。"""
    return min(max(int(round(value)), THRESHOLD_MIN), THRESHOLD_MAX)


class RembgAlgorithm(ABC):
    """阈值算法基类：**入口 = 灰度图，出口 = 文本掩码**。

    子类只需实现 :meth:`thresholds`（全局算法返回一个整数阈值，局部算法返回
    与图像同尺寸的阈值图）；文字/背景的判定统一在 :meth:`text_mask` 里做。
    """

    key: str = ""

    @abstractmethod
    def thresholds(
        self,
        gray: "np.ndarray",
        *,
        offset: int = 0,
        window: int = REMBG_DEFAULT_WINDOW,
        k: float = REMBG_DEFAULT_K,
    ) -> "int | np.ndarray":
        """计算阈值：整数（全局）或 ``(H, W)`` 数组（局部）。"""

    def text_mask(
        self,
        gray: "np.ndarray",
        *,
        offset: int = 0,
        window: int = REMBG_DEFAULT_WINDOW,
        k: float = REMBG_DEFAULT_K,
    ) -> "np.ndarray":
        """**统一出口**：灰度 < 阈值 ⇒ ``True``（文字）。"""
        threshold = self.thresholds(gray, offset=offset, window=window, k=k)
        return gray < threshold

    def shared_threshold(
        self,
        grays: "list[np.ndarray]",
        *,
        offset: int = 0,
    ) -> "int | None":
        """**多张图合并**算一个公共阈值（同页左右裁图共享）。

        默认返回 ``None``：局部算法逐像素定阈值，不能跨图共享。全局算法
        （fixed/mean/otsu）各自覆盖本方法，把多张图的统计量合在一起算。
        """
        return None


class FixedThresholdAlgorithm(RembgAlgorithm):
    """固定阈值：预设 128（叠加 offset 后夹紧）。"""

    key = "fixed"

    #: 预设固定值。用户要求「固定阈值」保留一个可预期的基准。
    FIXED_THRESHOLD = 128

    def thresholds(self, gray, *, offset=0, window=REMBG_DEFAULT_WINDOW,
                   k=REMBG_DEFAULT_K):
        return clamp_global_threshold(self.FIXED_THRESHOLD + int(offset))

    def shared_threshold(self, grays, *, offset=0):
        # 固定值与像素无关：合并后仍是同一个值。
        return clamp_global_threshold(self.FIXED_THRESHOLD + int(offset))


class GlobalMeanAlgorithm(RembgAlgorithm):
    """全局均值：整页平均灰度作阈值（叠加 offset 后夹紧）。"""

    key = "mean"

    def thresholds(self, gray, *, offset=0, window=REMBG_DEFAULT_WINDOW,
                   k=REMBG_DEFAULT_K):
        import numpy as np

        return clamp_global_threshold(float(np.mean(gray)) + int(offset))

    def shared_threshold(self, grays, *, offset=0):
        """多图合并的加权平均（按像素数加权），单图与 :meth:`thresholds` 一致。"""
        import numpy as np

        images = list(grays)
        if not images:
            return None
        if len(images) == 1:
            mean = float(np.mean(images[0]))
        else:
            total = sum(int(g.size) for g in images)
            pixel_sum = sum(int(g.sum(dtype=np.int64)) for g in images)
            mean = pixel_sum / total if total else 0.0
        return clamp_global_threshold(mean + int(offset))


class OtsuAlgorithm(RembgAlgorithm):
    """Otsu 大津法：与旧 ``rembg_page`` 的阈值计算逐位一致。"""

    key = "otsu"

    def thresholds(self, gray, *, offset=0, window=REMBG_DEFAULT_WINDOW,
                   k=REMBG_DEFAULT_K):
        import numpy as np

        # 函数内导入：image_utils 在模块顶部导入本模块，顶层互相导入会成环。
        from utils.image_utils import calculate_auto_threshold

        # 只让「非白像素」参与 Otsu：整页大片白底会把阈值拉偏。
        # 非白像素不足 500 视为近似空白页，退化为固定 128。
        non_white = gray < 250
        if np.count_nonzero(non_white) > 500:
            threshold = calculate_auto_threshold(gray[non_white]) + int(offset)
        else:
            threshold = 128
        return clamp_global_threshold(threshold)

    def shared_threshold(self, grays, *, offset=0):
        """多图合并：把各图非白像素的直方图相加，再算一次 Otsu。

        ⚠️ 单图时与 :meth:`thresholds` **逐位一致**（同一直方图 + 同一循环）；
        多图时不需要把像素拼成一个大数组，峰值内存只多一张 256 长的直方图。
        """
        import numpy as np

        # 函数内导入：image_utils 在模块顶部导入本模块，顶层互相导入会成环。
        from utils.image_utils import otsu_threshold_from_hist

        images = list(grays)
        if not images:
            return None
        hist = np.zeros(256, np.int64)
        count = 0
        for image in images:
            non_white = image[image < 250]
            if non_white.size:
                hist += np.bincount(non_white, minlength=256).astype(np.int64)
                count += int(non_white.size)
        threshold = otsu_threshold_from_hist(hist, count) if count > 500 else 128
        return clamp_global_threshold(threshold + int(offset))


class LocalAlgorithm(RembgAlgorithm, ABC):
    """局部算法的公共骨架：按行分块 → 每块算阈值图 → 拼回整页掩码。"""

    def thresholds(self, gray, *, offset=0, window=REMBG_DEFAULT_WINDOW,
                   k=REMBG_DEFAULT_K):
        """局部算法的阈值是逐像素图，统一出口是 :meth:`text_mask` 而不是这里。"""
        raise NotImplementedError("局部算法请使用 text_mask()")

    def text_mask(
        self,
        gray,
        *,
        offset: int = 0,
        window: int = REMBG_DEFAULT_WINDOW,
        k: float = REMBG_DEFAULT_K,
    ) -> "np.ndarray":
        import numpy as np

        win = max(3, int(window))
        half = win // 2
        height = int(gray.shape[0])
        mask = np.empty(gray.shape, dtype=bool)
        context = self._prepare(gray, win, k)
        for y0 in range(0, height, _BLOCK_ROWS):
            y1 = min(height, y0 + _BLOCK_ROWS)
            g0 = max(0, y0 - half)
            g1 = min(height, y1 + half)
            block = gray[g0:g1]
            thresholds = self._block_threshold(
                block, win, int(offset), float(k), context
            )
            top = y0 - g0
            mask[y0:y1] = gray[y0:y1] < thresholds[top:top + (y1 - y0)]
        return mask

    def _prepare(self, gray, window: int, k: float):
        """整页级预统计（只有 Wolf-Jolion 需要全局最小值）。"""
        return None

    @abstractmethod
    def _block_threshold(
        self, block: "np.ndarray", window: int, offset: int, k: float, context
    ) -> "np.ndarray":
        """一块（带上下 halo）→ 与该块同尺寸的 ``uint8`` 阈值图。"""


def _local_mean_std(block: "np.ndarray", window: int):
    """``(局部均值, 局部标准差)``，均为 float32 且与 block 同尺寸。"""
    import cv2
    import numpy as np

    values = block.astype(np.float32)
    mean = cv2.boxFilter(
        values, cv2.CV_32F, (window, window),
        normalize=True, borderType=cv2.BORDER_REPLICATE,
    )
    squared = cv2.boxFilter(
        values * values, cv2.CV_32F, (window, window),
        normalize=True, borderType=cv2.BORDER_REPLICATE,
    )
    variance = np.maximum(squared - mean * mean, 0.0, out=squared)
    std = np.sqrt(variance, out=variance)
    return mean, std


def _to_u8(thresholds: "np.ndarray") -> "np.ndarray":
    """阈值图 → ``uint8``（夹到 [0, 255]，与 uint8 灰度比较时省一次浮点提升）。"""
    import numpy as np

    return np.clip(thresholds, 0, 255).astype(np.uint8)


class NiblackAlgorithm(LocalAlgorithm):
    """Niblack：``T = mean - k × std``（k 取正值，内部固定为负号）。"""

    key = "niblack"

    def _block_threshold(self, block, window, offset, k, context):
        mean, std = _local_mean_std(block, window)
        return _to_u8(mean - abs(k) * std + offset)


class SauvolaAlgorithm(LocalAlgorithm):
    """Sauvola：``T = mean × (1 + k × (std / R - 1))``，R=128。"""

    key = "sauvola"

    def _block_threshold(self, block, window, offset, k, context):
        mean, std = _local_mean_std(block, window)
        return _to_u8(
            mean * (1.0 + abs(k) * (std / _DYNAMIC_RANGE - 1.0)) + offset
        )


class WolfJolionAlgorithm(LocalAlgorithm):
    """Wolf-Jolion：``T = mean - k × (mean - M) × (1 - std / R)``。

    ``M`` 是整页最小灰度（全局极值），用于低对比度/光照不均的页。
    """

    key = "wolf"

    def _prepare(self, gray, window, k):
        import numpy as np

        return float(np.min(gray))

    def _block_threshold(self, block, window, offset, k, context):
        mean, std = _local_mean_std(block, window)
        darkest = float(context if context is not None else 0.0)
        return _to_u8(
            mean - abs(k) * (mean - darkest) * (1.0 - std / _DYNAMIC_RANGE)
            + offset
        )


class BernsenAlgorithm(LocalAlgorithm):
    """Bernsen：局部对比度（max - min）。

    对比度足够时取 ``(min + max) / 2``；对比度不足的平坦区按局部中值偏黑/偏白
    直接判为文字/背景。``k`` 映射为对比度下限（``k × 75``，默认 0.2 → 15）。
    """

    key = "bernsen"

    def _block_threshold(self, block, window, offset, k, context):
        import cv2
        import numpy as np

        kernel = np.ones((window, window), np.uint8)
        low = cv2.erode(block, kernel, borderType=cv2.BORDER_REPLICATE)
        high = cv2.dilate(block, kernel, borderType=cv2.BORDER_REPLICATE)
        contrast = high.astype(np.int16) - low.astype(np.int16)
        middle = (low.astype(np.int16) + high.astype(np.int16)) // 2
        min_contrast = max(1, int(round(abs(k) * _BERNSEN_CONTRAST_SCALE)))
        # 平坦区：局部偏黑 → 整块算文字（255），偏白 → 整块算背景（0）
        flat = np.where(middle < 128, 255, 0)
        return _to_u8(
            np.where(contrast >= min_contrast, middle, flat) + offset
        )


#: key → 实现实例（注册表；加算法只需在这里加一行）。
_ALGORITHM_INSTANCES: dict[str, RembgAlgorithm] = {
    algo.key: algo
    for algo in (
        OtsuAlgorithm(),
        FixedThresholdAlgorithm(),
        GlobalMeanAlgorithm(),
        NiblackAlgorithm(),
        SauvolaAlgorithm(),
        BernsenAlgorithm(),
        WolfJolionAlgorithm(),
    )
}


def get_algorithm(key: Optional[str]) -> RembgAlgorithm:
    """按 key 取算法实例；未知 key 抛 ``ValueError``（不静默回落）。"""
    name = str(key or REMBG_DEFAULT_ALGORITHM)
    algorithm = _ALGORITHM_INSTANCES.get(name)
    if algorithm is None:
        raise ValueError(
            f"未知去底色算法 {name!r}，可选：{'/'.join(ALGORITHM_KEYS)}"
        )
    return algorithm


def text_mask(
    gray: "np.ndarray",
    algorithm: Optional[str] = None,
    *,
    offset: int = 0,
    window: int = REMBG_DEFAULT_WINDOW,
    k: float = REMBG_DEFAULT_K,
) -> "np.ndarray":
    """便捷入口：灰度图 → 文本掩码（等价于 ``get_algorithm(...).text_mask(...)``）。"""
    return get_algorithm(algorithm).text_mask(
        gray, offset=offset, window=window, k=k
    )


__all__ = [
    "ALGORITHM_KEYS",
    "ALGORITHMS",
    "AlgorithmInfo",
    "BernsenAlgorithm",
    "FixedThresholdAlgorithm",
    "GlobalMeanAlgorithm",
    "LOCAL_ALGORITHM_KEYS",
    "LocalAlgorithm",
    "NiblackAlgorithm",
    "OtsuAlgorithm",
    "REMBG_DEFAULT_ALGORITHM",
    "REMBG_DEFAULT_K",
    "REMBG_DEFAULT_WINDOW",
    "RembgAlgorithm",
    "SauvolaAlgorithm",
    "WolfJolionAlgorithm",
    "clamp_global_threshold",
    "get_algorithm",
    "text_mask",
]
