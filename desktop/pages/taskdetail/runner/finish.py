# -*- coding: utf-8 -*-
"""阶段收尾：识别结果、写 runs.json、刷新状态与提示。"""

from __future__ import annotations

from desktop.utils.files import list_stage_images
from desktop.store import STAGE_LABELS
from ._qt import QProcess, QProcessEnvironment
from typing import TYPE_CHECKING, Any, Callable, cast

from .constants import STATUS_LABELS


class StageFinishMixin:
    """阶段收尾（含看门狗兜底）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _drain_worker_output: Any
        _flush_annotations: Any
        _flush_progress_ui: Any
        _last_error_line: Any
        _last_progress: Any
        _latest_print_pdf_path: Any
        _logs: Any
        _node_scope: Any
        _output_path_for: Any
        _refresh_manifest: Any
        _refresh_preview: Any
        _refresh_stage_views: Any
        _refresh_stale_notices: Any
        _refresh_stats_now: Any
        _release_run: Any
        _set_stage_status: Any
        _submit_version_state: Any
        _toast: Any
        cancel_requested: Any
        current_node: Any
        extract_result_viewer: Any
        print_preview: Any
        stack_index_of_step: Any
        store: Any
        task_id: Any

    def _poll_extract_results(self) -> None:
        """提取过程中：输出目录一有新图片，当前页的预览立即跟上。

        ⚠️ 2026-10-09 合并双标签后左栏恒是 PDF 页缩略图，不再 ``set_images``
        重建清单；把产物目录交给查看器，当前页的产物一出现大图就切过去。
        ⚠️ 目录按**正在跑的那个节点**取（B 方案）：用户跑到一半切到同一步骤的
        另一个节点时，轮询不能跟着切——那样会把新节点的空目录当"提取结果"。
        """
        if not self.task_id:
            return
        directory = self.store.node_or_stage_output(
            self.task_id, self.running_node or self.current_node(), "extract"
        )
        paths = list_stage_images(directory)
        if len(paths) != self._extract_seen:
            self._extract_seen = len(paths)
            self.extract_result_viewer.set_extract_dir(directory)

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
                self._logs.append_now(f"收尾阶段出错（已强制复位执行状态）：{tail}")
            except Exception:  # noqa: BLE001
                pass
            self.process = None
            self.run_id = None
            self.running_stage = None
            self.running_node = None
            try:
                self._release_run()
                self._refresh_stage_views()
            except Exception:  # noqa: BLE001
                pass

    def _worker_finished_impl(self, exit_code: int, _status) -> None:
        stage = self.running_stage
        # ⚠️ 收尾全程用**局部** ``node``：下面清引用时 ``self.running_node``
        #    会一起清空，而"页清单归谁"这类判断发生在清空之后（B 方案）。
        node = self.running_node
        # ⚠️ 收尾第一件事：把管道里剩下的输出读完。
        # Qt 的 finished / 看门狗可能比最后一批 progress/log 事件先到（大任务时
        # GUI 本来就落在 worker 后面），而下面马上要清 self.process 与 self.run_id ——
        # 一清就等于把这批事件永久丢掉：进度停在中间值（历史里
        # 「成功 done=14/total=84」）、日志缺「🎉 处理完成」那行，用户看到的就是
        # "像被中断了/只提取了一半"。排空 + 落最后一次进度之后再清引用。
        proc = self.process
        if proc is not None:
            if proc.state() != QProcess.ProcessState.NotRunning:
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
        # ⚠️ 有 run_id 必有任务在身（两者同生共死，见 set_task 的复位）；显式
        #    并判只为让类型收窄，运行时行为不变。
        if self.run_id and self.task_id:
            # worker 的 finished 事件不带 done/total（进度由结构化事件实时汇报），
            # 用最近一次进度补齐，否则历史记录会停在中间的 done 值上。
            # ⚠️ 产物落点按**正在跑的那个节点**取（B 方案），不按当前格：
            #    用户可能在收尾前就切到同一步骤的另一个节点去了。
            self.store.finish_stage(
                self.task_id,
                self.run_id,
                status,
                self._output_path_for(stage, node),
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
        self.running_node = None
        # 进程收尾 = 释放执行权（按钮恢复可用、下一次点击可受理）。
        # 放在这里是唯一出口：正常结束、被杀、看门狗兜底都汇到本方法。
        self._release_run()
        if status == "success" and self.task_id:
            if stage == "extract":
                # 页面清单只由 extract 输出决定；detect/rembg 结果留在各自目录，
                # 不回写清单，避免污染 extract 预览和后续步骤的输入。
                # ⚠️ 清单与目录都按**跑的那个节点**（B 方案）：副本节点的页清单
                #    落 ``pages~<节点>.json``，读的时候也按节点读——写 A 读 B
                #    就是"跑完了还是空的"。
                output_dir = self.store.node_or_stage_output(
                    self.task_id, node, stage
                )
                page_count = len(
                    self.store.refresh_pages_from_dir(
                        self.task_id, output_dir,
                        **self._node_scope(node),
                    )
                )
                self._logs.append(f"页面清单已刷新（{page_count} 页）。")
                self._refresh_manifest()
                if page_count == 0:
                    self._toast(
                        "warning",
                        "结果为空",
                        f"{STAGE_LABELS[stage]} 未产生任何图片，请查看日志（可能参数有误）。",
                    )
            if stage == "print":
                pdf_path = self._latest_print_pdf_path()
                if pdf_path and pdf_path.exists():
                    self._logs.append(f"PDF 已生成：{pdf_path}")
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
                # ⚠️ 同一条道理清「取图内容已变」：source_mark 随 args 落进历史，
                #    这份 PDF 就是按**此刻**的取图目录内容生成的。
                self._print_data_stale = False
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
        if status == "success" and stage in ("detect", "detect_submit"):
            version = self._submit_version_state("detect")
            if stage == "detect":
                # 只检测完 = **这一步还没完成**（2026-10-22：提交才算完成），
                # 提示用户去提交，别让人以为可以直接进下一步。
                if version == "new_version":
                    override_toast = (
                        "info",
                        "检测完成",
                        "请核对检测框；确认后点「分割图片」把文本框内容裁出来，"
                        "下一步才能用",
                    )
            else:  # detect_submit
                # 裁好的图刚落地 → 下一步（去底色）的输入变了，刷一次第四步无关，
                # 但要把「已提交」说清楚（这是这一步的完成标志）。
                if version == "up_to_date":
                    override_toast = (
                        "success",
                        "提交完成",
                        "图片已按文本框裁好，可前往下一步「图片去底色」",
                    )
        if status == "failed":
            reason = failure or "退出码 " + str(exit_code)
            # 先落一行日志再弹 toast：toast 会自己消失，日志留在面板里
            self._logs.append_now(f"失败原因：{reason}")
            self._toast("error", f"{STAGE_LABELS.get(stage or '', '')}失败", reason)
        elif override_toast is not None:
            self._toast(*override_toast)
        else:
            self._toast(
                "success" if status == "success" else "error",
                # ⚠️ stage 收尾时可能已被清成 None（get(None) 运行时返回默认值，
                #    这里显式兜成空串语义相同）
                STAGE_LABELS.get(stage or "", ""),
                STATUS_LABELS.get(status, status),
            )
        # ⚠️ 收尾最后再冲刷一次日志攒批：本方法里还有几行收尾日志（页面清单/
        #    PDF/失败原因），不冲就会压在窗口里等下一次定时器——阶段已经结束了，
        #    用户此刻看到的是"日志少了一截"。见计划 A1。
        self._logs.flush()
        # ⚠️ 收尾时**立即**重算一次检测统计：上面 ``_flush_annotations`` 只标脏
        #    起节流（1s 后才会到点），而这一步已经结束——统计必须立刻是准的。
        self._refresh_stats_now()

    @staticmethod
    def _worker_env() -> QProcessEnvironment:
        """子进程强制 UTF-8：GUI 按 UTF-8 解析 JSON Lines，CLI 输出含 emoji。

        ⚠️ 同时把 ``GUJI_YOLO_REQUIRE_SERVICE`` 显式压成 ``"0"``：GUI 主进程自己
        是"强制走常驻服务"的（见 ``desktop.py`` 的 GUI 分支），但 detect **子进程**
        内回落加载 torch 是**可接受**的（独立进程，不冻 GUI，也不会污染主进程），
        硬失败反而更糟。这里的覆盖会赢过继承来的值（``systemEnvironment`` 在
        ``insert`` 之前取值，之后 insert 即改掉它）。
        """
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        env.insert("GUJI_YOLO_REQUIRE_SERVICE", "0")
        return env
