# -*- coding: utf-8 -*-
"""**模块一「选择拼版」控制器**：拼版页的增删与选择状态。

对应 UI 模块一（``desktop/components/imposition/page_list.py`` +
``picker.py``）与右侧面板的页管理按钮（``panel.py``）：
- 启用/取消拼版（决定第四步取图来源，落盘到 ``drafts/imposition.json``）；
- 「选择拼版」→ 弹窗挑两张加一页；或挑一张勾「自动拼版」批量加页；
  弹窗是**一个列表**（上游剩余图 + 本任务上传过的图），也能自己上传图片
  （2026-11-16：不再有「删除恢复」页签——删掉的图直接回到这个列表）；
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
    page_source_stems, same_path, used_source_files,
)

if TYPE_CHECKING:
    from desktop.store.store import TaskStore


def _chosen_items(dialog) -> list[dict]:
    """弹窗勾选结果 → ``[{"path": Path, "uploaded": bool}]``。

    ⚠️ 自测替身（``tests/selftests/imposition.py`` 里的 *_Fake*Dialog）只实现
    了 ``picked_files()``：这里用 ``getattr`` 兜底，替身不必跟着改；真弹窗
    走 ``chosen_items()``（带"是不是本次上传"的标记，宿主据此决定要不要
    复制文件）。
    """
    reader = getattr(dialog, "chosen_items", None)
    if callable(reader):
        return list(reader())
    return [
        {"path": Path(str(path)), "uploaded": False}
        for path in dialog.picked_files()
    ]


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
        _imposition_scope: Callable[[], dict]
        _imposition_flag_scope: Callable[[], dict]
        _refresh_print_source: Callable[..., None]
        _save_imposition_pages: Callable[..., None]
        _schedule_imposition_compose: Callable[..., None]
        _set_imposition_checked: Callable[..., None]
        _sync_imposition_step_bar: Callable[..., None]
        _update_imposition_status: Callable[..., None]
        imposition_source_files: Callable[[], list]
        # 上游检测节点的提交计划（``{产物 label: role}``，同级 Mixin 提供）
        imposition_role_map: Callable[[], dict[str, str]]
        # 当前格的节点实例 id（页面宿主提供）：缩略图实体目录按它分节点
        node_of_stage: Callable[[str], str | None]
        # 候选图的预生成小图来源（同级 Mixin 提供）：入口图片/去底色成品小图与
        # 源 PDF 页缩略图，见 :meth:`_imposition_picker_thumb`。
        _print_thumb_provider: Callable[[str], Any]
        _page_thumb_for: Callable[..., Any]

    # ------------------------------------------------------------- 选择状态
    def _load_imposition_enabled(self) -> bool:
        """当前任务是否选择了拼版（默认不选择）。

        ⚠️ 开关是**流程级**的（流程图上「是否拼版」网关问的就是它，决定第四步
        取图来源），所以读写都走**主节点**那一份文件
        （见 ``ImpositionBaseMixin._imposition_flag_scope``）；版面（pages）才
        按节点分。

        ⚠️ **流程条上那一格的"已选择/绿勾"不看它**（2026-10-18）：那一格表达的是
        "这一步处理到哪了"（判据是本节点有没有拼版页，见
        ``_sync_imposition_step_bar``）。这个开关只决定"第四步取不取拼版结果"。
        """
        if not self.task_id:
            return False
        return bool(
            self.store.load_imposition_doc(
                self.task_id, **self._imposition_flag_scope()
            ).get("enabled")
        )

    def _save_imposition_enabled(self, enabled: bool) -> None:
        """把选择状态随任务落盘（drafts/imposition.json ← 主节点那一份）。"""
        if not self.task_id:
            return
        scope = self._imposition_flag_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["enabled"] = bool(enabled)
        self.store.save_imposition_doc(self.task_id, doc, **scope)

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
    def _imposition_picker_thumb(self, path_text: str):
        """「选择拼版」弹窗候选图的**预生成小图路径**（没有则 ``None``）。

        用户 2026-10-17：弹窗里应该显示**缩略图**，而不是每次都现解码原图：

        - 「图片拼版」**不是**流程第一个节点时，候选是**上一个节点**的产物
          （正常是「图片去底色」提交后的成品 ``stages/rembg[~<节点>]``）——那些图
          在提交时就已生成 256px 小图（``thumbnails/print[~<节点>]``）；
        - 它是**流程第一个节点**时，候选是用户导入的入口图片
          （``stages/input/``）——导入时已生成 ``thumbnails/input/<图键>.jpg``；
        - 其余（``extract`` 上游的页图 / 手动插入的外部图）⇒ 回落源 PDF 页
          缩略图（``thumbnails/source``），仍没有就回 ``None``，由弹窗整幅解码。

        ⚠️ 判据**复用既有的两份 provider**，不在这里另写一套「哪个目录配哪份
        缓存」：:meth:`_print_thumb_provider`（入口图片 + 去底色提交成品）优先，
        :meth:`_page_thumb_for`（源 PDF 页）兜底——次序不能反：去底色成品与源
        PDF 页可能同名同页号，反了会把"去底色结果"显示成"PDF 原页"。

        ⚠️ **本任务上传的图一律现解码**（直接返回 ``None``）：两份缓存都是**按
        文件名**取图的，用户上传的图与上游某张同名时（``1-r.png`` 之类）会把
        别人的缩略图贴到它脸上。上传的图只有几张，现解码不慢。
        """
        insert_dir = self._imposition_insert_dir()
        if insert_dir is not None:
            try:
                if Path(path_text).is_relative_to(insert_dir):
                    return None
            except (OSError, ValueError):
                pass
        product = self._print_thumb_provider(path_text)
        if product is not None:
            return product
        page_spec = self._page_thumb_for(path_text)
        if isinstance(page_spec, dict):
            return Path(page_spec["path"])
        return None if page_spec is None else Path(page_spec)

    def _imposition_insert_dir(self) -> Path | None:
        """**上传图**的复制落点：``tasks/<任务号>/inserted/imposition/``。

        与「PDF排版 → 插入图片」同一口径（``print_list._print_insert_dir``）：
        不能放 ``stages/`` 下——那一层是阶段产物，``print_plan`` 会清理"本任务
        其它阶段的残留"，用户插进来的图会被当残留删掉。放任务根目录的兄弟
        目录，既不与阶段产物混淆，也随「删除任务」整体清理。

        ⚠️ 又**不与打印侧的 ``inserted/`` 混放**（用户 2026-11-16）：拼版的候选
        是**扫这个目录**得来的（见 :meth:`_imposition_candidate_pool`），混在一起
        会把「PDF排版」插进来的图也列进拼版候选。
        """
        if not self.task_id:
            return None
        from desktop.services.imposition_insert import upload_dir

        return upload_dir(self.store.task_dir(self.task_id))

    def _imposition_candidate_pool(self, doc: dict) -> list[Path]:
        """弹窗的**候选列表**：上游没用过的图 + 本任务上传过、现在没被页引用的图。

        用户 2026-11-16：删掉拼版页之后，自己上传的图必须像上游图一样**回到
        列表**（原先它不在任何"源清单"里，删页即永久消失）；上传过的图本就在
        任务目录里，扫目录即可，不必再往 ``imposition.json`` 里记一份（也就
        不会与上一步的页面清单打架）。

        顺序：上游图按源清单顺序在前，上传的按自然页序在后（``uploaded_candidates``
        已排序）。
        """
        from desktop.services.imposition_insert import uploaded_candidates

        used = used_source_files(doc)
        sources = [p for p in self.imposition_source_files() if str(p) not in used]
        seen = {str(path) for path in sources}
        uploaded = [
            path for path in uploaded_candidates(self._imposition_insert_dir())
            if str(path) not in used and str(path) not in seen
        ]
        return sources + uploaded

    def _resolve_chosen(self, items: list[dict]) -> list[Path]:
        """弹窗给的候选 → 可用文件路径（上传的图先复制进任务目录）。

        失败原因**逐条写进日志**（不弹一长串弹窗）：一张图读不到不该让整次
        插入报废，但用户必须知道少了一张。
        """
        from desktop.services.imposition_insert import resolve_chosen

        files, errors = resolve_chosen(items, self._imposition_insert_dir())
        for message in errors:
            self.log_view.append(f"插入图片：{message}")
        return files

    def _on_imposition_add_requested(self) -> None:
        """点「＋ 选择拼版」：弹窗自由多选，点「开始拼版」按每两张一页配对。"""
        if not self.task_id:
            return
        from desktop.components.imposition.picker import ImpositionPickerDialog

        doc = self._imposition_doc()
        pool = self._imposition_candidate_pool(doc)
        if not pool:
            # 一张候选都没有：**仍然打开弹窗**——用户可以直接上传自己的图
            # （用户 2026-11-16），只是先说清"为什么列表是空的"。
            self._toast(
                "info", "没有未使用的图片",
                "上一步还没有可用的成品图，或者所有图片都已被拼版使用；"
                "可以在弹窗里「上传图片」自己加图。",
            )
        dialog = ImpositionPickerDialog(
            pool, self.window(),
            # 候选图走**预生成小图**（上一节点成品小图 / 入口图片小图），
            # 不再每张整幅解码源图（用户 2026-10-17）
            thumb_provider=self._imposition_picker_thumb,
        )
        if not dialog.exec():
            return
        # 「从这张图片开始自动拼版」：只勾 1 张 + 勾了复选框 → 从那张起把
        # 剩余候选按规则自动拼完（整幅单独一页；前一个左半幅 + 当前右半幅
        # 配对；落单单页）。规则唯一实现在 services.imposition.auto_impose_pages。
        auto_file = dialog.auto_mode_file()
        auto_log: str | None = None
        if auto_file is not None:
            # 提交计划里的产物角色（``boxes.json``）：单栏书 / 窄页产出的
            # 无后缀半幅靠它才能与相邻页配对（用户 2026-10-23）。
            roles = self.imposition_role_map()
            new_pages = auto_impose_pages(
                dialog.auto_sequence(),
                role_for=lambda text: roles.get(Path(str(text)).stem),
            )
            if new_pages:
                auto_log = (
                    f"已从「{auto_file.stem}」起自动拼版：新增 {len(new_pages)} 页"
                    "（半幅按「前一左＋后一右」且页号连续配对；"
                    "无后缀半幅按两张连续页配对；整幅与落单图各自单独一页）。"
                )
        else:
            # 手动勾选（用户 2026-09-30 定的三种形态）：**1 张 → 单独一页**；
            # 2 张 → 拼成一页（序号在前的排右侧）。弹窗里勾 0/≥3 张时
            # 「开始拼版」不可点，这里只做兜底。
            #
            # ⚠️ 用户 2026-11-16：「同一张图片可以多次上传」——所以勾选结果里
            # 可能含**本次上传**的图，必须先把它们复制进任务目录再成页
            # （见 _resolve_chosen）；`batch` 是复制后的**最终路径**。
            new_pages, batch = self._pages_from_chosen(_chosen_items(dialog))
            if not batch:
                return
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

    def _pages_from_chosen(self, items: list[dict]) -> tuple[list[dict], list[Path]]:
        """弹窗勾选结果 → 拼版页（上传的图先复制进任务目录）。

        返回 ``(页列表, 复制后可用的文件列表)``：文件列表按**候选顺序**给出，
        调用方用它写日志（"从哪张开始每两张一页""哪张落单"）。
        """
        from desktop.services.imposition_insert import pages_from_candidates

        files = self._resolve_chosen(items)
        if not files:
            return [], []
        pages, failed = pages_from_candidates(files)
        if failed:
            self.log_view.append(
                f"有 {len(failed)} 张图片读不到尺寸，未参与拼版："
                + "、".join(failed) + "（文件可能已被移动或删除）。"
            )
        return pages, files

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
        pool = self._imposition_candidate_pool(doc)
        if not pool:
            # 一张候选都没有：仍开弹窗，用户可以直接上传自己的图（2026-11-16）
            self._toast(
                "info", "没有未使用的图片",
                "上一步还没有可用的成品图，或者所有图片都已被拼版使用；"
                "可以在弹窗里「上传图片」自己加图。",
            )
        dialog = ImpositionPickerDialog(
            pool, self.window(), mode="append",
            thumb_provider=self._imposition_picker_thumb,
        )
        if not dialog.exec():
            return
        picked = self._resolve_chosen(_chosen_items(dialog))
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

    def _on_imposition_page_move(self, index: int, delta: int) -> None:
        """左列右键「上移 / 下移」：把第 ``index`` 页挪一位（``delta`` = ±1）。

        与拖动排序（:meth:`_on_imposition_page_reorder`）落到同一份文档：都是
        "先改顺序再 ``_save_imposition_pages``"。``✕``/批量删除不同——那两个
        会**释放图片**回候选池，挪位只是换顺序，图片引用一个不动。

        越界不动（首行上移 / 末行下移）：右键菜单里已经置灰，这里再兜一次。
        """
        pages = self._imposition_pages()
        target = index + delta
        if not (0 <= index < len(pages) and 0 <= target < len(pages)):
            return
        page = pages.pop(index)
        pages.insert(target, page)
        self._save_imposition_pages(pages)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(target)
        self._update_imposition_status(target)

    def _on_imposition_page_insert(self, index: int, position: str) -> None:
        """左列右键「向前 / 向后插入拼版」：选图后把新页插到该页前/后。

        用户 2026-11-16：弹窗与「＋ 选择拼版」**同一个**（选择拼版 / 删除恢复
        两个页签 + 自己上传），只是多一行落点单选、并默认按右键那一项落位。
        与「＋ 选择拼版」的差别只在**插到哪儿**：那个追加到末尾，这个插中间。
        """
        if not self.task_id:
            return
        from desktop.components.imposition.picker import ImpositionPickerDialog

        doc = self._imposition_doc()
        pages = self._imposition_pages(doc)
        if not 0 <= index < len(pages):
            return
        pool = self._imposition_candidate_pool(doc)
        if not pool:
            # 一张候选都没有：仍开弹窗，用户可以直接上传自己的图（2026-11-16）
            self._toast(
                "info", "没有未使用的图片",
                "上一步还没有可用的成品图，或者所有图片都已被拼版使用；"
                "可以在弹窗里「上传图片」自己加图。",
            )
        dialog = ImpositionPickerDialog(
            pool, self.window(), mode="insert",
            thumb_provider=self._imposition_picker_thumb,
            position=position, current_row=index, total=len(pages),
        )
        if not dialog.exec():
            return
        new_pages, _batch = self._pages_from_chosen(_chosen_items(dialog))
        if not new_pages:
            self._toast(
                "error", "插入失败",
                "选中的图片无法读取尺寸，请换一张或换两张。",
            )
            return
        before = dialog.position() == "before"
        at = index if before else index + 1
        from desktop.services.imposition_insert import insert_pages_at

        merged = insert_pages_at(pages, new_pages, at)
        self._save_imposition_pages(merged)
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.set_current(at)
        self._update_imposition_status(at)
        listing = "、".join(
            " · ".join(page_source_stems(page)) for page in new_pages
        )
        self.log_view.append(
            f"已在第 {index + 1} 页{'之前' if before else '之后'}插入"
            f" {len(new_pages)} 页拼版：{listing}。"
        )

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
    def _imposition_thumb_window(self) -> tuple[int, int] | None:
        """左列**当前可见**的页号闭区间（缩略图只给这几页生成实体）。

        取不到（视图还没建/还没布局）返回 ``None`` ⇒ 管理者退化成"不筛"。
        """
        view = getattr(self, "imposition_view", None)
        if view is None:
            return None
        return view.visible_page_range()

    def _on_imposition_viewport_changed(self) -> None:
        """左列滚动/翻页/换任务：把新进窗口的页排进缩略图生成队列。

        ⚠️ 生成期间**不抢**（``refresh_window`` 在飞时直接返回）：那一批跑完
        的收尾回调会按**那一刻**的窗口再补一批，正好接上用户滚到的位置。
        """
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is not None:
            manager.refresh_window()

    def _imposition_page_thumb_manager(self):
        """页面缩略图**实体**的管理者（懒建；换任务自动换目录重读映射）。"""
        from desktop.components.imposition.page_thumb import PageThumbManager
        from desktop.utils.files import THUMBNAIL_EDGE

        if not self.task_id:
            return None
        # ⚠️ 目录按**当前拼版节点**取（B 方案）：两个「图片拼版」节点各有各的
        #    版面文档与合成产物，页面效果缩略图实体也跟着分
        #    （``thumbnails/imposition_pages[~<节点>]``），否则副本节点会读到主
        #    节点的实体（用户在另一节点改动版面，这一节点左列却显示旧图）。
        target = self.store.imposition_page_thumbs_dir(
            self.task_id, self.node_of_stage("imposition")
        )
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is None:
            manager = PageThumbManager(
                target, THUMBNAIL_EDGE, self.run_worker, parent=self,
                # 只生成左列**看得见**的那几页（用户 2026-11-21：拼版首屏
                # 在生产环境要等 5 分钟——整本 81 页一次性排进去，还要跟整本
                # 成品合成抢同一个进程）
                window_provider=self._imposition_thumb_window,
            )
            manager.page_ready.connect(self._on_imposition_page_thumb_ready)
            self._page_thumb_mgr = manager
        elif manager.directory != target:
            manager.bind(target)
        manager.set_window_provider(self._imposition_thumb_window)
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
