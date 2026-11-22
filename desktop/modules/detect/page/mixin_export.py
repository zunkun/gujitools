# -*- coding: utf-8 -*-
"""检测文本框独立页的导出线（坐标 JSON / 标注图 / YOLO，从原 ``page.py`` 拆出）。"""

from __future__ import annotations

import time
from pathlib import Path

import PySide6.QtWidgets as QtWidgets

from desktop.services.detect_export import (
    entries_from_mapping,
    export_annotated,
    export_yolo,
    yolo_entries,
)
from desktop.steps import StepRequest
from desktop.store.json_io import read_json, write_json
from desktop.utils.files import default_open_dir, singletask_yolo_export_path

from .constants import (
    EXPORT_NAME,
    _EXPORT_ANNOTATED,
    _EXPORT_YOLO,
    _YOLO_EXPORT_DIR_KEY,
    _YOLO_EXPORT_NAME_KEY,
)


class ExportMixin:
    """坐标 JSON、标注图与 YOLO 数据集的导出执行线与回调。"""

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
        kept = {
            k: v for k, v in self._corrected_slots_map().items() if any(v)
        }
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
        directory = QtWidgets.QFileDialog.getExistingDirectory(
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
            self.source_images(), self._corrected_slots_map()
        )

    # ------------------------------------------------------------ 导出 YOLO 标注
    def export_yolo_labels(self) -> None:
        """导出 YOLO 数据集切片：先弹窗填**名称**与选**导出目录**（用户 2026-10-16）。

        弹窗的两个默认值都取**上次记住的那一份**（独立任务页记在
        ``singletask/<独立功能>/yolo_export.json``，见
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
        chosen = self._ask_yolo_export(
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
            entries=yolo_entries(images, self._corrected_slots_map()),
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
        """本页「导出YOLO标注」的记忆文件（按独立功能一份，见 files.py 的说明）。"""
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
        # ⚠️ 带上整本书结论：单栏书里那个横跨整页的框在导出图上也要标「半幅」，
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
            self._reveal_dir(folder)
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
