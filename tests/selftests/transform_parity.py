# -*- coding: utf-8 -*-
"""统一变换的「画布预览」与「烘焙结果」逐像素对照（probe_xf_parity 转正）。

判据：预览（画布上看到的那张图）应当 == 烘焙产物（松手/离开工具后落地的
像素）。任何"框摆在这儿、内容却落在别处""内容被裁掉一块"都会在这里红——
用户 2026-10-09 报的「操作框跟图片分离」正是从这个盲区过去的（当时只有
探针、没有回归）。

转正时钉死 12 个场景（2026-10-12）：旋转/平移/切变/缩放 × 整幅/局部，
外加裁剪档、原比例档、校正（backward）方向。判据是**平均通道差 < 6**：

- 浮层的像素本来就是"选区按 ``_xf_preview_scale`` 缩过的"，放大回来看必然
  比烘焙糊一点（1px 细线被抹成浅带），逐像素差能到 6 上下——那是**分辨率**
  差、不是位置差，所以先把烘焙按 k 降采样对掉再比；
- **位置错**（偏几十上百像素）在任何口径下都是几十以上的差，藏不住。

⚠️ 页面尺寸必须**大于** ``TRANSFORM_PREVIEW_PIXELS``（0.5 MP）：
600×800 只有 0.48 MP ⇒ ``_xf_preview_scale`` 恒为 1，预览尺度那套矩阵
（``S(1/k) * placed * S(k)``）根本走不到，全绿也说明不了问题。
"""

from __future__ import annotations

from pathlib import Path

NAME = "transform_parity"
DEPENDS: list[str] = []
TITLE = "变换预览==烘焙逐像素对照（12 场景）"

THRESHOLD = 6.0
W, H = 1000, 1400


def _make_page():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(QColor("#f2ecdd"))
    p = QPainter(img)
    p.setPen(QColor("#111111"))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(20, 20, W - 40, H - 40)
    for x in range(60, W - 30, 60):
        p.drawLine(x, 40, x, H - 40)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#cc2222"))
    p.drawRect(30, 30, 90, 90)
    p.setBrush(QColor("#2244cc"))
    p.drawRect(W - 120, H - 120, 90, 90)
    p.end()
    return img


def _canvas_shot(canvas, rect) -> "QImage":
    """把场景按 ``rect``（图片坐标）1:1 渲染成一张图。

    ⚠️ 垫底用**白**：画布上"空"的那块（选区被搬走之后）是**透明的**，而烘焙
    产物是白底——比的是"内容落在纸上"，垫白再比。
    """
    from PySide6.QtGui import QColor, QImage, QPainter

    out = QImage(max(1, int(rect.width())), max(1, int(rect.height())),
                 QImage.Format.Format_ARGB32)
    out.fill(QColor("#ffffff"))
    p = QPainter(out)
    canvas._scene.render(p, out.rect(), rect)
    p.end()
    return out


def _argb32(_image):
    """ARGB32 格式（两臂比差异前统一到同一格式）。"""
    from PySide6.QtGui import QImage

    return QImage.Format.Format_ARGB32


def _diff(a, b) -> float:
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


def _down_up(image, scale: float):
    """缩到 ``scale`` 倍再放大回来——"只有降采样那么清晰"的版本（对掉分辨率差）。"""
    from PySide6.QtCore import Qt

    if scale >= 0.999:
        return image
    small = image.scaled(max(1, int(image.width() * scale)),
                         max(1, int(image.height() * scale)),
                         Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return small.scaled(image.width(), image.height(),
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


def _case(ok, title: str, act, *, rect=None, clipping="adjust", direction="forward") -> None:
    from PySide6.QtCore import QRectF

    from desktop.components.viewers.image_editor.canvas.core import EditorCanvas
    from desktop.components.viewers.image_editor.geometry import (
        center_crop_aspect,
        compose_transform,
    )

    image = _make_page()
    canvas = EditorCanvas()
    try:
        canvas.resize(900, 900)
        canvas.set_image(image)
        canvas.set_tool("transform")
        canvas._xf_clipping = clipping
        canvas._xf_direction = direction
        canvas._xf_interpolation = "linear"
        canvas.show()
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
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
            ok(f"{title}：有待应用变换", False, "transform_pending() 为 None")
            return
        sel, xf, region = pending
        if direction == "backward":
            inverse, ok_inv = xf.inverted()
            if ok_inv:
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
        bake = bake.convertToFormat(_argb32(image))
        shot = _canvas_shot(canvas, QRectF(origin[0], origin[1],
                                           bake.width(), bake.height()))
        k = canvas._xf_preview_scale
        value = _diff(_down_up(bake, k), shot)
        raw = _diff(bake, shot)
        ok(f"{title}：预览与烘焙对齐（差 {value:.2f} < {THRESHOLD}，原样 {raw:.2f}）",
           value < THRESHOLD,
           f"{bake.width()}x{bake.height()} @ {origin} k={k:.3f} 差={value:.2f}")
    finally:
        canvas.deleteLater()


def run(ctx) -> None:  # noqa: ARG001 - 不需要共享夹具
    from tests.selftests._context import ok

    _case(ok, "整幅旋转30", lambda c: c.transform_rotate(30))
    _case(ok, "整幅平移", lambda c: c.transform_move(-40, 25))
    _case(ok, "整幅切变", lambda c: c.transform_shear("r", 0.25))
    _case(ok, "局部旋转30", lambda c: c.transform_rotate(30),
          rect=(120, 200, 260, 300))
    _case(ok, "局部平移", lambda c: c.transform_move(70, -50),
          rect=(120, 200, 260, 300))
    _case(ok, "整幅校正", lambda c: c.transform_rotate(20), direction="backward")
    _case(ok, "整幅裁剪档", lambda c: c.transform_rotate(20), clipping="clip")
    _case(ok, "整幅原比例", lambda c: c.transform_rotate(20), clipping="aspect")
    _case(ok, "局部裁剪档", lambda c: c.transform_move(90, -60),
          rect=(120, 200, 260, 300), clipping="clip")
    _case(ok, "局部原比例", lambda c: c.transform_move(90, -60),
          rect=(120, 200, 260, 300), clipping="aspect")
    _case(ok, "整幅缩放", lambda c: c.transform_scale(1.4, 0.7))
    _case(ok, "局部切变", lambda c: c.transform_shear("b", -0.3),
          rect=(120, 200, 260, 300))


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
