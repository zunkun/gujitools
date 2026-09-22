"""gujitools 命令行（CLI）包。

⚠️ 本 `__init__.py` **必须存在**（哪怕只有这一行说明）。顶层还有同名的
`cli.py`（命令行可执行入口，打包成 `guji.exe`），而 Python 的 FileFinder
在"目录"与"同名模块文件"之间，**只有目录里真有 `__init__.py` 时目录才算
常规包**；否则 `import cli` 会解析到 `cli.py` 那个文件，`cli.cli_args` 之类
的子模块全部失效。desktop 侧同理（`desktop.py` + `desktop/__init__.py`）。

CLI 的实现放在 `cli/__main__.py`：它既是 `python -m cli` 的入口模块，也可被
`cli.py` 以 `from cli.__main__ import main` 复用。
"""
