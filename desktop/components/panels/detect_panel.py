# -*- coding: utf-8 -*-
"""检测文本框（detect）阶段面板：检测、保留框外空白与人工干预，**没有 area 参数**。

2026-10-22 口径（用户）：

> 移除所有 area 相关代码，不再有 area；识别出文本框后，把文本框裁剪出来。

所以这一步现在是**两个动作**，但 area 已从整个项目移除：

- 「检测文本框」（详情页主按钮）：只跑检测，出框到 ``boxes.json``；
- 「提交本次任务」（详情页次按钮）：把每个检测框各自裁成一张图
  （半幅页 ``-l``/``-r``，整幅页用页名），落到 ``stages/detect``。
  **没提交就不算这一步完成**——下一步的输入目录是空的。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QSizePolicy, QWidget

from qfluentwidgets import PrimaryPushButton, PushButton

from desktop.components.panels.base import StagePanel, default_for
from desktop.components.panels.params_spec import DEFAULTS
from desktop.ui import theme as T
from desktop.ui.widgets import (
    CONTROL_HEIGHT,
    Divider,
    SectionTitle,
    SegmentedToggle,
    apply_to,
)
from utils.box_draw import BOX_KIND_INDEX, box_kind_name

#: 框类型分段的项：(类型键, 文案)。键是跨层协议（`utils.box_draw.BOX_KIND_INDEX`），
#: 文案与预览里的框标签同源，不再各写一份中文。
BOX_KIND_ITEMS = tuple((kind, box_kind_name(kind)) for kind in BOX_KIND_INDEX)


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
    """检测文本框阶段面板：检测 + 保留框外空白 + 人工修正框。

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
        "「保留框外空白」是**本任务**口径：决定预览里画出来的框与提交裁图"
        "是否带上框外空白（不改检测结果本身，也**不影响别的任务**）；"
        "确认后点「提交本次任务」把每个文本框裁出来交给下一步——"
        "**提交了这一步才算完成**。"
    )

    # 手动触发当前页检测（重负载：检测子进程，不自动执行）
    detect_page_requested = Signal()
    #: 用户点了某个框类型（键见 BOX_KIND_ITEMS）：切换选中框的类型 / 选中该类框
    box_kind_changed = Signal(str)
    #: 用户点了「删除选中框」
    delete_box_requested = Signal()
    #: 「保留框外空白」被用户切换（**本任务参数**）：宿主据此重算本任务所有页面的划线
    keep_blank_changed = Signal(bool)

    def _build_form(self, form: QFormLayout) -> None:
        # 分组标题用 ``SectionTitle``（与右侧「检测结果统计」同一款：主色短竖线
        # + 加粗小标题），用户 2026-11-11 指定按那个样式分两段。
        # ⚠️ 分组名是「本任务参数」不是「全局参数」（用户 2026-11-12）：
        #    这个开关**只属于当前任务**（存 tasks/<任务号>/drafts/…，任务A 的
        #    设置不影响任务B，默认「不保留」）。写成"全局"会被读成"整个软件
        #    一个开关"，正好是用户明确否认的那个语义。
        # 参数名一律**加粗独占一行**、控件**铺满整行**：挤在 QFormLayout 的标签
        # 列里太不显眼（用户原话"保留框外空白这个选项不明显"）。
        #
        # ⚠️ 行距比其它面板紧一档（默认 SPACE_SM=8）：这一屏要装「两个分组标题
        # + 两个参数名 + 两个开关 + 两个按钮」，8px 行距会把「删除选中框」挤进
        # 滚动区（1366×768 实测可视区只有 246px）。参数名与它下面的控件本来就
        # 该贴紧——它们是"一对"；"分组"由标题 + 分隔线负责，不靠均匀行距。
        form.setVerticalSpacing(T.SPACE_XS)

        # ---- ① 本任务参数 ----
        #
        # ⚠️ 它在**最上面**、与「检测本页 / 人工干预」分成两段（用户 2026-11-11）：
        #    它不是"给本页检测用的参数"，而是对**本任务所有页面**都生效的
        #    显示/裁图口径，混在「检测本页」下面会被当成按页设置的开关。
        form.addRow(SectionTitle("本任务参数"))
        form.addRow(_param_label("保留框外空白"))

        self.keep_blank = SegmentedToggle((("keep", "保留"), ("tight", "不保留")))
        self.keep_blank.set_current(
            "keep" if bool(DEFAULTS[self.stage].get("keep_blank")) else "tight"
        )
        # 铺满整行：两段各占一半宽度，一眼看得出是两个互斥选项
        self.keep_blank.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.keep_blank.setToolTip(
            "本任务参数：对本任务的所有页面生效，**不影响其他任务**"
            "（默认「不保留」，改完由本任务记住）。\n"
            "决定预览里画出来的框与「提交本次任务」怎么裁图。\n"
            "**不改检测结果本身**（检测框一直在 boxes.json 里，切回「不保留」即还原）。\n"
            "· 不保留：每个检测框各裁一张；\n"
            "· 保留：左右双框以两框相邻边界的中点分界，左右各一张整页高的图；\n"
            "  单框以框的**内侧边**分界，另一侧同样留白；\n"
            "  整幅页/单栏页整页一张；无框页不处理。\n"
            "保留时预览上画的就是**要裁的整页左右两半**，可以直接拖动它的边/角\n"
            "来调分界和大小（手拉过的值记在 boxes.json 的 blank）。\n"
            "想回到自动：重新「检测本页」即可。"
        )
        self.keep_blank.current_changed.connect(self._on_keep_blank_toggled)
        form.addRow(self.keep_blank)

        # 当前取值的**文字说明**（两种状态都有，用户 2026-11-12：「不保留也要
        # 有文字说明」）。一行写完，折行会白占一行高度（面板是窄列）。
        self.keep_blank_hint = QLabel()
        self.keep_blank_hint.setWordWrap(True)
        apply_to(self.keep_blank_hint, T.SIZE_CAPTION, color=T.INK_SOFT)
        form.addRow(self.keep_blank_hint)
        self._sync_keep_blank_hint()

        # 两段之间的界：留白 + 一条**看得见**的分隔线。
        # ⚠️ 面板底色是浅灰（表单滚动区约 #EFEFEF），浅灰线在上面根本看不出
        #    （用户 2026-11-11 连提两次"分割线要清晰"）⇒ 用专门为浅灰底配的
        #    ``T.SEPARATOR`` + 2px 厚度，粗细本身就把"两段"这件事说清楚。
        # 留白只给 SPACE_XS：面板是窄列，删除按钮不能被挤到滚动区外面去。
        form.addRow(_spacer(T.SPACE_XS))
        form.addRow(Divider(color=T.SEPARATOR, thickness=2))
        form.addRow(_spacer(T.SPACE_XS))

        # ---- ② 本页参数（按页动作 + 人工干预） ----
        form.addRow(SectionTitle("本页参数"))
        button = PrimaryPushButton("检测本页")
        # 与其它阶段面板的表单控件同高（qfluent 按钮默认只有 27px）
        button.setFixedHeight(CONTROL_HEIGHT)
        button.setToolTip("对当前选中的页面执行一次检测文本框（需加载检测模型，耗时较长）")
        button.clicked.connect(self.detect_page_requested.emit)
        form.addRow(button)

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

        self.delete_box = PushButton("删除选中框")
        self.delete_box.setFixedHeight(CONTROL_HEIGHT)
        self.delete_box.setToolTip("删除当前选中的文本框（也可以用 Delete 键）")
        self.delete_box.clicked.connect(self.delete_box_requested.emit)
        form.addRow(self.delete_box)
        self.set_box_selection(-1, "")

    def get_args(self) -> dict:
        """本步骤唯一的参数：``keep_blank``（保留框外空白，默认 False）。

        它是**任务级**参数（不是系统级）：随本任务的参数暂存/历史落盘在
        ``tasks/<任务号>/`` 下，任务 A 设成「保留」不会影响任务 B；
        新任务没有暂存也没有历史时回到内置默认（不保留）。

        两处生效、都不改检测结果本身：

        - 预览里画出来的框（宿主 ``DetectMixin._apply_boxes`` 换算成扩展框）；
        - 「提交本次任务」的裁图几何（``print_plan._keep_blank_entries``）。

        检测运行的参数里也存一份，便于历史回填与提交版本判定。

        ⚠️ 不要在这里补 ``{"area": 1}`` 之类的"友好默认"：area 已从整个项目
        移除，补回去会让运行历史与提交版本判定多出一个不存在的参数。
        """
        return {"keep_blank": self.keep_blank.current() == "keep"}

    def _apply_args(self, parameters: dict) -> None:
        keep = bool(default_for(parameters, DEFAULTS[self.stage], "keep_blank"))
        self.keep_blank.set_current("keep" if keep else "tight")
        self._sync_keep_blank_hint()

    def _extra_param_signals(self) -> list:
        # SegmentedToggle 不是标准输入控件，基类接不到它的改动信号。
        return [self.keep_blank.current_changed]

    # --------------------------------------------------- 保留框外空白（本任务）
    def _on_keep_blank_toggled(self, key: str) -> None:
        """用户点了「保留 / 不保留」→ 刷本面板的状态说明，再通知宿主重算划线。

        ⚠️ 转成 ``bool`` 再发：宿主与 ``get_args()`` 用的是同一个语义（``keep_blank``
        ＝True 表示保留），别让宿主去认 "keep"/"tight" 这两个界面文案键。
        """
        self._sync_keep_blank_hint()
        self.keep_blank_changed.emit(key == "keep")

    def _sync_keep_blank_hint(self) -> None:
        """按当前选择刷新说明行（**两种状态都有文字**，用户 2026-11-12）。

        一行装得下的写法：面板是窄列，折成两行会白占一行高度（删除按钮就会
        被挤进滚动区）。措辞只讲"裁什么"，因为框现在**两种模式都能改**。
        """
        hint = getattr(self, "keep_blank_hint", None)
        if hint is None:
            return
        hint.setText(
            "整页左右两半各裁一张，框可直接拖动调整"
            if self.keep_blank.current() == "keep"
            else "每个检测框各裁一张，只裁框本身"
        )

    def set_box_selection(self, index: int, kind: str) -> None:
        """回填「选中框类型」控件：``index < 0``（无选中）时三段都不高亮。

        ``set_current`` 是程序化切换、**不发** ``current_changed``，因此不会
        反过来再触发一次类型切换（否则会自我递归）。

        未选中框时三段仍保持可点：点类型即"选中该类型的框"（用户要求 6）。
        """
        self.box_kind.set_current(kind if index >= 0 else "")
        self.delete_box.setEnabled(index >= 0)
