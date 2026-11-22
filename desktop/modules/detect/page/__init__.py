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

4. **整个「导出」分类随设置里「**启用YOLO标注**」开关显隐**（用户
   2026-11-17：分类要按 yolo 参数决定显隐；开关开着时导出区最底部是
   「**导出YOLO标注**」，用户 2026-10-16；2026-11-17 起不再挂在开发者模式下）：点它先弹窗填**名称**（父节点名 =
   文件名前缀）并选**导出目录**（按独立功能记住上次选的），确认后把全部页面
   导出成 YOLO 数据集切片 ``<导出目录>/<名称>/{images,labels}/<名称>-1.…``
   （类别顺序见 ``utils.box_geometry.YOLO_CLASS_NAMES``；无框页写空标签当负样本）。

⚠️ **槽位约定**（半幅 2 槽 ``[左, 右]``、整幅 1 槽 ``[整幅]``）的全部规则来自
``utils.box_geometry``（``page_box_slots_from_event`` 读事件、``half_slots`` 收
人工框），人工干预的**交互流**（切类型 / 整幅互斥确认 / 删框）在
``desktop.components.box_kinds.BoxKindEditor``（与任务流程第二步共用一份），
本页不自己数"还剩几个框"——按个数推类型会造成"删掉整幅框后右边的框自动变成
整幅"（用户 2026-09-29 报过的老问题）。

⚠️ **面板与任务流程第二步共用同一个** ``DetectPanel``（用户 2026-11-17：
「主任务节点功能发生变化，单任务要同步发生变化，将两套代码功能保持一致」）：
识别方式（自动识别/人工标注）、「自动使用上一个文本框标注」、「选中框类型 /
删除选中框」全部来自共享面板——主任务面板一改，本页**自动**跟着变，不再各抄
一份控件。此前本页把整个面板藏了、自己手抄两个框类型控件，主任务 2026-11-16
加「识别文本框模式」时这边就没同步上，正是那条要求的由来。

两种模式在本页的语义与任务流程一致：

- **自动识别**：主按钮「检测文本框」跑 YOLO 出框，预览里可手改；
- **人工标注**：**不调 YOLO**——执行按钮隐藏（与详情页
  ``_sync_detect_mode_ui`` 同口径），逐页画框；勾选「自动使用上一个文本框
  标注」时，切到还没有任何框的页会把上一页的框整份带过来（上一页有真框 +
  本页零框才带，判据与任务流程一致）。

交付（本页特有，任务流程没有）：「导出标注图」「导出坐标 JSON」与可选的
「导出YOLO标注」摆在与主任务相同的执行链之外，走 :meth:`StepControl.add_extra`
插在底部动作区（输出目录/执行/中断）**上方**。

2026-11-22 起按职责拆成子包：常量在 ``constants``，页面能力按「骨架/控件 /
回调与框类型 / 尺寸与画框 / 导出」分到各 ``mixin_*`` 子模块；本 ``__init``
只负责组装页面类并重导出既有名字（``from desktop.modules.detect.page import X``
保持不变）。

⚠️ 子模块之间只互相 import，不要反过来导入本包（会形成循环）。
"""

from __future__ import annotations

from desktop.components.viewers.image_actions import ImageEditActionsMixin
from desktop.components.yolo_export_dialog import ask_yolo_export
from desktop.modules.base import StepModulePage
from desktop.modules.thumb_source import ThumbSourceMixin
from desktop.utils.files import reveal_dir

from .constants import (
    EXPORT_NAME,
    _EXPORT_ANNOTATED,
    _EXPORT_YOLO,
    _SPEC,
    _YOLO_EXPORT_DIR_KEY,
    _YOLO_EXPORT_NAME_KEY,
)
from .mixin_core import CoreMixin
from .mixin_export import ExportMixin
from .mixin_geometry import GeometryMixin
from .mixin_view import ViewMixin

__all__ = ["DetectModulePage"]


class DetectModulePage(
    CoreMixin,
    ViewMixin,
    GeometryMixin,
    ExportMixin,
    StepModulePage,
    ThumbSourceMixin,
    ImageEditActionsMixin,
):
    """检测文本框模块页：拖入图片 → 检测内容框 → 图上修正 → 导出坐标 JSON。"""

    SPEC = _SPEC

    #: 「整本书形态判定」重算的节流窗口（ms）。
    #:
    #: ⚠️ 为什么要节流：``_refresh_book_layout`` → ``profile_book`` 要遍历**全部**
    #: 已收框的页，而增量检测是"每来一页就发一条 page_boxes 事件"——直接在里面
    #: 重算就是 O(N²)：1000 张图时主线程被这一件事拖住（用户报的「页面卡顿」）。
    #: 改成"置脏 + 300ms 节流"后，执行期间按窗口重算；用户动作（改框、跑完、
    #: 换源）仍走 ``_refresh_layout_now`` **立即**算。
    _LAYOUT_UI_MS = 300

    def _ask_yolo_export(self, *args, **kwargs):
        """按名取 ``ask_yolo_export``（自测把替身打在 page 模块命名上）。"""
        return ask_yolo_export(*args, **kwargs)

    def _reveal_dir(self, path) -> None:
        """按名取 ``reveal_dir``（自测把替身打在 page 模块命名上）。"""
        return reveal_dir(path)
