# -*- coding: utf-8 -*-
"""检测文本框（detect）阶段面板：识别方式 + 人工干预，**没有 area 参数**。

2026-11-16 口径（用户）：

> 一. 「保留框外空白」功能去除
> 二. 改成「识别文本框模式」：自动识别 / 人工标注 两种模式
> 三. 「检测本页」这个功能去除（检测只走底部「检测文本框」/ 主按钮那条批处理）

两种模式的分岔**只有一件事：调不调 YOLO**。

- **自动识别**（``mode="auto"``，默认）：主按钮「检测文本框」照旧跑 YOLO 出框；
  预览区仍然可以手动画框/拖框改结果；
- **人工标注**（``mode="manual"``）：**完全不调 YOLO**——底部不显示「检测文本
  框」，用户自己在每一页画框；
  另外提供「自动使用上一个文本框标注」（默认勾选）：切到一个**还没有任何标注**
  的页面时，把上一个页面的框带过来（已经标注过的页不受影响）。

两种模式共用同一个收尾动作「提交本次任务」（把框裁成图交给下一步）；人工标注
点它时会先检查有没有漏标注的页（见 ``pages/taskdetail/submit.py``）。

⚠️ 两段之间的**距离是固定的**（用户 2026-11-16 第 4 条）：自动识别没有「自动
使用上一个文本框标注」这一行，但那一行的**高度照样空着**，所以切换模式时
「识别文本框模式 / 本页参数」不会坍塌到一起（见 ``REUSE_ROW_HEIGHT``）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from qfluentwidgets import CheckBox, PushButton

from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import DEFAULTS
from desktop.ui import theme as T
from desktop.ui.widgets import (
    CONTROL_HEIGHT,
    SectionTitle,
    SegmentedToggle,
    apply_to,
)
from utils.box_draw import BOX_KIND_INDEX, box_kind_name

#: 框类型分段的项：(类型键, 文案)。键是跨层协议（`utils.box_draw.BOX_KIND_INDEX`），
#: 文案与预览里的框标签同源，不再各写一份中文。
BOX_KIND_ITEMS = tuple((kind, box_kind_name(kind)) for kind in BOX_KIND_INDEX)

#: 识别方式分段的项：(参数值, 文案)。参数值是跨层协议（``store/ui_state``
#: 的 ``DETECT_MODES``），宿主按它分岔，**不要**让它去认中文文案。
MODE_ITEMS = (("auto", "自动识别"), ("manual", "人工标注"))

#: 两种模式各自的一行说明（面板是窄列，一行写完；折行会白占一行高度）
MODE_HINTS = {
    "auto": "调 YOLO 自动出框，可在预览里手改",
    "manual": "不调 YOLO：每页自己画框",
}


#: 两个分组之间的空白高度（px）。
#:
#: 用户 2026-11-16：原来那条 2px 深灰横线"太深了或者太宽了"，改成"把两部分分
#: 一些距离"。加上表单行距（``SPACE_XS``×2）后，两段之间约 24px 纯白——既分得
#: 开，也不至于把窄面板撑高（1366×768 上表单可视区只有约 246px）。
SECTION_GAP = T.SPACE_LG

#: 「自动使用上一个文本框标注」那一行的**固定行高**（px）。
#:
#: 用户 2026-11-16 第 4 条：「……虽然自动识别没有『自动使用上一个文本框标注』
#: 这一行高度，但是也要给我留着空白高度」——自动识别时只把勾选框**藏起来**，
#: 这一行的高度照旧占着，两段的距离于是与人工标注下**完全一致**，切换模式时
#: 面板不会坍塌（用 ``setRowVisible`` 藏整行会连高度一起收掉，那样就会跳）。
REUSE_ROW_HEIGHT = CONTROL_HEIGHT


def _param_label(text: str) -> QLabel:
    """参数名：加粗、独占一行。

    用户 2026-11-11：「保留框外空白这个选项不明显」。它原先挤在 QFormLayout 的
    标签列里（和下面几行的标签同宽同重），看起来像条说明文字；改成加粗独立
    一行后，下面紧跟的整行开关才像"这个参数的取值"。
    """
    label = QLabel(text)
    apply_to(label, T.SIZE_BODY, bold=True, color=T.INK)
    return label


def _spacer(height: int) -> QWidget:
    """固定高度的空行（撑开两段之间的距离）。"""
    widget = QWidget()
    widget.setFixedHeight(int(height))
    return widget


class DetectPanel(StagePanel):
    """检测文本框阶段面板：识别方式 + 人工修正框。

    **人工干预**（用户 2026-09-29 定）：框的类型是**框自己的属性**，不随
    "还剩几个框"变化——

    - 半幅页的左右由**框的中心位置**决定，拖动跨过中线会自动换边；
    - 「整幅」由用户在本面板显式选择，选过之后无论怎么移动/缩放都是整幅；
    - 整幅与左右半幅互斥，且整幅一页只能有一个框（宿主负责提示与拦截）。
    """

    stage = "detect"
    # ⚠️ 标题仍是「检测文本框」：它是**这一步**的名字（步骤条、流程图、运行记录
    #    都用 ``ports.stage_label`` 的那一份）。用户 2026-11-16 说的"改成
    #    『识别文本框』"指的是**这组参数**——即下面那个分组标题。
    title = "检测文本框"
    description = (
        "自动识别：调 YOLO 检测每页的内容框（半幅左右两栏 / 整幅整页），"
        "出框后可在预览里手绘、拖动修正；人工标注：完全不调 YOLO，"
        "每页自己画框（可勾选「自动使用上一个文本框标注」把上一页的框带过来）。"
        "两种方式都用「提交本次任务」把每个文本框裁出来交给下一步——"
        "**提交了这一步才算完成**。"
    )

    # 用户点了某个框类型（键见 BOX_KIND_ITEMS）：切换选中框的类型 / 选中该类框
    box_kind_changed = Signal(str)
    #: 用户点了「删除选中框」
    delete_box_requested = Signal()
    #: 识别方式被切换（**本任务参数**，值为 ``"auto"`` / ``"manual"``）：
    #: 宿主据此显示/隐藏「检测文本框」主按钮、决定提交前要不要查漏标注的页
    mode_changed = Signal(str)
    #: 「自动使用上一个文本框标注」被切换（**本任务参数**，仅人工标注模式有意义）
    reuse_prev_changed = Signal(bool)

    def _build_form(self, form: QFormLayout) -> None:
        # 分组标题用 ``SectionTitle``（与右侧「检测结果统计」同一款：主色短竖线
        # + 加粗小标题）。
        # 参数名一律**加粗独占一行**、控件**铺满整行**：挤在 QFormLayout 的标签
        # 列里太不显眼。
        # ⚠️ 行距比其它面板紧一档（默认 SPACE_SM=8）：这一屏要装「两个分组标题
        # + 两组参数 + 两个按钮」，8px 行距会把「删除选中框」挤进滚动区
        # （1366×768 实测可视区只有 246px）。参数名与它下面的控件本来就该贴紧。
        form.setVerticalSpacing(T.SPACE_XS)
        #: 记下表单（自测要拿它量行/行高）
        self._form = form

        # ---- ① 识别文本框模式（本任务级：两种方式） ----
        #
        # ⚠️ 这一组取代了 2026-11-16 之前的「保留框外空白」（那个功能已整体
        #    移除）。用户原话：「改成『识别文本框模式』：自动识别 / 人工标注」。
        form.addRow(SectionTitle("识别文本框模式"))

        self.mode = SegmentedToggle(MODE_ITEMS)
        self.mode.set_current(str(DEFAULTS[self.stage].get("mode") or "auto"))
        self.mode.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.mode.setToolTip(
            "本任务参数：对本任务的所有页面生效，**不影响其他任务**。\n"
            "· 自动识别：调 YOLO 检测文本框（底部「检测文本框」），"
            "出框后仍可在预览里手绘、拖动、改类型；\n"
            "· 人工标注：**完全不调 YOLO**，底部不显示「检测文本框」，"
            "每页由你自己画框。"
        )
        self.mode.current_changed.connect(self._on_mode_changed)
        form.addRow(self.mode)

        # 当前取值的**文字说明**（两种状态都有文字）：面板是窄列，一行写完
        # （折行会白占一行高度）。
        self.mode_hint = QLabel()
        self.mode_hint.setWordWrap(True)
        apply_to(self.mode_hint, T.SIZE_CAPTION, color=T.INK_SOFT)
        form.addRow(self.mode_hint)

        # 人工标注专属选项（自动识别模式下**只把勾选框藏起来，行高留着**）
        self.reuse_prev = CheckBox("自动使用上一个文本框标注")
        self.reuse_prev.setChecked(bool(DEFAULTS[self.stage].get("reuse_prev", True)))
        self.reuse_prev.setToolTip(
            "仅「人工标注」有效，默认勾选。\n"
            "切到一页**还没有任何标注**的页面时，自动把上一页画的框带过来；\n"
            "已经标注过的页面不受影响（不会被覆盖）。"
        )
        self.reuse_prev.toggled.connect(self.reuse_prev_changed.emit)
        # ⚠️ 用**固定高度的壳**装它，而不是 ``setRowVisible`` 藏整行（用户
        #    2026-11-16 第 4 条）：自动识别下这一行要空出同样的高度，两段的
        #    距离才与人工标注一致，切换模式时不坍塌。
        self.reuse_prev_slot = QWidget()
        self.reuse_prev_slot.setFixedHeight(REUSE_ROW_HEIGHT)
        slot = QVBoxLayout(self.reuse_prev_slot)
        slot.setContentsMargins(0, 0, 0, 0)
        slot.addWidget(self.reuse_prev, 0, Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter)
        form.addRow(self.reuse_prev_slot)

        # 两段之间**只留空白，不画线**（用户 2026-11-16：那条 2px 深灰横线
        # "太深了或者太宽了"）。空白本身就是分组信号，比一条线轻，也不会在
        # 白底上显得像表格边框。
        # ⚠️ 高度**固定**：配合上面那个固定行高的壳，两段距离在任何模式下都一样。
        #    自测（``detect_modes``）钉住这一点。
        self.section_gap = _spacer(SECTION_GAP)
        form.addRow(self.section_gap)

        # ---- ② 本页参数（按页动作 + 人工干预） ----
        form.addRow(SectionTitle("本页参数"))

        form.addRow(_param_label("选中框类型"))
        self.box_kind = SegmentedToggle(BOX_KIND_ITEMS)
        # 未选中任何框时几段**都不高亮**（current 置空串）；此时点任意一段
        # = "选中该类框"（用户要求：点 left/right/full 都算选中）。
        self.box_kind.set_current("")
        self.box_kind.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.box_kind.setToolTip(
            "把选中的框改成左框 / 右框 / 半幅 / 整幅：\n"
            "· 左框、右框按框的中心位置自动判定，拖动跨过中线会换边；\n"
            "· 半幅＝单栏书里那个横跨整页的框（整本书判定，宽≥60%页宽），"
            "它不是左页也不是右页——所以不标左框/右框；\n"
            "· 整幅是整页唯一内容区，选过之后不随位置/大小改变；\n"
            "· 整幅与左右半幅互斥，且整幅一页只能有一个框。\n"
            "「提交本次任务」把每个文本框裁出来。\n"
            "没有选中框时，点这几项＝选中该类型的框。"
        )
        self.box_kind.current_changed.connect(self.box_kind_changed.emit)
        form.addRow(self.box_kind)

        # 删除是危险动作 ⇒ 与「图片拼版」的「删除选中图片」**同一份**样式
        # （`theme.danger_button_qss`，用户 2026-11-16：样式参考那一颗）。
        # ⚠️ 实例样式表会把 qfluent 按钮 qss 整体顶掉 ⇒ 内边距要按 fluent 同款
        #    补（6/7 上下＝补上 fluent 那 1px 边框，高度才与旁边的按钮齐）。
        self.delete_box = PushButton("删除选中框")
        self.delete_box.setStyleSheet(
            T.danger_button_qss(padding="6px 12px 7px 12px")
        )
        # 与面板里其它行同高（qfluent 按钮本身只有 27px 上下，窄面板会更矮）
        self.delete_box.setFixedHeight(CONTROL_HEIGHT)
        self.delete_box.setToolTip("删除当前选中的文本框（也可以用 Delete 键）")
        self.delete_box.clicked.connect(self.delete_box_requested.emit)
        form.addRow(self.delete_box)
        self.set_box_selection(-1, "")

        self._sync_mode_ui()

    # ------------------------------------------------------------------ 参数
    def get_args(self) -> dict:
        """本步骤的参数：``mode``（识别方式）与 ``reuse_prev``（沿用上一页标注）。

        两者都是**任务级**参数（不是系统级）：随本任务的参数落盘在
        ``tasks/<任务号>/ui.json`` 下（``store.save_detect_mode`` /
        ``save_detect_reuse_prev``），任务 A 设成人工标注不会影响任务 B；
        新任务没有记录时回到内置默认（自动识别 + 沿用上一页）。

        ⚠️ 它们**不影响检测结果本身**（框一直在 ``boxes.json`` 里）：
        ``mode`` 只决定调不调 YOLO，``reuse_prev`` 只决定切页时要不要带框。
        """
        return {
            "mode": self.mode.current() or "auto",
            "reuse_prev": bool(self.reuse_prev.isChecked()),
        }

    def _apply_args(self, parameters: dict) -> None:
        mode = default_for(parameters, DEFAULTS[self.stage], "mode")
        self.mode.set_current(mode if mode in ("auto", "manual") else "auto")
        self.reuse_prev.setChecked(
            bool(default_for(parameters, DEFAULTS[self.stage], "reuse_prev"))
        )
        self._sync_mode_ui()
        # ⚠️ 程序化回填也要通知宿主：识别方式决定底部「检测文本框」显不显示，
        #    回填后不刷一次，用户就会看到"面板写着人工标注、底部还挂着检测按钮"。
        #    （``set_current`` 本身不发信号，所以这里显式补一发。）
        self.mode_changed.emit(self.mode.current())

    def _extra_param_signals(self) -> list:
        # SegmentedToggle 不是标准输入控件，基类接不到它的改动信号
        # （reuse_prev 是 QCheckBox 子类，基类已连，别重复连）。
        return [self.mode.current_changed]

    # ------------------------------------------------------------ 识别方式
    def _on_mode_changed(self, key: str) -> None:
        """用户点了「自动识别 / 人工标注」→ 刷本面板的显隐与说明，再通知宿主。

        ⚠️ 转成参数值（"auto"/"manual"）再发：宿主与 ``get_args()`` 用同一套
        语义，别让宿主去认界面文案。
        """
        self._sync_mode_ui()
        self.mode_changed.emit(key if key in ("auto", "manual") else "auto")

    def _sync_mode_ui(self) -> None:
        """按当前识别方式藏/显**控件本身**（行高不变，两段距离才固定）。

        - 自动识别：「自动使用上一个文本框标注」这个勾选框藏起来（**行高留着**，
          见 ``REUSE_ROW_HEIGHT``）；
        - 人工标注：勾选框出现。

        面板里没有「检测本页」（用户 2026-11-16 第 1 条把它整个去掉了），所以
        切换模式只是这一个勾选框在不在，行数、行高都不变——不会坍塌。
        """
        manual = self.mode.current() == "manual"
        self.mode_hint.setText(MODE_HINTS["manual" if manual else "auto"])
        self.reuse_prev.setVisible(manual)

    #: 面板外读现值的一行入口（宿主 ``peek()`` 后调用，避免再解析参数表）
    def is_applying(self) -> bool:
        """当前是不是**程序化回填**（历史/暂存/换任务），而不是用户点击。

        宿主用它决定"要不要把这个值写进 ``tasks/<id>/ui.json``"：回填本身来自
        那份记录（或历史），再写回去只会多一次无意义的落盘，还会在"先复位再
        回填"的时序里短暂写错一次。
        """
        return bool(self._applying)

    def is_manual(self) -> bool:
        """当前是不是「人工标注」模式。"""
        return self.mode.current() == "manual"

    def set_box_selection(self, index: int, kind: str) -> None:
        """回填「选中框类型」控件：``index < 0``（无选中）时三段都不高亮。

        ``set_current`` 是程序化切换、**不发** ``current_changed``，因此不会
        反过来再触发一次类型切换（否则会自我递归）。

        未选中框时三段仍保持可点：点类型即"选中该类型的框"（用户要求 6）。
        """
        self.box_kind.set_current(kind if index >= 0 else "")
        self.delete_box.setEnabled(index >= 0)
