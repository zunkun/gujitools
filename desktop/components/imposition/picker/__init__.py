# -*- coding: utf-8 -*-
"""拼版选图弹窗（原 ``picker.py`` 拆包）：对外名字在此**显式重导出**。

拆包前 ``from desktop.components.imposition.picker import X`` 能取到的类与
常量（含 ``_source_thumb_pixmap``、卡片类），这里原样保留——外部 import
路径与名字不变。
"""

from __future__ import annotations

from desktop.components.imposition.picker.cards import _CardGrid, _SourceCard
from desktop.components.imposition.picker.constants import (
    CARD_GAP,
    CARD_H,
    CARD_HEAD,
    CARD_W,
    DIALOG_H,
    DIALOG_W,
    THUMB_BATCH,
    THUMB_GAP_MS,
    THUMB_H,
    THUMB_W,
)
from desktop.components.imposition.picker.dialog import ImpositionPickerDialog
from desktop.components.imposition.picker.thumb import _source_thumb_pixmap

__all__ = [
    "ImpositionPickerDialog",
    "THUMB_W",
    "THUMB_H",
    "CARD_W",
    "CARD_H",
    "CARD_HEAD",
    "CARD_GAP",
    "DIALOG_W",
    "DIALOG_H",
    "THUMB_BATCH",
    "THUMB_GAP_MS",
    "_SourceCard",
    "_CardGrid",
    "_source_thumb_pixmap",
]
