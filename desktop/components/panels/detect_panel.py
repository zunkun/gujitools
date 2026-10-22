# -*- coding: utf-8 -*-
"""检测文本框（detect）阶段面板：只有检测与人工干预，**没有 area 参数**。

⚠️ 2026-10-22 第二轮（用户口径）：

> 检测文本框流程，去除 area 参数，默认 area = 1，提交的时候 area 参数只在
> 提交的时候生效，desktop 页面去除这个参数，但是在后端代码保留 area 相关逻辑，
> 只是页面默认 area = 1。

所以这一步现在还是**两个动作**，但 area 不再出现在界面上：

- 「检测文本框」（详情页主按钮）：只跑检测，出框到 ``boxes.json``；
- 「提交本次任务」（详情页次按钮）：按 ``DETECT_DEFAULT_AREA``（=1，左右分开）
  把页面图裁成下一步要的图，落到 ``stages/detect``。**没提交就不算这一步完成**
  ——下一步的输入目录是空的。

裁图的 area 逻辑原样留在后端（``stages/detect_stage``、``services/print_plan``、
``utils.box_geometry``、CLI ``crop/cropremove``），桌面只把常量当默认值传下去。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout

from qfluentwidgets import PrimaryPushButton, PushButton

from desktop.components.panels.base import StagePanel
from desktop.ui.widgets import CONTROL_HEIGHT, SegmentedToggle
from utils.box_draw import BOX_KIND_INDEX, box_kind_name

#: 框类型分段的项：(类型键, 文案)。键是跨层协议（`utils.box_draw.BOX_KIND_INDEX`），
#: 文案与预览里的框标签同源，不再各写一份中文。
BOX_KIND_ITEMS = tuple((kind, box_kind_name(kind)) for kind in BOX_KIND_INDEX)


class DetectPanel(StagePanel):
    """检测文本框阶段面板：检测 + 人工修正框（无表单参数）。

    YOLO 检测每张图的内容框坐标（半幅：左右两栏；整幅：整页单一内容区），
    供预览标注与「提交本次任务」的裁图使用。

    **人工干预**（用户 2026-09-29 定）：框的类型是**框自己的属性**，不随
    "还剩几个框"变化——

    - 半幅页的左右由**框的中心位置**决定，拖动跨过中线会自动换边；
    - 「整幅」由用户在本面板显式选择，选过之后无论怎么移动/缩放都是整幅；
    - 整幅与左右半幅互斥，且整幅一页只能有一个框（宿主负责提示与拦截）。
    """

    stage = "detect"
    title = "检测文本框"
    description = (
        "自动检测每张图的内容框坐标（半幅左右两栏 / 整幅整页）。"
        "「检测文本框」只出框、可在图上手绘修正；"
        "确认后点「提交本次任务」按左右分开把图裁好交给下一步——"
        "**提交了这一步才算完成**。"
    )

    # 手动触发当前页检测（重负载：检测子进程，不自动执行）
    detect_page_requested = Signal()
    #: 用户点了某个框类型（键见 BOX_KIND_ITEMS）：切换选中框的类型 / 选中该类框
    box_kind_changed = Signal(str)
    #: 用户点了「删除选中框」
    delete_box_requested = Signal()

    def _build_form(self, form: QFormLayout) -> None:
        button = PrimaryPushButton("检测本页")
        # 与其它阶段面板的表单控件同高（qfluent 按钮默认只有 27px）
        button.setFixedHeight(CONTROL_HEIGHT)
        button.setToolTip("对当前选中的页面执行一次检测文本框（需加载检测模型，耗时较长）")
        button.clicked.connect(self.detect_page_requested.emit)
        form.addRow(button)

        # ---- 人工干预：选中框类型 / 删除选中框 ----
        self.box_kind = SegmentedToggle(BOX_KIND_ITEMS)
        # 未选中任何框时几段**都不高亮**（current 置空串）；此时点任意一段
        # = "选中该类框"（用户要求：点 left/right/full 都算选中）。
        self.box_kind.set_current("")
        self.box_kind.setToolTip(
            "把选中的框改成左框 / 右框 / 半框 / 整幅：\n"
            "· 左框、右框按框的中心位置自动判定，拖动跨过中线会换边；\n"
            "· 半框＝单栏书里那个横跨整页的框（整本书判定，宽≥80%页宽），"
            "它不是左页也不是右页——所以不标左框/右框；\n"
            "· 整幅是整页唯一内容区，选过之后不随位置/大小改变；\n"
            "· 整幅与左右半框互斥，且整幅一页只能有一个框。\n"
            "「提交本次任务」按左右分开裁图。\n"
            "没有选中框时，点这几项＝选中该类型的框。"
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
        """本步骤**没有表单参数**（area 归后端固定默认，界面上不暴露）。

        ⚠️ 不要在这里补 ``{"area": 1}`` 之类的"友好默认"：那会写进运行历史、
        变成一份用户"填过"的参数（历史回填与提交版本判定都会跟着变），而用户
        明确要求这个参数不出现在页面上。取默认值的地方只有一个：
        ``core.command_spec.DETECT_DEFAULT_AREA``（runner 与提交控制器读它）。
        """
        return {}

    def _apply_args(self, parameters: dict) -> None:
        pass

    def set_box_selection(self, index: int, kind: str) -> None:
        """回填「选中框类型」控件：``index < 0``（无选中）时三段都不高亮。

        ``set_current`` 是程序化切换、**不发** ``current_changed``，因此不会
        反过来再触发一次类型切换（否则会自我递归）。

        未选中框时三段仍保持可点：点类型即"选中该类型的框"（用户要求 6）。
        """
        self.box_kind.set_current(kind if index >= 0 else "")
        self.delete_box.setEnabled(index >= 0)
