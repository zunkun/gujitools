# -*- coding: utf-8 -*-
"""「去底色」独立模块页。

**复用共用组件**（``desktop/steps``）：页头下方是横跨整幅的**大输入区**
（拖图片、拖整个文件夹、点选），右栏是 :class:`StepControl`（参数 + 输出目录 +
执行/中断），执行走 :class:`StepKernel` → ``functions.get_function("rembg")``
——与任务流程第三步是同一条代码路径。本页不再自己写 worker 线程。

**独立**：不需要任务、不需要检测框——用户拖入**一整个图片文件夹**（批量）或
**单张图片**，结果用原图/结果对比控件（``RembgPreviewWidget``）看。

⚠️ 与任务流程的差别（有意为之）：第三步的 area/border 依赖第二步的检测框，
单文件模式下没有框可用，所以这里**只暴露「整图/去底参数」这一层**，area 固定
按「图像本身」处理，不参与框裁剪。
"""

from __future__ import annotations

from pathlib import Path

from desktop.components.viewers import RembgPreviewWidget
from desktop.modules.base import ModulePage
from desktop.steps import SourceZone, StepControl, spec_by_key
from desktop.ui.widgets import Card

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("rembg")


class RembgModulePage(ModulePage):
    """去底色模块页：拖入图片（单张或文件夹）→ 调参数 → 批量去底 → 对比看结果。"""

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
    def _build_preview(self) -> RembgPreviewWidget:
        """左栏：原图 / 去底结果对比（复用共享控件）。"""
        self.viewer = RembgPreviewWidget()
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：整块交给共用步骤控件（面板 + 输出目录 + 执行）。"""
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
        """换了源：把「源 → 输出」与图片张数显示到副标题上。"""
        if source is None:
            self.header.set_subtitle("")
            self.status("尚未选择图片", "info")
            return
        path = Path(source)
        count = len(self._source_images())
        suffix = "张图片" if count else "（未找到图片）"
        self.header.set_subtitle(
            f"{path}（{count} {suffix}） → {self.control.output()}"
        )
        self.status(f"已选择，共 {count} 张图片", "info")

    def _source_images(self) -> list[Path]:
        """源里的图片清单：源是文件就是它自己，是目录就取顶层图片。"""
        source = self.control.source()
        if source is None:
            return []
        source = Path(source)
        if source.is_file():
            return [source] if _SPEC.accepts_path(source) else []
        return _SPEC.listing(source)

    def _on_finished(self, out_dir: str) -> None:
        """成功：把「原图 → 结果」两组图塞进对比控件。"""
        sources = [str(p) for p in self._source_images()]
        if not sources:
            self.toast("warning", "没有产出", "源里没有找到图片。")
            return
        # RembgPreviewWidget.set_images(原图列表, 结果目录, ...)：
        # 传输出目录让它按同名文件找去底结果并做成左右对比。
        self.viewer.set_images(sources, Path(out_dir))
        self.toast("success", "处理完成", f"共处理 {len(sources)} 张图片。")

    def _on_failed(self, message: str) -> None:
        """失败：提示（状态行与日志已由共用控件写过）。"""
        self.toast("error", "处理失败", message)

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾共用步骤控件的执行线程（壳层关窗口时会调到这里）。"""
        self.control.shutdown()
        super().shutdown_workers()


__all__ = ["RembgModulePage"]
