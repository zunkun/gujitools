# -*- coding: utf-8 -*-
"""任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from desktop.services.print_plan import (
    drop_foreign_stage_pages, plan_print_entries,
)
from desktop.utils.files import default_open_dir, list_stage_images
from utils.sort_utils import pdf_custom_sort_key


class PrintListMixin:
    """依赖宿主页面提供的属性：store/task_id、print_preview、log_view、
    _toast()。"""

    def _print_thumb_provider(self, file_text: str):
        """第四步缩略条的小图来源：提交阶段预生成的缩略图（无则回落原图解码）。

        只服务 stages/rembg 的**提交产物**（缩略图按最终图 stem 存放，
        mtime 不旧于最终图才算有效——外部改动了最终图就自动失效回落）；
        拼版产物（stages/imposition）与用户手动「插入图片」的外部图没有预生成
        缩略图，照旧现解码。
        """
        if not self.task_id:
            return None
        try:
            page = Path(file_text)
            if page.parent != self.store.rembg_output_dir(self.task_id):
                return None
            thumb = self.store.rembg_thumbnails_dir(self.task_id) / f"{page.stem}.jpg"
            if (
                thumb.is_file()
                and thumb.stat().st_mtime >= page.stat().st_mtime
                and thumb.stat().st_size >= 512
            ):
                return thumb
        except OSError:
            return None
        return None

    def _print_entries(self) -> tuple[list[dict], dict]:
        """第四步待打印图片列表（规则见 services/print_plan.plan_print_entries）。

        ⚠️ **取图目录由拼版是否生效决定**（``ImpositionMixin.print_source_dir``）：
        拼版启用且有拼版页 → ``stages/imposition``（拼版已是成品整页），
        否则 → ``stages/rembg``（第三步「提交本次任务」的产物）。
        ``plan_print_entries`` 只认"一批成品图 + 顺序文档"，对来源无感。
        """
        source_dir = self.print_source_dir()
        rembg_files = sorted(
            list_stage_images(source_dir),
            key=lambda p: pdf_custom_sort_key(p.name),
        )
        doc = self.store.load_print_doc(self.task_id)
        # ⚠️ 来源切换（拼版 ↔ 去底色）后，旧来源那一批还留在 print.json 里；
        # 不剔掉就会被当成"用户插入的外部图片"追加进 PDF（见 print_plan 的
        # drop_foreign_stage_pages）。
        cleaned = drop_foreign_stage_pages(
            doc.get("pages") if doc else None,
            source_dir,
            self.store.task_dir(self.task_id) / "stages",
        )
        if doc and len(cleaned) != len(doc.get("pages") or []):
            doc = {**doc, "pages": cleaned}
            self.store.save_print_doc(self.task_id, doc)
        entries, new_doc = plan_print_entries(rembg_files, doc)
        self._print_doc_snapshot = new_doc
        if not doc or set(doc.get("rembg_snapshot") or []) != set(new_doc["rembg_snapshot"]):
            self.store.save_print_doc(self.task_id, new_doc)
        return entries, new_doc

    def _save_print_order(self, silent: bool = False) -> None:
        """列表拖动/删除后持久化顺序。

        ``silent=True`` 供版面编辑器复用：拖拽会频繁落盘，若每次都打一条
        「列表已更新」日志会淹没「第 N 页版面已更新」这条真正有用的信息。
        """
        if not self.task_id:
            return
        entries = self.print_preview.entries()
        doc = getattr(self, "_print_doc_snapshot", None) or {
            "rembg_snapshot": [], "pages": [],
        }
        doc["pages"] = [
            (
                {"file": e.get("file"), "label": e.get("label"),
                 "rect": e["rect"]}
                if e.get("rect") is not None
                else {"file": e.get("file"), "label": e.get("label")}
            )
            for e in entries
        ]
        try:
            self.store.save_print_doc(self.task_id, doc)
        except OSError as exc:
            # ⚠️ 落盘失败必须让用户看见（2026-09-26 审计）：任务目录被外部删除 /
            #    磁盘满时，原先这个异常会**直接从 Qt 槽里抛出去**（排序、拖动版面
            #    都是槽），只打印到控制台，用户看到的是"拖了没反应"且毫无原因。
            message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "列表未保存", message)
            return
        if not silent:
            self.log_view.append(
                f"待打印列表已更新（{self.print_preview.count()} 页）。"
            )

    def _insert_print_images(self) -> None:
        """插入外部图片到待打印列表末尾。"""
        if not self.task_id:
            return
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "插入图片",
            str(default_open_dir()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not filenames:
            return
        entries = self.print_preview.entries()
        for filename in filenames:
            source = Path(filename)
            entries.append({"file": str(source), "label": source.stem})
        try:
            self.store.save_print_pages(self.task_id, entries)
        except OSError as exc:
            # 同 _save_print_order：落盘失败必须可见，不能从 Qt 槽直接炸出去
            message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "列表未保存", message)
            return
        self.print_preview.set_entries(self._print_entries())
        self.log_view.append(f"已插入 {len(filenames)} 张图片到待打印列表。")

    def _latest_print_pdf_path(self) -> Path | None:
        """最近一次 print 执行产出的 PDF 路径（按 YAML pdf_name 解析）。"""
        if not self.task_id:
            return None
        pdf_name = "print.pdf"
        history = self.store.list_stage_runs(self.task_id, "print")
        if history:
            params = history[0].get("parameters", {})
            if params.get("pdf_name"):
                pdf_name = str(params["pdf_name"])
        out_dir = self.store.stage_dir(self.task_id, "print")
        candidate = out_dir / pdf_name
        if candidate.exists():
            return candidate
        # 兜底：目录下任意 pdf
        for cand in out_dir.glob("*.pdf"):
            return cand
        return None

    # ------------------------------------------------------- 取图来源 / 旧数据
    def print_source_stage(self) -> str:
        """第四步**当前**的取图来源阶段 key（``rembg_submit`` 或 ``imposition``）。

        ⚠️ 与 :meth:`print_source_dir` 同源：那边取路径、这边取 key，都走
        ``ports.print_pages_supplier(imposition_active())`` 这一次判定——
        "PDF 是从哪儿取的"只有一个答案，不许两处各判一次。
        """
        from desktop.steps.ports import print_pages_supplier

        # ⚠️ 用 **effective**（能不能真跑）而不是 active（勾没勾）：区域模式
        #    不支持拼版时，来源必须回到去底色，否则与 ``print_source_dir``
        #    给用户的预览不一致（界面说 A、执行做 B）。
        return print_pages_supplier(self.imposition_effective())

    def _print_source_switched(self) -> bool:
        """磁盘上那份 PDF 是不是**换了取图来源之后**生成的（旧数据）。

        用户 2026-10-03："之前没有启用拼板但生成了 pdf，此时再次启用拼板，
        则 PDF排版的数据要来源于拼板，**旧的数据不显示**"。所以这份判定是
        "旧数据不显示"的开关——判据与实现见
        :func:`desktop.services.stale_chain.print_source_switched`。
        """
        if not self.task_id:
            return False
        from desktop.services.stale_chain import print_source_switched

        return print_source_switched(
            self.store.all_stage_runs(self.task_id), self.print_source_stage()
        )

    def _current_print_pdf_path(self) -> Path | None:
        """**当前取图来源下**可用的 PDF；来源已切换则返回 ``None``。

        所有"给用户看/下载这份 PDF"的地方都走这里（第四步预览的下载按钮、
        下载动作本身），别再直接用 :meth:`_latest_print_pdf_path`——那个只
        回答"磁盘上有没有"，不回答"还是不是当前的"。
        """
        if self._print_source_switched():
            return None
        return self._latest_print_pdf_path()

    def _download_print_pdf(self) -> None:
        """将已生成的 PDF 另存到用户选择的位置（默认下载目录、同名文件）。"""
        if not self.task_id:
            return
        # ⚠️ 换了取图来源之后，磁盘上那份 PDF 属于**旧数据**，不再提供下载
        # （用户 2026-10-03："旧的数据不显示"）。先说清楚为什么不能下，
        # 别让用户以为是程序坏了。
        if self._print_source_switched():
            self._toast(
                "warning", "PDF 需要重新生成",
                "取图来源已改变（图片拼版开关），请先点「生成PDF」再下载。",
            )
            return
        # 优先用下载按钮当前绑定的 PDF；否则按最近一次 print 参数解析
        source = getattr(self.print_preview, "_pdf_path", None)
        if source is None or not Path(source).exists():
            source = self._latest_print_pdf_path()
        if source is None or not Path(source).exists():
            self._toast("warning", "无可下载 PDF", "请先执行「生成PDF」。")
            return
        source = Path(source)
        # 默认保存到系统「下载」目录，文件名与生成的 PDF 一致
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self, "下载 PDF", str(default_dir / source.name), "PDF 文件 (*.pdf)",
        )
        if not target:
            return
        # ⚠️ 复制进后台线程（审计 D2）：几百 MB 的 PDF 用主线程 copy2 会把
        # 界面冻住整个复制时长；复制期间不禁按钮但用标志防重入。
        if getattr(self, "_download_busy", False):
            self._toast("warning", "正在下载", "上一次下载还没完成。")
            return
        self._download_busy = True
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker([(source, Path(target))])
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self, w.finished, self._on_download_done, thread
                ),
                connect_queued(
                    self, w.failed,
                    lambda msg: self._on_download_done([], [(str(source), msg)]),
                    thread,
                ),
                w.finished.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_download_done(self, done: list, errors: list) -> None:
        """后台下载完成（主线程）：播报结果并解除防重入。"""
        self._download_busy = False
        if errors:
            self._toast("error", "下载失败", errors[0][1])
            return
        if not done:
            return
        target = done[0][1]
        self._toast("success", "下载完成", f"已保存到：{target}")
        self.log_view.append(f"PDF 已下载到：{target}")

    def _export_print_image(self) -> None:
        """把**当前页**的 A4 效果图另存为图片（单页；精度与 PDF 同级 300dpi）。

        渲染交给 ``print_preview``（它才懂排版口径），这里只负责对话框与提示：
        与「下载 PDF」保持同一套交互（默认下载目录、toast、写日志）。
        """
        default_name = self.print_preview.export_default_name()
        if not default_name:
            self._toast("warning", "无可导出页面", "请先在第四步添加要打印的图片。")
            return
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            self, "下载本页图片", str(default_dir / default_name),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg)",
        )
        if not target:
            return
        self._export_target = target
        self.print_preview.export_current_effect(target)

    def _on_export_finished(self, target: str) -> None:
        self._toast("success", "已导出本页图片", f"已保存到：{target}")
        self.log_view.append(f"本页图片已导出：{target}")

    def _on_export_failed(self, message: str) -> None:
        self._toast("error", "导出失败", message)
        self.log_view.append(f"导出本页图片失败：{message}")

    def _on_print_finished(self, printer_name: str) -> None:
        self._toast("success", "已发送打印", f"打印机：{printer_name}")
        self.log_view.append(f"本页已发送打印机：{printer_name}")

    def _on_print_failed(self, message: str) -> None:
        self._toast("error", "打印失败", message)
        self.log_view.append(f"打印本页失败：{message}")
