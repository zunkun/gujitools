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

    # 详情打开（后续模块都基于这个已打开的详情页）
    w._open_detail(tid)
    ok("点击详情进入任务页", d.task_id == tid)
