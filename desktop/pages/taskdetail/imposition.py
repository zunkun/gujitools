# -*- coding: utf-8 -*-
"""任务详情页的「图片拼版」共享基元与 Mixin 装配。

流程条上的「图片拼版」是**虚线可选节点**（``desktop.components.step_bar``）：
仅当第三步（图片去底色）的「区域模式」为 1（左右分开）时出现在「图片去底色」
与「生成 PDF」之间；用户可以选择它（启用）也可以不选择。

按操作逻辑拆成三个文件（后续可由不同 agent 分头维护，互不影响）：

- **本文件** ``ImpositionBaseMixin``：两个模块都要用的**共享基元**——
  area 读取与节点可见性、拼版文档读写（``drafts/imposition.json``）、
  源图清单与「拼版生效」判定、第四步取图切换（``print_source_dir``）、
  视图灌装、详情进出与切任务复位；
- **``imposition_pages.ImpositionPagesMixin``**（模块一「选择拼版」）：
  启用开关、弹窗加页、删页/页序/清空；
- **``imposition_layout.ImpositionLayoutMixin``**（模块二「拼版操作」）：
  旋转/复位、版面落盘、防抖后台合成、状态行。

⚠️ 拼版本身**不是** STAGES 里的一步：runs.json / 阶段面板机制一概不感知它，
执行按钮组在拼版详情里整组隐藏。
"""

from __future__ import annotations

from pathlib import Path

from desktop.pages.taskdetail.imposition_layout import ImpositionLayoutMixin
from desktop.pages.taskdetail.imposition_pages import ImpositionPagesMixin
from desktop.store import IMPOSITION_INDEX, IMPOSITION_LABEL, STAGES
from desktop.utils.files import list_stage_images
from utils.sort_utils import pdf_custom_sort_key

#: 拼版节点出现的条件：第三步「区域模式」= 1（左右分开）
IMPOSITION_AREA = 1


