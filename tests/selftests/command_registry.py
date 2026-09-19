# -*- coding: utf-8 -*-
"""命令 / 阶段「注册点」一致性守卫。

`core/command_spec.py` 的 `COMMAND_SPECS` 是命令的唯一事实来源，但另外几处
各自维护了一份清单：functions 的工厂表、`cli` 的 run 子命令、`utils/help.py`
的文档映射、desktop 的阶段表与阶段默认参数表。任何一份漏改，新增命令就会
「代码里有、某个入口里没有」——这类漂移是静默的，用户照着某个入口用才发现。

**为什么不硬集中**：把实现坐标（如 `("functions.extract", "ExtractFunction")`）
写进 `COMMAND_SPECS`，会让 `core` 在语义上依赖 `functions` 的内部结构，等于
把一处耦合换成另一处。所以清单留在各自的层，用本模块的断言钉住它们一致——
漏改会红，比「记得改 6 处」可靠。

注意 `STAGES`（GUI 四步）是 `COMMAND_SPECS`（六命令）的**子集**：GUI 流程不含
`crop`/`cropremove`（它们被 `cropremove` 复合流程覆盖）。所以这里判 `⊆` 不
是 `==`——这是「步骤不同」的合理差异，不是漂移。
"""

NAME = "command_registry"
DEPENDS: list[str] = []
TITLE = "命令与阶段注册点一致"

#: 命令表至少该有这些命令；低于此数说明表被清空或改坏，
#: 下面那些 `==` 断言会变成同义反复地全绿。
_MIN_COMMANDS = 6
_MIN_STAGES = 4

#: 允许比 `COMMAND_SPECS` 多出来的命令（**登记在案**，想加请先写理由）。
#: `init` 是「生成配置文件」命令：它走 `InitArgs` 而不是 `CommandArgs`，
#: 没有标准参数规格，因此不进 `COMMAND_SPECS`——但工厂要能构造它，
#: CLI 也要有这个子命令。
_EXTRA_COMMANDS = {"init"}


def run(ctx) -> None:
    from core.command_spec import COMMAND_SPECS
    from tests.selftests._context import ok

    known = set(COMMAND_SPECS)

    # ---- 0. 元守卫：先确认表本身是满的 ----
    ok(f"命令表至少有 {_MIN_COMMANDS} 个命令（防下面相等断言空转）",
       len(known) >= _MIN_COMMANDS, f"实际 {len(known)} 个：{sorted(known)}")

    # ---- 1. functions 工厂表 ----
    from functions import _COMMAND_MAP

    ok("functions 工厂表覆盖全部命令",
       known <= set(_COMMAND_MAP),
       f"工厂缺={sorted(known - set(_COMMAND_MAP))}")
    ok("functions 工厂表没有未登记的额外命令",
       set(_COMMAND_MAP) - known <= _EXTRA_COMMANDS,
       f"未登记={sorted(set(_COMMAND_MAP) - known - _EXTRA_COMMANDS)}；"
       f"已登记的白名单={sorted(_EXTRA_COMMANDS)}")

    # ---- 2. CLI run 子命令 ----
    from cli.cli_args import CliArgsParser

    parser = CliArgsParser().parser
    run_parser = None
    for action in parser._subparsers._group_actions:
        for name, choice in (getattr(action, "choices", None) or {}).items():
            if name == "run":
                run_parser = choice
                break
        if run_parser is not None:
            break
    ok("CLI 已注册 run 子命令", run_parser is not None, "未找到 run 子命令")
    pos = [a for a in run_parser._actions if a.dest == "subcommand"]
    run_vals = set(pos[0].choices) if pos else set()
    ok("CLI run 子命令覆盖全部命令",
       known <= run_vals,
       f"run 缺={sorted(known - run_vals)}")
    ok("CLI run 没有未登记的额外子命令",
       run_vals - known <= _EXTRA_COMMANDS,
       f"未登记={sorted(run_vals - known - _EXTRA_COMMANDS)}；"
       f"run 可选={sorted(run_vals)}")

    # ---- 3. 帮助文档映射 ----
    from utils.help import _DOC_MAP

    ok("每个命令都有帮助文档条目",
       known <= set(_DOC_MAP),
       f"缺文档={sorted(known - set(_DOC_MAP))}")

    # ---- 4/5. desktop：阶段表是子集，且每个阶段都有默认参数 ----
    from desktop.store.tasks import STAGES

    stages = set(STAGES)
    ok(f"GUI 阶段表至少有 {_MIN_STAGES} 个阶段（防子集断言空转）",
       len(stages) >= _MIN_STAGES, f"实际 {len(stages)} 个：{sorted(stages)}")
    ok("GUI 阶段是命令规格的子集（步骤不同允许少，但不能凭空多）",
       stages <= known, f"越界阶段={sorted(stages - known)}")

    from desktop.components.panels.params_spec import DEFAULTS

    ok("每个 GUI 阶段都有默认参数表",
       stages <= set(DEFAULTS),
       f"缺默认参数={sorted(stages - set(DEFAULTS))}")
