# -*- coding: utf-8 -*-
"""离屏探针：把预览区右键菜单**真渲染出来**看一眼观感（不是自测，不计数）。

用法（本机 py310）：

    QT_QPA_PLATFORM=offscreen python tests/probe_image_context_menu.py [输出目录]

产出 ``menu_edit.png``（有可回写文件：两项）与 ``menu_view.png``（PDF 矢量页：
只有「预览图片」）。qfluentwidgets 的 RoundMenu 是弹窗，``exec`` 会阻塞，这里
把 ``exec`` 换成「show → 截图 → hide」，只验证**画出来的样子**。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _capture(host, out: Path) -> None:
    import qfluentwidgets

    original = qfluentwidgets.RoundMenu.exec

    def _fake_exec(self, *args, **kwargs):
        self.show()
        for _ in range(10):
            host._app.processEvents()
            time.sleep(0.03)
        self.grab().save(str(out))
        self.hide()

    qfluentwidgets.RoundMenu.exec = _fake_exec
    try:
        host._open_zoom_menu()
    finally:
        qfluentwidgets.RoundMenu.exec = original


def main() -> int:
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication, QWidget

    from desktop.components.viewers.image_zoom_dialog import (
        ZoomPopupMixin, ZoomTarget,
    )

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("D:/tmp/shots")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication([])
    # 离屏环境默认没有中文字体，菜单文字会画成方块（豆腐块）——与真机无关，
    # 但截图就白截了。复用截图脚本的字体候选，把中文字体挂上再画。
    try:
        from tests.gui_shot import FONT_CANDIDATES

        for path in FONT_CANDIDATES:
            if Path(path).exists():
                index = QFontDatabase.addApplicationFont(path)
                if index >= 0:
                    families = QFontDatabase.applicationFontFamilies(index)
                    if families:
                        app.setFont(QFont(families[0], 10))
                        break
    except Exception as exc:  # noqa: BLE001 - 探针不该因字体失败而中断
        print(f"（字体加载跳过：{exc}）")

    class _Host(QWidget, ZoomPopupMixin):
        def __init__(self, target):
            super().__init__()
            self._app = app
            self._target = target
            self.resize(420, 300)

        def _zoom_index(self) -> int:
            return 0

        def _zoom_target(self, index: int):
            return self._target

    editable = _Host(ZoomTarget(render=lambda edge: None, edit_path=__file__))
    editable.show()
    app.processEvents()
    _capture(editable, out_dir / "menu_edit.png")

    readonly = _Host(ZoomTarget(render=lambda edge: None))
    readonly.show()
    app.processEvents()
    _capture(readonly, out_dir / "menu_view.png")

    print(f"已写出：{out_dir / 'menu_edit.png'}、{out_dir / 'menu_view.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
