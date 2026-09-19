# -*- coding: utf-8 -*-
"""分层依赖方向守卫。

`utils ← core ← {cli, functions, desktop}` 这条单向规则过去只写在文档里，靠人
记。本模块把它变成会红的断言：

1. **模块级**跨层 import 必须在白名单内（这是真的启动期耦合，会拖慢启动、
   绑死模块）；
2. `desktop` **任何位置**（含函数内）都不得引用 `cli` —— GUI 不该依赖命令行
   入口，否则界面没法脱离 CLI 单独演进；
3. 元守卫：确认真的扫到了足够多的文件，避免「一个都没扫到」时全绿。

⚠️ **只查模块级（行首）import**；缩进的 import 是**函数内延迟导入**，属于
有意的解耦手段（避免启动期加载 YOLO/torch 这类重依赖），不算违规。扫依赖时
若不分清这两者，会把延迟导入误报成耦合——体检时踩过一次，差点白重构。
"""

import re
from pathlib import Path

NAME = "layering"
DEPENDS: list[str] = []
TITLE = "分层依赖方向"

_LAYERS = ("utils", "core", "cli", "functions", "desktop")

#: 允许的模块级跨层依赖（依赖方 → 被依赖方）
_ALLOWED = {
    ("core", "utils"),
    ("cli", "utils"),
    ("cli", "core"),
    ("functions", "utils"),
    ("functions", "core"),
    ("desktop", "utils"),
    ("desktop", "core"),
}

#: 行首 = 模块级 import
_TOP_IMPORT = re.compile(r"^(?:from|import)\s+([A-Za-z_][\w.]*)", re.M)
#: 任意缩进 = 连函数内延迟导入一起抓
_ANY_CLI = re.compile(r"^\s*(?:from|import)\s+cli\b", re.M)


def run(ctx) -> None:
    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]

    # ---- 1. 模块级跨层依赖必须在白名单内 ----
    scanned = 0
    violations: dict[str, list[str]] = {}
    for layer in _LAYERS:
        for f in sorted((root / layer).rglob("*.py")):
            rel = f.relative_to(root).as_posix()
            if "__pycache__" in rel:
                continue
            scanned += 1
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in _TOP_IMPORT.finditer(text):
                top = m.group(1).split(".")[0]
                if top in _LAYERS and top != layer and (layer, top) not in _ALLOWED:
                    violations.setdefault(f"{layer} -> {top}", []).append(rel)

    ok("分层守卫真的扫到了源文件（不是空跑）",
       scanned >= 40, f"只扫到 {scanned} 个文件")
    detail = {k: sorted(set(v)) for k, v in violations.items()}
    ok("模块级跨层依赖全部在白名单内", not violations, f"违规={detail}")

    # ---- 2. desktop 不得引用 cli（含函数内）----
    cli_hits = [
        f.relative_to(root).as_posix()
        for f in sorted((root / "desktop").rglob("*.py"))
        if "__pycache__" not in f.relative_to(root).as_posix()
        and _ANY_CLI.search(f.read_text(encoding="utf-8", errors="ignore"))
    ]
    ok("desktop 不引用 cli（含函数内 import）",
       not cli_hits, f"仍有引用：{cli_hits}")
