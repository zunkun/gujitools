# -*- coding: utf-8 -*-
"""步骤的**声明式元数据**：一个步骤"是什么"，与流程顺序无关。

用户口径（2026-10-02）：

> 任务管理每个步骤组件有先后关系，因此我们的组件不需要相互关联，
> 公共组件定义好 API 就行，比如入口文件目录，输出文件目录等。

所以 :class:`StepSpec` 只描述**这一步自己**：跑哪个命令、用哪个参数面板、
输入是 PDF 还是图片（单张 / 目录 / 一批）、默认输出目录怎么从输入推出来。
「上一步是谁、下一步是谁、产物给谁用」**一概不写**——那是任务管理自己的
编排，不是步骤的属性。正因如此，同一个 spec 既能被任务流程用，也能被左侧
导航的独立模块用。

「入口」这一侧的三件事也都收在这里，**不散到界面代码**去（用户 2026-10-02：
「页面上有一个大的输入框，可以输入图片和输入文件，或者输入目录，也可以把
文件拖进去」）：

1. 认哪些后缀 —— :meth:`StepSpec.suffixes`（从 ``file_filter`` 里抠，过滤串
   仍是唯一事实来源）；
2. 允不允许直接拿目录当输入 —— ``accepts_dir``；
3. 用户给了一堆东西（拖进来的文件/文件夹混在一起）**到底算哪个源** ——
   :meth:`StepSpec.resolve_source`。这是纯逻辑，可以脱离 Qt 单测。

⚠️ 面板只记**类名**（字符串），到用的时候才从 ``desktop.components.panels``
惰性取——本模块因此不 import 任何 Qt 面板，可以被纯逻辑（CLI、自测、未来的
批处理）安全导入。

本包按职责拆成三个子模块（2026-11-22）：

- :mod:`desktop.steps.spec.constants`：文件过滤串 / 后缀正则 / 自动下钻层数；
- :mod:`desktop.steps.spec.step_spec`：:class:`StepSpec` 本身；
- :mod:`desktop.steps.spec.catalog`：:data:`SPECS` 及派生表。

⚠️ 本 ``__init__`` 只做重导出：既有 ``from desktop.steps.spec import X`` 全部
不变，子模块之间不要反过来导入本包（会形成循环）。
"""

from desktop.steps.spec.catalog import (
    FLOW_STAGES,
    NAV_STEPS,
    OPTIONAL_STEPS,
    SPECS,
    STEP_KEYS,
    _nav_written_index,
    spec_by_key,
)
from desktop.steps.spec.constants import (
    AUTO_DESCEND_DEPTH,
    IMAGE_FILTER,
    PDF_FILTER,
    _SUFFIX_RE,
)
from desktop.steps.spec.step_spec import StepSpec

__all__ = [
    "FLOW_STAGES",
    "IMAGE_FILTER",
    "NAV_STEPS",
    "OPTIONAL_STEPS",
    "PDF_FILTER",
    "SPECS",
    "STEP_KEYS",
    "StepSpec",
    "spec_by_key",
]
