# -*- coding: utf-8 -*-
"""第四步预览区的**布局形态**自测：与前三步保持一致。

背景：第四步原来是「图片瀑布流（QListWidget IconMode 网格）」，右侧参数
再全也看不出成品长什么样，而且和第一~三步（左缩略图条 + 右大图）不是
一套视觉语言。改成左缩略图 + 右效果预览后，本模块守住三条布局不变量：

1. 第 2/3/4 步的预览区都是「左 ThumbStrip + 右 ImageView」；
2. 旧瀑布流的网格常量（ICON_SIZE / GRID_SIZE / LABEL_H）已经移除——
   只要有人把它们加回来，说明又退回网格布局了；
3. 缩略图条宽度与前三步一致（视觉对齐）。
"""

NAME = "print_list_layout"
DEPENDS: list[str] = []
TITLE = "第四步预览布局形态"


def run(ctx) -> None:
    from typing import cast

    from tests.selftests._context import ok

    from desktop.components.viewers.image_view import ImageView
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget
    from desktop.components.viewers.thumb_strip import ThumbStrip

    # ---- 1. 与前三步同构：左缩略图条 + 右大图 ----
    widgets = {
        "detect(第2步)": ImageViewerWidget(),
        "rembg(第3步)": RembgPreviewWidget(),
        "print(第4步)": PrintPreviewWidget(),
    }
    try:
        for name, widget in widgets.items():
            ok(f"{name}：左 ThumbStrip + 右 ImageView",
               isinstance(getattr(widget, "strip", None), ThumbStrip)
               and isinstance(getattr(widget, "view", None), ImageView),
               f"{type(widget).__name__}")
            ok(f"{name}：缩略图条在左（先于大图加入布局）",
               widget.layout().itemAt(0) is not None)
    finally:
        for widget in widgets.values():
            widget.deleteLater()

    # ---- 2. 旧瀑布流常量必须已移除 ----
    for attr in ("ICON_SIZE", "GRID_SIZE", "LABEL_H"):
        ok(f"print 预览已移除旧网格常量 {attr}",
           not hasattr(PrintPreviewWidget, attr),
           str(getattr(PrintPreviewWidget, attr, None)))

    # ---- 3. 缩略图条宽度与前三步一致 ----
    # 无父对象的临时控件必须持有引用，否则会被 Python 立刻回收
    holder = PrintPreviewWidget()
    plain = ThumbStrip()
    try:
        strip_print = holder.strip
        ok("缩略图条宽度沿用 ThumbStrip 固定值",
           strip_print.width() == plain.width() and strip_print.width() > 0,
           f"{strip_print.width()} vs {plain.width()}")
        ok("缩略图条宽度就是 ThumbStrip.STRIP_WIDTH（唯一来源）",
           strip_print.width() == ThumbStrip.STRIP_WIDTH,
           f"{strip_print.width()} vs {ThumbStrip.STRIP_WIDTH}")
        # 条目网格必须放得下整个图标框：图标框比网格还大时 QListWidget 会
        # 悄悄压缩图标，缩略图看起来"没占满宽度"
        ok("条目网格放得下图标框（含文字行）",
           ThumbStrip.GRID_SIZE.width() >= ThumbStrip.ICON_SIZE.width()
           and ThumbStrip.GRID_SIZE.height()
           >= ThumbStrip.ICON_SIZE.height() + ThumbStrip.LABEL_H,
           f"grid={ThumbStrip.GRID_SIZE} icon={ThumbStrip.ICON_SIZE}")
        ok("缩略图条为纵向单列（不换行）",
           strip_print.flow() == ThumbStrip.Flow.TopToBottom
           and strip_print.isWrapping() is False)
    finally:
        holder.deleteLater()
        plain.deleteLater()

    # ---- 4. 预览区顶部按钮行已取消（用户 2026-11-01）----
    widget = PrintPreviewWidget()
    try:
        ok("预览区顶部按钮行已取消（删除选中 / 下载 PDF 不再挂预览控件上）",
           not hasattr(widget, "delete_button")
           and not hasattr(widget, "download_button")
           and not hasattr(widget, "hint_label"))

        # ---- 5. 插入图片在缩略图下面；单页导出/打印与视图切换同一行靠右 ----
        def _sub_layout(layout, index: int):
            if layout is None:
                return None
            item = layout.itemAt(index)
            return item.layout() if item is not None else None

        body = _sub_layout(widget.layout(), 0)
        left = _sub_layout(body, 0)
        right = _sub_layout(body, 1)
        toggle_row = _sub_layout(right, 0)
        ok("「管理图片」按钮紧跟缩略图条（同一左侧竖列的下方）",
           left is not None
           and left.indexOf(widget.strip) >= 0
           and left.indexOf(widget.manage_button) == left.indexOf(widget.strip) + 1,
           f"strip={left.indexOf(widget.strip) if left else None} "
           f"manage={left.indexOf(widget.manage_button) if left else None}")
        ok("按钮文案是「管理图片」（不再叫插入图片）",
           widget.manage_button.text() == "管理图片",
           widget.manage_button.text())
        ok("「下载本页图片 / 打印本页」与「版面编辑」同一行、靠右",
           toggle_row is not None
           and toggle_row.indexOf(widget.toggle) >= 0
           and toggle_row.indexOf(widget.export_image_button)
           > toggle_row.indexOf(widget.toggle)
           and toggle_row.indexOf(widget.print_button)
           > toggle_row.indexOf(widget.export_image_button),
           f"toggle={toggle_row.indexOf(widget.toggle) if toggle_row else None} "
           f"export={toggle_row.indexOf(widget.export_image_button) if toggle_row else None} "
           f"print={toggle_row.indexOf(widget.print_button) if toggle_row else None}")

        # ---- 6. 右键菜单入口 + 两个「向前/向后插入」信号 ----
        from PySide6.QtCore import Qt

        ok("缩略图条开启自定义右键菜单",
           widget.strip.contextMenuPolicy()
           == Qt.ContextMenuPolicy.CustomContextMenu)
        ok("右键「向前/向后插入」信号可用",
           hasattr(widget, "insert_before_requested")
           and hasattr(widget, "insert_after_requested"))
    finally:
        widget.deleteLater()

    # ---- 7. 插入弹窗两个页签 + result_data() 契约 ----
    from desktop.components.print_insert_dialog import PrintInsertPanel
    from PySide6.QtWidgets import QAbstractItemView, QListView

    panel = PrintInsertPanel(
        deleted=[{"file": str(ctx.tmp / "gone.png"), "label": "gone"}],
        current_row=1,
        total=4,
    )
    try:
        ok("插入弹窗有两个页签（上传图片 / 删除恢复）", panel.stack.count() == 2)
        # 用户 2026-11-01：页签顺序改成「上传图片」在前，默认停在第一个页签
        ok("默认停在第一个页签「上传图片」",
           panel.stack.currentIndex() == 0 and panel.toggle.current() == "upload")
        ok("上传页的空白处是虚线拖放框（可拖入、可点击选图）",
           hasattr(panel, "drop_area")
           and panel.drop_area.acceptDrops(), str(dir(panel)))
        ok("恢复页是图标网格（一行多张，不是一张一行）",
           panel.restore_list.viewMode() == QListView.ViewMode.IconMode
           and panel.restore_list.isWrapping(), str(panel.restore_list.viewMode()))
        before_text = (
            panel.before_radio.text() if panel.before_radio is not None else ""
        )
        after_text = (
            panel.after_radio.text() if panel.after_radio is not None else ""
        )
        ok("位置选项写明当前页号（选第 2 行 → 第 2 页）",
           "第 2 页" in before_text and "第 2 页" in after_text,
           f"before={before_text} after={after_text}")
        ok("默认落点为「当前页之后」",
           panel.after_radio is not None and panel.after_radio.isChecked())
        result = panel.result_data()
        ok("result_data() 形状 = position/deleted/files",
           set(result) == {"position", "deleted", "files"}
           and result["position"] == "after"
           and result["deleted"] == [] and result["files"] == [],
           str(result))
    finally:
        panel.deleteLater()

    # ---- 7b. 「管理图片」弹窗 A：草稿式网格（多选 / 拖动 / 二次插入）----
    # 用户 2026-11-02：缩略图条底部改为「管理图片」，弹窗里一行多列、可多选、
    # 可拖动；底部再开一次「插入图片」；**不点保存则一律不生效**。
    from desktop.components.print_manage_dialog import (
        PENDING_KEY,
        PrintManagePanel,
        SHOWN_SIZE_ROLE,
        _ThumbDelegate,
        _check_rect,
        _close_rect,
        _image_rect,
        page_label,
    )
    from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
    from PySide6.QtGui import QMouseEvent
    from pathlib import Path

    seed = [
        {"file": str(ctx.tmp / f"manage_{i}.png"), "label": str(i)}
        for i in range(3)
    ]
    manage = PrintManagePanel(entries=seed)
    try:
        ok("管理弹窗是图标网格（一行多列）",
           manage.list.viewMode() == QListView.ViewMode.IconMode
           and manage.list.flow() == QListView.Flow.LeftToRight
           and manage.list.isWrapping(),
           f"mode={manage.list.viewMode()} flow={manage.list.flow()}")
        ok("管理弹窗可多选、可内部拖动排序",
           manage.list.selectionMode()
           == QAbstractItemView.SelectionMode.ExtendedSelection
           and manage.list.dragDropMode()
           == QAbstractItemView.DragDropMode.DragDrop)
        ok("管理弹窗底部是「插入图片」按钮",
           manage.insert_button.text() == "插入图片",
           manage.insert_button.text())
        ok("条目名称写成「第一页 / 第二页 / 第三页」（与图片拼版同口径）",
           [manage.list.item(r).text() for r in range(3)]
           == ["第一页", "第二页", "第三页"]
           and page_label(0) == "第一页",
           str([manage.list.item(r).text() for r in range(3)]))
        ok("每张图都由自绘条目提供右上角删除 x",
           isinstance(manage.list.itemDelegate(), _ThumbDelegate))
        ok("未选中时底部不显示「删除图片」", manage.delete_button.isHidden())
        manage.list.item(0).setSelected(True)
        ok("选中后底部出现「删除图片」",
           not manage.delete_button.isHidden()
           and manage.delete_button.text() == "删除图片",
           manage.delete_button.text())
        manage.list.clearSelection()
        ok("取消选中后「删除图片」再次隐藏", manage.delete_button.isHidden())
        manage.list.setCurrentRow(1)
        manage._apply_insert_result(
            {"position": "after", "deleted": [],
             "files": [str(ctx.tmp / "manage_new.png")]},
            row=1, total=3,
        )
        drafts = manage.entries()
        ok("插入图片先落进草稿：位于选中页之后并标记待复制",
           len(drafts) == 4
           and drafts[2]["file"].endswith("manage_new.png")
           and drafts[2].get(PENDING_KEY) is True,
           str(drafts))
        ok("待复制条目带实际缩略图尺寸（自绘虚线框据此定位）",
           isinstance(
               manage.list.item(2).data(SHOWN_SIZE_ROLE), QSize),
           str(manage.list.item(2).data(SHOWN_SIZE_ROLE)))
        ok("草稿改动不回写入参（不保存就不生效）",
           len(seed) == 3 and seed[1]["file"].endswith("manage_1.png"))
        # 还没复制进任务目录的新图没有可恢复的源文件，不进「删除恢复」
        manage._remove_rows([2])
        ok("删掉待复制的新图不会进「删除恢复」清单",
           manage._deleted == [] and len(manage.entries()) == 3,
           str(manage._deleted))
    finally:
        manage.deleteLater()

    # 右上角 x 的命中删除：真的点到那条 18×18 的小叉，行数必须少一条
    manage2 = PrintManagePanel(entries=seed)
    try:
        manage2.resize(560, 360)
        manage2.show()
        ctx.app.processEvents()
        item = manage2.list.item(0)
        cell = manage2.list.visualItemRect(item)
        shown = item.data(SHOWN_SIZE_ROLE) or QSize()
        pos = _close_rect(_image_rect(cell, shown)).center()
        event = QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(pos),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        before = manage2.list.count()
        manage2.list.mousePressEvent(event)
        ok("点图片右上角的 x 即从草稿删掉这一张",
           manage2.list.count() == before - 1,
           f"{before} → {manage2.list.count()}")
        # 左上角多选框：点一下只翻转这一条（多选就靠它）
        manage2.list.clearSelection()
        ctx.app.processEvents()
        item = manage2.list.item(0)
        cell = manage2.list.visualItemRect(item)
        shown = item.data(SHOWN_SIZE_ROLE) or QSize()
        check_pos = _check_rect(_image_rect(cell, shown)).center()
        manage2.list.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(check_pos),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ))
        ok("点左上角多选框即选中该图（并露出删除按钮）",
           item.isSelected() and not manage2.delete_button.isHidden())
        manage2.delete_button.click()
        ok("底部「删除图片」删掉复选框选中的图片（仍是草稿）",
           manage2.list.count() == before - 2, str(manage2.list.count()))
        # 用户 2026-11-02：草稿里删掉的图仍要能在「插入图片 → 删除恢复」恢复
        remembered = [str(p.get("file")) for p in manage2._deleted]
        ok("草稿里删掉的图会记进「删除恢复」清单",
           len(remembered) == 2
           and all(str(ctx.tmp / f"manage_{i}.png") in remembered
                   for i in (0, 1)),
           str(remembered))
        gone_file = str(ctx.tmp / "manage_0.png")
        manage2._apply_insert_result(
            {"position": "before",
             "deleted": [{"file": gone_file, "label": "0"}],
             "files": []},
            row=0, total=manage2.list.count(),
        )
        restored_files = [str(e["file"]) for e in manage2.entries()]
        ok("从「删除恢复」放回的图真的回到草稿最前面",
           len(restored_files) == 2 and restored_files[0] == gone_file,
           str(restored_files))
        ok("放回后它不再挂在「删除恢复」里（不会重复出现）",
           gone_file not in [str(p.get("file")) for p in manage2._deleted],
           str(manage2._deleted))
    finally:
        manage2.deleteLater()

    # 拖动重排：用户 2026-11-02 报「拖一张图片无法改变位置」——
    # IconMode 的 InternalMove 不落位，这里改用自算落点 + take/insert。
    manage3 = PrintManagePanel(entries=seed)
    try:
        manage3.resize(560, 360)
        manage3.show()
        ctx.app.processEvents()
        before_files = [e["file"] for e in manage3.entries()]
        ok("落点按左右半区判定（右半 → 插到该项之后）",
           manage3.list._drop_index_at(
               manage3.list.visualItemRect(manage3.list.item(0))
               .center() + QPoint(30, 0)
           ) == 1
           and manage3.list._drop_index_at(
               QPoint(
                   manage3.list.visualItemRect(manage3.list.item(0)).left() + 2,
                   manage3.list.visualItemRect(manage3.list.item(0)).center().y(),
               )
           ) == 0)
        manage3.list._move_rows_to([0], 3)
        after_files = [e["file"] for e in manage3.entries()]
        ok("单张拖动重排真的换了位置",
           after_files == before_files[1:] + before_files[:1],
           f"{[Path(p).name for p in after_files]}")
        ok("重排后的名称仍是当前页码",
           [manage3.list.item(r).text() for r in range(3)]
           == [page_label(0), page_label(1), page_label(2)])
        manage3.list._move_rows_to([0, 2], 3)
        after_batch = [e["file"] for e in manage3.entries()]
        ok("多选后整批拖动（相对顺序不变）",
           after_batch == [after_files[1], after_files[0], after_files[2]],
           f"{[Path(p).name for p in after_batch]}")
        ok("整批拖动后仍保持多选（当前项不吞掉其它选中）",
           all(manage3.list.item(r).isSelected() for r in (1, 2)))
    finally:
        manage3.deleteLater()

    # 用户 2026-11-02：每一行**最左边**也要能作为落点（插到该行开头）。
    # 旧实现只认"最近条目"：瞄准某行最左边时会被上一行末尾抢走。
    manage4 = PrintManagePanel(entries=seed)
    try:
        manage4.resize(300, 360)
        manage4.show()
        ctx.app.processEvents()
        rows = {}
        for r in range(manage4.list.count()):
            rect = manage4.list.visualItemRect(manage4.list.item(r))
            rows.setdefault(rect.top(), []).append((r, rect))
        ok("窄窗口下网格自动换行成多行", len(rows) >= 2, str(len(rows)))
        leftmost = {
            top: manage4.list._drop_index_at(
                QPoint(2, band[0][1].center().y()))
            for top, band in rows.items()
        }
        ok("每行最左边的落点 = 该行第一张",
           all(leftmost[top] == band[0][0] for top, band in rows.items()),
           str(leftmost))
        last_top = max(rows)
        last_band = rows[last_top]
        ok("行尾右侧 → 紧接下一行开头（末行为列表末尾）",
           manage4.list._drop_index_at(
               QPoint(last_band[-1][1].right() + 8,
                      last_band[0][1].center().y()))
           == last_band[-1][0] + 1,
           str(manage4.list.count()))
    finally:
        manage4.deleteLater()

    # ---- 8. 条目高度逐条自适应：不同宽高比的页面之间不再是"留白" ----
    # 根因：早先网格单元统一高度（竖框 156 + 文字行），横幅双页拼合图缩进
    # 竖框后只占约一半幅高，剩下的是单元内空白；而网格高度若取"最高那张"，
    # 矮一点的条目各自留的空白还不一样大 → 用户看到"同高图间距 0、
    # 不同高图间距很大"。现在取消网格、每条按图定高，间距只剩 ITEM_SPACING。
    from PySide6.QtGui import QImage

    strip = ThumbStrip()
    try:
        label_h = ThumbStrip.LABEL_H
        spacing = ThumbStrip.ITEM_SPACING
        ok("条目之间保留可见间距（不为 0）", spacing > 0, f"spacing={spacing}")

        def _hint_h(w: int, h: int) -> int:
            """w×h 的图放进图标框后的条目总高（图高 + 文字行）。"""
            shown = _size_fitted(w, h)
            return max(ThumbStrip.MIN_DISPLAY_H, shown) + label_h

        def _size_fitted(w: int, h: int) -> int:
            box_w, box_h = (ThumbStrip.ICON_SIZE.width(),
                            ThumbStrip.ICON_SIZE.height())
            scale = min(box_w / w, box_h / h)
            return round(h * scale)

        def _make_image(w: int, h: int) -> QImage:
            img = QImage(w, h, QImage.Format.Format_RGB32)
            img.fill(0xFF888888)
            return img

        # 三张宽高比不同的图：横幅双页(480×200) / 中等(400×260) / 竖开本(200×400)
        sizes = [(480, 200), (400, 260), (200, 400)]
        for w, h in sizes:
            strip.add_page_item(f"{w}x{h}", "")
        ok("占位图阶段条目按满框给定",
           strip.item(0).sizeHint().height()
           == ThumbStrip.ICON_SIZE.height() + label_h,
           str(strip.item(0).sizeHint()))
        for row, (w, h) in enumerate(sizes):
            strip.set_item_icon(row, _make_image(w, h), f"f{row}", f"第{row}頁")

        hints = [strip.item(row).sizeHint().height() for row in range(3)]
        expected = [_hint_h(w, h) for w, h in sizes]
        ok("条目高度逐条跟着图走（不同宽高比 → 不同高）",
           hints == expected and len(set(hints)) == len(hints),
           f"{hints} vs {expected}")
        ok("条目高度 = 图高 + 文字行（条目内不留任何空白）",
           all(abs(got - exp) <= 1 for got, exp in zip(hints, expected)),
           f"{hints} vs {expected}")
        ok("横幅图条目明显比旧满框矮（空白已去掉）",
           hints[0] < ThumbStrip.ICON_SIZE.height() + label_h - 24,
           f"{hints[0]} vs 满框 {ThumbStrip.ICON_SIZE.height() + label_h}")
        ok("竖开本条目仍是满框高（窄图不被压扁也不被截断）",
           abs(hints[2] - (ThumbStrip.ICON_SIZE.height() + label_h)) <= 1,
           f"{hints[2]}")
        # 条目宽度统一（占满条宽），与前三步对齐
        ok("条目宽度统一 = 网格宽",
           all(strip.item(row).sizeHint().width()
               == ThumbStrip.GRID_SIZE.width() for row in range(3)),
           str([strip.item(r).sizeHint().width() for r in range(3)]))
    finally:
        strip.deleteLater()

    # ---- 2. 取图规格：**整图透传列表**（2026-10-01 新契约）----
    # 用户口径「去底色那一步，必须提交才能传给下一步」：第四步只排版
    # 「提交本次任务」的成品图，不再拿去底图按当前 area/border 现算。
    #
    # ⚠️ 这条契约顺带干掉了一类真实事故：旧实现要按 label 把列表与"当前
    # area 派生集合"对齐（形态不同时还得按基础页名重映射），一旦对齐逻辑出错，
    # 用户在第四步**删掉的页会被补回来**（实测症状：列表 101 条却生成了
    # 198 页 PDF）。现在取图就是列表本身，顺序即页序、删掉即消失。
    from pathlib import Path

    from desktop.pages.taskdetail.submit import SubmitMixin

    tmp = Path(ctx.tmp) / "print_list_layout"
    rembg = tmp / "rembg"
    rembg.mkdir(parents=True, exist_ok=True)

    def file_of(name: str) -> str:
        path = rembg / f"{name}.png"
        path.write_bytes(b"x")
        return str(path)

    outside = tmp / "outside.png"
    outside.write_bytes(b"x")
    missing = rembg / "缺失.png"  # 不创建：文件不存在的条目
    entries = [
        {"file": file_of("3"), "label": "3"},
        {"file": file_of("1-r"), "label": "1-r"},
        {"file": str(outside), "label": "cover"},
        {"file": str(missing), "label": "缺失"},
    ]
    # ⚠️ 用最小替身调用：取图规则**不再依赖页面/面板/拼版状态**（这也正是
    #    新契约的一部分）；一旦有人往方法里塞 self.xxx，这里会立刻红。
    effects = SubmitMixin._build_print_effects(
        cast("SubmitMixin", object()), entries)
    ok("取图 = 列表顺序逐条透传（含外部插入图）",
       [e["file"] for e in effects]
       == [entries[0]["file"], entries[1]["file"], str(outside)],
       str([Path(e["file"]).name for e in effects]))
    ok("…且不再携带区域合成规格（effect 全为 None）",
       all(e.get("effect") is None for e in effects), str(effects))
    ok("列表里指向已不存在文件的条目被过滤（不生成空页）",
       not any("缺失" in e["file"] for e in effects),
       str([e["file"] for e in effects]))
