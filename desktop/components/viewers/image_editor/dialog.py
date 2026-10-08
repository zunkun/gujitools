# -*- coding: utf-8 -*-
"""``ImageEditorDialog``：**装配点 + 基座 + 收尾**。

从 894 行的单类拆出（2026-10-07）。本文件放模块级常量、类头（类属性）、
``__init__``、快捷键、覆盖确认与「完成」收尾；工具栏、各工具选项页、撤销栈、
工具提交分别在兄弟模块的 Mixin 里。方法体逐字未改。

MRO 顺序：工具栏/选项页在前（``__init__`` 里就要用），提交与撤销在后。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget
from desktop.ui import theme as T
from desktop.ui.window_size import apply_window_size
from .canvas import EditorCanvas
from .consts import ERASER_DEFAULT, TEXT_DEFAULT


# ------------------------------------------------------------------ 弹窗
#: 图片编辑弹窗的**期望**尺寸与最小尺寸（逻辑像素）。落地前一律经
#: ``apply_window_size`` 夹进屏幕可用区域，所以这两个值是"上限"而不是承诺
#: （1920×1080 @125% 的机器上可用高只有 824，940 会被任务栏吃掉一截）。
#: 自测按这两个常量算期望值，别再在测试里写死 1440×940。
EDITOR_SIZE = QSize(1440, 940)


EDITOR_MIN_SIZE = QSize(1000, 680)




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
    """图片编辑器弹窗：左工具栏 + 中间画布 + 右侧选项页 + 底部状态栏。"""



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
        self.setWindowTitle("图片编辑")
        self.setModal(True)
        # 编辑要看得清字迹：默认开大，并带最小化/最大化按钮（标题栏双击
        # 最大化也随 maximize 按钮生效），用户 20:18 定
        # ✳️ 但默认尺寸与最小尺寸都要先夹进屏幕可用区域：1440×940 / 1000×680
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
        self._original = base.convertToFormat(QImage.Format.Format_ARGB32)
        self._image = self._original.copy()
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self._option_page: QWidget | None = None
        # 文字工具选项的活性引用（插入时现读，见 _commit_text_blocks）
        self._text_size: int = TEXT_DEFAULT
        self._text_color: str = "#000000"
        self._text_family: str = T.FONT_FAMILY
        self._erase_size: int = ERASER_DEFAULT
        #: 「完成」整体处理中（防**双击重入**：确认框的 ``exec()`` 自带
        #: 事件循环，会派发排队的第二次点击）
        self._finishing = False

        self.canvas = EditorCanvas(self)
        self.canvas.set_image(self._image)
        self.canvas.stroke_started.connect(self._push_undo)
        self.canvas.text_requested.connect(self._spawn_text_block)

        root = QVBoxLayout(self)
        root.setContentsMargins(T.SPACE_MD, T.SPACE_MD, T.SPACE_MD, T.SPACE_MD)
        root.setSpacing(T.SPACE_SM)
        # ⚠️ 两行结构（Win10 照片的布局）：主工具栏一行摆不下撤销/还原/
        #    缩放/四个工具/提示/应用/完成，一行时左侧按钮会被挤出窗口
        #    （用户 19:36 截图报"左上边有按钮隐藏掉了"）。
        # ⚠️ _option_row 必须先建：_build_toolbar_row 末尾的 _set_tool
        #    就会往里插第一份选项页。
        self._option_row = QHBoxLayout()
        self._option_row.setSpacing(T.SPACE_SM)
        root.addLayout(self._build_toolbar_row())
        # 第二行：随工具切换的上下文选项（提示/滑杆/应用按钮）
        root.addLayout(self._option_row)
        root.addWidget(self.canvas, 1)
        root.addWidget(self._build_status())
        # ⚠️ 不要在这里再调 _set_tool("crop")：_build_toolbar_row 末尾已经
        #    调过一次。调两次会遗弃一份旧选项页——removeWidget+deleteLater
        #    在构造期不生效，旧页就以默认几何 (0,0,100,30) 悬在左上角，
        #    盖住撤销按钮（用户截图报"左上角有个按钮被隐藏了"）。

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

        ⚠️ 四个"不打扰"的短路，都走 ``return True``（当作用户同意）：

        1. **无图**：没有可覆盖的东西；
        2. **目标尚不存在**（``target_exists=False``，宿主回填）：整页组合
           第一次编辑写的是缓存区里新建的文件，没有旧内容可丢；
        3. **没改动**：``self._image == self._original``（QImage 逐像素相等）。
           空跑一趟却弹"将覆盖原图"，用户只会觉得这框很蠢——真要改的话
           改动本身就在图上，一眼看得见；
        4. **测试替身**：``qfluentwidgets.MessageBox`` 被自测换成记录器时，
           它没有真 ``exec()``；用 ``getattr`` 兜住，替身返回 True 直接过。

        ⚠️ 延迟导入 ``MessageBox``（与 ``modules/detect/page.py`` 同款）：
        自测要能把它换成记录器，否则离屏跑会弹真模态把整个用例挂住。
        """
        if not self._save_back:
            return True
        if not getattr(self, "target_exists", True):
            return True
        if self._image is None or self._image.isNull():
            return True
        try:
            unchanged = self._image == self._original
        except Exception:      # noqa: BLE001（比较失败就当"改过了"，宁可多问）
            unchanged = False
        if unchanged:
            return True
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
        """「完成」：未应用的变换/未插入的文字一并写入，再应用全部编辑。

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
            self._commit_transform()
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
