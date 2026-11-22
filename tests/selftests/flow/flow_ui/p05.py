# -*- coding: utf-8 -*-
"""第 10 章（续）：创建任务不关窗口 + 空壳任务。"""

from __future__ import annotations

from ._helpers import _label_text_color, _viewer_entry_button


def run(st) -> None:
    from tests.selftests._context import ok
    ok("点「创建任务」**不关任何窗口**（用户 2026-10-06：创建成功但 GUI 不见了）",
       _submit_keeps_window(st.ctx_page))
    _check_shell_task(st.store_, st.ctx.pdf, st.app)


def _submit_keeps_window(create_page) -> bool:
    """点「创建任务」后宿主窗口仍在（回归钉子）。

    ⚠️ 这条对应一个真事故：``CreateTaskPanel.submit`` 里原来有
    ``self.window().close()``——面板被内嵌进创建任务页之后，``self.window()``
    返回的是**主窗口**，于是点一次"创建任务"把整个程序关掉（用户 2026-10-06
    报："创建任务成功，但是程序 gui 不可见了"）。

    验法：**只连一个收集器，不让它真的建任务**（那要改数据、要PDF）。收集器
    连上就把 ``submitted`` 的其它接收者挤掉了——PySide 的 ``connect`` 是多
    播的，所以第一个连的收集器独占这条信号，后续 ``shell`` 那边（这里是
    ``create_requested``）听不到。窗口在点之前后在同一个事件循环里都比一遍。
    """
    panel = create_page.panel
    win = create_page.window()
    before = win.isVisible()
    fired = []
    panel.submitted.connect(lambda: fired.append(1))
    panel.submit()
    return bool(fired) and win.isVisible() == before

