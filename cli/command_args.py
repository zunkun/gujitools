"""
File: cli/command_args.py
向后兼容转发模块（deprecated）。

`CommandArgs` 与 `InitArgs` 已迁入中立层 `core.args`，以解除
`functions` → `cli` 的反向依赖（详见 core/args.py 与 core/command_spec.py）。
本模块仅做转发，保留旧导入路径可用。

新代码请直接：
    from core.args import CommandArgs, InitArgs
"""

from core.args import ArgsProvider, CommandArgs, InitArgs  # noqa: F401

__all__ = ["CommandArgs", "InitArgs", "ArgsProvider"]
