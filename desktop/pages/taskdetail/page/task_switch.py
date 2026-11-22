# -*- coding: utf-8 -*-
"""任务详情页的任务切换：复位运行态、换源文件、补建副本、返回列表。"""

from __future__ import annotations

from pathlib import Path
from desktop.steps.spec import FLOW_STAGES
from desktop.workers import CopySourceWorker, connect_queued
from ._qt import QProcess
from typing import TYPE_CHECKING, Any


class TaskSwitchMixin:
    """任务切换与源文件生命周期（依赖宿主页面提供的界面控件）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        SOURCE_BACKUP_DELAY_MS: Any
        _aggregate_start_poll: Any
        _apply_pending_print_reset: Any
        _apply_pending_source_defaults: Any
        _backup_timer: Any
        _dismiss_source_prompt: Any
        _flush_annotations: Any
        _flush_param_drafts: Any
        _initial_stage_index: Any
        _logs: Any
        _prompt_missing_source: Any
        _rebuild_step_bar: Any
        _refresh_manifest: Any
        _refresh_source_actions: Any
        _refresh_stage_views: Any
        _refresh_stale_notices: Any
        _reset_imposition_state: Any
        _reset_rembg_live: Any
        _select_stage: Any
        _stop_detect_process: Any
        _toast: Any
        back_requested: Any
        control_stack: Any
        detail_title: Any
        detect_cache: Any
        detect_viewer: Any
        extract_result_viewer: Any
        flow_slots: Any
        log_view: Any
        print_preview: Any
        process: Any
        release_stage_buffers: Any
        rembg_viewer: Any
        run_worker: Any
        source_label: Any
        store: Any
        task_no_label: Any

    # ------------------------------------------------------------------ 任务切换
    def _warn_if_flow_degraded(self, task_id: str) -> None:
        """本任务的流程图**读不出来时已回落默认模板** ⇒ 明确告诉用户一次。

        ⚠️ 这是"自定义流程里总是冒出默认流程"这类报障**唯一**能自证的线索。
        ``store.task_diagram`` 在三种失败形态下都会回落默认模板（文件缺失 /
        XML 坏 / **一个步骤名都认不出**），而回落是**静默**的——用户看到的
        现象与"我没改过它"完全一样，最隐蔽的一种是他在 bpmn.io 里改了节点名，
        阶段按名接不回，整张自定义图被判成坏图。

        ⚠️ 同一次 :meth:`set_task` 只弹一次（``set_task`` 一条链上会被
        ``flow_slots`` 读很多次流程图，别弹成刷屏）。
        """
        reason = self.store.flow_degraded_reason(task_id)
        if not reason:
            self._flow_warned_for = None
            return
        if getattr(self, "_flow_warned_for", None) == task_id:
            return
        self._flow_warned_for = task_id
        self._toast(
            "warning", "流程已临时按默认显示",
            f"{reason}。\n\n"
            "本任务的界面暂时按**默认流程**显示（步骤条、执行顺序、取图目录"
            "都按默认那套算）。请到「查看 / 编辑流程」里把流程修好——在修好之前，"
            "改动这份流程不会有任何效果。",
        )

    def set_task(self, task_id: str) -> bool:
        """切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。

        加载任务后先调用各面板 reset_to_default 清掉上一任务手改参数，再清
        detect 缓存/运行态引用并刷新清单与预览；防止参数或 run_id 串到新任务。
        返回 False = 拒绝切换（任务不存在 / 步骤执行中），调用方应留在原地。
        """
        task = self.store.get_task(task_id)
        if not task:
            return False
        # 取证埋点（2026-11-22）：内存优化合入当晚起出现「切任务详情瞬间
        # use-after-free」，这里记下切任务的起点，崩溃日志末尾能直接对上。
        from utils.crash_log import breadcrumb
        breadcrumb(f"切换任务详情：{self.task_id or '-'} → {task_id}")
        # ⚠️ 步骤执行中禁止切换（2026-09-26 第二轮审计）：runner 的收尾
        #    全部按 self.task_id 落盘，切走后事件到达就会写进**新任务**的
        #    runs.json / 输出目录。单页检测是几秒的辅助操作，直接停掉即可。
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self._toast(
                "warning", "任务进行中", "请等待当前步骤完成后再切换其他任务。"
            )
            return False
        self._stop_detect_process()
        # ⚠️ 复位**跨任务会串味**的两个第四步状态（2026-09-26 审计）：
        #    ① `_print_dirty`：在任务 A 拖过版面，打开任务 B 时 B 的第四步会误显示
        #       「● 版面已修改，点击「生成PDF」生效」并把主按钮加粗；
        #    ② print 面板的 `_last_applied`（供「放弃本次修改」回填）：不重置的话
        #       在 B 点「放弃本次修改」会把 A 的参数（含 A 派生的 pdf_name/title_text）
        #       回填进来 —— 后续可能用 A 的名字生成 B 的 PDF。
        #    ⚠️ 面板是惰性的：**只能挂"待复位"标记**，等它真被建出来时再应用，
        #    绝不能在这里 `self.control_stack.widget(3)` 把它拽出来。
        self._print_dirty = False
        self._pending_print_reset = True
        self._apply_pending_print_reset()
        # ⚠️ 必须在覆盖 task_id 之前落盘：暂存要写进"上一个任务"的目录
        self._flush_param_drafts()
        # 标注攒批同理：攒着的尺寸/框属于**上一个任务**，切换后写就串任务了
        self._flush_annotations()
        # 实时去底色的台账同理：它记的是"哪张图盘上成品是按哪份参数算的"，
        # 属于**上一个任务**——放在覆盖 task_id 之后清，清的就是新任务（空表）。
        self._reset_rembg_live()
        # 换任务：上一任务的预览位图都用不上了，先全放掉（新任务会按各自的
        # refresh 重新装）。放在覆盖 task_id **之前**：此时 flush 已把上一
        # 任务的暂存落盘，放位图不会丢任何未保存状态。
        self.release_stage_buffers()
        # 当前节点（B 方案）随任务一起清：新流程的节点 id 与旧任务无关，
        # 留着会让"按节点寻址"在新任务上指错节点（末尾 _select_stage 会重设）。
        self._current_node_id = None
        self.task_id = task_id
        # ⚠️ 一律用任务目录里的**备份** PDF，不用索引里的 source_path：
        # 源文件在用户磁盘上会被移动/改名/删除，一走就「渲染失败」；
        # 备份随任务走，删除任务时一起清掉，任务才是自包含的。
        #
        # ⚠️⚠️ **这里绝不做同步复制**：老实现是 `ensure_source_copy()`，副本
        # 缺失时**在主线程里**把整个 PDF 复制一遍——一本 800MB 的书就是进页面
        # 卡住几秒到几十秒（用户报「进详情页要等一会」的真凶）。副本由导入
        # 后台任务负责落盘；这里只用**已落地**的副本，没有就先用源文件（两者
        # 二进制相同，渲染结果一致），后台补备份见 _schedule_source_backup()。
        #
        # ⚠️ **空壳任务**（创建时没选 PDF，用户 2026-10-06「PDF 输入不是必须
        # 的」）：索引里 source_path 是**空串**。`Path("")` 是"."（当前目录），
        # 直接 `or Path(task["source_path"])` 会得到一个**存在的目录**——
        # 于是 exists() 通过、`set_pdf` 去渲染一个目录、后面 extract 拿着
        # 它当输入，静默走到崩为止。所以这里显式判空，置成 None（"还没有
        # 源文件"这个状态有别于"文件丢了"，UI 与执行各自处理，见下）。
        source_text = str(task.get("source_path") or "").strip()
        copy = self.store.source_copy_path(task_id)
        if copy is not None:
            self.source_path = copy
        elif source_text and source_text != ".":
            self.source_path = Path(source_text)
        else:
            self.source_path = None
        self.has_source = self.source_path is not None
        self._schedule_source_backup(task_id)
        # ⚠️ 空壳任务（没选源文件）在这里**什么都不弹**：「还没选」不是错误，
        #    而且**并非所有流程都需要 PDF**——要不要催、催什么（补 PDF 还是
        #    补入口图片）由 ``_missing_input_kind()`` 按流程入口判，提示统一
        #    走 set_task 末尾的 ``_prompt_missing_source()``（页内提示层）
        #    与页头红字/按钮高亮，这里再来一条 toast 就是重复+误导（用户
        #    2026-10-07：右下角「尚未选择 PDF」不再需要）。「文件丢了」才是
        #    错误，仍在下面单独说。
        if self.source_path is not None and not self.source_path.exists():
            self._toast(
                "error",
                "PDF 缺失",
                f"任务备份与源文件都不存在：{task['source_path']}\n"
                "请重新导入该 PDF（或把原文件放回原处后重开任务）。",
            )
        self.detail_title.setText(task["name"])
        # 任务编号与任务名并排显示：编号是任务目录名/索引主键，创建后不变，
        # 任务名却可随时改，两者必须能分开看（用户 2026-10-24）。
        self.task_no_label.setText(f"任务#{task_id}")
        self.source_label.setText(
            self.source_path.name if self.source_path else "尚未选择源文件")
        self._warn_if_flow_degraded(task_id)
        self._refresh_source_actions()
        # 切任务时先把各阶段面板复位到默认：这些面板是长生命周期控件，
        # 上个任务手改过的参数（area/border/type/zoom…）否则会带到新任务上，
        # 而新任务往往没有历史记录可覆盖回来。
        # ⚠️ 四个面板都是**惰性**的，这里必须走 `peek()`（不触发构造）：直接
        #    `widget(i).reset_to_default()` 会经属性转发把面板全部现造出来，
        #    进详情页的时间就又回到"要为没进去的步骤买单"（用户明确要求
        #    第 2/3/4 步谁进去谁才建）。没建的面板本来就没动过，无需复位。
        #    ⚠️ 只遍历真实阶段（len(FLOW_STAGES)）：控制栈末尾是「图片拼版」占位面板，
        #    没有参数也没有 reset_to_default，混进来就是 AttributeError。
        for index in range(len(FLOW_STAGES)):
            host = self.control_stack.widget(index)
            peek = getattr(host, "peek", None)
            # ⚠️ 按鸭子类型取用：host 可能是 LazyPanelHost（惰性）也可能是
            #    真面板，panel 的类型检查器看不见，两种都得能调 reset_to_default。
            panel: Any = peek() if callable(peek) else host
            if panel is not None:
                panel.reset_to_default()
        # 第四步默认 PDF 名/古籍名随源 PDF 名派生（xxx[重制].pdf / xxx）；
        # ⚠️ 同样不能在这里碰面板本体：记下源名，面板真被建出来时再应用
        #    （见 _init_ui 里挂的 add_created_hook）。已有 print 历史时它会在
        #    进入第四步时再回填历史配置。
        # ⚠️ 空壳任务（没有源文件）没有 stem 可派生：给**任务名**当源名，
        #    这样补选 PDF 之前第四步的参数也不是空的（补选后会被覆盖，
        #    见 _on_pick_source）。
        self._pending_source_stem = (
            self.source_path.stem if self.source_path
            else str(task.get("name") or task_id)
        )
        self._apply_pending_source_defaults()
        # ⚠️ 先冲刷攒批再清空：``_logs`` 里可能还压着上一个任务的日志行，
        #    只 ``log_view.clear()`` 的话它们会在下一次定时器到期时**重新冒出来**
        #    （换任务后日志里混进上一个任务的内容）。
        self._logs.flush()
        self.log_view.clear()
        self.detect_cache.clear()
        # 整本书统计的「整幅→半幅」显示修正也按任务作废，别拿上一本的基线。
        self._half_width_median = None
        self._manual_stems = set()
        # 「自动沿用上一页标注」的"这一页已经带过了"记号按任务清：
        # 上一个任务带过的页名（0001…）在新任务里是**另一页**，留着会让新任务
        # 的头几页永远带不过来框（两个任务的页名天然重复）。
        self._inherit_done = set()
        # 「上一个停留的页面」同理会跨任务串味：新任务的第一次选页不该去沿用
        # 上一个任务的最后一页。
        self._detect_prev_path = None
        # 图头尺寸缓存按 (路径, mtime) 键控、只增不减：换任务清掉，别攒一整场会话
        self._thumb_size_cache = None
        # 第四步缩略图**路径记忆**同理：它按 (路径, mtime) 键控，键里有绝对路径，
        # 跨任务不会给错图，但会白攒一整场会话的内存（每页一条）。
        self._print_thumb_paths = {}
        # 上一个任务排着的"补生成待打印缩略图"必须撤掉：定时器回来时 task_id
        # 已换成新任务，会把上一任务的图生成进新任务的缓存目录。
        warm_timer = getattr(self, "_print_warm_timer", None)
        if warm_timer is not None:
            warm_timer.stop()
        self._print_warm_pending = []
        # 「上游产物逐文件指纹」的记忆同理按任务清：同一个任务**重进**（换源 PDF
        # 后又 set_task、或从列表再打开）时目录是老的、内容可能已被换过一遍，
        # 留着旧指纹会把"内容变了"漏判成"没变"。
        self._dir_files = {}
        # "当前步是不是聚合任务的输入节点"的缓存也按任务作废（换任务即换答案）
        self._input_node_cached = None
        # 汇集轮询停表：换任务后旧任务的轮询不许再刷新任务的清单
        self._aggregate_start_poll.stop()
        self.pdf_page_count = 0
        self._history_prefilled: set[str] = set()
        #: ``control_stack`` 页号 → 上次为它复位的**节点标记**（B 方案）。
        #: 同一步骤的多个节点共用一页，切节点时要先把表单复位再回填，
        #: 否则上一个节点手改的值会留在表单里、被当成这个节点的参数跑掉。
        self._restored_node_of_page: dict[int, str] = {}
        self._history_params: list[dict] = []
        # 运行态引用清零：避免上一个任务的 run_id/running_stage 影响新任务
        self.run_id = None
        self.running_stage = None
        self.running_node = None
        self.cancel_requested = False
        # 执行权也要清：切任务时上一个任务若卡在"已受理未启动"，标记不清会
        # 让新任务的执行按钮一直是灰的（且没有任何进程能来释放它）
        self._run_claim = None
        self._run_launched_at = 0.0
        self._last_error_line = None
        # ⚠️ 空壳任务：source_path 是 None（见上面），而``set_pdf`` 本身就
        #    接受 None（内部摆个占位就return，见 pdf_viewer.set_pdf），所以
        #    直接传；占位文案要说清是"还没选"而不是"加载失败"。
        #    ⚠️ 查看器是 ExtractPreviewWidget（extract 预览的唯一控件，
        #    用户 2026-10-09 合并双标签）：PDF 页缩略图与提取产物同屏。
        self.extract_result_viewer.set_pdf(
            self.source_path,
            placeholder=None if self.source_path else "尚未选择源文件",
            cache_dir=self.store.source_thumbnails_dir(task_id),
        )
        self.extract_result_viewer.set_extract_dir(
            self.store.extract_output_dir(task_id)
        )
        self._refresh_manifest()
        # 换任务就得重算"上游比下游新"的判定缓存（读的是新任务的 runs.json）
        self._refresh_stale_notices()
        # 拼版视图/状态复位（取消在飞合成、灌新任务的拼版文档）
        self._reset_imposition_state()
        # ⚠️ 按**本任务流程**重建步骤条（BPM 驱动）：构造期还没有任务，
        #    ``_build_step_bar`` 只能先按默认流程建。自定义流程换了步骤
        #    顺序/ 可选节点位置后，必须在这里按新流程重排，否则步骤条显示的
        #    仍是默认顺序、点节点也会切错步骤。默认流程下这是**同参数重建**，
        #    外观零变化（自测 detail_structure 钉死）。
        self._rebuild_step_bar()
        self._refresh_stage_views()
        # 落到「上次停留的步骤」（没有记录 / 记录匹配不上时回第一步）
        # ——这就是「点任务详情直接进上次那一步」的全部实现（用户 2026-10-06
        #   明确保留的口径），与启动行为无关。
        self._select_stage(self._initial_stage_index())
        # 记下「上次停留的任务」：启动不再自动跳回（用户 2026-10-06 改口径），
        # 这条全局记录只留给将来的显式"回到上次任务"入口，步骤仍由该任务自己的
        # ui.json 另记（见 _remember_stage）
        self.store.save_last_task(task_id)
        # ⚠️ 弹窗提示放在**最后**：前面已经把页头、红字、按钮高亮、预览都摆好
        #    了，用户点"现在选择"时看到的界面已经是就绪的。
        #    判据是"流程要 PDF 而这个任务还没有"（``_missing_source``）——
        #    有源文件的任务、流程里不需要 PDF 的任务（自定义流程删掉了
        #    「提取图片」）都不弹。
        self._prompt_missing_source()
        # YOLO 预加载（用户 2026-10-13）：流程里有「检测文本框」且还没执行过
        # 时，趁用户在页面里逗留把常驻服务的模型在后台热好——之后点「执行」
        # 不用再等那约 5 秒的模型加载。全局只加载一次（本会话），二次进入
        # 只做轻量探测；重活全在服务子进程（低优先级，让出 CPU），主线程
        # 只做毫秒级判定。失败无声，绝不影响进页面。
        self._schedule_yolo_prewarm()
        # ⚠️ 必须 True：_open_detail 靠返回值决定切不切页——漏了这句
        #    "返回 None 被当拒绝"，详情页就永远进不去（2026-09-27 事故）
        return True

    def _schedule_yolo_prewarm(self) -> None:
        """按预加载条件排一次 YOLO 预热（判定在主线程，重活在后台）。"""
        task_id = self.task_id
        if not task_id:
            return
        try:
            from desktop.services.yolo_prewarm import (  # noqa: PLC0415
                detect_pending, request_prewarm,
            )

            if detect_pending(
                self.flow_slots(),
                self.store.stage_states(task_id).get("detect"),
            ):
                request_prewarm()
        except Exception:  # noqa: BLE001 - 预加载是体验优化，任何失败都放行
            pass

    def _schedule_source_backup(self, task_id: str) -> None:
        """副本缺失且源还在时，**延时在后台**补一份（绝不在主线程里复制）。

        延时 `SOURCE_BACKUP_DELAY_MS`：导入流程本身就在复制，这里只为
        「导入时复制失败 / 早期版本没有备份的老任务」兜底，不该和正在跑的
        导入任务重复劳动（`copy_file_atomic` 各自的临时文件不同名，重复复制
        不会写坏文件，但白读白写一遍 800MB）。
        """
        if self.store.source_copy_path(task_id) is not None:
            return
        if not self._source_exists(task_id):
            return  # 源也没了：set_task 已经弹过「PDF 缺失」
        self._backup_task_id = task_id
        self._backup_timer.start(self.SOURCE_BACKUP_DELAY_MS)

    def _source_exists(self, task_id: str) -> bool:
        task = self.store.get_task(task_id)
        if not task:
            return False
        return Path(str(task.get("source_path") or "")).is_file()

    def _run_source_backup(self) -> None:
        """定时器到期：真正去后台复制（用户此时早就在用界面了）。"""
        task_id = self._backup_task_id
        self._backup_task_id = None
        if not task_id or self.task_id != task_id:
            return
        if self.store.source_copy_path(task_id) is not None:
            return  # 导入任务已经补上了
        task = self.store.get_task(task_id)
        if not task:
            return
        source = Path(str(task.get("source_path") or ""))
        if not source.is_file():
            return
        target = self.store.task_dir(task_id) / source.name
        self.run_worker(
            lambda: CopySourceWorker(source, target),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    lambda _path: self._on_source_backup_ready(),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_source_backup_ready(self) -> None:
        """副本补好了：若用户还在本任务上，把当前 PDF 换成副本。

        ⚠️ 只有在**还在看同一个任务**时才能换（定时器/线程回来时用户可能
        已经切走或返回列表了）。
        """
        if not self.task_id:
            return
        copy = self.store.source_copy_path(self.task_id)
        if copy is None or self.source_path == copy:
            return
        self.source_path = copy
        self.source_label.setText(copy.name)
        self.extract_result_viewer.set_pdf(
            copy, cache_dir=self.store.source_thumbnails_dir(self.task_id)
        )
        self.extract_result_viewer.set_extract_dir(
            self.store.extract_output_dir(self.task_id)
        )

    def _on_back(self) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self._toast("warning", "任务进行中", "请等待当前步骤完成后再返回。")
            return
        # ⚠️ 检测是几秒到十几秒的慢活：返回后旧进程的 boxes 事件才到达，
        #    task_id 已清空/换成别的任务 → 跨任务写 boxes.json（审计 H3）。
        self._stop_detect_process()
        # 离开前把待写暂存落盘：task_id 马上被清掉，之后再写就找不到任务了
        self._flush_param_drafts()
        self._flush_annotations()
        # 实时预览暂存同样要按"当前任务"清（覆盖 task_id 之前）
        self._reset_rembg_live()
        # ⚠️ 「缺源 PDF」提示层也要收：它是这一页的子控件，不收的话回到列表
        #    之后它还浮在那儿（页面只是被切走、并没有销毁），下次进来会看到
        #    一个"上个任务"的提示层。
        self._dismiss_source_prompt()
        self.task_id = None
        self.source_path = None
        # 释放 PDF：不释放的话回到列表删除该任务时，rmtree 可能撞上文件占用
        self.extract_result_viewer.set_pdf(None)
        self.extract_result_viewer.set_extract_dir(None)
        # ⚠️ **内存释放（2026-10-13 用户报「反复导入 PDF 内存越来越大」）**：
        #    详情页是惰性单例、返回主界面不销毁，下面三个 viewer 里还驻留着
        #    上个任务的数据——detect/rembg 的整包页面清单 + 当前页大图
        #    QPixmap（数千像素见方 = 十几 MB），print 的待打印条目。不清的话
        #    用户停在主界面期间这些就一直压着，和下个任务的导入期叠加推高
        #    峰值。set_task 进下一个任务时本来就会重建替换，这里只是把
        #    "返回主界面"这段时间的驻留放掉。
        self.detect_viewer.set_images([])
        self.rembg_viewer.set_images([], None)
        self.print_preview.set_entries([])
        self.print_preview.set_pdf_path(None)
        # 拼版侧同理：页面缩略图位图 memo（PageThumbManager._pix，无上限）
        # 与画布全分辨率解码缓存整包放掉（内部会停计时器/关预览弹窗）。
        self._reset_imposition_state()
        # ⚠️ 共享 fitz 文档缓存（LRU 最多 2 本）只在"删除任务/进程退出"时关，
        #    反复导入的场景永远走不到——每本扫描 PDF 的 Document 连同 MuPDF
        #    内部解码缓存可达数百 MB，跨任务常驻就是"内存阶梯式上涨且不回落"
        #    的最大单一来源。返回主界面 = 离开本任务，此刻没有任何渲染在用它
        #    （单页渲染走 single_flight，这里最多等当次 ~160ms 的渲染收尾），
        #    全部关掉；下次进任务再打开就是一次性的 xref 解析，不构成卡顿。
        try:
            from desktop.workers.preview_worker import close_cached_documents

            close_cached_documents()
        except Exception:  # noqa: BLE001 - 释放失败不该拦住返回
            pass
        self.back_requested.emit()
