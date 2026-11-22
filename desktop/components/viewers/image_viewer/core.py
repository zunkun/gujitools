# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``ImageViewerWidget``：**装配点 + 基座 + 展示主路径**。

从 ``image_viewer.py`` 拆出（2026-10-07），2026-11-22 又按职责把「清单装填 /
缩略图 / 选页加载」拆到 ``listing.py``（ListingMixin）、把「大图上屏 / 刷新 /
尺寸文案」拆到 ``display.py``（DisplayMixin）。本文件放类头（信号/类属性）、
``__init__``、宿主协议（``_zoom_*``）与少量与清单无关的开关。方法体逐字未改。

⚠️ 宿主协议三个方法留在本类，才能盖住 ``ZoomPopupMixin`` 的默认实现。
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon as FIF, ToolButton
from desktop.ui.widgets import mark_input_entry
from desktop.workers import PreviewWorker
from desktop.components.viewers.image_view import ImageView
from desktop.components.viewers.hint_banner import HintBanner
from desktop.components.viewers.image_zoom_dialog import ZoomPopupMixin, ZoomTarget
from desktop.components.viewers.thumb_strip import ThumbStrip
from desktop.components.viewers.thumbs_loader import ThumbsMixin

from .boxes import BoxesMixin
from .display import DisplayMixin
from .listing import ListingMixin
from .pdf import PdfSourceMixin
from .thumbs import ThumbsCacheMixin


