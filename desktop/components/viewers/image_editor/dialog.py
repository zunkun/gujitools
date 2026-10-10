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

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget
from desktop.ui import theme as T
from desktop.ui.window_size import apply_window_size
from .canvas import EditorCanvas
from .geometry import _trim_transparent_edges
from .consts import (
    ERASER_DEFAULT, HISTORY_ORIGIN_LABEL, TEXT_DEFAULT,
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


    def __init__(self, parent=None, image: QImage | None = None,
                 save_back: bool = False):
        super().__init__(parent)
        # 本页有真实文件可回写（宿主预览弹窗传入）：「完成」= 直接覆盖原图
        # 文件，而不是"回画布再自己下载"。只影响文案与覆盖确认，行为在弹窗侧。
        self._save_back = bool(save_back)
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
        self._text_color: str = "#000000"
        self._text_family: str = T.FONT_FAMILY
        self._erase_size: int = ERASER_DEFAULT
        #: 「完成」整体处理中（防**双击重入**：确认框的 ``exec()`` 自带
        #: 事件循环，会派发排队的第二次点击）
        self._finishing = False

        self.canvas = EditorCanvas(self)
        self.canvas.set_image(self._image)
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
            self._commit_crop()
            if self._begin_background_apply():
                return
            if not self._commit_transform(force=True, update_canvas=False):
                return
            self._commit_text_blocks()
            self.accept()
        finally:
            self._finishing = False


    # ------------------------------------------------------------ 对外
    def closeEvent(self, event) -> None:  # noqa: N802（Qt 回调）
        """关闭时清理画布引用。

        撤销栈是**整图快照**，大图下最多 12 份（见 ``UNDO_LIMIT``），
        关窗后必须释放，不能靠 Python GC（Qt 侧 C++ 对象不由引用计数托管）。
        """
        self._finishing = True
        try:
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
