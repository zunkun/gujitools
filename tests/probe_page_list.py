# -*- coding: utf-8 -*-
"""临时探针：悬浮框位置/拖动/配色渲染确认。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF, QEvent, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from desktop.components.imposition.view import ImpositionViewWidget  # noqa: E402

view = ImpositionViewWidget()
view.resize(1000, 620)
pages = [
    {"items": [{"file": "D:/a/第一张右图.png"}, {"file": "D:/a/第一张左图.png"}]},
    {"items": [{"file": "D:/a/第二张右图.png"}, {"file": "D:/a/第二张左图.png"}]},
    {"items": [{"file": "D:/a/第三张右图.png"}, {"file": "D:/a/第三张左图.png"}]},
]
view.set_pages(pages, current=0)
view.show()
app.processEvents()

pl = view.page_list
bar = pl.select_bar
print("bar parent is view:", bar.parentWidget() is view)
for e in pl.entries():
    e.checkbox.setChecked(True)
app.processEvents()
col = pl.geometry()
g = bar.geometry()
print("col geom:", col, " bar geom:", g)
print("bar centered y:", abs(g.center().y() - col.center().y()) <= 2)
print("bar right overhang:", g.x() + g.width() - col.right())
print("delete qss red:", "#E02020" in bar.delete_button.styleSheet())
print("clear qss calm:", "#E6F2F4" in bar.clear_button.styleSheet())

out = Path(__file__).parent / "_probe_bar.png"
view.grab().save(str(out))

def _mouse(kind, pos):
    return QMouseEvent(kind, QPointF(pos[0], pos[1]),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)

bar.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, (5, 5)))
bar.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, (5, 65)))
bar.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, (5, 65)))
app.processEvents()
print("after drag: user_moved=", bar._user_moved, " geom=", bar.geometry())
view.grab().save(str(out).replace(".png", "_dragged.png"))
print("saved", out)
