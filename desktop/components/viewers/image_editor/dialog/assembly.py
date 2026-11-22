# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``ImageEditorDialog``：**装配点 + 基座 + 收尾**（子包）。"""
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

from .constants import EDITOR_MIN_SIZE, EDITOR_SIZE
from ..dialog_commit import CommitMixin
from ..dialog_pages import ToolPagesMixin
from ..dialog_toolbar import ToolbarMixin
from ..dialog_undo import UndoMixin
from .finish import FinishMixin
from .layers import LayersMixin
from .layer_switch import LayerSwitchMixin


class ImageEditorDialog(
    ToolbarMixin,
    ToolPagesMixin,
    UndoMixin,
    CommitMixin,
    LayersMixin,
    LayerSwitchMixin,
    FinishMixin,
    QDialog,
):
    """图片编辑器弹窗：顶部功能条 + 中间画布 + 右侧参数面板 + 底部状态栏。"""

    #: 「完成」的**后台应用**成功（2026-10-10）：底片已原子覆盖、sidecar 已
    #: 写，参数 ``(底片路径, 最终图)``。宿主在 ``exec()`` 返回后发现
    #: :meth:`apply_in_progress` 为真时改接本信号做刷新链（不再自己写盘）。
    apply_completed = Signal(str, QImage)
    #: 后台应用失败/被取消：参数 ``(底片路径, 原因)``，底片原样未动
    #: （原子写保证：要么完整旧图、要么完整新图）。宿主据此报错即可。
    apply_failed = Signal(str, str)
    multi_image_saved = Signal(str, QImage)
    multi_layout_saved = Signal(object)


    def __init__(self, parent=None, image: QImage | None = None,
                 save_back: bool = False):
        super().__init__(parent)
        # 本页有真实文件可回写（宿主预览弹窗传入）：「完成」= 直接覆盖原图
        # 文件，而不是"回画布再自己下载"。只影响文案与覆盖确认，行为在弹窗侧。
        self._save_back = bool(save_back)
        self._multi_layers: list[dict] = []
        self._active_layer = -1
        self._pending_crop_offset = (0.0, 0.0)
        #: 双图编辑下与 ``_undo``/``_redo`` **平行**的"内容原点"栈（见
        #: :meth:`_multi_layer_shift`）：每步撤销点带上当时的 origin，撤销/
        #: 重做才能把两张图的相对位置一起退回去。
        self._undo_origins: list[tuple[float, float]] = []
        self._redo_origins: list[tuple[float, float]] = []
        #: 「完成」覆盖确认里显示的**目标文件名**（宿主在构造后回填，见
        #: :meth:`_confirm_overwrite`）。刻意做成**属性而不是构造参数**：
        #: 六个宿主各自算路径的位置不同，而 ``__init__`` 的签名被自测的
        #: 替身编辑器（``_StubEditor(parent, image, save_back)``）硬编码着，
        #: 多一个关键字参数就会让那些替身全部 TypeError。
        self.target_name = ""
        #: 目标文件**是否已经存在**。默认 True（绝大多数场景：改的就是
        #: 现存原图）。少数"保存到尚不存在的文件"（整页组合第一次编辑，
        #: 目标是缓存区里新建的 ``edited/NNNN.png``）由宿主改成 False，
        #: 于是不弹覆盖确认——没有旧内容可丢，问了是假警报。
        self.target_exists = True
        #: 编辑源文件路径（宿主构造后回填）：内容节点 sidecar
        #: ``<file>.quad.json`` 的读写依据。刻意走**属性**而不是构造参数——
        #: 自测的替身编辑器按死签名构造，多一个关键字参数全体 TypeError。
        self.source_path = ""
        self.setWindowTitle("图片编辑")
        self.setModal(True)
        # 编辑要看得清字迹：默认开大，并带最小化/最大化按钮（标题栏双击
        # 最大化也随 maximize 按钮生效），用户 20:18 定
        # ✳️ 但默认尺寸与最小尺寸都要先夹进屏幕可用区域：1440×940 / 1040×680
        # 在 1920×1080 @125%（逻辑可用 1536×824）下都会被任务栏吃掉一截，
        # 高缩放的笔记本上最小尺寸甚至比可用区域还大、用户连拖小都做不到。
        apply_window_size(self, EDITOR_SIZE, EDITOR_MIN_SIZE)
        # ⚠️ 显式设置窗口旗标时必须把 CloseButtonHint 一并给上：只给
        #    min/max 不给 close，Windows 标题栏的关闭按钮会失效（用户报障
        #    "编辑弹窗关闭按钮不生效"，2026-10-01）。
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        # 编辑窗是主窗口的"子窗口"（owned）：默认没有任务栏按钮（用户
        # 2026-11-18：要在任务栏看到多个窗口）。补 WS_EX_APPWINDOW。
        # ⚠️ 必须在 setWindowFlags 之后（那会重建原生窗口、丢样式位）。
        from desktop.ui.native_minimize import enable_taskbar_button

        enable_taskbar_button(self)
        base = image if image is not None else QImage()
        # 统一转 ARGB32：rembg 产物可能是调色板 PNG，就地绘制需要真彩格式
        base = base.convertToFormat(QImage.Format.Format_ARGB32)
        # ⚠️ 入口**内容提取**（用户 2026-10-10 口径："编辑 PA1 版本图片时，
        #    画布内部图片是 PANew 而不是 PA1"）：透明图四边若有纯空白
        #    （旋转扩版的遗留边，旧版文件会越滚越大），装图即裁到非透明
        #    像素的真实外框——**编辑主体永远是内容本身**，滚大过的旧文件
        #    一次重开就回到内容尺寸。不透明图不动（白边可能是"纸"的内容）。
        #    ⚠️ 有内容节点 sidecar 时这里的偏移要记下来：sidecar 里的矩阵
        #    以未收紧文件为基准，反变换回 upright 时要把偏移补回去。
        _entry_trim = _trim_transparent_edges(base)
        self._content_trim_offset = (0, 0)
        # ⚠️ **收紧前**的文件尺寸（用户 2026-10-15 报障「如果图片初始被向内
        #    裁掉一部分，可以向外扩到原始大小」）。它当裁剪框/平移的固定上界
        #    （``canvas.set_source_extent``）；收紧过就比 ``base`` 大，
        #    用户能把框拖回原始大小，没收紧就等于当前图大小。
        source_w, source_h = base.width(), base.height()
        if _entry_trim is not None and _entry_trim[1:] != (0, 0):
            base = _entry_trim[0]
            self._content_trim_offset = (_entry_trim[1], _entry_trim[2])
        self._source_extent = (source_w, source_h)
        self._original = base
        self._image = self._original.copy()
        # ---- 内容四角节点（统一变换 sidecar，2026-10-10） ----
        #: ``(rect0, V)``：upright 内容矩形 + upright→呈现 的**纯**矩阵。
        #: 宿主回填 :attr:`source_path` 后，首次进入变换工具时从
        #: ``<file>.quad.json`` 读回（见 dialog_commit._on_content_restore_requested）。
        self._content_state = None
        self._content_read = False
        #: 恢复会话中：``_image`` **保持文件原样**（PB1 画布，2026-10-10
        #: 口径），upright 只是浮层源与烘焙源（``_content_upright``），
        #: ``_content_seed`` 是挂回变换工具的画布系种子矩阵。
        self._content_restored = False
        self._content_seed = None
        self._content_upright = None
        #: upright 缓存是否失效（2026-10-11）：只有**真改像素**的操作
        #: （擦除/文字/扭曲）置 True；旋转/空裁剪不改像素 ⇒ 缓存复用，
        #: 切走再切回零重算、烘焙单代次（否则每轮多一代重采样＝PA1
        #: 边缘元素逐轮流失 + 每次切换秒级卡顿）。
        self._content_pixels_dirty = False
        #: 延迟恢复（2026-10-10「切换卡顿」）：进变换工具只挂矩阵/框，
        #: upright 反变换的参数与目标像素量存在这儿，第一次拖动时由
        #: ``_on_restore_pixels_requested`` 用掉（用完清 None）。
        self._content_restore_params: dict | None = None
        self._content_restore_target = 0.0
        #: **待定裁剪**（``QRectF`` 或 ``None``）：裁剪工具里松手定下的选区，
        #: 像素**还没动**。裁剪是非破坏性的——不落定就能继续向外拖，把变暗
        #: 的老区域拉回来；切走裁剪工具 / 点「完成」时才由
        #: ``_commit_crop`` 真正 ``copy()``（一步一个撤销点）。
        self._pending_crop: QRectF | None = None
        # 撤销栈 + **步骤名**。三者的对齐关系写在 ``dialog_undo.py`` 的开头：
        # ``_labels[i]`` 是"把 ``_undo[i]`` 这个状态改掉的那一步"的名字，
        # 长度恒等于 ``len(_undo) + len(_redo)``。
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self._labels: list[str] = []
        #: 时间轴第 0 格的名字（栈被截断后它换成被丢掉那一步的名字）
        self._origin_label: str = HISTORY_ORIGIN_LABEL
        #: 程序化刷新历史列表时的闸门（挡住 ``currentRowChanged`` 回灌）
        self._history_syncing = False
        self._option_page: QWidget | None = None
        # 文字工具参数的活性引用（插入时现读，见 _commit_text_blocks）
        self._text_size: int = TEXT_DEFAULT
        self._text_color: str = TEXT_COLOR_DEFAULT
        self._text_family: str = T.FONT_FAMILY
        self._erase_size: int = ERASER_DEFAULT
        #: 「完成」整体处理中（防**双击重入**：确认框的 ``exec()`` 自带
        #: 事件循环，会派发排队的第二次点击）
        self._finishing = False

        self.canvas = EditorCanvas(self)
        self.canvas.set_image(self._image)
        # 原文件基准（裁剪框的固定上界）。⚠️ 必须**在** set_image **之后**
        # 登记——set_image 会把基准重置成新图自己（见 core.py）。这里传的是
        # **相对收紧后图片**的矩形：收紧掉 (dx,dy) 透明边 ⇒ 原文件比图大
        # 出去左上一块 ⇒ 记 (-dx,-dy, 源宽, 源高)，用户就能把框拖回原始大小。
        _trim_dx, _trim_dy = self._content_trim_offset
        self.canvas.set_source_extent(QRectF(
            -_trim_dx, -_trim_dy,
            float(self._source_extent[0]), float(self._source_extent[1])))
        self.canvas.context_image_clicked.connect(self._switch_context_layer)
        # 一笔开始（擦除按下 / 扭曲提交前）⇒ 压撤销点，步骤名按当前功能取
        self.canvas.stroke_started.connect(self._on_stroke_started)
        # 进入变换工具 ⇒ 尝试从 sidecar 恢复"内容四角节点"（二次编辑）
        self.canvas.content_restore_requested.connect(
            self._on_content_restore_requested)
        # 恢复会话第一次需要像素（第一次拖动）⇒ 此刻才算 upright 反变换
        # （进工具零等待，2026-10-10「切换卡顿」）
        self.canvas.restore_pixels_requested.connect(
            self._on_restore_pixels_requested)
        self.canvas.text_requested.connect(self._spawn_text_block)
        # 裁剪**松手不落定**（选区可来回推拉），变换同理先在画布浮层预览
        self.canvas.crop_selection_changed.connect(self._preview_crop)
        self.canvas.transform_committed.connect(self._commit_transform)

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_MD, T.SPACE_MD, T.SPACE_MD, T.SPACE_MD)
        root.setSpacing(T.SPACE_SM)
        # ⚠️ 右侧面板必须先建：``_build_toolbar_row`` 末尾的 ``_set_tool``
        #    就会往面板的参数区里插第一份参数页。
        side_panel = self._build_side_panel()
        root.addLayout(self._build_toolbar_row())
        body = QHBoxLayout()
        body.setSpacing(T.SPACE_MD)
        body.addWidget(self.canvas, 1)
        body.addWidget(side_panel)
        root.addLayout(body, 1)
        root.addWidget(self._build_status())
        # 历史列表/尺寸提示要等面板与状态栏都在了才刷得动
        self._sync_history()

        for seq, slot in (
            (QKeySequence("Ctrl+Z"), self._undo_now),
            (QKeySequence("Ctrl+Y"), self._redo_now),
            (QKeySequence(Qt.Key.Key_Escape), self._escape),
        ):
            QShortcut(seq, self).activated.connect(slot)


    def _escape(self) -> None:
        """Esc：先结束文字编辑，然后才关窗。

        ⚠️ 关窗 = 放弃本次全部编辑（状态行里写着），正在打字时一个 Esc
        把整轮编辑清掉太伤人——所以文字编辑态优先吃掉这个键。
        """
        block = self.canvas.focused_text_block()
        if block is not None:
            block.clearFocus()
            return
        self.reject()
