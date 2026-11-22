# -*- coding: utf-8 -*-
"""去底色数据包检查与下载：2 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02

NAME = "data_package"
DEPENDS: list[str] = []
TITLE = "去底色数据包检查与下载"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1. 纯规则：解析 data.json / 2. sidecar + **生效文件解析**（权重目录换临时目录，不落仓库） / 2b. 防缓存 + \"取最新清单\"（不是\"取最快线路\"） / 3. 下载内核：落**发布名** → 校验 sha256 → 释放占用 → 切换 sidecar → 重新加载 / 3b. 在线兜底：**一份都没有**时才联网下载最新（"),
    (p02, "4. 控制器：真菜单 + 真控制器（弹窗/网络/下载 worker 换替身）"),
)


def run(ctx) -> None:

    st = SimpleNamespace(ctx=ctx)
    app, w = ctx.app, ctx.w
    st.app = app
    st.w = w

    try:
        for part, _title in PARTS:
            part.run(st)
    finally:
        pass

