# -*- coding: utf-8 -*-
"""「关于」弹窗（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from desktop.components.dialog_shell import shell_dialog
from desktop.ui import theme as T
from desktop.ui.widgets import ui_font

from ._qt import QFontMetrics
from .constants import BUTTON_OK
from .panels import _AboutPanel
from .verdicts import about_rows

def _about_size(window) -> tuple[int, int]:
    """「关于」弹窗的尺寸：**宽度按内容算**，高度交给外壳按内容量。

    ⚠️ 用户 2026-10-15 报「关于内容显示不完整」的另一半：写死 600 宽时，值列只有
    ~460px，而 Windows 路径这种**没有空格的长串**在 QLabel 的
    ``setWordWrap(True)`` 下不会折行（Qt 只在词边界断行）⇒ 直接被裁成半截。
    所以按"最长的键 + 最长的值"的字体宽度把弹窗撑开（宽度钳在 560~900 之间：
    再窄放不下键值对，再宽在小屏上会顶出去——``shell_dialog`` 仍会按屏幕夹一次）。

    ⚠️ 高度这里返回 **0**（= 别写死）：用户 2026-11-27 报「Linux 下高度被压缩、
    文字挤在一起」。原来写死 180 是按 Windows 字号量的，Linux 上正文行高更大，
    四行要 ~230px，布局最小高度撑破窗口高度后 Qt 只能裁着摆 ⇒ 行与行叠在一起。
    改由 ``shell_dialog(fit_height=True)`` 在排完布局后量实际所需高度。
    """
    rows = about_rows(window)
    metrics = QFontMetrics(ui_font(T.SIZE_BODY))
    key_w = max((metrics.horizontalAdvance(k) for k, _ in rows), default=0)
    value_w = max((metrics.horizontalAdvance(v) for _, v in rows), default=0)
    # 面板左右边距（shell_dialog 用 SPACE_XL）+ 键值间距（SPACE_LG）+ 一点余量
    width = key_w + value_w + 2 * T.SPACE_XL + T.SPACE_LG + 24
    return (max(560, min(900, int(width))), 0)


def open_about(window) -> None:
    """「关于」：程序名 / 版本 / 数据目录 / 项目地址。"""
    panel = _AboutPanel(about_rows(window))
    # 四行紧凑贴顶（对齐修好后多余高度都兜在末尾弹性行上），宽度按内容算
    # （见 _about_size：长路径不能被压成半截），高度按内容量
    # （fit_height：Linux 行高更大，写死高度会把行挤在一起）。
    shell_dialog(
        "关于",
        panel,
        window,
        size=_about_size(window),
        ok_text=BUTTON_OK,
        show_cancel=False,
        fit_height=True,
    ).exec()
