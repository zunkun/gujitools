# -*- coding: utf-8 -*-
"""「拼图」独立模块页（= 图片拼版）。

**复用共用组件**：

- 输入：:class:`~desktop.steps.source_zone.SourceZone`——页头下方横跨整幅的
  **大输入区**（拖一批图片、拖一个图片文件夹、或点选），与"图片提取 / 去底色"
  是同一块控件；
- 执行：:class:`~desktop.steps.kernel.StepKernel` + ``CallableJob``——
  拼版不是 CLI 命令，所以走"纯函数 job"这条路（内核同样只认"输出目录"）；
- 界面：``ImpositionViewWidget``（左页清单 + 右拖拽画布）、
  ``ImpositionPanel``（右侧控制面板）、``ImpositionPickerDialog``（选图弹窗）；
- 规则：``desktop.services.imposition`` 是**纯函数模块**（无 Qt），版面默认
  摆放、自动拼版、合成紧裁全部直接用；
- 元数据：``desktop/steps/spec.py`` 的 imposition 条目（标题/副标题/过滤串/
  后缀/输出名）。

**独立**：不依赖任务目录、不依赖 ``TaskDetailPage`` 的拼版控制器。用户选了
一批图片作为「源清单」，模块自己维护一份 ``doc``（内存 + 可导出），
点「导出成品」把每页合成为**白底** PNG（2026-10-13 用户：singletask 导出的
就是交付物，不要透明底；任务流程的 ``stages/imposition`` 仍默认透明底）。

**与去底色独立页的衔接**（2026-10-13 用户）：源图来自带
``guji_singletask_rembg`` 标记的导出目录时（``services.rembg_export``），
先把白底图转成**透明底副本**（singletask 缓存区，原图不动）再拼版；
没有标记的目录/散图原样直用。

⚠️ 与任务流程的差别（有意为之）：任务流程里拼版的产物供第四步 PDF排版使用，
且「启用开关」决定取图来源；单文件模式下没有下游，所以这里把面板里的
「启用开关」隐掉，只留版面操作与导出。

**面板能力与任务流程对齐**（2026-10-13 用户）：单图页「新增图片」
（append 弹窗挑 1 张并进当前页，``append_item_to_page`` 摆放）、
「删除选中图片」（选中才出现；本页最后一张删除前先确认）、整体旋转/
选中图旋转（停手 250ms 统一提交）——语义逐条与任务流程的拼版步骤一致。
"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import FluentIcon as FIF, PrimaryPushButton, PushButton

from desktop.components.imposition import (
    ImpositionPanel,
    ImpositionPickerDialog,
    ImpositionViewWidget,
)
from desktop.components.progress_row import ProgressRow
from desktop.modules.base import ModulePage
from desktop.services.imposition import (
    FILE_FMT,
    WHITE_BACKGROUND,
    append_item_to_page,
    auto_impose_pages,
    cn_page_label,
    compose_doc,
    excluded_files,
    flatten_onto_background,
    make_page,
    make_single_page,
    normalize_doc,
    normalize_page,
    page_has_file,
    page_source_stems,
    refresh_rects_for_edited_source,
    removed_source_files,
    same_path,
    used_source_files,
)
from desktop.steps import (
    SourceZone,
    StepKernel,
    StepRequest,
    StepSpec,
    callable_job,
    spec_by_key,
)
from desktop.ui.widgets import Card
from desktop.utils.files import THUMBNAIL_EDGE as THUMB_EDGE

#: 本页的步骤元数据（标题/副标题/过滤串的唯一来源）。⚠️ spec_by_key 的声明
#: 返回 StepSpec | None，但 spec 表里 imposition 是**写死存在**的一条（删掉它
#: 整条模块就没了），这里显式断言一次：与其在每个用到 _SPEC 的地方写一堆判空，
#: 不如在源头把「这条 spec 必须存在」这条不变量钉住（缺了就立刻炸，位置也清楚）。
_SPEC_OR_NONE = spec_by_key("imposition")
assert _SPEC_OR_NONE is not None, "spec 表里缺少 imposition 这一步"
#: 断言后的**非空别名**：模块级变量在函数体里不会被类型检查器保持收窄，故这里
#: 显式再声明一次类型（运行时就是上面那个对象，零开销）。
_SPEC: StepSpec = _SPEC_OR_NONE

#: 手工修饰过的整页组合落在 ``singletask/<子任务>/`` 下的哪个子目录。
EDITED_DIRNAME = "edited"

#: 版面改动 → 左列**单页缩略图**重合成的防抖（用户 2026-10-09：拖动松手/
#: 面板调整/编辑回写之后几秒内，缩略图要跟上页面效果）。拖动中签名每帧
#: 都在变，等真的停手了再合成一次就够。
THUMB_REFRESH_DEBOUNCE_MS = 2000

#: 旋转组件（整体/选中图）停手后统一提交的防抖（与任务流程
#: ``imposition_layout.EDIT_COMMIT_DEBOUNCE_MS`` 同一档）：滑块连续吐增量
#: 期间只转画布不落盘，停手 250ms 后一次性 flush + 重适配 + 回填面板。
EDIT_COMMIT_DEBOUNCE_MS = 250


def edited_page_dir() -> Path:
    """手工修饰过的整页组合的存放目录（**缓存**，不是产物）。

    「编辑整页组合」在独立拼图页里没有现成的落点：成品是点「导出成品」那一刻
    才写进用户选的目录的。所以手改的那张先存在 singletask 下（用户 2026-10-03
    定的独立任务缓存区），导出时再盖到对应成品上——输出目录归用户，程序只往
    里写最终成品。

    ⚠️ 目录名走 ``spec.disk_key()``（= ``imposition``）而不是标题：这里存着
    用户手改过的版面图，标题一改就再也读不到（"明明改过版面，重新打开又变回
    原样"）。见 :meth:`desktop.steps.spec.StepSpec.disk_key`。
    """
    from desktop.utils.files import singletask_dir

    return singletask_dir(_SPEC.disk_key()) / EDITED_DIRNAME


def _page_overrides(doc: dict) -> list[Path | None]:
    """按 ``compose_doc`` 的页序取出每页的手改图；没手改过的页是 ``None``。

    ⚠️ 过滤口径必须与 ``compose_doc`` **完全一致**（同样走 ``normalize_page``）：
    那边会静默丢掉不可修复的页，这里若按原列表下标取，一页坏数据就会让后面
    所有页的手改**错位到别人身上**。
    """
    overrides: list[Path | None] = []
    for raw in (doc or {}).get("pages") or []:
        if normalize_page(raw) is None:
            continue
        edited = raw.get("edited_file") if isinstance(raw, dict) else None
        overrides.append(Path(str(edited)) if edited else None)
    return overrides


class ImpositionModulePage(ModulePage):
    """拼图模块页：选图 → 自动/手动拼版 → 调整版面 → 导出成品。"""

    TITLE = _SPEC.title
    SUBTITLE = _SPEC.subtitle

    #: 拼版视图 + 控制面板需要更宽的控制列（沿用详情页拼版档位）
    CONTROL_MIN_WIDTH = 340
    CONTROL_MAX_WIDTH = 460

    def __init__(self, parent=None):
        """先建骨架，再补「选图 / 自动拼版 / 导出」这条操作链。"""
        self._sources: list[str] = []
        self._doc: dict = normalize_doc({})
        self._out_dir: Path | None = None
        #: 去底色导出目录衔接的**代际闸**（见 _prepare_sources）：换源/清空
        #: 即换新对象，迟到的副本转换回调整批丢弃。
        self._rembg_prep_batch: object | None = None
        #: 最近一次导出的页数（job 在 worker 线程里写、主线程读，只搬一个整数）
        self._export_result: dict = {}
        #: 左列每页的缩略图（QPixmap 列表，页序；未就绪处是 None）
        self._page_thumbs: list = []
        #: 预览弹窗（懒建，与任务流程的拼版步骤同一个控件）
        self._zoom_dialog = None
        super().__init__(parent)
        # 版面改动 → 防抖后单页重合成左列缩略图（见 _on_items_changed）
        self._thumb_dirty_pages: set[int] = set()
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(THUMB_REFRESH_DEBOUNCE_MS)
        self._thumb_timer.timeout.connect(self._refresh_dirty_page_thumbs)
        # 旋转组件（整体/选中图）停手提交的防抖（见 EDIT_COMMIT_DEBOUNCE_MS）
        self._rotate_commit_timer = QTimer(self)
        self._rotate_commit_timer.setSingleShot(True)
        self._rotate_commit_timer.setInterval(EDIT_COMMIT_DEBOUNCE_MS)
        self._rotate_commit_timer.timeout.connect(self._commit_rotation_edit)
        self.status("尚未选择图片")

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

    # ------------------------------------------------------------------ 预览
    def _build_preview(self) -> ImpositionViewWidget:
        """左栏：拼版页清单 + 操作画布（复用现成装配控件）。"""
        self.view = ImpositionViewWidget()
        self.view.add_requested.connect(self._on_add_pages)
        self.view.page_remove_requested.connect(self._on_release_page)
        self.view.page_selected.connect(lambda _i: self._refresh_panel())
        self.view.slot_selected.connect(lambda _slot: self._refresh_panel())
        self.view.items_changed.connect(self._on_items_changed)
        self.view.page_reorder_requested.connect(self._on_reorder)
        self.view.pages_batch_delete_requested.connect(self._on_batch_delete)
        # 双击 / 右键：预览（单张原图 · 整页左右组合）与「编辑单图 / 编辑整图」直达编辑器。
        # 与任务流程的拼版步骤**同一组信号、同一套语义**——此前这四条没接线，
        # 画布右键菜单弹得出来、双击也有反应信号，但**点了什么都不会发生**
        # （用户 2026-10-03：「独立步骤，图片也可以编辑生效」）。
        self.view.item_preview_requested.connect(self._open_item_preview)
        self.view.spread_preview_requested.connect(self._open_spread_preview)
        self.view.item_edit_requested.connect(self._open_item_edit)
        self.view.spread_edit_requested.connect(self._open_spread_edit)
        return self.view

    # ------------------------------------------------------------------ 控制
    def _build_control(self) -> Card:
        """右栏：自动拼版/导出按钮 + 复用 ``ImpositionPanel``（选图在页头输入区）。"""
        card = Card()

        # 导出走共用执行内核：拼版是纯函数，所以用 CallableJob
        self.kernel = StepKernel(callable_job(self._compose_job), self)
        self.kernel.log.connect(self.log)
        self.kernel.progress.connect(self._on_progress)
        self.kernel.finished.connect(self._on_exported)
        self.kernel.failed.connect(self._on_export_failed)

        # 执行进度：与四个步骤页**同一个**组件（``StepControl`` 内部那条也是
        # 它），所以拼图页的进度条长得跟别处一模一样。
        # ⚠️ 本页**不继承** ``StepModulePage``（源是一批图、执行是纯函数导出），
        # 所以这条得自己摆、自己接——别以为基类会捎带带上。
        self.progress_row = ProgressRow(noun=_SPEC.progress_unit())
        card.box.addWidget(self.progress_row)

        self.auto_button = PushButton(FIF.MOVE, "自动拼版")
        self.auto_button.setFixedHeight(34)
        self.auto_button.setToolTip(
            "按文件名规则自动配对：前一页左半幅 + 当前页右半幅拼成对页"
        )
        self.auto_button.clicked.connect(self._auto_impose)
        card.box.addWidget(self.auto_button)

        # enable_switch=False：单文件模式没有「第四步取图来源」概念，
        # 构造时声明收掉启用开关（任务流程专属概念不进独立页）。
        # 其余信号与任务流程的拼版步骤**逐条对齐**（2026-10-13 用户：独立
        # 拼图页跟任务流程保持一致）：整版旋转、单图页「新增图片」、
        # 「删除选中图片」、复位、清空。
        self.panel = ImpositionPanel(enable_switch=False)
        self.panel.reset_requested.connect(self._on_reset_layout)
        self.panel.whole_rotate_delta.connect(self._on_whole_rotate)
        self.panel.item_rotation_edited.connect(self._on_item_rotate)
        self.panel.add_image_requested.connect(self._on_add_image)
        self.panel.item_delete_requested.connect(self._on_delete_item)
        self.panel.clear_requested.connect(self._on_clear)
        card.box.addWidget(self.panel)

        self.export_button = PrimaryPushButton(FIF.SAVE, "导出成品")
        self.export_button.setFixedHeight(36)
        self.export_button.clicked.connect(self._export)
        card.box.addWidget(self.export_button)

        # ---- 查看处理文件（2026-10-11 用户：执行成功后右侧下边的入口）----
        # 导出成功才出现，指向最近一次导出的目录；再次导出/清空输入即收起。
        self._last_output: Path | None = None
        self.view_output_button = PushButton(FIF.FOLDER, "查看处理文件")
        self.view_output_button.setFixedHeight(34)
        self.view_output_button.setToolTip("在资源管理器中打开本次导出结果")
        self.view_output_button.setVisible(False)
        self.view_output_button.clicked.connect(self._open_last_output)
        card.box.addWidget(self.view_output_button)
        return card

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

    def _on_add_pages(self) -> None:
        """左侧虚线「＋ 选择拼版」：弹选图窗，勾选的图按规则成页。

        复用 ``ImpositionPickerDialog``（自带缩略图网格、删除/恢复、自动拼版
        起点选择），宿主只负责把勾选结果变成页。
        """
        if not self._sources:
            self.toast("warning", "还没有图片", "请先把图片拖到上面的输入框。")
            return
        candidates = self._sources + list(removed_source_files(self._doc))
        dialog = ImpositionPickerDialog(
            candidates,
            parent=self,
            removed_files=list(removed_source_files(self._doc)),
        )
        if not dialog.exec():
            # 取消也要落软删除黑名单（用户在弹窗里删过图）
            self._apply_picker_removed(dialog)
            self._refresh_view()
            return
        picked = [str(p) for p in dialog.checked_files()]
        self._apply_picker_removed(dialog)
        auto_start = dialog.auto_mode_file()
        if auto_start is not None:
            pages = auto_impose_pages(
                [str(p) for p in dialog.auto_sequence()]
            )
            self._doc["pages"] = list(self._doc.get("pages") or []) + pages
        else:
            self._append_pages_from(picked)
        self._refresh_view()
        self.status(f"当前共 {len(self._doc['pages'])} 页拼版", "info")

    def _apply_picker_removed(self, dialog) -> None:
        """把弹窗里「删除图片 / 恢复」的结果落回文档（``removed`` 黑名单）。

        与任务流程的 ``_apply_picker_removed`` 同一语义：删除/恢复是**即时
        意图**，与用户最终有没有开始拼版/添加无关（取消弹窗也要落盘）。
        """
        if not dialog.removed_changed():
            return
        self._doc["removed"] = [str(p) for p in dialog.removed_files()]

    def _on_add_image(self) -> None:
        """单图页点「新增图片」：append 弹窗挑 1 张，并进当前这一页。

        与任务流程的 ``_on_imposition_add_image`` 同一套语义（2026-10-13
        用户：独立拼图页跟任务流程保持一致）：版面规则唯一实现在
        ``services.imposition.append_item_to_page``——原图是左半幅 → 新图
        进右槽贴右边；其余 → 新图进左槽贴左边；原图的位置/大小/旋转
        **原样保留**。候选池与「选择拼版」同一套（剩余未用，可恢复已删除）。
        """
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if index < 0 or not (0 <= index < len(pages)):
            return
        items = pages[index].get("items") or []
        if len(items) != 1:
            return  # 按钮只在单图页出现；防御一下
        sources = list(self._sources)
        if not sources:
            self.toast("warning", "没有可添加的图片", "请先把图片拖到上面的输入框。")
            return
        used = used_source_files(self._doc)
        removed = excluded_files(sources, self._doc)
        removed_keys = {str(f) for f in removed}
        pool = [f for f in sources if str(f) not in used]
        remaining = [f for f in pool if str(f) not in removed_keys]
        if not remaining and not removed:
            self.toast(
                "warning", "没有可选的图片",
                "所有图片都已被拼版使用。可先删掉某些拼版页再来选。",
            )
            return
        dialog = ImpositionPickerDialog(
            pool, self, removed_files=removed, mode="append",
        )
        if not dialog.exec():
            # 取消也落盘：删除/恢复是即时意图，与是否添加无关
            self._apply_picker_removed(dialog)
            return
        self._apply_picker_removed(dialog)
        picked = dialog.picked_files()
        if len(picked) != 1:
            return  # append 弹窗只放行 1 张；这里兜底
        merged = append_item_to_page(items, picked[0])
        if merged is None:
            self.toast(
                "error", "添加失败",
                "读不到所选图片的尺寸（文件可能已被移动或删除），请换一张。",
            )
            return
        pages[index] = {**pages[index], "items": merged}
        # 版面变了，这一页的整页手改记录作废（与拖动/删除同口径）
        self._drop_page_override(index, reason="图片已改动")
        self._refresh_view()
        self.log(
            f"已在{cn_page_label(index)}新增图片「{Path(picked[0]).stem}」"
            f"（原有「{Path(items[0]['file']).stem}」的版面保持不动）。"
        )
        self.status(f"当前共 {len(pages)} 页拼版", "info")

    def _append_pages_from(self, picked: list[str]) -> None:
        """把勾选的图两两成页追加到文档末尾（奇数落单成单图页）。"""
        pages = self._doc.setdefault("pages", [])
        index = 0
        while index + 1 < len(picked):
            page = make_page(picked[index:index + 2])
            if page is not None:
                pages.append(page)
            index += 2
        if index < len(picked):
            page = make_single_page(picked[index])
            if page is not None:
                pages.append(page)

    def _auto_impose(self) -> None:
        """整份源清单按 ``auto_impose_pages`` 规则自动拼版（覆盖现有页）。"""
        if not self._sources:
            self.toast("warning", "还没有图片", "请先把图片拖到上面的输入框。")
            return
        pages = auto_impose_pages(self._sources)
        if not pages:
            self.toast("warning", "无法自动拼版", "图片尺寸读取失败，或清单为空。")
            return
        self._doc["pages"] = pages
        self._refresh_view()
        self.status(f"自动拼版完成，共 {len(pages)} 页", "success")
        self.log(f"自动拼版：{len(self._sources)} 张 → {len(pages)} 页")

    # ------------------------------------------------------------------ 版面
    def _on_items_changed(self, index: int, items: list) -> None:
        """画布改了当前页版面：写回文档（内存态）+ 攒一拍单页缩略图重合成。

        ⚠️ 顺带**作废这一页的手改记录**（``edited_file``）：版面一变，导出时
        会按新版面重新合成，手改的那张图已经不代表这一页了。

        缩略图（用户 2026-10-09）：拖动/缩放/旋转停手后，左列那条缩略图
        不能停在旧版面——页号攒进 ``_thumb_dirty_pages``，防抖
        (:data:`THUMB_REFRESH_DEBOUNCE_MS`) 到期单页重合成（拖动中签名
        每帧都在变，等真的停手了再合成一次就够）。
        """
        pages = self._doc.get("pages") or []
        if 0 <= index < len(pages):
            pages[index]["items"] = list(items)
            self._drop_page_override(index)
            self._thumb_dirty_pages.add(int(index))
            self._thumb_timer.start()
        self._refresh_panel()  # 拖动/旋转落定后回填面板角度与按钮显隐

    def _refresh_dirty_page_thumbs(self) -> None:
        """防抖到期：把攒下的那几页**单页**重生成缩略图实体并贴回左列。"""
        dirty, self._thumb_dirty_pages = self._thumb_dirty_pages, set()
        if not dirty:
            return
        pages = self._doc.get("pages") or []
        self._page_thumb_manager().invalidate(sorted(dirty), pages)

    def _drop_page_override(self, index: int, reason: str = "版面已改动") -> None:
        """丢掉第 ``index`` 页的整页手改记录（有的话写一句日志）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        if pages[index].pop("edited_file", None) is not None:
            self.log(
                f"{cn_page_label(index)}{reason}，之前对整页组合的手工修饰作废；"
                "导出时按当前版面重新合成。"
            )

    def _on_reorder(self, source: int, target: int) -> None:
        """左列拖动排序：把 ``source`` 移到 ``target``（移除后口径）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= source < len(pages)) or source == target:
            return
        page = pages.pop(source)
        pages.insert(min(max(target, 0), len(pages)), page)
        self._refresh_view()

    def _on_release_page(self, index: int) -> None:
        """左列「✕」：把这一页的源图移回候选池（页删除，文件不动）。"""
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        pages.pop(index)
        self._refresh_view()

    def _on_batch_delete(self) -> None:
        """左列勾选多页后批量删除。"""
        pages = self._doc.get("pages") or []
        for index in sorted(self.view.checked_pages(), reverse=True):
            if 0 <= index < len(pages):
                pages.pop(index)
        self._refresh_view()

    def _on_reset_layout(self) -> None:
        """「复位本页版面」：按当前页的源图重新生成默认并排。"""
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        files = [item["file"] for item in pages[index].get("items") or []]
        page = make_page(files) or make_single_page(files[0])
        if page is None:
            return
        # 复位 = 换掉整页内容（包括手改记录）：先按"原本有没有"记一句日志
        self._drop_page_override(index, reason="已复位为默认并排")
        pages[index] = page
        self._refresh_view()

    def _on_whole_rotate(self, delta: float) -> None:
        """「整体旋转」组件吐了增量：绕两图公共中心转（停手后统一提交）。

        与任务流程的 ``_on_imposition_whole_rotate`` 同口径：滑块连续吐增量
        期间只重绘不上报（``rotate_whole`` 只标脏），由
        :data:`_rotate_commit_timer` 在停手后 flush + 重适配 + 回填面板。
        """
        if self.view.current_index() < 0 or not self.view.canvas.has_items():
            return
        self.view.canvas.rotate_whole(delta)
        self._rotate_commit_timer.start()

    def _commit_rotation_edit(self) -> None:
        """旋转组件停手到期：把画布改动补报出去 + 重适配 + 回填面板。"""
        self.view.canvas.flush_pending()  # → items_changed → 写回文档+缩略图防抖
        # 整版转过后外接框变了：重新适配可视区（与任务流程同一行为）
        self.view.canvas.refit()
        self._refresh_panel()

    def _on_item_rotate(self, angle: float) -> None:
        """把选中图设为绝对旋转角（顺时针，度；停手后统一提交）。"""
        if self.view.current_index() < 0 or self.view.selected_slot() < 0:
            return  # 组件没选中时本来就该禁用；防御一下
        self.view.canvas.set_item_rotation(angle)
        self._rotate_commit_timer.start()

    def _on_delete_item(self) -> None:
        """删除选中图片（单图页删至空则整页移除，与详情页口径一致）。

        与任务流程的 ``_on_imposition_delete_item`` 对齐（2026-10-13 用户：
        独立拼图页跟任务流程保持一致）：**本页最后一张图删除前先弹确认框**
        ——整页拼版会一并移除；删剩一张时面板自动出现「新增图片」可再补。
        """
        slot = self.view.selected_slot()
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if slot < 0 or not (0 <= index < len(pages)):
            if index >= 0:
                self.toast("info", "没有选中的图片", "先在画布里点选要删除的图片。")
            return
        self.view.flush_pending()  # 拖住/转住没松手的改动先落定再删
        items = [dict(item) for item in pages[index].get("items") or []]
        if not 0 <= slot < len(items):
            return
        removed_item = items.pop(slot)
        if not items:
            # 本页最后一张：页会跟着一起删（与详情页同款：要确认）。
            # 此刻还没动任何状态（items 是副本），取消直接返回即可。
            from qfluentwidgets import Dialog

            dialog = Dialog(
                "删除图片",
                f"「{Path(removed_item['file']).stem}」是本页最后一张图片，"
                "删除后整页拼版将一并移除。\n是否继续？",
                self.window(),
            )
            dialog.yesButton.setText("删除")
            dialog.cancelButton.setText("取消")
            if not dialog.exec():
                return
        if items:
            pages[index]["items"] = items
            self._drop_page_override(index, reason="图片已改动")
        else:
            pages.pop(index)
        self._refresh_view()
        if items:
            self.log(
                f"已删除{cn_page_label(index)}选中的图片"
                f"「{Path(removed_item['file']).stem}」，回到未选择列表。"
            )
        else:
            self.log(
                f"已删除{cn_page_label(index)}最后一张图片"
                f"「{Path(removed_item['file']).stem}」，本页没有图了，整页移除。"
            )

    def _on_clear(self) -> None:
        """清空全部页（源清单保留，可重新拼）。"""
        self._doc["pages"] = []
        self.close_zoom_dialog()
        self._refresh_view()

    # -------------------------------------------------------------- 预览与编辑
    #
    # 用户 2026-10-03：「**独立步骤，图片也可以编辑生效**」。这四条此前在独立
    # 拼图页**整个没接线**——画布的右键菜单弹得出来、双击也会发信号，但点了
    # 什么都不会发生（信号发出去没人接）。语义与任务流程的拼版步骤逐条对齐：
    # 双击图上/空白 = 预览单张原图 / 整页左右组合（弹窗里「编辑」同样写回
    # 真实文件并接生效链）；右键「编辑单图 / 编辑整图」= 不经预览弹窗直接进编辑器，
    # 编辑结果覆盖真实文件并在导出时生效。

    def _open_item_preview(self, slot: int) -> None:
        """画布**双击某张图**：弹窗预览这张原图（可缩放、下载）。"""
        index = self.view.current_index()
        self._open_zoom(lambda _i: self._item_target(index, slot), 0)

    def _open_spread_preview(self) -> None:
        """画布**双击两图之外的空白**：预览整页左右组合（按导出口径合成）。"""
        index = self.view.current_index()
        self._open_zoom(lambda _i: self._spread_target(index), 0)

    def _open_zoom(self, factory, index: int) -> None:
        """打开（或复用）预览弹窗；没有可预览的页时静默返回。"""
        from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

        if factory(index) is None:
            return
        if self._zoom_dialog is None:
            self._zoom_dialog = dialog = ImageZoomDialog(
                self.window() or self, factory=factory
            )
            # 弹窗里「编辑」覆盖了真实文件 → 生效链（与各步骤预览区同一套）
            dialog.image_saved.connect(self._on_zoom_image_saved)
        dialog = self._zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(factory=factory, index=index)

    def close_zoom_dialog(self) -> None:
        """关掉预览弹窗（内容失效时调：换源 / 清空）。"""
        if self._zoom_dialog is not None:
            self._zoom_dialog.close()

    def _item_target(self, page_index: int, slot: int):
        """弹窗「**单张原图**」来源：``slot`` 即弹窗页码（0 右槽 / 1 左槽）。

        ``edit_path`` = 这张源图文件：弹窗里「编辑」「完成」后原子覆盖回源图，
        由 :meth:`_on_zoom_image_saved` 接生效链（2026-10-07 用户定：预览弹窗
        里的编辑也要生效，不再只读——与任务流程的拼版步骤保持一致）。
        """
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget
        from desktop.workers import PreviewWorker

        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return None
        items = pages[page_index].get("items") or []
        if not (0 <= slot < len(items)):
            return None
        path = Path(str(items[slot].get("file") or ""))
        if not path.is_file():
            return None
        side = "右侧" if slot == 0 else "左侧"
        return ZoomTarget(
            render=lambda edge, p=path: PreviewWorker(p, longest_edge=edge),
            note=f"{cn_page_label(page_index)} · {side}「{path.name}」",
            stem=path.stem,
            count=len(items),
            edit_path=path,
            edit_label="编辑单图",
        )

    def _spread_target(self, page_index: int):
        """弹窗「**整页左右组合**」来源：构造时快照版面，合成在 worker 线程。"""
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget
        from desktop.workers import ImpositionPagePreviewWorker

        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return None
        items = [dict(item) for item in pages[page_index].get("items") or []]
        if not items:
            return None
        stems = page_source_stems(pages[page_index])
        right = stems[0] if stems else ""
        left = stems[1] if len(stems) > 1 else ""
        # 整页组合是虚拟图，回写目标是**手改缓存**（edited/NNNN.png，导出时
        # 盖回成品）——只在 doc 里这一页的手改记录还挂着且文件在时给：记录
        # 在就代表版面自手改后没动过（一动手 ``_drop_page_override`` 就清），
        # 手改文件与当前版面内容一致，拿它当编辑基底不会张冠李戴。没手改过
        # 时弹窗退回只读（画布右键空白「编辑整图」不受限，它现场合成）。
        # ``save_path`` 一并给：显示与回写是同一份内容的整页图（非裁剪区域），
        # 编辑器加载的是全分辨率手改图，「完成」后弹窗直接显示编辑结果。
        edited = pages[page_index].get("edited_file")
        edit_path = Path(edited) if edited and Path(edited).is_file() else None
        return ZoomTarget(
            render=lambda edge, page={"items": items}: (
                # ⚠️ 白底（与「导出成品」同口径）：singletask 的整页组合预览
                #    和编辑基底都要长得跟导出的 PNG 一样（2026-10-13 用户）。
                ImpositionPagePreviewWorker(page, edge, WHITE_BACKGROUND)
            ),
            note=f"{cn_page_label(page_index)} 左右组合（左「{left}」+ 右「{right}」）",
            stem=f"imposition-{page_index + 1:02d}",
            count=1,
            save_path=edit_path,
            edit_path=edit_path,
            edit_label="编辑整图",
        )

    def _open_item_edit(self, slot: int) -> None:
        """画布**右键某张图 →「编辑单图」**：不经预览弹窗，直接编辑原图。

        编辑的是该槽位对应的**源图全分辨率原图**，「完成」= 原子覆盖回该文件
        （与其余独立步骤、任务流程同一套 ``overwrite_image_file``）。落盘后的
        刷新链：① 画布丢掉这张图的解码缓存并重绘；② 左列该页缩略图按新图重渲
        （源图 mtime 变新 ⇒ 缓存自动判过期重写）；③ 日志说明**什么时候生效**。
        """
        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QDialog

        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        items = pages[index].get("items") or []
        if not (0 <= slot < len(items)):
            return
        file_text = str(items[slot].get("file") or "")
        path = Path(file_text)
        image = QImage(file_text) if path.is_file() else QImage()
        if image.isNull():
            self.toast(
                "warning", "无法编辑",
                f"读不到原图：{path.name}（文件可能已被移动或删除）。",
            )
            return
        from desktop.components.viewers.image_editor import (
            ImageEditorDialog, sync_content_quad,
        )
        from desktop.components.viewers.image_zoom_dialog import overwrite_image_file

        editor = ImageEditorDialog(self.window(), image, save_back=True)
        editor.target_name = path.name
        editor.source_path = file_text
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        if editor.apply_in_progress():
            # ⚠️ 后台应用中（2026-10-10「应用卡顿」）：烘焙+写盘在工作线程，
            #    完成回调里做刷新链（磁盘与 sidecar 已由编辑器落好）。
            editor.apply_completed.connect(
                lambda _path, edited: self._after_source_edited(
                    file_text, edited))
            editor.apply_failed.connect(
                lambda _path, reason: self.toast(
                    "error", "保存失败",
                    f"编辑未生效：{path.name}（{reason}）"))
            return
        edited = editor.result_image()
        if edited is None or edited.isNull():
            return
        if not overwrite_image_file(edited, path):
            self.toast("error", "保存失败", f"编辑未生效：{path.name}")
            return
        sync_content_quad(file_text, editor)
        self._after_source_edited(file_text, edited)

    def _after_source_edited(self, file_text: str, edited) -> None:
        """拼版源图编辑生效后的**刷新链**（同步/后台应用两条路共用）。"""
        self.view.canvas.invalidate_image(file_text)
        # ⚠️⚠️ 源图尺寸可能变了（编辑器里旋转/裁剪后覆盖回同一文件）：版面
        #    rect 还按旧尺寸记着，合成时 compose_page 会把新图硬 resize 回
        #    旧宽高 ⇒ 形变 + 清晰度下降（2026-10-10 报障）。先刷新 rect 再
        #    刷视图，画布/缩略图/导出用的才是新几何。
        if refresh_rects_for_edited_source(self._doc, file_text):
            self._refresh_view()
        self._invalidate_page_thumbs_for(file_text)  # 含它的页重生成实体
        self.log(
            f"已编辑拼版源图「{Path(file_text).name}」并覆盖原图"
            f"（{edited.width()}×{edited.height()} px）；"
            "点「导出成品」即用上这次修改。"
        )

    def _open_spread_edit(self) -> None:
        """画布**右键空白处 →「编辑整图」**：直接编辑整页左右组合（成品口径）。

        组合图是**虚拟图**（没有源文件），所以这里按导出口径（``compose_page``
        的紧裁合成，与落盘成品同一套代码）在 worker 线程现场合成**全分辨率**
        图交给编辑器；「完成」把结果原子覆盖到 ``singletask/拼图/edited/<页>.png``，
        导出那一刻由 :meth:`_compose_job` 盖到对应成品上。

        ⚠️ 独立页没有任务流程那种"提交进 ``stages/imposition``"的落点，所以
        手改图先存缓存区；若之后又拖这一页的版面，会重新合成、覆盖这次修饰
        （:meth:`_on_items_changed` 会清掉手改记录，日志里也写了）。
        """
        index = self.view.current_index()
        pages = self._doc.get("pages") or []
        if not (0 <= index < len(pages)):
            return
        self.view.flush_pending()  # 拖住没松手的改动先落定，快照才是最新的
        items = [dict(item) for item in self.view.current_items()]
        if not items:
            return
        from desktop.workers import ImpositionPagePreviewWorker, connect_queued

        # longest_edge=0 = 不缩：编辑器要的是全分辨率（与落盘成品同一分辨率）。
        # ⚠️ 白底（与「导出成品」同口径）：编辑基底与导出 PNG 长得一样。
        self.run_worker(
            lambda: ImpositionPagePreviewWorker(
                {"items": items}, longest_edge=0, background=WHITE_BACKGROUND,
            ),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished,
                    lambda _i, image, _s, t=index: self._on_spread_edit_ready(
                        t, image
                    ),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda _i, msg: self.toast("error", "拼版合成失败", msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_spread_edit_ready(self, page_index: int, image) -> None:
        """组合图合成完毕（主线程）：开编辑器，「完成」存进缓存区待导出盖上。"""
        from PySide6.QtWidgets import QDialog

        if image is None or image.isNull():
            return
        pages = self._doc.get("pages") or []
        if not (0 <= page_index < len(pages)):
            return
        from desktop.components.viewers.image_editor import (
            ImageEditorDialog, sync_content_quad,
        )
        from desktop.components.viewers.image_zoom_dialog import overwrite_image_file

        target = edited_page_dir() / FILE_FMT.format(page_index + 1)
        editor = ImageEditorDialog(self.window(), image, save_back=True)
        editor.target_name = f"{cn_page_label(page_index)}的整页组合"
        editor.source_path = str(target)
        # 第一次编辑这页时 ``edited/NNNN.png`` 还不存在 ⇒ 没有旧图可覆盖，
        # 不弹确认（第二次起才弹，见 ImageEditorDialog._confirm_overwrite）。
        editor.target_exists = target.is_file()
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        if editor.apply_in_progress():
            # ⚠️ 后台应用中（2026-10-10「应用卡顿」）：完成回调接链
            editor.apply_completed.connect(
                lambda _path, edited: self._after_spread_edited(
                    page_index, target, edited))
            editor.apply_failed.connect(
                lambda _path, reason: self.toast(
                    "error", "保存失败",
                    f"编辑未生效：{target.name}（{reason}）"))
            return
        edited = editor.result_image()
        if edited is None or edited.isNull():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if not overwrite_image_file(edited, target):
            self.toast("error", "保存失败", f"编辑未生效：{target.name}")
            return
        sync_content_quad(str(target), editor)
        self._after_spread_edited(page_index, target, edited)

    def _after_spread_edited(self, page_index: int, target, edited) -> None:
        """整页组合编辑生效后的收尾（磁盘与 sidecar 已落好，两条路共用）。"""
        pages = self._doc.get("pages") or []
        if 0 <= page_index < len(pages):
            pages[page_index]["edited_file"] = str(target)
        self.log(
            f"已编辑{cn_page_label(page_index)}的整页组合并保存"
            f"（{edited.width()}×{edited.height()} px）；"
            "点「导出成品」时这一页用编辑后的图。"
        )
        self.toast("success", "整页组合已编辑", "导出成品时这一页用编辑后的图。")

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """预览弹窗里「编辑」覆盖了真实文件（``image_saved``）：按落点接链。

        回写目标由 ``ZoomTarget.edit_path`` 给（2026-10-07 用户定：预览弹窗里
        的编辑也要生效）——落点只有两种：

        - **源图**（单张原图编辑）：走与画布右键 :meth:`_open_item_edit`
          完全相同的善后——画布丢解码缓存、左列缩略图重渲、日志说明
          「导出成品」时生效。
        - **整页组合的手改缓存**（``edited/``）：给 ``edit_path`` 的前提就是
          doc 的 ``edited_file`` 本来指着它，文件已被覆盖成最新，补一句日志。

        ⚠️⚠️ **先无条件把画布那张图的解码缓存丢掉，再去认它属于哪一页**：
        认页靠路径比较，而缓存键是 ``item["file"]`` 原样字符串、``path_text``
        来自 ``Path(...)``——两边只要有一处形态不同（Windows 分隔符、大小写、
        相对/绝对），比较就落空，旧代码于是**整段 return 什么都不做**，
        用户看到的就是"从预览弹窗里编辑完，关掉弹窗拼版页还是老图"
        （2026-10-08 报障）。丢缓存本身按路径规范化命中、对不属于本页的
        路径也无害，所以放在判断之前；认页只用来决定"打哪句日志、刷哪条
        缩略图"。
        """
        if image is None or image.isNull():
            return
        path = Path(path_text)
        self.view.canvas.invalidate_image(path_text)
        pages = self._doc.get("pages") or []
        hits = [
            index for index, page in enumerate(pages)
            if page_has_file(page, path_text)
        ]
        if hits:
            # ⚠️ 同 _open_item_edit：源图尺寸可能变了，先刷 rect 再刷视图
            #    （否则 compose_page 把新图硬 resize 回旧宽高 ⇒ 压扁变形）。
            if refresh_rects_for_edited_source(self._doc, path_text):
                self._refresh_view()
            self._invalidate_page_thumbs_for(path_text, hits)
            self.log(
                f"已编辑拼版源图「{path.stem}」并覆盖原图"
                f"（{image.width()}×{image.height()} px）；"
                "点「导出成品」即用上这次修改。"
            )
            return
        if path.parent == edited_page_dir():
            self.log(
                f"已编辑整页组合「{path.name}」"
                f"（{image.width()}×{image.height()} px）；"
                "点「导出成品」时这一页用手改图。"
            )

    # ------------------------------------------------------------------ 导出
    def _compose_job(self, request: StepRequest, report) -> str | None:
        """执行内核的 job：把整份文档合成为图片（纯函数，线程里安全）。

        ⚠️ 写成 job 而不是页面方法，是为了让"跑什么"与"怎么跑/怎么汇报"
        分开——内核负责后者（线程 + 信号），本页只管前者。

        **手工修饰过的整页组合优先**：右键空白处「编辑整图」改出来的那张图
        存在 ``singletask/拼图/edited/`` 里（见 :meth:`_open_spread_edit`），
        这里在整套合成之上把它按页盖回去——不盖的话，用户改完一看导出的
        成品还是老样子（这就是"编辑没生效"）。
        """
        doc = request.args["doc"]
        dest = request.dest
        # job 契约：导出一定带输出目录（执行内核总会把 dest 设好）
        assert dest is not None, "拼图导出 job 必须带输出目录"
        dest = Path(dest)
        # ⚠️ 页数按 **compose_doc 的过滤后口径**取（``normalize_page`` 会静默
        #    丢掉不可修复的页），否则这里算出的分母与合成循环报的分母不一致，
        #    进度条会在末页突然倒退。``_page_overrides`` 用的也是这套口径。
        pages = len(_page_overrides(doc))
        # 逐页进度：``compose_doc`` 合成一页报一次（内核转成 progress 信号）。
        # ⚠️ report 为 None 时整条链都不汇报（内核正常运行时一定非None，
        #    但 job 契约允许"只干活"——既有自测就是这么直接调本 job 的）。
        # ⚠️ **白底导出**（2026-10-13 用户）：singletask 导出的 PNG 就是最终
        #    交付物，透明底在看图软件里不合理。任务流程的 ``stages/imposition``
        #    仍走默认透明底（PDF 侧压平白纸、编辑器要透明），互不影响。
        written = compose_doc(
            doc, dest,
            report=None if report is None else (
                lambda done, total: report(
                    "progress", {"done": done, "total": total}
                )
            ),
            background=WHITE_BACKGROUND,
        )
        overrides = _page_overrides(doc)
        for index, source in enumerate(overrides):
            if source is None or not source.is_file():
                continue
            target = dest / FILE_FMT.format(index + 1)
            try:
                # ⚠️ 手改页也压到**白底**（不能原样复制）：手改缓存是编辑器
                #    写出的 RGBA（透明底），原样盖回去的话同一批成品里就
                #    "合成页白底、手改页透明"两种底。
                flatten_onto_background(source, target, WHITE_BACKGROUND)
            except OSError:
                continue  # 盖不上就当没手改过，至少合成结果还在
            if target not in written:
                written.append(target)
        # ⚠️ 合成那 100% **不等于整轮跑完**：手改整页组合还要一页页盖回去。
        #    这里再报一轮"盖回 n/N"，否则进度条会在还有活儿的时候显示完成。
        # ⚠️ ``report`` 可能是 None——job 契约是"可只干活不汇报"（既有自测就是
        #    直接传 None 调本job 的），所以每处汇报前都要判，别假定它可用。
        edited = sum(1 for s in overrides if s is not None and s.is_file())
        if edited and report is not None:
            for index in range(edited):
                report("progress", {
                    "done": pages + index + 1,
                    "total": pages + edited,
                })
        self._export_result["count"] = len(written)
        return str(request.dest)

    def _export(self) -> None:
        """把整份文档合成为 PNG（后台线程，避免大图阻塞界面）。"""
        # 面板旋转组件的改动可能还挂在防抖里（转住没停满 250ms 就点导出）：
        # 先停表补报，导出的 doc 才是最新版面。
        self._rotate_commit_timer.stop()
        self.view.flush_pending()
        pages = self._doc.get("pages") or []
        if not pages:
            self.toast("warning", "没有拼版页", "请先把图片拖到上面的输入框，再拼版。")
            return
        if self.kernel.busy():
            self.toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        out_dir = self._out_dir
        if out_dir is None:
            base = Path(self._sources[0]).parent if self._sources else Path.cwd()
            out_dir = base / "拼图成品"
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出目录", str(out_dir)
        )
        if directory:
            out_dir = Path(directory)
        self._out_dir = out_dir

        self.export_button.setEnabled(False)
        # 再导一次：上一轮的「查看处理文件」先收起，成功后按新目录再亮
        self.view_output_button.setVisible(False)
        # 先点亮进度条再起线程：极小的一批可能瞬间跑完，先亮才不会被收尾盖掉
        self.progress_row.start()
        self.status("正在导出…", "info")
        self.log(f"开始导出 {len(pages)} 页 → {out_dir}")
        self._export_result = {}
        request = StepRequest(dest=out_dir, args={"doc": dict(self._doc)})
        if not self.kernel.run(request):
            self.export_button.setEnabled(True)
            self.progress_row.reset()
            self.status("正在导出", "warning")

    def _on_progress(self, done: int, total: int) -> None:
        """一条执行进度：喂给右栏那条进度行。"""
        self.progress_row.update(done, total)

    def _on_exported(self, out_dir: str) -> None:
        """导出成功：恢复按钮、进度条走到头并提示，亮出「查看处理文件」。"""
        count = int(self._export_result.get("count", 0))
        self.export_button.setEnabled(True)
        self._last_output = Path(out_dir)
        self.view_output_button.setVisible(True)
        self.progress_row.succeed(
            f"完成 {count} 页" if count else "已完成"
        )
        self.status(f"导出完成：{out_dir}（{count} 页）", "success")
        self.log(f"导出完成：{count} 页 → {out_dir}")
        self.toast("success", "导出完成", f"共导出 {count} 页到：\n{out_dir}")

    def _open_last_output(self) -> None:
        """「查看处理文件」：资源管理器打开最近一次导出的目录。"""
        if self._last_output is None:
            return
        from desktop.utils.files import reveal_in_explorer

        reveal_in_explorer(self._last_output)

    def _on_export_failed(self, message: str) -> None:
        """导出失败：恢复按钮、进度条停住并提示。"""
        self.export_button.setEnabled(True)
        self.progress_row.fail()
        self.status("导出失败", "error")
        self.log(f"导出失败：{message}")
        self.toast("error", "导出失败", message)

    # ------------------------------------------------------------------ 刷新
    def _refresh_view(self) -> None:
        """把当前文档灌进拼版视图（页清单 + 画布），并同步面板状态。"""
        pages = self._doc.get("pages") or []
        current = min(self.view.current_index(), len(pages) - 1)
        self.view.set_pages(pages, current=current if current >= 0 else -1)
        self._refresh_page_thumbs()
        self._refresh_panel()
        self.export_button.setEnabled(bool(pages))

    # -------------------------------------------------------------- 缩略图
    def _page_thumb_manager(self):
        """页面缩略图**实体**的管理者（懒建，首用即钉在独立区目录上）。"""
        from desktop.components.imposition.page_thumb import PageThumbManager
        from desktop.utils.files import page_thumbs_dir

        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is None:
            manager = PageThumbManager(
                page_thumbs_dir(_SPEC.disk_key()), THUMB_EDGE,
                self.run_worker, parent=self,
            )
            manager.page_ready.connect(self._on_page_thumb_ready)
            self._page_thumb_mgr = manager
        return manager

    def _on_page_thumb_ready(self, index: int, pixmap) -> None:
        """一页的实体缩略图生成完：贴回左列那一条。"""
        if pixmap is not None and not pixmap.isNull():
            self.view.set_thumb_at(index, pixmap)

    def _invalidate_page_thumbs_for(
        self, path_text: str, hits: list[int] | None = None
    ) -> None:
        """某张源图被覆盖（编辑落盘）：含它的页重新生成缩略图实体。

        ⚠️ 签名里带**源图文件指纹**（大小+mtime）：覆盖后签名必然变
        ⇒ 把含这个路径的页排进重生成批次即可。路径形态（斜杠/大小写）
        走 :func:`services.imposition.same_path` 判等（2026-10-08 报障
        "编辑完左列还是老图"的实体版防复发）。
        """
        pages = self._doc.get("pages") or []
        if hits is None:
            hits = [
                index for index, page in enumerate(pages)
                if any(same_path(str(item.get("file") or ""), path_text)
                       for item in page.get("items") or [])
            ]
        if hits:
            self._page_thumb_manager().invalidate(hits, pages)

    def _refresh_page_thumbs(self) -> None:
        """左列每页的缩略图：**页面效果**（落盘实体 ``pageN.jpg``）。

        旧口径"每页取第一张源图当代表"只显示半幅；上一版内存合成口径
        页内某张源图缩略图没到就出半张（用户 2026-10-09 在 0002 任务上
        二次报障，拍板：**缩略图实体要生成落地**，另放目录、按 page1
        page2 命名、做好映射数据）。现在是实体口径：按版面把整页合成
        一张小图落盘（``singletask/imposition/page_thumbs/page<N>.jpg``
        + ``index.json`` 映射），UI 只贴实体文件；签名（版面 + 源图文件
        指纹）不匹配的页后台重生成。命中的页直接读盘——重进页面零生成。

        ⚠️ 与任务流程拼版页共用管理者组件，但**缓存根各归各**（用户
        2026-10-04 明确「singletask 和 taskdetail 不是一回事」）。
        """
        pages = self._doc.get("pages") or []
        manager = self._page_thumb_manager()
        manager.retain(len(pages))
        thumbs = [manager.pixmap_for(i, page) for i, page in enumerate(pages)]
        self._page_thumbs = thumbs
        self.view.set_page_thumbs(thumbs)
        manager.flush()

    def _refresh_panel(self) -> None:
        """把画布当前状态回填到右侧面板（状态文案 + 旋转组件 + 按钮显隐）。

        与任务流程的 ``_sync_imposition_rotation_ui`` + 单图页判定同口径：
        整版角度=平均角、选中图角度=选中角（没有选中则「删除选中图片」
        隐藏、「当前图片样式」灰掉）；单图页才露出「新增图片」。回填走
        blockSignals 语义（panel 内部挡信号），不会把同步误当成用户输入。
        """
        panel = self.panel
        label = panel.status_label
        pages = self._doc.get("pages") or []
        index = self.view.current_index()
        canvas = self.view.canvas
        if not pages or index < 0 or not canvas.has_items():
            panel.set_page_available(False)
            panel.set_whole_angle(0.0)
            panel.set_item_rotation(None)
            panel.set_single_page(False)
            if not pages or index < 0:
                label.setText("还没有拼版页")
            return
        panel.set_page_available(True)
        panel.set_whole_angle(canvas.spread_rotation() or 0.0)
        panel.set_item_rotation(
            canvas.selected_rotation() if canvas.selected() >= 0 else None
        )
        stems = page_source_stems(pages[index])
        panel.set_single_page(len(stems) == 1)
        if len(stems) == 1:
            label.setText(f"{cn_page_label(index)}　·　整幅「{stems[0]}」")
        else:
            label.setText(
                f"{cn_page_label(index)}　·　右「{stems[0]}」　左「{stems[1]}」"
            )

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """关闭页面前中止并等待导出线程。"""
        try:
            self.view.flush_pending()
        except RuntimeError:
            pass
        self.kernel.shutdown()
        super().shutdown_workers()


__all__ = ["ImpositionModulePage"]
