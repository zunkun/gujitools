# -*- coding: utf-8 -*-
"""任务详情页的 rembg「提交本次任务」控制器。

- run_rembg_submit          ：提交动作（派生条目 → worker 子进程）；
- _update_submit_button 等  ：提交按钮的版本状态与提示。

纯版本判定规则见 services/submit_state.py，
条目/效果派生规则见 services/print_plan.py。
"""

from __future__ import annotations

from pathlib import Path

from desktop.services.print_plan import entry_to_effect_spec, plan_rembg_submit_entries
from desktop.services.submit_state import (
    NEW_VERSION, NO_PREVIEW, PREVIEW_STALE, UP_TO_DATE,
    rembg_submit_version_state,
)
from desktop.utils.files import list_stage_images
from desktop.pages.taskdetail.runner import STATUS_LABELS


class SubmitMixin:
    """依赖宿主页面提供的属性：store/task_id/source_path、process、
    control_stack、submit_button/submit_hint、log_view、_toast()。"""

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
        return rembg_submit_version_state(
            preview_run=self._latest_success_run("rembg"),
            submit_run=self._latest_success_run("rembg_submit"),
            panel_args=self.control_stack.widget(2).get_args(),
            preview_param_keys=self.PREVIEW_PARAM_KEYS,
        )

    # ---------------------------------------------------------- 派生条目
    def _rembg_result_path(self, stem: str) -> Path | None:
        """某页面对应的「生成预览」去底色结果（stages/rembgpreview）。"""
        rembg_dir = self.store.rembg_preview_output_dir(self.task_id)
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

    def _build_print_effects(
        self, list_entries: list[dict], area: int, border
    ) -> list[dict]:
        """第四步列表 + 第三步当前 area/border → worker 合成规格。"""
        from desktop.services.print_plan import plan_print_effects

        composed = self._rembg_submit_entries(area, border)
        rembg_dir = self.store.rembg_output_dir(self.task_id)
        submitted_labels = {p.stem for p in list_stage_images(rembg_dir)}
        return plan_print_effects(
            list_entries, composed, rembg_dir, submitted_labels, border,
        )

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
        if not self.task_id or not self.source_path:
            self._toast("warning", "提示", "请先导入 PDF")
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
        panel = self.control_stack.widget(2)  # rembg 面板
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
        preview_state = self.store.stage_states(self.task_id)["rembg"]["status"]
        has_preview = bool(
            list_stage_images(self.store.rembg_preview_output_dir(self.task_id))
        )
        if running:
            version = None
            tip = "当前有任务正在执行，请等待完成后再提交"
        elif preview_state != "success":
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
                NEW_VERSION: "预览已产生新版本（重新生成或参数已变更），"
                             "请点击「提交本次任务」更新最终图片",
                PREVIEW_STALE: "面板去底参数已修改，当前预览图不是最新；"
                               "建议先重新「生成预览」，再提交本次任务",
                UP_TO_DATE: "最终图片已是最新预览版本；参数变更或重新生成预览后需再次提交",
                NO_PREVIEW: "请先点击「生成预览」，执行成功后才能提交本次任务",
            }[version]
        self.submit_button.setToolTip(tip)

        # 按钮文案/高亮
        self.submit_button.setEnabled(version not in (None, NO_PREVIEW))
        if version == NEW_VERSION:
            self.submit_button.setText("提交本次任务（有新版本）")
            self.submit_button.setStyleSheet(
                "PrimaryPushButton{font-weight:bold;}"
            )
            self._show_submit_hint(
                "● 预览有新版本，请提交本次任务", "#c0392b"
            )
        elif version == PREVIEW_STALE:
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self._show_submit_hint(
                "● 去底参数已修改，请重新「生成预览」后再提交", "#b8860b"
            )
        elif version == UP_TO_DATE:
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self._show_submit_hint("最终图片已是最新版本", "#3a8a3e")
        else:  # no_preview / 执行中
            self.submit_button.setText("提交本次任务")
            self.submit_button.setStyleSheet("")
            self.submit_hint.hide()

    def _show_submit_hint(self, text: str, color: str) -> None:
        self.submit_hint.setText(text)
        self.submit_hint.setStyleSheet(f"color:{color}; font-weight:bold;")
        self.submit_hint.show()
