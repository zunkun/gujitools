# -*- coding: utf-8 -*-
"""7. 控件结构：左缩略图 + 右效果"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _hint_of, _tmp_png, _wait_new_image
    from desktop.ui.confirm_dialog import ConfirmDialog
    from pathlib import Path
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from PySide6.QtWidgets import QAbstractItemView
    from desktop.components.viewers.thumb_strip import ThumbStrip
    import desktop.ui.confirm_dialog as _cdmod
    from tests.selftests._context import ok, pump
    widget = PrintPreviewWidget(params_provider=lambda: dict(st.full))
    try:
        ok("左缩略图条 + 右大图，且 list 是 strip 的兼容别名",
           isinstance(widget.strip, ThumbStrip)
           and widget.list is widget.strip
           and widget.view is not None)
        ok("第四步缩略图条可拖动排序，通用 ThumbStrip 默认不可拖动",
           widget.strip.dragDropMode()
           == QAbstractItemView.DragDropMode.InternalMove
           and ThumbStrip().dragDropMode()
           == QAbstractItemView.DragDropMode.NoDragDrop)
        ok("默认停在「版面编辑」（可拖拽/缩放的画布）",
           widget._mode == "layout" and widget.canvas is not None)
        # 「打印效果」「原图」仍是同一控件上的另两个视图，可随时切回
        ok("三视图齐备：版面编辑 / 打印效果 / 原图",
           widget.toggle.current() == "layout"
           and widget.toggle.is_item_enabled("effect")
           and widget.toggle.is_item_enabled("original"))

        st.png_a = _tmp_png(st.tmp / "0001.png", 800, 1200)
        st.png_b = _tmp_png(st.tmp / "0002.png", 900, 1300)
        widget.set_entries([
            {"file": str(st.png_a), "label": "0001"},
            {"file": str(st.png_b), "label": "0002"},
        ])
        ok("左侧缩略图条按条目建项", widget.strip.count() == 2)
        ok("count() 与 entries() 一致",
           widget.count() == 2
           and [Path(e["file"]).stem for e in widget.entries()]
           == ["0001", "0002"])

        # 用户 2026-11-02：底部提示文字删除；「插入图片」按钮改为「管理图片」
        ok("缩略图区不再有底部提示文字",
           not hasattr(widget, "strip_hint"))
        ok("缩略图条下方是「管理图片」按钮（不再叫插入图片）",
           widget.manage_button.text() == "管理图片"
           and hasattr(widget, "manage_requested")
           and not hasattr(widget, "insert_button"))

        # 版面编辑：默认用「当前参数自动排版出的框」初始化，用户再微调
        _rect0 = widget.canvas.current_rect()
        ok("版面编辑初始框来自自动排版（在页面内且非空）",
           len(_rect0) == 4 and _rect0[2] > 0 and _rect0[3] > 0
           and _rect0[0] >= 0 and _rect0[1] >= 0, str(_rect0))

        # 切到「打印效果」看整页效果（含标题/页码），与后续断言保持一致
        widget._set_mode("effect")
        first = _wait_new_image(widget, st.app, None)
        ok("效果预览已渲染", first is not None and first.width() > 0)
        assert first is not None  # 上一条 ok 已断言渲染成功
        ok("效果页是横版（A4 landscape）", first.width() > first.height(),
           f"{first.width()}x{first.height()}")
        ok("说明行明确「不会生成 PDF」",
           "不会生成 PDF" in widget.caption.text(), widget.caption.text())

        # 切竖版 → 纸张变化必须反映到预览
        widget._params_provider = lambda: dict(st.full, orientation="portrait")
        widget.refresh_display()
        second = _wait_new_image(widget, st.app, (first.width(), first.height()))
        assert second is not None  # 竖版渲染必有新图（同上）
        ok("改成竖版后效果页随之变竖",
           second is not None and second.height() > second.width(),
           f"{second.width()}x{second.height()}")

        # 切「原图」→ 显示图片本身（比例 = 图片自身比例）
        widget._params_provider = lambda: dict(st.full)
        widget._set_mode("original")
        third = _wait_new_image(widget, st.app, (second.width(), second.height()))
        assert third is not None  # 「原图」模式渲染必有新图（同上）
        ok("「原图」显示图片本身（不再是纸张比例）",
           third is not None
           and abs(third.height() / third.width() - 1200 / 800) < 0.02,
           f"{third.width()}x{third.height()}")

        # 参数非法 → 退回原图并给出原因，不弹窗不抛异常
        def _bad_params():
            raise ValueError("颜色格式应为 r,g,b")

        widget._params_provider = _bad_params
        widget._set_mode("effect")
        widget.refresh_display()
        pump(st.app, 4)
        ok("参数非法时不抛异常，说明行给出原因",
           "参数暂不合法" in widget.caption.text(), widget.caption.text())

        # 拖动排序：QListWidget 的 model 不支持编程式 moveRow（返回 False），
        # 真实拖放只能人工验证；这里用 Qt 内部拖放的等价动作
        # （takeItem + insertItem）走同一条 rowsMoved → 同步链路。
        seen = []
        widget._params_provider = lambda: dict(st.full)
        widget.order_changed.connect(lambda: seen.append(1))
        moved = widget.strip.takeItem(1)
        widget.strip.insertItem(0, moved)
        widget._on_strip_order_changed()
        pump(st.app, 2)
        ok("顺序变化后 order_changed 已发出", bool(seen), str(seen))
        ok("顺序变化后 entries() 同步",
           [Path(e["file"]).stem for e in widget.entries()] == ["0002", "0001"],
           str([Path(e["file"]).stem for e in widget.entries()]))
        ok("缩略图条文字顺序也同步（页码 = 当前行号，拖动后重排）",
           [widget.strip.item(i).text() for i in range(widget.strip.count())]
           == ["第一页", "第二页"],
           str([widget.strip.item(i).text() for i in range(widget.strip.count())]))

        # 用户 2026-11-01：右键「上移 / 下移」——与拖动排序走同一套重排逻辑
        before_moves = len(seen)
        ok("右键「下移」把条目往后挪一格（缓存与页码同步）",
           widget.strip.move_row(0, 1)
           and [Path(e["file"]).stem for e in widget.entries()]
           == ["0001", "0002"]
           and [widget.strip.item(i).text()
                for i in range(widget.strip.count())] == ["第一页", "第二页"],
           str([Path(e["file"]).stem for e in widget.entries()]))
        ok("右键「上移」把条目往前挪一格（回到原序）",
           widget.strip.move_row(1, -1)
           and [Path(e["file"]).stem for e in widget.entries()]
           == ["0002", "0001"],
           str([Path(e["file"]).stem for e in widget.entries()]))
        ok("上移/下移都会落到 order_changed（宿主据此存顺序）",
           len(seen) == before_moves + 2, str(seen))
        ok("第一条再「上移」不动（返回 False，菜单里置灰）",
           widget.strip.move_row(0, -1) is False)
        ok("最后一条再「下移」不动（返回 False，菜单里置灰）",
           widget.strip.move_row(1, 1) is False)
        ok("越界的上移/下移不改变顺序",
           [Path(e["file"]).stem for e in widget.entries()]
           == ["0002", "0001"],
           str([Path(e["file"]).stem for e in widget.entries()]))

        # 删除选中
        widget.strip.item(0).setSelected(True)
        widget.remove_selected()
        ok("删除后列表与缓存同步",
           widget.strip.count() == 1 and widget.count() == 1)
        ok("删除后剩下的页页码重新排序（不留着被删那版的旧号）",
           widget.strip.item(0).text() == "第一页",
           widget.strip.item(0).text())
        ok("未选中时给出提示而不是静默",
           _hint_of(widget) == "请先在左侧缩略图条选中要删除的图片。")

        # 用户 2026-11-01：右键「删除当前图片」要先弹窗确认，并告知可恢复
        ok("删除确认文案说明删除后可用「插入图片 → 删除恢复」放回",
           "插入图片" in widget._delete_confirm_text(1)
           and "恢复" in widget._delete_confirm_text(1),
           widget._delete_confirm_text(1))
        ok("多选时确认文案写明张数",
           "2 张" in widget._delete_confirm_text(2),
           widget._delete_confirm_text(2))

        # 用户 2026-11-15：这个确认框在实机上点「删除」不生效、系统"当当响"。
        # 根因是底座用了 qfluentwidgets 的 ``MessageBox``（``MaskDialogBase``
        # 派生的**子控件遮罩**，``isWindow() == False``）——不是窗口就没有模态
        # 窗口的激活语义，点击落在遮罩上。拼版批量删除 2026-10-26 踩过同一个坑。
        # 这里钉两层：① 底座是真窗口；② 本方法确实走 ConfirmDialog（换回
        # MessageBox 会立刻红），且**不真弹模态**（替身记录）。
        from desktop.ui.confirm_dialog import ConfirmDialog

        _probe = ConfirmDialog("删除当前图片", widget._delete_confirm_text(1), widget)
        ok("删除确认框是**真窗口**（不是 qfluent 的遮罩子控件）",
           _probe.isWindow() and _probe.isModal(),
           f"isWindow={_probe.isWindow()} modal={_probe.isModal()}")
        _probe.deleteLater()

        import desktop.ui.confirm_dialog as _cdmod

        _seen_box: dict = {}

        class _FakeConfirmDialog:
            def __init__(self, title, content, parent=None, **kw):
                _seen_box["title"] = title
                _seen_box["yes"] = kw.get("yes_text")
                _seen_box["cancel"] = kw.get("cancel_text")
                # 调用方只读 exec() 的返回值，替身不必造按钮
                self.yesButton = None
                self.cancelButton = None

            def exec(self):
                return 1

        _real_confirm_cls = _cdmod.ConfirmDialog
        _cdmod.ConfirmDialog = _FakeConfirmDialog
        try:
            ok("右键删除确认走真窗口 ConfirmDialog（换回遮罩 MessageBox 会红）",
               widget._ask_delete_confirm(1) is True
               and _seen_box.get("yes") == "删除"
               and _seen_box.get("cancel") == "取消",
               str(_seen_box))
        finally:
            _cdmod.ConfirmDialog = _real_confirm_cls

        widget.strip.clearSelection()
        widget.strip.item(0).setSelected(True)
        widget._ask_delete_confirm = lambda count: False  # 离屏自测不真弹模态
        widget._remove_current_with_confirm()
        ok("右键删除点「取消」时条目保留",
           widget.strip.count() == 1 and widget.count() == 1,
           f"strip={widget.strip.count()} cache={widget.count()}")
        widget._ask_delete_confirm = lambda count: True
        widget._remove_current_with_confirm()
        ok("右键删除确认后才真的从列表删掉",
           widget.strip.count() == 0 and widget.count() == 0,
           f"strip={widget.strip.count()} cache={widget.count()}")
    finally:
        widget.deleteLater()

    # 顺序变化的转发开关：前三步的页序由数据层决定，不该被拖动打乱
    plain_strip = ThumbStrip()
    forwarded: list[int] = []
    plain_strip.order_changed.connect(lambda: forwarded.append(1))
    plain_strip._on_rows_moved()
    plain_strip.set_reorderable(True)
    plain_strip._on_rows_moved()
    try:
        ok("ThumbStrip 仅在可排序时转发顺序变化",
           forwarded == [1], str(forwarded))
    finally:
        plain_strip.deleteLater()

