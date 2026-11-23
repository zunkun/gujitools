# -*- coding: utf-8 -*-
"""整页去底色的**阈值算法族**：统一入口/出口 + 11 种实现（其中 6 种扩展算法）。

为什么单独一个模块
------------------
去底色原先只有一条「全局 Otsu」路径，阈值计算散在 ``utils/image_utils.py`` 里。
用户 2026-10-24 要求把各种阈值算法都做成可选算法，并把「入口 / 出口」抽象成
一套面向对象接口——这样加一种算法只需加一个子类，而不是在 ``rembg_page`` 里
再长一条 ``if`` 分支。用户 2026-11-23 又要求去掉不实用的「固定阈值(fixed)」与
「全局均值(mean)」，只留 Otsu + 四种局部算法；同一天补了 6 种文献算法
（NICK / Feng / Parker / Gatos / Howe / Su）。

扩展算法的口径
--------------
它们是文献里的多阶段方法，这里统一压成「局部阈值图 / 逐块掩码」，以便和既有
算法共用参数与性能模型。被简化的环节写在每个类的 docstring 里（Gatos 不做
Wiener 滤波与背景插值、Su 不做笔画宽度自适应窗口）。结果不承诺与论文逐位一致，
但与内置算法一样开箱可用——:data:`ALGORITHMS` 里给每种算法标了推荐窗口/灵敏度
（见 :func:`recommended_params`），选中即带上，用户不必自己摸参数。

**「空心字」这条坑单独说**：Parker 与 Howe 的判据都是「本像素比邻域更暗」，
只把**笔画边缘**判成文字，笔画内部因为「邻域一样暗」被判成背景 ⇒ 出来是空心
描边。原法靠区域生长 / 图割把内部连回去；这里用整页级的
:func:`_fill_dark_holes`（不与纸面连通且够暗的空洞回填）替代，配
:func:`_drop_small_components`（纸纹留下的 1~3 像素孤立点）——两者都只在**整页
掩码**上做一次，因此与分块无关（自测钉住「缩小块大小后逐像素一致」）。


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

局部算法（Niblack / Sauvola / Bernsen / Wolf-Jolion 与 6 种扩展算法）按**行分块**
计算：一整页 5000×4400 的 float32 中间数组约 88MB，整页算会乘上并发数；分块后
峰值只与块宽有关，产物仍与整页计算等价（块上下各留 ``window // 2`` 行 halo，
边界用 ``BORDER_REPLICATE``，与整页滤波一致；背景估计类算法再多留
:meth:`LocalAlgorithm._block_halo` 行的余量）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np


#: 默认算法（用户口径：默认仍是 Otsu）。
REMBG_DEFAULT_ALGORITHM = "otsu"
#: 阶段级窗口边长默认值（全局算法 Otsu 用不上；各局部算法有自己的推荐值）。
REMBG_DEFAULT_WINDOW = 25
#: 阶段级灵敏度默认值（同上）。
REMBG_DEFAULT_K = 0.2


#: 算法**分类**（下拉框分组标题的唯一来源，顺序即分组顺序）。
#:
#: 用户 2026-11-24 口径：下拉框里的算法要分类摆放。分类按**判据原理**分，不按
#: 新旧——这样每组内部的参数语义一致（同类里 ``k`` 是同一种意思），出问题的
#: 形态也一致（哪些会出空心字、哪些平坦区出噪点）。第一条同时对应
#: :data:`LOCAL_ALGORITHM_KEYS` 的补集：只有「全局阈值」组不吃窗口/灵敏度。
ALGORITHM_CATEGORIES: tuple[str, ...] = (
    "全局阈值",
    "局部统计（Niblack 族）",
    "对比度 / 边缘",
    "背景估计 / 混合",
)


@dataclass(frozen=True)
class AlgorithmInfo:
    """一种阈值算法的元数据（下拉框分组、帮助文案、推荐参数的唯一来源）。

    ``window`` / ``k`` 是该算法的**推荐默认参数**：面板切到这个算法、CLI 没显式
    给 ``--window/--k`` 时都用它。2026-11-23 在三张真实页（长边 ~2100px）上按
    「F1（对 Sauvola 共识）+ 孤立噪点惩罚 + 墨量偏差 + 笔画核心保留」打分定标，
    平台区内取最接近原有 25 / 0.2 的值（详见 :func:`recommended_params`）。
    """

    key: str
    label: str
    description: str
    #: 所属分类，必须是 :data:`ALGORITHM_CATEGORIES` 里的一项。
    category: str = ALGORITHM_CATEGORIES[0]
    #: 推荐窗口边长（像素）；全局算法（Otsu）用不上，保留占位值。
    window: int = REMBG_DEFAULT_WINDOW
    #: 推荐灵敏度（0~1）。
    k: float = REMBG_DEFAULT_K


#: 算法候选表（**顺序即下拉框顺序，同一分类必须相邻**——面板按分类插组标题）。
#: key 是命令行/JSON 里的值，label 是界面文案。
ALGORITHMS: tuple[AlgorithmInfo, ...] = (
    AlgorithmInfo(
        "otsu", "Otsu 大津法",
        "全局类间方差最大，默认算法，适合直方图近似双峰的页",
        category="全局阈值",
    ),
    AlgorithmInfo(
        "niblack", "Niblack",
        "局部均值±k×标准差，适应光照变化；灵敏度过小易出噪点，故推荐 0.40",
        category="局部统计（Niblack 族）", window=41, k=0.40,
    ),
    AlgorithmInfo(
        "nick", "NICK",
        "Niblack 的负 k 变体（文献固定 k=-0.2），数学上与 Niblack 等价，仅作文献对照",
        category="局部统计（Niblack 族）", window=41, k=0.20,
    ),
    AlgorithmInfo(
        "feng", "Feng",
        "Niblack 改良：局部对比度 + 局部最小值，按文献取固定 α",
        category="局部统计（Niblack 族）",
    ),
    AlgorithmInfo(
        "sauvola", "Sauvola",
        "Niblack + 动态范围抑制噪声，古籍文档效果最好",
        category="局部统计（Niblack 族）",
    ),
    AlgorithmInfo(
        "wolf", "Wolf-Jolion",
        "局部统计 + 全局极值归一化，适合低对比度/光照不均",
        category="局部统计（Niblack 族）",
    ),
    AlgorithmInfo(
        "bernsen", "Bernsen",
        "局部最大/最小对比度，对背景灰度渐变鲁棒；灵敏度即对比度下限",
        category="对比度 / 边缘", window=25, k=0.40,
    ),
    AlgorithmInfo(
        "parker", "Contrast（Parker）",
        "8 邻域最亮值求负梯度再取局部统计；笔画内部暗洞回填，不做区域生长",
        category="对比度 / 边缘", window=41, k=0.20,
    ),
    AlgorithmInfo(
        "howe", "Howe",
        "拉普拉斯谷底 + 局部对比度/更暗门限；省略图割连续性，用连通域清理代替",
        category="对比度 / 边缘", window=25, k=0.30,
    ),
    AlgorithmInfo(
        "gatos", "Gatos",
        "背景估计 + 差分阈值；简化：不做 Wiener 滤波与背景插值（灵敏度对它无效）",
        category="背景估计 / 混合",
    ),
    AlgorithmInfo(
        "su", "Su",
        "笔画边缘（对比度 Otsu）+ 边缘邻域均值/标准差；简化：窗口不随笔画宽度自适应",
        category="背景估计 / 混合", window=21, k=0.30,
    ),
)

#: 算法 key 的合法集合（CLI choices / 参数校验共用）。
ALGORITHM_KEYS: tuple[str, ...] = tuple(item.key for item in ALGORITHMS)

#: 2026-11-23 加入的 6 种扩展算法（不参与默认选型，供同页横向对比）。
EXPERIMENTAL_ALGORITHM_KEYS: frozenset[str] = frozenset(
    {"nick", "feng", "parker", "gatos", "howe", "su"}
)

#: 需要局部窗口的算法（面板据此决定「窗口/k」控件是否可用）。
LOCAL_ALGORITHM_KEYS: frozenset[str] = frozenset(
    {"niblack", "sauvola", "bernsen", "wolf"}
) | EXPERIMENTAL_ALGORITHM_KEYS


def algorithm_groups() -> tuple[tuple[str, tuple[AlgorithmInfo, ...]], ...]:
    """按分类分组：``((类名, (算法…)), …)``，顺序 = :data:`ALGORITHM_CATEGORIES`。

    面板据此插组标题；空分类不出现（加/删算法不必同步改这里）。
    """
    groups = []
    for category in ALGORITHM_CATEGORIES:
        members = tuple(item for item in ALGORITHMS if item.category == category)
        if members:
            groups.append((category, members))
    return tuple(groups)


def recommended_params(key: Optional[str]) -> dict:
    """该算法的推荐默认参数 ``{"window": int, "k": float}``。

    ⚠️ 这是「每种算法一套默认值」的**唯一来源**：面板切算法、CLI 没给
    ``--window/--k``、历史参数缺键时都调这里，别在别处再抄一份数字。

    未知 key（例如已下线算法的历史参数）回落阶段默认，不抛错——回填路径上
    抛错会连带整个面板回填失败。
    """
    name = str(key or REMBG_DEFAULT_ALGORITHM)
    for item in ALGORITHMS:
        if item.key == name:
            return {"window": int(item.window), "k": float(item.k)}
    return {"window": REMBG_DEFAULT_WINDOW, "k": REMBG_DEFAULT_K}


#: 全局阈值的夹紧范围（与旧 Otsu 实现完全一致）。
THRESHOLD_MIN = 30
THRESHOLD_MAX = 240

#: 局部算法的分块行数：控制 float32 中间数组的峰值内存。
_BLOCK_ROWS = 512

#: Sauvola / Wolf-Jolion 公式里的动态范围常数。
_DYNAMIC_RANGE = 128.0

#: Bernsen 的对比度下限换算：k × 该系数（默认 k=0.2 → 15）。
_BERNSEN_CONTRAST_SCALE = 75.0

#: Su 的「笔画边缘」检测窗口 = 用户窗口 / 该系数（向下取奇数，最小 3）。
#: ⚠️ 边缘是一条窄带：用用户窗口（25）去算局部最大/最小，笔画两侧各半个窗口
#: 都算「边缘」，带里纸面占多数 ⇒ 估计出来的阈值被抬到纸面灰度附近，沿每根
#: 笔画留一圈碎噪点（干净合成纸上纸面误判 29%，缩到 5 后降到 2%）。
_SU_EDGE_DIVISOR = 5


def _su_edge_window(window: int) -> int:
    """Su 的边缘检测窗口：用户窗口的 1/5（取奇数，最小 3）。"""
    return max(3, (max(3, int(window)) // _SU_EDGE_DIVISOR) | 1)


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

        默认返回 ``None``：局部算法逐像素定阈值，不能跨图共享。目前只有全局
        算法 Otsu 覆盖本方法，把多张图的直方图合在一起算。
        """
        return None


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
    """局部算法的公共骨架：按行分块 → 每块定墨/纸 → 拼回整页掩码 → 整页收尾。"""

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
        half = win // 2 + max(0, int(self._block_halo(win)))
        height = int(gray.shape[0])
        mask = np.empty(gray.shape, dtype=bool)
        context = self._prepare(gray, win, k)
        for y0 in range(0, height, _BLOCK_ROWS):
            y1 = min(height, y0 + _BLOCK_ROWS)
            g0 = max(0, y0 - half)
            g1 = min(height, y1 + half)
            block = gray[g0:g1]
            ink = self._block_mask(block, win, int(offset), float(k), context)
            top = y0 - g0
            mask[y0:y1] = ink[top:top + (y1 - y0)]
        return self._postprocess(mask, gray, win, float(k), context)

    def _block_mask(
        self, block: "np.ndarray", window: int, offset: int, k: float, context
    ) -> "np.ndarray":
        """一块（带上下 halo）→ 该块的文字掩码（默认「灰度 < 阈值图」）。"""
        thresholds = self._block_threshold(block, window, offset, k, context)
        return block < thresholds

    def _block_halo(self, window: int) -> int:
        """分块时在 ``window // 2`` 之外额外需要的上下余量（默认 0）。

        背景估计/模糊类算法（Gatos）滤波核比窗口更宽，halo 不够就会在块边界
        出现接缝 ⇒ 由子类声明额外行数。
        """
        return 0

    def _prepare(self, gray, window: int, k: float):
        """整页级预统计（全局最小值、全局 Otsu 阈值等）。"""
        return None

    def _postprocess(self, mask, gray, window: int, k: float, context):
        """整页级收尾（默认不做）。子类若需要连通域清理，在这里做。

        只在**整页掩码**上做一次 ⇒ 天然与分块无关（不会因为块大小变化而变结果）。
        """
        return mask

    def _clean_mask(self, mask, gray, window: int, dark_limit=None):
        """扩展算法共用收尾：去孤立噪点 + 回填笔画内部暗洞（治「空心字」）。"""
        cleaned = _drop_small_components(mask, max(8, int(window) // 2))
        limit = _global_dark_limit(gray) if dark_limit is None else float(dark_limit)
        return _fill_dark_holes(cleaned, gray, limit)

    def _block_threshold(
        self, block: "np.ndarray", window: int, offset: int, k: float, context
    ) -> "np.ndarray":
        """一块（带上下 halo）→ 与该块同尺寸的 ``uint8`` 阈值图。

        阈值图型的算法实现这里；**掩码型**算法（Howe：判据不是「灰度 < 阈值」）
        改写 :meth:`_block_mask`，本方法可不管。
        """
        raise NotImplementedError("该算法直接产出掩码，请实现 _block_mask()")


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


def _local_min_max(block: "np.ndarray", window: int):
    """``(局部最小, 局部最大)``，``uint8``，与 block 同尺寸。"""
    import cv2
    import numpy as np

    kernel = np.ones((window, window), np.uint8)
    low = cv2.erode(block, kernel, borderType=cv2.BORDER_REPLICATE)
    high = cv2.dilate(block, kernel, borderType=cv2.BORDER_REPLICATE)
    return low, high


def _neighbour_max(block: "np.ndarray") -> "np.ndarray":
    """8 邻域（不含中心）最亮值——Parker 负梯度的基准。"""
    import cv2
    import numpy as np

    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    return cv2.dilate(block, kernel, borderType=cv2.BORDER_REPLICATE)


def _masked_mean_std(block: "np.ndarray", mask: "np.ndarray", window: int):
    """窗口内**只统计 mask=True 的像素**的 ``(均值, 标准差, 权重像素数)``。

    第三个返回值是窗口内 mask 为真的像素个数：为 0 表示「这一窗里没有笔画
    边缘」，调用方据此判为纯纸面（Su 就是这样排除平坦区误判的）。此时均值/
    标准差退化为普通局部统计，只为避免除零，不再当成阈值用。
    """
    import cv2
    import numpy as np

    values = block.astype(np.float32)
    weight = mask.astype(np.float32)
    size = (window, window)
    count = cv2.boxFilter(
        weight, cv2.CV_32F, size,
        normalize=False, borderType=cv2.BORDER_REPLICATE,
    )
    total = cv2.boxFilter(
        values * weight, cv2.CV_32F, size,
        normalize=False, borderType=cv2.BORDER_REPLICATE,
    )
    total_sq = cv2.boxFilter(
        values * values * weight, cv2.CV_32F, size,
        normalize=False, borderType=cv2.BORDER_REPLICATE,
    )
    safe = np.maximum(count, 1.0)
    mean = total / safe
    variance = np.maximum(total_sq / safe - mean * mean, 0.0)
    std = np.sqrt(variance)
    empty = count < 0.5
    if bool(empty.any()):
        fallback_mean, fallback_std = _local_mean_std(block, window)
        mean = np.where(empty, fallback_mean, mean)
        std = np.where(empty, fallback_std, std)
    return mean, std, count


def _background_surface(block: "np.ndarray", window: int) -> "np.ndarray":
    """形态学闭运算 + 3×3 模糊：简化的背景亮度面（Gatos / Su 共用）。"""
    import cv2
    import numpy as np

    kernel = np.ones((window, window), np.uint8)
    closed = cv2.morphologyEx(
        block, cv2.MORPH_CLOSE, kernel, borderType=cv2.BORDER_REPLICATE
    )
    return cv2.GaussianBlur(
        closed, (3, 3), 0, borderType=cv2.BORDER_REPLICATE
    )


def _drop_small_components(mask: "np.ndarray", min_area: int) -> "np.ndarray":
    """去掉面积小于 ``min_area`` 的连通块（纸纹在阈值图上留下的孤立小点）。

    这是「原法后处理」的替身：Parker 的像素聚合、Howe 的图割连续性项都在干
    同一件事——把不合群的单像素判据连成整块或干脆丢掉。只在整页掩码上做一次，
    与分块无关。
    """
    import cv2
    import numpy as np

    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    if count <= 1:
        return np.zeros(mask.shape, dtype=bool)
    keep = np.zeros(count, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= max(1, int(min_area))
    return keep[labels]


def _fill_dark_holes(mask: "np.ndarray", gray: "np.ndarray", dark_limit: float):
    """回填「不与纸面连通、且本身够暗」的空洞——治「空心描边字」。

    按「比邻域更暗」定阈值的算法（Parker 的负梯度、Howe 的拉普拉斯符号）只把
    **笔画边缘**判成文字；笔画内部因为「邻域一样暗」被判成背景，于是字变成
    空心。原法靠区域生长/图割把内部连回去，这里用一条更便宜的等价判据：

    * 与页面边界连通的区域是纸面 ⇒ 不填；
    * 被文字包住、但平均灰度低于整页墨色门限 ⇒ 是笔画内部 ⇒ 填；
    * 被文字包住、但够亮的（口/日/田的字腔）⇒ 保留空白。

    ``dark_limit`` 由 :func:`_global_dark_limit` 给（整页非白像素的 Otsu）。
    """
    import cv2
    import numpy as np

    inverse = (~mask).astype(np.uint8)
    count, labels, _stats, _ = cv2.connectedComponentsWithStats(
        inverse, connectivity=4
    )
    if count <= 1:
        return mask
    flat = labels.ravel()
    areas = np.bincount(flat, minlength=count).astype(np.float64)
    totals = np.bincount(
        flat,
        weights=gray.ravel().astype(np.float64),
        minlength=count,
    )
    fill = (totals / np.maximum(areas, 1.0)) < float(dark_limit)
    fill[0] = False  # 0 号标签是文字本身
    border = np.unique(
        np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1]))
    )
    fill[border] = False
    return mask | fill[labels]


