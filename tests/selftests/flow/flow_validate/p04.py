# -*- coding: utf-8 -*-
"""``flow_validate`` 第 4 章：数据链（每步都有输入）。"""

from __future__ import annotations

from ._helpers import _chain


def run(st) -> None:
    _check_data_chain(st.ctx, st.ok)


# ---------------------------------------------- ④b 数据链：每步都有输入
def _check_data_chain(ctx, ok) -> None:
    """**第一个节点有输入 ⇒ 链上每一步的输入端口都解析得出**（数据不断链）。

    用户口径（2026-10-07）：除了页面能渲染，数据层要成立——比如
    ``rembg → imposition → print``：rembg 引入图片目录，处理后传给
    imposition，处理后再传给 print。判据：任意合法组合里，每个可运行
    阶段的**阻塞输入**（``required_stage_inputs``）都能经
    ``store.stage_input`` 解析出具体路径（上游产物目录或入口图片目录），
    不能有"到中间某步断链、解析出 None"的组合。
    """
    from desktop.steps import ports
    from desktop.steps.scheduler import Scheduler
    from desktop.store import TaskStore

    repo = TaskStore(ctx.tmp / "chain_store")
    combos = [
        ("extract", "detect", "rembg", "imposition", "print"),
        ("detect", "rembg", "imposition", "print"),
        ("rembg", "imposition", "print"),
        ("detect", "rembg", "print"),
        ("rembg", "print"),
        ("detect", "print"),
        ("extract", "print"),
        ("imposition", "print"),
        ("print",),
        ("rembg", "detect", "imposition", "print"),   # 乱序也算合法
    ]
    for index, stages in enumerate(combos):
        diagram = _chain(*stages)
        tid = repo.create_task(ctx.pdf, f"chain-{index}", "数据链",
                               diagram=diagram)
        try:
            for active in (False, True):
                label = f"{'→'.join(stages)}（拼版{'开' if active else '关'}）"
                sched = Scheduler.from_diagram(diagram, {"imposition": active})
                for stage in sched.stages:
                    for port in repo.required_stage_inputs(tid, stage, active):
                        path = repo.stage_input(tid, stage, port, active)
                        ok(f"{label}: {stage}.{port} 解析得出输入",
                           path is not None, f"{stage}.{port} -> {path}")
        finally:
            repo.delete_task(tid)

    # ---- 用户举例的链路逐跳核对（rembg → imposition → print）----
    diagram = _chain("rembg", "imposition", "print")
    tid = repo.create_task(ctx.pdf, "chain-user", "用户链", diagram=diagram)
    try:
        task_dir = repo.task_dir(tid)
        ok("rembg 是入口 ⇒ 吃入口图片目录",
           repo.stage_input(tid, "rembg", "pages") == repo.task_input_dir(tid),
           str(repo.stage_input(tid, "rembg", "pages")))
        ok("rembg 的成品传给 imposition",
           repo.stage_input(tid, "imposition", "pages")
           == ports.artifact_path(task_dir, "rembg", "pages"),
           str(repo.stage_input(tid, "imposition", "pages")))
        ok("imposition 的产物传给 print（开拼版）",
           repo.stage_input(tid, "print", "pages", True)
           == ports.artifact_path(task_dir, "imposition", "pages"),
           str(repo.stage_input(tid, "print", "pages", True)))
        ok("不开拼版时 print 回退吃去底色成品（不断链）",
           repo.stage_input(tid, "print", "pages", False)
           == ports.artifact_path(task_dir, "rembg", "pages"),
           str(repo.stage_input(tid, "print", "pages", False)))

    # ---- 无上游时入口回落、有上游时不许吃入口（两方向都钉） ----
        diagram2 = _chain("detect", "rembg", "print")
        tid2 = repo.create_task(ctx.pdf, "chain-entry", "入口回落",
                                diagram=diagram2)
        try:
            ok("detect 是入口 ⇒ 吃入口图片目录",
               repo.stage_input(tid2, "detect", "pages")
               == repo.task_input_dir(tid2),
               str(repo.stage_input(tid2, "detect", "pages")))
            ok("rembg 跟在 detect 后 ⇒ 吃检测提交的裁图（detect 那格的 pages）",
               repo.stage_input(tid2, "rembg", "pages")
               == ports.artifact_path(repo.task_dir(tid2), "detect_submit",
                                      "pages"),
               str(repo.stage_input(tid2, "rembg", "pages")))
            ok("rembg 不再吃检测框（整图去底色）",
               repo.stage_input(tid2, "rembg", "boxes") is None,
               str(repo.stage_input(tid2, "rembg", "boxes")))
            ok("print 吃 rembg 的成品",
               repo.stage_input(tid2, "print", "pages")
               == ports.artifact_path(repo.task_dir(tid2), "rembg",
                                      "pages"),
               str(repo.stage_input(tid2, "print", "pages")))
        finally:
            repo.delete_task(tid2)
    finally:
        repo.delete_task(tid)
