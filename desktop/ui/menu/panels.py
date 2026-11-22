# -*- coding: utf-8 -*-
"""检查更新/关于弹窗的内容面板与下载进度窗（自 ``desktop/ui/menu.py`` 拆出）。"""

from __future__ import annotations

from qfluentwidgets import BodyLabel, CaptionLabel

from desktop.components.dialog_shell import shell_dialog
from desktop.ui import theme as T
from desktop.ui.widgets import ProgressLine, apply_to

from ._qt import QGridLayout, QVBoxLayout, QWidget, Qt
from .constants import BUTTON_CANCEL

# ------------------------------------------------------------------ 面板
class _MessagePanel(QWidget):
    """结果弹窗的内容：一段可换行的正文 + 可选的可选中链接。"""

    def __init__(self, body: str, link: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        text = BodyLabel(body, self)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        apply_to(text, T.SIZE_BODY, color=T.INK)
        # ⚠️ 换行标签必须开 ``heightForWidth``：**弹窗高度按内容算**（见
        #    ``UpdateController._present`` 的 ``adjustSize``）时，Qt 才会把"折行后要
        #    多高"算进 sizeHint；不开的话算出来只有一行的身高，弹窗照样要么顶到内容
        #    （裁字）要么按写死高度留一大片空白（用户 2026-10-15 截图报「高度太高」）。
        policy = text.sizePolicy()
        policy.setHeightForWidth(True)
        text.setSizePolicy(policy)
        layout.addWidget(text)
        if link:
            hint = CaptionLabel(link, self)
            hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            apply_to(hint, T.SIZE_CAPTION, color=T.INK_FAINT)
            layout.addWidget(hint)
        layout.addStretch()


class _AboutPanel(QWidget):
    """「关于」的内容：键值两列表格（值可选中，便于复制版本号/路径）。"""

    def __init__(self, rows: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(T.SPACE_LG)
        grid.setVerticalSpacing(T.SPACE_SM)
        for index, (key, value) in enumerate(rows):
            key_label = BodyLabel(key, self)
            apply_to(key_label, T.SIZE_BODY, color=T.INK_SOFT)
            value_label = BodyLabel(value, self)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            apply_to(value_label, T.SIZE_BODY, color=T.INK)
            # ⚠️⚠️ 值**不加对齐参数**（用户 2026-10-15 报「关于内容显示不完整」）：
            #    ``QGridLayout.addWidget(w, r, c, alignment)`` 里的对齐参数会让控件
            #    **按自己的 sizeHint 摆放、不再填满单元格**——带自动换行的 QLabel 的
            #    sizeHint 宽度很小，于是长路径/长网址被压成"只看得见 C:"这种一截
            #    （实测截图就是它）。不给对齐即"填满该列"，列本身有 stretch ⇒ 拿到
            #    全部剩余宽度；文字的左右/垂直位置改由标签自己的 alignment 管。
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            # 换行标签必须开 heightForWidth，否则行高只按"一行"算，折下来的第二行
            # 会被裁掉（同一次报障的另一半）。
            policy = value_label.sizePolicy()
            policy.setHeightForWidth(True)
            value_label.setSizePolicy(policy)
            # ⚠️ 键仍要对齐（右对齐 + 贴顶），理由见上一段说明：短键右缘与长键齐平。
            grid.addWidget(
                key_label,
                index,
                0,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            )
            grid.addWidget(value_label, index, 1)
        grid.setColumnStretch(1, 1)
        # 键列不参与拉伸（宽度按最长的键名定），否则键与值之间会空出一大段。
        grid.setColumnStretch(0, 0)
        # ⚠️ 末尾兜一条弹性行：本面板在 ``shell_dialog`` 里是按 stretch=1 摆的，
        #    不兜住多余高度的话 QGridLayout 会把空白**摊到每一行上**（实测行距被
        #    撑到 ~75px，四行散成一大片）；内容该紧凑地贴顶。
        grid.setRowStretch(len(rows), 1)


class _ProgressPanel(QWidget):
    """下载进度弹窗的内容：一行状态文案 + 一根细进度条（``ProgressLine``）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)
        self.label = BodyLabel("准备下载…", self)
        self.label.setWordWrap(True)
        apply_to(self.label, T.SIZE_BODY, color=T.INK)
        # 同 ``_MessagePanel``：换行标签必须开 heightForWidth，弹窗高度才按内容算。
        policy = self.label.sizePolicy()
        policy.setHeightForWidth(True)
        self.label.setSizePolicy(policy)
        self.bar = ProgressLine(self)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addStretch()

    def set_progress(self, percent) -> None:
        """更新进度：``percent < 0`` = 总量未知（进度条切「来回滑动」未知态）。"""
        if percent is None or int(percent) < 0:
            self.bar.setRange(0, 0)
            self.label.setText("正在下载…")
            return
        value = max(0, min(100, int(percent)))
        self.bar.setRange(0, 100)
        self.bar.setValue(value)
        self.label.setText(f"正在下载… {value}%")

    def set_stage(self, text: str) -> None:
        """下载完成后的阶段提示（校验/释放占用/替换/重新加载）：只改文案。

        ⚠️ 这些阶段**总量不可知**（关服务、载模型各要几秒），进度条切成「来回
        滑动」的未知态——比画一根不动的空条更像"在干活"。
        """
        self.bar.setRange(0, 0)
        self.label.setText(text)


class _DownloadProgress:
    """下载进度窗的薄封装（**两个控制器共用**：程序更新 / 数据包）。

    一次下载一个实例：构造即弹窗（非模态，主线程接着收信号），期间用
    :meth:`progress` / :meth:`stage` 刷新，收尾 :meth:`close`。
    ⚠️ 按钮走 ``ok_text=BUTTON_CANCEL``：``shell_dialog`` 的 cancel 按钮在
    ``show_cancel=False`` 时被隐藏，所以"取消"只能占主按钮位。
    """

    def __init__(self, window, title: str, on_cancel) -> None:
        self.panel = _ProgressPanel()
        self.panel.set_progress(-1)      # 起步：总量未知（还没读到 Content-Length）
        self.dialog = shell_dialog(
            title, self.panel, window, size=(560, 160),
            ok_text=BUTTON_CANCEL, show_cancel=False, on_ok=on_cancel,
        )
        self.dialog.show()

    def progress(self, percent) -> None:
        self.panel.set_progress(percent)

    def stage(self, text: str) -> None:
        self.panel.set_stage(text)

    def close(self) -> None:
        self.dialog.close()
