# -*- coding: utf-8 -*-
"""空输入必须**报错**，不许静默成功。

起因（2026-09-26 极限测试）：`print -i final` 而图片实际在 `final/rembg` 时，
命令以**退出码 0** 成功结束、既不产出 PDF 也不报任何错——脚本/流水线完全
发现不了。同一形态在函数层有三处：

| 位置 | 旧行为 |
|---|---|
| `functions/print.py` | `print("未找到任何图片"); return {"processed": 0}` |
| `functions/base.py`（extract/crop/rembg/cropremove 共用） | 同上 |
| `functions/detect.py` | `return {"processed": 0, ...}` |

统一改成：**先发 `progress(0, 0)`**（GUI 靠它把进度条归零，这是原本就有的
明确信号，不能丢），**再抛 `FileNotFoundError`** → CLI 拿 FAILED 退出码、
GUI 弹出原因。

另有一条相邻的静默成功：`print` 的图片全被 `skip_pages` 排除时，会写出一个
0 页 PDF 并报成功——同样改为 `ValueError`。
"""

NAME = "empty_input"
DEPENDS: list[str] = []
TITLE = "空输入必须报错"


def run(ctx) -> None:
    from pathlib import Path

    from core.args import CommandArgs
    from functions import get_function
    from tests.selftests._context import ok

    root = ctx.tmp / "empty_input"
    empty = root / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    # 放一个非图片文件：确认判据是"没有图片"，不是"目录不存在/为空"
    (empty / "readme.txt").write_text("不是图片", encoding="utf-8")

    def expect_raises(label: str, command: str, **extra) -> None:
        """跑一条命令，要求它抛 FileNotFoundError（而不是静默成功）。"""
        args = CommandArgs(
            command=command, input=str(empty), output=str(root / command), **extra
        )
        try:
            get_function(command, args, None).execute()
        except FileNotFoundError as exc:
            ok(f"{command}：{label}", True, f"{exc}")
        except Exception as exc:  # noqa: BLE001 - 抛了但类型不对，也算不合格
            ok(f"{command}：{label}", False, f"抛的是 {type(exc).__name__}: {exc}")
        else:
            ok(f"{command}：{label}", False, "没有抛异常——静默成功了")

    # print 走自己的实现（不继承 base），单独测
    expect_raises("无图片时报错（不许静默成功）", "print")
    # base.py 那条（extract/crop/rembg/cropremove 共用）
    expect_raises("无图片时报错（不许静默成功）", "crop")
    expect_raises("无图片时报错（不许静默成功）", "rembg")
    # detect 自己有一份空输入分支
    expect_raises("无图片时报错（不许静默成功）", "detect")

    # 有图片但全被 skip_pages 排除 → 也不许当成功
    src = root / "images"
    src.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    for i in range(3):
        Image.new("RGB", (200, 300), (210, 200, 190)).save(src / f"{i + 1}.jpg")
    try:
        get_function(
            "print",
            CommandArgs(
                command="print", input=str(src), output=str(root / "o2"),
                skip_pages=[1, 2, 3],
            ),
            None,
        ).execute()
    except ValueError as exc:
        ok("print：图片全被 skip_pages 排除时报错", True, f"{exc}")
    except Exception as exc:  # noqa: BLE001
        ok("print：图片全被 skip_pages 排除时报错", False,
           f"抛的是 {type(exc).__name__}: {exc}")
    else:
        ok("print：图片全被 skip_pages 排除时报错", False,
           "没有抛异常——写出了一个 0 页 PDF 还报成功")

    # ---- extract：一页都没提出来，也必须报错 ----
    # 原实现无论成功几页都 `return True`（只把 success_count 打进日志），于是
    # 损坏的 PDF / 不可写的输出目录会让命令以退出码 0 结束、零产物、零提示。
    bad = root / "broken.pdf"
    bad.write_bytes(b"%PDF-1.4\nnot a real pdf\n%%EOF\n")
    try:
        get_function(
            "extract", CommandArgs(command="extract", input=str(bad), output=str(root / "o3")), None
        ).execute()
    except Exception as exc:  # noqa: BLE001 - 只关心"有没有报错"
        ok("extract：PDF 无法解析时报错（不是零产物报成功）", True, f"{type(exc).__name__}: {exc}")
    else:
        ok("extract：PDF 无法解析时报错（不是零产物报成功）", False,
           "没有报错——零产物还当成功")
    produced = list((root / "o3").rglob("*.jpg")) + list((root / "o3").rglob("*.png"))
    ok("extract：失败时不留下半截产物", not produced, str(produced[:3]))

    # ---- 回归形态：源码里不许再出现"空输入静默返回 processed: 0" ----
    # ⚠️ 先剥注释：说明性注释里正当地提到了旧写法，不剥会把自己判违规。
    root_dir = Path(__file__).resolve().parents[2]
    for rel in ("functions/print.py", "functions/base.py", "functions/detect.py"):
        raw = (root_dir / rel).read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in raw.splitlines())
        ok(
            f"{rel} 不许出现「静默返回 processed: 0」",
            '{"processed": 0' not in code and '"processed": 0,' not in code,
            "仍有静默成功的返回",
        )
