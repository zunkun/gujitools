# -*- coding: utf-8 -*-
"""**模块一「选择拼版」控制器**：拼版页的增删与选择状态。

对应 UI 模块一（``desktop/components/imposition/page_list.py`` +
``picker.py``）与右侧面板的页管理按钮（``panel.py``）：
- 启用/取消拼版（决定第四步取图来源，落盘到 ``drafts/imposition.json``）；
- 「选择拼版」→ 弹窗挑两张加一页；或挑一张勾「自动拼版」批量加页；
  弹窗是**一个列表**（上游剩余图 + 本任务上传过的图），也能自己上传图片
  （2026-11-16：不再有「删除恢复」页签——删掉的图直接回到这个列表）；
- **单图页「新增图片」**（2026-09-30）：append 模式弹窗挑 1 张并进当前页；
- 删页入口只剩**左列**：「✕」释放单页 / 勾选悬浮框批量删除 / 清空全部
  ——右侧面板的「删除本页拼版」按钮已删（2026-09-30 用户定）；
  页序在左列**拖动排序**，翻页在画布下方「上一页/下一页」。

只通过 ``self`` 依赖共享基元（``imposition.ImpositionBaseMixin`` 提供的
``_imposition_doc`` / ``_save_imposition_pages`` / ``imposition_active`` /
``_refresh_print_source`` / ``_update_imposition_status`` 等）与宿主页面
（``step_bar``、``log_view``、``_toast``），本包各分片**不 import** 其它拼版
控制器模块——两个模块的 agent 可以互不影响地改。

2026-11-22 起按职责拆成子包（对外 ``from desktop.pages.taskdetail.
imposition_pages import X`` 完全不变）：``state``（启用开关）、``picker``（弹窗
选图/加页）、``page_ops``（页序与删页）、``thumbnails``（左列缩略图）、
``helpers``（小工具）、``mixin``（装配）。
"""

from desktop.pages.taskdetail.imposition_pages.helpers import _chosen_items
from desktop.pages.taskdetail.imposition_pages.mixin import ImpositionPagesMixin

__all__ = ["ImpositionPagesMixin"]
