# -*- coding: utf-8 -*-
"""任务列表页自测：导入查重、行内操作按钮与任务表格视觉守卫。

创建主任务 ``ctx.tid`` 与同指纹重复任务 ``ctx.tid_dup``（后续模块共用），
并打开详情页，是大多数模块的依赖根。
"""

NAME = "tasklist"
DEPENDS: list[str] = []
TITLE = "任务列表"


def run(ctx) -> None:
    import time

    from qfluentwidgets import PushButton
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHeaderView

    from desktop.ui import theme as T
    from tests.selftests._context import ok

    app, w, d, repo = ctx.app, ctx.w, ctx.d, ctx.repo

    tid = repo.create_task(ctx.pdf, "hashA", "古籍样例")
    ctx.tid = tid
    w.list_page.refresh()
    ok("导入后立即出条目", w.list_page.table.table.rowCount() == 1)
    ok("创建任务带指纹", repo.get_task(tid)["source_hash"] == "hashA")

    tid_dup = repo.create_task(ctx.big_pdf, "hashA", "大部头")
    ctx.tid_dup = tid_dup
    w.list_page.refresh()
    ok("列表条目数正确", w.list_page.table.table.rowCount() == 2)

    # 查重：取消 → 不新建，定位到已有任务
    w.list_page._confirm_duplicate = lambda path, dups: False
    w.list_page._hash_ready(str(ctx.big_pdf), "hashA")
    ok("重复文件取消后未新建", len(repo.list_tasks()) == 2)
    ok("取消后可定位到已有任务", w.list_page.table.select_task(tid_dup))

    # 查重：确认 → 新建一条并标记 duplicate_confirmed
    w.list_page._confirm_duplicate = lambda path, dups: True
    rows_before = len(repo.list_tasks())
    w.list_page._hash_ready(str(ctx.big_pdf), "hashA")
    ok("重复文件确认后新建一条", len(repo.list_tasks()) == rows_before + 1)
    newest = repo.list_tasks()[0]
    ok("新建任务标记 duplicate_confirmed", newest["duplicate_confirmed"] == 1)
    ok("新建任务保留副本", (repo.task_dir(newest["id"]) / ctx.big_pdf.name).exists())
    thumbs_dir = repo.source_thumbnails_dir(newest["id"])
    for _ in range(100):
        if thumbs_dir.exists() and len(list(thumbs_dir.glob("*.jpg"))) == 80:
            break
        app.processEvents(); time.sleep(0.1)
    ok("导入后生成逐页缩略图", len(list(thumbs_dir.glob("*.jpg"))) == 80,
       f"实际 {len(list(thumbs_dir.glob('*.jpg'))) if thumbs_dir.exists() else 0} 张")
    repo.delete_task(newest["id"])

    # 行内按钮存在 + 防回归守卫：表头垂直居中、任务名称列占主体、删除按钮危险色
    table = w.list_page.table.table
    action_cell = table.cellWidget(0, table.columnCount() - 1)
    buttons = action_cell.findChildren(PushButton)
    ok("行内详情/删除按钮存在", len(buttons) == 2)

    header_view = table.horizontalHeader()
    aligns = [
        int(table.horizontalHeaderItem(c).textAlignment())
        for c in range(table.columnCount())
    ]
    ok(
        "表头文本均垂直居中",
        all(a & int(Qt.AlignmentFlag.AlignVCenter) for a in aligns),
        str([hex(a) for a in aligns]),
    )
    ok(
        "任务名称列自适应拉伸",
        header_view.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch,
    )
    ok(
        "子任务状态列固定宽",
        header_view.sectionResizeMode(3) == QHeaderView.ResizeMode.Interactive
        and header_view.sectionSize(3) == 256,
        str(header_view.sectionSize(3)),
    )

    # 「序号」列 = 任务自己的编号（0001、0002…），不是行号；且列宽必须真的
    # 放得下 4 位数字——委托按 SE_ItemViewItemText 扣掉左右各 ~16px 内边距，
    # 光按字宽设 56px 时 32px 宽的 "0001" 会被省略成「…」，界面等于"序号没了"。
    from PySide6.QtGui import QFontMetrics

    from desktop.components.task_table import TaskTable

    # 先刷新：本模块前面删过一条任务，表格还停在旧数据上
    w.list_page.refresh()
    shown_numbers = [
        table.item(r, 0).text() for r in range(table.rowCount())
    ]
    ok(
        "序号列显示任务自己的编号",
        shown_numbers == [t["id"] for t in repo.list_tasks()],
        f"{shown_numbers} vs {[t['id'] for t in repo.list_tasks()]}",
    )
    needed = QFontMetrics(table.font()).horizontalAdvance("0001")
    usable = header_view.sectionSize(0) - 2 * TaskTable._CELL_TEXT_MARGIN
    ok(
        "序号列宽放得下 4 位任务号（不会被省略成 …）",
        usable >= needed and header_view.sectionSize(0) > 0,
        f"可用 {usable}px，需要 {needed}px",
    )
    delete_btn = next(b for b in buttons if b.text() == "删除")
    danger_qss = delete_btn.styleSheet()
    ok(
        "删除按钮使用危险色样式（四态齐全）",
        T.DANGER in danger_qss
        and ":hover" in danger_qss
        and ":pressed" in danger_qss
        and ":disabled" in danger_qss,
    )

    # 防回归守卫：单元格容器锁定整行高，内容垂直居中。
    # qfluent 的 TableItemDelegate.updateEditorGeometry 用「改高度前」的容器高
    # 算居中偏移、随后又把高度改成整格高——容器高度≠行高时位置随时序漂移，
    # 真实运行中胶囊/按钮会偏到行底（离屏探针因时序不同可能无法复现）。
    from desktop.components.task_table import ROW_HEIGHT
    from desktop.ui import StatusChip
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QStyleOptionViewItem

    chips_cell = table.cellWidget(0, 3)
    ok(
        "状态/操作容器锁定整行高",
        chips_cell.height() == ROW_HEIGHT and action_cell.height() == ROW_HEIGHT,
        f"chips={chips_cell.height()} action={action_cell.height()} 期望 {ROW_HEIGHT}",
    )
    action_cell.layout().activate()
    btn_y = (ROW_HEIGHT - buttons[0].height()) // 2
    ok(
        "操作按钮在容器内垂直居中",
        all(b.geometry().y() == btn_y for b in buttons),
        str([(b.text(), b.geometry().y()) for b in buttons]),
    )
    chips_cell.layout().activate()
    chip_children = chips_cell.findChildren(StatusChip)
    chip_y = (ROW_HEIGHT - chip_children[0].height()) // 2
    ok(
        "状态胶囊在容器内垂直居中",
        chip_children and all(c.geometry().y() == chip_y for c in chip_children),
        str([c.geometry().y() for c in chip_children]),
    )
    # 直接过一遍 delegate 的几何更新（出问题的那一环）：锁定整行高后，
    # 无论此前容器处于什么状态，一次更新必须精确落到目标单元格。
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, ROW_HEIGHT, 132, ROW_HEIGHT)  # 模拟第 1 行操作列
    table.itemDelegate().updateEditorGeometry(action_cell, opt, table.model().index(1, 4))
    g = action_cell.geometry()
    ok(
        "几何更新后容器精确填满单元格",
        g.y() == opt.rect.y() and g.height() == ROW_HEIGHT,
        f"y={g.y()} h={g.height()} 期望 y={opt.rect.y()} h={ROW_HEIGHT}",
    )

    # 任务名称 = 可点击的链接样式（下划线 + 主色 + hover 变深 + 手型光标）
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent, QMouseEvent
    from PySide6.QtWidgets import QLabel

    # ⚠️ 窗口没 show 时单元格控件被布局压成 10px 宽（列宽还没算出来），
    # 名字会被省略成一串「…」，像素级断言全是假的。先 show 让布局落定。
    w.show()
    app.processEvents()

    name_cell = table.cellWidget(0, 1)
    ok("任务名称格有链接标签", name_cell is not None)
    name_labels = name_cell.findChildren(QLabel) if name_cell else []
    ok("任务名称用 QLabel 渲染", len(name_labels) == 1, str(len(name_labels)))
    name_label = name_labels[0]
    # 下划线是 paintEvent 自绘的（字体下划线间距不可调），只能按像素验：
    # 把标签渲染出来，找「主色像素最多的一行」——那必是那条横线。
    from PySide6.QtGui import QFontMetrics, QPixmap

    # 离屏下标签还没参与布局（高度只有字高），下划线会被裁在框外；
    # 先按真实行高给它尺寸，再渲染
    name_label.resize(max(name_label.width(), 160), ROW_HEIGHT)
    pm = QPixmap(name_label.size())
    pm.fill(Qt.white)
    name_label.render(pm)
    img = pm.toImage()
    # ⚠️ 按「非白像素」而不是「等于主色」统计：1px 的线落在半像素上会被
    # 抗锯齿摊成两行半透明，颜色早就不是纯主色了，比颜色必然假失败。
    longest = 0
    for y in range(img.height()):
        hits = 0
        for x in range(img.width()):
            p = img.pixel(x, y)
            if (
                abs(((p >> 16) & 255) - 255)
                + abs(((p >> 8) & 255) - 255)
                + abs((p & 255) - 255)
                > 60
            ):
                hits += 1
        longest = max(longest, hits)
    text_w = QFontMetrics(name_label.font()).horizontalAdvance(name_label.text())
    ok(
        "任务名称下方有自绘下划线",
        longest >= max(12, text_w * 0.9),
        f"最长着色行 {longest}px 文字宽 {text_w}px "
        f"label={name_label.width()}x{name_label.height()} pm={pm.size().toTuple()}",
    )
    ok(
        "任务名称用主色",
        name_label.linkColor().name().lower() == T.ACCENT.lower(),
        name_label.linkColor().name(),
    )
    ok(
        "任务名称是手型光标",
        name_label.cursor().shape() == Qt.CursorShape.PointingHandCursor,
    )
    ok(
        "任务名称容器锁定整行高",
        name_cell.height() == ROW_HEIGHT,
        f"{name_cell.height()} 期望 {ROW_HEIGHT}",
    )
    # ⚠️ 名称格的 item 不能省：select_task() 靠它取 UserRole 定位行
    ok(
        "名称格仍保留数据项（select_task 依赖）",
        table.item(0, 1) is not None
        and table.item(0, 1).data(Qt.UserRole) is not None,
    )
    # ⚠️ 单元格控件是透明的：item 里再写一遍名字就是「一条名字显示两次」
    ok(
        "名称只在标签里画一次（item 文本为空）",
        table.item(0, 1).text() == "" and name_label.text() != "",
        f"item={table.item(0, 1).text()!r} label={name_label.text()!r}",
    )

    # 点击标签 → 用**该行**的 id 跳详情（不是写死的某一个）
    got: list[str] = []
    w.list_page.table.open_detail.connect(got.append)
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5.0, 5.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    name_label.mousePressEvent(press)
    ok(
        "点击任务名称跳详情",
        got == [table.item(0, 1).data(Qt.UserRole)],
        str(got),
    )
    # 不 accept 的话事件会冒泡到视口，cellClicked 再跳一次
    ok("标签点击已 accept（不会重复触发）", press.isAccepted())
    w.list_page.table.open_detail.disconnect(got.append)

    name_label.enterEvent(QEnterEvent(QPointF(1, 1), QPointF(2, 2), QPointF(3, 3)))
    ok(
        "hover 变深",
        name_label.linkColor().name().lower() == T.ACCENT_HOVER.lower(),
        name_label.linkColor().name(),
    )
    name_label.leaveEvent(QEvent(QEvent.Type.Leave))
    ok(
        "移出恢复主色",
        name_label.linkColor().name().lower() == T.ACCENT.lower(),
        name_label.linkColor().name(),
    )
    # 验完立刻收起：窗口一直可见会改变后续模块（extract 读子进程日志）的事件时序
    w.hide()

    # 详情打开（后续模块都基于这个已打开的详情页）
    w._open_detail(tid)
    ok("点击详情进入任务页", d.task_id == tid)
