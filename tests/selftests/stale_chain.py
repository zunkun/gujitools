# -*- coding: utf-8 -*-
"""「上游重新执行 → 下游产物已过期」的判定与提示自测。

背景：跨阶段的过期判定以前是**空的**——重跑第一步提取/第二步检测之后，第三步的
最终图、第四步那个旧 PDF 一个字都不提，步骤条上还挂着成功对勾，最坏情况是把过期
PDF 当成品发出去。本模块钉住：

1. **纯函数判据**（`services/stale_chain.stale_upstream`）：只看成功运行的时间戳链；
   失败/中断不算数；容差内不算；下游从未成功不判；多个上游都更新时取最新的那个；
2. **界面提示**：第四步状态行给出「● 上游已重新执行（… 时间），本步产物可能已过期」，
   主按钮加粗高亮；重新生成后提示与高亮一起消失；
3. **版面改动优先**：改过逐图坐标（`_print_dirty`）时显示「● 版面已修改…」，
   盖过上游提示（用户的直接改动最该被看见）。

⚠️ 用**专用任务**（用完即删）：本模块要往 runs.json 里写自造时间戳，动到
ctx.tid 会影响后续模块（它们读同一个任务的历史）。
"""

from __future__ import annotations

NAME = "stale_chain"
DEPENDS: list[str] = ["tasklist"]
TITLE = "上游重跑→下游过期提示"

NOW = 1000.0


def _rec(rid: str, status: str, finished_at: float) -> dict:
    """一条够用的运行记录（判据只看 status 与 finished_at）。"""
    return {
        "run_id": rid, "status": status, "parameters": {},
        "done": 1, "total": 1,
        "started_at": finished_at - 1.0, "finished_at": finished_at,
        "output_path": None, "error": None,
    }


