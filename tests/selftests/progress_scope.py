# -*- coding: utf-8 -*-
"""进度条 / 状态文字必须只服务**当前显示的这一步**。

起因（用户报）：在第三步点「提交本次任务」，提交还在跑的时候切到第四步，看到
走动的进度条 +「进度 42/91」+ 灰掉的「生成PDF」按钮，于是以为「第四步在自动
生成 PDF」。根因是共享的 ``stage_progress`` / ``stage_status`` 被**无条件**写：
不看这条进度属于哪个阶段，也不看用户停在哪一步。

断言线：

1. **映射只有一份**：``STAGE_STEP`` 把 ``rembg_submit`` 归到第三步（否则第三步
   点提交后压根看不到任何进度）；
2. **跨步骤不上屏**：在第四步收到「提交」的进度事件，进度条与文案**一个像素都不动**；
3. **本步的照旧上屏**：同样的进度事件在第三步（它所属的步骤）会正常显示；
4. **本步在跑时别的路径不许抢**：``_refresh_stage_views()``（每 ≤200ms 由节流器调）
   不得把文案刷成"上一次运行"的 done/total —— 否则状态文字来回跳；
5. **跑完之后回到真实状态**：``running_stage`` 清空后再刷新，文案回到该步骤的
   真实状态（不是停留在进度数字上）；
6. **切走之后仍看得出"还有活儿在跑"**：提交正在执行时，**第三步的步骤条**要显示
   「执行中 · 42/91」——进度条只服务当前步骤，步骤条是用户切到别处后唯一的全局信号。
"""

from __future__ import annotations

NAME = "progress_scope"
DEPENDS: list[str] = ["tasklist"]
TITLE = "进度显示范围"


def run(ctx) -> None:
    from desktop.pages.taskdetail.runner import STATUS_LABELS
    from desktop.store import STAGE_LABELS, STAGE_STEP
    from desktop.store.tasks import STAGES
    from tests.selftests._context import ok, pump

    app, d = ctx.app, ctx.d
    ok("提交本次任务归属第三步（rembg_submit → rembg）",
       STAGE_STEP.get("rembg_submit") == "rembg"
       and all(STAGE_STEP.get(s) == s for s in STAGES),
       str(STAGE_STEP))

    saved_stage = d.running_stage
    try:
        d.set_task(ctx.tid)
        d._select_stage(3)                      # 停在第四步（生成PDF）
        pump(app, 3)

        def text() -> str:
            return d.stage_status.text()

        def bar() -> tuple:
            return (d.stage_progress.value(), d.stage_progress._maximum)

        # 第四步**自己的**真实状态：文案由 store 里的阶段状态算出来，不写死
        # （整跑时第四步可能已经成功生成过 PDF，单跑这个模块时还是"未执行"）
        d._refresh_stage_views()
        state = d.store.stage_states(d.task_id)["print"]
        own_text = f"{STAGE_LABELS['print']}：{STATUS_LABELS[state['status']]}"
        own_bar = bar()
        ok("第四步显示的是自己的状态（不是别的步骤的进度）",
           text() == own_text and "进度" not in text(), text())

        # ---- 2. 收到"第三步提交"的进度：第四步屏幕上必须毫无变化 ----
        d.running_stage = "rembg_submit"
        d._on_worker_progress({"stage": "rembg_submit", "done": 42, "total": 91})
        pump(app, 2)
        ok("在第四步收到「提交」的进度：状态文字不被动过",
           text() == own_text, f"「{own_text}」→「{text()}」")
        ok("在第四步收到「提交」的进度：进度条不被动过",
           bar() == own_bar, f"{own_bar} → {bar()}")
        ok("跨步骤进度被判为「不属于当前步骤」",
           not d._progress_belongs_here("rembg_submit"))
        ok("本步自己的进度照旧算数",
           d._progress_belongs_here("print"))

        # 第四步节流刷新一轮：还是不能再被第三步的进度污染
        d._progress_dirty = True
        d._flush_progress_ui()
        pump(app, 2)
        ok("第四步节流刷新后仍显示自己的状态",
           text() == own_text and bar() == own_bar,
           f"「{text()}」 {bar()}")

        # ---- 3. 切到第三步（提交所属的步骤）：同样的进度就该显示了 ----
        d._select_stage(2)
        pump(app, 3)
        d._on_worker_progress({"stage": "rembg_submit", "done": 42, "total": 91})
        pump(app, 2)
        ok("在第三步显示「提交」的进度文字",
           text() == "进度 42/91", text())
        ok("在第三步显示「提交」的进度条", bar() == (42, 91), str(bar()))

        # ---- 4. 本步在跑时，_refresh_stage_views 不许抢进度文案 ----
        d._refresh_stage_views()
        pump(app, 2)
        ok("本步在跑时，刷新步骤条不会把进度文案刷回「上一次运行」的值",
           text() == "进度 42/91" and bar() == (42, 91),
           f"「{text()}」 {bar()}")
        ok("本步在跑时 _own_step_running() 为真", d._own_step_running())

        # ---- 5. 跑完之后回到该步骤的真实状态 ----
        d.running_stage = None
        d._refresh_stage_views()
        pump(app, 2)
        ok("跑完后状态文字回到该步骤的真实状态",
           text().startswith(f"{STAGE_LABELS['rembg']}：") and "进度" not in text(),
           text())
        ok("空闲时 _own_step_running() 为假", not d._own_step_running())

        # 换到别的步骤看同一条进度：也不该动（第三步之外都不显示）
        d._select_stage(0)
        d._refresh_stage_views()
        pump(app, 2)
        before_text, before_bar = text(), bar()
        d._on_worker_progress({"stage": "rembg_submit", "done": 7, "total": 91})
        ok("在第一步收到「提交」的进度同样不上屏",
           text() == before_text and bar() == before_bar,
           f"「{text()}」 {bar()}")

        # ---- 6. 提交在跑时，第三步的步骤条是唯一的全局信号 ----
        d.running_stage = "rembg_submit"
        d._last_progress = (42, 91)
        d._select_stage(3)                 # 用户切到第四步
        d._refresh_stage_views()
        pump(app, 2)
        tile = d.step_bar.buttons[2]       # 第三步（去底/提交）
        ok("切到第四步时，第三步步骤条显示「执行中」（看得出还有活儿在跑）",
           tile._status == "running", tile._status)
        ok("第三步步骤条带上提交的进度",
           "42/91" in tile.detail_label.text(), tile.detail_label.text())
        ok("这时第四步状态行仍是自己的真实状态（没被提交的进度污染）",
           "进度" not in text() and "42/91" not in text(), text())

        # 提交跑完 → 第三步步骤条回到它会话里的真实状态（不再是"执行中"）
        d.running_stage = None
        d._select_stage(2)
        d._refresh_stage_views()
        pump(app, 2)
        ok("提交结束后第三步步骤条不再显示「执行中」",
           d.step_bar.buttons[2]._status != "running",
           d.step_bar.buttons[2]._status)
    finally:
        d.running_stage = saved_stage
        d._progress_dirty = False
        try:
            d._select_stage(0)
            d._refresh_stage_views()
        except Exception:
            pass
