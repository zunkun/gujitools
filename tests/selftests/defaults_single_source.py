# -*- coding: utf-8 -*-
"""「默认值只保留一份」守卫：functions 层不许自带第二套兜底值。

`core/command_spec.py` 的 `COMMAND_SPECS` / `PRINT_DEFAULTS` 是参数默认值的
唯一事实来源。`CommandArgs` 会把它们灌进 `command_args`，所以业务代码里
`command_args.get("键", 字面量)` 的第二个参数**本该永远用不上**——一旦用上，
就是在另一处又写了一份默认值，改 CLI 默认时这里不会跟着变。

`functions/print.py` 就出过这事：`title_font_size` 兜底 18、`page_number_font_size`
兜底 12，而命令规格里早就是 20。没人会去比这两个数字，直到某天行为对不上。

本模块用 AST（不是正则）扫出所有 `xxx.get("键", 字面量)` 调用，逐个与命令规格
比对：`ast.literal_eval` 求不出值的（比如写的是 `PRINT_DEFAULTS[...]`）
正是我们期望的写法，跳过不报。

⚠️ 只查**带第二个参数**的 `get`。不带兜底的 `get(key)` 由调用方自己处理 None，
不在本守卫的职责内。
"""

import ast
from pathlib import Path

NAME = "defaults_single_source"
DEPENDS: list[str] = []
TITLE = "默认值不自带第二份"

#: 文件名 → 命令名（用于取对应的 CommandSpec）
_FILE_TO_COMMAND = {
    "extract.py": "extract",
    "detect.py": "detect",
    "crop.py": "crop",
    "rembg.py": "rembg",
    "crop_remove.py": "cropremove",
    "print.py": "print",
}

#: 允许与命令规格不一致的键（**登记在案**，想加请先写理由）。
#: 这几个都是「空列表 vs None」：兜底 `[]` 比规格里的 `None` 更安全——省掉
#: 下游的 None 判断，语义等价（都表示「没有这一项」）。
_ALLOWED_MISMATCH = {
    ("print", "skip_pages"),
    ("print", "title_switch_nodes"),
}


class _GetWithDefault(ast.NodeVisitor):
    """收集 `.get("key", <字面量>)` 形式的调用。"""

    def __init__(self) -> None:
        self.hits: list[tuple[str, object]] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and len(node.args) == 2
        ):
            # ⚠️ `self.command_args` 在 AST 里是 Attribute（不是 Name），
            # 只取 `id` 会得到空串 → 所有调用被静默跳过、守卫形同虚设
            # （注入回归形态时全绿才发现的）。两种都要认。
            owner = (
                getattr(func.value, "id", "")
                or getattr(func.value, "attr", "")
                or ""
            )
            key_node, val_node = node.args
            if "args" in owner and isinstance(key_node, ast.Constant):
                key = key_node.value
                if isinstance(key, str):
                    try:
                        literal = ast.literal_eval(val_node)
                    except (ValueError, SyntaxError):
                        pass  # 不是字面量（如 PRINT_DEFAULTS[...]）：正是期望写法
                    else:
                        self.hits.append((key, literal))
        self.generic_visit(node)


def run(ctx) -> None:
    from core.command_spec import COMMAND_SPECS
    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]

    scanned = 0
    drift: dict[str, list[str]] = {}
    for filename, command in _FILE_TO_COMMAND.items():
        path = root / "functions" / filename
        if not path.exists():
            continue
        spec = COMMAND_SPECS.get(command)
        if spec is None:
            ok(f"{command} 已在 COMMAND_SPECS 登记（守卫前提）", False, str(command))
            continue
        scanned += 1
        visitor = _GetWithDefault()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        for key, literal in visitor.hits:
            if key not in spec.defaults:
                continue  # 通用键（input/output/clean/workers）不在规格里
            want = spec.defaults[key]
            if literal == want or (command, key) in _ALLOWED_MISMATCH:
                continue
            drift.setdefault(f"{filename}:{key}", []).append(
                f"代码兜底={literal!r}；规格默认={want!r}"
            )

    ok("默认值守卫扫到了 functions 源文件（不是空跑）",
       scanned >= 5, f"只扫到 {scanned} 个文件")
    ok("functions 层不自带与命令规格冲突的默认值",
       not drift, f"漂移={drift}")
