# -*- coding: utf-8 -*-
"""本包共享的常量、夹具与检查函数（由原大模块拆出）。"""

from __future__ import annotations

# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import cast

NAME = "preview_zoom"
DEPENDS: list[str] = []
TITLE = "图片预览弹窗"

#: 必须接上放大弹窗的四个预览宿主
#: ⚠️ 前三个 2026-10-07 起是**子包**（目录），故不写 ``.py``；
#:    ``module_source_text`` 两种形态都能解析。
HOST_FILES = [
    "desktop/components/viewers/image_viewer",
    "desktop/components/viewers/pdf_viewer.py",
    "desktop/components/viewers/rembg_viewer",
    "desktop/components/viewers/print_preview",
]


def make_image(width: int, height: int, marks: bool = False):
    """造一张测试图；marks=True 时在左上/右上放不同颜色（验翻转方向用）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#ffffff"))
    if marks:
        image.setPixelColor(0, 0, QColor("#ff0000"))          # 左上 红
        image.setPixelColor(width - 1, 0, QColor("#0000ff"))  # 右上 蓝
    return image


def rgb_array(image):
    """QImage → (h, w, 3) 的 float 数组（去掉行填充）。"""
    import numpy as np
    from PySide6.QtGui import QImage

    img = image.convertToFormat(QImage.Format.Format_RGB888)
    raw = np.frombuffer(bytes(img.constBits()), dtype=np.uint8)
    raw = raw[: img.height() * img.bytesPerLine()]
    return raw.reshape(img.height(), img.bytesPerLine())[
        :, : img.width() * 3
    ].reshape(img.height(), img.width(), 3).astype(float)


class _FakeWorker:
    """替身 worker：不真渲染，直接把给定图发回来（隔离弹窗自身逻辑）。

    ⚠️ 真 worker 是 ``QObject`` + ``run`` 槽 + ``finished`` 信号，弹窗只依赖
    这三样，所以替身必须长得一样（否则测的是替身而不是弹窗）。
    """

    def __init__(self, image, log: list):
        from PySide6.QtCore import QObject, Signal, Slot

        self._log = log

        class Worker(QObject):
            finished = Signal(int, object, str)
            failed = Signal(int, str)

            def __init__(self, image):
                super().__init__()
                self._image = image

            @Slot()
            def run(self):
                if self._image is None:
                    self.failed.emit(0, "没有图")
                else:
                    self.finished.emit(0, self._image, "")

        _ = (Slot,)
        self.instance = Worker(image)


def sharpness(image) -> float:
    """Laplacian 方差：越高越锐（糊图的高频被抹掉，这个值会明显掉）。"""
    import numpy as np

    gray = rgb_array(image).mean(axis=2)
    lap = (
        -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    return float(lap.var())


#: 仓库根（分片比原模块深一层，深两层，不能用 parents[2]/[3]）
import pathlib as _pathlib
ROOT = _pathlib.Path(__file__).resolve().parents[4]
