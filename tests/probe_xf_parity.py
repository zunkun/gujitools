# -*- coding: utf-8 -*-
"""探针：统一变换的「画布预览」与「烘焙结果」逐像素对照。

判据：预览（画布上看到的那张图）应当 == 烘焙产物（松手/离开工具后落地的
像素）。任何"框摆在这儿、内容却落在别处""内容被裁掉一块"都会在这里红。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QTransform  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from desktop.components.viewers.image_editor.canvas.core import (  # noqa: E402
    EditorCanvas,
)
from desktop.components.viewers.image_editor.geometry import (  # noqa: E402
    center_crop_aspect, compose_transform,
)


def make_page(width=1000, height=1400):
    """⚠️ 尺寸必须**大于** ``TRANSFORM_PREVIEW_PIXELS``（0.5 MP）。

    600×800 只有 0.48 MP ⇒ ``_xf_preview_scale`` 恒为 1，预览尺度那套矩阵
    （``S(1/k) * placed * S(k)``）根本走不到，"预览 vs 烘焙"全绿也说明不了
    问题——用户 2026-10-09 报的「操作框跟图片分离」正是从这个盲区过去的。
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
    p.drawRect(30, 30, 90, 90)
    p.setBrush(QColor("#2244cc"))
    p.drawRect(width - 120, height - 120, 90, 90)
    p.end()
    return img


def canvas_shot(canvas, rect: QRectF) -> QImage:
    """把场景按 ``rect``（图片坐标）1:1 渲染成一张图。

    ⚠️ 垫底用**白**：画布上"空"的那块（选区被搬走之后）现在是**透明**的
    （用户 2026-10-09：不再有白色区域），而烘焙产物那边仍然是白底——预览比的是
    "内容落在纸上"，所以垫纸色再比，不然会拿"格子 vs 白底"当差异。
    """
    out = QImage(max(1, int(rect.width())), max(1, int(rect.height())),
                 QImage.Format.Format_ARGB32)
    out.fill(QColor("#ffffff"))
    p = QPainter(out)
    canvas._scene.render(p, QRectF(out.rect()), rect)
    p.end()
    return out


def diff(a: QImage, b: QImage) -> float:
    """平均通道差（0–255）——只在同尺度同尺寸下比。"""
    if a.size() != b.size():
        return float("inf")
    total = 0
    count = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += (abs(ca.red() - cb.red()) + abs(ca.green() - cb.green())
                      + abs(ca.blue() - cb.blue()))
            count += 3
    return total / max(1, count)


def down_up(image: QImage, scale: float) -> QImage:
    """把 ``image`` 缩到 ``scale`` 倍再放大回来 —— "只有降采样那么清晰"的版本。

    ⚠️ 浮层的像素本来就是"选区按 ``_xf_preview_scale`` 缩过的"（预算
    ``TRANSFORM_PREVIEW_PIXELS``），放大回来看必然比烘焙**糊一点**：1px 细线
    会被抹成 1.7px 的浅带，逐像素差能到 6 上下。那是**分辨率**差、不是位置差。
    所以判"位置对不对"要先把这个分辨率差对掉；**位置错**（偏几十上百像素）
    在任何口径下都是几十以上的差，藏不住。
    """
    if scale >= 0.999:
        return image
    small = image.scaled(max(1, int(image.width() * scale)),
                         max(1, int(image.height() * scale)),
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return small.scaled(image.width(), image.height(),
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


def case(title: str, act, *, rect=None, clipping="adjust", direction="forward"):
    image = make_page()
    canvas = EditorCanvas()
    canvas.resize(900, 900)
    canvas.set_image(image)
    canvas.set_tool("transform")
    canvas._xf_clipping = clipping
    canvas._xf_direction = direction
    canvas._xf_interpolation = "linear"
    canvas.show()
    app.processEvents()
    canvas.fit()
    app.processEvents()
    if rect is not None:
        canvas._rect = QRectF(*rect)
        canvas._xf_pivot = canvas._rect.center()
        canvas._sync_overlay()
    act(canvas)
    app.processEvents()

    pending = canvas.transform_pending()
    if pending is None:
        print(f"{title}: 无待应用变换（跳过）")
        return
    sel, xf, region = pending
    if direction == "backward":
        inverse, ok = xf.inverted()
        if ok:
            xf = inverse
    grow = clipping != "clip"
    bake = compose_transform(image, sel, xf, region, grow=grow,
                             interpolation="linear")
    if grow:
        bake, origin = bake
    else:
        origin = (0.0, 0.0)
    if clipping == "aspect":
        cropped = center_crop_aspect(bake, image.width(), image.height())
        origin = (origin[0] + (bake.width() - cropped.width()) // 2,
                  origin[1] + (bake.height() - cropped.height()) // 2)
        bake = cropped
    bake = bake.convertToFormat(QImage.Format.Format_ARGB32)
    shot = canvas_shot(canvas, QRectF(origin[0], origin[1],
                                      bake.width(), bake.height()))
    k = canvas._xf_preview_scale
    # 位置判据：把"预览分辨率"这个因素对掉再比（见 down_up 的说明）
    value = diff(down_up(bake, k), shot)
    raw = diff(bake, shot)
    flag = "✅" if value < 6.0 else "❌"
    print(f"{flag} {title}: 烘焙 {bake.width()}x{bake.height()} @ {origin} "
          f"k={k:.3f} 对齐差 = {value:.2f}（原样 {raw:.2f}）")
    shot.save(f"tests/tmp/parity_{title}_preview.png")
    bake.save(f"tests/tmp/parity_{title}_bake.png")


case("整幅旋转30", lambda c: c.transform_rotate(30))
case("整幅平移", lambda c: c.transform_move(-40, 25))
case("整幅切变", lambda c: c.transform_shear("r", 0.25))
case("局部旋转30", lambda c: c.transform_rotate(30),
     rect=(120, 200, 260, 300))
case("局部平移", lambda c: c.transform_move(70, -50),
     rect=(120, 200, 260, 300))
case("整幅校正", lambda c: c.transform_rotate(20), direction="backward")
case("整幅裁剪档", lambda c: c.transform_rotate(20), clipping="clip")
case("整幅原比例", lambda c: c.transform_rotate(20), clipping="aspect")
case("局部裁剪档", lambda c: c.transform_move(90, -60), rect=(120, 200, 260, 300),
     clipping="clip")
case("局部原比例", lambda c: c.transform_move(90, -60), rect=(120, 200, 260, 300),
     clipping="aspect")
case("整幅缩放", lambda c: c.transform_scale(1.4, 0.7))
case("局部切变", lambda c: c.transform_shear("b", -0.3), rect=(120, 200, 260, 300))
