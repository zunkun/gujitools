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
from utils.box_geometry import compute_final_boxes
from desktop.store.json_io import write_json
from desktop.utils.files import project_root


class DetectMixin:
    """依赖宿主页面提供的属性：store/task_id、detect_viewer、log_view、
    detect_process/detect_cache、current_stage()。"""

    @staticmethod
    def _valid_boxes(boxes) -> list:
        """过滤存储中的 null 框（左右身份占位）。"""
        if not isinstance(boxes, list):
            return []
        return [b for b in boxes if b]

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
        """
        entry = (
            self.store.detect_boxes_entry(self.task_id, Path(path_text).stem)
            if self.task_id
            else None
        )
        if entry and entry[1] == "manual":
            boxes = self._valid_boxes(entry[0])
            if boxes:
                return boxes, "manual"
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
                self.detect_viewer.info_label.setText(
                    "整页模式：读取不到页面尺寸，请先完成第一步提取。"
                )
                return
            # 整页框是**派生**出来的：既不入库也不进缓存，避免切回 area=1
            # 时把整页框当成真实检测结果去拆左右页。
            self._show_boxes_info(boxes, origin)
            size = self._image_size_for(key) or (0, 0)
            self.detect_viewer.apply_boxes(
                boxes, QSize(size[0], size[1]), self._describe_boxes(boxes)
            )
            self._refresh_reference_boxes()
            return
        if key in self.detect_cache:
            boxes = self._valid_boxes(self.detect_cache[key])
            self._show_boxes_info(boxes)
            if boxes:
                size = QImageReader(key).size()
                self.detect_viewer.apply_boxes(
                    boxes, size, self._describe_boxes(boxes)
                )
            self._refresh_reference_boxes()
            return
        # 优先使用库里的框（含手动调整过的）
        entry = self.store.detect_boxes_entry(self.task_id, path.stem)
        if entry is not None:
            boxes, origin = entry
            self.detect_cache[key] = boxes
            display = self._valid_boxes(boxes)
            self._show_boxes_info(display, origin)
            if display:
                size = QImageReader(key).size()
                self.detect_viewer.apply_boxes(display, size, self._describe_boxes(display))
            self._refresh_reference_boxes()
            return
        self.detect_viewer.info_label.setText(
            "尚未检测：执行「本子任务」批量检测，或点击面板中的「检测本页」"
        )

    def _detect_current_page(self) -> None:
        """手动触发当前页的文本框检测（YOLO 子进程，重负载）。"""
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
            self._show_boxes_info(boxes, origin)
            size = self._image_size_for(key) or (0, 0)
            self.detect_viewer.apply_boxes(
                boxes, QSize(size[0], size[1]), self._describe_boxes(boxes)
            )
            self._refresh_reference_boxes()
            self._toast(
                "info", "整页模式",
                "未做检测：整页作为一个文本框，可拖动四角调整或重画。",
            )
            return
        entry = self.store.detect_boxes_entry(self.task_id, Path(path).stem)
        if entry is not None and any(entry[0] or []):
            display = self._valid_boxes(entry[0])
            self.detect_cache[key] = entry[0]
            self._show_boxes_info(display, entry[1])
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
            entry = self.store.detect_boxes_entry(
                self.task_id, Path(path_text).stem
            )
            boxes = entry[0] if entry else []
        return boxes or []

    def _current_detect_params(self) -> tuple[int, str | None]:
        """区域参数（area/border）现在位于 rembg 面板（步骤三）。"""
        args = self.control_stack.widget(2).get_args()
        return args.get("area", 1), args.get("border")

    # ------------------------------------------------------ 整页模式开关联动
    def _set_whole_page_mode(self, on: bool) -> None:
        """第二步「整页模式」开关 → 第三步 area（4 ↔ 1）。

        area 的唯一事实来源是第三步面板，本开关只是它的入口：勾选即把 area
        切到 4，取消则回到 1，随后刷新检测预览（整页框立即画在边界上）。
        """
        panel = self.control_stack.widget(2)
        target = WHOLE_PAGE_AREA if on else 1
        if int(str(panel.area.currentText())[0]) != target:
            panel.area.setCurrentIndex(target - 1)  # 触发 _refresh_reference_boxes
            return
        path = self.detect_viewer.current_path()
        if path:
            self._detect_image_selected(0, str(path))

    def _sync_whole_page_checkbox(self) -> None:
        """第二步勾选状态回填自第三步 area（切阶段/改 area 时保持一致）。"""
        panel = self.control_stack.widget(1)
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
                self.detect_viewer.set_reference_boxes(
                    compute_final_boxes(boxes, area, None)
                )
        # rembg 预览的区域同步刷新（显示范围跟随检测框 + area/border）
        self.rembg_viewer.refresh_display()

    def _show_boxes_info(self, boxes, origin: str | None = None) -> None:
        if boxes is None:
            self.detect_viewer.info_label.setText("正在检测文本框位置...")
            return
        suffix = {
            "manual": "（手动）", "auto": "", "fullpage": "（整页，未检测）",
        }.get(origin, "")
        self.detect_viewer.info_label.setText(self._describe_boxes(boxes) + suffix)

    @staticmethod
    def _describe_boxes(boxes) -> str:
        if not boxes:
            return "未检测到文本框"
        names = ("左框", "右框")
        return "  ｜  ".join(
            f"{names[i % 2]}({b[0]},{b[1]},{b[2]},{b[3]})" for i, b in enumerate(boxes)
        )

    def _save_manual_boxes(self, path_text: str, boxes) -> None:
        """预览区编辑线框后保存到库（origin=manual），不生成任何文件。"""
        if not self.task_id:
            return
        normalized = [[int(round(float(v))) for v in box] for box in boxes]
        image_key = Path(path_text).stem
        self.detect_cache[str(path_text)] = normalized
        self.store.save_detect_boxes(
            self.task_id, image_key, normalized, origin="manual"
        )
        self._show_boxes_info(normalized, "manual")
        self._refresh_reference_boxes()

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
        for line in data.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "boxes":
                boxes = []
                for key in ("left", "right"):
                    if event.get(key):
                        boxes.append([int(v) for v in event[key]])
                self.detect_cache[event["image"]] = boxes
                # 检测结果写回 boxes.json；无框不存，避免下次选中无法重新检测
                if boxes:
                    self.store.save_detect_boxes(
                        self.task_id, Path(event["image"]).stem, boxes, origin="auto"
                    )
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
        self.detect_process = None
        self._release_run()

    def _apply_detect_result(self, path: Path, boxes) -> None:
        if self.current_stage() != "detect":
            return
        if str(self.detect_viewer.current_path()) != str(path):
            return
        size = QImageReader(str(path)).size()
        self.detect_viewer.apply_boxes(
            boxes or [], size, self._describe_boxes(boxes)
        )
        if str(path) in self.detect_cache:
            self.detect_cache[str(path)] = boxes or []
        self._refresh_reference_boxes()
