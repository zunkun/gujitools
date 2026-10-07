# -*- coding: utf-8 -*-
"""「去底色」独立模块页。

**复用共用组件**：页头下方是横跨整幅的**大输入区**（拖图片、拖整个文件夹、
点选），右栏是 :class:`~desktop.steps.control.StepControl`（参数 + 输出目录 +
执行/中断），执行走 :class:`~desktop.steps.kernel.StepKernel` →
``functions.get_function("rembg")``——与任务流程第三步是同一条代码路径。
这些外设由 :class:`StepModulePage` 收口，本页只补两件事：左栏用哪个预览
控件、产物怎么上屏（附带的"副标题带图片张数"由 ``source_summary`` 覆盖）。

**独立**：不需要任务、不需要检测框——用户拖入**一整个图片文件夹**（批量）或
**单张图片**，结果用原图/结果对比控件（``RembgPreviewWidget``）看。

⚠️ 与任务流程的差别（有意为之）：第三步的 area/border 依赖第二步的检测框，
单文件模式下没有框可用，所以这里**只暴露「整图/去底参数」这一层**，area 固定
按「图像本身」处理，不参与框裁剪。
"""

from __future__ import annotations

from pathlib import Path

from desktop.components.viewers import RembgPreviewWidget
from desktop.modules.base import StepModulePage
from desktop.modules.thumb_source import ThumbSourceMixin
from desktop.steps import spec_by_key

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("rembg")


class RembgModulePage(StepModulePage, ThumbSourceMixin):
    """去底色模块页：拖入图片（单张或文件夹）→ 调参数 → 批量去底 → 对比看结果。"""

    SPEC = _SPEC

    def __init__(self, parent=None):
        #: 已就绪的缓存缩略图：真实图路径 → 缓存小图路径。缩略图条按这个
        #: 取图（``RembgPreviewWidget.refresh_page`` 刷单条）。
        self._cached_thumbs: dict[str, str] = {}
        super().__init__(parent)

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> RembgPreviewWidget:
        """左栏：原图 / 去底结果对比（复用共享控件）。"""
        self.viewer = RembgPreviewWidget()
        return self.viewer

    # ------------------------------------------------------------------ 源
    def _on_source_changed(self, source) -> None:
        """换源：左栏**立刻**显示这批源图，再走基类那套显隐/副标题。

        ⚠️ 此前本页不在换源时刷新左栏（只在 ``on_result`` 里塞），于是「拖进来、
        还没点执行」这段时间左栏是空的——得先跑一遍才知道有哪些图。

        ``set_images`` 的第二参是**去底色结果目录**，这里传 ``None``：条目照源图
        建好、显示原图，结果生成后 :meth:`on_result` 再传真目录。
        """
        self._cached_thumbs.clear()
        images = self.source_images() if source is not None else []
        self.viewer.set_images(images, None)
        self._warm_thumb_cache(images)
        super()._on_source_changed(source)

    def _warm_thumb_cache(self, images) -> None:
        """后台把这批图的缩略图渲进 singletask 缓存（命中即复用）。"""
        if not images:
            return
        from desktop.workers import ImageThumbCacheWorker, connect_queued

        images = [Path(p) for p in images]
        cache_dir = self._thumb_cache_dir()
        edge = self.THUMB_EDGE
        self.run_worker(
            lambda: ImageThumbCacheWorker(images, cache_dir, edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.thumbnail_ready,
                    lambda index, image, cached, items=list(images): (
                        self._on_thumb_cached(index, cached, items)
                    ),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_thumb_cached(self, index: int, cached: str, images: list[Path]) -> None:
        """一张缓存缩略图就绪：记下路径并**只刷相关条目**。

        ⚠️ 走 ``set_cached_thumbs``（单文件映射，内部只重画命中的条目）而不是
        重建整个缩略图条：重建会把已加载好的图标全丢掉重来。
        ⚠️ 每张都用当前 ``images`` 的同一张回查下标——宿主换源后 worker 可能
        还在跑，索引已经错位了。
        """
        if not cached or not (0 <= index < len(images)):
            return
        path_text = str(images[index])
        self._cached_thumbs[path_text] = cached
        self.viewer.set_cached_thumbs({path_text: cached})

    # ------------------------------------------------------------------ 副标题
    def source_summary(self, source) -> str:
        """在共用的 ``<源> → <输出>`` 之外，**补上图片张数**。"""
        images = self.source_images()
        count = len(images)
        tail = f"{count} 张图片" if count else "未找到图片"
        return f"{Path(source)}（{tail}） → {self.control.output()}"

    # ------------------------------------------------------------------ 编辑
    def edit_effect_note(self, path: Path) -> str:
        """编辑器改了图：**改的是源图还是去底色结果**，生效方式不一样。

        - 源图（左栏「原图」形态）→ 结果还是按旧图算的，重跑一次才用上；
        - 结果文件（「去底色结果」形态）→ 它自己就是这一步的产物，下游
          （PDF排版）读的就是它。
        """
        sources = {str(p) for p in self.source_images()}
        if str(path) in sources:
            return f"已更新源图「{path.name}」；重新执行去底色即用上这次修改。"
        return f"已更新去底色结果「{path.name}」；合成为 PDF 时用的就是这张图。"

    # ------------------------------------------------------------------ 结果
    def on_result(self, out_dir: Path, _result: dict) -> None:
        """成功：把「原图 → 结果」两组图塞进对比控件。"""
        sources = list(self.source_images())
        if not sources:
            self.toast("warning", "没有产出", "源里没有找到图片。")
            return
        # RembgPreviewWidget.set_images(原图列表, 结果目录, ...)：
        # 传输出目录让它按同名文件找去底结果并做成左右对比。
        self.viewer.set_images(sources, out_dir)
        self.toast("success", "处理完成", f"共处理 {len(sources)} 张图片。")


    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾查看器自己的后台线程（缩略图缓存 / 大图渲染）+ 执行线程。

        与 extract / detect / print 三页一致：查看器是独立于页面外壳的
        ``WorkerHost``，不给它收尾，退出时那些线程还在跑。
        """
        self.viewer.shutdown_workers()
        super().shutdown_workers()


__all__ = ["RembgModulePage"]
