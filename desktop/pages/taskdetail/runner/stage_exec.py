# -*- coding: utf-8 -*-
"""一次完整阶段执行：参数校验、effects 组装、写运行配置并起进程。"""

from __future__ import annotations

from pathlib import Path
from desktop.services.print_plan import missing_extract_pages_spec, ordered_page_record
from desktop.store import STAGE_LABELS, STAGE_STEP
from ._qt import QProcess
from typing import TYPE_CHECKING, Any, Callable, cast


class StageExecMixin:
    """真正执行一个阶段（不含执行权守卫）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _aggregate_pending: Any
        _build_print_effects: Any
        _compose_imposition_now: Any
        _drop_live_results: Any
        _flush_pending_offset: Any
        _imposition_switch_state: Any
        _is_aggregate_task: Any
        _launch_stage_process: Any
        _logs: Any
        _manifest_paths: Any
        _missing_input_kind: Any
        _node_scope: Any
        _print_entries: Any
        _print_source_mark_text: Any
        _refresh_manifest: Any
        _set_stage_status: Any
        _stage_inputs_ready: Any
        _toast: Any
        control_stack: Any
        current_node: Any
        current_stage: Any
        imposition_active: Any
        imposition_effective: Any
        pdf_page_count: Any
        process: Any
        source_path: Any
        store: Any
        task_id: Any

    def _run_stage_unchecked(self, resume: bool = False) -> None:
        """启动当前阶段的 worker 子进程（不含执行权守卫，勿直接调用）。

        resume=True 表示续跑：extract 只补缺失页、其余阶段跳过已有输出，
        否则 clean=True 全量重跑。会取面板参数、写运行配置、起子进程并连接
        输出/错误/完成信号，再挂看门狗兜底 Windows 偶发的 finished 丢失。
        """
        if not self.task_id or not self._stage_inputs_ready():
            # ⚠️ **聚合任务**：它的输入是创建时按成员顺序汇集进来的（见
            #    ``services/aggregate_ingest``），不是用户上传的、也没有上游
            #    可以"先跑完"。缺输入只有两种真实原因，必须说准，否则用户会
            #    被引去点一个不存在的按钮/反复重跑不存在的上游。
            if self._is_aggregate_task():
                if self._aggregate_pending():
                    self._toast(
                        "info",
                        "聚合输入正在汇集",
                        "正在把各成员任务在起始节点上的输入与产出复制进来，"
                        "请稍候再执行。",
                    )
                else:
                    self._toast(
                        "warning",
                        "聚合输入不完整",
                        "成员任务在起始节点上没有可复制的图。请先确认各成员"
                        "任务这一步真的跑完了，或删除本聚合任务后重新创建。",
                    )
                return
            # ⚠️ 空壳任务（创建时没选 PDF，用户 2026-10-06）说清去哪儿补，
            #    而不是"请先导入 PDF"——那听着像要去列表页重新导入。
            #
            # ⚠️⚠️ 判据是"**这一步需要的输入**齐不齐"，**不是"有没有 PDF"**
            # （用户 2026-10-06：非提取节点做第一个节点时该提醒上传图片）：
            #   · 流程第一步是 extract ⇒ 要源 PDF，没就催"补 PDF"；
            #   · 流程第一步是「检测文本框」这类不吃 PDF 的 ⇒ 输入是入口图片
            #     目录（``stages/input/``），**有图就能跑**，哪怕整个任务压根
            #     没有 PDF。此前这里写死 ``not self.source_path``，于是那种
            #     任务图都放好了也点不动（守卫比流程还严）。
            kind = self._missing_input_kind()
            if kind == "images":
                self._toast(
                    "warning",
                    "这一步需要图片",
                    "本流程第一步不吃 PDF，请点页头的图片按钮选择图片，"
                    "或把图片放进任务目录下的 stages/input。",
                )
            elif kind == "pdf":
                # ⚠️ 指页头按钮前先确认它**在**（用户 2026-10-06 规则③：
                #    输入控件只属于第一个流程节点）。「图片提取」打头时按钮
                #    才显示，那时指它没错。
                self._toast(
                    "warning",
                    "尚未选择源文件",
                    "点页头的「选择源文件」按钮为本任务补上 PDF/DjVu，之后才能执行。",
                )
            else:
                # 入口不吃 PDF 也不缺图，输入还是不齐 ⇒ 多半是上游没跑
                # （或「图片提取」被挪到了中间、此刻轮到它却没有源文件）。
                # ⚠️ 别再说"点页头的「选择 PDF」"——那种流程里按钮是藏着的
                #    （规则①③），指一个不存在的按钮就是"点了没反应"的前奏。
                self._toast(
                    "warning",
                    "这一步的输入还没就位",
                    "这一步的输入由流程上游提供：先把它的上游步骤执行完，"
                    "或到「查看 / 编辑流程」里检查连线。",
                )
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self._toast("warning", "任务进行中", "当前步骤正在执行")
            return
        stage = self.current_stage()
        task = self.store.get_task(self.task_id)
        if not task:
            self._toast("error", "任务不存在", "该任务可能已被删除，请返回列表刷新。")
            return
        # ⚠️ **状态机守卫**：这一步不在**本任务的流程图**里就别跑。
        #    界面通常已经按图隐藏了没有的步骤，但面板/快捷键/旧引用仍可能把
        #    一个"图上已删掉"的阶段递进来——那时它的输入目录没人产出，
        #    跑起来只会报"找不到输入"，不如当场说清原因（用户改了流程图之后
        #    这一条真的会中）。
        #    ⚠️ 判据是**界面格**不是节点：`detect_submit`（提交检测结果）是
        #    第二步内的第二个动作，图上通常没有它的节点，但它跟着 `detect`
        #    那一格一起活着——按节点判会把「提交」挡死。
        if stage:
            # ⚠️ effective：图里没有拼版节点时，拼版这一步本来就跳过
            scheduler = self.store.task_scheduler(
                self.task_id, self.imposition_effective()
            )
            live_steps = {STAGE_STEP.get(s, s) for s in scheduler.stages}
            if STAGE_STEP.get(stage, stage) not in live_steps:
                self._toast(
                    "warning",
                    "这一步不在流程里",
                    f"当前任务的流程图里没有「{STAGE_LABELS.get(stage, stage)}」，"
                    "请先在「查看/编辑流程」里把它加回来。",
                )
                return
        if stage == "rembg":
            # 正式执行开始：实时台账作废（本步会按逐张偏移表重写**全部**页）。
            self._drop_live_results()
        if stage == "extract" and (
            self.source_path is None or not Path(self.source_path).exists()
        ):
            # self.source_path 已是任务目录里的备份（见 page.set_task）；
            # ⚠️ 空壳任务（还没补 PDF）source_path 为 None，一并按缺失处理
            self._toast("error", "PDF 缺失", f"任务备份 PDF 不存在：{self.source_path}")
            return

        panel: Any = self.control_stack.currentWidget()
        try:
            args = panel.get_args()
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        if stage == "extract":
            args["input"] = str(self.source_path)
            args["output"] = str(
                self.store.node_or_stage_output(
                    self.task_id, self.current_node(), "extract"
                )
            )
            if resume:
                missing = missing_extract_pages_spec(
                    self.store.node_or_stage_output(
                        self.task_id, self.current_node(), "extract"
                    ),
                    self.pdf_page_count or 0,
                )
                if not missing:
                    self._toast("info", "无需续跑", "提取输出已完整。")
                    return
                args["pages"] = missing
                args["clean"] = False
        elif stage == "print":
            # print：左侧列表顺序即 PDF 页序。图片就是第三步「图片去底色」
            # 落盘的成品图（非拼版 stages/rembg、拼版 stages/imposition），
            # 不在这一步重新合成（裁图/透明底已在前面的步骤兑现）。
            #
            # ⚠️ 拼版生效时**取图来源换到 stages/imposition**（见
            #    ImpositionMixin.print_source_dir）：这里先保证拼版成品是
            #    最新版面——2026-10-12 改造：磁盘成品已覆盖落盘版面就直接
            #    跳过（旧版每次点击都在 GUI 主线程全量重合成，点「生成PDF」
            #    界面立刻冻结）；真要合成时也转后台线程 + 事件循环等待，
            #    界面保持响应（详见 _compose_imposition_now 的说明）。
            self._compose_imposition_now()
            entries, doc = self._print_entries()
            entries = [e for e in entries if Path(e["file"]).exists()]
            effects = self._build_print_effects(entries)
            # ⚠️ 2026-10-22：去底色不再有 border，「上游 border 级联第四步默认
            #    边距」这件事随之结束——第四步保持自己的默认边距（20mm）。
            #    参数名保留（CLI 契约），恒为 None。
            args["upstream_border"] = None
            if not effects:
                # ⚠️ 提示要按**当前取图来源**给：启用拼版后列表为空，原因是
                # 「还没拼版」，而不是「第三步没提交」——照旧文案会把人引去
                # 第三步反复重跑，解决不了问题（用户 2026-10-03）。
                if self.imposition_active() and not self.imposition_effective():
                    # 勾了但**当前用不上**（流程图里没这一步）：
                    # ⚠️ 别说成"第三步没提交"——那会把人引去第三步反复重跑，
                    #    解决不了问题（正是用户 2026-10-03 报过的那类误导）
                    _usable, reason = self._imposition_switch_state()
                    self._toast("warning", "拼版当前用不上", reason)
                    return
                if self.imposition_effective():
                    self._toast(
                        "warning",
                        "没有拼版页",
                        "已启用「图片拼版」，但拼版清单是空的。请先回到"
                        "「图片拼版」点「＋ 选择拼版」，或取消勾选"
                        "「在流程中启用图片拼版」改用去底色图片。",
                    )
                    return
                self._toast(
                    "warning",
                    "无输入页面",
                    "待打印列表为空，请先在第三步「图片去底色」生成成品图，"
                    "或在左侧列表插入图片。",
                )
                return
            doc["pages"] = [
                ordered_page_record(e) for e in entries
            ]
            self.store.save_print_doc(self.task_id, doc, **self._node_scope())
            args["_effects"] = effects
            # 记下**本次取图来源**（rembg / imposition）。这是"旧数据"
            # 判定的依据：用户随后改了拼版开关，磁盘上这份 PDF 就属于上一轮
            # 来源的产物，界面据此停止提供下载/预览并提示重新生成
            # （见 services/stale_chain.print_source_switched）。
            # ⚠️ 用阶段 key 而不是布尔：BPM 换连线时这个值自动跟着变，
            # 不必再为"多了一个上游"改判定逻辑。
            # ⚠️ 前缀不带下划线是为了**留在 runs.json 历史里**（入史只剥
            # _effects/files/page_rects 这几个大块派生字段）；它不是 CLI 参数，
            # 只由 GUI 侧读取。
            # ⚠️ 走 store.node_supplier（**按图求解**）：直接查端口级边表会
            #    在"流程里没有去底色"这类自定义流程下指向不存在的产物目录。
            #    ⚠️ **按节点求解**（B 方案）：同一步骤的多个节点各有自己的上游，
            #    按阶段查会把副本节点的来源记成主节点的（"旧数据"判定跟着错）。
            _print_node = self.current_node()
            args["source_stage"] = (
                self.store.node_supplier_stage(
                    self.task_id, _print_node, "pages", self.imposition_effective()
                )
                if _print_node
                else self.store.stage_supplier(
                    self.task_id, "print", "pages", self.imposition_effective()
                )
            )
            # 取图目录的**内容标记**（目录 + 内容指纹），与 source_stage 一并落进
            # 执行记录：来源阶段没换、但目录内容变了（图片拼版删页 ⇒ 成品页
            # 重新编号重存）时，第四步那份旧 PDF 同样不该再被当成结果。
            # 判据见 services/stale_chain.print_input_changed。
            args["source_mark"] = self._print_source_mark_text()
            # 有序清单即页序：拖拽重排只改 print.json，不再物化任何文件。
            # input 仅供 CLI 作默认目录兜底，实际顺序由 files 决定。
            args["files"] = [str(Path(e["file"])) for e in entries]
            # 逐图坐标覆盖：把版面编辑器里记录的 rect 按 1-based 页序注入，
            # 生成 PDF 时直接作图片框（所见即所得），未编辑的页走自动排版。
            page_rects = {
                i + 1: list(e["rect"])
                for i, e in enumerate(entries)
                if e.get("rect") is not None
            }
            if page_rects:
                args["page_rects"] = page_rects
            # 逐图旋转覆盖：{页号(1-based): 角度}（float，顺时针为正）。
            # 与 page_rects 同源（版面编辑器里旋转后一起落进 pages[].rotate），
            # PDF 侧据此先转位图再贴进同一个框——「预览看到的方向 = 成品方向」。
            page_rotations = {
                i + 1: float(e.get("rotate") or 0)
                for i, e in enumerate(entries)
                if e.get("rotate")
            }
            if page_rotations:
                args["page_rotations"] = page_rotations
            args["input"] = str(self.store.task_dir(self.task_id))
            # ⚠️ 输出目录按**节点**取（B 方案）：两个「PDF排版」节点各自出 PDF，
            #    共用 stages/print 就会互相覆盖（默认 PDF 名都从源 PDF 名派生）。
            #    主节点仍是 stages/print（零迁移），副本是 stages/print~<节点>。
            args["output"] = str(
                self.store.scoped_stage_dir(self.task_id, _print_node, "print")
            )
            # 开始重新生成即清除「版面已修改」标脏
            self._print_dirty = False
            try:
                # ⚠️ 必须走 _set_stage_status（不能只 setText）：状态行是同一个
                # QLabel 被三处共用，只改文字不重置颜色的话，上一条"过期提示"的
                # 红字会留在这里（见 page.py::_set_stage_status）。
                self._set_stage_status("未执行")
            except Exception:
                pass
            self._logs.append_now(
                (
                    f"图片拼版：{len(effects)} 页（PDF排版用拼版结果）"
                    if self.imposition_effective()
                    else f"PDF排版：{len(effects)} 页"
                    "（用第二步「分割图片」的成品图）"
                )
            )
        else:
            self._refresh_manifest()
            if not self._manifest_paths():
                # ⚠️ 别说"请先完成上一步"——流程里可能**没有**上一步
                #    （自定义流程把这一步放在第一位，用户 2026-10-06 报障）。
                #    那时唯一说得通、也真能解决问题的出路就是"放图进来"。
                self._toast(
                    "warning",
                    "无输入页面",
                    "这一步还没有可处理的图片：点左侧列表下方的「＋」插入图片，"
                    "或把图片放进本任务的输入目录后重试。",
                )
                return
            # detect/rembg 都是逐图独立处理（不依赖顺序与命名），直接以
            # extract 输出目录为输入，不再物化 workset 副本。
            #
            # ⚠️ 这里问的是「这一步的 pages 端口在哪」而不是「提取的目录在哪」
            #    （:mod:`desktop.steps.ports` 按连线解析）：将来 BPM 把 extract
            #    换到别的环节、或让 rembg 直接吃拼版的图，都只改 ports 的连线表，
            #    这一行不用动。
            # ⚠️ **按节点问**（B 方案）：同一步骤的多个节点各有自己的上游，
            #    按阶段问会让副本节点吃到主节点的输入图（"跑的是 B、图是 A 的"）。
            node = self.current_node()
            pages_input = (
                self.store.node_input(
                    self.task_id, node, "pages", self.imposition_effective()
                )
                if node
                else self.store.stage_input(self.task_id, stage, "pages")
            )
            if pages_input is None:
                self._toast(
                    "error",
                    "输入未接好",
                    f"{STAGE_LABELS.get(stage, stage)} 的图片输入没有连线，"
                    "请检查流程配置。",
                )
                return
            args["input"] = str(pages_input)
            if stage == "rembg":
                # 去底色只有一步：成品图固定写入 ``stages/rembg``（副本节点
                # 写到它自己的 ``stages/rembg~<节点>``）。
                # rembg CLI 会自行追加 "rembg" 子目录，故用 _outpath 精确覆盖。
                self._flush_pending_offset()
                args["_outpath"] = str(
                    self.store.node_or_stage_output(
                        self.task_id, node, "rembg"
                    )
                )
                # 逐张图片的 offset（黑名单法）：用户单独调过的图片按自己的值
                # 去底色，没调过的沿用面板当前值（默认 0）。
                args["offsets"] = self.store.load_rembg_offsets(
                    self.task_id, **self._node_scope(node)
                )
                # 逐张算法覆盖（白名单法）：用户单独改过算法的页按自己的值，
                # 没记录的页用面板上的 ``args["algorithm"]``（全量默认算法）。
                args["algorithms"] = self.store.load_rembg_algorithms(
                    self.task_id, **self._node_scope(node)
                )
                # 当前去底色节点沿流程往前最近的 detect 提交计划：全局算法要
                # 按「同页左右裁图」合并阈值（用户 2026-10-25 口径）。没有
                # 上游 detect（自定义流程/独立模块）时为空，回落逐图计算。
                boxes_path = self.store.nearest_boxes_path(
                    self.task_id, node, self.imposition_effective()
                )
                if boxes_path is not None:
                    args["_boxes_path"] = str(boxes_path)
            else:
                # detect 的输出目录解析会在 output 后追加默认子目录名（detect）
                args["output"] = str(self.store.task_dir(self.task_id) / "stages")
            args["clean"] = not resume

        if stage == "print":
            # 记录最近一次执行的表单参数（供面板「重置」恢复）
            try:
                panel.mark_applied(args)
            except Exception:
                pass

        self._launch_stage_process(stage, args, resume)
