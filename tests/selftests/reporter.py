# -*- coding: utf-8 -*-
"""结构化事件通道（core.reporter）的自测。

背景：历史上 functions 层把「给程序读的信号」和「给人看的日志」都塞进
print()，desktop 侧只能跑正则从中文提示里捞进度与坐标：

    _PROGRESS_PAIR = re.compile(r"(?:进度|图片加载进度|写入进度)\\s*[:：]?\\s*(\\d+)\\s*/\\s*(\\d+)")

于是改一句提示文案就可能静默断掉 GUI 进度条。现在信号走
``core.reporter.Reporter``：CLI 不注入（空实现，回退到纯 print），
desktop 注入 JsonLinesReporter 直接写 JSON Lines。

本模块守住三件事：
1. 空实现真的什么都不做（CLI 路径零副作用）；
2. JsonLinesReporter 产出的事件能被 GUI 的解析逻辑原样消费；
3. functions/utils 真的在关键节点调用了 reporter（而不是忘了接）。
"""

import io
import json

NAME = "reporter"
DEPENDS: list[str] = []
TITLE = "结构化事件通道"


class _Recorder:
    """记录所有汇报的测试桩（满足 Reporter 协议）。"""

    def __init__(self):
        self.progress_calls = []
        self.events = []
        self.logs = []

    def progress(self, done, total):
        self.progress_calls.append((done, total))

    def event(self, name, **payload):
        self.events.append((name, payload))

    def log(self, message):
        self.logs.append(message)


