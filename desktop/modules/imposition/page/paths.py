# -*- coding: utf-8 -*-
"""独立拼图页的目录落点与页面覆盖清单（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

from desktop.services.imposition import normalize_page

from .constants import EDITED_DIRNAME, UPLOAD_DIRNAME, _SPEC


def uploaded_page_dir() -> Path:
    """「上传图片」在独立拼图页里的复制落点（**缓存**，与任务流程的
    ``tasks/<任务号>/inserted/`` 对应）。

    ⚠️ 上传的图**必须复制一份**再进版面：源文件放在桌面/下载里，用户随手
    挪走或删掉，拼版就再也合不出来（导出时 ``_open_rgba`` 直接抛错）。复制
    进 singletask 缓存区意味着它会跟着"清空输入"一起被丢弃——那正是我们要的
    语义（这批图只属于这一次拼版）。
    """
    from desktop.utils.files import singletask_dir

    return singletask_dir(_SPEC.disk_key()) / UPLOAD_DIRNAME


def _chosen_items(dialog) -> list[dict]:
    """弹窗勾选结果 → ``[{"path": Path, "uploaded": bool}]``（替身兜底）。

    与任务流程 ``pages/taskdetail/imposition_pages.py::_chosen_items`` 同一
    口径：自测替身只实现 ``picked_files()``，真弹窗走 ``chosen_items()``。
    """
    reader = getattr(dialog, "chosen_items", None)
    if callable(reader):
        return list(reader())
    return [
        {"path": Path(str(path)), "uploaded": False}
        for path in dialog.picked_files()
    ]


def edited_page_dir() -> Path:
    """手工修饰过的整页组合的存放目录（**缓存**，不是产物）。

    「编辑整页组合」在独立拼图页里没有现成的落点：成品是点「导出成品」那一刻
    才写进用户选的目录的。所以手改的那张先存在 singletask 下（用户 2026-10-03
    定的独立任务缓存区），导出时再盖到对应成品上——输出目录归用户，程序只往
    里写最终成品。

    ⚠️ 目录名走 ``spec.disk_key()``（= ``imposition``）而不是标题：这里存着
    用户手改过的版面图，标题一改就再也读不到（"明明改过版面，重新打开又变回
    原样"）。见 :meth:`desktop.steps.spec.StepSpec.disk_key`。
    """
    from desktop.utils.files import singletask_dir

    return singletask_dir(_SPEC.disk_key()) / EDITED_DIRNAME


def _page_overrides(doc: dict) -> list[Path | None]:
    """按 ``compose_doc`` 的页序取出每页的手改图；没手改过的页是 ``None``。

    ⚠️ 过滤口径必须与 ``compose_doc`` **完全一致**（同样走 ``normalize_page``）：
    那边会静默丢掉不可修复的页，这里若按原列表下标取，一页坏数据就会让后面
    所有页的手改**错位到别人身上**。
    """
    overrides: list[Path | None] = []
    for raw in (doc or {}).get("pages") or []:
        if normalize_page(raw) is None:
            continue
        edited = raw.get("edited_file") if isinstance(raw, dict) else None
        overrides.append(Path(str(edited)) if edited else None)
    return overrides
