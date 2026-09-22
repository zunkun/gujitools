<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# cli API 参考

命令行入口层：参数解析、子命令调度

覆盖 3 个模块、2 个公开类、8 个公开函数/方法（生成于 2026-09-22）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`cli.__main__`](#cli__main__) | 0 | 3 |
| [`cli.cli_args`](#clicli_args) | 1 | 3 |
| [`cli.config_io`](#cliconfig_io) | 1 | 2 |

---

## `cli.__main__`

源码：[`cli/__main__.py`](../../cli/__main__.py)

File: cli/__main__.py
CLI 启动逻辑：参数解析 → 功能分发 → 结果输出。

流程:
1. `CliArgsParser` 构建 argparse 解析器并解析命令行参数；
2. 如果命令是 run：加载配置文件中的子命令配置块，构造参数对象；
   否则直接使用命令行解析结果（过滤掉 None 值）；
3. 将参数包装为 `core.args.CommandArgs`（标准化参数，不做文件 I/O）；
4. 通过 `get_function()` 工厂方法获取对应功能实例；
5. 调用 `func.execute()` 执行功能；
6. 顶层捕获异常并设置退出码。

退出码约定（与 `core.result.StageStatus` 对齐）:
- 0: 正常完成
- 1: 错误（未知命令、参数错误、配置错误、功能执行失败）
- 130: 用户中断（Ctrl+C）

本模块只保留「命令行外壳」独有的职责：argparse、YAML 覆盖语义、退出码。
参数默认值/校验规则在 `core.command_spec`，执行引擎在 `functions`，
均与 desktop 入口共用，不再各自维护。

注意: `functions` 包延迟导入（在 main() 内部），使 `guji help` 无需加载 cv2/ultralytics。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _DRY_RUN_HINT | `"ERROR: 'detect' 不接受空跑（既未指定 --save，就不会产生任何文件）。      命令行执行 …"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `execute_function(func) -> int` | 执行已构造的功能实例，统一处理退出码与异常。 |
| `execute_command(command: str, command_args) -> int` | 按命令名获取功能实例并执行，返回退出码。 |
| `main() -> int` | 命令行主入口函数，返回进程退出码。 |

#### `execute_function(func) -> int`

执行已构造的功能实例，统一处理退出码与异常。

返回进程退出码；不再直接 sys.exit，便于上层组合与测试。

---

## `cli.cli_args`

源码：[`cli/cli_args.py`](../../cli/cli_args.py)

File: cli/cli_args.py
命令行参数解析模块。

定义所有支持的子命令（extract/crop/rembg/cropremove/help）及其参数。

子命令与别名:
- extract (-e): 从 PDF 提取页面图片
- detect: 检测图片左右文本框坐标（默认不落盘，--save 输出标注图）
- crop: 基于 YOLO 检测裁剪左右文本框
- rembg (-r): 整图去底色/二值化/印章保留
- cropremove (-cr): 复合流程（crop + rembg）
- print: 打印 PDF（仅支持通过 run 命令执行）
- help: 查看命令手册（guji help <command>，内容来自 docs/functions/*.md）

每个子命令的参数定义包含帮助文本（--help 时显示）和类型约束。
所有默认值统一在 CommandArgs._build_args 中维护，此处不设 default。

### `class CliArgsParser`

包装 argparse，定义程序支持的子命令与参数。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__()` | 构造 CLI 参数解析器。 |
| `create_parser() -> argparse.ArgumentParser` | 创建并配置 argparse.ArgumentParser 以及所有子命令。 |
| `parse_args()` | 解析命令行参数并处理别名/帮助命令。 |

##### `__init__()`

构造 CLI 参数解析器。

创建 CliArgsParser 实例时即构建并配置好 argparse.ArgumentParser
及全部子命令（extract/crop/rembg/cropremove/init/run/print/help）。

##### `create_parser() -> argparse.ArgumentParser`

创建并配置 argparse.ArgumentParser 以及所有子命令。

备注：使用 `add_help=False` 并自定义 `-h/--help`，以便统一使用 `utils.help` 中的帮助显示逻辑。

##### `parse_args()`

解析命令行参数并处理别名/帮助命令。

返回 argparse.Namespace。

---

## `cli.config_io`

源码：[`cli/config_io.py`](../../cli/config_io.py)

File: cli/config_io.py
YAML 配置读取：把从 `cli.py` 抽出的配置解析逻辑集中于此。

抽出原因：原实现把文件读取、YAML 解析、错误退出（sys.exit）与命令分发
混在 cli.py 中，使「配置加载」无法被单独测试或复用。现在错误以异常抛出，
由入口层决定如何退出，职责更清晰。

### `class ConfigError(Exception)`

配置文件缺失、格式错误或缺少对应命令块。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `load_yaml_config(path: Path) -> dict` | 加载 YAML 配置文件，返回 dict；解析失败抛 ConfigError。 |
| `load_command_config(path: Path, command: str) -> dict` | 读取指定命令的 YAML 配置块，过滤 None 值。 |

#### `load_command_config(path: Path, command: str) -> dict`

读取指定命令的 YAML 配置块，过滤 None 值。

配置缺失时抛 ConfigError，由调用方决定退出方式。

---
