# -*- coding: utf-8 -*-
"""rembg「提交本次任务」按钮的版本状态机（纯函数）。"""

from __future__ import annotations

PREVIEW_STALE = "preview_stale"
NEW_VERSION = "new_version"
UP_TO_DATE = "up_to_date"
NO_PREVIEW = "no_preview"


def rembg_submit_version_state(
    preview_run: dict | None,
    submit_run: dict | None,
    panel_args: dict,
    preview_param_keys,
) -> str:
    """提交按钮版本状态：

    - no_preview   ：从未成功生成预览（或最近一次失败/中断）→ 禁止提交；
    - preview_stale：面板去底参数相对最近一次成功预览已修改，
                     磁盘上的预览图不是最新 → 建议重新生成预览；
    - new_version  ：预览有新版本（重新生成过、或 area/border 已改），
                     最终图片落后于预览 → 提示需要提交；
    - up_to_date   ：最终图片已是最新预览版本。
    """
    if preview_run is None:
        return NO_PREVIEW
    prev_params = preview_run.get("parameters", {})
    if any(prev_params.get(k) != panel_args.get(k) for k in preview_param_keys):
        return PREVIEW_STALE
    if submit_run is None:
        return NEW_VERSION
    sub_params = submit_run.get("parameters", {})
    if sub_params.get("_preview_run_id") != preview_run.get("run_id"):
        return NEW_VERSION  # 预览已用新参数重新生成
    if (sub_params.get("area") != panel_args.get("area")
            or sub_params.get("border") != panel_args.get("border")):
        return NEW_VERSION  # area/border 变了，最终图需要重新合成
    return UP_TO_DATE