def _global_dark_limit(gray: "np.ndarray") -> float:
    """整页「墨色门限」（非白像素的 Otsu）：判断空洞里是墨还是纸的标尺。"""
    import numpy as np

    from utils.image_utils import calculate_auto_threshold

    non_white = gray[gray < 250]
    if int(non_white.size) < 500:
        return 128.0
    return float(calculate_auto_threshold(non_white))


def _thumbnail(gray: "np.ndarray", max_edge: int = 600):
    """下采样副本 + 缩放比：整页统计（Otsu/均值）用它估一个标量，省内存。"""
    import cv2
    import numpy as np

    height, width = int(gray.shape[0]), int(gray.shape[1])
    longest = max(height, width, 1)
    scale = min(1.0, float(max_edge) / float(longest))
    if scale >= 0.999:
        return gray, 1.0
    size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return cv2.resize(gray, size, interpolation=cv2.INTER_AREA), scale


def _contrast_floor(gray: "np.ndarray", window: int) -> float:
    """整页「笔画边缘」的对比度门槛：对比度图（局部最大 − 最小）的 Otsu。

    Su / Parker / Howe 都需要一个「窗口内明暗差够不够大」的判据：够大才谈得上
    字与纸的落差，不够大就是一片纸面。用下采样副本估一个标量（整页共用），
    因此不影响分块等价性。
    """
    from utils.image_utils import calculate_auto_threshold

    thumb, scale = _thumbnail(gray)
    size = max(3, int(round(window * scale)) | 1)
    low, high = _local_min_max(thumb, size)
    contrast = (high.astype("int16") - low.astype("int16")).astype("uint8")
    return max(15.0, float(calculate_auto_threshold(contrast)))


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


