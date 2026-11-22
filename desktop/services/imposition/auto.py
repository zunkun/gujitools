# -*- coding: utf-8 -*-
"""自动拼版：按提交计划/文件名把源图两两配成页。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）。配对规则
（左侧别 + 页号连续 + 整幅单独成页）的唯一实现在 ``auto_impose_pages``。
"""

from __future__ import annotations

from desktop.services.imposition.constants import (
    ROLE_SOURCES,
    SOURCE_FULL,
    SOURCE_HALF_UNSIDED,
    SOURCE_LEFT,
    SOURCE_RIGHT,
)
from desktop.services.imposition.layout import make_page, make_single_page
from desktop.services.imposition.sources import (
    _role_page_key, classify_source, source_page_number,
)


def expand_role_aliases(roles: dict[str, str]) -> dict[str, str]:
    """角色表补上**同一页的各种文件名写法**（按页号归并）。

    背景（用户 2026-10-23，任务 0004）：提交计划按**产物 label** 记录身份，
    而拼版拿到的是下游产物文件名。正常链路名字一路不变（detect 提交 →
    去底色到拼版都沿用 stem），但跨版本/人工改侧别会让两边的写法不一致：

    - 计划已归一化成无后缀 ``1100``，旧产物还叫 ``1100-l.png``；
    - 用户把某页指定成左半幅后计划叫 ``1100-l``，旧产物还叫 ``1100.png``。

    ⚠️ 归并规则：**该页只有一个 role** 时，``<页号>`` / ``-l`` / ``-r`` /
    ``_l`` / ``_r`` 全部认这个 role；该页有**多个** role（真双栏页的左右两张）
    时**不造别名**，只认精确 label——否则会把左右两张都认成同一边。

    ⚠️ 已存在的精确 label 永远优先，不会被别名覆盖。
    """
    by_page: dict[object, set[str]] = {}
    for label, role in roles.items():
        by_page.setdefault(_role_page_key(label), set()).add(str(role))
    expanded = dict(roles)
    for label, role in roles.items():
        key = _role_page_key(label)
        if not key or len(by_page.get(key) or ()) != 1:
            continue  # 同页有多种角色（真双栏）→ 只能按精确 label 认
        for suffix in ("", "-l", "-r", "_l", "_r"):
            expanded.setdefault(f"{key}{suffix}", role)
    return expanded


def source_kind(path, role_for=None) -> str:
    """源图形态：优先用提交计划的 ``role``，缺失时回落到文件名后缀。

    判定顺序（**唯一口径**，用户 2026-10-23 确认）：

    1. **提交计划**（``boxes.json`` 的 ``plan.outputs``，按产物 label 一一对应）
       ——``role`` 直接给出 ``full / half-left / half-right / half-unsided``；
       旧产物名 ``<页号>-l/-r`` 也能通过别名认到该页的无后缀角色；
    2. **文件名后缀** ``-l`` / ``-r``（该图在计划里查不到时才用）；
    3. 都没有 → **整幅**（单独一页，不与任何图配对）。

    ⚠️ 第 1 层的前提是**流程里能沿连线找到喂给拼版的检测节点**（不是随便找
    一份 ``boxes.json``）；找不到（无检测步骤 / 旧任务没有计划 / 独立拼图页
    没有任务存储）就整体降级到 2~3——即"整批输入都按文件名判"，**不做**
    整本书形态推断：没有逐页证据时，猜出来的单栏/双栏只会把图错配。

    ``role_for`` 是 ``(路径文本) -> role | None``：任务详情页从
    ``boxes.json`` 的提交计划建映射（见 ``expand_role_aliases``）。
    """
    if role_for is not None:
        role = role_for(str(path))
        kind = ROLE_SOURCES.get(role) if role else None
        if kind is not None:
            return kind
    return classify_source(path)

def auto_impose_pages(files: list, role_for=None) -> list[dict]:
    """自动拼版（用户 2026-09-30 规则，**唯一实现**）：

    1. **默认两张半栏拼一页**：配对必须是「前一个左半幅 + 当前右半幅」
       （序号在前的进右槽，与手动配对口径一致）。例：``3-r, 3-l, 4-r,
       4-l, 5-r`` 从 ``3-l`` 起 → ``(3-l, 4-r)、(4-l, 5-r)``；从 ``3-r``
       起 → ``[3-r]、(3-l, 4-r)、(4-l, 5-r)``（首位右半幅前面没有左半幅，
       单独一页）；
    2. **页号必须连续**：不连续的图片不可以合并在一页——``3-l`` 之后隔着
       已用掉的 4 直接来 ``5-r``，则 ``3-l`` 单独一页、``5-r`` 重新开始；
       文件名无数字前缀的图永不配对；
    3. **整幅(fullcontent)标注的图单独一页**，不与任何图配对；等配对的
       上一张因此落单、也单独一页；整幅之后拼版重新开始；末尾落单的
       左半幅同样单独一页。
    4. **无侧半幅（``half-unsided``）同样可以两两配对**（用户 2026-10-23）：
       单栏书 / 窄页的产物名没有 ``-l``/``-r``，但提交计划把它记成半幅。
       两张连续的 ``half-unsided`` 拼一页，序号在前的同样进右槽；它**不与**
       带侧别的半幅混拼（``role_for`` 缺失时按文件名，即退回旧行为）。

    ``role_for``：``(路径文本) -> role | None``，任务详情页用它把
    ``boxes.json`` 提交计划里的角色喂进来；``None`` = 只看文件名后缀。

    遍历按源清单顺序（``natural_sort_key``：同页号 r 在前），产出的
    页清单顺序即 PDF 页序。尺寸读不到的图跳过（不产出残页）。
    """
    pages: list[dict] = []
    pending: str | None = None   # 等待配对的上一张（右槽候选）
    pending_no: int | None = None  # pending 的页号（连续性判据）
    pending_kind: str | None = None  # pending 的形态（配对必须同形态）
    for raw in files:
        file = str(raw)
        kind = source_kind(file, role_for)
        no = source_page_number(file)
        if kind == SOURCE_FULL:
            if pending is not None:
                page = make_single_page(pending)
                if page is not None:
                    pages.append(page)
                pending = None
                pending_no = None
                pending_kind = None
            page = make_single_page(file)
            if page is not None:
                pages.append(page)
            continue
        paired = (
            pending is not None
            and pending_no is not None
            and no == pending_no + 1
            and (
                (pending_kind == SOURCE_LEFT and kind == SOURCE_RIGHT)
                or (pending_kind == SOURCE_HALF_UNSIDED
                    and kind == SOURCE_HALF_UNSIDED)
            )
        )
        if paired:
            page = make_page([pending, file])
            if page is not None:
                pages.append(page)
            pending = None
            pending_no = None
            pending_kind = None
            continue
        if pending is not None:
            page = make_single_page(pending)
            if page is not None:
                pages.append(page)
        pending = file
        pending_no = no
        pending_kind = kind
    if pending is not None:
        page = make_single_page(pending)
        if page is not None:
            pages.append(page)
    return pages

