# -*- coding: utf-8 -*-
"""图片编辑弹窗·双图编辑（拼版编辑整图）：3 个分片的编排入口（原大模块按章节拆开）。

⚠️ 各分片共享同一个 ``st``（SimpleNamespace）：``tmp`` / ``page`` 等跨段
夹具挂在上面；分片之间**按顺序**执行，与拆分前逐行执行的语义一致。
改某一章节只动对应 ``pNN.py``，不必读整包。
"""

from __future__ import annotations

from types import SimpleNamespace

from . import p01, p02, p03

NAME = "image_editor_multi"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·双图编辑（拼版编辑整图）"


#: 执行顺序 + 各分片覆盖的章节（改章节先看这里定位文件）
PARTS = (
    (p01, "1. 场景矩形 ∪ 双图（画布完整显示两张图） / 2. 真裁剪 ⇒ 内容原点平移，另一张图不漂 / 3. 换层：状态保持 + 各层视图 / 4. 撤销/还原带原点一起退 / 5. 变换烘焙（adjust 档）原点平移 / 6. 恢复会话进「统一变换」零等待（延迟建预览） / 7. 首次拖动**不**白出一帧精确重采样（2026-10-14 卡顿报障） / "),
    (p02, "拼版缩放不同也不自动调整 view 中心/倍率 / 开关必须管住「适配选区」这条独立路径（2026-10-14 用户报障） / 切层绝不缩放；自动缩放只发生在\"操作结束\"（2026-10-14 用户口径） / 开关关闭＝**画面绝对不动**（不只是不缩放，2026-10-14 用户口径 / 大图变换 ghost：先应用浮层变换、再移到 ghost 原点 / "),
    (p03, "完成双图编辑：新画布原点/尺寸要回写为页面版面 rect / 带透明留白的源图：入口版面对齐 + 移动后尺寸不回缩"),
)


def run(ctx) -> None:
    from ._helpers import _spread_dialog

    st = SimpleNamespace(ctx=ctx)
    dialog, left, right = _spread_dialog()
    canvas = dialog.canvas
    st.canvas = canvas
    st.dialog = dialog
    st.left = left
    st.right = right

    try:
        for part, _title in PARTS:
            part.run(st)
    finally:
        pass

