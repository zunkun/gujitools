"""
File: core/__init__.py
中立共享层：不依赖 cli、desktop、functions 任何一方。

本层存放「两个入口（命令行 /desktop）都需要，且语义必须完全一致」的东西：

- `command_spec`：命令的参数名、默认值、枚举取值、校验规则的**唯一事实来源**；
- `args`：参数容器（`CommandArgs`）与只读接口协议（`ArgsProvider`）；
- `result`：统一的阶段结果与状态语义（取代 cli 的退出码 / desktop 的状态字符串双份定义）；
- `reporter`：功能模块向宿主汇报结构化事件的通道协议（`Reporter` / `CoreReporter`）。
  functions 调 `reporter.progress/event`，cli 用空实现、desktop 注入 JSON Lines 实现，
  两端不再靠正则解析中文提示文案。

依赖方向（严格单向）：
    utils  ←  core  ←  cli
                     ←  functions
                     ←  desktop

core 只允许依赖标准库与 utils，禁止反向引用三个上层。
"""

from core.args import ArgsProvider, CommandArgs, InitArgs
from core.reporter import (
    EVENT_PAGE_BOXES,
    EVENT_PAGE_SIZE,
    EVENT_PROGRESS,
    NULL_REPORTER,
    CallbackReporter,
    CoreReporter,
    Reporter,
    normalize_reporter,
)
from core.result import (
    STAGE_STATUS_LABELS,
    StageResult,
    StageStatus,
    exit_code_for,
)
from core.command_spec import (
    COMMAND_SPECS,
    PAPER_SIZES,
    PRINT_DEFAULTS,
    CommandSpec,
    get_spec,
    normalize_margin,
    supported_commands,
)

__all__ = [
    "ArgsProvider",
    "CommandArgs",
    "InitArgs",
    "Reporter",
    "CoreReporter",
    "CallbackReporter",
    "NULL_REPORTER",
    "normalize_reporter",
    "EVENT_PROGRESS",
    "EVENT_PAGE_BOXES",
    "EVENT_PAGE_SIZE",
    "StageResult",
    "StageStatus",
    "STAGE_STATUS_LABELS",
    "exit_code_for",
    "COMMAND_SPECS",
    "CommandSpec",
    "PRINT_DEFAULTS",
    "PAPER_SIZES",
    "get_spec",
    "normalize_margin",
    "supported_commands",
]
