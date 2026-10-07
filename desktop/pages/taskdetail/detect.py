# -*- coding: utf-8 -*-
"""任务详情页的 detect 检测控制器。

框坐标持久化在任务目录的 `boxes.json`（键为页面 stem）：
- 选中图片时优先读已有结果（命中则不再检测，手动框不被自动结果覆盖）；
- 子进程检测到的框写回（origin=auto）；
- 预览区拖动线框后写回（origin=manual），全程不生成新文件。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QSize
from PySide6.QtGui import QImageReader

from core.command_spec import WHOLE_PAGE_AREA
from desktop.components.box_kinds import BoxKindEditor
from utils.box_geometry import (
    classify_page_slots,
    compute_final_boxes,
    half_slots,
    is_full_content,
    present_boxes,
)
from desktop.store.json_io import write_json
from desktop.utils.files import project_root

#: 信息条尾注：按本次框的来源（origin）标注。⚠️ `_apply_boxes` 与
#: `_show_boxes_info` 必须共用这一份——apply_boxes 的 info_text 也会写
#: 信息条，两处后缀不一致时后写的会覆盖先写的（曾丢过「（手动）」标记）。
ORIGIN_SUFFIX = {
    "manual": "（手动）",
    "auto": "",
    "fullpage": "（整页，未检测）",
}


class DetectMixin:
    """依赖宿主页面提供的属性：store/task_id、detect_viewer、log_view、
    detect_process/detect_cache、current_stage()。"""

    @staticmethod
    def _valid_boxes(boxes) -> list:
        """过滤存储中的 null 框（左右身份占位）。

        等价于 :func:`utils.box_geometry.present_boxes`——独立「检测文本框」
        模块页直接用那个纯函数，这里保留这个名字是因为本文件里到处都是它。
        """
        return present_boxes(boxes)

    # ------------------------------------------------------- 框类型（人工干预）
    #
    # 三条约定的落点（用户 2026-09-29 定）：类型在槽位里、半幅左右由位置决定、
    # 整幅显式且互斥。**交互顺序与文案的唯一实现在
    # `desktop/components/box_kinds.py::BoxKindEditor`**（与独立检测页共用）；
    # 本 Mixin 只提供宿主协议（预览控件 / 提示出口 / 落库 / 确认框）。

    def _box_editor(self) -> BoxKindEditor:
        """共享交互器（无状态，按需构造；宿主协议见下面 box_ 前缀一组）。"""
        return BoxKindEditor(self)

    # ---- BoxKindHost 协议（box_ 前缀，避免与页面其他成员撞名）----
    def box_viewer(self):
        return self.detect_viewer

    def box_toast(self, kind: str, title: str, content: str) -> None:
        self._toast(kind, title, content)

    def box_raw_slots(self, path_text: str) -> list:
        return self._raw_boxes_for(path_text)

    def box_page_is_full(self, _path_text: str) -> bool:
        # 查看器的整幅标志即当前页形态（编辑动作都发生在当前显示页上）
        return bool(self.detect_viewer.box_full_mode())

    def box_image_size(self, path_text: str):
        return self._image_size_for(path_text)

    def box_commit(self, path_text: str, slots: list, select_box=None) -> None:
        self._store_slots(path_text, slots, "manual", select_box=select_box)

    def box_confirm(self, title: str, body: str, yes_text: str, cancel_text: str) -> bool:
        # ⚠️ 延迟导入必须留在方法体内：自测靠替换 qfluentwidgets.Dialog 记录确认
        from qfluentwidgets import Dialog  # noqa: PLC0415

        dialog = Dialog(title, body, self.window())
        dialog.yesButton.setText(yes_text)
        dialog.cancelButton.setText(cancel_text)
        return bool(dialog.exec())

    def box_full_declined(self, index: int) -> None:
        self._on_box_selection_changed(index)  # 回填面板高亮，别停在「整幅」

    def box_current_path_text(self) -> str:
        path = self.detect_viewer.current_path()
        return str(path) if path else ""

    # ---- 旧入口：保留名字（自测按这些签名钉行为），实现委托共享交互器 ----
    def _box_kinds(self) -> list:
        """预览里每个框当前的类型（"left"/"right"/"full"）。"""
        return self.detect_viewer.box_kinds()

    def _on_box_selection_changed(self, index: int) -> None:
        """预览里选中态变化 → 回填面板的「选中框类型」与删除按钮。"""
        panel = self.panel_host_of_step("detect")
        setter = getattr(panel, "set_box_selection", None)
        if not callable(setter):
            return
        kinds = self._box_kinds()
        kind = kinds[index] if 0 <= index < len(kinds) else ""
        setter(index, kind)

    def _on_box_edit_rejected(self, message: str) -> None:
        """框数已达上限（整幅 1 / 半幅 2）→ 弹出可操作的提示。"""
        self._toast("warning", "框数已达上限", message)

    def _set_selected_box_kind(self, kind: str) -> None:
        """面板里点了「左框 / 右框 / 整幅」（整页模式拦截是本页特有）。"""
        path = self.detect_viewer.current_path()
        if path is None or not self.task_id:
            return
        if self._current_area() == WHOLE_PAGE_AREA:
            self._toast(
                "warning",
                "整页模式",
                "当前是整页模式（整页即唯一文本框）。要按左右/整幅标注，" "请先取消第二步的「整页模式」。",
            )
            return
        self._box_editor().set_kind(str(path), self.detect_viewer.selected_index(), kind)

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

    # ------------------------------------------------------- 检测结果统计
    #
    # 第二步右侧的「检测结果统计」：按页形态（fullcontent / harfcontent /
    # 单独页 / 无文本框）分类计数，默认总览、点进看页码明细。分类规则唯一
    # 实现在 `utils.box_geometry.classify_page_slots`；这里只负责**取数**与
    # 触发时机（切阶段、批量检测、单页检测、人工编辑框之后都要重算）。

    @staticmethod
    def _page_label(path: Path) -> str:
        """页码展示文案：数字页名去掉前导零（0007 → 7），其余原样。"""
        stem = path.stem
        return str(int(stem)) if stem.isdigit() else stem

    def _refresh_detect_stats(self) -> None:
        """重算右侧统计：清单 × 每页槽位（内存缓存优先，boxes.json 一次读盘）。"""
        widget = getattr(self, "detect_stats", None)
        if widget is None:
            return
        paths = self._manifest_paths()
        if not self.task_id or not paths:
            widget.set_results(len(paths), {})
            return
        boxes_all = self.store.detect_boxes_all(self.task_id)
        classes: dict[str, list[tuple[int, str]]] = {}
        for row, path in enumerate(paths):
            raw = self.detect_cache.get(str(path))
            if raw is None:
                raw = boxes_all.get(path.stem, ([], "auto"))[0]
            # ⚠️ 传给分类器的是**槽位**（保留 None）：单独页（双槽缺一侧）
            #    过滤掉 None 会被误判成整幅。
            classes.setdefault(classify_page_slots(raw), []).append((row, self._page_label(path)))
        widget.set_results(len(paths), classes)

    def _goto_stats_page(self, row: int) -> None:
        """统计明细里点了页码 → 预览跳到那一页（联动框重读）。"""
        strip = self.detect_viewer.strip
        if 0 <= row < strip.count():
            strip.setCurrentRow(row)

    def _raw_boxes_for(self, path_text: str) -> list:
        """某页**槽位**表示（保留 null，形态信息就在槽数里）。"""
        raw = self.detect_cache.get(str(path_text))
        if raw is None and self.task_id:
            entry = self.store.detect_boxes_entry(self.task_id, Path(path_text).stem)
            raw = entry[0] if entry else []
        return list(raw or [])

    def _store_slots(self, path_text: str, raw: list, origin: str, select_box=None) -> None:
        """把槽位结果落库 + 进缓存 + 刷预览（人工编辑与类型切换共用一条路径）。

        ``select_box`` 给定某个框时，重新上屏后仍选中**同一个框**（按坐标找回）——
        切换类型 / 整理槽位会改变框在列表里的次序，按下标保持会选错框。
        """
        image_key = Path(path_text).stem
        self.detect_cache[str(path_text)] = list(raw)
        if self.task_id:
            self.store.save_detect_boxes(self.task_id, image_key, list(raw), origin=origin)
        shown = self._valid_boxes(raw)
        index = -1
        if select_box is not None:
            target = list(select_box)
            index = next((i for i, b in enumerate(shown) if list(b) == target), -1)
        self._apply_boxes(path_text, raw, origin, select_index=index)
        self._refresh_reference_boxes()
        # 拖动/删框/切类型都会改这一页的形态 → 右侧统计同步重算
        self._refresh_detect_stats()

    def _apply_boxes(self, path_text: str, raw, origin: str | None = None, select_index: int = -1) -> None:
        """把某页的槽位结果画到大图上。

        显示用的名称/颜色**由控件按中心位置现算**（`image_view.box_styles`），
        这里只把 ``full``（整幅页）标志、一行文案与要选中的下标交给它——
        规则不抄第二份。
        """
        from desktop.components.viewers.image_view import box_names  # noqa: PLC0415

        shown = self._valid_boxes(raw)
        full = is_full_content(raw)
        size = self._image_size_for(path_text)
        qsize = QSize(size[0], size[1]) if size else QImageReader(str(path_text)).size()
        names = box_names(shown, size, full)
        info = self._describe_boxes(shown, names) + ORIGIN_SUFFIX.get(origin, "")
        self._show_boxes_info(shown, origin, names=names)
        self.detect_viewer.apply_boxes(
            shown,
            qsize,
            info,
            full=full,
            selected=select_index,
        )

    # ------------------------------------------------------------ 整页模式
    def _current_area(self) -> int:
        """当前 area（区域模式参数位于第三步 rembg 面板）。"""
        return int(self._current_detect_params()[0])

    def _image_size_for(self, path_text: str):
        """页面图片原始尺寸 (w, h)：优先 sizes.json，回退读图头。"""
        if self.task_id:
            size = self.store.image_size(self.task_id, Path(path_text).stem)
            if size and size[0] > 0 and size[1] > 0:
                return int(size[0]), int(size[1])
        head = QImageReader(str(path_text)).size()
        if head.isValid() and head.width() > 0:
            return head.width(), head.height()
        return None

    def _whole_page_boxes(self, path_text: str) -> list:
        """整页模式的默认框：整页边界 [0, 0, W, H]（与图片一样大）。"""
        size = self._image_size_for(path_text)
        if not size:
            return []
        return [[0, 0, size[0], size[1]]]

    def _whole_page_entry(self, path_text: str) -> tuple[list, str]:
        """整页模式下应展示的 (框, 来源)。

        只认人工框（origin=manual）：自动检测结果在整页模式下不生效——
        语义上整页模式就是「不检测」，旧 YOLO 结果留着只会让切换后画面困惑。
        用户手动画过框则沿用，其余一律整页。

        ⚠️ 返回的是**原始槽位**（保留 None），不是过滤后的框列表：槽数编码
        形态（半幅 2 槽 / 整幅 1 槽），过滤掉 None 后「手动半幅只剩一侧」会
        退化成 1 槽，被当成整幅。
        """
        entry = self.store.detect_boxes_entry(self.task_id, Path(path_text).stem) if self.task_id else None
        if entry and entry[1] == "manual" and self._valid_boxes(entry[0]):
            return list(entry[0]), "manual"
        return self._whole_page_boxes(path_text), "fullpage"

    def _current_boxes_for(self, path_text: str) -> list:
        """当前应展示的框（整页模式忽略自动检测结果）。"""
        if self._current_area() == WHOLE_PAGE_AREA:
            return self._whole_page_entry(path_text)[0]
        return self._valid_boxes(self.detect_cache.get(str(path_text)) or [])

    def _detect_image_selected(self, index: int, path_text: str) -> None:
        """选中图片：只展示已有检测结果，绝不自动执行检测（重负载操作需用户触发）。"""
        path = Path(path_text)
        key = str(path)
        self.detect_viewer.set_reference_boxes([])
        if self._current_area() == WHOLE_PAGE_AREA:
            boxes, origin = self._whole_page_entry(key)
            if not boxes:
                self.detect_viewer.info_label.setText("整页模式：读取不到页面尺寸，请先完成第一步提取。")
                return
            # 整页框是**派生**出来的：既不入库也不进缓存，避免切回 area=1
            # 时把整页框当成真实检测结果去拆左右页。
            self._apply_boxes(key, boxes, origin)
            self._refresh_reference_boxes()
            return
        if key in self.detect_cache:
            raw = self.detect_cache[key] or []
            if self._valid_boxes(raw):
                self._apply_boxes(key, raw)
            else:
                self._show_boxes_info([])
                # ⚠️ 无框时也要把预览的形态复位：否则上一页如果是整幅页，
                #    本页会沿用「整幅」的框数上限（只能画一个框）。
                self.detect_viewer.apply_boxes(
                    [],
                    QImageReader(key).size(),
                    self._describe_boxes([]),
                    full=is_full_content(raw),
                )
            self._refresh_reference_boxes()
            return
        # 优先使用库里的框（含手动调整过的）
        entry = self.store.detect_boxes_entry(self.task_id, path.stem)
        if entry is not None:
            boxes, origin = entry
            self.detect_cache[key] = boxes
            self._apply_boxes(key, boxes, origin)
            self._refresh_reference_boxes()
            return
        self.detect_viewer.info_label.setText("尚未检测：执行「本子任务」批量检测，或点击面板中的「检测本页」")

        self.detect_viewer.info_label.setText("尚未检测：执行「本子任务」批量检测，或点击面板中的「检测本页」")

    def _detect_current_page(self) -> None:
        """手动触发当前页的检测文本框（YOLO 子进程，重负载）。"""
        if not self.task_id:
            return
        path = self.detect_viewer.current_path()
        if not path:
            self._toast("warning", "提示", "请先完成提取，再执行检测。")
            return
        key = str(path)
        if self._current_area() == WHOLE_PAGE_AREA:
            # 整页模式：不启 YOLO 子进程，直接用整页框（可继续拖动/重画）
            boxes, origin = self._whole_page_entry(key)
            if not boxes:
                self._toast("warning", "提示", "读取不到页面尺寸，请先完成第一步提取。")
                return
            self._apply_boxes(key, boxes, origin)
            self._refresh_reference_boxes()
            self._toast(
                "info",
                "整页模式",
                "未做检测：整页作为一个文本框，可拖动四角调整或重画。",
            )
            return
        entry = self.store.detect_boxes_entry(self.task_id, Path(path).stem)
        if entry is not None and any(entry[0] or []):
            self.detect_cache[key] = entry[0]
            self._apply_boxes(key, entry[0], entry[1])
            self._refresh_reference_boxes()
            self._toast("info", "已有检测结果", "该页检测结果已存在，直接展示。")
            return
        # 执行权守卫：单页检测同样要抢 worker 槽位（一次 torch 冷启动 5 秒以上）。
        # ``replace=("单页检测",)`` 是刻意留的口子——连点不同页面时应该「换一页重检」
        # （_start_detect 会先断旧进程信号再杀），而不是弹一句"正在执行"卡住用户；
        # 但子任务在跑时必须拦住，那种情况下再塞一个检测只会两个 torch 抢内存。
        if not self._acquire_run("单页检测", replace=("单页检测",)):
            return
        self.detect_viewer.info_label.setText("正在检测文本框位置...")
        self.detect_cache[key] = None  # 防止重复派发
        self._start_detect(path)

    def _detect_boxes_for(self, path_text: str) -> list:
        """某页的检测框（内存缓存优先，其次 boxes.json）。

        整页模式（area=4）没有存档框时兜底为整页边界，使 rembg 预览/提交
        与第四步打印都按整页走，无需真的检测。
        """
        if self._current_area() == WHOLE_PAGE_AREA:
            return self._whole_page_entry(path_text)[0]
        boxes = self.detect_cache.get(str(path_text))
        if boxes is None:
            entry = self.store.detect_boxes_entry(self.task_id, Path(path_text).stem)
            boxes = entry[0] if entry else []
        return boxes or []

    def _current_detect_params(self) -> tuple[int, str | None]:
        """区域参数（area/border）现在位于 rembg 面板（步骤三）。

        ⚠️ 流程里**没有去底色这一步**时给 ``(1, None)``（左右分栏 + 无边距）
        ——那是 detect 的默认口径，**不是**去兜一个别的面板：自定义流程里把
        「图片去底色」删掉后，用户从来没填过 area，借别的面板读出来的是
        一份没人填过的表单。
        """
        host = self.panel_host_of_step("rembg")
        if host is None:
            return 1, None
        args = host.get_args()
        return args.get("area", 1), args.get("border")

    # ------------------------------------------------------ 整页模式开关联动
    def _set_whole_page_mode(self, on: bool) -> None:
        """第二步「整页模式」开关 → 第三步 area（4 ↔ 1）。

        area 的唯一事实来源是第三步面板，本开关只是它的入口：勾选即把 area
        切到 4，取消则回到 1，随后刷新检测预览（整页框立即画在边界上）。
        """
        panel = self.panel_host_of_step("rembg")
        if panel is None:
            return   # 流程里没有去底色这一步：没有 area 可切
        if getattr(panel, "whole_page_only", False):
            # area 锁 4（本流程里去底色拿不到检测框，1/2/3 没框可裁——
            # 见 ports.detect_feeds_rembg）：整页模式**关不掉**，取消勾选
            # 直接回填、area 保持 4，并说明原因（用户 2026-10-07）
            if not on:
                host = self.panel_host_of_step("detect")
                if host is not None:
                    host.set_whole_page(True)
                self._toast(
                    "info", "整页模式",
                    "本流程里「图片去底色」前面没有「检测文本框」，"
                    "区域模式 1/2/3 没有检测框可用，只能整页模式。",
                )
            return
        target = WHOLE_PAGE_AREA if on else 1
        if int(str(panel.area.currentText())[0]) != target:
            panel.area.setCurrentIndex(target - 1)  # 触发 _refresh_reference_boxes
            return
        path = self.detect_viewer.current_path()
        if path:
            self._detect_image_selected(0, str(path))

    def _sync_whole_page_checkbox(self) -> None:
        """第二步勾选状态回填自第三步 area（切阶段/改 area 时保持一致）。"""
        panel = self.panel_host_of_step("detect")
        setter = getattr(panel, "set_whole_page", None)
        if callable(setter):
            setter(self._current_area() == WHOLE_PAGE_AREA)

    def _refresh_reference_boxes(self) -> None:
        """按当前 area 参数重算参考框（虚线标注）。

        border 属于第三步（rembg/裁剪），detect 预览的参考框
        只体现检测框本身（area=1）或并集轮廓（area=2/3），不叠加 border。
        """
        path = self.detect_viewer.current_path()
        if path:
            boxes = self._current_boxes_for(str(path))
            if not boxes:
                self.detect_viewer.set_reference_boxes([])
            else:
                area, _border = self._current_detect_params()
                self.detect_viewer.set_reference_boxes(compute_final_boxes(boxes, area, None))
        # rembg 预览的区域同步刷新（显示范围跟随检测框 + area/border）
        self.rembg_viewer.refresh_display()

    def _show_boxes_info(self, boxes, origin: str | None = None, names=None) -> None:
        if boxes is None:
            self.detect_viewer.info_label.setText("正在检测文本框位置...")
            return
        suffix = ORIGIN_SUFFIX.get(origin, "")
        self.detect_viewer.info_label.setText(self._describe_boxes(boxes, names) + suffix)

    @staticmethod
    def _describe_boxes(boxes, names=None) -> str:
        """框列表 → 一行说明；names 与 boxes 对齐（整幅页显示「整幅」）。

        names 缺失时回退到「左框/右框」（旧的按序号命名）。
        """
        if not boxes:
            return "未检测到文本框"
        labels = list(names) if names else []
        return "  ｜  ".join(
            f"{(labels[i] if i < len(labels) else ('左框', '右框')[i % 2])}" f"({b[0]},{b[1]},{b[2]},{b[3]})"
            for i, b in enumerate(boxes)
        )

    def _save_manual_boxes(self, path_text: str, boxes) -> None:
        """预览区编辑线框后保存到库（origin=manual），不生成任何文件。

        ⚠️ 存的是**槽位**表示，不是"用户画了几个框"：
        - 整幅页 → 1 槽 ``[整幅]``；
        - 半幅页 → **恒 2 槽** ``[左, 右]``（缺失侧 null）。

        这样删到一个不剩或只剩一侧时，形态都不会从半幅变成整幅——用户报的
        "删掉整幅框后，右边的框自动变成了整幅" 就是按元素个数推断类型的后果。
        """
        if not self.task_id:
            return
        normalized = [[int(round(float(v))) for v in box] for box in boxes]
        size = self._image_size_for(path_text) or (0, 0)
        sel = self.detect_viewer.selected_index()
        sel_box = normalized[sel] if 0 <= sel < len(normalized) else None
        if not normalized:
            raw: list = []
        elif self.detect_viewer.box_full_mode() and len(normalized) == 1:
            raw = [normalized[0]]  # 整幅：只允许一个框（控件侧已按 max_boxes 拦住）
        else:
            # 半幅：恒 2 槽。⚠️ 万一"整幅页"却拿到多个框（不该发生），按半幅存——
            # 宁可形态变半幅，也不能悄悄丢掉用户画出来的框。
            raw = half_slots(normalized, size)
        self._store_slots(path_text, raw, "manual", select_box=sel_box)

    def _stop_detect_process(self) -> None:
        """停掉在跑的单页检测并释放执行权（返回列表/切任务前必须调）。

        ⚠️ 不停的话（2026-09-26 第二轮审计 H3）：检测是几秒到十几秒的慢活，
        用户中途「返回」或切到任务 B 后，旧进程的 boxes 事件才姗姗到达——
        而 ``self.task_id`` 已经是 B 了，``save_detect_boxes`` 就会把 A 的
        检测框写进 **B 的** boxes.json（两本书页名同为 0001 时直接污染裁剪）；
        若 A 已被删除，这里还会 FileNotFoundError 从 Qt 槽直接炸出去。
        与 ``_start_detect`` 的顶替逻辑同款：先断信号再 kill。
        """
        proc = self.detect_process
        if proc is None:
            return
        if proc.state() != QProcess.NotRunning:
            for signal in (
                proc.readyReadStandardOutput,
                proc.readyReadStandardError,
                proc.finished,
            ):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            proc.kill()
            proc.waitForFinished(1000)
        self.detect_process = None
        self._detect_out_buffer = ""
        self._release_run()

    def _start_detect(self, path: Path) -> None:
        old = self.detect_process
        if old is not None and old.state() != QProcess.NotRunning:
            # 关键：先断开旧进程的全部信号再杀。否则旧进程迟到的 finished
            # 会把 self.detect_process 清空，新进程的输出就被当成无主的丢弃。
            for signal in (
                old.readyReadStandardOutput,
                old.readyReadStandardError,
                old.finished,
            ):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            old.kill()
            old.waitForFinished(1000)
        runs_dir = self.store.runs_config_dir(self.task_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / "detect-config.json"
        write_json(
            config_path,
            {"mode": "detect", "image": str(path), "area": self._current_area()},
        )
        self.detect_process = QProcess(self)
        self._detect_out_buffer = ""  # stdout 半行重组缓冲（见 _read_detect_output）
        self.detect_process.setProgram(sys.executable)
        self.detect_process.setProcessEnvironment(self._worker_env())
        if getattr(sys, "frozen", False):
            arguments = ["--worker", "--config", str(config_path)]
        else:
            arguments = ["-m", "desktop.worker", "--config", str(config_path)]
            self.detect_process.setWorkingDirectory(str(project_root()))
        self.detect_process.setArguments(arguments)
        self.detect_process.readyReadStandardOutput.connect(self._read_detect_output)
        self.detect_process.readyReadStandardError.connect(self._read_worker_error)
        self.detect_process.finished.connect(self._detect_finished)
        self.detect_process.start()
        # 进程真的起来了 → 防抖窗口从这里开始计时（见 _run_launched_at）
        self._mark_run_launched()

    def _read_detect_output(self) -> None:
        if not self.detect_process:
            return
        data = bytes(self.detect_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        # ⚠️ 半行重组（审计 P2）：readyRead 只保证"有字节"，不保证按行切齐。
        # JSON Lines 事件被切成两半时，两半都 json.loads 失败 → boxes 事件
        # 整条静默丢弃，界面上表现为"检测完了但框没了"。把不完整的首段
        # 留到缓冲，与下一块拼上再解析；进程结束时缓冲里如有残留按坏行丢弃。
        data = getattr(self, "_detect_out_buffer", "") + data
        if "\n" in data:
            data, self._detect_out_buffer = data.rsplit("\n", 1)
        else:
            self._detect_out_buffer = data
            return
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "boxes":
                boxes = []
                try:
                    full = event.get("full")
                    if full:
                        # 整幅内容(fullcontent)：单个框、**单槽**
                        boxes = [[int(v) for v in full]]
                    else:
                        # 半幅：固定 2 槽 [左, 右]，缺失侧为 None（保留左右身份），
                        # 与批量检测的 _store_stage_boxes 完全一致的槽位约定。
                        for key in ("left", "right"):
                            value = event.get(key)
                            boxes.append([int(v) for v in value] if value else None)
                except (TypeError, ValueError):
                    # 畸形坐标（int() 转不动）宁可整条丢弃也别让槽抛异常——
                    # 那样 Qt 只往控制台打一句，界面毫无反应
                    self.log_view.append(f"检测输出格式异常，已忽略：{str(event)[:120]}")
                    continue
                if "image" not in event:
                    continue
                self.detect_cache[event["image"]] = boxes
                # 检测结果写回 boxes.json；无框不存，避免下次选中无法重新检测
                if any(boxes):
                    self.store.save_detect_boxes(self.task_id, Path(event["image"]).stem, boxes, origin="auto")
                self._apply_detect_result(Path(event["image"]), boxes)
            elif event.get("type") == "log":
                # 单页检测路径原先只认 boxes/detect_error，于是「模型加载用时」
                # 「detect xx.jpg …」这些记录全被丢掉，用户看不出执行了什么
                self.log_view.append(event.get("message", ""))
            elif event.get("type") == "detect_error":
                self.log_view.append(f"检测失败：{event.get('message')}")

    def _detect_finished(self, *_args) -> None:
        # sender() 是真正发出信号的那个进程：只有它仍是"当前进程"时才清空引用
        proc = self.sender()
        if proc is not None and proc is not self.detect_process:
            # 被顶替的旧进程（_start_detect 已断其信号，理论上到不了这里）：
            # 绝不能顺手释放执行权——新进程才持有它
            return
        # 结束后缓冲里若还有半行，是坏行/被截断的输出，直接丢弃防串到下一次
        self._detect_out_buffer = ""
        self.detect_process = None
        self._release_run()
        # 单页检测完成 → 该页形态可能变了，重算右侧统计
        self._refresh_detect_stats()

    def _apply_detect_result(self, path: Path, boxes) -> None:
        """自动检测结果到达 → 上屏（只在本页仍是预览页、且还停在第二步时应用）。"""
        if self.current_stage() != "detect":
            return
        if str(self.detect_viewer.current_path()) != str(path):
            return
        if str(path) in self.detect_cache:
            self.detect_cache[str(path)] = boxes or []
        self._apply_boxes(str(path), boxes or [])
        self._refresh_reference_boxes()
