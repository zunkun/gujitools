# -*- coding: utf-8 -*-
"""方向键翻页推广到**所有步骤**（「焦点在哪里，哪里就切换」）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _tmp_png
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QSize, Qt
    from desktop.store.tasks import STAGES
    from desktop.components.viewers.thumb_strip import ThumbStrip
    from tests.selftests._context import ok, pump
    from desktop.steps import ports
    from desktop.store.tasks import STAGES
    from desktop.steps import ports

    declared = {
        stage: ports.spec_for_stage(stage).preview_attr  # type: ignore[reportOptionalMemberAccess]  # STAGES 里的每个阶段都注册了 spec
        for stage in STAGES
    }
    ok("每一步都声明了主预览控件（preview_attr 非空）",
       all(declared.values()), str(declared))
    ok("声明的预览控件在页面上真实存在",
       all(getattr(st.detail, attr, None) is not None
           for attr in declared.values()), str(declared))
    ok("四步预览组件都有 navigate 入口",
       all(hasattr(getattr(st.detail, attr, None), "navigate")
           for attr in declared.values()), str(declared))
    from desktop.components.viewers.thumb_strip import ThumbStrip

    nav_strip = ThumbStrip()
    for i in range(3):
        nav_strip.add_page_item(str(i))
    nav_strip.setCurrentRow(2)
    nav_strip.navigate(True)
    ok("末页再前进不回绕（ThumbStrip.navigate 夹取，唯一逻辑处）",
       nav_strip.currentRow() == 2, str(nav_strip.currentRow()))
    nav_strip.navigate(False)
    nav_strip.navigate(False)
    ok("首页再后退同样夹住", nav_strip.currentRow() == 0,
       str(nav_strip.currentRow()))
    # ⚠️ 竖排条里 ←/→ 没有相邻格，QListWidget 对它们毫无反应（↑/↓ 却能移动
    # 选择）——用户实测「上下可以切换、左右不行」。条内必须显式翻译成翻页。
    from PySide6.QtTest import QTest

    kb_strip = ThumbStrip()
    for i in range(3):
        kb_strip.add_page_item(str(i))
    kb_strip.show()                       # ⚠️ 不 show 的话 QTest 按键不可靠
    pump(st.app, times=2)
    kb_strip.setFocus()
    pump(st.app, times=2)
    kb_strip.setCurrentRow(0)
    QTest.keyClick(kb_strip, Qt.Key.Key_Right)
    pump(st.app, times=2)
    ok("条内按 → 翻页（焦点在缩略图条上也要能左右切换）",
       kb_strip.currentRow() == 1, str(kb_strip.currentRow()))
    QTest.keyClick(kb_strip, Qt.Key.Key_Left)
    pump(st.app, times=2)
    ok("条内按 ← 翻回", kb_strip.currentRow() == 0, str(kb_strip.currentRow()))
    kb_strip.deleteLater()

    nav_widget = PrintPreviewWidget()
    try:
        nav_src = _tmp_png(st.tmp / "nav-src.png", 400, 560)
        nav_widget.set_entries(
            [{"file": str(nav_src), "label": str(i)} for i in range(1, 5)]
        )
        nav_widget.strip.setCurrentRow(1)
        pump(st.app, times=2)
        nav_widget.navigate(True)
        pump(st.app, times=2)
        ok("navigate(True) 前进一行（联动预览刷新）",
           nav_widget.strip.currentRow() == 2, str(nav_widget.strip.currentRow()))
        nav_widget.navigate(False)
        pump(st.app, times=2)
        ok("navigate(False) 后退一行",
           nav_widget.strip.currentRow() == 1, str(nav_widget.strip.currentRow()))
        nav_widget.strip.setCurrentRow(3)
        pump(st.app, times=2)
        nav_widget.navigate(True)
        pump(st.app, times=2)
        ok("末页再前进不回绕（夹在两端）",
           nav_widget.strip.currentRow() == 3, str(nav_widget.strip.currentRow()))
    finally:
        nav_widget.deleteLater()

