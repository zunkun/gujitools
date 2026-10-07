# -*- coding: utf-8 -*-
"""框编辑画布 ``ImageView``：**装配点 + 基座**。

从 ``image_view.py`` 拆出（2026-10-07）。本文件放类头（信号/类属性）、
``__init__``、装图/取图、选中与框数据访问；绘制在 ``render``，编辑交互在
``edit``（Mixin）。方法体逐字未改。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel
from desktop.ui import theme as T
from utils.box_geometry import half_sides

from .edit import EditMixin
from .render import RenderMixin


class ImageView(
    RenderMixin,
    EditMixin,
    QLabel,
):
    """大图查看：随控件尺寸实时缩放，支持在图片坐标系叠加切割框。"""

    boxes_edited = Signal(list)  # 移动/缩放/删除/新增后：全部框（图片像素坐标）
    #: 双击大图（宿主据此打开图片预览弹窗；只读查看，不改任何数据）
    double_clicked = Signal()
    #: 右键大图（宿主据此弹出「预览图片 / 编辑图片」菜单）。有图才发。
    context_menu_requested = Signal()
    #: 选中框变化：新下标，无选中为 -1（宿主据此同步「选中框类型」控件与删除按钮）
    selection_changed = Signal(int)
    #: 本次编辑被拒绝（含原因文案）：超框数上限等，宿主弹出提示
    edit_rejected = Signal(str)

    #: 预览渲染最长边的**下限**：控件尚未布局（尺寸还是 0）时的兜底，也避免
    #: 小控件把预览渲染得过小——之后窗口一最大化就只能放大、糊掉。
    MIN_PREVIEW_EDGE = 1200
    #: 预览渲染最长边的**上限**：超大窗口 × 高分屏下别为一页预览分配几十 MB。
    #: 3000px 竖页约 37 MB（RGB32），是渲染耗时与内存的折中。
    MAX_PREVIEW_EDGE = 3000

    def __init__(self, placeholder: str = "无预览", parent=None):
        """初始化画布与框编辑状态；placeholder 为空图时的占位文案。"""
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        #: 本页是否**整幅**(fullcontent)：整幅页的框是显式类型（恒为「整幅」，
        #: 不按位置判左右），且只允许一个框；否则是半幅页（按中心定左右、最多两个）。
        self._full_mode = False
        self._reference_boxes: list = []  # 参考框（最终裁剪大框），虚线显示
        self._image_size: QSize | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        #: 源图版本号：每次 set_image 递增。缓存键用它而不是 id()——旧 pixmap
        #: 被回收后新对象可能拿到同一个 id，键就撞了。
        self._pixmap_version = 0
        #: SmoothTransformation 的缓存底图（不带叠加层）+ 缓存键。⇒ 拖框逐帧
        #: 只做「拷贝 + 画叠加层」（毫秒级），不再对 3000px 源图整张重采样
        #: （37MB/帧，实测拖框明显掉帧——见审计 D3）。
        self._scaled_base: QPixmap | None = None
        self._scaled_key: tuple | None = None


    @property
    def has_image(self) -> bool:
        """当前是否已装入图片。"""
        return self._pixmap is not None


    @property
    def full_mode(self) -> bool:
        """本页是否为整幅(fullcontent)——整幅页只有「整幅」一种框类型。"""
        return self._full_mode


    @property
    def max_boxes(self) -> int:
        """本页允许的框数上限：整幅 1 个；半幅左右各一，共 2 个。"""
        return 1 if self._full_mode else 2


    def selected_index(self) -> int:
        """当前选中的框下标；无选中为 -1。"""
        return -1 if self._selected is None else self._selected


    def _select(self, index: int | None) -> None:
        """更新选中框并在**真的变化时**发 ``selection_changed``（-1 = 无选中）。"""
        if index == self._selected:
            return
        self._selected = index
        self.selection_changed.emit(self.selected_index())


    def select_box(self, index: int) -> None:
        """程序化选中第 index 个框（-1 = 取消选中）并重绘。"""
        self._select(None if index is None or index < 0 else int(index))
        self._rerender()


    def box_kinds(self) -> list:
        """当前每个框的类型：``"left"`` / ``"right"`` / ``"full"``。

        与 :meth:`_draw_boxes` 用的是**同一份规则**（整幅页恒为 full；半幅页按
        中心位置判左右），所以面板高亮与实际画出的标签永远一致。
        """
        if self._full_mode:
            return ["full"] * len(self._boxes)
        size = (
            (self._image_size.width(), self._image_size.height())
            if self._image_size else None
        )
        return half_sides(self._boxes, size)


    def set_boxes_editable(self, editable: bool) -> None:
        """开关框编辑；开启时接受点击焦点以响应键盘删除。"""
        self._boxes_editable = editable
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus if editable else Qt.FocusPolicy.NoFocus)


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
        self._pixmap_version += 1  # 缓存底图作废（见 _scaled_base）
        # 换页即回到「半幅、无选中」；整幅页由随后的 set_boxes(full=True) 标明
        self._full_mode = False
        self._select(None)
        self._mode = None
        self._drag_index = None
        self._ghost_box = None
        self._rerender()


    def set_boxes(self, boxes: list, image_size: QSize, full: bool = False,
                  selected: int | None = None) -> None:
        """仅更新切割框、形态与图片原始尺寸并重绘（不换图）。

        boxes 为图片像素坐标；image_size 为坐标映射基准，与显示缩放无关。
        ``full=True`` 表示本页是整幅(fullcontent)：框显示为「整幅」且**只允许
        一个**；否则是半幅页，框按中心位置显示为左/右，最多两个。
        ``selected`` 非负时把选中态落到该下标（宿主切换框类型后保持选中）。

        ⚠️ 名称/颜色不在这里传：它们由 `box_styles` 按**中心位置**每帧现算，
        这样拖动框跨过中线时名字与颜色会立刻跟着换（用户 2026-09-29 要求）。
        """
        self._boxes = [list(box) for box in boxes]
        self._full_mode = bool(full)
        self._image_size = image_size
        self._select(None)
        if selected is not None and 0 <= selected < len(self._boxes):
            self._select(int(selected))
        self._mode = None
        self._rerender()


    def clear_image(self, text: str = "无预览") -> None:
        """清空图片与全部框（含参考框），显示占位文案。"""
        self._pixmap = None
        self._boxes = []
        self._full_mode = False
        self._reference_boxes = []
        self._select(None)
        self._mode = None
        self._drag_index = None
        self.setText(text)


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


    # ------------------------------------------------------------------ 渲染
    def _update_mapping(self, scaled: QPixmap) -> None:
        """按当前显示尺寸刷新坐标映射（必须在绘制之前调用）。

        缩放比以 _image_size（图片原始尺寸）为基准：显示的 pixmap 可能是
        预览加载时降采样过的版本，框坐标始终是原始像素坐标。

        ⚠️ ``scaled`` 带 devicePixelRatio，其 ``width()`` 报的是**物理**像素，
        必须换算回逻辑尺寸再算映射与居中偏移——把物理尺寸当逻辑尺寸用，
        在高分屏下恰好差一个 dpr，框会整体放大并偏移。
        """
        pix = self._pixmap
        assert pix is not None  # _rerender 已挡住 _pixmap 为空的情况
        ref_w = self._image_size.width() if self._image_size else pix.width()
        ref_h = self._image_size.height() if self._image_size else pix.height()
        dpr = scaled.devicePixelRatio() or 1.0
        disp_w = scaled.width() / dpr
        disp_h = scaled.height() / dpr
        self._scale_x = disp_w / ref_w if ref_w else 1.0
        self._scale_y = disp_h / ref_h if ref_h else 1.0
        # setPixmap 后 QLabel 按 AlignCenter 居中显示
        self._offset_x = max(0.0, (self.width() - disp_w) / 2)
        self._offset_y = max(0.0, (self.height() - disp_h) / 2)
