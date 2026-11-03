# -*- coding: utf-8 -*-
"""任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtWidgets import QDialog, QFileDialog, QWidget

from desktop.services.print_plan import (
    drop_foreign_stage_pages,
    ordered_page_record,
    plan_print_entries,
    stale_rect_pages,
)
from desktop.utils.files import THUMBNAIL_EDGE, book_key, list_stage_images
from utils.sort_utils import natural_sort_key

if TYPE_CHECKING:
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.store.store import TaskStore


def _parent(page) -> "QWidget":
    """Mixin 里的 ``self`` 当文件对话框的 parent 用——宿主是 QWidget。

    ⚠️ 类型检查器看 Mixin 只看到「一个普通类」，故这里 cast 一下；运行时
    什么也没做（cast 是恒等函数）。
    """
    return cast(QWidget, page)


class PrintListMixin:
    """依赖宿主页面提供的属性：store/task_id、print_preview、log_view、
    _toast()。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法：Mixin 本体不持有，
        # 这里只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        print_preview: PrintPreviewWidget
        log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
        _toast: Callable[..., None]
        run_worker: Callable[..., Any]
        print_source_dir: Callable[[], Any]
        imposition_effective: Callable[[], bool]
        node_of_stage: Callable[[str], str | None]
        current_stage: Callable[[], str]
        _node_scope: Callable[..., dict]
        #: 上游输入是否**已经生效**（目录有东西 + 产出动作执行成功），
        #: 由 ManifestMixin 提供（见 manifest.py）。
        _stage_input_visible: Callable[[], bool]
        # 本 Mixin 内部在多个方法间传递的快照（_print_entries 写、落盘读）
        _print_doc_snapshot: dict[str, Any]

    def _print_thumb_provider(self, file_text: str):
        """第四步缩略条的小图来源：一律给**已生成的小图**，不现解码原图。

        查找顺序：
        1. 入口图片（``thumbnails/input/``，导入即生成）；
        2. 去底色成品（``thumbnails/print[~<节点>]/<图名>.jpg``，第三步执行时生成）；
        3. **PDF排版统一缓存**（``thumbnails/print_manage/``，本步进入时后台生成）
           ——拼版成品、手动「插入图片」的外部图都靠它，管理弹窗才不用同步
           解码 85 张原图（用户 2026-11-02「弹窗打开慢」）。
        都没有时返回 ``None``（调用方决定要不要回落原图；管理弹窗不再回落）。

        ⚠️ **缩略图目录按节点取**（B 方案）：两个「图片去底色」节点各有各的成品
        产物目录，缩略图缓存也跟着分（``thumbnails/print[~<节点>]``）。这里从
        **产物自己的目录名**反推节点后缀（与写入端 ``rembg_stage.py`` 同一份
        规则，见 :func:`desktop.steps.ports.node_scope_from_output_dir`）——比按
        界面当前节点取更准：第四步消费的是**上游那个**节点交的图，未必是当前选中
        的节点。
        """
        if not self.task_id:
            return None
        try:
            page = Path(file_text)
            # 入口图片的预生成小图优先（按图键缓存，命中即用）
            entry = self.store.entry_thumb_path(self.task_id, page)
            if entry is not None:
                return entry
        except (OSError, ValueError):
            return None
        from desktop.steps.ports import node_scope_from_output_dir

        parent = page.parent
        # 去底色成品目录恒为 ``stages/rembg`` 或 ``stages/rembg~<节点>``。
        if parent.parent == self.store.task_dir(self.task_id) / "stages" and (
            parent.name == "rembg" or parent.name.startswith("rembg~")
        ):
            thumb_dir = (
                self.store.task_dir(self.task_id)
                / "thumbnails"
                / f"print{node_scope_from_output_dir(parent.name)}"
            )
            thumb = thumb_dir / f"{page.stem}.jpg"
            try:
                if (
                    thumb.is_file()
                    and thumb.stat().st_mtime >= page.stat().st_mtime
                    and thumb.stat().st_size >= 512
                ):
                    return thumb
            except OSError:
                return None
        # PDF排版统一缓存（拼版成品 / 手动插入图 / 其它来源）
        try:
            from desktop.workers.thumb_cache_worker import (
                cache_usable,
                stat_mtime,
            )

            manage = (
                self.store.print_manage_thumbnails_dir(self.task_id)
                / f"{book_key(page)}.jpg"
            )
            if cache_usable(manage, stat_mtime(page)):
                return manage
        except (OSError, ValueError):
            return None
        return None

    def _warm_print_thumbs(self, files) -> None:
        """PDF排版缩略图**后台预生成**到 ``thumbnails/print_manage/``。

        用户 2026-11-02：「管理图片」弹窗打开慢——它构造时逐条同步解码原图。
        这里在**进入本步 / 列表刷新**时就把待打印条目（连同已删除条目，供
        「删除恢复」页签用）的小图生成好，弹窗只读小图。

        ⚠️ 与 ``_warm_entry_thumbs`` 同样按 ``(路径, mtime)`` 记账：读不出来的
        坏图永远写不出缓存，不记账会在每次刷新时反复派发同一批。
        """
        if not self.task_id:
            return
        cache_dir = self.store.print_manage_thumbnails_dir(self.task_id)
        candidates: list[Path] = []
        for item in files or ():
            text = str(item or "")
            if text:
                candidates.append(Path(text))
        if not candidates:
            return
        from desktop.workers import connect_queued
        from desktop.workers.thumb_cache_worker import (
            ImageThumbCacheWorker,
            stat_mtime,
        )

        warmed = self.__dict__.setdefault("_print_thumb_warmed", {})
        todo: list[Path | str] = []
        for path in candidates:
            # 已有可用小图（入口图 / 去底色成品 / 本缓存）就不用再渲一份：
            # 85 页去底色成品若都往 print_manage 复制一遍，等于白解码 85 次。
            if self._print_thumb_provider(str(path)) is not None:
                continue
            mtime = stat_mtime(path)
            key = str(path)
            if warmed.get(key) == mtime:
                continue  # 已请求过且源没变（多为读不出来的坏图）
            todo.append(path)
            warmed[key] = mtime
        if not todo:
            return
        worker = ImageThumbCacheWorker(todo, cache_dir, edge=THUMBNAIL_EDGE)
        owner_task = self.task_id
        # ⚠️ ``thumbnail_ready`` 第三参数是**缓存文件路径**（见 worker 的信号
        #    注释），而弹窗按**源图路径**认条目；这里用 index → 源图 的回溯，
        #    别把缓存路径直接当 file 传进去（那样一格都匹配不上）。
        sources = list(todo)
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.thumbnail_ready,
                    lambda index, _image, _cache, o=owner_task, p=sources:
                    self._on_print_thumb_ready(
                        o, str(p[index]) if 0 <= index < len(p) else "",
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    w.completed,
                    lambda o=owner_task: self._on_print_thumbs_warmed(o),
                    thread,
                ),
                w.completed.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_print_thumb_ready(self, owner_task: str, path: str) -> None:
        """一张缩略图生成好：管理弹窗正开着就就地换掉那一格。"""
        if owner_task != self.task_id:
            return
        panel = getattr(self, "_manage_panel", None)
        if panel is not None and panel.isVisible():
            panel.refresh_thumb(str(path))

    def _on_print_thumbs_warmed(self, owner_task: str) -> None:
        """整批缩略图生成完：管理弹窗还开着就整体刷一遍（此时都命中缓存）。"""
        if owner_task != self.task_id:
            return
        panel = getattr(self, "_manage_panel", None)
        if panel is not None and panel.isVisible():
            panel.refresh_thumbs()

    def _print_image_size(self, path_text: str) -> tuple[int, int] | None:
        """某张待打印图片的**当前**像素尺寸（只读文件头，不解码整图）。

        给 ``plan_print_entries`` 当 ``size_for``：逐页 rect 是**用户按当时那张图**
        摆出来的坐标，图像一换（拼版成品重合成、去底色重提交、编辑器回写）旧框
        就不该再套（用户 2026-10-18：「上一步的输出归上一步，当前步 PDF排版，页面
        效果都要按相关参数来调整」）。
        """
        from PySide6.QtGui import QImageReader

        try:
            size = QImageReader(path_text).size()
        except Exception:  # noqa: BLE001 - 坏图/占用：当作读不到（旧框保留）
            return None
        if not size.isValid() or size.width() <= 0 or size.height() <= 0:
            return None
        return (size.width(), size.height())

    def _report_updated_print_images(self, stale: list[dict]) -> None:
        """把"哪几张图被上游更新了、旧版面已按本步参数重排"记进日志（去重）。

        ⚠️ ``_print_entries`` 在切步骤/后台合成收尾/开关变化时都会被调到，
        无条件打日志会刷屏——同一批（路径 + 当前尺寸）只报一次。
        """
        if not stale:
            return
        signature = tuple(
            (str(page["file"]), tuple(page["image"])) for page in stale
        )
        if getattr(self, "_logged_stale_rects", None) == signature:
            return
        self._logged_stale_rects = signature
        names = "、".join(Path(page["file"]).name for page in stale[:6])
        if len(stale) > 6:
            names += f" 等 {len(stale)} 张"
        self.log_view.append(
            f"图片已更新（{names}）：原版面是按旧图尺寸摆的，"
            "已改按当前 PDF排版参数重新排版。"
        )

    def _drop_updated_print_thumbs(self, stale: list[dict]) -> None:
        """更新过的图片：把它在**待打印缩略图缓存**里的那条删掉，下次现解新图。

        ``thumbnails/print[~<节点>]/<图名>.jpg`` 是第三步「执行去底色」时预生成的
        小图；它自带 ``mtime 不旧于源图`` 的有效性判据（改过的图本来就会回落真图），
        这里再**主动删掉**是因为用户要求"更新过的图片不要留旧缓存"（2026-10-18）：
        留着那份文件，翻目录/排查时看到的仍是旧像素。
        """
        if not self.task_id:
            return
        stems = {
            Path(page["file"]).stem for page in stale if page.get("file")
        }
        if not stems:
            return
        thumbs_root = self.store.task_dir(self.task_id) / "thumbnails"
        if not thumbs_root.is_dir():
            return
        for directory in thumbs_root.glob("print*"):
            # 目录名形态 ``print`` / ``print~<节点>``（与 _print_thumb_provider 同源）
            if not directory.is_dir() or not directory.name.startswith("print"):
                continue
            for stem in stems:
                try:
                    (directory / f"{stem}.jpg").unlink(missing_ok=True)
                except OSError:
                    pass

    def _print_entries(self) -> tuple[list[dict], dict]:
        """第四步待打印图片列表（规则见 services/print_plan.plan_print_entries）。

        ⚠️ **取图目录由拼版是否生效决定**（``ImpositionMixin.print_source_dir``）：
        拼版启用且有拼版页 → ``stages/imposition``（拼版已是成品整页），
        否则 → ``stages/rembg``（第三步「执行去底色」的成品）。
        ``plan_print_entries`` 只认"一批成品图 + 顺序文档"，对来源无感。

        ``size_for``（= :meth:`_print_image_size`）：逐页 rect 只对**画它时那张图**
        有效——图片已被上游换掉的那些页不再套旧框，改由 ``plan_print_page`` 按
        **当前 PDF排版参数**（纸张/方向/边距/原比例）重新排版。
        """
        task_id = self.task_id
        if not task_id:
            return [], {"rembg_snapshot": [], "pages": []}
        # ⚠️ 上游**执行成功**之前不建表：去底色的实时预览会把成品写进
        #    ``stages/rembg``，但那只是"去底色这一步内部能看到的东西"，
        #    不该被 PDF排版看到（用户 2026-11-03）。
        if self.current_stage() == "print" and not self._stage_input_visible():
            return [], {"rembg_snapshot": [], "pages": []}
        source_dir = self.print_source_dir()
        rembg_files = sorted(
            list_stage_images(source_dir),
            key=lambda p: natural_sort_key(p.name),
        )
        # ⚠️ 没有任务（task_id 为 None）时这份清单无处可落。调用方都在有任务时
        #    才进这里，这里显式挡一道：早失败比把 None 拼进路径好。
        doc = self.store.load_print_doc(task_id, **self._node_scope())
        # ⚠️ 来源切换（拼版 ↔ 去底色）后，旧来源那一批还留在 print.json 里；
        # 不剔掉就会被当成"用户插入的外部图片"追加进 PDF（见 print_plan 的
        # drop_foreign_stage_pages）。
        stages_root = self.store.task_dir(task_id) / "stages"
        cleaned = drop_foreign_stage_pages(
            doc.get("pages") if doc else None, source_dir, stages_root,
        )
        # 「已删除图片」同样要随来源切换清理：旧来源的页面残留既不该出现在
        # 待打印列表，也不该出现在「恢复图片」里（恢复回来也取不到图）。
        cleaned_deleted = drop_foreign_stage_pages(
            doc.get("deleted_pages") if doc else None, source_dir, stages_root,
        )
        if doc and (
            len(cleaned) != len(doc.get("pages") or [])
            or len(cleaned_deleted) != len(doc.get("deleted_pages") or [])
        ):
            doc = {
                **doc, "pages": cleaned, "deleted_pages": cleaned_deleted,
            }
            self.store.save_print_doc(task_id, doc, **self._node_scope())
        # 「上一步更新了哪些图片」的记录 + 那些页的旧缩略图缓存失效：
        # 都在建表之前按**逐图判据**做掉（判据本体见 print_plan.rect_fits_image）。
        stale = stale_rect_pages(
            doc.get("pages") if doc else None, self._print_image_size
        )
        self._report_updated_print_images(stale)
        self._drop_updated_print_thumbs(stale)
        entries, new_doc = plan_print_entries(
            rembg_files, doc, size_for=self._print_image_size
        )
        self._print_doc_snapshot = new_doc
        if not doc or set(doc.get("rembg_snapshot") or []) != set(
            new_doc["rembg_snapshot"]
        ):
            self.store.save_print_doc(task_id, new_doc, **self._node_scope())
        # 管理弹窗/删除恢复页签要的缩略图：进入本步就后台备好（拼版成品、
        # 手动插入图没有第三步的预生成缓存）。
        self._warm_print_thumbs(
            [str(e.get("file") or "") for e in entries]
            + [str(p.get("file") or "") for p in (new_doc.get("deleted_pages") or [])]
        )
        return entries, new_doc

    def _save_print_order(self, silent: bool = False) -> None:
        """列表拖动/删除后持久化顺序。

        ``silent=True`` 供版面编辑器复用：拖拽会频繁落盘，若每次都打一条
        「列表已更新」日志会淹没「第 N 页版面已更新」这条真正有用的信息。

        ⚠️ 连 ``rect_size``（**画这个框时那张图的像素尺寸**）一起落盘：它是
        "这张图的版面是按哪张图量的"的唯一凭据——下次这张图被上游换掉时，
        靠它判定旧框失效、改按当前参数重排（见 ``print_plan.rect_fits_image``）。
        """
        if not self.task_id:
            return
        entries = self.print_preview.entries()
        doc = getattr(self, "_print_doc_snapshot", None) or {
            "rembg_snapshot": [],
            "pages": [],
        }
        # 删除是**软删除**（用户 2026-10-31）：从列表里拿掉的条目记进
        # ``deleted_pages``，供「插入图片 → 恢复图片」重新放回；文件本身不动。
        # 用"上次落盘的 pages"与当前列表求差——拖动/删除/键盘 Delete 都走这里，
        # 不必让每个删除入口各自上报（少一处就会漏记）。
        previous = doc.get("pages") or []
        current_files = {str(e.get("file")) for e in entries}
        removed = [
            p for p in previous
            if str(p.get("file")) and str(p.get("file")) not in current_files
        ]
        deleted = list(doc.get("deleted_pages") or [])
        known = {str(p.get("file")) for p in deleted}
        for page in removed:
            file_text = str(page.get("file"))
            if file_text not in known:
                deleted.append(ordered_page_record(page))
                known.add(file_text)
        doc["pages"] = [
            ordered_page_record(e) for e in entries
        ]
        if deleted:
            doc["deleted_pages"] = deleted
        try:
            self.store.save_print_doc(self.task_id, doc, **self._node_scope())
        except OSError as exc:
            # ⚠️ 落盘失败必须让用户看见（2026-09-26 审计）：任务目录被外部删除 /
            #    磁盘满时，原先这个异常会**直接从 Qt 槽里抛出去**（排序、拖动版面
            #    都是槽），只打印到控制台，用户看到的是"拖了没反应"且毫无原因。
            message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "列表未保存", message)
            return
        if not silent:
            self.log_view.append(
                f"待打印列表已更新（{self.print_preview.count()} 页）。"
            )

    def _print_insert_dir(self) -> Path | None:
        """「插入图片」的**复制落点**：``tasks/<任务号>/inserted/``。

        ⚠️ 不能放 ``stages/`` 下：那一层是各阶段产物，``print_plan``
        ``drop_foreign_stage_pages`` 会把"本任务其它阶段的残留"剔掉——用户插入的
        图会被当成上一轮来源残留删掉。放任务根目录的兄弟目录，既不与阶段产物
        混淆，也随「删除任务」整体清理。
        """
        if not self.task_id:
            return None
        return self.store.task_dir(self.task_id) / "inserted"

    def _print_deleted_pages(self) -> list[dict]:
        """当前任务里**已软删除、可恢复**的待打印条目。

        只认 print.json 的 ``deleted_pages``（由 ``_save_print_order`` 记录），
        文件已不存在的条目没有恢复价值，直接跳过。
        """
        if not self.task_id:
            return []
        doc = self.store.load_print_doc(self.task_id, **self._node_scope()) or {}
        out: list[dict] = []
        for page in doc.get("deleted_pages") or []:
            file_text = str(page.get("file") or "")
            if file_text and Path(file_text).exists():
                out.append(dict(page))
        return out

    def _manage_print_images(self) -> None:
        """缩略图条下方「管理图片」：打开**草稿式**管理弹窗 A。

        面板里的排序 / 多选 / 插入 / 恢复都只是草稿（用户 2026-11-02：
        「管理弹窗A中的效果如果不保存，则不生效」）；只有外壳的「保存」才由
        本方法写回数据层。
        """
        if not self.task_id:
            return
        from desktop.components.dialog_shell import shell_dialog
        from desktop.components.print_manage_dialog import PrintManagePanel

        entries = self.print_preview.entries()
        # 打开前先确保缩略图在后台生成（已生成过的直接命中，不重复派发）：
        # 弹窗构造只读小图，否则 85 张原图同步解码就是"打开慢"的来源。
        self._warm_print_thumbs(
            [str(entry.get("file") or "") for entry in entries]
            + [str(page.get("file") or "") for page in self._print_deleted_pages()]
        )
        panel = PrintManagePanel(
            entries=entries,
            deleted=self._print_deleted_pages(),
            thumb_for=self._print_thumb_provider,
            parent=_parent(self),
        )
        # 后台缩略图就绪后就地刷新弹窗（缩略图生成可能比弹窗慢）
        self._manage_panel = panel
        try:
            dialog = shell_dialog(
                "管理图片", panel, _parent(self),
                size=(900, 640), ok_text="保存",
            )
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._manage_panel = None
        if not accepted:
            return
        self._apply_print_manage(panel.entries())

    def _apply_print_manage(self, entries: list[dict]) -> None:
        """把管理弹窗的草稿写回列表（离屏自测可直接调用，不弹窗）。

        草稿里带 ``_pending`` 的是**刚从本地选入、还没复制**的新图：先按插入
        口径复制进 ``inserted/``，成功后再整体落盘；复制期间界面保持原样，
        全部完成才刷新一次。没有待复制项时同步落盘。
        """
        if not self.task_id:
            return
        from desktop.components.print_manage_dialog import PENDING_KEY, TARGET_KEY

        draft = [dict(entry) for entry in entries]
        pending = [entry for entry in draft if entry.get(PENDING_KEY)]
        if not pending:
            self._commit_print_manage(draft)
            return
        target_dir = self._print_insert_dir()
        if target_dir is None:
            return
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            message = f"插入目录创建失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "管理图片失败", message)
            return
        # 重名避让：同一次里选中同一张图两次，也要各自落到不同文件名上
        jobs: list[tuple[Path, Path]] = []
        reserved: set[str] = set()
        for entry in pending:
            source = Path(str(entry.get("file") or ""))
            target = target_dir / source.name
            counter = 1
            while target.name in reserved or target.exists():
                target = target_dir / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            reserved.add(target.name)
            entry[TARGET_KEY] = str(target)
            jobs.append((source, target))
        task_id = self.task_id
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker(jobs)
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.finished,
                    lambda done, errors: self._on_print_manage_copied(
                        done, errors, draft, task_id
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    w.failed,
                    lambda msg: self._toast("error", "管理图片失败", msg),
                    thread,
                ),
                w.finished.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_print_manage_copied(
        self, done: list, errors: list, entries: list[dict], task_id: str,
    ) -> None:
        """后台复制完成（主线程）：把 ``_pending`` 换成任务目录里的副本再落盘。"""
        from desktop.components.print_manage_dialog import PENDING_KEY, TARGET_KEY

        # 复制期间切了任务：这批文件属于旧任务，不能进新任务的清单
        if self.task_id != task_id:
            self.log_view.append("已切换任务，忽略上一次未完成的管理图片保存。")
            return
        if not self.task_id:
            return
        done_targets = {str(target) for _source, target in done}
        failed = 0
        final: list[dict] = []
        for entry in entries:
            if not entry.get(PENDING_KEY):
                final.append(entry)
                continue
            target = str(entry.get(TARGET_KEY) or "")
            if target not in done_targets:
                # 复制失败的新图不进清单（其余条目照常保存）
                failed += 1
                continue
            renamed = {
                key: value for key, value in entry.items()
                if key not in (PENDING_KEY, TARGET_KEY, "file", "label")
            }
            final.append({
                **renamed, "file": target, "label": Path(target).stem,
            })
        self._commit_print_manage(final)
        if errors or failed:
            reason = errors[0][1] if errors else "复制失败"
            note = f"{failed or len(errors)} 张新图未能插入：{reason}"
            self.log_view.append(note)
            self._toast("warning", "部分图片未插入", note)

    def _commit_print_manage(self, entries: list[dict]) -> None:
        """管理弹窗「保存」的落盘：写回 pages 顺序，并维护软删除清单。"""
        task_id = self.task_id
        if not task_id:
            return
        doc = self.store.load_print_doc(
            task_id, **self._node_scope()
        ) or {"rembg_snapshot": [], "pages": []}
        previous = doc.get("pages") or []
        current_files = {
            str(entry.get("file")) for entry in entries if entry.get("file")
        }
        # 在弹窗里拿掉的条目与右键删除同口径：记进 deleted_pages 以便恢复
        removed = [
            page for page in previous
            if str(page.get("file")) and str(page.get("file")) not in current_files
        ]
        deleted = list(doc.get("deleted_pages") or [])
        known = {str(page.get("file")) for page in deleted}
        for page in removed:
            file_text = str(page.get("file"))
            if file_text not in known:
                deleted.append(ordered_page_record(page))
                known.add(file_text)
        # 恢复回列表的图片不再属于「已删除」
        doc["pages"] = [ordered_page_record(entry) for entry in entries]
        doc["deleted_pages"] = [
            page for page in deleted
            if str(page.get("file")) not in current_files
        ]
        try:
            self.store.save_print_doc(task_id, doc, **self._node_scope())
        except OSError as exc:
            message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "列表未保存", message)
            return
        self.print_preview.set_entries(self._print_entries()[0])
        self.log_view.append(
            f"待打印列表已更新（{self.print_preview.count()} 页）。"
        )

    def _insert_print_images(self, position: str | None = None) -> None:
        """打开「插入图片」弹窗（恢复已删除图片 / 新上传图片）。

        ``position``：右键「向前插入 / 向后插入」指定的默认落点；工具栏按钮
        不传，沿用旧行为「落在当前选中页之后」（弹窗里仍可改）。

        弹窗底部的位置选项以**当前选中的页**为准（用户 2026-10-31：
        「插入第x页之前 / 之后，x是当前的页」）。
        """
        if not self.task_id:
            return
        from desktop.components.dialog_shell import shell_dialog
        from desktop.components.print_insert_dialog import PrintInsertPanel

        entries = self.print_preview.entries()
        row = self.print_preview.strip.currentRow()
        deleted = self._print_deleted_pages()
        # 恢复页签的缩略图同样走 print_manage 缓存（刚删掉的图还没预热过）
        self._warm_print_thumbs(
            [str(page.get("file") or "") for page in deleted]
        )
        panel = PrintInsertPanel(
            deleted=deleted,
            current_row=row,
            total=len(entries),
            default_position=position or "after",
            thumb_for=self._print_thumb_provider,
        )
        dialog = shell_dialog(
            "插入图片", panel, _parent(self),
            size=(760, 640), ok_text="插入",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = panel.result_data()
        if not result["files"] and not result["deleted"]:
            self._toast("warning", "未选择图片", "请勾选要恢复的图片或选择新图片。")
            return
        self._apply_print_insert(result, row)

    def _apply_print_insert(self, result: dict, base_row: int) -> None:
        """把弹窗结果落到列表：先恢复已删除图片，再异步复制新上传的图片。

        ``base_row`` 是弹窗打开时选中的行（-1 = 未选中）。
        """
        if not self.task_id:
            return
        task_id = self.task_id
        entries = self.print_preview.entries()
        total = len(entries)
        before = result.get("position") == "before"
        if total <= 0:
            insert_at = 0
        elif base_row < 0:
            insert_at = 0 if before else total
        else:
            insert_at = base_row if before else min(base_row + 1, total)
        restored = [
            dict(page) for page in result.get("deleted") or []
            if Path(str(page.get("file") or "")).exists()
        ]
        if restored:
            doc = self.store.load_print_doc(task_id, **self._node_scope()) or {
                "rembg_snapshot": [], "pages": [],
            }
            restored_files = {str(p["file"]) for p in restored}
            new_entries = list(entries)
            new_entries[insert_at:insert_at] = restored
            doc["pages"] = [ordered_page_record(e) for e in new_entries]
            doc["deleted_pages"] = [
                p for p in (doc.get("deleted_pages") or [])
                if str(p.get("file")) not in restored_files
            ]
            try:
                self.store.save_print_doc(task_id, doc, **self._node_scope())
            except OSError as exc:
                message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
                self.log_view.append(message)
                self._toast("error", "列表未保存", message)
                return
            # ⚠️ _print_entries 返回 (条目, 文档) 两件，set_entries 只要前者。
            self.print_preview.set_entries(self._print_entries()[0])
            entries = self.print_preview.entries()
            self.print_preview.strip.setCurrentRow(
                min(insert_at, max(len(entries) - 1, 0))
            )
            item = self.print_preview.strip.item(insert_at)
            if item is not None:
                self.print_preview.strip.scrollToItem(item)
            self.log_view.append(
                f"已恢复 {len(restored)} 张已删除的图片（第 {insert_at + 1} 页位置）。"
            )
        filenames = [str(p) for p in (result.get("files") or [])]
        if not filenames:
            return
        task_id = self.task_id
        # 落点锚点：插入位置**前一条**的路径。复制在后台，回来时按锚点重新定位
        # （用户可能在复制期间又拖了列表）。
        new_index = insert_at + len(restored)
        anchor = (
            entries[new_index - 1]["file"]
            if 0 < new_index <= len(entries) else None
        )
        target_dir = self._print_insert_dir()
        if target_dir is None:
            return
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            message = f"插入目录创建失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "插入图片失败", message)
            return
        # 主线程只算 (源, 目标) 对；重名避让：同一次多选里选到同一张图也要各自
        # 落到不同文件名上（reserved 记录本次已占用的名字）。
        jobs: list[tuple[Path, Path]] = []
        reserved: set[str] = set()
        for filename in filenames:
            source = Path(filename)
            target = target_dir / source.name
            counter = 1
            while target.name in reserved or target.exists():
                target = target_dir / f"{source.stem}-{counter}{source.suffix}"
                counter += 1
            reserved.add(target.name)
            jobs.append((source, target))
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker(jobs)
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.finished,
                    lambda done, errors: self._on_print_images_copied(
                        done, errors, anchor, task_id, new_index
                    ),
                    thread,
                ),
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

    def _on_print_images_copied(
        self, done: list, errors: list, anchor: str | None, task_id: str,
        fallback_index: int | None = None,
    ) -> None:
        """后台复制完成（主线程）：把成功的副本按锚点插进列表并刷新。"""
        # 复制期间切了任务：这批文件属于旧任务，不能进新任务的清单
        if self.task_id != task_id:
            self.log_view.append("已切换任务，忽略上一次未完成的图片插入。")
            return
        if not self.task_id or not done:
            if errors:
                self._toast("error", "插入图片失败", errors[0][1])
            return
        entries = self.print_preview.entries()
        insert_at = max(
            0, min(int(fallback_index or 0), len(entries))
        )
        if anchor is not None:
            for index, entry in enumerate(entries):
                if entry.get("file") == anchor:
                    insert_at = index + 1
                    break
        new_entries = [
            {"file": str(Path(target)), "label": Path(target).stem}
            for _source, target in done
        ]
        entries[insert_at:insert_at] = new_entries
        try:
            self.store.save_print_pages(self.task_id, entries, **self._node_scope())
        except OSError as exc:
            # 同 _save_print_order：落盘失败必须可见，不能从 Qt 槽直接炸出去
            message = f"待打印列表保存失败：{type(exc).__name__}: {exc}"
            self.log_view.append(message)
            self._toast("error", "列表未保存", message)
            return
        # ⚠️ _print_entries 返回 (条目, 文档) 两件，set_entries 只要前者。
        self.print_preview.set_entries(self._print_entries()[0])
        # set_entries 会把当前行复位到第一页；落回第一张新图并滚到可见处，
        # 让用户立刻看到"插在这里了"。
        self.print_preview.strip.setCurrentRow(insert_at)
        item = self.print_preview.strip.item(insert_at)
        if item is not None:
            self.print_preview.strip.scrollToItem(item)
        note = f"已插入 {len(done)} 张图片（第 {insert_at + 1} 页位置）。"
        if errors:
            note += f"（{len(errors)} 张失败：{errors[0][1]}）"
            self._toast("warning", "部分图片插入失败", errors[0][1])
        self.log_view.append(note)

    def _latest_print_pdf_path(self) -> Path | None:
        """最近一次 print 执行产出的 PDF 路径（按 YAML pdf_name 解析）。

        ⚠️ 目录与历史都按**当前 PDF排版节点**取（B 方案）：两个「PDF排版」节点
        各有自己的输出目录（``stages/print[~<节点>]``），按阶段取会把 A 节点的
        PDF 当成 B 节点的产物——用户点下载拿到的是另一个节点的文件。
        """
        if not self.task_id:
            return None
        node = self.node_of_stage("print")
        pdf_name = "print.pdf"
        history = (
            self.store.list_node_runs(self.task_id, node, "print")
            if node
            else self.store.list_stage_runs(self.task_id, "print")
        )
        if history:
            params = history[0].get("parameters", {})
            if params.get("pdf_name"):
                pdf_name = str(params["pdf_name"])
        out_dir = self.store.scoped_stage_dir(self.task_id, node, "print")
        candidate = out_dir / pdf_name
        if candidate.exists():
            return candidate
        # 兜底：目录下任意 pdf
        for cand in out_dir.glob("*.pdf"):
            return cand
        return None

    # ------------------------------------------------------- 取图来源 / 旧数据
    def print_source_stage(self) -> str:
        """第四步**当前**的取图来源阶段 key（``rembg`` 或 ``imposition``）。

        ⚠️ 与 :meth:`print_source_dir` 同源：那边取路径、这边取 key，都走
        ``ports.print_pages_supplier(imposition_active())`` 这一次判定——
        "PDF 是从哪儿取的"只有一个答案，不许两处各判一次。
        """
        from desktop.steps.ports import print_pages_supplier

        # ⚠️ 用 **effective**（能不能真跑）而不是 active（勾没勾）：图里没有
        #    拼版节点时，来源必须回到去底色，否则与 ``print_source_dir``
        #    给用户的预览不一致（界面说 A、执行做 B）。
        return print_pages_supplier(self.imposition_effective())

    def _print_source_switched(self) -> bool:
        """磁盘上那份 PDF 是不是**换了取图来源之后**生成的（旧数据）。

        用户 2026-10-03："之前没有启用拼版但生成了 pdf，此时再次启用拼版，
        则 PDF排版的数据要来源于拼版，**旧的数据不显示**"。所以这份判定是
        "旧数据不显示"的开关——判据与实现见
        :func:`desktop.services.stale_chain.print_source_switched`。
        """
        if not self.task_id:
            return False
        from desktop.services.stale_chain import print_source_switched

        return print_source_switched(
            self.store.all_stage_runs(self.task_id), self.print_source_stage()
        )

    def _current_print_pdf_path(self) -> Path | None:
        """**当前取图来源下**可用的 PDF；来源或取图内容已变则返回 ``None``。

        所有"给用户看/下载这份 PDF"的地方都走这里（第四步预览的下载按钮、
        下载动作本身），别再直接用 :meth:`_latest_print_pdf_path`——那个只
        回答"磁盘上有没有"，不回答"还是不是当前的"。
        """
        if self._print_source_switched() or getattr(self, "_print_data_stale", False):
            return None
        return self._latest_print_pdf_path()

    def can_delete_selected_print(self) -> bool:
        """顶部菜单「编辑 → 删除选中」的启用判据：正在第四步且有选中项。"""
        return (
            self.current_stage() == "print"
            and bool(self.print_preview.strip.selectedItems())
        )

    def delete_selected_print(self) -> None:
        """顶部菜单「编辑 → 删除选中」：删掉缩略图条里选中的待打印图。"""
        if self.can_delete_selected_print():
            self.print_preview.remove_selected()

    def _download_print_pdf(self) -> None:
        """将已生成的 PDF 另存到用户选择的位置（默认下载目录、同名文件）。"""
        if not self.task_id:
            return
        # ⚠️ 换了取图来源、或取图目录里的图片变了（拼版成品重存）之后，磁盘上那份
        #    PDF 属于**旧数据**，不再提供下载（用户 2026-10-03："旧的数据不显示"）。
        #    先说清楚为什么不能下，别让用户以为是程序坏了。
        source_switched = self._print_source_switched()
        if source_switched or getattr(self, "_print_data_stale", False):
            reason = (
                "取图来源已改变（图片拼版开关）" if source_switched
                else "取图里的图片已更新（拼版成品 / 去底色成品变了）"
            )
            self._toast(
                "warning",
                "PDF 需要重新生成",
                f"{reason}，请先点「生成PDF」再下载。",
            )
            return
        # 优先用下载按钮当前绑定的 PDF；否则按最近一次 print 参数解析
        source = getattr(self.print_preview, "_pdf_path", None)
        if source is None or not Path(source).exists():
            source = self._latest_print_pdf_path()
        if source is None or not Path(source).exists():
            self._toast("warning", "无可下载 PDF", "请先执行「生成PDF」。")
            return
        source = Path(source)
        # 默认保存到系统「下载」目录，文件名与生成的 PDF 一致
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            _parent(self),
            "下载 PDF",
            str(default_dir / source.name),
            "PDF 文件 (*.pdf)",
        )
        if not target:
            return
        # ⚠️ 复制进后台线程（审计 D2）：几百 MB 的 PDF 用主线程 copy2 会把
        # 界面冻住整个复制时长；复制期间不禁按钮但用标志防重入。
        if getattr(self, "_download_busy", False):
            self._toast("warning", "正在下载", "上一次下载还没完成。")
            return
        self._download_busy = True
        from desktop.workers import CopyFilesWorker, connect_queued

        worker = CopyFilesWorker([(source, Path(target))])
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(self, w.finished, self._on_download_done, thread),
                connect_queued(
                    self,
                    w.failed,
                    lambda msg: self._on_download_done([], [(str(source), msg)]),
                    thread,
                ),
                w.finished.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_download_done(self, done: list, errors: list) -> None:
        """后台下载完成（主线程）：播报结果并解除防重入。"""
        self._download_busy = False
        if errors:
            self._toast("error", "下载失败", errors[0][1])
            return
        if not done:
            return
        target = done[0][1]
        self._toast("success", "下载完成", f"已保存到：{target}")
        self.log_view.append(f"PDF 已下载到：{target}")

    def _export_print_image(self) -> None:
        """把**当前页**的 A4 效果图另存为图片（单页；精度与 PDF 同级 300dpi）。

        渲染交给 ``print_preview``（它才懂排版口径），这里只负责对话框与提示：
        与「下载 PDF」保持同一套交互（默认下载目录、toast、写日志）。
        """
        default_name = self.print_preview.export_default_name()
        if not default_name:
            self._toast("warning", "无可导出页面", "请先在第四步添加要打印的图片。")
            return
        downloads = Path.home() / "Downloads"
        default_dir = downloads if downloads.exists() else Path.home()
        target, _ = QFileDialog.getSaveFileName(
            _parent(self),
            "下载本页图片",
            str(default_dir / default_name),
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg)",
        )
        if not target:
            return
        self._export_target = target
        self.print_preview.export_current_effect(target)

    def _on_export_finished(self, target: str) -> None:
        self._toast("success", "已导出本页图片", f"已保存到：{target}")
        self.log_view.append(f"本页图片已导出：{target}")

    def _on_export_failed(self, message: str) -> None:
        self._toast("error", "导出失败", message)
        self.log_view.append(f"导出本页图片失败：{message}")

    def _on_print_finished(self, printer_name: str) -> None:
        self._toast("success", "已发送打印", f"打印机：{printer_name}")
        self.log_view.append(f"本页已发送打印机：{printer_name}")

    def _on_print_failed(self, message: str) -> None:
        self._toast("error", "打印失败", message)
        self.log_view.append(f"打印本页失败：{message}")
