# -*- coding: utf-8 -*-
"""任务详情页的「提交本次任务」控制器（第二步、第三步共用）。

2026-10-22 口径（用户）：

> 检测文本框……增加「提交本次任务」，图片按照 area 切割处理。提交任务，本步骤
> 才算是执行完毕，才能转入下一阶段。
> 去底色步骤的 area 和 border 参数去除，去底色直接整个图片去底色。

于是「两个动作」的步骤变成了**两个**：

======================  ==========================  ==========================
步骤                     第一个动作（主按钮）          第二个动作（提交）
======================  ==========================  ==========================
检测文本框                「检测文本框」：只出框        「提交本次任务」：逐框裁图 → stages/detect
图片去底色                「生成预览」：整图去底色      白底转透明 → stages/rembg
======================  ==========================  ==========================

两边的按钮状态机是同一套（``services/submit_state``），只有"比哪些参数"
不同。本模块负责：
- ``run_submit``              ：按当前步骤分发到下面两个提交动作；
- ``run_detect_submit``       ：第二步提交（检测框 → 逐框裁图）；
- ``run_rembg_submit``        ：第三步提交（预览图 → 透明底成品）；
- ``_update_submit_button``   ：按钮状态/提示（也按步骤分发）。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.pages.taskdetail.runner import STATUS_LABELS
from desktop.services.print_plan import (
    entry_to_effect_spec,
    plan_detect_submit_entries,
    plan_rembg_submit_entries,
)
from desktop.services.submit_state import (
    NEW_VERSION, NO_PREVIEW, PREVIEW_STALE, UP_TO_DATE,
    submit_version_state,
)
from desktop.ui.widgets import bold_button, set_red_frame
from desktop.utils.files import list_stage_images
from utils.book_layout import profile_book

if TYPE_CHECKING:
    from desktop.store.store import TaskStore

#: 提交按钮的**唯一**文案（构造处与状态刷新处共用一份，避免两处各写一遍）。
#: ⚠️ 别再加「（有新版本）」后缀：它与主按钮并排后放不下（见
#:    ``_update_submit_button`` 的实测说明），"待提交"由加粗 + 红字提示表达。
SUBMIT_TEXT = "提交本次任务"

#: 有「提交本次任务」这一类次动作的步骤 → 它的"预览动作"叫什么（提示语用）。
PREVIEW_ACTION_LABEL = {
    "detect": "检测文本框",
    "rembg": "生成预览",
}


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
        submit_button: Any  # 「提交本次任务」按钮（第二步/第三步共用）
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
        _detect_boxes_for: Callable[..., Any]
        _detect_boxes_map: Callable[[], dict]
        _boxes_map_all: Callable[[], dict]
        _boxes_write_path: Callable[[], Any]
        _side_overrides_all: Callable[[], dict]
        _book_page_widths: Callable[..., dict]
        _book_profile: Callable[..., Any]
        _page_width_of: Callable[..., int]

    # 影响「生成预览」产物（去底预览图）的参数；变化后预览图即过期
    PREVIEW_PARAM_KEYS = (
        "type", "offset", "seal", "sealcolor", "sealarea", "sealmin_sat",
    )
    #: 第二步「检测文本框」：没有可调参数（area 已彻底移除，2026-10-22），
    #: 产物只取决于检测框本身。
    DETECT_PREVIEW_PARAM_KEYS = ()

    # ---------------------------------------------------------- 状态判定
    def _latest_success_run(self, stage: str) -> dict | None:
        """**当前节点**最近一次成功的该阶段运行（B 方案：按节点取）。

        同一步骤的多个节点各跑各的：「提交本次任务」的版本判定（预览 vs 提交）
        必须拿**同一个节点**的两次运行比，否则 A 节点的预览会去和 B 节点的提交
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
        """某步骤「提交」按钮的版本状态（第二/三步共用一套状态机）。"""
        step = "detect" if stage == "detect" else "rembg"
        host = self.panel_host_of_step(step)
        # ⚠️ 流程里没有这一格 ⇒ 没有可比对的表单参数，传空字典
        #    （别借别的面板，那是一份用户没填过的值）。
        panel_args = host.get_args() if host else {}
        if stage == "detect":
            # ⚠️ 第二步没有表单参数（area 已彻底移除）：只比运行版本 + 检测框
            #    是否在提交后被改过。
            state = submit_version_state(
                preview_run=self._latest_success_run("detect"),
                submit_run=self._latest_success_run("detect_submit"),
                panel_args={},
                preview_param_keys=self.DETECT_PREVIEW_PARAM_KEYS,
                submit_param_keys=self.DETECT_PREVIEW_PARAM_KEYS,
            )
            if state == UP_TO_DATE and self._boxes_edited_after_submit():
                # 检测框被改过：提交产物仍是改框前那份，必须重新提交。
                return NEW_VERSION
            return state
        state = submit_version_state(
            preview_run=self._latest_success_run("rembg"),
            submit_run=self._latest_success_run("rembg_submit"),
            panel_args=panel_args,
            preview_param_keys=self.PREVIEW_PARAM_KEYS,
        )
        if state == UP_TO_DATE and self._preview_edited_after_submit():
            # 去底色结果被编辑过：提交产物仍是编辑前那一份，必须重新提交才会
            # 传给第四步（用户 2026-10-01「去底色那一步，必须提交才能传给
            # 下一步」）。参数没变，纯版本判定看不出这件事，所以另判一次。
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

    def _preview_edited_after_submit(self) -> bool:
        """``stages/rembgpreview`` 里是否有文件比最近一次成功提交还新。

        提交产物是「提交那一刻」的去底图结果，之后单独编辑去底图**不会**
        自动生效——按钮/提示必须把"请重新提交"说出来，不能让用户以为白编辑了。
        """
        if not self.task_id:
            return False
        submit_run = self._latest_success_run("rembg_submit")
        if not submit_run:
            return False
        try:
            submit_at = float(submit_run.get("finished_at") or 0.0)
        except (TypeError, ValueError):
            return False
        if submit_at <= 0:
            return False
        for image in list_stage_images(
            self.store.node_or_stage_output(
                self.task_id, self.current_node(), "rembg"
            )
        ):
            try:
                if image.stat().st_mtime > submit_at:
                    return True
            except OSError:  # 竞态下文件没了：不算编辑
                continue
        return False

    # ---------------------------------------------------------- 派生条目
    def _rembg_result_path(self, stem: str) -> Path | None:
        """某页面对应的「生成预览」去底色结果（``stages/rembgpreview[~节点]``）。

        ⚠️ 结果目录按**当前节点**取（B 方案）：两个「图片去底色」节点各有自己
        的预览目录，走主节点目录会把副本节点的页面显示成"还没生成预览"。
        """
        task_id = self.task_id
        if not task_id:
            return None
        rembg_dir = self.store.node_or_stage_output(
            task_id, self.current_node(), "rembg"
        )
        for ext in ("png", "jpg", "jpeg"):
            candidate = rembg_dir / f"{stem}.{ext}"
            if candidate.exists():
                return candidate
        return None

    def _book_page_widths(self) -> dict:
        """整本书每页的原始像素宽度：``{页名: 宽}``。

        ⚠️ **一次读盘算完整本**（``store.image_sizes_all``）：判定要遍历全部页面，
        逐页调 ``image_size`` 会整份读 sizes.json，320 页就是 320 次全量解析。
        缺记录的页回落读图片头（由 ``_page_width_of`` 负责）。
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
        widths: dict = {}
        for path in self._manifest_paths():
            try:
                widths[path.stem] = self._page_width_of(path, sizes)
            except Exception:  # noqa: BLE001 - 取不到宽度按"无页宽"处理
                widths[path.stem] = 0
        return widths

    def _book_profile(self, widths: dict | None = None, boxes_for=None):
        """整本书的形态判定（``utils.book_layout.BookProfile``）。

        规则本体在 :mod:`utils.book_layout`；这里只负责**取数**：清单 × 每页
        槽位（与 :meth:`DetectMixin._refresh_detect_stats` 同一口径）＋页宽。

        ``boxes_for``：可选的取框入口（默认整本一次读齐）。第三步实时预览传
        查表版，避免逐页重读 boxes.json 的 O(n²)。
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
        """当前步骤的提交条目（第二步=源页逐框裁图；第三步=去底图→成品）。

        全书级判定（单栏书 / 页宽 / 指定左右）与检测框都**一次读盘**：
        ``plan_*`` 会遍历整本 manifest 逐页回调，逐页走 ``_detect_boxes_for``
        就是 O(n²)。
        """
        widths = self._book_page_widths()
        profile = self._book_profile(widths)
        sides = self._side_overrides_all()
        boxes_map = self._boxes_map_all()
        boxes_for = lambda text: boxes_map.get(Path(text).stem, []) or []  # noqa: E731
        common = dict(
            manifest_paths=self._manifest_paths(),
            boxes_for=boxes_for,
            single_column_book=profile.single_column_book,
            page_width_for=lambda text: widths.get(Path(text).stem, 0),
            side_for=lambda text: sides.get(Path(text).stem),
        )
        if self.current_stage() == "detect":
            return plan_detect_submit_entries(**common)
        return plan_rembg_submit_entries(
            result_path_for=self._rembg_result_path, **common
        )

    def _side_overrides_all(self) -> dict:
        """整份 boxes.json 里的 ``{页名: 指定左右}``（一次读盘）。

        ⚠️ 别逐页调 ``box_side_at``——那个每次都整份读盘，320 页就是 320 次
        全量解析（与 ``image_sizes_all`` 同一个理由）。
        """
        getter = getattr(self.store, "box_sides_all_at", None)
        if not callable(getter):
            return {}
        try:
            return getter(self._boxes_write_path())
        except Exception:  # noqa: BLE001 - 读不到＝没有任何指定
            return {}

    def _side_override_for(self, path_text: str) -> str | None:
        """某页的**用户指定左右**（单页查询；批量场景用 :meth:`_side_overrides_all`）。"""
        getter = getattr(self.store, "box_side_at", None)
        if not callable(getter) or not self.task_id:
            return None
        try:
            return getter(self._boxes_write_path(), Path(path_text).stem)
        except Exception:  # noqa: BLE001 - 读不到按"没指定"
            return None

    def _build_print_effects(self, list_entries: list[dict]) -> list[dict]:
        """第四步的取图规格：**一律透传第三步「提交本次任务」的最终图**。

        用户 2026-10-01 口径：「去底色那一步，必须提交才能传给下一步」。
        ``effect=None`` 表示"这份文件的全部像素就是要排版的内容"，worker
        直接原样送进 PDF——裁图/透明底都已在前面两步提交时兑现。
        """
        return [
            {"file": str(Path(e["file"])), "effect": None}
            for e in list_entries
            if Path(e["file"]).exists()
        ]

    # ---------------------------------------------------------- 提交动作
    def run_submit(self) -> None:
        """「提交本次任务」按钮的统一入口：按当前步骤分发。"""
        stage = self.current_stage()
        if stage == "detect":
            self.run_detect_submit()
        else:
            self.run_rembg_submit()

    def run_detect_submit(self) -> None:
        """第二步提交：按 area 把页面图裁成下一步要的图 → ``stages/detect``。

        前提是最近一次「检测文本框」成功（与第三步"先生成预览再提交"同一套
        语义）；提交后这一步才算执行完毕，去底色才能拿到输入。
        """
        if not self._acquire_run("子任务"):
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
                    "warning", "尚未选择 PDF",
                    "点页头的「选择 PDF」按钮为本任务补上源文件，之后才能执行。",
                )
            else:
                self._toast(
                    "warning", "这一步的输入还没就位",
                    "这一步的输入由流程上游提供：先把它的上游步骤执行完，"
                    "或到「查看 / 编辑流程」里检查连线。",
                )
            return
        detect_state = self._node_stage_state("detect")["status"]
        if detect_state != "success":
            self._toast(
                "warning", "请先检测文本框",
                "「检测文本框」执行成功后才能提交本次任务"
                + ("" if detect_state == "pending" else
                   f"（当前状态：{STATUS_LABELS.get(detect_state, detect_state)}）"),
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
            panel.get_args()  # 本步没有表单参数；留着只为走同一条校验路径
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        self._refresh_manifest()
        if not self._manifest_paths():
            self._toast(
                "warning", "无输入页面",
                "页面清单为空，请先完成上一步子任务，或在预览区插入图片。",
            )
            return
        # 检测框决定几何：每个框各裁一张图（2026-10-22 起没有 area）。
        # border 沿用历史默认 "0"（不加留白：第四步会在纸上重新排版）。
        entries = self._submit_entries()
        if not entries:
            self._toast(
                "warning", "没有可提交的页面",
                "页面清单里没有能读取的图片，请检查上一步的产物。",
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
        }
        detect_run = self._latest_success_run("detect")
        if detect_run:
            out_args["_preview_run_id"] = detect_run.get("run_id")
        self.log_view.append(
            f"提交本次任务：按检测框裁图 {len(entries)} 张 → {out_args['output']}"
        )
        self._launch_stage_process("detect_submit", out_args, resume=False)

    def run_rembg_submit(self) -> None:
        """第三步提交：把「生成预览」的整图去底结果转透明底，输出到 stages/rembg。

        ⚠️ 与主按钮共用同一份执行权（``_acquire_run``）：提交与生成预览抢的是
        同一个 worker 槽位与同一批输出目录，同时在跑只会互相覆盖。
        """
        if not self._acquire_run("子任务"):
            return
        try:
            self._run_rembg_submit_unchecked()
        finally:
            if self.running_stage is None:
                self._release_run()

    def _run_rembg_submit_unchecked(self) -> None:
        """第三步提交的实现体（不含执行权守卫，勿直接调用）。"""
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
                    "warning", "尚未选择 PDF",
                    "点页头的「选择 PDF」按钮为本任务补上源文件，之后才能执行。",
                )
            else:
                self._toast(
                    "warning", "这一步的输入还没就位",
                    "这一步的输入由流程上游提供：先把它的上游步骤执行完，"
                    "或到「查看 / 编辑流程」里检查连线。",
                )
            return
        # 必须以最近一次「生成预览」成功为前提（旧图残留/失败/中断均拒绝提交）
        preview_state = self._node_stage_state("rembg")["status"]
        if preview_state != "success":
            self._toast(
                "warning", "请先生成预览",
                "「生成预览」执行成功后才能提交本次任务"
                + ("" if preview_state == "pending" else
                   f"（当前状态：{STATUS_LABELS.get(preview_state, preview_state)}）"),
            )
            return
        panel = self.panel_host_of_step("rembg")
        if panel is None:
            self._toast(
                "warning", "这一步不在流程里",
                "当前任务的流程图里没有「图片去底色」，请先在「查看 / 编辑流程」"
                "里把它加回来。",
            )
            return
        try:
            args = panel.get_args()
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        self._refresh_manifest()
        if not self._manifest_paths():
            self._toast(
                "warning", "无输入页面",
                "页面清单为空，请先完成上一步子任务，或在预览区插入图片。",
            )
            return
        # ⚠️ 去底色**不裁图**（2026-10-22）：预览目录里每一张原样变成一张成品。
        entries = [
            {"file": str(path), "label": Path(path).stem}
            for path in self._manifest_paths()
            if self._rembg_result_path(Path(path).stem) is not None
        ]
        if not entries:
            self._toast(
                "warning", "尚未生成预览",
                "请先点击「生成预览」生成去底色图片，再提交本次任务。",
            )
            return
        args["_effects"] = [
            {
                "file": str(self._rembg_result_path(Path(e["file"]).stem)),
                "label": e["label"],
            }
            for e in entries
        ]
        args["output"] = str(
            self.store.node_or_stage_output(
                self.task_id, self.current_node(), "rembg_submit"
            )
        )
        args["clean"] = True
        preview_run = self._latest_success_run("rembg")
        if preview_run:
            args["_preview_run_id"] = preview_run.get("run_id")
        self.log_view.append(
            f"提交本次任务：{len(entries)} 张最终图片 → {args['output']}"
        )
        self._launch_stage_process("rembg_submit", args, resume=False)

    # ---------------------------------------------------------- 按钮状态
    def _update_submit_button(self, running: bool) -> None:
        """「提交本次任务」按钮：按当前步骤分发到对应的状态刷新。"""
        stage = self.current_stage()
        if not self.task_id or stage not in PREVIEW_ACTION_LABEL:
            self.submit_hint.hide()
            # 离开这两步（或没任务）时把红框一起收掉，别圈到别的步骤去
            set_red_frame(self.submit_button, False)
            return
        if stage == "detect":
            self._update_detect_submit_button(running)
        else:
            self._update_rembg_submit_button(running)

    def _submit_button_common(self, running: bool, preview_state: str,
                              has_preview: bool, action: str) -> tuple:
        """两个步骤共用的"什么时候能提交"判据 → ``(状态, 提示语)``。

        返回 ``(None, 提示)`` 表示"执行中/不可提交但不必细判"。
        """
        if running:
            return None, "当前有任务正在执行，请等待完成后再提交"
        if preview_state != "success":
            if preview_state in ("failed", "cancelled"):
                return NO_PREVIEW, (
                    f"上次「{action}」{STATUS_LABELS.get(preview_state, preview_state)}，"
                    "请重新执行并成功后再提交本次任务"
                )
            return NO_PREVIEW, f"请先点击「{action}」，执行成功后才能提交本次任务"
        if not has_preview:
            return NO_PREVIEW, f"预览结果缺失，请重新点击「{action}」"
        return None, ""

    def _apply_submit_state(self, version, tip: str, hints: dict) -> None:
        """把版本状态落到按钮（文案/禁用/红框/加粗/提示行）。

        ⚠️ 文案**始终**是「提交本次任务」：它与主按钮并排一行后，每颗按钮
        只剩控制列（340~440px）的一半，实测 166~216px，而更长的写法必被
        qfluent 截成省略号（见 tests/probe_row_button_width.py 的实测）。
        "有新版本待提交"这层含义由**加粗** + 下方常驻的红字提示承担。
        """
        self.submit_button.setToolTip(tip)
        self.submit_button.setEnabled(version not in (None, NO_PREVIEW))
        set_red_frame(self.submit_button, version == NEW_VERSION)
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

    def _update_detect_submit_button(self, running: bool) -> None:
        """第二步「提交本次任务」：最近一次「检测文本框」成功后才可用。"""
        version, tip = self._submit_button_common(
            running,
            self._node_stage_state("detect")["status"],
            bool(self._manifest_paths()),
            "检测文本框",
        )
        if version is None and not tip:
            version = self._submit_version_state("detect")
            tip = {
                NEW_VERSION: "检测框有改动（或还没提交过），"
                             "请点击「提交本次任务」把文本框内容裁出来交给下一步",
                PREVIEW_STALE: "检测结果已过期，请先重新「检测文本框」再提交",
                UP_TO_DATE: "已提交：下一步（图片去底色）拿到的是这次裁好的图；"
                            "改框后需再次提交",
                NO_PREVIEW: "请先点击「检测文本框」，执行成功后才能提交本次任务",
            }[version]
        elif version is None:
            version = NO_PREVIEW
        self._apply_submit_state(version, tip, {
            NEW_VERSION: "● 有新版本待提交（检测框有改动，或还没提交）",
            PREVIEW_STALE: "● 检测结果已过期，请重新「检测文本框」后再提交",
            UP_TO_DATE: "已提交：下一步已能用这次裁好的图",
        })

    def _update_rembg_submit_button(self, running: bool) -> None:
        """第三步「提交本次任务」：最近一次「生成预览」成功后才可用。

        ⚠️ 开销按需付（审计 D6）：这个函数在执行期间**每 ≤200ms 被进度节流
        器拉一次**（_refresh_stage_views → _update_run_buttons → 这里）。
        ``stage_states``（读 JSON）+ ``list_stage_images``（扫目录）+
        ``_submit_version_state``（再读两遍 runs.json）加起来每 tick 几十毫秒
        都在主线程上。所以先判 running，只有空闲时才做这些读盘。
        """
        version, tip = self._submit_button_common(
            running,
            self._node_stage_state("rembg")["status"],
            bool(
                list_stage_images(
                    self.store.node_or_stage_output(
                        self.task_id, self.current_node(), "rembg"
                    )
                )
            ),
            "生成预览",
        )
        if version is None and not tip:
            version = self._submit_version_state("rembg")
            tip = {
                NEW_VERSION: "预览已产生新版本（重新生成预览、参数变更，"
                             "或去底色结果被编辑过），"
                             "请点击「提交本次任务」更新最终图片",
                PREVIEW_STALE: "面板去底参数已修改，当前预览图不是最新；"
                               "建议先重新「生成预览」，再提交本次任务",
                UP_TO_DATE: "最终图片已是最新预览版本；参数变更或重新生成预览后需再次提交",
                NO_PREVIEW: "请先点击「生成预览」，执行成功后才能提交本次任务",
            }[version]
        elif version is None:
            version = NO_PREVIEW
        self._apply_submit_state(version, tip, {
            NEW_VERSION: "● 有新版本待提交（预览/参数/去底色结果有改动）",
            PREVIEW_STALE: "● 去底参数已修改，请重新「生成预览」后再提交",
            UP_TO_DATE: "最终图片已是最新版本",
        })

    def _show_submit_hint(self, text: str, color: str) -> None:
        self.submit_hint.setText(text)
        self.submit_hint.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.submit_hint.show()
