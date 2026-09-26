# -*- coding: utf-8 -*-
"""参数类型转换：配置里把数字/布尔写成字符串时要转对，转不不了要给一句人话。

起因（2026-09-26 审计实测）
    `guji.yaml` 里给数字加引号（`zoom: "2"`）是很自然的写法，而 `CommandArgs`
    原样保留字符串 → 校验器 `"2" < 1` 抛
    `TypeError: '<' not supported between instances of 'str' and 'int'`，
    而 `cli/__main__.py` 只捕获 `ValueError/FileNotFoundError` → 用户拿到的是
    Python traceback，不是「参数错误：zoom 需要整数」。

    布尔更危险：`clean: "false"` 加了引号在 Python 里是**真值**，会让"只清输出
    目录"的破坏性开关真的去删目录。所以字符串的真假必须认，认不出来就报错。
"""

NAME = "arg_types"
DEPENDS: list[str] = []
TITLE = "参数类型转换"


def run(ctx) -> None:
    from pathlib import Path

    from core.args import _NUMERIC_KEYS_WITH_NONE_DEFAULT, CommandArgs
    from core.command_spec import COMMAND_SPECS
    from tests.selftests._context import ok

    work = ctx.tmp / "arg_types"
    work.mkdir(parents=True, exist_ok=True)
    (work / "a.pdf").write_bytes(b"%PDF-1.4 x")
    src = str(work)

    def build(command, **kw):
        args = CommandArgs(command=command, input=src, **kw)
        args.validate()
        return args

    # ---- 数字：字符串要转成数字（否则校验器里做比较会 TypeError）----
    for command, key, text in (
        ("extract", "zoom", "2"),
        ("extract", "batch_size", "8"),
        ("extract", "start", "3"),  # 默认值 None，靠显式登记的类型
        ("extract", "workers", "4"),
        ("rembg", "sealarea", "80"),
        ("detect", "workers", "6"),
    ):
        got = build(command, **{key: text}).get(key)
        ok(f"{command}.{key}=\"{text}\" 转成数字", got == int(text) and isinstance(got, int),
           f"{got!r} ({type(got).__name__})")

    # ---- 数字：转不了要抛 ValueError（带键名），不能是 TypeError ----
    for command, key, bad in (("extract", "zoom", "abc"), ("extract", "workers", "x")):
        try:
            build(command, **{key: bad})
        except ValueError as exc:
            ok(f"{command}.{key}=\"{bad}\" 抛 ValueError 且指出键名",
               key in str(exc), str(exc))
        except Exception as exc:  # noqa: BLE001
            ok(f"{command}.{key}=\"{bad}\" 抛 ValueError 且指出键名", False,
               f"抛的是 {type(exc).__name__}: {exc}")
        else:
            ok(f"{command}.{key}=\"{bad}\" 抛 ValueError 且指出键名", False, "没抛")

    # ---- 布尔：字符串真假要认，破坏性开关尤其不能反 ----
    for text, want in (("false", False), ("true", True), ("0", False), ("1", True),
                       ("no", False), ("yes", True)):
        got = build("extract", clean=text).get("clean")
        ok(f'clean="{text}" → {want}', got is want, repr(got))
    ok('clean=False（真布尔）保持 False', build("extract", clean=False).get("clean") is False)
    for text in ("maybe", "2"):
        try:
            build("extract", clean=text)
        except ValueError as exc:
            ok(f'clean="{text}" 认不出来 → 报错（绝不猜）', "clean" in str(exc), str(exc))
        else:
            ok(f'clean="{text}" 认不出来 → 报错（绝不猜）', False, "竟然接受了")

    # ---- 登记的「默认值 None 但是数字」的键必须真的存在于某个规格里 ----
    all_keys = set()
    for spec in COMMAND_SPECS.values():
        all_keys |= set(spec.defaults)
    stale = sorted(_NUMERIC_KEYS_WITH_NONE_DEFAULT - all_keys)
    ok("_NUMERIC_KEYS_WITH_NONE_DEFAULT 里的键都还在命令规格里（没有陈旧登记）",
       not stale, f"已不存在的键={stale}")
