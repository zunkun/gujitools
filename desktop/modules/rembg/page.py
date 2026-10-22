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

⚠️ 2026-10-22 起，**任务流程里的去底色也是整图去底色了**（area/border 已从
这一步移除，按框裁图归「检测文本框」的提交）。所以本独立页与任务流程第三步
现在是**同一件事**：拖图 → 调去底参数 → 出整图去底结果，没有任何裁剪分支。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QTimer

from core.reporter import EVENT_PAGE_DONE
from desktop.components.viewers import RembgPreviewWidget
from desktop.modules.base import StepModulePage
from desktop.modules.thumb_source import ThumbSourceMixin
from desktop.steps import spec_by_key
from desktop.ui.widgets import Card

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("rembg")

#: 换源时**预热**缩略图缓存的上限（张）。用户 2026-10-21：所有步骤的缩略图
#: 不必全部一次加载——只把首屏几屏渲进 singletask 缓存，更靠后的页等用户滚到
#: 可见窗口时由查看器现解码（``ThumbsMixin`` 按可见窗口懒加载）。
_WARM_THUMB_LIMIT = 60


class RembgModulePage(StepModulePage, ThumbSourceMixin):
    """去底色模块页：拖入图片（单张或文件夹）→ 调参数 → 批量去底 → 对比看结果。"""

    SPEC = _SPEC

    #: 「某几页结果刚落盘」的界面刷新窗口（ms）。与任务流程同一个口径：
    #: 逐页完成事件攒 400ms、每次只刷看得见的行（见 ``refresh_running_results``）。
    _REMBG_UI_MS = 400

    if TYPE_CHECKING:
        # ⚠️ 本页左栏是「原图 / 去底结果对比」控件 ``RembgPreviewWidget``，它
        # **不是** ``ImageViewerWidget``（两类控件各实现自己的接口，没有继承
        # 关系）。这里按**实际控件类型**重新声明 ``viewer``，覆盖
        # ``ThumbSourceMixin`` 里那条通用声明；因两者无继承关系，pyright 会报
        # 「override 不兼容」——按实际类型覆盖是这里唯一正确的写法。
        viewer: RembgPreviewWidget  # type: ignore[reportIncompatibleVariableOverride]

    def __init__(self, parent=None):
        #: 当前缓存 pass 的映射（真实图路径 → 缓存小图路径）。换源即换新
        #: 对象＝代际：旧 worker 的迟到信号按**对象身份**丢弃。缓存 pass
        #: 结束时它被整体交给查看器（``RembgPreviewWidget.set_cached_thumbs``
        #: 的整体替换语义）。
        self._thumb_cache_batch: dict[str, str] = {}
        #: 本轮执行里**结果刚落盘**的源路径（见 :meth:`_on_step_event`）
        self._rembg_dirty: set[str] = set()
        super().__init__(parent)
        #: 阶段反馈的攒批定时器（见 ``_REMBG_UI_MS``）
        self._rembg_ui_timer = QTimer(self)
        self._rembg_ui_timer.setSingleShot(True)
        self._rembg_ui_timer.setInterval(self._REMBG_UI_MS)
        self._rembg_ui_timer.timeout.connect(self._flush_rembg_feedback)

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> RembgPreviewWidget:
        """左栏：原图 / 去底结果对比（复用共享控件）。

        ⚠️ ``image_editable=False``（2026-10-09 用户）：去底色阶段**只许
        预览、不许编辑**——右键不给「编辑图片」、弹窗不给「编辑」按钮。
        """
        self.viewer = RembgPreviewWidget(image_editable=False)
        return self.viewer

    # ------------------------------------------------------------------ 源
    def _build_control(self) -> Card:
        """共用步骤控件 + 接「单页完成」事件（阶段反馈的来源）。

        ⚠️ ``StepKernel`` 把非 progress/log 事件原样透传上来（见
        ``desktop.steps.kernel``），去底色的每页产物一落盘就有
        ``page_done``——本页据此边跑边刷新（与「检测文本框」页同一个通道）。
        """
        card = super()._build_control()
        self.control.event.connect(  # type: ignore[reportAttributeAccessIssue]  # ``event`` 与 QObject.event 同名，运行时是 Signal
            self._on_step_event
        )
        return card

    def _on_step_event(self, name: str, payload) -> None:
        """一条步骤私有事件：只关心 ``page_done``（其它步骤事件本页用不上）。"""
        if name != EVENT_PAGE_DONE or not isinstance(payload, dict):
            return
        source = str(payload.get("source") or "")
        if not source:
            return
        self._rembg_dirty.add(source)
        if not self._rembg_ui_timer.isActive():
            self._rembg_ui_timer.start()

    def _flush_rembg_feedback(self) -> None:
        """攒批到期：把刚落盘的几页刷到左栏（只刷**看得见**的行 + 当前大图）。

        结果目录取 ``control.output()``——独立页的执行内核把 ``dest``
        **精确**当作产物目录（见 ``CommandJob.__call__``），与收尾时
        ``on_result`` 拿到的是同一个。
        """
        changed = self._rembg_dirty
        self._rembg_dirty = set()
        if not changed:
            return
        viewer = self.viewer
        if viewer.result_dir is None:
            dest = self.control.output()
            if dest is None:
                return
            viewer.set_result_dir(dest)
        viewer.refresh_running_results(changed)

    def _on_source_changed(self, source) -> None:
        """换源：左栏**立刻**显示这批源图，再走基类那套显隐/副标题。

        ⚠️ 此前本页不在换源时刷新左栏（只在 ``on_result`` 里塞），于是「拖进来、
        还没点执行」这段时间左栏是空的——得先跑一遍才知道有哪些图。

        ``set_images`` 的第二参是**去底色结果目录**，这里传 ``None``：条目照源图
        建好、显示原图，结果生成后 :meth:`on_result` 再传真目录。
        """
        self._thumb_cache_batch = {}
        # 换源：上一轮攒着的 page_done 属于旧清单，别刷到新条目上
        self._rembg_dirty.clear()
        self._rembg_ui_timer.stop()
        images = self.source_images() if source is not None else []
        # list 不变型：清单是 list[Path]，控件收 list[Path | str]
        self.viewer.set_images(cast("list[Path | str]", images), None)
        self._warm_thumb_cache(images)
        super()._on_source_changed(source)

    def _warm_thumb_cache(self, images) -> None:
        """后台把这批图的缩略图渲进 singletask 缓存（命中即复用）。

        ⚠️ **只记映射、不逐张刷**（2026-10-11 用户报「左栏缩略图不显示」）：
        此前每张就绪都调 ``viewer.set_cached_thumbs({单条})``，而那个调用
        内部走 ``_load_thumbs_chunked``＝「重新装载」——代际令牌 +1、批次
        光标重置。结果是初始批次的在飞回调全被作废、单张刷新又被下一张的
        代际作废，左栏缩略图几乎一张都落不了地。缓存小图与初始批次解码
        原图得到的是**同一内容**，等缓存 pass 结束整体替换一次即可。
        """
        if not images:
            return
        from desktop.workers import ImageThumbCacheWorker, connect_queued

        # 只预热首屏那几屏（见 _WARM_THUMB_LIMIT）
        images = [Path(p) for p in images][:_WARM_THUMB_LIMIT]
        mapping: dict[str, str] = {}
        self._thumb_cache_batch = mapping
        cache_dir = self._thumb_cache_dir()
        edge = self.THUMB_EDGE
        self.run_worker(
            lambda: ImageThumbCacheWorker(
                # list 不变型：清单是 list[Path]，worker 收 list[Path | str]
                cast("list[Path | str]", images), cache_dir, edge=edge,
            ),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.thumbnail_ready,
                    lambda index, image, cached, items=list(images), m=mapping: (
                        self._on_thumb_cached(index, cached, items, m)
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    worker.completed,
                    lambda m=mapping: self._apply_cached_thumbs(m),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_thumb_cached(
        self, index: int, cached: str, images: list[Path],
        mapping: dict[str, str],
    ) -> None:
        """一张缓存缩略图就绪：记进**本批**映射，不碰缩略图条。

        ⚠️ 下标回查用 ``_warm_thumb_cache`` 捕获的那份 ``images``——宿主换源
        后 worker 可能还在跑，索引已经错位；换过源的话 ``mapping`` 也不是
        当前的批（对象身份不等），整条丢弃（完成回调里的整体替换同样有
        这道身份闸）。
        """
        if not cached or not (0 <= index < len(images)):
            return
        mapping[str(images[index])] = cached

    def _apply_cached_thumbs(self, mapping: dict[str, str]) -> None:
        """缓存 pass 结束：把攒好的映射**整体**交给查看器（整体替换语义）。

        此刻初始批次的原图解码若还在跑，会被这次重装载的代际作废，后续
        批次改用已缩好的缓存图——正好省掉整张原图解码。
        """
        if mapping and mapping is self._thumb_cache_batch:
            self.viewer.set_cached_thumbs(dict(mapping))

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
        # ⚠️ **留标记**（2026-10-13 用户）：singletask 导出目录写一个
        #    ``guji_singletask_rembg.json``——独立拼图页选源时据此识别"这是
        #    去底色导出目录"，把里面的白底图转成透明底**副本**再拼版（原图
        #    不动）。只标记目录、不改任何图片；失败不影响本次结果。
        from desktop.services import rembg_export

        try:
            rembg_export.write_marker(out_dir)
        except Exception as exc:  # noqa: BLE001 - 标记是旁路，别拖垮结果呈现
            self.log(f"导出目录标记写入失败（不影响本次结果）：{exc}")
        # RembgPreviewWidget.set_images(原图列表, 结果目录, ...)：
        # 传输出目录让它按同名文件找去底结果并做成左右对比。
        # list 不变型：清单是 list[Path]，控件收 list[Path | str]
        self.viewer.set_images(cast("list[Path | str]", sources), out_dir)
        self.toast("success", "处理完成", f"共处理 {len(sources)} 张图片。")


    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾查看器自己的后台线程（缩略图缓存 / 大图渲染）+ 执行线程。

        与 extract / detect / print 三页一致：查看器是独立于页面外壳的
        ``WorkerHost``，不给它收尾，退出时那些线程还在跑。
        """
        self._rembg_ui_timer.stop()
        self._rembg_dirty.clear()
        self.viewer.shutdown_workers()
        super().shutdown_workers()


__all__ = ["RembgModulePage"]
