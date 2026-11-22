# -*- coding: utf-8 -*-
"""拼版页管理控制器的模块级小工具。"""

from __future__ import annotations

from pathlib import Path


def _chosen_items(dialog) -> list[dict]:
    """弹窗勾选结果 → ``[{"path": Path, "uploaded": bool}]``。

    ⚠️ 自测替身（``tests/selftests/printing/imposition/`` 里的 *_Fake*Dialog）只实现
    了 ``picked_files()``：这里用 ``getattr`` 兜底，替身不必跟着改；真弹窗
    走 ``chosen_items()``（带"是不是本次上传"的标记，宿主据此决定要不要
    复制文件）。
    """
    reader = getattr(dialog, "chosen_items", None)
    if callable(reader):
        return list(reader())
    return [
        {"path": Path(str(path)), "uploaded": False}
        for path in dialog.picked_files()
    ]
