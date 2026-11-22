# -*- coding: utf-8 -*-
"""页面清单与当前步骤输入目录的对齐（含聚合任务起点判定）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from .reconcile import reconcile_page_files


class ManifestSyncMixin:
    """清单同步：把页面清单对齐到当前步骤的输入目录。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _node_scope: Any
        current_stage: Any
        imposition_effective: Any
        log_view: Any
        node_of_stage: Any
        store: Any
        task_id: Any

    # ------------------------------------------------------------------ 清单
    def _current_stage_input_dir(self):
        """**当前这一步**的图片输入目录（插图与取图都问它）。

        ⚠️ 走 ``stage_input`` 而不是"extract 输出目录"：前者按图解析、无上游
        时回落到 ``stages/input/``（用户 2026-10-06 要求"第一个节点一定有
        输入可用"）。拼版开关会影响取图来源，所以一并传进去。
        """
        if not self.task_id:
            return None
        stage = self.current_stage()
        if not stage:
            return None
        # ⚠️ 按**节点**取输入（B 方案）：同一步骤的多个节点各有输入来源
        #    （各自的连线回溯），单节点时就是主节点、与旧口径逐字节一致。
        node = self.node_of_stage(stage)
        if node:
            return self.store.node_input(
                self.task_id, node, "pages", self.imposition_effective()
            )
        return self.store.stage_input(
            self.task_id, stage, "pages", self.imposition_effective()
        )

    def _sync_manifest_to_input(self) -> None:
        """按**当前步骤的输入目录**重建页面清单。

        ⚠️ 以前只有 extract 跑成功才刷新清单（``runner`` 里那个
        ``if stage == "extract"``），于是"流程里没有 extract"的任务清单永远
        是空的——即便用户已经往 ``stages/input/`` 放了图、或者从界面插了图，
        预览仍显示"暂无图片，请先完成提取"（用户 2026-10-06 报障）。

        ⚠️ 两个"不覆盖用户意图"的红线（2026-10-17 补充）：

        - 清单里的页**就在当前输入目录** ⇒ 一字不动（插过图/删过页/重排过都是
          用户的明确选择）；
        - 清单**整个属于别的目录**（上游换了：拼版刚产出成品、换了节点、上游
          重跑换了产物）⇒ 作废重建。此前只在"清单为空"时重建，于是上游的产物
          换了以后清单还停在旧图上——用户看到的就是"第二步没有拿上一步的
          输出当输入"（B 方案：输入输出一律由图上的连线决定）。
        """
        if not self.task_id:
            return
        # ⚠️ 「PDF排版」与「图片拼版」各有自己的文档（``print.json`` / 拼版版面），
        #    页条上的清单不服务它们。这两步的输入目录是**成品**目录，拿它重建
        #    会把提取/检测那几步的页集合整体换掉——在步骤之间来回切就会反复
        #    覆盖，用户的删页/插页随之丢失。
        from desktop.steps import ports as _ports

        if _ports.STAGE_STEPS.get(self.current_stage(), "") in (
            "print",
            "imposition",
        ):
            return
        # ⚠️ 聚合任务的**提取起点**没有输入（成员的源 PDF 不搬，见
        #    ``aggregate_ingest.INPUT_COPY_STAGES``）：页清单取它的**产出**
        #    ——汇集进来的整本书。检测/去底色起点不在这里特判：它们的输入
        #    已由汇集器搬进 ``stages/input``（入口输入天然生效），走下面
        #    普通路径按输入目录重建即可；PDF排版/拼版起点在方法开头早退。
        if self._aggregate_start_stage() == "extract":
            node = self.node_of_stage("extract")
            out_dir = self.store.node_or_stage_output(
                self.task_id, node, "extract", "pages"
            )
            self.pages = self.store.refresh_pages_from_dir(
                self.task_id, out_dir, **self._node_scope()
            )
            return
        # ⚠️ **上游的产出动作没成功执行过 ⇒ 这一步没有正式输入**（用户
        #    2026-11-04「检查所有的步骤」）。此前这里只按目录重建清单，于是
        #    未生效的目录内容会被写进清单，提交/统计/YOLO 导出/按钮状态全都
        #    拿到旧图。现在只在内存里清空、**不落盘**——``pages.json`` 保留用户
        #    之前的页序，等上游执行成功后按目录重建即可。
        current = self.current_stage()
        if (
            current
            and "pages" in _ports.stage_inputs(current)
            and not self._stage_input_visible()
        ):
            self.pages = []
            return
        directory = self._current_stage_input_dir()
        if directory is None or not directory.is_dir():
            return
        if self.pages:
            inside = any(
                Path(str(page.get("file") or "")).parent == directory
                for page in self.pages
            )
            if inside:
                # ⚠️ 目录没变 ≠ 清单还有效（2026-10-25 用户报障：检测提交从
                #    PNG 改成 JPEG 后，旧 pages.json 仍指向同目录的 .png；文件
                #    已被替换成 .jpg，预览却显示「暂无图片」）。
                #    按 **stem** 对齐实际文件：同 stem 换格式就更新路径，jpg/png
                #    都支持；只有一条都对不上才整表重建。
                kept, resolved = reconcile_page_files(self.pages, directory)
                if resolved < 0:  # 目录读不了：保持原清单，不误清空
                    return
                if resolved > 0:
                    if kept != self.pages:
                        self.pages = kept
                        self.store.save_pages(
                            self.task_id, self.pages, **self._node_scope()
                        )
                        self.log_view.append(
                            "页面清单里有文件换了格式，已按同名文件更新"
                            "（jpg/png 都支持）。"
                        )
                    return
                self.log_view.append(
                    "页面清单里的文件已全部找不到，已按当前输入目录重建。"
                )
                self.pages = []
            else:
                # 旧清单整个属于**另一个**输入源：作废（上游产物已经换了）
                self.log_view.append(
                    "上游产物已更新，页面清单已按本步骤的输入目录重建。"
                )
                self.pages = []
        # ⚠️ 清单落点按**节点**（B 方案）：副本节点的页集合写它自己的
        #    ``pages~<节点>.json``，不覆盖主节点那份。
        self.pages = self.store.refresh_pages_from_dir(
            self.task_id, directory, **self._node_scope()
        )

    def _aggregate_start_stage(self) -> str | None:
        """本任务是聚合任务、且**当前步骤就是它的起点**时返回起点阶段。

        判据（三者同时成立）：

        1. 本任务是聚合任务（``kind == "aggregate"``）；
        2. 当前步骤就是它的起点（``member_stage``）；
        3. 流程图上找得到这个阶段的节点（用户改图把起点删了就按普通步骤算）。

        起点节点的图片由子任务汇集而来（:mod:`desktop.services.aggregate_ingest`
        搬成员该节点的**输入 + 产出**，2026-11-18 晚口径："x 的输入做了聚合
        开始节点的输入，x 的输出作为聚合开始节点的输出"）。
        """
        if not self.task_id:
            return None
        try:
            record = self.store.get_task(self.task_id) or {}
        except Exception:  # noqa: BLE001 —— 读不到任务就当普通任务
            return None
        if record.get("kind") != "aggregate":
            return None
        stage = str(record.get("member_stage") or "")
        if not stage or self.current_stage() != stage:
            return None
        if not self.node_of_stage(stage):
            return None
        return stage

    def _is_aggregate_input_node(self) -> bool:
        """当前这一步是不是聚合任务的**纯展示起点**（只有「图片提取」）。

        是 ⇒ 这一步**没有可执行的东西**：成员的输入是源 PDF、不搬（
        ``aggregate_ingest.INPUT_COPY_STAGES`` 不含 extract），没有源 PDF
        就不能现场提取，屏上只需把汇集来的页图列出来。用户 2026-11-18（
        任务 0025）：

        > 选择的开始节点是提取图片，但是进入任务详情里面，提取图片里面没有
        > 显示任何图片…… 提取图片虽然是处理 PDF 的，但是此时作为输入节点，
        > 不需要 PDF，只需要图片列表显示出来。

        ⚠️ **其余起点（检测/去底色/拼版/PDF排版）不再是"输入节点"**（用户
        2026-11-18 晚：检测起点"不需要执行再次检测"是不对的——子任务的节点
        本来就能重跑，聚合起点同样保留完整操作能力）：输入与产出都由汇集器
        备好（产出记已完成，下游能直接跑），但这一步照常可以重跑/编辑，
        重跑的产物覆盖汇集来的那份。
        """
        return self._aggregate_start_stage() == "extract"

    def _stage_input_visible(self) -> bool:
        """当前这一步的输入是否**已经生效**（上游的产出动作真的执行过）。

        ⚠️ 只查目录是不够的：去底色只是切缩略图就会把成品写进
        ``stages/rembg``；检测没提交时上游目录也可能留有旧图。这些文件
        不该被当成正式输入——**产物没执行成功，下一步就不该有数据**
        （用户 2026-11-03）。判据统一走 store，见
        :meth:`desktop.store.tasks.TaskStore.node_input_effective`。
        """
        if not self.task_id:
            return False
        stage = self.current_stage()
        if not stage:
            return False
        active = self.imposition_effective()
        node = self.node_of_stage(stage)
        if node:
            return self.store.node_input_effective(self.task_id, node, "pages", active)
        return self.store.stage_input_effective(self.task_id, stage, "pages", active)

    def _stage_input_is_entry(self) -> bool:
        """当前这一步的图片输入是不是**用户自己的入口图片**（``stages/input/``）。

        ⚠️ 与 :meth:`_stage_input_visible` 是两个问题（用户 2026-11-21 报障）：

        - "生效了吗"问的是**上游**跑没跑——入口图没有上游可等；
        - "能不能往里放图"问的是**这个目录归谁**——归用户，放多久都行。

        混成一个判据的后果：流程里只有「图片去底色」（它打头、没有上游）时，
        入口目录本来就是**空的**（正因为空才等着用户导图），而"空 ⇒ 未生效"
        会把这一步判成"上游没执行"，插图直接被拦并弹"这一步的图片来自流程
        上游"。用户原话：**任何节点都可以作为第一个节点，都可以导入数据**。

        判据用"这一步输入目录 == 入口图片目录"：这类目录里的图**就是**本步
        的输入，插进去立刻可用；而指向上游产物目录（如 ``stages/detect`` 的
        裁图）时仍是"上游没跑就别塞"，那条守卫照旧成立。
        """
        if not self.task_id:
            return False
        directory = self._current_stage_input_dir()
        if directory is None:
            return False
        try:
            entry = self.store.task_input_dir(self.task_id)
        except (OSError, ValueError):
            return False
        try:
            return directory.resolve() == entry.resolve()
        except OSError:  # 网络盘/路径异常：按名字兜底比直接崩了好
            return directory == entry

    def _refresh_manifest(self) -> None:
        if not self.task_id:
            return
        self.pages = self.store.load_pages(self.task_id, **self._node_scope())
        self._sync_manifest_to_input()

    def _manifest_paths(self) -> list[Path]:
        """页面清单路径，**过滤掉已在磁盘上消失的页**。

        ⚠️ 存在性检查按**清单签名**缓存：``Path.exists()`` 是每页一次文件系统
        stat，本机实测 211 页 = 16ms、2000 页 ≈ 150ms。而「切换选中框类型」
        这类操作每次刷新都会走这里（还要连带重算整本书统计），主线程上就是
        肉眼可见的卡顿（用户 2026-10-17 报「点类型卡顿」）。

        失效靠签名比对（``tuple(p["file"])``，2000 页 ≈ 0.2ms）：导入 / 删页 /
        换任务都会改 `pages`，签名随之变化，缓存自动作废——比手工在各处调
        invalidate 可靠（`pages` 有七八处赋值点，漏一处就是"删了页还在"）。
        """
        signature = tuple(page.get("file") for page in self.pages)
        cached = getattr(self, "_manifest_paths_cache", None)
        if cached is not None and cached[0] == signature:
            return list(cached[1])
        paths = [Path(text) for text in signature if text and Path(text).exists()]
        self._manifest_paths_cache = (signature, paths)
        return list(paths)
