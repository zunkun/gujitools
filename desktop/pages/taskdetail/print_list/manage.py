# -*- coding: utf-8 -*-
"""「管理图片」与「插入图片」弹窗（从原 ``print_list.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.services.print_plan import ordered_page_record
from desktop.pages.taskdetail.print_list._qt import QDialog
from desktop.pages.taskdetail.print_list.helpers import _parent

if TYPE_CHECKING:
    from desktop.pages.taskdetail.print_list._host import PrintListHost
else:
    PrintListHost = object


class PrintManageMixin(PrintListHost):
    """管理/插入图片对话框、改名与批量插入后的落盘。"""
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