# ---------------------------------------------------------------------------
# 扩展算法（2026-11-23 加入下拉框；2026-11-23 用户口径：名称不带「试验」后缀）
#
# 共同约定：
# * 一律是 ``LocalAlgorithm``，参数只用面板已有的 window / k，不新增控件；
# * 文献里的多阶段后处理按类 docstring 里写的范围简化，不承诺逐位复现论文；
# * 需要在整页层面估标量的（Gatos 的 τ、Su/Parker/Howe 的对比度门槛与墨色
#   门限），都在 ``_prepare`` 里用下采样副本算，因此**不影响分块等价性**
#   （每块拿到的是同一组标量）；
# * 判据不是「灰度 < 阈值」的（Parker / Su / Howe）改写 ``_block_mask``，
#   需要整页连通域清理的改写 ``_postprocess``。
# ---------------------------------------------------------------------------


class NickAlgorithm(LocalAlgorithm):
    """NICK（Khurshid 等 2009）：``T = mean + k·sqrt(E[I²] − mean²)``，k 取负。

    ⚠️ ``sqrt(E[I²] − mean²)`` 就是局部标准差，所以窗口与 k 相同时 NICK 与
    :class:`NiblackAlgorithm` **逐像素等价**（NICK 本质是「k 固定为 −0.2 的
    Niblack」）。保留独立 key 只为与文献/其它工具的输出对照，并不是多一种效果。
    """

    key = "nick"

    def _block_threshold(self, block, window, offset, k, context):
        mean, std = _local_mean_std(block, window)
        return _to_u8(mean - abs(k) * std + offset)


