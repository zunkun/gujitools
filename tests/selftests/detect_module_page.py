# -*- coding: utf-8 -*-
"""独立「检测文本框」模块页自测（用户 2026-10-03 提的三件事）。

不跑 YOLO、不起子进程——全部是控件接线与纯函数断言，所以本机缺
``ultralytics``/权重时也能跑（`detect` / `detect_shared` 那两个用例才需要）。

守护三件事：

1. **手绘 + 框类型控件真的摆出来了、且接上线**——此前本页把整个
   ``DetectPanel`` 藏了，用户手画完的框**没法标成左框/右框/整幅**，
   也就没法与任务流程第二步得到同样的产物；
2. **两个导出出口**都在，且「导出标注图」先选目录、目录非空才问覆盖；
3. **槽位约定**：人工干预后的结果仍走 ``utils.box_geometry``（半幅 2 槽 /
   整幅 1 槽），本页不自己数框。
"""

from __future__ import annotations

from pathlib import Path

NAME = "detect_module_page"
DEPENDS: list[str] = ["modules_shell"]
TITLE = "独立检测模块页（手绘 / 框类型 / 导出）"

W, H = 1000, 800
LEFT = [40, 100, 460, 700]
RIGHT = [540, 100, 960, 700]
FULL = [20, 40, 980, 760]


def _png(path: Path, width: int = W, height: int = H) -> Path:
    """造一张纯色 PNG（``cv2`` 在本用例里首次被 import 是允许的）。"""
    import numpy as np
    import utils

    utils.imwrite(path, np.full((height, width, 3), 240, dtype="uint8"))
    return path


def run(ctx) -> None:  # noqa: ARG001 - 用自己的夹具，不共享 ctx 的窗口
    from PySide6.QtWidgets import QFileDialog

    from desktop.modules.detect.page import DetectModulePage
    from tests.selftests._context import ok

    tmp = Path(ctx.tmp) / "detect_module"
    tmp.mkdir(parents=True, exist_ok=True)
    page = DetectModulePage()
    try:
        _check_controls(page, ok)
        _check_drawing(page, tmp, ok)
        _check_export_annotated(page, tmp, QFileDialog, ok, ctx)
        _check_export_json(page, tmp, ok)
    finally:
        page.shutdown_workers()
        page.deleteLater()


def _check_controls(page, ok) -> None:
    """① 框类型控件摆出来了、且导出按钮存在。"""
    ok("摆出「选中框类型」分段控件", hasattr(page, "box_kind"))
    ok("分段控件三项就是左框/右框/整幅",
       [label for _key, label in page.box_kind._items] == ["左框", "右框", "整幅"],
       str(page.box_kind._items))
    ok("摆出「删除选中框」按钮", hasattr(page, "delete_box"))
    ok("没选中框时删除按钮禁用（点不动）",
       page.delete_box.isEnabled() is False)
    ok("摆出「导出标注图」按钮", hasattr(page, "annotated_button"))
    ok("摆出「导出坐标 JSON」按钮", hasattr(page, "export_button"))
    # 没框时两个导出都不该能点（导出一批没画的图没有意义）
    ok("无框时两个导出按钮都禁用",
       not page.annotated_button.isEnabled()
       and not page.export_button.isEnabled())
    # 整页模式 / 检测本页 仍不摆（单文件模式没有宿主驱动它们）。
    # ⚠️ 判**面板本身**对页面可见，而不是判里面的控件对面板可见——父控件
    #    藏起来时子控件对父仍报"可见"，那样这条断言恒真、等于没钉。
    ok("DetectPanel 整体不摆（整页模式/检测本页无宿主驱动）",
       page.control.panel is not None
       and not page.control.panel.isVisibleTo(page),
       str(page.control.panel))


