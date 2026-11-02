# -*- coding: utf-8 -*-
"""第四步「版面编辑器」交互画布：在 A4 纸上拖拽 / 缩放 / 旋转图片。

坐标体系与 ``utils.page_layout.plan_print_page`` 算出的 ``plan.image`` 完全一致
——**页面毫米，左上原点，x 向右、y 向下**。控件把页面等比缩放到可视区，
用 ``px_per_mm`` 在「页面 mm」与「控件像素」之间换算；用户拖拽/缩放得到的
``[x_mm, y_mm, w_mm, h_mm]`` 直接写回 ``print.json`` 的 ``pages[].rect``，
出 PDF 时由 ``plan_print_page(image_rect=...)`` 原样采用——所见即所得。

交互（与 detect/rembg 的裁剪框编辑同款手感）：
- 框内拖动 → 整体移动；**四角**手柄拖动 → 缩放（勾「原比例缩放」时等比）；
  **四条边整条都是命中带**（不限边中点的小圆点）→ 拖上/下边只改高度、
  拖左/右边只改宽度（自由拉伸改变比例）；松手 emit ``rect_changed``；
- **框外上方的旋转钮**（用户 2026-11-02：与「图片拼版」同款组件）→ 左键
  拖动绕框心旋转任意角度（按住 Shift 吸附 15°）；旋转后框按外接框重算，
  角度与框一起落盘 ``pages[].rotate``；
- 框始终被夹在页面内（夹到纸边即停），不会拖出页面；
- 悬停手柄/边/旋转钮/框时显示对应光标。

**标题与页码照画**：它们是「版面」的一部分，去掉就无从判断图片挪动后会不会
压到字（曾误判为「标题页码被去除」）。绘制复用 ``preview_worker`` 的
``_draw_print_text``——与成品 PDF 同源，只是多了画布自身的居中偏移。
标题/页码的落点只取决于 ``page_margins``，**不随图片框移动**，与 PDF 一致。

图片按目标矩形绘制（未旋转时**拉伸**，与成品 ``pdf.image(img, x, y, w, h)``
的拉伸规则一致）；旋转时先绕框心转、再按旋转后的外接框等比放进同一个框，
与 PDF / 效果预览共用 ``utils.page_layout.fit_rotated_rect``。
"""

from __future__ import annotations

import math
from typing import Sequence

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from desktop.ui import theme as T
from desktop.utils.image_scaling import smooth_downscale
from utils.page_layout import (
    fit_rotated_rect, normalize_page_rotation, rotated_bbox_size,
)
# 标题/页码的绘制必须与成品 PDF 同源：直接复用效果预览那套（mm → px 换算
# 与竖排分段完全一致），避免编辑器和 PDF 各画各的、看起来对不上。
from desktop.workers.preview_worker import (
    _draw_print_text, _pick_preview_font,
)

# 纸张恒为白底（PDF 纸张即白）；边框/控件用中性色，深浅主题下都清楚
PAGE_COLOR = QColor("#ffffff")
PAGE_BORDER = QColor("#cbd2dc")
# 命中 skip_pages 的页：成品里没有它，编辑时给灰底明确提示（与效果预览同色）
SKIP_COLOR = QColor("#eceff3")
SKIP_INK = QColor("#98a2b3")
IMAGE_STROKE = QColor("#2563eb")
HANDLE_STROKE = QColor("#2563eb")
HANDLE_FILL = QColor("#ffffff")
HANDLE_RADIUS = 6  # 手柄半径（控件像素）

# 手柄光标：0~3 = 四角（左上/右上/右下/左下），4~7 = 四边（上/右/下/左）。
# ⚠️ 四边手柄**只在取消「原比例缩放」时出现**（那时才允许单方向拉伸）。
_CORNER_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]
_EDGE_CURSORS = [
    Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
    Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
]
_HANDLE_CURSORS = _CORNER_CURSORS + _EDGE_CURSORS

#: 边手柄索引 → 受影响的边
_EDGE_BY_HANDLE = {4: "top", 5: "right", 6: "bottom", 7: "left"}

#: 框的最小边长（mm）：拖到两边重合会让命中判定与后续缩放都失效
MIN_RECT_MM = 2.0

