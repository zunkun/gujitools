# -*- coding: utf-8 -*-
"""任务详情页的阶段切换：索引换算、记忆停留、切步骤主入口。"""

from __future__ import annotations

from desktop.settings.config import app_config
from desktop.steps import ports
from desktop.store import IMPOSITION_STAGE
from typing import TYPE_CHECKING, Any


class StageSwitchMixin:
    """阶段切换与「上次停留的步骤」记忆。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _apply_control_width: Any
        _flush_param_drafts: Any
        _imposition_node_visible: Any
        _invalidate_page_caches_for: Any
        _rebuild_node_index: Any
        _refresh_history_options: Any
        _refresh_imposition_node: Any
        _refresh_manifest: Any
        _refresh_preview: Any
        _refresh_stage_views: Any
        _restore_stage_params: Any
        _select_imposition_detail: Any
        _slot_of_node: Any
        _step_input_updated_files: Any
        _sync_download_print_button: Any
        _sync_yolo_export_card: Any
        _toast: Any
        action_row: Any
        bar_index_of_step: Any
        control_stack: Any
        current_stage: Any
        detect_stats: Any
        flow_slots: Any
        flush_layout_pending: Any
        history_block: Any
        log_view: Any
        preview_stack: Any
        release_stage_buffers: Any
        run_button: Any
        stack_index_of: Any
        stage_at_index: Any
        step_at_index: Any
        step_bar: Any
        store: Any
        submit_button: Any
        task_id: Any

    # --------------------------------------------------- 上次停留的步骤（记忆）
    # 「上次停留的步骤」按 **key** 记（不是下标）：步骤会增减（「图片拼版」就是
    # 条件出现的可选节点），下标一旦错位就会把用户送到**另一个**步骤去。key 是
    # 按语义匹配的，匹配不上就回落第一步——这正是用户要的口径。
    def _stage_index_of(self, stage: str | None) -> int | None:
        """把记录的步骤 key 映射成**当前流程**里的格序；匹配不上返回 None。

        ⚠️ 查**本任务流程**的槽位表而不是 ``STAGES.index``：自定义流程
        里这一步可能被删掉（``bar_index_of_step`` 返回 ``None``）→ 视为
        "找不到匹配"，回第一步，而不是把用户送到流程条上不存在的那一格。
        「图片拼版」另有一道条件可见性检查，见
        :meth:`_imposition_node_visible_index`。
        """
        if not stage:
            return None
        if stage == IMPOSITION_STAGE:
            return self._imposition_node_visible_index()
        return self.bar_index_of_step(stage)

    def _imposition_node_visible_index(self) -> int | None:
        """拼版节点在步骤条上的格序；本流程里没有它时 ``None``。

        「图片拼版」是**条件节点**：**流程图里没画它**时它根本不在流程条上，
        即便 key 认得出来也算"找不到匹配"——否则会切进一个流程条上不存在的
        步骤，紧接着又被 ``_refresh_imposition_node`` 踢回第三步（落到哪一步
        全看谁后跑，比"回第一步"更难解释）。
        """
        if not self._imposition_node_visible():
            return None
        return self.bar_index_of_step(IMPOSITION_STAGE)

    def _initial_stage_index(self) -> int:
        """进详情页默认落到第几步：**上次停留的那一格**，匹配不上则第一步。

        这是「打开任务详情默认打开记录的那一步，找不到匹配就从第一步开始」
        的唯一实现处（``set_task`` 末尾调它）。

        ⚠️ **优先按节点恢复**（B 方案，2026-10-17）：同一步骤有多个节点时，
        "上次停在图片去底色"这句话不足以定位——两个节点共用一个 step key，
        只按 step 恢复会稳定回到主节点（用户在副本节点上调完参数、关掉再打开，
        看到的是另一个节点的面板与产物）。
        """
        if not self.task_id:
            return 0
        node = self.store.load_last_node(self.task_id)
        if node:
            slot = self._slot_of_node(node)
            if slot is not None:
                return slot.bar_index
        index = self._stage_index_of(self.store.load_last_stage(self.task_id))
        return 0 if index is None else index

    def _remember_stage(self, index: int) -> None:
        """记下"用户最后停留的步骤（含节点）"，下次打开这个任务直接回到这里。

        写在 ``_select_stage`` 里（切步骤的唯一入口）而不是"返回列表/关窗口"
        时：进程被强杀、断电都不会把记录丢掉。⚠️ 记的是 key 不是下标，理由
        见 :meth:`_stage_index_of`；任务目录已删时 ``save_last_stage`` 自己
        跳过（不重建目录）。
        """
        if not self.task_id:
            return
        # ⚠️ 记key 不记下标（理由见 :meth:`_stage_index_of`）。下标要**反查**
        #    槽位表，不能用 ``STAGES[index]``——自定义流程里那一格可能是
        #    拼版（可选节点）或换个顺序的别的步骤。
        # ⚠️ 连**节点**一起记（B 方案）：同一步骤的多个节点共用一个 step key，
        #    只记 key 就等于"永远回到第一个节点"。
        stage = self.step_at_index(index)
        if stage is None:
            return
        slot = self._slot_at_index(index)
        self.store.save_last_stage(
            self.task_id, stage, (slot.node_id or None) if slot else None
        )

    # ------------------------------------------------- 执行记录区块（设置开关）
    def _wire_history_switch(self) -> None:
        """订阅「显示执行记录」总开关（设置 →「功能」），并立刻算一次显隐。

        用户 2026-11-16：右栏的「执行记录」默认**不显示**，需要时到设置里打开。
        ⚠️ 配置项是长期存活的 QObject，本页被销毁时 Qt 会自动断开，不必手动收
        （范式同 ``DetectMixin._wire_yolo_export_card``）。
        """
        app_config().showHistory.valueChanged.connect(self._sync_history_block)
        self._sync_history_block()

    def _sync_history_block(self, *_args) -> None:
        """「执行记录」区块的显隐：总开关 × 这一步自己有没有专属区块。

        两个条件都满足才显示：
        1. 设置 →「功能」→「显示执行记录」打开（默认关）；
        2. 这一步**没有** ``spec.panel_extra``（第二步显示的是「检测结果统计」，
           那里没有表单参数、历史回填用不上，见 ``spec_for_stage``）。

        「图片拼版」是可选节点（伪步骤）：它不是可执行步骤，执行记录不适用
        （``_select_imposition_detail`` 也会藏它，这里同样挡掉，保证"切到别处
        再切回来"不会把它露出来）。
        """
        stage = self.current_stage() if getattr(self, "task_id", None) else ""
        if not app_config().showHistory.value or stage == IMPOSITION_STAGE:
            self.history_block.setVisible(False)
            return
        spec = ports.spec_for_stage(stage)
        self.history_block.setVisible(not spec or not spec.panel_extra)

    def _select_stage(self, index: int) -> None:
        """切到步骤条的**第``index`` 格**（格序，含可选节点占位）。

        ⚠️ **参数是格序、不是栈页号**：默认流程 ``extract=0/detect=1/rembg=2/
        imposition=3/print=4``，而两个栈的页号是 ``extract=0/detect=1/rembg=2/
        print=3/imposition=4``（伪步骤占末位）。混用两者 = 切错步骤或切到越界页。
        调用方一律先 ``bar_index_of_step(step)`` / ``stack_index_of_step(step)``
        查表，**不要写死数字**（``IMPOSITION_INDEX=len(STAGES)=4`` 是改造前的
        遗留口径，现在落在 print 那一格）。
        """
        # 面包屑：切步骤会成批创建/销毁界面与线程，崩溃取证里这一条最值钱
        # （2026-11-21 排查 Qt6Gui 崩溃用）。放在 flush 之前，这样"切到哪一步"
        # 与"切之前先落了什么"顺序清楚。
        try:
            from utils.crash_log import breadcrumb

            breadcrumb(f"切步骤：{self.current_stage() or '-'} → "
                       f"{self.stage_at_index(index) or '-'}"
                       f"（任务 {self.task_id}）")
        except Exception:  # noqa: BLE001 - 取证绝不该影响切页
            pass
        # 离开当前阶段前把待写暂存落盘、把未提交的版面拖动补发
        # （防抖未到期/拖住未松手就走人不该丢改动）
        self.flush_layout_pending()
        self._flush_param_drafts()
        # ⚠️ **在 set_current 之前**拦下"图上有、但还没有功能"的灰节点：
        #    放行的话步骤条会高亮在这一格、还会被记成"上次停留"，而右侧显示
        #    的仍是上一步的内容——看着就像"点了没反应"。
        slot = self._slot_at_index(index)
        if slot is not None and not slot.mapped:
            self._explain_unmapped_step(slot)
            return
        # ⚠️ **先**把当前格对应的节点记下来再刷一切（B 方案）：随后的预览刷新、
        #    参数回填、历史选项、就绪判据都按 `_current_node_id` 寻址。同一步骤
        #    的多个节点共用同一页面板，靠这个字段把数据按节点重定向。
        # 离开上一步：把它预览区的位图放掉（用户 2026-11-21「离开就释放」）。
        # 只在**真的切走**时放——点了"图上有、还没功能"的灰节点在上面已经
        # return（那时界面还停在这一步，释放了就得白白重装）。
        leaving_stage = self.current_stage() if self.task_id else ""
        target_stage = self.stage_at_index(index)
        if leaving_stage and target_stage and leaving_stage != target_stage:
            self.release_stage_buffers(leaving_stage)
        previous_node = self._current_node_id
        self._current_node_id = (slot.node_id or None) if slot is not None else None
        # 缩略图白名单与节点索引跟着切（B 方案：新节点的副本产物目录要进白名单）
        self._rebuild_node_index()
        # ⚠️ 换了节点 ⇒ **页清单也要换**（B 方案）：清单回答的是"**这个节点**
        #    要处理哪几页"（插过图/删过页/重排过）。不换的后果是"看的是 B、
        #    列的是 A 的图"——预览、右键编辑回写、右键「定位图片资源」全指着
        #    另一个节点的文件（这正是"副本节点定位到主节点图片"的根因）。
        #    清单的每次改写都已落盘（见 manifest 各插入/删除处），所以丢弃内存
        #    副本重新按节点读是安全的。
        if previous_node != self._current_node_id:
            self.pages = []
            self._refresh_manifest()
        self.step_bar.set_current(index)
        # 记住这一步：下次打开任务默认回到这里
        self._remember_stage(index)
        step = self.step_at_index(index)
        if step == IMPOSITION_STAGE:
            # ⚠️ 节点本身的显示/选择状态要在这里先补一次：真实步骤是在本方法
            #    **末尾**刷的（那边得等 area 回填完），而这条分支提前 return 了。
            #    漏掉它的后果（用户 2026-09-30 报的 bug）：上次停在「图片拼版」，
            #    重进任务直接恢复到这一步时，流程条上**没有那个虚线节点**——
            #    节点显示状态还停在上一个任务/构造时的隐藏态，只能等用户点了
            #    别处再切回来才会出现。
            #    ⚠️ 这一步内部可能发现 area≠1 而把当前步踢回第三步
            #    （见 ImpositionMixin._refresh_imposition_node）：那就跟随它，
            #    别再进拼版详情，否则步骤条说"第三步"、页面却是拼版。
            self._refresh_imposition_node()
            #⚠️ 用**当前格序反查**判断有没有被踢走：`_refresh_imposition_node`
            #    在 area≠1 时会把当前步踢回第三步，那时 ``_current`` 已不是
            #    拼版那一格（旧代码写死 ``!= IMPOSITION_INDEX``，自定义流程
            #    下拼版的格序会变，写死就判错了）。
            if self.step_at_index(self.step_bar._current) != IMPOSITION_STAGE:
                return
            # 「图片拼版」可选节点：右侧/预览区都是占位详情，不碰阶段面板
            self._select_imposition_detail()
            return
        # ⚠️ 这一格不在本流程里（自定义流程删掉了对应节点，而调用方拿着
        #    旧下标）：回第一步，别拿越界页号去 setCurrentIndex。
        if step is None:
            self._select_stage(0)
            return
        # ⚠️ 面板是**惰性**的：用户切到这一步，就现在把它建出来（不建的话
        #    左侧控制区是空白）。反过来，没切过来的步骤一直不建——这正是
        #    用户 2026-09-25 要求的"谁进去谁才建"。
        # ⚠️ 栈的页号是``stack_index`` 而非步骤条格序：可选节点在步骤条上
        #    插在它该在的位置（bar_index），但两个栈仍按"真实步骤 + 伪步骤
        #    占最后一位"建页（stack_index）。默认流程下两者逐值相等。
        page = self.stack_index_of(index)
        # ``peek`` / ``panel`` 是惰性面板宿主（LazyPanelHost）上的属性，QWidget
        # 类型里没有；标成 ``Any`` 即可按鸭子类型直接访问（运行时完全一致）。
        target: Any = self.control_stack.widget(page)
        if hasattr(target, "peek") and target.peek() is None:
            target.panel  # noqa: B018 - 触发构造
        self.control_stack.setCurrentIndex(page)
        self.preview_stack.setCurrentIndex(page)
        # 真实步骤：执行按钮组恢复可见（拼版详情页整组藏掉，见
        # _select_imposition_detail；两种状态互斥、切换时都要还原）
        # ⚠️ 恢复的是**整行** action_row（「检测文本框 + 分割图片」并排），
        #    只恢复 run_button 的话行本身仍带着上一步的隐藏标记。
        self.action_row.setVisible(True)
        # 按钮文案与区块显隐**全查 spec**（不再 `if stage == ...`）：
        # 第二步是「检测文本框」+「分割图片」，第三步是「图片去底色」，
        # 第四步是「生成PDF」，其余是「提取文档图片」——文案与"跑完会发生什么"
        # 绑定，所以放 spec 而不是散在页面里（加一步 / BPM 换顺序都不必改这里）。
        # ⚠️ 走 ``ports.spec_for_stage``：伪步骤（拼版）取不到 spec 时用默认值。
        spec = ports.spec_for_stage(step)
        self.run_button.setText(
            spec.run_button_text if spec else "执行本步骤"
        )
        submit_visible = bool(spec and spec.has_submit)
        self.submit_button.setVisible(submit_visible)
        if not submit_visible:
            # ⚠️ 提交按钮藏起来时它的红框必须一起摘（2026-10-13 用户截图：
            #    「图片拼版」伪步骤的红框悬在进度条上——伪步骤分支不跑
            #    _update_run_buttons，没人替它摘框，隐藏的按钮留着旧框）。
            from desktop.ui.widgets import set_red_frame

            set_red_frame(self.submit_button, False)
        # 右侧面板的步骤专属区块：``spec.panel_extra`` 非空 → 显示该专属区块
        # （detect 显示「检测结果统计」），否则显示「执行记录」
        # （detect 无表单参数，历史回填没用武之地）。
        self.detect_stats.setVisible(
            bool(spec) and spec.panel_extra == "detect_stats"
        )
        # 「导出YOLO标注」那张卡片也只在第二步出现，另加"YOLO 开关"条件
        # （判据全在 DetectMixin._sync_yolo_export_card 里，见那里）
        self._sync_yolo_export_card()
        # 执行记录：还多一道"设置 →「功能」→ 显示执行记录"的总开关（默认关）
        self._sync_history_block()
        self._apply_control_width()
        self._refresh_stage_views()
        # 「下载 PDF」只属于第四步：切到别的步骤就收起来（拼版详情页另行处理）
        self._sync_download_print_button()
        # ⚠️ **按内容判一次"这一步的输入产物换了没有"**（用户 2026-10-18）：
        #    上游产物会被同名覆盖（拼版成品重合成、单页重提取、编辑器回写），
        #    路径没变、内容变了。这种情况下列表/图标是**解码一次就缓存**的，
        #    不强制重装就会一直停在旧图上——"上一步图片发生变化，切到这一步要自动
        #    加载最新的图片"讲的就是它。
        # ⚠️ 必须在 ``step_bar.set_current`` **之后**算：判据要问"当前这一步的
        #    输入目录"（``current_stage`` 读的是步骤条的高亮格）。
        updated = self._step_input_updated_files()
        if updated:
            # 「上一步更新了哪些图片」的记录（用户 2026-10-18）：日志里说清是哪几张
            # ——旧版面/旧缩略图就是按这份清单**按页**失效的。
            names = "、".join(path.name for path in updated[:6])
            if len(updated) > 6:
                names += f" 等 {len(updated)} 张"
            self.log_view.append(
                f"上游产物已更新 {len(updated)} 张图片（{names}）："
                "本步骤按最新图片重新载入。"
            )
        self._invalidate_page_caches_for(updated)
        # ⚠️ 传的是**栈页号**（``_refresh_preview`` 按 ``preview_stack`` 这一层
        #    理解入参），不是格序——自定义流程里两者不等。
        self._refresh_preview(self.stack_index_of(index), force=bool(updated))
        self._restore_stage_params(index)
        self._refresh_history_options()
        # 流程条上的「图片拼版」节点跟随流程图（切步骤后统一补一次）
        self._refresh_imposition_node()

    def _slot_at_index(self, index: int):
        """步骤条**格序** → 槽位对象；没有这一格返回 ``None``。

        与 :meth:`step_at_index` 的区别：那个只给 step key，这个给整个槽位
        （要拿 ``optional`` / ``mapped`` 这类只有槽位才有的信息）。
        """
        for slot in self.flow_slots():
            if slot.bar_index == index:
                return slot
        return None

    def _explain_unmapped_step(self, slot) -> None:
        """图上画了、但还没有对应功能的节点：说清怎么接上，别静默跳走。

        两种出路都写进提示里，用户不用猜：改**名字**接上已有步骤，或直接
        **删掉**不需要的那一格（编辑器工具栏有「删除」与「恢复默认」）。
        """
        self._toast(
            "warning", "这一步还没有功能",
            f"流程图里的「{slot.label}」目前没有对应的处理功能，还不能执行。"
            "要用它：点页头「查看 / 编辑流程」把它的名字改成已有步骤"
            "（如「图片去底色」）；不需要就把它删掉。",
        )
