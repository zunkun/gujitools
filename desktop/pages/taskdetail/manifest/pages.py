# -*- coding: utf-8 -*-
"""页面清单的增删与插入（插入/上传的落点由 services 决定）。"""

from __future__ import annotations

from pathlib import Path
from desktop.utils.files import default_open_dir
from desktop.workers import connect_queued
from ._qt import QUrl, QDesktopServices, QFileDialog, QWidget
from typing import TYPE_CHECKING, Any, Callable, cast


class ManifestPagesMixin:
    """页面增删、插入图片/文件夹、打开任务目录。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _active_page_viewer: Any
        _current_stage_input_dir: Any
        _node_scope: Any
        _refresh_downstream_preview: Any
        _refresh_preview: Any
        _refresh_source_actions: Any
        _stage_input_is_entry: Any
        _stage_input_visible: Any
        _toast: Any
        _viewer_index_to_manifest_index: Any
        _warm_entry_thumbs: Any
        current_stage: Any
        log_view: Any
        node_of_stage: Any
        pages: Any
        run_worker: Any
        store: Any
        task_id: Any

    def delete_selected_page(self) -> None:
        """删除当前选中的页面：按路径反查 manifest 下标后落盘。

        预览行号不能直接用于删除——文件缺失会导致查看器行号与清单下标错位；
        故先经 _viewer_index_to_manifest_index 按路径反查真实下标再 pop，
        删除后刷新预览并同步 detect/extract 两侧。
        """
        if not self.task_id:
            return
        viewer = self._active_page_viewer()
        row = viewer.strip.currentRow()
        if row < 0:
            self._toast("warning", "提示", "请先选择要删除的页面。")
            return
        index = self._viewer_index_to_manifest_index(viewer, row)
        if index < 0:
            self._toast("warning", "提示", "该页面已不在清单中，请刷新后重试。")
            return
        removed = self.pages.pop(index)
        self.store.save_pages(self.task_id, self.pages, **self._node_scope())
        self.log_view.append(f"已删除页面：{removed.get('label')}")
        self._refresh_preview()
        self._refresh_downstream_preview("extract")

    def insert_pages_from_folder(self) -> None:
        """「选文件夹」按钮：把**一个目录**里的图片批量插进来（用户 2026-10-06）。

        为什么要单独一条：``QFileDialog.getOpenFileNames``（原
        :meth:`insert_pages` 用的）**选不了目录**——原生 Windows 对话框只接受
        文件。而"把整本扫描结果的文件夹丢进来"恰恰是最自然的批量用法，所以
        必须有一个**目录**选择框。

        展开规则复用 :meth:`StepSpec.collect_files`：先看顶层，顶层空而只有
        一个子目录装着图就下钻那一层；**多个子目录各装图时不猜**（返回空并
        提示），因为把不同书的页混在一起要到看结果时才发现错了。
        """
        if not self.task_id:
            return
        directory = QFileDialog.getExistingDirectory(
            cast("QWidget", self),
            "选择图片文件夹（把里面的图片批量插入）",
            str(default_open_dir()),
        )
        if not directory:
            return
        self._insert_paths([directory], title="插入文件夹")

    def _insert_paths(self, paths, title: str = "插入图片") -> None:
        """把一批路径（文件**或目录**）插成页面图片——两个入口共用的实现。

        :param paths: 用户选中的原始路径，可以混着文件与目录；
        :param title: 失败提示的措辞（"插入图片"/"插入文件夹"）。
        """
        from desktop.steps import ports

        current = self.current_stage()
        if (
            current
            and "pages" in ports.stage_inputs(current)
            and not self._stage_input_is_entry()
            and not self._stage_input_visible()
        ):
            # 上游没执行成功时，这一步的"输入目录"其实是上游的正式产物目录；
            # 往里塞图既不会被看见（可见性仍要求上游成功），又可能被当成上游
            # 产物（用户 2026-11-04「检查所有的步骤」）。
            #
            # ⚠️ 入口节点（目录就是 ``stages/input/``）**不受这条拦**（用户
            # 2026-11-21）：那目录归用户，空着只说明"还没导图"，正是要插的
            # 时候。流程里只有「去底色」这一步时它打头、没有上游，旧判据把
            # "空"读成"上游没跑"，导图就被挡在门外（见 _stage_input_is_entry）。
            self._toast(
                "warning",
                "上游尚未执行",
                "这一步的图片来自流程上游：请先把上游步骤执行成功，再插入图片。",
            )
            return
        spec = ports.spec_for_stage(current)
        sources = (
            spec.collect_files(paths) if spec is not None else [Path(p) for p in paths]
        )
        sources = [p for p in sources if p.is_file()]
        if not sources:
            self._toast(
                "warning",
                "没有可用的图片",
                f"{title}：选中的位置里没有找到本步骤能处理的图片文件。",
            )
            return
        target_dir = self._current_stage_input_dir()
        if target_dir is None:
            self._toast(
                "error",
                "无法插入",
                "这一步的图片输入尚未接好，请检查流程配置。",
            )
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        # ⚠️ **已经在输入目录里的图跳过复制**（用户选了入口目录本身、或重选了
        #    同一批图）：否则下面 `while target.exists()` 会把它重命名成
        #    "xxx-1.png" 再塞进去，同一张图在清单里出现两次。
        jobs: list[tuple[Path, Path]] = []
        already: list[Path] = []
        try:
            resolved_dir = target_dir.resolve()
        except OSError:  # 目录刚建好/网络盘偶发失败：退化为"不跳过"
            resolved_dir = target_dir
        for source in sources:
            try:
                in_place = source.resolve().parent == resolved_dir
            except OSError:
                in_place = False
            if in_place:
                already.append(source)
                continue
            target = target_dir / source.name
            counter = 1
            while target.exists():
                target = target_dir / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            jobs.append((source, target))
        if already:
            added = self._append_pages_to_manifest(already)
            if not added:
                self.log_view.append("选中的图片都已在页面清单中，无需重复添加。")
        if not jobs:
            if already:
                self._refresh_preview()
            return
        # 主线程只算好 (源, 目标) 对（含重名避让）；复制进后台线程（审计 D2：
        # 大图逐张 copy2 在主线程会把界面冻住整个复制时长）。插入锚点在复制
        # 完成后按**当时的**选中行反查（_on_pages_copied）——用户在复制期间
        # 可能已经点了别的行。
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker(jobs)
        # ⚠️ 任务令牌（2026-09-26 第二轮审计 M2）：复制可能要几秒，期间用户
        #    已切到任务 B 的话，完成回调绝不能把 A 的文件插进 B 的清单。
        owner_task = self.task_id
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(self, w.finished, self._on_pages_copied, thread),
                connect_queued(
                    self,
                    w.failed,
                    lambda msg: self._toast("error", "插入图片失败", msg),
                    thread,
                ),
                w.finished.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )
        self._pages_copy_owner = owner_task

    def insert_pages(self) -> None:
        """「＋」按钮：插入**图片**（可多选），复制到当前这一步的输入目录。

        弹框选图后用当前选中行经路径反查得到 manifest 插入锚点；文件缺失时
        查看器行号与清单下标会错位，必须用路径。

        ⚠️ **想整目录导入走「📁 选文件夹」按钮**（:meth:`insert_pages_from_folder`）
        ——``getOpenFileNames`` 选不了目录，别指望在这里选中文件夹。

        ⚠️ **复制目标必须问"这一步的输入在哪"，不能写死 extract 目录**
        （用户 2026-10-06）。自定义流程里第一个节点可能是「检测文本框」，
        它的 ``pages`` 输入既不是 extract 目录、也还没有任何上游产物——
        写死 extract 目录的后果是"图插进去了，这一步却还是读不到"
        （界面表现为插完左侧列表空着）。这里走
        ``store.stage_input``，它在无上游时回落到 ``stages/input/``，
        与执行时读的是**同一个目录**。
        """
        if not self.task_id:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            cast("QWidget", self),
            "插入图片（可多选）",
            str(default_open_dir()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not paths:
            return
        self._insert_paths(paths)

    def _append_pages_to_manifest(self, files) -> int:
        """把一批**已在输入目录里**的文件追加到清单并落盘（不复制）。

        ⚠️ 追加到**末尾**而不是"选中行之后"：这条路径没有"选中行"可用
        （用户可能一个都没选就选了文件夹），插到中间去反而会打乱页序。

        ⚠️⚠️ **按路径去重**：用户选了输入目录本身时（外加"清单已含这批图"
        这个常见组合）会走到这里，不去重的话同一张图在清单里出现两次——
        左侧列表与页序都会跟着重复（实测过）。返回**实际新增**条数，供调用方
        决定要不要提示（0 = 全都已在清单里）。
        """
        if not files:
            return 0
        # ⚠️ 调用链（insert_pages / insert_pages_from_folder）已保证有任务在身
        task_id = self.task_id
        assert task_id is not None, "追加页面清单时没有任务在身"
        known = {str(p.get("file")) for p in self.pages}
        added = 0
        for source in files:
            key = str(source)
            if key in known:
                continue
            known.add(key)
            self.pages.append({"file": key, "label": source.stem})
            added += 1
        if not added:
            return 0
        self.store.save_pages(task_id, self.pages, **self._node_scope())
        # 入口图片**引入即生成缩略图**（用户 2026-10-17）：已在输入目录里的图也要
        # 有缓存，左栏才不至于现解码原图。
        self._warm_entry_thumbs([Path(f) for f in files])
        return added

    def _on_pages_copied(self, done: list, errors: list) -> None:
        """后台复制完成后：把成功对插入清单、保存并刷新（主线程）。"""
        if not self.task_id or not done:
            if errors:
                self._toast("error", "插入图片失败", errors[0][1])
            return
        # 复制期间切了任务：这批文件属于旧任务的 extract 目录，不能进新任务
        if getattr(self, "_pages_copy_owner", None) != self.task_id:
            self.log_view.append("已切换任务，忽略上一次未完成的图片插入。")
            return
        viewer = self._active_page_viewer()
        row = viewer.strip.currentRow()
        anchor = self._viewer_index_to_manifest_index(viewer, row)
        insert_at = anchor + 1 if anchor >= 0 else len(self.pages)
        for _source, target in done:
            target_path = Path(target)
            self.pages.insert(insert_at, {"file": target, "label": target_path.stem})
            insert_at += 1
        self.store.save_pages(self.task_id, self.pages, **self._node_scope())
        note = f"已插入 {len(done)} 张图片。"
        if errors:
            note += f"（{len(errors)} 张失败：{errors[0][1]}）"
            self._toast("warning", "部分图片插入失败", errors[0][1])
        self.log_view.append(note)
        # 这批新图落在入口目录时，**复制完即生成缩略图**（用户 2026-10-17）
        self._warm_entry_thumbs([Path(target) for _source, target in done])
        self._refresh_preview()
        self._refresh_downstream_preview("extract")
        # ⚠️ 插完图"缺入口图片"可能就解除了：红字/高亮/提示层要当场收掉，
        #    不能等下次进任务才对（与 _apply_source 补完 PDF 同一个道理）
        self._refresh_source_actions()

    # ------------------------------------------------------------------ 杂项
    def _image_selected(self, index: int, path_text: str) -> None:
        pass  # 预览组件内部已渲染大图，此处留作扩展

    def _open_task_dir(self) -> None:
        """打开**当前流程节点**的产物目录（右下角「打开任务目录」）。

        用户 2026-10-18："打开的是当前任务节点的目录"，且"如果任务节点打不开，
        打开任务目录；如果能打开节点目录，打开节点目录，其次是任务目录"。
        此前恒开任务根目录（``tasks/<任务号>/``），看某一步产物时还得自己翻
        ``stages/<阶段>``；现在优先落到**正看着的那一步（当前格对应的节点）**
        的产物落点，同一步骤有多个节点时也各归各（B 方案：副本落 ``~<节点>``）。
        """
        if self.task_id:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current_node_dir())))

    def _current_node_dir(self) -> Path:
        """「打开任务目录」的目标：**节点产物目录优先，其次任务根目录**。

        用户 2026-10-18：

        > 如果任务节点打不开，打开任务目录；如果能打开节点目录，打开节点目录，
        > 其次是任务目录。

        ⚠️ **必须判"打得开吗"（目录存在）再选**：节点产物目录是**跑过那一步才
        有**的（``stages/extract[~<节点>]`` / ``stages/rembg[~<节点>]`` /
        ``stages/imposition[~<节点>]`` / ``stages/print[~<节点>]``）；没产出时
        ``openUrl`` 指过去＝**点了没反应**（这正是用户"并非所有任务节点都能打开"
        的现场）。任务根目录建任务时就建好了、恒在，所以它是可靠的兜底。

        节点目录的按阶段口径（与执行端的 :meth:`_output_path_for` 同源）：

        - 「PDF排版」产物是 PDF（``stages/print[~<节点>]/print.pdf``）⇒ 取它
          所在目录；
        - 「图片去底色」⇒ 成品图目录 ``stages/rembg[~<节点>]``（执行后才有）；
        - 「检测文本框」不落页面图目录——产物是任务根下的 ``boxes[~<节点>].json``
          （参考缩略图 ``thumbnails/detect[~<节点>]`` 只是界面缓存、不是产物）
          ⇒ 没有节点目录，直接回落任务根，正好能看到那个坐标文件；
        - 其余（提取 / 拼版）⇒ 按节点取端口 ``pages`` 的落点。

        节点目录不存在 / 阶段认不出 / 节点没登记对应端口（自定义流程、图坏了）
        一律回落到任务根目录（与改造前逐字节一致）。
        """
        task_id = self.task_id
        if task_id is None:
            return Path()
        stage = self.current_stage()
        node = self.node_of_stage(stage) if stage else None
        candidates: list[Path] = []
        if stage == "print":
            candidates.append(self.store.scoped_stage_dir(task_id, node, "print"))
        elif stage == "rembg":
            # 去底色：成品图目录（可能还没产出）
            try:
                candidates.append(
                    self.store.node_or_stage_output(task_id, node, "rembg")
                )
            except KeyError:
                pass
        elif stage and stage != "detect":
            try:
                candidates.append(
                    self.store.node_or_stage_output(task_id, node, stage, "pages")
                )
            except KeyError:
                pass
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return self.store.task_dir(task_id)
