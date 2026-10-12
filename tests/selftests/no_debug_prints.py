# -*- coding: utf-8 -*-
"""功能层源码不许有 ``[debug]`` 调试残留（2026-10-12 真实体验审计）。

事故现场：``utils/pdf_extract.py::run_on_input_directory`` 里留着 3 行
``print("[debug] ...")``。它们在 CLI 里只是终端噪声，但在 **desktop worker
子进程**里，stdout 是 JSON Lines 事件通道——runner 会把非 JSON 行降级成
"人读日志"写进用户的日志面板（``runner._consume_worker_stdout`` 的兜底分支），
于是用户每次目录提取都能在日志里看到三行 ``[debug] run_on_input_directory
called with: ...``。

本守卫在 L0（纯源码文本，秒级）钉住：四个功能层（utils/functions/core/cli）
的任何 ``.py`` 源码里不许再出现 ``[debug]`` / ``[DBG]`` 字样的 print 残留。
正常面向用户的输出请走 reporter / 明确的中文提示，别用调试记号。
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "no_debug_prints"
DEPENDS: list[str] = []
TITLE = "功能层无 [debug] 调试残留"

ROOT = Path(__file__).resolve().parents[2]
#: 扫描的功能层（入口 desktop.py / cli.py 例外——它们不面向执行输出）
_LAYERS = ("utils", "functions", "core", "cli")
_MARKERS = re.compile(r"\[debug\]|\[DBG\]", re.IGNORECASE)


def run(ctx) -> None:  # noqa: ARG001 - 不需要共享夹具
    from tests.selftests._context import ok

    offenders: dict[str, list[int]] = {}
    for layer in _LAYERS:
        for py in sorted((ROOT / layer).rglob("*.py")):
            text = py.read_text(encoding="utf-8")
            hits = [
                i + 1 for i, line in enumerate(text.splitlines())
                if _MARKERS.search(line)
            ]
            if hits:
                offenders[str(py.relative_to(ROOT))] = hits

    ok("utils/functions/core/cli 四层源码无 [debug]/[DBG] 残留",
       not offenders, str(offenders))


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
