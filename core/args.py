"""
File: core/args.py
命令参数容器与只读接口协议。

本模块从中立层提供参数容器，使 `functions` 层不再需要反向导入 `cli`：

- `ArgsProvider`：只读协议。`functions` 只依赖这个 Protocol，不再依赖具体容器类，
  因此 cli 与 desktop 双方都可以传入各自的实现；
- `CommandArgs`：标准容器（原 `cli.command_args.CommandArgs` 迁入），
  负责注入默认值、标准化 input/output/workers 等；
- `default_workers()` / `default_worker_cap()` / `MAX_DEFAULT_WORKERS` /
  `MAX_DEFAULT_DETECT_WORKERS`：默认并发数的唯一来源（函数层、检测、提取都从
  这里取，不许各自写 `cpu_count()`；`detect` 的上限与通用值不同，见
  `_COMMAND_DEFAULT_WORKER_CAP`）。
- `InitArgs`：init 命令专用容器，保留原始参数、不注入默认值
  （原 `cli.init_args.InitArgs` 迁入）。

默认值不再在本文件逐条硬编码，而是从 `core.command_spec` 读取，
保证与 GUI 表单使用同一份定义。
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.command_spec import get_spec, normalize_margin

#: 函数层（functions/base.execute、检测、提取）的**默认并发上限**。
#:
#: 为什么不直接用 CPU 核数：一张 5000×4400 的页在去底/裁剪时要 ~350MB 瞬时内存
#: （PIL RGB 68MB + numpy 拷贝 68MB + 灰度 23MB + 掩码/输出若干），并发数直接乘
#: 这个数就是峰值内存。本机（6 核 12 线程）实测同一批 12 张大页：
#:
#: | 线程数 | 峰值内存 | 耗时 |
#: |---|---|---|
#: | 12 | 4266MB | 8.02s |
#: | 6  | 2153MB | 7.12s |
#: | 4  | 1372MB | 7.56s |
#: | 2  |  706MB | 10.31s |
#:
#: 超过核数只是抢核 + 抢内存带宽：12 线程峰值是 4 线程的 3 倍，反而更慢。
#: 故默认收敛到 4（与 desktop 的 SUBMIT_WORKERS 一致），**用户显式 --workers N
#: 不受影响**——那是用户自己的选择。性能现场见 .workbuddy/perf/。
MAX_DEFAULT_WORKERS = 4

MAX_DEFAULT_DETECT_WORKERS = 8

#: 命令 → 默认并发**上限**（未列出的用 `MAX_DEFAULT_WORKERS`）。
#:
#: 为什么 `detect` 单独放宽到 `MAX_DEFAULT_DETECT_WORKERS`：它**每张图只
#: imread/BGR 一次**（1669×2746 约 13MB、5000×4400 约 68MB），而且推理跑在
#: **常驻 YOLO 服务**里、客户端线程只是等结果——与去底/裁剪的 ~350MB/张完全
#: 不是一个量级。实测同一批 320 张：4 线程 52.6s / 8 线程 40.4s / 12 线程
#: 39.2s，**8 线程即饱和**（12 线程只快 3%，却让客户端每线程多攥一张解码图）。
#: 其余命令仍取 4。
_COMMAND_DEFAULT_WORKER_CAP = {"detect": MAX_DEFAULT_DETECT_WORKERS}


def default_worker_cap(command: str | None = None) -> int:
    """该命令的默认并发**上限**（与机器核数无关）。

    `static/guji.yaml` 的示例值、文档表格与护栏都按它写：改上限只需改
    `core/args.py` 这一处，别处不必跟着动。
    """
    return _COMMAND_DEFAULT_WORKER_CAP.get(command or "", MAX_DEFAULT_WORKERS)


def default_workers(files: int | None = None, command: str | None = None) -> int:
    """默认并发数：``min(该命令的上限, CPU 核数)``；给了张数就再按张数收敛。

    `files` 传待处理张数（如 3 张图没必要开 4 个线程），None 表示不按张数收敛。
    `command` 传命令名以取该命令的上限（见 `default_worker_cap`），不传按通用上限。
    """
    value = max(1, min(default_worker_cap(command), multiprocessing.cpu_count()))
    if files is not None:
        value = max(1, min(value, int(files)))
    return value


#: 默认值是 `None` 但语义为数字的键——没法从默认值推断类型，只能显式登记。
#: 其余数字键（`zoom`/`dpi`/`batch_size`/`area`/`sealarea`…）都按**默认值的类型**
#: 自动推断，所以这里只有这三个。`tests/selftests/arg_types.py` 会检查：这个集合里的
#: 每个键都真的存在于某个 CommandSpec 里（键被改名/删除时会红）。
_NUMERIC_KEYS_WITH_NONE_DEFAULT = frozenset(
    {"start", "end", "page_number_end_page"}
)


def _coerce_scalar(key: str, value: Any, default: Any) -> Any:
    """把配置里**写成字符串**的标量转回本来的类型，转不了就给一句人话。

    起因（2026-09-26 审计实测）：`guji.yaml` 里给数字加引号（`zoom: "2"`）是很自然
    的写法，而 `CommandArgs` 原样保留字符串，于是校验器 `"2" < 1` 抛
    `TypeError: '<' not supported between instances of 'str' and 'int'`；而
    `cli/__main__.py` 只捕获 `ValueError/FileNotFoundError` → 用户拿到的是
    Python traceback，而不是「参数错误：zoom 需要整数」。

    **布尔键更要命**：`clean: "false"`（加了引号）在 Python 里是**真值**，
    会让本来"只清输出目录"的开关变成真的去删目录。所以字符串的 true/false
    也要认，认不出来的直接报错，绝不猜。

    规则：按默认值的类型转 —— `int`/`float` 转数字，`bool` 认常见真假写法；
    其它类型（含默认值 None 的非数字键）原样返回。
    """
    if not isinstance(value, str):
        return value
    if isinstance(default, bool):
        text = value.strip().lower()
        if text in _TRUE_WORDS:
            return True
        if text in _FALSE_WORDS:
            return False
        raise ValueError(f"{key} 需要布尔值(true/false)，当前={value!r}")
    if isinstance(default, int):
        want, label = int, "整数"
    elif isinstance(default, float):
        want, label = float, "数字"
    elif key in _NUMERIC_KEYS_WITH_NONE_DEFAULT:
        want, label = int, "整数"
    else:
        return value
    text = value.strip()
    try:
        return want(text)
    except ValueError:
        raise ValueError(f"{key} 需要{label}，当前={value!r}") from None


#: 字符串形式的真假写法（YAML 里加引号会得到字符串）
_TRUE_WORDS = frozenset({"true", "1", "yes", "on", "y", "t"})
_FALSE_WORDS = frozenset({"false", "0", "no", "off", "n", "f", ""})


@runtime_checkable
class ArgsProvider(Protocol):
    """参数只读协议。

    `functions` 层只要求「能按 key 取参」，不关心实现来自 argparse、
    YAML 配置还是 Qt 表单。满足此协议的对象即可直接传入 FunctionBase。
    """

    def get(self, key: str, default: Any = None) -> Any:
        """按 key 获取参数值，缺失或为 None 时返回 default。"""
        ...


class CommandArgs:
    """解析后参数的轻量容器。

    通过 `get(key, default)` 按字典风格获取参数，兼容 FunctionBase 的使用方式。
    默认值与校验规则统一定义在 `core.command_spec.COMMAND_SPECS`。
    """

    def __init__(self, **kwargs):
        """构造参数容器并标准化全部参数。

        接收任意关键字参数（常来自 argparse.Namespace 或配置字典），提取
        command 后调用 _build_args 注入默认值并标准化 input/output/workers 等。
        """
        command = kwargs.get("command", None)
        self.command = command
        self.args: Dict[str, Any] = {"command": command}
        self._build_args(**kwargs)

    def get(self, key: str, default: Any = None) -> Any:
        """按字典风格获取参数。"""
        return self.args.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.args

    def as_dict(self) -> Dict[str, Any]:
        """返回参数快照（浅拷贝），供序列化到运行配置文件。"""
        return dict(self.args)

    # ---------- 内部：取值与标准化 ----------
    def _get_with_default(self, key: str, default: Any, kwargs: dict) -> Any:
        """安全取值：仅当键不存在或值为 None 时返回默认值。"""
        if key not in kwargs or kwargs[key] is None:
            return default
        return kwargs[key]

    def _build_args(self, **kwargs) -> None:
        """按命令规格注入默认值并标准化参数（只做内存级处理，不触及磁盘 I/O）。"""
        # -------- 通用参数（所有命令共享） --------
        input_raw = self._get_with_default("input", ".", kwargs)
        if isinstance(input_raw, str) and input_raw.strip() == "":
            input_raw = "."
        self.args["input"] = Path(input_raw).expanduser().resolve()
        self.args["output"] = kwargs.get("output", None)
        self.args["workers"] = _coerce_scalar(
            "workers",
            self._get_with_default("workers", default_workers(command=self.command), kwargs),
            default_workers(command=self.command),
        )
        # `clean` 是破坏性开关（会 rmtree 输出目录），字符串的 "false" 必须
        # 认成 False —— 否则用户照 YAML 习惯加引号，反而把目录删了。
        self.args["clean"] = _coerce_scalar(
            "clean", self._get_with_default("clean", False, kwargs), False
        )

        spec = get_spec(self.command)
        if spec is None:
            return  # 未登记的命令（如 help）不做额外处理

        # -------- 命令特有参数：默认值全部来自 CommandSpec --------
        for key, default in spec.defaults.items():
            if key == "page_margins":
                # margin 族支持 CSS 简写，需先标准化。
                # ⚠️ 非法输入要**报错**，不能静默回落默认（2026-09-26 审计）：
                #    `page_margins: "abc"` 以前会悄悄变成 [20,20,20,20]，用户写错
                #    边距却毫无反馈、输出与预期不符也无从发现；而同一个 print 的
                #    `title_margins` 是会明确报错的——两处行为本该一致。
                raw_margins = kwargs.get(key)
                if raw_margins not in (None, "") and normalize_margin(
                    raw_margins, default=None
                ) is None:
                    raise ValueError(
                        f"{key} 应为 1~4 个数字（mm，CSS 简写），当前={raw_margins!r}"
                    )
                self.args[key] = normalize_margin(
                    raw_margins, default=list(default)
                )
            elif key in ("left_page_margins", "right_page_margins"):
                raw_side = kwargs.get(key)
                if raw_side not in (None, "") and normalize_margin(
                    raw_side, default=None
                ) is None:
                    raise ValueError(
                        f"{key} 应为 1~4 个数字（mm，CSS 简写），当前={raw_side!r}"
                    )
                self.args[key] = normalize_margin(raw_side, default=None)
            else:
                # 数字键要容忍「配置里写成字符串」（`zoom: "2"`），否则校验器里
                # 的数值比较会抛 TypeError 穿透到用户面前（见 _coerce_numeric）。
                self.args[key] = _coerce_scalar(
                    key, self._get_with_default(key, default, kwargs), default
                )

    def validate(self) -> None:
        """按命令规格校验参数；不通过抛 ValueError，不做任何 I/O 写操作。

        校验规则来自 `CommandSpec.validators`，与 GUI 共用同一份定义，
        避免「命令行拒绝、界面放过」这类不一致。
        """
        cmd = self.command
        if cmd is None:
            raise ValueError("未指定子命令")

        input_p: Path = self.get("input")
        workers = self.get("workers")

        if workers is not None and workers <= 0:
            raise ValueError(f"workers 必须大于0，当前={workers}")
        if not isinstance(input_p, Path):
            raise ValueError(f"input 必须为路径对象，得到 {type(input_p)}")
        if not input_p.exists():
            raise FileNotFoundError(f"输入路径不存在：{input_p.resolve()}")

        spec = get_spec(cmd)
        if spec is None:
            raise ValueError(f"不支持的命令 {cmd}")
        for check in spec.validators:
            check(self)


class InitArgs(ArgsProvider):
    """`init` 命令专用参数容器：保留用户显式传入的原始参数。

    与 `CommandArgs` 不同，本容器**不添加任何默认值**、不标准化路径——
    因为 init 需要区分「用户显式给了 -i/-o」与「用了默认值」。
    实现 ArgsProvider 协议，故可直接传入 FunctionBase。
    """

    def __init__(self, raw: Optional[Dict[str, Any]] = None):
        """
        参数:
            raw: 原始参数字典。若为 None 则回退读取 sys.argv
                 （直接构造 InitArgs() 时的便利行为）。
        """
        if raw is None:
            raw = self._from_argv()
        self.raw: Dict[str, Any] = dict(raw)

    @staticmethod
    def _from_argv() -> Dict[str, Any]:
        """从命令行提取 key=value / -k v 形式的原始参数（不经过 argparse）。"""
        import sys

        result: Dict[str, Any] = {}
        argv = sys.argv[1:]
        # 跳过 "init" 本身
        if argv and argv[0] == "init":
            argv = argv[1:]
        index = 0
        while index < len(argv):
            token = argv[index]
            if token.startswith("--"):
                key = token[2:]
                if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
                    result[key] = argv[index + 1]
                    index += 2
                    continue
                result[key] = True
            index += 1
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """仅在用户显式提供时返回其值，否则返回 default（不注入任何默认值）。"""
        value = self.raw.get(key)
        return default if value is None else value

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.raw)