def run(ctx) -> None:
    from tests.selftests._context import ok

    from core.reporter import (
        NULL_REPORTER,
        CallbackReporter,
        CoreReporter,
        normalize_reporter,
    )
    from desktop.stages.events import JsonLinesReporter, ProgressStream

    # ---- 1. 空实现是 no-op：CLI 不注入时的行为必须与「只 print」一致 ----
    null = CoreReporter()
    null.progress(3, 10)
    null.event("page_boxes", image="x", left=[1, 2, 3, 4])
    null.log("hello")
    ok("CoreReporter 可实例化且无副作用", True)
    ok("NULL_REPORTER 是 CoreReporter", isinstance(NULL_REPORTER, CoreReporter))
    ok("normalize_reporter(None) 返回空实现", normalize_reporter(None) is NULL_REPORTER)
    recorder = _Recorder()
    ok("normalize_reporter 透传真实实现", normalize_reporter(recorder) is recorder)

    # ---- 2. CallbackReporter：三个方法都落到同一个 sink ----
    seen = []
    cb = CallbackReporter(lambda name, payload: seen.append((name, payload)))
    cb.progress(2, 5)
    cb.event("page_size", image="p1", width=100, height=200)
    cb.log("msg")
    ok("CallbackReporter progress 映射为事件",
       seen[0] == ("progress", {"done": 2, "total": 5}), str(seen[0]))
    ok("CallbackReporter event 透传负载",
       seen[1] == ("page_size", {"image": "p1", "width": 100, "height": 200}),
       str(seen[1]))
    ok("CallbackReporter log 映射为事件",
       seen[2] == ("log", {"message": "msg"}), str(seen[2]))

    # ---- 3. JsonLinesReporter 的线上格式：GUI 必须能原样消费 ----
    buf = io.StringIO()
    bridge = JsonLinesReporter(
        {"task_id": "t1", "stage": "extract", "run_id": "r1"}, stream=buf
    )
    bridge.progress(4, 9)
    bridge.event("page_size", image="0001", width=2481, height=3508)
    bridge.event("page_boxes", image="0002", left=[10, 20, 300, 400], right=None)
    bridge.event("progress_total", total=42)  # 引擎先给总数：归一化为 0/total
    bridge.log("普通日志")

    lines = [json.loads(l) for l in buf.getvalue().splitlines() if l.strip()]
    ok("每条汇报产出一行 JSON", len(lines) == 5, f"实际 {len(lines)}")

    kinds = [l["type"] for l in lines]
    ok("progress 事件类型正确", kinds[0] == "progress", str(kinds))
    ok("page_size 事件类型正确", kinds[1] == "page_size", str(kinds))
    ok("page_boxes 事件类型正确", kinds[2] == "page_boxes", str(kinds))
    ok("log 事件类型正确", kinds[4] == "log", str(kinds))

    for line in lines:
        ok(f"{line['type']} 携带 context 归位信息",
           line.get("task_id") == "t1" and line.get("run_id") == "r1", str(line))

    ok("progress 负载为 done/total",
       lines[0]["done"] == 4 and lines[0]["total"] == 9, str(lines[0]))
    ok("page_size 负载为宽高",
       lines[1]["image"] == "0001" and lines[1]["width"] == 2481
       and lines[1]["height"] == 3508, str(lines[1]))
    ok("page_boxes 保留左右身份",
       lines[2]["left"] == [10, 20, 300, 400] and lines[2]["right"] is None,
       str(lines[2]))
    ok("progress_total 归一化为 done=0 的 progress",
       lines[3]["type"] == "progress" and lines[3]["done"] == 0
       and lines[3]["total"] == 42, str(lines[3]))

    # 事件负载不得夹带 GUI 不认识的键（防止内部字段泄漏到协议里）
    _allowed = {"type", "task_id", "stage", "run_id", "message",
                "done", "total", "image", "width", "height", "left", "right"}
    for line in lines:
        extra = set(line) - _allowed
        ok(f"{line['type']} 无协议外字段", not extra, str(extra))

    # ---- 4. ProgressStream 只转发日志，不再解析 ----
    buf2 = io.StringIO()
    stream = ProgressStream(buf2, {"task_id": "t2", "stage": "crop", "run_id": "r2"})
    # 故意喂进历史正则的所有目标文案：现在它们必须只是普通日志
    stream.write("进度: 3/10 页 - 第 3 页 用时: 0.10s\n")
    stream.write("图片总数: 10\n")
    stream.write("[boxes] 0001 left=10,20,300,400 right=none\n")
    stream.write("[imgsize] 1 2481,3508\n")
    stream.flush()
    logs = [json.loads(l) for l in buf2.getvalue().splitlines() if l.strip()]
    ok("ProgressStream 每行一条 log", len(logs) == 4, f"实际 {len(logs)}")
    ok("ProgressStream 不产出 progress 事件",
       all(l["type"] == "log" for l in logs), str([l["type"] for l in logs]))
    ok("ProgressStream 不再维护计数",
       stream.done == 0 and stream.total == 0, f"{stream.done}/{stream.total}")
    ok("历史正则目标文案被原样保留在日志里",
       any("[boxes]" in l["message"] for l in logs)
       and any("图片总数" in l["message"] for l in logs), str(logs))

    # ---- 5. 接线检查：functions/utils 真的在关键节点汇报了 ----
    import inspect

    from functions.base import FunctionBase
    from functions.text_region import TextRegionProcessor
    from utils.pdf_utils import process_page_batch, report_image_size

    ok("FunctionBase.__init__ 接受 reporter",
       "reporter" in inspect.signature(FunctionBase.__init__).parameters)
    ok("TextRegionProcessor.__init__ 接受 reporter",
       "reporter" in inspect.signature(TextRegionProcessor.__init__).parameters)
    ok("process_page_batch 接受 reporter",
       "reporter" in inspect.signature(process_page_batch).parameters)
    ok("report_image_size 接受 reporter",
       "reporter" in inspect.signature(report_image_size).parameters)

    src_base = inspect.getsource(FunctionBase)
    ok("base 引擎发出 progress",
       ".progress(" in src_base, "未在 FunctionBase 中找到 reporter.progress 调用")
    src_tr = inspect.getsource(TextRegionProcessor)
    ok("text_region 发出 page_boxes",
       '"page_boxes"' in src_tr, "未找到 page_boxes 事件上报")
    src_pdf = inspect.getsource(report_image_size)
    ok("report_image_size 发出 page_size", '"page_size"' in src_pdf, "未找到 page_size 事件")

    # ---- 6. 端到端：get_function 能接受并透传 reporter ----
    import tempfile
    from pathlib import Path

    from cli.command_args import CommandArgs
    from functions import get_function

    tmp = Path(tempfile.mkdtemp(prefix="guji_reporter_"))
    src = tmp / "in"
    src.mkdir()
    from PIL import Image

    Image.new("RGB", (600, 800), (250, 248, 240)).save(src / "0001.png")

    rec = _Recorder()
    fn = get_function(
        "rembg",
        CommandArgs(command="rembg", input=str(src), output=str(tmp / "out")),
        rec,
    )
    ok("get_function 把 reporter 装到功能实例上",
       getattr(fn, "reporter", None) is rec, str(type(getattr(fn, "reporter", None))))

    # 不传 reporter → 空实现，绝不能是 None（否则 callsite 要到处判空）
    fn2 = get_function(
        "rembg",
        CommandArgs(command="rembg", input=str(src), output=str(tmp / "out2")),
    )
    ok("不传 reporter 时落到空实现",
       getattr(fn2, "reporter", None) is NULL_REPORTER,
       str(getattr(fn2, "reporter", None)))
