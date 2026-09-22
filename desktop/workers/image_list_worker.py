# -*- coding: utf-8 -*-
"""图片清单缩略图生成（用于阶段页面列表）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QImage, QImageReader

from desktop.workers.preview_worker import compose_outputs_horizontal, compose_region_output


class ImageListWorker(QObject):
    """为一份图片路径清单生成缩略图（用于阶段页面列表）。

    使用 QImageReader 的缩放解码，避免把原始分辨率扫描图整张解入内存。
    effects 与 paths 对齐：非空时先按 area/border 规则合成效果再缩放
    （用于 print 列表的效果预览）。
    """

    thumbnail_ready = Signal(int, QImage, str)  # index, thumbnail, path
    completed = Signal()
    failed = Signal(str)

    def __init__(
        self,
        paths: list[Path],
        edge: int = 96,
        effects: list | None = None,
        crops: list | None = None,
        cache_dir: Path | None = None,
    ):
        """构造图片清单缩略图 worker。

        paths 为目标图片；edge 为缩略图最长边（默认 96）。effects/crops
        与 paths 对齐：非空时先按 area/border 合成效果或按像素框裁剪，
        再缩放到 edge（用于 print 列表效果预览）。

        cache_dir 给定时启用**磁盘缩略图缓存**（``<stem>.jpg``）。只有
        「既无 effect 也无 crop」的纯缩放结果才走缓存——带参数的合成结果
        尺寸取决于参数，缓存下来会串味。命中且不比源图旧就直接读小图，
        省掉整张原图的解码：详情页每次切阶段都会重建图条，而源图动辄
        两三千像素。
        """
        super().__init__()
        self.paths = paths
        self.edge = edge
        self.effects = effects
        # 与 paths 对齐的裁剪框列表（各自图片的像素坐标），None 表示不裁剪
        self.crops = crops
        self.cache_dir = Path(cache_dir) if cache_dir else None

    @staticmethod
    def _cache_fresh(cache_file: Path, source: Path) -> bool:
        """缓存文件存在、且不比源图旧（源图重新生成过就作废）。"""
        try:
            return (
                cache_file.exists()
                and cache_file.stat().st_mtime >= source.stat().st_mtime
            )
        except OSError:
            return False

    @Slot()
    def run(self) -> None:
        """逐图生成缩略图，发 thumbnail_ready(index, image, path)，结束发 completed。"""
        try:
            for index, path in enumerate(self.paths):
                crop = self.crops[index] if getattr(self, "crops", None) else None
                effect = (
                    self.effects[index]
                    if getattr(self, "effects", None)
                    else None
                )
                reader = QImageReader(str(path))
                reader.setAutoTransform(True)
                if crop is None and not effect:
                    size = reader.size()
                    if size.isValid():
                        reader.setScaledSize(
                            size.scaled(
                                QSize(self.edge, self.edge), Qt.KeepAspectRatio
                            )
                        )
                image = reader.read()
                if image.isNull():
                    # 回退：整图解码后内存缩放（部分格式/异常文件缩放解码会失败）
                    image = QImage(str(path))
                if image.isNull():
                    continue
                if effect and any(effect.get("boxes") or []):
                    outputs = compose_region_output(
                        image,
                        effect.get("boxes", []),
                        int(effect.get("area", 1)),
                        effect.get("border"),
                        dpi=int(effect.get("dpi", 300)),
                    )
                    image = compose_outputs_horizontal(outputs)
                    if image.isNull():
                        continue
                if crop:
                    x1, y1, x2, y2 = (int(round(v)) for v in crop[:4])
                    image = image.copy(
                        max(x1, 0), max(y1, 0),
                        max(x2 - x1, 1), max(y2 - y1, 1),
                    )
                    if image.isNull():
                        continue
                if image.width() > self.edge or image.height() > self.edge:
                    image = image.scaled(
                        self.edge,
                        self.edge,
                        aspectMode=Qt.KeepAspectRatio,
                        mode=Qt.SmoothTransformation,
                    )
                self.thumbnail_ready.emit(index, image, str(path))
            self.completed.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
