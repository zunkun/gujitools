# -*- coding: utf-8 -*-
"""大图查看控件：随控件尺寸缩放，支持叠加切割框。

坐标基准是图片原始像素坐标（_image_size），与预览显示缩放无关。

开启 boxes_editable 后：
- 点击框选中（四角出现缩放手柄），拖动框内移动整框，拖手柄缩放；
- 在空白处按下并拖动可手绘一个新框；
- Delete/Backspace 删除选中框；
- 每次修改结束通过 boxes_edited 发出全部框（仅内存与信号，不落盘）。

reference_boxes 为参考框（如按 area/border 规则推导的最终裁剪大框），
橙色虚线显示，不参与编辑。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel

from desktop.ui import theme as T

# 框颜色：绿/蓝/琥珀对应左框/右框/合并框，与检测语义一致
BOX_COLORS = [QColor("#21c178"), QColor("#3b82f6"), QColor("#f59e0b")]
BOX_NAMES = ["左框", "右框", "合并框"]
REFERENCE_COLOR = QColor("#f97316")
HANDLE_RADIUS = 5  # 缩放手柄半径（控件像素）

# 选中框四角手柄：0=左上 1=右上 2=右下 3=左下
_HANDLE_CURSORS = [
    Qt.SizeFDiagCursor, Qt.SizeBDiagCursor,
    Qt.SizeFDiagCursor, Qt.SizeBDiagCursor,
]


class ImageView(QLabel):
    """大图查看：随控件尺寸实时缩放，支持在图片坐标系叠加切割框。"""

    boxes_edited = Signal(list)  # 移动/缩放/删除/新增后：全部框（图片像素坐标）
    #: 双击大图（宿主据此打开图片预览弹窗；只读查看，不改任何数据）
    double_clicked = Signal()

    #: 预览渲染最长边的**下限**：控件尚未布局（尺寸还是 0）时的兜底，也避免
    #: 小控件把预览渲染得过小——之后窗口一最大化就只能放大、糊掉。
    MIN_PREVIEW_EDGE = 1200
    #: 预览渲染最长边的**上限**：超大窗口 × 高分屏下别为一页预览分配几十 MB。
    #: 3000px 竖页约 37 MB（RGB32），是渲染耗时与内存的折中。
    MAX_PREVIEW_EDGE = 3000

    def __init__(self, placeholder: str = "无预览", parent=None):
        """初始化画布与框编辑状态；placeholder 为空图时的占位文案。"""
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 300)
        self.setText(placeholder)
        # 浅色画布：古籍页面本身是白底，深色底会把页面衬得像悬浮贴片；
        # 空状态也用同一底色，避免出现一大块"黑屏"观感
        self.setStyleSheet(
            f"background:{T.SURFACE_SOFT}; color:{T.INK_FAINT};"
            f" border:1px solid {T.BORDER}; border-radius:{T.RADIUS_MD}px;"
        )
        self._pixmap: QPixmap | None = None
        self._boxes: list[list[int]] = []  # [(x1,y1,x2,y2)] 图片像素坐标
        self._reference_boxes: list = []  # 参考框（最终裁剪大框），虚线显示
        self._image_size: QSize | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self._boxes_editable = False
        self._selected: int | None = None
        self._mode: str | None = None  # move / resize / new
        self._ghost_box: list | None = None
        self._dirty = False  # 本次拖动/缩放是否实际改变了坐标
        self._drag_index: int | None = None
        self._grab_dx = 0
        self._grab_dy = 0
        self._resize_corner = 0
        self._new_start: tuple[float, float] | None = None
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._offset_x = 0
        self._offset_y = 0
        #: 本次渲染用的 dpr。叠加层线宽要按它取整到**设备像素**（见 _pen_width）。
        self._dpr = 1.0

    @property
    def has_image(self) -> bool:
        """当前是否已装入图片。"""
        return self._pixmap is not None

    # ------------------------------------------------------------------ API
    def preview_edge(self) -> int:
        """当前控件需要多高的预览分辨率（**最长边**像素数）。

        按控件的**物理**像素算（逻辑尺寸 × dpr），取宽高较大者：图片按等比
        缩放适配控件，长边必定落在控件的长边上，所以按较大边给就够。

        交给 ``PreviewWorker(longest_edge=...)`` 用。⚠️ 早先四处调用点都写死
        1600：高分屏（150%~200%）或大窗口下屏幕需要的像素比 1600 还多，
        源图只能被放大 → 糊。实测（.workbuddy/perf/2026-09-24-preview-sharpness.md）
        把密度拉满后 RMSE 再降 30~50%、锐度再涨 1.4~1.7 倍，代价是每页多 25~160ms。
        """
        dpr = self.devicePixelRatioF() or 1.0
        longest = max(self.width(), self.height())
        return max(
            self.MIN_PREVIEW_EDGE,
            min(self.MAX_PREVIEW_EDGE, int(round(longest * dpr))),
        )

    def set_boxes_editable(self, editable: bool) -> None:
        """开关框编辑；开启时接受点击焦点以响应键盘删除。"""
        self._boxes_editable = editable
        self.setFocusPolicy(Qt.ClickFocus if editable else Qt.NoFocus)

    def set_reference_boxes(self, boxes: list) -> None:
        """设置参考框（橙色虚线，不参与编辑）并重绘。"""
        self._reference_boxes = [list(box) for box in (boxes or [])]
        self._rerender()

    def set_image(self, image, boxes=None, image_size: QSize | None = None) -> None:
        """
        装入图片并重置编辑状态。

        image 为 QImage；image_size 非空时作为框坐标的坐标系基准（大图可能被
        降采样显示，坐标必须按原始尺寸算）。
        """
        self._image_size = image_size or image.size()
        self._boxes = [list(box) for box in (boxes or [])]
        self._pixmap = QPixmap.fromImage(image)
        self._selected = None
        self._mode = None
        self._drag_index = None
        self._ghost_box = None
        self._rerender()

    def set_boxes(self, boxes: list, image_size: QSize) -> None:
        """仅更新切割框与图片原始尺寸并重绘（不换图）。

        boxes 为图片像素坐标；image_size 为坐标映射基准，与显示缩放无关。
        """
        self._boxes = [list(box) for box in boxes]
        self._image_size = image_size
        self._selected = None
        self._mode = None
        self._rerender()

    def clear_image(self, text: str = "无预览") -> None:
        """清空图片与全部框（含参考框），显示占位文案。"""
        self._pixmap = None
        self._boxes = []
        self._reference_boxes = []
        self._selected = None
        self._mode = None
        self._drag_index = None
        self.setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rerender()

    def event(self, event) -> bool:  # noqa: N802
        """跨显示器拖动（dpr 变化）时按新 dpr 重画。

        Qt 在窗口 dpr 变化时发 ``DevicePixelRatioChange``，**不保证**同时发
        ``resizeEvent``。不接这个事件的话，把窗口从 100% 屏拖到 200% 屏，
        图会一直停在按旧 dpr 出的那版（明显发糊），要等下次换页才恢复。
        """
        if event.type() == QEvent.Type.DevicePixelRatioChange and self._pixmap:
            self._rerender()
        return super().event(event)

    # ------------------------------------------------------------------ 坐标
    def _to_image_coords(self, pos: QPointF) -> tuple[float, float]:
        """控件坐标 → 图片原始像素坐标。"""
        return (
            (pos.x() - self._offset_x) / self._scale_x,
            (pos.y() - self._offset_y) / self._scale_y,
        )

    def _handle_rects(self, box) -> list[tuple[int, int, float, float]]:
        """选中框四角手柄的显示位图坐标区域 [(corner, cx, cy, r)]。

        与 _draw_boxes 的绘制坐标系一致（display 位图原点，不含居中偏移）；
        命中判断时由 _hit_handle 先减去偏移换算回该坐标系。
        """
        x1, y1, x2, y2 = box
        corners = [
            (x1 * self._scale_x, y1 * self._scale_y),
            (x2 * self._scale_x, y1 * self._scale_y),
            (x2 * self._scale_x, y2 * self._scale_y),
            (x1 * self._scale_x, y2 * self._scale_y),
        ]
        return [
            (i, cx, cy, HANDLE_RADIUS)
            for i, (cx, cy) in enumerate(corners)
        ]

    def _hit_handle(self, pos: QPointF) -> int | None:
        if self._selected is None or self._selected >= len(self._boxes):
            return None
        # 鼠标在控件坐标，display 位图以 (offset_x, offset_y) 为原点居中
        px = pos.x() - self._offset_x
        py = pos.y() - self._offset_y
        for corner, cx, cy, r in self._handle_rects(self._boxes[self._selected]):
            if abs(px - cx) <= r + 2 and abs(py - cy) <= r + 2:
                return corner
        return None

    def _hit_box(self, ix: float, iy: float) -> int | None:
        """命中检测：返回被点中的框下标（后画的优先），未命中返回 None。"""
        for index in range(len(self._boxes) - 1, -1, -1):
            x1, y1, x2, y2 = self._boxes[index]
            if x1 <= ix <= x2 and y1 <= iy <= y2:
                return index
        return None

    @staticmethod
    def _normalize(box) -> list[int]:
        x1, x2 = sorted((box[0], box[2]))
        y1, y2 = sorted((box[1], box[3]))
        return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]

    def _commit_edit(self) -> None:
        self.boxes_edited.emit([list(box) for box in self._boxes])

    # ------------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._boxes_editable and event.button() == Qt.LeftButton and self._pixmap is not None:
            ix, iy = self._to_image_coords(event.position())
            # 1) 选中框的缩放手柄
            corner = self._hit_handle(event.position())
            if corner is not None:
                self._mode = "resize"
                self._drag_index = self._selected
                self._resize_corner = corner
                self._dirty = False
                return
            # 2) 点中某个框 → 选中并进入拖动
            index = self._hit_box(ix, iy)
            if index is not None:
                self._selected = index
                self._drag_index = index
                self._mode = "move"
                self._dirty = False
                x1, y1, _, _ = self._boxes[index]
                self._grab_dx = ix - x1
                self._grab_dy = iy - y1
                self.setCursor(Qt.ClosedHandCursor)
                self._rerender()
                return
            # 3) 空白处 → 手绘新框
            self._selected = None
            self._mode = "new"
            self._new_start = (ix, iy)
            self._rerender()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        ix, iy = self._to_image_coords(event.position())
        if self._mode == "move" and self._drag_index is not None and self._image_size is not None:
            x1, y1, x2, y2 = self._boxes[self._drag_index]
            width, height = x2 - x1, y2 - y1
            nx1 = min(max(ix - self._grab_dx, 0), self._image_size.width() - width)
            ny1 = min(max(iy - self._grab_dy, 0), self._image_size.height() - height)
            self._boxes[self._drag_index] = [
                round(nx1), round(ny1), round(nx1 + width), round(ny1 + height)
            ]
            self._dirty = True
            self._rerender()
            return
        if self._mode == "resize" and self._drag_index is not None:
            box = list(self._boxes[self._drag_index])
            anchor_x, anchor_y = {
                0: (box[2], box[3]), 1: (box[0], box[3]),
                2: (box[0], box[1]), 3: (box[2], box[1]),
            }[self._resize_corner]
            self._boxes[self._drag_index] = self._normalize(
                [anchor_x, anchor_y, ix, iy]
            )
            self._dirty = True
            self._rerender()
            return
        if self._mode == "new" and self._new_start is not None:
            sx, sy = self._new_start
            self._ghost_box = self._normalize([sx, sy, ix, iy])
            self._rerender()
            return
        # 悬停光标
        if self._boxes_editable and self._pixmap is not None and self._boxes:
            corner = self._hit_handle(event.position())
            if corner is not None:
                self.setCursor(_HANDLE_CURSORS[corner])
                return
            if self._hit_box(ix, iy) is not None:
                self.setCursor(Qt.PointingHandCursor)
                return
            self.setCursor(Qt.ArrowCursor)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode == "move" and self._drag_index is not None:
            self._drag_index = None
            self._mode = None
            self.setCursor(Qt.PointingHandCursor)
            if self._dirty:
                self._commit_edit()
            self._dirty = False
            return
        if self._mode == "resize" and self._drag_index is not None:
            self._drag_index = None
            self._mode = None
            if self._dirty:
                self._commit_edit()
            self._dirty = False
            return
        if self._mode == "new" and self._new_start is not None:
            ix, iy = self._to_image_coords(event.position())
            box = self._normalize([self._new_start[0], self._new_start[1], ix, iy])
            self._new_start = None
            self._mode = None
            self._ghost_box = None
            # 过滤误触产生的极小框
            if box[2] - box[0] > 8 and box[3] - box[1] > 8 and self._image_size is not None:
                box = [
                    min(max(box[0], 0), self._image_size.width()),
                    min(max(box[1], 0), self._image_size.height()),
                    min(max(box[2], 0), self._image_size.width()),
                    min(max(box[3], 0), self._image_size.height()),
                ]
                self._boxes.append(box)
                self._selected = len(self._boxes) - 1
                self._commit_edit()
            self._rerender()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击 → ``double_clicked``（宿主打开图片预览弹窗）。

        ⚠️ 必须把本次按下可能已经开始的"手绘新框"清干净：双击的第一下会先落到
        ``mousePressEvent`` 的"空白处 → 手绘"分支，不清就会在图上留一个跟着
        鼠标跑的橡皮筋残影，而且第二下松开还会真的落一个框。
        """
        if event.button() == Qt.LeftButton and self._pixmap is not None:
            self._mode = None
            self._new_start = None
            self._drag_index = None
            self._ghost_box = None
            self._rerender()
            self.double_clicked.emit()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._boxes_editable and self._selected is not None and event.key() in (
            Qt.Key_Delete, Qt.Key_Backspace,
        ):
            del self._boxes[self._selected]
            self._selected = None
            self._commit_edit()
            self._rerender()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ 渲染
    def _update_mapping(self, scaled: QPixmap) -> None:
        """按当前显示尺寸刷新坐标映射（必须在绘制之前调用）。

        缩放比以 _image_size（图片原始尺寸）为基准：显示的 pixmap 可能是
        预览加载时降采样过的版本，框坐标始终是原始像素坐标。

        ⚠️ ``scaled`` 带 devicePixelRatio，其 ``width()`` 报的是**物理**像素，
        必须换算回逻辑尺寸再算映射与居中偏移——把物理尺寸当逻辑尺寸用，
        在高分屏下恰好差一个 dpr，框会整体放大并偏移。
        """
        ref_w = self._image_size.width() if self._image_size else self._pixmap.width()
        ref_h = self._image_size.height() if self._image_size else self._pixmap.height()
        dpr = scaled.devicePixelRatio() or 1.0
        disp_w = scaled.width() / dpr
        disp_h = scaled.height() / dpr
        self._scale_x = disp_w / ref_w if ref_w else 1.0
        self._scale_y = disp_h / ref_h if ref_h else 1.0
        # setPixmap 后 QLabel 按 AlignCenter 居中显示
        self._offset_x = max(0.0, (self.width() - disp_w) / 2)
        self._offset_y = max(0.0, (self.height() - disp_h) / 2)

    def _rerender(self) -> None:
        """按当前控件尺寸缩放显示（窗口缩放/布局变化后保持完整可见）。

        ⚠️ 必须按**物理**像素出图并把 dpr 写回 pixmap：早先按逻辑像素出图，
        高分屏下 Qt 再按 dpr 放大一次，等于把图「先降后升」重采样两轮。
        实测 150% 缩放下锐度 494 → 3755（**7.6 倍**）、200% 下 171 → 2831
        （**16 倍**），而 100% 缩放下几乎无差别——所以只在普通屏上是看不出
        这个问题的（数据见 .workbuddy/perf/2026-09-24-preview-sharpness.md）。

        叠加层（框/手柄/文字）用**逻辑**坐标绘制。

        ⚠️ **不要再手动 `painter.scale(dpr, dpr)`**：Qt 在带 devicePixelRatio 的
        pixmap 上作画时，painter 的坐标**已经是逻辑坐标**（实测 dpr=1.5 时
        `drawRect(0,0,10,10)` 覆盖物理 0~15px，而 `transform().m11()` 仍报 1.0
        ——dpr 是在设备层生效的，不体现在 painter 的变换里）。再乘一次 dpr
        等于放大两次：框会整体放大并偏移，而底图是对的，看上去就是"框和图片
        对不上/比例不对"。离屏自测（dpr 恒为 1）测不出这个，必须在 dpr≠1 下
        用像素级断言验（见 tests/selftests/preview_dpr.py）。
        """
        if self._pixmap is None:
            return
        dpr = self.devicePixelRatioF() or 1.0
        self._dpr = dpr
        if self.width() <= 0 or self.height() <= 0:
            # 还没布局（尺寸 0）：照 0 尺寸缩放只会得到一张 1x1，别覆盖上一张图
            return
        target = QSize(
            max(1, round(self.width() * 0.96 * dpr)),
            max(1, round(self.height() * 0.96 * dpr)),
        )
        scaled = self._pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        scaled.setDevicePixelRatio(dpr)
        # 先刷新映射，再绘制：框/参考框/橡皮筋都使用本次渲染的缩放比
        self._update_mapping(scaled)
        painter = QPainter(scaled)
        if self._reference_boxes:
            self._draw_reference_boxes(painter)
        if self._boxes and self._image_size:
            self._draw_boxes(painter)
        ghost = getattr(self, "_ghost_box", None)
        if ghost:
            painter.setPen(QPen(QColor("#8b949e"), 1, Qt.DashLine))
            painter.drawRect(
                round(ghost[0] * self._scale_x), round(ghost[1] * self._scale_y),
                round((ghost[2] - ghost[0]) * self._scale_x),
                round((ghost[3] - ghost[1]) * self._scale_y),
            )
        painter.end()
        self.setPixmap(scaled)

    def _pen_width(self, logical: int | float) -> float:
        """叠加层线宽：取整到**设备像素**后再换算回逻辑宽度。

        ⚠️ Qt 用**逻辑**线宽 × dpr 得到设备线宽。不是整数设备像素时（125% 缩放
        下 2×1.25 = 2.5；150% 下选中态 3×1.5 = 4.5），光栅化对四条边的取整不一致
        ——实测同一个框会出现「上3 下3 左3 右2」这种**粗细不匀**。取整到设备像素
        后四条边一致（实测 dpr=1.0/1.25/1.5/2.0 全部均匀）。
        """
        dpr = self._dpr or 1.0
        return max(1.0 / dpr, round(float(logical) * dpr) / dpr)

    def _draw_reference_boxes(self, painter: QPainter) -> None:
        """参考框：按 area/border 规则推导的最终裁剪大框，橙色虚线。"""
        pen = QPen(REFERENCE_COLOR, self._pen_width(2), Qt.DashLine)
        painter.setPen(pen)
        for box in self._reference_boxes:
            x1, y1, x2, y2 = box
            painter.drawRect(
                round(x1 * self._scale_x), round(y1 * self._scale_y),
                round((x2 - x1) * self._scale_x), round((y2 - y1) * self._scale_y),
            )
        if self._reference_boxes:
            painter.setPen(QPen(REFERENCE_COLOR))
            painter.drawText(
                round(self._reference_boxes[0][0] * self._scale_x) + 4,
                max(14, round(self._reference_boxes[0][3] * self._scale_y) - 4),
                "最终裁剪框",
            )

    def _draw_boxes(self, painter: QPainter) -> None:
        font = painter.font()
        font.setPixelSize(13)
        painter.setFont(font)
        for index, box in enumerate(self._boxes):
            x1, y1, x2, y2 = box
            color = BOX_COLORS[index % len(BOX_COLORS)]
            selected = index == self._selected
            # 选中的框加粗（3 逻辑像素），未选中 2；两者都取整到设备像素，
            # 否则高分屏下四边会粗细不匀（见 _pen_width）
            pen = QPen(color, self._pen_width(3 if selected else 2))

            painter.setPen(pen)
            painter.drawRect(
                round(x1 * self._scale_x), round(y1 * self._scale_y),
                round((x2 - x1) * self._scale_x), round((y2 - y1) * self._scale_y),
            )
            name = BOX_NAMES[index % len(BOX_NAMES)]
            painter.drawText(
                round(x1 * self._scale_x) + 4,
                max(14, round(y1 * self._scale_y) - 4),
                f"{name} ({x1},{y1},{x2},{y2})" + (" ｜ 已选中，Delete 删除" if selected else ""),
            )
        # 选中框的四角缩放手柄
        if self._selected is not None and self._selected < len(self._boxes):
            painter.setPen(QPen(QColor("#ffffff")))
            painter.setBrush(QColor(0, 0, 0, 160))
            for _corner, cx, cy, r in self._handle_rects(self._boxes[self._selected]):
                painter.drawRect(round(cx - r), round(cy - r), 2 * r, 2 * r)
            painter.setBrush(Qt.NoBrush)
