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
  **跟着图一起转**——用户 2026-09-30 报过"旋转后高亮框不跟着转"），
  框外上方同时挂一个**常显的旋转圆钮**（用户 2026-10-23）；
  **按住鼠标操作期间**才在细框上补出手柄的完整虚线框，**一松手回到
  细框**（2026-09-30：选中态要一直看得见，右侧旋转控件跟着切到这张图）；
- **选中的图永远画在最上面**（用户 2026-10-10：类似 CSS 里 ``z-index``
  更大）——两图重叠时，被压住的那张一旦选中就得浮上来，否则看不清在
  操作哪张；命中判定（``_item_at``）同样优先命中选中图；
- **切页 / 点空白处 → 取消选中**（右侧图片操作区随之灰掉）；
- **双击某张图 → 编辑整页组合**；**双击两图之外的空白处 → 预览左右组合**
  （整页按产出口径合成的效果，``emit`` 给控制器开预览弹窗，画布自己不管弹窗）；
- **滚轮 → 缩放视图**（以光标为锚点，松开即停在当前倍率）：缩放只改
  ``_px_per_unit`` 与偏移两个数，不解码、不重排；重绘**不在滚轮事件里直接
  要**——滚轮/触控板连发时一秒能来上百个事件，直接要就是把大图重绘拉到
  事件率。渲染合并策略见 ``wheelEvent`` / ``_on_wheel_frame``：滚动期间每
  帧最多重绘一次、走**快速档**（不做平滑采样），停稳后补一帧高质量重绘；
- 未按下时靠**光标**提示可抓的位置：图内 `OpenHand`、四角/四边缩放光标、
  框外上方圆钮处 `Cross`；
- 点某张图 → 选中；框内拖动 → 整体移动；**四角**手柄 → 缩放（按住 Shift
  等比）；**四条边整条都是命中带** → 只改一个维度；**框外上方的小圆钮** →
  旋转（选中后常显，**在图片外面**用左键拖动；按住 Shift 吸附到 15°）；
  松手 emit ``items_changed``（拖动过程中只重绘）；
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

本文件只放**主类骨架**（信号 / 构造 / 对外 API / 编辑入口）；坐标换算见
:mod:`.geometry`、渲染见 :mod:`.paint`、鼠标与滚轮见 :mod:`.interaction`。
"""

from __future__ import annotations

import math
from typing import Callable

from desktop.components.imposition.canvas._qt import (
    QImage,
    QPointF,
    QTimer,
    QWidget,
    Signal,
)
from desktop.components.imposition.canvas.constants import (
    PAGE_COLOR,
    ROTATE_KNOB_GAP,
    ROTATE_KNOB_RADIUS,
    WHEEL_REPAINT_MS,
)
from desktop.components.imposition.canvas.geometry import _GeometryMixin
from desktop.components.imposition.canvas.interaction import _InteractionMixin
from desktop.components.imposition.canvas.paint import _PaintMixin
from desktop.ui import theme as T


class ImpositionCanvas(_PaintMixin, _InteractionMixin, _GeometryMixin, QWidget):
    """拼版画布：白底上拖动/缩放/旋转两张图；``items_changed`` 发出图坐标。"""

    #: 版面变化（松手时发一次；切页/离开页面前由 flush_pending 补发）
    items_changed = Signal(list)
    #: 当前选中的图（0 右槽 / 1 左槽 / -1 未选中）
    selection_changed = Signal(int)
    #: **右键菜单「预览图片」**（0 右槽 / 1 左槽）：预览这张原图
    item_preview_requested = Signal(int)
    #: **双击了图片之外的空白处**：请求预览整页左右组合
    spread_double_clicked = Signal()
    #: **右键菜单在图片上选了「编辑图片」**（0 右槽 / 1 左槽）：编辑整页组合
    item_edit_requested = Signal(int)
    #: **右键菜单在空白处选了「编辑图片」**：编辑整页组合
    spread_edit_requested = Signal()
    #: **「定位图片资源」没定位成**（文件已不存在等）：一行人读说明，由宿主提示
    locate_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self._items: list[dict] = []
        self._images: dict[str, QImage] = {}
        #: 贴图底图缓存：``(路径, 档位边长) -> 已降采样的 QImage``。与
        #: ``_images`` 同生命周期（换页/清空/失效时一并丢弃）。
        self._display_cache: dict[tuple[str, int], QImage] = {}
        self._selected = -1
        #: 右键「定位图片资源」的目标解析（宿主给出）：``(index) -> list[Path]``，
        #: 按优先级。⚠️ 拼版这一步的"图片资源"是**拼版成品**（``stages/imposition``
        #: ——实时重合成产出新图），不是输入源图（用户 2026-10-18）。不设时定位的
        #: 就是画布上那张源图（旧口径）。
        self._locate_resolver: Callable[[int], list] | None = None
        self._pad = 18
        #: 顶部额外留白：选中图的旋转钮挂在**框外上方**（``ROTATE_KNOB_GAP`` +
        #: 半径），适配可视区时必须把这块让出来——否则打开一页就看全时，
        #: 钮被顶到控件外面，用户根本抓不到（用户 2026-10-23 的「图片外面旋转」）
        self._pad_top = ROTATE_KNOB_GAP + ROTATE_KNOB_RADIUS + 10
        self._px_per_unit = 1.0
        self._off_x = float(self._pad)
        self._off_y = float(self._pad_top)
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
        self._display_cache = {}
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
        self._display_cache = {}
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

    def frame_visible(self) -> bool:
        """当前是否画**带手柄的完整操作框**（= 鼠标按住期间）。

        平时选中的图另有常显细框（``_draw_selected_border``，含框外那个
        常显的旋转钮），不算在内。
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
