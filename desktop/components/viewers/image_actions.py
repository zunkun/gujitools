# -*- coding: utf-8 -*-
"""「编辑」菜单里「下载图片 / 打印图片」的通用实现。

菜单层只认页面上的 ``can_edit_* / edit_*`` 四对方法（见 ``desktop/ui/menu.py``），
具体取哪张图由各页面决定。本模块提供两件事：

- :func:`download_image` / :func:`print_image`：与图片预览弹窗同一套存盘/打印行为；
- :class:`ImageEditActionsMixin`：给「左栏就是一个查看器」的模块页直接混入，
  按查看器的当前条目取图。

⚠️ 取图一律走查看器自己的 ``current_display_path()`` / ``current_path()``：
PDF 矢量页这类**没有真实文件**的条目返回 ``None`` ⇒ 菜单项自然置灰，不硬渲。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QFileDialog, QWidget

from desktop.components.viewers.image_zoom_dialog.io import save_image


def load_image(path: str | Path) -> QImage | None:
    """按路径读整分辨率图（读不到/坏文件返回 ``None``）。

    用 ``QImageReader`` 而不是 ``QImage(path)``：前者能直接吃到 PNG/JPEG/TIFF
    的 EXIF 旋转标记，且对中文路径按 Qt 的文件名规则处理。
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    return None if image.isNull() else image


def download_image(
    image: QImage,
    stem: str,
    parent: QWidget | None,
    title: str = "保存图片",
) -> Path | None:
    """弹保存对话框并把整分辨率图写到磁盘（PNG/JPEG，与预览弹窗同规则）。"""
    suggested = str(Path.home() / f"{stem or 'image'}.png")
    path, selected = QFileDialog.getSaveFileName(
        parent, title, suggested,
        "PNG 图片（无损） (*.png);;JPEG 图片（有损，画质 95） (*.jpg *.jpeg)",
    )
    if not path:
        return None
    target = Path(path)
    if not target.suffix:
        target = target.with_suffix(
            ".jpg" if "jpg" in selected.lower() or "jpeg" in selected.lower()
            else ".png"
        )
    return target if save_image(image, target) else None


def print_image(
    image: QImage,
    parent: QWidget | None,
    title: str = "打印图片",
) -> bool:
    """把整分辨率图送到打印机：等比铺满可打印区并居中（不拉伸变形）。"""
    if image.isNull():
        return False
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(title)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    page = printer.pageRect(QPrinter.Unit.DevicePixel)
    scaled = image.scaled(
        page.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(printer)
    painter.drawImage(
        QPointF(page.x() + (page.width() - scaled.width()) / 2,
                page.y() + (page.height() - scaled.height()) / 2),
        scaled,
    )
    painter.end()
    return True


class ImageEditActionsMixin:
    """给「``self.viewer`` 是当前图来源」的模块页混入下载/打印能力。

    子类若当前图不来自 ``self.viewer``（如任务详情页按阶段选查看器），
    覆写 :meth:`_edit_image_path` 即可，四对方法不必重写。
    """

    if TYPE_CHECKING:
        # 宿主是 QWidget 子类：这里只做类型侧声明，运行时零副作用。
        def window(self) -> QWidget: ...

    def _edit_image_path(self) -> Path | None:
        """当前可下载/打印的真实图片文件；没有（PDF 虚拟页）时返回 ``None``。"""
        viewer = getattr(self, "viewer", None)
        if viewer is None:
            return None
        for name in ("current_display_path", "current_path"):
            getter = getattr(viewer, name, None)
            if not callable(getter):
                continue
            value = getter()
            if value:
                return Path(str(value))
        return None

    def can_edit_download_image(self) -> bool:
        path = self._edit_image_path()
        return path is not None and path.exists()

    def can_edit_print_image(self) -> bool:
        return self.can_edit_download_image()

    def edit_download_image(self) -> None:
        path = self._edit_image_path()
        if path is None:
            return
        image = load_image(path)
        if image is None:
            self._edit_image_toast("warning", "读不到图片", f"无法解码：{path}")
            return
        target = download_image(image, path.stem, self.window())
        if target is not None:
            self._edit_image_toast("success", "图片已保存", str(target))

    def edit_print_image(self) -> None:
        path = self._edit_image_path()
        if path is None:
            return
        image = load_image(path)
        if image is None:
            self._edit_image_toast("warning", "读不到图片", f"无法解码：{path}")
            return
        if print_image(image, self.window()):
            self._edit_image_toast("success", "已发送打印机", path.name)

    def _edit_image_toast(self, kind: str, title: str, content: str) -> None:
        """页面自己的提示出口；模块页由 ``ModulePage.toast`` 提供。"""
        toast = getattr(self, "toast", None)
        if callable(toast):
            toast(kind, title, content)
