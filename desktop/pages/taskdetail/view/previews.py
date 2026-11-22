# -*- coding: utf-8 -*-
"""左侧预览栈与拼版预览的组装（从原 ``view.py`` 拆出）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.components.imposition import ImpositionViewWidget
from desktop.components.viewers import (
    ExtractPreviewWidget,
    ImageViewerWidget,
    PrintPreviewWidget,
    RembgPreviewWidget,
)
from desktop.ui import theme as T
from desktop.ui.widgets import Card

from desktop.pages.taskdetail.view._qt import QStackedWidget

if TYPE_CHECKING:
    from desktop.pages.taskdetail.view._host import DetailViewHost
else:
    DetailViewHost = object


class DetailPreviewMixin(DetailViewHost):
    """四步预览控件与拼版伪步骤的画布。"""
    def _build_preview_card(self) -> Card:
        card = Card(padding=T.SPACE_SM, spacing=0, radius=T.RADIUS_MD)
        card.box.addWidget(self._build_preview_stack())
        return card

    def _wrap_with_input_list(self, stage_viewer):
        """把某一步的预览包成 ``[正常查看器 | 只读图片清单]`` 的两页宿主。

        **只读图片清单**是给"聚合任务的提取起点"用的（用户 2026-11-18，任务
        0025）：提取起点没有输入源可看（成员的源 PDF 不搬），屏上要显示的就
        是子任务汇集来的提取产物本身——硬用 PDF 查看器只会显示"暂无图片"。
        （检测起点用 detect_viewer、去底色起点用原图/成品对比查看器——它们的
        输入与产出都已汇集进来，2026-11-18 晚口径。）

        为什么包两层而不是直接加一页到 ``preview_stack``：外层栈的页号与步骤
        一一对应（``stack_index_of`` / ``stage_at_stack_index`` 全靠它），
        多一页就会把这些下标算错；内层宿主不影响任何页号映射。

        返回 ``(宿主, 清单控件)``；宿主自己 :meth:`QStackedWidget.addWidget` 到
        外层栈。
        """
        listing = ImageViewerWidget(
            editable=False,
            show_boxes=False,
            image_editable=False,
            empty_hint="暂无图片（子任务汇集完成后会出现在这里）",
            image_size_provider=self._original_image_size,
            thumb_provider=self._page_thumb_for,
        )
        host = QStackedWidget()
        host.addWidget(stage_viewer)
        host.addWidget(listing)
        return host, listing

    def _build_preview_stack(self) -> QStackedWidget:
        self.preview_stack = QStackedWidget()
        # extract：**单缩略图**预览（用户 2026-10-09：不再分「PDF 预览 |
        # 提取结果」双标签——那是一本书两份清单）。左栏是 PDF 每页一份
        # 缩略图；切到某页时该页的提取产物已存在就显示产物，没有就后台
        # 单页提取落盘（stages/extract）后显示。产物目录与参数由宿主注入。
        self.extract_result_viewer = ExtractPreviewWidget("尚未导入 PDF")
        self.extract_result_viewer.page_count_changed.connect(
            self._pdf_page_count_ready
        )
        # 单页提取落盘完成 → 宿主登记 sizes.json / 重建页面清单
        self.extract_result_viewer.extract_saved.connect(self._on_single_extract_saved)
        # 右键「编辑图片」覆盖了产物文件 → 与旧 ImageViewerWidget 同形接线
        self.extract_result_viewer.image_saved.connect(self._on_page_image_saved)
        # 单页提取参数跟「图片提取」面板的当前表单走（与批量提取一致）
        self.extract_result_viewer.set_params_provider(self._extract_params)
        self.extract_viewer_host, self.extract_input_viewer = (
            self._wrap_with_input_list(self.extract_result_viewer)
        )
        self.preview_stack.addWidget(self.extract_viewer_host)

        # detect：图片 + 检测框
        # ⚠️ 空态文案**不写死"请先完成提取"**（用户2026-10-06）：自定义流程
        #    可能把这一步放在第一位、压根没有提取这一步可完成，那时这句话
        #    会把用户引到一个不存在的目标上。统一说"插入图片/文件夹"，
        #    对有无上游都成立。
        self.detect_viewer = ImageViewerWidget(
            editable=True,
            show_boxes=True,
            empty_hint="暂无图片，请点下方「＋」插入图片或整个文件夹，"
            "或把图片放进本任务的输入目录",
            image_size_provider=self._original_image_size,
            thumb_provider=self._page_thumb_for,
        )
        self.detect_viewer.current_changed.connect(self._detect_image_selected)
        self.detect_viewer.delete_requested.connect(self.delete_selected_page)
        self.detect_viewer.insert_requested.connect(self.insert_pages)
        self.detect_viewer.insert_folder_requested.connect(
            self.insert_pages_from_folder
        )
        self.detect_viewer.boxes_edited.connect(self._save_manual_boxes)
        # 编辑器「完成」覆盖原图后：同步 sizes.json/缩略图并刷新显示
        self.detect_viewer.image_saved.connect(self._on_page_image_saved)
        self.preview_stack.addWidget(self.detect_viewer)

        # rembg：原图/结果对比
        # ⚠️ image_editable=False（2026-10-09 用户）：去底色阶段**只许预览、
        #    不许编辑**——右键不给「编辑图片」、弹窗不给「编辑」按钮。
        # ⚠️ 2026-11-18 晚口径：去底色做聚合起点时，输入（成员裁图）与产出
        #    （成员成品）都已汇集进来 ⇒ 对比查看器就是这一步的如实回放，
        #    不再包「只读图片清单」（那是"起点没有输入"年代的兜底）。
        self.rembg_viewer = RembgPreviewWidget(image_editable=False)
        self.rembg_viewer.image_saved.connect(self._on_page_image_saved)
        self.rembg_viewer_host = QStackedWidget()
        self.rembg_viewer_host.addWidget(self.rembg_viewer)
        self.preview_stack.addWidget(self.rembg_viewer_host)

        # print：左缩略图条 + 右「打印效果」预览（可拖动排序/删除/插入）
        # ⚠️ params_provider 必须传：缺了它预览永远显示"未接入打印参数，已显示原图"，
        # 标题/页码/纸张效果一概看不到（组件自测传了参数，测不出宿主漏接线）。
        self._print_dirty = False  # 版面编辑器改过坐标、尚未重新生成 PDF
        #: 已生成的 PDF 是否已因**取图来源换掉**（拼版开关）而作废。缓存，
        #: 由 ``_refresh_stale_notices`` 重算（见 page.py）——状态行经
        #: ``_regenerate_notice`` 在执行期间每 ≤200ms 读它，不能现算。
        self._print_source_stale = False
        #: 已生成的 PDF 是否已因**取图目录内容变化**（拼版成品重存 / 去底色成品
        #: 被实时改写）而作废。缓存，同 `_print_source_stale` 一起由
        #: ``_refresh_stale_notices`` 重算（见 page.py）。
        self._print_data_stale = False
        self.print_preview = PrintPreviewWidget(
            empty_hint="暂无图片，请先在第三步「图片去底色」生成成品图",
            params_provider=self._print_params,
            # 提交阶段预生成的缩略图（thumbnails/print）：不再对每条目现解码
            # 6000px 原图（2026-09-27 用户反馈第四步缩略图渲染慢）
            thumb_provider=self._print_thumb_provider,
        )
        self.print_preview.order_changed.connect(self._save_print_order)
        self.print_preview.manage_requested.connect(self._manage_print_images)
        # 右键「向前 / 向后插入」：直接开插入弹窗，只是默认落点不同
        self.print_preview.insert_before_requested.connect(
            lambda: self._insert_print_images("before")
        )
        self.print_preview.insert_after_requested.connect(
            lambda: self._insert_print_images("after")
        )
        # 「下载 PDF」不归预览控件自己弹按钮：宿主右下方控制面板按 PDF 可用
        # 状态显示/隐藏（用户 2026-11-01，见 _sync_download_print_button）
        self.print_preview.pdf_state_changed.connect(self._sync_download_print_button)
        # 编辑器覆盖了某张待打印图：记日志提示「点生成 PDF 即生效」
        self.print_preview.image_saved.connect(self._on_page_image_saved)
        # 单页导出：当前页排进 A4 后的效果图（精度与 PDF 同级 300dpi）
        self.print_preview.export_image_requested.connect(self._export_print_image)
        self.print_preview.export_finished.connect(self._on_export_finished)
        self.print_preview.export_failed.connect(self._on_export_failed)
        # 单页打印：同一份 A4 效果渲染，交系统打印对话框
        self.print_preview.print_finished.connect(self._on_print_finished)
        self.print_preview.print_failed.connect(self._on_print_failed)
        # 版面编辑：某一页图片坐标被拖拽/缩放后落盘 print.json 并标脏
        self.print_preview.layout_changed.connect(self._on_print_layout_changed)
        self.print_preview.hint.connect(
            lambda message: self._toast("info", "提示", message)
        )
        self.preview_stack.addWidget(self.print_preview)

        # 拼版伪步骤（index 4）：左列拼版页 + 右侧拼版操作画布
        self.preview_stack.addWidget(self._build_imposition_preview())
        return self.preview_stack

    def _build_imposition_preview(self) -> Card:
        """「图片拼版」页面：左侧拼版页清单（模块一）+ 右侧操作画布（模块二）。

        左列是「第一页 / 第二页 / …」加末尾一个**虚线**「＋ 选择拼版」；
        右侧画布可拖动 / 缩放拉伸 / 旋转当前页的两张图。业务动作全部委托给
        拼版控制器（``imposition.py`` 基元 + ``imposition_pages`` /
        ``imposition_layout`` 两模块的 Mixin）。
        """
        card = Card(padding=T.SPACE_SM, spacing=0, radius=T.RADIUS_MD)
        self.imposition_view = ImpositionViewWidget()
        # 右键「定位图片资源」的目标 = **拼版成品**（不是画布上那张输入源图）：
        # 拼版会实时重合成产出新图，用户要定位的是这一步的产物（用户 2026-10-18）
        self.imposition_view.canvas.set_locate_resolver(self._imposition_locate_targets)
        self.imposition_view.page_selected.connect(self._on_imposition_page_selected)
        self.imposition_view.add_requested.connect(self._on_imposition_add_requested)
        self.imposition_view.page_reorder_requested.connect(
            self._on_imposition_page_reorder
        )
        # 左列右键：上移/下移、向前/向后插入拼版（用户 2026-11-16，照「PDF排版」
        # 左列那套菜单）
        self.imposition_view.page_move_requested.connect(self._on_imposition_page_move)
        self.imposition_view.page_insert_requested.connect(
            self._on_imposition_page_insert
        )
        self.imposition_view.page_remove_requested.connect(
            self._on_imposition_release_page
        )
        self.imposition_view.pages_batch_delete_requested.connect(
            self._on_imposition_batch_delete
        )
        self.imposition_view.items_changed.connect(self._on_imposition_items_changed)
        self.imposition_view.slot_selected.connect(self._on_imposition_slot_selected)
        self.imposition_view.item_preview_requested.connect(
            self._open_imposition_item_preview
        )
        self.imposition_view.spread_preview_requested.connect(
            self._open_imposition_spread_preview
        )
        self.imposition_view.item_edit_requested.connect(
            lambda _slot: self._open_imposition_spread_edit()
        )
        self.imposition_view.spread_edit_requested.connect(
            self._open_imposition_spread_edit
        )
        # 「定位图片资源」没定位成（源文件已不存在）：说清原因，别静默
        self.imposition_view.locate_failed.connect(
            lambda message: self._toast("warning", "定位图片资源", message)
        )
        # 左列滚到新的位置：按新窗口补生成缩略图（只生成看得见的那几页）
        self.imposition_view.viewport_changed.connect(
            self._on_imposition_viewport_changed
        )
        card.box.addWidget(self.imposition_view)
        return card
