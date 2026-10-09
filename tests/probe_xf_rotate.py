# -*- coding: utf-8 -*-
"""探针：统一变换「只旋转」时的预览渲染实况（整幅选区）。

输出 ``tests/tmp/xf_rotate_before.png`` / ``..._after.png``，供肉眼比对
"底图是否还在、内容是否完整"。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from desktop.components.viewers.image_editor.canvas.core import (  # noqa: E402
    EditorCanvas,
)


def make_page(width=1000, height=1400):
    """⚠️ 必须**大于预览预算**（``TRANSFORM_PREVIEW_PIXELS`` = 0.5 MP）。

    600×800 只有 0.48 MP ⇒ ``_xf_preview_scale`` 恒为 1，预览尺度那套矩阵
    走不到，"只旋转"的定位错误就藏住了（用户 2026-10-09 第三轮报障正是这条）。
    """
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor("#f2ecdd"))
    p = QPainter(img)
    p.setPen(QColor("#111111"))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(20, 20, width - 40, height - 40)
    for x in range(60, width - 30, 60):
        p.drawLine(x, 40, x, height - 40)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#cc2222"))
    p.drawRect(30, 30, 90, 90)          # 左上角红块：一眼看出朝向
    p.setBrush(QColor("#2244cc"))
    p.drawRect(width - 120, height - 120, 90, 90)   # 右下角蓝块
    p.end()
    return img


def render_scene(canvas, path, pad=40):
    rect = canvas.sceneRect().adjusted(-pad, -pad, pad, pad)
    out = QImage(int(rect.width()), int(rect.height()),
                 QImage.Format.Format_ARGB32)
    out.fill(QColor("#8fa08f"))
    p = QPainter(out)
    canvas._scene.render(p, QRectF(out.rect()), rect)
    p.end()
    out.save(path)
    return path


canvas = EditorCanvas()
canvas.resize(900, 900)
canvas.set_image(make_page())
canvas.set_tool("transform")
canvas.show()
app.processEvents()
canvas.fit()
app.processEvents()

canvas.transform_rotate(30)
app.processEvents()
canvas._sync_overlay()
app.processEvents()

print("preview_scale =", canvas._xf_preview_scale)
print("xf_rect       =", canvas._xf_rect)
print("base_origin   =", canvas._xf_base_origin)
print("paint_image   =", None if canvas._paint_image is None
      else (canvas._paint_image.width(), canvas._paint_image.height()))
print("image size    =", canvas.image.width(), canvas.image.height())
print("float bbox    =", canvas._float_item.sceneBoundingRect())
quad = canvas._transform_quad()
xs = [point.x() for point in quad.values()]
ys = [point.y() for point in quad.values()]
expect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
got = canvas._float_item.sceneBoundingRect()
print("quad   bbox   =", expect)
print("对齐          =", "✅ 框与内容一致"
      if got.contains(expect) and abs(got.width() - expect.width()) <= 8
      else "❌ 框与内容分离")
print("拖动档 placed =", canvas._float_fast_xf().map(QPointF(0, 0)),
      "vs", canvas._placed_xf().map(QPointF(0, 0)))
print("视图锚点      =", canvas.mapFromScene(QPointF(0, 0)),
      "  sceneRect =", canvas.sceneRect())
print("float visible =", canvas._float_item.isVisible(),
      "opacity =", canvas._float_item.opacity())
print("item visible  =", canvas._item.isVisible(), "pos =", canvas._item.pos())
print("sceneRect     =", canvas.sceneRect())
print("saved         =", render_scene(canvas, "tests/tmp/xf_rotate_before.png"))

# 浮层像素本身（未套图元 transform 的"本地"画布）单独出图
plane = canvas._float_item.pixmap().toImage()
plane.save("tests/tmp/xf_float_plane.png")
print("float plane   =", plane.width(), plane.height())
backdrop = canvas._paint_image.copy()
backdrop.save("tests/tmp/xf_backdrop.png")
print("float xf      =", canvas._float_item.transform())
print("base rect     =", canvas._base_current_rect())
for pt in ((2, 2), (300, 400), (598, 798)):
    print("plane", pt, "=", plane.pixelColor(*pt).name(),
          "alpha", plane.pixelColor(*pt).alpha())
print("base  (2,2)   =", canvas._paint_image.pixelColor(2, 2).name())
