# -*- coding: utf-8 -*-
"""GUI 全功能自测入口（offscreen，按功能模块拆分、可动态增删用例）。

用例按功能拆在 ``tests/selftests/`` 下，一个功能一个文件；运行器扫描
目录动态发现——**新增用例 = 新增一个 .py 文件，删除用例 = 删文件或
--skip**，无需改运行器。（原先 800+ 行单文件每次都要整体跑，无法单独
重跑某个功能，已按功能拆分。）

运行方式：
    QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py              # 全部
    python tests/gui_selftest.py --list                                 # 列出模块与依赖
    python tests/gui_selftest.py --only tasklist,extract                # 只跑指定模块（自动带上依赖）
    python tests/gui_selftest.py --skip rembg,print                     # 跳过模块（依赖它们的一并跳过）
    python tests/gui_selftest.py --module-timeout 300                   # 单模块看门狗秒数

模块声明 ``DEPENDS`` 的会被自动补跑并拓扑排序；``TEARDOWN = True`` 的
清场模块（删除任务等）排在最后，不销毁其他用例还需要的夹具。成功判据：
输出「全部 N 项断言通过 ✅」。
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).parents[1]))


def discover_modules() -> dict:
    """扫描 tests/selftests/*.py 动态发现用例模块，返回 {NAME: module}。"""
    modules: dict = {}
    package_dir = Path(__file__).parent / "selftests"
    for path in sorted(package_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue  # _context 等内部设施不当作用例
        module = importlib.import_module(f"tests.selftests.{path.stem}")
        name = getattr(module, "NAME", path.stem)
        modules[name] = module
    return modules


def expand_only(names: set[str], modules: dict) -> set[str]:
    """--only：选中模块 + 其全部传递依赖。"""
    keep: set[str] = set()

    def visit(name: str) -> None:
        if name in keep:
            return
        if name not in modules:
            raise SystemExit(f"未知模块：{name}（用 --list 查看可用模块）")
        keep.add(name)
        for dep in modules[name].DEPENDS:
            visit(dep)

    for name in names:
        visit(name)
    return keep


def prune_skipped(skipped: set[str], modules: dict) -> set[str]:
    """--skip：被跳过模块 + 所有（传递）依赖它的模块都不能跑。"""
    dead = set(skipped) & set(modules)
    changed = True
    while changed:
        changed = False
        for name, mod in modules.items():
            if name in dead:
                continue
            if any(dep in dead for dep in mod.DEPENDS):
                dead.add(name)
                changed = True
    return dead


def topo_order(names: list[str], modules: dict) -> list[str]:
    """按 DEPENDS 拓扑排序（保持 discover 的字典序作稳定次序）。

    ``TEARDOWN = True`` 的模块（清场/销毁型，如 task_delete 删除任务）一律
    排在最后：它们销毁共享夹具，若跑在普通用例中间，后续模块就再也看不到
    任务目录了（thumb_cache 曾因此拿到空缩略图目录）。排序键取
    (是否清场, 模块名)，同层内仍按字典序稳定排列。
    """
    order: list[str] = []
    seen: dict[str, int] = {}

    def visit(name: str) -> None:
        if seen.get(name) == 2:
            return
        if seen.get(name) == 1:
            raise SystemExit(f"模块依赖成环：{name}")
        seen[name] = 1
        for dep in modules[name].DEPENDS:
            visit(dep)
        seen[name] = 2
        order.append(name)

    for name in sorted(names, key=lambda n: (bool(getattr(modules[n], "TEARDOWN", False)), n)):
        visit(name)
    return order


def main() -> int:
    parser = argparse.ArgumentParser(description="GUI 全功能自测（按功能模块动态发现）")
    parser.add_argument("--list", action="store_true", help="列出模块与依赖后退出")
    parser.add_argument("--only", default="", help="只跑这些模块（逗号分隔，自动带上依赖）")
    parser.add_argument("--skip", default="", help="跳过这些模块（依赖它们的一并跳过）")
    parser.add_argument(
        "--module-timeout", type=float,
        default=float(os.environ.get("GUI_SELFTEST_MODULE_TIMEOUT", "600")),
        help="单模块看门狗秒数（默认 600，环境变量 GUI_SELFTEST_MODULE_TIMEOUT 可覆盖）",
    )
    args = parser.parse_args()

    from tests.selftests import _context
    from tests.selftests._context import Context, install_module_watchdog

    modules = discover_modules()
    if args.list:
        print(f"共 {len(modules)} 个模块（按实际执行顺序）：")
        for i, name in enumerate(topo_order(list(modules), modules)):
            mod = modules[name]
            deps = "、".join(mod.DEPENDS) or "（无）"
            mark = "  [清场，排最后]" if getattr(mod, "TEARDOWN", False) else ""
            doc = (mod.__doc__ or "").strip().splitlines()[0]
            print(f"{i:2d}. {name:18s} 依赖：{deps}{mark}")
            print(f"    {'':18s} {doc}")
        return 0

    names = list(modules)
    if args.only:
        keep = expand_only({n.strip() for n in args.only.split(",") if n.strip()}, modules)
        names = [n for n in names if n in keep]
    if args.skip:
        dead = prune_skipped({n.strip() for n in args.skip.split(",") if n.strip()}, modules)
        names = [n for n in names if n not in dead]
    if not names:
        print("没有要执行的模块。用 --list 查看可用模块。")
        return 0
    order = topo_order(names, modules)

    ctx = Context()
    ctx.prepare()
    watchdog_state: dict = {}
    arm = install_module_watchdog(ctx.app, watchdog_state, args.module_timeout)

    for name in order:
        mod = modules[name]
        print(f"== {getattr(mod, 'TITLE', name) or name} ==")
        arm(name)
        started = time.time()
        try:
            mod.run(ctx)
        except Exception:
            print(f"\n[失败] 模块 {name} 执行异常（上方最后一个 PASS 之后）")
            raise
        finally:
            watchdog_state["timer"].stop()
        print(f"    ({name} 用时 {time.time() - started:.1f}s)")

    print(f"\n全部 {_context.PASS} 项断言通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
