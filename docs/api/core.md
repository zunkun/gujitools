<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# core API 参考

中立共享层：CLI 与 desktop 都依赖且语义必须一致的契约

覆盖 4 个模块、9 个公开类、31 个公开函数/方法（生成于 2026-09-17）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`core.args`](#coreargs) | 3 | 8 |
| [`core.command_spec`](#corecommand_spec) | 1 | 6 |
| [`core.reporter`](#corereporter) | 3 | 11 |
| [`core.result`](#coreresult) | 2 | 6 |

---

## `core.args`

源码：[`core/args.py`](../../core/args.py)

File: core/args.py
命令参数容器与只读接口协议。

本模块从中立层提供参数容器，使 `functions` 层不再需要反向导入 `cli`：

- `ArgsProvider`：只读协议。`functions` 只依赖这个 Protocol，不再依赖具体容器类，
  因此 cli 与 desktop 双方都可以传入各自的实现；
- `CommandArgs`：标准容器（原 `cli.command_args.CommandArgs` 迁入），
  负责注入默认值、标准化 input/output/workers 等；
- `InitArgs`：init 命令专用容器，保留原始参数、不注入默认值
  （原 `cli.init_args.InitArgs` 迁入）。

默认值不再在本文件逐条硬编码，而是从 `core.command_spec` 读取，
保证与 GUI 表单使用同一份定义。

### `class ArgsProvider(Protocol)`

参数只读协议。

`functions` 层只要求「能按 key 取参」，不关心实现来自 argparse、
YAML 配置还是 Qt 表单。满足此协议的对象即可直接传入 FunctionBase。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get(key: str, default: Any=None) -> Any` | 按 key 获取参数值，缺失或为 None 时返回 default。 |

### `class CommandArgs`

解析后参数的轻量容器。

通过 `get(key, default)` 按字典风格获取参数，兼容 FunctionBase 的使用方式。
默认值与校验规则统一定义在 `core.command_spec.COMMAND_SPECS`。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(**kwargs)` | 构造参数容器并标准化全部参数。 |
| `get(key: str, default: Any=None) -> Any` | 按字典风格获取参数。 |
| `as_dict() -> Dict[str, Any]` | 返回参数快照（浅拷贝），供序列化到运行配置文件。 |
| `validate() -> None` | 按命令规格校验参数；不通过抛 ValueError，不做任何 I/O 写操作。 |

##### `__init__(**kwargs)`

构造参数容器并标准化全部参数。

接收任意关键字参数（常来自 argparse.Namespace 或配置字典），提取
command 后调用 _build_args 注入默认值并标准化 input/output/workers 等。

##### `validate() -> None`

按命令规格校验参数；不通过抛 ValueError，不做任何 I/O 写操作。

校验规则来自 `CommandSpec.validators`，与 GUI 共用同一份定义，
避免「命令行拒绝、界面放过」这类不一致。

### `class InitArgs(ArgsProvider)`

`init` 命令专用参数容器：保留用户显式传入的原始参数。

与 `CommandArgs` 不同，本容器**不添加任何默认值**、不标准化路径——
因为 init 需要区分「用户显式给了 -i/-o」与「用了默认值」。
实现 ArgsProvider 协议，故可直接传入 FunctionBase。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(raw: Optional[Dict[str, Any]]=None)` | 参数: |
| `get(key: str, default: Any=None) -> Any` | 仅在用户显式提供时返回其值，否则返回 default（不注入任何默认值）。 |
| `as_dict() -> Dict[str, Any]` | — |

##### `__init__(raw: Optional[Dict[str, Any]]=None)`

参数:
    raw: 原始参数字典。若为 None 则回退读取 sys.argv
         （直接构造 InitArgs() 时的便利行为）。

---

## `core.command_spec`

源码：[`core/command_spec.py`](../../core/command_spec.py)

File: core/command_spec.py
命令规格：参数默认值、枚举取值与校验规则的**唯一事实来源**。

设计目标：
- cli 侧（`CommandArgs._build_args`）与 desktop 侧（`print_params.DEFAULT_PARAMS`）
  原先各维护一份默认值，改一处必漏另一处；本模块把这些定义收敛到一处；
- 枚举值（纸张、方向、输出类型等）与校验规则同理，避免「命令行拒绝、界面放过」；
- 本模块是纯数据 + 纯函数，不导入任何上层模块，也不做 I/O。

新增命令或参数时，只需在 `COMMAND_SPECS` 登记一次。

### `class CommandSpec`

单个命令的参数规格。

属性:
    name: 命令名。
    defaults: 参数名 → 默认值。用户未显式提供时注入。
    validators: 校验函数列表，每个函数接收 ArgsProvider 并可能抛 ValueError。
    ui_groups: GUI 表单分组（可选），供 desktop 面板生成表单时参考。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `normalize_margin(value: Any, default: Optional[List[float]]=None) -> Optional[List[float]]` | 把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左]。 |
| `validate_border(border: Any) -> None` | 校验 border 参数；支持 None / "30" / "20,30" / "20,30,25" / "20,30,20,25"。 |
| `parse_color(value: Any) -> Tuple[int, int, int]` | 解析颜色为 (r, g, b) 整数元组，取值域 [0,255]。 |
| `validate_color_fields(args) -> None` | 校验 print 命令中的颜色参数（title_color / page_number_color）。 |
| `get_spec(command: Optional[str]) -> Optional[CommandSpec]` | 按命令名取规格；未登记的命令返回 None。 |
| `supported_commands() -> Tuple[str, ...]` | 返回所有已登记的命令名。 |

#### `normalize_margin(value: Any, default: Optional[List[float]]=None) -> Optional[List[float]]`

把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左]。

实现委托 utils.margin_utils.normalize_margin（最低层），使命令行、
GUI 表单与 PDF 生成三方共用同一份规则，不再各自实现。

#### `parse_color(value: Any) -> Tuple[int, int, int]`

解析颜色为 (r, g, b) 整数元组，取值域 [0,255]。

实现委托 utils.color_utils.parse_color（最低层），命令行与 GUI 共用，
非法输入抛 ValueError，不做静默降级。

---

## `core.reporter`

源码：[`core/reporter.py`](../../core/reporter.py)

File: core/reporter.py
功能模块（functions/）向宿主汇报的结构化事件通道。

**为什么需要这一层**

`functions/` 是 CLI 与 desktop 共用的核心层，但它同时要做两件事：
给人看的日志（「输入路径：…」「处理完成: x.jpg」）与给程序读的信号
（当前进度、每页检测框、图片尺寸）。历史上这两件事**都**走 `print()`，
于是 desktop 侧只能在 stdout 上跑正则去把信号捞回来：

    _PROGRESS_PAIR = re.compile(r"(?:进度|图片加载进度|写入进度)\s*[:：]?\s*(\d+)\s*/\s*(\d+)")

这种「文案即契约」的耦合有三个必然的坏结果：
1. 改一句中文提示就可能静默断掉 GUI 进度条 / 框入库，且没有任何测试会红；
2. 并发路径下 print 是**非原子**的（`\r` 与 `\n` 混用、线程池多线程同时写），
   正则偶尔会漏读一行，进度就少一格；
3. desktop 侧要复刻 `functions/` 的文案格式，两处必须同步维护。

**本模块的做法**

把「机器可读信号」从「人类文案」里剥离出来，走结构化回调：

    reporter.progress(done, total)          # 进度
    reporter.event("page_boxes", image=…, left=…, right=…)   # 结构化负载

`CoreReporter` 是**空实现**（Null Object）：不注入 reporter 时，所有方法都是
no-op，行为与「只 print 日志」完全一致 —— 因此 CLI 路径零改动、零风险。

各层的分工：
- `core/`：本模块（事件协议定义）。只依赖标准库，是依赖图上的叶子。
- `functions/`：在关键节点调用 `self.reporter.*`，**同时保留**人类可读的 print。
- `utils/pdf_utils.py`：同样接受可选 reporter（extract 的渲染在 utils 层）。
- `cli/`：不注入 → 空实现，输出与人读日志不变。
- `desktop/`：注入 `JsonLinesReporter`，把事件直接写成 JSON Lines。

⚠️ 渐进式迁移约定：本轮先把「有明确机器读者的信号」结构化（进度 / 检测框 /
图片尺寸），**人类日志仍走 print**，由 desktop 的 stdout 兜底层照收，
保证日志视图一行不少。后续可继续把高频日志也搬到 `reporter.log()`。

### 模块常量

| 名称 | 值 |
| --- | --- |
| EVENT_PROGRESS | `"progress"` |
| EVENT_PAGE_BOXES | `"page_boxes"` |
| EVENT_PAGE_SIZE | `"page_size"` |

### `class Reporter(Protocol)`

功能模块报告运行时信息的只读协议。

只要求实现三个方法，因此任何对象（包括 `CoreReporter`、测试桩、
desktop 的 JSON Lines 实现）都能直接充当 reporter，无需继承。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `progress(done: int, total: int) -> None` | 报告已完成数量与总数。 |
| `event(name: str, **payload: Any) -> None` | 报告一条具名结构化事件（name 取 EVENT_* 常量）。 |
| `log(message: str) -> None` | 报告一条人类可读日志（可选实现，缺省等价于 print）。 |

### `class CoreReporter`

空实现（Null Object）：所有汇报都被吞掉。

`functions/` 的默认 reporter 就是它 —— 不注入时功能模块的行为与
「只有 print」的历史实现逐字节一致，CLI 因此完全不受影响。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `progress(done: int, total: int) -> None` | — |
| `event(name: str, **payload: Any) -> None` | — |
| `log(message: str) -> None` | — |

### `class CallbackReporter`

把汇报转成回调的轻量适配器，便于测试与复用。

参数 sink 收到 ``(name, payload_dict)``；``progress``/``log`` 也统一
映射为同名事件，调用方不必实现三个方法。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(sink: Callable[[str, Dict[str, Any]], None])` | — |
| `progress(done: int, total: int) -> None` | — |
| `event(name: str, **payload: Any) -> None` | — |
| `log(message: str) -> None` | — |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `normalize_reporter(reporter: Optional[Reporter]) -> Reporter` | None 一律视作 NULL_REPORTER，省掉调用点的判空。 |

---

## `core.result`

源码：[`core/result.py`](../../core/result.py)

File: core/result.py
统一的阶段结果与状态语义。

背景：同一件事在两侧各有表述——
- cli 侧用进程退出码：0 / 1 / 130；
- desktop 侧用状态字符串：pending / running / success / failed / cancelled，
  并在 runner.py 与 store 中各自维护一份映射。

本模块把二者收敛为单一枚举 + 双向转换，任一入口都从这里取值。

### `class StageStatus(str, Enum)`

阶段状态。继承 str 以便直接与 JSON / 数据库中的字符串比较。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `from_exit_code(code: int) -> 'StageStatus'` | 退出码 → 状态：0 成功；130 中断（Ctrl+C）；其余失败。 |
| `to_exit_code() -> int` | 状态 → 退出码（CLI 进程退出用）。 |

### `class StageResult`

功能/阶段执行的统一结果。

取代原先「cli 只看退出码、desktop 只看 result dict」的碎片化传递：
两侧都拿到同一个结构，各自取所需字段渲染。

属性:
    status: 标准化状态。
    exit_code: 对应退出码，供 CLI 直接使用。
    output: 输出目录（若有）。
    processed: 已处理数量。
    status_counts: 各处理状态计数（success/skipped/error…）。
    message: 失败原因或补充说明。
    raw: 功能模块原始返回字典（保留供桥接期使用）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `from_function_result(result: Optional[Dict[str, Any]], status: str=StageStatus.SUCCESS.value, message: Optional[str]=None) -> 'StageResult'` | 由 FunctionBase.execute() 的返回字典构造。 |
| `to_dict() -> Dict[str, Any]` | 转为可 JSON 序列化的字典。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `exit_code_for(status: str) -> int` | 字符串状态 → 退出码；未知状态按失败处理。 |
| `status_for_exit_code(code: int) -> str` | 退出码 → 字符串状态。 |

---
