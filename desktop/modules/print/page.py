# -*- coding: utf-8 -*-
"""独立模块「PDF排版」：与任务流程无关，选一批成品图直接合成 PDF。

**复用共用组件**：页头下方横跨整幅的**大输入区**（拖图片文件夹 / 拖一批图片 /
点选），右栏是 :class:`~desktop.steps.control.StepControl`（打印参数 + 输出目录 +
执行/中断），执行走 :class:`~desktop.steps.kernel.StepKernel` →
``functions.get_function("print")``——与任务流程第四步是同一条代码路径（连参数
面板都是同一个 ``PrintPanel``）。外设由 :class:`StepModulePage` 收口。

⚠️ **改参数即看单页效果**（用户 2026-11-21）：用户调纸张/边距/标题/页码
时，左栏**当前这张图**会立刻按新参数重排成"打印效果"（与任务流程第四步的
效果预览同一条合成链 ``PreviewWorker(print_spec=...)``），不必先点「生成PDF」。
合成只在内存里做，一个文件都不写。

⚠️ **与任务流程第四步的有意差别：页序。** 流程里页序 = 第四步列表里用户手动排的
那份清单（``functions/print`` 的 ``files`` 参数）。独立页面按用户 2026-10-02 的
选择**不提供手动排序**——页序就是文件名顺序
（``utils.sort_utils.natural_sort_key``，与 CLI 直跑 ``guji run print <目录>``
一致）。要调页序，先用「拼图」模块把版面排好再拖过来。

⚠️ **产物形态与别的模块不同**：``print`` 产出的是**一个 PDF 文件**，不是一目录
图片。所以 ``StepSpec.artifact_is_file=True``——执行内核**不会**把
``function.outpath`` 覆盖成输出目录（那样会拿目录当文件路径写），并且把**真正的
PDF 路径**回传给 ``on_result``；本页据此把左栏切到「产物 PDF 的页缩略图」。

⚠️ **左栏前后两个形态**（用户 2026-10-03：「所有独立任务左侧都是缩略图」）：

- **未生成**：左侧是**待打印图片**的缩略图（缓存在 ``singletask/print/``），
  选完源就能翻看要合进去的是哪几张；
- **生成后**：左侧换成**产物 PDF 的页缩略图**，看成品。

两种形态共用同一个 :class:`~desktop.components.viewers.ImageViewerWidget`——
它既能显示一批图片，也能把一本 PDF 的页当"图片"列出来（``set_pdf_source``）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

from desktop.components.viewers import ImageViewerWidget
from desktop.components.viewers.image_actions import ImageEditActionsMixin
from desktop.modules.base import StepModulePage
from desktop.modules.thumb_source import ThumbSourceMixin
from desktop.steps import spec_by_key

#: 本页的步骤元数据（标题/副标题/面板/过滤串/默认输出后缀的唯一来源）
_SPEC = spec_by_key("print")

#: 参数连发时的防抖窗口（拖一次"页边距"会发很多次 valueChanged）。
#: 与任务流程第四步的 250ms 同口径：再短会让每次拖动都排一遍版、把主线程拖住。
LIVE_DEBOUNCE_MS = 250


class PrintModulePage(StepModulePage, ThumbSourceMixin, ImageEditActionsMixin):
    """PDF排版模块页：拖入成品图（一批或一个文件夹）→ 调版面 → 合成 PDF。"""

    SPEC = _SPEC

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImageViewerWidget:
        """左栏：**缩略图条 + 大图**（复用共享控件）。

        初始是空的（还没选源），选中后是待打印图片的缩略图；生成完成后换成
        产物 PDF 的页缩略图。

        ⚠️ 大图挂一个**合成参数提供者**：大图显示的不是裸图，而是"按当前版面
        参数排进纸面的效果"（缩略图条不受影响，仍是原图小样）。
        """
        self.viewer = ImageViewerWidget(
            editable=False,
            empty_hint="选好成品图之后，这里会显示每一张",
        )
        self.viewer.set_preview_spec_provider(self._preview_spec)
        return self.viewer

    # ------------------------------------------------------------------ 控制
    def _build_control(self):
        """共用步骤控件 + 把「参数变化 → 重排当前页」接上。

        ⚠️ 面板是惰性/共用的 ``PrintPanel``，它的 ``params_changed`` 只在
        **影响排版**的控件变化时发（标题文字、边距、纸张…）。别挂 ``param_edited``：
        那个连"输出目录里选的文件名"之类也会发，会把预览刷得没必要地勤。
        """
        card = super()._build_control()
        panel = self.control.panel
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._refresh_effect)
        if panel is not None:
            panel.params_changed.connect(self._live_timer.start)
        return card

    # -------------------------------------------------------------- 实时效果
    def _preview_spec(self, path_text: str, index: int, total: int) -> dict | None:
        """当前页的「打印效果」参数（交给 ``PreviewWorker(print_spec=...)``）。

        返回 ``None`` 表示不合成（面板还没建好、参数填了一半、或当前不是图片
        清单形态）。合成几何全部由 ``utils.page_layout`` 决定——与最终 PDF 是
        同一份规则，所以这里的预览就是"生成出来会是什么样"。

        ⚠️ ``nodes``（标题切换节点）必须在这里按**列表位置**解析好：worker 拿不到
        条目清单，交给 ``plan_print_page`` 内部兜底的话节点永远匹配不上（任务流程
        2026-09-29 踩过同一个坑）。
        """
        control = getattr(self, "control", None)
        panel = getattr(control, "panel", None)
        if panel is None:
            return None
        try:
            args = panel.get_args()
        except Exception:  # noqa: BLE001 - 参数填了一半：这一帧先显示原图
            return None
        try:
            from utils.page_layout import resolve_title_nodes

            nodes = resolve_title_nodes(
                [str(i + 1) for i in range(max(0, int(total)))],
                args.get("title_switch_nodes") or [],
            )
        except Exception:  # noqa: BLE001 - 节点填坏了不该阻断预览
            nodes = []
        return {
            "args": args,
            "index": index,
            "total": total,
            "name": Path(path_text).stem,
            "nodes": nodes,
            "note": f"打印效果预览 · 第 {index + 1}/{total} 页"
                    "（按当前版面参数合成，不会生成 PDF）",
        }

    def _refresh_effect(self) -> None:
        """防抖到期：按最新参数重排当前页（不落盘、不动清单）。"""
        self.viewer.refresh_current()

    # ------------------------------------------------------------------ 源
    def _on_source_changed(self, source) -> None:
        """换源：左栏立刻显示这批待打印图，再走基类那套显隐/副标题。

        ⚠️ 此前本页不在换源时刷左栏（只在 ``on_result`` 里塞 PDF），于是「选完
        源、还没点生成」这段时间左栏是空的。
        """
        self.show_source(source, paths=self.source_images() if source else None)
        super()._on_source_changed(source)

    # ------------------------------------------------------------------ 副标题
    def source_summary(self, source) -> str:
        """在共用的 ``<源> → <输出>`` 之外，**补上待合成张数**。"""
        images = self.source_images()
        tail = f"{len(images)} 张图片" if images else "未找到图片"
        return f"{Path(source)}（{tail}） → {self.control.output()}"

    def edit_effect_note(self, path: Path) -> str:
        """编辑器改了待打印图：那张图就是最终进 PDF 的那张。

        ⚠️ 生成完成之后左栏切成了**产物 PDF 的页缩略图**——矢量页没有可回写
        的图片文件，右键不提供「编辑图片」，所以能走到这里的都是待打印图。
        """
        return f"已更新待打印图「{path.name}」；重新点「生成 PDF」即用上这次修改。"

    # ------------------------------------------------------------------ 结果
    def on_result(self, pdf: Path, _result: dict) -> None:
        """成功：``pdf`` 是**PDF 文件路径**（见 ``StepSpec.artifact_is_file``）。

        左栏从「待打印图片」切到「产物 PDF 的页缩略图」——页缩略图缓存在
        ``singletask/print/thumbnails/<产物>/``，所以第二次看同一个成品
        是秒开。
        """
        if not pdf.is_file():
            self.toast("warning", "没有找到 PDF", f"输出位置没有 PDF 文件：{pdf}")
            return
        self.show_pdf(pdf)
        size_kb = max(1, pdf.stat().st_size // 1024)
        self.header.set_subtitle(f"{pdf}（{size_kb} KB）")
        self.toast("success", "已生成 PDF", pdf.name)

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """收尾左栏自己的后台线程（缩略图缓存 / 大图渲染）+ 共用控件的执行线程。"""
        timer = getattr(self, "_live_timer", None)
        if timer is not None:
            timer.stop()
        self.viewer.shutdown_workers()
        super().shutdown_workers()


__all__ = ["PrintModulePage"]