def _check_shell_task(store, pdf, app) -> None:
    """空壳任务（创建时没给 PDF）的落库与补选入口。"""
    from desktop.ui import theme as T
    from tests.selftests._context import ok

    # 没给源文件 + 没给名字 ⇒ 名字回落「任务#实际号」
    tid = store.create_task(None, "", "")
    record = store.get_task(tid) or {}
    ok("没给PDF 时建得出任务（PDF 非必需）", bool(tid) and record.get("id") == tid)
    ok("没给名字时默认名是「任务#<实际任务号>」",
       record.get("name") == f"任务#{tid}", repr(record.get("name")))
    ok("⚠️ 名字里的序号用的是**实际分配到的号**（不是预测值）",
       record.get("name", "").endswith(tid), str(record.get("name")))
    ok("没给 PDF 时source_path 存空串（不是 '.' 那类假路径）",
       record.get("source_path") == "", repr(record.get("source_path")))

    # 有名字 ⇒ 照用；名字里给的序号不作数
    tid2 = store.create_task(None, "", "我自己起的名字")
    ok("给了名字就用给的", (store.get_task(tid2) or {}).get("name")
       == "我自己起的名字")
    # 给了 PDF ⇒ 索引里有路径
    tid3 = store.create_task(pdf, "h-shell", "有源文件")
    ok("给了 PDF 就记下路径",
       (store.get_task(tid3) or {}).get("source_path") == str(pdf))

    # 补选：set_task_source 把文件收进任务目录并改索引
    ok("set_task_source 拒绝不存在的文件",
       store.set_task_source(tid, pdf.parent / "没有这个.pdf") is False)
    ok("set_task_source 拒绝不存在的任务",
       store.set_task_source("9999", pdf) is False)
    ok("补选 PDF 成功：索引更新 + 副本落进任务目录",
       store.set_task_source(tid, pdf)
       and (store.get_task(tid) or {}).get("source_path") == str(pdf)
       and store.source_copy_path(tid) is not None)
    # 清空名字回落：空壳任务（没源）⇒ 任务#号；不是留空
    store.rename_task(tid2, "  ")
    ok("空壳任务清空名字回落到「任务#号」（不是留空、也不是文件名）",
       (store.get_task(tid2) or {}).get("name") == f"任务#{tid2}",
       str((store.get_task(tid2) or {}).get("name")))
    # 详情页对空壳任务的处理
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.steps.flow import default_flow_path

    empty_tid = store.create_task(None, "", "")
    probe = TaskDetailPage(store)
    probe.resize(1080, 720)
    probe.show()
    try:
        app.processEvents()
        # ⚠️ 离屏绝不能真弹模态（项目硬规则）：换成记录器，顺便当断言材料
        from tests.selftests._context import silence_source_prompt

        prompt_calls = silence_source_prompt(probe)
        ok("空壳任务能进详情页（不崩、不被拒）",
           probe.set_task(empty_tid) is True)
        prompt = probe._source_prompt
        ok("进空壳任务详情时**弹出**了「缺源 PDF」提示层（用户 2026-10-06）",
           prompt is not None and prompt.isVisible(),
           f"prompt={prompt} calls={len(prompt_calls)}")
        assert prompt is not None  # 上一条 ok 已断言提示层已弹出
        # ---- 用户截图三条：遮罩完整 / 盖住流程条 / 按钮在遮罩之上 ----
        geo = prompt.geometry() if prompt else None
        # ⚠️ 「内容区上沿」用**根布局里主体那一行**（页头之后那项）的位置，
        #    **别用步骤条自己的 geometry** —— 刚被 _rebuild_step_bar 换掉、
        #    布局还没定位，读出来是 QWidget 默认的 (0,0,640,480)，比出来
        #    永远是 0（与 _content_top 里记的同一个坑）。
        body_item = probe._root_layout.itemAt(probe._step_bar_row + 1)
        content_top = body_item.geometry().y() if body_item else 0
        # ⚠️ 用 ``y() + height()`` 比，**别用 QRect.bottom()**——那是
        #    **包含式**的（= top+height-1），跟高度比永远差 1。
        ok("遮罩**铺满内容区**（用户：mask 不完整只有一部分）",
           geo is not None
           and geo.x() == 0 and geo.width() == probe.width()
           and geo.y() + geo.height() == probe.height(),
           f"mask={geo.getRect() if geo else None} page={probe.rect().getRect()} "
           f"content_top={probe._content_top()}")
        ok("遮罩**盖住流程条**（用户：mask 没覆盖流程图）",
           geo is not None and geo.y() <= content_top,
           f"mask.y={geo.y() if geo else None} content_top={content_top}")
        btn = probe.source_button
        ok("页头操作按钮**留在遮罩之上**且可用（用户第3 条）",
           btn.geometry().bottom() <= (geo.top() if geo else 0)
           and btn.isEnabled(),
           f"btn={btn.geometry().getRect()} mask.top={geo.top() if geo else None}")
        ok("提示层**非模态**（模态会把页头按钮的事件全吃掉）",
           prompt is not None
           and prompt.windowModality() == prompt.windowModality().NonModal,
           str(prompt.windowModality()) if prompt else "")
        ok("提示卡片有内容且不是被压扁的空白条",
           prompt is not None
           and prompt.card.height() > 80
           and prompt.card.layout().count() >= 4,
           f"h={prompt.card.height()} n={prompt.card.layout().count()}"
           if prompt else "")
        # ---- 按钮**真的点得动**（用户 2026-10-06："那个导入按钮，你不能把
        #      它给遮住啊"）。上面那些只验了"看起来可点"，这里真点一下。----
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        picked_by_button = []
        real_pick = probe._on_pick_source
        probe._on_pick_source = lambda: picked_by_button.append(1)
        try:
            QTest.mouseClick(probe.source_button, Qt.MouseButton.LeftButton)
            app.processEvents()
            QTest.mouseClick(probe.source_button, Qt.MouseButton.LeftButton)
            app.processEvents()
        finally:
            probe._on_pick_source = real_pick
        ok("提示层显示时，页头 PDF 按钮**点了真的有反应**（没被遮罩吃掉）",
           len(picked_by_button) == 2,
           f"picked={len(picked_by_button)}")
        ok("点了按钮后提示层**不自己消失**（用户可以接着补文件）",
           prompt is not None and prompt.isVisible())
        # ---- 点内容区（被遮罩覆盖的地方）：吃掉点击、但**不关提示** ----
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF, QEvent as QEventEnum

        ev = QMouseEvent(
            QEventEnum.Type.MouseButtonPress, QPointF(prompt.width() / 2,
                                                prompt.height() / 2),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        prompt.mousePressEvent(ev)
        app.processEvents()
        ok("点被遮住的内容区**不会关掉提示**（否则用户以为关掉了、按钮又没反应）",
           prompt.isVisible())
        # ---- **第二次进入仍要弹**（用户 2026-10-06："没有选择源文件，为何弹窗
        #      也没有了，每次进入都要检测"）----
        # 先模拟用户点了「稍后再说」（提示层被收起），再重新进同一个任务
        prompt.dismiss()
        app.processEvents()
        ok("收起来之后提示层确实不可见", not prompt.isVisible())
        prompt_calls.clear()
        probe.set_task(empty_tid)
        app.processEvents()
        ok("**再次进入同一个缺源任务，提示层照样弹出**（每次进入都检测）",
           prompt.isVisible(),
           f"visible={prompt.isVisible()}")
        # ---- 卡片**高度够**（用户 2026-10-06：文字显示不完整）----
        ok("提示卡片高度容得下所有文字（wordWrap 换行后的真实高度）",
           prompt.card.height() >= prompt.card.box.sizeHint().height(),
           f"h={prompt.card.height()} need={prompt.card.box.sizeHint().height()}")
        # ---- 卡片能**拖动**（用户 2026-10-06：不可以移动）----
        from PySide6.QtCore import QEvent as _QE, QPoint, QPointF
        from PySide6.QtGui import QMouseEvent as _QMouseEvent

        origin = prompt.card.pos()
        center = prompt.card.rect().center()
        for _kind, _pos, _btn, _btns in (
            (_QE.Type.MouseButtonPress, QPointF(center),
             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (_QE.Type.MouseMove, QPointF(center + QPoint(90, 45)),
             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton),
            (_QE.Type.MouseButtonRelease, QPointF(center + QPoint(90, 45)),
             Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton),
        ):
            app.sendEvent(prompt.card, _QMouseEvent(
                _kind, _pos, _btn, _btns, Qt.KeyboardModifier.NoModifier))
        app.processEvents()
        ok("提示卡片**可以拖动**（按住卡片空白处）",
           prompt.card.pos() != origin,
           f"{origin} -> {prompt.card.pos()}")
        prompt._move_card(QPoint(99999, 99999))
        ok("卡片拖不出提示层范围（会被夹住）",
           prompt.card.x() + prompt.card.width() <= prompt.width()
           and prompt.card.y() + prompt.card.height() <= prompt.height()
           and prompt.card.x() >= 0 and prompt.card.y() >= 0,
           f"{prompt.card.pos()} in {prompt.width()}x{prompt.height()}")
        # ---- 卡片上两个按钮都**真的能点**（第一版把它们的按下吞了）----
        prompt.card_host_center()
        dis = []
        prompt.dismissed.connect(lambda: dis.append(1))
        QTest.mouseClick(prompt.later_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        ok("卡片上「稍后再说」**点得动**（过滤器不许吞按钮的按下）",
           bool(dis), f"dismissed={len(dis)}")
        # ⚠️⚠️ 收集器**直连 ``prompt.picked``**，**不能**靠替换
        #    ``probe._on_pick_source`` —— Qt 在 ``connect`` 的那一刻就把槽
        #    绑成当时的 callable 了，之后改对象属性对已连的信号**无效**
        #    （而真槽会真的去弹模态文件框）。我先写成替换属性，自测里
        #    「picked=0」假红了一轮才发现。
        picked = []
        # ⚠️ 信号**带一个参**（``pick_kind``：要目录框还是文件框，用户
        #    2026-10-06"改成选择图片目录"）⇒ 收集器必须**收下这个参**，
        #    写 `lambda: ...` 会 TypeError（PySide6 不像 PyQt 那样容忍）。
        prompt.picked.connect(lambda kind="": picked.append(kind))
        prompt.show_prompt()
        # ⚠️ ``show()`` 是**异步**的：不跑一圈事件循环，控件还没真正显示，
        #    这时 ``mouseClick`` 点上去是空的。
        app.processEvents()
        QTest.mouseClick(prompt.pick_button, Qt.MouseButton.LeftButton)
        app.processEvents()
        ok("卡片上主按钮**点得动**", bool(picked), f"picked={len(picked)}")
        ok("默认（缺 PDF）走**文件框**", picked == ["files"], str(picked))
        ok("空壳任务：source_path 是 None（不是 Path('') 那类假路径）",
           probe.source_path is None, repr(probe.source_path))
        ok("空壳任务：页头写「尚未选择 PDF」",
           "尚未选择" in probe.source_label.text(), probe.source_label.text())
        ok("空壳任务：页头有补选 PDF 的入口",
           hasattr(probe, "source_button")
           and not probe.source_button.isHidden()
           and "PDF" in probe.source_button.toolTip(),
           probe.source_button.toolTip()
           if hasattr(probe, "source_button") else "无按钮")
        ok("补选按钮的提示随「有没有源文件」变",
               probe._refresh_source_actions() is None
               and "还没有" in probe.source_button.toolTip(),
               probe.source_button.toolTip())
        # ---- 缺源 PDF 时：按钮高亮 + 页头红字（用户 2026-10-06）----
        ok("缺源 PDF 时判据成立（该催用户补）",
           probe._missing_source() is True)
        ok("缺源文件时页头出红字提示",
           not probe.source_warning.isHidden()
           and "尚未选择源文件" in probe.source_warning.text(),
           probe.source_warning.text())
        ok("红字是**红**的（原生 QLabel 走 palette；qfluent 标签走 setTextColor）",
           _label_text_color(probe.source_warning).upper()
           == T.DANGER.upper(),
           _label_text_color(probe.source_warning))
        style = probe.source_button.styleSheet()
        ok("缺源 PDF 时补选按钮**高亮**（红边框 + 淡红底）",
           T.DANGER in style and T.DANGER_SOFT in style, style[:80])
        # 换源文件前的确认：判据可被替身覆盖（离屏自测绝不真弹模态）
        ok("空壳任务没有任何产物 ⇒ 换源文件不必问（静默换）",
           probe._source_replace_is_blocked(pdf) is False)
        # 造一点产物出来 ⇒ 该问
        (store.task_dir(empty_tid) / "pages.json").write_text("[]",
                                                              encoding="utf-8")
        ok("有中间产物时换源文件需要确认（会清掉旧产物）",
           probe._source_replace_is_blocked(pdf) is True)
        ok("有产物判定看得见：_has_task_artifacts 能认出 pages.json",
           probe._has_task_artifacts() is True)
        (store.task_dir(empty_tid) / "pages.json").unlink()
        # 换源文件会清产物
        (store.task_dir(empty_tid) / "runs.json").write_text("[]",
                                                             encoding="utf-8")
        # ⚠️ 造两个"待写"标记：set_task 开头的 flush 会把它们落盘。若换源
        #    只删文件不清标记，旧书的参数暂存/检测框就复活了。
        #    ``_draft_dirty`` 是 **页号 → 改动那一刻的节点 id** 的字典（B 方案：
        #    同一步骤的多个节点共用一页，落盘时要按节点归属），所以清空后是 {}。
        probe._draft_dirty = {0: None}
        probe._pending_sizes = {"0001.jpg": (10, 20)}
        probe._pending_boxes = {"0001.jpg": [[0, 0, 5, 5]]}
        probe._reset_artifacts_for_new_source()
        ok("换源文件清掉旧书的中间产物（否则界面混着两本书的结果）",
           not (store.task_dir(empty_tid) / "runs.json").exists()
           and probe.pages == [] and probe.pdf_page_count == 0)
        ok("换源文件连**待写标记**一起清（否则 set_task 的 flush 把旧书数据写回来）",
           probe._draft_dirty == {} and probe._pending_sizes == {}
           and probe._pending_boxes == {})
        ok("换源文件**不碰**流程图（流程是用户配的，与源文件无关）",
           default_flow_path(store.task_dir(empty_tid)).exists())
    finally:
        probe.shutdown_all_workers()
        probe.close()
        app.processEvents()
    # ---- 补上文件后高亮/红字要收掉；流程不要 PDF 时不催 ----
    # ⚠️ **另起探针**：这两条要反复 `set_task` 切任务，共用 `probe` 会把上面
    #    那些断言的上下文（当前任务、产物状态）带偏——之前就踩过一次，
    #    表现为"改一个断言，后面一串莫名假红"。
    _check_source_prompt_cycle(store, pdf, app)
    # 清场：本节建的几个任务
    for extra in (tid, tid2, tid3, empty_tid):
        store.delete_task(extra)

def _check_source_prompt_cycle(store, pdf, app) -> None:
    """补上 PDF ⇒ 提示全收；流程不需 PDF ⇒ 一律不催（用户 2026-10-06）。"""
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.ui import theme
    from desktop.steps.bpmn_diagram import (
        DiagramFlow, FlowDiagram,
    )
    from desktop.utils.files import file_hash
    from tests.selftests._context import ok, silence_source_prompt

    empty_tid = store.create_task(None, "", "")
    no_pdf_flow = store.create_task(None, "", "")
    # 造一条"没有提取图片"的流程（用户自定义流程可能删掉那一步）
    base = store.task_diagram(empty_tid)
    keep = [n for n in base.nodes if n.name != "提取图片"]
    if len(keep) >= 2:
        store.save_task_diagram(no_pdf_flow, FlowDiagram(
            nodes=tuple(keep),
            flows=tuple(DiagramFlow(f"nf{i}", keep[i - 1].id, keep[i].id)
                        for i in range(1, len(keep))),
        ))
    probe = TaskDetailPage(store)
    probe.resize(1080, 720)
    probe.show()
    try:
        app.processEvents()
        prompt_calls = silence_source_prompt(probe)
        # ---- 补上 PDF ⇒ 红字与高亮都收掉 ----
        real = store.task_dir(empty_tid) / "补选.pdf"
        real.write_bytes(pdf.read_bytes())
        store.set_task_source(empty_tid, real, source_hash=file_hash(real))
        probe.set_task(empty_tid)
        ok("补上 PDF 后红字消失（不留一句过期的话）",
           probe.source_warning.isHidden(), probe.source_warning.text())
        ok("补上 PDF 后按钮高亮撤掉（回默认样式）",
           probe.source_button.styleSheet() == "",
           repr(probe.source_button.styleSheet()[:40]))
        ok("补上 PDF 后不再催（判据为假）", probe._missing_source() is False)
        ok("补上 PDF 后进页面也不弹提示（提示层被收掉）",
           not prompt_calls or probe._source_prompt is None
           or not probe._source_prompt.isVisible(),
           f"visible={probe._source_prompt is not None and probe._source_prompt.isVisible()}")
        # ---- 流程里不需要 PDF ⇒ **不催 PDF**，改催"上传图片" ----
        # ⚠️⚠️ 这条断言 2026-10-06 改过一次口径：删掉「提取图片」后的流程，
        #    第一格是「检测文本框」——它**不吃 PDF**，输入是入口图片目录。
        #    所以正确表现不是"一律不催"，而是"**催的是图片不是 PDF**"
        #    （用户 2026-10-06：「非图片提取节点如果做第一个节点……应该提醒
        #    上传输入目录或者图片」）。旧的"不催"断言与新口径直接冲突。
        if len(keep) >= 2:
            prompt_calls.clear()
            probe.set_task(no_pdf_flow)
            app.processEvents()
            # ⚠️ 判"提示层没出现"要看**它有没有被建出来/显示**，不能只看
            #    记录列表——那记的是"被请求"，每次 set_task 都会记一笔。
            shown = (probe._source_prompt is not None
                     and probe._source_prompt.isVisible())
            ok("流程里没有要 PDF 的步骤 ⇒ **不催 PDF**（不催错的方向）",
               probe._missing_source() is False
               and probe.source_button.styleSheet() == "",
               f"missing={probe._missing_source()} "
               f"btn={probe.source_button.styleSheet()[:30]}")
            ok("流程第一步不吃 PDF 且入口目录没图 ⇒ 判据是「缺图片」",
               probe._missing_input_kind() == "images",
               f"kind={probe._missing_input_kind()!r}")
            ok("缺图片 ⇒ 提示层照样弹出（每次进入都检测）", shown,
               f"shown={shown}")
            # 判"高亮"直接看有没有非空样式表就够：非空 = 有边框+底色那套
            # （_set_tool_highlight 撤掉时写的是空串），不必去比对色值。
            ok("缺图片 ⇒ 高亮的是**图片按钮**、不是 PDF 按钮",
               bool(probe.insert_button.styleSheet())
               and probe.source_button.styleSheet() == "",
               f"insert={bool(probe.insert_button.styleSheet())} "
               f"pdf={bool(probe.source_button.styleSheet())}")
            ok("缺图片 ⇒ 页头图片/目录入口**显示**（藏了就没法补，规则②）",
               not probe.insert_button.isHidden()
               and not probe.insert_dir_button.isHidden())
            ok("缺图片 ⇒ 检测页左下角「＋/📁」显示（入口就是检测，规则③）",
               (_btn_img := _viewer_entry_button(
                   probe.detect_viewer, "插入图片（可多选）")) is not None
               and not _btn_img.isHidden())
            ok("缺图片 ⇒ 页头红字说的是图片（不是 PDF）",
               "图片" in probe.source_warning.text()
               and "PDF" not in probe.source_warning.text(),
               probe.source_warning.text())
            _sp = probe._source_prompt
            ok("缺图片 ⇒ 提示层文案说图片，不说 PDF",
               shown and _sp is not None
               and "图片" in _sp.title_label.text()
               and "PDF" not in _sp.title_label.text(),
               _sp.title_label.text() if _sp is not None else "")
            ok("缺图片 ⇒ 主按钮文案是**选择图片目录**（用户 2026-10-06）",
               shown and _sp is not None
               and _sp.pick_button.text() == "选择图片目录",
               _sp.pick_button.text() if _sp is not None else "")
            # ⚠️ **文案与行为必须一致**：按钮写着"选目录"，点了就必须真开
            #    **目录**框。`getOpenFileNames` 选不了目录，所以这条钉的是
            #    `pick_kind` 传出去的值——它决定宿主走哪个 QFileDialog。
            ok("缺图片 ⇒ 该按钮声明自己要**目录框**（点下去开目录对话框）",
               shown and _sp is not None
               and _sp._content.get("pick_kind") == "folder",
               str(_sp._content.get("pick_kind")) if _sp is not None else "")
            # ---- 往入口目录放一张图 ⇒ 提示全收 ----
            entry = store.task_input_dir(no_pdf_flow)
            entry.mkdir(parents=True, exist_ok=True)
            (entry / "page001.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            probe.set_task(no_pdf_flow)
            app.processEvents()
            ok("入口目录里已有图 ⇒ 不再判缺（不催了）",
               probe._missing_input_kind() == "",
               f"kind={probe._missing_input_kind()!r}")
            # ⚠️ 判"动态高亮撤掉"**不能**看 ``styleSheet() == ""``：插图按钮
            #    自2026-10-06 起带**常驻红框**（入口标识，用户要求"都是红色
            #    框住"），样式表永远非空。动态那层与常驻那层**同色**、无法从
            #    样式表文本区分——它的可见性由「红字还在不在」如实反映：
            #    有红字＝还在催你；红字消失＝动态高亮确实撤了。
            #    （曾经在这里断言 styleSheet 为空，改成常驻红框后必然假红。）
            ok("入口目录里已有图 ⇒ 不再催（红字消失＝动态高亮已撤）",
               probe.source_warning.isHidden()
               and probe._missing_input_kind() == "",
               f"hidden={probe.source_warning.isHidden()} "
               f"kind={probe._missing_input_kind()!r}")
            ok("入口目录里已有图 ⇒ 常驻红框仍在（入口标识不被撤掉）",
               str(theme.DANGER) in (probe.insert_button.styleSheet() or ""),
               f"style={probe.insert_button.styleSheet()[:40]}")
        else:
            ok("流程里没有要 PDF 的步骤 ⇒ 不催 PDF（构造跳过）", True)

        # ---- 流程读不出来 ⇒ **必须让用户看见**（不再静默回落默认流程）----
        # ⚠️⚠️ `store.task_diagram` 在三种失败形态下都会**静默**回落默认模板：
        #   ① `flow.bpmn` 不存在；② XML 非法；③ **解析得动但一个步骤名都认不出**。
        # 第三种最狠：用户在 bpmn.io 里把「图片去底色」改名成「AI 抠图」——
        # 一次完全合法的编辑——整张自定义图被判成"坏"，界面变回默认流程，
        # 而用户看到的现象与"我没改过它"完全一样，找不到任何线索。
        # 所以回落必须配一条提示（`flow_degraded_reason` + `_warn_if_flow_degraded`）。
        bad_tid = store.create_task(None, "", "")
        bad_flow = store.task_dir(bad_tid) / "flow.bpmn"
        try:
            bad_flow.write_text(
                '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/'
                '20100524/MODEL" xmlns:guji="https://guji.tools/bpmn/2025">'
                '<bpmn:process id="p" isExecutable="false">'
                '<bpmn:task id="a" name="AI 抠图"/>'
                "</bpmn:process></bpmn:definitions>",
                encoding="utf-8",
            )
            # 走一次读：降级原因就是这时记下的
            store.task_diagram(bad_tid)
            reason = store.flow_degraded_reason(bad_tid)
            ok("步骤名一个都认不出 ⇒ 记下降级原因（不是无声换回默认流程）",
               "认不出来" in reason or "步骤" in reason, reason)

            toasts: list = []
            _real_toast = probe._toast
            probe._toast = (lambda kind, title, content:
                            toasts.append((kind, title, content)))
            try:
                probe.set_task(bad_tid)
                app.processEvents()
                ok("流程降级 ⇒ 进任务就弹一次警告（告诉用户为什么变回默认）",
                   any("默认" in t[1] for t in toasts), str(toasts[:2]))
                ok("警告里说清了改流程不会有效果（下一步该做什么）",
                   any("不会有任何效果" in t[2] for t in toasts),
                   str(toasts[:1]))
                ok("同一次进入只弹一次（flow_slots 会被读很多遍，别刷屏）",
                   len([t for t in toasts if "默认" in t[1]]) == 1,
                   str(toasts))
            finally:
                probe._toast = _real_toast

            # 修好之后 ⇒ 不再提示，且降级原因被清掉
            from desktop.steps.scheduler import load_default_diagram
            load_default_diagram().save(bad_flow)
            store.task_diagram(bad_tid)
            ok("流程修好 ⇒ 不再判降级（提示会收）",
               store.flow_degraded_reason(bad_tid) == "",
               store.flow_degraded_reason(bad_tid))
        finally:
            try:
                store.delete_task(bad_tid)
            except OSError:
                pass
    finally:
        probe.shutdown_all_workers()
        probe.close()
        app.processEvents()
        for extra in (empty_tid, no_pdf_flow):
            try:
                store.delete_task(extra)
            except OSError:
                pass
