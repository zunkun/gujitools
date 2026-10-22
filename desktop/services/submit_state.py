# -*- coding: utf-8 -*-
"""「提交本次任务」按钮的版本状态机（纯函数）。

2026-10-22 起只服务第二步「检测文本框」（检测 → 提交裁图）：去底色已收成
单一步动作，不再有提交/预览。状态语义见 :func:`submit_version_state`。
"""

from __future__ import annotations

PREVIEW_STALE = "preview_stale"
NEW_VERSION = "new_version"
UP_TO_DATE = "up_to_date"
NO_PREVIEW = "no_preview"

#: 提交时还要再比一遍的参数（"预览之后又改了参数 ⇒ 成品要重新做"）。
#: 2026-10-22 起两个步骤都没有 area/border 了：默认不额外比参数，
#: 调用方按需显式传 ``submit_param_keys``。
DEFAULT_SUBMIT_PARAM_KEYS: tuple = ()


def submit_version_state(
    preview_run: dict | None,
    submit_run: dict | None,
    panel_args: dict,
    preview_param_keys,
    submit_param_keys=DEFAULT_SUBMIT_PARAM_KEYS,
) -> str:
    """提交按钮版本状态：

    - no_preview   ：从未成功检测（或最近一次失败/中断）→ 禁止提交；
    - preview_stale：面板参数相对最近一次成功检测已修改（当前无参数，恒不触发）；
    - new_version  ：检测有新版本（重新检测过、或参数已改），
                     裁图产物落后于检测 → 提示需要提交；
    - up_to_date   ：裁图产物已是最新检测结果。
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
        return NEW_VERSION  # 检测已重新跑过
    if any(sub_params.get(k) != panel_args.get(k) for k in submit_param_keys):
        return NEW_VERSION  # 影响产物的参数变了，成品需要重做
    return UP_TO_DATE
