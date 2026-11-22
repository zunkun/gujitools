# -*- coding: utf-8 -*-
"""图片预览弹窗：3 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03

NAME = "preview_zoom"
DEPENDS: list[str] = []
TITLE = "图片预览弹窗"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1~5 / 5b / 6~7"),
    (p02, "8~9 / 工具条按钮：图标 + 纯中文文案（界面文案口径：按钮不放键名/英文） / 窗口态：min/max 按钮、双击顶部栏全屏、F11、百分比点击复位 / 打印按钮：取图走 canvas.export_image()（虚拟图也适用） / 11"),
    (p03, "10 / 11 / 12"),
)


def run(ctx) -> None:
    from ._helpers import ROOT
    from pathlib import Path
    import tempfile

    st = SimpleNamespace(ctx=ctx)
    root = ROOT
    app = ctx.app
    tmp = Path(tempfile.mkdtemp(prefix="guji_zoom_"))
    st.app = app
    st.root = root
    st.tmp = tmp

    try:
        for part, _title in PARTS:
            part.run(st)
    finally:
        pass

