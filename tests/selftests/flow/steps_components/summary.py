# -*- coding: utf-8 -*-
"""共用步骤组件层：4 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03, p04

NAME = "steps_components"
DEPENDS: list[str] = ["tasklist"]
TITLE = "共用步骤组件层"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1. 步骤元数据 / 1b. 「入口」规则：后缀 / 目录 / 一堆路径归一成一个源 / 1c. 出口布局：入口自动下钻 + 单 PDF 平铺"),
    (p02, "1d. 清单只有一份：流程/导航/面板都从 SPECS 派生 / 独立功能目录名（磁盘路径）与显示文案**必须解耦** / 2. 执行内核：纯函数 job / 3. 命令 job：入参映射与\"输出目录精确生效\" / 3b. 产物是**单个文件**的步骤（print）：不能覆盖 outpath / 4. 共用控件：三个模块各持一份，互不影响 / 4a. 「查看"),
    (p03, "4b. 大输入区（用户要的那块\"大的输入框\"） / 4b-2. 点空白处 → 直接开选择对话框（无小菜单、且不压在同一鼠标事件里） / 4b-3. 可见的选择按钮（用户 2026-10-03 报\"不能直接点击按钮选择\"） / 4b-3c. 「更换」真的能换源（用户 2026-10-03 报\"点了没反应\"） / 4b-3b. 独占模式（用户 2026-10-0"),
    (p04, "4b-4. 传 str 的路径不许流到 PreviewWorker（用户 2026-10-03 报） / 4c. 大输入区 + 控制组件：外部摆、内部接线（模块页的用法） / 5. 子进程传输层：启动参数与 UTF-8 环境（不起真进程） / 6. 独立功能目录改名的一次性迁移（磁盘路径不能被文案改动带走）"),
)


def run(ctx) -> None:

    st = SimpleNamespace(ctx=ctx)
    app = ctx.app
    st.app = app

    try:
        for part, _title in PARTS:
            part.run(st)
    finally:
        pass