def run(ctx) -> None:
    from desktop.services.stale_chain import (
        TIMESTAMP_TOLERANCE_S, stale_upstream,
    )
    from desktop.store import STAGE_LABELS
    from desktop.ui import theme as T
    from tests.selftests._context import is_reddish, ok, painted_color, pump

    app, d, repo = ctx.app, ctx.d, ctx.repo

    # ---------------- 1. 纯函数 ----------------
    fresh = {
        "extract": [_rec("e1", "success", NOW - 100)],
        "rembg": [_rec("r1", "success", NOW - 50)],
        "print": [_rec("p1", "success", NOW - 10)],
    }
    ok("下游比上游新 → 不算过期", stale_upstream(fresh) == {},
       str(stale_upstream(fresh)))

    # 「提交本次任务」比 PDF 新 → PDF 过期，且指出是哪个上游
    late_submit = dict(fresh)
    late_submit["rembg_submit"] = [_rec("s1", "success", NOW)]
    verdict = stale_upstream(late_submit)
    ok("提交重跑 → PDF 判过期，并指出上游是「提交去底色结果」",
       verdict.get("print", {}).get("stage") == "rembg_submit"
       and verdict["print"]["upstream_at"] == NOW,
       str(verdict))

    # 容差内的前后脚完成不算过期
    tight = dict(fresh)
    tight["rembg_submit"] = [
        _rec("s1", "success", NOW - 10 + TIMESTAMP_TOLERANCE_S / 2)
    ]
    ok("容差内（同一次连续操作）不算过期",
       "print" not in stale_upstream(tight), str(stale_upstream(tight)))

    # 失败/中断的上游不算数
    failed = dict(fresh)
    failed["rembg_submit"] = [_rec("s1", "failed", NOW), _rec("s2", "cancelled", NOW)]
    ok("失败/中断的上游不算数（它们没产出可比对的产物）",
       stale_upstream(failed) == {}, str(stale_upstream(failed)))

    # 下游从未成功过 → 不判过期（界面本来就在说"未执行"）
    never = dict(fresh)
    never.pop("print")
    never["rembg_submit"] = [_rec("s1", "success", NOW)]
    ok("下游从未成功过时不判过期",
       "print" not in stale_upstream(never), str(stale_upstream(never)))

    # 多个上游都更新 → 取最新的那个（提示里说清"谁"最新）
    both = dict(fresh)
    both["extract"] = [_rec("e1", "success", NOW - 5)]
    both["rembg_submit"] = [_rec("s1", "success", NOW)]
    ok("多个上游都更新时取最新的那个",
       stale_upstream(both)["print"]["stage"] == "rembg_submit",
       str(stale_upstream(both)["print"]))
    ok("第一步重跑也能判定第三步过期（提取页图变了）",
       stale_upstream(both).get("rembg", {}).get("stage") == "extract",
       str(stale_upstream(both)))

    # ---------------- 2. 界面提示 ----------------
    tid = repo.create_task(ctx.pdf, "hash-stale", "过期提示样例")
    saved_dirty = getattr(d, "_print_dirty", False)
    saved_notices = dict(getattr(d, "_stale_notices", {}))
    try:
        d.set_task(tid)
        # 自造历史：PDF 先成，提交后跑（差 60 秒 > 容差）
        repo._save_runs(tid, {
            "rembg": [_rec("r1", "success", NOW - 200)],
            "print": [_rec("p1", "success", NOW - 60)],
            "rembg_submit": [_rec("s1", "success", NOW)],
        })
        d._refresh_stale_notices()
        d._select_stage(3)
        pump(app, 3)
        text = d.stage_status.text()

        def status_color() -> str:
            """状态行的**实际渲染色**（不是调色板）。

            ⚠️ 这里必须看渲染结果：状态行是 qfluentwidgets 的 ``CaptionLabel``，
            它不读调色板。第一版查 ``palette().color(foregroundRole())``，
            调色板里是红的、画出来是黑的，断言却一直是绿的——用户 2026-09-23
            截图报「这个红色没有修改过来」就是这么漏过去的。
            """
            rgb = painted_color(d.stage_status)
            return "#000000" if rgb is None else "#%02x%02x%02x" % rgb

        ok("第四步状态行提示上游已重新执行（并点出是「提交去底色结果」）",
           text.startswith("● 上游已重新执行")
           and STAGE_LABELS["rembg_submit"] in text,
           text)
        ok("提示里带上上游执行的时间（时:分）", ":" in text, text)
        ok("过期提示**真的画成红字**（不是只在调色板里红）",
           is_reddish(painted_color(d.stage_status)),
           f"实际渲染 {status_color()}；调色板 {d.stage_status.palette().color(d.stage_status.foregroundRole()).name()}")
        ok("「生成PDF」按钮被加粗高亮",
           d.run_button.font().bold(),
           f"bold={d.run_button.font().bold()}")
        ok("加粗不得动按钮的样式表（qss 一被整串替换，图标就压到文字上）",
           "hasIcon=true" in d.run_button.styleSheet(),
           f"样式表长度 {len(d.run_button.styleSheet())}")

        # 版面改动（用户直接改）优先于上游提示
        d._print_dirty = True
        d._refresh_stage_views()
        pump(app, 2)
        ok("改过版面时显示「版面已修改」而不是上游提示",
           d.stage_status.text().startswith("● 版面已修改"), d.stage_status.text())
        ok("版面提示同样是警示色（同一类「需重新生成」）",
           is_reddish(painted_color(d.stage_status)),
           f"实际渲染 {status_color()}")
        d._print_dirty = False

        # 重新生成 PDF（写入更新的成功记录）→ 提示与高亮一起消失、颜色复位
        repo._save_runs(tid, {
            "rembg": [_rec("r1", "success", NOW - 200)],
            "print": [_rec("p2", "success", NOW + 60)],
            "rembg_submit": [_rec("s1", "success", NOW)],
        })
        d._refresh_stale_notices()
        d._refresh_stage_views()
        pump(app, 2)
        ok("重新生成后提示消失、回到本步真实状态",
           "过期" not in d.stage_status.text()
           and d.stage_status.text().startswith(f"{STAGE_LABELS['print']}："),
           d.stage_status.text())
        ok("颜色也复位成常规柔和色（红字不许留在常规状态上）",
           not is_reddish(painted_color(d.stage_status)),
           f"实际渲染 {status_color()}（常规状态 {T.INK_SOFT} 不该是红的）")
        ok("重新生成后按钮加粗也撤掉（且样式表仍原封不动）",
           not d.run_button.font().bold()
           and "hasIcon=true" in d.run_button.styleSheet(),
           f"bold={d.run_button.font().bold()} "
           f"样式表长度 {len(d.run_button.styleSheet())}")

        # 上游没过期时，其它步骤不该被误报
        d._select_stage(2)
        pump(app, 2)
        ok("未过期的步骤不显示过期提示",
           "过期" not in d.stage_status.text(), d.stage_status.text())
    finally:
        d._print_dirty = saved_dirty
        d._stale_notices = saved_notices
        # 把详情页还给公共任务，再删掉本模块的专用任务（别把"已删任务"留在页面上）
        try:
            d.set_task(ctx.tid)
        except Exception:
            pass
        try:
            repo.delete_task(tid)
        except Exception:
            pass
