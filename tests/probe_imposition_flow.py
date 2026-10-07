# -*- coding: utf-8 -*-
"""独立探针：绕开 gui_selftest 的 tasklist 模块（沙箱 QProcess 环境问题），
直接验证流程条「图片拼版」节点的布局顺序与选择联动（箭头修复的回归验证）。

用法：C:/Users/liuzu/anaconda3/python.exe tests/probe_imposition_flow.py
跑完自清理临时目录，退出码 0 = 全部通过。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 测试临时文件统一落点：tests/tmp/（见 tests/tmpdir.py）。
from tests.tmpdir import install as _install_tmpdir  # noqa: E402

_install_tmpdir()


def main() -> int:
    from PySide6.QtWidgets import QApplication, QStackedWidget

    from desktop.components.step_bar import _Connector
    from desktop.store import TaskStore
    from desktop.app import MainWindow
    from tests.selftests._context import make_pdf, pump

    results: list[tuple[bool, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        results.append((bool(cond), name if not detail else f"{name}（{detail}）"))

    tmp = Path(tempfile.mkdtemp(prefix="guji_probe_imposition_"))
    try:
        app = QApplication([])
        repo = TaskStore(tmp)
        pdf = make_pdf(tmp / "探针古籍.pdf", 6)
        tid = repo.create_task(pdf, "probe-hash", "探针任务")
        repo.copy_source_to_task(tid, pdf)

        w = MainWindow()
        w.store = repo
        w.list_page.store = repo
        w.detail_page.store = repo
        pages = w.findChild(QStackedWidget, "pageRoot")
        if pages is not None:
            pages.setCurrentWidget(w.detail_page)
        w.resize(1080, 720)
        w.show()
        pump(app, times=12)
        d = w.detail_page
        ok("进入任务详情", d.set_task(tid))
        pump(app, times=12)
        # 新判据（2026-09-30）：拼版节点只认「已知」的区域模式（面板值/草稿/
        # 执行历史），不再凭内置默认 area=1 冒出来——探针里用草稿确定 area=1。
        repo.save_draft(tid, "rembg", {"area": 1})
        d._refresh_imposition_node()
        pump(app, times=6)

        # ---- 布局顺序：节点前有箭头（本次修复的回归钉子）----
        # ⚠️ 流程条里放的是节点的**等宽槽位**（imposition_slot），虚线框在槽位里
        #     靠左贴合文字——见 desktop/components/step_bar.py 的说明。
        row = d.step_bar.layout()
        assert row is not None        # ⚠️ 步骤条必带布局
        pos = row.indexOf(d.step_bar.imposition_slot)
        order = []
        for i in range(row.count()):
            _it = row.itemAt(i)
            widget = _it.widget() if _it is not None else None
            if widget is d.step_bar.imposition_slot:
                order.append("拼")
            elif isinstance(widget, _Connector):
                order.append("→")
            elif widget is not None:
                order.append("步")
        _before = row.itemAt(pos - 1)
        ok("节点前有「去底色→拼版」箭头",
           pos > 0 and isinstance(_before.widget() if _before else None, _Connector))
        _after = row.itemAt(pos + 1)
        ok("节点后有「拼版→PDF」箭头",
           isinstance(_after.widget() if _after else None, _Connector))
        ok("整体顺序 步→步→步→箭→拼→箭→步",
           order[-8:] == ["步", "→", "步", "→", "步", "→", "拼", "→", "步"][-8:]
           or order == ["步", "→", "步", "→", "步", "→", "拼", "→", "步", None][:9],
           ",".join(order))

        # ---- 选择联动 ----
        ok("默认可见且未选择",
           d.step_bar.imposition_node.isVisible()
           and not d.step_bar.imposition_node.is_selected())
        d.imposition_enabled_checkbox.setChecked(True)
        pump(app)
        ok("勾选 → 节点已选择", d.step_bar.imposition_node.is_selected())
        ok("选择已落盘", bool((repo.load_draft(tid, "imposition") or {}).get("enabled")))
        d.imposition_enabled_checkbox.setChecked(False)
        pump(app)
        ok("取消 → 恢复未选择", not d.step_bar.imposition_node.is_selected())

        # ---- area 离开 1 → 节点消失 ----
        # host 是这一格的面板宿主（去底色面板），源码侧标注是 QWidget；
        # 运行时是带 area 属性的具体面板，这里按鸭子类型取用。
        host = cast(Any, d.control_stack.widget(2))
        host.area.setCurrentIndex(1)  # area=2
        d._flush_param_drafts()
        d._refresh_imposition_node()
        pump(app)
        ok("area=2 → 节点隐藏", not d.step_bar.imposition_node.isVisible())
        host.area.setCurrentIndex(0)  # 回到 area=1
        d._flush_param_drafts()
        d._refresh_imposition_node()
        pump(app)
        ok("area=1 → 节点恢复", d.step_bar.imposition_node.isVisible())

        failed = [name for passed, name in results if not passed]
        for passed, name in results:
            print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        print(f"探针 {len(results) - len(failed)}/{len(results)} 通过")
        return 1 if failed else 0
    finally:
        try:
            w.detail_page.shutdown_all_workers()
            w.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
