# -*- coding: utf-8 -*-
"""「导出YOLO标注」的卡片显隐与后台导出（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject

from desktop.services.detect_export import export_yolo, yolo_entries
from desktop.settings.config import app_config
from desktop.steps import StepKernel, StepRequest, callable_job
from desktop.utils.files import reveal_dir

if TYPE_CHECKING:
    from desktop.pages.taskdetail.detect._host import DetectHost
else:
    DetectHost = object


def _ask_yolo_export(*args, **kwargs):
    """延迟从本包取 ``ask_yolo_export``：自测按 ``detect.ask_yolo_export`` 打桩。"""
    from desktop.pages.taskdetail import detect as _pkg

    return _pkg.ask_yolo_export(*args, **kwargs)


class YoloExportMixin(DetectHost):
    """导出卡片显隐、导出请求与后台 job 的完成播报。"""
    # ------------------------------------------------- 「导出YOLO标注」
    #
    # 用户 2026-10-16：设置里打开「启用YOLO标注」后，第二步右栏**最底部**
    # 多一个「导出YOLO标注」。点它先弹窗（名称 = 父节点名 = 文件名前缀；
    # 导出目录按**任务**记住），确认后把本任务的页面导出成 YOLO 数据集切片。
    #
    # 与独立「检测文本框」模块页是**同一条业务链**（同一个
    # `services.detect_export.export_yolo` 与同一个弹窗），区别只在宿主：
    # 那边用页面的输出目录，这边用任务目录里的页面清单。
    #
    # 用户 2026-11-17：开发者模式删掉了，显隐只看 YOLO 开关。

    def _wire_yolo_export_card(self) -> None:
        """卡片建好后接线：订阅开关 + 立刻算一次显隐（视图层建卡片时调）。"""
        self._yolo_kernel: StepKernel | None = None
        #: 导出 job 的统计（见 ``detect_export.export_yolo`` 的返回值）
        self._yolo_summary: dict = {}
        cfg = app_config()
        # 配置项是长期存活的 QObject，页面销毁时 Qt 会自动断开
        cfg.yoloAnnotation.valueChanged.connect(self._sync_yolo_export_card)
        self._sync_yolo_export_card()

    def _sync_yolo_export_card(self) -> None:
        """按「当前是不是 detect 步骤 + YOLO 开关」显隐那张卡片。"""
        card = getattr(self, "yolo_export_card", None)
        if card is None:
            return
        # 构造期/还没任务时不做判断（那时步骤还无从谈起），保持隐藏
        stage = self.current_stage() if getattr(self, "task_id", None) else ""
        cfg = app_config()
        card.setVisible(
            stage == "detect"
            and bool(cfg.yoloAnnotation.value)
        )

    def export_yolo_labels(self) -> None:
        """导出 YOLO 数据集切片：先弹窗，确认后在后台线程复制图片 + 写标签。

        导出的页面清单就是第二步左栏那份（``_manifest_paths``，只含还存在的
        文件）；**没有框的页也照导**（图片 + 空标签 = 负样本，用户 2026-10-16）。
        弹窗的两个默认值都取**本任务上次记住的那一份**（名称 + 导出目录，存在
        任务目录的 ``ui.json`` 里，见 ``store.ui_state``）——用户 2026-10-16：
        「导出目录，和前缀都要保存下来，跟任务绑定」。

        **没记过时**：导出目录默认文档目录（``YoloExportPanel`` 自己兜底）、
        名称默认任务号（``_yolo_dataset_name``）。
        """
        if not self.task_id:
            return
        paths = self._manifest_paths()
        if not paths:
            self._toast(
                "warning", "还没有图片",
                "先执行第一步提取，或把图片放进任务目录的 stages/input，再导出。",
            )
            return
        if self._yolo_kernel is not None and self._yolo_kernel.busy():
            self._toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        saved = self.store.load_yolo_export_state(self.task_id)
        chosen = _ask_yolo_export(
            self.window(),
            directory=saved.get("directory") or None,
            name=saved.get("name") or self._yolo_dataset_name(),
        )
        if chosen is None:
            self._toast("info", "已取消", "没有导出任何文件。")
            return
        name, directory = chosen
        self.store.save_yolo_export_state(self.task_id, name, directory)
        entries = yolo_entries(paths, self._yolo_boxes_by_stem())
        kernel = self._ensure_yolo_kernel()
        self.yolo_export_button.setEnabled(False)
        self.log_view.append(
            f"开始导出 YOLO 数据集（{len(entries)} 页）→ {directory}"
        )
        request = StepRequest(
            dest=Path(directory),
            args={
                "name": name,
                # 任务号写进切片的 data.json（用户 2026-10-16）：校验工具据此
                # 自动找到 tasks/<id>/boxes.json 当基准，不必再回忆任务号
                "task_id": str(self.task_id),
                "source": self._yolo_source_name(),
                "entries": [(str(p), slots) for p, slots in entries],
            },
        )
        if not kernel.run(request):
            self.yolo_export_button.setEnabled(True)
            self._toast("warning", "正在导出", "上一次导出还没结束，请稍候。")

    def _yolo_dataset_name(self) -> str:
        """弹窗里「名称」的**默认**值 = ``b<任务号>``（用户 2026-10-16：
        「前缀默认改成 b{TASKID}，比如 b0020」）。

        ⚠️ 只是"没记过时"的兜底：一旦导出过一次，下次进来回填的是**上次那个
        名称**（存在任务目录的 ``ui.json`` 里，见 :meth:`export_yolo_labels`）
        ——用户改成 ``bxxxa`` 之后就一直用它，不会被这个默认值盖回去。

        ⚠️ 用任务号而不是任务名：任务名是中文书名（``XX大學圖書館藏…``），既长
        又要过 ``safe_dirname`` 洗一遍；任务号短、稳定、天然适合当切片前缀
        （一个任务 = 一本书，前缀天然唯一），前面加个 ``b`` 只是为了好看好认。
        """
        return f"b{self.task_id}" if self.task_id else ""

    def _yolo_source_name(self) -> str:
        """本任务源文件的**文件名**（写进切片的 ``data.json``，当来龙去脉）。

        空壳任务（还没选 PDF）没有源文件，回落任务名——总比留空强。
        """
        if self.source_path:
            return Path(self.source_path).name
        task = self.store.get_task(self.task_id) if self.task_id else None
        return str((task or {}).get("name") or "")

    def _yolo_boxes_by_stem(self) -> dict:
        """页面 stem → **槽位**（内存缓存优先，其次 ``boxes.json``）。

        与 :meth:`_refresh_detect_stats` 同一套取数口径：``detect_cache`` 里
        可能有 ``None``（检测在跑时的占位），``yolo_entries`` 会把它当空表
        （那一页就是负样本）。
        """
        boxes: dict[str, list] = {}
        if self.task_id:
            boxes_all = self.store.boxes_all_at(self._boxes_write_path())
            for stem, entry in boxes_all.items():
                boxes[stem] = list(entry[0] or [])
        for path_text, raw in self.detect_cache.items():
            boxes[Path(path_text).stem] = list(raw or [])
        return boxes

    def _ensure_yolo_kernel(self) -> StepKernel:
        """导出执行内核（懒建；纯函数 job 跑在后台线程，不冻界面）。

        ⚠️ 不复用第二步那条执行线：那条跑的是检测子进程（重、要抢执行权），
        导出是"读已有框 + 复制图片"的短活，互不影响。
        """
        if self._yolo_kernel is None:
            kernel = StepKernel(callable_job(self._yolo_job), cast("QObject", self))
            kernel.log.connect(self._on_yolo_log)
            kernel.finished.connect(self._on_yolo_finished)
            kernel.failed.connect(self._on_yolo_failed)
            self._yolo_kernel = kernel
        return self._yolo_kernel

    def _yolo_job(self, request: StepRequest, report) -> str | None:
        """导出 job（跑在 worker 线程）：复制图片 + 写标签。"""
        dest = request.dest
        assert dest is not None, "导出 job 必须带输出目录"

        def log(text: str) -> None:
            report("log", {"message": text})

        def progress(done: int, total: int) -> None:
            report("progress", {"done": done, "total": total})

        self._yolo_summary = export_yolo(
            [(Path(p), slots) for p, slots in request.args["entries"]],
            dest,
            str(request.args.get("name", "")),
            task_id=str(request.args.get("task_id", "")),
            source=str(request.args.get("source", "")),
            report=log,
            progress=progress,
        )
        return str(dest)

    def _on_yolo_log(self, message: str) -> None:
        self.log_view.append(message)

    def _on_yolo_finished(self, out_dir: str) -> None:
        """导出完成：恢复按钮 + 报清"几页有框、几页负样本、落点在哪"，
        并**打开导出目录**（用户 2026-10-16：「导出成功后，打开相应的目录」）。"""
        self.yolo_export_button.setEnabled(True)
        summary = self._yolo_summary or {}
        folder = summary.get("folder") or out_dir
        count = len(summary.get("labels") or [])
        detail = (
            f"{summary.get('labeled', 0)} 页有框（{summary.get('boxes', 0)} 个框）、"
            f"{summary.get('empty', 0)} 页负样本"
        )
        self.log_view.append(f"YOLO 数据集导出完成：{detail} → {folder}")
        self._toast("success", "已导出YOLO标注", f"{count} 页（{detail}）→ {folder}")
        if count:
            reveal_dir(folder)

    def _on_yolo_failed(self, message: str) -> None:
        self.yolo_export_button.setEnabled(True)
        self.log_view.append(f"导出YOLO标注失败：{message}")
        self._toast("error", "导出失败", message)
