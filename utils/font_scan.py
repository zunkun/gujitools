# -*- coding: utf-8 -*-
"""扫描系统字体目录，找出所有含中文的字体文件。

与 `utils.fonts` 的分工
-----------------------
`utils.fonts` 是**纯查表**：一张跨平台候选清单，查它永远很快（只 stat 几个
已知路径），覆盖日常要用的字体。`utils.fonts` 因此是生成 PDF 的唯一入口——
**出 PDF 的路上绝不做全盘扫描**，那会白白多花好几秒。

本模块是**真扫描**：遍历系统字体目录、逐个文件读 cmap 判断有没有汉字。用户
自己装的补字字体（花园明朝、BabelStone Han…）只有扫描才能发现，而它们恰恰是
古籍异体字最需要的字体。代价是慢（本机 200+ 字体约 7 秒），因此：

- 结果**缓存到磁盘**，第二次起毫秒级返回；
- 只在 GUI 空闲时由后台线程跑（`desktop.services.font_catalog`），
  绝不出现在主线程与生成 PDF 的路径上。

扫描失败（没装 fontTools、目录不可读、文件损坏）一律返回空元组——调用方
把它当"没有额外字体"，仍然有 `utils.fonts` 的候选表可用。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from utils.fonts import GROUP_OTHER, FontEntry

#: 缓存文件（临时目录）：换机器/装新字体后指纹会变，自动重扫
_CACHE_NAME = "guji-cjk-font-cache.json"
#: 扫描目录树的最大深度，防止 /usr/share/fonts 下的深层嵌套拖慢扫描
_MAX_DEPTH = 4
_FONT_EXTS = (".ttf", ".otf", ".ttc")
#: 判定"含中文"的探针码位：一（常用）、电（常用），两者都有才算
_PROBE_CODEPOINTS = (0x4E00, 0x7535)


def font_directories() -> tuple[str, ...]:
    """按平台给出要扫描的字体目录（可能不存在，调用方自己判空）。"""
    home = str(Path.home())
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        dirs = [
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        ]
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        return tuple(dirs)
    if sys.platform == "darwin":
        return (
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.join(home, "Library", "Fonts"),
        )
    return (
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.join(home, ".fonts"),
        os.path.join(home, ".local", "share", "fonts"),
    )


def _iter_font_files():
    """遍历字体目录下的字体文件（带深度限制，跳过不可读目录）。"""
    for root_dir in font_directories():
        root = Path(root_dir)
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - base_depth
            if depth >= _MAX_DEPTH:
                dirnames[:] = []
            for name in filenames:
                if name.lower().endswith(_FONT_EXTS):
                    yield os.path.join(dirpath, name)


def _directory_fingerprint(files) -> str:
    """目录指纹：文件数 + 总大小 + 最新 mtime。装/删字体后它会变。"""
    count = 0
    total = 0
    newest = 0.0
    for path in files:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        count += 1
        total += stat.st_size
        newest = max(newest, stat.st_mtime)
    return f"{count}:{total}:{int(newest)}"


def _read_display_name(font) -> str:
    """取字体的人类可读名：优先中文（简/繁），其次英文。"""
    try:
        names = font["name"].names
    except Exception:
        return ""
    buckets: dict[int, str] = {}
    for record in names:
        if record.nameID not in (1, 4, 16):
            continue
        try:
            value = record.toUnicode().strip()
        except Exception:
            continue
        if not value:
            continue
        # langID：0x804 简体中文、0x404 繁体中文、0x409 英文
        buckets.setdefault(record.langID, value)
    for lang in (0x804, 0x404, 0x409):
        if buckets.get(lang):
            return buckets[lang]
    return next(iter(buckets.values()), "") if buckets else ""


def _probe_file(path: str) -> tuple[str, bool] | None:
    """读一个字体文件：返回 (显示名, 是否含汉字)；读不动返回 None。"""
    try:
        from fontTools.ttLib import TTCollection, TTFont

        if path.lower().endswith(".ttc"):
            fonts = TTCollection(path, lazy=True).fonts[:3]
        else:
            fonts = [TTFont(path, lazy=True)]
        display = ""
        has_cjk = False
        for font in fonts:
            try:
                cmap = font.getBestCmap()
            except Exception:
                continue
            if all(code in cmap for code in _PROBE_CODEPOINTS):
                has_cjk = True
            if not display:
                display = _read_display_name(font)
        if not display:
            display = os.path.splitext(os.path.basename(path))[0]
        return display, has_cjk
    except Exception:
        return None


def _cache_path() -> Path:
    """缓存文件位置（临时目录下，随时可丢）。"""
    import tempfile

    return Path(tempfile.gettempdir()) / _CACHE_NAME


def _load_cache(fingerprint: str):
    """读磁盘缓存；指纹不符（装过新字体）返回 None。"""
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("fingerprint") != fingerprint:
        return None
    try:
        return tuple(
            FontEntry(display=row[0], path=row[1], group=int(row[2]))
            for row in data.get("fonts", [])
        )
    except Exception:
        return None


def _save_cache(fingerprint: str, entries) -> None:
    """写磁盘缓存；写不进去（权限/磁盘满）无所谓，下次重扫即可。"""
    try:
        payload = {
            "fingerprint": fingerprint,
            "fonts": [[e.display, e.path, e.group] for e in entries],
        }
        _cache_path().write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def scan_system_fonts(force: bool = False) -> tuple[FontEntry, ...]:
    """扫描系统里的中文字体，返回按显示名排序的条目。

    ⚠️ 首次调用要遍历整个字体目录、逐个读 cmap，**本机约 7 秒**——
    只能在后台线程里调（见 `desktop.services.font_catalog`）。结果会写
    磁盘缓存，之后每次调用毫秒级返回。
    """
    files = list(_iter_font_files())
    fingerprint = _directory_fingerprint(files)
    if not force:
        cached = _load_cache(fingerprint)
        if cached is not None:
            return cached

    entries: list[FontEntry] = []
    seen: set[str] = set()
    for path in files:
        probed = _probe_file(path)
        if probed is None:
            continue
        display, has_cjk = probed
        if not has_cjk or path in seen:
            continue
        seen.add(path)
        entries.append(FontEntry(display=display, path=path, group=GROUP_OTHER))

    entries.sort(key=lambda e: (e.display.lower(), e.path))
    result = tuple(entries)
    _save_cache(fingerprint, result)
    return result


def scan_seconds_hint() -> float:
    """上一次扫描的耗时（秒）；没有记录返回 0.0（调试用）。"""
    return getattr(scan_system_fonts, "_last_seconds", 0.0)


def timed_scan(force: bool = False) -> tuple[tuple[FontEntry, ...], float]:
    """带计时的扫描（调试与自测用）：返回 (条目, 耗时秒)。"""
    started = time.time()
    entries = scan_system_fonts(force=force)
    spent = time.time() - started
    scan_system_fonts._last_seconds = spent
    return entries, spent
