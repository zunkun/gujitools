# -*- coding: utf-8 -*-
"""阶段执行入口：执行权校验、输入就绪判定。"""

from __future__ import annotations

from desktop.store import IMPOSITION_STAGE, STAGE_STEP
from typing import TYPE_CHECKING, Any, Callable, cast


class StageLaunchMixin:
    """阶段执行入口（run_stage）与输入就绪判据。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _acquire_run: Any
        _input_node_mode: Any
        _release_run: Any
        _run_stage_unchecked: Any
        current_node: Any
        current_stage: Any
        imposition_effective: Any
        running_stage: Any
        store: Any
        task_id: Any
        window: Any

    # ---------------------------------------------------- 进度该显示在哪一步
    def _step_of_stage(self, stage: str | None) -> str | None:
        """运行阶段 → 它归属的界面步骤（``detect_submit`` 归第二步，见 STAGE_STEP）。"""
        if not stage:
            return None
        return STAGE_STEP.get(stage, stage)

    def _progress_belongs_here(self, stage: str | None) -> bool:
        """这条进度是否该画在**当前显示的这一步**上。

        ⚠️ 进度条与状态文字是**全页面共享**的一份控件，必须只服务当前这一步。
        以前无条件更新，于是第三步「分割图片」的进度被画在第四步的界面上：
        走动的进度条 +「进度 42/91」+ 灰掉的「生成PDF」按钮 —— 看起来就像第四步
        在自己出 PDF（用户报的「在第三步提交，然后进第四步，pdf 在生成过程中」）。

        跨步骤的进度一律不上屏：想知道它还在跑，看日志在滚。
        """
        return self._step_of_stage(stage) == self.current_stage()

    def _own_step_running(self) -> bool:
        """当前这一步**自己**的活儿是否正在跑。

        此时进度条与状态文案归 :meth:`_on_worker_progress` 所有，别的路径
        （``_apply_stage_state``）不许再写，否则两者每 200ms 互相盖一次，
        状态文字来回跳。
        """
        return (
            self.running_stage is not None
            and self._step_of_stage(self.running_stage) == self.current_stage()
        )

    # ---------------------------------------------------------- 执行/中断
    def run_stage(self, resume: bool = False) -> None:
        """启动当前阶段的 worker 子进程（带执行权守卫，防连点起两个）。

        ⚠️ 守卫必须包在**最外层**：下面要做参数校验、effects 组装、写运行配置，
        这些都是同步重活，做完才 ``QProcess.start()``。若只在 start 之前判断
        ``self.process``，那段时间它还是 None，连点第二下就能再起一个 worker，
        两个 torch 同时加载、同时写同一批输出目录。

        守卫由 :meth:`TaskDetailPage._acquire_run` 提供（受理标记 + 防抖窗口）；
        真正干活的是 :meth:`_run_stage_unchecked`。

        ⚠️ 「图片拼版」伪步骤没有可执行内容（占位详情页，执行按钮组处于
        隐藏态）；这里再挡一道，防自动化/快捷路径绕过可见性直接触发。
        """
        if self.current_stage() == IMPOSITION_STAGE:
            return
        # ⚠️ 聚合任务的**纯展示起点**（只有「图片提取」：成员的源 PDF 不搬，
        #    没有可执行的东西）拦截一下：按钮已置灰，这里再挡一道，防快捷键/
        #    自动化绕过可见性直接触发（用户 2026-11-18 任务 0025）。其余起点
        #    照常可重跑/编辑（用户 2026-11-18 晚口径）。
        if self._input_node_mode():
            from desktop.ui.toast import show_toast

            show_toast(
                self.window(), "info", "这一步不用执行",
                "当前步骤是聚合任务的提取起点：图片由子任务汇集而来，"
                "直接看清单或进入下一步即可。",
            )
            return
        if not self._acquire_run("步骤"):
            return
        try:
            self._run_stage_unchecked(resume)
        finally:
            # ``running_stage`` 仍是 None 说明这次受理没落到进程上（参数错、
            # 无输入、无需续跑…）——立刻释放，否则按钮会一直灰着没人来解锁。
            # 一旦进程起来了，生命周期改由 _worker_finished 释放。
            if self.running_stage is None:
                self._release_run()

    def _stage_inputs_ready(self) -> bool:
        """**当前这一步（当前节点）**的输入齐不齐，可以开跑吗。

        ⚠️ 别拿"有没有源 PDF"当判据（用户 2026-10-06）：自定义流程把
        「检测文本框」之类**不吃 PDF** 的步骤放第一位时，它的输入是入口图片
        目录（``stages/input/``，见 ``store.stage_input`` 的入口回落），
        那个目录里有图就能跑——哪怕整个任务压根没有 PDF。

        ⚠️ 也不能拿 ``ports.stage_inputs``（**静态声明**）当判据：声明回答的是
        "这一步**可能**吃什么"，要问的是"**这张流程图上**它吃什么"。两者分叉的
        两种情形都会把好端端的步骤锁死（用户 2026-10-06 现场）：

        · ``extract`` 的 ``pdf`` 由**任务自己**供给（不是阶段产物目录），
          拿它当路径查 ``exists()`` 恒为假 ⇒「图片提取」永远点不动；
        · 自定义流程把「图片去底色」放第一个节点、没有「检测文本框」时，
          ``boxes`` **本流程里没人产出** ⇒ 弹"这一步的输入还没就位"的假提示，
          而那一步其实完全能跑（它按 area 处理整张图）。

        所以判据走节点粒度的 :meth:`~desktop.store.tasks.TaskRepo.required_node_inputs`
        （= :func:`desktop.steps.ports.node_blocking_inputs`）：只查**这张图上
        这个节点**确实阻塞的端口，逐个按**该节点的连线**解析出路径并确认存在。
        同一步骤的多个节点各有上游（B 方案），按阶段查会让副本节点拿主节点的
        输入判就绪——"看着有输入，跑起来报找不到图"。
        """
        stage = self.current_stage()
        if not self.task_id or stage is None:
            return False
        # ⚠️ ``boxes`` 这类端口**缺文件不阻塞**（见 ports.OPTIONAL_INPUT_PORTS）：
        #    检测可能一框未检（空白页），那时 boxes.json 本来就不存在，而这一步
        #    按 area 处理整张图照样能跑。判据本身（"本流程里吃哪些端口"）仍走
        #    required_*_inputs，只是不再拿"文件在不在"当硬门槛。
        from desktop.steps import ports as _ports

        optional = _ports.OPTIONAL_INPUT_PORTS
        node = self.current_node()
        if node:
            for port in self.store.required_node_inputs(
                self.task_id, node, self.imposition_effective()
            ):
                if port in optional:
                    continue
                # ⚠️ 不只看"文件在不在"：上游的产出动作必须**执行成功**过
                #    （去底色的实时预览会提前写 stages/rembg，检测没提交时
                #    上游也可能留图），否则等于拿未生效的半成品当输入
                #    （用户 2026-11-03）。
                if not self.store.node_input_effective(
                    self.task_id, node, port, self.imposition_effective()
                ):
                    return False
            return True
        for port in self.store.required_stage_inputs(
            self.task_id, stage, self.imposition_effective()
        ):
            if port in optional:
                continue
            if not self.store.stage_input_effective(
                self.task_id, stage, port, self.imposition_effective()
            ):
                return False
        return True
