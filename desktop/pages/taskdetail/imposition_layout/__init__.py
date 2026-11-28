# -*- coding: utf-8 -*-
"""**模块二「拼版操作」控制器**：画布版面操作与拼版合成落盘。

对应 UI 模块二（``desktop/components/imposition/canvas.py`` +
``panel.py``）：
- 画布里拖动 / 缩放拉伸 / 旋转 → ``items_changed`` → 落盘 + 防抖合成；
- **双击预览**（用户 2026-09-30）：双击空白处预览整页左右组合；
- **右键菜单「预览图片 / 编辑图片」**：预览仍可针对单图或整页；编辑统一在
  同一画布显示本页两张源图，点击切换活动图并分别保存有修改的源图；
- **弹窗里「编辑」也落盘**（2026-10-07 用户定：预览弹窗不再只读）：单张
  原图回写源图文件；整页组合只预览，不提供合成图回写入口，
  生效链汇聚在 ``_on_imposition_zoom_image_saved``；
- 面板的**整体旋转**（滑块/输入框增量）、复位本页版面（对当前页或
  选中槽位做版面变换）、**删除选中图片**（2026-09-30 用户定：选中哪张
  就能删哪张，页保留、图回未选择列表）；
- 状态行（当前页 / 选中槽位 / 拼版是否生效 / 单图页显隐「新增图片」）；
- **后台防抖合成**（``stages/imposition/``，列表顺序即页序）与点「生成PDF」前
  的同步兜底合成。

只通过 ``self`` 依赖共享基元（``imposition.ImpositionBaseMixin``）与宿主
页面（``store``、``log_view``、``run_worker``、``_toast``），本包各分片
**不 import** 其它拼版控制器模块。

2026-11-22 起按职责拆成子包（对外 ``from desktop.pages.taskdetail.
imposition_layout import X`` 完全不变）：

- ``constants``：防抖/让路阈值与签名侧车后缀；
- ``compose_sigs``：逐页签名的侧车文件读写；
- ``layout_ops``：旋转/复位/删除选中图片；
- ``preview``：双击预览、定位、右键编辑回写；
- ``persist``：版面落盘与状态行；
- ``compose``：防抖排期、增量合成、签名记录；
- ``mixin``：``ImpositionLayoutMixin`` 的装配。
"""

from desktop.pages.taskdetail.imposition_layout.compose_sigs import (
    _read_composed_sigs, _write_composed_sigs,
)
from desktop.pages.taskdetail.imposition_layout.constants import (
    COMPOSED_SIGS_SUFFIX,
    COMPOSE_DEBOUNCE_MS,
    COMPOSE_YIELD_MAX_MS,
    COMPOSE_YIELD_MIN_PAGES,
    COMPOSE_YIELD_TO_THUMBS_MS,
    EDIT_COMMIT_DEBOUNCE_MS,
    PRINT_WAIT_POLL_MS,
    PRINT_WAIT_TIMEOUT_MS,
    THUMB_REFRESH_DEBOUNCE_MS,
)
from desktop.pages.taskdetail.imposition_layout.mixin import ImpositionLayoutMixin

__all__ = [
    "COMPOSED_SIGS_SUFFIX",
    "COMPOSE_DEBOUNCE_MS",
    "COMPOSE_YIELD_MAX_MS",
    "COMPOSE_YIELD_MIN_PAGES",
    "COMPOSE_YIELD_TO_THUMBS_MS",
    "EDIT_COMMIT_DEBOUNCE_MS",
    "ImpositionLayoutMixin",
    "PRINT_WAIT_POLL_MS",
    "PRINT_WAIT_TIMEOUT_MS",
    "THUMB_REFRESH_DEBOUNCE_MS",
]
