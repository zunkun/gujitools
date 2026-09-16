"""
File: cli/config_io.py
YAML 配置读取：把从 `cli.py` 抽出的配置解析逻辑集中于此。

抽出原因：原实现把文件读取、YAML 解析、错误退出（sys.exit）与命令分发
混在 cli.py 中，使「配置加载」无法被单独测试或复用。现在错误以异常抛出，
由入口层决定如何退出，职责更清晰。
"""

from __future__ import annotations

from pathlib import Path

import yaml


class ConfigError(Exception):
    """配置文件缺失、格式错误或缺少对应命令块。"""


def load_yaml_config(path: Path) -> dict:
    """加载 YAML 配置文件，返回 dict；解析失败抛 ConfigError。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件根节点应为映射（dict）：{path}")
    return data


def load_command_config(path: Path, command: str) -> dict:
    """读取指定命令的 YAML 配置块，过滤 None 值。

    配置缺失时抛 ConfigError，由调用方决定退出方式。
    """
    if not path.exists():
        raise ConfigError(
            f"config file not found: {path}\n"
            "You can create a default config with `guji init`."
        )
    full_config = load_yaml_config(path)
    config_data = full_config.get(command)
    if not isinstance(config_data, dict):
        raise ConfigError(f"config section '{command}' missing or not an object in {path}")
    return {key: value for key, value in config_data.items() if value is not None}
