# -*- coding: utf-8 -*-
"""独立模块「生成 PDF」：与任务流程无关，选一批成品图直接合成 PDF。

**复用共用组件**（``desktop/steps``）：页头下方横跨整幅的**大输入区**（拖图片
文件夹 / 拖一批图片 / 点选），右栏是 :class:`StepControl`（打印参数 + 输出目录 +
执行/中断），执行走 ``StepKernel`` → ``functions.get_function("print")``——
与任务流程第四步是同一条代码路径（连参数面板都是同一个 ``PrintPanel``）。

⚠️ **与任务流程第四步的有意差别：页序。** 流程里页序 = 第四步列表里用户手动排的
那份清单（``functions/print`` 的 ``files`` 参数）。独立页面按用户 2026-10-02 的
选择**不提供手动排序**——页序就是文件名顺序
（``utils.sort_utils.pdf_custom_sort_key``，与 CLI 直跑 ``guji run print <目录>``
一致）。要调页序，先用「拼图」模块把版面排好再拖过来。

⚠️ **产物形态与别的模块不同**：``print`` 产出的是**一个 PDF 文件**，不是一目录
图片。所以 ``StepSpec.artifact_is_file=True``——执行内核**不会**把
``function.outpath`` 覆盖成输出目录（那样会拿目录当文件路径写），并且把**真正的
PDF 路径**回传给 ``finished``；本页据此直接把它交给左侧的 PDF 预览控件。
"""

from __future__ import annotations

from pathlib import Path

from desktop.components.viewers import PdfViewerWidget
from desktop.modules.base import ModulePage
from desktop.steps import SourceZone, StepControl, spec_by_key
from desktop.ui.widgets import Card

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("print")


class PrintModulePage(ModulePage):
    """生成 PDF 模块页：拖入成品图（一批或一个文件夹）→ 调版面 → 合成 PDF。"""

    TITLE = _SPEC.title
    SUBTITLE = _SPEC.subtitle

    def __init__(self, parent=None):
        """建骨架与共用步骤控件。"""
        super().__init__(parent)
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
    def _build_preview(self) -> PdfViewerWidget:
        """左栏：生成出来的 PDF（复用共享的 PDF 预览控件）。"""
        self.viewer = PdfViewerWidget("还没有生成 PDF——先拖入成品图，再点「生成 PDF」")
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：整块交给共用步骤控件（打印面板 + 输出目录 + 执行）。"""
        card = Card()
        self.control = StepControl(_SPEC, zone=self.zone)
        self.control.status.connect(self.status)
        self.control.log.connect(self.log)
        self.control.source_changed.connect(self._on_source_changed)
        self.control.finished.connect(self._on_finished)
        self.control.failed.connect(self._on_failed)
        card.box.addWidget(self.control)
        return card

    # ------------------------------------------------------------------ 回调
    def _on_source_changed(self, source) -> None:
        """换了源：把「源 → 输出」与图片张数写到副标题上。"""
        if source is None:
            self.header.set_subtitle(_SPEC.subtitle)
            self.status("尚未选择图片", "info")
            return
        path = Path(source)
        count = len(self._source_images())
        tail = f"{count} 张图片" if count else "（未找到图片）"
        self.header.set_subtitle(f"{path}（{tail}） → {self.control.output()}")
        self.status(f"已选择，共 {count} 张图片将合成 PDF", "info")

    def _source_images(self) -> list[Path]:
        """源里的图片清单：源是文件就是它自己，是目录就取顶层图片。"""
        source = self.control.source()
        if source is None:
            return []
        source = Path(source)
        if source.is_file():
            return [source] if _SPEC.accepts_path(source) else []
        return _SPEC.listing(source)

    def _on_finished(self, output: str) -> None:
        """成功：``output`` 是**PDF 文件路径**（见 ``StepSpec.artifact_is_file``）。"""
        pdf = Path(output)
        if not pdf.is_file():
            self.toast("warning", "没有找到 PDF", f"输出位置没有 PDF 文件：{output}")
            return
        self.viewer.set_pdf(pdf)
        size_kb = max(1, pdf.stat().st_size // 1024)
        self.header.set_subtitle(f"{pdf}（{size_kb} KB）")
        self.toast("success", "已生成 PDF", pdf.name)

    def _on_failed(self, message: str) -> None:
        """失败：提示（状态行与日志已由共用控件写过）。"""
        self.toast("error", "生成失败", message)

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾：PDF 预览自己的后台线程 + 共用步骤控件的执行线程。"""
        self.viewer.shutdown_workers()
        self.control.shutdown()
        super().shutdown_workers()


__all__ = ["PrintModulePage"]
