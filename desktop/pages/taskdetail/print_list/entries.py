# -*- coding: utf-8 -*-
"""待打印条目的规划与顺序持久化（从原 ``print_list.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.services.print_plan import (
    drop_foreign_stage_pages,
    ordered_page_record,
    plan_print_entries,
    stale_rect_pages,
)
from desktop.utils.files import list_stage_images
from utils.sort_utils import natural_sort_key

if TYPE_CHECKING:
    from desktop.pages.taskdetail.print_list._host import PrintListHost
else:
    PrintListHost = object


class PrintEntriesMixin(PrintListHost):
    """条目规划（``plan_print_entries``）与 ``print.json`` 落盘。"""
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
        # 管理弹窗/删除恢复页签要的缩略图：**推后**在首帧之后后台备好（拼版成品、
        # 手动插入图没有第三步的预生成缓存）。⚠️ 不能在这里同步做——那是 343 次
        # 逐条查缓存，全落在"进页面"这一拍上（见 _schedule_print_thumbs_warm）。
        self._schedule_print_thumbs_warm(
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
