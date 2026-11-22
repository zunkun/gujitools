# -*- coding: utf-8 -*-
"""拼版共享基元的**拼版详情**分片：视图灌装、进详情、切任务复位。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.store import IMPOSITION_LABEL, IMPOSITION_STAGE

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition._host import ImpositionBaseHost
else:
    ImpositionBaseHost = object


class DetailMixin(ImpositionBaseHost):
    """拼版视图刷新、详情切换与任务切换复位。"""

    # ------------------------------------------------------------- 视图刷新
    def _refresh_imposition_view(self) -> None:
        """把落盘的拼版文档灌进页面控件（左列清单 + 画布）。

        保留用户当前看的那一页；之前"没有页"（-1）而现在已经有了，就落到
        第一页——否则用户看不到刚加的那页（画布停在空纸）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        pages = self._imposition_pages()
        index = view.current_index()
        if index < 0 and pages:
            index = 0
        view.set_pages(pages, current=index)
        # 左列缩略图跟着页清单走（每页取"第一张源图"的缩略图；用户 2026-10-04
        # 报「任务流程里缩略图不显示、只有占位」——这条链此前从没喂过缩略图）
        self._refresh_imposition_page_thumbs(pages)

    # ------------------------------------------------------------- 拼版详情
    def _select_imposition_detail(self) -> None:
        """流程条点了「图片拼版」：预览区/控制区切到拼版详情。

        拼版不是可执行步骤：执行/提交按钮整组隐藏，
        执行记录与检测统计也不适用。
        """
        self._refresh_imposition_view()
        view = getattr(self, "imposition_view", None)
        if view is not None and view.current_index() < 0 and view.pages():
            view.set_current(0)
        # ⚠️ 两个栈都按**页号**（``stack_index``）翻，不是步骤条格序：
        #    拼版节点在步骤条上插在它该在的位置，但栈里仍占"伪步骤"那一页。
        #    找不到（自定义流程删了拼版节点）就别动栈，交给调用方回退。
        page = self.stack_index_of_step(IMPOSITION_STAGE)
        if page is not None:
            self.control_stack.setCurrentIndex(page)
            self.preview_stack.setCurrentIndex(page)
        # ⚠️ 藏**整行**（action_row =「检测文本框 + 分割图片」并排），不是
        #    单个按钮：只藏按钮的话行高仍在，控制区底部会留一条空白。
        self.action_row.setVisible(False)
        # 「下载 PDF」同样只在第四步出现（拼版页没有生成 PDF 这一步）
        self._sync_download_print_button()
        self.detect_stats.setVisible(False)
        self.history_block.setVisible(False)
        self._set_stage_status(f"{IMPOSITION_LABEL}：可选节点（拼版版面）")
        self._apply_control_width()
        # 开关回填当前选择状态（blockSignals 避免回抛覆盖落盘值）
        checkbox = getattr(self, "imposition_enabled_checkbox", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(self._load_imposition_enabled())
            checkbox.blockSignals(False)
        self._update_imposition_status(view.current_index() if view is not None else -1)

    def _reset_imposition_state(self) -> None:
        """切任务：取消在飞合成、清忙标记，并把新任务的拼版文档灌进视图。"""
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            timer.stop()
        edit_timer = getattr(self, "_imposition_edit_timer", None)
        if edit_timer is not None:
            edit_timer.stop()  # 上一任务的旋转组件停顿提交别再落进新任务
        # 单页缩略图的重合成计时器同理：旧任务攒的页号不能落进新任务
        thumb_timer = getattr(self, "_imposition_thumb_timer", None)
        if thumb_timer is not None:
            thumb_timer.stop()
        self._imposition_thumb_dirty = set()
        # 预览弹窗里那页是上个任务打开时的快照，留着就是旧任务的图
        self.close_imposition_zoom_popup()
        self._imposition_dirty = False
        self._imposition_composing = False
        # 「给可见页缩略图让路」的计时随任务清（旧任务的等待不该拖住新任务合成）
        self._imposition_compose_deferred_at = None
        # 「上次落盘时的逐页签名」随任务清：新任务的版面与本任务无关，留着会让
        # "只重存变了的那几页"算错页（也会把本任务的成品误判成已最新）。
        # ⚠️ 真正的基线在**侧车文件**里（``drafts/imposition[~节点].composed.json``，
        #    跨会话有效）；这里清的是**内存缓存**，下次用到时按新任务重读。
        self._imposition_page_sigs = {}
        self._composed_sigs_cache = {}
        self._imposition_compose_doc = None
        self._imposition_compose_out_dir = None
        self._imposition_compose_sigs_path = None
        self._imposition_compose_doc_path = None
        self._imposition_compose_doc_mtime = None
        self._imposition_composed_pages = []
        # 页面缩略图实体的管理者：清空内存态（旧任务的位图/排队页不能带进
        # 新任务）；目录切换交给下次刷新时的访问器判等（实体按内容签名寻址，
        # 目录不换就不会拿旧任务的实体）
        mgr = getattr(self, "_page_thumb_mgr", None)
        if mgr is not None:
            mgr.reset()
        # 新任务的取图来源未必和上个任务一样：让 _refresh_print_source 重新判定
        self._print_source_cache = None
        # ⚠️ **不在这里灌拼版页清单**：``_refresh_imposition_view`` 会建 107 个页条
        #    控件 + 逐页缩略图实体（真实 GUI 实测 ~220ms），而落地步骤绝大多数
        #    是「图片去底色」——拼版页根本不可见，这笔钱纯属白付（用户 2026-10-21
        #    报"进详情要等 2~3 秒"）。这里只把视图清空（旧任务的页不能带进来），
        #    真进「图片拼版」时 ``_select_imposition_detail`` / ``_save_imposition_pages``
        #    会照常刷新。
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_pages([], current=-1)
            self._refresh_imposition_page_thumbs([])
        self._update_imposition_status(-1)
