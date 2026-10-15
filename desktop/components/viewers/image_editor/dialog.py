# -*- coding: utf-8 -*-
"""``ImageEditorDialog``：**装配点 + 基座 + 收尾**。

从 894 行的单类拆出（2026-10-07）。本文件放模块级常量、类头（类属性）、
``__init__``、快捷键、覆盖确认与「完成」收尾；顶部功能条/右侧参数面板、
各功能参数页、撤销与步骤历史、工具提交分别在兄弟模块的 Mixin 里。

MRO 顺序：功能条/参数页在前（``__init__`` 里就要用），提交与历史在后。

版式（2026-10-08 重排）：**顶部功能选择 + 中间画布 + 右侧参数面板 + 底部状态**，
另有右侧面板里的「编辑历史」步骤列表。编辑**实时生效**——文字块本身就是预览、
切功能或「完成」时自动写入，变换拖动中由画布浮层实时显示，因此没有「应用裁剪」
「应用变换」「插入文字」三个确认按钮。

⚠️ **裁剪是非破坏性的**（用户 2026-10-10：「裁剪线可以向内移动也可以向外移动，
向外移动，原本被隐藏的区域要显示出来」）：裁剪框松手只**记下选区**，不切像素，
画布画的始终是原图 + 选区外的半透明遮罩 ⇒ 裁剪线在整段编辑里都能来回推拉。
落定时机 = **切走裁剪工具**或点**「完成」**（各调一次 ``_commit_crop``，一步一个
撤销点）；Ctrl+Z / Ctrl+Y / 「还原」遇到待定裁剪先把它退掉（像素没动过，不记步）。

⚠️ 「完成」仍然要求一次覆盖确认（``_confirm_overwrite``）：这一步不是"单步
变更确认"，而是"要不要覆盖磁盘上的原图"，原图被覆盖后不可逆，用户
2026-10-04 明确要求必须问。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut, QTransform
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget,
)
from desktop.ui import theme as T
from desktop.ui.window_size import apply_window_size
from .canvas import EditorCanvas
from .geometry import _trim_transparent_edges, _transparent_content_bounds
from .consts import (
    ERASER_DEFAULT, HISTORY_ORIGIN_LABEL, TEXT_COLOR_DEFAULT, TEXT_DEFAULT,
)


# ------------------------------------------------------------------ 弹窗
#: 图片编辑弹窗的**期望**尺寸与最小尺寸（逻辑像素）。落地前一律经
#: ``apply_window_size`` 夹进屏幕可用区域，所以这两个值是"上限"而不是承诺
#: （1920×1080 @125% 的机器上可用高只有 824，940 会被任务栏吃掉一截）。
#: 自测按这两个常量算期望值，别再在测试里写死 1440×940。
EDITOR_SIZE = QSize(1440, 940)


EDITOR_MIN_SIZE = QSize(1040, 680)




from .dialog_commit import CommitMixin
from .dialog_pages import ToolPagesMixin
from .dialog_toolbar import ToolbarMixin
from .dialog_undo import UndoMixin


class ImageEditorDialog(
    ToolbarMixin,
    ToolPagesMixin,
    UndoMixin,
    CommitMixin,
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
        if _entry_trim is not None and _entry_trim[1:] != (0, 0):
            base = _entry_trim[0]
            self._content_trim_offset = (_entry_trim[1], _entry_trim[2])
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
                "scale": (
                    rect.width() / max(1, image.width()),
                    rect.height() / max(1, image.height()),
                ),
                # ---- 内容原点（2026-10-13「两张图片相互远离」）----
                #: 当前 ``_image`` 左上角在**初始图像素系**里的位置：
                #: 初值＝入口收紧偏移（透明图裁掉空白边后内容从这儿开始），
                #: 之后每次真裁剪/变换烘焙按新画布左上角累加（见
                #: :meth:`_multi_layer_shift`）。双图相对摆放全靠它换算，
                #: 不追踪的话一边裁剪/旋转，另一边就"漂走"。
                #: ``origin0``＝「还原」时的初值。
                "origin": (float(trim_offset[0]), float(trim_offset[1])),
                "origin0": (float(trim_offset[0]), float(trim_offset[1])),
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

    # ---- 激活图层：右侧面板显示 + 切换（2026-10-13 用户口径） ----
    def _build_layer_switcher(self) -> None:
        """按当前图层标签在右侧面板顶部铺一排切换按钮（双图才显示）。"""
        row = getattr(self, "_layer_row", None)
        if row is None:
            return
        layout = row.layout()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._layer_buttons = []
        if len(self._multi_layers) < 2:
            row.setVisible(False)
            return
        from qfluentwidgets import ToggleButton

        for index, layer in enumerate(self._multi_layers):
            button = ToggleButton(layer["label"] or f"图层{index + 1}", row)
            button.clicked.connect(
                lambda _checked=False, i=index: self._activate_layer(i))
            layout.addWidget(button)
            self._layer_buttons.append(button)
        row.setVisible(True)
        self._sync_layer_switcher()

    def _sync_layer_switcher(self) -> None:
        """按钮选中态跟随活动层（程序化刷新，挡住回灌）。"""
        self._layer_buttons_syncing = True
        try:
            for index, button in enumerate(self._layer_buttons):
                button.setChecked(index == self._active_layer)
        finally:
            self._layer_buttons_syncing = False

    def _activate_layer(self, index: int) -> None:
        """右侧面板/外部请求把第 ``index`` 层设为激活层。"""
        if not self._multi_layers or index == self._active_layer:
            # 点的就是当前层：按钮弹回选中态即可，不空跑一次切层
            self._sync_layer_switcher()
            return
        if not 0 <= index < len(self._multi_layers):
            return
        self._switch_context_layer()
        self._sync_layer_switcher()

    def _switch_context_layer(self) -> None:
        """点击另一张图切换活动层：世界纹丝不动，两边互不影响。

        用户 2026-10-13 定的模型（对齐拼版页的手感）：两张图是两个**一直
        存在的独立图层**，摆在版面相对位置上；切换只换"哪张可编辑"——

        - **不烘焙**：挂起的变换预览不"应用"，当前显示效果拼成 ghost 留给
          非活动态展示（A 转了 15°，切到 B 时 A 还是转过的样子）；切回本层
          实时预览从快照原样恢复（亚毫秒，零重采样）。烘焙只发生在「完成」
          （:meth:`_bake_inactive_pending`）。
        - **视图不动**：切层不适配、不缩放、不重定位，只替换活动图片与
          非活动图片的显示图元。
        """
        if len(self._multi_layers) != 2 or self._active_layer < 0:
            return
        old_index = self._active_layer
        new_index = 1 - old_index
        self._commit_text_blocks()
        self._commit_crop()
        # 挂起变换预览：拼 ghost（要在 `_commit_crop` **之后**——裁剪若
        # 真落了像素，浮层已被 set_image 清掉，ghost 自然为 None）
        ghost = self._render_layer_ghost()
        self._multi_layers[old_index]["state"] = self._capture_layer_state()
        self._multi_layers[old_index]["canvas_state"] = (
            self.canvas.capture_transform_state()
        )
        self._multi_layers[old_index]["ghost"] = ghost[0] if ghost else None
        self._multi_layers[old_index]["ghost_origin"] = (
            ghost[1] if ghost else None)
        self._load_layer(new_index)
        self._multi_layers[new_index]["ghost"] = None
        self._multi_layers[new_index]["ghost_origin"] = None
        self.canvas.clear_text_blocks()
        # ``refit=False``：切层只换图片，不改视图缩放。
        self.canvas.set_image(self._image, refit=False)
        layer_canvas_state = self._multi_layers[new_index].get("canvas_state")
        if layer_canvas_state is None:
            self.canvas.rearm_content_restore()
            if self.canvas.tool == "transform":
                self.canvas.set_tool("transform")
        else:
            self.canvas.restore_transform_state(layer_canvas_state)
        self._refresh_multi_canvas()
        self._refresh_tool_page(self.canvas.tool)
        self._refresh_size_label()
        self._sync_undo_buttons()
        self._sync_history()
        self._sync_layer_switcher()


    def _confirm_overwrite(self) -> bool:
        """「完成」前问一句"要不要覆盖原图"；用户取消返回 False。

        用户 2026-10-04 定的：图片编辑最后应用时**必须提醒会覆盖原图**。
        只在 ``save_back``（本页有真实文件可回写）时问——虚拟预览
        （区域合成/打印重排/PDF 页）压根不写盘，问了是假警报。

        ⚠️ 这不是"单步变更确认"：单步确认按钮已经全部删掉、编辑实时生效，
        唯一保留的确认是"覆盖磁盘原图"这件不可逆的事。

        ⚠️ 三个"不打扰"的短路，都走 ``return True``（当作用户同意）：

        1. **无图**：没有可覆盖的东西；
        2. **目标尚不存在**（``target_exists=False``，宿主回填）：整页组合
           第一次编辑写的是缓存区里新建的文件，没有旧内容可丢；
        3. **没改动**：``self._image == self._original``（QImage 逐像素相等）
           且没有待定裁剪。空跑一趟却弹"将覆盖原图"，用户只会觉得这框很蠢——
           真要改的话改动本身就在图上，一眼看得见。

        ⚠️ 延迟导入 ``MessageBox``（与 ``modules/detect/page.py`` 同款）：
        自测要能把它换成记录器，否则离屏跑会弹真模态把整个用例挂住。
        """
        if self._multi_layers:
            if any(self._layer_has_changes(layer) for layer in self._multi_layers):
                return self._ask_overwrite()
            return True
        if not self._save_back:
            return True
        if not getattr(self, "target_exists", True):
            return True
        if self._image is None or self._image.isNull():
            return True
        # ⚠️ **待定裁剪也算"改过了"**：它还没落到像素上（``_image`` 仍是原图），
        #    但「完成」马上就要把它裁掉并覆盖磁盘——只比 ``_image`` 的话，
        #    "只裁不改"的编辑会一声不吭地把原图裁小写回去。
        if getattr(self, "_pending_crop", None) is not None:
            return self._ask_overwrite()
        # ⚠️ **挂起的变换也算"改过了"**：统一变换松手只挂起预览（像素没动、
        #    ``_image`` 仍是原图，见 dialog_commit），但「完成」马上就要把
        #    变换烘焙进去并覆盖磁盘——只比 ``_image`` 的话，"只转了个角度"
        #    的编辑会一声不吭地覆盖原图（连确认框都不弹，2026-10-10）。
        if self.canvas.has_pending_transform():
            return self._ask_overwrite()
        try:
            unchanged = self._image == self._original
        except Exception:      # noqa: BLE001（比较失败就当"改过了"，宁可多问）
            unchanged = False
        if unchanged:
            return True
        return self._ask_overwrite()

    def _layer_has_changes(self, layer: dict) -> bool:
        if layer is self._multi_layers[self._active_layer]:
            if self.canvas.has_pending_transform() \
                    or getattr(self, "_pending_crop", None) is not None \
                    or any(block.toPlainText().strip()
                           for block in self.canvas.text_blocks()):
                return True
            state = self._capture_layer_state()
        else:
            # ⚠️ 非活动层的**挂起未烘焙变换**也算改过（切层不烘焙，
            #    2026-10-13）：判据 = 画布快照里"碰过变换且有预览数据"
            #    （``_xf_touched`` + rect/region）＝``transform_pending``
            #    的快照版——「完成」时这层会被补烘焙并写盘。
            canvas_state = layer.get("canvas_state") or {}
            if (canvas_state.get("_xf_touched")
                    and canvas_state.get("_xf_rect") is not None
                    and canvas_state.get("_xf_region") is not None):
                return True
            state = layer["state"]
        image = state.get("_image")
        original = state.get("_original")
        return image is not None and original is not None and image != original

    def _bake_inactive_pending(self) -> None:
        """「完成」前把**非活动层**挂着的未烘焙变换逐层落进像素。

        切层从不烘焙（2026-10-13 口径：切换要快、互不影响），挂起预览随层
        快照保存；但「完成」要写底片——不补烘的话那笔变换就**无声丢了**。
        逐层临时激活 → 恢复画布快照 → ``_commit_transform(force=True)``
        （大图走进度框，可取消）→ 快照写回层。烘焙失败/取消的层保持原样
        （像素与快照都不动，下次进来继续编辑）。
        """
        active_index = self._active_layer
        active_state = self._capture_layer_state()
        active_canvas = self.canvas.capture_transform_state()
        for index, layer in enumerate(self._multi_layers):
            if index == active_index:
                continue
            canvas_state = layer.get("canvas_state") or {}
            if not (canvas_state.get("_xf_touched")
                    and canvas_state.get("_xf_rect") is not None
                    and canvas_state.get("_xf_region") is not None):
                continue
            before_state = layer.get("state")
            self._load_layer(index)
            self.canvas.set_image(self._image, refit=False)
            self.canvas.restore_transform_state(canvas_state)
            if self._commit_transform(force=True, update_canvas=False):
                layer["state"] = self._capture_layer_state()
                layer["canvas_state"] = None
                layer["ghost"] = None
                layer["ghost_origin"] = None
            else:
                layer["state"] = before_state   # 取消/失败：原样保留
        layer = self._multi_layers[active_index]
        layer["state"] = active_state
        layer["canvas_state"] = active_canvas
        self._load_layer(active_index)
        self.canvas.set_image(self._image, refit=False)
        self.canvas.restore_transform_state(active_canvas)
        self._refresh_multi_canvas()

    def _save_multiple_images(self) -> bool:
        from desktop.components.viewers.image_zoom_dialog.io import (
            overwrite_image_file,
        )
        from .content_quad import sync_content_quad

        self._multi_layers[self._active_layer]["state"] = self._capture_layer_state()
        active_index = self._active_layer
        layout_updates = []
        for index, layer in enumerate(self._multi_layers):
            state = layer["state"]
            image = state.get("_image")
            original = state.get("_original")
            if image is None or original is None or image == original:
                continue
            if not overwrite_image_file(image, Path(layer["file"])):
                if layout_updates:
                    self.multi_layout_saved.emit(layout_updates)
                self._load_layer(active_index)
                QMessageBox.warning(
                    self, "保存失败",
                    f"无法保存「{layer['label']}」：{Path(layer['file']).name}",
                )
                return False
            self._load_layer(index)
            sync_content_quad(layer["file"], self)
            self.multi_image_saved.emit(layer["file"], QImage(image))
            x, y, _width, _height = layer["rect"].getRect()
            scale_x, scale_y = self._layer_scale(layer)
            origin_x, origin_y = self._layer_origin(layer)
            # ⚠️⚠️ 回报给拼版页的 rect 必须是**可见内容**的框，不是整张像素图
            #    （2026-10-14 用户报障「弹窗里把图下移 200px，应用后拼版页左图
            #    变大了、左右不等高」）。裁剪"移动"把位移编码成**透明边距**，
            #    像素图因此变大（实测 1000 → 1200 高），而内容其实没变——直接
            #    回报 ``image.height()`` 就等于**把留白算进版面**，虚线框比图
            #    大一圈、底部多出一截。
            #    这里只报**内容框**，拼版侧据此摆框。
            # ⚠️⚠️ **位移取内容框在新画布里的偏移 ``content[0:2]``，不是
            #    ``layer["origin"]``**（2026-10-15 用户报障「裁剪里把左图往右图
            #    方向拖，松手后两图重合／挨得比拖动时更近」）：``origin`` 的定义
            #    是"画布 (0,0) 在初始图像素系里的坐标"＝**画布原点的位置**，
            #    纯裁剪时它非零（=box）而内容没动、裁剪移动时它为零而内容动了
            #    （位移已烤进留白）——两个方向都与"内容往哪边挪了"无关或相反。
            #    位移的权威口径只有一个：**内容框在新画布里的偏移**。
            #    （与 :meth:`_commit_crop` 的 origin 累加彻底解耦：那条管的是
            #    **两图相对摆放**的锚点，这条管的是**回报给拼版页的版面框**。）
            content = _transparent_content_bounds(image)
            if content is None:
                offset_x, offset_y = 0.0, 0.0
                content_w, content_h = image.width(), image.height()
            else:
                offset_x, offset_y = float(content[0]), float(content[1])
                content_w, content_h = content[2], content[3]
            layout_updates.append({
                "index": layer["page_item_index"],
                "file": layer["file"],
                "rect": [
                    x + offset_x * scale_x,
                    y + offset_y * scale_y,
                    content_w * scale_x,
                    content_h * scale_y,
                ],
            })
        self._load_layer(active_index)
        self._refresh_multi_canvas()
        if layout_updates:
            self.multi_layout_saved.emit(layout_updates)
        return True


    def _ask_overwrite(self) -> bool:
        """弹一次"覆盖原图"确认；问不出来（无事件循环/测试替身）时按同意处理。

        延迟导入 ``MessageBox``（与 ``modules/detect/page.py`` 同款）：自测要能
        把它换成记录器，否则离屏跑会弹真模态把整个用例挂住。
        """
        try:
            from qfluentwidgets import MessageBox  # noqa: PLC0415

            name = str(getattr(self, "target_name", "") or "").strip()
            detail = f"「{name}」" if name else "原图片"
            # ⚠️ 正文**不用 markdown 粗体**（``**…**``）：MessageBox 的
            #    contentLabel 是普通 QLabel，``**`` 会原样显示成两个星号。
            box = MessageBox(
                "确定要覆盖原图吗？",
                f"应用这次编辑会覆盖掉{detail}的现有内容，"
                "磁盘上的原图将不再保留。\n\n"
                "若只是想先看看效果，请直接关闭本弹窗（本次编辑全部作废）。",
                self,
            )
            box.yesButton.setText("覆盖并应用")
            box.cancelButton.setText("返回继续编辑")
            return bool(box.exec())
        except Exception:      # noqa: BLE001（无 Qt 事件循环/替身无 exec）
            return True


    def _finish(self) -> None:
        """「完成」：待定裁剪/变换/未提交的文字一并落定，再应用全部编辑。

        ⚠️ 顺序有讲究：先落**裁剪**（它改画布尺寸）、再落变换（变换作用在
        裁完的图上）、最后写入文字块。变换**必须 ``force=True``**：松手只
        挂起预览（像素没动），不带 force 会被 :meth:`_commit_transform` 的
        "挂起跳过"分支原样退回 ⇒ 变换永远落不到实体图上——用户 2026-10-10
        报的正是这个（「统一变换不能落地到实体图片」，其它工具没挂起机制
        所以都正常）。这里不是"兜底"，是挂起机制下**唯一的烘焙时机**之一
        （另一个是离开变换工具，走 ``_set_tool`` 的 force=True）。

        ⚠️⚠️ **save_back 且有挂起变换时走后台应用**（``_begin_background_apply``
        返回 True 就直接 return，``accept()`` 在启动器里已经调了）：弹窗立刻
        关闭，烘焙 + 写底片在工作线程里跑，完成后经 ``apply_completed`` 通
        知宿主刷新。用户 2026-10-10 口径：「应用保存时页面上的数据可以不
        保存，只需要将数据存到相应的底片上」——此前整幅重采样（12 MP 约
        11 秒）+ 写盘全程把界面钉死，正是「应用卡顿」的来源。

        ⚠️ 烘焙被用户取消（进度框点取消）/ 失败时 ``_commit_transform``
        返回 ``False``：**中止收尾**、留在编辑器里继续改——绝不能往下
        ``accept()`` 把"没变换的图"当结果交出去（save_back 时那会无声
        覆盖磁盘原图）。（后台应用没有"留在编辑器"一说：取消/失败经
        ``apply_failed`` 告知宿主，底片未动。）

        ⚠️ ``_finishing`` 必须在**确认框之前**就置位：``MessageBox.exec()``
        自带事件循环，双击「完成」会在框弹出后再进一次这里⇒ 叠出第二个
        确认框。所以顺序是"先上锁 → 再问 → 不同意就退出并解锁"，
        不是"问完再上锁"。
        """
        if getattr(self, "_finishing", False):
            return
        self._finishing = True
        try:
            if not self._confirm_overwrite():
                return
            if self._multi_layers:
                # 非活动层的挂起变换逐层补烘焙（切层不烘焙，见
                # _bake_inactive_pending）——必须在写盘之前
                self._bake_inactive_pending()
            self._commit_crop()
            if self._begin_background_apply():
                return
            if not self._commit_transform(force=True, update_canvas=False):
                return
            self._commit_text_blocks()
            if self._multi_layers and not self._save_multiple_images():
                return
            self.accept()
        finally:
            self._finishing = False


    # ------------------------------------------------------------ 对外
    def release_buffers(self, keep_result: bool = False) -> None:
        """释放**整图级**缓冲（原图/当前图/撤销与重做快照/upright 缓存）。

        为什么必须有（2026-10-13「程序内存越来越大」）：编辑器的缓冲全是
        原分辨率整图——``_original`` + ``_image`` 两份，外加撤销栈最多
        ``UNDO_LIMIT`` 份整图快照（大图下可达 GB 级）。编辑器是 QDialog、
        由宿主长期持有，只 close 不销毁的话这些像素**一直驻留**，跨任务
        都不释放。宿主在结果消费完（或弹窗整体关闭）后调用本方法即可放掉。

        ``keep_result=True``：保留 ``_image``（后台应用完成链用——宿主约定
        「关窗后仍可取 ``result_image()``」，见 ``image_editor_saveback``
        自测）。其余整图缓冲照放：撤销栈 + 原图 + upright 才是大头。

        ⚠️ ``keep_result=False``（默认）时结果即作废：只能在"不再需要
        ``result_image()``"之后调用。
        """
        self._original = None
        if not keep_result:
            self._image = None
        self._undo = []
        self._redo = []
        self._labels = []
        # ⚠️ 双图编辑（拼版「编辑整图」）：每层的整图缓冲（``_image``/
        #    ``_original``/撤销栈/upright）也驻留在层字典里——两个图层就是
        #    双倍内存，宿主消费完结果放缓冲时必须一起放。``canvas_state``
        #    里的底图/浮层像素快照同理（换层捕获的整图拷贝）。
        for layer in getattr(self, "_multi_layers", None) or []:
            state = layer.get("state")
            if isinstance(state, dict):
                state["_image"] = None
                state["_original"] = None
                state["_undo"] = []
                state["_redo"] = []
                state["_undo_origins"] = []
                state["_redo_origins"] = []
                state["_content_upright"] = None
                state["_content_restore_params"] = None
            layer["canvas_state"] = None
            layer["ghost"] = None
            layer["ghost_origin"] = None
        # 内容节点 sidecar 的 upright 是另一份全分辨率反变换缓存，一并放掉
        self._content_upright = None
        self._content_restore_params = None

    def closeEvent(self, event) -> None:  # noqa: N802（Qt 回调）
        """关闭时清理画布引用。

        撤销栈是**整图快照**，大图下最多 12 份（见 ``UNDO_LIMIT``），
        关窗后必须释放，不能靠 Python GC（Qt 侧 C++ 对象不由引用计数托管）。

        ⚠️ 只有**未采纳**的关闭（X / Esc / reject）能在这里直接放缓冲：
        accept() 的关闭不触发 closeEvent，而调用方在 ``exec()`` 返回后还要
        读 ``result_image()``——采纳路径的释放由调用方消费完结果后显式调
        :meth:`release_buffers`（或后台应用链在 ``_on_async_apply_done``
        里兜底）。
        """
        self._finishing = True
        try:
            if self.result() != QDialog.DialogCode.Accepted:
                self.release_buffers()
            # EditorCanvas 无 clear（此调用在运行期恒抛 AttributeError，被下面
            # 吞掉，等价于不做事）；保留原样以免改变关闭时的清理行为。
            self.canvas.clear()  # type: ignore[attr-defined]
        except Exception:      # noqa: BLE001（销毁期清理不该再抛）
            pass
        super().closeEvent(event)


    def result_image(self) -> QImage | None:
        """编辑结果（无图时 None；是否采纳由调用方的 exec 结果决定）。"""
        if self._image is None or self._image.isNull():
            return None
        return self._image