class FengAlgorithm(LocalAlgorithm):
    """Feng（Niblack 改良）：引入局部对比度与局部最小值。

    ``T = (1−α1)·m + α2·(s/Rs)·(m − M) + α3·M``，``M`` = 局部最小，
    ``α2 = k1·(s/Rs)²``、``α3 = k2·(s/Rs)²``；文献取 α1≈0.15、k1≈0.2、k2≈0.03。
    ``k`` 映射为 k1，k2 = 0.15·k1。
    **简化**：Rs 用固定动态范围 128（论文在更大的窗口里估 Rs）。
    """

    key = "feng"

    def _block_threshold(self, block, window, offset, k, context):
        mean, std = _local_mean_std(block, window)
        low, _high = _local_min_max(block, window)
        ratio = std / _DYNAMIC_RANGE
        k1 = abs(float(k))
        k2 = 0.15 * k1
        darkest = low.astype("float32")
        threshold = (
            (1.0 - 0.15) * mean
            + (k1 * ratio * ratio) * (mean - darkest)
            + (k2 * ratio * ratio) * darkest
        )
        return _to_u8(threshold + offset)


class ParkerAlgorithm(LocalAlgorithm):
    """Contrast / Parker 对比度阈值（Parker 1991 的局部规则，直接产出掩码）。

    原法：``D = I − max(8 邻域)``（负梯度），对 ``D`` 取局部均值 ``M``、标准差
    ``S``，``D`` 明显低于 ``M`` 的像素判为文字边缘。这里照判据做：
    ``edge = D < M(D) − k·S(D)``（``k`` 是面板灵敏度）。

    ⚠️ 两个坑都是实测踩出来的，别再改回去：

    1. **不能映射回「灰度 < 阈值」**：把判据改写成 ``T = max8 + M + k·S`` 后，
       纸面上 ``D = 0`` 的像素（占多数）会被算成 ``0 < M + k·S``，阈值正好压在
       纸面灰度上 ⇒ 干净合成纸上纸面误判 51%、真实页沿界栏一圈碎噪点。必须在
       D 空间判，``D = 0`` 天然不满足。
    2. **要回填笔画内部**：判据只看边缘，笔画内部「邻域一样暗」⇒ 出来是空心
       描边。原法靠区域生长/像素聚合填补，这里用整页级的
       :meth:`_clean_mask`（去孤立噪点 + 回填暗洞）顶上。

    **平坦区**：窗口里几乎没有明暗差时（对比度 < 整页对比度门槛），「比邻域
    更暗」不成立，退化成 Bernsen 式中值判定（偏黑整窗判墨、偏白整窗判纸）。
    """

    key = "parker"

    def _block_halo(self, window):
        # 阈值里叠了 8 邻域梯度图 ⇒ 比窗口再多 1 行原始像素才不出现接缝。
        return 1

    def _prepare(self, gray, window, k):
        # 整页只估两个标量：对比度门槛（判「窗里有没有字痕」）与墨色门限
        # （收尾回填暗洞用）。每块拿到的是同一对值 ⇒ 分块结果与整页一致。
        return {
            "min_contrast": _contrast_floor(gray, window),
            "dark": _global_dark_limit(gray),
        }

    def _block_mask(self, block, window, offset, k, context):
        import numpy as np

        context = context if isinstance(context, dict) else {}
        min_contrast = float(context.get("min_contrast", 15.0))
        # 原法判据直接在 D 空间做：``D = I − max(8 邻域)``、``D < M(D) + k·S(D)``。
        # ⚠️ 必须在 D 空间判，不能改写回「灰度 < T」：D=0（不比任何邻居暗）的
        #    像素在纸面上占多数，映射回灰度后阈值正好压在纸面灰度上，干净合成
        #    纸上会有一半纸面/一圈纸纹被判成字（实测纸面误判 51%）。
        brightest = _neighbour_max(block)
        gradient = block.astype("float32") - brightest.astype("float32")
        mean, std = _local_mean_std(gradient, window)
        edge = gradient < (mean - abs(float(k)) * std)
        # 平坦区（窗口内几乎没有明暗差）没有「比邻居更暗」可言，退化成 Bernsen
        # 式中值判定：局部中值偏黑 ⇒ 整窗判墨，偏白 ⇒ 整窗判纸。
        low, high = _local_min_max(block, window)
        contrast = high.astype("int16") - low.astype("int16")
        middle = (low.astype("int16") + high.astype("int16")) // 2
        return np.where(contrast >= min_contrast, edge, middle < 128)

    def _postprocess(self, mask, gray, window, k, context):
        limit = context.get("dark") if isinstance(context, dict) else None
        return self._clean_mask(mask, gray, window, limit)


