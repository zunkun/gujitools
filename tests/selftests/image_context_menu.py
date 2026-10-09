# -*- coding: utf-8 -*-
"""图片预览区右键「查看 / 编辑」自测（2026-10-01 需求）。

用户原则：**图片编辑不是"本步骤看看"，各步骤改动要串成一条链、最终落到
PDF**。所以每个步骤的预览区都要能右键，且「编辑图片」改的是**当前显示图
对应的真实文件**——显示的是处理前的图就改源图，显示的是处理后的图就改该
结果文件（下一步读的就是它）。

断言线（都只看可观测行为，不看实现细节）：

1. ``ImageView`` 有图才发 ``context_menu_requested``，无图不发（不弹空菜单）；
2. 右键菜单项：有可回写文件 → 「预览图片 + 编辑图片」；PDF 矢量页这类没有
   → 只给「预览图片」（不给死按钮）；
3. ``edit_current_image`` 把编辑结果**原子覆盖到 edit_path** 指向的真实文件，
   并通知宿主 ``_on_zoom_image_saved``（刷新尺寸/缩略图/各处大图）；
4. ``ZoomTarget.edit_path`` 语义：显式给出时不回落 save_path；不给时回落
   save_path（1:1 显示的老用法不变）；
5. 各步骤查看器的编辑目标指向正确的真实文件：
   - 第一步/第二步（``ImageViewerWidget``）→ 页面图本身；
   - 第三步结果形态（``RembgPreviewWidget``）→ **去底色结果文件**（区域合成
     只是显示口径，save_path 为 None，但 edit_path 必须是结果文件）；
   - 第四步打印效果形态（``PrintPreviewWidget``）→ 待打印的条目图。
6. **编辑开关**（2026-10-09 用户：图片去底色阶段只许预览不许编辑）：
   ``image_editable=False`` 的宿主——右键菜单只给「预览图片」、
   ``edit_current_image`` 直接拒绝（不弹编辑器不写文件）、预览弹窗不渲染
   「编辑」按钮；``set_image_editable`` 运行期可重开；默认（不传参数）
   仍可编辑，其余宿主零改动。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

NAME = "image_context_menu"
DEPENDS: list[str] = []
TITLE = "图片预览右键查看/编辑"


def _make_image(width: int = 64, height: int = 48, color: str = "#ffffff"):
    from PySide6.QtGui import QColor, QImage

    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    return image


def _pixel_is(image, x: int, y: int, expected: str, tol: int = 40) -> bool:
    from PySide6.QtGui import QColor

    want = QColor(expected)
    got = image.pixelColor(x, y)
    return (
        abs(got.red() - want.red()) <= tol
        and abs(got.green() - want.green()) <= tol
        and abs(got.blue() - want.blue()) <= tol
    )


def _context_event():
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent

    return QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(5, 5)
    )


def _stub_editor(edited, accepted: bool = True):
    """替身编辑器工厂：edit_current_image 只依赖 exec() 与 result_image()。"""
    from PySide6.QtWidgets import QDialog

    class _Stub:
        def __init__(self, parent=None, image=None, save_back=False):
            self.save_back = save_back

        def exec(self):
            return (
                QDialog.DialogCode.Accepted if accepted
                else QDialog.DialogCode.Rejected
            )

        def result_image(self):
            return edited

    return _Stub


class _Host:
    """最小宿主：实现 ZoomPopupMixin 要求的两个钩子，记录 image_saved。"""


def run(ctx) -> None:
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QWidget

    from tests.selftests._context import ok, pump

    from desktop.components.viewers.image_view import ImageView
    from desktop.components.viewers.image_zoom_dialog import (
        ZoomPopupMixin, ZoomTarget,
    )

    app = ctx.app
    tmp = Path(tempfile.mkdtemp(prefix="guji_ctx_menu_"))
    try:
        # -------------------------------------------------- ImageView 右键信号
        view = ImageView()
        fired: list = []
        view.context_menu_requested.connect(lambda: fired.append(1))
        view.contextMenuEvent(_context_event())
        ok("无图时右键不发信号（不弹空菜单）", fired == [])
        view.set_image(_make_image())
        view.contextMenuEvent(_context_event())
        ok("有图时右键发出 context_menu_requested", fired == [1], str(fired))
        view.deleteLater()
        pump(app, times=1)

        # -------------------------------------------------- 菜单项组成
        class _MenuHost(QWidget, ZoomPopupMixin):
            def __init__(self, target):
                super().__init__()
                self._target = target

            def _zoom_index(self) -> int:
                return 0

            def _zoom_target(self, index: int):
                return self._target

        direct = ZoomTarget(render=lambda edge: None, edit_path=tmp / "a.png")
        host = _MenuHost(direct)
        texts = [item[0] for item in host._zoom_menu_items(direct)]
        ok("有可回写文件 → 菜单含「预览图片」+「编辑图片」",
           texts == ["预览图片", "编辑图片"], str(texts))
        virtual = ZoomTarget(render=lambda edge: None)  # 无 save/edit
        texts2 = [item[0] for item in host._zoom_menu_items(virtual)]
        ok("PDF 矢量页这类无文件 → 只给「预览图片」（不留死按钮）",
           texts2 == ["预览图片"], str(texts2))
        ok("无 target 时同样只给预览（防御）",
           [t[0] for t in host._zoom_menu_items(None)] == ["预览图片"])
        host.deleteLater()
        pump(app, times=1)

        # -------------------------------------------------- edit_path 语义
        fallback = ZoomTarget(render=lambda edge: None, save_path=tmp / "b.png")
        _fb_edit = fallback.edit_path
        assert _fb_edit is not None        # ⚠️ 给了 save_path 就会派生出 edit_path
        ok("不给 edit_path 时回落 save_path（1:1 老用法不变）",
           _fb_edit == fallback.save_path
           and _fb_edit.name == "b.png",
           str(_fb_edit))
        explicit = ZoomTarget(
            render=lambda edge: None, edit_path=tmp / "c.png"
        )
        _exp_edit = explicit.edit_path
        assert _exp_edit is not None
        ok("显式 edit_path 且无 save_path：派生显示也能编辑真实文件",
           explicit.save_path is None and _exp_edit.name == "c.png",
           f"save={explicit.save_path} edit={_exp_edit}")

        # -------------------------------------------------- 回写真实文件
        target = tmp / "page.png"
        ok("准备：原图可写出", _make_image().save(str(target), "PNG"))  # type: ignore[reportCallIssue]

        class _WriteHost(QWidget, ZoomPopupMixin):
            def __init__(self, tgt):
                super().__init__()
                self._target = tgt
                self.saved: list = []

            def _zoom_index(self) -> int:
                return 0

            def _zoom_target(self, index: int):
                return self._target

            def _on_zoom_image_saved(self, path_text, image=None) -> None:
                self.saved.append((path_text, image))

        write_host = _WriteHost(
            ZoomTarget(render=lambda edge: None, edit_path=target)
        )
        red = _make_image(color="#00aa00")

        import desktop.components.viewers.image_editor as editor_mod

        original_dialog = editor_mod.ImageEditorDialog
        editor_mod.ImageEditorDialog = _stub_editor(red)
        try:
            done = write_host.edit_current_image()
        finally:
            editor_mod.ImageEditorDialog = original_dialog

        ok("edit_current_image 返回 True（确实写回了）", done is True)
        ok("编辑结果覆盖到 edit_path 指向的真实文件",
           _pixel_is(QImage(str(target)), 2, 2, "#00aa00"))
        ok("通知宿主 _on_zoom_image_saved（路径 + 编辑图）",
           len(write_host.saved) == 1
           and write_host.saved[0][0] == str(target)
           and write_host.saved[0][1].pixelColor(2, 2).name() == "#00aa00",
           str([(p, i.pixelColor(2, 2).name()) for p, i in write_host.saved]))
        write_host.deleteLater()
        pump(app, times=1)

        # 取消 = 不写
        write_host2 = _WriteHost(
            ZoomTarget(render=lambda edge: None, edit_path=target)
        )
        editor_mod.ImageEditorDialog = _stub_editor(red, accepted=False)
        try:
            done2 = write_host2.edit_current_image()
        finally:
            editor_mod.ImageEditorDialog = original_dialog
        ok("取消编辑不写回、不通知、返回 False",
           done2 is False and write_host2.saved == []
           and _pixel_is(QImage(str(target)), 2, 2, "#00aa00"))
        write_host2.deleteLater()

        # 无 edit_path = 不编辑
        no_edit = _WriteHost(ZoomTarget(render=lambda edge: None))
        ok("没有可回写文件时 edit_current_image 直接返回 False",
           no_edit.edit_current_image() is False and no_edit.saved == [])
        no_edit.deleteLater()
        pump(app, times=1)

        # -------------------------------------------------- 各查看器 edit_path
        from desktop.components.viewers.image_viewer import ImageViewerWidget

        page = tmp / "extract" / "0001.png"
        page.parent.mkdir()
        _make_image().save(str(page), "PNG")  # type: ignore[reportCallIssue]
        viewer = ImageViewerWidget()
        try:
            viewer.set_images([page])
            pump(app, times=6)
            tgt = viewer._zoom_target(0)
            ok("第一步/第二步：编辑目标 = 页面图本身",
               tgt is not None and tgt.edit_path == page,
               str(getattr(tgt, "edit_path", None)))

            # 端到端：右键信号真的把菜单弹出来（patch exec，避免模态阻塞）
            import qfluentwidgets

            captured: list = []
            orig_exec = qfluentwidgets.RoundMenu.exec
            qfluentwidgets.RoundMenu.exec = (
                lambda self, *a, **k: captured.append(
                    [act.text() for act in self.menuActions()]
                )
            )
            try:
                viewer.view.context_menu_requested.emit()
            finally:
                qfluentwidgets.RoundMenu.exec = orig_exec
            ok("预览区右键 → 真的弹出「预览图片 / 编辑图片」两项",
               captured == [["预览图片", "编辑图片"]], str(captured))
        finally:
            viewer.shutdown_workers()
            viewer.deleteLater()
        pump(app, times=1)

        from desktop.components.viewers.rembg_viewer import RembgPreviewWidget

        src = tmp / "src" / "1.png"
        src.parent.mkdir()
        _make_image(color="#ffffff").save(str(src), "PNG")  # type: ignore[reportCallIssue]
        result_dir = tmp / "rembgpreview"
        result_dir.mkdir()
        result = result_dir / "1.png"      # 与源同名 → 认作该页去底色结果
        _make_image(color="#f0e8d8").save(str(result), "PNG")  # type: ignore[reportCallIssue]

        rembg = RembgPreviewWidget()
        try:
            rembg.set_images(
                [src], result_dir,
                boxes_provider=lambda _p: [[10, 20, 300, 700]],
                region_params_provider=lambda: (1, None),
            )
            pump(app, times=6)
            tgt = rembg._zoom_target(0)
            ok("第三步结果形态：编辑目标 = 去底色结果文件（本步产出）",
               tgt is not None and tgt.edit_path == result,
               str(getattr(tgt, "edit_path", None)))
            ok("结果形态是区域合成（派生显示）→ 不给 save_path",
               tgt is not None and tgt.save_path is None,
               str(getattr(tgt, "save_path", None)))

            # 实时暂存（参数已改、尚未「生成预览」）：显示的是临时文件，
            # 编辑它会被下次实时预览覆盖、也不进提交产物 → 不给编辑
            live_dir = tmp / "live"
            live_dir.mkdir()
            _make_image(color="#dddddd").save(str(live_dir / "1.png"), "PNG")  # type: ignore[reportCallIssue]  # PySide6 存根把 format 标成 bytes，运行时只收 str
            rembg.set_live_dir(live_dir)
            tgt_live = rembg._zoom_target(0)
            ok("第三步实时暂存结果 → 不给编辑（改了不生效，宁可不给）",
               tgt_live is not None and tgt_live.edit_path is None,
               str(getattr(tgt_live, "edit_path", None)))
        finally:
            rembg.shutdown_workers()
            rembg.deleteLater()
        pump(app, times=1)

        # ---------------------------------- 编辑开关（2026-10-09 只许预览）
        # 去底色阶段（taskdetail 与独立页）都传 image_editable=False：
        # 门装在**入口层**（菜单/按钮/edit_current_image），不在目标层——
        # _zoom_target 仍如实报告可回写文件，关掉的是"允许编辑"这件事。
        rembg_ro = RembgPreviewWidget(image_editable=False)
        try:
            rembg_ro.set_images(
                [src], result_dir,
                boxes_provider=lambda _p: [[10, 20, 300, 700]],
                region_params_provider=lambda: (1, None),
            )
            pump(app, times=6)
            ok("image_editable=False：开关确实关上",
               rembg_ro._zoom_editable is False)
            tgt_ro = rembg_ro._zoom_target(0)
            ok("开关关了但编辑目标如实指向结果文件（门在入口层）",
               tgt_ro is not None and tgt_ro.edit_path == result,
               str(getattr(tgt_ro, "edit_path", None)))
            texts_ro = [item[0] for item in rembg_ro._zoom_menu_items(tgt_ro)]
            ok("image_editable=False：右键菜单只给「预览图片」",
               texts_ro == ["预览图片"], str(texts_ro))

            # 端到端：右键真的只弹一项（patch exec，避免模态阻塞）
            import qfluentwidgets

            captured_ro: list = []
            orig_exec = qfluentwidgets.RoundMenu.exec
            qfluentwidgets.RoundMenu.exec = (
                lambda self, *a, **k: captured_ro.append(
                    [act.text() for act in self.menuActions()]
                )
            )
            try:
                rembg_ro.view.context_menu_requested.emit()
            finally:
                qfluentwidgets.RoundMenu.exec = orig_exec
            ok("image_editable=False：右键端到端只弹「预览图片」",
               captured_ro == [["预览图片"]], str(captured_ro))

            before = QImage(str(result)).pixelColor(2, 2).name()
            ok("image_editable=False：edit_current_image 直接拒绝（不写文件）",
               rembg_ro.edit_current_image() is False
               and QImage(str(result)).pixelColor(2, 2).name() == before)

            # 运行期重开：菜单恢复「编辑图片」项
            rembg_ro.set_image_editable(True)
            texts_re = [
                item[0]
                for item in rembg_ro._zoom_menu_items(rembg_ro._zoom_target(0))
            ]
            ok("set_image_editable(True)：菜单恢复「编辑图片」",
               texts_re == ["预览图片", "编辑图片"], str(texts_re))
        finally:
            rembg_ro.shutdown_workers()
            rembg_ro.deleteLater()
        pump(app, times=1)

        # 预览弹窗：editable=False 不渲染「编辑」按钮；运行期可来回切换
        from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

        dlg_ro = ImageZoomDialog(factory=lambda _i: None, editable=False)
        try:
            ok("弹窗 editable=False：工具栏不渲染「编辑」按钮",
               dlg_ro.edit_btn.isHidden())
            dlg_ro.set_editable(True)
            ok("弹窗 set_editable(True)：「编辑」按钮恢复",
               not dlg_ro.edit_btn.isHidden())
            dlg_ro.set_editable(False)
            ok("弹窗 set_editable(False)：「编辑」按钮再次隐藏",
               dlg_ro.edit_btn.isHidden())
        finally:
            dlg_ro.deleteLater()
        pump(app, times=1)
        dlg_default = ImageZoomDialog(factory=lambda _i: None)
        try:
            ok("弹窗默认（不传 editable）：「编辑」按钮照常在",
               not dlg_default.edit_btn.isHidden())
        finally:
            dlg_default.deleteLater()
        pump(app, times=1)

        from desktop.components.viewers.print_preview import PrintPreviewWidget

        entry = tmp / "rembg_out" / "1.png"
        entry.parent.mkdir()
        _make_image().save(str(entry), "PNG")  # type: ignore[reportCallIssue]
        preview = PrintPreviewWidget(
            params_provider=lambda: {
                "paper_size": "A4", "orientation": "landscape",
            },
        )
        try:
            preview.set_entries([{"file": str(entry), "label": "1"}])
            pump(app, times=4)
            tgt = preview._zoom_target(0)
            ok("第四步打印效果形态：编辑目标 = 待打印条目图（进 PDF 的那张）",
               tgt is not None and tgt.edit_path == entry,
               str(getattr(tgt, "edit_path", None)))
            preview._mode = "original"
            tgt2 = preview._zoom_target(0)
            ok("第四步原图形态：编辑目标同为条目图，且显示即文件（save_path）",
               tgt2 is not None and tgt2.edit_path == entry
               and tgt2.save_path == entry,
               f"edit={getattr(tgt2, 'edit_path', None)} "
               f"save={getattr(tgt2, 'save_path', None)}")
        finally:
            preview.shutdown_workers()
            preview.deleteLater()
        pump(app, times=1)

        # -------------------------------------------------- 版面画布右键
        from desktop.components.viewers.print_layout_canvas import (
            PrintLayoutCanvas,
        )

        canvas = PrintLayoutCanvas()
        canvas_fired: list = []
        canvas.context_menu_requested.connect(lambda: canvas_fired.append(1))
        canvas.contextMenuEvent(_context_event())
        ok("版面画布空页右键不弹菜单", canvas_fired == [])
        canvas.set_page(210.0, 297.0, _make_image(120, 80), [10, 10, 100, 60])
        canvas.contextMenuEvent(_context_event())
        ok("版面画布有图右键发出 context_menu_requested", canvas_fired == [1])
        canvas.deleteLater()
        pump(app, times=1)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
