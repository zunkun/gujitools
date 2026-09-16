"""
File: cli/init_args.py
向后兼容转发模块（deprecated）。

`InitArgs` 已迁入中立层 `core.args`，使 `functions` 层无需反向依赖 cli。
本模块仅做转发，保留旧导入路径可用。

新代码请直接：
    from core.args import InitArgs
"""

from core.args import InitArgs  # noqa: F401

__all__ = ["InitArgs"]
