# -*- coding: utf-8 -*-
"""源图的路径比较键与形态判定（左/右半幅、整幅、无侧半幅）。

从 ``desktop/services/imposition.py`` 拆出（2026-11-22）。判据唯一处仍是
文件名后缀（提交计划的 role 见 ``auto.source_kind``）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from desktop.services.imposition.constants import (
    SOURCE_FULL, SOURCE_LEFT, SOURCE_RIGHT,
)


def classify_source(path) -> str:
    """源图形态：左半幅 / 右半幅 / 整幅（**判据唯一处：文件名后缀**）。

    自动拼版只能靠文件名认图——拼版侧读不到检测框，而第三步的落盘口径是
    半幅页 ``<页号>-l`` / ``<页号>-r``、整幅页 ``<页号>``（见
    ``desktop.services.print_plan.plan_detect_submit_entries``）。

    ⚠️ 单栏书 / 窄页会把半幅的侧别归一化掉（产物仍叫 ``<页号>``），此时
    文件名与整幅**无法区分**。那种页的形态必须由任务提交计划给出，见
    :func:`source_kind`。
    """
    match = re.search(r"[_-]([lr])$", Path(str(path)).stem.lower())
    if match:
        return SOURCE_LEFT if match.group(1) == "l" else SOURCE_RIGHT
    return SOURCE_FULL


def _role_page_key(label: str):
    """产物 label → **同页归并键**：能解析出页号就用页号，否则用名字本身。"""
    number = source_page_number(label)
    return number if number is not None else str(label)

def source_page_number(path) -> int | None:
    """源图**页号**：文件名开头的连续数字（``3-r`` → 3、``004-l`` → 4）。

    「不连续的图片不可以合并在一页」的判据。文件名不带数字前缀的图
    （如 ``cover``）返回 None——永不参与配对，只能单独成页。
    """
    match = re.match(r"(\d+)", Path(str(path)).stem)
    return int(match.group(1)) if match else None

def same_path(left, right) -> bool:
    """两个路径串是否指同一处文件（**形态无关**）。

    文档里存的是路径**原样字符串**，而"编辑器刚覆盖的那个文件"往往是从
    ``Path(...)`` 取出来的——Windows 上 ``Path`` 会把 ``/`` 翻成 ``\\``，
    大小写也可能有差异。拿字符串直接 ``==`` 比会**静默落空**（用户
    2026-10-08 报的"预览弹窗里编辑完，拼版页还是老图"就是这个）。
    比较前一律 ``normpath`` + ``normcase``；空串永远不相等（``Path("")``
    会退化成 ``"."``，那是"还没选文件"，不是同一处）。
    """
    if not left or not right:
        return False
    return _path_key(left) == _path_key(right)

def _path_key(value) -> str:
    """路径的比较键：展开 ``~`` → 绝对化 → 统一分隔符 → 统一大小写。

    ⚠️ 只在"比较"里用，**不要**拿它当落盘值——落盘仍写原路径。
    """
    return os.path.normcase(
        os.path.normpath(os.path.abspath(os.path.expanduser(str(value))))
    )