class GatosAlgorithm(LocalAlgorithm):
    """Gatos（简化）：局部背景估计 + 差值阈值。

    原法是多阶段（Wiener 预处理 → Sauvola 粗分割 → 背景插值 → 差值阈值 →
    形态学后处理）。这里保留核心一步：背景 ``B`` 用闭运算 + 3×3 模糊估计，
    ``T = B − τ``，``τ`` 取「粗分割为文字处 ``B − I`` 的均值」——整页只估一次
    （下采样副本），因此每块用同一个 τ。
    **省略**：Wiener 滤波、双线性背景插值、上采样与后处理。
    """

    key = "gatos"

    def _block_halo(self, window):
        # 背景面 = 闭运算（膨胀+腐蚀，各 window//2）+ 3×3 模糊（1 行）：
        # 块边界的 BORDER_REPLICATE 会沿两级形态学向内传播 window//2 + 1 行，
        # 余量不够会在块缝处留下阈值接缝（自测 rembg_algorithms 的分块等价项钉住）。
        return window // 2 + 2

    def _prepare(self, gray, window, k):
        import numpy as np

        thumb, scale = _thumbnail(gray)
        size = max(3, int(round(window * scale)) | 1)
        background = _background_surface(thumb, size).astype(np.float32)
        diff = background - thumb.astype(np.float32)
        ink = diff > 10.0
        if int(np.count_nonzero(ink)) < 100:
            return 25.0
        depth = float(np.mean(diff[ink]))
        return min(max(depth, 5.0), 120.0)

    def _block_threshold(self, block, window, offset, k, context):
        background = _background_surface(block, window)
        tau = float(context if context is not None else 25.0)
        return _to_u8(background.astype("float32") - tau + offset)


