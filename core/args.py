"""
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
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.command_spec import get_spec, normalize_margin


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
        self.args["workers"] = self._get_with_default(
            "workers", multiprocessing.cpu_count(), kwargs
        )
        self.args["clean"] = self._get_with_default("clean", False, kwargs)

        spec = get_spec(self.command)
        if spec is None:
            return  # 未登记的命令（如 help）不做额外处理

        # -------- 命令特有参数：默认值全部来自 CommandSpec --------
        for key, default in spec.defaults.items():
            if key == "page_margins":
                # margin 族支持 CSS 简写，需先标准化
                self.args[key] = normalize_margin(kwargs.get(key), default=list(default))
            elif key in ("left_page_margins", "right_page_margins"):
                self.args[key] = normalize_margin(kwargs.get(key), default=None)
            else:
                self.args[key] = self._get_with_default(key, default, kwargs)

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