def _check_drawing(page, tmp: Path, ok) -> None:
    """② 手绘 → 存槽位 → 改类型 → 删框，整条链接线。"""
    image = _png(tmp / "0001.png")
    images = tmp / "images"
    images.mkdir(exist_ok=True)
    target = _png(images / "0001.png")
    image.unlink(missing_ok=True)

    page.control.set_source(images)
    page.viewer.set_images([target])
    page._on_page_changed(0, str(target))
    ok("给了源之后操作界面显形", page.workspace_shown() is True)

    # --- 手绘一个框（走真实的 ImageView 事件链，而不是直接塞数据）---
    view = page.viewer.view
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QPixmap

    from utils.box_geometry import is_full_content

    view.set_boxes_editable(True)
    view._pixmap = QPixmap(400, 320)
    view._image_size = view._image_size or __import__(
        "PySide6.QtCore", fromlist=["QSize"]
    ).QSize(W, H)

    def press(ix, iy):
        view.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(ix * view._scale_x + view._offset_x,
                    iy * view._scale_y + view._offset_y),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))

    def release(ix, iy):
        view.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(ix * view._scale_x + view._offset_x,
                    iy * view._scale_y + view._offset_y),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        ))

    press(*LEFT[:2])
    release(*LEFT[2:])
    ok("手绘一个框后存成半幅 2 槽（形态靠槽数编码）",
       page._boxes.get("0001") == [LEFT, None],
       str(page._boxes.get("0001")))
    ok("手绘后原点记为 manual（不被后续自动检测覆盖）",
       page._origins.get("0001") == "manual", str(page._origins.get("0001")))
    ok("有框了 → 两个导出按钮解禁",
       page.export_button.isEnabled() and page.annotated_button.isEnabled())
    ok("手绘后自动选中新画的框（可直接改类型）",
       page.viewer.selected_index() == 0, str(page.viewer.selected_index()))
    ok("选中态回填到类型控件（不递归触发切换）",
       page.box_kind.current() == "left", str(page.box_kind.current()))

    # --- 改类型：整幅 → 2 槽（按中心位置定左右）---
    page._on_box_kind_changed("full")
    ok("单框切成整幅 → 1 槽",
       page._boxes.get("0001") == [LEFT], str(page._boxes.get("0001")))
    ok("切成整幅后确实是整幅形态", is_full_content(page._boxes.get("0001")))
    page._on_box_kind_changed("left")
    ok("整幅切回半幅 → 2 槽（左半的框落左槽）",
       page._boxes.get("0001") == [LEFT, None], str(page._boxes.get("0001")))

    # --- 删框 → 空表，且删除按钮随后禁用 ---
    page.viewer.select_box(0)
    page._delete_selected_box()
    ok("删框后该页没有槽位了", not page._boxes.get("0001"),
       str(page._boxes.get("0001")))
    ok("删光后导出按钮回到禁用", not page.export_button.isEnabled())
    ok("删框后没有选中，类型控件三段都不高亮",
       page.box_kind.current() == "", str(page.box_kind.current()))

    # --- 没选中框时点类型 = 选中该类框（用户 2026-09-29 要求 6）---
    page._boxes["0001"] = [LEFT, RIGHT]
    page._apply_boxes(str(target))
    page.viewer.select_box(-1)
    page._on_box_kind_changed("right")
    ok("没选中时点「右框」→ 选中右侧那个框",
       page.viewer.selected_index() == 1, str(page.viewer.selected_index()))


