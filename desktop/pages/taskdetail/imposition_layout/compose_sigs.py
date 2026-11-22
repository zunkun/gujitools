# -*- coding: utf-8 -*-
"""逐页「已落盘签名」侧车文件的读写（缺失/损坏一律当空表）。"""

from __future__ import annotations

from pathlib import Path


def _read_composed_sigs(path: Path) -> dict[int, str]:
    """读侧车文件 → ``{页号: 签名}``；缺失/损坏一律当空表（判据退回全量合成）。"""
    from desktop.store.json_io import read_json

    raw = read_json(path, {})
    pages = raw.get("pages") if isinstance(raw, dict) else None
    out: dict[int, str] = {}
    for key, value in (pages or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, str):
            out[index] = value
    return out


def _write_composed_sigs(path: Path, sigs: dict[int, str]) -> None:
    """原子写侧车文件；目录已不存在（任务被删）时静默跳过，绝不重建目录。"""
    from desktop.store.json_io import write_json

    try:
        write_json(path, {"pages": {str(k): sigs[k] for k in sorted(sigs)}})
    except OSError:
        pass
