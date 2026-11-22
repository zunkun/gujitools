# -*- coding: utf-8 -*-
"""「显示执行记录」开关自测（用户 2026-11-16 提的功能）。

需求原话：

> 所有步骤如果右侧控制面板中存在「执行记录」项，默认不显示；可以在设置中
> 增加一个「功能」大项，下面有个「显示执行记录」，默认不开启。

守住四件事：

1. **配置项**：``AppConfig.showHistory`` 默认值是 ``False``（不是"当前值"，
   用户可能已经手动打开过）；
2. **设置页**：新增「功能」大项，里面那张开关卡绑的就是这个配置项
   （绑错 = 点了没反应）；
3. **详情页默认**：开关关着时，各步骤右栏都没有「执行记录」
   （含第一步/第三步这种本来会显示它的步骤）；
4. **开关即时生效**：打开后**不用切页**就出现；第二步仍然不显示（那里用的
   是「检测结果统计」，``spec.panel_extra`` 非空的步骤不摆执行记录）；
   关掉后立刻收起。测完把配置项还原，别把状态留给后面的模块。

⚠️ 配置项一直是**直接改 ``item.value``**（不落盘），不走 ``qconfig.set``，
否则会把开关写进用户真实的 ``~/Documents/guji/config.json``。
"""

NAME = "history_switch"
DEPENDS: list[str] = ["tasklist"]
TITLE = "显示执行记录开关（默认关）"


def run(ctx) -> None:
    from desktop.settings.config import app_config
    from tests.selftests._context import ok, pump

    app, d = ctx.app, ctx.d
    cfg = app_config()

    # ---- 1. 配置项默认值 ----
    ok("「显示执行记录」配置项默认关",
       cfg.showHistory.defaultValue is False,
       str(cfg.showHistory.defaultValue))

    # ---- 2. 设置页：新增「功能」大项，卡片绑到配置项 ----
    page = ctx.w.shell.settings_page()
    app.processEvents()
    ok("设置页有「功能」大项", hasattr(page, "feature_group"))
    ok("「显示执行记录」卡片绑到配置项",
       page.history_card.configItem is cfg.showHistory)
    ok("卡片挂在「功能」大项里（不是开发者/更新组）",
       page.history_card.parent() is page.feature_group)

    # ---- 3/4. 详情页：默认藏、开关即时生效 ----
    if not ctx.tid:
        print("    （跳过：本轮没有主任务，测不了右栏显隐）")
        return
    if d.task_id != ctx.tid and not d.set_task(ctx.tid):
        print("    （跳过：set_task 没成功，详情页没落到这个任务上）")
        return
    rembg_bar = d.bar_index_of_step("rembg")
    detect_bar = d.bar_index_of_step("detect")
    if rembg_bar is None:
        print("    （跳过：本任务的流程里没有「图片去底色」这一步）")
        return

    before = bool(cfg.showHistory.value)
    #: 进来时停在哪一格（别的模块可能依赖详情页停在特定步骤，收工要还回去）
    bar_before = d.step_bar._current
    try:
        # 默认关：第三步（本来会显示执行记录的步骤）也不显示
        cfg.showHistory.value = False
        d._select_stage(rembg_bar)
        pump(app, times=3)
        ok("开关关着 → 第三步不显示「执行记录」",
           not d.history_block.isVisibleTo(d))

        # 打开：**不切页**就该出现（接线在配置项信号上）
        cfg.showHistory.value = True
        pump(app, times=3)
        ok("打开开关 → 同一步立刻出现（不必切页）",
           d.history_block.isVisibleTo(d))

        # 第二步仍不显示：它用专属区块「检测结果统计」
        if detect_bar is not None:
            d._select_stage(detect_bar)
            pump(app, times=3)
            ok("第二步即使打开开关也不显示执行记录",
               not d.history_block.isVisibleTo(d)
               and d.detect_stats.isVisibleTo(d))
            d._select_stage(rembg_bar)
            pump(app, times=3)

        # 关掉：立刻收起
        cfg.showHistory.value = False
        pump(app, times=3)
        ok("关掉开关 → 立刻收起",
           not d.history_block.isVisibleTo(d))
    finally:
        cfg.showHistory.value = before
        if bar_before >= 0:
            d._select_stage(bar_before)
        pump(app, times=2)


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
