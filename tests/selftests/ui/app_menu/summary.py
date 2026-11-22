# -*- coding: utf-8 -*-
"""顶部菜单栏（文件/独立功能/帮助）：2 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02

NAME = "app_menu"
DEPENDS: list[str] = ["tasklist"]
TITLE = "顶部菜单栏（文件/独立功能/帮助）"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1. 结构：四个顶级菜单 + 动作文案（含助记符） / 1b. 菜单**在标题栏里、跟在标题后面**（用户 2026-10-15 的要求） / 1c. 顶栏文字与底色统一（用户 2026-10-15 的几条要求） / 1c2. 顶部「有新版本」提示条（用户 2026-11-02） / 1d. 「关于」的值要放得下（长路径/长网址曾只显示半截） / 真点一遍："),
    (p02, "5. 检查更新：真发一次后台请求（网络函数被替换），含重入防护 / 5 的测试替身：绝不碰真网络 / 真浏览器 / 真安装器 / 真数据目录 / 6. 退出：走 window.close()（收尾链），用第二个窗口，别关掉 ctx.w"),
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

