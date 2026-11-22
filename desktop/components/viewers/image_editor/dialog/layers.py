# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""多图编辑：图层状态 / 原点 / 切换画布。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut, QTransform
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget,
)

from desktop.ui import theme as T
from desktop.ui.window_size import apply_window_size
from ..canvas import EditorCanvas
from ..consts import (
    ERASER_DEFAULT, HISTORY_ORIGIN_LABEL, TEXT_COLOR_DEFAULT, TEXT_DEFAULT,
)
from ..geometry import _trim_transparent_edges, _transparent_content_bounds

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class LayersMixin(DialogHost):
    """多图编辑：图层状态 / 原点 / 切换画布。"""


    def configure_multiple_images(self, items: list[dict]) -> None:
        """把拼版源图装入同一编辑器画布，并以点击切换活动图片。"""
        if not 1 <= len(items) <= 2:
            raise ValueError("拼版编辑支持一张或两张图片")

        first = self._capture_layer_state()
        layers: list[dict] = []
        for item_index, item in enumerate(items):
            image = item.get("image")
            path = str(item.get("file") or "")
            if not isinstance(image, QImage) or image.isNull() or not path:
                raise ValueError("双图编辑的图片或源文件路径无效")
            raw = image.convertToFormat(QImage.Format.Format_ARGB32)
            trimmed = _trim_transparent_edges(raw)
            trim_offset = (0, 0)
            if trimmed is not None and trimmed[1:] != (0, 0):
                raw = trimmed[0]
                trim_offset = (trimmed[1], trimmed[2])

            rect_values = item.get("rect")
            if isinstance(rect_values, (list, tuple)) and len(rect_values) == 4:
                rect = QRectF(
                    float(rect_values[0]), float(rect_values[1]),
                    float(rect_values[2]), float(rect_values[3]),
                )
            elif isinstance(rect_values, QRectF):
                rect = QRectF(rect_values)
            else:
                raise ValueError("双图编辑的拼版区域无效")
            if rect.isNull() or raw.isNull():
                raise ValueError("双图编辑的拼版区域无效")
            state = first.copy()
            state.update({
                "_image": raw.copy(),
                "_original": raw.copy(),
                "_content_state": None,
                "_content_read": False,
                "_content_restored": False,
                "_content_seed": None,
                "_content_upright": None,
                "_content_pixels_dirty": False,
                "_content_restore_params": None,
                "_content_restore_target": 0.0,
                "_content_trim_offset": trim_offset,
                "_pending_crop": None,
                "_undo": [],
                "_redo": [],
                "_undo_origins": [],
                "_redo_origins": [],
                "_labels": [],
                "_origin_label": HISTORY_ORIGIN_LABEL,
            })
            layers.append({
                "state": state,
                "canvas_state": None,
                "file": path,
                "page_item_index": item_index,
                "rect": rect,
                "rotation": float(item.get("rotation", 0.0) or 0.0),
                # ⚠️⚠️ 比例必须按**裁边后的 raw（可见内容）**算，**不能**按入口
                #    传进来的整张原图算（2026-10-15 用户报障「拼版页移动图片后
                #    弹窗编辑，两图位置/大小对不上；弹窗里移动后应用，拼版页大小
                #    不对、图片高度被压缩」）：拼版侧 ``rect`` 是**可见内容框**
                #    （画布 ``_trim_transparent_border``、合成 ``_trim_to_content``、
                #    ``refresh_rects_for_edited_source`` 全是内容口径），而去底色
                #    产物普遍带透明留白（内容 < 整图）。按整图算会把比例算**小**
                #    ⇒ ① 弹窗里两图相对距离被放大、各自显示得比页面小一圈；
                #    ② 回写 ``content_w * scale`` 也偏小 ⇒ 页面 rect 缩水（高度
                #    被压扁）。此处改按内容尺寸算后，写回值＝入口 rect 尺寸，
                #    与页面所见一致；旧的"整尺寸 rect"版面也由比例自动桥接。
                "scale": (
                    rect.width() / max(1, raw.width()),
                    rect.height() / max(1, raw.height()),
                ),
                # ---- 内容原点（2026-10-13「两张图片相互远离」）----
                #: 当前 ``_image`` 左上角在**入口内容坐标系**里的位置。
                #: 初值必须是 ``(0, 0)``：入口 ``_image`` 已被
                #: ``_trim_transparent_edges`` 收成**内容图**，画布 (0,0) 就是内容
                #: 原点。旧值填入口收紧偏移，等于把这段留白**重复计一次**——
                #: ``_refresh_multi_canvas`` 的 offset 公式里 origin 项与 ``rect``
                #: 反映的是同一段几何（两侧原点不同时两图就会挨得比页面近，
                #: 2026-10-15 报障的"位置对不上"正出在这儿）。
                #: 之后每次真裁剪/变换烘焙才按新画布左上角累加
                #: （见 :meth:`_multi_layer_shift`）。双图相对摆放全靠它换算，
                #: 不追踪的话一边裁剪/旋转，另一边就"漂走"。
                #: ``origin0``＝「还原」时的初值。
                "origin": (0.0, 0.0),
                "origin0": (0.0, 0.0),
                # ---- 挂起效果的**静态显示图**（ghost，2026-10-13）----
                #: 非活动层也要"看到它转过的样子"（用户口径：A 旋转了，
                #: 切到 B 操作时 A 的旋转效果要存在）——切走时把画布上
                #: 未烘焙的变换预览（底图残余+浮层）用 QPainter 拼成一张
                #: ghost（零重采样），非活动态就显示它；切回本层作废。
                "ghost": None,
                "ghost_origin": None,
                "label": "",
            })

        layers.sort(key=lambda layer: layer["rect"].center().x())
        if len(layers) == 2:
            layers[0]["label"] = "左图"
            layers[1]["label"] = "右图"
        else:
            layers[0]["label"] = "单图"
        self._multi_layers = layers
        self._active_layer = 0
        self._save_back = True
        self.target_name = "左图与右图"
        self._build_layer_switcher()
        self._load_layer(0)
        self.canvas.set_image(self._image)
        self._refresh_multi_canvas()
        self.canvas.fit()
        self.done_btn.setToolTip(
            "确认后保存有修改的源图；未修改的图片保持不变"
        )
        self._refresh_size_label()

    def _capture_layer_state(self) -> dict:
        """把当前编辑状态快照进层字典（换层时保存/装回）。

        ⚠️⚠️ **全部浅拷贝**（2026-10-13「切换不丝滑」）：旧版对 ``_image``/
        ``_original``/upright 和整个撤销栈做 ``.copy()`` **深拷贝**——最多
        12 份整图快照 × 2 份 × 2 层，12 MP 下一刀就是几百 MB 的 memcpy，
        换层卡一两秒全耗在这儿。QImage 本身隐式共享（写时分离）：擦除是
        就地画（QPainter 会先 detach）、裁剪/变换/文字都生成新图——浅拷贝
        的快照不可能被后续编辑写穿。列表同理只 ``list()`` 浅拷贝（层字典
        与 ``self`` 不能共享**同一个列表对象**，append/pop 会串）。
        """
        names = (
            "_image", "_original", "_content_state", "_content_read",
            "_content_restored", "_content_seed", "_content_upright",
            "_content_pixels_dirty", "_content_restore_params",
            "_content_restore_target", "_content_trim_offset",
            "_pending_crop", "_undo", "_redo", "_labels", "_origin_label",
            "_undo_origins", "_redo_origins",
        )
        state = {}
        for name in names:
            value = getattr(self, name, None)
            if name in ("_image", "_original", "_content_upright") \
                    and isinstance(value, QImage):
                value = QImage(value)          # 浅拷贝：隐式共享
            elif name in ("_undo", "_redo", "_undo_origins", "_redo_origins"):
                assert isinstance(value, list)
                value = list(value)
            elif name == "_labels":
                assert isinstance(value, list)
                value = list(value)
            elif name == "_content_restore_params" and value is not None:
                value = dict(value)
                if isinstance(value.get("image"), QImage):
                    value["image"] = QImage(value["image"])
            state[name] = value
        return state

    def _load_layer(self, index: int) -> None:
        self._active_layer = index
        layer = self._multi_layers[index]
        for name, value in layer["state"].items():
            setattr(self, name, value)
        self.source_path = layer["file"]
        self.target_name = layer["label"]

    def _refresh_multi_canvas(self) -> None:
        if not self._multi_layers or self._active_layer < 0:
            return
        active = self._multi_layers[self._active_layer]
        if len(self._multi_layers) == 1:
            self.canvas.set_context_image(None)
            self.setWindowTitle("图片编辑 - 单图")
            return
        other = self._multi_layers[1 - self._active_layer]
        active_scale_x, active_scale_y = self._layer_scale(active)
        other_scale = self._layer_scale(other)
        delta = other["rect"].topLeft() - active["rect"].topLeft()
        # ⚠️ 相对摆放按**内容原点**（origin）换算（2026-10-13）：active 的
        #    画布经过裁剪/变换后，它的 (0,0) 已经不在"初始图"的 (0,0) 上了
        #    ——不把这段位移算进去，active 一编辑，另一张就"漂走"。other 的
        #    origin 决定它自己的内容起点，active 的 origin 决定坐标系锚点。
        #    other 带 ghost 时显示原点再挪 ghost 左上角（挂起变换把内容
        #    搬出了原画布，ghost 的 (0,0) 不是 `_image` 的 (0,0)）。
        active_origin = self._layer_display_origin(active)
        other_origin = self._layer_display_origin(other)
        offset = QPointF(
            delta.x() / active_scale_x
            + other_origin[0] * other_scale[0] / active_scale_x
            - active_origin[0],
            delta.y() / active_scale_y
            + other_origin[1] * other_scale[1] / active_scale_y
            - active_origin[1],
        )
        # 场景矩形的并集由画布按"显示图尺寸的未旋转版"算（见
        # canvas.set_context_image / _sync_scene_rect）：与它成为活动层时的
        # `_display_bounds` 同口径 ⇒ 换层画面不跳、内容再远也滚得到。
        self.canvas.set_context_image(
            other.get("ghost") or other["state"]["_image"], offset,
            other_scale[0] / active_scale_x,
            other_scale[1] / active_scale_y,
            other["rotation"],
        )
        self.setWindowTitle(
            f"图片编辑 - {active['label']}（点击另一张图片切换）"
        )

    # ---- 双图内容原点（相对摆放的锚，2026-10-13） ----
    @staticmethod
    def _layer_origin(layer: dict) -> tuple[float, float]:
        origin = layer.get("origin")
        if not origin:
            return (0.0, 0.0)
        return (float(origin[0]), float(origin[1]))

    @staticmethod
    def _layer_scale(layer: dict) -> tuple[float, float]:
        sx, sy = layer["scale"]
        return (max(0.01, float(sx)), max(0.01, float(sy)))

    def _layer_display_origin(self, layer: dict) -> tuple[float, float]:
        """层的**显示原点**＝内容原点 + ghost 偏移（初始图像素系）。"""
        o = self._layer_origin(layer)
        g = layer.get("ghost_origin") or (0.0, 0.0)
        return (o[0] + float(g[0]), o[1] + float(g[1]))

    def _render_layer_ghost(self):
        """把活动层**当前显示效果**（含未烘焙的变换浮层）拼成静态 ghost。

        用户 2026-10-13 口径：切层**不**"应用变换"——左侧转了 15°，切到
        右侧操作时，左侧必须**仍然显示转过的样子**。浮层像素（底图残余
        ``_paint_image`` + 变换内容浮层）都是画布上现成的图元像素，用
        QPainter 按各自图元变换拼一张图即得（一次合成，**零重采样**，
        12 MP 也是几十毫秒）；切回本层时实时预览从快照原样恢复，ghost
        作废。返回 ``(ghost, ghost 左上角在当前画布坐标系的位置)``；
        画布上没有未烘焙的变换浮层时返回 ``None``（非活动态直接显示
        ``_image``）。⚠️ 走到这里前若刚 ``_commit_crop`` 过，浮层已被
        ``set_image`` 清掉（裁剪+变换同挂时切层丢预览是既有行为）。
        """
        canvas = self.canvas
        float_item = getattr(canvas, "_float_item", None)
        if float_item is None or self._image is None:
            return None
        from PySide6.QtGui import QColor, QPainter

        float_pixmap = float_item.pixmap()
        if float_pixmap.isNull():
            return None
        # 浮层像素口径：精确档（松手后重采样过）⇒ 纯缩放平移；拖动中
        # （原始区域像素 + 图元承担变换）⇒ 快速矩阵。与屏幕显示一致。
        if canvas._xf_preview_keyframe is not None:
            float_xf = canvas._float_placement()
        else:
            float_xf = canvas._float_fast_xf()
        # 外框＝内容紧凑外框（与 `_display_bounds` 同一套数学）：整幅选区
        # 时底图一片空白不算，只有局部选区才并上底图残余。
        bounds = None
        if not canvas._backdrop_is_whole() and canvas._paint_image is not None:
            bounds = QRectF(canvas._base_current_rect())
        float_rect = float_xf.mapRect(
            QRectF(0, 0, float_pixmap.width(), float_pixmap.height()))
        bounds = float_rect if bounds is None else bounds.united(float_rect)
        rect = bounds.toAlignedRect()
        if rect.isEmpty():
            return None
        ghost = QImage(rect.width(), rect.height(),
                       QImage.Format.Format_ARGB32)
        ghost.fill(QColor(0, 0, 0, 0))
        painter = QPainter(ghost)
        world = QTransform().translate(-rect.x(), -rect.y())
        base = canvas._paint_image
        base_scale = canvas._xf_base_scale
        # 先映射到场景坐标，再减 ghost 原点；顺序反过来会让缩放后的
        # 平移量不匹配外框，大图降采样时内容就会偏移并被截断。
        base_xf = QTransform()
        if base_scale is not None:
            base_xf = QTransform().scale(
                base_scale.x(), base_scale.y())
        base_xf = base_xf * QTransform().translate(
            canvas._xf_base_origin.x(), canvas._xf_base_origin.y())
        base_xf = base_xf * world
        # ⚠️ 整幅选区时底图是一片空白（内容全在浮层上）——不画进 ghost，
        #    ghost 外框＝内容紧凑外框（与活动图边框同一口径，2026-10-13）。
        if (base is not None and not base.isNull()
                and not canvas._backdrop_is_whole()):
            painter.setTransform(base_xf)
            painter.drawImage(0, 0, base)
        painter.setTransform(float_xf * world)
        painter.drawPixmap(0, 0, float_pixmap)
        painter.end()
        return ghost, (float(rect.x()), float(rect.y()))

    def _active_layer_origin(self) -> tuple[float, float]:
        layers = getattr(self, "_multi_layers", None)
        if layers and 0 <= self._active_layer < len(layers):
            return self._layer_origin(layers[self._active_layer])
        return (0.0, 0.0)

    def _set_active_layer_origin(self, origin) -> None:
        layers = getattr(self, "_multi_layers", None)
        if layers and 0 <= self._active_layer < len(layers):
            layers[self._active_layer]["origin"] = (
                float(origin[0]), float(origin[1]))

    def _reset_active_layer_origin(self) -> None:
        """「还原」把 origin 退回本层初值（＝入口收紧偏移）。"""
        layers = getattr(self, "_multi_layers", None)
        if layers and 0 <= self._active_layer < len(layers):
            layers[self._active_layer]["origin"] = tuple(
                layers[self._active_layer].get("origin0") or (0.0, 0.0))

    def _multi_layer_shift(self, dx: float, dy: float) -> None:
        """活动层的画布原点平移 ``(dx, dy)``（初始图像素系）。

        两个调用点，语义都是"新画布的 (0,0) 在旧画布里挪到了哪儿"：

        - **真裁剪**（``_commit_crop``）：``+= 裁剪框左上角``；
        - **变换烘焙**（``_commit_transform``，adjust/aspect 档）：
          ``+= compose_transform`` 返回的新画布原点。

        ⚠️ 必须在 ``_push_undo`` **之后**调（撤销点要带走平移**前**的
        origin，撤销才能退回去）。
        """
        if not getattr(self, "_multi_layers", None):
            return
        ox, oy = self._active_layer_origin()
        self._set_active_layer_origin((ox + float(dx), oy + float(dy)))
