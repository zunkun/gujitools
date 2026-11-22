# -*- coding: utf-8 -*-
"""独立拼图页的输入区与选源链路（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

from desktop.services.imposition import normalize_doc
from desktop.steps import SourceZone

from .constants import _SPEC


class SourcesMixin:
    """大输入区、选源、去底色导出目录衔接与清空输入。"""

    # ------------------------------------------------------------------ 输入
    def _build_input(self) -> SourceZone:
        """页头下方的**大输入区**：拖一批图片 / 拖一个图片文件夹 / 点选。

        ⚠️ 拼图的"源"是**一批**图片（不是单个源），所以这里不关心
        :meth:`StepSpec.resolve_source` 的单源归一化，而是把拖进来的东西
        **展开成图片清单**（文件夹取顶层图片），见 :meth:`_on_paths_chosen`。
        """
        self.zone = SourceZone(_SPEC)
        self.zone.paths_chosen.connect(self._on_paths_chosen)
        self.zone.cleared.connect(self._on_clear_sources)
        self.zone.rejected.connect(
            lambda message: self.toast("warning", "没能完成这次选择", message)
        )
        return self.zone

    # ------------------------------------------------------------------ 选图
    def _on_paths_chosen(self, paths: list) -> None:
        """大输入区给了路径：展开成**图片清单**（文件夹取图片，含唯一子目录下钻）。

        与"图片提取 / 去底色"的差别在这里：那两步最终只要**一个**源（文件或
        目录），拼图要的是**一批**图片，所以走 :meth:`StepSpec.collect_files`
        （摊平成清单、去重、按名字排序），而不是 :meth:`StepSpec.resolve_source`。
        """
        images = _SPEC.collect_files(paths)
        if not images:
            self.toast(
                "warning", "没有可用的图片",
                "请拖入图片文件，或拖一个放着图片的文件夹。",
            )
            return
        self._prepare_sources(images)

    # -------------------------------------------------- 去底色导出目录衔接
    #
    # 用户 2026-10-13：独立去底色页的导出目录带 ``guji_singletask_rembg``
    # 标记（``services.rembg_export.write_marker``）。拼图页用到**带标记目录**
    # 里的白底图时，先在 singletask 缓存区生成**透明底副本**（原图绝不动）
    # 再拼版——白底图互相遮挡、没法自由挪动；没有标记的目录/散图原样直用，
    # 不复制、不转换。

    def _prepare_sources(self, images: list[Path]) -> None:
        """选源前置：带标记目录里的图转透明副本（后台），完成后才正式定源。

        ⚠️ **代际闸**：预备期间用户又拖了新源/清空了输入 ⇒ ``batch`` 身份
        不等，迟到的完成回调整批丢弃（与缩略图缓存 pass 同一套思路）。
        ⚠️ 转换（几百张图逐张解码+重编码）**比较耗时**（用户 2026-10-13）：
        右栏进度条 + toast + 页头状态行三处都提示，让用户知道在等什么；
        「自动拼版」「导出成品」在预备完成前禁用——旧清单还挂在页面上，
        不禁用的话新旧两批图会混进一份成品。
        """
        from desktop.services import rembg_export

        _plain, marked = rembg_export.split_marked(images)
        if not marked:
            self._set_sources(images)
            return
        batch: object = object()
        self._rembg_prep_batch = batch
        self.auto_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress_row.start(
            f"正在准备透明副本…（去底色导出目录，共 {len(marked)} 张）"
        )
        self.status(
            f"检测到去底色导出目录（{len(marked)} 张），正在准备透明副本…", "info"
        )
        self.toast(
            "info", "检测到去底色导出目录",
            f"正在把 {len(marked)} 张白底图转成透明底副本（原图不动），"
            "完成后自动开始拼版，请稍候…",
        )
        self.log(
            f"命中去底色导出目录标记：{len(marked)} 张图将生成透明底副本用于拼版"
            "（原图不动，副本在 singletask 缓存区）。"
        )
        from desktop.workers import RembgTransparentWorker, connect_queued

        self.run_worker(
            lambda: RembgTransparentWorker([str(p) for p in marked]),
            lambda worker, thread: (
                connect_queued(
                    self, worker.progress, self._on_prep_progress, thread,
                ),
                connect_queued(
                    self, worker.finished,
                    lambda mapping, errors, b=batch, imgs=list(images):
                        self._on_prep_finished(mapping, errors, b, imgs),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda message, b=batch, imgs=list(images):
                        self._on_prep_failed(message, b, imgs),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_prep_progress(self, done: int, total: int) -> None:
        """副本转换进度：右栏进度条（定量）+ 页头状态行双处可见。"""
        self.progress_row.update(done, total)
        self.status(f"正在准备透明副本 {done}/{total}…", "info")

    def _on_prep_finished(
        self, mapping: dict, errors: list, batch: object, images: list[Path]
    ) -> None:
        """副本就绪：命中映射的换成副本路径，失败的回落原图，正式定源。"""
        if batch is not self._rembg_prep_batch:
            return  # 预备期间换过源/清空了输入：整批作废
        if not mapping:
            self.progress_row.fail("透明副本生成失败")
        elif errors:
            self.progress_row.succeed(
                f"副本就绪 {len(mapping)} 张（{len(errors)} 张失败用原图）"
            )
        else:
            self.progress_row.succeed(f"透明副本就绪 {len(mapping)} 张")
        if errors:
            self.log(
                "部分透明副本生成失败（这些图按原图拼版）："
                + "；".join(errors)
            )
        # ⚠️ 顺序**沿用 collect_files 的清单序**（映射按源路径回填）——自动
        #    拼版按清单顺序配对，副本文件名带指纹后缀，绝不能按名字重排。
        sources = [Path(mapping.get(str(p), p)) for p in images]
        self._set_sources(sources, output_hint=images[0])

    def _on_prep_failed(self, message: str, batch: object, images: list[Path]) -> None:
        """转换线程整体失败：全部回落原图定源（拼版仍可用，只是白底）。"""
        if batch is not self._rembg_prep_batch:
            return
        self.progress_row.fail("副本准备失败，按原图拼版")
        self.log(f"透明副本准备失败，按原图拼版：{message}")
        self._set_sources(images)

    def _set_sources(
        self, images: list[Path], output_hint: Path | None = None
    ) -> None:
        """把图片清单定为本页的源：复位文档与输出目录，并刷新视图。

        文档一律重置——换了源清单还留着上一批图的拼版页，导出时会去合并不存在
        的文件（或者更糟：把两批图混在一份成品里）。

        ``output_hint``：**输出目录与页头展示**的锚点（默认取第一张源图）。
        ⚠️ 源清单是去底色导出的**透明底副本**时（见 :meth:`_prepare_sources`），
        必须传**原图**当锚点——否则输出目录会落到 singletask 缓存区里、页头
        显示缓存路径，用户完全找不到自己的成品。
        """
        self._sources = [str(p) for p in images]
        self._doc = normalize_doc({})
        self.close_zoom_dialog()  # 弹窗里那几页是上一批图的快照
        # 源定了 ⇒ 副本预备期结束（预备期里禁掉的是它），恢复可用
        self.auto_button.setEnabled(True)
        first = Path(output_hint) if output_hint is not None else Path(self._sources[0])
        self._out_dir = _SPEC.default_output(first)
        # 选到图了 → 显出拼版视图与控制面板（初始只有输入框，见
        # ModulePage 类 docstring）
        self.sync_workspace_visible(first)
        if len(self._sources) == 1:
            self.zone.set_source(first, f"1 张图片 · {first.parent}")
            summary = f"已选 1 张图片 → {self._out_dir}"
        else:
            common = first.parent
            self.zone.set_source(
                common, f"共 {len(self._sources)} 张图片 · {common}"
            )
            summary = f"已选 {len(self._sources)} 张图片 → {self._out_dir}"
        self.header.set_subtitle(summary)
        self.status("已选好图片，点「自动拼版」或左侧「＋ 选择拼版」", "info")
        self._refresh_view()
        self.log(f"已选择 {len(self._sources)} 张图片")

    def _on_clear_sources(self) -> None:
        """清空输入：源清单、拼版文档、输出目录一起复位。

        操作界面也一起收回去——源没了就没有可拼的图，只留输入框（用户
        2026-10-03：初始/清空后页面上只有输入框）。
        """
        self._sources = []
        self._doc = normalize_doc({})
        self._out_dir = None
        self._rembg_prep_batch = None  # 在飞的副本转换回调整批作废
        self._last_output = None
        self.view_output_button.setVisible(False)
        self._page_thumbs = []
        self._page_thumb_manager().reset()
        self._thumb_timer.stop()
        self._rotate_commit_timer.stop()
        self._thumb_dirty_pages.clear()
        self.close_zoom_dialog()
        self.sync_workspace_visible(None)
        self.header.set_subtitle("")
        self.status("已清空输入", "info")
        self._refresh_view()
