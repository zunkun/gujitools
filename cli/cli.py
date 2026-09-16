"""
File: cli/cli.py
CLI 启动逻辑：参数解析 → 功能分发 → 结果输出。

流程:
1. `CliArgsParser` 构建 argparse 解析器并解析命令行参数；
2. 如果命令是 run：加载配置文件中的子命令配置块，构造参数对象；
   否则直接使用命令行解析结果（过滤掉 None 值）；
3. 将参数包装为 `core.args.CommandArgs`（标准化参数，不做文件 I/O）；
4. 通过 `get_function()` 工厂方法获取对应功能实例；
5. 调用 `func.execute()` 执行功能；
6. 顶层捕获异常并设置退出码。

退出码约定（与 `core.result.StageStatus` 对齐）:
- 0: 正常完成
- 1: 错误（未知命令、参数错误、配置错误、功能执行失败）
- 130: 用户中断（Ctrl+C）

本模块只保留「命令行外壳」独有的职责：argparse、YAML 覆盖语义、退出码。
参数默认值/校验规则在 `core.command_spec`，执行引擎在 `functions`，
均与 desktop 入口共用，不再各自维护。

注意: `functions` 包延迟导入（在 main() 内部），使 `guji help` 无需加载 cv2/ultralytics。
"""

import sys

from core.args import CommandArgs, InitArgs
from core.result import StageStatus

from cli.cli_args import CliArgsParser
from cli.config_io import ConfigError, load_command_config

# 需要跳过 parse / 不参与参数构造的键
_META_KEYS = ("command", "config", "subcommand")


def _collect_raw_kwargs(args) -> dict:
    """从 argparse 结果提取排除元键、且值非 None 的参数。"""
    return {
        k: v
        for k, v in vars(args).items()
        if k not in _META_KEYS and v is not None
    }


def execute_function(func) -> int:
    """执行已构造的功能实例，统一处理退出码与异常。

    返回进程退出码；不再直接 sys.exit，便于上层组合与测试。
    """
    try:
        result = func.execute()
    except KeyboardInterrupt:
        print("\nUser interrupted.")
        return StageStatus.CANCELLED.to_exit_code()
    except Exception as exc:
        print(f"\nERROR: {exc}")
        import traceback

        traceback.print_exc()
        return StageStatus.FAILED.to_exit_code()

    print("\nProcess completed!")
    if result:
        print(f"Statistics: {result}")
    return StageStatus.SUCCESS.to_exit_code()


def execute_command(command: str, command_args) -> int:
    """按命令名获取功能实例并执行，返回退出码。"""
    from functions import get_function

    func = get_function(command=command, command_args=command_args)
    if func is None:
        print(f"ERROR: unknown command '{command}'")
        print(f"run 'guji help {command}' for usage")
        return StageStatus.FAILED.to_exit_code()
    return execute_function(func)


def _build_for_run(args) -> CommandArgs:
    """run 命令：配置即全部参数来源。"""
    subcmd = args.subcommand
    config_data = load_command_config(args.config, subcmd)
    return CommandArgs(command=subcmd, **config_data)


def _build_for_subcommand(args, command: str) -> CommandArgs:
    """普通子命令：--config 提供基础值，命令行显式值覆盖之。"""
    cli_kwargs = _collect_raw_kwargs(args)
    config_path = getattr(args, "config", None)
    if config_path is not None:
        config_data = load_command_config(config_path, command)
        # 布尔类型若为 False 视为「未显式开启」，不覆盖配置文件中的 True
        cli_kwargs = {
            key: value
            for key, value in cli_kwargs.items()
            if not isinstance(value, bool) or value
        }
        config_data.update(cli_kwargs)
        cli_kwargs = config_data
    return CommandArgs(command=command, **cli_kwargs)


# detect 不做落盘时，命令行上没有任何产出去处：坐标只会打到 stdout，
# 既没有文件落地，也没有下游步骤读取（crop / cropremove 各自内部会检测）。
# 因此命令行必须显式 --save，否则纯属白算一趟。
_DRY_RUN_HINT = """\
ERROR: 'detect' 不接受空跑（既未指定 --save，就不会产生任何文件）。

    命令行执行 detect 的目的就是把标注图落地，请加上 --save：

        guji detect -i <图片目录> --save            # 输出到 <输入父目录>/detect
        guji detect -i <图片目录> --save -o <输出根目录>

    如果你只是想拿到左右文本框坐标，不需要单独跑 detect：
      - 裁剪：  guji crop -i <图片目录>        （内部自动检测）
      - 裁剪+去底：guji cropremove -i <图片目录>（内部自动检测）
      - 代码调用：functions.detect.detect_page_boxes(img)，无需 --save。
"""


def _reject_dry_run(command: str, command_args: CommandArgs) -> bool:
    """拒绝「命令行上没有任何产出」的 detect 空跑。

    仅针对 **CLI 入口**：`detect` 不带 `--save` 时不写任何文件、不建目录，
    在命令行语境下等于空耗一次 YOLO 推理。

    不放进 `CommandArgs.validate()`（那是 CLI 与 GUI 共用的），因为 GUI 的
    detect 阶段本就不落盘——它通过事件通道把坐标交给界面画框，属于正常用法。
    同理，`functions` 层也不设限：`DetectFunction` / `detect_page_boxes`
    作为 `crop` / `cropremove` 的中间步骤被代码调用时必须保持可用。

    返回 True 表示已拒绝（调用方直接返回失败退出码）。
    """
    if command != "detect":
        return False
    if command_args.get("save"):
        return False
    print(_DRY_RUN_HINT)
    return True


def main() -> int:
    """命令行主入口函数，返回进程退出码。"""
    # 1. 解析命令行参数（help/version 在此阶段处理并退出，不触发重依赖加载）
    parser = CliArgsParser()
    args = parser.parse_args()
    command = args.command

    # 2. 处理 help/version（已在 parse_args 中处理，这里仅安全返回）
    if command in ("help", "version"):
        return StageStatus.SUCCESS.to_exit_code()

    if command == "print":
        # print 命令只能通过 run 执行，直接提示用户
        print("ERROR: 'print' command can only be executed via 'guji run print'.")
        return StageStatus.FAILED.to_exit_code()

    # ---------- init 命令（保留原始参数，不使用 CommandArgs） ----------
    # init 需区分用户是否显式提供了 -i/--input 和 -o/--output，
    # 而 CommandArgs 会填充默认值，故改用 InitArgs。
    if command == "init":
        from functions.init import InitFunction

        func = InitFunction(InitArgs(_collect_raw_kwargs(args)))
        return execute_function(func)

    # ---------- run / 其他普通子命令 ----------
    try:
        if command == "run":
            command_args = _build_for_run(args)
            target = args.subcommand
        else:
            command_args = _build_for_subcommand(args, command)
            target = command
        command_args.validate()
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return StageStatus.FAILED.to_exit_code()
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: parameter validation error: {exc}")
        return StageStatus.FAILED.to_exit_code()

    # 命令行空跑拦截：detect 不带 --save 时无任何产出，直接拒绝而非白算一趟
    if _reject_dry_run(target, command_args):
        return StageStatus.FAILED.to_exit_code()

    return execute_command(target, command_args)


if __name__ == "__main__":
    sys.exit(main())
