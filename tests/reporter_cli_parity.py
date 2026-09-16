# -*- coding: utf-8 -*-
"""CLI 改造前后输出比对（一次性验证脚本）。

核心保证：给 functions 加结构化 reporter 后，**不注入 reporter 的 CLI 路径
输出必须逐字不变**。本脚本把 CLI 各命令的真实 stdout 抓下来，跟「历史预期
文案」对比；同时验证注入 reporter 时结构化事件真的出现。

用法：python tests/reporter_cli_parity.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import contextlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from cli.command_args import CommandArgs  # noqa: E402
from core.reporter import CallbackReporter, CoreReporter  # noqa: E402
from functions import get_function  # noqa: E402

def _show(a: str, b: str) -> str:
    """失败详情：用带标记的块展示两份 stdout，便于肉眼对比。"""
    return f"\n<<<A\t---\n{a}\t---\n<<<B\t---\n{b}\t---\n"


FAILURES: list[str] = []

# 耗时行天然每次不同（`用时: 0.04s`），比对前统一抹平；
# 除此之外 stdout 必须逐字一致。
_TIMING = re.compile(r"用时[:：]\s*[\d.]+")


def normalize(text: str) -> str:
    """抹掉每次运行必然不同的耗时数字，只留文案与结构。"""
    return _TIMING.sub("用时: <t>", text)


def sorted_lines(text: str) -> str:
    """把行排序后比较。

    `处理完成: x` 的**相对顺序**由 ThreadPoolExecutor.as_completed 决定，
    本身就是不确定的（多线程竞速），与 reporter 改造无关。非要逐字比顺序
    只会得到随机失败的测试。行集合一致 + 计数一致即已证明文案未变。
    """
    return "\n".join(sorted(text.splitlines()))


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [OK  ] {name}")
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAILURES.append(name)


def make_pages(root: Path, count: int = 2) -> Path:
    """造几张带明显左右内容的白底图，让 YOLO 有机会检出框。"""
    src = root / "in"
    src.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        img = Image.new("RGB", (1200, 1600), (252, 250, 244))
        # 画两块竖向文字块，增加被检测为左右文本框的概率
        from PIL import ImageDraw

        d = ImageDraw.Draw(img)
        d.rectangle([80, 200, 500, 1400], outline=(40, 40, 40), width=6)
        d.rectangle([700, 200, 1120, 1400], outline=(40, 40, 40), width=6)
        img.save(src / f"{i + 1:04d}.png")
    return src


def capture(fn, *args, **kwargs):
    """运行并抓取 stdout（耗时数字归一化，避免假失败）。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    return result, normalize(buf.getvalue())


