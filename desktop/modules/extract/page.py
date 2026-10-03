# -*- coding: utf-8 -*-
"""「图片提取」独立模块页。

**复用共用组件**：页头下方是横跨整幅的**大输入区**
（:class:`~desktop.steps.source_zone.SourceZone`：拖 PDF、点选），右栏是
:class:`~desktop.steps.control.StepControl`（参数 + 输出目录 + 执行/中断），
执行走 :class:`~desktop.steps.kernel.StepKernel` →
``functions.get_function("extract")``——与 CLI 同一条代码路径，本页不再
自己写 worker 线程；这些外设全部由 :class:`StepModulePage` 收口。

**左栏是「缩略图条 + 右侧大图」一种形态走到底**（用户 2026-10-03）：

- **未提取**：选完 PDF 立刻把每页渲成缩略图（缓存在
  ``~/Documents/guji/singletask/图片提取/thumbnails/<书>/``），左栏按「第 N 页」
  列出，点哪页右侧就按需渲那一页的**高清**大图；
- **提取完成**：清单换成输出目录里的**提取出的图片**，直接看结果。

⚠️ 此前这里是个**上下分栏**（上半 PDF 预览 + 下半提取结果），两个控件各带一套
缩略图条与线程。现在只剩一个 :class:`ImageViewerWidget`——「所有独立任务左侧
都是缩略图」这条要求在本页就落在这一个控件上。

⚠️ **产物位置不动**：输出目录仍默认在源 PDF 旁边
（:meth:`desktop.steps.spec.StepSpec.default_output`）。singletask 下面**只放
缩略图缓存**，不放产物（用户 2026-10-03 明确「生成目录按照原先的」）。
"""

from __future__ import annotations

import re
from pathlib import Path

from desktop.components.viewers import ImageViewerWidget
from desktop.modules.base import StepModulePage
from desktop.modules.thumb_source import ThumbSourceMixin
from desktop.steps import spec_by_key

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("extract")

#: 认得的结果图片后缀（与 spec.IMAGE_FILTER 同义；这里独立列一份是为了
#: 不把"读目录里的图片"这件事绑在对话框过滤串上）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class ExtractModulePage(StepModulePage, ThumbSourceMixin):
    """图片提取模块页：选 PDF → 看页缩略图 → 调参数 → 执行 → 看提取结果。"""

    SPEC = _SPEC

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImageViewerWidget:
        """左栏：**缩略图条 + 大图**（复用共享控件，与其余独立任务页同一种形态）。

        未提取时它是「这本 PDF 的每一页」，提取完成后是「提取出的图片」——
        两种形态共用这一个控件，见 :meth:`_on_source_changed` 与
        :meth:`on_result`。
        """
        self.viewer = ImageViewerWidget(
            editable=False,
            empty_hint="选好 PDF 之后，这里会立刻显示每一页",
        )
        return self.viewer

    # ------------------------------------------------------------------ 源
    def _on_source_changed(self, source) -> None:
        """换源：先把 PDF 的页缩略图显示出来，再走基类那套显隐/副标题。

        ⚠️ **顺序要紧**：先 ``show_source``（起缩略图 pass）再 ``super()``——
        基类会 ``source_summary()`` 并据此改副标题，缩略图那边是纯后台的，
        两者互不依赖，但让「选完就能翻页看」这条反馈先发出去更符合直觉。
        """
        self.show_source(source)
        super()._on_source_changed(source)

    # ------------------------------------------------------------------ 编辑
    def edit_effect_note(self, path: Path) -> str:
        """编辑器改了提取出来的图片：**这张图本身就是这一步的产物**。

        未提取时左栏列的是 PDF 的页缩略图（虚拟页，没有可回写的文件，右键
        不提供「编辑图片」），所以能走到这里的只有产物图。
        """
        return f"已更新提取图片「{path.name}」；检测、去底色读的就是这张图。"

    # ------------------------------------------------------------------ 结果
    def on_result(self, out_root: Path, _result: dict) -> None:
        """成功：清单换成输出目录里的图片（**从此左栏就是提取结果**）。

        ``show_images`` 内部会经 ``set_images`` 退出 PDF 页模式
        （见 :meth:`ImageViewerWidget.set_images` 的注释）——不退出的话点哪页
        都会回到 PDF 的同一页。
        """
        images = collect_result_images(out_root)
        if images:
            self.show_images(images)
            self.toast("success", "提取完成", f"共生成 {len(images)} 张图片。")
        else:
            self.toast("warning", "没有产出", "输出目录里没有找到图片。")

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾查看器自己的后台线程（页缩略图 pass / 大图渲染）。"""
        self.viewer.shutdown_workers()
        super().shutdown_workers()


def _natural_key(path: str) -> tuple:
    """按文件名里的数字自然排序（page2 排在 page10 前面）。"""
    parts = re.split(r"(\d+)", Path(path).name)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


def collect_result_images(out_root: str | Path) -> list[Path]:
    """收集提取产物图片，**同名只保留一份**。

    ⚠️ 为什么要去重（用户 2026-10-03 报）：``rglob("*")`` 会把
    ``<输出>/1.jpg``（单 PDF 时的平铺产物）**和**
    ``<输出>/<PDF名>/images/1.jpg``（命令自己的嵌套布局残留）一起收进来，
    同一个 PDF 跑两遍就会留下两套 ⇒ 预览里**每页出现两次**（截图里两个
    ``1.jpg``），用户以为程序重复处理了。

    规则：**顶层优先，其次按路径排序取第一个**。顶层就是"应该在那儿"的位置
    （平铺的产物），嵌套里的是残留；同名冲突时不覆盖、不删除——**只影响
    预览显示**，产物原样留给用户。
    """
    found: dict[str, Path] = {}
    for path in Path(out_root).rglob("*"):
        if path.suffix.lower() not in _IMAGE_EXTS or not path.is_file():
            continue
        key = path.name.lower()
        previous = found.get(key)
        if previous is None or len(path.parts) < len(previous.parts):
            found[key] = path
    return sorted(found.values(), key=_natural_key)


__all__ = ["ExtractModulePage", "collect_result_images"]
