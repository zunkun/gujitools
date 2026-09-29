# -*- coding: utf-8 -*-
"""检测文本框（detect）阶段面板：本阶段只识别坐标，不生成文件。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout
from qfluentwidgets import CheckBox, PrimaryPushButton, PushButton

from desktop.components.panels.base import StagePanel
from desktop.ui.widgets import CONTROL_HEIGHT, SegmentedToggle
from utils.box_draw import BOX_KIND_INDEX, box_kind_name

#: 框类型分段的项：(类型键, 文案)。键是跨层协议（`utils.box_draw.BOX_KIND_INDEX`），
#: 文案与预览里的框标签同源，不再各写一份中文。
BOX_KIND_ITEMS = tuple(
    (kind, box_kind_name(kind)) for kind in BOX_KIND_INDEX
)


class DetectPanel(StagePanel):
    """检测文本框阶段面板：仅识别坐标，不生成文件。

    YOLO 检测每张图的内容框坐标（半幅：左右两栏；整幅：整页单一内容区），
    供预览标注与去底色/裁剪使用；
    本阶段无表单参数，get_args 返回空字典，手动检测经信号触发。

    「整页模式」是第三步 area=4 的入口开关：勾选后整页即唯一文本框，
    **不加载也不调用 YOLO**，预览里框画在页面边界，仍可手动拖动/重画。

    **人工干预**（用户 2026-09-29 定）：框的类型是**框自己的属性**，不随
    "还剩几个框"变化——

    - 半幅页的左右由**框的中心位置**决定，拖动跨过中线会自动换边；
    - 「整幅」由用户在本面板显式选择，选过之后无论怎么移动/缩放都是整幅；
    - 整幅与左右半幅互斥，且整幅一页只能有一个框（宿主负责提示与拦截）。
    """

    stage = "detect"
    title = "检测文本框"
    description = (
        "自动检测每张图的内容框坐标（半幅左右两栏 / 整幅整页），"
        "用于预览标注与去底色/裁剪区域。本阶段只识别坐标，不生成文件。"
        "普通文档/检测失败可勾选「整页模式」，整页作为一个文本框，跳过检测。"
        "选中某个框后可在「选中框类型」里把它改成左框/右框/整幅。"
    )

    # 手动触发当前页检测（重负载：检测子进程，不自动执行）
    detect_page_requested = Signal()
    # 整页模式开关（等价于第三步的「整页」区域）
    whole_page_toggled = Signal(bool)
    #: 用户点了某个框类型（键见 BOX_KIND_ITEMS）：切换选中框的类型 / 选中该类框
    box_kind_changed = Signal(str)
    #: 用户点了「删除选中框」
    delete_box_requested = Signal()

    def _build_form(self, form: QFormLayout) -> None:
        self.whole_page = CheckBox("整页模式：不做检测")
        self.whole_page.setToolTip(
            "整页作为一个文本框（与第三步「区域模式」里的整页是同一件事）："
            "跳过检测，预览里的框画在页面边界，可继续拖动/重画。"
            "适合普通文档或古籍检测失败时"
        )
        self.whole_page.toggled.connect(self.whole_page_toggled.emit)
        form.addRow(self.whole_page)

        button = PrimaryPushButton("检测本页")
        # 与其它阶段面板的表单控件同高（qfluent 按钮默认只有 27px）
        button.setFixedHeight(CONTROL_HEIGHT)
        button.setToolTip("对当前选中的页面执行一次文本框检测（需加载检测模型，耗时较长）")
        button.clicked.connect(self.detect_page_requested.emit)
        form.addRow(button)

        # ---- 人工干预：选中框类型 / 删除选中框 ----
        self.box_kind = SegmentedToggle(BOX_KIND_ITEMS)
        # 未选中任何框时三段**都不高亮**（current 置空串）；此时点任意一段
        # = "选中该类框"（用户要求：点 left/right/full 都算选中）。
        self.box_kind.set_current("")
        self.box_kind.setToolTip(
            "把选中的框改成左框 / 右框 / 整幅：\n"
            "· 左框、右框按框的中心位置自动判定，拖动跨过中线会换边；\n"
            "· 整幅是整页唯一内容区，选过之后不随位置/大小改变；\n"
            "· 整幅与左右半幅互斥，且整幅一页只能有一个框。\n"
            "没有选中框时，点这三项＝选中该类型的框。"
        )
        self.box_kind.current_changed.connect(self.box_kind_changed.emit)
        kind_row = QHBoxLayout()
        kind_row.setContentsMargins(0, 0, 0, 0)
        kind_row.addWidget(self.box_kind)
        kind_row.addStretch(1)
        form.addRow("选中框类型", kind_row)

        self.delete_box = PushButton("删除选中框")
        self.delete_box.setFixedHeight(CONTROL_HEIGHT)
        self.delete_box.setToolTip("删除当前选中的文本框（也可以用 Delete 键）")
        self.delete_box.clicked.connect(self.delete_box_requested.emit)
        form.addRow(self.delete_box)
        self.set_box_selection(-1, "")

    def get_args(self) -> dict:
        """返回空参数字典（detect 阶段无表单参数）。

        整页模式不在这里上报：area 归第三步 rembg 面板所有，本开关只负责
        把 area 切到 4 / 切回 1（见宿主的 _set_whole_page_mode）。
        """
        return {}

    def _apply_args(self, parameters: dict) -> None:
        pass

    def set_whole_page(self, on: bool) -> None:
        """外部（第三步 area）回填勾选状态；blockSignals 避免回抛造成循环。"""
        if self.whole_page.isChecked() == bool(on):
            return
        self.whole_page.blockSignals(True)
        self.whole_page.setChecked(bool(on))
        self.whole_page.blockSignals(False)

    def set_box_selection(self, index: int, kind: str) -> None:
        """回填「选中框类型」控件：``index < 0``（无选中）时三段都不高亮。

        ``set_current`` 是程序化切换、**不发** ``current_changed``，因此不会
        反过来再触发一次类型切换（否则会自我递归）。

        未选中框时三段仍保持可点：点类型即"选中该类型的框"（用户要求 6）。
        """
        self.box_kind.set_current(kind if index >= 0 else "")
        self.delete_box.setEnabled(index >= 0)