#: 画布贴图底图的降采样上限（最长边）。
#:
#: 源图常见 3000~6000px，而画布把整页塞进可视区后每毫米只剩 ~2px：直接
#: `drawImage` 是一次 8~10 倍缩小的**最近邻**采样，古籍的细笔画/淡墨会被
#: 跳采样（用户报「rembg 图放大看还行，PDF 排版页却发虚」）。先把源图平滑
#: 缩到这个上限（一次性、换图才重算），贴图时再平滑缩一档——两档温和缩放
#: 质量接近理论最优；而且每帧只对 ≤2000px 的小图采样，拖框不会掉帧。
DISPLAY_IMAGE_EDGE = 2000

#: 边命中带（控件像素）：距边线这么近就算"拖这条边"，**不限边中点**。
#: 角仍是小圆点邻域（角落优先按对角缩放处理）。
EDGE_HIT_PX = 6

#: 框外上方的旋转钮（与「图片拼版」同款，用户 2026-11-02）：
#: 距框上边的距离 / 圆钮半径 / 命中半宽（比画出来的圆大一圈，点太小不好抓）。
ROTATE_KNOB_GAP = 26
ROTATE_KNOB_RADIUS = 6
ROTATE_KNOB_HIT = ROTATE_KNOB_RADIUS + 8
#: 弧形箭头画在圆钮**外侧**（用户 2026-11-02：圆里那圈小弧看不清）：
#: 距圆边的半径增量 / 起点角 / 跨度 / 箭头臂长。
#: Qt 角度 0° = 3 点方向；跨度取**负值 = 顺时针**（用户要的旋转方向）；
#: 缺口留在下方，避开引线。
ROTATE_ARC_GAP = 5.0
ROTATE_ARC_START = 210
ROTATE_ARC_SPAN = -240
ROTATE_ARC_BARB = 4.0
#: 旋转吸附步长（按住 Shift）
SNAP_DEGREES = 15.0


