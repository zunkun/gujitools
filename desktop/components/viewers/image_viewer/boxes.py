# -*- coding: utf-8 -*-
"""``ImageViewerWidget`` Mixin：**框数据接口**。

把检测框交给画布、选中与整幅模式查询。（从 ``image_viewer.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import ImageViewerHost
else:
    ImageViewerHost = object


class BoxesMixin(ImageViewerHost):
    """把检测框交给画布、选中与整幅模式查询。"""

    def apply_boxes(self, boxes: list[tuple], image_size: QSize, info_text: str = "",
                    full: bool = False, selected: int = -1) -> None:
        """在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。

        ``full=True`` 表示本页是整幅(fullcontent)：框显示为「整幅」且只允许一个；
        否则按框的**中心位置**显示为左/右框。名称/颜色由控件每帧现算，不用传。
        ``selected`` 为要选中的框下标（-1 = 不选），用于切换类型后保持选中。
        """
        if self.view.has_image:
            self.view.set_boxes(boxes, image_size, full=full, selected=selected)
            if info_text:
                self.info_label.setText(info_text)
        else:
            self._pending_boxes = (boxes, image_size, info_text, full, selected)


    def set_single_column(self, single_column: bool) -> None:
        """告知画布「整本书是单栏书」：横跨整页的半幅框标「半幅」而非左/右框。

        ⚠️ 结论来自整本书的统计（``utils.book_layout.profile_book``），由宿主
        算好后传入。这里只转发，判据不在本层重写。
        """
        self.view.set_single_column(single_column)

    def set_side_override(self, side: str | None, rerender: bool = True) -> None:
        """告知画布「用户在这个半幅页上指定了左/右」（``None``＝清除指定）。

        半幅的框横跨整页、中心压在中线上，按位置判左右没有意义，所以由用户
        指定（用户 2026-10-17）。指定值存在 boxes.json 的 ``side``。
        ``rerender=False``＝调用方随后还会 ``apply_boxes``，别画两遍。
        """
        self.view.set_side_override(side, rerender)

    def side_override(self) -> str | None:
        """当前页的用户指定左右（无指定为 ``None``）。"""
        return self.view.side_override()


    def single_column(self) -> bool:
        """当前是否按单栏书显示（宿主算标签文案时与画面保持同一口径）。"""
        return bool(self.view.single_column())


    def set_reference_boxes(self, boxes: list) -> None:
        """设置参考框（最终裁剪大框，虚线显示，不参与编辑）。"""
        self.view.set_reference_boxes(boxes)


    def select_box(self, index: int) -> None:
        """程序化选中第 index 个框（-1 = 取消选中）。"""
        self.view.select_box(index)


    def selected_index(self) -> int:
        """当前选中的框下标；无选中为 -1。"""
        return self.view.selected_index()


    def box_full_mode(self) -> bool:
        """本页是否为整幅(fullcontent)。"""
        return self.view.full_mode


    def box_kinds(self) -> list:
        """当前每个框的类型（"left"/"right"/"full"）。"""
        return self.view.box_kinds()


    def _boxes_edited(self, boxes: list) -> None:
        path = self.current_path()
        if path is not None:
            self.boxes_edited.emit(str(path), boxes)
