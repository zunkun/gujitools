# -*- coding: utf-8 -*-
"""图片编辑器「完成 = 覆盖原图」自测（2026-10-01 需求：编辑结果要生效）。

断言线（都只看可观测行为，不看实现细节）：

1. **回写路径**：``ZoomTarget.save_path`` 存在时，编辑器「完成」把结果
   **原子覆盖**到原文件（像素真的变了），并发 ``image_saved``、更新画布；
2. **虚拟图不写回**：没有 ``save_path``（区域合成/打印重排/PDF 页）时维持
   旧行为——只更新画布、不覆盖任何文件、不发 ``image_saved``；
3. **原图读取失败**不覆盖任何东西（tip 提示，画布保持旧图）；
4. **原子覆盖的安全性**：硬链接另一头不受影响（就地写会把源文件一起改掉）、
   落盘后目录里不剩 ``.part`` 半截文件；
5. **文案**：``save_back=True`` 的编辑器明确说「完成 = 覆盖原图片」，
   不再让用户以为要去「下载」。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

NAME = "image_editor_saveback"
DEPENDS: list[str] = []
TITLE = "图片编辑器覆盖原图"


def _make_image(width: int = 64, height: int = 48, color: str = "#ffffff"):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(color))
    return image


def _pixel_is(image, x: int, y: int, expected: str, tol: int = 40) -> bool:
    """颜色近似相等（JPEG 有损，solid 色写出再读回会有几十级漂移）。"""
    from PySide6.QtGui import QColor

    want = QColor(expected)
    got = image.pixelColor(x, y)
    return (
        abs(got.red() - want.red()) <= tol
        and abs(got.green() - want.green()) <= tol
        and abs(got.blue() - want.blue()) <= tol
    )


class _StubEditor:
    """替身编辑器：_edit_image 只依赖 exec() 与 result_image() 两个接口。"""

    def __init__(self, result, code):
        from PySide6.QtWidgets import QDialog

        self._result = result
        self._code = code

    def exec(self):
        return self._code

    def result_image(self):
        return self._result


def run(ctx) -> None:
    from PySide6.QtWidgets import QDialog

    from tests.selftests._context import ok, pump

    from desktop.components.viewers.image_zoom_dialog import (
        ImageZoomDialog, ZoomTarget, overwrite_image_file,
    )

    app = ctx.app
    tmp = Path(tempfile.mkdtemp(prefix="guji_saveback_"))
    try:
        # ---------------------------------------------------- 原子覆盖工具
        target = tmp / "0001.jpg"
        original = _make_image(color="#ffffff")
        ok("准备：原图可写出", original.save(str(target), "JPEG", 90))

        hardlink = tmp / "hardlink.jpg"
        if not hardlink.exists():
            os.link(target, hardlink)
        ok("准备：硬链接已建立", hardlink.exists())

        edited = _make_image(color="#ff0000")
        ok("覆盖原图成功", overwrite_image_file(edited, target))
        from PySide6.QtGui import QImage

        reread = QImage(str(target))
        ok("覆盖后像素真的是编辑结果",
           not reread.isNull() and _pixel_is(reread, 2, 2, "#ff0000"))
        ok("硬链接另一头保持旧图（不许就地写穿）",
           _pixel_is(QImage(str(hardlink)), 2, 2, "#ffffff"))
        ok("落盘后不剩 .part 半截文件",
           not list(tmp.glob("*.part")))
        ok("未知后缀按 PNG 兜底也能写出",
           overwrite_image_file(edited, tmp / "page.xxx"))

        # ---------------------------------------------------- 文案
        from desktop.components.viewers.image_editor import ImageEditorDialog

        saveback_dialog = ImageEditorDialog(None, _make_image(), save_back=True)
        ok("可回写时「完成」明说覆盖原图片",
           "覆盖原图片" in saveback_dialog.done_btn.toolTip(),
           saveback_dialog.done_btn.toolTip())
        from qfluentwidgets import CaptionLabel

        hints = [
            label.text()
            for label in saveback_dialog.findChildren(CaptionLabel)
            if label.text()
        ]
        ok("可回写时状态行同步提醒", any("覆盖原图片" in text for text in hints),
           str(hints))
        saveback_dialog.deleteLater()
        plain_dialog = ImageEditorDialog(None, _make_image())
        ok("虚拟图维持「下载」口径",
           "覆盖原图片" not in plain_dialog.done_btn.toolTip())
        plain_dialog.deleteLater()
        pump(app, times=2)

        # ---------------------------------------------------- 回写路径
        real_target = tmp / "0002.png"
        ok("准备：PNG 原图可写出", _make_image().save(str(real_target), "PNG"))

        dialog = ImageZoomDialog()
        dialog._target = ZoomTarget(
            render=lambda edge: None, save_path=real_target
        )
        saved: list[tuple] = []
        dialog.image_saved.connect(lambda p, img: saved.append((p, img)))
        red = _make_image(color="#00aa00")

        original_open = ImageZoomDialog._open_editor

        def _stub_open(self, image, save_back: bool = False):
            self._stub_save_back = save_back
            return _StubEditor(red, QDialog.DialogCode.Accepted)

        try:
            ImageZoomDialog._open_editor = _stub_open
            dialog._edit_image()
        finally:
            ImageZoomDialog._open_editor = original_open

        ok("编辑器以 save_back 模式打开", dialog._stub_save_back is True)
        ok("「完成」发出 image_saved（路径 + 编辑图）",
           len(saved) == 1 and saved[0][0] == str(real_target)
           and saved[0][1].pixelColor(2, 2).name() == "#00aa00",
           str([(p, i.pixelColor(2, 2).name()) for p, i in saved]))
        ok("原文件被覆盖为编辑结果",
           _pixel_is(QImage(str(real_target)), 2, 2, "#00aa00"))
        ok("画布同步更新为编辑结果",
           dialog.canvas.export_image().pixelColor(2, 2).name() == "#00aa00")

        # ---------------------------------------------------- 拒绝 = 不写
        saved.clear()
        dialog._open_editor = lambda image, save_back=False: _StubEditor(
            red, QDialog.DialogCode.Rejected
        )
        dialog._edit_image()
        ok("取消编辑不覆盖文件",
           _pixel_is(QImage(str(real_target)), 2, 2, "#00aa00"))
        ok("取消编辑不发 image_saved", saved == [])

        # ---------------------------------------------------- 虚拟图
        virtual = tmp / "virtual.jpg"
        ok("准备：虚拟参照文件可写出", _make_image().save(str(virtual), "JPEG"))
        dialog2 = ImageZoomDialog()
        dialog2.canvas.set_image(_make_image(color="#ffffff"))
        dialog2._target = ZoomTarget(render=lambda edge: None)  # 无 save_path
        saved2: list[tuple] = []
        dialog2.image_saved.connect(lambda p, img: saved2.append((p, img)))
        blue = _make_image(color="#0000ff")

        def _stub_open2(self, image, save_back: bool = False):
            self._stub_save_back = save_back
            return _StubEditor(blue, QDialog.DialogCode.Accepted)

        try:
            ImageZoomDialog._open_editor = _stub_open2
            dialog2._edit_image()
        finally:
            ImageZoomDialog._open_editor = original_open

        ok("虚拟图不走 save_back 模式", dialog2._stub_save_back is False)
        ok("虚拟图只更新画布、不覆盖文件",
           dialog2.canvas.export_image().pixelColor(2, 2).name() == "#0000ff"
           and _pixel_is(QImage(str(virtual)), 2, 2, "#ffffff"))
        ok("虚拟图不发 image_saved", saved2 == [])

        # ---------------------------------------------------- 读取失败
        dialog3 = ImageZoomDialog()
        dialog3.canvas.set_image(_make_image(color="#ffffff"))
        dialog3._target = ZoomTarget(
            render=lambda edge: None, save_path=tmp / "missing.png"
        )
        saved3: list[tuple] = []
        dialog3.image_saved.connect(lambda p, img: saved3.append((p, img)))
        try:
            ImageZoomDialog._open_editor = _stub_open2
            dialog3._edit_image()
        finally:
            ImageZoomDialog._open_editor = original_open

        ok("原图读不到：不动编辑器、不覆盖、不发信号",
           saved3 == []
           and dialog3.canvas.export_image().pixelColor(2, 2).name() == "#ffffff"
           and "无法读取原图" in dialog3.tip_label.text(),
           dialog3.tip_label.text())

        # ---------------------------------------------------- 宿主上屏接口
        from desktop.components.viewers.image_viewer import ImageViewerWidget

        page = tmp / "0003.png"
        ok("准备：主查看器页面图可写出", _make_image().save(str(page), "PNG"))
        viewer = ImageViewerWidget()
        try:
            viewer.set_images([page])
            pump(app, times=6)
            edited_page = _make_image(color="#112233")
            viewer.apply_edited_image(str(page), edited_page)
            pump(app, times=2)
            ok("接口：编辑图立即上屏主查看器画布（不等重解码）",
               viewer.view.has_image
               and viewer.info_label.text() == "64 × 48 px",
               f"info={viewer.info_label.text()!r} has={viewer.view.has_image}")
        finally:
            viewer.shutdown_workers()
            viewer.deleteLater()
        pump(app, times=2)

        for d in (dialog, dialog2, dialog3):
            d.close()
            d.deleteLater()
        pump(app, times=2)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
