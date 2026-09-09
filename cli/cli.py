"""
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
"""

import sys
import json
import yaml
from pathlib import Path

from cli.cli_args import CliArgsParser
from cli.command_args import CommandArgs


def load_yaml_config(path: Path) -> dict:
    """加载 YAML 配置文件，支持 .yaml/.yml，返回 dict。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error in {path}: {e}")
        sys.exit(1)


def load_command_config(path: Path, command: str) -> dict:
    """读取指定命令的 YAML 配置块。"""
    if not path.exists():
        print(f"ERROR: config file not found: {path}")
        print("You can create a default config with `guji init`.")
        sys.exit(1)

    full_config = load_yaml_config(path)
    config_data = full_config.get(command)
    if not isinstance(config_data, dict):
        print(f"ERROR: config section '{command}' missing or not an object in {path}")
        sys.exit(1)
    return {key: value for key, value in config_data.items() if value is not None}


def execute_command(command: str, command_args: CommandArgs):
    """通用命令执行器：获取功能实例并执行。"""
    from functions import get_function

    func = get_function(command=command, command_args=command_args)
    if func is None:
        print(f"ERROR: unknown command '{command}'")
        print(f"run 'guji help {command}' for usage")
        sys.exit(1)

    try:
        result = func.execute()
        print("\nProcess completed!")
        if result:
            print(f"Statistics: {result}")
    except KeyboardInterrupt:
        print("\nUser interrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """命令行主入口函数。"""
    # 1. 解析命令行参数（help/version 在此阶段处理并退出，不触发重依赖加载）
    parser = CliArgsParser()
    args = parser.parse_args()
    command = args.command

    # 2. 处理 help/version（已在 parse_args 中处理，这里仅安全返回）
    if command in ("help", "version"):
        return

    if command == "print":
        # print 命令只能通过 run 执行，直接提示用户
        print("ERROR: 'print' command can only be executed via 'guji run print'.")
        sys.exit(1)

    # ---------- run 命令 ----------
    if command == "run":
        subcmd = args.subcommand
        cfg_path = args.config  # 已经是 Path 对象，默认 ./guji.yaml

        config_data = load_command_config(cfg_path, subcmd)

        # 构造参数对象：命令为 subcmd，参数来自配置
        command_args = CommandArgs(command=subcmd, **config_data)

        # 校验参数
        try:
            command_args.validate()
        except (ValueError, FileNotFoundError) as e:
            print(f"ERROR: parameter validation error: {e}")
            sys.exit(1)

        execute_command(subcmd, command_args)
        return

    # ---------- init 命令（特殊处理，不使用 CommandArgs） ----------
    # init 命令需要区分用户是否显式提供了 -i/--input 和 -o/--output，
    # 因此不能使用 CommandArgs（它会填充默认值）。使用 InitArgs 保留原始参数。
    if command == "init":
        from cli.init_args import InitArgs
        from functions.init import InitFunction

        # 提取原始命令行参数（不经过 CommandArgs，避免默认值填充）
        raw_kwargs = {
            k: v
            for k, v in vars(args).items()
            if k not in ("command", "config") and v is not None
        }
        init_args = InitArgs(raw_kwargs)
        func = InitFunction(init_args)

        try:
            result = func.execute()
            print("\nProcess completed!")
            if result:
                print(f"Statistics: {result}")
        except KeyboardInterrupt:
            print("\nUser interrupted.")
            sys.exit(130)
        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
        return

    # ---------- 其他普通子命令（extract/crop/rembg/cropremove） ----------
    # --config 提供基础值；命令行中显式提供的值覆盖配置。
    cli_kwargs = {
        k: v
        for k, v in vars(args).items()
        if k not in ("command", "config") and v is not None
    }
    config_path = getattr(args, "config", None)
    if config_path is not None:
        config_data = load_command_config(config_path, command)
        cli_kwargs = {
            key: value
            for key, value in cli_kwargs.items()
            if not isinstance(value, bool) or value
        }
        config_data.update(cli_kwargs)
        cli_kwargs = config_data
    command_args = CommandArgs(command=command, **cli_kwargs)

    # 参数校验（init 已跳过）
    try:
        command_args.validate()
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: parameter validation error: {e}")
        sys.exit(1)

    execute_command(command, command_args)


if __name__ == "__main__":
    main()
