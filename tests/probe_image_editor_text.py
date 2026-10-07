# -*- coding: utf-8 -*-
"""探针：图片编辑 → 文字工具的选项行 / 颜色面板观感与关键行为。

跑法（离屏）：
    QT_QPA_PLATFORM=offscreen python tests/probe_image_editor_text.py

产出（本目录）：``_probe_editor_text.png``（整窗）、``_probe_option_row.png``
（选项行）、``_probe_color_panel.png``（颜色面板）。

离屏平台插件取不到系统字体，脚本会显式注册几个 Windows 字体——否则截图里
全是豆腐块，看不出字体下拉到底有没有中文。自测那边只断言行为（见
``tests/selftests/image_editor.py``），这里专门看"好不好看"。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QColor, QFontDatabase, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simkai.ttf",
    r"C:\Windows\Fonts\simfang.ttf",
)
for font_path in FONT_CANDIDATES:
    if Path(font_path).exists():
        QFontDatabase.addApplicationFont(font_path)

from desktop.components.viewers.image_editor import ImageEditorDialog  # noqa: E402
from desktop.ui.color_picker import ColorPickerButton  # noqa: E402
from qfluentwidgets import ComboBox, Slider  # noqa: E402

OUT = Path(__file__).parent

image = QImage(560, 300, QImage.Format.Format_ARGB32)
image.fill(QColor("#fbf8f1"))

dialog = ImageEditorDialog(None, image)
dialog.resize(1100, 720)
dialog.show()
for _ in range(6):
    app.processEvents()
dialog._set_tool("text")
for _ in range(6):
    app.processEvents()

page = dialog._option_page
# 切成 text 工具后 _option_page 才被换上（源码侧标注是 QWidget | None）
assert page is not None
combo = page.findChild(ComboBox)
slider = page.findChild(Slider)
picker = page.findChild(ColorPickerButton)
# 这三个控件由 ImageEditorDialog 建的时候挂上去的，拿不到就是源码变了，
# 直接断掉（否则下面全是 AttributeError，读不出真正的失败原因）
assert combo is not None and slider is not None and picker is not None

print("字体下拉：%d 项" % combo.count())
print("  前 12：", [combo.itemText(i) for i in range(min(12, combo.count()))])
print("  后 8 ：", [combo.itemText(i)
                    for i in range(max(0, combo.count() - 8), combo.count())])
print("当前字体：", combo.currentText())
print("字号滑杆 focusPolicy：", slider.focusPolicy(), "（应为 NoFocus）")
print("颜色按钮初始色：", picker.color().name())

# 字号：焦点先被滑杆抢走，字号仍必须落在当前文字块上（2026-10-01 回归点）
canvas = dialog.canvas
block = canvas.add_text_block(QPointF(40, 40), dialog._text_size,
                              QColor(dialog._text_color), dialog._text_family)
block.setPlainText("古籍批注")
app.processEvents()
before = block.boundingRect().height()
slider.setFocus()
app.processEvents()
slider.setValue(120)
app.processEvents()
print("字号 48→120：块高 %.0f → %.0f（生效=%s）"
      % (before, block.boundingRect().height(),
         block.boundingRect().height() > before * 2))

# 颜色面板：截图 + 面板内点常用色块
picker._open_popup()
app.processEvents()
panel = picker.popup()
assert panel is not None     # ⚠️ _open_popup 之后必然弹出面板
print("颜色面板：%dx%d，色块 %d 个"
      % (panel.size().width(), panel.size().height(), len(panel._swatches)))
panel.grab().save(str(OUT / "_probe_color_panel.png"))
zhu = next(s for s in panel._swatches
           if s.color().name().lower() == "#d32f2f")
zhu.click()
app.processEvents()
print("点「朱批」后：文字色 %s，面板已收起 %s"
      % (block.defaultTextColor().name(), not panel.isVisible()))

app.processEvents()
dialog.grab().save(str(OUT / "_probe_editor_text.png"))
page.grab().save(str(OUT / "_probe_option_row.png"))
print("截图已写入", OUT)
