# -*- coding: utf-8 -*-
"""**模块一「选择拼版」控制器**：拼版页的增删与选择状态。

对应 UI 模块一（``desktop/components/imposition/page_list.py`` +
``picker.py``）与右侧面板的页管理按钮（``panel.py``）：
- 启用/取消拼版（决定第四步取图来源，落盘到 ``drafts/imposition.json``）；
- 「选择拼版」→ 弹窗挑两张加一页；或挑一张勾「自动拼版」批量加页；
  弹窗里还能「删除图片」（黑名单 ``removed`` 字段，软删除）与恢复；
- **单图页「新增图片」**（2026-09-30）：append 模式弹窗挑 1 张并进当前页；
- 删页入口只剩**左列**：「✕」释放单页 / 勾选悬浮框批量删除 / 清空全部
  ——右侧面板的「删除本页拼版」按钮已删（2026-09-30 用户定）；
  页序在左列**拖动排序**，翻页在画布下方「上一页/下一页」。

只通过 ``self`` 依赖共享基元（``imposition.ImpositionBaseMixin`` 提供的
``_imposition_doc`` / ``_save_imposition_pages`` / ``imposition_active`` /
``_refresh_print_source`` / ``_update_imposition_status`` 等）与宿主页面
（``step_bar``、``log_view``、``_toast``），本文件**不 import** 其它拼版
控制器模块——两个模块的 agent 可以互不影响地改。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.services.imposition import (
    ITEMS_PER_PAGE, append_item_to_page, auto_impose_pages, cn_page_label,
    excluded_files, make_page, make_single_page, same_path, used_source_files,
)

if TYPE_CHECKING:
    from desktop.store.store import TaskStore


class ImpositionPagesMixin:
    """拼版页管理（模块一）：启用开关、加页、删页、清空。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage 提供的属性（store/task_id/log_view/run_worker/window）
        # 与同级 Mixin 共享的基元（ImpositionBaseMixin 那一组）：本 Mixin 本体不
        # 持有，只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
        run_worker: Callable[..., Any]
        window: Callable[[], Any]
        _toast: Callable[..., None]
        _imposition_pages: Callable[[], list]
        _imposition_doc: Callable[[], dict[str, Any]]
        _refresh_print_source: Callable[..., None]
        _save_imposition_pages: Callable[..., None]
        _schedule_imposition_compose: Callable[..., None]
        _set_imposition_checked: Callable[..., None]
        _sync_imposition_step_bar: Callable[..., None]
        _update_imposition_status: Callable[..., None]
        imposition_source_files: Callable[[], list]

    # ------------------------------------------------------------- 选择状态
    def _load_imposition_enabled(self) -> bool:
        """当前任务是否选择了拼版（默认不选择）。"""
        if not self.task_id:
            return False
        return bool(self.store.load_imposition_doc(self.task_id).get("enabled"))

    def _save_imposition_enabled(self, enabled: bool) -> None:
        """把选择状态随任务落盘（drafts/imposition.json）。"""
        if not self.task_id:
            return
        doc = self.store.load_imposition_doc(self.task_id)
        doc["enabled"] = bool(enabled)
        self.store.save_imposition_doc(self.task_id, doc)

    def _on_imposition_enabled_toggled(self, on: bool) -> None:
        """拼版详情里的启用开关：更新节点选择态并落盘。

        启用/取消会**改变第四步的取图来源**（见 ``print_source_dir``），所以
        同时把待打印列表刷新一次——否则用户切到第四步看到的还是旧的来源。
        """
        self._save_imposition_enabled(on)
        self._sync_imposition_step_bar()
        self._toast(
            "info", "图片拼版",
            "已启用「图片拼版」：第四步「PDF排版」将使用拼版结果。"
            if on else
            "已取消「图片拼版」：第四步「PDF排版」回到第三步的去底色产物。",
        )
        if on:
            self._schedule_imposition_compose()
        self._refresh_print_source()

    # ------------------------------------------------------------- 加页
    def _on_imposition_add_requested(self) -> None:
        """点「＋ 选择拼版」：弹窗自由多选，点「开始拼版」按每两张一页配对。"""
        if not self.task_id:
            return
        from desktop.components.imposition.picker import ImpositionPickerDialog

        doc = self._imposition_doc()
        sources = self.imposition_source_files()
        if not sources:
            self._toast(
                "warning", "没有可拼版的图片",
                "请先在第三步「生成预览」并「提交本次任务」，"
                "再从拼版里选择成品图片。",
            )
            return
        used = used_source_files(doc)
        removed = excluded_files(sources, doc)
        # 候选池 = 没被页用过的图（**含已删除的**——弹窗里可以恢复它们）；
        # remaining 才是真正的候选。池子按源清单顺序传给弹窗。
        removed_keys = {str(f) for f in removed}
        pool = [f for f in sources if str(f) not in used]
        remaining = [f for f in pool if str(f) not in removed_keys]
        if not remaining and not removed:
            self._toast(
                "warning", "没有可选的图片",
                "所有图片都已被拼版使用。可先删掉某些拼版页再来选。",
            )
            return
        dialog = ImpositionPickerDialog(pool, self.window(), removed_files=removed)
        if not dialog.exec():
            # 取消也落盘：删除/恢复是即时意图，与是否开始拼版无关
            self._apply_picker_removed(dialog)
            return
        self._apply_picker_removed(dialog)
        # 「从这张图片开始自动拼版」：只勾 1 张 + 勾了复选框 → 从那张起把
        # 剩余候选按规则自动拼完（整幅单独一页；前一个左半幅 + 当前右半幅
        # 配对；落单单页）。规则唯一实现在 services.imposition.auto_impose_pages。
        auto_file = dialog.auto_mode_file()
        auto_log: str | None = None
        if auto_file is not None:
            new_pages = auto_impose_pages(dialog.auto_sequence())
            if new_pages:
                auto_log = (
                    f"已从「{auto_file.stem}」起自动拼版：新增 {len(new_pages)} 页"
                    "（半幅按「前一左＋后一右」且页号连续配对；"
                    "整幅与落单图各自单独一页）。"
                )
        else:
            # 手动勾选（用户 2026-09-30 定的三种形态）：**1 张 → 单独一页**；
            # 2 张 → 拼成一页（序号在前的排右侧）。弹窗里勾 0/≥3 张时
            # 「开始拼版」不可点，这里只做兜底。
            batch = dialog.picked_files()
            if not batch:
                return
            if len(batch) == 1:
                made = make_single_page(batch[0])
                new_pages = [made] if made is not None else []
            else:
                new_pages = []
                for i in range(0, len(batch) - 1, 2):
                    made = make_page(batch[i:i + ITEMS_PER_PAGE])
                    if made is not None:
                        new_pages.append(made)
        if not new_pages:
            self._toast(
                "error", "拼版失败",
                "选中的图片无法读取尺寸，请换一张或换两张。",
            )
            return
        pages = self._imposition_pages()
        pages.extend(new_pages)
        self._save_imposition_pages(pages)
        first_index = len(pages) - len(new_pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(first_index)
        self._update_imposition_status(first_index)
        if auto_log is not None:
            self.log_view.append(auto_log)
        elif len(new_pages) == 1:
            page = new_pages[0]
            if len(page["items"]) == 1:
                self.log_view.append(
                    f"已添加第 {first_index + 1} 页拼版：单图"
                    f"「{Path(page['items'][0]['file']).stem}」单独一页。"
                )
            else:
                self.log_view.append(
                    f"已添加第 {first_index + 1} 页拼版："
                    f"右侧「{Path(page['items'][0]['file']).stem}」、"
                    f"左侧「{Path(page['items'][1]['file']).stem}」。"
                )
        else:
            paired = len(new_pages) * ITEMS_PER_PAGE
            leftover = batch[paired:]
            self.log_view.append(
                f"已添加 {len(new_pages)} 页拼版：从"
                f"「{Path(batch[0]).stem}」开始每两张一页"
                + (f"（「{Path(leftover[0]).stem}」落单，未拼）。"
                   if leftover else "。")
            )
        if not self._load_imposition_enabled():
            # 加了拼版页却还没启用：顺手启用，否则第四步不会用到它
            self._set_imposition_checked(True)

    def _apply_picker_removed(self, dialog) -> None:
        """把弹窗里「删除图片 / 恢复」的结果落盘（``removed`` 黑名单字段）。

        集合没变（删了又恢复）就不动文档；有变化就写日志——被删的图不再
        进入「选择拼版」候选（``remaining_files`` 会排除它），恢复即回来。
        """
        if self.task_id is None or not dialog.removed_changed():
            return
        removed = [str(p) for p in dialog.removed_files()]
        doc = self.store.load_imposition_doc(self.task_id)
        old = {str(f) for f in doc.get("removed") or []}
        doc["removed"] = removed
        self.store.save_imposition_doc(self.task_id, doc)
        added = [f for f in removed if f not in old]
        restored = [f for f in old if f not in set(removed)]
        if added:
            self.log_view.append(
                f"已把 {len(added)} 张图片移出选择范围："
                + "、".join(Path(f).stem for f in added) + "。"
            )
        if restored:
            self.log_view.append(
                f"已恢复 {len(restored)} 张图片到选择范围："
                + "、".join(Path(f).stem for f in restored) + "。"
            )

    # ------------------------------------------------------------- 单图页加图
    def _on_imposition_add_image(self) -> None:
        """单图页点「新增图片」：append 弹窗挑 1 张，并进当前这一页。

        版面规则唯一实现在 ``services.imposition.append_item_to_page``：
        原图是左半幅 → 新图进右槽贴右边；其余 → 新图进左槽贴左边；原图
        的位置/大小/旋转**原样保留**。候选池与「选择拼版」同一套（剩余
        未用，可恢复已删除）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0 or not self.task_id:
            return
        index = view.current_index()
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = pages[index].get("items") or []
        if len(items) != 1:
            return  # 按钮只在单图页出现；防御一下
        from desktop.components.imposition.picker import ImpositionPickerDialog

        doc = self._imposition_doc()
        sources = self.imposition_source_files()
        if not sources:
            self._toast(
                "warning", "没有可添加的图片",
                "请先在第三步「生成预览」并「提交本次任务」。",
            )
            return
        used = used_source_files(doc)
        removed = excluded_files(sources, doc)
        removed_keys = {str(f) for f in removed}
        pool = [f for f in sources if str(f) not in used]
        remaining = [f for f in pool if str(f) not in removed_keys]
        if not remaining and not removed:
            self._toast(
                "warning", "没有可选的图片",
                "所有图片都已被拼版使用。可先删掉某些拼版页再来选。",
            )
            return
        dialog = ImpositionPickerDialog(
            pool, self.window(), removed_files=removed, mode="append",
        )
        if not dialog.exec():
            # 取消也落盘：删除/恢复是即时意图，与是否添加无关
            self._apply_picker_removed(dialog)
            return
        self._apply_picker_removed(dialog)
        picked = dialog.picked_files()
        if len(picked) != 1:
            return  # append 弹窗只放行 1 张；这里兜底
        merged = append_item_to_page(items, picked[0])
        if merged is None:
            self._toast(
                "error", "添加失败",
                "读不到所选图片的尺寸（文件可能已被移动或删除），请换一张。",
            )
            return
        pages[index] = {**pages[index], "items": merged}
        self._save_imposition_pages(pages)
        view.set_current(index)
        self._update_imposition_status(index)
        self.log_view.append(
            # ⚠️ `picked` 在边界收口成 Path：真实弹窗给 list[Path]，而自测替身
            #    给 list[str]——此前直接 `picked[0].stem` 会让**每次全量自测**
            #    都往 stderr 喷一条 AttributeError（图其实已加进版面，只是这行
            #    日志炸了、断言照过，长期被当成噪声忽略）。
            f"已在{cn_page_label(index)}新增图片「{Path(picked[0]).stem}」"
            f"（原有「{Path(items[0]['file']).stem}」的版面保持不动）。"
        )

    # ------------------------------------------------------------- 切页
    def _on_imposition_page_selected(self, index: int) -> None:
        """左列切到某一页（视图自己已切好画布，这里只更新状态行）。"""
        self._update_imposition_status(index)

    # ------------------------------------------------------------- 删页/页序
    def _on_imposition_batch_delete(self) -> None:
        """左列勾选多页后点悬浮框「批量删除」——**先弹窗确认**再删。

        语义与单页删除一致：版面调整丢失、图片释放回未选择列表。落盘后
        ``_save_imposition_pages`` 重建清单，勾选集合随页消失自动清空；
        当前页被删时落到「第一个被删页」左移后的位置（被删光了则钳到尾页）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        pages = self._imposition_pages()
        indexes = [i for i in view.checked_pages() if 0 <= i < len(pages)]
        if not indexes:
            self._toast("info", "没有勾选", "先在左列勾选要删除的拼版页。")
            return
        # 确认弹窗（用户 2026-09-30 口径）：宽度固定、正文折行，正文下方
        # 逐页列出被勾选的页（「第一页：图名 · 图名」），页数多时列表
        # 内部滚动、弹窗高度封顶——见 BatchDeleteConfirmDialog。
        from desktop.components.imposition.confirm_delete import (
            BatchDeleteConfirmDialog,
        )

        dialog = BatchDeleteConfirmDialog(
            [(i, pages[i]) for i in indexes], self.window(),
        )
        if not dialog.exec():
            return
        current = view.current_index()
        drop = set(indexes)
        self._save_imposition_pages(
            [p for i, p in enumerate(pages) if i not in drop]
        )
        if current in drop:
            anchor = min(indexes)
            new_current = anchor - sum(1 for i in indexes if i < anchor)
        else:
            new_current = current - sum(1 for i in indexes if i < current)
        new_current = min(new_current, len(pages) - len(drop) - 1)
        view.set_current(new_current)
        self._update_imposition_status(view.current_index())
        # ⚠️ 页码清单必须先拼出来再用：此前这里直接引用 `{listing}` 而未定义
        #    ——批量删除**必定**在这条日志上抛 NameError（页已删、异常逃出，
        #    用户见不到任何提示；自测只验了信号发射，没跑过真正的处理器）。
        listing = "、".join(str(i + 1) for i in indexes)
        self.log_view.append(
            f"已批量删除 {len(indexes)} 页拼版（第 {listing} 页），"
            "图片已释放回未选择列表。"
        )

    def _on_imposition_page_reorder(self, source: int, target: int) -> None:
        """左列拖动排序松手：把第 ``source`` 页移到 ``target``（移除后口径）。

        ``_save_imposition_pages`` 会重建左列清单——页码标签「第几页」随新
        顺序重新生成，画布跟着落到拖动后的那一页。
        """
        pages = self._imposition_pages()
        if not (0 <= source < len(pages)):
            return
        page = pages.pop(source)
        target = max(0, min(target, len(pages)))
        pages.insert(target, page)
        self._save_imposition_pages(pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(target)
        self._update_imposition_status(target)

    def _on_imposition_release_page(self, index: int) -> None:
        """左列某页右侧的「✕」：删掉该页，把它的两张图释放回未选择列表。

        「未选择图片列表」= 源清单减去页引用与「删除图片」黑名单
        （``remaining_files``），所以删页即释放——下次「选择拼版」这两张图
        就回来了（除非它们被用户移出了选择范围）。
        """
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        removed = pages.pop(index)
        self._save_imposition_pages(pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(min(index, len(pages) - 1))
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )
        self.log_view.append(
            f"已释放第 {index + 1} 页的两张图片（"
            + "、".join(Path(i["file"]).stem for i in removed.get("items") or [])
            + "），回到未选择列表，可重新「选择拼版」。"
        )

    def _on_imposition_clear(self) -> None:
        """清空全部拼版页（选择态保留，便于重新拼）。"""
        pages = self._imposition_pages()
        if not pages:
            return
        from qfluentwidgets import Dialog

        dialog = Dialog(
            "清空拼版",
            f"将删除全部 {len(pages)} 页拼版（源图片不受影响）。\n是否继续？",
            self.window(),
        )
        dialog.yesButton.setText("清空")
        dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        self._save_imposition_pages([])
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(-1)
        self._update_imposition_status(-1)
        self.log_view.append("已清空全部拼版页。")

    # ------------------------------------------------------------- 左列缩略图
    def _imposition_page_thumb_manager(self):
        """页面缩略图**实体**的管理者（懒建；换任务自动换目录重读映射）。"""
        from desktop.components.imposition.page_thumb import PageThumbManager
        from desktop.utils.files import THUMBNAIL_EDGE

        if not self.task_id:
            return None
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is None:
            manager = PageThumbManager(
                self.store.imposition_page_thumbs_dir(self.task_id),
                THUMBNAIL_EDGE, self.run_worker, parent=self,
            )
            manager.page_ready.connect(self._on_imposition_page_thumb_ready)
            self._page_thumb_mgr = manager
        else:
            target = self.store.imposition_page_thumbs_dir(self.task_id)
            if manager.directory != target:
                manager.bind(target)
        return manager

    def _on_imposition_page_thumb_ready(self, index: int, pixmap) -> None:
        """一页的实体缩略图生成完：**只贴那一条**（反 O(N²) 护栏，2026-10-06）。"""
        view = getattr(self, "imposition_view", None)
        if view is not None and pixmap is not None and not pixmap.isNull():
            view.set_thumb_at(index, pixmap)

    def _refresh_imposition_page_thumbs(self, pages: list) -> None:
        """左列每页的缩略图：**落盘实体**（页面效果，``pageN.jpg``）。

        用户 2026-10-09 两轮报障的合流：①一页拼版是两张图合成的页面，旧
        口径"每页取第一张源图当代表"只显示半幅；②内存合成口径页内某张
        源图缩略图没到就出半张、且回填反查表只登记每页第一张（0002 任务
        实测 3-l·4-r 页只有半边有内容）。现在改**实体**口径：按版面把整页
        合成一张小图落盘（``tasks/<id>/thumbnails/imposition_pages/
        page<N>.jpg`` + ``index.json`` 映射），UI 只贴实体文件；签名（版面
        + 源图文件指纹）不匹配的页后台重生成。命中的页直接读盘——重进
        任务零生成。

        ⚠️ 与独立拼图页（``modules/imposition/page.py``）共用管理者组件，
        但**缓存根各归各**（用户 2026-10-04 明确「singletask 和 taskdetail
        不是一回事」）。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        manager = self._imposition_page_thumb_manager()
        if manager is None:
            return
        manager.retain(len(pages))
        by_index = [manager.pixmap_for(i, page) for i, page in enumerate(pages)]
        view.set_page_thumbs(by_index)
        manager.flush()

    def _drop_imposition_source_thumb(self, path_text: str) -> None:
        """某个源图被覆盖（编辑落盘）：含它的页重新生成缩略图实体。

        ⚠️ 签名里带**源图文件指纹**（大小 + mtime）：覆盖后签名必然变
        ⇒ 把含这个路径的页排进重生成批次即可，不用逐张清内存缓存（旧
        内存口径的坑：同路径换内容照旧贴回旧 QPixmap——用户 2026-10-08
        报"编辑完左列还是老图"）。路径形态（斜杠/大小写）仍走
        :func:`same_path` 判等。
        """
        pages = self._imposition_pages()
        hits = [
            index for index, page in enumerate(pages)
            if any(
                same_path(str(item.get("file") or ""), path_text)
                for item in page.get("items") or []
            )
        ]
        manager = self._imposition_page_thumb_manager()
        if hits and manager is not None:
            manager.invalidate(hits, pages)
