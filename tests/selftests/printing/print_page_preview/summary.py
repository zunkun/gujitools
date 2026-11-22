# -*- coding: utf-8 -*-
"""第四步打印效果预览：5 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03, p04, p05

NAME = "print_page_preview"
DEPENDS: list[str] = []
TITLE = "第四步打印效果预览"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1. 纸张/方向 / 2. 图片落点 / 3. 标题与页码 / 3b. 标题/页码「距页边」（左右可不同，允许压在图片上） / 4. skip_pages / 4b. 标题切换节点：预览按 **PDF 页序（列表位置）** 解析（2026-09-29 回归） / 5. 与成品 PDF 逐值比对（预览几何 == PDF 几何） / 5b. 带「距页边」时，成品"),
    (p02, "7. 控件结构：左缩略图 + 右效果"),
    (p03, "7b. 面板接线：标题/页码「距页边」（勾选框 + 两行通栏输入框） / 8. 缩略图来源：条目自带 thumb / provider / 原图 / 8b. 预览字体：不能是裸 QFont() 的 generic 族 / 8b'. PDF 内容（标题/页码）字体必须**仿宋优先** / 8c. 竖排里的拉丁字符：整段旋转 90°，不拆成\"每字母一格\""),
    (p04, "8c-2. 绘制端步进：旋转段用渲染端实测宽度 / 9. 密度与缩略图尺寸 / 10. 宿主接线：详情页必须把打印面板参数交给效果预览 / 进度来源唯一：一条进度条只能被一个阶段驱动 / 原比例缩放（keep_ratio）：自动排版的两种落点 / 11. 单页导出（「下载本页图片」）：A4 效果图，精度与 PDF 同级 / 打印本页：同一份 A4 效果渲染，"),
    (p05, "方向键翻页推广到**所有步骤**（「焦点在哪里，哪里就切换」）"),
)


def run(ctx) -> None:
    from pathlib import Path

    st = SimpleNamespace(ctx=ctx)
    app = ctx.app
    tmp = Path(ctx.tmp) / "print_page_preview"
    tmp.mkdir(parents=True, exist_ok=True)
    st.app = app
    st.tmp = tmp

    try:
        for part, _title in PARTS:
            part.run(st)
    finally:
        pass

