# -*- coding: utf-8 -*-
"""创建任务（指纹 / 查重 / 建任务 / 后台导入）与删除任务。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Slot

from desktop import ui
from desktop.ui import theme as T
from desktop.ui.confirm_dialog import ConfirmDialog
from desktop.workers import (
    HashWorker,
    SourceThumbnailsWorker,
    close_cached_documents,
    connect_queued,
)
from desktop.utils.files import set_producing_marker
from desktop.pages.tasklist.page.constants import HEADER_SUBTITLE
from desktop.pages.tasklist.page.messages import _duplicate_message


class TaskListImportMixin:
    """从「创建任务」到后台复制/缩略图，以及删除任务。"""

    # ------------------------------------------------------------------ 创建任务
    def import_pdf(self) -> None:  # noqa: D401 - 见下方说明
        """「创建任务」入口：**切到创建任务页**（不再弹模态窗）。

        用户 2026-10-06：「创建任务不再是弹窗，而是进入二级页面」。本方法只
        发信号，真正切页由壳层做（列表页不认识壳层）。
        """
        self.create_requested.emit()

    def start_create(self, path: str, name: str, diagram) -> None:
        """创建任务页提交了 → 走**既有**的指纹/查重/建任务链路。

        ⚠️ 这一页只负责收集输入（PDF、任务名、流程图），指纹计算、查重确认、
        预热详情页都还在这里（逻辑一字未改）——创建页重做一遍只会引入两套
        指纹/查重逻辑，那种重复历史上已经出过 bug。

        :param path: PDF 路径；**空串 = 还没选 PDF**（用户 2026-10-06
            「PDF 输入不是必须的」）。这时**跳过整个指纹/查重链路**直接建
            任务：没有文件就无从算指纹，无从查重。空壳任务建好后进详情页，
            那边有补选 PDF 的入口。
        :param diagram: 流程图（``None`` = 没编辑过，用默认流程模板字节拷贝；
            用户 2026-11-17 起"是否自定义"不再单独传——流程恒可编辑，
            编辑保存过才传图）
        """
        self._pending_diagram = diagram
        self._pending_name = str(name or "").strip()
        if not str(path or "").strip():
            # 空壳任务：不等文件，直接建（名字留空 ⇒ store 用「任务#实际号」）
            self._create_imported_task(Path(), "")
            return
        if self.hash_thread and self.hash_thread.isRunning():
            self._toast("warning", "正在创建",
                        "上一个文件指纹尚未计算完成，请稍候。")
            return
        self._start_import(Path(path))

    def _start_import(self, path: Path) -> None:
        """选定 PDF 之后：后台算指纹，完成后按查重结果建任务。"""
        # 按钮由 _init_ui 建好；这里断言只为让类型检查器收窄（可能为 None 的声明）
        assert self._import_button is not None
        self._import_button.setEnabled(False)
        # 指纹后台计算，完成后决定是否建任务（查重 → 确认）
        self.hash_thread = QThread(self)
        self.hash_worker = HashWorker(path)
        self.hash_worker.moveToThread(self.hash_thread)
        self.hash_thread.started.connect(self.hash_worker.run)
        # ⚠⚠ 必须走 ``connect_queued``：``_hash_ready``/``_hash_failed`` 定义在
        #     mixin（普通 Python 类）上，PySide 认不出"接收者是主线程的 QObject"，
        #     AutoConnection 就退化成**直连**——回调直接跑在哈希子线程里。
        #     接着 refresh() → _render() → TaskTable.set_data() 全在子线程，
        #     Qt 拒绝把单元格控件挂到表格视口，只刷一行
        #     ``QObject::setParent: Cannot set parent, new parent is in a
        #     different thread``，控件于是变成一个个独立的顶层小窗——标题是
        #     ``__main__``、内容是行内的任务名 / 「详情·删除」按钮，每导入一次
        #     就多一批堆在屏幕上（用户 2026-11-28 截图："感觉是表格的一部分被
        #     拆开了，而且越来越多"）。顺带表格还会显示不全（行在、格是空的）。
        #     连到 QObject 的**绑定方法**才安全，而 mixin 方法不是——
        #     判据见 ``workers/worker_host.py::connect_queued`` 的注释。
        # ⚠ 这两个中继**刻意不挂 thread**：``_hash_ready`` 里可能开模态查重
        #   弹窗（``.exec()``）。若中继绑在 ``hash_thread.finished`` 上被
        #   deleteLater，模态事件循环会把"正在执行 forward 的中继"删掉
        #   （use-after-free）。改由 ``_hash_thread_done`` 统一销毁——它排在
        #   同一队列里、一定在 ``_hash_ready`` 返回之后才跑。
        self._hash_relays = [
            connect_queued(self, self.hash_worker.finished, self._hash_ready),
            connect_queued(self, self.hash_worker.failed, self._hash_failed),
        ]
        self.hash_worker.finished.connect(self.hash_thread.quit)
        self.hash_worker.failed.connect(self.hash_thread.quit)
        self.hash_thread.finished.connect(self.hash_worker.deleteLater)
        # 同上：_hash_thread_done 要动「创建任务」按钮，不能在子线程里做
        connect_queued(
            self, self.hash_thread.finished, self._hash_thread_done, self.hash_thread
        )
        self.hash_thread.start()

    def _hash_thread_done(self) -> None:
        # 按钮由 _init_ui 建好；这里断言只为让类型检查器收窄（可能为 None 的声明）
        assert self._import_button is not None
        self._import_button.setEnabled(True)
        # 本次导入的两个中继到这里使命已尽：_hash_ready/_hash_failed 都已跑完
        # （见 _start_import 的说明），显式销毁，别让长会话反复导入攒一堆。
        for relay in getattr(self, "_hash_relays", ()):
            try:
                relay.deleteLater()
            except RuntimeError:  # C++ 侧已随页面销毁
                pass
        self._hash_relays = []
        # ⚠️ 线程对象也要销毁（parent=本页，只覆盖属性不会析构 C++ 对象）：
        #    每次导入一个，长期使用会一批批堆着（2026-11-21「内存越用越大」）。
        # ⚠⚠ 引用也必须**同步清空**（2026-11-28 用户报"再导入一次就报错"）：
        #    deleteLater 之后 C++ 对象已销毁，而属性还指着一个"空壳包装器"；
        #    下一次 ``start_create``/``import_pdf`` 的守卫
        #    ``if self.hash_thread and self.hash_thread.isRunning()`` 会直接抛
        #    ``RuntimeError: Internal C++ object (PySide6.QtCore.QThread)
        #    already deleted`` —— 第一次导入正常、第二次必炸。
        thread = self.hash_thread
        self.hash_thread = None
        self.hash_worker = None
        if thread is not None:
            try:
                thread.deleteLater()
            except RuntimeError:  # C++ 侧已销毁
                pass

    @Slot(str, str)
    def _hash_ready(self, path_text: str, source_hash: str) -> None:
        path = Path(path_text)
        duplicates = self.store.find_tasks(source_hash)
        if duplicates:
            if self._confirm_duplicate(path, duplicates):
                self._create_imported_task(path, source_hash, duplicate_confirmed=True)
            else:
                first = duplicates[0]
                # 走 focus_task 而不是 table.select_task：命中项可能在别的页上
                if self.focus_task(first["id"]):
                    self._toast(
                        "info",
                        "已定位到已有任务",
                        f"「{first['name']}」已在列表中选中",
                    )
                self.refresh()
                # ⚠️ 直接进那个任务的详情：用户刚走完"创建任务"这一页，
                #    停在创建页上会以为还能继续点（查重已经否掉了这次创建）。
                self.open_detail.emit(first["id"])
            return
        self._create_imported_task(path, source_hash)

    def _confirm_duplicate(self, path: Path, duplicates: list) -> bool:
        """发现相同内容文件时弹窗确认；返回 True 表示仍创建新任务。"""
        return bool(self._build_duplicate_dialog(path, duplicates).exec())

    def _build_duplicate_dialog(self, path: Path, duplicates: list) -> ConfirmDialog:
        """构造（**不弹出**）查重确认框。

        ⚠️ 构造与 ``exec()`` 分开：离屏自测绝不真弹模态（项目硬规则），自测
        只造框、验宽度/折行/红字，验完 ``deleteLater()``。

        ⚠️ 为什么不用 qfluent 的 ``Dialog``（2026-11-16 用户报"弹窗会随 PDF
        文件名加宽"）：它的 ``setContentText`` 让窗口按**单行自然宽度**算
        sizeHint，任务名默认就是 PDF 文件名，名字一长窗口就顶到屏幕边缘，长
        到一定程度还点不到按钮。``ConfirmDialog`` 宽度钉死、正文折行，名字
        再长也只让弹窗**变高**（三条"不响"的防线一并得到，见该模块头）。
        """
        dialog = ConfirmDialog(
            "发现相同文件",
            _duplicate_message(
                path.name, [t.get("name") or "" for t in duplicates]
            ),
            self.window(),
            rich=True,
            yes_text="创建新任务",
            cancel_text="定位已有任务",
        )
        return dialog

    @Slot(str)
    def _hash_failed(self, message: str) -> None:
        self._toast("warning", "指纹计算失败", f"{message}（未创建任务）")

    def _create_imported_task(
        self, path: Path, source_hash: str, duplicate_confirmed: bool = False
    ) -> None:
        """建任务 → 立刻出列表行 → 源文件副本与缩略图交给后台队列。

        ⚠️ **主线程只做「写一个 tasks.json」这一件事**（实测 ~5ms）。复制源
        文件（一本书几十 MB）和渲染整本缩略图（2400 页要 69s）都进后台：
        它们由 ``_thumb_queue`` 串行跑，**并且等列表行画完再放行**。

        为什么顺序这么讲究（实测见 ``.workbuddy/perf/``）：
        - 列表回程要读 N 个任务的 runs.json，无争抢时 7.5ms；一旦和渲染线程
          撞上，每次文件操作都要排 GIL 队列，「导入 → 看见新行」从 0.2s
          变成 0.5~2.5s；
        - 多个渲染线程并行时主线程 ``create_task`` 中位从 5ms 涨到 929ms。
        所以：**先出行，再放后台干活**，且一次只跑一个。
        """
        # ⚠️⚠️ **空壳判据必须把 "." 一起挡掉**（2026-11-17 任务 0017）：
        #    ``start_create`` 的空壳分支传的是 ``Path()`` —— 它在 pathlib 里
        #    就是 ``Path('.')``，``str()`` 是 "."（**真值**）。下面的
        #    ``str(path or "").strip()`` 挡不住它，于是空壳任务被当成
        #    "选了源文件"：① 给 thumbnails/source 立了假 `.producing` 标记
        #    （查看器白等一轮回扫）；② 往串行队列塞一个 ``pdf_path=Path('.')``
        #    的 worker —— 复制线程 ``copy('.')`` 报
        #    「[Errno 13] Permission denied: '.'」，``fitz.open('.')`` 报
        #    「'.' is no file」，用户看到两块错误 toast。与
        #    ``store.create_task`` 里那条 "Path('') 是 '.'" 的守卫同一口径。
        has_source = str(path or "").strip() not in ("", ".")
        # ⚠️ 任务名：创建页填了就用它；留空回落到**源文件名**，连PDF 都没选
        #    时回落到「任务#实际号」（两级回落都在 store.create_task 里，
        #    用户 2026-10-06：「任务名称可以有默认的」「没填写可以是上传的
        #    pdf 名称」）。改名入口在详情页页头的铅笔按钮。
        task_name = self._pending_name
        self._pending_name = ""
        task_id = self.store.create_task(
            path if has_source else None,
            source_hash,
            task_name,
            duplicate_confirmed=duplicate_confirmed,
            # 创建任务弹窗选了「自定义流程」才传；None = 默认流程
            # （store 内部从 ports 派生，见 TaskMixin.create_task）。
            diagram=self._pending_diagram,
        )
        # 流程是一次性的：只对**这一次**建的任务生效，别漏到下一个去
        self._pending_diagram = None
        self.refresh()
        # ⚠️ **先立"这个目录正有人在填"的标记，再放后台活、再进详情**
        #    （2026-10-21）：详情页的 PDF 查看器一进来就问"缩略图有人在填吗"，
        #    没有标记时它看不到生产者（此刻目录还是空的），于是自己又渲一遍
        #    整本——与导入任务各渲一遍，28 页 JPX 就是 56 次 ~850ms 的解码，
        #    用户看到的是"缩略图老半天不齐"。标记由 worker 收尾时撤掉。
        if has_source:
            # 空壳任务（没选 PDF）不会有缩略图生产者，别立标记（否则查看器
            # 白等一轮回扫）
            set_producing_marker(self.store.source_thumbnails_dir(task_id), True)
        # 用户下一步必是点进这一行：趁"刚点完导入"的等待期把详情页建出来
        self.import_queued.emit()
        # ⚠️ 直接进详情（用户 2026-10-06 第 4 条）：建完还停在列表页等于让
        #    用户再点一次。app.py 已把本信号连到壳层的 open_detail。
        self.open_detail.emit(task_id)
        # ⚠️ **空壳任务没有 PDF**：不排队任何后台活——SourceThumbnailsWorker
        #    会去开那个不存在的文件（白报错，还可能把整个串行队列卡住）。
        #    补选 PDF 由详情页的入口负责（store.set_task_source）。
        if not has_source:
            self._toast(
                "info", "任务已创建",
                "尚未选择源文件（PDF/DjVu），可在任务详情页右上角补选。",
            )
            return
        # 逐页缩略图 + 源文件副本：后台生成，落到任务目录 thumbnails/ 与根目录，
        # 之后不再清理。渲染的是**副本**，源文件随后被移动/删除都不影响本任务。
        worker = SourceThumbnailsWorker(
            path,
            self.store.source_thumbnails_dir(task_id),
            copy_to=self.store.task_dir(task_id) / path.name,
        )
        self._thumb_queue.submit(
            worker,
            label=path.name,
            on_warning=lambda msg: self._toast("warning", "副本保存失败", msg),
            on_failed=lambda msg: self._toast("warning", "缩略图生成失败", msg),
            tag=task_id,  # 归属标记：删这个任务时必须能精确停掉它自己的活
        )

    # ------------------------------------------------------ 导入进度提示
    def _on_import_job_started(self, label: str) -> None:
        """后台活开工：把「正在导入」写进页头副标题。"""
        self._import_progress = None
        self._show_import_status(self._import_status_text(0))

    def _on_import_progress(self, done: int, total: int) -> None:
        """缩略图渲染进度：把「12/123」写进页头。"""
        self._import_progress = (done, total)
        self._show_import_status(self._import_status_text(done))

    def _on_import_job_finished(self, label: str) -> None:
        """一个后台活结束：还有排队的就继续显示，全干完才恢复页头。"""
        if self._thumb_queue.busy():
            self._show_import_status(self._import_status_text(0))
            return
        self._import_progress = None
        self._show_import_status("")
        self._toast("success", "导入完成", f"{label} 已可处理")

    #: 提示文案里文件名的最大展示长度（页头是一行，长名会顶到右侧按钮）
    _IMPORT_NAME_LIMIT = 12

    def _import_status_text(self, done: int) -> str:
        """拼「正在导入」文案：干到哪、哪一本、后面还排了几个。"""
        name = self._thumb_queue.current_label() or "文件"
        if len(name) > self._IMPORT_NAME_LIMIT:
            name = name[: self._IMPORT_NAME_LIMIT] + "…"
        waiting = self._thumb_queue.pending_count()
        total = self._import_progress[1] if self._import_progress else 0
        if done and total:
            body = f"正在导入 · 缩略图 {done}/{total}"
        elif total:
            body = f"正在导入 · 已复制，共 {total} 页"
        else:
            body = "正在导入 · 复制源文件"
        body += f" · {name}"
        if waiting:
            body += f" +{waiting} 排队"
        return body

    def _show_import_status(self, text: str) -> None:
        """把「正在导入」写进**页头副标题**；空串则恢复默认说明。

        为什么不用 InfoBar 常驻条：qfluentwidgets 的 InfoBarManager 在
        ``showEvent`` 里登记，控件被隐藏再显示时会重复登记，列表里留下悬垂
        条目——之后任何一条 toast 自动关闭都会在 ``_updateDropAni`` 里对
        已销毁对象取属性，控制台刷 ``Internal C++ object already deleted``。
        页头是固定高度的，改副标题不会顶动右侧按钮，长驻状态放这里最稳。
        """
        if text:
            ui.apply_to(self._header.subtitle_label, T.SIZE_CAPTION, color=T.ACCENT)
            self._header.set_subtitle(text)
        else:
            ui.apply_to(self._header.subtitle_label, T.SIZE_CAPTION, color=T.INK_FAINT)
            self._header.set_subtitle(HEADER_SUBTITLE)

    # ------------------------------------------------------------------ 删除
    def delete_task(self, task_id: str) -> None:
        """删除指定任务及其全部中间产物（带确认弹窗）。

        任务不存在时直接返回；否则弹确认框，确认后删库并刷新列表与提示。
        """
        task = self.store.get_task(task_id)
        if not task:
            return
        dialog = ConfirmDialog(
            "删除任务", f"确定删除任务「{task['name']}」及其全部中间产物？",
            self, yes_text="删除",
        )
        if not dialog.exec():
            return
        # ⚠️ 先关掉预览缓存里可能还开着的这本 PDF（Windows 上打开的句柄
        # 会让 rmtree 一直 PermissionError，store 的重试救不了"永不关闭"）。
        # 此刻在任务列表页，没有查看器在用它，关掉是安全的。
        close_cached_documents()
        # ⚠️ 再停掉**这个任务自己的**后台导入（复制源文件 + 渲染整本缩略图，
        # 2400 页要 69s）。不停就删：rmtree 撞上正在写的文件（复制中的 .part
        # 还是打开的句柄）→ 重试 8 次后失败、弹「文件正被占用」；更糟的是删完
        # 后台线程还按旧路径继续写（2026-09-26 审计）。
        if not self._thumb_queue.cancel_tag(task_id, wait_ms=self.DELETE_STOP_WAIT_MS):
            # 等不到就**别硬删**：明确告诉用户稍后再试，比留半个目录好
            self._toast(
                "warning", "导入仍在收尾",
                "该任务的缩略图/源文件副本还在写，请几秒后再删除。",
            )
            return
        # 聚合任务的汇集线程同样可能在写这个目录（几百张图）：先等它收手。
        job = self._aggregate_jobs.pop(task_id, None)
        if job is not None:
            from desktop.workers.worker_host import stop_thread

            stop_thread(job[0], self.DELETE_STOP_WAIT_MS, "聚合汇集线程")
        if not self.store.delete_task(task_id):
            # 目录被占用时 store 会保留任务记录，不留孤儿目录
            self._toast("error", "删除未完成", "文件正被占用，请稍后重试。")
            return
        self.refresh()
        self._toast("success", "删除成功", task["name"])

    # ------------------------------------------------------ 聚合任务汇集
    def start_create_aggregate(self, members: list, member_stages: list, name: str,
                               diagram) -> None:
        """聚合任务提交了 → 建聚合任务（不走指纹/查重：聚合任务不吃源文件）。

        ``member_stages`` 与成员对齐（创建页 2026-11-17 本轮：全体共用
        一个起始节点，所以值都相同；老口径允许逐成员不同）；store 落库时取
        清单里最早的作 ``member_stage`` 并从它派生流程。成员不存在 / 节点
        非法时 ``store.create_aggregate_task`` 抛 ``ValueError``——这里 toast
        说清原因留在创建页，不崩。
        """
        from desktop.steps.aggregate import (
            aggregate_start_label,
            earliest_aggregate_stage,
        )

        try:
            task_id = self.store.create_aggregate_task(
                [str(m) for m in (members or [])],
                member_stages=[str(s) for s in (member_stages or [])],
                name=str(name or "").strip(),
                diagram=diagram,
            )
        except ValueError as exc:
            self._toast("warning", "无法创建聚合任务", str(exc))
            return
        self.refresh()
        # 建完直接进详情（与普通任务同一体验）
        self.open_detail.emit(task_id)
        earliest = earliest_aggregate_stage(member_stages)
        self._toast(
            "info", "聚合任务已创建",
            f"成员 {len(members)} 个，起始节点「"
            f"{aggregate_start_label(earliest) if earliest else '—'}」。"
            "正在把各成员的输入与产出汇集进来…",
        )
        # ⚠️ **必须后台做**：一本古籍几百页，逐页复制就是几十秒的界面冻结。
        #    做完发 aggregate_ready，由壳层决定要不要刷新详情页。
        self._start_aggregate_ingest(task_id)

    def _start_aggregate_ingest(self, task_id: str) -> None:
        """后台汇集聚合任务的成员产物（见 ``services/aggregate_ingest``）。"""
        from desktop.workers import AggregateIngestWorker

        try:
            worker = AggregateIngestWorker(self.store, task_id)
            # ⚠️ 起线程**之前**立标记：用户此刻已经被带进详情页（open_detail
            #    在调用本方法之前），晚一步就会先看到"输入还没就位"的误导提示。
            from desktop.services.aggregate_ingest import set_pending_marker

            set_pending_marker(self.store.task_dir(task_id), True)
        except Exception as exc:  # noqa: BLE001 - 建 worker 失败不该拖垮建任务
            self._toast("warning", "聚合汇集未能启动", str(exc))
            return
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # 同 `_start_import`：这两个回调也在 mixin 上 → 直连会跑在子线程，
        # 里面又要 refresh()、又要 toast，跨线程摸控件同样会炸出游离窗口。
        connect_queued(
            self, worker.finished, self._on_aggregate_ingest_finished, thread
        )
        connect_queued(
            self, worker.failed, self._on_aggregate_ingest_failed, thread
        )
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # 线程收尾就从表里摘掉：留着已删除的 QThread 包装，之后任何访问都会
        # 抛 RuntimeError（删任务前的"等它停"会踩到）。
        connect_queued(
            self,
            thread.finished,
            lambda tid=task_id: self._aggregate_jobs.pop(tid, None),
            thread,
        )
        self._aggregate_jobs[task_id] = (thread, worker)
        thread.start()

    @Slot(str, int, int, list)
    def _on_aggregate_ingest_finished(self, task_id: str, pages: int,
                                      copied: int, notes: list) -> None:
        """汇集完成：提示 + 让宿主刷新详情页（若正开着这个任务）。"""
        self.refresh()
        if pages:
            detail = f"共 {pages} 页（复制 {copied} 个文件）。"
            if notes:
                # 部分成员缺产物：说清第一个原因，别让用户以为"全都搬过来了"
                detail += f"（{notes[0]}）"
            self._toast(
                "success", "聚合输入已汇集",
                detail + "起始节点的输入与产出都已就位。",
            )
        else:
            self._toast(
                "warning", "聚合输入为空",
                "各成员在起始节点上都没有可用的图，请检查成员任务是否真跑完。"
                + (f"（{notes[0]}）" if notes else ""),
            )
        self.aggregate_ready.emit(task_id)

    @Slot(str, str)
    def _on_aggregate_ingest_failed(self, task_id: str, error: str) -> None:
        """汇集失败：任务已建好但内容不完整，说清怎么收拾。"""
        self._toast(
            "warning", "聚合汇集失败",
            f"{error}（可删除该聚合任务后重新创建）",
        )
