# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""画布基座：边框 / 场景矩形同步。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView,
)

from ...consts import (
    CANVAS_OUTSIDE, CLIPPING_DEFAULT,
    DIRECTION_DEFAULT, DISTORT_HARDNESS, DISTORT_SIZE, DISTORT_SPACING,
    DISTORT_STRENGTH, EDIT_FIT_RATIO, ERASER_DEFAULT, GUIDE_DEFAULT,
    INTERPOLATION_DEFAULT, MAX_ZOOM, MIN_RECT_EDGE, MIN_ZOOM,
    PREVIEW_OPACITY_DEFAULT, SEL_FIT_RATIO,
)
from ...geometry import _transparent_content_bounds
from ...text_item import TextBlockItem
from ..distortion import DistortionMixin
from ..interaction import InteractionMixin
from ..overlay import OverlayMixin
from ..text import TextMixin
from ..transform import TransformMixin

if TYPE_CHECKING:
    from .._host import CanvasHost
else:
    CanvasHost = object



class BorderMixin(CanvasHost):
    """画布基座：边框 / 场景矩形同步。"""


    def _border_pen(self) -> QPen:
        """图片边框画笔：**虚线**（cosmetic ⇒ 任何倍率下都是 1px 虚线）。

        ⚠️ 2026-10-13 用户口径：边框改**虚线**，且"并不是固定不变的，应该
        根据图片四至边界扩大和缩小"——矩形由 :meth:`_sync_border` 维护：
        活动图跟随当前显示范围（含挂起变换的外扩），非活动图跟随自己的
        显示外框。
        """
        pen = QPen(QColor("#5b6472") if self._tool == "transform"
                   else QColor("#8a93a3"))
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def _apply_border_pen(self) -> None:
        """按当前工具刷新纸边框的画笔（换工具/装图时调）。"""
        if self._border is not None:
            self._border.setPen(self._border_pen())

    def _display_bounds(self) -> QRectF:
        """活动图**当前内容**的紧凑外框（图片坐标）——虚线边框的依据。

        用户 2026-10-13 口径：框要**包裹单张图片本身**——单图旋转 45°，
        框就是旋转后内容的外接框（√2 比例），**位置跟着内容移动**，不是
        钉死在原矩形上。所以：有挂起变换预览时＝变换后内容的紧凑外框
        （整幅内容选区时底图是一片空白，**不算**进外框；局部选区时选区外的
        原图残余还在画面上，要并进来）；没有预览时＝非透明内容的实际外框，
        不把裁剪位移产生的透明留白算进图片边界。
        """
        float_item = getattr(self, "_float_item", None)
        if float_item is None or float_item.pixmap().isNull():
            image_rect = self.image_rect()
            bounds = self._content_rect()
            if bounds is not None:
                return bounds.translated(image_rect.topLeft())
            return QRectF(image_rect)
        if self._xf_preview_keyframe is not None:
            float_xf = self._float_placement()
        else:
            float_xf = self._float_fast_xf()
        pixmap = float_item.pixmap()
        bounds = float_xf.mapRect(
            QRectF(0, 0, pixmap.width(), pixmap.height()))
        if not self._backdrop_is_whole() and self._paint_image is not None:
            bounds = bounds.united(self._base_current_rect())
        return bounds

    def _sync_border(self) -> None:
        """边框矩形跟随活动图当前显示范围（见 :meth:`_display_bounds`）。"""
        if self._border is None or self._image is None:
            return
        if self._tool == "crop" and self._item is not None:
            # 裁剪移动/变换扩画布可能在像素图周围留下透明边距；虚线框仍应
            # 包住可见图片，而不是整个透明画布。边框与图元共享本地坐标变换。
            bounds = self._content_rect()
            if bounds is None:
                bounds = self._item.boundingRect()
            self._border.setRect(bounds)
            self._border.setPos(self._item.pos())
            self._border.setTransform(self._item.transform())
            return
        self._border.setRect(self._display_bounds())
        # _display_bounds() 已是场景坐标；清除裁剪模式跟随图片图元的本地
        # 坐标变换，避免工具切换时把旧偏移再次叠加到边框上。
        self._border.setPos(0.0, 0.0)
        self._border.setTransform(QTransform())

    def _sync_scene_rect(self, keep_view: bool = False) -> None:
        """场景矩形＝两图**当前显示范围**的并集（滚动条够得到全部内容）。

        2026-10-13 用户报障「右侧图向右移一段后切到左侧，右侧显示不全」：
        矩形只圈基准矩形时，被变换搬出去的 content 落在矩形外 ⇒ 滚动条
        够不着，永远看不全。现在并集里放的是**显示范围**：

        - 活动图：:meth:`_display_bounds`（无预览＝图片矩形；有挂起预览＝
          变换后内容的紧凑外框）；
        - 非活动图：:attr:`_context_display_rect`（图元的实际场景外接矩形，
          含版面旋转）。

        ⚠️ 两侧口径一致 ⇒ 换层前后并集是**同一块版面**，画面不跳（2026-10-13
        的切换跳动修复保持不变）。
        ⚠️ **拖动中冻结**（2026-10-09 的旧病：矩形一帧帧跟着浮层长大，画面
        跟着漂）：松手后 ``finish_transform_drag`` 会再刷一次，那时才扩。
        ⚠️ 换矩形时用 :meth:`_set_scene_rect_keeping_view` **保持画面不动**。

        参数 ``keep_view``：**换层等"必须同步滚动范围"的场景**传 True
        （走原来的保画面路径，2026-10-13 的"切层不跳"依赖它）；默认 False 时，
        「是否自动缩放画布」关闭就**整个不调** ``setSceneRect``——
        2026-10-14 用户口径「彻底关闭后，松鼠标也不要自动缩放**和平移**」。
        ⚠️ 为何不能"换个方式调再摆回去"：本视图设了 ``setAlignment``
        （AlignCenter），``setSceneRect`` **调用本身**就重排视口（实测额外
        平移 27px），而视口小于场景时 ``centerOn`` 被对齐钳制、居中对齐下
        滚动条又不代表真实位置 ⇒ 临时改 alignment／事后 centerOn／还原
        滚动条／按位移补偿四版补救**全部无效**（恒 27px）。不调才是可靠的。
        """
        if self._item is None:
            return
        if getattr(self, "_xf_dragging", False):
            return
        if not keep_view and not self._xf_auto_fit_canvas:
            return
        rect = self._content_scene_rect()
        if (self._context_item is not None
                and self._xf_auto_fit_pending
                and not self._xf_auto_fit_canvas):
            # 变换让内容扩出场景时保留旧视口可见范围，确保 QGraphicsView
            # 有足够滚动余量维持同一视口中心，而不是被滚动范围夹回内容中心。
            rect = rect.united(
                self.mapToScene(self.viewport().rect()).boundingRect())
        self._set_scene_rect_keeping_view(rect)

    def _content_scene_rect(self) -> QRectF:
        """当前图片内容范围，不含为保持视口位置而保留的空白场景范围。"""
        if self._context_item is None:
            # ⚠️ **单图模式维持旧口径**：矩形钉住原图矩形（2026-10-09「转多
            #    少圈画面都不动」——单图时场景常小于视口，AlignCenter 会跟着
            #    矩形中心走，矩形一扩画面就漂）。浮层跑出矩形的部分照常画得
            #    出来，只是滚不到——这是单图模式的既有取舍。
            return QRectF(self.image_rect())
        # 双图：并集圈住**两图当前显示范围**（内容再远也滚得到）
        rect = QRectF(self._display_bounds())
        context = (QRectF(self._context_display_rect)
                   if self._context_display_rect is not None
                   else self._context_item.sceneBoundingRect())
        return rect.united(context)

    def _set_scene_rect_keeping_view(self, rect: QRectF) -> None:
        """换场景矩形但**画面不动**（把原视口中心的场景点重新摆回中心）。

        ``setSceneRect`` 只改滚动范围；滚动值锚在矩形原点上，矩形原点一变，
        同样的滚动值就对应到别的场景位置（画面整体漂移——2026-10-09 报障的
        "格子跟图片相互远离"就是这个）。所以改完立刻把同一个场景点居中回来。
        """
        if self.sceneRect() == rect:
            return
        center = self.mapToScene(self.viewport().rect().center())
        self.setSceneRect(rect)
        self.centerOn(center)
