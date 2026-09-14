<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# cli API 参考

命令行入口层：参数解析、子命令调度

覆盖 4 个模块、3 个公开类、12 个公开函数/方法（生成于 2026-09-15）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`cli.cli`](#clicli) | 0 | 4 |
| [`cli.cli_args`](#clicli_args) | 1 | 3 |
| [`cli.command_args`](#clicommand_args) | 1 | 3 |
| [`cli.init_args`](#cliinit_args) | 1 | 2 |

---

## `cli.cli`

源码：[`cli/cli.py`](../../cli/cli.py)

File: cli/cli.py
CLI 启动逻辑：参数解析 → 功能分发 → 结果输出。
流程:
1. `CliArgsParser` 构建 argparse 解析器并解析命令行参数；
2. 如果命令是 run：加载配置文件中的子命令配置块，构造参数对象；
   否则直接使用命令行解析结果（过滤掉 None 值）；
3. 将参数包装为 `CommandArgs`（标准化参数，不做文件 I/O）；
4. 通过 `get_function()` 工厂方法获取对应功能实例；
5. 调用 `func.execute()` 执行功能；
6. 顶层捕获异常并设置退出码。

退出码约定:
- 0: 正常完成
- 1: 错误（未知命令、参数错误、配置错误、功能执行失败）
- 130: 用户中断（Ctrl+C）

注意: `functions` 包延迟导入（在 main() 内部），使 `guji help` 无需加载 cv2/ultralytics。

配置行为约定：
- run 命令从配置文件读取当前子命令配置块。
- 普通子命令支持可选 --config；配置值作为基础值，命令行参数优先覆盖。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `load_yaml_config(path: Path) -> dict` | 加载 YAML 配置文件，支持 .yaml/.yml，返回 dict。 |
| `load_command_config(path: Path, command: str) -> dict` | 读取指定命令的 YAML 配置块。 |
| `execute_command(command: str, command_args: CommandArgs)` | 通用命令执行器：获取功能实例并执行。 |
| `main()` | 命令行主入口函数。 |

---

## `cli.cli_args`

源码：[`cli/cli_args.py`](../../cli/cli_args.py)

File: cli/cli_args.py
命令行参数解析模块。

定义所有支持的子命令（extract/crop/rembg/cropremove/help）及其参数。

子命令与别名:
- extract (-e): 从 PDF 提取页面图片
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

## `cli.command_args`

源码：[`cli/command_args.py`](../../cli/command_args.py)

File: cli/command_args.py
命令行参数标准化容器。
将 argparse.Namespace 或 config 字典中的参数统一为功能模块可直接使用的字典结构。
约定:
- 不在此阶段进行文件系统创建/校验（如创建输出目录）；
- `input` 标准化为 Path 并 expanduser().resolve()；
- `output` 保留为原始字符串，由上层功能决定如何解析；
- 各命令的特定参数按默认值注入；
- **所有默认值统一在此维护**，命令行解析器不再设置 default。
- 从 kwargs 取值时，若键不存在或值为 None，则使用默认值。

### `class CommandArgs`

解析后参数的轻量容器。
通过 `get(key, default)` 按字典风格获取参数，兼容 FunctionBase 的使用方式。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(**kwargs)` | 构造参数容器并标准化全部参数。 |
| `get(key: str, default: Any=None) -> Any` | 按字典风格获取参数。 |
| `validate() -> None` | 参数语义校验；全部来源(命令行/config json)统一校验。 |

##### `__init__(**kwargs)`

构造参数容器并标准化全部参数。

接收任意关键字参数（常来自 argparse.Namespace 或配置字典），提取
command 后调用 _build_args 注入默认值并标准化 input/output/workers 等。
所有默认值集中在此维护，命令行解析器不再设置 default。

##### `validate() -> None`

参数语义校验；全部来源(命令行/config json)统一校验。
校验不通过抛出 ValueError，上层捕获并退出程序。
不做IO写操作，不创建目录。

---

## `cli.init_args`

源码：[`cli/init_args.py`](../../cli/init_args.py)

File: cli/init_args.py
init 命令的原始参数容器。

与 `CommandArgs` 不同，此容器不添加任何默认值，仅保留用户显式传入的参数。
这样 `InitFunction` 能正确区分用户是否提供了 `-i/--input` 和 `-o/--output`，
从而决定是否交互式询问。

提供简单的 `.get()` 方法，兼容 `InitFunction` 的使用方式。

### `class InitArgs`

init 命令的原始参数容器，不填充默认值。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(raw_kwargs: Dict[str, Any])` | 参数: |
| `get(key: str, default: Any=None) -> Any` | 获取参数，若不存在则返回默认值。 |

##### `__init__(raw_kwargs: Dict[str, Any])`

参数:
    raw_kwargs: 从 argparse.Namespace 提取的原始参数字典
                （已过滤掉 command、config 等无关字段）。

---