class SuAlgorithm(LocalAlgorithm):
    """Su（简化）：笔画边缘 + 边缘邻域均值/标准差定阈值。

    原法：背景估计 → 局部最大/最小算对比度 → 对对比度做 Otsu 取「笔画边缘」
    像素 → 以边缘邻域的统计量定阈值。这里保留这条主线，两处简化：

    * 边缘检测用**小窗口**（``window / 5``，见 :func:`_su_edge_window`）：边缘
      本就是窄带，用整窗去算局部极值会把笔画两侧各半个窗口都算成「边缘」，带
      里纸面占多数 ⇒ 阈值被抬到纸面灰度附近，沿每根笔画留一圈碎噪点（纸面
      误判 29% → 2%）；
    * 边缘对比度门槛 ``τc`` 与阈值都用整页标量/``k``：``T = m_edge − k·σ_edge``。

    ⚠️ 早期写成 ``(m + σ)/2``：边缘像素里混着大量纸面过渡点，均值偏高，双双
    取半会把阈值压到纸上一点点 ⇒ 只剩最黑的笔芯、笔画断裂（真实页面实测墨量
    8%，正常应在 20% 上下）。
    **简化**：窗口不随笔画宽度自适应，省略背景补偿。
    """

    key = "su"

    def _block_halo(self, window):
        return 2

    def _prepare(self, gray, window, k):
        edge_window = _su_edge_window(window)
        return {
            "edge_window": edge_window,
            "contrast": _contrast_floor(gray, edge_window),
        }

    def _block_mask(self, block, window, offset, k, context):
        # 掩码型：窗口里**没有**笔画边缘像素 ⇒ 纯纸面，直接判背景。走阈值图
        # 那条路会退化成普通局部均值/标准差，把平坦纸面判出一片字（实测纸面
        # 误判 ~24%）。
        context = context if isinstance(context, dict) else {}
        edge_window = int(context.get("edge_window", _su_edge_window(window)))
        floor = float(context.get("contrast", 15.0))
        low, high = _local_min_max(block, edge_window)
        contrast = high.astype("int16") - low.astype("int16")
        stroke = contrast >= floor
        mean, std, weight = _masked_mean_std(block, stroke, window)
        threshold = mean - abs(float(k)) * std + offset
        return (block < threshold) & (weight > 0.5)

    def _postprocess(self, mask, gray, window, k, context):
        # 「笔画边缘」是一圈**带**（窗口统计量，笔画两侧各半个窗口都算），带里
        # 纸面占比高 ⇒ 阈值被抬到纸面附近，沿笔画留下细碎噪点。这些噪点都是
        # 孤立小连通块，用统一收尾清掉即可（不动笔画本体）。
        return self._clean_mask(mask, gray, window)


