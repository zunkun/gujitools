# -*- coding: utf-8 -*-
"""分页条位置（用户 2026-11-18：分页应该在右边，不是挤在中间） / 勾 0 条不算错误（用户 2026-11-18）：落回空勾选 ⇒ 成员原样保留 / 成员表格：高度自适应 + 10 条/页分页（用户 2026-11-18） / 5. 创建页：任务类型 + 名称 / 单选语义 + 切类型换内容（用户 2026-11-17 第 3 条） / 成员「详情」＝**非模态预览窗**（用户 2026-11-17：不跳转、不挡页面、 / 6. 列表页建聚合任务 + 标记 / 后台汇集：成员产物按顺序拼进聚合任务，详情页自动重载 / 重新汇集（成员重跑之后）：页面上那个按钮走的就是这条链路"""

from typing import Any


def run(st: Any) -> None:
    from desktop.components.aggregate_create_panel import (
        MEMBER_HEADER_HEIGHT,
        MEMBER_PAGE_SIZE,
        AggregateCreatePanel,
        AggregateMemberPicker,
        DEFAULT_START_STAGE,
    )
    from qfluentwidgets import BodyLabel, CheckBox, PushButton
    from desktop.pages.createtask.page import (
        CreateTaskPage,
        ROUTE_CREATE,
        TAB_AGGREGATE,
        TAB_TASK,
    )
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QLabel, QScrollArea
    from PySide6.QtTest import QTest
    from desktop.ui.widgets import SegmentedToggle, StatusChip
    from desktop.utils.files import list_stage_images
    from tests.selftests._context import ok, pump
    from tests.selftests._context import wait_until
    st.picker.resize(900, 600)
    st.picker.show()
    pump(st.app)
    _pg = st.picker.pagination
    _pg_right = _pg.mapTo(st.picker, QPoint(_pg.width(), 0)).x()
    ok(
        "弹窗：分页条占满整行、右沿顶到弹窗内容区右缘（翻页控件靠右）",
        _pg.x() <= 2
        and _pg.width() >= 860
        and abs(_pg_right - st.picker.width()) <= 4,
        f"x={_pg.x()} w={_pg.width()} 右沿={_pg_right} 弹窗宽={st.picker.width()}",
    )
    st.picker.hide()
    ok(
        "弹窗：表头复选框存在且盖在表头第 0 列内",
        st.picker.header_check.parent() is st.picker.table.horizontalHeader()
        and st.picker.header_check.x() >= 0
        and st.picker.header_check.x() + st.picker.header_check.width()
        <= st.picker.table.horizontalHeader().sectionSize(0),
        f"pos=({st.picker.header_check.x()},{st.picker.header_check.y()}) "
        f"size={st.picker.header_check.width()}x{st.picker.header_check.height()}",
    )
    ok(
        "弹窗：勾了一条 ⇒ 表头复选框不亮（全勾才亮）",
        not st.picker.header_check.isChecked(),
        str(st.picker.header_check.isChecked()),
    )
    st.picker.header_check.setChecked(True)  # 走真信号链（同手点）
    ok(
        "弹窗：表头勾选 ⇒ 本页全部行都进 _checked",
        st.picker.checked_ids() == [f"90{i:02d}" for i in range(15, 0, -1)],
        str(st.picker.checked_ids()),
    )
    row_boxes = [
        st.picker.table.cellWidget(r, 0).findChildren(CheckBox)[0].isChecked()
        for r in range(st.picker.table.rowCount())
    ]
    ok(
        "弹窗：表头勾选 ⇒ 每行的勾选框都亮",
        all(row_boxes),
        str(row_boxes),
    )
    ok(
        "弹窗：全勾后表头复选框保持亮",
        st.picker.header_check.isChecked(),
        str(st.picker.header_check.isChecked()),
    )
    st.picker.set_checked("9003", False)
    ok(
        "弹窗：单独点掉一行 ⇒ 表头复选框回灭",
        not st.picker.header_check.isChecked(),
        str(st.picker.header_check.isChecked()),
    )
    # ⚠️ 表头取消走的是 toggled 信号链：此刻表头已被回显成灭（回显走
    # blockSignals），先补回 9003 让它回亮，取消才有信号可发。
    st.picker.set_checked("9003", True)
    ok(
        "弹窗：补回单独点掉的那行 ⇒ 表头复选框回亮（全勾才亮）",
        st.picker.header_check.isChecked(),
        str(st.picker.header_check.isChecked()),
    )
    st.picker.header_check.setChecked(False)
    ok(
        "弹窗：表头取消 ⇒ 本页全部行的勾都清掉",
        st.picker.checked_ids() == [],
        str(st.picker.checked_ids()),
    )

    # 窗口功能（用户 2026-11-18）：「选择子任务弹窗要显示窗口功能，放大缩小」
    # ⚠️ 只建外壳不 show/exec —— 离屏下 exec() 会卡住
    _dlg = st.picker.build_dialog(None)
    ok(
        "弹窗外壳：标题栏带最小化/最大化按钮",
        bool(_dlg.windowFlags() & Qt.WindowType.WindowMinMaxButtonsHint),
        str(_dlg.windowFlags()),
    )
    ok(
        "弹窗外壳：最小尺寸小于开窗尺寸（小屏上缩得回来）",
        _dlg.minimumWidth() < 1040 and _dlg.minimumHeight() < 720,
        f"{_dlg.minimumWidth()}x{_dlg.minimumHeight()}",
    )
    ok(
        "弹窗外壳：仍是模态（放大缩小不能顺手漏掉模态）",
        _dlg.isModal(),
        str(_dlg.isModal()),
    )
    _dlg.deleteLater()
    st.picker.deleteLater()
    _many = [st.repo.create_task(None, "", f"成员{i:02d}") for i in range(1, 13)]
    paged = AggregateCreatePanel(st.repo)
    _row_h = paged.MEMBER_ROW_HEIGHT
    _h = lambda rows: MEMBER_HEADER_HEIGHT + rows * _row_h + 2  # noqa: E731
    paged.set_members(_many)
    ok(
        "表格：12 个成员 ⇒ 第 1 页只画 10 行、出现分页条",
        paged.member_table.rowCount() == MEMBER_PAGE_SIZE == 10
        and not paged.member_pager.isHidden(),
        f"{paged.member_table.rowCount()} 行 / 分页条隐藏="
        f"{paged.member_pager.isHidden()}",
    )
    ok(
        "表格：高度 = 表头 + 当前页行数×行高（不是固定 10 行高）",
        paged.member_table.height() == _h(10),
        f"{paged.member_table.height()} vs {_h(10)}",
    )
    paged._on_member_page_changed(2)
    ok(
        "表格：翻到第 2 页只剩 2 行，表格跟着变矮",
        paged.member_table.rowCount() == 2
        and paged.member_table.height() == _h(2),
        f"{paged.member_table.rowCount()} 行 / {paged.member_table.height()}",
    )
    # 行内按钮带的是**成员下标**（跨页别错位：第 2 页第 1 行 = 第 11 个成员）
    _second_page_del = next(
        b for b in paged.member_table.cellWidget(0, 3).findChildren(PushButton)
        if b.text() == "删除"
    )
    _second_page_del.click()
    ok(
        "表格：第 2 页行内「删除」删的是第 11 个成员（下标没有错位）",
        len(paged.members()) == 11 and _many[10] not in paged.members(),
        f"{len(paged.members())} 个 / 删掉的是 {_many[10]} 还在?"
        f"{_many[10] in paged.members()}",
    )
    paged.set_members(_many[:3])
    ok(
        "表格：只有 3 个成员 ⇒ 只占 3 行高、分页条不出现",
        paged.member_table.rowCount() == 3
        and paged.member_table.height() == _h(3)
        and paged.member_pager.isHidden(),
        f"{paged.member_table.rowCount()} 行 / {paged.member_table.height()} / "
        f"隐藏={paged.member_pager.isHidden()}",
    )
    # 勾 0 条不算错误（用户 2026-11-18：选择子任务弹窗里勾 0 条不该报错）
    _before_members = paged.members()
    paged._apply_checked([])
    ok(
        "表格：弹窗勾 0 条 ⇒ 成员原样保留（不报错、不清空）",
        paged.members() == _before_members == _many[:3],
        str(paged.members()),
    )
    paged._apply_checked(list(reversed(_many[:3])))
    ok(
        "表格：弹窗落回勾选 ⇒ 已排好的顺序不被冲掉（保序保留）",
        paged.members() == _many[:3],
        str(paged.members()),
    )
    paged.deleteLater()
    st.page = CreateTaskPage(st.repo)
    # ⚠️ 创建页外层是 QScrollArea（用户 2026-11-18：整页纵向滚动），只
    #    ``layout().activate()`` 不会布到滚动内容里 ⇒ 必须 show + pump 一次，
    #    否则下面量出来的 y 全是 0/1。
    st.page.resize(1400, 800)
    st.page.show()
    pump(st.app)
    st.page.layout().activate()
    st._ts = st.page.type_selector
    st._boxes = st._ts._boxes
    ok(
        "创建页：任务类型是**复选框**（常规任务/聚合任务），不是胶囊",
        st._ts.keys() == [TAB_TASK, TAB_AGGREGATE]
        and [st._boxes[k].text() for k in (TAB_TASK, TAB_AGGREGATE)]
        == ["常规任务", "聚合任务"]
        and all(isinstance(b, CheckBox) for b in st._boxes.values())
        and not isinstance(st._ts, SegmentedToggle),
        f"{[b.text() for b in st._boxes.values()]} / {type(st._ts).__name__}",
    )
    ok(
        "创建页：默认选中「常规任务」且内容区是常规面板",
        st.page.current_tab() == TAB_TASK and st.page._stack.currentIndex() == 0,
        f"{st.page.current_tab()} / {st.page._stack.currentIndex()}",
    )
    # 用户 2026-11-17 指定顺序：**任务类型 → 任务名称 → 后续内容**
    _type_y = st._ts.mapTo(st.page, QPoint(0, 0)).y()
    _name_y = st.page.name_edit.mapTo(st.page, QPoint(0, 0)).y()
    ok(
        "创建页：任务类型排在任务名称之上（顺序＝类型/名称/后续内容）",
        _type_y < _name_y,
        f"类型 y={_type_y} / 名称 y={_name_y}",
    )
    # 复选框一行只占自己文案的宽度，不许被拉成"跟页面一样宽"
    ok(
        "创建页：任务类型一行不被拉满整页",
        st._ts.width() <= 320 and st._ts.width() < st.page.width() // 3,
        f"{st._ts.width()} / 页面 {st.page.width()}",
    )
    # 用户 2026-11-17：字段名（任务类型/任务名称/子任务/上传文件…）要加粗
    _wanted = ["任务类型：", "任务名称：", "上传文件：", "子任务：", "起始节点："]
    _found = {l.text(): l for l in st.page.findChildren(BodyLabel)}
    _not_bold = [t for t in _wanted if t in _found and not _found[t].font().bold()]
    ok(
        "创建页：字段名一律加粗（任务类型/任务名称/上传文件/子任务/起始节点）",
        all(t in _found for t in _wanted) and not _not_bold,
        f"缺={[t for t in _wanted if t not in _found]} 未加粗={_not_bold}",
    )
    # 用户 2026-11-18：整页纵向滚动；底部流程图**不再自带滚动条**，整张铺开
    ok(
        "创建页：整页外层是可纵向滚动的 QScrollArea",
        isinstance(st.page.scroll, QScrollArea) and st.page.scroll.widgetResizable(),
        str(type(getattr(st.page, "scroll", None)).__name__),
    )
    _ep = st.page.panel._editor_panel
    ok(
        "创建页：流程图不自带滚动条（画面交给页面滚，一次看全）",
        _ep is not None and _ep._scroll is None,
        f"panel={type(_ep).__name__ if _ep is not None else None}",
    )
    st.page.resize(1200, 520)
    pump(st.app)
    _vbar = st.page.scroll.verticalScrollBar()
    ok(
        "创建页：内容比窗口高时出现纵向滚动（滚轮能翻）",
        _vbar.maximum() > 0,
        f"最大滚动量={_vbar.maximum()}（页面高 {st.page.height()}）",
    )
    _switched: list[str] = []
    st._ts.current_changed.connect(_switched.append)
    QTest.mouseClick(st._boxes[TAB_AGGREGATE], Qt.MouseButton.LeftButton)
    ok(
        "创建页：勾「聚合任务」⇒ 常规任务自动灭（单选）+ 内容换到聚合面板",
        st.page.current_tab() == TAB_AGGREGATE
        and st._boxes[TAB_TASK].isChecked() is False
        and st.page._stack.currentWidget() is st.page.aggregate_panel,
        f"{st.page.current_tab()} / {[b.isChecked() for b in st._boxes.values()]}",
    )
    QTest.mouseClick(st._boxes[TAB_AGGREGATE], Qt.MouseButton.LeftButton)
    ok(
        "创建页：点掉当前唯一勾选不生效（恒有一个类型被选中）",
        st.page.current_tab() == TAB_AGGREGATE and st._boxes[TAB_AGGREGATE].isChecked(),
        f"{st.page.current_tab()} / {st._boxes[TAB_AGGREGATE].isChecked()}",
    )
    ok(
        "创建页：用户点击才发 current_changed（每次切换一条）",
        _switched == [TAB_AGGREGATE],
        str(_switched),
    )
    # 程序化切：不发信号，但仍换内容区
    st.page.select_tab(TAB_TASK)
    ok(
        "创建页：程序化切回「常规任务」⇒ 内容区回常规面板且不发信号",
        st.page._stack.currentWidget() is st.page.panel and _switched == [TAB_AGGREGATE],
        f"{st.page._stack.currentIndex()} / {_switched}",
    )
    # 追一个类型：清单延长，界面自己多出一个复选框（"后续还可以加"）
    st._ts.add_item("other", "其他任务")
    ok(
        "创建页：任务类型可扩展（加一项就多一个复选框）",
        st._ts.keys() == [TAB_TASK, TAB_AGGREGATE, "other"]
        and st._ts.box("other") is not None,
        str(st._ts.keys()),
    )
    st.page.select_tab(TAB_TASK)
    # 聚合提交从页面冒出去（带上任务名）
    emitted: list = []
    st.page.aggregate_requested.connect(
        lambda m, s, n, d: emitted.append((list(m), s, n, d))
    )
    st.page.aggregate_panel.set_members([st.tid_a])
    st.page.set_name("全书合并")
    st.page._on_aggregate_submit([st.tid_a], ["imposition"], None)
    ok(
        "创建页：聚合提交带上任务名与各成员节点",
        emitted == [([st.tid_a], ["imposition"], "全书合并", None)],
        str(emitted),
    )
    st.page.aggregate_panel.detail_requested.emit(st.tid_a)      # 走真实信号链
    _dlg = st.page._previews.get(st.tid_a)
    ok(
        "创建页：点「详情」弹出任务详情窗（不再切走创建页）",
        _dlg is not None and _dlg.isVisible(),
        str(_dlg),
    )
    ok(
        "创建页：详情窗**非模态**（不挡创建页，也就不会「当当」响）",
        _dlg is not None and _dlg.isModal() is False,
        f"modal={getattr(_dlg, 'isModal', lambda: None)()}",
    )
    ok(
        "创建页：详情窗里是真任务详情页、且开得够宽",
        _dlg is not None
        and _dlg.page.task_id == st.tid_a
        and _dlg.width() >= 1000,
        f"{getattr(getattr(_dlg, 'page', None), 'task_id', None)} / "
        f"{getattr(_dlg, 'width', lambda: 0)()}",
    )
    ok(
        "创建页：同一子任务不重复开窗（再点只前置）",
        st.page.open_member_preview(st.tid_a) is _dlg and len(st.page._previews) == 1,
        str(len(st.page._previews)),
    )
    ok(
        "创建页：详情窗收起「查看/编辑流程」（预览窗没有壳层可跳）",
        _dlg is not None and _dlg.page.flow_button.isHidden(),
        "",
    )
    ok(
        "创建页：详情窗标题栏带最小化/最大化（用户 2026-11-18 要能放大缩小）",
        _dlg is not None
        and bool(_dlg.windowFlags() & Qt.WindowType.WindowMinMaxButtonsHint),
        str(getattr(_dlg, "windowFlags", lambda: None)()),
    )
    st.page.reset()
    ok(
        "创建页：reset 回「常规任务」、聚合面板清空、预览窗跟着收",
        st.page._stack.currentIndex() == 0
        and st.page.aggregate_panel.members() == []
        and st.page._previews == {},
        f"{st.page._stack.currentIndex()} / {len(st.page._previews)}",
    )
    st.page.deleteLater()
    for tid, names in ((st.tid_a, ["1.jpg", "2.jpg"]), (st.tid_b, ["1.jpg"])):
        st._make_images(st.repo.task_dir(tid) / "stages" / "detect", names)
        st._make_images(
            st.repo.task_dir(tid) / "stages" / "rembg",
            [n.replace(".jpg", ".png") for n in names],
        )
        run_id = st.repo.create_stage_run(tid, "rembg", {})
        st.repo.finish_stage(tid, run_id, "success")

    st.opened: list = []
    st.w.list_page.open_detail.connect(st.opened.append)
    st.w.list_page.start_create_aggregate(
        [st.tid_a, st.tid_b], ["rembg", "rembg"], "合并本", None
    )
    pump(st.app, times=8)
    ok("列表页：聚合创建后自动进详情", len(st.opened) >= 1, str(st.opened))
    st.agg_final = st.opened[-1]
    newest = st.repo.get_task(st.agg_final)
    ok(
        "列表页：聚合任务真的落库（含逐成员节点）",
        newest is not None
        and newest.get("kind") == "aggregate"
        and newest.get("members") == [st.tid_a, st.tid_b]
        and newest.get("member_stages") == ["rembg", "rembg"],
        str(newest),
    )
    ok(
        "列表页：详情页能打开聚合任务（set_task 不崩）",
        st.w.detail_page.task_id == st.agg_final,
        st.w.detail_page.task_id,
    )
    from tests.selftests._context import wait_until

    agg_out = st.repo.task_dir(st.agg_final) / "stages" / "rembg"
    agg_entry = st.repo.task_dir(st.agg_final) / "stages" / "input"

    def _out_names() -> list:
        return [p.name for p in list_stage_images(agg_out)]
    st._out_names = _out_names

    def _entry_names() -> list:
        return [p.name for p in list_stage_images(agg_entry)]

    ok(
        "后台汇集：成员**产出**按顺序落进聚合任务（001_1/001_2/002_1）",
        wait_until(
            st.app,
            lambda: st._out_names() == ["001_1.png", "001_2.png", "002_1.png"],
            timeout=15.0,
        ),
        str(st._out_names()),
    )
    ok(
        "后台汇集：成员的**输入**（检测裁图）也按顺序搬进入口目录"
        "（2026-11-18 晚口径：x 的输入做起点输入）",
        wait_until(
            st.app,
            lambda: _entry_names()
            == ["001_1.jpg", "001_2.jpg", "002_1.jpg"],
            timeout=15.0,
        ),
        str(_entry_names()),
    )
    ok(
        "后台汇集：起点（去底色）在步骤条上显示已完成",
        wait_until(st.app, lambda: st.repo.stage_states(st.agg_final)["rembg"]["completed"],
                   timeout=10.0),
        str(st.repo.stage_states(st.agg_final)["rembg"]),
    )
    ok(
        "后台汇集：详情页已重载出页面清单（不是空任务）",
        wait_until(st.app, lambda: len(getattr(st.w.detail_page, "pages", []) or []) == 3,
                   timeout=10.0),
        str(len(getattr(st.w.detail_page, "pages", []) or [])),
    )
    ok(
        "后台汇集：聚合任务不催用户上传输入（入口输入按钮全藏）",
        st.w.detail_page._entry_input_kind() == "",
        st.w.detail_page._entry_input_kind(),
    )
    ok(
        "后台汇集：完成后「正在汇集」标记已撤（能点执行）",
        not st.w.detail_page._aggregate_pending(),
        "",
    )
    st._make_images(st.repo.task_dir(st.tid_b) / "stages" / "detect", ["2.jpg"])
    st._make_images(st.repo.task_dir(st.tid_b) / "stages" / "rembg", ["2.png"])
    st.w.detail_page._run_aggregate_refresh(st.agg_final)
    ok(
        "重新汇集：成员新增的页被搬进来（002_2 出现）",
        wait_until(
            st.app,
            lambda: st._out_names()
            == ["001_1.png", "001_2.png", "002_1.png", "002_2.png"],
            timeout=15.0,
        ),
        str(st._out_names()),
    )
    ok(
        "重新汇集：按钮对聚合任务可见（普通任务恒藏）",
        not st.w.detail_page.aggregate_refresh_button.isHidden(),
        str(st.w.detail_page.aggregate_refresh_button.isHidden()),
    )

