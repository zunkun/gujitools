# -*- coding: utf-8 -*-
"""4b. 大输入区（用户要的那块\"大的输入框\"） / 4b-2. 点空白处 → 直接开选择对话框（无小菜单、且不压在同一鼠标事件里） / 4b-3. 可见的选择按钮（用户 2026-10-03 报\"不能直接点击按钮选择\"） / 4b-3c. 「更换」真的能换源（用户 2026-10-03 报\"点了没反应\"） / 4b-3b. 独占模式（用户 2026-10-03：初始只有一个输入框）"""

from typing import Any


def run(st: Any) -> None:
    from desktop.steps.source_zone import BUTTON_HEIGHT, FILLED_HEIGHT as _FILLED
    from desktop.steps.source_zone import EMPTY_HEIGHT, FILLED_HEIGHT, SourceZone
    from pathlib import Path
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from desktop.steps.source_zone import SOLO_HEIGHT, SOLO_MIN_WIDTH
    from desktop.steps.spec import (
        FLOW_STAGES,
        NAV_STEPS,
        SPECS,
        STEP_KEYS,
        StepSpec,
        spec_by_key,
    )
    from desktop.utils.files import default_open_dir
    from tests.selftests._context import ok, wait_until
    from PySide6.QtCore import QMimeData, QUrl

    from desktop.steps.source_zone import EMPTY_HEIGHT, FILLED_HEIGHT, SourceZone

    # ⚠️ 用 rembg（仍收目录）当夹具，不用 extract：图片提取已经改成
    #    **只支持文件**（用户 2026-10-03），它不摆「选择文件夹」按钮。
    st.zone = SourceZone(st.rembg)
    st.zone.resize(420, 240)
    ok("大输入区默认收拖拽", st.zone.acceptDrops() is True)
    ok(
        "空态是大块（还没选东西）",
        st.zone.source() is None and st.zone.height() == EMPTY_HEIGHT,
        str(st.zone.height()),
    )

    zone_seen: list = []
    zone_rejected: list = []
    st.zone.paths_chosen.connect(zone_seen.append)
    st.zone.rejected.connect(zone_rejected.append)
    # ⚠️ 用户 2026-10-04：「如果没有导入完全没有必要提示」。空 offer 走到这里
    #    只有一种情形——选择对话框里点了「取消」。那是"我什么都没选"，不是
    #    "你给的东西用不了"，弹「这个用不上」纯属噪声 ⇒ 静默（两个信号都不发）。
    st.zone.offer([])
    ok(
        "取消选择（空 offer）完全静默：不发路径、也不报 rejected",
        zone_seen == [] and zone_rejected == [],
        f"seen={zone_seen} rejected={zone_rejected}",
    )

    mime = QMimeData()
    mime.setUrls(
        [
            QUrl.fromLocalFile(str(st.drop_dir)),
            QUrl("https://example.com/not-local"),
        ]
    )
    ok(
        "拖拽数据只取本地文件/文件夹",
        [Path(p) for p in SourceZone.paths_from_mime(mime)] == [st.drop_dir],
        str(SourceZone.paths_from_mime(mime)),
    )
    ok("纯文本的拖拽数据取不到路径", SourceZone.paths_from_mime(QMimeData()) == [])

    st.zone.offer(SourceZone.paths_from_mime(mime))
    ok(
        "拖进来的路径原样发出去（不做合法性判断）",
        len(zone_seen) == 1 and [Path(p) for p in zone_seen[0]] == [st.drop_dir],
        str(zone_seen),
    )
    st.zone.set_source(st.drop_dir, "12 个可用文件")
    ok(
        "已选态收窄成一行",
        st.zone.source() == st.drop_dir and st.zone.height() == FILLED_HEIGHT,
        str(st.zone.height()),
    )

    cleared: list = []
    st.zone.cleared.connect(lambda: cleared.append(True))
    st.zone.clear()
    ok(
        "清空回到空态并发出 cleared",
        cleared == [True] and st.zone.source() is None and st.zone.height() == EMPTY_HEIGHT,
    )

    # 拖动经过时的高亮开关（宿主页面转发整页拖拽时用）
    st.zone.set_hot(True)
    ok("可以外部点亮拖拽热区", st.zone._hot is True)
    st.zone.set_hot(False)
    ok("可以熄灭拖拽热区", st.zone._hot is False)
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QFileDialog

    from desktop.utils.files import default_open_dir

    browse_calls: list = []
    st.original_name = QFileDialog.getOpenFileName
    original_menu = getattr(SourceZone, "_ask_kind", None)

    # 若还留着那个小菜单方法，就让它一被调用就炸（用来证明它**没**被调用）
    def _menu_should_not_run(self):
        browse_calls.append("MENU")
        raise AssertionError("不该弹两选项小菜单（用户 2026-10-03 要求去掉）")

    if original_menu is not None:
        SourceZone._ask_kind = _menu_should_not_run  # type: ignore[reportAttributeAccessIssue]  # 该属性已被移除，hasattr 兜底（防回归期间方法复活）
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (browse_calls.append(("file", a[2])), ("", ""))[1])  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
    try:
        st.zone.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(st.zone.width() // 2, st.zone.height() // 2),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        ok(
            "点击大输入区**不当场**开模态（否则会叠在同一个鼠标事件里）",
            browse_calls == [],
            str(browse_calls),
        )
        ok(
            "事件循环跑完直接开选文件对话框（不再先弹两选项小菜单）",
            wait_until(st.app, lambda: bool(browse_calls), timeout=3)
            and [c[0] if isinstance(c, tuple) else c for c in browse_calls] == ["file"],
            str(browse_calls),
        )
        ok(
            "对话框起始目录是文档目录，不是空串"
            "（空串会回退到进程工作目录，打包后就是程序目录）",
            bool(browse_calls) and browse_calls[0][1] == str(default_open_dir()),
            repr(browse_calls[0][1] if browse_calls else None),
        )
    finally:
        if original_menu is not None:
            SourceZone._ask_kind = original_menu  # type: ignore[reportAttributeAccessIssue]  # 该属性已被移除，hasattr 兜底（防回归期间方法复活）
        QFileDialog.getOpenFileName = st.original_name
    from desktop.steps.source_zone import BUTTON_HEIGHT, FILLED_HEIGHT as _FILLED

    # ⚠️ 用 `isVisibleTo(zone)` 而不是 `isVisible()`：后者要求**顶层窗口已 show**，
    #    而自测里这个 zone 从不显示，断言会假红（第一版就踩了这个）。
    ok("空态摆出「选择文件」按钮", st.zone.file_button.isVisibleTo(st.zone))
    ok(
        "accepts_dir=True 时摆出「选择文件夹」按钮",
        st.zone.dir_button is not None and st.zone.dir_button.isVisibleTo(st.zone),
    )
    ok(
        "按钮落在虚框内、不被裁掉",
        st.zone.file_button.height() == BUTTON_HEIGHT
        and st.zone.file_button.geometry().bottom() <= st.zone.height(),
        f"{st.zone.file_button.geometry()} h={st.zone.height()}",
    )
    ok(
        "空态按钮行居中",
        abs(
            (st.zone.file_button.geometry().left() + st.zone.file_button.width() / 2)
            - st.zone.width() / 2
        )
        < st.zone.width() / 2,
        str(st.zone.file_button.geometry()),
    )

    # ⚠️ 2026-10-03：点按钮 = 直接开**资源管理器的选择对话框**（不是"弹一个
    #    资源管理器窗口去监听选中项"，用户明确纠正过两者区别）。
    #    这里钉住：文件按钮 → 选文件对话框、目录按钮 → 选目录对话框、起始目录
    #    仍是文档目录。
    btn_calls: list = []
    orig_multi = QFileDialog.getOpenFileNames
    orig_dir = QFileDialog.getExistingDirectory
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (btn_calls.append(("file", a[2])), ("", ""))[1])  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: (btn_calls.append(("dir", a[2])), "")[1])  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
    try:
        st.zone.file_button.click()
        ok(
            "点「选择文件」**不当场**弹模态（仍在同一个鼠标事件里）",
            btn_calls == [],
            str(btn_calls),
        )
        ok(
            "点「选择文件」弹出的是选文件对话框",
            wait_until(st.app, lambda: bool(btn_calls), timeout=3)
            and [c[0] for c in btn_calls] == ["file"],
            str(btn_calls),
        )
        ok(
            "按钮路径的起始目录也是文档目录（不是空串）",
            bool(btn_calls) and btn_calls[0][1] == str(default_open_dir()),
            repr(btn_calls[0][1] if btn_calls else None),
        )

        btn_calls.clear()
        assert st.zone.dir_button is not None  # rembg 收目录，目录按钮必已建
        st.zone.dir_button.click()
        ok(
            "点「选择文件夹」弹出的是选目录对话框",
            wait_until(st.app, lambda: bool(btn_calls), timeout=3)
            and [c[0] for c in btn_calls] == ["dir"],
            str(btn_calls),
        )
    finally:
        QFileDialog.getOpenFileName = st.original_name
        QFileDialog.getExistingDirectory = orig_dir
        QFileDialog.getOpenFileNames = orig_multi

    # 已选态：换成右端「更换」，两个选择按钮收起来
    st.zone.set_source(st.drop_dir / "a.pdf")
    ok("已选态出现「更换」按钮", st.zone._swap_button.isVisibleTo(st.zone))
    ok(
        "已选态收起两个选择按钮（不给人三个同权入口）",
        not st.zone.file_button.isVisibleTo(st.zone)
        and not (st.zone.dir_button is not None and st.zone.dir_button.isVisibleTo(st.zone)),
    )
    ok("已选态高度收窄成一行", st.zone.height() == _FILLED, str(st.zone.height()))
    ok(
        "已选态「更换」与清空 ✕ 不重叠",
        st.zone._swap_button.geometry().right() < st.zone.width() - 26 - 8 + 1,
        f"swap={st.zone._swap_button.geometry()} w={st.zone.width()}",
    )

    # accepts_dir=False 的步骤不该摆一个注定被拒的「选择文件夹」，
    # 但「选择文件」要照常在（那才是它唯一的合法入口）
    st.no_dir = SourceZone(
        StepSpec(
            key="probe",
            command=None,
            title="探针",
            panel=None,
            pick_label="选择文件",
            file_filter="PDF 文件 (*.pdf)",
            accepts_dir=False,
        )
    )
    ok(
        "不接受目录的步骤不摆「选择文件夹」，但保留「选择文件」",
        st.no_dir.dir_button is None and st.no_dir.file_button.isVisibleTo(st.no_dir),
    )
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    swap_calls: list = []
    orig_name2 = QFileDialog.getOpenFileName
    # 「更换」= 再选一次，走同一条选文件对话框。这段的重点是它的**几何/命中**
    # （QTest.mouseClick 走命中测试，测的是"画出来了却点不到"那类问题）。
    pdf_a, pdf_b = st.drop_dir / "a.pdf", st.drop_dir / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (swap_calls.append(str(a[2])), (str(pdf_b), ""))[1])  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
    # ⚠️ 必须 show 出来：``QTest.mouseClick`` 走的是**命中测试**路径，控件不在
    #    任何已显示的窗口里时命中不到，事件会悄悄丢掉（自测里表现为"点了没反应"
    #    ——正是本次要防的那个症状本身，不能自己踩一遍）。
    st.no_dir.show()
    st.no_dir.resize(900, _FILLED)
    st.app.processEvents()
    try:
        st.no_dir.set_source(pdf_a)
        st.app.processEvents()
        ok("PDF 步骤已选态有「更换」按钮", st.no_dir._swap_button.isVisibleTo(st.no_dir))
        QTest.mouseClick(st.no_dir._swap_button, Qt.MouseButton.LeftButton)
        ok(
            "点「更换」会请求文件对话框（不是目录对话框）",
            wait_until(st.app, lambda: bool(swap_calls), timeout=3),
            str(swap_calls),
        )
        ok(
            "「更换」的起始目录是文档目录",
            bool(swap_calls) and swap_calls[0] == str(default_open_dir()),
            repr(swap_calls[0] if swap_calls else None),
        )

        # 端到端：真的换掉（offer → paths_chosen → 宿主 set_source）
        picked: list = []
        st.no_dir.paths_chosen.connect(picked.append)
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(pdf_b), ""))  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
        st.no_dir.set_source(pdf_a)
        st.app.processEvents()
        QTest.mouseClick(st.no_dir._swap_button, Qt.MouseButton.LeftButton)
        wait_until(st.app, lambda: bool(picked), timeout=3)
        ok("「更换」选完真的把新路径交出去", picked == [[str(pdf_b)]], str(picked))

        # 点已选态的**空白处**也换源（2026-10-03 改回来：不再依赖子控件几何）
        # ⚠️ 这里必须把 stub 换回**会记账**的那个：上一段为了验"交出去的路径"
        #    换了个不记账的 stub，直接拿来断言 ``swap_calls`` 必然是空的
        #    （我自己踩了一次，别再踩）。
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (swap_calls.append(str(a[2])), (str(pdf_b), ""))[1])  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
        swap_calls.clear()
        QTest.mouseClick(st.no_dir, Qt.MouseButton.LeftButton, pos=st.no_dir.rect().center())
        ok(
            "点已选态空白处也能换源（不依赖按钮几何）",
            wait_until(st.app, lambda: bool(swap_calls), timeout=3),
            str(swap_calls),
        )

        # ✕ 仍是清空（别被上面的"点哪都换源"吃掉）
        cleared: list = []
        st.no_dir.cleared.connect(lambda: cleared.append(1))
        st.no_dir.set_source(pdf_a)
        st.app.processEvents()
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent

        hit = st.no_dir._close_rect.center().toPoint()
        st.no_dir.mousePressEvent(
            QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(hit),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        ok("点右上角 ✕ 是清空、不是换源", bool(cleared), str(cleared))

        # 对话框炸了要说给用户听（Qt 会吞掉 singleShot 回调里的异常）
        boom: list = []
        st.no_dir.rejected.connect(boom.append)

        def _boom(*a, **k):
            raise RuntimeError("模拟对话框故障")

        QFileDialog.getOpenFileName = staticmethod(_boom)  # type: ignore[reportAttributeAccessIssue]  # 测试替身：离屏不许真弹文件对话框，换成记录器
        st.no_dir.set_source(pdf_a)
        st.app.processEvents()
        QTest.mouseClick(st.no_dir._swap_button, Qt.MouseButton.LeftButton)
        ok(
            "对话框异常会转成 rejected 提示（而不是静默无反应）",
            wait_until(st.app, lambda: bool(boom), timeout=3) and "对话框" in boom[0],
            str(boom),
        )
    finally:
        QFileDialog.getOpenFileName = orig_name2
        st.no_dir.hide()
        st.no_dir.deleteLater()
    from desktop.steps.source_zone import SOLO_HEIGHT, SOLO_MIN_WIDTH

    solo = SourceZone(st.rembg)
    solo.resize(600, 200)
    solo.set_solo_mode(True)
    ok("独占模式：撑满整幅", solo.height() == SOLO_HEIGHT, str(solo.height()))
    solo.set_solo_mode(False)
    ok("退出独占：回到常规空态高度", solo.height() == EMPTY_HEIGHT, str(solo.height()))
    solo.set_solo_mode(True)
    solo.set_source(st.drop_dir / "a.png")
    ok(
        "独占模式下选中源 → 收窄成一行（纵向空间让给分栏）",
        solo.height() == FILLED_HEIGHT,
        str(solo.height()),
    )
    solo.set_source(None)
    ok("独占模式 + 回到空态 → 又撑满", solo.height() == SOLO_HEIGHT, str(solo.height()))
    # ⚠️ 这条是**真实 bug 的钉子**（靠截图发现的，断言全绿时根本看不出来）：
    #    独占模式最初用 setFixedHeight(320)，它同时钉死了 maximumHeight；
    #    后来改成"最小 320 + 可拉伸"却只改了 minimumHeight，控件就永远长不大
    #    ——整页只有一条 320px 的框，上下各留一片空白。
    ok(
        "独占模式真的能长高（不是被旧的最大高度钉住）",
        solo.maximumHeight() > solo.minimumHeight(),
        f"min={solo.minimumHeight()} max={solo.maximumHeight()}",
    )
    # ⚠️ 这条钉的是**stderr 警告**（用户 2026-10-03 报「单独拼版界面报错」）：
    #    "QWidget::setMaximumSize: The largest allowed size is (16777215,16777215)"。
    #    Qt 的硬上限 QWIDGETSIZE_MAX == (1<<24)-1 == 16777215，哨兵写成 1<<24
    #    就超了 1，Qt 截断回上限并往 stderr 打警告；拼版独立页初始即独占模式，
    #    于是每次进页面都刷一条，看着像报错。断言取"Qt 自己认的上限"。
    ok(
        "独占模式的最大高度哨兵不超 Qt 硬上限（否则进页面就刷警告）",
        solo.maximumHeight() <= (1 << 24) - 1,
        str(solo.maximumHeight()),
    )
    solo.set_solo_mode(False)

    # 独占模式的最小宽度也要比常规宽（独占时没有分栏挤它，不必那么窄）
    narrow = SourceZone(st.rembg)
    narrow.set_solo_mode(True)
    ok(
        "独占模式抬高最小宽度",
        narrow.minimumWidth() == SOLO_MIN_WIDTH,
        str(narrow.minimumWidth()),
    )
    narrow.set_solo_mode(False)
    ok(
        "退出独占后最小宽度复原",
        narrow.minimumWidth() == 260,
        str(narrow.minimumWidth()),
    )