class PrintLayoutCanvas(QWidget):
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

    # ---------------------------------------------------------------- 旋转几何
    def _content_size_mm(self, rect, angle) -> tuple[float, float]:
        """由「旋转后的外接框 + 朝向」反推**未旋转内容**的宽高（mm）。

        用源图宽高比约束（框通常就是按它摆的）：内容等比落在框内，
        旋转到任何角度都不会把图片拉伸变形。框被自由拉成别的比例时按
        "完整放进框"取较小的一档，预览与 PDF 同样少一点而不裁掉内容。
        """
        box_w, box_h = float(rect[2]), float(rect[3])
        image = self._image
        if image is None or image.isNull() or image.height() <= 0:
            return box_w, box_h
        aspect = image.width() / image.height()
        rad = math.radians(normalize_page_rotation(angle))
        cos_v, sin_v = abs(math.cos(rad)), abs(math.sin(rad))
        content_w = min(
            aspect * box_w / (aspect * cos_v + sin_v),
            aspect * box_h / (aspect * sin_v + cos_v),
        )
        return content_w, content_w / aspect

    def _bbox_for_content(self, content, angle) -> list[float]:
        """内容尺寸 + 朝向 → 居中的外接框（超出纸张时等比缩回页内）。"""
        content_w, content_h = content
        bbox_w, bbox_h = rotated_bbox_size(content_w, content_h, angle)
        scale = min(
            1.0,
            self._page_w_mm / bbox_w if bbox_w > 0 else 1.0,
            self._page_h_mm / bbox_h if bbox_h > 0 else 1.0,
        )
        bbox_w, bbox_h = bbox_w * scale, bbox_h * scale
        center = self._rect_center_mm()
        nx = min(max(center[0] - bbox_w / 2.0, 0.0),
                 max(0.0, self._page_w_mm - bbox_w))
        ny = min(max(center[1] - bbox_h / 2.0, 0.0),
                 max(0.0, self._page_h_mm - bbox_h))
        return [nx, ny, bbox_w, bbox_h]

    def _rect_center_mm(self) -> tuple[float, float]:
        x, y, w, h = self._rect_mm
        return x + w / 2.0, y + h / 2.0

    def _display_image_for(self) -> QImage | None:
        """贴图用的底图：源图平滑缩到 ``DISPLAY_IMAGE_EDGE`` 以内（换图才重算）。

        拖拽/缩放/旋转期间 ``_rect_mm`` 每帧在变，但**不参与**缓存键——底图按
        整页可能的最大显示尺寸准备（图片框被夹在页面内，不会比整页更大），
        所以拖框时零重采样；旋转是 QPainter 变换，同样不重采样位图。
        """
        source = self._image
        if source is None or source.isNull():
            return None
        if source is self._display_source:
            return self._display_image
        self._display_source = source
        self._display_image = smooth_downscale(source, DISPLAY_IMAGE_EDGE)
        return self._display_image

    # ------------------------------------------------------------------ 坐标
    def _recompute(self) -> None:
        avail_w = self.width() - 2 * self._pad
        avail_h = self.height() - 2 * self._pad
        if (avail_w <= 0 or avail_h <= 0
                or self._page_w_mm <= 0 or self._page_h_mm <= 0):
            self._px_per_mm = 1.0
            self._off_x = float(self._pad)
            self._off_y = float(self._pad)
            return
        # 等比缩放：整页（含留白）刚好放进可视区
        self._px_per_mm = min(
            avail_w / self._page_w_mm, avail_h / self._page_h_mm
        )
        page_px_w = self._page_w_mm * self._px_per_mm
        page_px_h = self._page_h_mm * self._px_per_mm
        self._off_x = (self.width() - page_px_w) / 2
        self._off_y = (self.height() - page_px_h) / 2

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

    def _to_mm(self, pos: QPointF) -> tuple[float, float]:
        """控件坐标 → 页面 mm 坐标。"""
        return (
            (pos.x() - self._off_x) / self._px_per_mm,
            (pos.y() - self._off_y) / self._px_per_mm,
        )

    def _rect_px(self) -> QRectF:
        x, y, w, h = self._rect_mm
        return QRectF(
            self._off_x + x * self._px_per_mm,
            self._off_y + y * self._px_per_mm,
            w * self._px_per_mm,
            h * self._px_per_mm,
        )

    def _handle_positions(self) -> list[tuple[float, float]]:
        """手柄位置：四角 + 四边，**恒 8 个**。

        四边手柄始终可用——用户明确去拖某条边，就是要单方向拉伸那条边
        （拖上/下边改高度、左/右边改宽度），与「原比例缩放」无关；
        该勾选只约束**四角**拖拽是否等比（True=等比，False=自由）。
        """
        r = self._rect_px()
        cx = r.x() + r.width() / 2
        cy = r.y() + r.height() / 2
        return [
            (r.x(), r.y()),                     # 0 左上
            (r.x() + r.width(), r.y()),         # 1 右上
            (r.x() + r.width(), r.y() + r.height()),  # 2 右下
            (r.x(), r.y() + r.height()),        # 3 左下
            (cx, r.y()),                        # 4 上
            (r.x() + r.width(), cy),            # 5 右
            (cx, r.y() + r.height()),           # 6 下
            (r.x(), cy),                        # 7 左
        ]

    def _rotate_knob_pos(self) -> QPointF:
        """旋转钮位置（控件坐标）：框上边中点再向上 ``ROTATE_KNOB_GAP``。"""
        r = self._rect_px()
        return QPointF(r.center().x(), r.y() - ROTATE_KNOB_GAP)

    def _hit_handle(self, pos: QPointF) -> int | None:
        """命中手柄：**旋转钮** → 四角（圆点邻域）→ 四边（**整条边的命中带**）。

        ⚠️ 旋转钮在图片**外面**（框上方），命中区比画出来的圆大一圈：它是
        唯一的旋转抓手，点太小抓不住（与「图片拼版」同一套手感，用户 2026-11-02）。
        ⚠️ 边命中**不限于边中点的小圆点**——整条边两侧 `EDGE_HIT_PX` 控件
        像素内都算拖那条边（窗口边缘的惯例：靠边即改宽/高，靠角即缩放）。
        角优先于边：角落同时邻近两条边，按角处理才符合直觉（圆点邻域
        判定在前，走到边判定时说明离角已经够远）。
        """
        if self._image is not None:
            knob = self._rotate_knob_pos()
            if abs(pos.x() - knob.x()) <= ROTATE_KNOB_HIT and \
                    abs(pos.y() - knob.y()) <= ROTATE_KNOB_HIT:
                return 8  # 旋转
        positions = self._handle_positions()
        for i in range(4):  # 四角：圆点邻域
            cx, cy = positions[i]
            if abs(pos.x() - cx) <= HANDLE_RADIUS + 2 and \
                    abs(pos.y() - cy) <= HANDLE_RADIUS + 2:
                return i
        r = self._rect_px()
        hit = EDGE_HIT_PX
        near_top = abs(pos.y() - r.y()) <= hit
        near_bottom = abs(pos.y() - (r.y() + r.height())) <= hit
        near_left = abs(pos.x() - r.x()) <= hit
        near_right = abs(pos.x() - (r.x() + r.width())) <= hit
        x_in = r.x() - hit <= pos.x() <= r.x() + r.width() + hit
        y_in = r.y() - hit <= pos.y() <= r.y() + r.height() + hit
        if near_top and x_in:
            return 4
        if near_right and y_in:
            return 5
        if near_bottom and x_in:
            return 6
        if near_left and y_in:
            return 7
        return None

    def _hit_rect(self, pos: QPointF) -> bool:
        return self._rect_px().contains(pos)

    # ------------------------------------------------------------------ 鼠标
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._image is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        corner = self._hit_handle(event.position())
        if corner == 8:
            # 旋转钮：记下起点角度与起点内容尺寸，拖动时按增量算朝向
            self._mode = "rotate"
            center = self._rect_px().center()
            mx, my = event.position().x(), event.position().y()
            self._grab_angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
            self._grab_rotation = self._rotation
            self._grab_content = self._content_size_mm(
                self._rect_mm, self._rotation
            )
            self._dirty = False
            self.update()
            return
        if corner is not None:
            self._mode = "resize"
            self._corner = corner
            # 保比例的角拖拽以**起点框**为基准（比例与对角锚点都取自它）；
            # 读拖动中的 _rect_mm 会逐帧累积偏差。
            self._grab_rect = list(self._rect_mm)
            self._dirty = False
            self.update()
            return
        if self._hit_rect(event.position()):
            self._mode = "move"
            self._dirty = False
            mx, my = self._to_mm(event.position())
            self._grab_x = mx - self._rect_mm[0]
            self._grab_y = my - self._rect_mm[1]
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            return
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "rotate":
            center = self._rect_px().center()
            mx, my = event.position().x(), event.position().y()
            angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
            value = self._grab_rotation + angle - self._grab_angle
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                value = round(value / SNAP_DEGREES) * SNAP_DEGREES
            self._rotation = normalize_page_rotation(value)
            self._rect_mm = self._bbox_for_content(
                self._grab_content, self._rotation
            )
            self._dirty = True
            self.update()
            return
        if self._mode == "move":
            mx, my = self._to_mm(event.position())
            nx = min(max(mx - self._grab_x, 0.0),
                      self._page_w_mm - self._rect_mm[2])
            ny = min(max(my - self._grab_y, 0.0),
                      self._page_h_mm - self._rect_mm[3])
            self._rect_mm[0] = nx
            self._rect_mm[1] = ny
            self._dirty = True
            self.update()
            return
        if self._mode == "resize":
            mx, my = self._to_mm(event.position())
            self._rect_mm = self._resize_from_handle(mx, my)
            self._dirty = True
            self.update()
            return
        # 悬停光标提示
        if self._image is not None:
            corner = self._hit_handle(event.position())
            if corner == 8:
                self.setCursor(Qt.CursorShape.CrossCursor)
                return
            if corner is not None:
                self.setCursor(_HANDLE_CURSORS[corner])
                return
            if self._hit_rect(event.position()):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        return super().mouseMoveEvent(event)

    def _resize_from_handle(self, mx: float, my: float) -> list[float]:
        """按当前手柄算出新框（页面 mm，始终夹在页面内）。

        - 四边手柄：只改受影响的那个维度，**自由拉伸**（这是「取消原比例」
          的核心手感：上下/左右单独拉，比例随之改变）；
        - 四角手柄：`keep_ratio=False` 时自由拉伸；`True` 时以**对角为锚点**
          等比缩放——比例取自拖拽起点框 `_grab_rect`，鼠标决定的宽高里取
          **更受限**的那个维度配对，这样往任何方向拖都不会跑形。
        """
        gx, gy, gw, gh = self._grab_rect
        pw, ph = self._page_w_mm, self._page_h_mm
        edge = _EDGE_BY_HANDLE.get(self._corner)
        if edge is not None:
            x, y, w, h = self._rect_mm
            if edge == "top":
                top = min(max(my, 0.0), y + h - MIN_RECT_MM)
                return [x, top, w, y + h - top]
            if edge == "bottom":
                bottom = min(max(my, y + MIN_RECT_MM), ph)
                return [x, y, w, bottom - y]
            if edge == "left":
                left = min(max(mx, 0.0), x + w - MIN_RECT_MM)
                return [left, y, x + w - left, h]
            right = min(max(mx, x + MIN_RECT_MM), pw)
            return [x, y, right - x, h]
        # ---- 四角 ----
        ax, ay = {
            0: (gx + gw, gy + gh), 1: (gx, gy + gh),
            2: (gx, gy), 3: (gx + gw, gy),
        }[self._corner]
        if not self._keep_ratio or gw <= 0 or gh <= 0:
            nx1, ny1 = min(ax, mx), min(ay, my)
            nx2, ny2 = max(ax, mx), max(ay, my)
            nx1 = min(max(nx1, 0.0), pw)
            ny1 = min(max(ny1, 0.0), ph)
            nx2 = min(max(nx2, 0.0), pw)
            ny2 = min(max(ny2, 0.0), ph)
            return [nx1, ny1, nx2 - nx1, ny2 - ny1]
        ratio = gh / gw
        scale = min(
            abs(mx - ax) / gw if gw else 0.0,
            abs(my - ay) / gh if gh else 0.0,
        )
        new_w = max(MIN_RECT_MM, gw * scale)
        new_h = max(MIN_RECT_MM, new_w * ratio)
        # 超出页面就等比缩回来（不破比例，也不做单维度夹取）
        if new_w > pw:
            new_w, new_h = pw, pw * ratio
        if new_h > ph:
            new_h, new_w = ph, ph / ratio if ratio else new_w
        nx = ax - new_w if self._corner in (0, 3) else ax
        ny = ay - new_h if self._corner in (0, 1) else ay
        nx = min(max(nx, 0.0), pw - new_w)
        ny = min(max(ny, 0.0), ph - new_h)
        return [nx, ny, new_w, new_h]

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击 → ``double_clicked``（宿主打开预览弹窗）。"""
        if event.button() == Qt.MouseButton.LeftButton and self._image is not None:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键 → ``context_menu_requested``（宿主弹「预览图片 / 编辑图片」菜单）。

        左键的拖拽/缩放不受影响（右键不参与编辑手势）；空页不弹菜单。
        """
        if self._image is not None:
            self.context_menu_requested.emit()
            event.accept()
            return
        super().contextMenuEvent(event)

    def flush_pending(self) -> bool:
        """把"还没松手"的拖动结果补发出去（关窗口/切步骤/切页时调）。

        ⚠️ 为什么需要（2026-09-26 审计）：`rect_changed` 只在 `mouseReleaseEvent`
        里发（拖动过程中只 `update()` 重绘、不落盘）。于是「拖住图片框不放、
        直接关窗口 / 返回列表」这一下改动就**永久丢失**，而且用户以为已经生效了
        （画布上就是拖动后的样子）。这里主动补发一次，语义与正常松手完全一致。

        返回 True 表示确实补发了一次（即存在未提交的改动）。
        """
        if not self._dirty:
            return False
        self.rect_changed.emit([round(v, 2) for v in self._rect_mm])
        self._dirty = False
        return True

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode in ("move", "resize", "rotate"):
            self._mode = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._dirty:
                self.rect_changed.emit([round(v, 2) for v in self._rect_mm])
            self._dirty = False
            self.update()
            return
        return super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ 渲染
    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        # 纸张
        page_rect = QRectF(
            self._off_x, self._off_y,
            self._page_w_mm * self._px_per_mm,
            self._page_h_mm * self._px_per_mm,
        )
        if self._plan is not None and self._plan.skipped:
            # 命中 skip_pages：成品不含此页，编辑时明确提示（与效果预览同款）
            painter.fillRect(page_rect, SKIP_COLOR)
            painter.setPen(SKIP_INK)
            painter.setFont(_pick_preview_font(14))
            painter.drawText(page_rect, Qt.AlignmentFlag.AlignCenter, "该页已跳过，不会输出到 PDF")
            painter.end()
            return
        painter.fillRect(page_rect, PAGE_COLOR)
        painter.setPen(QPen(PAGE_BORDER, 1))
        painter.drawRect(page_rect)
        # 图片（未旋转时按目标矩形拉伸，与成品 pdf.image 一致；旋转时绕框心
        # 转、按旋转后的外接框等比放进框里，与预览/PDF 同一份几何）
        image = self._display_image_for()
        if image is not None and not image.isNull():
            r = self._rect_px()
            if r.width() > 0 and r.height() > 0:
                # ⚠️ 必须开平滑：Qt 默认关闭 SmoothPixmapTransform 时走最近邻，
                # 一次大比例缩小会把细笔画/淡墨直接跳采样（版面页看着发虚的
                # 原因）。底图已先降到 ≤2000px（见 DISPLAY_IMAGE_EDGE），这里
                # 再平滑缩一档，代价只有毫秒级，拖框不掉帧。
                painter.setRenderHint(
                    QPainter.RenderHint.SmoothPixmapTransform, True
                )
                self._draw_image(painter, image, r)
            painter.setPen(QPen(IMAGE_STROKE, 2))
            painter.drawRect(r)
        # 标题 / 页码：与成品 PDF 同一份 PrintTextSpec 与同一套绘制函数，
        # 只多一层画布居中偏移。落点只由 page_margins 决定，不随图片框移动。
        if self._plan is not None:
            painter.save()
            painter.translate(self._off_x, self._off_y)
            for spec in (self._plan.title, self._plan.page_number):
                if spec is not None:
                    _draw_print_text(painter, spec, self._px_per_mm)
            painter.restore()
        # 四角缩放手柄 + 框外上方的旋转钮
        if self._image is not None:
            painter.setPen(QPen(HANDLE_STROKE, 1.5))
            painter.setBrush(HANDLE_FILL)
            for cx, cy in self._handle_positions():
                painter.drawRect(
                    QRectF(cx - HANDLE_RADIUS, cy - HANDLE_RADIUS,
                           2 * HANDLE_RADIUS, 2 * HANDLE_RADIUS)
                )
            self._draw_rotate_knob(painter)
        painter.end()

    def _draw_image(self, painter: QPainter, image: QImage,
                    rect_px: QRectF) -> None:
        """把图片画进当前框：未旋转直接拉伸；旋转时绕框心变换。

        旋转后的内容尺寸由 :meth:`_content_size_mm` 反推（按源图宽高比），
        因此画出来正好落在旋转后的**外接框**里——与 PDF / 效果预览用
        ``fit_rotated_rect`` 算出的落点同一份几何，不会出现"预览转过去、
        成品转回来"。
        """
        if not self._rotation:
            painter.drawImage(rect_px, image)
            return
        content_w, content_h = self._content_size_mm(
            self._rect_mm, self._rotation
        )
        cw = content_w * self._px_per_mm
        ch = content_h * self._px_per_mm
        painter.save()
        painter.translate(rect_px.center())
        painter.rotate(self._rotation)
        painter.drawImage(QRectF(-cw / 2, -ch / 2, cw, ch), image)
        painter.restore()

    def _draw_rotate_knob(self, painter: QPainter) -> None:
        """画框外上方的旋转钮（**常显**，与「图片拼版」同款）。

        一条引线 + 一个白底圆钮，**圆外**环绕一段顺时针弧形箭头——一眼看出
        这是"旋转"抓手而不是缩放手柄（用户 2026-11-02：画在圆里太小、看不清）。
        左键拖它即可绕框心旋转当前页图片。
        """
        knob = self._rotate_knob_pos()
        anchor = QPointF(knob.x(), knob.y() + ROTATE_KNOB_GAP)
        painter.setPen(QPen(HANDLE_STROKE, 1.5))
        painter.drawLine(anchor, knob)
        painter.setBrush(HANDLE_FILL)
        painter.drawEllipse(knob, ROTATE_KNOB_RADIUS, ROTATE_KNOB_RADIUS)
        # 弧形箭头在圆钮外侧（顺时针；缺口在下方，不压住引线）
        arc_r = ROTATE_KNOB_RADIUS + ROTATE_ARC_GAP
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(
            QRectF(knob.x() - arc_r, knob.y() - arc_r, arc_r * 2, arc_r * 2),
            ROTATE_ARC_START * 16, ROTATE_ARC_SPAN * 16,
        )
        # 箭头：弧末端沿**顺时针**切线方向收两道短线
        end = math.radians(ROTATE_ARC_START + ROTATE_ARC_SPAN)
        tip = QPointF(
            knob.x() + arc_r * math.cos(end),
            knob.y() - arc_r * math.sin(end),
        )
        dx, dy = math.sin(end), math.cos(end)
        for turn in (-0.8, 0.8):
            barb_x = dx * math.cos(turn) - dy * math.sin(turn)
            barb_y = dx * math.sin(turn) + dy * math.cos(turn)
            painter.drawLine(
                tip, QPointF(tip.x() - ROTATE_ARC_BARB * barb_x,
                             tip.y() - ROTATE_ARC_BARB * barb_y)
            )
