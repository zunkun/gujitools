# -*- coding: utf-8 -*-
"""失败必须**可见**：原因要落到历史/弹窗，不能只剩一句「退出码 1」。

2026-09-26 审计发现四处「失败了但看不见原因」：

1. worker 的结构化 `error` 事件只被写进日志，**从不写 `_last_error_line`**
   → 历史记录与失败弹窗只显示「退出码 1」，真因淹没在日志里。
2. `desktop/worker.py` 在**进入任何阶段之前**崩溃（配置读不到 / JSON 解析失败 /
   config 不是 dict / argparse 报错）时，stdout 一条事件都没有 → GUI 什么都看不到。
3. stderr 的「像错误的那一行」匹配是**区分大小写**的 `"Error"`，而 argparse 的
   报错是小写 `error:` → 还是漏。
4. `functions/base.py`：所有输入都被跳过 / 全部失败时仍返回成功
   （`crop`/`cropremove` 的合法成功状态叫 `no_detect`/`whole_otsu`，所以判据要用
   「有没有产出」而不是「status 是不是 success」）。
5. `_flush_annotations` 用 `except: pass` 吞掉落盘失败 → 下游按缺失的坐标基准
   算错布局，界面上毫无提示。
"""

NAME = "failure_visibility"
DEPENDS: list[str] = []
TITLE = "失败必须可见"


def run(ctx) -> None:
    import json
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    from tests.selftests._context import ok

    repo = Path(__file__).resolve().parents[2]
    py = sys.executable

    # ---- 1. worker 启动期崩溃也要发 error 事件（真跑子进程）----
    for label, payload, name in (
        ("配置文件不存在", None, "missing.json"),
        ("配置不是 JSON 对象", "[]", "array.json"),
        ("配置不是合法 JSON", "{坏掉的", "broken.json"),
    ):
        work = Path(tempfile.mkdtemp(prefix="guji_failvis_"))
        cfg = work / name
        if payload is not None:
            cfg.write_text(payload, encoding="utf-8")
        proc = subprocess.run(
            # 与 GUI 完全一致的启动方式（源码环境走 -m，工作目录=项目根）
            [py, "-m", "desktop.worker", "--worker", "--config", str(cfg)],
            cwd=str(repo), capture_output=True, text=True, timeout=180,
        )
        errors = []
        for line in (proc.stdout or "").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "error":
                errors.append(event.get("message") or "")
        ok(f"{label}：退出码非 0", proc.returncode != 0, str(proc.returncode))
        ok(f"{label}：stdout 里有 error 事件（GUI 才看得见原因）",
           bool(errors) and all(errors), str(errors[:1]) or (proc.stdout or "")[-120:])

    # ---- 2. stderr 的错误行匹配要大小写不敏感 ----
    from desktop.pages.taskdetail.runner import StageRunnerMixin

    class _Stub:
        def __init__(self):
            self.log_view = []
            self._last_error_line = None

    _Stub._consume_worker_stderr = StageRunnerMixin._consume_worker_stderr
    for raw, want in (
        (b"prog: error: the following arguments are required: --config", True),
        (b"Traceback (most recent call last):", True),
        (b"[Errno 28] No space left on device", True),
        (b"E: Unable to locate package fonts-wqy", True),
        ("INFO 正在加载模型".encode("utf-8"), False),
    ):
        stub = _Stub()
        stub._consume_worker_stderr(raw)
        marked = stub._last_error_line is not None
        ok(f"stderr {raw.decode()[:38]!r} → 记为失败原因={want}", marked is want,
           f"实际={stub._last_error_line!r}")

    # ---- 3. 全部输入都没产出 → 报错（base 系命令）----
    from PIL import Image

    from core.args import CommandArgs
    from functions import get_function

    tiny = Path(tempfile.mkdtemp(prefix="guji_failvis_tiny_"))
    for i in range(3):
        # 远小于 is_valid_image_size 的 100 字节阈值 → 全部 skipped
        (tiny / f"{i + 1}.png").write_bytes(b"x")
    try:
        get_function(
            "rembg",
            CommandArgs(command="rembg", input=str(tiny), output=str(tiny / "out"),
                        type=1, offset=0, area=1, border="0"),
            None,
        ).execute()
    except RuntimeError as exc:
        ok("全部输入被跳过时报错（不是 exit 0）", "没有产出" in str(exc), str(exc)[:90])
    except Exception as exc:  # noqa: BLE001
        ok("全部输入被跳过时报错（不是 exit 0）", False, f"{type(exc).__name__}: {exc}")
    else:
        ok("全部输入被跳过时报错（不是 exit 0）", False, "静默返回成功")

    # ---- 4. 正常输入仍然成功，且返回值带上「产出数」----
    good = Path(tempfile.mkdtemp(prefix="guji_failvis_good_"))
    for i in range(2):
        Image.new("RGB", (240, 180), (200, 210, 190)).save(good / f"{i + 1}.png")
    result = get_function(
        "rembg",
        CommandArgs(command="rembg", input=str(good), output=str(good / "out"),
                    type=1, offset=0, area=1, border="0"),
        None,
    ).execute()
    ok("正常输入返回 produced 计数", result.get("produced") == 2, str(result))

    # ---- 5. 回归形态：这几处不许退回「静默吞掉」----
    def code_of(rel: str) -> str:
        raw = (repo / rel).read_text(encoding="utf-8")
        return "\n".join(line.split("#", 1)[0] for line in raw.splitlines())

    runner_code = code_of("desktop/pages/taskdetail/runner.py")
    ok("error 事件要写进 _last_error_line",
       'self._last_error_line = message.strip()' in runner_code)
    ok("annotations 落盘失败不许再 except: pass",
       "页框/尺寸落盘失败" in runner_code)
    base_code = code_of("functions/base.py")
    ok("base 的「无产出」判据要按 error/skipped 算，不按 status==success",
       'status_counts.get("skipped", 0)' in base_code and "produced == 0" in base_code)
    detect_code = code_of("functions/detect.py")
    ok("detect 返回值要带 detected/failed（否则分不清部分失败）",
       '"detected": detected' in detect_code and '"failed": failed' in detect_code)
    worker_code = code_of("desktop/worker.py")
    ok("worker 启动期异常要发 error 事件",
       "_emit_fatal(exc)" in worker_code)
    stage_code = code_of("desktop/stages/generic_stage.py")
    ok("finished 事件的 result 必须先转成 JSON 安全类型",
       "_json_safe(result)" in stage_code)
