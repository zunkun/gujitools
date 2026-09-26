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

第 2 节守**默认并发数**：`core/args.py` 的 `default_workers()` /
`default_worker_cap()`（`MAX_DEFAULT_WORKERS` / `MAX_DEFAULT_DETECT_WORKERS`）
是唯一来源，函数层与桌面阶段都从那里取。桌面参数表单
不暴露 `workers`（`EXCLUDED_KEYS`），所以阶段里的兜底**就是用户实际拿到的
并发数**——一旦某处又写成 `os.cpu_count()`，用户就会莫名其妙开到 12 个线程。
真实的 bug 就是这么来的：832MB/320 页的《长短经》提取时兜底 12 线程，
12 张 6000px 大页同时渲染，峰值内存 4.2GB、CPU 打满 6 核，整机卡死。
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

#: 各自算「默认并发数」兜底的文件：必须引用 `default_workers`（可带 `command=`
#: 取该命令的上限），且**都不许自己调 cpu_count()**（真源只有 core/args.py 一处）。
_WORKERS_FALLBACK_FILES = (
    "functions/base.py",
    "functions/detect.py",
    "desktop/stages/detect_stage.py",
    "desktop/stages/generic_stage.py",
)


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

    # ---------------- 默认并发数：唯一来源 core/args.py ----------------
    import multiprocessing

    from core.args import (
        MAX_DEFAULT_DETECT_WORKERS,
        MAX_DEFAULT_WORKERS,
        CommandArgs,
        default_worker_cap,
        default_workers,
    )

    want_default = max(1, min(MAX_DEFAULT_WORKERS, multiprocessing.cpu_count()))
    want_detect = max(
        1, min(MAX_DEFAULT_DETECT_WORKERS, multiprocessing.cpu_count())
    )
    ok("默认并发上限 = 4（一页 5000×4400 约 350MB，线程数直接乘成峰值内存）",
       MAX_DEFAULT_WORKERS == 4, f"上限={MAX_DEFAULT_WORKERS}")
    ok("检测的默认并发上限 = 8（每张只在常驻服务里读一次图，比去底/裁剪轻得多）",
       MAX_DEFAULT_DETECT_WORKERS == 8, f"上限={MAX_DEFAULT_DETECT_WORKERS}")
    ok("default_workers() = min(通用上限, CPU 核数)",
       default_workers() == want_default, f"{default_workers()} vs {want_default}")
    ok("default_workers(command='detect') = min(8, CPU 核数)",
       default_workers(command="detect") == want_detect,
       f"{default_workers(command='detect')} vs {want_detect}")
    ok("default_workers(张数) 按张数收敛（通用与检测各自收敛）",
       default_workers(2) == min(2, want_default)
       and default_workers(999) == want_default
       and default_workers(2, command="detect") == min(2, want_detect),
       f"通用 2→{default_workers(2)}、999→{default_workers(999)}；"
       f"检测 2→{default_workers(2, command='detect')}")

    for cmd in ("extract", "detect", "crop", "rembg", "cropremove", "print"):
        got = CommandArgs(command=cmd, input=".").get("workers")
        want = default_workers(command=cmd)
        # 走 default_workers(command=cmd) 而不是写死 4：这条守的是**接线**
        # ——CommandArgs 必须把命令名透给 default_workers，否则 detect 会拿到
        # 通用上限 4（曾经就是这样：检测白慢 23%）。
        ok(f"{cmd} 的默认并发 = default_workers(command='{cmd}')={want}",
           got == want, f"注入值={got}")
    explicit = CommandArgs(command="rembg", input=".", workers=9).get("workers")
    ok("用户显式给的 workers 不被改写", explicit == 9, f"{explicit}")

    missing: list[str] = []
    cpu_count_hits: list[str] = []
    for rel in _WORKERS_FALLBACK_FILES:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        if not any(
            isinstance(node, ast.Name) and node.id == "default_workers"
            for node in ast.walk(tree)
        ):
            missing.append(rel)
        for node in ast.walk(tree):
            # 注释里写 cpu_count() 是说明，不算命中（AST 看不到注释）
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "cpu_count"
            ):
                cpu_count_hits.append(f"{rel}:{node.lineno}")
    # ⚠️ cpu_count 这条必须**排在「是否引用 default_workers」之前**：
    # 注入 `os.cpu_count()` 会同时把 default_workers 的引用弄没，两条都会红；
    # ok() 一失败就抛异常、模块中止，后一条根本没机会跑 → 双向验证时
    # 「失败的不是目标断言」，等于这条断言没被验证过（2026-09-25 实测踩到）。
    ok("并发兜底都不自己调 cpu_count()",
       not cpu_count_hits, f"命中={cpu_count_hits}")
    ok("并发兜底都引用 default_workers（不是各写一份）",
       not missing, f"没引用的={missing}")

    import yaml

    template = yaml.safe_load((root / "static" / "guji.yaml").read_text(encoding="utf-8"))
    # 逐段比对：每段的示例值要等于**该命令**的上限（detect=8、其余=4）。
    # 原来只收集去重后的集合、要求恰好等于 [4]，加了 detect 的 8 就会红——
    # 那样写会把「哪个命令用哪个上限」这条信息丢掉。
    template_wrong = {
        name: section["workers"]
        for name, section in (template or {}).items()
        if isinstance(section, dict)
        and isinstance(section.get("workers"), int)
        and section["workers"] != default_worker_cap(name)
    }
    template_seen = sorted(
        name
        for name, section in (template or {}).items()
        if isinstance(section, dict) and isinstance(section.get("workers"), int)
    )
    ok("配置模板扫到了各命令的 workers 段（不是空跑）",
       len(template_seen) >= 5, f"扫到={template_seen}")
    ok("配置模板各段的 workers 示例值 = 该命令的上限",
       not template_wrong,
       f"不符={template_wrong}（应为 {[(n, default_worker_cap(n)) for n in template_seen]}）")
