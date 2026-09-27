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
#: 故默认收敛（与 desktop 的 SUBMIT_WORKERS 一致），**用户显式 --workers N
#: 不受影响**——那是用户自己的选择。性能现场见 .workbuddy/perf/。
#:
#: 2026-09-27：改为**动态预算**（见 machine_worker_budget）——用户反馈
#: 「不能定死 8 或 4，按电脑配置动态调整」。本常量降级为动态预算的**封顶值**；
#: 单页内存靠 `_mask_to_u8`、PIL 位图及时关闭等瘦身手段控制，实测本机
#: 4 vs 8 线程整批耗时基本一致（内存带宽 4 线程即饱和），上调无害。
MAX_DEFAULT_WORKERS = 8

MAX_DEFAULT_DETECT_WORKERS = 8

#: 命令 → 默认并发**上限**（未列出的用 `MAX_DEFAULT_WORKERS`）。
#:
#: 为什么 `detect` 单独放宽到 `MAX_DEFAULT_DETECT_WORKERS`：它**每张图只
#: imread/BGR 一次**（1669×2746 约 13MB、5000×4400 约 68MB），而且推理跑在
#: **常驻 YOLO 服务**里、客户端线程只是等结果——与去底/裁剪的 ~350MB/张完全
#: 不是一个量级。实测同一批 320 张：4 线程 52.6s / 8 线程 40.4s / 12 线程
#: 39.2s，**8 线程即饱和**（12 线程只快 3%，却让客户端每线程多攥一张解码图）。
_COMMAND_DEFAULT_WORKER_CAP = {"detect": MAX_DEFAULT_DETECT_WORKERS}


def _total_physical_memory_gb() -> float:
    """物理内存大小（GB）；取不到（平台冷门/权限受限）返回 0.0，调用方跳过内存维度。"""
    import os as _os
    import sys as _sys

    try:
        if _sys.platform == "win32":
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullTotalPhys / (1024 ** 3)
            return 0.0
        return (
            _os.sysconf("SC_PHYS_PAGES") * _os.sysconf("SC_PAGE_SIZE") / (1024 ** 3)
        )
    except Exception:  # noqa: BLE001 - 探测失败就只用 CPU 维度
        return 0.0


#: 内存维度的换算参数：预算 = 物理内存 × 60%；每个去底/裁剪 worker 峰值
#: 约 350~500MB（位图 + Otsu 中间数组，见 _mask_to_u8 的注释）。
_WORKER_MEM_BUDGET_RATIO = 0.6
_WORKER_MEM_PER_THREAD_MB = 500

_machine_budget_cache: Optional[int] = None


def machine_worker_budget() -> int:
    """按**这台机器**的配置动态算出默认并发预算（物理核 + 内存双约束）。

    - CPU 维度：**物理核数**（psutil 可用则取，否则逻辑核）。去底/裁剪是
      numpy/cv2 的内存带宽型负载，超线程几乎不涨吞吐（实测 4≈8 线程，
      带宽 4 线程即饱和）——按物理核给先验，剩下的超线程兄弟核自然留给
      GUI/系统，不需要再减；
    - 内存维度：物理内存 × 60% ÷ 单 worker 峰值 500MB，至少 2；
    - 两者取小，再封顶 ``MAX_DEFAULT_WORKERS``。结果进程内缓存（配置不会
      在运行中途变）。

    这只是**先验**：真实瓶颈只有跑起来才知道，functions/base 的自适应并发
    会在默认值场景下按实测吞吐微调（见 ``CommandArgs.is_defaulted``）。
    用户显式 ``--workers N`` / 面板数值**不受影响**——那是用户自己的选择。
    """
    global _machine_budget_cache
    if _machine_budget_cache is None:
        logical = multiprocessing.cpu_count() or 4
        physical = _physical_core_count() or logical
        by_cpu = max(2, min(MAX_DEFAULT_WORKERS, physical))
        by_mem = MAX_DEFAULT_WORKERS
        total_gb = _total_physical_memory_gb()
        if total_gb > 0:
            by_mem = max(
                2,
                min(
                    MAX_DEFAULT_WORKERS,
                    int(
                        total_gb
                        * _WORKER_MEM_BUDGET_RATIO
                        * 1024
                        // _WORKER_MEM_PER_THREAD_MB
                    ),
                ),
            )
        _machine_budget_cache = max(2, min(by_cpu, by_mem))
    return _machine_budget_cache


def _physical_core_count() -> int:
    """物理核数（不含超线程）；探测失败返回 0，调用方回落逻辑核。

    psutil 由 ultralytics 带入（检测环境必有）；纯 CLI 环境没有它也能活。"""
    try:
        import psutil  # noqa: PLC0415

        count = psutil.cpu_count(logical=False)
        return int(count) if count else 0
    except Exception:  # noqa: BLE001 - 没有就退回逻辑核
        return 0


def default_worker_cap(command: str | None = None) -> int:
    """该命令的默认并发**上限**。

    通用命令走 ``machine_worker_budget()``（按机器配置动态，≤
    ``MAX_DEFAULT_WORKERS``）；detect 单独放宽到 ``MAX_DEFAULT_DETECT_WORKERS``
    （每张图只在常驻服务里读一次，比去底/裁剪轻得多，见下）。
    """
    cap = _COMMAND_DEFAULT_WORKER_CAP.get(command or "")
    return cap if cap is not None else machine_worker_budget()


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
        self._defaulted_keys: set = set()
        self._build_args(**kwargs)

    def get(self, key: str, default: Any = None) -> Any:
        """按字典风格获取参数。"""
        return self.args.get(key, default)

    def is_defaulted(self, key: str) -> bool:
        """该键的当前值是**注入的默认值**（调用方没显式给/给了 None）吗？

        用途：自适应并发的开关——用户显式 ``--workers 4`` 是自己的选择
        （固定 4 线程执行）；默认值才是"按机器预算的先验"，允许运行时按
        实测吞吐微调（见 functions/base 的波次爬山）。
        """
        return key in self._defaulted_keys

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

        # 记录哪些键是**注入的默认值**（调用方没给/给了 None）：显式指定的值
        # 语义不同——如 workers 用户给了就固定执行，默认值才允许自适应微调
        # （见 CommandArgs.is_defaulted）。
        self._defaulted_keys = {
            key
            for key in ("workers", "clean", *spec.defaults.keys())
            if kwargs.get(key) is None
        }

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
