# -*- coding: utf-8 -*-
"""**全书级**页形态判定：单栏书 / 整幅书，以及整幅书里的可疑半幅页。

⚠️ 本模块与 :mod:`utils.box_geometry` 的分工必须分清，否则必然出现两份真相：

- ``box_geometry`` 管的是**单页**槽位形态（半幅恒 2 槽 / 整幅恒 1 槽），
  以及左右分栏、border、画布几何——它**不看页宽**，也不看别的页；
- 本模块管的是**跨页**的整体判定：一个「单宽框」的框到底该按左半幅还是
  按整幅理解，取决于**整本书**长什么样，而不是这一页本身。

**为什么需要它（用户 2026-10-17）**：模型把「一栏横跨整页」的单栏书也判成
``harfcontent``。这类书从头到尾只有一栏，永远不会出现一页里并排左页+右页，
于是按单页判据产出的 ``7-l.png`` 是**假身份**——第四步拼版会把它当左半幅去找
``8-r`` 配对，找不到就整页落单；PDF 侧还会拿 ``-l/-r`` 后缀推算奇偶页。于是
「一个文本框 = 一个页」这件事在文件名上彻底丢了。

**两个极端是对称的**：

1. **单栏书**：几乎所有有框页都是「单个、且框宽 ≥ 60% 页宽」的半幅框 ⇒
   整本书按**单栏**理解，这些页不再拆 ``-l``/``-r``，直接按页码命名（``7.png``）；
2. **整幅书**：几乎所有有框页都是整幅 ⇒ 这时**不该**出现半幅框，真出现就是
   可疑结果（多半是模型把整幅误判成半幅），必须让用户看见——但**不自动改**
   （用户 2026-10-17 明确选择「只警告」：悄悄改会把本来对的框改坏）。

纯规则、无 Qt / 无 cv2 / 无模型，供 GUI 主进程与 worker 共用。
"""

from __future__ import annotations

from typing import Iterable, NamedTuple, Sequence

from utils.box_geometry import (
    PAGE_CLASS_EMPTY,
    PAGE_CLASS_FULLCONTENT,
    PAGE_CLASS_HARFCONTENT,
    PAGE_CLASS_SINGLE,
    classify_page_slots,
)

#: 「单宽框」的宽度下限：框宽 ≥ 页宽 × 该比例才算一栏横跨整页。
#:
#: **为什么是 0.60（用户 2026-10-23 报 0012 半幅规则没生效）**：
#:
#: - **几何**：真双栏书里左右两栏并排，每栏必然 **< 50% 页宽**（两栏相加
#:   不超一页）。所以一个 > 50% 的框**不可能**有并排的另一半——它只能是一整栏。
#: - **实测**（本机 9 个任务）：真双栏书（一图并排两页）的框宽 0.41~0.489；
#:   单页扫描 / 单栏书的框宽 0.63~0.93（任务 0012 实测 0.70~0.78）。
#:   0.50~0.63 是一段明显的空档，取 0.60 两边都留了余量。
#:
#: ⚠️ 旧值 0.80 是拍出来的：0012（单页扫描、框宽 70~78%）整本被判不出单栏书，
#:    于是每页都按中心位置拆成左框/右框——可这类单页扫描的文本块位置随装订
#:    方向左右偏，中心位置**没有鉴别力**，拆出来的左右基本是错的。用户要的
#:    正是把它标成「半幅」（仍是 harfcontent，页面上归为半幅）。
#:
#: ⚠️ 与 yolo_utils 里那个"窄整幅算失败检测"的 0.70 阈值是**两回事**，别混：
#:    那个是**单页消解**规则，作用对象是整幅框；这里是**全书统计**规则，
#:    作用对象是半幅框。
#:    ⚠️ 全仓唯一性守卫（``tests/selftests/content_classes.py`` 第 7 节）按
#:    **标识符文本**扫描，禁止别处再抄那个常量名——所以这里刻意不写出它，
#:    以免被守卫误判成"重复定义"。要查那个阈值请直接看 yolo_utils。
SINGLE_COLUMN_WIDTH_RATIO = 0.60

