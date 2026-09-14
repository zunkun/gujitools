"""API 参考文档生成器。

用标准库 `ast` 静态解析源码（**不导入被测模块**，因此不需要 cv2/torch/PySide6
等重依赖，离线和 CI 均可运行），把 `desktop` / `cli` / `functions` / `utils`
各包与顶层入口脚本的公开 API 渲染成 Markdown，输出到 `docs/api/`。

为什么用 AST 而不是 `inspect`：

- `inspect.signature` 必须先 import 模块，而本项目模块在导入期就会拉起重依赖
  （`functions` → cv2/torch，`desktop` → PySide6），生成文档不该有这种副作用；
- AST 解析对语法错误之外的情况完全确定，且能拿到装饰器、`async def`、位置参数
  分隔符等完整签名信息。

用法：

```bash
python tools/gen_api_docs.py            # 生成 / 覆盖 docs/api/*.md
python tools/gen_api_docs.py --check    # 只校验：文档与源码不一致时退出码非 0
python tools/gen_api_docs.py --out DIR  # 输出到其它目录
```

收集范围：

- 模块：各包内全部 `*.py`（含 `__init__.py`）；
- 类：模块顶层的公开类（不以 `_` 开头）；
- 方法：公开方法 + `__init__`（其余 dunder 与私有方法跳过）；
- 函数：模块顶层的公开函数；
- 常量：模块顶层的全大写名字（仅收录字面量，便于渲染成表格）。
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# 路径与目标
# ---------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "api"

#: (输出文件名, 待扫描目录或 None 表示仓库根目录下的顶层脚本, 展示名, 一句话说明)
TARGETS: list[tuple[str, str | None, str, str]] = [
    ("desktop", "desktop", "desktop", "桌面端：GUI 主进程、worker 子进程、存储、界面系统"),
    ("cli", "cli", "cli", "命令行入口层：参数解析、子命令调度"),
    ("functions", "functions", "functions", "图像处理功能模块：GUI 与 CLI 共用同一套算法"),
    ("utils", "utils", "utils", "通用工具函数：几何、排序、图像 IO、PDF、YOLO"),
    ("entrypoints", None, "入口脚本", "仓库顶层的可执行入口与配置读取"),
]

#: 顶层入口脚本的收集名单（排除打包脚本等与运行时无关的文件）。
ROOT_SCRIPTS = ("main.py", "desktop.py", "config.py")

GENERATED_BANNER = (
    "<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。"
    "修改源码后重跑生成命令即可。 -->"
)

_PRIVATE = re.compile(r"^_")

#: Qt 约定覆写方法 → 自动生成的说明。
#: 这类方法是框架回调，逐个手写 docstring 只会得到一堆同义句；这里统一标注语义，
#: 让 API 参考里的条目不再是空的「—」，同时不给源码增加噪音。
QT_OVERRIDES: dict[str, str] = {
    "paintEvent": "Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。",
    "resizeEvent": "Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。",
    "showEvent": "Qt 事件覆写：显示时刷新状态。",
    "hideEvent": "Qt 事件覆写：隐藏时收尾。",
    "closeEvent": "Qt 事件覆写：关闭前释放子进程 / 后台线程。",
    "enterEvent": "Qt 事件覆写：鼠标移入时进入高亮态。",
    "leaveEvent": "Qt 事件覆写：鼠标移出时恢复常态。",
    "mousePressEvent": "Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。",
    "mouseMoveEvent": "Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。",
    "mouseReleaseEvent": "Qt 事件覆写：松开（提交本次编辑）。",
    "mouseDoubleClickEvent": "Qt 事件覆写：双击。",
    "wheelEvent": "Qt 事件覆写：滚轮（缩放 / 滚动）。",
    "keyPressEvent": "Qt 事件覆写：键盘操作（如 Delete 删除选中项）。",
    "dragEnterEvent": "Qt 事件覆写：拖入时校验并接受拖放。",
    "dragMoveEvent": "Qt 事件覆写：拖动过程中更新落点提示。",
    "dropEvent": "Qt 事件覆写：放下时处理拖入内容。",
    "sizeHint": "Qt 覆写：建议尺寸。",
    "minimumSizeHint": "Qt 覆写：最小建议尺寸。",
    "eventFilter": "Qt 事件过滤器。",
}


# ---------------------------------------------------------------------------
# 解析：把源码变成结构化数据
# ---------------------------------------------------------------------------


class ApiFunction:
    """一个模块级函数或类方法的签名与说明。"""

    __slots__ = ("name", "signature", "doc", "decorators", "is_async", "lineno")

    def __init__(
        self,
        name: str,
        signature: str,
        doc: str | None,
        decorators: list[str],
        is_async: bool,
        lineno: int,
    ) -> None:
        self.name = name
        self.signature = signature
        self.doc = doc
        self.decorators = decorators
        self.is_async = is_async
        self.lineno = lineno

    @property
    def display(self) -> str:
        prefix = "async " if self.is_async else ""
        return f"{prefix}{self.name}{self.signature}"


class ApiClass:
    """一个公开类：基类、类说明与公开方法。"""

    __slots__ = ("name", "bases", "doc", "methods", "lineno")

    def __init__(
        self,
        name: str,
        bases: list[str],
        doc: str | None,
        methods: list[ApiFunction],
        lineno: int,
    ) -> None:
        self.name = name
        self.bases = bases
        self.doc = doc
        self.methods = methods
        self.lineno = lineno

    @property
    def display(self) -> str:
        return f"{self.name}({', '.join(self.bases)})" if self.bases else self.name


class ApiModule:
    """一个模块：说明、公开类、公开函数、公开常量。"""

    __slots__ = ("path", "dotted", "doc", "classes", "functions", "constants")

    def __init__(
        self,
        path: pathlib.Path,
        dotted: str,
        doc: str | None,
        classes: list[ApiClass],
        functions: list[ApiFunction],
        constants: list[tuple[str, str]],
    ) -> None:
        self.path = path
        self.dotted = dotted
        self.doc = doc
        self.classes = classes
        self.functions = functions
        self.constants = constants

    @property
    def is_empty(self) -> bool:
        return not (self.classes or self.functions or self.constants)


def _render_args(node: ast.FunctionDef | ast.AsyncFunctionDef, drop_self: bool) -> str:
    """把 `arguments` 节点渲染成 `(a, b=1, *args, **kw)`，方法则去掉 self/cls。"""
    args = node.args
    text = ast.unparse(args)
    if drop_self and (node.args.posonlyargs or node.args.args):
        first = (node.args.posonlyargs or node.args.args)[0]
        if first.arg in ("self", "cls"):
            # 只替换首个标识符，避免误伤默认值中的同名参数
            text = re.sub(rf"^\b{first.arg}\b\s*(,)?\s*", "", text, count=1)
    return f"({text})"


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef, drop_self: bool) -> str:
    sig = _render_args(node, drop_self)
    if node.returns is not None:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out = []
    for dec in node.decorator_list:
        try:
            out.append(ast.unparse(dec))
        except Exception:  # pragma: no cover - 极端语法
            out.append("<?>")
    return out


def _const_value(node: ast.AST) -> str | None:
    """只要字面量常量；复杂表达式返回 None（不收录，避免文档出现大段代码）。"""
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, str):
            shown = value if len(value) <= 60 else value[:57] + "…"
            return f'`"{shown}"`'
        return f"`{value!r}`"
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and not node.elts:
        return {ast.List: "`[]`", ast.Tuple: "`()`", ast.Set: "`set()`"}[type(node)]
    return None


def parse_module(path: pathlib.Path, dotted: str) -> ApiModule:
    """解析单个文件为 `ApiModule`。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    classes: list[ApiClass] = []
    functions: list[ApiFunction] = []
    constants: list[tuple[str, str]] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if _PRIVATE.match(node.name):
                continue
            methods = []
            for sub in node.body:
                if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if sub.name == "__init__":
                    # 无参构造且没写说明时不入表：类说明已覆盖，`__init__() -> None`
                    # 这种条目只提供噪音。
                    if _signature(sub, drop_self=True) == "() -> None" and not ast.get_docstring(sub):
                        continue
                elif _PRIVATE.match(sub.name):
                    continue
                methods.append(
                    ApiFunction(
                        name=sub.name,
                        signature=_signature(sub, drop_self=True),
                        doc=ast.get_docstring(sub),
                        decorators=_decorators(sub),
                        is_async=isinstance(sub, ast.AsyncFunctionDef),
                        lineno=sub.lineno,
                    )
                )
            classes.append(
                ApiClass(
                    name=node.name,
                    bases=[ast.unparse(b) for b in node.bases],
                    doc=ast.get_docstring(node),
                    methods=methods,
                    lineno=node.lineno,
                )
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _PRIVATE.match(node.name):
                continue
            functions.append(
                ApiFunction(
                    name=node.name,
                    signature=_signature(node, drop_self=False),
                    doc=ast.get_docstring(node),
                    decorators=_decorators(node),
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    lineno=node.lineno,
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    shown = _const_value(node.value)
                    if shown is not None:
                        constants.append((target.id, shown))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper() and node.value is not None:
                shown = _const_value(node.value)
                if shown is not None:
                    constants.append((node.target.id, shown))

    return ApiModule(
        path=path,
        dotted=dotted,
        doc=ast.get_docstring(tree),
        classes=classes,
        functions=functions,
        constants=constants,
    )


def collect(target_dir: str | None, dotted_prefix: str) -> list[ApiModule]:
    """收集一个目标下的全部模块，按文件路径排序（`__init__` 优先）。"""
    if target_dir is None:
        paths = [(ROOT / name, name[:-3]) for name in ROOT_SCRIPTS if (ROOT / name).exists()]
    else:
        base = ROOT / target_dir
        paths = []
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(ROOT).with_suffix("")
            dotted = ".".join(rel.parts)
            if dotted.endswith(".__init__"):
                dotted = dotted[: -len(".__init__")]
            paths.append((p, dotted))
    return [parse_module(p, d) for p, d in paths]


# ---------------------------------------------------------------------------
# 渲染：结构化数据 → Markdown
# ---------------------------------------------------------------------------


def _source_link(module: ApiModule) -> str:
    rel = module.path.relative_to(ROOT).as_posix()
    return f"[`{rel}`](../../{rel})"


def _code(text: str) -> str:
    return f"`{text}`"


def _cell(text: str) -> str:
    """转义表格单元格内容。

    GFM 的表格里 ``|`` 一律是列分隔符（即使它在行内代码里），所以签名中的
    ``dict | None`` 这种联合类型必须写成 ``dict \\| None``，否则整行会错列。
    """
    return text.replace("|", "\\|").replace("\n", " ")


def _prose(text: str) -> str:
    """中和 docstring 里的 Markdown 链接语法。

    docstring 是纯文本说明，不应在生成的文档里变成真链接。例如
    ``utils/help.py`` 里描述「链接 [text](url) → text」的说明文字，直接渲染会
    产出一个指向 "url" 的失效链接；转义成 ``]\\(`` 后视觉完全一致但不再是链接。
    """
    return text.replace("](", "]\\(")


def _anchor(text: str) -> str:
    """按 GitHub Flavored Markdown 的规则生成标题锚点。

    GFM 会去掉反引号、点号等非字母数字字符，空格转连字符，其余小写化。
    """
    lowered = text.lower().replace("`", "")
    stripped = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", lowered)
    return stripped.replace(" ", "-")


#: 方法表格中「说明」列的截断长度；超过则首行被省略并另起明细小节。
_BRIEF_LIMIT = 72


def _brief(item: ApiFunction) -> str:
    """取 docstring 首行作为表格说明；无说明时回退到 Qt 覆写标注或占位符。"""
    doc = item.doc
    if not doc or not doc.strip():
        return QT_OVERRIDES.get(item.name, "—")
    first = _prose(doc.strip().splitlines()[0].strip())
    if len(first) > _BRIEF_LIMIT:
        return first[: _BRIEF_LIMIT - 1].rstrip() + "…"
    return first


def _needs_detail(item: ApiFunction) -> bool:
    """docstring 是否含有表格首行容纳不下的内容（多行，或首行被截断）。"""
    if not item.doc or not item.doc.strip():
        return False
    text = item.doc.strip()
    return "\n" in text or len(text.splitlines()[0].strip()) > _BRIEF_LIMIT


def _render_doc(doc: str | None) -> list[str]:
    """把 docstring 渲染为正文段落。"""
    if not doc or not doc.strip():
        return ["_（暂无说明）_", ""]
    lines = [_prose(line.rstrip()) for line in doc.strip().splitlines()]
    return lines + [""]


def _render_callables(
    items: list[ApiFunction], level: int, title: str, column: str
) -> list[str]:
    """渲染一组函数/方法：概览表格 + 仅对含细节的条目展开明细小节。"""
    if not items:
        return []
    out = [f"{'#' * level} {title}", "", f"| {column} | 说明 |", "| --- | --- |"]
    for item in items:
        out.append(f"| {_cell(_code(item.display))} | {_cell(_brief(item))} |")
    out.append("")

    details = [item for item in items if _needs_detail(item)]
    for item in details:
        out += [f"{'#' * (level + 1)} `{item.display}`", ""]
        if item.decorators:
            out += [f"装饰器：{'、'.join(_code(d) for d in item.decorators)}", ""]
        out += _render_doc(item.doc)
    return out


def render_module(module: ApiModule) -> list[str]:
    """渲染一个模块的 Markdown 片段。"""
    out: list[str] = [f"## `{module.dotted}`", "", f"源码：{_source_link(module)}", ""]
    out += _render_doc(module.doc)

    if module.constants:
        out += ["### 模块常量", "", "| 名称 | 值 |", "| --- | --- |"]
        out += [f"| {_cell(name)} | {_cell(value)} |" for name, value in module.constants]
        out.append("")

    for cls in module.classes:
        out += [f"### `class {cls.display}`", ""]
        out += _render_doc(cls.doc)
        out += _render_callables(cls.methods, level=4, title="方法", column="方法")

    out += _render_callables(module.functions, level=3, title="模块函数", column="函数")
    return out


def render_file(
    slug: str, title: str, summary: str, modules: list[ApiModule], generated_at: str
) -> str:
    """渲染一个输出文件的完整内容。"""
    n_cls = sum(len(m.classes) for m in modules)
    n_fn = sum(len(m.functions) for m in modules) + sum(
        len(c.methods) for m in modules for c in m.classes
    )

    lines = [
        GENERATED_BANNER,
        "",
        f"# {title} API 参考",
        "",
        summary,
        "",
        f"覆盖 {len(modules)} 个模块、{n_cls} 个公开类、{n_fn} 个公开函数/方法"
        f"（生成于 {generated_at}）。",
        "",
        "> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，"
        "表格中标注 _—_ 表示该符号尚未编写 docstring。",
        "",
        "## 模块一览",
        "",
        "| 模块 | 类 | 函数 |",
        "| --- | --- | --- |",
    ]
    for m in modules:
        anchor = "#" + _anchor(m.dotted)
        n_fn_mod = len(m.functions) + sum(len(c.methods) for c in m.classes)
        lines.append(f"| [{_code(m.dotted)}]({anchor}) | {len(m.classes)} | {n_fn_mod} |")
    lines += ["", "---", ""]

    for m in modules:
        lines += render_module(m)
        lines += ["---", ""]

    return "\n".join(lines).rstrip() + "\n"


def render_index(files: list[tuple[str, str, str]], generated_at: str) -> str:
    """渲染 `docs/api/README.md` 索引。"""
    lines = [
        GENERATED_BANNER,
        "",
        "# API 参考",
        "",
        "本目录由 `tools/gen_api_docs.py` 从源码静态解析生成，"
        "**与代码逐次同步、不要手工编辑**。",
        "",
        "重新生成：",
        "",
        "```bash",
        "python tools/gen_api_docs.py          # 生成/覆盖",
        "python tools/gen_api_docs.py --check  # 校验是否与源码一致（CI 用）",
        "```",
        "",
        "## 收录范围",
        "",
        "- **包含**：模块顶层公开类/函数、类的公开方法与 `__init__`、"
        "模块级全大写常量；",
        "- **不含**：私有成员（`_` 开头）、第三方库符号；",
        "- **Qt 事件覆写**（`paintEvent`、`mouse*Event`、`resizeEvent` 等）不写"
        " docstring，由生成器按方法名统一标注语义；",
        "- 无参数且无说明的 `__init__`（如多数控件）不单列，类说明已覆盖。",
        "",
        "生成器只读源码（`ast` 静态解析），**不导入任何模块**，因此离线可跑、"
        "不会拉起 cv2 / torch / PySide6 等重依赖。",
        "",
        f"生成时间：{generated_at}",
        "",
        "| 文档 | 内容 |",
        "| --- | --- |",
    ]
    for slug, title, summary in files:
        lines.append(f"| [{title}]({slug}.md) | {summary} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def build(out_dir: pathlib.Path) -> dict[pathlib.Path, str]:
    """生成全部文件内容（不落盘），返回 {路径: 文本}。"""
    import datetime

    generated_at = datetime.date.today().isoformat()
    result: dict[pathlib.Path, str] = {}
    index_rows: list[tuple[str, str, str]] = []

    for slug, target_dir, title, summary in TARGETS:
        modules = [m for m in collect(target_dir, slug) if not m.is_empty]
        result[out_dir / f"{slug}.md"] = render_file(slug, title, summary, modules, generated_at)
        index_rows.append((slug, title, summary))

    result[out_dir / "README.md"] = render_index(index_rows, generated_at)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从源码生成 API 参考文档")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录（默认 docs/api）")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只校验：已生成内容与磁盘不一致时退出码为 1，不写文件",
    )
    args = parser.parse_args(argv)

    out_dir = pathlib.Path(args.out)
    files = build(out_dir)

    if args.check:
        stale = []
        for path, text in files.items():
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path)
        if stale:
            print("以下 API 文档与源码不一致，请重跑 python tools/gen_api_docs.py：")
            for p in stale:
                print("  -", p)
            return 1
        print(f"API 文档已是最新（{len(files)} 个文件）")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
        try:
            shown = path.relative_to(ROOT)
        except ValueError:  # 输出到仓库之外（如临时目录预览）
            shown = path
        print("写入", shown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
