# -*- coding: utf-8 -*-
"""验证 worker 子进程真实产出的 JSON Lines 协议（一次性/可重跑脚本）。

前面 `tests/selftests/reporter.py` 验证的是「事件对象」；本脚本验证的是
**真的启一个子进程、真的往 stdout 写、真的被解析**这条链路 ——
因为历史上出问题的地方恰恰是「函数调用没问题，但线上协议变了」。

用法：python tests/reporter_worker_e2e.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

PY = sys.executable
ROOT = Path(__file__).resolve().parents[1]

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [OK  ] {name}")
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAILURES.append(name)


def run_worker(config: dict) -> tuple[int, list[dict], str]:
    """跑一次 worker 子进程，返回 (退出码, 事件列表, stderr)。"""
    tmp = Path(tempfile.mkdtemp(prefix="guji_worker_"))
    cfg = tmp / "config.json"
    cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [PY, "-m", "desktop.worker", "--config", str(cfg)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"__unparsed__": line})
    return proc.returncode, events, proc.stderr


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="guji_worker_e2e_"))
    src = tmp / "in"
    src.mkdir(parents=True)
    for i in range(3):
        Image.new("RGB", (1000, 1400), (250, 248, 240)).save(src / f"{i + 1:04d}.png")

    # ⚠️ args 里**不能**带 "command"：GUI 面板 get_args() 不产出它，
    # run_stage 内部是 CommandArgs(command=stage, **args)。带上会撞
    # "got multiple values for keyword argument 'command'"。

    print("== 1. rembg 阶段（通用 run_stage 路由）==")
    code, events, err = run_worker({
        "task_id": "t-e2e", "stage": "rembg", "run_id": "r-e2e",
        "args": {"input": str(src), "output": str(tmp / "out")},
    })
    check("退出码 0", code == 0, f"code={code}\nstderr={err[-800:]}")
    check("stdout 全部是合法 JSON", not any("__unparsed__" in e for e in events),
          str([e for e in events if "__unparsed__" in e][:2]))

    # __unparsed__ 是解析失败的兜底项，没有 type 字段；取 type 前先滤掉
    types = [e["type"] for e in events if "type" in e]
    check("有 started 事件", "started" in types, str(types))
    check("有 progress 事件", "progress" in types, str(types))
    check("有 log 事件（人读日志仍转发）", "log" in types, str(types))
    check("有 finished 事件", "finished" in types, str(types))
    check("每条事件都带 task_id/stage/run_id",
          all(e.get("task_id") == "t-e2e" and e.get("stage") == "rembg"
              and e.get("run_id") == "r-e2e" for e in events),
          str([e for e in events if e.get("task_id") != "t-e2e"][:2]))

    progs = [e for e in events if e["type"] == "progress"]
    # progress_total 不是独立事件类型：JsonLinesReporter 把它归一化成
    # done=0 的 progress（GUI 只关心 total 用来设进度条 range）。
    first = [e for e in events if e["type"] == "progress" and e["done"] == 0]
    check("总量先到（存在 done=0 的 progress）", bool(first), str(progs[:3]))
    check("总量与实际图片数一致", bool(first) and first[0]["total"] == 3, str(first))
    check("progress 收尾于 3/3",
          bool(progs) and progs[-1]["done"] == progs[-1]["total"] == 3,
          str(progs[-3:]))
    check("progress 单调不减",
          all(a["done"] <= b["done"] for a, b in zip(progs, progs[1:])), str(progs))

    # finished 不再带 done/total（协议变更）；GUI 用 _last_progress 补齐
    fin = [e for e in events if e["type"] == "finished"][0]
    check("finished 带 output", bool(fin.get("output")), str(fin))
    check("finished 不再附带 done/total（GUI 侧补齐）",
          "done" not in fin and "total" not in fin, str(fin))

    # 人读日志必须一行不漏（含 emoji 与长行）
    logs = [e["message"] for e in events if e["type"] == "log"]
    check("日志含「输入路径」", any("输入路径" in m for m in logs), str(logs[:6]))
    check("日志含「处理完成」", any("处理完成:" in m for m in logs), str(logs[:6]))
    check("日志条数合理（≥6）", len(logs) >= 6, f"{len(logs)} 条：{logs}")

    print("== 2. extract 阶段（run_extract_stage 路由，page_size 信号）==")
    import pymupdf

    pdf = tmp / "book.pdf"
    doc = pymupdf.open()
    for i in range(3):
        p = doc.new_page()
        p.insert_text((72, 72), f"page {i + 1}")
    doc.save(str(pdf))
    doc.close()

    code, events, err = run_worker({
        "task_id": "t-ex", "stage": "extract", "run_id": "r-ex",
        "args": {"input": str(pdf), "output": str(tmp / "ex"), "quick": False},
    })
    check("extract 退出码 0", code == 0, f"code={code}\nstderr={err[-800:]}")
    etypes = [e["type"] for e in events if "type" in e]
    sizes = [e for e in events if e["type"] == "page_size"]
    check("extract 产出 3 条 page_size", len(sizes) == 3, str(etypes))
    check("page_size 负载含 image/width/height",
          all({"image", "width", "height"} <= set(s) for s in sizes), str(sizes))
    check("page_size 尺寸为正整数",
          all(s["width"] > 0 and s["height"] > 0 for s in sizes), str(sizes))
    check("extract 有 progress 事件", "progress" in etypes, str(etypes))
    ext_fin = [e for e in events if e["type"] == "finished"]
    check("extract finished 带 output 目录", bool(ext_fin and ext_fin[0].get("output")),
          str(ext_fin))

    print("== 3. detect 阶段（run_detect_stage 路由，page_boxes 信号）==")
    code, events, err = run_worker({
        "task_id": "t-dt", "stage": "detect", "run_id": "r-dt",
        "args": {"input": str(src)},
    })
    check("detect 退出码 0", code == 0, f"code={code}\nstderr={err[-800:]}")
    dtypes = [e["type"] for e in events if "type" in e]
    pboxes = [e for e in events if e["type"] == "page_boxes"]
    check("detect 产出 3 条 page_boxes", len(pboxes) == 3, str(dtypes))
    check("detect stdout 无协议外裸行",
          not any("__unparsed__" in e for e in events),
          str([e for e in events if "__unparsed__" in e][:3]))
    check("page_boxes 保留左右身份（含 None）",
          all({"image", "left", "right"} <= set(b) for b in pboxes), str(pboxes))
    check("page_boxes 的 image 用 stem 而非绝对路径",
          all("/" not in str(b["image"]) and "\\" not in str(b["image"]) for b in pboxes),
          str([b["image"] for b in pboxes]))

    print("== 4. CLI 侧不注入 reporter 时协议无副作用 ==")
    # CLI 直接调 functions，stdout 里不应该出现任何 JSON Lines 事件
    proc = subprocess.run(
        [PY, "cli.py", "extract", "-i", str(pdf), "-o", str(tmp / "cli_out")],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )
    check("CLI extract 退出码 0", proc.returncode == 0, proc.stderr[-500:])
    json_like = [l for l in proc.stdout.splitlines()
                 if l.strip().startswith("{") and '"type"' in l]
    check("CLI stdout 不含任何 JSON 事件", not json_like, str(json_like[:3]))
    check("CLI 仍打印人读进度", "处理完成" in proc.stdout or "进度:" in proc.stdout,
          proc.stdout[:300])

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{FAILURES}")
        return 1
    print("worker 协议端到端验证通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