#: 认定为「单栏书」所需的比例：≥ 该比例的**有框页**都是单宽框。
#:
#: 分母是**有框页**而不是总页数——封面、空白页、书口本来就常常无框（用户
#: 2026-10-17：「harfcontent + no content」），把它们算进分母会让判据在正常
#: 书上也可能成立。留 10% 余量容忍个别漏检页。
SINGLE_COLUMN_BOOK_RATIO = 0.90

#: 认定为「整幅书」所需的比例：≥ 该比例的**有框页**都是整幅。
FULL_BOOK_RATIO = 0.90

#: 认定为「左右双栏书」所需的比例：≥ 该比例的**有框页**都是半幅双框。
#:
#: 用户 2026-10-23 定的「一、整本书整体是 left/right 双栏结构」就是这一类
#: （每页左右两栏并排）。空白页要按「补左右两张占位」处理，见
#: ``desktop.services.print_plan.plan_detect_submit_entries``。
DOUBLE_COLUMN_BOOK_RATIO = 0.90

#: 全书形态键（:func:`book_form` 的返回值）：决定空白页补几张占位。
BOOK_FORM_DOUBLE = "double"   # 左右双栏书：每页两框（缺一侧要补另一侧）
BOOK_FORM_SINGLE = "single"   # 单栏书（半幅单宽框）：每页一框
BOOK_FORM_FULL = "full"       # 整幅书：每页一框
BOOK_FORM_MIXED = "mixed"     # 混排：空白页跟随前一页的形态


def is_single_wide_box(box, page_width) -> bool:
    """**单个框**是否宽到不可能与另一栏并排（单栏书那一栏的宽度特征）。

    只看几何，不看槽位——供**标注层**用它把「半幅单框」标成「半幅」而不是
    「左框/右框」（见 ``desktop.components.viewers.image_view.styles``）。
    槽位级判据见 :func:`is_single_wide_half`，两者共用同一个宽度阈值。

    页宽未知（``None``/0/非数）或框畸形时返回 ``False``：没证据不下结论。
    """
    if not box:
        return False
    try:
        width = float(page_width)
    except (TypeError, ValueError):
        return False
    if width <= 0:
        return False
    try:
        box_width = float(box[2]) - float(box[0])
    except (TypeError, ValueError, IndexError):
        return False
    return box_width / width >= SINGLE_COLUMN_WIDTH_RATIO


def is_single_wide_half(slots: Sequence, page_width) -> bool:
    """本页是否「单个半幅框、且宽到横跨整页」——单栏书的典型页。

    三个条件都要满足，缺一不可：

    1. **槽位是 2 槽**（半幅形态，见 ``box_geometry`` 槽位约定）：整幅页恒
       1 槽，本来就按整幅处理，不该被这里改写；``[框]`` 这种 1 槽的半幅退化
       形态也不认——那已经是整幅语义了，再判一次是重复。
    2. **恰好一个框**（另一侧为 ``None``）：双框是真双栏书，一页里确实有左页
       和右页，拆 ``-l``/``-r`` 是对的。
    3. **框宽 ≥ 60% 页宽**：这是"其实是一整栏"的唯一硬证据（> 50% 就不可能
       与另一栏并排，见 :data:`SINGLE_COLUMN_WIDTH_RATIO`）。缺页宽（``None``
       / 0）时判 ``False``——宁可漏判成普通半幅，也不要在没证据时改写身份。

    ⚠️ 宽度按 ``x2 - x1`` 算，不看中心位置：单栏书的框可能略偏左/偏右
    （装订线、天头地脚不对称），但它横跨整页。
    """
    raw = list(slots or [])
    if len(raw) != 2:
        return False
    present = [b for b in raw if b]
    if len(present) != 1:
        return False
    return is_single_wide_box(present[0], page_width)


