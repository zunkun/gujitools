# -*- coding: utf-8 -*-
"""已生成 PDF 的定位、下载与导出打印（从原 ``print_list.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.pages.taskdetail.print_list._qt import QFileDialog
from desktop.pages.taskdetail.print_list.helpers import _parent

if TYPE_CHECKING:
    from desktop.pages.taskdetail.print_list._host import PrintListHost
else:
    PrintListHost = object


class PrintPdfMixin(PrintListHost):
    """PDF 路径解析、旧数据判定、另存与逐页导出。"""
    def _latest_print_pdf_path(self) -> Path | None:
        """最近一次 print 执行产出的 PDF 路径（按 YAML pdf_name 解析）。

        ⚠️ 目录与历史都按**当前 PDF排版节点**取（B 方案）：两个「PDF排版」节点
        各有自己的输出目录（``stages/print[~<节点>]``），按阶段取会把 A 节点的
        PDF 当成 B 节点的产物——用户点下载拿到的是另一个节点的文件。
        """
        if not self.task_id:
            return None
        node = self.node_of_stage("print")
        pdf_name = "print.pdf"
        history = (
            self.store.list_node_runs(self.task_id, node, "print")
            if node
            else self.store.list_stage_runs(self.task_id, "print")
        )
        if history:
            params = history[0].get("parameters", {})
            if params.get("pdf_name"):
                pdf_name = str(params["pdf_name"])
        out_dir = self.store.scoped_stage_dir(self.task_id, node, "print")
        candidate = out_dir / pdf_name
        if candidate.exists():
            return candidate
        # 兜底：目录下任意 pdf
        for cand in out_dir.glob("*.pdf"):
            return cand
        return None

    # ------------------------------------------------------- 取图来源 / 旧数据
    def print_source_stage(self) -> str:
        """第四步**当前**的取图来源阶段 key（``rembg`` 或 ``imposition``）。

        ⚠️ 与 :meth:`print_source_dir` 同源：那边取路径、这边取 key，都走
        ``ports.print_pages_supplier(imposition_active())`` 这一次判定——
        "PDF 是从哪儿取的"只有一个答案，不许两处各判一次。
        """
        from desktop.steps.ports import print_pages_supplier

        # ⚠️ 用 **effective**（能不能真跑）而不是 active（勾没勾）：图里没有
        #    拼版节点时，来源必须回到去底色，否则与 ``print_source_dir``
        #    给用户的预览不一致（界面说 A、执行做 B）。
        return print_pages_supplier(self.imposition_effective())

    def _print_source_switched(self) -> bool:
        """磁盘上那份 PDF 是不是**换了取图来源之后**生成的（旧数据）。

        用户 2026-10-03："之前没有启用拼版但生成了 pdf，此时再次启用拼版，
        则 PDF排版的数据要来源于拼版，**旧的数据不显示**"。所以这份判定是
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
        """**当前取图来源下**可用的 PDF；来源或取图内容已变则返回 ``None``。

        所有"给用户看/下载这份 PDF"的地方都走这里（第四步预览的下载按钮、
        下载动作本身），别再直接用 :meth:`_latest_print_pdf_path`——那个只
        回答"磁盘上有没有"，不回答"还是不是当前的"。
        """
        if self._print_source_switched() or getattr(self, "_print_data_stale", False):
            return None
        return self._latest_print_pdf_path()

    def can_delete_selected_print(self) -> bool:
        """顶部菜单「编辑 → 删除选中」的启用判据：正在第四步且有选中项。"""
        return (
            self.current_stage() == "print"
            and bool(self.print_preview.strip.selectedItems())
        )

    def delete_selected_print(self) -> None:
        """顶部菜单「编辑 → 删除选中」：删掉缩略图条里选中的待打印图。"""
        if self.can_delete_selected_print():
            self.print_preview.remove_selected()

    def _download_print_pdf(self) -> None:
        """将已生成的 PDF 另存到用户选择的位置（默认下载目录、同名文件）。"""
        if not self.task_id:
            return
        # ⚠️ 换了取图来源、或取图目录里的图片变了（拼版成品重存）之后，磁盘上那份
        #    PDF 属于**旧数据**，不再提供下载（用户 2026-10-03："旧的数据不显示"）。
        #    先说清楚为什么不能下，别让用户以为是程序坏了。
        source_switched = self._print_source_switched()
        if source_switched or getattr(self, "_print_data_stale", False):
            reason = (
                "取图来源已改变（图片拼版开关）" if source_switched
                else "取图里的图片已更新（拼版成品 / 去底色成品变了）"
            )
            self._toast(
                "warning",
                "PDF 需要重新生成",
                f"{reason}，请先点「生成PDF」再下载。",
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
            _parent(self),
            "下载 PDF",
            str(default_dir / source.name),
            "PDF 文件 (*.pdf)",
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
                connect_queued(self, w.finished, self._on_download_done, thread),
                connect_queued(
                    self,
                    w.failed,
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
            _parent(self),
            "下载本页图片",
            str(default_dir / default_name),
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
