# -*- coding: utf-8 -*-
"""独立拼图页的常量与步骤元数据（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from desktop.steps import StepSpec, spec_by_key

#: 本页的步骤元数据（标题/副标题/过滤串的唯一来源）。⚠️ spec_by_key 的声明
#: 返回 StepSpec | None，但 spec 表里 imposition 是**写死存在**的一条（删掉它
#: 整条模块就没了），这里显式断言一次：与其在每个用到 _SPEC 的地方写一堆判空，
#: 不如在源头把「这条 spec 必须存在」这条不变量钉住（缺了就立刻炸，位置也清楚）。
_SPEC_OR_NONE = spec_by_key("imposition")
assert _SPEC_OR_NONE is not None, "spec 表里缺少 imposition 这一步"
#: 断言后的**非空别名**：模块级变量在函数体里不会被类型检查器保持收窄，故这里
#: 显式再声明一次类型（运行时就是上面那个对象，零开销）。
_SPEC: StepSpec = _SPEC_OR_NONE

#: 手工修饰过的整页组合落在 ``singletask/<独立功能>/`` 下的哪个子目录。
EDITED_DIRNAME = "edited"

#: 「上传图片」复制进 ``singletask/<独立功能>/`` 的哪个子目录（与任务流程的
#: ``tasks/<任务号>/inserted/`` 同一口径，见 :func:`uploaded_page_dir`）。
UPLOAD_DIRNAME = "inserted"

#: 版面改动 → 左列**单页缩略图**重合成的防抖（用户 2026-10-09：拖动松手/
#: 面板调整/编辑回写之后几秒内，缩略图要跟上页面效果）。拖动中签名每帧
#: 都在变，等真的停手了再合成一次就够。
THUMB_REFRESH_DEBOUNCE_MS = 2000

#: 旋转组件（整体/选中图）停手后统一提交的防抖（与任务流程
#: ``imposition_layout.EDIT_COMMIT_DEBOUNCE_MS`` 同一档）：滑块连续吐增量
#: 期间只转画布不落盘，停手 250ms 后一次性 flush + 重适配 + 回填面板。
EDIT_COMMIT_DEBOUNCE_MS = 250
