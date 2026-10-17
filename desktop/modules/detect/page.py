# -*- coding: utf-8 -*-
"""「检测文本框」独立模块页：与任务流程无关，选一批图片直接检测内容框。

**复用共用组件**（``desktop/steps``）：页头下方横跨整幅的**大输入区**（拖图片 /
拖文件夹 / 点选），右栏是 :class:`StepControl`（输出目录 + 执行/中断），执行走
``StepKernel`` → ``functions.get_function("detect")``——与任务流程第二步是同一条
代码路径。

**和别的模块页最大的不同：这一步的产物不是文件，是坐标。**

``detect`` 默认不落盘（``--save`` 关着），框只经 ``page_boxes`` 结构化事件回来
（见 ``functions.detect.DetectFunction._report_boxes``）。所以：

1. 内核必须把**非 progress/log 的事件**原样透传上来（``StepKernel.event``，
   2026-10-02 补的通道）——改造前它只转进度和日志，这一步的结果到不了界面；
2. 本页把每页的框收在内存里（``self._boxes``，键 = 文件名去后缀），左栏用共享
   查看器把框画在图上，用户可直接**手绘 / 拖动 / 缩放手柄 / Delete** 修正；
3. 交付有两条路（用户 2026-10-03 定的）：
   - 「**导出标注图**」：把框画回原图写成 PNG，一眼能核对框对不对；
   - 「**导出坐标 JSON**」：写 ``<输出目录>/boxes.json``，格式与任务流程的
     ``tasks/<id>/boxes.json`` **逐字段一致**（``{stem: {boxes, origin,
     updated_at}}``），可直接当作下一步（或将来自定义流程里任意一步）的输入。

4. **开发者模式**打开且「启用YOLO标注」勾上时，导出区最底部多一个
   「**导出YOLO标注**」（用户 2026-10-16）：点它先弹窗填**名称**（父节点名 =
   文件名前缀）并选**导出目录**（按子任务记住上次选的），确认后把全部页面
   导出成 YOLO 数据集切片 ``<导出目录>/<名称>/{images,labels}/<名称>-1.…``
   （类别顺序见 ``utils.box_geometry.YOLO_CLASS_NAMES``；无框页写空标签当负样本）。

⚠️ **槽位约定**（半幅 2 槽 ``[左, 右]``、整幅 1 槽 ``[整幅]``）的全部规则来自
``utils.box_geometry``（``page_box_slots_from_event`` 读事件、``half_slots`` 收
人工框），人工干预的**交互流**（切类型 / 整幅互斥确认 / 删框）在
``desktop.components.box_kinds.BoxKindEditor``（与任务流程第二步共用一份），
本页不自己数"还剩几个框"——按个数推类型会造成"删掉整幅框后右边的框自动变成
整幅"（用户 2026-09-29 报过的老问题）。

⚠️ **框类型控件摆在这里、检测按钮不搬过来**（用户 2026-10-03）：
- 「选中框类型 / 删除选中框」**摆出来**并接线——它们只依赖查看器，本页完全
  驱动得了，而用户要的"手绘之后能标成左框/右框/整幅"正需要它们；
- ``DetectPanel`` 里的「整页模式」与「检测本页」**不摆**：前者切的是**第三步**
  的 area（单文件模式没有下游），后者由任务流程宿主用子进程驱动单页检测，
  本页的执行入口是整批的 :class:`StepControl`。留着就是两个点不动的死控件。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import CaptionLabel, FluentIcon as FIF
from qfluentwidgets import PrimaryPushButton, PushButton

from desktop.components.box_kinds import BoxKindEditor
from desktop.components.progress_row import ProgressRow
from desktop.components.viewers import ImageViewerWidget
from desktop.components.viewers.image_view import box_names
from desktop.components.yolo_export_dialog import ask_yolo_export
from desktop.modules.base import StepModulePage
from desktop.modules.thumb_source import ThumbSourceMixin
from desktop.services.detect_export import (
    entries_from_mapping,
    export_annotated,
    export_yolo,
    yolo_entries,
)
from desktop.settings.config import app_config
from desktop.steps import (
    StepKernel,
    StepRequest,
    callable_job,
    spec_by_key,
)
from desktop.store.json_io import read_json, write_json
from desktop.ui import theme as T
from desktop.ui.widgets import CONTROL_HEIGHT, Card, SectionTitle, apply_to
from desktop.utils.files import (
    default_open_dir,
    reveal_dir,
    singletask_yolo_export_path,
)
from utils.book_layout import is_single_wide_half, profile_book
from utils.box_draw import BOX_KIND_INDEX, box_kind_name
from utils.box_geometry import (
    YOLO_CLASS_NAMES,
    half_slots,
    is_full_content,
    page_box_slots_from_event,
)

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("detect")

#: 导出文件名。⚠️ 与任务流程 ``tasks/<id>/boxes.json`` **同名**是刻意的：
#: 用户拿它跟任务里的那份对照/替换时不必换算名字，格式也是同一套。
EXPORT_NAME = "boxes.json"

#: 导出执行线的两条**产物形态**：同一个 ``_export_kernel`` 按
#: ``request.args["kind"]`` 分派（见 :meth:`_export_job`）。
_EXPORT_ANNOTATED = "annotated"
_EXPORT_YOLO = "yolo"

#: 本页「导出YOLO标注」记忆文件里的两个键（与 ``store.ui_state`` 那份同名同义，
#: 但不是同一个文件：那边按任务记在 ``ui.json`` 里，这边按子任务单独一份）。
_YOLO_EXPORT_DIR_KEY = "yolo_export_dir"
_YOLO_EXPORT_NAME_KEY = "yolo_export_name"


class DetectModulePage(StepModulePage, ThumbSourceMixin):
    """检测文本框模块页：拖入图片 → 检测内容框 → 图上修正 → 导出坐标 JSON。"""

    SPEC = _SPEC

    def __init__(self, parent=None):
        """建骨架、共用步骤控件与内存中的框表。"""
        #: 文件名去后缀 → **槽位表示**（半幅 2 槽 / 整幅 1 槽）。
        #: 与任务流程同构：不在内存里存"用户画了几个框"，只存槽位。
        self._boxes: dict[str, list] = {}
        #: 用户在半框页上**指定**的左右：``{stem: "left"|"right"}``。
        #: 半框的框横跨整页、中心压在中线上，位置判定没意义，所以由用户指定
        #: （用户 2026-10-17）。本页不落盘这些框，故只存内存。
        self._sides: dict[str, str] = {}
        #: 页宽缓存 ``{stem: 宽}``：整本书判据要逐页宽度，而 ``_image_size`` 走
        #: ``QImageReader`` 读文件头——每次重建判定都重读一遍是白花开销。
        self._widths: dict[str, int] = {}
        #: 同上，键 → "auto"（检测来的）/ "manual"（用户改过）。
        #: 与任务流程一样，人工框不被后续自动检测覆盖。
        self._origins: dict[str, str] = {}
        #: 导出标注图的结果：文件名列表（job 在 worker 线程里写、主线程读）
        self._exported: list[str] = []
        #: 当前这条导出线的产物形态（``_EXPORT_ANNOTATED`` / ``_EXPORT_YOLO``），
        #: 由 :meth:`_begin_export` 置位、收尾回调据此写不同的状态文案。
        self._export_kind = _EXPORT_ANNOTATED
        #: YOLO 导出 job 的统计（见 ``detect_export.export_yolo`` 的返回值）
        self._yolo_summary: dict = {}
        #: 应用配置（开发者模式 / YOLO 标注两个开关，见 desktop.settings.config）
        self.cfg = app_config()
        super().__init__(parent)

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImageViewerWidget:
        """左栏：图片查看器（复用共享控件），框可编辑所以能在图上直接修正。"""
        self.viewer = ImageViewerWidget(
            editable=False,          # 不做页面增删（那是任务流程第一步的事）
            show_boxes=True,         # 框可手绘/拖动/缩放/Delete
            empty_hint="还没有图片——先拖入图片或图片文件夹",
        )
        self.viewer.current_changed.connect(self._on_page_changed)
        self.viewer.boxes_edited.connect(self._on_boxes_edited)
        self.viewer.box_edit_rejected.connect(
            lambda message: self.toast("warning", "这个框改不了", message)
        )
        # 选中态 → 回填右栏「选中框类型」与删除按钮（任务流程第二步同一条链）
        self.viewer.selection_changed.connect(self._on_selection_changed)
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：共用步骤控件 + 框类型控件 + 两个导出按钮。

        ⚠️ 在 :class:`StepModulePage` 的通用控制区之外**再加两段**（本页特有）：
        手绘修正的框类型控件与两个导出出口。共用的那部分（输入区接线、状态/日志/
        失败提示、源变了怎么改副标题）由基类负责，本方法只做加法。
        """
        card = super()._build_control()
        #: 步骤私有事件：这一步的产物（每页框坐标）就是从这里上来的。
        self.control.event.connect(  # type: ignore[reportAttributeAccessIssue]  # ``event`` 与 QObject.event 同名，运行时是 Signal
            self._on_step_event
        )
        if self.control.panel is not None:
            # 面板的控件全由任务流程宿主驱动，本页接管不了（见模块 docstring）：
            # 「整页模式」切的是第三步 area，「检测本页」要子进程单页检测。
            # 里面**唯一**该搬出来的是「选中框类型 / 删除选中框」，本方法
            # 单独重建这两个（下面的 _build_box_kind_controls），不搬整个面板。
            self.control.panel.setVisible(False)
        card.box.addWidget(self._build_box_kind_controls())
        card.box.addWidget(self._build_export_buttons())

        # 导出（标注图 / YOLO 标签）走**另一条**执行内核：它是纯函数 job
        # （画框 / 写标签 + 落盘），与 detect 的命令 job 互不干扰——用户可以在
        # 检测跑完后再导出，两次执行不抢同一个槽位，也不会因为 detect 失败而
        # 不能导出。
        # ⚠️ 两种导出**共用**这一条线（job 按 ``request.args["kind"]`` 分派）：
        #    它们都是"把已有框落盘"的短活，并行没有意义，各占一条进度行反而让
        #    用户看不出是哪条在跑。
        self._export_kernel = StepKernel(callable_job(self._export_job), self)
        self._export_kernel.log.connect(self.log)
        self._export_kernel.progress.connect(self._on_export_progress)
        self._export_kernel.finished.connect(self._on_export_finished)
        self._export_kernel.failed.connect(self._on_export_failed)

        # ⚠️ 导出标注图是本页的**第二条执行线**（另一条是 detect 本身，走
        #    ``StepControl``），两者能同时跑（用户可以边检测边导出上一批的框）。
        #    所以它要**自己一条**进度行，不能借用 control 那条——共用的话两边的
        #    进度会互相覆盖，用户看到"12/30"却不知道是谁在跑。
        self.export_progress = ProgressRow(noun="张")
        card.box.addWidget(self.export_progress)
        return card

    def _build_box_kind_controls(self) -> Card:
        """「选中框类型（左框/右框/整幅）」+「删除选中框」。

        ⚠️ 为什么不复用 ``DetectPanel``：那个面板还带「整页模式」（切第三步
        area）与「检测本页」（任务流程的子进程单页检测），单文件模式下都没有
        对应宿主；只把这两个控件的**声明**搬过来（``BOX_KIND_ITEMS`` 仍取自
        ``utils.box_draw``，文案不另写一份），接线由本页负责。
        """
        from desktop.ui.widgets import SegmentedToggle

        holder = Card(padding=T.SPACE_SM, spacing=T.SPACE_XS, radius=T.RADIUS_SM)
        holder.box.addWidget(SectionTitle("手绘修正"))
        tip = CaptionLabel("在图上拖动空白处画新框；拖框移动、拖角缩放、Delete 删除")
        tip.setWordWrap(True)
        apply_to(tip, T.SIZE_CAPTION, color=T.INK_FAINT)
        holder.box.addWidget(tip)

        self.box_kind = SegmentedToggle(
            tuple((kind, box_kind_name(kind)) for kind in BOX_KIND_INDEX)
        )
        # 没选中框时三段都不高亮；点任意一段 = "选中该类框"（与任务流程同口径）
        self.box_kind.set_current("")
        self.box_kind.setToolTip(
            "把选中的框改成左框 / 右框 / 整幅：\n"
            "· 左框、右框由框的中心位置自动判定，拖过中线会换边；\n"
            "· 整幅是整页唯一内容区，选过之后不随位置/大小改变；\n"
            "· 整幅与左右半幅互斥，且整幅一页只能有一个框。\n"
            "没有选中框时，点这三项＝选中该类型的框。"
        )
        self.box_kind.current_changed.connect(self._on_box_kind_changed)
        holder.box.addWidget(self.box_kind)

        self.delete_box = PushButton("删除选中框")
        self.delete_box.setFixedHeight(CONTROL_HEIGHT)
        self.delete_box.setToolTip("删除当前选中的文本框（也可以用 Delete 键）")
        self.delete_box.clicked.connect(self._delete_selected_box)
        self.delete_box.setEnabled(False)
        holder.box.addWidget(self.delete_box)
        return holder

    def _build_export_buttons(self) -> Card:
        """三个交付出口（前两个是用户 2026-10-03 定的两条路，第三个是 2026-10-16 的 YOLO 标注）。"""
        holder = Card(padding=T.SPACE_SM, spacing=T.SPACE_XS, radius=T.RADIUS_SM)
        holder.box.addWidget(SectionTitle("导出"))

        self.annotated_button = PrimaryPushButton(FIF.PHOTO, "导出标注图")
        self.annotated_button.setFixedHeight(34)
        self.annotated_button.setToolTip(
            "把框画回原图导出成 PNG（一眼核对框对不对）；"
            "会让你选输出目录，目录已存在时询问是否覆盖"
        )
        self.annotated_button.setEnabled(False)
        self.annotated_button.clicked.connect(self.export_annotated_images)
        holder.box.addWidget(self.annotated_button)

        self.export_button = PushButton(FIF.SAVE_AS, "导出坐标 JSON")
        self.export_button.setFixedHeight(34)
        self.export_button.setToolTip(
            f"把各页框坐标写成 {EXPORT_NAME}（与任务流程同格式）"
        )
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_boxes)
        holder.box.addWidget(self.export_button)

        # ---- YOLO 标注（开发者模式专属，摆在导出区**最底部**）----
        self.yolo_button = PushButton(FIF.TAG, "导出YOLO标注")
        self.yolo_button.setFixedHeight(34)
        self.yolo_button.setToolTip(
            "把各页导出成 YOLO 训练数据集切片（点它先弹窗填名称、选导出目录）：\n"
            "<导出目录>/<名称>/images/<名称>-1.jpg（按页序复制原图）\n"
            "<导出目录>/<名称>/labels/<名称>-1.txt（同页的框）\n"
            f"类别顺序 {YOLO_CLASS_NAMES[0]}=左框/右框、{YOLO_CLASS_NAMES[1]}=整幅；\n"
            "没有框的页面写空标签（负样本）。"
        )
        self.yolo_button.setEnabled(False)
        self.yolo_button.clicked.connect(self.export_yolo_labels)
        holder.box.addWidget(self.yolo_button)

        # 两个开关任一变化都要重算按钮显隐（配置项是长期存活的 QObject，
        # 页面销毁时 Qt 自动断开）
        self.cfg.developerMode.valueChanged.connect(self._sync_yolo_button)
        self.cfg.yoloAnnotation.valueChanged.connect(self._sync_yolo_button)
        self._sync_yolo_button()
        return holder

    def _sync_yolo_button(self, *_args) -> None:
        """「导出YOLO标注」按钮的显隐：开发者模式**且** YOLO 标注都开着。

        ⚠️ 两个条件缺一不可：YOLO 标注是开发者模式下的选项（见设置页），
        开发者模式关着时那个开关根本不可见，此时把按钮当"未启用"处理——否则
        会出现"设置里看不到开关、检测页却多出一个按钮"的错位。
        """
        self.yolo_button.setVisible(
            bool(self.cfg.developerMode.value) and bool(self.cfg.yoloAnnotation.value)
        )

    # ------------------------------------------------------------------ 回调
    def _on_source_changed(self, source) -> None:
        """换了源：**清空上一批的框**，再走基类那套显隐与副标题。

        ⚠️ 先清框再调 ``super()``：基类会 ``source_summary()`` → ``source_images()``
        并把结果灌进标题，清框必须排在前面，否则标题里的张数还是上一批的。
        """
        self._boxes.clear()
        self._origins.clear()
        self._sides.clear()           # 人工指定左右跟着换源作废
        self._widths.clear()          # 页宽缓存跟着换源作废
        self._refresh_book_layout()   # 新的一批 = 新的整本书判定，别留上一批结论
        self._sync_export_buttons()
        self.viewer.select_box(-1)
        self._sync_box_kind()
        # 预览跟着换源走：检测页的左栏要**立刻**显示这批待检测的图片，
        # 缩略图走 singletask 缓存（清单仍是真实图片——画框按 stem 取键）。
        self.show_images(self.source_images())
        super()._on_source_changed(source)

    def source_summary(self, source) -> str:
        """在共用的 ``<源> → <输出>`` 之外，**补上待检测张数**。"""
        images = self.source_images()
        tail = f"{len(images)} 张图片" if images else "未找到图片"
        return f"{source}（{tail}） → {self.control.output()}"

    def edit_effect_note(self, path: Path) -> str:
        """编辑器改了待检测的图片：框坐标以**图片原始像素**为基准。

        改了尺寸就必须重跑检测（旧框还按旧图的坐标系画，会整体偏移）；只改
        像素不改尺寸时旧框仍然对得上，所以提示里区分这两种情况而不是一律要求
        重跑。
        """
        return (
            f"已更新「{path.name}」；框坐标以图片原始像素为基准，"
            "改过尺寸请重新执行检测后再导出坐标。"
        )

    def _on_page_changed(self, index: int, path_text: str) -> None:
        """切页：把这一页的框画到大图上（没有就清空并给一句说明）。"""
        self._apply_boxes(path_text)

    def _on_step_event(self, name: str, payload) -> None:
        """接住 ``page_boxes``：把这一页的框收进内存（人工框优先，不被覆盖）。

        ⚠️ 事件名与任务流程第二步完全相同（``functions.detect`` 只发这一个），
        所以这里不需要认得别的名字；别的步骤将来报自己的事件也走同一条通道。
        """
        if name != "page_boxes":
            return
        key = str(payload.get("image", ""))
        slots = page_box_slots_from_event(payload)
        if not any(slots):
            return
        if self._origins.get(key) == "manual":
            return  # 人工框优先：重跑检测不许把用户改过的框冲掉
        self._boxes[key] = slots
        self._origins[key] = "auto"
        # 增量检测（逐张返回）也立刻重算：整本书判定随页数累积而变化，
        # 等全部跑完再算的话，中途看到的标注会一直是左/右框。
        self._refresh_book_layout()

    def _on_boxes_edited(self, path_text: str, boxes) -> None:
        """用户在图上改完框：换算成槽位存下（origin=manual），并重画归一化后的形态。"""
        key = Path(path_text).stem
        slots = self._manual_slots(
            boxes, self._image_size(path_text), full=self.viewer.box_full_mode()
        )
        self._boxes[key] = slots
        self._origins[key] = "manual"
        self._sync_export_buttons()
        # 人工改动可能改变整本书的判定（如把一页的宽框缩窄）→ 先重算再重画，
        # 否则这一帧仍按旧结论标「半框」。
        self._refresh_book_layout()
        self._apply_boxes(path_text, selected=self.viewer.selected_index())
        self._sync_box_kind()

    def on_result(self, out_dir: Path, _result: dict) -> None:
        """检测跑完：重画当前页，并把「检出几页 / 几页无框」写到状态行。

        ``out_dir`` 是输出目录（``detect`` 默认不落盘，这里只是共用控件回传的
        那个路径），导出按钮会用到它。
        """
        # 整本书的框都齐了 → 重算形态判定（决定「半框」标注）再重画当前页
        self._refresh_book_layout()
        self._apply_boxes(
            str(self.viewer.current_path() or ""), selected=self.viewer.selected_index()
        )
        self._sync_export_buttons()
        self._sync_box_kind()
        total = len(self.source_images())
        hit = sum(1 for slots in self._boxes.values() if any(slots))
        if not hit:
            self.toast(
                "warning",
                "没有检测到内容框",
                "可能这批图不是正文页；也可以在图上手动画框后导出。",
            )
            self.status(f"共 {total} 张，都没有检出内容框", "warning")
            return
        self.status(f"共 {total} 张，{hit} 张检出内容框（可手绘修正后导出）", "success")
        self.toast("success", "检测完成", f"{hit} / {total} 张检出内容框。")

    # ------------------------------------------------- 框类型（人工干预）
    #
    # 与任务流程第二步**同一套规则**，且"怎么问用户"也只有一份——交互顺序、
    # 确认框与提示文案在 `desktop/components/box_kinds.py::BoxKindEditor`
    # （结果计算在 `utils.box_geometry` 纯函数里）；本页只提供宿主协议。

    def _current_slots(self) -> tuple[str, list]:
        """当前页的 ``(图片路径, 槽位)``；没有页时路径为空串。"""
        path = str(self.viewer.current_path() or "")
        return path, (self._boxes.get(Path(path).stem, []) if path else [])

    def _on_selection_changed(self, index: int) -> None:
        """查看器里选中态变了 → 回填「选中框类型」与删除按钮。"""
        self._sync_box_kind()

    def _sync_box_kind(self) -> None:
        """按当前选中框回填类型控件与删除按钮（无选中时三段都不高亮）。"""
        index = self.viewer.selected_index()
        kinds = self.viewer.box_kinds()
        kind = kinds[index] if 0 <= index < len(kinds) else ""
        # ⚠️ ``set_current`` 是程序化切换、**不发** ``current_changed``，否则
        # 回填会反过来再触发一次类型切换（自我递归）。
        self.box_kind.set_current(kind if index >= 0 else "")
        self.delete_box.setEnabled(index >= 0)

    def _on_box_kind_changed(self, kind: str) -> None:
        """用户点了「左框 / 右框 / 整幅」（交互实现委托共享 BoxKindEditor）。"""
        path_text, _slots = self._current_slots()
        if not path_text:
            return
        self._box_editor().set_kind(path_text, self.viewer.selected_index(), kind)

    # ---- BoxKindHost 协议（box_ 前缀，避免与页面其他成员撞名）----
    def _box_editor(self) -> BoxKindEditor:
        """共享交互器（无状态，按需构造）。"""
        return BoxKindEditor(self)

    def box_viewer(self):
        return self.viewer

    def box_toast(self, kind: str, title: str, content: str) -> None:
        self.toast(kind, title, content)

    def box_raw_slots(self, path_text: str) -> list:
        return list(self._boxes.get(Path(path_text).stem, []))

    def box_page_is_full(self, path_text: str) -> bool:
        return bool(is_full_content(self._boxes.get(Path(path_text).stem, [])))

    def box_image_size(self, path_text: str):
        return self._image_size(path_text) or None

    def box_commit(self, path_text: str, slots: list, select_box=None,
                   side="keep") -> None:
        """落库 + 重画；``side`` 按需写入/清除这页的人工左右指定。

        ⚠️ **先写 side、再上屏**（同任务流程那份）：``_store_slots`` →
        ``_apply_boxes`` 要读 ``_sides`` 决定标签与面板高亮。先上屏后写的话
        第一次点击读到的还是旧值 ⇒ 界面不动、得点第二次（用户 2026-10-17 报）。
        """
        if side != "keep":
            key = Path(path_text).stem
            if side in ("left", "right"):
                self._sides[key] = side
            else:
                self._sides.pop(key, None)
        self._store_slots(path_text, slots, select=select_box)

    def box_page_half_candidate(self, path_text: str) -> bool:
        """这页是否**够「半框」**（整本书单栏 + 只有一个横跨整页的框）——为真时
        左/右可由用户指定（中心压在中线上，位置判定没意义）。"""
        if not self.viewer.single_column():
            return False
        slots = self._boxes.get(Path(path_text).stem, [])
        return is_single_wide_half(slots, self._page_width(path_text))

    def box_confirm(self, title: str, body: str, yes_text: str, cancel_text: str) -> bool:
        # ⚠️ 延迟导入必须留在方法体内：自测靠替换 qfluentwidgets.MessageBox
        #    记录/否决确认（离屏跑弹真模态会把整个用例挂住）
        from qfluentwidgets import MessageBox  # noqa: PLC0415 - 延迟导入便于自测替换

        box = MessageBox(title, body, self.window())
        box.yesButton.setText(yes_text)
        box.cancelButton.setText(cancel_text)
        return bool(box.exec())

    def box_resync_kind(self, _index: int) -> None:
        """按现值回填类型控件高亮（类型操作结束后必调，别停在假位置）。"""
        self._sync_box_kind()

    def box_current_path_text(self) -> str:
        return str(self.viewer.current_path() or "")

    def _select_box_of_kind(self, kind: str) -> None:
        """没有选中框时，点类型＝选中该类框；该类型不存在则提示。"""
        self._box_editor().select_box_of_kind(kind)

    def _make_box_full(self, path_text: str, index: int) -> None:
        """把第 index 个框设为「整幅」（整幅与半幅互斥、一页只能一个框）。"""
        self._box_editor().make_full(path_text, index)

    def _make_box_half(self, path_text: str, index: int, kind: str) -> None:
        """把第 index 个框改成半幅（左/右）。"""
        self._box_editor().make_half(path_text, index, kind)

    def _delete_selected_box(self) -> None:
        """删除当前选中的文本框（与 Delete 键同一条路径）。"""
        self._box_editor().delete_selected()

    def _store_slots(self, path_text: str, slots: list, select=None) -> None:
        """把槽位结果写进内存表 + 重画，并同步类型控件与导出按钮。

        ``select`` 给定某个框时，重新上屏后仍选中**同一个框**（按坐标找回）
        ——切换类型/删框会改变框在列表里的次序，按下标保持会选错框。
        """
        key = Path(path_text).stem
        self._boxes[key] = slots
        self._origins[key] = "manual"
        self._sync_export_buttons()
        shown = [b for b in slots if b]
        index = -1
        if select is not None:
            target = list(select)
            index = next(
                (i for i, b in enumerate(shown) if list(b) == target), -1
            )
        self._apply_boxes(path_text, selected=index)
        self._sync_box_kind()

    # ------------------------------------------------------------------ 画框
    def _image_size(self, path_text: str) -> tuple[int, int]:
        """图片**原始**尺寸 (w, h)。

        ⚠️ 必须是原始像素尺寸，不是预览里被降采样后的尺寸——框坐标以原始像素为
        基准，给错基准框就会整体偏移（``ImageView._update_mapping`` 的注释同此）。
        ``QImageReader.size()`` 只读图片头，不解码，够快。
        """
        size = QImageReader(str(path_text)).size()
        if size.isValid() and size.width() > 0:
            return size.width(), size.height()
        return 0, 0

    def _page_width(self, path_text: str) -> int:
        """该页原始像素宽度（整本书判据用）；取不到给 0＝不参与单宽框判定。

        结果按 stem 缓存：``_image_size`` 每次都要 ``QImageReader`` 读文件头，
        而整本书判定要遍历全部页面，反复读纯属浪费。
        """
        key = Path(path_text).stem
        if key in self._widths:
            return self._widths[key]
        try:
            width = int(self._image_size(path_text)[0])
        except Exception:  # noqa: BLE001 - 取不到宽度按"无页宽"保守处理
            width = 0
        self._widths[key] = width
        return width

    def _refresh_book_layout(self) -> None:
        """重算**整本书**的形态判定，并同步给预览控件（决定「半框」标注）。

        ⚠️ 判据本体在 ``utils/book_layout.profile_book``：它要的是"整本书长什么
        样"——单页分不出「一栏横跨整页」与「真双栏书漏检一侧」。本方法只负责
        取数（每页槽位 + 页宽）与转发。
        """
        paths = {Path(p).stem: str(p) for p in self.source_images()}
        pages = [
            (stem, slots, self._page_width(paths.get(stem, stem)))
            for stem, slots in self._boxes.items()
        ]
        profile = profile_book(pages)
        setter = getattr(self.viewer, "set_single_column", None)
        if callable(setter):
            setter(bool(profile.single_column_book))

    def _apply_boxes(self, path_text: str, selected: int = -1) -> None:
        """把某一页的槽位结果画到查看器上（命名/配色由控件按位置现算）。"""
        if not path_text:
            return
        size = self._image_size(path_text)
        slots = self._boxes.get(Path(path_text).stem, [])
        shown = [b for b in slots if b]
        full = is_full_content(slots)
        # ⚠️ 单栏书里横跨整页的那个框叫「半框」，不是左框/右框——整本书的结论
        #    来自 _refresh_book_layout（见 profile_book）。用户在半框页上指定过
        #    左右时用指定值（优先级见 box_styles）。
        side = self._sides.get(Path(path_text).stem)
        setter = getattr(self.viewer, "set_side_override", None)
        if callable(setter):
            setter(side)
        names = box_names(
            shown, size, full, self.viewer.single_column(), side
        )
        if not shown:
            info = "未检测到文本框"
        else:
            info = "  ｜  ".join(
                f"{names[i]}({b[0]},{b[1]},{b[2]},{b[3]})"
                for i, b in enumerate(shown)
            )
        self.viewer.apply_boxes(
            shown, QSize(size[0], size[1]), info, full=full, selected=selected
        )

    @staticmethod
    def _manual_slots(boxes, size, full: bool) -> list:
        """用户画出来的扁平框列表 → **槽位表示**（与任务流程第二步同规则）。

        规则本体在 ``utils.box_geometry``：整幅恒 1 槽、半幅恒 2 槽（``half_slots``）。
        ⚠️ 单独抽出成静态方法纯粹为了可测：它不碰任何控件状态。

        ``full`` 是查看器当前的「整幅」标志（用户显式选的类型，不靠框个数推断）。
        半幅情境下即使只剩 1 个框也走 ``half_slots`` 补成 2 槽——否则那个框会被
        ``is_full_content`` 当成整幅，正是用户报过的"删掉整幅框后右边的框自动变成
        整幅"。整幅却拿到多个框（不该发生，控件侧按 max_boxes 拦过）时同样按半幅
        存：宁可形态变半幅，也不能悄悄丢掉用户画出来的框。
        """
        normalized = [[int(round(float(v))) for v in box] for box in boxes]
        if not normalized:
            return []
        if full and len(normalized) == 1:
            return [normalized[0]]
        return half_slots(normalized, size)

    # ------------------------------------------------------------------ 导出
    def _export_buttons(self) -> tuple:
        """导出区那一列按钮（导出期间要整排禁用，所以收在一处取）。"""
        return (self.export_button, self.annotated_button, self.yolo_button)

    def _sync_export_buttons(self) -> None:
        """有框才让导出（没框导出一份空表 / 一批没画的图都没有意义）。"""
        has = any(any(slots) for slots in self._boxes.values())
        for button in self._export_buttons():
            button.setEnabled(has)

    def export_boxes(self) -> None:
        """把各页框坐标写成 ``<输出目录>/boxes.json``（与任务流程同格式）。

        格式（``desktop/store/annotations.py`` 的 ``boxes.json``）::

            {"<页名去后缀>": {"boxes": [[x1,y1,x2,y2], ...],
                             "origin": "auto" | "manual",
                             "updated_at": <秒级时间戳>}}

        用 ``desktop.store.json_io.write_json``（临时文件 + ``os.replace`` 原子
        落盘）——与任务流程写这份文件走的是同一个 IO，不另写一套。
        """
        kept = {k: v for k, v in self._boxes.items() if any(v)}
        if not kept:
            self.toast("warning", "还没有结果", "先检测或手动画框，再导出。")
            return
        out_dir = self.control.output()
        if out_dir is None:
            self.toast("warning", "没有输出目录", "请先选择图片，或点「输出目录」指定位置。")
            return
        out_dir = Path(out_dir)
        target = out_dir / EXPORT_NAME
        now = time.time()
        data = {
            key: {
                "boxes": slots,
                "origin": self._origins.get(key, "auto"),
                "updated_at": now,
            }
            for key, slots in kept.items()
        }
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            write_json(target, data)
        except OSError as exc:
            self.toast("error", "导出失败", str(exc))
            self.log(f"导出失败：{exc}")
            return
        self.log(f"坐标已导出：{target}")
        self.status(f"已导出 {len(data)} 页坐标 → {target}", "success")
        self.toast("success", "已导出坐标 JSON", f"{len(data)} 页 → {target.name}")

    # ------------------------------------------------------------ 导出标注图
    def export_annotated_images(self) -> None:
        """把框画回原图导出成 PNG：先选目录，**目录已存在就问是否覆盖**。

        用户 2026-10-03 的原话是「导出的时候提示选择输出目录，如果输出目录
        已经存在了，则提示是否覆盖」，所以这里**一定先弹目录选择**，再用
        「目录已存在且非空」作为覆盖确认的条件：

        - 目录不存在 → 直接写（没什么可覆盖的）；
        - 目录存在但**空** → 直接写，不必为一个空目录打断用户；
        - 目录存在且**有文件** → 弹确认，说清"会覆盖同名标注图"。

        ⚠️ 确认框里**不列文件名**：一屏几十页列出来反而看不过来，只说清
        「同名覆盖、其余保留」——本模块只写自己的 ``<stem>.png``，绝不动
        目录里别的文件（``export_annotated`` 没有任何删除逻辑）。
        """
        entries = self._annotated_entries()
        if not entries:
            self.toast("warning", "还没有结果", "先检测或手动画框，再导出。")
            return
        current = self.control.output()
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择标注图输出目录",
            str(current) if current else str(default_open_dir()),
        )
        if not directory:
            return
        out_dir = Path(directory)
        if out_dir.is_dir() and any(out_dir.iterdir()):
            # ⚠️ 延迟导入（与 taskdetail/detect.py 同款）：自测要能把
            #    qfluentwidgets.MessageBox 换成记录器，否则离屏跑会弹真模态
            #    把整个用例挂住。
            from qfluentwidgets import MessageBox  # noqa: PLC0415

            box = MessageBox(
                "目录已存在，是否覆盖？",
                f"输出目录里已经有文件了：\n{out_dir}\n\n"
                "继续会把同名标注图覆盖掉（其它文件不动）。",
                self.window(),
            )
            box.yesButton.setText("覆盖导出")
            box.cancelButton.setText("取消")
            if not box.exec():
                self.toast("info", "已取消", "没有导出任何文件。")
                return
        if self._export_kernel.busy():
            self.toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        self._begin_export(
            _EXPORT_ANNOTATED,
            dest=out_dir,
            entries=entries,
            status=f"正在导出标注图…（{len(entries)} 张）",
        )

    def _annotated_entries(self) -> list:
        """要导出的 ``(图片路径, 槽位)`` 清单（**只取有框的页**）。

        口径在 :func:`desktop.services.detect_export.entries_from_mapping`，
        与导出循环分开：改"哪些页要导出"只需改那一个纯函数。
        """
        return entries_from_mapping(
            self.source_images(), self._boxes
        )

    # ------------------------------------------------------------ 导出 YOLO 标注
    def export_yolo_labels(self) -> None:
        """导出 YOLO 数据集切片：先弹窗填**名称**与选**导出目录**（用户 2026-10-16）。

        弹窗的两个默认值都取**上次记住的那一份**（独立任务页记在
        ``singletask/<子任务>/yolo_export.json``，见
        :func:`desktop.utils.files.singletask_yolo_export_path`）：同一批图分几次
        导成不同前缀时要汇进同一个数据集根，重填重选纯属折腾。

        **没记过时**：导出目录默认文档目录（``YoloExportPanel`` 自己兜底），
        名称回落当前源的名（独立页没有任务号，源名就是"这一批图叫什么"的唯一
        线索；任务流程那边默认的是任务号，见 ``DetectMixin._yolo_dataset_name``）。

        ⚠️ 导出的是**全部图片**（不止有框的页）：没有框的页照样复制图片 + 写
        空标签当负样本（用户 2026-10-16：「写空标签当负样本」）。
        """
        images = self.source_images()
        if not images:
            self.toast("warning", "还没有图片", "先选择图片或图片文件夹，再导出。")
            return
        if self._export_kernel.busy():
            self.toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        saved = self._load_yolo_export_state()
        chosen = ask_yolo_export(
            self.window(),
            directory=saved.get("directory") or None,
            # 没记过时用当前源的名兜底（"这一批图叫什么"对用户没有别的线索）
            name=saved.get("name") or self._default_dataset_name(),
        )
        if chosen is None:
            self.toast("info", "已取消", "没有导出任何文件。")
            return
        name, directory = chosen
        self._save_yolo_export_state(name, directory)
        self._begin_export(
            _EXPORT_YOLO,
            dest=Path(directory),
            entries=yolo_entries(images, self._boxes),
            name=name,
            # 独立页**没有任务号**：data.json 里记的是源，校验时只能做自洽检查
            # （任务流程那条链会把任务号写进去，见 DetectMixin.export_yolo_labels）
            source=self._default_dataset_name(),
            status=f"正在导出 YOLO 数据集：{len(images)} 页 → {directory}",
        )

    def _default_dataset_name(self) -> str:
        """弹窗里「名称」的默认值：当前源的名（目录取目录名、文件取去后缀名）。"""
        source = self.control.source()
        if source is None:
            return ""
        path = Path(source)
        return path.stem if path.is_file() else path.name

    def _yolo_export_state_path(self) -> Path:
        """本页「导出YOLO标注」的记忆文件（按子任务一份，见 files.py 的说明）。"""
        spec = self.SPEC
        assert spec is not None, "步骤模块页必须声明 SPEC"
        return singletask_yolo_export_path(spec.disk_key())

    def _load_yolo_export_state(self) -> dict:
        """上次填的名称与导出目录；没记过/写坏了给两个空串。"""
        data = read_json(self._yolo_export_state_path(), None)
        doc = data if isinstance(data, dict) else {}

        def text(key: str) -> str:
            value = doc.get(key)
            return value if isinstance(value, str) else ""

        return {
            "name": text(_YOLO_EXPORT_NAME_KEY),
            "directory": text(_YOLO_EXPORT_DIR_KEY),
        }

    def _save_yolo_export_state(self, name: str, directory: str) -> None:
        """记住本次填的名称与导出目录（写不动只记一行日志，不打断导出）。"""
        try:
            write_json(
                self._yolo_export_state_path(),
                {
                    _YOLO_EXPORT_NAME_KEY: str(name or ""),
                    _YOLO_EXPORT_DIR_KEY: str(directory),
                },
            )
        except OSError as exc:
            self.log(f"记住导出设置失败：{exc}")

    # ------------------------------------------------------------------ 导出内核
    def _begin_export(self, kind: str, dest: Path, entries: list, *,
                      name: str = "", task_id: str = "", source: str = "",
                      status: str = "") -> None:
        """起一次导出（标注图 / YOLO 切片共用这一条执行线）。

        ⚠️ 两种导出共用 ``_export_kernel`` 与 ``export_progress``：它们都是
        "把已有框落盘"的短活，并行没有意义；各占一条进度行反而让用户看不出
        是哪条在跑。
        """
        self._export_kind = kind
        self._exported = []
        self._yolo_summary = {}
        for button in self._export_buttons():
            button.setEnabled(False)
        self.export_progress.start()
        self.status(status or "正在导出…", "info")
        self.log(f"开始导出（{kind}）：{len(entries)} 页 → {dest}")
        args: dict = {
            "kind": kind,
            "entries": [(str(p), slots) for p, slots in entries],
        }
        if kind == _EXPORT_YOLO:
            args["name"] = name
            args["task_id"] = task_id
            args["source"] = source
        if not self._export_kernel.run(StepRequest(dest=dest, args=args)):
            self._sync_export_buttons()
            self.export_progress.reset()
            self.status("正在导出", "warning")

    def _export_job(self, request: StepRequest, report) -> str | None:
        """导出 job（跑在 worker 线程）：按 ``kind`` 分派到两个纯函数。

        ⚠️ ``import utils``（cv2）发生在这个线程里——GUI 主进程不会因此付出
        几百毫秒的启动代价（见 :mod:`desktop.services.detect_export` 的模块
        docstring）。YOLO 那条只用 PIL 读文件头，不加载 cv2。
        """
        dest = request.dest
        # job 契约：导出一定带输出目录（执行内核总会把 dest 设好）
        assert dest is not None, "导出 job 必须带输出目录"
        entries = [(Path(p), slots) for p, slots in request.args["entries"]]

        def log(text: str) -> None:
            report("log", {"message": text})

        def progress(done: int, total: int) -> None:
            report("progress", {"done": done, "total": total})

        if request.args.get("kind") == _EXPORT_YOLO:
            summary = export_yolo(
                entries, dest, str(request.args.get("name", "")),
                task_id=str(request.args.get("task_id", "")),
                source=str(request.args.get("source", "")),
                report=log, progress=progress,
            )
            # ⚠️ 统计里带 Path，跨线程回主线程前不改它：主线程只读
            self._yolo_summary = summary
            self._exported = list(summary["labels"])
            return str(dest)
        # ⚠️ 带上整本书结论：单栏书里那个横跨整页的框在导出图上也要标「半框」，
        #    否则导出图与界面看到的标注不一致（同一批框、两种叫法）。
        self._exported = export_annotated(
            entries, dest, report=log, progress=progress,
            single_column=self.viewer.single_column(),
        )
        return str(dest)

    def _on_export_progress(self, done: int, total: int) -> None:
        """一条导出进度：喂给本页第二条执行线自己的进度行。"""
        self.export_progress.update(done, total)

    def _on_export_finished(self, out_dir: str) -> None:
        """导出完成：恢复按钮、进度条走到头、按**产物形态**写状态行与日志。"""
        self._sync_export_buttons()
        if self._export_kind == _EXPORT_YOLO:
            self._on_yolo_exported(out_dir)
            return
        count = len(self._exported)
        self.export_progress.succeed(
            f"完成 {count} 张" if count else "已完成"
        )
        self.status(f"已导出 {count} 张标注图 → {out_dir}", "success")
        self.log(f"标注图导出完成：{count} 张 → {out_dir}")
        if count:
            self.toast("success", "已导出标注图", f"共 {count} 张 → {out_dir}")
        else:
            self.toast("warning", "没有导出", "这些图片都读不出来，请检查文件是否还在。")

    def _on_yolo_exported(self, out_dir: str) -> None:
        """YOLO 切片导出完成：报清"几页有框、几页负样本、落点在哪"，
        并**打开导出目录**（用户 2026-10-16：「导出成功后，打开相应的目录」）。"""
        summary = self._yolo_summary or {}
        count = len(self._exported)
        skipped = list(summary.get("skipped") or [])
        folder = summary.get("folder") or out_dir
        detail = (
            f"{summary.get('labeled', 0)} 页有框（{summary.get('boxes', 0)} 个框）、"
            f"{summary.get('empty', 0)} 页负样本"
        )
        self.export_progress.succeed(f"完成 {count} 页" if count else "已完成")
        self.status(f"已导出 {count} 页 → {folder}", "success")
        self.log(f"YOLO 数据集导出完成：{detail} → {folder}")
        if skipped:
            self.log(f"跳过 {len(skipped)} 页（读不到原图）：{'、'.join(skipped[:5])}")
        if count:
            self.toast("success", "已导出YOLO标注", f"{count} 页（{detail}）→ {folder}")
            reveal_dir(folder)
        else:
            self.toast("warning", "没有导出", "这些图片都读不出来，请检查文件是否还在。")

    def _on_export_failed(self, message: str) -> None:
        """导出失败：恢复按钮、进度条停住并提示。"""
        self._sync_export_buttons()
        self.export_progress.fail()
        title = "导出YOLO标注失败" if self._export_kind == _EXPORT_YOLO else "导出标注图失败"
        self.status(title, "error")
        self.log(f"{title}：{message}")
        self.toast("error", "导出失败", message)

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾：查看器自己的后台线程 + 两个执行线程（检测、导出标注图）。"""
        self.viewer.shutdown_workers()
        self._export_kernel.shutdown()
        self.control.shutdown()
        super().shutdown_workers()


__all__ = ["DetectModulePage"]
