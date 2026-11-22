# -*- coding: utf-8 -*-
"""创建任务弹窗与 BPMN 流程渲染/编辑：4 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03, p04, p05, p06, p07, p08, p09, p10

NAME = "flow_ui"
DEPENDS: list[str] = ["tasklist"]
TITLE = "创建任务弹窗与 BPMN 流程渲染/编辑"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1 / 2 / 3 / 4 / 5"),
    (p02, "6"),
    (p03, "6b"),
    (p04, "7 / 8 / 9 / 任务名输入框的外观（用户 2026-10-06：不好看/ 高度不够 / 太长）"),
    (p05, "10. 创建任务不关窗口 / 空壳任务"),
    (p06, "11. 缺源 PDF 提示 / 补选入口"),
    (p07, "12. 创建页重置 / 清空文件 / 首次进入提示"),
    (p08, "14 / 15. 保存刷新步骤条 / 选文件夹导入"),
    (p09, "16 / 17. 输入入口红框 / 提示层选目录"),
    (p10, "18 / 19. 源PDF 成对删除 / 结束事件级联"),
)


def run(ctx) -> None:

    st = SimpleNamespace(ctx=ctx)
    app, w = ctx.app, ctx.w
    page = w.list_page
    st.app = app
    st.page = page
    st.w = w

    try:
        for part, _title in PARTS:
            part.run(st)
    finally:
        pass