def _check_export_annotated(page, tmp: Path, QFileDialog, ok, ctx) -> None:
    """③ 导出标注图：先选目录 → 目录非空才问覆盖 → 真的写出 PNG。"""
    from desktop.services.detect_export import annotated_name

    # 一个框都没有 → 不该进入选目录流程
    asked: list = []
    original = QFileDialog.getExistingDirectory
    QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: (asked.append(a[1]), "")[1]
    )
    try:
        page._boxes.clear()
        page._sync_export_buttons()
        page.export_annotated_images()
        ok("没有框时不弹目录选择（先在界面上说清楚）", asked == [], str(asked))
        ok("没有框时标注图按钮是禁用的",
           page.annotated_button.isEnabled() is False)
    finally:
        QFileDialog.getExistingDirectory = original

    # 造一页带框的图，导出到一个**还不存在**的目录 → 不问覆盖，直接写
    images = tmp / "images"
    source = _png(images / "0001.png")
    page._boxes["0001"] = [LEFT, RIGHT]
    page._origins["0001"] = "auto"
    out_dir = tmp / "annotated_new"

    asked.clear()
    QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: (asked.append(a[1]), str(out_dir))[1]
    )
    confirmed: list = []

    class _Box:
        """替掉 qfluentwidgets.MessageBox：记录一次确认。"""

        def __init__(self, title, content, parent=None):
            confirmed.append((title, content))
            self.yesButton = self
            self.cancelButton = self

        def setText(self, _text):
            pass

        def exec(self):
            return True

    import qfluentwidgets

    original_box = qfluentwidgets.MessageBox
    try:
        qfluentwidgets.MessageBox = _Box
        page.export_annotated_images()
        # 等导出线程收尾
        from tests.selftests._context import wait_until

        done = wait_until(ctx.app, lambda: not page._export_kernel.busy(), timeout=60)
        ok("导出线程正常结束", done, "线程仍在跑")
        ok("目录不存在 → 不问覆盖", confirmed == [], str(confirmed))
        ok("确实弹过目录选择（用户要求「导出的时候提示选择输出目录」）",
           len(asked) == 1, str(asked))
        expected = out_dir / annotated_name(source)
        ok("标注图写出来了", expected.is_file(), str(expected))
        ok("标注图非空（真的画了框）",
           expected.is_file() and expected.stat().st_size > 0)
    finally:
        qfluentwidgets.MessageBox = original_box

    # 目录**已存在且非空** → 必须问一次覆盖
    asked.clear()
    confirmed.clear()
    QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: (asked.append(a[1]), str(out_dir))[1]
    )
    try:
        qfluentwidgets.MessageBox = _Box
        page.export_annotated_images()
        from tests.selftests._context import wait_until

        wait_until(ctx.app, lambda: not page._export_kernel.busy(), timeout=60)
        ok("目录已存在且非空 → 问是否覆盖", len(confirmed) == 1, str(confirmed))
        ok("覆盖确认写清了「覆盖」二字",
           confirmed and "覆盖" in confirmed[0][0], str(confirmed))
    finally:
        qfluentwidgets.MessageBox = original_box
        QFileDialog.getExistingDirectory = original

    # 取消覆盖 → 一个文件都不该动
    asked.clear()
    before = sorted(p.name for p in out_dir.iterdir())
    stamp = (out_dir / annotated_name(source)).stat().st_mtime_ns

    class _CancelBox(_Box):
        def exec(self):
            return False

    QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: (asked.append(a[1]), str(out_dir))[1]
    )
    try:
        qfluentwidgets.MessageBox = _CancelBox
        page.export_annotated_images()
        ok("取消覆盖 → 不启动导出（也不弹第二次目录选择）",
           len(asked) == 1, str(asked))
        ok("取消覆盖 → 目录内容未变",
           sorted(p.name for p in out_dir.iterdir()) == before)
        ok("取消覆盖 → 没有覆写已有标注图",
           (out_dir / annotated_name(source)).stat().st_mtime_ns == stamp)
    finally:
        qfluentwidgets.MessageBox = original_box
        QFileDialog.getExistingDirectory = original


def _check_export_json(page, tmp: Path, ok) -> None:
    """④ 坐标 JSON 仍按任务流程那套格式写（与 boxes.json 逐字段一致）。"""
    import json

    out_dir = tmp / "json_out"
    page.control.set_output(out_dir)
    page._boxes.clear()
    page._boxes["0001"] = [LEFT, RIGHT]
    page._origins["0001"] = "manual"
    page.export_boxes()
    target = out_dir / "boxes.json"
    ok("坐标 JSON 写到输出目录", target.is_file(), str(target))
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
        entry = data.get("0001") or {}
        ok("JSON 顶层键是页名去后缀", "0001" in data, str(list(data)))
        ok("字段是 boxes/origin/updated_at（与任务流程一致）",
           set(entry) == {"boxes", "origin", "updated_at"}, str(list(entry)))
        ok("boxes 存的是槽位（保留 None 占位）",
           entry.get("boxes") == [LEFT, RIGHT], str(entry.get("boxes")))
        ok("origin 记为 manual", entry.get("origin") == "manual",
           str(entry.get("origin")))


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
