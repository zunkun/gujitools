# -*- coding: utf-8 -*-
"""YOLO 预加载自测：条件判定、全局只加载一次、绝不进 GUI 主进程加载。

守的是用户 2026-10-13 的三条口径：

1. **加载条件**：流程里有「检测文本框」节点**且**没执行过（跑过/失败过
   都算执行过，不再预载；流程里没这个节点更不预载）；
2. **全局只加载一次**：本会话第一次领到 ``"prewarm"`` 槽位，之后每次进
   详情页只领 ``"probe"``（轻量探测，不拉起、不加载）；
3. **不影响主进程**：预加载模块**模块级**不许 import functions（分层守卫
   只查函数内延迟导入）；整个模块**任何位置**都不许出现
   ``load_yolo_model``——GUI 主进程禁重依赖，预热失败也绝不回落进程内加载；
   服务子进程要被降到低优先级、真检测时升回。

本用例**不拉起服务、不加载 torch**（那笔开销 yolo_service 用例已经付过），
全部是纯逻辑断言 + 源码护栏 + 服务关闭态下的快速行为验证。
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace

NAME = "yolo_prewarm"
DEPENDS: list[str] = []
TITLE = "YOLO 预加载（进详情页后台热模型，全局只加载一次）"

ROOT = Path(__file__).resolve().parents[2]


def _slot(step: str):
    """伪造一个流程槽位（只带判定用到的 ``step`` 属性）。"""
    return SimpleNamespace(step=step, stage=step, bar_index=0, stack_index=0)


def _pending_state() -> dict:
    return {"status": "pending", "done": 0, "total": 0, "completed": False}


def run(ctx) -> None:
    from tests.selftests._context import ok

    from desktop.services import yolo_prewarm as yp

    # ---- 1. 加载条件：detect_pending 纯函数 ----
    ok("流程里没有「检测文本框」节点 → 不预载（哪怕从没执行过）",
       yp.detect_pending([_slot("extract"), _slot("rembg"), _slot("print")],
                         _pending_state()) is False)
    ok("流程里有 detect 节点且从未执行 → 预载",
       yp.detect_pending([_slot("extract"), _slot("detect"), _slot("rembg")],
                         None) is True)
    ok("流程里有 detect 节点、状态停在 pending（无运行记录）→ 预载",
       yp.detect_pending([_slot("extract"), _slot("detect")],
                         _pending_state()) is True)
    for name, state in (
        ("已成功执行过", {"status": "success", "done": 6, "total": 6,
                          "completed": True}),
        ("执行过但失败", {"status": "failed", "done": 2, "total": 6,
                          "completed": False}),
        ("执行过被中断", {"status": "cancelled", "done": 3, "total": 6,
                          "completed": False}),
        ("有进度记录（在跑/跑过）", {"status": "pending", "done": 1,
                                      "total": 6, "completed": False}),
    ):
        ok(f"流程里有 detect 节点但{name} → 不预载",
           yp.detect_pending([_slot("detect")], state) is False)
    ok("空流程/无槽位 → 不预载",
       yp.detect_pending([], None) is False)

    # ---- 2. 全局只加载一次：槽位领取顺序 ----
    yp._reset_for_tests()
    ok("本会话第一次进入 → 领到真正的预热槽位",
       yp.claim_prewarm_slot() == "prewarm")
    ok("第二次进入 → 只领探测槽位（不加载）",
       yp.claim_prewarm_slot() == "probe")
    ok("第三次进入 → 仍只探测",
       yp.claim_prewarm_slot() == "probe")

    # ---- 3. 服务关闭态的快速行为（不拉起、不加载、不抛）----
    saved = os.environ.get("GUJI_YOLO_SERVICE")
    os.environ["GUJI_YOLO_SERVICE"] = "0"
    try:
        from functions import yolo_service as ys

        backend, seconds = ys.warm_up_service_only()
        ok("GUJI_YOLO_SERVICE=0 时预热直接报 disabled（不尝试任何加载）",
           backend == "disabled" and seconds == 0.0, f"{backend}/{seconds}")
        probe = ys.service_model_loaded()
        ok("探测不抛异常且返回 bool|None", probe is None or isinstance(probe, bool),
           repr(probe))
    finally:
        if saved is None:
            os.environ.pop("GUJI_YOLO_SERVICE", None)
        else:
            os.environ["GUJI_YOLO_SERVICE"] = saved

    # ---- 4. 源码护栏：预加载模块绝不把模型加载拽进 GUI 主进程 ----
    src = (ROOT / "desktop" / "services" / "yolo_prewarm.py").read_text(
        encoding="utf-8")
    ok("预加载模块全文不出现 load_yolo_model（进程内加载在 GUI 主进程是禁区）",
       "load_yolo_model" not in src)
    ok("预加载模块走的是服务专用预热（warm_up_service_only，无进程内回落）",
       "warm_up_service_only" in src and ".warm_up(" not in src)
    ok("预加载模块轻量探测走 service_model_loaded（不拉起、不加载）",
       "service_model_loaded" in src)
    top_imports = {
        line for line in src.splitlines()
        if line.startswith(("import ", "from "))
    }
    ok("预加载模块模块级不 import functions（重依赖只许函数内延迟导入）",
       not any(i.split()[1].split(".")[0] == "functions" for i in top_imports),
       str(top_imports))

    # ---- 5. 源码护栏：页面钩子接在 set_task 末尾、判定先行 ----
    page_src = (ROOT / "desktop" / "pages" / "taskdetail" / "page.py").read_text(
        encoding="utf-8")
    ok("任务详情页 set_task 调了 _schedule_yolo_prewarm()",
       "self._schedule_yolo_prewarm()" in page_src)
    ok("页面侧判定的是 detect_pending（流程节点 + 是否执行过），不是瞎排",
       "detect_pending(" in page_src and "stage_states(task_id)" in page_src)
    ok("页面对预加载的 import 是函数内延迟导入（模块级零耦合）",
       "from desktop.services.yolo_prewarm import (  # noqa" in page_src)

    # ---- 6. 源码护栏：服务侧的让出 CPU 与升回 ----
    ys_src = (ROOT / "functions" / "yolo_service.py").read_text(
        encoding="utf-8")
    tree = ast.parse(ys_src)
    warm = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef)
                and n.name == "warm_up_service_only")
    calls = {
        n.func.attr for n in ast.walk(warm)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    ok("warm_up_service_only 函数体里没有任何进程内加载调用",
       "load_yolo_model" not in calls and "warm_up" not in calls, str(calls))
    ok("warm_up_service_only 失败时不置 _given_up（不替真检测放弃服务路）",
       "_given_up = True" not in ast.unparse(warm))
    ok("拉起服务后降到低优先级（预热/空闲让出 CPU）",
       "_set_process_priority(proc, _BELOW_NORMAL_PRIORITY_CLASS)" in ys_src)
    ok("真检测请求触发服务端升回正常优先级",
       "_boost_priority()" in ys_src
       and ys_src.count("_boost_priority()") >= 2
       and "NORMAL_PRIORITY_CLASS)" in ys_src)