class HoweAlgorithm(LocalAlgorithm):
    """Howe（简化）：拉普拉斯谷底判据 + 对比度/亮度门限。

    原法把「标签与拉普拉斯符号一致」和「不连续性只贴在 Canny 边缘」写成一个
    能量函数，用图割求全局最优。这里保留单点项并补两条门限：

    * ``∇²I > 0``：灰度谷底（墨迹比周围暗）；
    * 局部对比度 ≥ ``τc``（对比度图的整页 Otsu）：压掉平坦纸面；
    * ``I < 局部均值 − k·σ``：只在「确实更暗」的地方落墨。

    **简化**：省略图割连续性项与 Canny 边缘项，改用整页级的
    :meth:`_clean_mask`（去孤立噪点 + 回填暗洞）。只留 ``∇²I > 0`` 一条判据时
    实测整页 44% 变黑、完全不可读——这就是原法非有图割不可的原因。
    """

    key = "howe"

    def _block_halo(self, window):
        # 拉普拉斯 3×3（1 行）+ 局部最大/最小窗口（窗口已计入）的余量。
        return 2

    def _prepare(self, gray, window, k):
        return {
            "min_contrast": _contrast_floor(gray, window),
            "dark": _global_dark_limit(gray),
        }

    def _block_mask(self, block, window, offset, k, context):
        import cv2
        import numpy as np

        context = context if isinstance(context, dict) else {}
        min_contrast = float(context.get("min_contrast", 15.0))
        laplacian = cv2.Laplacian(
            block.astype(np.float32), cv2.CV_32F,
            ksize=3, borderType=cv2.BORDER_REPLICATE,
        )
        low, high = _local_min_max(block, window)
        contrast = high.astype(np.int16) - low.astype(np.int16)
        mean, std = _local_mean_std(block, window)
        darker = block.astype(np.float32) < mean - abs(float(k)) * std
        return (laplacian > 0) & (contrast >= min_contrast) & darker

    def _postprocess(self, mask, gray, window, k, context):
        limit = context.get("dark") if isinstance(context, dict) else None
        return self._clean_mask(mask, gray, window, limit)


