# -*- coding: utf-8 -*-
"""页面清单的缩略图与尺寸：图头尺寸缓存、编辑回写后的刷新、入口预热。"""

from __future__ import annotations

from pathlib import Path
from desktop.components.viewers.edit_sync import show_edited_image
from desktop.utils.files import THUMBNAIL_EDGE
from desktop.workers import ImageListWorker, connect_queued
from utils.file_utils import replace_with_retry
from ._qt import QSize, QImageReader
from typing import TYPE_CHECKING, Any, Callable, cast


#: 入口图片**预热**缩略图的上限（张）。用户 2026-10-21：所有步骤的缩略图都不
#: 必全部一次加载——只把首屏几屏生成到 ``thumbnails/input/``，更靠后的页等
#: 用户滚到可见窗口时由查看器现解码。
_ENTRY_THUMB_WARM_LIMIT = 60


class ManifestThumbsMixin:
    """缩略图/尺寸提供与编辑回写后的刷新。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _is_aggregate_input_node: Any
        _manifest_paths: Any
        _refresh_manifest: Any
        _refresh_preview: Any
        _scope_of: Any
        _size_node_for: Any
        _toast: Any
        detect_viewer: Any
        extract_input_viewer: Any
        extract_result_viewer: Any
        log_view: Any
        pages: Any
        preview_stack: Any
        rembg_viewer: Any
        run_worker: Any
        stack_index_of_step: Any
        stage_at_stack_index: Any
        store: Any
        task_id: Any

    #: 页缩略图的**图头尺寸**缓存（审计 D9）：键 = (路径, mtime)。
    #: 清单每次增删/重排都会重建，对 320 个条目逐个 `QImageReader.size()`
    #: 虽然只读文件头，主线程累计也有几十~几百毫秒；同一会话里缩略图
    #: 基本不变，缓存后重建清单是零读盘。（实例属性，惰性建——见 __init__）
    _thumb_size_cache: dict | None = None

    def _page_thumb_for(
        self,
        path_text: str,
        box=None,
        border_mm=None,
    ):
        """extract/rembg 数字页名 → 预生成页缩略图。

        box（原始像素坐标）非空时，返回在缩略图上按 border 规则
        **裁出该框**的效果图参数（坐标/边距按缩略图比例缩放）。返回：
        - {"path": 缩略图路径, "effect": {boxes, border, dpi} | None}
        - None：无可用缩略图，调用方回退真图

        2026-10-22 起没有 area：一条目就是一个框（或整页），
        不再需要并集/对称/整页模式这些分支。
        """
        p = Path(path_text)
        if not self.task_id:
            return None
        # ⚠️ **入口图片优先按图键查缓存**（用户 2026-10-17）：流程第一个节点是
        #    检测/去底色/排版时，输入是用户放进 ``stages/input/`` 的那批图——它们
        #    既不来自源 PDF（没有按页号的 source 缩略图），名字又未必是数字。
        #    导入时已生成了缩略图到 ``thumbnails/input/``，命中就用它，别回落到
        #    现解码原图（几千像素的扫描图，一页几百毫秒）。
        #    ⚠️ 必须在"数字页名"判据**之前**：入口图若也叫 ``1.jpg``，走数字
        #    分支会误取到**源 PDF** 第 1 页的缩略图（另一张图）。
        try:
            in_entry = p.parent == self.store.task_input_dir(self.task_id)
        except ValueError:
            in_entry = False
        if in_entry:
            cached = self.store.entry_thumb_path(self.task_id, p)
            return {"path": str(cached), "effect": None} if cached else None
        if not p.stem.isdigit():
            return None
        allowed = {
            self.store.extract_output_dir(self.task_id),
            self.store.rembg_output_dir(self.task_id),
            # ⚠️ 入口图片目录也要算：自定义流程里第一个节点可能是「检测文本框」
            # （用户2026-10-06），它的图就在这儿。不加的话这些图走"回退真图"
            #    ——功能正常，但左侧缩略图条会明显慢一截。
            self.store.task_input_dir(self.task_id),
        }
        # ⚠️ B 方案：副本节点（同一步骤的第二个及之后的节点）的产物目录
        #    （``stages/<阶段>~<节点>``）也要在白名单里。集合在切步骤/重建
        #    步骤条时算好（见 ``_rebuild_node_dirs``），这里只读不查流程图。
        allowed |= self.__dict__.get("_node_dirs") or set()
        if p.parent not in allowed:
            return None
        total = self.pdf_page_count or 0
        n = int(p.stem)
        if total and n > total:
            return None
        thumb = self.store.source_thumbnails_dir(self.task_id) / f"{n:04d}.jpg"
        if not thumb.exists():
            return None
        raw = [b for b in ([box] if box else []) if b]
        if not raw:
            return {"path": str(thumb), "effect": None}
        meta = self.store.image_size(
            self.task_id, p.stem, **self._scope_of(self._size_node_for(path_text))
        )
        if not meta:
            return {"path": str(thumb), "effect": None}
        try:
            cache_key = (str(thumb), thumb.stat().st_mtime)
        except OSError:
            cache_key = None
        # Mixin 宿主可能绕过 __init__（测试探针）：缓存字典惰性建
        cache = self.__dict__.get("_thumb_size_cache")
        if cache is None:
            cache = self._thumb_size_cache = {}
        if cache_key is not None and cache_key in cache:
            ts = cache[cache_key]
        else:
            ts = QImageReader(str(thumb)).size()
            if cache_key is not None:
                cache[cache_key] = ts
        if not ts.isValid() or not meta[0] or not meta[1]:
            return {"path": str(thumb), "effect": None}
        sx, sy = ts.width() / meta[0], ts.height() / meta[1]
        scaled = [[b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy] for b in raw]
        return {
            "path": str(thumb),
            "effect": {
                "boxes": scaled,
                "border": border_mm,
                "dpi": 300 * sx,  # border 像素随缩略图比例缩放
            },
        }

    def _pdf_page_count_ready(self, count: int) -> None:
        self.pdf_page_count = count

    def _original_image_size(self, path_text: str) -> QSize | None:
        """页面图片的原始像素尺寸：优先 extract 阶段写入 sizes.json 的记录。"""
        if self.task_id:
            meta = self.store.image_size(
                self.task_id,
                Path(path_text).stem,
                **self._scope_of(self._size_node_for(path_text)),
            )
            if meta:
                return QSize(meta[0], meta[1])
        size = QImageReader(path_text).size()
        return size if size.isValid() else None

    # -------------------------------------------------- 编辑器覆盖原图
    def _on_page_image_saved(self, path_text: str, image=None) -> None:
        """编辑器「完成」覆盖了某张页面图（extract/detect/rembg 预览转来）。

        磁盘上的图变了，派生数据按快慢两条线跟上，否则就是"编辑不生效"：
        1. **立即**（本调用内）：``sizes.json`` 同步新尺寸（检测框坐标与
           预览映射的像素基准，不跟上框就错位；只针对 extract 页面图），
           并把编辑结果直接上屏到 extract/detect 查看器的大图与条目图标
           （``apply_edited_image``，不等任何后台重解码）；
        2. **后台**：``thumbnails/source`` 页缩略图重生成（异步），完成后
           只刷条目图标兜底（大图已即时同步过）。
        rembg 结果等其他文件：无坐标基准，直接按文件刷新 rembg 显示。
        另按**被编辑文件所处的阶段**提示"下一步怎么让它生效"——用户原则
        （2026-10-01）：各步骤的编辑要串成一条链、最终落到 PDF。
        """
        if not self.task_id:
            return
        path = Path(path_text)
        size_node = self._size_node_for(path_text)
        extract_dir = self.store.node_or_stage_output(
            self.task_id, size_node, "extract"
        )
        if path.parent == extract_dir and path.stem.isdigit():
            reader = QImageReader(path_text)
            size = reader.size()
            if size.isValid():
                self.store.save_image_size(
                    self.task_id,
                    path.stem,
                    size.width(),
                    size.height(),
                    **self._scope_of(size_node),
                )
                self.log_view.append(
                    f"页面图片已更新：{path.name}"
                    f"（{size.width()}×{size.height()} px）；"
                    "检测框基于旧图坐标，失配时请重新执行检测。"
                )
            show_edited_image(self.extract_result_viewer, path_text, image)
            show_edited_image(self.detect_viewer, path_text, image)
            self._regen_page_thumb(path_text)
        else:
            # rembg 结果等：无坐标基准与页缩略图要跟，按文件刷新显示即可
            self.rembg_viewer.refresh_page(path_text)
            self._log_edit_downstream(path)

    def _log_edit_downstream(self, path: Path) -> None:
        """按被编辑文件所处阶段，提示"下一步怎么让这次编辑生效"。

        去底色的成品图与拼版成品、第四步待打印图：点「生成PDF」即生效。
        不属于这两类的路径（外部插入图等）不打日志。
        """
        task_id = self.task_id
        if task_id is None:
            return  # 已切走任务：既没有阶段目录可比，也没有按钮可改
        try:
            if path.parent == self.store.rembg_output_dir(task_id):
                self.log_view.append(
                    f"已编辑去底色结果「{path.name}」；"
                    "点「生成 PDF」即用上这次修改。"
                )
            elif path.parent == self.store.imposition_output_dir(task_id):
                self.log_view.append(
                    f"已编辑待打印图片「{path.name}」；"
                    "点「生成 PDF」即用上这次修改。"
                )
        except Exception:  # noqa: BLE001 - 提示不该影响刷新主链路
            pass

    def _on_single_extract_saved(self, path_text: str) -> None:
        """单页按需提取落盘完成（用户在 extract 预览里翻到了没提过的页）。

        与批量提取收尾**同一口径**：
        1. ``sizes.json`` 登记该页尺寸（检测框/预览映射的坐标基准）；
        2. ``refresh_pages_from_dir`` 按产物目录重建页面清单（runner 在批量
           提取成功后就是这么做的；单页提取产物也是 extract 目录的正式成员，
           下游 detect/rembg 必须能看到）。
        """
        if not self.task_id:
            return
        path = Path(path_text)
        size_node = self._size_node_for(path_text)
        extract_dir = self.store.node_or_stage_output(
            self.task_id, size_node, "extract"
        )
        if path.parent != extract_dir or not path.stem.isdigit():
            return
        reader = QImageReader(path_text)
        size = reader.size()
        if size.isValid():
            self.store.save_image_size(
                self.task_id,
                path.stem,
                size.width(),
                size.height(),
                **self._scope_of(size_node),
            )
        self.store.refresh_pages_from_dir(
            self.task_id, extract_dir, **self._scope_of(size_node)
        )
        self._refresh_manifest()
        self.log_view.append(f"第 {int(path.stem)} 页已提取（单页）。")

    def _regen_page_thumb(self, path_text: str) -> None:
        """后台重生成某页的 source 缩略图（256px），完成后刷新各查看器。"""
        worker = ImageListWorker([Path(path_text)], edge=THUMBNAIL_EDGE)
        # ⚠️ 调用方 _on_page_image_saved 已保证有任务在身
        owner_task = self.task_id
        assert owner_task is not None, "刷新缩略图时没有任务在身"
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.thumbnail_ready,
                    lambda _i, image, _p, t=path_text, o=owner_task: self._on_saved_thumb_ready(
                        image, t, o
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    w.failed,
                    lambda msg: self._toast("warning", "缩略图刷新失败", msg),
                    thread,
                ),
                w.completed.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_saved_thumb_ready(self, image, path_text: str, owner_task: str) -> None:
        """新缩略图就绪：原子替换缓存文件，条目图标兜底刷新。

        大图已在 _on_page_image_saved 里用编辑结果即时上屏，这里只把
        图标从「编辑结果现缩的临时版」换成「与文件一致的缓存版」。
        """
        if owner_task != self.task_id or image.isNull() or self.task_id is None:
            return  # 复制/编辑期间切了任务，旧任务的缩略图不能写进新任务
        path = Path(path_text)
        if not path.stem.isdigit():
            return
        thumb = self.store.source_thumbnails_dir(self.task_id) / (
            f"{int(path.stem):04d}.jpg"
        )
        thumb.parent.mkdir(parents=True, exist_ok=True)
        # 原子写：预生成缩略图随时会被缩略图条/清单读取，半截图就是花图标
        temp = thumb.with_name(f"{thumb.stem}.part.jpg")
        if not image.save(str(temp), "JPEG", 90):
            temp.unlink(missing_ok=True)
            return
        replace_with_retry(temp, thumb)
        self.extract_result_viewer.refresh_page(path_text)
        self.detect_viewer.refresh_page(path_text)
        self.rembg_viewer.refresh_page(path_text)

    # --------------------------------------------------- 入口图片缩略图（导入即生成）
    def _warm_entry_thumbs(self, files) -> None:
        """给落在入口输入目录的图**后台生成缩略图缓存**（用户 2026-10-17）。

        用户口径：「检测文本框 / 图片去底色 / 图片拼版 / PDF排版」作为流程第一个
        节点时，它的输入是用户**引入的文件图片或文件夹**；此时左栏此前只能现解码
        原图（几千像素的扫描件）。所以**从引入那一刻起**就把缩略图生成到
        ``thumbnails/input/``，左栏直接读小图（:meth:`_page_thumb_for` /
        :meth:`_print_thumb_provider` 已在查它）。

        只处理祖先目录 == ``stages/input/`` 的图（入口图）；已有且不旧的缓存跳过
        （按 ``cache_usable``：不比源图旧、体积不像截断）。生成完成后刷一次预览
        把左栏的占位换成小图。

        ⚠️ **必须记住"已请求过预热的 (路径, mtime)"**（``_entry_thumb_warmed``）：
        读不出来的坏图永远写不出缓存，而 :meth:`_on_entry_thumbs_warmed` 完成
        后会再调本方法——没这道记忆就会"预热→刷预览→再预热"无限循环。记的是
        mtime，源图被编辑（mtime 变）后仍会重新预热。
        """
        if not self.task_id:
            return
        try:
            entry_dir = self.store.task_input_dir(self.task_id)
            cache_dir = self.store.input_thumbnails_dir(self.task_id)
        except ValueError:
            return
        candidates = []
        for item in files:
            if not item:
                continue
            try:
                path = Path(item)
            except TypeError:  # 非法路径（None/奇怪对象）：跳过
                continue
            if path.parent == entry_dir:
                candidates.append(path)
        if not candidates:
            return
        from desktop.workers.thumb_cache_worker import (
            ImageThumbCacheWorker,
            cache_usable,
            stat_mtime,
            thumb_cache_file,
        )

        warmed = self.__dict__.setdefault("_entry_thumb_warmed", {})
        todo = []
        for path in candidates:
            mtime = stat_mtime(path)
            if cache_usable(thumb_cache_file(cache_dir, path), mtime):
                continue
            key = str(path)
            if warmed.get(key) == mtime:
                continue  # 这张已经请求过预热且源没变（多为读不出来的坏图）
            todo.append(path)
            # ⚠️ 先记下**全部**待预热图（含下面被限额跳过的）：完成回调会经
            #    _refresh_preview 再调本方法，只记账不跳过就会一轮接一轮地把
            #    整本书都预热完——那正是"缩略图全部一次加载"的老毛病。
            warmed[key] = mtime
        if not todo:
            return
        # 只预热首屏那几屏（用户 2026-10-21「所有步骤缩略图不用全部一次加载」）：
        # 其余页面滚动到时由查看器按可见窗口现解码，不在这里提前付 CPU。
        todo = todo[:_ENTRY_THUMB_WARM_LIMIT]
        worker = ImageThumbCacheWorker(todo, cache_dir, edge=THUMBNAIL_EDGE)
        owner_task = self.task_id
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.completed,
                    lambda o=owner_task: self._on_entry_thumbs_warmed(o),
                    thread,
                ),
                w.completed.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_entry_thumbs_warmed(self, owner_task: str) -> None:
        """入口图片缩略图生成完：重刷当前预览，把占位图标换成缓存小图。

        ⚠️ 防串任务：后台生成期间用户可能已切走，旧任务的缓存不能刷进新任务。
        重刷会**再次**调 :meth:`_warm_entry_thumbs`，但那时缓存已齐（``todo`` 空）
        ⇒ 不会再起 worker，不会循环。
        """
        if owner_task != self.task_id:
            return
        self._refresh_preview()

    # ------------------------------------------------------------------ 增删
    def _active_page_viewer(self):
        """当前预览阶段对应的可编辑查看器（detect 或 extract）。

        ⚠️ 判据走 ``preview_stack.currentIndex()``（**栈页号**）经
        ``stage_at_stack_index`` 反查阶段，**不要**拿它跟 ``== 1`` 比：
        那是默认流程下detect 的页号，自定义流程里 detect 完全可能是 0
        （它是第一个节点时），写死1 会把 detect 的增删插接到 extract 上去。
        """
        stage = self.stage_at_stack_index(self.preview_stack.currentIndex())
        if stage == "detect":
            return self.detect_viewer
        if stage == "extract" and self._is_aggregate_input_node():
            # 聚合任务的提取起点显示的是**只读图片清单**（没有 PDF 可看）：
            # 增删/定位/编辑这些动作要落到真正在屏上的那个控件上。
            # 检测起点本就用 detect_viewer、去底色起点用原图/成品对比查看器
            # （输入与产出都已汇集进来），不需要这里的替身。
            return self.extract_input_viewer
        return self.extract_result_viewer

    def _refresh_downstream_preview(self, source_step: str) -> None:
        """改了 ``source_step`` 那一格的图，顺手把它的下游预览也刷一遍。

        ⚠️ 此前这里写死 ``preview_stack.currentIndex() == 0`` ⇒
        ``_refresh_preview(1)``：``0``/``1`` 是**默认流程**里 extract/detect 的
        栈页号。自定义流程把 detect 放第一位时，"extract 改完顺手刷 detect"
        就变成了"extract 改完把 extract 自己再刷一遍"，而 detect 的预览压根
        没刷新（用户看到的仍是旧图）。现在按 **step key** 查页号。

        只有当 ``source_step`` 那一格**正被看着**时才刷下游——不是无脑全刷。
        """
        if self.stage_at_stack_index(self.preview_stack.currentIndex()) != source_step:
            return
        index = self.stack_index_of_step("detect")
        if index is not None:
            self._refresh_preview(index)

    def _viewer_index_to_manifest_index(self, viewer, row: int) -> int:
        """把预览区的行号换算成页面清单里的下标。

        预览区展示的是"文件确实存在"的那部分页面（``_manifest_paths``），
        清单里可能有条目对应的图片已被外部删除，两者行号会错位——直接拿
        行号去 pop/insert 会删错页、插错位置。这里按路径反查。
        """
        paths = self._manifest_paths()
        if row < 0 or row >= len(paths):
            return -1
        target = str(paths[row])
        for index, page in enumerate(self.pages):
            if str(page.get("file")) == target:
                return index
        return -1
