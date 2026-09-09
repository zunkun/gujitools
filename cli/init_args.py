"""
File: cli/init_args.py
init 命令的原始参数容器。

与 `CommandArgs` 不同，此容器不添加任何默认值，仅保留用户显式传入的参数。
这样 `InitFunction` 能正确区分用户是否提供了 `-i/--input` 和 `-o/--output`，
从而决定是否交互式询问。

提供简单的 `.get()` 方法，兼容 `InitFunction` 的使用方式。
"""

from typing import Any, Dict, Optional


class InitArgs:
    """init 命令的原始参数容器，不填充默认值。"""

    def __init__(self, raw_kwargs: Dict[str, Any]):
        """
        参数:
            raw_kwargs: 从 argparse.Namespace 提取的原始参数字典
                        （已过滤掉 command、config 等无关字段）。
        """
        self._data = raw_kwargs

    def get(self, key: str, default: Any = None) -> Any:
        """获取参数，若不存在则返回默认值。"""
        return self._data.get(key, default)
