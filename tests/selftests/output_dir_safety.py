# -*- coding: utf-8 -*-
"""输出目录**绝不许撞上输入目录**（2026-09-26 审计发现的数据丢失级问题）。

问题
    `resolve_final_output_dir` 在「目录输入 + 不给 `--output`」时返回
    ``input.parent / <该命令的子目录名>``。当**输入目录的 basename 恰好等于
    该命令的子目录名**时（`.../rembg` 跑 rembg、`.../crop` 跑 crop、
    `.../detect` 跑 `detect --save`），输出目录就是输入目录本身。实测把两张
    可辨认的 PNG 放进一个叫 `rembg` 的目录：

    | `clean` | 实测结果 |
    |---|---|
    | False | 两张原图**被原地覆盖**（rembg 输出名与输入同名） |
    | True  | `rmtree(outpath)` 把**输入目录连同图片全部删除**，随后重建为空目录，**退出码仍是 0** |

    「重跑自己上一步的输出目录」是常见操作（`.../rembg`、`.../crop`），
    所以这条必须由代码挡，不能指望用户小心。

本模块钉三件事：
1. 六个命令在「输入目录名 == 该命令子目录名」时都**抛 ValueError**；
2. 端到端：真的跑一次 rembg，输入必须完好、且以失败退出；
3. 正常场景（并列目录）**不受影响**，产物照常生成。
"""

NAME = "output_dir_safety"
DEPENDS: list[str] = []
TITLE = "输出目录不许撞输入"


def run(ctx) -> None:
    from pathlib import Path

    from PIL import Image

    from core.args import CommandArgs
    from functions import get_function
    from functions.base import DEFAULT_TEMP_NAME_MAP
    from tests.selftests._context import ok
    from utils.path_utils import assert_output_not_input, resolve_final_output_dir

    root = ctx.tmp / "output_dir_safety"

    # ---- 1. 六个命令：输入目录名等于子目录名时一律拒绝 ----
    for command, subdir in DEFAULT_TEMP_NAME_MAP.items():
        inp = root / "proj" / subdir
        try:
            out = resolve_final_output_dir(inp, None, is_file=False, default_subdir=subdir)
        except ValueError as exc:
            ok(f"{command}：输入目录名为 {subdir!r} 时拒绝（输出会等于输入）",
               "输出目录与输入目录相同" in str(exc), str(exc)[:80])
        else:
            ok(f"{command}：输入目录名为 {subdir!r} 时拒绝（输出会等于输入）",
               False, f"居然放行，输出={out}")

    # ---- 2. 边界：并列目录仍然合法（不能把正常用法一起挡了）----
    inp = root / "proj" / "images"
    out = resolve_final_output_dir(inp, None, is_file=False, default_subdir="rembg")
    ok("输入 .../images、子目录 rembg → 输出并列，不受影响",
       out == inp.parent / "rembg", str(out))

    # 显式 -o 指到别处时，即使输入目录叫 rembg 也必须放行
    inp2 = root / "proj2" / "rembg"
    out2 = resolve_final_output_dir(inp2, "out", is_file=False, default_subdir="rembg")
    ok("输入叫 rembg 但显式 -o out → 放行（给出路，不然用户没法重跑）",
       out2 == inp2.parent / "out" / "rembg", str(out2))

    # 输出是输入的**上级**也要挡（rmtree 会连输入一起删）
    try:
        assert_output_not_input(root / "a" / "b", root)
    except ValueError as exc:
        ok("输出是输入的上级时拒绝", "上级" in str(exc), str(exc)[:60])
    else:
        ok("输出是输入的上级时拒绝", False, "放行了")

    # ---- 3. 端到端：输入目录叫 rembg，跑 rembg 必须失败且输入完好 ----
    work = root / "e2e"
    src_dir = work / "rembg"
    src_dir.mkdir(parents=True, exist_ok=True)
    for i in (1, 2):
        Image.new("RGB", (300, 200), (30 * i, 200, 120)).save(src_dir / f"{i}.png")
    before = {p.name: p.stat().st_size for p in sorted(src_dir.glob("*.png"))}

    for clean in (False, True):
        args = CommandArgs(
            command="rembg", input=str(src_dir),
            type=1, offset=0, area=4, border="0", clean=clean,
        )
        try:
            get_function("rembg", args, None).execute()
        except ValueError as exc:
            refused = "输出目录与输入目录相同" in str(exc)
        else:
            refused = False
        ok(f"端到端 rembg（clean={clean}）：拒绝执行", refused, "没有抛拒绝错误")
        now = {p.name: p.stat().st_size for p in sorted(src_dir.glob("*.png"))}
        ok(f"端到端 rembg（clean={clean}）：输入图**完好无损**",
           now == before, f"前={before} 后={now}")
