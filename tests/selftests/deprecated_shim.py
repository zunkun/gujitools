# -*- coding: utf-8 -*-
"""兼容 re-export 壳不许再被**生产代码**使用。

拆分大文件时留下的兼容壳（如 `utils/pdf_utils.py`）是**过渡设施**：
它的存在是为了让调用点不用一次性全改，但每多一个生产调用点走壳，
将来删壳就多一处要迁，而且壳会掩盖"这个符号其实住在哪"——
`functions/print.py` 就曾经在换过 margin/color 之后，仍从壳里取
`register_fonts` / `draw_vertical_text`，谁都没发现。

本守卫钉住：**生产代码（core/ cli/ functions/ desktop/）不得 import 壳**，
测试可以直接用底模块，也可以暂时走壳（不强求）。

⚠️ 登记新壳时想清楚：壳是为了"先拆完、再慢慢迁调用点"，
不是为了让"不迁"变成合法状态。
"""

import re
from pathlib import Path

NAME = "deprecated_shim"
DEPENDS: list[str] = []
TITLE = "兼容壳不得被生产代码使用"

_ROOT = Path(__file__).resolve().parents[2]
#: 生产代码目录（测试不算）
_PROD_DIRS = ("core", "cli", "functions", "desktop")

#: 兼容壳模块 → 它 re-export 的**真实模块**（用于报错时给出迁移指向）
_SHIMS = {
    "utils.pdf_utils": ("utils.pdf_extract", "utils.pdf_draw"),
}
#: 允许 import 壳的文件（一般只有壳自己）
_ALLOWED = {
    "utils/pdf_utils.py",
}

# 抓 `from utils.pdf_utils import ...`（模块级与函数内都算）
_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(re.escape(m) for m in _SHIMS) + r")\b",
    re.M,
)


def run(ctx) -> None:
    from tests.selftests._context import ok

    hits: dict[str, list[str]] = {}
    scanned = 0
    for layer in _PROD_DIRS:
        for f in sorted((_ROOT / layer).rglob("*.py")):
            rel = f.relative_to(_ROOT).as_posix()
            if "__pycache__" in rel or rel in _ALLOWED:
                continue
            scanned += 1
            text = f.read_text(encoding="utf-8", errors="ignore")
            for m in _IMPORT_RE.finditer(text):
                hits.setdefault(m.group(1), []).append(rel)

    ok("守卫真的扫到了生产代码（不是空跑）",
       scanned >= 40, f"只扫到 {scanned} 个文件")

    detail = {
        mod: {"改用": list(_SHIMS[mod]), "命中": sorted(set(files))}
        for mod, files in hits.items()
    }
    ok("生产代码不再 import 兼容壳", not hits, f"仍在走壳={detail}")
