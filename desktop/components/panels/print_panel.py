# -*- coding: utf-8 -*-
"""生成 PDF（print）阶段面板：YAML 文本编辑模式。

print 参数复杂，直接编辑 YAML；input/output/workers/clean 由系统管理，
不需要也不应该出现在配置中。配置可初始化（生成默认模板）、可重置。
"""

from __future__ import annotations

import yaml
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, PushButton, SubtitleLabel

from .base import StagePanel

# 不允许在编辑器中配置的键（系统管理）
_EXCLUDED_KEYS = ("input", "output", "workers", "clean")

DEFAULT_PRINT_YAML = """# print 参数（YAML 编辑）
# pdf_name: 输出 PDF 文件名
pdf_name: "print.pdf"

# ----- 纸张与方向 -----
paper_size: "A4"              # A3 / A4 / A5 / B5
orientation: "landscape"      # landscape(横) / portrait(竖)

# ----- 页边距(mm) -----
# "20" / "20,30"(上下,左右) / "20,30,25,35"(上,右,下,左)
page_margins: [20, 20, 20, 20]
# left_page_margins:          # 左侧页边距（双页排版覆盖）
# right_page_margins:

# ----- 标题（书名） -----
title_printing: false
title_text: ""
title_font_size: 18
title_color: "0,0,0"          # "r,g,b" 0~255
title_position: "top"         # top / bottom
title_orientation: "vertical" # vertical / horizontal
# 标题切换节点: [页码, 标题] 或 [页码, 标题, side(left/right/both)]
# 页码 >= 触发页码时使用该标题（取最后一个匹配）
title_switch_nodes: []
#  - [1, "书名", "left"]

# ----- 页码 -----
page_number_printing: false
page_number_start_page: 1     # 开始显示页码的页（1-based）
page_number_end_page:         # null = 到最后一页
page_number_base: 0           # 页码基数（实际页码 = base + 页索引）
page_number_font_size: 12
page_number_color: "0,0,0"
page_number_position: "bottom"
page_number_orientation: "vertical"

# ----- 跳过页（文件名不含扩展名） -----
# "cover,menu" 或列表
skip_pages:
"""


class PrintPanel(StagePanel):
    stage = "print"
    title = "生成 PDF (print)"
    description = (
        "以 YAML 编辑 print 参数（input/output/workers/clean 由系统管理，无需配置）。"
        "左侧列表决定参与生成的图片与顺序。"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.yaml_edit.setPlaceholderText("在此编辑 print 参数（YAML）")

    def build_form(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        buttons = QHBoxLayout()
        init_btn = PushButton("初始化配置")
        init_btn.setToolTip("载入默认参数模板（覆盖当前编辑内容）")
        init_btn.clicked.connect(self.reset_to_default)
        reset_btn = PushButton("重置")
        reset_btn.setToolTip("撤销编辑，恢复到最近一次执行的参数")
        reset_btn.clicked.connect(self.reset_edits)
        buttons.addWidget(init_btn)
        buttons.addWidget(reset_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.yaml_edit = QPlainTextEdit()
        self.yaml_edit.setPlainText(DEFAULT_PRINT_YAML)
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        self.yaml_edit.setFont(font)
        self.yaml_edit.setMinimumHeight(300)
        layout.addWidget(self.yaml_edit, 1)

        self.yaml_status = BodyLabel("")
        layout.addWidget(self.yaml_status)
        return container

    def reset_to_default(self) -> None:
        self.yaml_edit.setPlainText(DEFAULT_PRINT_YAML)
        self.yaml_status.setText("已载入默认模板")

    def reset_edits(self) -> None:
        if getattr(self, "_last_applied", None):
            self.yaml_edit.setPlainText(self._last_applied)
            self.yaml_status.setText("已恢复到最近一次执行的参数")
        else:
            self.reset_to_default()

    def mark_applied(self, parameters: dict) -> None:
        """记录最近一次执行使用的参数（供「重置」恢复）。"""
        self._last_applied = yaml.safe_dump(
            parameters, allow_unicode=True, sort_keys=False
        )

    def get_args(self) -> dict:
        text = self.yaml_edit.toPlainText()
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML 解析失败：{exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("YAML 顶层必须是键值映射")
        for key in _EXCLUDED_KEYS:
            data.pop(key, None)
        # CLI 的 pdf_name 缺省为 None 会直接崩溃，这里兜底
        if not str(data.get("pdf_name") or "").strip():
            data["pdf_name"] = "print.pdf"
        return data

    def _apply_args(self, parameters: dict) -> None:
        self.yaml_edit.setPlainText(
            yaml.safe_dump(parameters, allow_unicode=True, sort_keys=False)
        )
