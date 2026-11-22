# -*- coding: utf-8 -*-
"""模块一「选择拼版」的**弹窗选图**分片：候选池、上传解析、加页/新增图片。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.pages.taskdetail.imposition_pages.helpers import _chosen_items
from desktop.services.imposition import (
    ITEMS_PER_PAGE, append_item_to_page, auto_impose_pages, cn_page_label,
    used_source_files,
)

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition_pages._host import (
        ImpositionPagesHost,
    )
else:
    ImpositionPagesHost = object


class PickerMixin(ImpositionPagesHost):
    """「选择拼版 / 新增图片」弹窗：候选图、上传复制与成页。"""

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
