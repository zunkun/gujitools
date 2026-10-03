# -*- coding: utf-8 -*-
"""共用步骤组件层：把「一个处理步骤」抽成**与流程无关**的可复用零件。

用户 2026-10-02 的定调：

> 复用组件，但是需要抽取出来公共组件，任务管理每个步骤组件有先后关系，
> 因此我们的组件不需要相互关联，公共组件定义好 API 就行，比如入口文件
> 目录，输出文件目录等；新的功能可以批量处理也可以处理一张图片。

于是这一层只回答三个问题，**不关心调用方是谁、第几步、上下游是谁**：

1. **这个步骤是什么** —— :class:`~desktop.steps.spec.StepSpec`：
   命令名、参数面板、输入是 PDF/图片/目录、输出目录怎么派生；外加"用户拖进来
   一堆文件/文件夹到底算哪个源"的归一化规则（:meth:`StepSpec.resolve_source`）。
2. **怎么把它跑起来** —— :class:`~desktop.steps.kernel.StepKernel`：
   一个 API 只认「输入路径 + 输出路径 + 参数」的执行内核，单张或批量都行，
   进度/成功/失败以 Qt 信号回报，跑在后台线程里，不卡界面。
3. **怎么摆到界面上** —— :class:`~desktop.steps.source_zone.SourceZone`
   （大输入区：拖文件、拖文件夹、点选，用户 2026-10-02 明确要的那块）+
   :class:`~desktop.steps.control.StepControl`：把「选源 → 调参数 → 执行/中断」
   这条操作链组装成一块可直接塞进卡片、也可只借它大输入区的控件。

   ⚠️ **「点选」走的是资源管理器的选择对话框**（用户 2026-10-03：「能否底部
   不设置选择图片或者目录的弹窗」⇒ 去掉了点空白处那个两选项小菜单），
   **不是**"另开一个资源管理器窗口再监听选中项"—— 用户明确纠正过这两者的
   区别，详见 :class:`SourceZone` 的类 docstring。

谁在用：

- **左侧导航的三个模块**（``desktop/modules/{extract,rembg,imposition}``）：
  各持一份自己的组件实例 ⇒ 三个功能**互不影响**（没有共享的可变状态）；
- **任务详情页**（``desktop/pages/taskdetail``）：把子进程传输层
  （:mod:`desktop.steps.process`）交给这一层，任务管理不再自己攥着
  QProcess/看门狗/事件解析那套代码。

4. **输入输出怎么连** —— :mod:`desktop.steps.ports`：产物类型、每步的输入/输出
   端口、产物落点、以及"谁供给谁"的连线表。它是将来 BPM 换顺序/换连线的
   **唯一改动点**（原先这些知识散在 ``desktop.store.tasks`` 的四个
   ``*_output_dir`` 方法与 ``taskdetail.runner`` 的 if-else 里）。

⚠️ 本层**不 import** ``desktop.modules.*`` 与 ``desktop.pages.*``：依赖方向
是单向的（调用方 → 本层），否则又绕回"改一个步骤要动三处"的老问题。
"""

from __future__ import annotations

__all__ = [
    "StepSpec",
    "SPECS",
    "STEP_KEYS",
    "FLOW_STAGES",
    "OPTIONAL_STEPS",
    "NAV_STEPS",
    "spec_by_key",
    "StepRequest",
    "StepKernel",
    "StepJob",
    "CommandJob",
    "CallableJob",
    "command_job",
    "callable_job",
    "extract_job",
    "job_for",
    "StageProcess",
    "StepControl",
    "SourceZone",
]

#: 惰性导出：``spec`` / ``kernel`` 是纯逻辑（无 Qt），而 ``control`` / ``process``
#: 会拖进 PySide6。任务管理的执行路径只想拿 ``StageProcess``，模块页才需要
#: ``StepControl``——分开导入能少加载一坨。
_LAZY = {
    "StepSpec": ("desktop.steps.spec", "StepSpec"),
    "SPECS": ("desktop.steps.spec", "SPECS"),
    "STEP_KEYS": ("desktop.steps.spec", "STEP_KEYS"),
    "FLOW_STAGES": ("desktop.steps.spec", "FLOW_STAGES"),
    "OPTIONAL_STEPS": ("desktop.steps.spec", "OPTIONAL_STEPS"),
    "NAV_STEPS": ("desktop.steps.spec", "NAV_STEPS"),
    "spec_by_key": ("desktop.steps.spec", "spec_by_key"),
    "StepRequest": ("desktop.steps.kernel", "StepRequest"),
    "StepKernel": ("desktop.steps.kernel", "StepKernel"),
    "StepJob": ("desktop.steps.kernel", "StepJob"),
    "CommandJob": ("desktop.steps.kernel", "CommandJob"),
    "CallableJob": ("desktop.steps.kernel", "CallableJob"),
    "command_job": ("desktop.steps.kernel", "command_job"),
    "callable_job": ("desktop.steps.kernel", "callable_job"),
    "extract_job": ("desktop.steps.kernel", "extract_job"),
    "job_for": ("desktop.steps.kernel", "job_for"),
    "StageProcess": ("desktop.steps.process", "StageProcess"),
    "StepControl": ("desktop.steps.control", "StepControl"),
    "SourceZone": ("desktop.steps.source_zone", "SourceZone"),
    # ⚠️ 端口模块走**模块**惰性导出（不是逐个名字）：它是一整套配套的表与
    #    函数，调用方一律 ``from desktop.steps import ports`` 整体取用，
    #    逐个转发只会让 __all__ 与 _LAZY 越滚越长（见 __getattr__ 的处理）。
    "ports": ("desktop.steps.ports", None),
}


def __getattr__(name: str):
    """按需导入（PEP 562），并把结果缓存进 globals。

    ``_LAZY`` 的值是 ``(模块名, 属性名)``；**属性名为 ``None`` 时返回整个模块**
    （见 ``ports`` 那条）——Python 的模块对象本就是合法的导出值。
    """
    entry = _LAZY.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(entry[0])
    value = module if entry[1] is None else getattr(module, entry[1])
    globals()[name] = value
    return value