class ImageViewerWidget(
    ThumbsCacheMixin,
    PdfSourceMixin,
    BoxesMixin,
    ListingMixin,
    DisplayMixin,
    QWidget,
    ThumbsMixin,
    ZoomPopupMixin,
):
    """图片查看器：缩略图条 + 大图，支持切割框叠加、拖动与页面增删按钮。"""

    current_changed = Signal(int, str)
    delete_requested = Signal()
    insert_requested = Signal()
    #: 「选文件夹」按钮：宿主弹**目录**选择框，把一个文件夹批量插进来
    #: （用户 2026-10-06）。⚠️ 与 :attr:`insert_requested` 分开是因为
    #: ``QFileDialog`` 选不了目录，两者是不同的对话框、不同的语义。
    insert_folder_requested = Signal()
    boxes_edited = Signal(str, list)  # (图片路径, 全部框坐标) 拖动结束后发出
    #: 选中框变化（-1 = 无选中）：宿主据此同步「选中框类型」控件
    selection_changed = Signal(int)
    #: 编辑被拒绝（超框数上限等）：宿主弹提示
    box_edit_rejected = Signal(str)
    #: 手绘的框太小、没有生效：宿主弹「画框太小」提示（与上面那条分开，
    #: 标题不同；见 ``image_view.core.ImageView.box_too_small``）
    box_too_small = Signal(str)
    #: 编辑器在放大弹窗里覆盖了某张页面图 ``image_saved(path, edited)``：
    #: 宿主据此同步 sizes.json、重生成缩略图并刷新各处显示
    image_saved = Signal(str, object)

    def __init__(
        self,
        editable: bool = False,
        show_boxes: bool = False,
        empty_hint: str = "暂无图片",
        image_size_provider=None,
        thumb_provider=None,
        image_editable: bool = True,
        parent=None,
    ):
        """
        构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。

        image_size_provider 供大图降采样时还原原始像素尺寸；thumb_provider
        让缩略图条改用预生成小图，避免反复解码原图。

        ⚠️ ``editable`` 与 ``image_editable`` 是**两件事**：前者管**页面清单**
        （增删/插入按钮，提取页等只读宿主传 False），后者管**图片内容**
        （右键「编辑图片」+ 预览弹窗「编辑」按钮，2026-10-09 新增接口；
        去底色阶段的 ``RembgPreviewWidget`` 传 False，只许预览）。
        """
        super().__init__(parent)
        self._init_thumbs()
        # ⚠️ 元素类型是 ``Path | str``（set_images 的入参就是两者都收，调用方
        # 有时给 Path、有时给字符串路径），不是 list[Path]：list 不协变，写成
        # list[Path] 会让每一处 list(paths) 赋值都变成类型错误。
        self._paths: list[Path | str] = []
        self._empty_hint = empty_hint
        #: PDF 页模式：``(pdf 路径, 代际号)``。非 None 时左栏是「页缩略图条」，
        #: 大图按需从 PDF 渲那一页——而不是拿 256px 缓存小图放大（会糊）。
        #: 见 :meth:`set_pdf_source`。
        self._page_source: tuple[Path, int] | None = None
        #: PDF 页模式下的页缩略图缓存目录（``None`` = 不落盘缓存）。
        #: 供宿主/自测核对"缩略图真的落在 singletask 下"。
        self._page_source_cache: Path | None = None
        #: 缩略图缓存接线（:meth:`set_thumb_source` 装上）：目录、边长，
        #: 以及「真实图片路径 → 已就绪的缓存小图」。
        self._thumb_cache_dir: Path | None = None
        self._thumb_cache_edge: int | None = None
        self._thumb_cache_ready: dict[str, Path] = {}
        self._thumb_cache_lookup = None
        #: 每条清单对应的**显式**缓存文件名（extract 的序号口径用；None 项
        #: 回落到图键命名）。与 :attr:`_paths` 同序，长度不一致时按越界回落。
        self._thumb_cache_names: list[str | None] | None = None
        # 原始尺寸提供者：(path_text) -> QSize | None。
        # 预览加载的大图可能被降采样，框坐标以原始尺寸为坐标系基准。
        self._image_size_provider = image_size_provider
        #: 缩略图提供者：(path_text) -> Path | None。返回预生成的小图路径，
        # 避免左侧缩略图条反复解码原始分辨率大图；返回 None/原路径则解码真图。
        self._thumb_provider = thumb_provider
        #: 「大图按参数合成」的提供者：(path_text, index, total) -> dict | None。
        #: 目前只有独立「PDF排版」页用（打印效果，见
        #: :meth:`set_preview_spec_provider`）。缩略图条**不**套用它。
        self._preview_spec_provider = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        left = QVBoxLayout()
        self.strip = ThumbStrip()
        self.strip.current_path_changed.connect(self._select_image)
        left.addWidget(self.strip, 1)
        if editable:
            buttons = QHBoxLayout()
            delete_btn = ToolButton(FIF.DELETE)
            delete_btn.setToolTip("从页面清单删除所选图片")
            delete_btn.clicked.connect(self.delete_requested.emit)
            insert_btn = ToolButton(FIF.ADD)
            insert_btn.setToolTip("插入图片（可多选）")
            insert_btn.clicked.connect(self.insert_requested.emit)
            # ⚠️ **「选文件夹」是独立按钮，不靠文件对话框顺带选目录**（用户
            #    2026-10-06："是否可以选择目录"）。Qt 的 ``getOpenFileNames``
            #    **不能**选目录（原生 Windows 对话框只接受文件），所以"把整个
            #    扫描结果文件夹丢进来"这个最自然的批量用法**必须**有单独入口——
            #    指望用户在文件对话框里选中文件夹是不成立的。
            folder_btn = ToolButton(FIF.FOLDER)
            folder_btn.setToolTip("把一个文件夹里的图片批量插入")
            folder_btn.clicked.connect(self.insert_folder_requested.emit)
            buttons.addWidget(delete_btn)
            buttons.addWidget(insert_btn)
            buttons.addWidget(folder_btn)
            # ⚠️ ＋与📁 加**常驻红框**（用户 2026-10-06"左下角输入图片和目录
            #    也用红色框住"）：它们是"给这一步喂图片"的入口，自定义流程
            #    第一步不吃 PDF 时全靠它们。删除按钮**不标红**——删图不是入口。
            # ⚠️ 显隐归**宿主**：这些输入控件只属于流程的**入口**那一步
            #    （用户 2026-10-06 规则③"非第一个流程节点，不存在这些输入
            #    控件"），入口吃什么由宿主按 :func:`ports.flow_entry_input_kind`
            #    决定后调 :meth:`set_insert_visible`。组件构造时默认显示，
            #    免得宿主忘了调就一直没入口。
            self._insert_buttons = (insert_btn, folder_btn)
            for button in self._insert_buttons:
                mark_input_entry(button)
            buttons.addStretch()
            left.addLayout(buttons)
        layout.addLayout(left)
        right = QVBoxLayout()
        # 画布**顶部**的红框提示（用户 2026-11-12）：默认隐藏，谁需要谁给文案
        # （目前只有「检测文本框」：提示可以手绘框、改框类型）。藏着的控件在
        # 布局里不占位，所以其它步骤的预览区高度一点不变。
        self.hint_banner = HintBanner()
        right.addWidget(self.hint_banner)
        self.view = ImageView(empty_hint)
        right.addWidget(self.view, 1)
        self.info_label = CaptionLabel("")
        right.addWidget(self.info_label)
        layout.addLayout(right, 1)
        self.show_boxes = show_boxes
        self.view.set_boxes_editable(show_boxes)
        self.view.boxes_edited.connect(self._boxes_edited)
        # 选中态与"编辑被拒"直接转发给宿主（第二步面板据此高亮框类型/提示）
        self.view.selection_changed.connect(self.selection_changed.emit)
        self.view.edit_rejected.connect(self.box_edit_rejected.emit)
        self.view.box_too_small.connect(self.box_too_small.emit)
        # 双击大图 → 图片预览弹窗（只读查看；编辑仍在原画布上做）
        self._init_zoom_popup(self.view, editable=image_editable)
        self._pending_boxes: tuple | None = None  # (boxes, image_size, info, full)，等大图加载后应用
        #: 每次选页递增的加载令牌，只有最新一次选择的渲染结果允许上屏。
        #: ⚠️ 不能改用「路径是否相同」判断：同一页也会被重复选择（见
        #: ``_select_image`` 的递归回调），路径一样但加载任务有两个。
        self._load_token = 0
        #: 离开步骤时被 :meth:`release_buffers` 清过位图：回来第一次
        #: ``set_images`` 必须**重装图标并重载当前页**（清单没变也不许早退，
        #: 否则左列停在占位图、右侧停在空白）。
        self._buffers_released = False


    @property
    def paths(self) -> list[Path | str]:
        """当前页面清单（按显示顺序）。

        ⚠️ 元素是 ``Path | str``（与 :meth:`set_images` 的入参一致）：调用方
        两种都传，要拿名字/后缀时用 ``Path(x)`` 收一下。
        """
        return self._paths


    def current_path(self) -> Path | None:
        """当前选中的页面路径；无选中或无清单时为 None。

        返回 ``Path``：清单元素可能是 str，这里统一成 Path 交出去，调用方
        就直接 ``.name`` / ``.stem`` 了。
        """
        row = max(self.strip.currentRow(), 0)
        if row < len(self._paths):
            return Path(self._paths[row])
        return None


    def navigate(self, forward: bool) -> None:
        """方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。"""
        self.strip.navigate(forward)


    def set_insert_visible(self, visible: bool) -> None:
        """「＋/📁」两个**图片输入入口**的显隐（宿主按流程入口决定）。

        ⚠️ 只动这两个，**不碰**🗑：删图是清单管理，不是"喂图片"的入口，
        在哪一步都该有（详情页把它留在原地，见构造处的红框注释）。
        ``editable=False`` 的查看器没有这两个按钮，静默忽略。
        """
        for button in getattr(self, "_insert_buttons", ()):
            button.setVisible(visible)


    def set_empty_hint(self, hint: str) -> None:
        """换空态文案（输入入口藏起来后，"请点下方「＋」"就指错方向了）。

        当前正空着的话立刻把两处占位（缩略图条 + 大图）一起换掉；有图时
        只存着，等下次清空自然用新文案。⚠️ 占位要**清了重加**：
        ``add_placeholder`` 是追加语义，直接再调会叠出两条占位条目。
        """
        self._empty_hint = hint
        if self._paths:
            return
        self.strip.clear()
        self.strip.add_placeholder(hint)
        self.view.clear_image(hint)

    def set_hint_banner(self, text: str) -> None:
        """换画布顶部那条**红框提示**（空串＝收起）。

        只有「检测文本框」用它（用户 2026-11-12：提示用户可以在图上手动调整
        框类型与手绘框）。文案由业务层现算（``box_kinds.manual_hint_text``），
        控件只负责显示；用户点过 × 之后这里怎么调都不会再弹（见 HintBanner）。
        """
        banner = getattr(self, "hint_banner", None)
        if banner is not None:
            banner.set_hint(text)


    # -------------------------------------------------------------- 图片预览
    def _zoom_index(self) -> int:
        """放大弹窗当前页 = 缩略图条的当前行。"""
        return max(self.strip.currentRow(), 0)


    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 页的图片预览来源。

        ``cap`` 取原图原生边长：解码到超过原生尺寸只是白放大（还会白占内存），
        所以超过就按原生渲——此时 100% 恰好是"一个原生像素对一个屏幕像素"。

        ⚠️ **PDF 页模式**（图片提取页未提取时的形态）也要给得出目标：这时
        ``_paths`` 是空的、条目上写的是**页号**，走的必须是
        ``PreviewWorker(page=index)`` 那条渲页通道。不认这个形态的话，双击/
        右键在那一屏上**整个没反应**（连「预览图片」都没有），而任务流程里
        对应的「PDF 预览」标签页是能双击放大的——同一件事两处行为不一样。
        矢量页没有可回写的图片文件，所以这一支**不给** ``edit_path``。
        """
        if self._page_source is not None:
            pdf = self._page_source[0]
            total = self.strip.count()
            if not (0 <= index < total):
                return None
            return ZoomTarget(
                render=lambda edge: PreviewWorker(pdf, page=index, longest_edge=edge),
                note=f"第 {index + 1}/{total} 页 · {pdf.name}",
                stem=f"{pdf.stem}-{index + 1:04d}",
                count=total,
            )
        if not (0 <= index < len(self._paths)):
            return None
        path = self._paths[index]
        original = self._original_size(str(path))
        cap = max(original.width(), original.height()) if original else None
        return ZoomTarget(
            render=lambda edge: PreviewWorker(path, longest_edge=edge),
            note=f"第 {index + 1}/{len(self._paths)} 页 · {Path(path).name}",
            stem=Path(path).stem,
            count=len(self._paths),
            original=original,
            cap=cap,
            # 页面图就是磁盘上的真实文件：编辑器「完成」= 覆盖它
            save_path=path,
            # 编辑目标 = 这张页面图本身（第一步产出，第二步检测读的就是它）
            edit_path=path,
        )


    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """弹窗里覆盖了页面图：转发给宿主（同步 sizes.json/缩略图）。"""
        self.image_saved.emit(path_text, image)
