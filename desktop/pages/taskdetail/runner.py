# -*- coding: utf-8 -*-
"""任务详情页的阶段执行控制器：构建参数、启动 worker 子进程、解析进度日志。

纯业务派生规则见 desktop/services/print_plan.py，
rembg 提交控制器见 desktop/pages/taskdetail/submit.py，
历史配置回填见 desktop/pages/taskdetail/history.py。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer

from desktop.services.print_plan import missing_extract_pages_spec
from desktop.steps.process import StageProcess, worker_arguments
from desktop.store.json_io import write_json
from desktop.utils.files import list_stage_images, project_root
from desktop.store import IMPOSITION_STAGE, STAGE_LABELS, STAGE_STEP

from utils.box_geometry import page_box_slots_from_event


STATUS_LABELS = {
    "pending": "未执行",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "cancelled": "已中断",
}


class StageRunnerMixin:
    """依赖宿主页面提供的属性：store/task_id/source_path/pages、
    control_stack、stage_* 控件、log_view、process/run_id 等。"""

    #: 进度事件的**界面刷新合并窗口**(ms)。
    #:
    #: ⚠️ 为什么必须合并：extract 每渲染完一页就发一条 progress 事件，一本 100 页
    #: 的书就是 100 条。每条都去做「写 runs.json + 重建步骤条 + 重建提取结果缩略图
    #: 条」是几十毫秒级的重活（实测 GUI 每秒只吃得下十几条），GUI 于是远远落在
    #: worker 后面。后果有两个：界面明显发卡；更严重的是**进程退出时管道里还压着
    #: 一大批没读的事件**，收尾时被一并丢掉 —— 历史里留下「成功 done=14/total=84」、
    #: 日志缺「处理完成」那行，用户看到的就是"像被中断了/只提取了一半"。
    #: 进度条与状态文字仍逐条即时更新（纯内存操作，便宜）。
    _PROGRESS_UI_MS = 200

    #: 「多少秒没有任何 worker 输出」就提醒用户可能卡住（只提醒，不自动杀）。
    #: ⚠️ 真正的实现与判定在 ``desktop.steps.process.StageProcess``
    #: （``STALL_WARN_S``）——那里是"看门狗"的归属地；本页只负责把提醒
    #: 画到日志与状态行上（见 :meth:`_on_stage_stalled`）。
    #: 页面尺寸/检测框的攒批落盘间隔（ms）。逐条落盘在 320 页上累计 3.1 秒
    #: 主线程阻塞（见 _store_page_size / _store_stage_boxes 的说明）。
    _ANNOT_FLUSH_MS = 400

    def _init_progress_ui(self) -> None:
        """建进度刷新节流器（宿主页面 __init__ 里调一次，须在 _init_ui 之后）。"""
        self._progress_ui_timer = QTimer(self)
        self._progress_ui_timer.setSingleShot(True)
        self._progress_ui_timer.setInterval(self._PROGRESS_UI_MS)
        self._progress_ui_timer.timeout.connect(self._flush_progress_ui)
        self._progress_dirty = False

    def _flush_progress_ui(self) -> None:
        """把合并掉的进度落盘并刷新步骤条 / 提取结果（收尾时也必须调一次）。"""
        if self._progress_ui_timer.isActive():
            self._progress_ui_timer.stop()
        if not self._progress_dirty:
            return
        self._progress_dirty = False
        if self.task_id and self.run_id:
            done, total = self._last_progress
            if total:
                self.store.set_progress(self.task_id, self.run_id, done, total)
        self._refresh_stage_views()
        if self.running_stage == "extract":
            self._poll_extract_results()

    # ---------------------------------------------------- 进度该显示在哪一步
    def _step_of_stage(self, stage: str | None) -> str | None:
        """运行阶段 → 它归属的界面步骤（``rembg_submit`` 归第三步，见 STAGE_STEP）。"""
        if not stage:
            return None
        return STAGE_STEP.get(stage, stage)

    def _progress_belongs_here(self, stage: str | None) -> bool:
        """这条进度是否该画在**当前显示的这一步**上。

        ⚠️ 进度条与状态文字是**全页面共享**的一份控件，必须只服务当前这一步。
        以前无条件更新，于是第三步「提交本次任务」的进度被画在第四步的界面上：
        走动的进度条 +「进度 42/91」+ 灰掉的「生成PDF」按钮 —— 看起来就像第四步
        在自己生成 PDF（用户报的「在第三步提交，然后进第四步，pdf 在生成过程中」）。

        跨步骤的进度一律不上屏：想知道它还在跑，看「中断」按钮点得亮、日志在滚。
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
        if not self._acquire_run("子任务"):
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
        """**当前这一步**的输入齐不齐，可以开跑吗。

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

        所以判据走 :meth:`~desktop.store.tasks.TaskRepo.required_stage_inputs`
        （= :func:`desktop.steps.ports.stage_blocking_inputs`）：只查**这张图上
        确实阻塞**的端口，逐个解析出路径并确认存在。
        """
        stage = self.current_stage()
        if not self.task_id or stage is None:
            return False
        for port in self.store.required_stage_inputs(
            self.task_id, stage, self.imposition_effective()
        ):
            path = self.store.stage_input(
                self.task_id, stage, port, self.imposition_effective())
            if path is None or not path.exists():
                return False
        return True

    def _run_stage_unchecked(self, resume: bool = False) -> None:
        """启动当前阶段的 worker 子进程（不含执行权守卫，勿直接调用）。

        resume=True 表示续跑：extract 只补缺失页、其余阶段跳过已有输出，
        否则 clean=True 全量重跑。会取面板参数、写运行配置、起子进程并连接
        输出/错误/完成信号，再挂看门狗兜底 Windows 偶发的 finished 丢失。
        """
        if not self.task_id or not self._stage_inputs_ready():
            # ⚠️ 空壳任务（创建时没选 PDF，用户 2026-10-06）说清去哪儿补，
            #    而不是"请先导入 PDF"——那听着像要去列表页重新导入。
            #
            # ⚠️⚠️ 判据是"**这一步需要的输入**齐不齐"，**不是"有没有 PDF"**
            #（用户 2026-10-06：非提取节点做第一个节点时该提醒上传图片）：
            #   · 流程第一步是 extract ⇒ 要源 PDF，没就催"补 PDF"；
            #   · 流程第一步是「检测文本框」这类不吃 PDF 的 ⇒ 输入是入口图片
            #     目录（``stages/input/``），**有图就能跑**，哪怕整个任务压根
            #     没有 PDF。此前这里写死 ``not self.source_path``，于是那种
            #     任务图都放好了也点不动（守卫比流程还严）。
            kind = self._missing_input_kind()
            if kind == "images":
                self._toast(
                    "warning", "这一步需要图片",
                    "本流程第一步不吃 PDF，请点页头的图片按钮选择图片，"
                    "或把图片放进任务目录下的 stages/input。",
                )
            elif kind == "pdf":
                # ⚠️ 指页头按钮前先确认它**在**（用户 2026-10-06 规则③：
                #    输入控件只属于第一个流程节点）。「图片提取」打头时按钮
                #    才显示，那时指它没错。
                self._toast(
                    "warning", "尚未选择 PDF",
                    "点页头的「选择 PDF」按钮为本任务补上源文件，之后才能执行。",
                )
            else:
                # 入口不吃 PDF 也不缺图，输入还是不齐 ⇒ 多半是上游没跑
                # （或「图片提取」被挪到了中间、此刻轮到它却没有源文件）。
                # ⚠️ 别再说"点页头的「选择 PDF」"——那种流程里按钮是藏着的
                #    （规则①③），指一个不存在的按钮就是"点了没反应"的前奏。
                self._toast(
                    "warning", "这一步的输入还没就位",
                    "这一步的输入由流程上游提供：先把它的上游步骤执行完，"
                    "或到「查看 / 编辑流程」里检查连线。",
                )
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            self._toast("warning", "任务进行中", "当前子任务正在执行")
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
        #    ⚠️ 判据是**界面格**不是节点：`rembg_submit`（提交去底色结果）是
        #    第三步内的第二个动作，图上通常没有它的节点，但它跟着 `rembg`
        #    那一格一起活着——按节点判会把「提交」挡死。
        if stage:
            # ⚠️ effective：区域模式不支持拼版时，拼版这一步本来就跳过
            scheduler = self.store.task_scheduler(
                self.task_id, self.imposition_effective()
            )
            live_steps = {STAGE_STEP.get(s, s) for s in scheduler.stages}
            if STAGE_STEP.get(stage, stage) not in live_steps:
                self._toast(
                    "warning", "这一步不在流程里",
                    f"当前任务的流程图里没有「{STAGE_LABELS.get(stage, stage)}」，"
                    "请先在「查看/编辑流程」里把它加回来。",
                )
                return
        if stage == "extract" and not Path(self.source_path).exists():
            # self.source_path 已是任务目录里的备份（见 page.set_task）
            self._toast(
                "error", "PDF 缺失", f"任务备份 PDF 不存在：{self.source_path}"
            )
            return

        panel = self.control_stack.currentWidget()
        try:
            args = panel.get_args()
        except ValueError as exc:
            self._toast("error", "参数错误", str(exc))
            return
        if stage == "extract":
            args["input"] = str(self.source_path)
            args["output"] = str(self.store.stage_dir(self.task_id, "extract"))
            if resume:
                missing = missing_extract_pages_spec(
                    self.store.extract_output_dir(self.task_id),
                    self.pdf_page_count or 0,
                )
                if not missing:
                    self._toast("info", "无需续跑", "提取输出已完整。")
                    return
                args["pages"] = missing
                args["clean"] = False
        elif stage == "print":
            # print：左侧列表顺序即 PDF 页序。图片就是第三步「提交本次任务」
            # 落盘的成品图（非拼版 stages/rembg、拼版 stages/imposition），
            # 不在这一步重新合成——area/border 已在提交时兑现（用户
            # 2026-10-01：「去底色那一步，必须提交才能传给下一步」）。
            #
            # ⚠️ 拼版生效时**取图来源换到 stages/imposition**（见
            #    ImpositionMixin.print_source_dir）：这里先同步补一次合成，
            #    保证 PDF 用的拼版版面是最新的——用户改完版面立刻点
            #    「生成 PDF」时，后台那轮防抖合成可能还没跑完。
            self._compose_imposition_now()
            entries, doc = self._print_entries()
            entries = [e for e in entries if Path(e["file"]).exists()]
            rembg_panel = self.panel_host_of_step("rembg")
            try:
                # ⚠️ 流程里没有「图片去底色」这一格时没有面板可读——那就不做
                #    border 级联（``upstream_border`` 留 None），而不是去借
                #    任意一个面板的 border 填进来（界面说 A、执行做 B）。
                rargs = rembg_panel.get_args() if rembg_panel else {}
            except ValueError as exc:
                self._toast("error", "去底色参数错误", str(exc))
                return
            border = rargs.get("border")
            effects = self._build_print_effects(entries)
            # 第三步 border 级联第四步默认边距：把上游 border 透传给 print，
            # 让其「通用边距默认」在 border 非 0 时回落为 0（避免双重留白）。
            args["upstream_border"] = border
            if not effects:
                # ⚠️ 提示要按**当前取图来源**给：启用拼板后列表为空，原因是
                # 「还没拼版」，而不是「第三步没提交」——照旧文案会把人引去
                # 第三步反复重跑，解决不了问题（用户 2026-10-03）。
                if self.imposition_active() and not self.imposition_effective():
                    # 勾了但**当前用不上**（流程图里没这一步 / 区域模式不支持）：
                    # ⚠️ 别说成"第三步没提交"——那会把人引去第三步反复重跑，
                    #    解决不了问题（正是用户 2026-10-03 报过的那类误导）
                    _usable, reason = self._imposition_switch_state()
                    self._toast("warning", "拼版当前用不上", reason)
                    return
                if self.imposition_effective():
                    self._toast(
                        "warning", "没有拼版页",
                        "已启用「图片拼版」，但拼版清单是空的。请先回到"
                        "「图片拼版」点「＋ 选择拼版」，或取消勾选"
                        "「在流程中启用图片拼版」改用去底色图片。",
                    )
                    return
                self._toast(
                    "warning", "无输入页面",
                    "待打印列表为空，请先在第三步「生成预览」（必要时「提交"
                    "本次任务」选页），或在左侧列表插入图片。",
                )
                return
            doc["pages"] = [
                (
                    {"file": e.get("file"), "label": e.get("label"),
                     "rect": e["rect"]}
                    if e.get("rect") is not None
                    else {"file": e.get("file"), "label": e.get("label")}
                )
                for e in entries
            ]
            self.store.save_print_doc(self.task_id, doc)
            args["_effects"] = effects
            # 记下**本次取图来源**（rembg_submit / imposition）。这是"旧数据"
            # 判定的依据：用户随后改了拼版开关，磁盘上这份 PDF 就属于上一轮
            # 来源的产物，界面据此停止提供下载/预览并提示重新生成
            # （见 services/stale_chain.print_source_switched）。
            # ⚠️ 用阶段 key 而不是布尔：BPM 换连线时这个值自动跟着变，
            # 不必再为"多了一个上游"改判定逻辑。
            # ⚠️ 前缀不带下划线是为了**留在 runs.json 历史里**（入史只剥
            # _effects/files/page_rects 这几个大块派生字段）；它不是 CLI 参数，
            # 只由 GUI 侧读取。
            # ⚠️ 走 store.stage_supplier（**按图求解**）：直接查端口级边表会
            #    在"流程里没有去底色"这类自定义流程下指向不存在的产物目录。
            args["source_stage"] = self.store.stage_supplier(
                self.task_id, "print", "pages", self.imposition_effective()
            )
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
            args["input"] = str(self.store.task_dir(self.task_id))
            args["output"] = str(self.store.stage_dir(self.task_id, "print"))
            # 开始重新生成即清除「版面已修改」标脏
            self._print_dirty = False
            try:
                # ⚠️ 必须走 _set_stage_status（不能只 setText）：状态行是同一个
                # QLabel 被三处共用，只改文字不重置颜色的话，上一条"过期提示"的
                # 红字会留在这里（见 page.py::_set_stage_status）。
                self._set_stage_status("未执行")
            except Exception:
                pass
            self.log_view.append(
                (
                    f"图片拼版：{len(effects)} 页（生成 PDF 用拼版结果）"
                    if self.imposition_effective() else
                    f"生成 PDF：{len(effects)} 页"
                    "（用第三步「提交本次任务」的成品图）"
                )
            )
        else:
            self._refresh_manifest()
            if not self._manifest_paths():
                # ⚠️ 别说"请先完成上一步子任务"——流程里可能**没有**上一步
                #    （自定义流程把这一步放在第一位，用户 2026-10-06 报障）。
                #    那时唯一说得通、也真能解决问题的出路就是"放图进来"。
                self._toast(
                    "warning", "无输入页面",
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
            pages_input = self.store.stage_input(self.task_id, stage, "pages")
            if pages_input is None:
                self._toast(
                    "error", "输入未接好",
                    f"{STAGE_LABELS.get(stage, stage)} 的图片输入没有连线，"
                    "请检查流程配置。",
                )
                return
            args["input"] = str(pages_input)
            if stage == "detect":
                # 整页模式（area=4）：区域参数归第三步面板所有，detect 只是
                # 借来判定「要不要加载 YOLO」，worker 侧据此整页跳过检测。
                # ⚠️ 借的面板按**流程**找，不是 ``widget(2)``：自定义流程里
                #    「图片去底色」可能压根不在图上，此时给默认 1（照常检测），
                #    别把一个用户没填过的表单当参数传进 worker。
                rembg_host = self.panel_host_of_step("rembg")
                args["area"] = int(
                    rembg_host.get_args().get("area", 1) if rembg_host else 1
                )
            if stage == "rembg":
                # 「生成预览」整页去底图固定写入 stages/rembgpreview；
                # rembg CLI 会自行追加 "rembg" 子目录，故用 _outpath 精确覆盖
                args["_outpath"] = str(
                    self.store.rembg_preview_output_dir(self.task_id)
                )
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

    def _launch_stage_process(self, stage: str, args: dict, resume: bool = False) -> None:
        """写入运行配置并启动 worker 子进程。"""
        self.run_id = self.store.create_stage_run(self.task_id, stage, args, resume)
        runs_dir = self.store.runs_config_dir(self.task_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / f"run-{self.run_id}.json"
        write_json(
            config_path,
            {"task_id": self.task_id, "stage": stage, "run_id": self.run_id, "args": args},
        )
        self.cancel_requested = False
        self.running_stage = stage
        self._last_error_line = None
        # 最近一次 progress 事件 (done, total)：worker 结束时不带计数，
        # 用它把最终进度落到历史记录里（见 _worker_finished）。
        self._last_progress = (0, 0)
        # 半行缓冲/进度合并都是**每次运行**的临时状态，别把上一次的残留带过来
        # （"无进展计时"的临时状态已随看门狗搬进传输层，不在这里）
        self._stdout_tail = ""
        self._progress_dirty = False
        self._progress_ui_timer.stop()
        # 本步**自己**的活儿：立刻显示"执行中"并把进度归零 —— 第一个 progress
        # 事件到达之前（torch 冷启动可达数秒）不该继续挂着上一次的「成功 91/91」。
        # 跨步骤启动（在别的步骤点了按钮）则一个像素都不动：那一步的进度条与
        # 文案不该被这一步的活儿改写（见 _progress_belongs_here）。
        if self._progress_belongs_here(stage):
            self.stage_progress.setRange(0, 1)
            self.stage_progress.setValue(0)
            # 走 _set_stage_status 而不是 setText：颜色要跟着回到常规色，
            # 否则上一条"上游已重跑/版面已修改"的红字会留在「执行中」上
            self._set_stage_status(
                f"{STAGE_LABELS[stage]}：{STATUS_LABELS['running']}"
            )
        if stage == "extract":
            self._extract_seen = len(
                list_stage_images(self.store.extract_output_dir(self.task_id))
            )
        # ---- 传输层：起进程 + 读字节流 + 看门狗（实现见 desktop.steps.process）----
        # ⚠️ 这里只接"业务"需要的信号；半行重组 / JSON 解析 / 落盘仍在本页——
        #    它们写 runs.json、boxes.json 与日志视图，是**页面**的事，
        #    放进传输层会让那一层重新长出"任务流程"的触手、也就没法复用了。
        # 上一次运行的传输层已经收尾（能走到这里说明没有进程在跑），顺手回收，
        # 免得一场会话跑几十次就攒几十个对象。
        previous = getattr(self, "_stage_transport", None)
        if previous is not None:
            previous.deleteLater()
        transport = StageProcess(self)
        transport.stdout.connect(self._on_stage_stdout)
        transport.stderr.connect(self._consume_worker_stderr)
        transport.process_error.connect(self._worker_error_occurred)
        transport.stalled.connect(self._on_stage_stalled)
        transport.unclean_exit.connect(self._on_stage_unclean_exit)
        transport.finished.connect(self._on_stage_finished)
        self._stage_transport = transport
        self.process = transport.start(
            sys.executable,
            worker_arguments(config_path),
            # 打包环境主程序即入口，工作目录随意；源码环境必须是项目根
            # （能解析出 desktop 包的那一级）
            workdir=None if getattr(sys, "frozen", False) else project_root(),
        )
        # 进程真的起来了 → 防抖窗口从这里开始计时（见 _run_launched_at）
        self._mark_run_launched()

        self.store.update_task(self.task_id, "running")
        self._refresh_stage_views()
        # 开始执行时自动展开日志：用户此刻最需要看到实时输出
        self.log_panel.set_expanded(True)
        self.log_view.append(
            f"=== 开始执行 {STAGE_LABELS[stage]}{'（续跑）' if resume else ''} ==="
        )

    def cancel_stage(self) -> None:
        """中断正在执行的阶段：先落 cancelled 再 kill 子进程。

        先立即把运行记录置为 cancelled——防止进程被强杀来不及回调时状态永远
        停留 running（重启后按钮状态错乱）；随后置 cancel_requested 并 kill。
        """
        if self.process and self.process.state() != QProcess.NotRunning:
            self.cancel_requested = True
            self._set_stage_status("正在中断子任务...")
            self.log_view.append("已请求中断，正在终止子任务进程...")
            # 立即把运行记录置为已中断：进程被强杀来不及回调时，
            # 状态不会永远停留在 "running"（否则重启后按钮状态是错的）
            if self.run_id:
                self.store.finish_stage(self.task_id, self.run_id, "cancelled")
            self.process.kill()
            # kill 是 TerminateProcess：worker 里的 `finally`/`with` 都不会执行，
            # 「生成 PDF」的效果图暂存目录（整页 PNG，几百 MB~GB）会留在 %TEMP%。
            # 这里立刻扫一次（按属主 pid 判死活），不等下一次生成 PDF 才回收。
            try:
                from desktop.stages import sweep_orphan_staging

                sweep_orphan_staging()
            except Exception:  # noqa: BLE001 - 回收是尽力而为，不能影响中断
                pass

    # ---------------------------------------------------------- 输出解析
    def _on_stage_stdout(self, data: bytes) -> None:
        """传输层转来一批 stdout 原始字节：交给解析层（半行重组在这里）。

        ⚠️ "有输出就算有进展"的计时与提醒标志由传输层维护（见
        ``StageProcess._on_stdout``）——那是看门狗自己的状态。
        """
        self._consume_worker_stdout(data)

    def _on_stage_stalled(self, minutes: float) -> None:
        """传输层报"很久没有任何输出"：写日志 + 状态行（只提醒，不自动杀）。

        ⚠️ 为什么只提醒不自动杀（2026-09-26 审计）：worker 卡死（死锁、等
        常驻 YOLO 服务、torch 卡住、管道反压）与**合法的慢阶段**（2400 页的
        去底色/生成 PDF）在外部看是一样的——都只是"没输出"。自动杀掉会把
        用户跑了几分钟的正常任务误杀，代价远大于收益。所以这里只把
        "已经 N 分钟没有任何进展"摆到用户面前，让**他**决定要不要点中断。
        """
        self.log_view.append(
            f"[看门狗] 已 {minutes:.0f} 分钟没有任何进度输出，"
            "若确认卡住可点「中断」或关闭窗口。"
        )
        self._set_stage_status(
            f"已 {minutes:.0f} 分钟无进展（可能卡住，可中断重试）"
        )

    def _on_stage_unclean_exit(self) -> None:
        """传输层报"进程已退出但 Qt 没能正常收尾"：记成失败原因（看门狗兜底）。"""
        self.log_view.append("[看门狗] 子任务进程已退出但未正常收尾，按失败处理")
        self._last_error_line = "子任务进程未正常收尾（看门狗兜底）"

    def _on_stage_finished(self, exit_code: int, status) -> None:
        """传输层报"进程结束"（**保证只发一次**）→ 走页面收尾链。"""
        self._worker_finished(exit_code, status)

    def _consume_worker_stdout(self, data: bytes, final: bool = False) -> None:
        """解析 worker 输出的 JSON Lines 事件。

        ``final=True`` 用于收尾的最后一次读取：此时把残留的半行也当完整行
        处理，别让它永远留在缓冲区里。

        ⚠️ **必须做半行重组**：管道读取会在任意字节处截断，一条 JSON 事件被劈成
        两半时 ``json.loads`` 必然失败、整条事件被降级成"人读日志"丢掉 ——
        表现就是"进度偶尔少一条"。所以留一个尾巴，等下一批字节拼回来。
        """
        text = self._stdout_tail + data.decode("utf-8", errors="replace")
        if final:
            self._stdout_tail = ""
            lines = text.splitlines()
        else:
            lines = text.split("\n")
            tail = lines.pop()  # 末段可能不完整，留给下一批
            # ⚠️ 只有「看起来是半条 JSON 事件」的余量才值得留到下一批拼回来。
            # 协议外的裸 print（没有换行的库输出）一旦被留下，下一条真正的事件
            # 会被拼到它后面、一起解析失败 —— 那就从"丢半条"变成"丢一条"。
            # 所以非 JSON 的余量立刻当人读日志收掉。
            if tail and not tail.lstrip().startswith("{"):
                if tail.strip():
                    self.log_view.append(tail)
                tail = ""
            self._stdout_tail = tail
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # 非 JSON 行：worker 侧已用 ProgressStream 拦下大部分库输出，
                # 这里是最后的兜底（协议外的裸 print / 半行撕裂）。当日志收下，
                # 总比静默丢掉让用户「日志里什么都没有」要好。
                if line.strip():
                    self.log_view.append(line)
                continue
            etype = event.get("type")
            if etype == "progress":
                self._on_worker_progress(event)
            elif etype == "log":
                self.log_view.append(event.get("message", ""))
            elif etype == "page_boxes":
                self._store_stage_boxes(event)
            elif etype == "page_size":
                self._store_page_size(event)
            elif etype == "started":
                self.log_view.append(f"子任务进程已启动：{STAGE_LABELS.get(event.get('stage'), event.get('stage'))}")
            elif etype == "error":
                # ⚠️ 结构化 error 事件是 worker 侧**最准确的失败原因**（stage 自己发的，
                # 比 stderr 里那行启发式匹配可靠）。必须同时记进 _last_error_line：
                # 只写日志的话，历史记录与失败弹窗只会显示「退出码 1」，真因
                # （比如"没有生成任何图片，请先执行「生成预览」"）被淹在日志里，
                # 用户事后完全查不到（2026-09-26 审计发现）。
                message = event.get("message") or ""
                self.log_view.append(f"错误：{message}")
                if message.strip():
                    self._last_error_line = message.strip()
            elif etype == "cancelled":
                self.log_view.append("子任务进程已被中断。")

    def _on_worker_progress(self, event: dict) -> None:
        """一条 progress 事件：轻量部分即时上屏，重活按窗口合并。

        ⚠️ 只有**当前显示这一步**自己的进度才上屏（见 :meth:`_progress_belongs_here`）：
        共享的进度条/文案被跨步骤的进度写进去，就会让人以为"这一步在跑"。
        """
        done, total = event.get("done", 0), event.get("total", 0)
        if total and self._progress_belongs_here(event.get("stage")):
            self.stage_progress.setRange(0, total)
            self.stage_progress.setValue(min(done, total))
            self._set_stage_status(f"进度 {done}/{total}")
        # 记住最近一次进度：finish_stage 用它补齐最终计数（见 _worker_finished）
        self._last_progress = (done, total)
        # 写运行记录 / 重建步骤条 / 重建提取结果缩略图条都是重活，见 _PROGRESS_UI_MS
        self._progress_dirty = True
        if not self._progress_ui_timer.isActive():
            self._progress_ui_timer.start()

    def _drain_worker_output(self, proc) -> None:
        """收尾前把管道余量读干（含最后那条不完整的行）。

        ⚠️ 唯一调用点是 :meth:`_worker_finished`，且**必须在清 ``self.process`` /
        ``self.run_id`` 之前**：这两个引用一清，后面到达的事件就再也进不了日志
        与运行记录（大任务时 GUI 本来就落后，管道里常常还压着一批事件）。
        """
        try:
            self._consume_worker_stdout(bytes(proc.readAllStandardOutput()), final=True)
            self._consume_worker_stderr(bytes(proc.readAllStandardError()))
        except RuntimeError:
            pass  # 底层对象已析构（进程被强行收掉）

    def _store_page_size(self, event: dict) -> None:
        """extract 阶段上报的页面图片原始尺寸 → 攒批（sizes.json 是框坐标基准）。

        ⚠️ 不逐条落盘：320 页逐条「读整个 sizes.json + 写回」实测累计 **1.3 秒**
        主线程阻塞（2400 页的书记忆里是几十秒）。攒到 400ms 一次批量写。
        """
        if not self.task_id:
            return
        self._pending_sizes[event.get("image", "")] = (
            int(event.get("width", 0)), int(event.get("height", 0)),
        )
        self._annot_timer.start(self._ANNOT_FLUSH_MS)

    def _store_stage_boxes(self, event: dict) -> None:
        """detect 阶段上报的框坐标 → 攒批（origin=auto；人工框不被覆盖）。

        槽位拼装走 **共用实现**（``utils.box_geometry.page_box_slots_from_event``，
        ``utils`` 层无重依赖、主进程可直连）——独立「检测文本框」模块页读的是
        同一条通道、同一个约定，两处各写一遍必然漂移。槽位约定的含义见
        ``functions/detect.PageBoxes``（半幅 2 槽 ``[左, 右]``、整幅 1 槽
        ``[整幅]``，下游据此分辨形态）。

        ⚠️ 逐条落盘是「读 boxes.json + 写回」× 页数，320 页实测累计 **1.8 秒**
        主线程阻塞；改攒批 + 一次性写。人工框的优先级判定挪到批量写里
        （见 store.save_detect_boxes_batch），顺带省掉每条一次的文件读。
        """
        if not self.task_id:
            return
        boxes = page_box_slots_from_event(event)
        if not any(boxes):
            return
        self._pending_boxes[event.get("image", "")] = boxes
        self._annot_timer.start(self._ANNOT_FLUSH_MS)

    def _flush_annotations(self) -> None:
        """把攒下的尺寸/框一次性落盘（定时器到期、阶段收尾、切任务时都要调）。

        ⚠️ 必须在 `_worker_finished` 里调：阶段结束后下游要用 sizes.json/
        boxes.json 做坐标基准，攒着不写会让下一阶段读到旧数据。
        """
        if self._annot_timer.isActive():
            self._annot_timer.stop()
        sizes, self._pending_sizes = self._pending_sizes, {}
        boxes, self._pending_boxes = self._pending_boxes, {}
        if not self.task_id:
            return
        try:
            if sizes:
                self.store.save_image_sizes_batch(self.task_id, sizes)
            if boxes:
                self.store.save_detect_boxes_batch(self.task_id, boxes)
                # detect 批量检测中：落了一批框 → 右侧统计跟着实时重算
                # （boxes.json 一次读盘 ~1ms，400ms 一次可忽略）
                if self.current_stage() == "detect" \
                        and self.detect_stats.isVisible():
                    self._refresh_detect_stats()
        except Exception as exc:  # noqa: BLE001 - 落盘失败不该打断阶段收尾
            # ⚠️ 但不能**静默**吞掉（2026-09-26 审计）：磁盘满 / 任务目录被删 /
            # 权限异常时，下游（去底色、打印）会按**缺失的坐标基准**算错布局，
            # 而界面上一点提示都没有。这里做三件事：告警、记成失败原因、把数据
            # 放回去等下次 flush 再试一次（否则这批攒好的框就永久丢了）。
            message = f"页框/尺寸落盘失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._last_error_line = message
            for key, value in sizes.items():
                self._pending_sizes.setdefault(key, value)
            for key, value in boxes.items():
                self._pending_boxes.setdefault(key, value)

    def _init_annotation_batch(self) -> None:
        """建标注攒批器（宿主页面 __init__ 里调一次）。"""
        self._pending_sizes: dict[str, tuple[int, int]] = {}
        self._pending_boxes: dict[str, list] = {}
        self._annot_timer = QTimer(self)
        self._annot_timer.setSingleShot(True)
        self._annot_timer.setInterval(self._ANNOT_FLUSH_MS)
        self._annot_timer.timeout.connect(self._flush_annotations)

    def _read_worker_error(self) -> None:
        """worker 的 stderr：崩溃堆栈/告警原样进日志，避免失败时无从排查。"""
        source = self.process or self.detect_process
        if not source:
            return
        self._consume_worker_stderr(bytes(source.readAllStandardError()))

    def _consume_worker_stderr(self, data: bytes) -> None:
        """解析 stderr 字节：逐行进日志，并记下像错误的那一行（失败提示用）。

        ⚠️ 匹配**不区分大小写**且覆盖几种常见形态：原先只认 `"Error"`/`"Traceback"`
        （首字母大写），而 argparse 的报错是 `prog: error: the following arguments
        are required: --config`（小写）、apt/pip 之类是 `E:`，全都会漏掉 →
        `_last_error_line` 仍是 None，用户看到的还是「退出码 1」。
        """
        _MARKERS = (
            "error", "traceback", "exception", "failed", "failure", "unable",
            "cannot", "can't", "no such", "no space", "denied", "errno",
            "not found", "missing",
            "错误", "失败", "异常",
        )
        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                self.log_view.append(f"[stderr] {line}")
                lowered = line.lower()
                if any(marker in lowered for marker in _MARKERS):
                    self._last_error_line = line

    def _worker_error_occurred(self, error) -> None:
        if self.cancel_requested:
            return
        self.log_view.append(f"[进程错误] {error}")
        if error == QProcess.ProcessError.FailedToStart:
            program = self.process.program() if self.process else "worker"
            self._last_error_line = f"子进程启动失败：{program}"

    def _poll_extract_results(self) -> None:
        """提取过程中：一旦输出目录出现新图片，立即在「提取结果」里展示。"""
        if not self.task_id:
            return
        paths = list_stage_images(self.store.extract_output_dir(self.task_id))
        if len(paths) != self._extract_seen:
            self._extract_seen = len(paths)
            self.extract_result_viewer.set_images(paths)

    def _worker_finished(self, exit_code: int, _status) -> None:
        """顶层兜底：收尾链里任何一环（store 写盘 / 读盘 / 刷新）抛异常，
        都不能让状态机卡死——``process/run_id/running_stage`` 不清、
        ``_release_run`` 不执行 → 执行按钮永久灰死，看门狗每 300ms 空转
        （2026-09-26 第二轮审计 H2：``replace_with_retry`` 重试耗尽抛
        PermissionError 就会走到这里）。异常路径强制复位后照常刷新界面。"""
        try:
            self._worker_finished_impl(exit_code, _status)
        except Exception:  # noqa: BLE001 - 收尾兜底必须接住一切
            import traceback
            import sys as _sys

            tail = traceback.format_exc(limit=3).strip().splitlines()[-1]
            print(f"[worker-finished-exception] {tail}", file=_sys.stderr, flush=True)
            try:
                self.log_view.append(f"收尾阶段出错（已强制复位执行状态）：{tail}")
            except Exception:  # noqa: BLE001
                pass
            self.process = None
            self.run_id = None
            self.running_stage = None
            try:
                self._release_run()
                self._refresh_stage_views()
            except Exception:  # noqa: BLE001
                pass

    def _worker_finished_impl(self, exit_code: int, _status) -> None:
        stage = self.running_stage
        # ⚠️ 收尾第一件事：把管道里剩下的输出读完。
        # Qt 的 finished / 看门狗可能比最后一批 progress/log 事件先到（大任务时
        # GUI 本来就落在 worker 后面），而下面马上要清 self.process 与 self.run_id ——
        # 一清就等于把这批事件永久丢掉：进度停在中间值（历史里
        # 「成功 done=14/total=84」）、日志缺「🎉 处理完成」那行，用户看到的就是
        # "像被中断了/只提取了一半"。排空 + 落最后一次进度之后再清引用。
        proc = self.process
        if proc is not None:
            if proc.state() != QProcess.NotRunning:
                try:
                    proc.waitForFinished(300)  # 让 Qt 收尾并排空管道
                except RuntimeError:
                    pass
            self._drain_worker_output(proc)
        self._flush_progress_ui()
        # ⚠️ 标注（sizes.json / boxes.json）在这里必须落盘：阶段结束后下游要用
        #    它们做坐标基准，攒着不写会让下一阶段读到旧数据。
        self._flush_annotations()
        if self.cancel_requested:
            status = "cancelled"
        elif exit_code == 130:
            # ⚠️ stage 内部捕获 KeyboardInterrupt 时以退出码 130 结束（约定见
            #    core.result.StageStatus.from_exit_code），应记为「已取消」而非
            #    「失败」——用户自己中断的不该背一个红色失败（审计 #16）。
            status = "cancelled"
        elif exit_code == 0:
            status = "success"
        else:
            status = "failed"
        # ⚠️ 失败原因算一次、用三处（落盘 / 日志 / toast）：worker 起不来的那类
        # 失败**一条输出都没有**（0 事件、0.2 秒退出），只有退出码可依。以前只
        # 弹一条转瞬即逝的 toast，记录里连原因都没有，事后完全无从查起。
        failure = None
        if status == "failed":
            failure = self._last_error_line or f"退出码 {exit_code}"
        if self.run_id:
            # worker 的 finished 事件不带 done/total（进度由结构化事件实时汇报），
            # 用最近一次进度补齐，否则历史记录会停在中间的 done 值上。
            self.store.finish_stage(
                self.task_id, self.run_id, status,
                str(self.store.stage_output_dir(self.task_id, stage)) if stage else None,
                progress=self._last_progress,
                error=failure,
            )
        if self.task_id:
            self.store.update_task(
                self.task_id, "completed" if status == "success" else status
            )
        # 这一步刚跑完 → "上游比下游新"的关系可能变了，重算过期提示缓存
        # （判定要读 runs.json，只能在这类"收尾"时刻做，不能放刷新热路径）。
        # 必须在下面的 _refresh_stage_views() 之前：那一次刷新就要用新缓存。
        try:
            self._refresh_stale_notices()
        except Exception:
            pass
        self.process = None
        self.run_id = None
        self.running_stage = None
        # 进程收尾 = 释放执行权（按钮恢复可用、下一次点击可受理）。
        # 放在这里是唯一出口：正常结束、被杀、看门狗兜底都汇到本方法。
        self._release_run()
        if status == "success" and self.task_id:
            if stage == "extract":
                # 页面清单只由 extract 输出决定；detect/rembg 结果留在各自目录，
                # 不回写清单，避免污染 extract 预览和后续子任务的输入。
                output_dir = self.store.stage_output_dir(self.task_id, stage)
                page_count = len(self.store.refresh_pages_from_dir(self.task_id, output_dir))
                self.log_view.append(f"页面清单已刷新（{page_count} 页）。")
                self._refresh_manifest()
                if page_count == 0:
                    self._toast(
                        "warning", "结果为空",
                        f"{STAGE_LABELS[stage]} 未产生任何图片，请查看日志（可能参数有误）。",
                    )
            if stage == "print":
                pdf_path = self._latest_print_pdf_path()
                if pdf_path and pdf_path.exists():
                    self.log_view.append(f"PDF 已生成：{pdf_path}")
                    self.print_preview.set_pdf_path(pdf_path)
                else:
                    self.print_preview.set_pdf_path(None)
                # 重新生成完成，清除「版面已修改」标脏
                self._print_dirty = False
                # ⚠️ 也清「取图来源已换」：刚才这次就是按**当前**来源跑的
                # （source_stage 随 args 落进历史），否则状态行会一直提示
                # "请重新生成"，主按钮也一直加粗。放在 set_pdf_path 之后，
                # 让下载按钮先恢复再撤提示。
                self._print_source_stale = False
                try:
                    # 同上：颜色要一起回到常规色
                    self._set_stage_status("成功")
                except Exception:
                    pass
        self._refresh_stage_views()
        self._refresh_preview()
        if stage == "extract":
            # ⚠️ 查表拿栈页号，别写死1（用户 2026-10-06）。自定义流程里
            #    detect 可能是格序 0 / 栈页号 1，写死会把"刷新提取结果"刷到
            #    别的步骤上；而且这里的目的是刷**detect**（提取结果的消费者）。
            detect_page = self.stack_index_of_step("detect")
            if detect_page is not None:
                self._refresh_preview(detect_page)
        override_toast = None
        if status == "success" and stage in ("rembg", "rembg_submit"):
            version = self._rembg_submit_version_state()
            if stage == "rembg":
                # 新预览图已落盘：若与最近一次提交不一致，提示有新版本待提交
                if version == "new_version":
                    override_toast = (
                        "info", "已生成新的预览版本",
                        "去底预览图片已更新，请点击「提交本次任务」生成最终图片",
                    )
                elif version == "preview_stale":
                    override_toast = (
                        "info", "预览已生成",
                        "提示：面板参数又有修改，请确认后重新「生成预览」",
                    )
            else:  # rembg_submit
                # 最终图变化，同步刷新第四步（print）列表。⚠️ 查表拿栈页号，
                # 写死3 在自定义流程下会刷错步骤（MEMORY「三套下标」那条）。
                print_page = self.stack_index_of_step("print")
                if print_page is not None:
                    self._refresh_preview(print_page)
                if version == "up_to_date":
                    override_toast = (
                        "success", "提交完成",
                        "最终图片已是最新预览版本，可前往第四步生成 PDF",
                    )
        if status == "failed":
            reason = failure or "退出码 " + str(exit_code)
            # 先落一行日志再弹 toast：toast 会自己消失，日志留在面板里
            self.log_view.append(f"失败原因：{reason}")
            self._toast("error", f"{STAGE_LABELS.get(stage, '')}失败", reason)
        elif override_toast is not None:
            self._toast(*override_toast)
        else:
            self._toast(
                "success" if status == "success" else "error",
                STAGE_LABELS.get(stage, ""),
                STATUS_LABELS.get(status, status),
            )

    @staticmethod
    def _worker_env() -> QProcessEnvironment:
        """子进程强制 UTF-8：GUI 按 UTF-8 解析 JSON Lines，CLI 输出含 emoji。"""
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        return env
