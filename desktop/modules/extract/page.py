# -*- coding: utf-8 -*-
"""「图片提取」独立模块页。

**复用共用组件**（``desktop/steps``）：页头下方是横跨整幅的**大输入区**
（:class:`~desktop.steps.source_zone.SourceZone`：拖 PDF、拖文件夹、点选），
右栏是 :class:`StepControl`（参数 + 输出目录 + 执行/中断），执行走
:class:`StepKernel` → ``functions.get_function("extract")``——与 CLI 同一条
代码路径，本页不再自己写 worker 线程。

**独立**：不依赖任务、不依赖 ``TaskDetailPage``——用户自选 PDF 与输出目录，
在后台线程里跑，产出的图片用现成的 ``ImageViewerWidget`` 展示。三个模块各持
自己的一份 :class:`StepControl`，因此**互不影响**。
"""

from __future__ import annotations

import re
from pathlib import Path

from desktop.components.viewers import ImageViewerWidget
from desktop.modules.base import ModulePage
from desktop.steps import SourceZone, StepControl, spec_by_key
from desktop.ui.widgets import Card

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("extract")

#: 认得的结果图片后缀（与 spec.IMAGE_FILTER 同义；这里独立列一份是为了
#: 不把"读目录里的图片"这件事绑在对话框过滤串上）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class ExtractModulePage(ModulePage):
    """图片提取模块页：选 PDF → 调参数 → 执行 → 看结果。"""

    TITLE = _SPEC.title
    SUBTITLE = _SPEC.subtitle

    def __init__(self, parent=None):
        """建骨架与共用步骤控件；预览区是空态，等执行完再灌结果。"""
        super().__init__(parent)
        self.status("尚未选择 PDF")

    # ------------------------------------------------------------------ 输入
    def _build_input(self) -> SourceZone:
        """页头下方的**大输入区**：拖 PDF / 拖文件夹 / 点选（共用组件）。"""
        self.zone = SourceZone(_SPEC)
        # 归一化失败（拖进来的不是 PDF）时，用页头 toast 说话——大输入区自己
        # 只负责发信号，"怎么说给用户听"是页面的事。
        self.zone.rejected.connect(
            lambda message: self.toast("warning", "这个用不上", message)
        )
        return self.zone

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImageViewerWidget:
        """左栏：提取结果图片浏览（复用共享控件，自带缩略图条与编辑入口）。"""
        self.viewer = ImageViewerWidget(
            editable=False,
            empty_hint="尚未提取。把 PDF 拖到上面的输入框，再点「开始提取」",
        )
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：整块交给共用步骤控件（面板 + 输出目录 + 执行）。"""
        card = Card()
        self.control = StepControl(_SPEC, zone=self.zone)
        # StepControl 只发信号、不弹提示；页头状态行与日志区由本页负责呈现
        self.control.status.connect(self.status)
        self.control.log.connect(self.log)
        self.control.source_changed.connect(self._on_source_changed)
        self.control.finished.connect(self._on_finished)
        self.control.failed.connect(self._on_failed)
        card.box.addWidget(self.control)
        return card

    # ------------------------------------------------------------------ 回调
    def _on_source_changed(self, source) -> None:
        """换了源：把「PDF → 输出目录」显示到副标题上。"""
        if source is None:
            self.header.set_subtitle("")
            self.status("尚未选择 PDF", "info")
            return
        self.header.set_subtitle(f"{Path(source).name} → {self.control.output()}")
        self.status("已选择输入，点击「开始提取」", "info")

    def _on_finished(self, out_root: str) -> None:
        """成功：把输出目录里的图片塞给预览控件。"""
        images = sorted(
            (
                str(p)
                for p in Path(out_root).rglob("*")
                if p.suffix.lower() in _IMAGE_EXTS
            ),
            key=_natural_key,
        )
        if images:
            self.viewer.set_images(images)
            self.toast("success", "提取完成", f"共生成 {len(images)} 张图片。")
        else:
            self.toast("warning", "没有产出", "输出目录里没有找到图片。")

    def _on_failed(self, message: str) -> None:
        """失败：提示（状态行与日志已由共用控件写过）。"""
        self.toast("error", "提取失败", message)

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾共用步骤控件的执行线程（壳层关窗口时会调到这里）。"""
        self.control.shutdown()
        super().shutdown_workers()


def _natural_key(path: str) -> tuple:
    """按文件名里的数字自然排序（page2 排在 page10 前面）。"""
    parts = re.split(r"(\d+)", Path(path).name)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


__all__ = ["ExtractModulePage"]
