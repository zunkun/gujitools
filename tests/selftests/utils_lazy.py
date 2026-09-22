# -*- coding: utf-8 -*-
"""utils 包的惰性表与「子模块属性访问」守卫。

## 为什么需要

`utils` 对重依赖子模块（`yolo_utils` / `image_utils` / `pdf_extract`…）采用
``_LAZY`` 表 + ``__getattr__`` 延迟加载：**包属性是首次被 `__getattr__` 命中时
才挂上去的**。由此产生一个极隐蔽的坑：

```python
utils.yolo_utils.is_model_loaded()   # ❌ 靠偶然才成立
```

只有在这**之前**恰好有代码执行过 `from utils.yolo_utils import ...`，子模块才会
成为 `utils` 包的属性；没跑过那条路径就**直接 AttributeError**——静态检查全绿、
单元测试也可能全绿，只看用户哪条路径先走（真实踩过：常驻 YOLO 服务的预热在
`_fingerprint()` 先跑时一切正常，直接调就炸）。

正确写法是把名字登记进 `utils/__init__.py` 的 `_LAZY` 表，然后写 `utils.<名字>`。

本模块守两条：

1. `_LAZY` 里登记的名字**全部真的可取**（抓"目标名写错 / 登记了却不存在"）；
2. 生产代码**不得**出现 `utils.<子模块>.<属性>` 形态的访问（用 AST 精确识别，
   文档字符串与注释里提到这些路径不算违规）。
"""

from __future__ import annotations

import ast
from pathlib import Path

NAME = "utils_lazy"
DEPENDS: list[str] = []
TITLE = "utils 惰性表与子模块属性访问"

#: 参与扫描的目录与顶层入口文件
_SCAN_DIRS = ("functions", "desktop", "core", "cli", "utils")
_SCAN_FILES = ("cli.py", "desktop.py", "config.py")


def _dotted(node) -> str:
    """把 `utils.yolo_utils.is_model_loaded` 这类链式 Attribute 还原成点分名。"""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def run(ctx) -> None:
    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]

    # ---- 1. 惰性表登记的名字全部真的可取 ----
    import utils

    lazy = getattr(utils, "_LAZY", None)
    ok("utils._LAZY 存在（惰性表没有被删）",
       isinstance(lazy, dict) and len(lazy) >= 5,
       f"取到 {type(lazy).__name__}")
    missing = sorted(name for name in lazy if not hasattr(utils, name))
    ok("惰性表登记的名字全部能从包属性取到（抓目标名写错/漏实现）",
       not missing, f"取不到的名字：{missing}")

    # ---- 2. 生产代码不得出现 utils.<子模块>.<属性> ----
    # 用 AST 而不是正则：文档字符串/注释里提到 `utils.path_utils.xxx` 是在
    # 说明出处，不算违规（正则会误报 29 处，全是 prose）。
    submodule_names = {
        p.stem for p in (root / "utils").glob("*.py") if p.stem != "__init__"
    }
    hits: list[str] = []
    scanned = 0

    def _scan_file(path: Path, rel: str) -> None:
        nonlocal scanned
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            dotted = _dotted(node)
            if not dotted:
                continue
            head, second = dotted.split(".", 1)[0], dotted.split(".")[1]
            if head == "utils" and second in submodule_names:
                hits.append(f"{rel}:{node.lineno}: {dotted}")

    for directory in _SCAN_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            _scan_file(f, f.relative_to(root).as_posix())
    for name in _SCAN_FILES:
        f = root / name
        if f.is_file():
            _scan_file(f, name)

    ok("真的扫到了源文件（不是空跑）", scanned >= 40, f"只扫到 {scanned} 个")
    ok("生产代码没有 utils.<子模块>.<属性> 访问（应登记进 _LAZY 后写 utils.<名字>）",
       not hits, f"命中 {len(hits)} 处：" + "; ".join(hits[:5]))
