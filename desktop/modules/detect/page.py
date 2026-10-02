# -*- coding: utf-8 -*-
"""「检测文本框」独立模块页：与任务流程无关，选一批图片直接检测内容框。

**复用共用组件**（``desktop/steps``）：页头下方横跨整幅的**大输入区**（拖图片 /
拖文件夹 / 点选），右栏是 :class:`StepControl`（输出目录 + 执行/中断），执行走
``StepKernel`` → ``functions.get_function("detect")``——与任务流程第二步是同一条
代码路径（连参数面板都是同一个 ``DetectPanel``）。

**和别的模块页最大的不同：这一步的产物不是文件，是坐标。**

``detect`` 默认不落盘（``--save`` 关着），框只经 ``page_boxes`` 结构化事件回来
（见 ``functions.detect.DetectFunction._report_boxes``）。所以：

1. 内核必须把**非 progress/log 的事件**原样透传上来（``StepKernel.event``，
   2026-10-02 补的通道）——改造前它只转进度和日志，这一步的结果到不了界面；
2. 本页把每页的框收在内存里（``self._boxes``，键 = 文件名去后缀），左栏用共享
   查看器把框画在图上，用户可直接**手绘 / 拖动 / 缩放手柄 / Delete** 修正；
3. 交付方式是「**导出坐标 JSON**」——写 ``<输出目录>/boxes.json``，格式与任务
   流程的 ``tasks/<id>/boxes.json`` **逐字段一致**（``{stem: {boxes, origin,
   updated_at}}``），所以导出的文件可以直接当作下一步（或将来自定义流程里任意
   一步）的输入。

⚠️ **槽位约定**（半幅 2 槽 ``[左, 右]``、整幅 1 槽 ``[整幅]``）的全部规则来自
``utils.box_geometry``（``page_box_slots_from_event`` 读事件、``half_slots`` 收
人工框），本页不自己数"还剩几个框"——按个数推类型会造成"删掉整幅框后右边的框
自动变成整幅"（用户 2026-09-29 报过的老问题）。

⚠️ **为什么不摆 ``DetectPanel``**：面板里那三个控件（「整页模式」切的是**第三步**
的 area、「选中框类型」/「删除选中框」依赖任务流程的框类型机制）全部由任务流程
宿主驱动；本页的框编辑直接由查看器承担，留着面板就是三个点不动的死控件。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import PushButton

from desktop.components.viewers import ImageViewerWidget
from desktop.components.viewers.image_view import box_names
from desktop.modules.base import ModulePage
from desktop.steps import SourceZone, StepControl, spec_by_key
from desktop.store.json_io import write_json
from desktop.ui.widgets import Card
from utils.box_geometry import (
    half_slots,
    is_full_content,
    page_box_slots_from_event,
)

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("detect")

#: 导出文件名。⚠️ 与任务流程 ``tasks/<id>/boxes.json`` **同名**是刻意的：
#: 用户拿它跟任务里的那份对照/替换时不必换算名字，格式也是同一套。
EXPORT_NAME = "boxes.json"


class DetectModulePage(ModulePage):
    """检测文本框模块页：拖入图片 → 检测内容框 → 图上修正 → 导出坐标 JSON。"""

    TITLE = _SPEC.title
    SUBTITLE = _SPEC.subtitle

    def __init__(self, parent=None):
        """建骨架、共用步骤控件与内存中的框表。"""
        super().__init__(parent)
        #: 文件名去后缀 → **槽位表示**（半幅 2 槽 / 整幅 1 槽）。
        #: 与任务流程同构：不在内存里存"用户画了几个框"，只存槽位。
        self._boxes: dict[str, list] = {}
        #: 同上，键 → "auto"（检测来的）/ "manual"（用户改过）。
        #: 与任务流程一样，人工框不被后续自动检测覆盖。
        self._origins: dict[str, str] = {}
        self.status("尚未选择图片")

    # ------------------------------------------------------------------ 输入
    def _build_input(self) -> SourceZone:
        """页头下方的**大输入区**：拖图片 / 拖文件夹 / 点选（共用组件）。"""
        self.zone = SourceZone(_SPEC)
        self.zone.rejected.connect(
            lambda message: self.toast("warning", "这个用不上", message)
        )
        return self.zone

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
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：共用步骤控件（输出目录 + 执行）+ 「导出坐标 JSON」。"""
        card = Card()
        self.control = StepControl(_SPEC, zone=self.zone)
        self.control.status.connect(self.status)
        self.control.log.connect(self.log)
        self.control.source_changed.connect(self._on_source_changed)
        self.control.finished.connect(self._on_finished)
        self.control.failed.connect(self._on_failed)
        #: 步骤私有事件：这一步的产物（每页框坐标）就是从这里上来的。
        self.control.event.connect(self._on_step_event)
        if self.control.panel is not None:
            # 面板的控件全由任务流程宿主驱动，本页接管不了（见模块 docstring）。
            self.control.panel.setVisible(False)
        card.box.addWidget(self.control)

        self.export_button = PushButton(FIF.SAVE_AS, "导出坐标 JSON")
        self.export_button.setFixedHeight(34)
        self.export_button.setToolTip(
            f"把各页框坐标写成 {EXPORT_NAME}（与任务流程同格式）"
        )
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_boxes)
        card.box.addWidget(self.export_button)
        return card

    # ------------------------------------------------------------------ 回调
    def _on_source_changed(self, source) -> None:
        """换了源：清空上一批的框，把「源 → 输出」与张数写到副标题上。"""
        self._boxes.clear()
        self._origins.clear()
        self._sync_export_button()
        paths = self._source_images()
        self.viewer.set_images(paths)
        if source is None:
            self.header.set_subtitle(_SPEC.subtitle)
            self.status("尚未选择图片", "info")
            return
        count = len(paths)
        tail = f"{count} 张图片" if count else "（未找到图片）"
        self.header.set_subtitle(f"{source}（{tail}） → {self.control.output()}")
        self.status(f"已选择，共 {count} 张图片，可以开始检测", "info")

    def _source_images(self) -> list[Path]:
        """源里的图片清单：源是文件就是它自己，是目录就取顶层图片。"""
        source = self.control.source()
        if source is None:
            return []
        source = Path(source)
        if source.is_file():
            return [source] if _SPEC.accepts_path(source) else []
        return _SPEC.listing(source)

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

    def _on_boxes_edited(self, path_text: str, boxes) -> None:
        """用户在图上改完框：换算成槽位存下（origin=manual），并重画归一化后的形态。"""
        key = Path(path_text).stem
        slots = self._manual_slots(
            boxes, self._image_size(path_text), full=self.viewer.box_full_mode()
        )
        self._boxes[key] = slots
        self._origins[key] = "manual"
        self._sync_export_button()
        self._apply_boxes(path_text, selected=self.viewer.selected_index())

    def _on_finished(self, out_dir: str) -> None:
        """检测跑完：重画当前页，并把「检出几页 / 几页无框」写到状态行。

        ``out_dir`` 是输出目录（``detect`` 默认不落盘，这里只是共用控件回传的
        那个路径），导出按钮会用到它。
        """
        self._apply_boxes(
            str(self.viewer.current_path() or ""), selected=self.viewer.selected_index()
        )
        self._sync_export_button()
        total = len(self._source_images())
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

    def _on_failed(self, message: str) -> None:
        """失败：提示（状态行与日志已由共用控件写过）。"""
        self.toast("error", "检测失败", message)

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

    def _apply_boxes(self, path_text: str, selected: int = -1) -> None:
        """把某一页的槽位结果画到查看器上（命名/配色由控件按位置现算）。"""
        if not path_text:
            return
        size = self._image_size(path_text)
        slots = self._boxes.get(Path(path_text).stem, [])
        shown = [b for b in slots if b]
        full = is_full_content(slots)
        names = box_names(shown, size, full)
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
    def _sync_export_button(self) -> None:
        """有框才让导出（没框导出一份空表没有意义）。"""
        has = any(any(slots) for slots in self._boxes.values())
        self.export_button.setEnabled(has)

    def export_boxes(self) -> None:
        """把各页框坐标写成 ``<输出目录>/boxes.json``（与任务流程同格式）。

        格式（``desktop/store/annotations.py`` 的 ``boxes.json``）：:

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

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾：查看器自己的后台线程 + 共用步骤控件的执行线程。"""
        self.viewer.shutdown_workers()
        self.control.shutdown()
        super().shutdown_workers()


__all__ = ["DetectModulePage"]