def run_case(tmp: Path, src: Path, command: str, reporter, extra: dict | None = None):
    kwargs = dict(command=command, input=str(src), output=str(tmp / f"out_{command}"))
    kwargs.update(extra or {})
    events: list[tuple[str, dict]] = []
    if reporter == "callback":
        rep = CallbackReporter(lambda n, p: events.append((n, p)))
    else:
        rep = None
    fn = get_function(command, CommandArgs(**kwargs), rep)
    out, text = capture(fn.execute)
    return out, text, events


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="guji_cli_parity_"))
    src = make_pages(tmp)

    # 两点前提，否则会得到随机假失败：
    # 1) 所有对比用**同一个输出目录** —— 路径不同会让「输出目录：…」天然不同；
    # 2) 比对时忽略行序 ——  的先后由线程池竞速决定，本就不确定。

    print("== 1. rembg（走 FunctionBase 并发引擎）==")
    out_a, text_a, _ = run_case(tmp / "same", src, "rembg", None)
    check("不注入 reporter 时输出成功",
          isinstance(out_a, dict) and out_a.get("processed") == 2, str(out_a))
    check("stdout 含「输入路径：」", "输入路径：" in text_a, text_a[:200])
    check("stdout 含「输出目录：」", "输出目录：" in text_a, text_a[:200])
    check("stdout 仍打印「处理完成」", text_a.count("处理完成:") == 2, text_a)

    # 空 reporter 与不注入：同一个输出目录 → 必须逐字相同
    out_c, text_c, _ = run_case(tmp / "same", src, "rembg", CoreReporter())
    check("空实现与不注入 stdout 行集合一致", sorted_lines(text_a) == sorted_lines(text_c),
          _show(sorted_lines(text_a), sorted_lines(text_c)))
    check("空实现与不注入返回值相同", out_a == out_c, f"{out_a} vs {out_c}")

    print("== 2. rembg（注入 recorder）==")
    out_d, text_d, events = run_case(tmp / "same", src, "rembg", "callback")
    check("注入后 stdout 行集合一致", sorted_lines(text_d) == sorted_lines(text_a),
          _show(sorted_lines(text_a), sorted_lines(text_d)))
    check("注入后返回值仍相同", out_d == out_a, f"{out_d} vs {out_a}")

    kinds = [n for n, _ in events]
    check("注入后出现 progress_total 事件", "progress_total" in kinds, str(kinds))
    check("注入后出现 progress 事件", "progress" in kinds, str(kinds))
    progs = [p for n, p in events if n == "progress"]
    check("progress 单调不减且以 total 收尾",
          bool(progs) and progs[-1]["done"] == progs[-1]["total"] == 2
          and all(a["done"] <= b["done"] for a, b in zip(progs, progs[1:])),
          str(progs))
    check("progress_total 的总数与实际图片数一致",
          [p for n, p in events if n == "progress_total"] == [{"total": 2}],
          str([p for n, p in events if n == "progress_total"]))
    # 不注入时绝不能有任何汇报（CLI 路径零副作用）
    check("不注入时零事件", not [n for n, _ in
          run_case(tmp / "same", src, "rembg", None)[2]], "不该有事件")
    check("产出文件数为 2",
          len(list((tmp / "same" / "out_rembg").rglob("*.png"))) == 2,
          str(list((tmp / "same" / "out_rembg").rglob("*.png"))))

    print("== 3. crop（走 TextRegionProcessor，page_boxes 信号）==")
    try:
        out_e, text_e, events_e = run_case(tmp / "e", src, "crop", "callback")
        kinds_e = [n for n, _ in events_e]
        check("crop 成功执行", isinstance(out_e, dict), str(out_e))
        check("crop 发出 page_boxes 事件", "page_boxes" in kinds_e, str(kinds_e))
        # 兼容保留的文本行必须还在（GUI 迁移期对照用）
        check("crop 仍打印 [boxes] 兼容行", "[boxes]" in text_e, text_e[:300])
        check("crop 仍打印「处理完成」", "处理完成:" in text_e, text_e[:300])
        boxes_ev = [p for n, p in events_e if n == "page_boxes"][0]
        check("page_boxes 负载含 image/left/right",
              {"image", "left", "right"} <= set(boxes_ev), str(boxes_ev))
        # 结构化负载的坐标必须与文本行一致（两通道同源）
        if boxes_ev.get("left"):
            line = [l for l in text_e.splitlines() if l.startswith("[boxes]")][0]
            nums = ",".join(str(v) for v in boxes_ev["left"])
            check("结构化坐标与文本行一致", f"left={nums}" in line,
                  f"{boxes_ev['left']} vs {line}")
        else:
            check("无框时左右均为 None",
                  boxes_ev.get("left") is None and boxes_ev.get("right") is None,
                  str(boxes_ev))
    except Exception as exc:  # noqa: BLE001
        check("crop 执行未抛异常", False, f"{type(exc).__name__}: {exc}")

    print("== 4. extract（走 utils.pdf_utils，page_size 信号）==")
    import pymupdf

    pdf = tmp / "样例.pdf"
    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"第 {i + 1} 页 内容")
    doc.save(str(pdf))
    doc.close()

    args = dict(command="extract", input=str(pdf), output=str(tmp / "ex"))
    ev: list[tuple[str, dict]] = []
    fn = get_function("extract", CommandArgs(**args),
                      CallbackReporter(lambda n, p: ev.append((n, p))))
    _, text_f = capture(fn.execute)

    kinds_f = [n for n, _ in ev]
    check("extract 发出 page_size 事件", kinds_f.count("page_size") == 3, str(kinds_f))
    check("extract 发出 progress 事件", "progress" in kinds_f, str(kinds_f))
    sizes = [p for n, p in ev if n == "page_size"]
    check("page_size 负载含宽高", all({"image", "width", "height"} <= set(s) for s in sizes),
          str(sizes[:2]))
    check("page_size 图片名与页号一致",
          [s["image"] for s in sizes] == ["1", "2", "3"], str([s["image"] for s in sizes]))
    check("extract 仍打印 [imgsize] 兼容行", text_f.count("[imgsize]") == 3, text_f[:300])

    # 不注入的 extract 必须与注入的逐字相同（同一输出目录）
    args2 = dict(command="extract", input=str(pdf), output=str(tmp / "ex"))
    fn2 = get_function("extract", CommandArgs(**args2))
    _, text_h = capture(fn2.execute)
    check("extract 注入/不注入 stdout 行集合一致", sorted_lines(text_f) == sorted_lines(text_h),
          _show(sorted_lines(text_f), sorted_lines(text_h)))

    print("== 5. 事件流是合法 JSON Lines ==")
    buf = io.StringIO()
    from desktop.stages.events import JsonLinesReporter

    rep = JsonLinesReporter({"task_id": "t", "stage": "rembg", "run_id": "r"}, stream=buf)
    fn3 = get_function(
        "rembg",
        CommandArgs(command="rembg", input=str(src), output=str(tmp / "jl")),
        rep,
    )
    fn3.execute()
    bad = []
    for line in buf.getvalue().splitlines():
        try:
            json.loads(line)
        except json.JSONDecodeError:
            bad.append(line)
    check("所有事件行都是合法 JSON", not bad, str(bad[:3]))
    types = [json.loads(l)["type"] for l in buf.getvalue().splitlines() if l.strip()]
    check("事件流含 progress", "progress" in types, str(set(types)))

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{FAILURES}")
        return 1
    print("CLI 输出一致性验证通过 ✅（stdout 文案未变，结构化事件新增）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
