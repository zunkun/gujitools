# -*- coding: utf-8 -*-
"""任务详情页的 rembg「提交本次任务」控制器。

- run_rembg_submit          ：提交动作（派生条目 → worker 子进程）；
- _update_submit_button 等  ：提交按钮的版本状态与提示。

纯版本判定规则见 services/submit_state.py，
条目/效果派生规则见 services/print_plan.py。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.services.print_plan import entry_to_effect_spec, plan_rembg_submit_entries
from desktop.services.submit_state import (
    NEW_VERSION, NO_PREVIEW, PREVIEW_STALE, UP_TO_DATE,
    rembg_submit_version_state,
)
from desktop.ui.widgets import bold_button
from desktop.utils.files import list_stage_images
from desktop.pages.taskdetail.runner import STATUS_LABELS

if TYPE_CHECKING:
    from desktop.store.store import TaskStore

#: 提交按钮的**唯一**文案（构造处与状态刷新处共用一份，避免两处各写一遍）。
#: ⚠️ 别再加「（有新版本）」后缀：它与「生成预览」并排后放不下（见
#:    ``_update_submit_button`` 的实测说明），"待提交"由加粗 + 红字提示表达。
SUBMIT_TEXT = "提交本次任务"


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
        submit_button: Any  # 第三步「提交本次任务」按钮
        submit_hint: Any  # 提交区文案标签
        _toast: Callable[..., None]
        current_stage: Callable[[], str]
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

    # 影响「生成预览」产物（去底预览图）的参数；变化后预览图即过期
    PREVIEW_PARAM_KEYS = (
        "type", "offset", "seal", "sealcolor", "sealarea", "sealmin_sat",
    )

    # ---------------------------------------------------------- 状态判定
    def _latest_success_run(self, stage: str) -> dict | None:
        if not self.task_id:
            return None
        for record in self.store.list_stage_runs(self.task_id, stage):
            if record.get("status") == "success":
                return record
        return None

    def _rembg_submit_version_state(self) -> str:
        rembg_host = self.panel_host_of_step("rembg")
        state = rembg_submit_version_state(
            preview_run=self._latest_success_run("rembg"),
            submit_run=self._latest_success_run("rembg_submit"),
            # ⚠️ 流程里没有「图片去底色」这一格 ⇒ 没有可比对的表单参数，
            #    传空字典（别借别的面板，那是一份用户没填过的值）。
            panel_args=rembg_host.get_args() if rembg_host else {},
            preview_param_keys=self.PREVIEW_PARAM_KEYS,
        )
        if state == UP_TO_DATE and self._preview_edited_after_submit():
            # 去底色结果被编辑过：提交产物仍是编辑前那一份，必须重新提交才会
            # 传给第四步（用户 2026-10-01「去底色那一步，必须提交才能传给
            # 下一步」）。参数没变，纯版本判定看不出这件事，所以另判一次。
            return NEW_VERSION
        return state

    def _preview_edited_after_submit(self) -> bool:
        """``stages/rembgpreview`` 里是否有文件比最近一次成功提交还新。

        提交产物是「提交那一刻」的去底图合成结果，之后单独编辑去底图**不会**
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
            self.store.rembg_preview_output_dir(self.task_id)
        ):
            try:
                if image.stat().st_mtime > submit_at:
                    return True
            except OSError:  # 竞态下文件没了：不算编辑
                continue
        return False

    # ---------------------------------------------------------- 派生条目
    def _rembg_result_path(self, stem: str) -> Path | None:
        """某页面对应的「生成预览」去底色结果（stages/rembgpreview）。"""
        # 结果目录按任务归属；没有任务就没有结果可指（调用方都在任务态进这里）
        task_id = self.task_id
        if not task_id:
            return None
        rembg_dir = self.store.rembg_preview_output_dir(task_id)
        for ext in ("png", "jpg", "jpeg"):
            candidate = rembg_dir / f"{stem}.{ext}"
            if candidate.exists():
                return candidate
        return None

    def _rembg_submit_entries(self, area: int, border) -> list[dict]:
        """预览结果 + 检测框 + area/border → 最终图片条目（规则见 print_plan）。"""
        return plan_rembg_submit_entries(
            manifest_paths=self._manifest_paths(),
            result_path_for=self._rembg_result_path,
            boxes_for=self._detect_boxes_for,
            area=area,
        )

    def _build_print_effects(self, list_entries: list[dict]) -> list[dict]:
        """第四步的取图规格：**一律透传「提交本次任务」的最终图**。

        用户 2026-10-01 口径：「去底色那一步，必须提交才能传给下一步」。
        所以第四步**不再**拿去底图（``stages/rembgpreview``）+ 当前
        area/border 现算，只用第三步落盘的成品图（``stages/rembg``，拼版
        生效时是 ``stages/imposition``）——它们是同一套几何规则在**提交
        那一刻**合成出来的。由此：

        - 编辑去底色结果、改 area/border 之后，都要重新「提交本次任务」
          才会进 PDF（提交按钮本来就会高亮「有新版本」提示）；
        - 编辑第四步的「待打印图」则是点「生成PDF」即生效（它就是要交付的
          那张图本身）；
        - 拼版页同样是"已经合成好的整页成品"，本来就走这条透传——再走一遍
          区域合成会把整页当半幅紧裁，拼出来的版面全毁。

        ``effect=None`` 表示"这份文件的全部像素就是要排版的内容"，worker
        直接原样送进 PDF。
        """
        return [
            {"file": str(Path(e["file"])), "effect": None}
            for e in list_entries
            if Path(e["file"]).exists()
        ]

    # ---------------------------------------------------------- 提交动作
    def run_rembg_submit(self) -> None:
        """提交本次任务：把「生成预览」的去底色图片按 area/border 等
        合成为真正想要的最终图片，输出到 stages/rembg 目录。

        ⚠️ 与「执行本子任务」共用同一份执行权（``_acquire_run``）：提交与
        生成预览抢的是同一个 worker 槽位与同一批输出目录，同时在跑只会互相
        覆盖；连点两下同样由防抖窗口吞掉。
        """
        if not self._acquire_run("子任务"):
            return
        try:
            self._run_rembg_submit_unchecked()
        finally:
            if self.running_stage is None:
                self._release_run()

    def _run_rembg_submit_unchecked(self) -> None:
        """提交本次任务的实现体（不含执行权守卫，勿直接调用）。"""
        if not self.task_id or not self._stage_inputs_ready():
            # ⚠️ 空壳任务（创建时没选 PDF，用户 2026-10-06）说清去哪儿补，
            #    而不是"请先导入 PDF"——那听着像要去列表页重新导入。
            # ⚠️ 判据是"**这一步需要的输入**齐不齐"而不是"有没有 PDF"，
            #    与 ``runner._run_stage_unchecked`` 同一个（用户 2026-10-06）：
            #    流程第一步不吃 PDF 时，那种任务压根不需要源文件。
            kind = self._missing_input_kind()
            if kind == "images":
                self._toast(
                    "warning", "这一步需要图片",
                    "本流程第一步不吃 PDF，请点页头的图片按钮选择图片，"
                    "或把图片放进任务目录下的 stages/input。",
                )
            elif kind == "pdf":
                # ⚠️ 指页头按钮前先确认它**在**（用户 2026-10-06 规则③：
                #    输入控件只属于第一个流程节点；「图片提取」打头才显示）。
                self._toast(
                    "warning", "尚未选择 PDF",
                    "点页头的「选择 PDF」按钮为本任务补上源文件，之后才能执行。",
                )
            else:
                # 与 runner._run_stage_unchecked 同一个口径（用户 2026-10-06
                # 规则③）：入口不吃 PDF 也不缺图时别再指"选择 PDF"——那种
                # 流程里按钮是藏着的，指过去就是"点了没反应"。
                self._toast(
                    "warning", "这一步的输入还没就位",
                    "这一步的输入由流程上游提供：先把它的上游步骤执行完，"
                    "或到「查看 / 编辑流程」里检查连线。",
                )
            return
        # 必须以最近一次「生成预览」成功为前提（旧图残留/失败/中断均拒绝提交）
        preview_state = self.store.stage_states(self.task_id)["rembg"]["status"]
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
        entries = self._rembg_submit_entries(args["area"], args.get("border"))
        if not entries:
            self._toast(
                "warning", "尚未生成预览",
                "请先点击「生成预览」生成去底色图片，再提交本次任务。",
            )
            return
        args["_effects"] = [
            entry_to_effect_spec(e, args.get("border")) for e in entries
        ]
        args["output"] = str(self.store.rembg_output_dir(self.task_id))
        args["clean"] = True
        # 记录本次提交所基于的「生成预览」成功版本，用于判断预览是否又有新版本
        preview_run = next(
            (r for r in self.store.list_stage_runs(self.task_id, "rembg")
             if r.get("status") == "success"),
            None,
        )
        if preview_run:
            args["_preview_run_id"] = preview_run.get("run_id")
        self.log_view.append(
            f"提交本次任务：{len(entries)} 张最终图片 → {args['output']}"
        )
        self._launch_stage_process("rembg_submit", args, resume=False)

    # ---------------------------------------------------------- 按钮状态
    def _update_submit_button(self, running: bool) -> None:
        """步骤三「提交本次任务」：最近一次「生成预览」成功后才可用；
        预览产生新版本（重跑/参数变更）时按钮高亮提示需要重新提交。"""
        if not self.task_id or self.current_stage() != "rembg":
            self.submit_hint.hide()
            return
        # ⚠️ 开销按需付（审计 D6）：这个函数在执行期间**每 ≤200ms 被进度节流
        # 器拉一次**（_refresh_stage_views → _update_run_buttons → 这里）。
        # `stage_states`（读 JSON）+ `list_stage_images`（扫目录）+
        # `_rembg_submit_version_state`（再读两遍 runs.json）加起来每 tick
        # 几十毫秒都在主线程上。而 `running=True` 时下面两个判据的结果根本
        # 不进任何分支（直接落"执行中"提示）——纯浪费。先判 running，
        # 只有空闲（低频状态变化）时才做这些读盘。
        if running:
            version = None
            tip = "当前有任务正在执行，请等待完成后再提交"
        else:
            preview_state = self.store.stage_states(self.task_id)["rembg"]["status"]
            has_preview = bool(
                list_stage_images(self.store.rembg_preview_output_dir(self.task_id))
            )
            if preview_state != "success":
                version = NO_PREVIEW
                if preview_state in ("failed", "cancelled"):
                    tip = (
                        f"上次「生成预览」{STATUS_LABELS.get(preview_state, preview_state)}，"
                        "请重新执行并成功后再提交本次任务"
                    )
                else:
                    tip = "请先点击「生成预览」，执行成功后才能提交本次任务"
            elif not has_preview:
                version = NO_PREVIEW
                tip = "预览结果缺失，请重新点击「生成预览」"
            else:
                version = self._rembg_submit_version_state()
                tip = {
                    NEW_VERSION: "预览已产生新版本（重新生成预览、参数变更，"
                                 "或去底色结果被编辑过），"
                                 "请点击「提交本次任务」更新最终图片",
                    PREVIEW_STALE: "面板去底参数已修改，当前预览图不是最新；"
                                   "建议先重新「生成预览」，再提交本次任务",
                    UP_TO_DATE: "最终图片已是最新预览版本；参数变更或重新生成预览后需再次提交",
                    NO_PREVIEW: "请先点击「生成预览」，执行成功后才能提交本次任务",
                }[version]
        self.submit_button.setToolTip(tip)

        # 按钮文案/高亮
        self.submit_button.setEnabled(version not in (None, NO_PREVIEW))
        # ⚠️ 文案**始终**是「提交本次任务」：它与「生成预览」并排一行后，每颗
        #    按钮只剩控制列（340~440px）的一半，实测 166~216px，而
        #    「提交本次任务（有新版本）」需要 218px ⇒ 必被 qfluent 截成省略号
        #    （见 tests/probe_row_button_width.py 的实测）。这层"有新版本待提交"
        #    的含义由**加粗** + 下方常驻的红字提示承担，信息不丢。
        #    （与「继续执行 / 中断执行」并排时收敛文案是同一处理原则。）
        self.submit_button.setText(SUBMIT_TEXT)
        if version == NEW_VERSION:
            # ⚠️ 加粗走 setFont：setStyleSheet 会把 qfluent 按钮的整套 qss
            # （含 hasIcon=true 的 36px 左边距）整串抹掉（见 widgets.bold_button）
            bold_button(self.submit_button, True)
            self._show_submit_hint(
                "● 有新版本待提交（预览/参数/去底色结果有改动）", "#c0392b"
            )
        elif version == PREVIEW_STALE:
            bold_button(self.submit_button, False)
            self._show_submit_hint(
                "● 去底参数已修改，请重新「生成预览」后再提交", "#b8860b"
            )
        elif version == UP_TO_DATE:
            bold_button(self.submit_button, False)
            self._show_submit_hint("最终图片已是最新版本", "#3a8a3e")
        else:  # no_preview / 执行中
            bold_button(self.submit_button, False)
            self.submit_hint.hide()

    def _show_submit_hint(self, text: str, color: str) -> None:
        self.submit_hint.setText(text)
        self.submit_hint.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.submit_hint.show()