def single_column_slots(slots: Sequence, single_column_book: bool, page_width) -> list:
    """单栏书里把「单个宽框」的半幅槽位**退化成单槽**；其余原样返回。

    ⚠️ **这是"单栏书改写身份"的唯一实现**。第三步预览（``rembg_viewer``）与
    提交派生（``print_plan``）都必须调它——两处各写一遍的话，预览会显示
    ``0007-l``、成品却是 ``0007.png``，用户改参数重提交时无从判断哪边是对的。

    退化后为什么就够了：``box_geometry.is_full_content`` 靠**槽数**判整幅
    （1 槽＝整幅），于是下游三条语义**自动**一起变对——不拆 ``-l``/``-r``、
    不做对称镜像、拼版不会按后缀把它当左半幅去配对。绝不要只改文件名。

    参数:
        slots: 槽位表示（半幅恒 2 槽、整幅 1 槽）。
        single_column_book: 整本书是否已判定为单栏书（``profile_book``）。
        page_width: 该页像素宽度；未知时传 ``None``/0（判据保守不改写）。

    返回:
        新列表；未命中时返回原槽位的浅拷贝。
    """
    raw = list(slots or [])
    if not single_column_book or len(raw) != 2:
        return raw
    if is_single_wide_half(raw, page_width):
        return [b for b in raw if b]
    return raw


def page_single_wide_slots(slots: Sequence, page_width) -> list:
    """**页级**判据：单个宽框（≥60% 页宽）的半幅页退化成单槽。

    用户 2026-10-23（任务 0004）：一页只检出一个 ``harfcontent``、框宽 >60%
    时，中心位置**没有鉴别力**——它必然是「半幅」，不能因为整本书不是单栏书
    就按中心硬拆 ``-l``/``-r``。所以这一步**不看** ``single_column_book``。

    与 :func:`single_column_slots` 的差别只有"不要求全书结论"；退化后的下游
    语义完全一致（不拆后缀、不镜像、可配对）。
    """
    return single_column_slots(slots, True, page_width)


#: 「窄页」判据：某页页宽 < **全书典型页宽** × 该比例 ⇒ 这页是**单页扫描**。
#:
#: 用户 2026-10-23：整本基本都是左右双栏（每张图并排两页），但封面/扉页/
#: 封底常是**单页扫描**——图片尺寸明显小于其它页。这类页理论上**放不下第二
#: 栏**，所以：
#:
#: - 整页无框时只补**一张**占位（不是左右两张）；
#: - 只检出一个框时**不补**缺失侧（另一栏不可能存在），命名也不带 ``-l``/``-r``。
#:
#: 0.70 与「整幅框最小宽度比例」同值但**不是同一件事**：那个比的是框宽/页宽，
#: 这个比的是**页宽/全书页宽**。真双栏书的页宽彼此相差不到 5%（任务 0001
#: 实测 2322~2400），单页扫描只有 ~58%（1390/2400），中间空档很大。
NARROW_PAGE_WIDTH_RATIO = 0.70


