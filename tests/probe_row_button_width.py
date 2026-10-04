# -*- coding: utf-8 -*-
"""离屏探针：量一量「生成预览 / 提交本次任务」并排后的实际宽度与文字是否被截断。

用途：并排后每颗按钮只剩控制列（340~440px）的一半，长文案会被 qfluent 的
省略号机制吃掉——先量清楚再决定文案要不要收敛。跑法::

    QT_QPA_PLATFORM=offscreen python tests/probe_row_button_width.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    from PySide6.QtWidgets import QApplication

    # ⚠️ 必须用项目自己的字体加载（tests/gui_shot.py::load_fonts）：offscreen 下
    #    中文会变豆腐块，量出来的宽度偏小，结论不可信。
    from tests.gui_shot import load_fonts

    app = QApplication.instance() or QApplication([])
    print("已加载中文字体：", load_fonts(app)[:3])

    from qfluentwidgets import FluentIcon as FIF, PrimaryPushButton

    run_btn = PrimaryPushButton(FIF.PLAY, "生成预览")
    run_btn.setFixedHeight(36)
    submit_btn = PrimaryPushButton(FIF.ACCEPT, "提交本次任务（有新版本）")
    submit_btn.setFixedHeight(36)

    for col_width in (340, 440):
        each = (col_width - 8) // 2
        for btn, name in ((run_btn, "生成预览"), (submit_btn, "长文案提交")):
            btn.resize(each, 36)
            print(
                f"控制列 {col_width}px → 每按钮 {each}px | {name}: "
                f"sizeHint 需要 {btn.sizeHint().width()}px "
                f"（{'放得下' if btn.sizeHint().width() <= each else '会被截断'}）"
            )


if __name__ == "__main__":
    main()
