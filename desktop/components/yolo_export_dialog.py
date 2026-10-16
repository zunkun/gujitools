# -*- coding: utf-8 -*-
"""「导出YOLO标注」的弹窗：选导出目录 + 填名称（父节点名 = 文件名前缀）。

用户 2026-10-16 定的三条：

1. 点按钮**先弹窗**（不是直接开导）；
2. **名称**一个字段，同时当导出目录下的**父节点名**与**文件名前缀**——
   填 ``b1`` 就是 ``b1-1.jpg`` / ``b1-1.txt``（``x`` 是**页序序号**，从 1 起）；
3. 弹窗里有「取消」「确认导出」两个按钮。

外壳用 :func:`desktop.components.dialog_shell.shell_dialog`（仓库里"标题 + 内容
+ 底部按钮"的唯一实现），本模块只提供里面的**内容面板**与一个
:func:`ask_yolo_export` 入口。

⚠️ 「导出目录」由调用方从**上次记住的值**回填（任务级 / 独立任务级各记一份，
见 ``desktop/store/ui_state.py`` 与 ``desktop/utils/files.py``）；调用方给空时
本模块自己兜底成**文档目录**（用户 2026-10-16：「导出目录默认是 ~/Documents」）
——本模块不认识存储，只认"拿到什么显示什么 + 空值怎么兜"。「名称」的默认值
（任务号 / 源名）由**宿主**给，因为只有它知道当前是哪本书。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, LineEdit, PushButton

from desktop.components.dialog_shell import shell_dialog
from desktop.services.detect_export import (
    YOLO_IMAGES_DIRNAME,
    YOLO_LABELS_DIRNAME,
    YOLO_LABEL_SUFFIX,
)
from desktop.ui import theme as T
from desktop.ui.widgets import CONTROL_HEIGHT, SectionTitle, apply_to
from desktop.utils.files import default_open_dir, safe_dirname


class YoloExportPanel(QWidget):
    """导出参数面板：导出目录（只读 + 选择…）+ 名称 + 落点预览。"""

    def __init__(self, directory: str | Path | None = None,
                 name: str = "", parent=None):
        """``directory`` / ``name`` 是回填值（上次记住的那一份）。

        ⚠️ ``directory`` 为空时默认**文档目录**（``default_open_dir()``，用户
        2026-10-16：「导出目录默认是 ~/Documents」）——留一个空输入框等于让用户
        每次都从零点起；文档目录是所有"我要导出去的东西"的共同起点。
        """
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(T.SPACE_SM)

        root.addWidget(SectionTitle("导出目录"))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)
        self.dir_edit = LineEdit(self)
        self.dir_edit.setText(str(directory or default_open_dir()))
        # 只读：路径一律经「选择…」对话框产生，手敲既容易写错又绕过了目录校验
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setPlaceholderText("点右边的「选择目录…」指定导出目录")
        self.dir_edit.setClearButtonEnabled(False)
        row.addWidget(self.dir_edit, 1)
        self.pick_button = PushButton("选择目录…", self)
        self.pick_button.setFixedHeight(CONTROL_HEIGHT)
        self.pick_button.clicked.connect(self._pick_directory)
        row.addWidget(self.pick_button)
        root.addLayout(row)

        root.addWidget(SectionTitle("名称（文件夹名 = 文件名前缀）"))
        self.name_edit = LineEdit(self)
        self.name_edit.setText(name)
        self.name_edit.setPlaceholderText("例如 b1 → b1-1.jpg / b1-1.txt")
        self.name_edit.setToolTip(
            "这一批图片的标识：它既是导出目录下的文件夹名，也是每个文件的前缀。\n"
            "序号按页序从 1 开始（b1-1、b1-2…）。"
        )
        self.name_edit.textChanged.connect(self._refresh_preview)
        root.addWidget(self.name_edit)

        self.preview = CaptionLabel("", self)
        self.preview.setWordWrap(True)
        apply_to(self.preview, T.SIZE_CAPTION, color=T.INK_FAINT)
        root.addWidget(self.preview)

        self.warning = CaptionLabel("", self)
        self.warning.setWordWrap(True)
        apply_to(self.warning, T.SIZE_CAPTION, color=T.DANGER)
        self.warning.setVisible(False)
        root.addWidget(self.warning)
        root.addStretch(1)
        self._refresh_preview()

    # ------------------------------------------------------------------ 取值
    def directory(self) -> str:
        """当前导出目录（空串 = 还没选）。"""
        return self.dir_edit.text().strip()

    def name(self) -> str:
        """当前名称（空串 = 还没填）。"""
        return self.name_edit.text().strip()

    def values(self) -> tuple[str, str]:
        """``(名称, 导出目录)``。"""
        return self.name(), self.directory()

    def set_warning(self, text: str) -> None:
        """在面板里写一行红色提示（空串则隐藏）。"""
        self.warning.setText(text)
        self.warning.setVisible(bool(text))

    # ------------------------------------------------------------------ 交互
    def _pick_directory(self) -> None:
        """选导出目录；用户取消则保持原值。"""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "选择导出目录",
            self.directory() or str(default_open_dir()),
        )
        if not chosen:
            return
        self.dir_edit.setText(chosen)
        self._refresh_preview()

    def _refresh_preview(self, *_args) -> None:
        """把"这次会导出成什么"实时写出来（路径 + 命名规律）。"""
        label = safe_dirname(self.name() or "名称")
        base = Path(self.directory()) if self.directory() else Path("<导出目录>")
        folder = base / label
        self.preview.setText(
            f"导出到 {folder}\n"
            f"　{YOLO_IMAGES_DIRNAME}/{label}-1.jpg、{label}-2.jpg…（按页序复制原图）\n"
            f"　{YOLO_LABELS_DIRNAME}/{label}-1{YOLO_LABEL_SUFFIX}、"
            f"{label}-2{YOLO_LABEL_SUFFIX}…（同页的框，无框页是空文件）"
        )


def ask_yolo_export(
    parent,
    directory: str | Path | None = None,
    name: str = "",
) -> tuple[str, str] | None:
    """弹「导出YOLO标注」窗。

    返回 ``(名称, 导出目录)``；用户点「取消」（或直接关窗）返回 ``None``。

    ⚠️ 校验放在 ``on_ok`` 里（而不是"关完再看"）：名称或目录空着时**不关窗**，
    把红色提示写在面板里让用户当场补——关掉再弹一次抱怨"没填名称"很烦人。
    """
    panel = YoloExportPanel(directory, name, parent)
    holder: dict = {}

    def _confirm(*_args) -> None:
        name_text, directory_text = panel.values()
        if not name_text:
            panel.set_warning("请填写名称：它同时用作文件夹名与文件名前缀。")
            return
        if not directory_text:
            panel.set_warning("请先点「选择目录…」指定导出目录。")
            return
        holder["result"] = (name_text, directory_text)
        holder["dialog"].accept()

    dialog = shell_dialog(
        "导出YOLO标注",
        panel,
        parent,
        size=(640, 360),
        ok_text="确认导出",
        cancel_text="取消",
        on_ok=_confirm,
    )
    holder["dialog"] = dialog
    dialog.exec()
    return holder.get("result")


__all__ = ["YoloExportPanel", "ask_yolo_export"]