def typical_page_width(widths: Iterable) -> int:
    """全书**典型页宽**：全部已知页宽的**中位数**（无有效宽度返回 0）。

    用中位数而不是最大值：个别超宽折页不该把"正常页"全判成窄页。
    """
    values: list[int] = []
    for width in widths or []:
        try:
            value = int(width)
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    if not values:
        return 0
    values.sort()
    return values[len(values) // 2]


def is_narrow_page(page_width, typical_width) -> bool:
    """该页是否**明显窄于全书**（= 单页扫描，放不下第二栏）。"""
    try:
        width = int(page_width)
        typical = int(typical_width)
    except (TypeError, ValueError):
        return False
    if width <= 0 or typical <= 0:
        return False
    return width < typical * NARROW_PAGE_WIDTH_RATIO


def narrow_page_slots(slots: Sequence, narrow: bool) -> list:
    """窄页（单页扫描）里把「唯一的框」退化成**单槽**；其余原样返回。

    与 :func:`single_column_slots` 同一目的（让下游按整幅语义走、不拆
    ``-l``/``-r``、不补另一栏），区别只在判据来源：这里是**页宽明显小于
    全书**，与「框宽 ≥60% 页宽」无关（任务 0001 第 1 页的框只占 49% 页宽，
    但那一页本身就是单页扫描）。

    ⚠️ 只有「2 槽且恰好 1 个框」才退化；真双栏页（两个框）原样不动。
    """
    raw = list(slots or [])
    if not narrow or len(raw) != 2:
        return raw
    present = [b for b in raw if b]
    if len(present) != 1:
        return raw
    return present


class BookProfile(NamedTuple):
    """整本书的形态判定结果（一次性统计，各判据共用）。

    属性:
        total_pages: 参与统计的页数（含无框页）。
        boxed_pages: 检出了框的页数——所有比例的分母都是它，不是总页数。
        single_wide_pages: 「单宽框」页（见 :func:`is_single_wide_half`）。
        double_half_pages: 真双栏页（左右两个框都检出）。
        narrow_single_pages: 单个半幅框但**不够宽**的页——单栏书里的漏网
            之鱼（如某页正文只占 3/4 页宽），仍按半幅处理，不改写身份。
        full_pages: 整幅页。
        empty_pages: 无框页。
        single_column_book: 是否认定为**单栏书**（这些页不该拆 ``-l``/``-r``）。
        full_book: 是否认定为**整幅书**。
        double_column_book: 是否认定为**左右双栏书**（每页左右两框并排）。
        suspicious_half_pages: 整幅书里出现的半幅页（页名）——**可疑结果**，
            交由界面提示，不自动改。
        suspicious_half_ratio: 可疑半幅页占整幅书有框页的比例（0~1）。

    ⚠️ ``single_column_book`` / ``full_book`` / ``double_column_book`` 三者
    互斥（比例都 ≥90%，不可能同时成立）；三者都为 ``False`` 即**混排书**
    （一部分单栏页、一部分整幅页/双栏页）。
    """

    total_pages: int
    boxed_pages: int
    single_wide_pages: tuple
    double_half_pages: tuple
    narrow_single_pages: tuple
    full_pages: tuple
    empty_pages: tuple
    single_column_book: bool
    full_book: bool
    double_column_book: bool
    suspicious_half_pages: tuple
    suspicious_half_ratio: float

    @property
    def has_suspicious_half(self) -> bool:
        """是否有"整幅书里冒出半幅"的可疑结果需要提示。"""
        return bool(self.suspicious_half_pages)


def _page_name(item) -> str:
    """统计项 → 页名（兼容 ``(name, slots, width)`` 与 ``(name, slots)``）。"""
    return str(item[0])


def profile_book(pages: Iterable) -> BookProfile:
    """整本书的形态判定（**唯一入口**）。

    参数:
        pages: 逐页三元组 ``(页名, 槽位, 页宽)``；页宽未知时可给 ``None``/0
            （该页因此不会计入「单宽框」，见 :func:`is_single_wide_half`）。
            页宽只用于算比例，**不需要精确到像素**。

    返回:
        :class:`BookProfile`。

    ⚠️ 「整幅书 + 有半幅」**不改写任何数据**，只把页名记进
    ``suspicious_half_pages``——模型判成半幅的那些页仍按半幅走完流程，由用户
    看着提示去核对。这与单栏书那条相反：单栏书是**有充分证据**的形态改写
    （≥90% 有框页都是横跨整页的一栏），整幅书里的半幅则是**证据不足**的异常。
    """
    single_wide: list[str] = []
    double_half: list[str] = []
    narrow_single: list[str] = []
    full: list[str] = []
    empty: list[str] = []
    half_pages: list[str] = []
    total = 0

    for item in pages or []:
        name, slots = _page_name(item), list(item[1] or [])
        width = item[2] if len(item) > 2 else None
        total += 1
        kind = classify_page_slots(slots)
        if kind == PAGE_CLASS_EMPTY:
            empty.append(name)
            continue
        if kind == PAGE_CLASS_FULLCONTENT:
            full.append(name)
            continue
        # 半幅与单独页都属"半幅形态"：整本书的判定只看它是不是单宽框。
        half_pages.append(name)
        if kind == PAGE_CLASS_HARFCONTENT:
            double_half.append(name)
        elif is_single_wide_half(slots, width):
            single_wide.append(name)
        else:
            narrow_single.append(name)

    boxed = len(single_wide) + len(double_half) + len(narrow_single) + len(full)
    single_column_book = (
        boxed > 0 and len(single_wide) / boxed >= SINGLE_COLUMN_BOOK_RATIO
    )
    full_book = boxed > 0 and len(full) / boxed >= FULL_BOOK_RATIO
    double_column_book = (
        boxed > 0 and len(double_half) / boxed >= DOUBLE_COLUMN_BOOK_RATIO
    )

    # ⚠️ 单栏书里**不能**同时报"可疑半幅"：那些单宽框页本来就该是半幅形态
    #   （模型没错），它们已被 single_column_book 解释掉了。这里只把**真双栏**
    #   与**窄单框**页算作需要用户看一眼的异常。
    suspicious: tuple = ()
    ratio = 0.0
    if full_book:
        suspicious = tuple(double_half + narrow_single)
        ratio = len(suspicious) / len(full) if full else 0.0

    return BookProfile(
        total_pages=total,
        boxed_pages=boxed,
        single_wide_pages=tuple(single_wide),
        double_half_pages=tuple(double_half),
        narrow_single_pages=tuple(narrow_single),
        full_pages=tuple(full),
        empty_pages=tuple(empty),
        single_column_book=single_column_book,
        full_book=full_book,
        double_column_book=double_column_book,
        suspicious_half_pages=suspicious,
        suspicious_half_ratio=ratio,
    )


def book_form(profile: BookProfile) -> str:
    """整本书的形态键（``BOOK_FORM_*``），决定空白页补几张占位。

    三个极端互斥（各自要求 ≥90%），都不成立即**混排**——混排时空白页跟随
    前一张有框页的形态（用户 2026-10-23 的规则四）。

    优先级：单栏 → 整幅 → 双栏。单栏书里「单个宽框」已被判成单栏形态，
    不该再被双栏判据接管（两者比例互斥，这里只是写死一个确定的次序）。
    """
    if profile.single_column_book:
        return BOOK_FORM_SINGLE
    if profile.full_book:
        return BOOK_FORM_FULL
    if profile.double_column_book:
        return BOOK_FORM_DOUBLE
    return BOOK_FORM_MIXED


def single_column_summary(profile: BookProfile) -> str:
    """:class:`BookProfile` → 单栏书的一行人读结论（无框页不计入比例分母）。"""
    if not profile.single_column_book:
        return ""
    return (
        f"单栏书：有框的 {profile.boxed_pages} 页里 "
        f"{len(profile.single_wide_pages)} 页是单个宽框"
        f"（≥{int(SINGLE_COLUMN_WIDTH_RATIO * 100)}% 页宽），"
        f"已按单栏处理——文本框直接按页码命名，不再拆 -l/-r"
    )


def suspicious_summary(profile: BookProfile) -> str:
    """:class:`BookProfile` → 整幅书里冒出半幅的一行人读结论（无需提示时返回空串）。"""
    if not profile.has_suspicious_half:
        return ""
    names = "、".join(profile.suspicious_half_pages[:5])
    more = len(profile.suspicious_half_pages) - 5
    tail = f" 等 {len(profile.suspicious_half_pages)} 页" if more > 0 else ""
    return (
        f"⚠️ 可疑结果：这本基本是整幅书"
        f"（{len(profile.full_pages)}/{profile.boxed_pages} 页为整幅），"
        f"却有 {len(profile.suspicious_half_pages)} 页被判成半幅"
        f"（{names}{tail}）。半幅在整幅书里通常意味着误判，"
        f"请核对这几页——已按半幅原样处理，未自动改动。"
    )


__all__ = [
    "BOOK_FORM_DOUBLE",
    "BOOK_FORM_FULL",
    "BOOK_FORM_MIXED",
    "BOOK_FORM_SINGLE",
    "BookProfile",
    "DOUBLE_COLUMN_BOOK_RATIO",
    "FULL_BOOK_RATIO",
    "NARROW_PAGE_WIDTH_RATIO",
    "SINGLE_COLUMN_BOOK_RATIO",
    "SINGLE_COLUMN_WIDTH_RATIO",
    "book_form",
    "is_narrow_page",
    "is_single_wide_box",
    "is_single_wide_half",
    "narrow_page_slots",
    "profile_book",
    "single_column_slots",
    "single_column_summary",
    "suspicious_summary",
    "typical_page_width",
]
