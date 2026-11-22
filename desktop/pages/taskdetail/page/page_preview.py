# -*- coding: utf-8 -*-
"""任务详情页的预览刷新：切步骤重装预览、位图释放、聚合起点轮询。"""

# pylint: disable=not-callable
# ^ ``getattr`` 探测可选方法（reload_thumb / release_buffers / restore_buffers）
#   后的 ``callable()`` 守卫；拆分到普通 Mixin 后 pylint 把默认值 None 当成
#   唯一类型，属既有误报，与 PySide6 的 no-name-in-module 同类。

from __future__ import annotations

import os
from pathlib import Path
from desktop.steps import ports
from desktop.store import IMPOSITION_STAGE
from desktop.utils.files import changed_images, image_files_fingerprint
from typing import TYPE_CHECKING, Any

from .constants import INPUT_NODE_POLL_MS


class PagePreviewMixin:
    """预览刷新与阶段位图生命周期。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _aggregate_pending: Any
        _aggregate_start_poll: Any
        _aggregate_start_stage: Any
        _apply_current_image_offset: Any
        _current_print_pdf_path: Any
        _current_stage_input_dir: Any
        _dir_files: Any
        _drop_imposition_source_thumb: Any
        _is_aggregate_input_node: Any
        _manifest_paths: Any
        _node_dir: Any
        _page_thumb_for: Any
        _page_thumb_mgr: Any
        _print_entries: Any
        _print_source_mark: Any
        _refresh_detect_stats: Any
        _set_stage_status: Any
        _stage_input_visible: Any
        _sync_manifest_to_input: Any
        _warm_entry_thumbs: Any
        control_stack: Any
        current_stage: Any
        detect_viewer: Any
        extract_input_viewer: Any
        extract_result_viewer: Any
        extract_viewer_host: Any
        imposition_view: Any
        node_of_stage: Any
        pages: Any
        preview_stack: Any
        print_preview: Any
        rembg_viewer: Any
        rembg_viewer_host: Any
        stage_at_stack_index: Any
        store: Any
        task_id: Any

    # ------------------------------------------------------------------ 预览刷新
    def _step_input_updated_files(self) -> list[Path]:
        """**当前这一步**的输入产物里，这次**更新了哪些图片**（逐文件比对指纹）。

        上游产物被**同名覆盖**时（拼版成品重合成、单页重提取、编辑器回写源图）
        路径毫无变化，只看路径/目录级指纹只能问出"这个目录有没有变过"，问不出
        **是哪几张**——而"按页失效旧版面、旧缩略图"必须精确到文件（用户
        2026-10-18：「上一步更新了哪些图片要有记录」）。

        返回的是本次新发现变化的绝对路径（升序）；没有基线（第一次见到这个目录）
        或目录读不到时返回空表——**第一次见面不能算"上一步更新了它"**。

        ⚠️ 记录是**无条件**写回的（基线永远更新到最新），否则判据会变成"和很早
        以前比"。
        ⚠️ 指纹要 **readdir + stat**（第四步取图目录可能几百页），所以只在
        **切步骤**这一次算（``_select_stage`` 调它），不进 ≤200ms 的热路径。
        """
        directory = self._current_stage_input_dir()
        if directory is None:
            return []
        key = str(directory)
        after = image_files_fingerprint(directory)
        updated = changed_images(self._dir_files.get(key), after)
        if after is not None:
            self._dir_files[key] = after
        return [Path(text) for text in updated]

    def _invalidate_page_caches_for(self, updated: list[Path]) -> None:
        """把**上游刚更新过的那几张图片**的页面缓存失效（用户 2026-10-18）。

        逐文件记录（:meth:`_step_input_updated_files`）的另一半用途：知道是哪几张
        变了，就能**只清那几张**的缓存，而不是整批重来——

        - **拼版页缩略图实体**（``thumbnails/imposition_pages[~<节点>]/pageN.jpg``，
          按"含这张源图的页"失效，见 ``_drop_imposition_source_thumb``）；
        - **预览区查看器的缩略图记忆**（detect / rembg 两个查看器按路径缓存了
          "缩略图路径 → 已解码图标"，文件被覆盖后不丢就会一直贴旧的）。

        ⚠️ 一次切步骤最多算一次；每张图只做 O(1) 计数的指针操作，不重新解码任何
        图片（真正的重解码由随后的 ``_refresh_preview(force=True)`` 分批做）。
        """
        if not updated:
            return
        for path in updated:
            text = str(path)
            try:
                self._drop_imposition_source_thumb(text)
            except Exception:  # noqa: BLE001 - 缓存失效失败不该拦住切步骤
                pass
            for viewer in getattr(self, "detect_viewer", None), \
                    getattr(self, "rembg_viewer", None):
                reload_thumb = getattr(viewer, "reload_thumb", None)
                if callable(reload_thumb):
                    try:
                        reload_thumb(text)
                    except Exception:  # noqa: BLE001
                        pass

    # ------------------------------------------- 离开步骤 → 释放预览区位图
    def _stage_preview_widget(self, stage: str):
        """步骤 → 它的预览控件（``preview_attr`` 是事实来源，拼版另开一路）。"""
        if stage == IMPOSITION_STAGE:
            return getattr(self, "imposition_view", None)
        spec = ports.spec_for_stage(stage)
        attr = spec.preview_attr if spec else ""
        return getattr(self, attr, None) if attr else None

    def release_stage_buffers(self, stage: str | None = None) -> None:
        """丢掉某一步骤（``None`` = 全部）预览区里**可重建的位图**。

        用户 2026-11-21：「离开拼版页面就释放，其他步骤也一样」。切走之后
        的几十~几百 MB 大图与缩略图没人再看，没必要攥着等内存涨到顶。

        ⚠️ 对照实验开关（2026-11-22）：内存优化（c6e8969）合入当晚起出现
        use-after-free（切换任务详情瞬间，Qt6Widgets notify_helper 写已释放
        的 QEvent），时间与场景都指向「离开即释放」。设
        ``GUJI_NO_RELEASE_BUFFERS=1`` 可整体跳过释放路径，用于隔离变量：
        关掉后不再崩 ⇒ 释放路径背锅；还崩 ⇒ Qt 6.11.3 自身的 bug。
        （跳过只是少省内存，功能不受影响——回来各控件自己会重装。）

        只释放位图：页面清单、当前页、勾选、未落盘的版面改动全都不动
        （离开前 ``flush_layout_pending`` / ``_flush_param_drafts`` 已补发）。
        回来由各控件的 ``restore_buffers`` 或既有的"进步骤刷新"重建。

        ⚠️ 这些预览控件是**直接构造的实例**，不是 ``LazyPanelHost``，
        ``getattr`` 探测 ``release_buffers`` 安全——``flush_layout_pending``
        那条"禁 getattr"约束针对的是 LazyPanelHost（它的 ``__getattr__``
        会把面板顺带建出来），与此无关。
        """
        if os.environ.get("GUJI_NO_RELEASE_BUFFERS"):
            return
        from utils.crash_log import breadcrumb
        breadcrumb(f"释放预览位图：stage={stage or '全部'}")
        stages = (
            [stage] if stage
            else ["extract", "detect", "rembg", "print", IMPOSITION_STAGE]
        )
        for key in stages:
            widget = self._stage_preview_widget(key)
            release = getattr(widget, "release_buffers", None)
            if callable(release):
                release()
        if stage in (None, IMPOSITION_STAGE):
            # 拼版左列缩略图的**实体管理者**挂在页面层（不在 view 里）
            manager = getattr(self, "_page_thumb_mgr", None)
            if manager is not None:
                manager.release_pixmaps()

    def _restore_stage_buffers(self, stage: str) -> None:
        """进入某步：它若被释放过，按原清单重装（未释放时是空操作）。"""
        widget = self._stage_preview_widget(stage)
        restore = getattr(widget, "restore_buffers", None)
        if callable(restore):
            restore()

    def _refresh_preview(self, index: int | None = None,
                         force: bool = False) -> None:
        """刷新某一步的预览；``force`` = 清单没变也按磁盘最新内容重装一遍。

        ``force`` 由 :meth:`_step_input_updated_files` 给出（上游产物被同名
        覆盖时本步的图标/条目会停在旧图上）。只有"图标/条目会被缓存下来"的
        那两步需要它（detect / rembg）——extract 的产物是**每次切页现读**、
        print 的列表本来每次都重建（见各自分支）。
        """
        if not self.task_id:
            return
        # ⚠️ **两套下标，这里必须显式分开**（用户 2026-10-06 报障的根因之一）：
        #    无参调用时手上只有 ``preview_stack.currentIndex()``，那是**栈页号**；
        #    而 ``stage_at_index`` 收的是**步骤条格序**。自定义流程里两者不等
        #    （detect 可以是格序 0 / 栈页号 1），混用会刷错那一步的预览——
        #    表现为"插了图，左侧列表却不动"。
        #    所以这里统一走 ``stage_at_stack_index``：调用方给的是栈页号或
        #    ``None``，都按栈页号这一层理解（``_select_stage`` 传的格序经
        #    ``stack_index`` 转一下，见调用处）。
        page = self.preview_stack.currentIndex() if index is None else index
        stage = self.stage_at_stack_index(page)
        if stage is None:
            return
        # 这一步若在离开时被释放过位图，先按原清单重装：否则随后的 set_images
        # 会因"清单没变"早退，用户回到这一步看到的是占位图 + 空白预览。
        self._restore_stage_buffers(stage)
        # ⚠️ 进detect/rembg 前按"这一步的输入目录"兜一次清单：流程里没有
        #    extract 时清单不会被任何阶段刷新，用户放进stages/input/ 的图
        #    就成了"明明有图却显示暂无图片"（用户 2026-10-06）。
        self._sync_manifest_to_input()
        # ⚠️ 清单有了不代表**上游已经生效**：去底色只是切缩略图就会把成品写进
        #    ``stages/rembg``，检测没提交时上游目录也可能留图。上游的产出动作
        #    没成功执行过，这一步就该显示"暂无图片"（用户 2026-11-03）。
        visible = self._stage_input_visible()
        # ⚠️ 聚合任务的**纯展示起点**（只有图片提取）：它没有输入（源 PDF
        #    不搬）⇒ 输入判据恒为假，用 input_node 兜住，别让起点显示"暂无
        #    图片"。其余起点（检测/去底色/拼版/PDF排版）的输入回落到
        #    ``stages/input``、入口输入天然生效，判据照普通步骤算就成立
        #    （用户 2026-11-18 任务 0026：「聚合数据来源需要显示在第一个
        #    节点中」；晚上口径：那些起点照常可重跑/编辑）。
        input_node = self._is_aggregate_input_node()
        visible = visible or input_node
        if stage == "extract":
            if input_node:
                # 没有 PDF 可看、也不该现场提取：屏上是只读图片清单（列表来自
                # 页清单＝产出目录，见 ``manifest._sync_manifest_to_input``
                # 的提取起点特判）
                self.extract_viewer_host.setCurrentWidget(self.extract_input_viewer)
                self.extract_input_viewer.set_images(
                    self._manifest_paths(), force=force
                )
                self._schedule_aggregate_start_poll()
                return
            self.extract_viewer_host.setCurrentWidget(self.extract_result_viewer)
            # ⚠️ 不再 set_images(manifest)（用户 2026-10-09 合并双标签）：
            #    左栏恒是 PDF 页缩略图；这里只把产物目录交给查看器——
            #    当前页已有产物就立即显示产物，没有等切页时现场提取。
            # ⚠️ 目录按**节点**取（B 方案）：同一步骤的多个节点各有产物目录。
            self.extract_result_viewer.set_extract_dir(self._node_dir("extract"))
        elif stage == "detect":
            paths = self._manifest_paths() if visible else []
            self.detect_viewer.set_images(paths, force=force)
            # 入口图片（这一步是流程第一步时）缩略图预热：没有就后台生成，
            # 别让左栏一直现解码原图（用户 2026-10-17）
            self._warm_entry_thumbs(paths)
            # 清单可能变了（增删页/切任务/批量检测跑完）→ 统计跟着重算
            self._refresh_detect_stats()
            # 检测起点可重跑/编辑（2026-11-18 晚口径）；汇集期间分批显示
            self._schedule_aggregate_start_poll()
        elif stage == "rembg":
            # 去底色起点（聚合任务）不再特判成只读清单：输入（成员的裁图）与
            # 产出（成员的成品图）都已汇集进来 ⇒ 原图/成品对比查看器就是
            # 这一步的如实回放（2026-11-18 晚口径）。
            self.rembg_viewer_host.setCurrentWidget(self.rembg_viewer)
            # ⚠️ 2026-10-22：去底色**不再按区域裁图**（area/border 已移除），
            #    所以这里不再喂 boxes_provider / border_provider——
            #    查看器于是按"一张输入图 = 一个条目"显示整图，与产物一致。
            #    裁好的半页图（-l/-r）是上一步「分割图片」的产物，本来就是
            #    独立文件，不需要再合成。
            paths = self._manifest_paths() if visible else []
            # ⚠️ 实时调整的草稿目录（2026-11-04 用户）：只在这一步显示，
            #    下游取图仍旧是正式成品目录。
            preview_dir = (
                self.store.rembg_preview_dir(
                    self.task_id, self.node_of_stage("rembg")
                )
                if self.task_id else None
            )
            self.rembg_viewer.set_images(
                paths,
                self._node_dir("rembg"),
                thumb_provider=self._page_thumb_for,
                preview_dir=preview_dir,
                force=force,
            )
            # 每张图片有自己的阈值偏移（黑名单法）：进入这一步/刷新清单后，
            # 把当前这张图的 offset 回填到面板（程序化回填，不算用户改动）。
            self._apply_current_image_offset()
            # 入口图片缩略图预热（同上：这一步是流程第一步时才有效）
            self._warm_entry_thumbs(paths)
            # 去底色起点可重跑（2026-11-18 晚口径）；汇集期间分批显示
            self._schedule_aggregate_start_poll()
        elif stage == "print":
            entries, _doc = self._print_entries()
            self.print_preview.set_entries(entries)
            # 入口图片缩略图预热：流程第一步就是「PDF排版」时，待打印清单直接
            # 来自入口目录（见 print_source_dir 的入口回落）
            self._warm_entry_thumbs([e.get("file") for e in entries])
            # 记下本次列表的来源：进入路径在 _refresh_print_source 里是"只作废
            # 缓存不重建"，不在这里补记的话，进第四步后每次后台合成回调都会
            # 把整批列表白重建一遍（同步解码首图，UI 冻结）
            # ⚠️ 记的是**内容标记**（目录 + 指纹）而不是目录字符串：拼版成品
            #    重合成后目录没变、内容换了，只记路径会让后台合成的收尾回调
            #    （``_on_imposition_composed`` → ``_refresh_print_source``）
            #    误判成"来源没换"而跳过重建（用户 2026-10-18 报障）。
            self._print_source_cache = self._print_source_mark()
            # 若此前已生成过 PDF，恢复下载按钮状态。
            # ⚠️ 走 _current_print_pdf_path（不是 _latest_print_pdf_path）：
            # 拼版开关一改，磁盘上那份 PDF 就是旧来源的产物，得让下载按钮
            # 灭掉——用户 2026-10-03："旧的数据不显示"。
            self.print_preview.set_pdf_path(self._current_print_pdf_path())

    def _schedule_aggregate_start_poll(self) -> None:
        """汇集期间每 ``INPUT_NODE_POLL_MS`` 重刷一次**聚合起点**清单
        （**分批显示**）。

        后台汇集是逐文件复制的：清单不必等全部复制完才出现——每次轮询都会
        ``_sync_manifest_to_input`` 按**当前输入目录现状**重建页清单，文件落
        一批显示一批（用户 2026-11-18：「如果时间长，是否可以分批导入，分批
        显示」）。检测/去底色起点显示的也是输入图，同样受益；提取起点显示
        产出图（它没有输入）。汇集结束（``.aggregate-pending`` 撤掉）就停表，
        改由 ``aggregate_ready`` 的整页重载收尾。
        """
        if self._aggregate_pending():
            self._aggregate_start_poll.start(INPUT_NODE_POLL_MS)
        else:
            self._aggregate_start_poll.stop()

    def _on_aggregate_start_poll(self) -> None:
        """轮询到点：还在汇集且还停在聚合起点上就重刷清单，否则停表。"""
        if not self.task_id or self._aggregate_start_stage() is None:
            self._aggregate_start_poll.stop()
            return
        if not self._aggregate_pending():
            self._aggregate_start_poll.stop()
            return
        self._refresh_preview()
        count = len(self.pages or [])
        self._set_stage_status(
            f"正在汇集子任务产物……已列出 {count} 张，清单会陆续补全"
            "（汇集完成后自动就绪）"
        )

    def _extract_params(self) -> dict:
        """第一步「图片提取」参数（单页按需提取用）：读当前面板表单。

        只在**正看着 extract 这一步**时读——面板是当前控制页，必然已构造；
        别的时候（别的步骤/离开任务）给空表，查看器按默认参数兜底。
        ⚠️ 表单填到一半 ``get_args()`` 会抛 ``ValueError``：不弹窗、按空表
        兜底（单页提取是预览性质的顺手活，不值得为它打断用户输入）。
        """
        if self.current_stage() != "extract" or not self.task_id:
            return {}
        panel: Any = self.control_stack.currentWidget()
        try:
            return dict(panel.get_args())
        except (ValueError, AttributeError, RuntimeError):
            return {}
