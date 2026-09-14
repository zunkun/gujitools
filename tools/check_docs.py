"""Markdown 文档自检工具：校验相对链接、锚点与 GFM 表格列数。

遍历 ``docs/`` 与根 ``README.md`` 下的所有 Markdown 文件，检查：

1. 相对链接指向的文件是否存在（外部 http/https 链接跳过）；
2. 带 ``#anchor`` 的链接，其锚点在目标文件中是否存在（含 GFM 标题锚点规则）；
3. GFM 表格每一行的列数与表头是否一致（正确处理 ``\\|`` 转义）。

退出码：0 表示全部通过，1 表示存在问题（供 CI 使用）。

用法::

    python tools/check_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: 项目根目录（本文件位于 <root>/tools/）。
ROOT = Path(__file__).resolve().parents[1]

#: 需要跳过外部链接判断的前缀。
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "ftp://")

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _anchor(text: str) -> str:
    """按 GitHub Flavored Markdown 规则把标题文本转成锚点。"""
    lowered = text.lower().replace("`", "")
    stripped = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", lowered)
    return stripped.replace(" ", "-")


def _heading_text(raw: str) -> str:
    """去掉标题里的行内标记，得到用于生成锚点的纯文本。

    行内代码（`` ` `` 包裹）内的内容原样保留，避免其中的 ``_`` 被当作强调符号删掉。
    """
    codes: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]*)`", _stash, raw)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接取文字
    text = re.sub(r"[*_~]+", "", text)  # 粗体/斜体/删除线
    text = re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)
    return text.strip()


def _split_row(line: str) -> list[str]:
    """按未转义的 ``|`` 拆分表格行，返回单元格列表（已去首尾竖线）。"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _is_separator(cells: list[str]) -> bool:
    """判断是否是表格分隔行（如 ``|---|---|``）。"""
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def collect_anchors(md_path: Path) -> set[str]:
    """收集文件内所有标题对应的锚点（重复标题按 GFM 追加 -1/-2）。"""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in md_path.read_text(encoding="utf-8").splitlines():
        m = _HEADING_RE.match(line)
        if not m:
            continue
        base = _anchor(_heading_text(m.group(2)))
        if base in seen:
            seen[base] += 1
            anchors.add(f"{base}-{seen[base]}")
        else:
            seen[base] = 0
            anchors.add(base)
    return anchors


def iter_md_files() -> list[Path]:
    """返回需要检查的 Markdown 文件列表。"""
    files = sorted(ROOT.joinpath("docs").rglob("*.md"))
    readme = ROOT / "README.md"
    if readme.exists():
        files.append(readme)
    return files


def check_file(md: str, anchor_cache: dict[Path, set[str]]) -> list[str]:
    """检查单个 Markdown 文件，返回问题描述列表。"""
    path = Path(md)
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    lines = text.splitlines()

    # --- 链接检查 ---
    for lineno, line in enumerate(lines, 1):
        for _label, target in _LINK_RE.findall(line):
            if target.startswith(_EXTERNAL_PREFIXES):
                continue
            file_part, _, anchor = target.partition("#")
            if not file_part:
                # 同文件锚点
                if anchor and anchor not in collect_anchors(path):
                    problems.append(f"{path.name}:{lineno} 锚点不存在 #{anchor}")
                continue
            dest = (path.parent / file_part).resolve()
            if not dest.exists():
                problems.append(f"{path.name}:{lineno} 链接目标不存在 {file_part}")
                continue
            if anchor and dest.suffix == ".md":
                cache = anchor_cache.setdefault(dest, collect_anchors(dest))
                if anchor not in cache:
                    problems.append(
                        f"{path.name}:{lineno} 跨文件锚点不存在 {file_part}#{anchor}"
                    )

    # --- 表格列数检查 ---
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block: list[tuple[int, str]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append((i + 1, lines[i]))
                i += 1
            if len(block) >= 2:
                header = _split_row(block[0][1])
                width = len(header)
                # 第 2 行应为分隔行，否则不算规范表格
                sep = _split_row(block[1][1])
                if _is_separator(sep):
                    for lineno, raw in block[2:]:
                        cells = _split_row(raw)
                        if len(cells) != width:
                            problems.append(
                                f"{path.name}:{lineno} 表格列数 {len(cells)} != 表头 {width}"
                            )
                    if len(sep) != width:
                        problems.append(
                            f"{path.name}:{block[1][0]} 分隔行列数 {len(sep)} != 表头 {width}"
                        )
            continue
        i += 1
    return problems


def main() -> int:
    """执行全部检查并输出结果。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    files = iter_md_files()
    cache: dict[Path, set[str]] = {}
    all_problems: list[str] = []
    for md in files:
        all_problems.extend(check_file(str(md), cache))

    if all_problems:
        print(f"发现 {len(all_problems)} 个问题：")
        for p in all_problems:
            print("  -", p)
        return 1
    print(f"文档自检通过：{len(files)} 个文件，链接与表格均正常。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
