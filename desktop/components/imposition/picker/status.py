# -*- coding: utf-8 -*-
"""插入落点单选行与底部状态说明（``_StatusMixin``）。

Mixin 只在运行期与 ``ImpositionPickerDialog`` 组合；宿主面见 :mod:`._host`，
本模块**不 import** 主类 ``dialog``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qfluentwidgets import RadioButton

from desktop.components.imposition.picker._qt import (
    QHBoxLayout,
    QLabel,
    QWidget,
)
from desktop.services.imposition import SOURCE_FULL, classify_source
from desktop.ui import theme as T
from desktop.ui.widgets import apply_to

if TYPE_CHECKING:
    from desktop.components.imposition.picker._host import PickerHost as _Host
else:
    _Host = object


class _StatusMixin(_Host):
    """「插入第 x 页之前/之后」单选行与说明/状态行。"""

    # ------------------------------------------------------- 落点选项（插入）
    def _build_position_row(self, default_position: str) -> QWidget:
        """底部「插入第 x 页之前 / 之后」——**只 insert 模式显示**。

        ⚠️ 右键菜单已经表达了落点（向前/向后），这里再给一次单选是为了
        "能在弹窗里改"：「PDF排版 → 插入图片」也是这个口径（用户 2026-10-31）。
        """
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_MD)
        self.before_radio: RadioButton | None = None
        self.after_radio: RadioButton | None = None
        if self._total <= 0:
            label = QLabel("清单为空，插入的页会放到最前面。")
            apply_to(label, T.SIZE_CAPTION, color=T.INK_SOFT)
            layout.addWidget(label)
            layout.addStretch()
            row.setVisible(False)
            return row
        page_no = min(max(self._current_row, 0) + 1, self._total)
        self.before_radio = RadioButton(f"插入第 {page_no} 页之前", row)
        self.after_radio = RadioButton(f"插入第 {page_no} 页之后", row)
        (self.before_radio if default_position == "before"
         else self.after_radio).setChecked(True)
        layout.addWidget(self.before_radio)
        layout.addWidget(self.after_radio)
        layout.addStretch()
        row.setVisible(self._mode == "insert")
        return row

    # ------------------------------------------------------------------ 状态
    def _update_status(self) -> None:
        """说明行/状态行 + 确认按钮的可用性。

        口径：
        1. 勾 **1 张** → 确认可点，单张单独成一页；
        2. 勾 **2 张** → 拼成一页，序号在前的排右侧；
        3. 勾 0 张或 ≥3 张 → 确认不可点（宿主的兜底逻辑按 1/2 张处理）；
        4. 只勾 1 张且是**宿主候选**（不是本次上传）时，pick 模式下方出现
           「从这张图片开始自动拼版」。

        **append 模式**（单图页「新增图片」）：只能勾 **1 张**——0 张或
        ≥2 张时「添加」不可点，「自动拼版」选项整段隐藏。
        """
        append_mode = self._mode == "append"
        picked = [card for card in self.cards if card.is_checked()]
        self.position_row.setVisible(self._mode == "insert")
        auto_available = (
            not append_mode and self._mode == "pick"
            and len(picked) == 1 and not picked[0].uploaded
        )
        self.auto_checkbox.setVisible(auto_available)
        if not auto_available and self.auto_checkbox.isChecked():
            # 选项只在恰好勾 1 张时有意义：离开该状态就复位，避免残留旧勾选
            self.auto_checkbox.setChecked(False)
        self.ok_button.setEnabled(len(picked) in ((1,) if append_mode else (1, 2)))
        uploaded = len(self._uploads)
        self.upload_hint.setText(
            f"本次已上传 {uploaded} 张（排在列表末尾、默认勾选）" if uploaded else ""
        )
        if append_mode:
            self.note.setText(
                f"从剩余未拼版的 {self.count()} 张图片中选 1 张，"
                "添加到当前这一页拼版；也可以拖入/上传自己的图片。"
            )
        elif self._mode == "insert":
            page_no = min(max(self._current_row, 0) + 1, max(self._total, 1))
            where = "之前" if self.position() == "before" else "之后"
            self.note.setText(
                f"从剩余未拼版的 {self.count()} 张图片中勾选，插到第 {page_no} 页"
                f"{where}：1 张单独成一页，2 张拼成一页（序号在前的排在右侧）；"
                "也可以拖入/上传自己的图片。"
            )
        else:
            self.note.setText(
                f"从剩余未拼版的 {self.count()} 张图片中勾选："
                "1 张单独成一页，2 张拼成一页（序号在前的排在右侧）；"
                "只勾 1 张图片时可勾选下方「从这张图片开始自动拼版」，"
                "从那张图起自动拼完。也可以拖入/上传自己的图片。"
            )
        self.status.setStyleSheet(f"color:{T.INK_SOFT};")
        count = len(picked)
        if count == 0:
            self.status.setText(
                "已选 0 张。点卡片勾选：1 张单独成页，2 张拼成一页。"
            )
            return
        if count == 1:
            first = picked[0]
            tag = ""
            if not first.uploaded and classify_source(first.path) == SOURCE_FULL:
                tag = "（整幅）"
            self.status.setText(
                f"已选 1 张：「{first.path.stem}」{tag}。"
                + ("点「插入」把它插到目标位置。" if self._mode == "insert"
                   else "点「开始拼版」单独成一页；也可勾选下方"
                        "「从这张图片开始自动拼版」从这张起自动拼完。")
            )
            return
        if count == 2:
            self.status.setText(
                "已选 2 张：将拼成一页，序号在前的排在右侧。"
            )
            return
        self.status.setText(
            f"已选 {count} 张：最多勾 2 张——两张拼一页，或 1 张单独成页。"
        )