#: key → 实现实例（注册表；加算法只需在这里加一行）。
_ALGORITHM_INSTANCES: dict[str, RembgAlgorithm] = {
    algo.key: algo
    for algo in (
        OtsuAlgorithm(),
        NiblackAlgorithm(),
        SauvolaAlgorithm(),
        BernsenAlgorithm(),
        WolfJolionAlgorithm(),
        NickAlgorithm(),
        FengAlgorithm(),
        ParkerAlgorithm(),
        GatosAlgorithm(),
        SuAlgorithm(),
        HoweAlgorithm(),
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
    "ALGORITHM_CATEGORIES",
    "ALGORITHM_KEYS",
    "ALGORITHMS",
    "AlgorithmInfo",
    "BernsenAlgorithm",
    "EXPERIMENTAL_ALGORITHM_KEYS",
    "FengAlgorithm",
    "GatosAlgorithm",
    "HoweAlgorithm",
    "LOCAL_ALGORITHM_KEYS",
    "LocalAlgorithm",
    "NiblackAlgorithm",
    "NickAlgorithm",
    "OtsuAlgorithm",
    "ParkerAlgorithm",
    "REMBG_DEFAULT_ALGORITHM",
    "REMBG_DEFAULT_K",
    "REMBG_DEFAULT_WINDOW",
    "RembgAlgorithm",
    "SauvolaAlgorithm",
    "SuAlgorithm",
    "WolfJolionAlgorithm",
    "algorithm_groups",
    "clamp_global_threshold",
    "get_algorithm",
    "recommended_params",
    "text_mask",
]
