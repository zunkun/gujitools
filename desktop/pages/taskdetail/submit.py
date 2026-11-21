# -*- coding: utf-8 -*-
"""任务详情页的「提交本次任务」控制器（第二步「检测文本框」专用）。

2026-10-22 口径（用户）：

> 检测文本框……增加「提交本次任务」，图片按照检测框切割处理。提交任务，本步骤
> 才算是执行完毕，才能转入下一阶段。
>
> 去底色步骤……「生成预览」改成「执行去底色」，直接去底色到 rembg，
> 不再需要预览了。

于是「两个动作」的步骤只剩**一个**：

==========================  ==========================  ==========================
步骤                         第一个动作（主按钮）          第二个动作（提交）
==========================  ==========================  ==========================
检测文本框                    「检测文本框」：只出框        「提交本次任务」：逐框裁图 → stages/detect
==========================  ==========================  ==========================

⚠️ 2026-11-16 起第二步有两种**识别方式**（「自动识别 / 人工标注」，见
``components/panels/detect_panel.py``）：人工标注**不调 YOLO**，框全靠用户画，
所以「检测」那次运行可能压根不存在——提交的门槛与版本判定都按方式分岔
（人工标注只比"提交之后有没有动过框"），并且提交前会先查一遍有没有漏标注的页
（用户 2026-11-16 第 4 条）。

去底色**只有一个动作**（「执行去底色」直接落 ``stages/rembg``），不再有提交
按钮/版本状态机，也没有预览目录。本模块负责：
- ``run_submit``              ：提交按钮入口（当前固定分发到检测提交）；
- ``run_detect_submit``       ：检测框 → 逐框裁图；
- ``_update_submit_button``   ：按钮状态/提示。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.pages.taskdetail.runner import STATUS_LABELS
from desktop.services.print_plan import (
    entry_to_effect_spec,
    plan_detect_submit_entries,
)
from desktop.services.submit_state import (
    NEW_VERSION, NO_PREVIEW, PREVIEW_STALE, UP_TO_DATE,
    submit_version_state,
)
from desktop.ui.widgets import bold_button, set_red_frame
from utils.book_layout import profile_book

if TYPE_CHECKING:
    from desktop.store.store import TaskStore

#: 提交按钮的**唯一**文案（构造处与状态刷新处共用一份，避免两处各写一遍）。
#: ⚠️ 别再加「（有新版本）」后缀：它与主按钮并排后放不下（见
#:    ``_update_detect_submit_button`` 的说明），"待提交"由加粗 + 红字提示表达。
#: 用户 2026-11-17：「提交本次任务」→「分割图片」（按钮直接说出这一下干什么）。
SUBMIT_TEXT = "分割图片"

#: 「还有页面没有标注」弹窗里最多列出多少个页码（再多就折成"等 N 页"）
MISSING_LABEL_PREVIEW = 12


def missing_labels_message(labels) -> str:
    """漏标注提示的**正文**（纯函数：页数/页码怎么折都在这里，便于自测钉住）。

    ``labels`` 是页码展示文案（``"7"`` / ``"12"``）而不是文件名——
    用户看的是页码，不是 ``0007.png``。
    """
    shown = [str(item) for item in list(labels)[:MISSING_LABEL_PREVIEW]]
    total = len(list(labels))
    pages = "、".join(shown)
    if total > len(shown):
        pages += f" 等 {total} 页"
    return (
        f"有 {total} 页还没有标注文本框：{pages}。\n\n"
        "这些页面提交后没有可裁的文本框（下游会缺这几页）。\n"
        "「继续标注」回去把框画完；「执行任务」按现在的标注直接裁图。"
    )


def confirm_missing_labels(parent, labels) -> bool:
    """「还有页面没有标注」的二次确认 → ``True`` 表示**执行任务**。

    ⚠️ 必须用真窗口底座的 ``ConfirmDialog``（``desktop/ui/confirm_dialog.py``）：
    qfluent 的 ``MessageBox`` 是主窗口里的**子控件遮罩层**，点按钮会"当当"响
    且可能根本不生效（用户 2026-10-26 报过两次）。
    ⚠️ 延迟导入：本模块在纯逻辑自测里也要能导入，不想连带 Qt 控件一起拉起来。
    """
    from desktop.ui.confirm_dialog import ConfirmDialog

    dialog = ConfirmDialog(
        "还有页面没有标注",
        missing_labels_message(labels),
        parent,
        yes_text="执行任务",
        cancel_text="继续标注",
    )
    return bool(dialog.exec())


class SubmitMixin:
    """依赖宿主页面提供的属性：store/task_id/source_path、process、
    control_stack、submit_button/submit_hint、log_view、_toast()。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法：Mixin 本体不持有，
        # 这里只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        running_stage: str | None
        log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
        submit_button: Any  # 「提交本次任务」按钮（第二步）
        submit_hint: Any  # 提交区文案标签
        _toast: Callable[..., None]
        current_stage: Callable[[], str]
        current_node: Callable[[], str | None]
        node_of_stage: Callable[[str], str | None]
        _node_stage_state: Callable[[str], dict]
        _node_scope: Callable[..., dict]
        # ⚠️ 返回值是 LazyPanelHost 或真面板（属性转发、鸭子类型），用 Any 承接
        panel_host_of_step: Callable[[str], Any]
        _acquire_run: Callable[..., bool]
        _release_run: Callable[[], None]
        _launch_stage_process: Callable[..., Any]
        _stage_inputs_ready: Callable[..., Any]
        _missing_input_kind: Callable[..., Any]
        _manifest_paths: Callable[[], list]
        _refresh_manifest: Callable[..., None]
        _detect_boxes_map: Callable[[], dict]
        _boxes_map_all: Callable[[], dict]
        _boxes_write_path: Callable[[], Any]
        _page_width_of: Callable[..., int]

    #: 第二步「识别文本框」：检测结果只取决于图片与模型（识别方式、沿用上一页
    #: 都不影响已经落盘的框），所以没有任何参数要进 preview 键。
    DETECT_PREVIEW_PARAM_KEYS = ()
    #: 影响提交产物的参数：**现在一个都没有**——裁图几何完全由 ``boxes.json``
    #: 决定，而"提交后又改过框"由 :meth:`_boxes_edited_after_submit` 的 mtime
    #: 判定（比参数比对更准）。保留这个常量是给以后真有"影响裁图"的开关用。
    DETECT_SUBMIT_PARAM_KEYS: tuple = ()

    # ---------------------------------------------------------- 状态判定
    def _latest_success_run(self, stage: str) -> dict | None:
        """**当前节点**最近一次成功的该阶段运行（B 方案：按节点取）。

        同一步骤的多个节点各跑各的：「提交本次任务」的版本判定（检测 vs 提交）
        必须拿**同一个节点**的两次运行比，否则 A 节点的检测会去和 B 节点的提交
        比时间戳（结果是"版本永远是新/永远是旧"这类看不懂的状态）。
        """
        if not self.task_id:
            return None
        node = self.current_node()
        records = (
            self.store.list_node_runs(self.task_id, node, stage)
            if node
            else self.store.list_stage_runs(self.task_id, stage)
        )
        for record in records:
            if record.get("status") == "success":
                return record
        return None

    def _submit_version_state(self, stage: str) -> str:
        """第二步「提交」按钮的版本状态（``stage`` 只接受 ``"detect"``）。"""
        if stage != "detect":
            # 去底色已无提交动作（2026-10-22）；旧调用方拿到"无需提交"。
            return UP_TO_DATE
        # panel 可能还没构造（不在第二步时）：用 peek 看一眼，绝不触发构造。
        panel = self.panel_host_of_step("detect")
        peek = getattr(panel, "peek", None)
        panel_obj: Any = peek() if callable(peek) else panel
        panel_args: dict = {}
        if panel_obj is not None:
            try:
                panel_args = dict(panel_obj.get_args())
            except ValueError:
                panel_args = {}
        if self._is_manual_detect(panel_args):
            # 人工标注：没有「检测」那次运行可比（压根不调 YOLO）⇒ 只判
            # "提交之后有没有动过框"。用检测/提交两个 run 去比会把按钮永远
            # 钉在 NO_PREVIEW 上（用户点不动提交）。
            if self._latest_success_run("detect_submit") is None:
                return NEW_VERSION
            return NEW_VERSION if self._boxes_edited_after_submit() else UP_TO_DATE
        state = submit_version_state(
            preview_run=self._latest_success_run("detect"),
            submit_run=self._latest_success_run("detect_submit"),
            panel_args=panel_args,
            preview_param_keys=self.DETECT_PREVIEW_PARAM_KEYS,
            # 面板尚未构造时不比参数（否则空面板会让旧任务误报"有新版本"）。
            submit_param_keys=(
                self.DETECT_SUBMIT_PARAM_KEYS if panel_obj is not None else ()
            ),
        )
        if state == UP_TO_DATE and self._boxes_edited_after_submit():
            # 检测框被改过：提交产物仍是改框前那份，必须重新提交。
            return NEW_VERSION
        return state

    def _boxes_edited_after_submit(self) -> bool:
        """``boxes.json`` 是否比最近一次成功提交还新（＝提交后改过框）。

        改框（拖动/切类型/删除/单页重检）都会写这个文件，所以拿它的 mtime 和
        提交完成时刻比就够了——不需要另记一份"改过没"的状态。
        """
        if not self.task_id:
            return False
        submit_run = self._latest_success_run("detect_submit")
        if not submit_run:
            return False
        try:
            submit_at = float(submit_run.get("finished_at") or 0.0)
        except (TypeError, ValueError):
            return False
        if submit_at <= 0:
            return False
        path = self._boxes_write_path()
        if path is None:
            return False
        try:
            return Path(path).stat().st_mtime > submit_at
        except OSError:  # 文件还没落盘/被删：不算编辑
            return False

    # ---------------------------------------------------------- 派生条目
    def _book_page_sizes(self) -> dict:
        """整本书每页的原始像素尺寸：``{页名: (宽, 高)}``。

        **一次读盘**（``store.image_sizes_all``）；缺记录的页回落读图片头
        （由 ``_page_width_of`` 负责，只能拿到宽——高记 0）。

        ⚠️ 2026-11-16 起提交**不再补框**（占位图那张"按页高从中间截取"的规则
        已删），这里保留完整尺寸只是本方法的历史形状：宽度是单宽框/窄页归一化
        的必需输入（见 :meth:`_book_page_widths`），高度目前没有消费方。
        """
        sizes: dict = {}
        if self.task_id:
            getter = getattr(self.store, "image_sizes_all", None)
            if getter is not None:
                try:
                    sizes = getter(
                        self.task_id,
                        **self._node_scope(self.node_of_stage("detect")),
                    )
                except Exception:  # noqa: BLE001 - 读不到就全部回落图片头
                    sizes = {}
        result: dict = {}
        for path in self._manifest_paths():
            size = sizes.get(path.stem)
            if size and len(size) >= 2 and size[0] > 0 and size[1] > 0:
                result[path.stem] = (int(size[0]), int(size[1]))
                continue
            try:
                width = self._page_width_of(path, sizes)
            except Exception:  # noqa: BLE001 - 取不到宽度按"无页宽"处理
                width = 0
            result[path.stem] = (int(width), 0)
        return result

    def _book_page_widths(self) -> dict:
        """整本书每页的原始像素宽度：``{页名: 宽}``。

        ⚠️ **一次读盘算完整本**（``store.image_sizes_all``）：判定要遍历全部页面，
        逐页调 ``image_size`` 会整份读 sizes.json，320 页就是 320 次全量解析。
        缺记录的页回落读图片头（由 ``_page_width_of`` 负责）。
        """
        return {
            stem: int(size[0]) for stem, size in self._book_page_sizes().items()
        }

    def _book_profile(self, widths: dict | None = None, boxes_for=None):
        """整本书的形态判定（``utils.book_layout.BookProfile``）。

        规则本体在 :mod:`utils.book_layout`；这里只负责**取数**：清单 × 每页
        槽位（与 :meth:`DetectMixin._refresh_detect_stats` 同一口径）＋页宽。
        """
        if widths is None:
            widths = self._book_page_widths()
        provider = boxes_for
        if provider is None:
            mapping = self._boxes_map_all()
            provider = lambda text: mapping.get(Path(text).stem, []) or []  # noqa: E731
        pages = [
            (path.stem, provider(str(path)), widths.get(path.stem, 0))
            for path in self._manifest_paths()
        ]
        return profile_book(pages)

    def _submit_entries(self) -> list[dict]:
        """第二步的提交条目：源页按文本框逐框裁图。

        全书级判定（单栏书 / 页宽 / 指定左右）与框都**一次读盘**：
        ``plan_detect_submit_entries`` 会遍历整本 manifest 逐页回调，逐页走
        ``_detect_boxes_for`` 就是 O(n²)。

        框从哪来（YOLO 检测 / 用户手画）对这一步没有区别：两者在
        ``boxes.json`` 里同构，都是槽位。

        ⚠️ 派生结果里**不会**有"补出来的框"（用户 2026-11-16）：一个框都没有
        的页直接没有条目（＝这一步不出那张图），漏检一侧的页只裁画出来的那一侧。
        """
        widths = self._book_page_widths()
        profile = self._book_profile(widths)
        sides = self._side_overrides_all()
        boxes_map = self._boxes_map_all()
        boxes_for = lambda text: boxes_map.get(Path(text).stem, []) or []  # noqa: E731
        return plan_detect_submit_entries(
            manifest_paths=self._manifest_paths(),
            boxes_for=boxes_for,
            single_column_book=profile.single_column_book,
            page_width_for=lambda text: widths.get(Path(text).stem, 0),
            side_for=lambda text: sides.get(Path(text).stem),
            book_profile=profile,
        )

    def _save_submit_plan(self, entries: list[dict]) -> None:
        """把本次提交的**产物角色**写进 boxes.json（拼版配对用，2026-10-23）。

        条目是**按产物**的（一页可能拆成 ``-r``/``-l`` 两张，也可能只是一张
        无后缀图），这里按源页聚合成 ``plan.outputs``；``page_class`` 记的是
        归一化**之前**的检测形态。拼版读它来认"_无后缀但其实是半幅_"的图。

        ⚠️ 计划只是拼版配对的**参考快照**：写不进去（老任务/磁盘异常）不该
        阻断提交，拼版会回落到文件名后缀规则（旧行为）。
        """
        saver = getattr(self.store, "save_detect_plans", None)
        if not callable(saver) or not self.task_id:
            return
        plans: dict[str, dict] = {}
        for entry in entries or []:
            stem = Path(str(entry.get("file") or "")).stem
            if not stem:
                continue
            plan = plans.setdefault(
                stem,
                {"page_class": entry.get("page_class") or "empty",
                 "outputs": []},
            )
            # ⚠️ 2026-11-16 起没有占位条目了（不再补框），所以这里只记
            #    产物名与角色。老任务那份计划里可能还带 ``placeholder``，
            #    读侧（``rembg_groups``）保留容错、照旧认它。
            plan["outputs"].append({
                "label": entry.get("label") or stem,
                "role": entry.get("role") or "full",
            })
        try:
            saver(self.task_id, plans, self.current_node())
        except Exception:  # noqa: BLE001 - 计划写失败不阻断提交（见 docstring）
            pass

    def _side_overrides_all(self) -> dict:
        """整份 boxes.json 里的 ``{页名: 指定左右}``（一次读盘）。

        ⚠️ 别逐页调 ``box_side_at``——那个每次都整份读盘，320 页就是 320 次
        全量解析（与 ``image_sizes_all`` 同一个理由）。
        """
        getter: Any = getattr(self.store, "box_sides_all_at", None)
        if not callable(getter):
            return {}
        try:
            result: Any = getter(self._boxes_write_path())
            return result if isinstance(result, dict) else {}
        except Exception:  # noqa: BLE001 - 读不到＝没有任何指定
            return {}

    def _side_override_for(self, path_text: str) -> str | None:
        """某页的**用户指定左右**（单页查询；批量场景用 :meth:`_side_overrides_all`）。"""
        getter: Any = getattr(self.store, "box_side_at", None)
        if not callable(getter) or not self.task_id:
            return None
        try:
            result: Any = getter(
                self._boxes_write_path(), Path(path_text).stem
            )
            return result if isinstance(result, str) else None
        except Exception:  # noqa: BLE001 - 读不到按"没指定"
            return None

    def _build_print_effects(self, list_entries: list[dict]) -> list[dict]:
        """第四步的取图规格：**原样透传上游成品图**。

        裁图/透明底都已在前面的步骤兑现（检测提交裁图、去底色落透明底），
        ``effect=None`` 表示"这份文件的全部像素就是要排版的内容"。
        """
        return [
            {"file": str(Path(e["file"])), "effect": None}
            for e in list_entries
            if Path(e["file"]).exists()
        ]

    # ---------------------------------------------------------- 提交动作
    def run_submit(self) -> None:
        """「提交本次任务」按钮入口：当前只有第二步有提交动作。"""
        if self.current_stage() != "detect":
            return
        self.run_detect_submit()

    def run_detect_submit(self) -> None:
        """第二步提交：把文本框逐框裁成下一步要的图 → ``stages/detect``。

        自动识别：前提是最近一次「检测文本框」成功（没检测就没框可裁）。
        人工标注：没有那次运行，框是用户自己画的 ⇒ 只要求页面清单非空，
        且提交前先查一遍**有没有漏标注的页**（用户 2026-11-16 第 4 条）。
        """
        if not self._acquire_run("步骤"):
            return
        try:
            self._run_detect_submit_unchecked()
        finally:
            if self.running_stage is None:
                self._release_run()

    def _run_detect_submit_unchecked(self) -> None:
        """第二步提交的实现体（不含执行权守卫，勿直接调用）。"""
        if not self.task_id or not self._stage_inputs_ready():
            kind = self._missing_input_kind()
            if kind == "images":
                self._toast(
                    "warning", "这一步需要图片",
                    "本流程第一步不吃 PDF，请点页头的图片按钮选择图片，"
                    "或把图片放进任务目录下的 stages/input。",
                )
            elif kind == "pdf":
                self._toast(
                    "warning", "尚未选择源文件",
                    "点页头的「选择源文件」按钮为本任务补上 PDF/DjVu，之后才能执行。",
                )
            else:
                self._toast(
                    "warning", "这一步的输入还没就位",
                    "这一步的输入由流程上游提供：先把它的上游步骤执行完，"
                    "或到「查看 / 编辑流程」里检查连线。",
                )
            return
        panel = self.panel_host_of_step("detect")
        if panel is None:
            self._toast(
                "warning", "这一步不在流程里",
                "当前任务的流程图里没有「检测文本框」，请先在「查看 / 编辑流程」"
                "里把它加回来。",
            )
            return
        try:
            panel_args = panel.get_args()
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        manual = self._is_manual_detect(panel_args)
        if not manual:
            # 自动识别：没有成功的检测就没有框可裁（人工标注跳过这条：
            # 框是用户自己画的，可能压根没跑过检测）
            detect_state = self._node_stage_state("detect")["status"]
            if detect_state != "success":
                self._toast(
                    "warning", "请先检测文本框",
                    "「检测文本框」执行成功后才能分割图片"
                    + ("" if detect_state == "pending" else
                       f"（当前状态：{STATUS_LABELS.get(detect_state, detect_state)}）"),
                )
                return
        self._refresh_manifest()
        if not self._manifest_paths():
            self._toast(
                "warning", "无输入页面",
                "页面清单为空，请先完成上一步，或在预览区插入图片。",
            )
            return
        if manual and not self._confirm_missing_labels():
            return
        # 检测框决定几何：每个框各裁一张图（2026-10-22 起没有 area）。
        # border 沿用历史默认 "0"（不加留白：第四步会在纸上重新排版）。
        entries = self._submit_entries()
        if not entries:
            # 两种可能：①页面清单里没有能读的图；②有图但**一个框都没标注**
            # （2026-11-16 起不补框，没框＝不出图）。人工标注时后者更常见，
            # 提示要说得出来，否则用户会以为程序坏了。
            self._toast(
                "warning", "没有可裁剪的文本框",
                "页面清单里没有能读取的图片，请检查上一步的产物；"
                "如果图片都在，那就是**还没有任何页面画了框**——"
                "请先在预览里标注，再提交。",
            )
            return
        out_args = {
            "_effects": [entry_to_effect_spec(e, "0") for e in entries],
            "output": str(
                self.store.node_or_stage_output(
                    self.task_id, self.current_node(), "detect_submit"
                )
            ),
            "clean": True,
            # 记进运行参数：审计时能看出这次提交是哪种识别方式送的
            # （不影响产物几何，裁图只认 boxes.json）。
            "mode": "manual" if manual else "auto",
        }
        # 产物角色落进 boxes.json：拼版据此把"无后缀但其实是半幅"的图配对。
        self._save_submit_plan(entries)
        detect_run = self._latest_success_run("detect")
        if detect_run:
            out_args["_preview_run_id"] = detect_run.get("run_id")
        pages = len({Path(str(e.get("file") or "")).stem for e in entries})
        total = len(self._manifest_paths())
        self.log_view.append(
            f"分割图片：按{'人工标注' if manual else '检测框'}裁图"
            f" {len(entries)} 张（{pages}/{total} 页有框，没框的页不出图）"
            f" → {out_args['output']}"
        )
        self._launch_stage_process("detect_submit", out_args, resume=False)

    # ---------------------------------------------------- 识别方式 / 漏标注检查
    @staticmethod
    def _is_manual_detect(panel_args: dict) -> bool:
        """这次提交是不是「人工标注」方式送的（未知按键按自动识别处理）。"""
        return str((panel_args or {}).get("mode") or "auto") == "manual"

    def _confirm_missing_labels(self) -> bool:
        """人工标注提交前查漏：有页没画框就弹二次确认，返回是否**真去执行**。

        用户 2026-11-16 第 4 条：点「提交本次任务」时检查哪些页面没有标注，
        提醒用户；弹窗两个按钮都对——「继续标注」什么也不做（回来接着画），
        「执行任务」才真的裁图。

        没有漏标注的页 ⇒ 直接放行（不弹窗）。返回 False 时调用方**什么都不做**。
        """
        finder = getattr(self, "_unlabeled_pages", None)
        if not callable(finder):
            return True
        pages = list(finder() or [])
        if not pages:
            return True
        labels = [self._page_label_of(path) for path in pages]
        self.log_view.append(
            f"提交前检查：有 {len(pages)} 页没有标注（{'、'.join(labels[:20])}）"
        )
        return bool(confirm_missing_labels(self.window(), labels))

    def _page_label_of(self, path) -> str:
        """页码展示文案（去前导零）：与统计面板同一个口径，取不到就原样。"""
        labeler = getattr(self, "_page_label", None)
        if callable(labeler):
            try:
                return str(labeler(Path(path)))
            except Exception:  # noqa: BLE001 - 取不到就退回页名
                pass
        return Path(path).stem

    # ---------------------------------------------------------- 按钮状态
    def _update_submit_button(self, running: bool) -> None:
        """「提交本次任务」按钮：只在第二步显示，其余步骤隐藏。

        ⚠️ 顺带同步主按钮（「检测文本框」）的显隐：人工标注方式下它不显示。
        放在这里是因为本方法在**每次切步骤/执行权变化**时都会被调一次
        （``_update_run_buttons`` → 本方法），是最全的刷新点；离开第二步时
        也正好由它把主按钮还原回来。
        """
        sync = getattr(self, "_sync_detect_mode_ui", None)
        if callable(sync):
            sync()
        if not self.task_id or self.current_stage() != "detect":
            self.submit_hint.hide()
            # 离开第二步（或没任务）时把红框一起收掉，别圈到别的步骤去
            set_red_frame(self.submit_button, False)
            return
        self._update_detect_submit_button(running)

    def _update_detect_submit_button(self, running: bool) -> None:
        """第二步「提交本次任务」的可用性与提示。

        门槛按**识别方式**分岔（用户 2026-11-16）：

        - 自动识别：最近一次「检测文本框」成功后才可用；
        - 人工标注：**不看那次运行**（压根不调 YOLO），有页面就能提交——
          漏画的页在点下去时再查（``_confirm_missing_labels``）。
        """
        panel = self.panel_host_of_step("detect")
        peek = getattr(panel, "peek", None)
        panel_obj: Any = peek() if callable(peek) else panel
        panel_args: dict = {}
        if panel_obj is not None:
            try:
                panel_args = dict(panel_obj.get_args())
            except ValueError:
                panel_args = {}
        manual = self._is_manual_detect(panel_args)
        preview_state = self._node_stage_state("detect")["status"]
        if running:
            version, tip = NO_PREVIEW, "当前有任务正在执行，请等待完成后再提交"
        elif not self._manifest_paths():
            version, tip = NO_PREVIEW, "没有可提交的页面，请先放入图片"
        elif not manual and preview_state != "success":
            version = NO_PREVIEW
            tip = (
                f"上次「检测文本框」{STATUS_LABELS.get(preview_state, preview_state)}，"
                "请重新执行并成功后再分割图片"
                if preview_state in ("failed", "cancelled")
                else "请先点击「检测文本框」，执行成功后才能分割图片"
            )
        else:
            version = self._submit_version_state("detect")
            tip = {
                NEW_VERSION: (
                    "检测框有改动（或还没提交过），请点击「分割图片」"
                    "把文本框内容裁出来交给下一步"
                    if not manual else
                    "标注有改动（或还没提交过），请点击「分割图片」"
                    "把文本框内容裁出来交给下一步（没画框的页会先提示）"
                ),
                PREVIEW_STALE: "检测结果已过期，请先重新「检测文本框」再提交",
                UP_TO_DATE: "已提交：下一步（图片去底色）拿到的是这次裁好的图；"
                            "改框后需再次提交",
                NO_PREVIEW: "请先点击「检测文本框」，执行成功后才能分割图片",
            }[version]
        self._apply_submit_state(version, tip, {
            NEW_VERSION: (
                "● 有新版本待提交（标注有改动，或还没提交）" if manual
                else "● 有新版本待提交（检测框有改动，或还没提交）"
            ),
            PREVIEW_STALE: "● 检测结果已过期，请重新「检测文本框」后再提交",
            UP_TO_DATE: "已提交：下一步已能用这次裁好的图",
        })

    def _apply_submit_state(self, version, tip: str, hints: dict) -> None:
        """把版本状态落到按钮（文案/禁用/红框/加粗/提示行）。

        ⚠️ 文案**始终**是「提交本次任务」：它与主按钮并排一行后，每颗按钮
        只剩控制列（340~440px）的一半，实测 166~216px，而更长的写法必被
        qfluent 截成省略号。"有新版本待提交"这层含义由**加粗** + 下方常驻的
        红字提示承担。
        """
        self.submit_button.setToolTip(tip)
        self.submit_button.setEnabled(version not in (None, NO_PREVIEW))
        self.submit_button.setText(SUBMIT_TEXT)
        if version == NEW_VERSION:
            # 加粗走 setFont：setStyleSheet 会把 qfluent 按钮的整套 qss
            # （含 hasIcon=true 的 36px 左边距）整串抹掉（见 widgets.bold_button）
            bold_button(self.submit_button, True)
            self._show_submit_hint(hints[NEW_VERSION], "#c0392b")
        elif version == PREVIEW_STALE:
            bold_button(self.submit_button, False)
            self._show_submit_hint(hints[PREVIEW_STALE], "#b8860b")
        elif version == UP_TO_DATE:
            bold_button(self.submit_button, False)
            self._show_submit_hint(hints[UP_TO_DATE], "#3a8a3e")
        else:  # no_preview / 执行中
            bold_button(self.submit_button, False)
            self.submit_hint.hide()
        # ⚠️ 红框**最后**挂：提示行的显隐会改变执行按钮行的位置，先让上面这些
        #    状态落定再算框（否则第一帧会框在旧位置，用户 2026-10-23 报
        #    「切步骤节点返回后，提交按钮外的红框定位不准确」）。
        set_red_frame(self.submit_button, version == NEW_VERSION)

    def _show_submit_hint(self, text: str, color: str) -> None:
        self.submit_hint.setText(text)
        # ⚠️ **颜色没变就别重复 setStyleSheet**（2026-11-21「内存越用越大」）：
        #    qfluentwidgets 的 StyleSheetManager 每调一次就给控件挂一对 watcher
        #    （CustomStyleSheetWatcher / DirtyStyleSheetWatcher），同一个控件被
        #    反复设置，旧的 watcher 不会解绑——切步骤每次都走这里，实测每轮多
        #    出上百个 watcher，且永不回落。
        wanted = f"color:{color}; font-weight:bold;"
        if getattr(self, "_submit_hint_qss", None) != wanted:
            self._submit_hint_qss = wanted
            self.submit_hint.setStyleSheet(wanted)
        self.submit_hint.show()
