# -*- coding: utf-8 -*-
"""任务详情页的页面清单控制器：manifest 维护、缩略图/尺寸提供、页面增删。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl, QSize
from PySide6.QtGui import QDesktopServices, QImageReader
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import MessageBox

from desktop.components.viewers.edit_sync import show_edited_image
from desktop.ui import theme as T
from desktop.ui.widgets import mark_input_entry
from desktop.utils.files import (
    THUMBNAIL_EDGE, default_open_dir, list_stage_images,
)
from desktop.workers import HashWorker, ImageListWorker, connect_queued
from utils.file_utils import replace_with_retry


class PageListMixin:
    """依赖宿主页面提供的属性：store/task_id、pages、pdf_page_count、
    preview_stack、detect_viewer、extract_result_viewer、log_view、_toast()。"""

    #: 页缩略图的**图头尺寸**缓存（审计 D9）：键 = (路径, mtime)。
    #: 清单每次增删/重排都会重建，对 320 个条目逐个 `QImageReader.size()`
    #: 虽然只读文件头，主线程累计也有几十~几百毫秒；同一会话里缩略图
    #: 基本不变，缓存后重建清单是零读盘。（实例属性，惰性建——见 __init__）
    _thumb_size_cache: dict | None = None

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
        if stage is None:
            return None
        return self.store.stage_input(
            self.task_id, stage, "pages", self.imposition_effective()
        )

    def _sync_manifest_to_input(self) -> None:
        """按**当前步骤的输入目录**重建页面清单（清单为空时）。

        ⚠️ 以前只有 extract 跑成功才刷新清单（``runner`` 里那个
        ``if stage == "extract"``），于是"流程里没有 extract"的任务清单永远
        是空的——即便用户已经往 ``stages/input/`` 放了图、或者从界面插了图，
        预览仍显示"暂无图片，请先完成提取"（用户 2026-10-06 报障）。

        这里**只在清单为空时**重建，是刻意的：清单非空说明用户已经表达过
        "参与处理的是哪几页"（插过图、删过页、重排过），拿目录内容覆盖它
        等于把用户的增删悄悄撤销。非空时只保证它与输入目录一致地读出来。
        """
        if not self.task_id or self.pages:
            return
        directory = self._current_stage_input_dir()
        if directory is None or not directory.is_dir():
            return
        self.pages = self.store.refresh_pages_from_dir(self.task_id, directory)

    def _refresh_manifest(self) -> None:
        if not self.task_id:
            return
        self.pages = self.store.load_pages(self.task_id)
        self._sync_manifest_to_input()

    def _manifest_paths(self) -> list[Path]:
        return [Path(p["file"]) for p in self.pages if Path(p["file"]).exists()]

    def _page_thumb_for(self, path_text: str, box=None, parea: int = 1,
                        border_mm=None, boxes=None, full: bool = False):
        """extract/rembg 数字页名 → 预生成页缩略图。

        box（原始像素坐标）非空时，返回在缩略图上按 area/border 规则
        合成的效果图参数（坐标/边距按缩略图比例缩放）。返回：
        - {"path": 缩略图路径, "effect": {boxes, area, border, dpi, full} | None}
        - None：无可用缩略图，调用方回退真图

        ⚠️ ``boxes`` 优先：合成必须拿**原始检测框列表**而不是并集单框——
        双框 + area=2/3 若只给并集框，``compose_region_output`` 会误判为
        「单框 → 对称画布」（凭空多出一半空白镜像），与真实产出不符。
        ``full`` 由调用方按**原始槽位**判定后传入（整幅单框不镜像）。
        """
        p = Path(path_text)
        if not p.stem.isdigit() or not self.task_id:
            return None
        allowed = {
            self.store.extract_output_dir(self.task_id),
            self.store.rembg_preview_output_dir(self.task_id),
            self.store.rembg_output_dir(self.task_id),
            # ⚠️ 入口图片目录也要算：自定义流程里第一个节点可能是「检测文本框」
            #（用户2026-10-06），它的图就在这儿。不加的话这些图走"回退真图"
            #    ——功能正常，但左侧缩略图条会明显慢一截。
            self.store.task_input_dir(self.task_id),
        }
        if p.parent not in allowed:
            return None
        total = self.pdf_page_count or 0
        n = int(p.stem)
        if total and n > total:
            return None
        thumb = self.store.source_thumbnails_dir(self.task_id) / f"{n:04d}.jpg"
        if not thumb.exists():
            return None
        raw = [b for b in (boxes or []) if b] or ([box] if box else [])
        if not raw:
            return {"path": str(thumb), "effect": None}
        meta = self.store.image_size(self.task_id, p.stem)
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
        scaled = [
            [b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy] for b in raw
        ]
        return {
            "path": str(thumb),
            "effect": {
                "boxes": scaled,
                "area": parea,
                "border": border_mm,
                "dpi": 300 * sx,  # border 像素随缩略图比例缩放
                "full": bool(full),
            },
        }

    def _pdf_page_count_ready(self, count: int) -> None:
        self.pdf_page_count = count

    def _original_image_size(self, path_text: str) -> QSize | None:
        """页面图片的原始像素尺寸：优先 extract 阶段写入 sizes.json 的记录。"""
        if self.task_id:
            meta = self.store.image_size(self.task_id, Path(path_text).stem)
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
        if path.parent == self.store.extract_output_dir(self.task_id) \
                and path.stem.isdigit():
            reader = QImageReader(path_text)
            size = reader.size()
            if size.isValid():
                self.store.save_image_size(
                    self.task_id, path.stem, size.width(), size.height()
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

        第三步「去底色结果」要重新「提交本次任务」才会合成到 stages/rembg
        被第四步取用；第四步待打印图与拼版成品改了「生成 PDF」即生效。
        不属于这两类的路径（外部插入图等）不打日志。
        """
        try:
            if path.parent == self.store.rembg_preview_output_dir(self.task_id):
                self.log_view.append(
                    f"已编辑去底色结果「{path.name}」；"
                    "点「提交本次任务」后，第四步（生成 PDF）才会用上这次修改。"
                )
                # 按钮立刻改口（绿色「已是最新版本」在这里是假话）：编辑后必须
                # 重新提交才传给第四步，见 submit._preview_edited_after_submit
                self._update_submit_button(self.running_stage is not None)
            elif path.parent in (
                self.store.rembg_output_dir(self.task_id),
                self.store.imposition_output_dir(self.task_id),
            ):
                self.log_view.append(
                    f"已编辑待打印图片「{path.name}」；"
                    "点「生成 PDF」即用上这次修改。"
                )
        except Exception:  # noqa: BLE001 - 提示不该影响刷新主链路
            pass

    def _regen_page_thumb(self, path_text: str) -> None:
        """后台重生成某页的 source 缩略图（256px），完成后刷新各查看器。"""
        worker = ImageListWorker([Path(path_text)], edge=THUMBNAIL_EDGE)
        owner_task = self.task_id
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.thumbnail_ready,
                    lambda _i, image, _p, t=path_text, o=owner_task:
                        self._on_saved_thumb_ready(image, t, o),
                    thread,
                ),
                connect_queued(
                    self, w.failed,
                    lambda msg: self._toast(
                        "warning", "缩略图刷新失败", msg
                    ),
                    thread,
                ),
                w.completed.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_saved_thumb_ready(self, image, path_text: str,
                              owner_task: str) -> None:
        """新缩略图就绪：原子替换缓存文件，条目图标兜底刷新。

        大图已在 _on_page_image_saved 里用编辑结果即时上屏，这里只把
        图标从「编辑结果现缩的临时版」换成「与文件一致的缓存版」。
        """
        if owner_task != self.task_id or image.isNull():
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

    # ------------------------------------------------------------------ 增删
    def _active_page_viewer(self):
        """当前预览阶段对应的可编辑查看器（detect 或 extract）。

        ⚠️ 判据走 ``preview_stack.currentIndex()``（**栈页号**）经
        ``stage_at_stack_index`` 反查阶段，**不要**拿它跟 ``== 1`` 比：
        那是默认流程下detect 的页号，自定义流程里 detect 完全可能是 0
        （它是第一个节点时），写死1 会把 detect 的增删插接到 extract 上去。
        """
        stage = self.stage_at_stack_index(self.preview_stack.currentIndex())
        return self.detect_viewer if stage == "detect" else self.extract_result_viewer

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
        self.store.save_pages(self.task_id, self.pages)
        self.log_view.append(f"已删除页面：{removed.get('label')}")
        self._refresh_preview()
        if self.preview_stack.currentIndex() == 0:
            self._refresh_preview(1)

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
            self, "选择图片文件夹（把里面的图片批量插入）",
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

        spec = ports.spec_for_stage(self.current_stage())
        sources = (spec.collect_files(paths) if spec is not None
                   else [Path(p) for p in paths])
        sources = [p for p in sources if p.is_file()]
        if not sources:
            self._toast(
                "warning", "没有可用的图片",
                f"{title}：选中的位置里没有找到本步骤能处理的图片文件。",
            )
            return
        target_dir = self._current_stage_input_dir()
        if target_dir is None:
            self._toast(
                "error", "无法插入",
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
                connect_queued(
                    self, w.finished, self._on_pages_copied, thread
                ),
                connect_queued(
                    self, w.failed,
                    lambda msg: self._toast("error", "插入图片失败", msg), thread,
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
            self,
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
        self.store.save_pages(self.task_id, self.pages)
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
            self.pages.insert(
                insert_at, {"file": target, "label": target_path.stem}
            )
            insert_at += 1
        self.store.save_pages(self.task_id, self.pages)
        note = f"已插入 {len(done)} 张图片。"
        if errors:
            note += f"（{len(errors)} 张失败：{errors[0][1]}）"
            self._toast("warning", "部分图片插入失败", errors[0][1])
        self.log_view.append(note)
        self._refresh_preview()
        if self.preview_stack.currentIndex() == 0:
            self._refresh_preview(1)

    # ------------------------------------------------------------------ 杂项
    def _image_selected(self, index: int, path_text: str) -> None:
        pass  # 预览组件内部已渲染大图，此处留作扩展

    def _open_task_dir(self) -> None:
        if self.task_id:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.store.task_dir(self.task_id)))
            )

    # ------------------------------------------------------- 补选源 PDF
    def _missing_source(self) -> bool:
        """这个任务**现在缺源 PDF 吗**（该催用户补 PDF）。

        ⚠️ 两个条件都要满足，缺一不可：
        ①**流程里真的要 PDF**（`flow_needs_source_pdf`：用户可能自定义流程
        删掉了「提取图片」，那整条流程不碰源文件，催他上传毫无意义）；
        ②**这个任务确实没有**（`source_path is None`，即"还没选"而不是
        "文件丢了"——文件丢了是另一条错误提示，不该混进这条）。

        判据与创建页**共用** :func:`desktop.steps.ports.flow_needs_source_pdf`，
        ①那一半走 :meth:`_flow_needs_source_pdf`（同一个方法，别在两处各判）。
        ⚠️ "缺 PDF"与"缺入口图片"是**两件不同的事**（用户 2026-10-06）：
        自定义流程把「检测文本框」放第一步时压根不碰 PDF，这时该催的是
        "往输入目录放图"。合并判据见 :meth:`_missing_input_kind`。
        """
        if self.source_path is not None:
            return False
        return self._flow_needs_source_pdf()

    def _missing_entry_images(self) -> bool:
        """这个任务**现在缺入口图片吗**（该催用户上传图）。

        场景（用户 2026-10-06）：「非图片提取节点如果做第一个节点」——自定义
        流程第一步是「检测文本框」这类**不吃 PDF** 的步骤，它的 ``pages`` 输入
        沿图回溯不到上游，回落到入口图片目录 ``stages/input/``
        （见 :func:`desktop.steps.ports.resolve_input_with_entry`）。那个目录
        空着的话，第一步就无从下手——而界面一点提示都没有，用户只能对着空的
        预览区猜。

        判据 = **流程需要入口图片**（`flow_needs_entry_images`：入口阶段不吃
        源 PDF）**且入口目录里确实没有图**。⚠️ 两个都要：用户放过图之后就不该
        再被催。
        """
        if not self.task_id:
            return False
        from desktop.steps.ports import flow_needs_entry_images

        diagram = self.store.task_diagram(self.task_id)
        if not flow_needs_entry_images(diagram):
            return False
        return not self._entry_dir_has_images()

    def _entry_dir_has_images(self) -> bool:
        """入口图片目录（``stages/input/``）里有没有可用的图。"""
        try:
            directory = self.store.task_input_dir(self.task_id)
        except ValueError:
            return False
        # ⚠️ 用现成的 ``list_stage_images``（同一套后缀表+ 自然排序，
        #    入口目录和阶段输出目录"什么算一张图"必须一致）。
        return bool(list_stage_images(directory))

    def _missing_input_kind(self) -> str:
        """当前缺哪种输入：``"pdf"`` / ``"images"`` / ``""``（什么都不缺）。

        ⚠️ **PDF 优先**：两种都缺时先说 PDF，因为入口图片那一步往往要等
        提取出来才有意义（默认流程就是 extract 打头）。用户处理完 PDF 之后
        下一轮自然会看到"缺图片"的提示。

        ⚠️ 界面**所有**"缺输入"的表现都走这一个判据（按钮高亮 / 页头红字 /
        提示层文案）——散成两处各判各的，漂移起来就是"红字说缺图、弹窗说缺
        PDF"（用户 2026-10-06 报过文案重复/矛盾的类似问题）。
        """
        if self._missing_source():
            return "pdf"
        if self._missing_entry_images():
            return "images"
        return ""

    def _source_prompt_content(self) -> dict:
        """提示层文案：按缺的是 PDF 还是入口图片给**两套**说法。

        ⚠️ 不能一套文案通吃："这个任务还没有 PDF"对"流程第一步是检测"的
        用户是**错的引导**——他该去放图，不是去找 PDF。文案与按钮文案都跟着
        判据走（用户 2026-10-06：「应该提醒上传输入目录或者图片」）。
        """
        from desktop.steps.ports import flow_entry_stage, stage_label

        if self._missing_input_kind() != "images":
            return {}
        try:
            entry = stage_label(flow_entry_stage(
                self.store.task_diagram(self.task_id)))
        except (OSError, ValueError):
            entry = "第一步"
        return {
            "title": "这个流程的第一步需要图片",
            "body": (
                f"当前流程的第一步是「{entry}」，它不吃 PDF，"
                "需要你提供图片作为输入。\n\n"
                "· 选择图片目录 → 选一个文件夹，里面的图片会整批放进"
                "本任务的输入目录；\n"
                "· 稍后再说 → 也可以直接点页头右上角那两个红框按钮"
                "（插图片 / 选文件夹），或把图片拷进任务目录下的 stages/input。"
            ),
            "hint": "内容区暂时不可操作，页头与右上角按钮照常可用。",
            "later_text": "稍后再说",
            # ⚠️ 按钮**直接选目录**（用户 2026-10-06："改成选择图片目录"）：
            #    一个任务一两百页图，逐张多选不现实，而"把整本扫描结果的文件夹
            #    丢进来"才是最自然的用法。⚠️ 文件对话框（``getOpenFileNames``）
            #    **选不了目录**，所以必须是 ``getExistingDirectory`` 那条路。
            "pick_text": "选择图片目录",
            # ⚠️ 告诉宿主点了要开**目录**框（而不是文件框）——组件自己不决定
            #    打开哪种对话框，只把意图传出去。
            "pick_kind": "folder",
        }

    def _refresh_source_actions(self) -> None:
        """按"缺不缺源 PDF"调页头的**按钮显隐 + 高亮 + 红字 + 提示语**。

        ⚠️ **PDF 按钮在"流程不吃 PDF"时整颗藏起来**（用户 2026-10-06：
        "不需要上传 pdf 的流程右侧不需 pdf 上传图标"）——那种流程里没有
        「提取图片」，源文件毫无用处，摆个按钮在那儿纯粹是噪声，还会让人
        以为这步要 PDF。
        ⚠️ 判据是 :func:`ports.flow_needs_source_pdf`（**问图**），不是"这个
        任务有没有 PDF"：判据搞反的话，**空壳任务**（还没选 PDF、但流程要
        PDF）会把补救入口一起藏掉，用户就再也没法自己补了——那正是它恒可见
        的原因。所以这里只在"流程压根不碰 PDF"时藏，其余情况恒可见。
        """
        button = getattr(self, "source_button", None)
        insert = getattr(self, "insert_button", None)
        # ⚠️ **所有"缺输入"的表现都读这一个判据**（``_missing_input_kind``）。
        #    缺的不只是 PDF：自定义流程第一步是「检测文本框」时该催的是
        #    "上传图片"（用户 2026-10-06），那时高亮的必须是**图片按钮**。
        kind = self._missing_input_kind()
        # ---- PDF 按钮：流程不吃 PDF 时整颗藏起来 ----
        needs_pdf = self._flow_needs_source_pdf()
        if button is not None:
            button.setVisible(needs_pdf)
        _set_tool_highlight(button, needs_pdf and kind == "pdf")
        # ⚠️⚠️ 插图按钮**同时**带"常驻红框"（入口标识）与"缺图片时高亮"
        #    （动态提醒），而 ``_set_tool_highlight(button, False)`` 会
        #    ``setStyleSheet("")`` ——**把常驻红框一起抹掉**（用户 2026-10-06
        #    要求"都是红色框住"，那红框不能只在缺图时才出现）。
        #    所以：先按动态判据走一遍，**再无条件重贴常驻红框**。
        #    ⚠️ 别"优化"成两者只用一个——那会退回"入口看不出该点哪儿"。
        _set_tool_highlight(insert, kind == "images")
        if insert is not None:
            mark_input_entry(insert)
        # ---- 按钮提示语：跟着"缺什么"变（不变会指错方向）----
        if button is not None:
            button.setToolTip(
                "这个任务还没有 PDF，点此选择源文件" if kind == "pdf"
                else "更换这个任务的 PDF 源文件")
        if insert is not None:
            insert.setToolTip(
                "本流程第一步需要图片，点此选择图片（放进输入目录）"
                if kind == "images"
                else "为本任务插入图片（放到入口图片目录）")
        # ---- 页头红字：缺文件时一直显示，直到补上（toast 会自己消失）----
        warning = getattr(self, "source_warning", None)
        if warning is not None:
            warning.setText(_MISSING_INPUT_TEXT.get(kind, ""))
            warning.setVisible(bool(kind))
        # ⚠️ 不缺了就收提示层（补上文件的路径不都经过 _apply_source，
        #    比如 store 侧直接改的）
        if not kind:
            self._dismiss_source_prompt()

    def _flow_needs_source_pdf(self) -> bool:
        """**本任务的流程**要不要源 PDF（问图；没任务时按"要"处理）。

        ⚠️ 与 :meth:`_missing_source` 里的同名判据是**同一份**
        （``ports.flow_needs_source_pdf``），别在两处各判一次。
        没有任务时给 ``True``：构造期 ``source_button`` 还没确定该不该显，
        按"要"走等于保持原样，等 :meth:`set_task` 调
        :meth:`_refresh_source_actions` 时再按真实流程定。
        """
        if not getattr(self, "task_id", None):
            return True
        from desktop.steps.ports import flow_needs_source_pdf

        return flow_needs_source_pdf(self.store.task_diagram(self.task_id))

    def _prompt_missing_source(self) -> None:
        """进任务详情时**提示**该上传 PDF（用户 2026-10-06）。

        用 :class:`MissingSourcePrompt`（页内**非模态**提示层）而不是
        ``MessageBox``，三个原因都是被用户截图逼出来的（见该组件的模块头）：
        库里遮罩的尺寸只在**构造那一刻**取一次（于是只盖住页面左上角一小块）、
        它铺满 parent 所以**留不下页头**、它是模态的所以**按钮点了没反应**。

        ⚠️ **每次进入都弹**（用户 2026-10-06："没有选择源文件，为何弹窗也没有了，
        每次进入都要检测"）。⚠️ 别学我上一轮加的"提示层已存在就不再弹"——
        那看着像省事，实际是**第二次进同一个任务时提示再也不出现**，而用户
        恰恰是忘了才要重新进来提醒他一下的。
        已建过的提示层**复用**（重建会丢信号连接与拖动位置），只是重新显示 +
        重铺几何。
        """
        if not self._missing_input_kind():
            self._dismiss_source_prompt()
            return
        prompt = getattr(self, "_source_prompt", None)
        if prompt is None:
            from desktop.components.missing_source_prompt import (
                MissingSourcePrompt,
            )

            prompt = MissingSourcePrompt(self, self._content_top)
            # ⚠️ 「现在选择」按缺的东西分派：缺 PDF 去选文件、缺图去选图片。
            #    ⚠️**连的是信号**（``connect`` 那一刻就绑定了当时的槽），
            #    所以宿主这边换实现不会影响它——别用"替换页面方法"的方式
            #    去做这件事（自测踩过：替换属性对已连信号完全无效）。
            prompt.picked.connect(self._on_prompt_pick_input)
            prompt.dismissed.connect(self._on_source_prompt_dismissed)
            self._source_prompt = prompt
        # ⚠️ 每次显示前**刷文案**：同一个提示层对象会被复用（重建会丢信号
        #    连接与拖动位置），而缺的东西可能变了——上一次说"缺 PDF"、
        #    这一次说"缺图片"，文案不刷就会对着错的目标催人。
        prompt.configure(**self._source_prompt_content())
        prompt.show_prompt()

    def _on_prompt_pick_input(self, kind: str = "") -> None:
        """提示层那个主按钮：按缺的是什么 **+ 按钮要哪种对话框** 去动作。

        :param kind: ``"folder"``＝要**目录**（缺入口图片时的默认，用户
            2026-10-06："改成选择图片目录"）；空/``"files"``＝要文件。

        ⚠️ 目录框与文件框是**两个不同的 QFileDialog 调用**
        （``getExistingDirectory`` vs ``getOpenFileNames``），后者**选不了
        目录**，所以这个分流不能省。
        """
        if self._missing_input_kind() == "images":
            if kind == "folder":
                self.insert_pages_from_folder()
            else:
                self.insert_pages()
        else:
            self._on_pick_source()

    def _dismiss_source_prompt(self) -> None:
        """收掉提示层（如果有）。切任务/ 返回/ 补上文件后都要调。"""
        prompt = getattr(self, "_source_prompt", None)
        if prompt is not None:
            prompt.hide()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """窗口尺寸变了：让「缺源 PDF」提示层**跟着重铺**。

        ⚠️ 这正是 qfluentwidgets ``MaskDialogBase`` 踩的坑（用户2026-10-06
        截图：遮罩只盖住页面左上角一小块）：它只在**构造那一刻**读一次
        ``parent.width()``，之后不跟随。我们的提示层每次显示都重铺，但**显示
        期间**窗口还会变（用户拖窗口、最大化），所以这里再补一次。

        ⚠️⚠️ **别用 ``prompt.isVisible()`` 当条件**（用户 2026-10-06 报"第一次
        进入没有弹窗、第二次才有"）：``set_task`` 是**先于**
        ``setCurrentWidget`` 跑的（见 :meth:`ModuleShell.open_detail`），那一刻
        页面还没被显示，``show()`` 过的子控件 ``isVisible()`` 仍为 **False**
        （Qt 的 isVisible 看整条祖先链）。于是"首次进入"这一路恰好被这个条件
        拦掉，留在 ``640x480`` 时代算出的**零高度**遮罩上（实测
        ``mask=(0, 491, 640, 0)``）——用户看到的就是"压根没弹"。
        重铺一个隐藏的层是无害的，所以这里只判"有没有建过"。
        """
        super().resizeEvent(event)
        prompt = getattr(self, "_source_prompt", None)
        if prompt is not None:
            prompt._reanchor()
            prompt.card_host_center()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """页面真正显示出来：把「缺源 PDF」提示层铺到**最终**尺寸上。

        ⚠️⚠️ 这是"第一次进入不弹"的**正主修复**（用户 2026-10-06报障）。
        第一次进入时序是 ``set_task`` → ``setCurrentWidget``，而 ``set_task``
        里就调了 ``show_prompt()``：那一刻详情页刚被 ``addWidget`` 进栈、**还没
        布局**，尺寸是 QWidget 默认的 ``640x480``、``_content_top()`` 返回布局
        未跑时的垃圾值（实测 491）。遮罩于是是 ``(0, 491, 640, 0)``——**高度
        0**，看上去就是"没弹"。

        ``showEvent`` 是布局与尺寸都已就绪的第一个时刻（QStackedWidget 切页会先
        resize 子控件再 show），在这里重铺一次就对了。⚠️ 别改成"在
        ``set_current`` 里同步重铺"：那时候尺寸同样还是旧的。

        这里也**顺带兜住"每次进入都弹"**：用户答过「稍后再说」再切回来时，
        ``set_task`` 跑在页面还看不见的时候，``show_prompt()`` 铺的是旧几何；
        真正显示出来时这一句会重新 ``show_prompt()``（内部先重铺再 show），
        用户看到的才是铺好的那一版。
        """
        super().showEvent(event)
        # ⚠️⚠️ **必须先判 ``task_id``**：详情页是 ``addWidget`` 进栈的，那一下就会
        # 触发 ``showEvent``——**早于第一次 ``set_task``**，此时 ``task_id`` 还是
        # ``None``。而 ``_missing_source()`` 会拿它去查流程图，
        # ``store.task_dir(None)`` 直接抛 ``ValueError``（自测实测：整个自测进程
        # 都被这一个未捕获异常打断）。这不是"理论上不会发生"——它每次建页都发生。
        if not self.task_id:
            return
        if not self._missing_input_kind():
            return
        prompt = getattr(self, "_source_prompt", None)
        if prompt is None:
            # ⚠️ 正常不会走到（``set_task`` 里已建）；真走到说明那条路径被改
            #    过，这里补建一次，别让用户看不到任何提示。
            self._prompt_missing_source()
            prompt = getattr(self, "_source_prompt", None)
        if prompt is not None:
            prompt.show_prompt()

    def _on_source_prompt_dismissed(self) -> None:
        """用户答「稍后再说」/点了遮罩：只收提示，其余一概不动。

        ⚠️ **不碰**高亮与红字——它们要一直留着，直到真的补上文件（那是用户
        反复需要看到的路标，不是"看一眼就消失的提示"）。
        """

    def _content_top(self) -> int:
        """要遮盖区域的**上沿 y**（页内坐标）＝**页头下沿 + 间距**。

        给 :class:`MissingSourcePrompt` 当 geometry 用。

        ⚠️⚠️ **只能用页头算，不能用步骤条**（这一点踩了两层坑）：

        1. ``_rebuild_step_bar`` 是 ``removeWidget`` + ``insertWidget`` 换的
           控件，Qt 的布局是**延迟**生效的，``set_task`` 末尾那一刻新步骤条
           **还没被定位**——``geometry()`` 仍是 QWidget 默认的 640×480、
           ``isHidden()`` 为 True，``mapTo`` 得到的 y 是 **0**。用它算，遮罩
           会从页头顶上盖下来，"按钮留在遮罩之上"当场作废（库里那个遮罩 bug
           也是同一个根因）。
        2. 连 ``layout.activate()`` 都不管用：那对 ``removeWidget`` +
           ``insertWidget`` 之后的结构不重排（实测 itemAt(row) 仍是 640×480）。

        **页头卡片是稳定的**——它构造后再没被换过，``itemAt(0)`` 的 geometry
        一直是准的（实测 bottom=74 + 间距 12 = 86，正好是步骤条该在的 y）。
        """
        layout = getattr(self, "_root_layout", None)
        if layout is not None:
            item = layout.itemAt(0)
            if item is not None and item.geometry().height() > 0:
                return max(0, item.geometry().bottom() + layout.spacing())
        # 兜底：页头控件自己的位置（万一根布局还没跑）
        header = getattr(self, "header_card", None)
        if header is not None:
            from PySide6.QtCore import QPoint

            return max(0, header.mapTo(self, QPoint(0, 0)).y()
                       + header.height())
        return 0

    def _on_pick_source(self) -> None:
        """页头「选择 PDF」：给任务补上 / 更换源文件（用户 2026-10-06）。

        为什么需要它：创建任务时 PDF **非必需**（用户明确要求），所以会有
        "空壳任务"；另外源文件被移走/删除时也走这里自救。

        ⚠️ **先算指纹再决定**（用户 2026-10-06 第 3 条的判据）：几百 MB 的
        PDF 算一次 SHA-256 要一两秒，所以指纹走**后台**（``HashWorker``），
        算完才进 ``_on_source_hash_ready`` 走三条分支：

        - **这个 PDF 已经在这个任务里** ⇒ 什么都不做（重复选同一个文件，
          换过去等于什么都没变，还要白清一遍产物）；
        - **这个 PDF 已在别的任务里** ⇒ **问一句**"是否仍然使用"，用户答
          "仍然使用"才换（与列表页的查重确认同一个模式，见
          :meth:`_confirm_duplicate_source`）；
        - **是新的 PDF** ⇒ 换源之前先问一句（清空后果），确认后才换。

        ⚠️ 换文件等于换了整本书的内容，**已有的中间产物全部作废**（提取出来
        的图、检测框、去底色结果……都对应着旧文件）。不清理的话，界面上会
        同时摆着"旧书的页"与"新书的结果"。
        """
        if not self.task_id:
            return
        # ⚠️ 用**原生** QFileDialog（项目硬规则：「资源管理器」= 原生选择
        #    对话框，不是浏览窗口）。
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 源文件", str(default_open_dir()), "PDF (*.pdf)"
        )
        if not filename:
            return
        source = Path(filename)
        if not source.is_file():
            self._toast(
                "warning", "选择失败",
                f"「{source.name}」已经不在那个位置了，请重新选择。",
            )
            return
        self._set_picking_source(True)
        self._pending_source = source
        # ⚠️ 指纹计算**必须进后台**：一本 800MB 的书 SHA-256 要一两秒，
        #    放主线程就是界面白住一两秒（导入链路早就为此建了 HashWorker）。
        self.run_worker(
            lambda: HashWorker(source),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished, self._on_source_hash_ready, thread,
                ),
                connect_queued(
                    self, worker.failed, self._on_source_hash_failed, thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_source_hash_failed(self, message: str) -> None:
        """指纹算不出来（文件被占用/权限不足/已被删除）。"""
        self._set_picking_source(False)
        self._toast("warning", "无法读取", f"{message}（未更换源文件）")

    def _on_source_hash_ready(self, path_text: str, source_hash: str) -> None:
        """指纹算完 → 三条分支的判据（见 :meth:`_on_pick_source`）。"""
        self._set_picking_source(False)
        source = self._pending_source or Path(path_text)
        self._pending_source = None
        if not self.task_id:
            return          # 算指纹这几秒里用户可能已经切走任务了

        current = (self.store.get_task(self.task_id) or {}).get("source_hash")
        if current and str(current) == source_hash:
            # 同一个文件又选了一遍：换过去等于什么都没变，还要清一遍产物
            self._toast(
                "info", "已经是当前文件",
                f"「{source.name}」就是这个任务正在用的源文件，无需更换。",
            )
            return
        duplicates = self.store.find_tasks(source_hash)
        if duplicates:
            # ⚠️ **问一句再决定，不是一律拒绝**（用户 2026-10-06："当前是不
            #    允许的，这个不合理。应该提示已经存在相同文件任务，是否继续
            #    等，跟外层一样"）。与列表页的查重确认同一个模式：把重复的
            #    事实与后果说清，用户答"仍然使用"就换。
            other = duplicates[0]
            if not self._confirm_duplicate_source(source, other):
                return
            #⚠️ **不再问第二次**：清空后果已经写在这一个弹窗里了，连弹两次
            #    只是折磨用户。
            self._apply_source(source, source_hash, duplicate_of=other)
            return

        # 真的是新 PDF：换源前问一句（清空后果）
        if self.source_path is not None and not self._confirm_replace_source(source):
            return
        self._apply_source(source, source_hash)

    def _confirm_duplicate_source(self, source: Path, other: dict) -> bool:
        """这个 PDF 已在别的任务里 ⇒ 问"是否仍然使用"（``False`` = 取消）。

        ⚠️ 判据（有没有产物、要不要提清空）与弹窗**分开**——离屏自测绝不
        真弹模态（项目硬规则），自测把这个方法替掉就能验两条分支。

        文案**一次把两件事说清**（重复 + 清空后果），别让用户连点两个弹窗。
        """
        if not self._duplicate_source_needs_confirm(other):
            return True
        warning = ""
        if self._has_task_artifacts():
            # ⚠️ MessageBox 是**纯文本**、不解析 markdown：写 ** 粗体会让
            #    用户看到一串星号。要强调就靠措辞。
            warning = (
                "\n\n继续使用会把它换成本任务的源文件，已有的提取图片、"
                "检测框、去底色结果会被清空，四个步骤需要重新跑一遍。"
            )
        dialog = MessageBox(
            "已存在相同的文件",
            f"「{source.name}」的内容与任务「{other.get('name')}」"
            f"（{other.get('id')}）完全相同。\n\n"
            f"是否仍然用它作为本任务的源文件？{warning}",
            self,
        )
        dialog.yesButton.setText("仍然使用")
        dialog.cancelButton.setText("取消")
        return bool(dialog.exec())

    def _duplicate_source_needs_confirm(self, other: dict) -> bool:
        """该问吗（True = 需要问）。

        存在**别的**任务 ⇒ 一律问一句：重复内容是用户该知道的事实（他可能
        是想换个任务继续处理这本），替他决定不合适。本任务自己那条（选了
        一模一样的文件）不走这里，已经在 :meth:`_on_source_hash_ready` 里
        提前处理掉了。
        """
        return str(other.get("id") or "") != str(self.task_id or "")

    def _set_picking_source(self, picking: bool) -> None:
        """算指纹期间锁住按钮并换个提示（免得用户以为没点上）。"""
        self._picking_source = bool(picking)
        button = getattr(self, "source_button", None)
        if button is None:
            return
        button.setEnabled(not picking)
        if picking:
            button.setToolTip("正在读取文件…")
        else:
            self._refresh_source_actions()

    def _apply_source(self, source: Path, source_hash: str,
                      duplicate_of: dict | None = None) -> None:
        """确认过了 → 复制进任务目录、改索引、清旧产物、重载页面。

        ``duplicate_of`` 非空 = 用户明知"这个 PDF 已在任务X 里"仍选择使用
        （与列表页建任务时的 ``duplicate_confirmed`` 同一个意图）。这时提示
        里要点出"另一个任务也在处理同一本"，否则用户回头在两个任务的页面上
        看到同一批页，会以为哪里出了错。
        """
        replacing = self.source_path is not None
        # 复制进任务目录 + 改索引（store.set_task_source 内部做拷贝；失败
        # 返回 False 时不碰界面——索引指向一个不存在的文件比什么都不做更糟）
        try:
            ok = self.store.set_task_source(self.task_id, source,
                                            source_hash=source_hash)
        except OSError as exc:
            self._toast("error", "选择失败", f"{type(exc).__name__}: {exc}")
            return
        if not ok:
            self._toast(
                "warning", "选择失败",
                f"没能把「{source.name}」收进这个任务（文件可能已被移走）。",
            )
            return
        if replacing:
            self._reset_artifacts_for_new_source()
        # ⚠️ 补上文件了 ⇒ 提示层立刻收掉（它存在的理由已经消失）
        self._dismiss_source_prompt()
        if duplicate_of:
            self._toast(
                "info", "已使用相同文件",
                f"源文件：{source.name}（任务「{duplicate_of.get('name')}」"
                "用的也是同一本）。",
            )
        else:
            self._toast("info", "已选择", f"源文件：{source.name}")
        # 重载任务：走一遍 set_task 的全套（源路径、页头、清单、预览、步骤记忆）
        self.set_task(self.task_id)

    def _confirm_replace_source(self, source: Path) -> bool:
        """换源文件前的确认（``False`` = 取消）。

        ⚠️ 判据（"有没有中间产物"）在 :meth:`_source_replace_is_blocked`
        里，与弹窗分开——**离屏自测绝不真弹模态**（项目硬规则），自测把
        那个方法替掉就能验两条分支。
        """
        if not self._source_replace_is_blocked(source):
            return True
        dialog = MessageBox(
            "更换 PDF 源文件",
            f"确定把本任务的源文件换成「{source.name}」吗？\n\n"
            "已有的提取图片、检测框、去底色结果都对应着旧文件，"
            "换完会被清空，需要重新跑一遍。",
            self,
        )
        dialog.yesButton.setText("更换并清空")
        dialog.cancelButton.setText("取消")
        return bool(dialog.exec())

    def _source_replace_is_blocked(self, source: Path) -> bool:
        """该不该拦住这次替换：True = 需要用户确认，False = 直接换。

        有任何中间产物就要问一句（用户可能白跑了几十分钟）；什么都没有就
        静默换掉（此时换文件没有任何损失，问了只是多一次点击）。
        """
        return self._has_task_artifacts()

    def _has_task_artifacts(self) -> bool:
        """这个任务目录里有没有任何中间产物（页清单/执行记录/阶段输出）。"""
        try:
            for name in ("pages.json", "runs.json", "boxes.json", "sizes.json"):
                if (self.store.task_dir(self.task_id) / name).exists():
                    return True
            stages = self.store.task_dir(self.task_id) / "stages"
            if stages.is_dir() and any(stages.iterdir()):
                return True
        except OSError:
            return False
        return False

    def _reset_artifacts_for_new_source(self) -> None:
        """换源文件后清掉旧书的中间产物（让下游必须重跑）。

        ⚠️ 只删**产物与清单**，不碰源文件副本（那个已经被新文件替换了）与
        流程图 ``flow.bpmn``（流程是用户配的，与源文件无关）。
        ⚠️ 逐个 ``unlink`` 且**吞掉异常**：某个文件被占用/无权限时不该让
        整个换源流程失败——剩下的残留只会在"上游重跑"时按 mtime 判过期，
        不会算错结果。
        """
        import shutil

        task_dir = self.store.task_dir(self.task_id)
        for name in ("pages.json", "runs.json", "boxes.json", "sizes.json",
                     "print.json"):
            try:
                (task_dir / name).unlink(missing_ok=True)
            except OSError:
                pass
        for sub in ("stages", "thumbnails/detect", "thumbnails/print",
                     "thumbnails/imposition", "drafts"):
            try:
                shutil.rmtree(task_dir / sub, ignore_errors=True)
            except OSError:
                pass
        # 页缓存按**页号**命名，跨书共用会串页（见 MEMORY「按页号命名的缓存
        # 不能跨书共用」）——源一换，整本源缩略图缓存作废。
        try:
            shutil.rmtree(task_dir / "thumbnails/source",
                          ignore_errors=True)
        except OSError:
            pass
        # ⚠️⚠️ **必须把"待写"标记也清掉**：``set_task`` 开头会
        #    ``_flush_param_drafts()`` / ``_flush_annotations()``（切任务前把
        #    用户最后 400ms 的输入、攒批的框与尺寸落盘）。那些暂存是**旧书**
        #    的，目录刚被删掉，这一 flush 又把它们写回来——等于"换完文件，
        #    旧书的参数与检测框复活了"。只删文件不清标记是半个修复。
        self._draft_dirty = set()
        self._pending_sizes = {}
        self._pending_boxes = {}
        # 预览器的内存态也要清，否则还指着旧书的第一页
        self.pages = []
        self.pdf_page_count = 0
        self.detect_cache.clear()


#: 页头红字：缺哪种输入就说哪件事（键与 ``_missing_input_kind`` 的返回值对应）。
#: ⚠️ **两套文案不能混用**（用户 2026-10-06）：对"流程第一步是检测"的用户说
#: "请上传 PDF"是错的引导——他该去放图。
_MISSING_INPUT_TEXT = {
    "pdf": "尚未选择 PDF：本流程需要 PDF 源文件，请点右侧「选择 PDF」"
           "上传后才能执行各步骤。",
    "images": "本流程第一步需要图片：请点右侧的图片按钮上传，"
              "或把图片/图片文件夹放进任务目录下的 stages/input。",
}


def _set_tool_highlight(button, on: bool) -> None:
    """给页头某个工具按钮加/去「该点这里」的**红框高亮**。

    ⚠️ 用样式表而不是换成 ``PrimaryPushButton``：那会让这一排工具按钮
    **尺寸**变掉（文字按钮比图标按钮宽），把页头撑变形。qfluentwidgets 的
    按钮本来就是整串 setStyleShell 进去的（见 ``desktop/ui/widgets.py``
    里的 ``bold_button`` 说明），追加边框/底色是安全的。
    ⚠️ 去掉时必须设成**空串**：留着上一次的红框会让"已经不缺了"看起来
    还缺。
    """
    if button is None:
        return
    if on:
        button.setStyleSheet(
            f"ToolButton {{ border: 1.5px solid {T.DANGER};"
            f" border-radius: 6px; background-color: {T.DANGER_SOFT}; }}"
            f"ToolButton:hover {{ background-color: {T.DANGER_SOFT}; }}"
        )
    else:
        button.setStyleSheet("")
