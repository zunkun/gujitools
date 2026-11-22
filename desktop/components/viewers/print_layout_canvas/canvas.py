# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``PrintLayoutCanvas`` 类头 + 初始化 + 对外 API（几何/鼠标/绘制在兄弟 Mixin）。"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget

from desktop.ui import theme as T
from utils.page_layout import (
    fit_rotated_rect, normalize_page_rotation,
)

from .geometry import GeometryMixin
from .mouse import MouseMixin
from .paint import PaintMixin


class PrintLayoutCanvas(GeometryMixin, MouseMixin, PaintMixin, QWidget):
    """A4 纸上的图片拖拽/缩放/旋转画布；rect_changed 发出页面 mm 坐标。"""

    rect_changed = Signal(list)  # [x_mm, y_mm, w_mm, h_mm]
    # 双击画布 → 宿主打开预览弹窗（看该页的打印效果放大；编辑态下没有
    # 别的双击语义，滚轮/拖拽都已被占用为编辑手势）
    double_clicked = Signal()
    # 右键画布 → 宿主弹出「预览图片 / 编辑图片」菜单（与其余步骤预览区同一套；
    # 有图才发，空页不弹）
    context_menu_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self._page_w_mm = 210.0
        self._page_h_mm = 297.0
        self._image: QImage | None = None
        #: 贴图用的已降采样底图 + 它的来源对象（见 DISPLAY_IMAGE_EDGE）。
        #: 键用对象本身做 `is` 比较而不是 id：旧图被回收后新对象可能拿到同一 id。
        self._display_source: QImage | None = None
        self._display_image: QImage | None = None
        #: 图片朝向（度，顺时针为正，(-180, 180]）：显示 + 落盘共用的同一份
        #: 状态，宿主经 ``rotation()`` 读取落盘 ``pages[].rotate``。
        self._rotation = 0.0
        self._plan = None          # PrintPagePlan：标题/页码/跳过态的来源
        self._rect_mm = [0.0, 0.0, 0.0, 0.0]
        self._pad = 18
        self._px_per_mm = 1.0
        self._off_x = float(self._pad)
        self._off_y = float(self._pad)
        self._mode: str | None = None  # move / resize / rotate
        self._corner = 0
        self._grab_x = 0.0
        self._grab_y = 0.0
        #: 旋转手势：起点角度 / 起点朝向 / 起点时的**未旋转内容尺寸**（mm）。
        #: 每帧从起点内容尺寸重算外接框，避免逐帧累积误差（与拼版同一做法）。
        self._grab_angle = 0.0
        self._grab_rotation = 0.0
        self._grab_content = (0.0, 0.0)
        # 原比例缩放（来自 print 参数 keep_ratio）：
        #   True  → 四角拖拽保持宽高比，且**不提供**四边手柄；
        #   False → 铺满语义，另给上/下/左/右四个边手柄，可单独拉伸改变比例。
        self._keep_ratio = True
        #: 拖拽开始时的框（页面 mm）。保比例的角拖拽必须以**起点**为基准算比例，
        #: 不能读拖动中的 _rect_mm（它每帧都在变，会越拖越偏）。
        self._grab_rect = [0.0, 0.0, 0.0, 0.0]
        self._dirty = False
        self.setMouseTracking(True)
        self.setStyleSheet(
            f"background:{T.SURFACE_SOFT}; border:1px solid {T.BORDER};"
            f" border-radius:{T.RADIUS_MD}px;"
        )

    # ------------------------------------------------------------------ API
    def set_page(
        self,
        page_w_mm: float,
        page_h_mm: float,
        image: QImage | None,
        rect_mm: Sequence[float],
        plan=None,
        keep_ratio: bool = True,
        rotate: float = 0.0,
    ) -> None:
        """设置页面尺寸、待绘制图片与初始图片框（页面 mm）。

        ``plan`` 为 ``utils.page_layout.PrintPagePlan``：本控件据它画标题/
        页码与「已跳过」提示——版面编辑不能只看图片，否则无从判断挪动后
        会不会压到字。传 None 表示纯图片编辑（无标题/页码）。

        ``keep_ratio``（print 参数 `keep_ratio`）：True（默认）= 四角拖拽
        **保持宽高比**、不提供四边手柄；False = 四角自由拉伸 + 上/下/左/右
        四个边手柄可单独拉伸（与「铺满可用区域」的自动排版语义配套）。

        ``rotate``：图片朝向（度，顺时针为正）。坐标框是**旋转后**的外接框；
        传入的 ``rect_mm`` 若与旋转后的比例不符（例如老数据），先等比收进
        这个框（与 PDF / 效果预览同一份 ``fit_rotated_rect``）。
        """
        self._page_w_mm = float(page_w_mm)
        self._page_h_mm = float(page_h_mm)
        self._image = image
        self._plan = plan
        self._keep_ratio = bool(keep_ratio)
        self._rect_mm = [float(v) for v in rect_mm]
        self._rotation = normalize_page_rotation(rotate)
        if self._rotation and image is not None and not image.isNull():
            self._rect_mm = fit_rotated_rect(
                self._rect_mm, (image.width(), image.height()), self._rotation
            )
        self._recompute()
        self.update()

    def current_rect(self) -> list[float]:
        """当前图片框（页面 mm），供宿主落盘前读取。"""
        return list(self._rect_mm)

    def rotation(self) -> float:
        """当前图片朝向（度，顺时针为正），供宿主落盘前读取。"""
        return self._rotation

    def set_rotation(self, degrees) -> None:
        """程序化设置朝向：绕框心重算外接框，并立即上报（与拖钮同口径）。"""
        if self._image is None or self._image.isNull():
            return
        angle = normalize_page_rotation(degrees)
        if angle == self._rotation:
            return
        content = self._content_size_mm(self._rect_mm, self._rotation)
        self._rotation = angle
        self._rect_mm = self._bbox_for_content(content, angle)
        self._dirty = False
        self.update()
        self.rect_changed.emit([round(v, 2) for v in self._rect_mm])

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        """显示时重算：首次进入第四步可能在布局完成前就 ``set_page`` 过，
        那时 ``width()/height()`` 还是 0，``_px_per_mm`` 会退化为 1.0。
        仅靠 resizeEvent 兜不住「已分配尺寸但从未显示」的情况。"""
        super().showEvent(event)
        self._recompute()
        self.update()