class ImpositionBaseMixin:
    """拼版共享基元：节点可见性、文档读写、取图切换、详情进出。

    依赖宿主页面提供：store/task_id、control_stack、step_bar、
    _select_stage()、_set_stage_status()、_toast()、log_view。
    """

    # ------------------------------------------------------------- area 读取
    def _rembg_area_value(self) -> int:
        """当前**已知**的 area（区域模式）：有依据才给值，没依据返回 0。

        优先级与 ``HistoryMixin._restore_stage_params`` 一致：第三步面板
        当前值 > 暂存（drafts/rembg.json）> 最近一次执行参数；**不再退到
        内置默认**（用户 2026-09-30：「图片去底色都没有生效，拼版节点更
        不可能生效，不显示」——全新任务靠默认 area=1 冒出拼版节点就是
        旧判据的毛病）。需要默认值兜底的调用方自己补 ``REMBG_DEFAULTS``。
        ⚠️ 面板未构造时只读盘上数据，绝不能走 LazyPanelHost 的属性转发
        ——那会把面板整个建出来，"谁进去谁才建"就白做了。
        """
        host = self.control_stack.widget(2)
        peek = getattr(host, "peek", None)
        panel = peek() if callable(peek) else None
        if panel is not None:
            try:
                value = panel.area.currentData()
                if isinstance(value, int) and value > 0:
                    return value
            except Exception:  # noqa: BLE001 - 面板半构造时不该拖垮流程条
                pass
        if self.task_id:
            draft = self.store.load_draft(self.task_id, "rembg") or {}
            value = self._as_area(draft.get("area"))
            if value:
                return value
            history = self.store.list_stage_runs(self.task_id, "rembg")
            if history:
                value = self._as_area(
                    (history[0].get("parameters") or {}).get("area")
                )
                if value:
                    return value
        return 0

    @staticmethod
    def _as_area(value) -> int:
        """任意来源的 area 值 → 合法整数（非法返回 0，由调用方跳过）。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------- 节点刷新
    def _imposition_node_visible(self) -> bool:
        """拼版节点当前是否**在流程里**（判据唯一处：已知 area == 1）。

        「已知」= 第三步面板当前值 / 草稿 / 最近执行参数三者之一——没有
        任何依据（全新任务、去底色从没配置或执行过）就不显示，绝不凭内置
        默认 area=1 冒出来（用户 2026-09-30）。
        宿主判"记录的步骤 key 还能不能匹配"（``page.py::_stage_index_of``）
        也走这里——两处必须同源，否则流程条上没这个节点、详情却能被切进去。
        """
        return self._rembg_area_value() == IMPOSITION_AREA

    def _sync_imposition_step_bar(self) -> None:
        """把拼版节点三态（可见/已选择/生效）一次性同步到流程条。

        「生效」= ``imposition_active()``（**已启用**即可，不要求已拼页）：
        生效时拼版两侧的连接线常规点亮、徽标转绿色对勾；未生效时是灰色虚线、
        「去底色 → 生成 PDF」走节点上方的绕行线——与第四步真实取图来源
        （``print_source_dir``）保持一致，两处看同一个判据。
        """
        self.step_bar.set_imposition_visible(self._imposition_node_visible())
        self.step_bar.set_imposition_selected(self._load_imposition_enabled())
        self.step_bar.set_imposition_active(self.imposition_active())

    def _refresh_imposition_node(self) -> None:
        """按当前 area 决定拼版节点是否出现在流程条，并回填选择/生效状态。

        触发时机：切任务（经 ``_select_stage``）、切阶段（经 ``_select_stage``）、
        第三步面板参数变化（``_wire_rembg_panel`` 的去抖刷新）。area 离开 1
        时节点消失；若用户正停在拼版详情上，退回第三步。
        """
        visible = self._imposition_node_visible()
        self._sync_imposition_step_bar()
        if not visible and self.step_bar._current == IMPOSITION_INDEX:
            self._select_stage(2)

    # ------------------------------------------------------------- 文档读写
    def _imposition_doc(self) -> dict:
        """当前任务的拼版文档（含选择态与逐页版面）。"""
        if not self.task_id:
            return {"enabled": False, "pages": []}
        return self.store.load_imposition_doc(self.task_id)

    def _imposition_pages(self, doc: dict | None = None) -> list[dict]:
        return list((doc or self._imposition_doc()).get("pages") or [])

    def _save_imposition_pages(self, pages: list[dict]) -> None:
        """把拼版页清单落盘（保持选择态不变）并刷新视图 + 重新合成。

        页数 0↔n 会翻转「生效」状态（流程条连线/绕行线跟着变），一并同步。
        """
        if not self.task_id:
            return
        doc = self.store.load_imposition_doc(self.task_id)
        doc["pages"] = [dict(page) for page in pages]
        self.store.save_imposition_doc(self.task_id, doc)
        self._sync_imposition_step_bar()
        self._refresh_imposition_view()
        self._schedule_imposition_compose()

    def _set_imposition_checked(self, on: bool) -> None:
        """程序化同步启用开关（blockSignals 避免回抛覆盖落盘值）。"""
        checkbox = getattr(self, "imposition_enabled_checkbox", None)
        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(on))
            checkbox.blockSignals(False)
        self._save_imposition_enabled(bool(on))
        self._sync_imposition_step_bar()
        if on:
            self._schedule_imposition_compose()
        self._refresh_print_source()
        self._update_imposition_status(
            getattr(getattr(self, "imposition_view", None), "current_index", lambda: -1)()
        )

    # ------------------------------------------------------------- 源图与生效
    def imposition_source_files(self) -> list[Path]:
        """可挑选的源图：第三步「提交本次任务」的成品图（stages/rembg）。"""
        if not self.task_id:
            return []
        files = list_stage_images(self.store.rembg_output_dir(self.task_id))
        return sorted(files, key=lambda p: pdf_custom_sort_key(p.name))

    def imposition_active(self) -> bool:
        """拼版**是否已启用**（用户勾了「在流程中启用图片拼版」就是启用）。

        ⚠️ **只看勾没勾，不看有没有拼版页**（用户 2026-10-03 口径："如果启用了
        拼板，则最后一步生成 pdf 的数据来源就是拼板"）。早先这里额外要求
        "至少有一页"，于是勾了开关却还没拼页时——取图仍走去底色、流程条仍是
        灰虚线 + 绕行线，用户看到的就是"启用了却不生效"。「有没有拼版页」是
        另一件事（能不能真出东西），走 :meth:`imposition_has_pages`。

        本方法是"**流程走不走拼板**"的唯一判据：第四步取图来源
        (:meth:`print_source_dir`) 与流程条生效态
        (:meth:`_sync_imposition_step_bar`) 都只看它。
        """
        if not getattr(self, "task_id", None):
            return False
        return bool(self._imposition_doc().get("enabled"))

    def imposition_has_pages(self) -> bool:
        """拼版文档里**至少有一页**版面（能不能真的合成出图）。

        与 :meth:`imposition_active` 分开：启用是**用户意图**（决定取图来源），
        有页是**当前进度**（决定要不要提示"还没拼版，生成 PDF 没有输入"）。
        """
        if not getattr(self, "task_id", None):
            return False
        return bool(self._imposition_doc().get("pages"))

    def print_source_dir(self) -> Path:
        """第四步的取图目录：拼版生效 → stages/imposition，否则 stages/rembg。

        ⚠️ 走的是 :mod:`desktop.steps.ports` 的**条件连线**（"print 的 pages
        端口由谁供给"），不是在这里 if/else 挑目录——BPM 换上游时只改连线表，
        这一行不用动。
        """
        source = self.store.stage_input(
            self.task_id, "print", "pages",
            imposition_active=self.imposition_active(),
        )
        # 连线表永远给得出路径（rembg_submit 是 print 的静态上游），
        # 但仍留一道兜底：将来若有人把静态上游摘掉，这里不该抛 AttributeError。
        return source or self.store.rembg_output_dir(self.task_id)

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

        拼版没有可执行的子任务：执行/提交/继续/中断按钮整组隐藏，
        执行记录与检测统计也不适用。
        """
        self._refresh_imposition_view()
        view = getattr(self, "imposition_view", None)
        if view is not None and view.current_index() < 0 and view.pages():
            view.set_current(0)
        self.control_stack.setCurrentIndex(IMPOSITION_INDEX)
        self.preview_stack.setCurrentIndex(IMPOSITION_INDEX)
        # ⚠️ 藏**整行**（action_row =「生成预览 + 提交本次任务」并排），不是
        #    单个按钮：只藏按钮的话行高仍在，控制区底部会留一条空白。
        self.action_row.setVisible(False)
        self.followup_row.setVisible(False)
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
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )

    def _reset_imposition_state(self) -> None:
        """切任务：取消在飞合成、清忙标记，并把新任务的拼版文档灌进视图。"""
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            timer.stop()
        edit_timer = getattr(self, "_imposition_edit_timer", None)
        if edit_timer is not None:
            edit_timer.stop()  # 上一任务的旋转组件停顿提交别再落进新任务
        # 预览弹窗里那页是上个任务打开时的快照，留着就是旧任务的图
        self.close_imposition_zoom_popup()
        self._imposition_dirty = False
        self._imposition_composing = False
        # 已渲好的源图缩略图按**路径**缓存，跨任务留着没有意义（还有旧图
        # 占内存）；左列重灌时自然按新任务的路径重新渲。
        self._imposition_source_thumbs = {}
        # 新任务的取图来源未必和上个任务一样：让 _refresh_print_source 重新判定
        self._print_source_cache = None
        self._refresh_imposition_view()
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(0 if view.pages() else -1)
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )

    def _refresh_print_source(self) -> None:
        """第四步取图来源变了：让待打印列表跟上（拼版 ↔ 去底色 切换时用）。

        ⚠️ **只作废缓存，不在原地重建**（2026-09-30 用户报「开关拼版后顶部
        空白/卡住 2s 才恢复」）：重建 = 缩略条清空 + 几十条重建 +
        ``_select_entry(0)`` **在 UI 线程同步解码整张首图**——真实任务上
        冻结 1-2s，流程条的新状态（虚线/绕行线）也跟着画不出来。而本方法的
        触发点（启用开关、后台合成完成、自动启用）都发生在**拼版详情里**，
        那一刻第四步根本不可见：进第四步时 ``_refresh_preview`` 本来就会
        重建一次，不怕漏。只有第四步**正被看着**（比如开关后停在第四步等
        后台合成收尾）才当场重建，否则用户会一直盯着旧来源。

        另做两件**不重**的事（它们只动按钮/提示，不碰列表）：
        1. 重算"取图来源已换"缓存（``_print_source_stale``）——本方法是拼版开关
           变化的统一出口，缓存必须在这儿跟上，否则状态行还按旧来源显示提示；
        2. 同步下载按钮：来源一换，磁盘上那份 PDF 就是旧数据，得灭掉
           （用户 2026-10-03："旧的数据不显示"）。
        """
        # 缓存与按钮先无条件跟上（都很轻，不碰列表）
        try:
            self._refresh_stale_notices()
        except Exception:  # noqa: BLE001 - 判定失败不该拦住开关生效
            pass
        preview = getattr(self, "print_preview", None)
        if preview is None or not self.task_id:
            return
        try:
            preview.set_pdf_path(self._current_print_pdf_path())
        except Exception:  # noqa: BLE001 - 第四步尚未就绪时不该拖垮拼版页
            pass
        source = str(self.print_source_dir())
        if getattr(self, "_print_source_cache", None) == source:
            return
        if self.preview_stack.currentIndex() != STAGES.index("print"):
            self._print_source_cache = None
            # 第四步不可见：状态行/主按钮高亮留给进第四步时的那次刷新
            return
        self._print_source_cache = source
        try:
            entries, _doc = self._print_entries()
            preview.set_entries(entries)
            self._refresh_stage_views()
        except Exception:  # noqa: BLE001 - 第四步尚未就绪时不该拖垮拼版页
            self._print_source_cache = None
            return


class ImpositionMixin(ImpositionPagesMixin, ImpositionLayoutMixin,
                      ImpositionBaseMixin):
    """「图片拼版」节点控制器 = 模块一（页管理） + 模块二（版面/合成） + 基元。

    方法查找顺序：模块一 → 模块二 → 共享基元；三个文件互不 import，
    只经 ``self`` 在组合后的宿主页面上协作。
    """


__all__ = ["ImpositionMixin", "ImpositionBaseMixin"]
