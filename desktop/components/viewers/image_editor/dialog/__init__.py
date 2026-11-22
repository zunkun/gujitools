# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``ImageEditorDialog`` 子包（装配点在 ``assembly.py``）。"""
from __future__ import annotations

from .assembly import ImageEditorDialog
from .constants import EDITOR_MIN_SIZE, EDITOR_SIZE

__all__ = ["EDITOR_MIN_SIZE", "EDITOR_SIZE", "ImageEditorDialog"]
