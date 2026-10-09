# -*- coding: utf-8 -*-
"""宿主侧混入 ``ZoomPopupMixin``：双击/右键开预览弹窗与「预览 / 编辑」菜单。

从 ``image_zoom_dialog.py`` 拆出（2026-10-07）。方法体逐字未改。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QCursor, QImage
from PySide6.QtWidgets import QDialog, QWidget

from .canvas import ZoomTarget
from .dialog import ImageZoomDialog
from .io import overwrite_image_file

class ZoomPopupMixin:
    """宿主侧混入：双击/右键大图打开图片预览弹窗与「预览 / 编辑」菜单。

    子类需要实现 :meth:`_zoom_target` 与 :meth:`_zoom_index`，并在
    ``__init__`` 里调 :meth:`_init_zoom_popup`。
    """

    if TYPE_CHECKING:
        # 宿主是 QWidget 子类（QWidget + 本 Mixin 混入）：window() 由 QWidget
        # 提供，这里只做类型侧声明，运行时零副作用。
        def window(self) -> QWidget: ...

    #: 弹窗实例（懒建）。类属性给个 None 兜底：子类可能在 _init_zoom_popup
    #: 之前（如构造中途换数据）就调到 close_zoom_popup。
    _zoom_dialog: "ImageZoomDialog | None" = None
    #: 本宿主的图**允许编辑**（对外接口参数，2026-10-09 用户：图片去底色
    #: 阶段只许预览不许编辑）。类属性 True 兜底：子类还没调
    #: ``_init_zoom_popup`` 就读它也不炸；默认可编辑，其余宿主零改动。
    _zoom_editable: bool = True

    def _init_zoom_popup(self, view, editable: bool = True) -> None:
        """把 ``view``（``ImageView``）的双击/右键接到弹窗与菜单上。

        ``editable=False``：本宿主的图**只许预览、不许编辑**——右键菜单不给
        「编辑图片」、预览弹窗不给「编辑」按钮、:meth:`edit_current_image`
        直接拒绝（图片去底色阶段，2026-10-09 用户）。
        """
        self._zoom_editable = bool(editable)
        self._zoom_dialog = None
        view.double_clicked.connect(self._open_zoom_popup)
        view.context_menu_requested.connect(self._open_zoom_menu)

    def set_image_editable(self, editable: bool) -> None:
        """运行期改「是否可以编辑图片」：菜单项与弹窗按钮随之同步。

        弹窗已建的就地更新；还没建也不要紧——:meth:`_open_zoom_popup`
        每次打开都会按当前开关校准一次。
        """
        self._zoom_editable = bool(editable)
        if self._zoom_dialog is not None:
            self._zoom_dialog.set_editable(self._zoom_editable)

    def _open_zoom_popup(self) -> None:
        """打开弹窗；没有可预览的页时静默返回。"""
        index = self._zoom_index()
        if self._zoom_target(index) is None:
            return
        if self._zoom_dialog is None:
            self._zoom_dialog = ImageZoomDialog(
                self.window() or self, factory=self._zoom_target,
                editable=self._zoom_editable,
            )
            dialog = self._zoom_dialog
            # 编辑器覆盖了原图：宿主要同步尺寸/缩略图/大图（默认空实现，
            # 有真实文件的宿主各自覆写）
            dialog.image_saved.connect(self._on_zoom_image_saved)
        dialog = self._zoom_dialog
        # 每次打开都校准一次编辑开关：宿主中途 set_image_editable 过的话，
        # 早已建好的弹窗也得跟上
        dialog.set_editable(self._zoom_editable)
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(index=index)

    def close_zoom_popup(self) -> None:
        """内容被换掉时关掉弹窗（弹窗里那页是打开时的快照，留着就是旧数据）。"""
        if self._zoom_dialog is not None:
            self._zoom_dialog.close()

    # ------------------------------------------------------ 右键「预览 / 编辑」
    def _open_zoom_menu(self) -> None:
        """预览区右键菜单：**预览图片 / 编辑图片**（各步骤预览区统一）。

        - 「预览图片」与双击同一条路（打开图片预览弹窗）；
        - 「编辑图片」**不经预览弹窗**直达编辑器，编辑当前图对应的真实文件
          并覆盖回写（见 :meth:`edit_current_image`）。没有可回写的真实文件
          （PDF 矢量页）时不提供这一项。

        没有可预览/可编辑的图时静默返回（不弹空菜单）。
        """
        target = self._zoom_target(self._zoom_index())
        if target is None:
            return
        from qfluentwidgets import Action, RoundMenu

        menu = RoundMenu(parent=self if isinstance(self, QWidget) else None)
        for text, icon, slot in self._zoom_menu_items(target):
            action = Action(icon, text, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        menu.exec(QCursor.pos())

    def _zoom_menu_items(self, target) -> list:
        """右键菜单项 ``[(文案, 图标, 槽)]``：有可回写文件才给「编辑…」。

        编辑文案由 ``ZoomTarget.edit_label`` 决定（默认「编辑图片」；拼版
        传「编辑单图」/「编辑整图」，与拼版画布的右键菜单一致——2026-10-07
        用户定）。抽成方法是为了可测——``_open_zoom_menu`` 要 ``exec`` 模态，
        离屏测不了；这里只算"该有哪些项"，与弹菜单解耦。
        """
        from qfluentwidgets import FluentIcon as FIF

        items: list[tuple] = [("预览图片", FIF.PHOTO, self._open_zoom_popup)]
        # 「编辑图片」三重把关：有可回写文件 **且** 宿主开了编辑开关
        # （image_editable=False 的宿主——去底色阶段——只给预览）。
        if (
            target is not None
            and target.edit_path is not None
            and getattr(self, "_zoom_editable", True)
        ):
            items.append((target.edit_label, FIF.EDIT, self.edit_current_image))
        return items

    def edit_current_image(self) -> bool:
        """右键「编辑图片」：直接编辑当前显示图对应的**真实文件**并覆盖回写。

        用户原则（2026-10-01）：图片编辑不是"本步骤看看"，各步骤改动要串成
        一条链、最终落到 PDF。目标由 ``ZoomTarget.edit_path`` 决定——

        - 显示的是**处理前**的图（如第三步「原图」）→ 改该源图文件；
        - 显示的是**处理后**的图（如第三步「去底色结果」、第四步待打印图）
          → 改该结果文件（本步产出，下一步读的就是它）。

        编辑器「完成」后：原子覆盖该文件 → ``_on_zoom_image_saved`` 通知宿主
        刷新（尺寸 / 缩略图 / 各处大图）。返回是否真的写回了文件。
        """
        if not getattr(self, "_zoom_editable", True):
            return False  # 本宿主不许编辑（去底色阶段），菜单层已不给入口
        from desktop.components.viewers.image_editor import ImageEditorDialog

        target = self._zoom_target(self._zoom_index())
        if target is None or target.edit_path is None:
            return False
        path = target.edit_path
        image = QImage(str(path))
        if image.isNull():
            self._notify_edit("warning", "无法编辑", f"读不到原图：{path.name}")
            return False
        parent = self.window() if isinstance(self, QWidget) else None
        editor = ImageEditorDialog(parent, image, save_back=True)
        editor.target_name = path.name
        if editor.exec() != QDialog.DialogCode.Accepted:
            return False
        edited = editor.result_image()
        if edited is None or edited.isNull():
            return False
        if not overwrite_image_file(edited, path):
            self._notify_edit("error", "保存失败", f"编辑未生效：{path.name}")
            return False
        self._on_zoom_image_saved(str(path), edited)
        return True

    def _notify_edit(self, kind: str, title: str, content: str) -> None:
        """编辑失败的提示（InfoBar）。没有可用的宿主窗口时静默。"""
        parent = self.window() if isinstance(self, QWidget) else None
        if parent is None:
            return
        from qfluentwidgets import InfoBar, InfoBarPosition

        factory = getattr(InfoBar, kind, InfoBar.info)
        factory(
            title=title,
            content=content,
            parent=parent,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=3000,
        )

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """编辑器覆盖原图后的宿主钩子 ``image_saved(path, edited)``。

        默认什么都不做：没有真实文件的宿主（PDF 预览）永远收不到；有
        回写路径的宿主覆写本方法去立即同步大图/条目图标并登记尺寸。
        """

    # ---- 子类实现 ----
    def _zoom_index(self) -> int:
        """当前选中页下标（0 基）。"""
        raise NotImplementedError

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """第 index 页的数据来源；不可预览时返回 None。"""
        raise NotImplementedError
