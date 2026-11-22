# -*- coding: utf-8 -*-
"""导入查重弹窗的提示文案。"""

from __future__ import annotations

import html

from desktop.ui import theme as T


def _duplicate_message(file_name: str, names: list) -> str:
    """导入查重弹窗的正文（**富文本**，供 ``_build_duplicate_dialog`` 用）。

    用户 2026-11-16 的两条要求：①弹窗宽度固定、文字自动折行（长书名不能把
    窗口撑宽）；②**文件名用红色标出来**——一眼看出拦的是哪个文件。

    - 红字走 ``<font color=…>``（取 ``desktop/ui/theme`` 的危险色），**不用
      样式表**：样式表只能整段上色，分不出"文件名"和"其余说明"。
    - 名字/文件名一律 ``html.escape``：书名里带 ``<``、``&`` 是常事，不转义
      会被当成标签吃掉（连后面的字一起吞）。
    - 最多列 3 个已有任务，其余折成「共 N 个」：宽度钉死时列出 20 个任务只会
      让弹窗高到屏幕外。
    """
    total = len(names)
    shown = [html.escape(str(n)) for n in names[:3]]
    quoted = "、".join(f"「{n}」" for n in shown)
    if total > len(shown):
        quoted += f" 等（共 {total} 个）"
    red = T.DANGER
    return (
        f'源文件<font color="{red}">「{html.escape(file_name)}」</font>'
        f"已在任务列表中导入过，内容相同的任务："
        f'<font color="{red}">{quoted}</font>。<br><br>'
        "是否仍然创建一条新任务？"
    )
