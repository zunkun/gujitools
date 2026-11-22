# -*- coding: utf-8 -*-
"""面板旋转组件：增量语义 / ±180° 跨界 / 程序化回填不回抛 / 公共组件契约：无下游流程的宿主构造时声明收掉启用开关 / 页级接线：面板增量 → 画布即时转 → 停顿提交落盘 + 面板回填"""

from typing import Any


def run(st: Any) -> None:
    from desktop.ui.widgets import HelpButton
    from desktop.components.imposition.panel import ImpositionPanel
    from desktop.services import imposition as S
    from tests.selftests._context import make_pdf, ok, pump
    def _column_index(box, widget) -> int:
        """控件在面板竖排布局里的下标（判「页级块在前、图片级块在后」）。"""
        for i in range(box.count()):
            if box.itemAt(i).widget() is widget:
                return i
        return -1

    def _row_layout_of(box, widget):
        """面板里**含 ``widget`` 的那一行**的行布局（找不到返回 None）。"""
        for i in range(box.count()):
            _item = box.itemAt(i)
            _row = _item.layout() if _item is not None else None
            if _row is not None and _row.indexOf(widget) >= 0:
                return _row
        return None

    panel = ImpositionPanel()
    deltas: list[float] = []
    item_angles: list[float] = []
    panel.whole_rotate_delta.connect(deltas.append)
    panel.item_rotation_edited.connect(item_angles.append)
    ok(
        "面板上没有「上移/下移」与「左转/右转 90°」按钮（2026-09-30 删除）",
        not any(
            hasattr(panel, name)
            for name in (
                "up_button",
                "down_button",
                "rotate_left_button",
                "rotate_right_button",
            )
        ),
    )
    ok(
        "旋转组件微调口径：滑块 0.01°/格、输入框 2 位小数步进 0.1°",
        (panel.whole_slider.minimum(), panel.whole_slider.maximum())
        == (-18000, 18000)
        and panel.whole_slider.singleStep() == 1
        and panel.whole_slider.pageStep() == 100
        and panel.whole_spin.decimals() == 2
        and panel.whole_spin.singleStep() == 0.1,
        f"slider={panel.whole_slider.minimum()}.."
        f"{panel.whole_slider.maximum()} "
        f"step={panel.whole_slider.singleStep()} "
        f"spin={panel.whole_spin.decimals()}位/"
        f"{panel.whole_spin.singleStep()}",
    )
    panel.show()
    st.ctx.app.processEvents()
    ok(
        "输入框在说明行、滑块通栏独占下一行（不挤一行）",
        panel.whole_spin.geometry().bottom() <= panel.whole_slider.geometry().top()
        and panel.whole_slider.width() > panel.whole_spin.width(),
        f"spin_bottom={panel.whole_spin.geometry().bottom()} "
        f"slider_top={panel.whole_slider.geometry().top()} "
        f"slider_w={panel.whole_slider.width()}",
    )
    panel.whole_spin.setValue(10.0)
    ok("整体旋转组件：输入 10° 吐 +10° 增量", deltas == [10.0], str(deltas))
    panel.set_whole_angle(170.0)
    ok("程序化回填整版角度不吐增量", deltas == [10.0], str(deltas))
    panel.whole_spin.setValue(-170.0)
    ok("跨 ±180° 边界换算成 +20° 增量", deltas == [10.0, 20.0], str(deltas))
    ok(
        "未选中图片时旋转目标为整版",
        not panel._item_mode
        and panel.whole_caption.text() == "整体旋转（绕两图公共中心）",
    )
    panel.set_item_rotation(45.0)
    ok(
        "选中图片后同一组旋转控件切换到该图并回填角度",
        panel._item_mode
        and panel.whole_spin.isEnabled()
        and abs(panel.whole_spin.value() - 45.0) < 0.01
        and panel.whole_caption.text() == "当前图片旋转（绕图片中心）",
        str(panel.whole_spin.value()),
    )
    ok("单图回填不吐信号", item_angles == [], str(item_angles))
    panel.whole_spin.setValue(60.0)
    ok("选中图改值发**绝对角度**", item_angles == [60.0], str(item_angles))
    panel.set_item_rotation(25.0)
    ok(
        "切换到另一张图片后旋转控件立即回填另一张角度",
        abs(panel.whole_spin.value() - 25.0) < 0.01,
        str(panel.whole_spin.value()),
    )
    panel.set_item_rotation(None)
    ok(
        "点空白取消选择后旋转控件恢复整版角度",
        not panel._item_mode
        and panel.whole_caption.text() == "整体旋转（绕两图公共中心）"
        and abs(panel.whole_spin.value() - (-170.0)) < 0.01,
        str(panel.whole_spin.value()),
    )
    ok(
        "面板上没有「选择拼版」按钮（2026-09-30 删除：入口只在左列虚线格）",
        not hasattr(panel, "add_button"),
    )
    ok(
        "「复位本页版面」独占一行 block（删除按钮挪走后不再拼行）",
        _column_index(panel.box, panel.reset_button) >= 0,
    )
    _actions_row = _row_layout_of(panel.box, panel.add_image_button)
    ok(
        "「删除选中图片」挪进页级区，与「新增图片」同一行",
        _actions_row is not None
        and _actions_row.indexOf(panel.delete_item_button) >= 0
        and not hasattr(panel, "item_section"),
    )
    ok(
        "未选中图时删除按钮隐藏、新增按钮隐藏（两图页初始态）",
        panel.delete_item_button.isHidden() and panel.add_image_button.isHidden(),
    )
    panel.set_item_rotation(30.0)
    ok(
        "选中图后「删除选中图片」露出（页级区里）",
        not panel.delete_item_button.isHidden(),
    )
    ok(
        "「删除选中图片」用共享危险按钮样式 theme.danger_button_qss"
        "（2026-09-30 用户定：样式对齐任务列表删除按钮）",
        "#C93A3A" in panel.delete_item_button.styleSheet()
        and ":hover" in panel.delete_item_button.styleSheet()
        and "padding: 6px 12px 7px 12px" in panel.delete_item_button.styleSheet()
        and "#C0392B" not in panel.delete_item_button.styleSheet(),
    )
    ok(
        "「删除选中图片」不带图标（红底上 fluent 深色图标对比度差）",
        panel.delete_item_button.icon().isNull(),
    )
    panel.set_single_page(True)
    ok(
        "「删除选中图片」与「新增图片」等高（内边距补齐 fluent 上下边框）",
        panel.delete_item_button.sizeHint().height()
        == panel.add_image_button.sizeHint().height(),
        str(
            (
                panel.delete_item_button.sizeHint().height(),
                panel.add_image_button.sizeHint().height(),
            )
        ),
    )
    panel.set_single_page(False)
    panel.set_item_rotation(None)
    ok("清空选中后删除按钮重新隐藏", panel.delete_item_button.isHidden())
    ok(
        "「在流程中启用图片拼版」开关在面板最底部",
        0 <= _column_index(panel.box, panel.enabled_checkbox)
        and _column_index(panel.box, panel.enabled_checkbox)
        > _column_index(panel.box, panel.clear_button),
    )
    ok(
        "说明挂在问号按钮上（不再平铺）",
        isinstance(getattr(panel, "help_button", None), HelpButton)
        and "可选节点" in panel.help_button.toolTip(),
    )
    ok(
        "清空选中后旋转说明恢复未选中整版样式",
        not panel._item_mode
        and panel.whole_caption.text() == "整体旋转（绕两图公共中心）",
    )
    panel.set_item_rotation(30.0)
    ok(
        "选中图后旋转说明切换为当前图片样式",
        panel._item_mode
        and panel.whole_caption.text() == "当前图片旋转（绕图片中心）",
    )
    panel.deleteLater()
    bare = ImpositionPanel(enable_switch=False)
    ok(
        "enable_switch=False 收起「在流程中启用图片拼版」开关（任务流程专属概念不进公共面板）",
        bare.enabled_checkbox.isHidden() and bare.enabled_checkbox.isChecked(),
    )
    bare.set_enabled_checked(False)
    ok(
        "隐藏态下程序化回填 set_enabled_checked 仍可用",
        not bare.enabled_checkbox.isChecked(),
    )
    bare.deleteLater()
    st.page._save_imposition_pages(st.before_release)
    st.page._imposition_timer.stop()
    st.page.imposition_view.set_current(0)
    st.page.imposition_view.canvas.select(0)
    st.page.imposition_view.canvas.set_page(S.default_items([str(st.a), str(st.b)]))
    pump(st.ctx.app, times=4)
    st.page._on_imposition_whole_rotate(15.0)
    live = [it["rotation"] for it in st.page.imposition_view.canvas.items()]
    ok(
        "整版增量**即时**作用于画布（不等落盘）",
        all(abs(r - 15.0) < 0.01 for r in live),
        str(live),
    )
    st.page._commit_imposition_edit()
    st.page._imposition_timer.stop()
    saved = st.page._imposition_pages()[0]["items"]
    ok(
        "停顿提交把整版旋转落盘（两张都 +15°）",
        all(abs(it["rotation"] - 15.0) < 0.01 for it in saved),
        str([it["rotation"] for it in saved]),
    )
    ok(
        "提交后面板回填整版角度",
        abs(st.page.imposition_panel.whole_spin.value() - 15.0) < 0.01,
        str(st.page.imposition_panel.whole_spin.value()),
    )
    st.page.imposition_view.canvas.select(1)
    ok(
        "切换选中图后共用旋转控件回填新目标角",
        st.page.imposition_panel._item_mode
        and abs(st.page.imposition_panel.whole_spin.value() - 15.0) < 0.01,
        str(st.page.imposition_panel.whole_spin.value()),
    )
    st.page.imposition_panel.whole_spin.setValue(25.0)
    st.page._commit_imposition_edit()
    st.page._imposition_timer.stop()
    saved = st.page._imposition_pages()[0]["items"]
    ok(
        "单图绝对角度落盘（只改选中的左槽）",
        abs(saved[1]["rotation"] - 25.0) < 0.01
        and abs(saved[0]["rotation"] - 15.0) < 0.01,
        str([it["rotation"] for it in saved]),
    )
    ok(
        "提交后单图组件回填选中角",
        st.page.imposition_panel._item_mode
        and abs(st.page.imposition_panel.whole_spin.value() - 25.0) < 0.01,
        str(st.page.imposition_panel.whole_spin.value()),
    )

