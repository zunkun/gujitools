# -*- coding: utf-8 -*-
"""图片拼版操作画布：**白底**上拖动 / 缩放拉伸 / 旋转两张源图。

坐标体系与落盘完全一致——**源图像素，左上原点，x 向右、y 向下**
（``desktop.services.imposition``）。控件把「所有图的外接框」等比缩放到可视区，
用 ``px_per_unit`` 在「图坐标」与「控件像素」之间换算；用户拖动/缩放/旋转
得到的结果直接写回 ``drafts/imposition.json`` 的 ``items``，由
``compose_page`` 原样采用——所见即所得。

**拼版没有纸张**（用户 2026-09-30：「这个拼版不需要设置纸张，只需要背景是
白色的就行，后续提交的时候根据图片的四个区域合并出一张图片」）：画布就是一块
白底，没有纸张矩形、也没有边界线；产出图由服务层按「所有图外接框」紧裁。

交互（用户定的观感）：
- **点击某张图 → 选中**：选中的图带一圈**常显的细虚线**（选中状态，
  **跟着图一起转**——用户 2026-09-30 报过"旋转后高亮框不跟着转"）；
  **按住鼠标操作期间**才升级为带手柄/旋转钮的完整虚线框，**一松手回到
  细框**（2026-09-30：选中态要一直看得见，右侧「当前图片样式」区跟着激活）；
- **切页 / 点空白处 → 取消选中**（右侧图片操作区随之灰掉）；
- **双击某张图 → 预览这张原图**；**双击两图之外的空白处 → 预览左右组合**
  （整页按产出口径合成的效果，``emit`` 给控制器开预览弹窗，画布自己不管弹窗）；
- **滚轮 → 缩放视图**（以光标为锚点，松开即停在当前倍率）：缩放只改
  ``_px_per_unit`` 与偏移两个数，不解码、不重排；重绘**不在滚轮事件里直接
  要**——滚轮/触控板连发时一秒能来上百个事件，直接要就是把大图重绘拉到
  事件率。渲染合并策略见 ``wheelEvent`` / ``_on_wheel_frame``：滚动期间每
  帧最多重绘一次、走**快速档**（不做平滑采样），停稳后补一帧高质量重绘；
- 未按下时靠**光标**提示可抓的位置：图内 `OpenHand`、四角/四边缩放光标、
  框上方圆钮处 `Cross`（命中判定是几何的，不依赖框线可见）；
- 点某张图 → 选中；框内拖动 → 整体移动；**四角**手柄 → 缩放（按住 Shift
  等比）；**四条边整条都是命中带** → 只改一个维度；框**上方的小圆钮** → 旋转
  （按住 Shift 吸附到 15°）；松手 emit ``items_changed``（拖动过程中只重绘）；
- **红色对齐线**恒显（**两图页**）：两图 rect 中心中点所在的竖线
  （``SPINE_COLOR``）——整版/单图旋转时拿它当"转没转歪"的对比基准；
  **单图页只认横图（源图宽>高）**（2026-09-30 用户定：单独一张半页图片
  不需要显示中间红线；单独一张整幅对开（横图）仍要）——判据用源图
  宽高比（竖图=半页/单页、横图=整幅对开），文件名后缀认不出"无后缀的
  半页图"；整版旋转走 ``rotate_whole``（滑块增量，绕该中点公转+自转），
  单图绝对角度走 ``set_item_rotation``，两者都只重绘、由控制器择机 commit；
- **灰色截图范围框**恒显（``CROP_COLOR``）：两图旋转后外接框的并集——
  上下左右最外侧点组成的虚线矩形，与产出图的紧裁范围是同一套几何
  （``services.imposition.page_bounds``），转一转就能看到范围跟着变。

**⚠️ 不限制图片位置/大小**（用户：「图片拉伸、移动后可能超出原本界限，现在是
不显示了，现在不要限制」）：拖动与缩放**都不夹在某个范围内**，画布也**不做
裁剪**——画到哪就是哪，可视范围按所有图的外接框自适应，打开一页就能看全。

⚠️ ``rotation`` 是**顺时针角度**（与 Qt ``QPainter.rotate`` 同向），绕该项
``rect`` 的中心转——与 PIL 合成侧的取负口径配套（见 services.imposition）。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget
from qfluentwidgets import Action, RoundMenu
from qfluentwidgets import FluentIcon as FIF

from desktop.ui import theme as T

#: 背景恒白（用户口径：拼版不需要纸张，白底就行）
PAGE_COLOR = QColor("#ffffff")
#: 选中框是**虚线**（用户 2026-09-30：默认不显示蓝边，按住操作时才出现虚线）
FRAME_STYLE = Qt.PenStyle.DashLine
FRAME_COLOR = QColor("#0E7C8B")
HANDLE_STROKE = QColor("#0E7C8B")
HANDLE_FILL = QColor("#ffffff")
HANDLE_RADIUS = 5
ROTATE_KNOB_RADIUS = 6
ROTATE_KNOB_GAP = 26  # 旋转钮距框上边的距离（控件像素）

_CORNER_CURSORS = [
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
    Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor,
]
_EDGE_CURSORS = [
    Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
]
_HANDLE_CURSORS = _CORNER_CURSORS + _EDGE_CURSORS

#: 边手柄索引 → 受影响的边
_EDGE_BY_HANDLE = {4: "top", 5: "right", 6: "bottom", 7: "left"}

#: 框的最小边长（合成像素）：拖到两边重合会让命中判定与后续缩放都失效
MIN_RECT = 4.0
#: 边命中带（控件像素）：距边线这么近就算"拖这条边"，不限边中点
EDGE_HIT_PX = 6

#: 旋转吸附步长（按住 Shift）
SNAP_DEGREES = 15.0

#: **红色对齐线**（用户 2026-09-30：左右两张文本框中心的垂直红色虚线，无论
#: 何时都显示——整体旋转时它就是"转没转歪"的对比基准）
SPINE_COLOR = QColor("#E02020")

#: **成品截图范围框**（用户 2026-09-30：整版旋转时要能看到"截图框"——两图
#: 上下左右四个方向最外侧点组成的虚线框）。与产出图的紧裁范围
#: （``services.imposition.page_bounds``）同一套几何，恒显。
CROP_COLOR = QColor("#5F6368")

#: 滚轮缩放步长（每格 120 的角度增量算一格；与预览弹窗同款手感）
WHEEL_ZOOM_STEP = 1.15
#: 滚轮缩放倍率边界（相对"适配可视区"的基准倍率）：太小会找不到图，
#: 太大缩放期间像素化的图没有参考价值
ZOOM_MIN = 0.2
ZOOM_MAX = 8.0
#: 滚轮连发期间的重绘合并窗口：窗口内最多重绘一帧（约 33fps）
WHEEL_REPAINT_MS = 30


class ImpositionCanvas(QWidget):
    """拼版画布：白底上拖动/缩放/旋转两张图；``items_changed`` 发出图坐标。"""

    #: 版面变化（松手时发一次；切页/离开页面前由 flush_pending 补发）
    items_changed = Signal(list)
    #: 当前选中的图（0 右槽 / 1 左槽 / -1 未选中）
    selection_changed = Signal(int)
    #: **双击某张图**（0 右槽 / 1 左槽）：请求预览这张原图
    item_double_clicked = Signal(int)
    #: **双击了图片之外的空白处**：请求预览整页左右组合
    spread_double_clicked = Signal()
    #: **右键菜单「编辑单图」**（0 右槽 / 1 左槽）：不经预览弹窗，直接编辑
    #: 这张原图（2026-10-01 用户定：编辑原本是预览弹窗里的按钮，现在右键直达）
    item_edit_requested = Signal(int)
    #: **右键菜单在空白处选了「编辑整图」**：直接编辑整页左右组合（成品口径）
    spread_edit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self._items: list[dict] = []
        self._images: dict[str, QImage] = {}
        self._selected = -1
        self._pad = 18
        self._px_per_unit = 1.0
        self._off_x = float(self._pad)
        self._off_y = float(self._pad)
        self._mode: str | None = None  # move / resize / rotate
        self._handle = 0
        self._grab_x = 0.0
        self._grab_y = 0.0
        self._grab_rect = [0.0, 0.0, 0.0, 0.0]
        self._grab_rotation = 0.0
        self._grab_angle = 0.0
        #: 缩放手势起点时 rect 中心（控件像素）：局部换算的固定锚点，
        #: 不能用"当前中心"——缩放过程中中心在动，会越算越飘
        self._grab_center = QPointF()
        self._dirty = False
        #: 鼠标是否**按下**（框线/手柄只在按住期间画，见模块 docstring）
        self._pressed = False
        #: 用户滚轮缩放倍率（1.0 = 适配可视区）；``_px_per_unit`` 是它套在
        #: 适配基准（``_fit_ppu``）上的最终值——几何换算只看后者
        self._zoom = 1.0
        #: 适配基准：按「所有图外接框」算出的基准比例与偏移（不含滚轮缩放）
        self._fit_ppu = 1.0
        self._fit_off_x = float(self._pad)
        self._fit_off_y = float(self._pad)
        # ---- 滚轮缩放的渲染合并（减渲染的重头，见 wheelEvent）----
        self._wheel_burst = False       # 滚动连发期间：重绘走快速档
        self._wheel_paint_pending = False  # 窗口内又来了滚动：并到下一帧
        self._wheel_timer = QTimer(self)
        self._wheel_timer.setSingleShot(True)
        self._wheel_timer.setInterval(WHEEL_REPAINT_MS)
        self._wheel_timer.timeout.connect(self._on_wheel_frame)
        self.setMouseTracking(True)
        # ⚠️ 背景**恒白**，不是主题色：拼版没有纸张了，这块就是成品的底
        self.setStyleSheet(
            f"background:{PAGE_COLOR.name()}; border:1px solid {T.BORDER};"
            f" border-radius:{T.RADIUS_MD}px;"
        )

    # ------------------------------------------------------------------ API
    def set_page(self, items) -> None:
        """设置这一页的版面（图坐标即源图像素）；**不选中任何图**。

        ⚠️ 参数**只有 items**：拼版没有纸张（用户 2026-09-30），可视范围按
        「所有图的外接框」自适应，不再有一个"纸张矩形"要摆。
        ⚠️ 每次载页都**清空选中**（用户 2026-09-30：切页后右侧「操作当前
        图片」区不激活，点击某张图才选中）。
        """
        self._items = [
            {
                "file": str(item.get("file") or ""),
                "rect": [float(v) for v in item["rect"]],
                "rotation": float(item.get("rotation") or 0.0),
            }
            for item in (items or [])
            if item.get("rect")
        ]
        self._selected = -1
        self._dirty = False
        self._pressed = False
        self._zoom = 1.0  # 载页回"打开就能看全"
        # ⚠️ 换页必须丢掉上一页的 QImage 缓存：一页两张原图（几千像素见方，
        # 各几十 MB），一路翻几十页就能把内存吃到 GB 级。当前页只有两张，
        # 缓存只需覆盖这一页。
        self._images = {}
        self._recompute()
        self.selection_changed.emit(self._selected)
        self.update()

    def clear_page(self) -> None:
        """清空（无拼版页时用）：只留白底。"""
        self._items = []
        self._selected = -1
        self._dirty = False
        self._pressed = False
        self._zoom = 1.0
        self._images = {}
        self.selection_changed.emit(-1)
        self.update()

    def items(self) -> list[dict]:
        """当前版面（合成像素，已四舍五入到两位）。"""
        return [
            {
                "file": item["file"],
                "rect": [round(v, 2) for v in item["rect"]],
                "rotation": round(float(item.get("rotation") or 0.0), 2),
            }
            for item in self._items
        ]

    def selected(self) -> int:
        """当前选中的槽位下标（-1 = 未选中）。"""
        return self._selected

    def select(self, index: int) -> None:
        """外部选中某个槽位（右侧面板切换时用）。"""
        if index == self._selected:
            return
        self._selected = index if 0 <= index < len(self._items) else -1
        self.selection_changed.emit(self._selected)
        self.update()

    def has_items(self) -> bool:
        return bool(self._items)

    def _spine_visible(self) -> bool:
        """红色对齐线要不要画：两图页恒显；**单图页只认横图（宽>高）**。

        单图页判据走**源图的宽高比**而不是文件名后缀（用户 2026-09-30 晚：
        「单独一张半页图片在某页，不需要显示中间红线」）——实际任务里
        **没有 ``-l``/``-r`` 后缀的竖图也可能是半页**（整幅误检、封面插页、
        单页扫描），文件名认不出来，而半页/单页图恒为竖图（高≥宽）、
        整幅对开页恒为横图（宽>高，见任务 0007 实测 1917×1410）。
        尺寸读不到（文件已丢）不画——宁可少画也不画误导线。
        """
        if len(self._items) >= 2:
            return True
        if len(self._items) == 1:
            size = self._image_size(self._items[0]["file"])
            return size is not None and size[0] > size[1]
        return False

    def frame_visible(self) -> bool:
        """当前是否画**带手柄的完整操作框**（= 鼠标按住期间）。

        平时选中的图另有常显细框（``_draw_selected_border``），不算在内。
        """
        return self._pressed and 0 <= self._selected < len(self._items)

    # ------------------------------------------------------------------ 编辑入口
    def rotate_selected(self, delta_deg: float) -> None:
        """把选中的图旋转 ``delta_deg``（顺时针为正），并立即上报。"""
        if not 0 <= self._selected < len(self._items):
            return
        item = self._items[self._selected]
        item["rotation"] = (float(item.get("rotation") or 0.0) + delta_deg) % 360.0
        self._emit_changed()

    def rotate_whole(self, delta_deg: float) -> None:
        """**整版旋转** ``delta_deg``（顺时针为正）：两张图绕公共中心转。

        公共中心 = 两图 ``rect`` 中心的**中点**（也就是红色对齐线所在的竖线，
        见 ``_spread_center_units``）。每张图"中心绕公共中心公转 + 自身
        ``rotation`` 叠加"——两图的相对位置、相对角度都不变，对齐线也不动，
        用户拖滑块时看到的就是整版在一根固定的中线上左右倾摆。

        ⚠️ 只重绘**不上报**：滑块会连续吐增量，落盘交给控制器在停顿后统一
        ``flush_pending``（与拖动的"松手才上报"同一策略）。
        """
        if not self._items:
            return
        center_x, center_y = self._spread_center_units()
        rad = math.radians(delta_deg)
        cos_v, sin_v = math.cos(rad), math.sin(rad)
        for item in self._items:
            x, y, w, h = item["rect"]
            dx = x + w / 2.0 - center_x
            dy = y + h / 2.0 - center_y
            # y 向下坐标系里的"视觉顺时针"旋转矩阵（与 QPainter.rotate 同向）
            item["rect"] = [
                center_x + dx * cos_v - dy * sin_v - w / 2.0,
                center_y + dx * sin_v + dy * cos_v - h / 2.0,
                w, h,
            ]
            item["rotation"] = (
                float(item.get("rotation") or 0.0) + delta_deg
            ) % 360.0
        self._dirty = True
        self.update()

    def set_item_rotation(self, angle_deg: float) -> None:
        """把选中的图的旋转设为绝对角度（绕自身 rect 中心，只重绘不上报）。"""
        if not 0 <= self._selected < len(self._items):
            return
        self._items[self._selected]["rotation"] = float(angle_deg) % 360.0
        self._dirty = True
        self.update()

    def spread_rotation(self) -> float | None:
        """整版当前的"平均旋转角"（收敛到 [-180, 180)；无图返回 None）。

        单图自转过后两图角度可能不同，这里取平均当作整版角度——滑块就以
        这个值为基准继续吐增量，两图的角度差原样保留。
        """
        if not self._items:
            return None
        mean = sum(
            float(item.get("rotation") or 0.0) for item in self._items
        ) / len(self._items)
        return (mean + 180.0) % 360.0 - 180.0

    def selected_rotation(self) -> float | None:
        """选中图当前的旋转角（无选中返回 None）。"""
        if not 0 <= self._selected < len(self._items):
            return None
        return float(self._items[self._selected].get("rotation") or 0.0)

    def refit(self) -> None:
        """按当前 items 重新适配可视区并重绘（整版旋转后外接框变了）。

        ⚠️ 滚轮缩放倍率一并归一：这里语义就是"回到打开时的样子"。
        """
        self._zoom = 1.0
        self._recompute()
        self.update()

    def flush_pending(self) -> bool:
        """把"还没松手"的编辑结果补发出去（切页/切步骤/离开时调）。

        与 ``print_layout_canvas.flush_pending`` 同一理由：``items_changed``
        只在松手时发，拖住不放直接切走会让这一下改动永久丢失。
        """
        self._pressed = False  # 换了页/离开就别留着框线
        if not self._dirty:
            self.update()
            return False
        self._emit_changed()
        return True

    def _emit_changed(self) -> None:
        self._dirty = False
        self.update()
        self.items_changed.emit(self.items())

    # ------------------------------------------------------------------ 坐标
    def _scene_rect(self) -> QRectF:
        """需要显示的范围（图坐标）：**所有图外接框的并集**。

        拼版没有纸张（用户 2026-09-30），可视范围就按图算——这样挪多远、拉多大
        都还看得见（超出控件可视区的部分由 Qt 丢弃，与"我们主动裁掉"不同）。
        旋转过的图按**外接框**算（用 w/h 与角度推），与画出来的样子一致。
        没有图时给一个占位方块，避免除零（此时画面就是纯白底）。
        """
        boxes = [self._item_box_units(item) for item in self._items]
        if not boxes:
            return QRectF(0.0, 0.0, 1.0, 1.0)
        return QRectF(
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(max(b[2] for b in boxes) - min(b[0] for b in boxes), 1.0),
            max(max(b[3] for b in boxes) - min(b[1] for b in boxes), 1.0),
        )

    @staticmethod
    def _item_box_units(item: dict) -> tuple[float, float, float, float]:
        """一项的**外接框**（旋转后），单位与图坐标一致。"""
        x, y, w, h = item["rect"]
        center_x, center_y = x + w / 2.0, y + h / 2.0
        angle = math.radians(float(item.get("rotation") or 0.0))
        box_w = abs(w * math.cos(angle)) + abs(h * math.sin(angle))
        box_h = abs(w * math.sin(angle)) + abs(h * math.cos(angle))
        return (center_x - box_w / 2.0, center_y - box_h / 2.0,
                center_x + box_w / 2.0, center_y + box_h / 2.0)

    def _spread_center_units(self) -> tuple[float, float]:
        """两图 rect 中心的**中点**（图坐标）——红色对齐线的落点。

        ⚠️ 用**未旋转的 rect 中心**（不是外接框中心）：单图自转不挪中心，
        整版旋转又绕这个中点公转——所以无论怎么转，对齐线都稳稳钉在同一处。
        只有一张图时就是它自己的中心。
        """
        if not self._items:
            return 0.0, 0.0
        centers = [
            (item["rect"][0] + item["rect"][2] / 2.0,
             item["rect"][1] + item["rect"][3] / 2.0)
            for item in self._items
        ]
        return (
            sum(c[0] for c in centers) / len(centers),
            sum(c[1] for c in centers) / len(centers),
        )

    def _recompute(self) -> None:
        """按「所有图的外接框」等比适配控件，再套上滚轮缩放倍率。

        ⚠️ 只在 ``set_page`` / 尺寸变化时算，**拖动过程中不重算**——否则一边拖
        一边缩放视图，手感会飘。所以拖动把图挪出可视区是可能的：松手后切页再
        回来（或窗口尺寸一变）就会重新适配、把整页显示全。
        ⚠️ 尺寸变化**保留**滚轮缩放倍率：只重算适配基准（``_fit_*``），倍率以
        控件中心为锚套回去——拖一下窗口大小不该把视图打回原形。归一只有
        ``set_page`` / ``refit`` 两处。
        """
        avail_w = self.width() - 2 * self._pad
        avail_h = self.height() - 2 * self._pad
        scene = self._scene_rect()
        if avail_w <= 0 or avail_h <= 0 or scene.width() <= 0 or scene.height() <= 0:
            self._fit_ppu = 1.0
            self._fit_off_x = float(self._pad)
            self._fit_off_y = float(self._pad)
        else:
            self._fit_ppu = min(
                avail_w / scene.width(), avail_h / scene.height()
            )
            self._fit_off_x = (
                (self.width() - scene.width() * self._fit_ppu) / 2.0
                - scene.x() * self._fit_ppu
            )
            self._fit_off_y = (
                (self.height() - scene.height() * self._fit_ppu) / 2.0
                - scene.y() * self._fit_ppu
            )
        self._px_per_unit = self._fit_ppu * self._zoom
        # 以控件中心为锚套倍率：场景中心（适配时在控件中心）不动
        cx, cy = self.width() / 2.0, self.height() / 2.0
        self._off_x = cx - (cx - self._fit_off_x) * self._zoom
        self._off_y = cy - (cy - self._fit_off_y) * self._zoom

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._recompute()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._recompute()
        self.update()

    def _to_units(self, pos: QPointF) -> tuple[float, float]:
        """控件坐标 → 合成像素坐标。"""
        return (
            (pos.x() - self._off_x) / self._px_per_unit,
            (pos.y() - self._off_y) / self._px_per_unit,
        )

    def _rect_px(self, index: int) -> QRectF:
        x, y, w, h = self._items[index]["rect"]
        return QRectF(
            self._off_x + x * self._px_per_unit,
            self._off_y + y * self._px_per_unit,
            w * self._px_per_unit,
            h * self._px_per_unit,
        )

    def _to_local_px(self, index: int, pos: QPointF) -> QPointF:
        """控件像素 → 该项**局部**坐标：原点 = rect 中心，已反转旋转角。

        框与手柄是**跟着图一起转**的（用户 2026-09-30），命中判定、缩放取
        鼠标都得先反转旋转角——不反转就等于拿"转过的鼠标"去比"没转的框"。
        返回值与 ``_handle_positions_local`` / ``_rotate_knob_local`` 同一
        坐标系，可以直接比。
        """
        c = self._rect_px(index).center()
        angle = math.radians(float(self._items[index].get("rotation") or 0.0))
        cos_v, sin_v = math.cos(-angle), math.sin(-angle)
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        return QPointF(dx * cos_v - dy * sin_v, dx * sin_v + dy * cos_v)

    def _item_contains_px(self, index: int, pos: QPointF) -> bool:
        """点（控件像素）是否落在该项**旋转后**的图里。"""
        r = self._rect_px(index)
        local = self._to_local_px(index, pos)
        return (
            abs(local.x()) <= r.width() / 2.0
            and abs(local.y()) <= r.height() / 2.0
        )

    def _handle_positions_local(self, index: int) -> list[tuple[float, float]]:
        """手柄位置（**局部**坐标，rect 中心为原点）：四角 + 四边，恒 8 个。

        画框是在"平移到 rect 中心 + 旋转 rotation"的坐标系里画的，直接用它。
        """
        r = self._rect_px(index)
        hw, hh = r.width() / 2.0, r.height() / 2.0
        return [
            (-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh),
            (0.0, -hh), (hw, 0.0), (0.0, hh), (-hw, 0.0),
        ]

    def _handle_positions(self, index: int) -> list[tuple[float, float]]:
        """手柄位置（**控件**坐标，已按该项 rotation 转过）：命中判定与自测用。"""
        c = self._rect_px(index).center()
        angle = math.radians(float(self._items[index].get("rotation") or 0.0))
        cos_v, sin_v = math.cos(angle), math.sin(angle)
        return [
            (c.x() + lx * cos_v - ly * sin_v, c.y() + lx * sin_v + ly * cos_v)
            for lx, ly in self._handle_positions_local(index)
        ]

    def _rotate_knob_local(self, index: int) -> QPointF:
        """旋转钮位置（局部坐标）：框上边中点再向上 ``ROTATE_KNOB_GAP``。"""
        return QPointF(
            0.0, -self._rect_px(index).height() / 2.0 - ROTATE_KNOB_GAP
        )

    def _rotate_knob(self, index: int) -> QPointF:
        """旋转钮位置（**控件**坐标，已按该项 rotation 转过）。"""
        local = self._rotate_knob_local(index)
        c = self._rect_px(index).center()
        angle = math.radians(float(self._items[index].get("rotation") or 0.0))
        cos_v, sin_v = math.cos(angle), math.sin(angle)
        return QPointF(
            c.x() + local.x() * cos_v - local.y() * sin_v,
            c.y() + local.x() * sin_v + local.y() * cos_v,
        )

    def _hit_handle(self, index: int, pos: QPointF) -> int | None:
        """命中手柄：旋转钮 → 四角（圆点邻域）→ 四边（整条边的命中带）。

        ``pos`` 是控件坐标，先 ``_to_local_px`` 反转旋转角再与**局部**手柄
        位置比——框转了，命中带也跟着转（用户 2026-09-30）。
        """
        local = self._to_local_px(index, pos)
        knob = self._rotate_knob_local(index)
        if (abs(local.x() - knob.x()) <= ROTATE_KNOB_RADIUS + 3
                and abs(local.y() - knob.y()) <= ROTATE_KNOB_RADIUS + 3):
            return 8  # 旋转
        for i, (cx, cy) in enumerate(self._handle_positions_local(index)[:4]):
            if abs(local.x() - cx) <= HANDLE_RADIUS + 2 and \
                    abs(local.y() - cy) <= HANDLE_RADIUS + 2:
                return i
        r = self._rect_px(index)
        hit = EDGE_HIT_PX
        hw, hh = r.width() / 2.0, r.height() / 2.0
        near_top = abs(local.y() + hh) <= hit
        near_bottom = abs(local.y() - hh) <= hit
        near_left = abs(local.x() + hw) <= hit
        near_right = abs(local.x() - hw) <= hit
        x_in = -hw - hit <= local.x() <= hw + hit
        y_in = -hh - hit <= local.y() <= hh + hit
        if near_top and x_in:
            return 4
        if near_right and y_in:
            return 5
        if near_bottom and x_in:
            return 6
        if near_left and y_in:
            return 7
        return None

    def _item_at(self, pos: QPointF) -> int:
        """最上面一张命中的图（后画的在上 → 倒序找）。

        ⚠️ 命中按**旋转后**的图算：每个项各自反转自己的旋转角再判包含。
        """
        for index in range(len(self._items) - 1, -1, -1):
            if self._item_contains_px(index, pos):
                return index
        return -1

    # ------------------------------------------------------------------ 鼠标
    def invalidate_image(self, path: str) -> None:
        """某个源图文件被外部覆盖（编辑器「完成」回写）后：丢掉它的解码
        缓存并重绘——不丢的话画布会一直显示覆盖前的旧图。
        """
        self._images.pop(str(path), None)
        self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键菜单：**预览图片 / 编辑单图·编辑整图**（2026-10-01 用户定）。

        目标规则与双击一致：**图上** → 这张原图；**两图之外的空白** →
        整页左右组合（成品口径）。预览与双击走**同一组信号**（行为完全
        一样，只是入口多一个）；编辑是新加的直接入口——原本编辑是预览
        弹窗工具条里的按钮，现在不经过弹窗、右键直达，由控制器接管。
        编辑文案按目标区分（2026-10-07 用户定）：图上是「编辑单图」、
        空白是「编辑整图」——拼版页一张成品图由多张子图组成，目标是两
        种东西，同一句「编辑图片」让人不知道要改哪张。其余步骤没有这个
        区分，右键仍是「编辑图片」。
        右键即选中（与左键点击同款语义），右侧「当前图片样式」跟着激活。
        空画布没有菜单（没有可预览/可编辑的东西）。
        """
        if not self._items:
            return super().contextMenuEvent(event)
        index = self._item_at(QPointF(event.pos()))
        if index >= 0 and index != self._selected:
            self._selected = index
            self.selection_changed.emit(self._selected)
            self.update()
        menu = RoundMenu(parent=self)
        for text, icon, slot in (
            ("预览图片", FIF.PHOTO, lambda: self._emit_context(index, False)),
            ("编辑单图" if index >= 0 else "编辑整图", FIF.EDIT,
             lambda: self._emit_context(index, True)),
        ):
            action = Action(icon, text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.exec(event.globalPos())
        event.accept()

    def _emit_context(self, index: int, edit: bool) -> None:
        """右键菜单点了某一项：按目标（图上/空白）发出对应的请求信号。

        预览复用双击信号——两者对下游（视图→控制器）是同一个请求。
        """
        if index >= 0:
            (self.item_edit_requested if edit
             else self.item_double_clicked).emit(index)
        else:
            (self.spread_edit_requested if edit
             else self.spread_double_clicked).emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """双击：**图上 → 预览这张原图**；**两图之外的空白 → 预览左右组合**。

        ⚠️ 处理了就 ``accept``：Qt 对未接受的双击会**再补一个 mousePress**，
        那会走进 ``mousePressEvent`` 把编辑手势带起来（用户双击预览、松手时
        画布却以为刚拖动过一下）。
        """
        if event.button() != Qt.MouseButton.LeftButton or not self._items:
            return super().mouseDoubleClickEvent(event)
        index = self._item_at(event.position())
        if index >= 0:
            self.item_double_clicked.emit(index)
        else:
            self.spread_double_clicked.emit()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._items or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        # 按住期间才画框线/手柄（松手即消失，见模块 docstring）
        self._pressed = True
        # 选中项的手柄优先（它可能被另一张图压住）
        if self._selected >= 0:
            handle = self._hit_handle(self._selected, event.position())
            if handle is not None:
                self._begin_edit(handle, event)
                return
        index = self._item_at(event.position())
        if index >= 0:
            if index != self._selected:
                self._selected = index
                self.selection_changed.emit(self._selected)
                self.update()
            self._begin_edit(-1, event)
            return
        # 点在纸上空白处：取消选中
        if self._selected != -1:
            self._selected = -1
            self.selection_changed.emit(-1)
        self.update()
        return super().mousePressEvent(event)

    def _begin_edit(self, handle: int, event) -> None:
        """开始一次编辑手势（handle=-1 表示移动）。"""
        item = self._items[self._selected]
        self._grab_rect = list(item["rect"])
        self._grab_rotation = float(item.get("rotation") or 0.0)
        if handle == 8:
            self._mode = "rotate"
            center = self._rect_px(self._selected).center()
            mx, my = event.position().x(), event.position().y()
            self._grab_angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
        elif handle >= 0:
            self._mode = "resize"
            self._handle = handle
            self._grab_center = self._rect_px(self._selected).center()
        else:
            self._mode = "move"
            mx, my = self._to_units(event.position())
            self._grab_x = mx - item["rect"][0]
            self._grab_y = my - item["rect"][1]
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._dirty = False
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "move":
            item = self._items[self._selected]
            mx, my = self._to_units(event.position())
            item["rect"][0] = mx - self._grab_x
            item["rect"][1] = my - self._grab_y
            self._dirty = True
            self.update()
            return
        if self._mode == "resize":
            self._items[self._selected]["rect"] = self._resize_from_handle(
                event, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            )
            self._dirty = True
            self.update()
            return
        if self._mode == "rotate":
            item = self._items[self._selected]
            center = self._rect_px(self._selected).center()
            mx, my = event.position().x(), event.position().y()
            angle = math.degrees(
                math.atan2(mx - center.x(), center.y() - my)
            )
            item["rotation"] = (self._grab_rotation + angle - self._grab_angle) % 360.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                item["rotation"] = (
                    round(item["rotation"] / SNAP_DEGREES) * SNAP_DEGREES
                ) % 360.0
            self._dirty = True
            self.update()
            return
        # 悬停光标提示
        if self._items:
            index = self._selected if self._selected >= 0 else self._item_at(
                event.position()
            )
            if index >= 0:
                handle = self._hit_handle(index, event.position())
                if handle == 8:
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    return
                if handle is not None:
                    self.setCursor(_HANDLE_CURSORS[handle])
                    return
                if self._item_contains_px(index, event.position()):
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                    return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        return super().mouseMoveEvent(event)

    def _resize_from_handle(self, event, keep_ratio: bool) -> list[float]:
        """按当前手柄算出新框（合成像素）。

        - 四边手柄：只改受影响的那个维度（自由拉伸，能改比例）；
        - 四角手柄：默认自由拉伸；按住 Shift 以**对角为锚点**等比缩放
          （比例取自拖拽起点框，避免逐帧累积偏差）。

        ⚠️ 鼠标先反转该图的旋转角（绕**手势起点**的 rect 中心）再落到
        图坐标——手柄跟着框转了，光标也得换到局部系里读。
        """
        pos = event.position()
        c = self._grab_center
        angle = math.radians(
            float(self._items[self._selected].get("rotation") or 0.0)
        )
        cos_v, sin_v = math.cos(-angle), math.sin(-angle)
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        # 局部控件像素（原点 = 手势起点中心）→ 图坐标（单位 = 源图像素）
        local = QPointF(dx * cos_v - dy * sin_v, dx * sin_v + dy * cos_v)
        gx, gy = self._to_units(c)
        mx = gx + local.x() / self._px_per_unit
        my = gy + local.y() / self._px_per_unit
        gx, gy, gw, gh = self._grab_rect
        edge = _EDGE_BY_HANDLE.get(self._handle)
        if edge is not None:
            x, y, w, h = self._grab_rect
            if edge == "top":
                top = min(my, y + h - MIN_RECT)
                return [x, top, w, y + h - top]
            if edge == "bottom":
                bottom = max(my, y + MIN_RECT)
                return [x, y, w, bottom - y]
            if edge == "left":
                left = min(mx, x + w - MIN_RECT)
                return [left, y, x + w - left, h]
            right = max(mx, x + MIN_RECT)
            return [x, y, right - x, h]
        # ---- 四角 ----
        ax, ay = {
            0: (gx + gw, gy + gh), 1: (gx, gy + gh),
            2: (gx, gy), 3: (gx + gw, gy),
        }[self._handle]
        if not keep_ratio or gw <= 0 or gh <= 0:
            nx1, ny1 = min(ax, mx), min(ay, my)
            nx2, ny2 = max(ax, mx), max(ay, my)
            return [nx1, ny1, max(nx2 - nx1, MIN_RECT),
                    max(ny2 - ny1, MIN_RECT)]
        ratio = gh / gw
        scale = min(
            abs(mx - ax) / gw if gw else 0.0,
            abs(my - ay) / gh if gh else 0.0,
        )
        new_w = max(MIN_RECT, gw * scale)
        new_h = max(MIN_RECT, new_w * ratio)
        nx = ax - new_w if self._handle in (0, 3) else ax
        ny = ay - new_h if self._handle in (0, 1) else ay
        return [nx, ny, new_w, new_h]

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._mode is not None or self._pressed:
            self._mode = None
            self._pressed = False      # 松手 → 框线/手柄立即消失
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._dirty:
                self._emit_changed()
            else:
                self.update()
            return
        return super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """指针离开画布：按下状态收不到 release 时也别留着框线。"""
        if self._pressed:
            self._pressed = False
            self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ 滚轮缩放
    def wheelEvent(self, event) -> None:  # noqa: N802
        """滚轮缩放视图（以光标为锚点）；**重绘按帧合并**（减渲染的关键）。

        缩放本身只是 ``_zoom_at`` 里几个乘法——不解码、不重排、不碰图缓存。
        真正贵的是重绘：两张几千像素见方的原图 + 平滑采样。高分滚轮/触控板
        一秒能吐上百个 wheel 事件，若每个事件都 ``update()``，重绘就被拉到
        事件率。所以这里**不直接要重绘**：

        - 启动帧窗口定时器（``WHEEL_REPAINT_MS``），窗口内再来滚动只置
          ``_wheel_paint_pending``；
        - 窗口到期画一帧（``_on_wheel_frame``）；窗口内还有滚动就滚到下一帧，
          没有就关掉快速档、补一帧带平滑的高质量重绘收尾。

        连发期间 paintEvent 走**快速档**（不做 ``SmoothPixmapTransform``，
        大图缩放的重头开销在这）——反正下一滚就整帧重画，糊一帧没人看得出。
        """
        delta = event.angleDelta().y()
        if not self._items or delta == 0:
            return super().wheelEvent(event)
        event.accept()
        self._zoom_at(event.position(), WHEEL_ZOOM_STEP ** (delta / 120.0))
        self._wheel_burst = True
        if self._wheel_timer.isActive():
            self._wheel_paint_pending = True
        else:
            self._wheel_timer.start()

    def _zoom_at(self, pos: QPointF, factor: float) -> None:
        """以控件点 ``pos`` 为锚缩放 ``factor`` 倍（只改几何，不重绘）。

        锚点不动 = 光标指着的图上的点缩放前后还在光标底下。倍率钳在
        ``ZOOM_MIN``/``ZOOM_MAX``（相对适配基准），缩到头就不再动。
        """
        if not self._items or factor <= 0.0 or math.isclose(factor, 1.0):
            return
        new_zoom = min(ZOOM_MAX, max(ZOOM_MIN, self._zoom * factor))
        if math.isclose(new_zoom, self._zoom):
            return
        ratio = new_zoom / self._zoom
        self._zoom = new_zoom
        self._px_per_unit = self._fit_ppu * self._zoom
        self._off_x = pos.x() - (pos.x() - self._off_x) * ratio
        self._off_y = pos.y() - (pos.y() - self._off_y) * ratio

    def _on_wheel_frame(self) -> None:
        """帧窗口到期（定时器线程安全，主线程回调）：画一帧 + 收尾判定。"""
        self.update()
        if self._wheel_paint_pending:
            self._wheel_paint_pending = False
            self._wheel_timer.start()  # 窗口内还有滚动：并到下一帧
            return
        # 滚动停稳：关快速档，补一帧带平滑的高质量重绘
        self._wheel_burst = False
        self.update()

    # ------------------------------------------------------------------ 渲染
    def _image(self, path: str) -> QImage | None:
        """按路径懒加载 QImage（同一路径只解码一次）。"""
        if not path:
            return None
        cached = self._images.get(path)
        if cached is not None:
            return cached
        image = QImage(path)
        if image.isNull():
            return None
        self._images[path] = image
        return image

    def _image_size(self, path: str) -> tuple[int, int] | None:
        image = self._image(path)
        if image is None:
            return None
        return image.width(), image.height()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        # 滚轮连发期间走快速档（不做平滑采样，大图缩放的重头开销在这）；
        # 停稳后由 _on_wheel_frame 关掉快速档并补一帧高质量重绘
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, not self._wheel_burst
        )
        # 纯白底（用户口径：拼版不需要纸张，白底就行）——没有纸张矩形要画，
        # 控件自身的样式表已经是白的。
        for index, item in enumerate(self._items):
            self._draw_item(painter, index, item)
        # 红色对齐线（用户 2026-09-30）：两图公共中心所在竖线，**恒显**——
        # 不管有没有选中、有没有在拖动，它都在；整版旋转时拿它当对比基准。
        # ⚠️ 单图页只认横图（源图宽>高；2026-09-30 晚用户定：单张半页图
        # ——包括无 -l/-r 后缀的竖图——不画红线；单张整幅对开仍要），
        # 见 _spine_visible。
        if self._items:
            if self._spine_visible():
                center_x, _ = self._spread_center_units()
                x = self._off_x + center_x * self._px_per_unit
                # 宽度 1.0（用户 2026-09-30：1.5 的红线渲染出来约 2px，嫌太宽）
                painter.setPen(QPen(SPINE_COLOR, 1.0, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(
                    QPointF(x, 0.0), QPointF(x, float(self.height()))
                )
            # 成品截图范围框（用户 2026-09-30）：两图外接框并集的灰虚线，
            # **恒显**——产出图就是这块范围的紧裁，旋转/挪动时它跟着变。
            self._draw_crop_frame(painter)
        # 框线分两态（用户 2026-09-30）：按住操作期间画**带手柄的完整框**；
        # 平时选中的那张图带**常显细虚线**（选中状态）。没选中的图永远干净。
        if self.frame_visible():
            self._draw_frame(painter, self._selected)
        elif 0 <= self._selected < len(self._items):
            self._draw_selected_border(painter, self._selected)
        painter.end()

    def _draw_crop_frame(self, painter: QPainter) -> None:
        """画**成品截图范围**虚线框：两图旋转后外接框的并集。

        「上下左右四个方向最外面点组成的框」（用户 2026-09-30 口径）——
        ``_item_box_units`` 与 ``services.imposition.page_bounds`` 是同一套
        几何：画布上这个框里有什么，产出图就是什么。
        """
        boxes = [self._item_box_units(item) for item in self._items]
        left = min(b[0] for b in boxes)
        top = min(b[1] for b in boxes)
        right = max(b[2] for b in boxes)
        bottom = max(b[3] for b in boxes)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(CROP_COLOR, 1.2, FRAME_STYLE, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawRect(QRectF(
            self._off_x + left * self._px_per_unit,
            self._off_y + top * self._px_per_unit,
            (right - left) * self._px_per_unit,
            (bottom - top) * self._px_per_unit,
        ))

    def _draw_item(self, painter: QPainter, index: int, item: dict) -> None:
        """画一张图：**只画图像，不画任何框线**（框线归 _draw_frame）。

        ⚠️ **不做裁剪**（用户 2026-09-30：「图片拉伸、移动后可能超出原本界限，
        现在是不显示了，现在不要限制」）：图可以拖/拉到任何位置，越界的部分也
        必须画出来。真正落到控件可视区之外的部分由 Qt 自己丢弃，那与"我们主动
        裁掉"是两回事。
        """
        r = self._rect_px(index)
        if r.width() <= 0 or r.height() <= 0:
            return
        painter.save()
        center = r.center()
        painter.translate(center)
        painter.rotate(float(item.get("rotation") or 0.0))
        image = self._image(item["file"])
        box = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        if image is not None and not image.isNull():
            painter.drawImage(box, image)
        else:
            painter.fillRect(box, QColor("#f0f2f5"))
        painter.restore()

    def _draw_frame(self, painter: QPainter, index: int) -> None:
        """按住期间画的选中框：**虚线**矩形 + 四角四边手柄 + 旋转钮。

        ⚠️ 框与手柄**跟着图一起转**（用户 2026-09-30：选中高亮虚线不随旋转
        是 bug）：在"平移到 rect 中心 + 旋转 rotation"的坐标系里画，与
        ``_draw_item`` 的图像变换同一套。命中判定（``_hit_handle``）已在
        局部系里做，手柄画在哪就能在哪抓到。
        """
        r = self._rect_px(index)
        painter.save()
        painter.translate(r.center())
        painter.rotate(float(self._items[index].get("rotation") or 0.0))
        local = QRectF(
            -r.width() / 2.0, -r.height() / 2.0, r.width(), r.height()
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(FRAME_COLOR, 1.6, FRAME_STYLE, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawRect(local)
        painter.setPen(QPen(HANDLE_STROKE, 1.5))
        painter.setBrush(HANDLE_FILL)
        for cx, cy in self._handle_positions_local(index):
            painter.drawRect(
                QRectF(cx - HANDLE_RADIUS, cy - HANDLE_RADIUS,
                       2 * HANDLE_RADIUS, 2 * HANDLE_RADIUS)
            )
        # 旋转钮：一条引线 + 一个圆钮
        knob = self._rotate_knob_local(index)
        painter.setPen(QPen(HANDLE_STROKE, 1.5))
        painter.drawLine(QPointF(0.0, -r.height() / 2.0), knob)
        painter.setBrush(HANDLE_FILL)
        painter.drawEllipse(knob, ROTATE_KNOB_RADIUS, ROTATE_KNOB_RADIUS)
        painter.restore()

    def _draw_selected_border(self, painter: QPainter, index: int) -> None:
        """选中态**常显**的细虚线框（用户 2026-09-30：点击某张图后它要有
        "选中状态"）：只描边、无手柄——手柄全框只在按住操作期间出现。

        ⚠️ 跟着图一起转（用户 2026-09-30：旋转后高亮框要贴着图像的边）。
        """
        r = self._rect_px(index)
        painter.save()
        painter.translate(r.center())
        painter.rotate(float(self._items[index].get("rotation") or 0.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(FRAME_COLOR, 1.2, FRAME_STYLE, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.drawRect(QRectF(
            -r.width() / 2.0, -r.height() / 2.0, r.width(), r.height()
        ))
        painter.restore()
