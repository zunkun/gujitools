# -*- coding: utf-8 -*-
"""图片编辑弹窗·外壳：窗口旗标、工具栏、布局、撤销栈、预览接线、线程守卫。

断言线（只看可观测行为）：

1. **窗口旗标**：最小化/最大化/关闭按钮齐备（缺 ``CloseButtonHint`` 时
   Windows 上关闭按钮失效，用户报障过）；默认开大到 1440×940 但不许
   顶出屏幕可用区域（1920×1080 @125% 的机器可用高只有 824）；
2. **工具栏**：五个工具都是 ToggleButton（选中态有主色高亮）、撤销/还原/
   完成/缩放按钮都在窗口内（单行时会被挤出左上角，2026-10-08 布局重排
   改两行）；**没有游离控件压在左上角**（``__init__`` 里 ``_set_tool``
   被调两次，被遗弃的旧选项页以 (0,0,100,30) 悬着盖住撤销按钮）；
3. **布局**：功能选择条在顶部动作行下方、参数面板在画布右侧、右侧有
   「编辑历史」列表；三个单步确认按钮已全部删除（编辑改为实时生效）；
4. **初始自适应**：窗口就位/改变大小后画布自动适应窗口（占视口
   ``EDIT_FIT_RATIO``，四周留白），手柄视觉尺寸 ≈ 12px（fit 换倍率后
   覆盖层已重算），底层是素色浅底（棋盘格已移除）；
5. **「适应窗口」按钮**：**真点一次**（``clicked`` 会塞 ``checked=False``
   进来，2026-10-08 报障"点一下图片立刻变得非常小"）；
6. **选区门槛**：宽或高 < 4px 的选区视为没有（误点不产生 1px 裁剪）；
7. **撤销/重做/还原**：按步回退/前进、还原可撤销、栈深 ≤ 12 且步骤名与
   快照一一对齐（截断后序号不漂移）；
8. **预览弹窗接线**：有「编辑」按钮、宽度取满（理想 1360，超出屏幕夹进
   可用区域）、无图禁用/有图可用、``_open_editor`` 拿到画布整图且以弹窗
   为父；编辑结果写回后画布就是新图；
9. **崩溃守卫**（2026-10-02，都是用户报过的"程序崩溃/点了没反应"且实测
   复现过）：worker 捕获工作函数异常、``run_with_progress`` 重抛以区分
   失败与取消、正常完成不被收尾 cancel 污染、progress 取消信号可见、
   有 ``closeEvent``、「完成」整体防重入。

（裁剪交互见 ``image_editor_crop.py``，其余主题见 ``image_editor_*.py``。）
"""

from __future__ import annotations

NAME = "image_editor"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·外壳（窗口/工具栏/布局/撤销栈/线程守卫）"


def run(ctx) -> None:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt
    from PySide6.QtGui import QColor, QImage

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import canvas_img, make_image

    from desktop.components.viewers.image_editor import (
        EDIT_FIT_RATIO, ImageEditorDialog,
    )
    from desktop.components.viewers.image_editor.consts import (
        CANVAS_OUTSIDE,
    )

    app = ctx.app
    img = make_image(200, 120)
    dialog = ImageEditorDialog(None, img)
    try:
        ok("弹窗：编辑画布装入了整图",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120, "")

        # ---- 弹窗开大 + 最小化/最大化/关闭按钮 + 工具按钮选中高亮 ----
        # ⚠️ 期望 1440×940 只是**上限**：落地尺寸会被 apply_window_size 夹进
        #    屏幕可用区域（1920×1080 @125% 的机器可用高只有 824）。这里按同
        #    一个公式算期望值，既守住"默认开大"，也守住"不许顶出屏幕"。
        from desktop.components.viewers.image_editor import (
            EDITOR_MIN_SIZE, EDITOR_SIZE,
        )
        from desktop.ui.window_size import (
            FRAME_ALLOWANCE, FIT_RATIO, available_area,
        )

        area = available_area(dialog)
        assert area is not None  # 离屏环境下可用区域总能取到
        expect_w = min(EDITOR_SIZE.width(),
                       int((area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        expect_h = min(EDITOR_SIZE.height(),
                       int((area.height() - FRAME_ALLOWANCE.height()) * FIT_RATIO))
        ok("弹窗：默认开大（1440×940，超出屏幕时夹进可用区域）并带"
           "最小化/最大化/关闭按钮",
           dialog.width() == expect_w and dialog.height() == expect_h
           and dialog.width() <= area.width()
           and dialog.height() + FRAME_ALLOWANCE.height() <= area.height()
           and bool(dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
           and bool(dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint),
           f"size={dialog.width()}x{dialog.height()} 期望={expect_w}x{expect_h} "
           f"可用区={area.width()}x{area.height()} "
           f"flags={hex(int(dialog.windowFlags()))}")
        ok("弹窗：最小尺寸也被夹进可用区域（小屏上仍能拖到放得下）",
           dialog.minimumWidth() <= min(EDITOR_MIN_SIZE.width(), dialog.width())
           and dialog.minimumHeight() <= min(EDITOR_MIN_SIZE.height(), dialog.height()),
           f"min={dialog.minimumWidth()}x{dialog.minimumHeight()}")
        ok("工具栏：工具按钮是 ToggleButton（选中态有主色高亮），"
           "裁剪/变换/扭曲/擦除/文字五个",
           all(type(dialog._tool_buttons[k]).__name__ == "ToggleButton"
               for k in dialog._tool_buttons)
           and set(dialog._tool_buttons) == {"crop", "transform", "distort",
                                             "erase", "text"}
           and dialog._tool_buttons["crop"].isChecked()
           and not dialog._tool_buttons["erase"].isChecked()
           and dialog._tool_buttons["distort"].iconSize() == QSize(14, 14),
           f"tools={sorted(dialog._tool_buttons)} "
           f"crop={dialog._tool_buttons['crop'].isChecked()} "
           f"erase={dialog._tool_buttons['erase'].isChecked()}")
        ok("文字：默认颜色为朱批红",
           dialog._text_color == "#d32f2f", dialog._text_color)
        dialog.set_tool_visible("text", False)
        ok("功能显示：宿主可隐藏文字工具而不影响其他工具",
           dialog._tool_buttons["text"].isHidden()
           and not dialog._tool_buttons["crop"].isHidden(), "")
        dialog.set_tool_visible("text", True)
        ok("功能显示：默认步骤可继续显示文字工具",
           not dialog._tool_buttons["text"].isHidden(), "")

        dialog._set_tool("distort")
        from qfluentwidgets import CheckBox as FluentCheckBox
        from qfluentwidgets import Slider as FluentSlider
        from qfluentwidgets import ComboBox as FluentComboBox

        distortion_page = dialog._option_page
        assert distortion_page is not None
        distortion_combos = distortion_page.findChildren(FluentComboBox)
        distortion_sliders = distortion_page.findChildren(FluentSlider)
        distortion_checks = distortion_page.findChildren(FluentCheckBox)
        ok("扭曲工具：参数面板提供七种笔刷模式、三种插值、大小/硬度/强度/间距和预览开关",
           dialog.canvas._tool == "distort"
           and {combo.currentData() for combo in distortion_combos}
           == {"move", "cubic"}
           and sorted(slider.value() for slider in distortion_sliders)
           == [10, 50, 50, 117]
           and len(distortion_checks) == 2
           and any(check.text() == "实时预览" and check.isChecked()
                   for check in distortion_checks)
           and any(check.text() == "高质量预览" and check.isChecked()
                   for check in distortion_checks),
           f"combos={[c.currentData() for c in distortion_combos]} "
           f"sliders={[s.value() for s in distortion_sliders]} "
           f"checks={len(distortion_checks)}")
        dialog._set_tool("crop")

        # ---- 初始自适应 + 两行工具栏（需要真实布局几何，先显示） ----
        dialog.show()
        app.processEvents()
        dialog.resize(1000, 720)
        app.processEvents()
        app.processEvents()
        canvas = dialog.canvas
        vw, vh = canvas.viewport().width(), canvas.viewport().height()
        # 图片占视口 EDIT_FIT_RATIO（缺省不铺满，四周留白，用户 2026-10-02 定）
        expected = EDIT_FIT_RATIO * min(vw / 200, vh / 120)
        ok("画布：窗口就位后自动适应窗口（修复初始过小，四周留白）",
           abs(canvas.transform().m11() - expected) <= expected * 0.05
           and canvas._user_zoomed is False,
           f"m11={canvas.transform().m11():.3f} expected={expected:.3f} "
           f"viewport={vw}x{vh}")
        # 手柄视觉尺寸 = 视图像素(12) ÷ 倍率 × 倍率 ≈ 12px：fit() 换倍率后
        # 必须重算覆盖层，否则 set_image 时脏 viewport 算的小倍率会留下巨型手柄
        tl_view = canvas.mapFromScene(
            canvas._handle_boxes(canvas.image_rect())["tl"]).boundingRect()
        ok("画布：手柄视觉尺寸 ≈ 12px（fit 换倍率后覆盖层已重算）",
           7 <= tl_view.width() <= 20 and 7 <= tl_view.height() <= 20,
           f"tl_view={tl_view.width():.1f}x{tl_view.height():.1f}")

        # 画布配色（用户 2026-10-09「背景灰色太突兀」→ 2026-10-13「去除底层
        # 方块格子」）：棋盘格已整体移除，视口只剩一层素色浅底（图外与图内
        # 同色，透明区域露的就是它）；这条只守"底色必须够浅、不抢戏"。
        ok("画布：底层为素色浅底（棋盘格已移除）",
           CANVAS_OUTSIDE.lightness() >= 220,
           f"outside={CANVAS_OUTSIDE.lightness()}")

        # ---- 「适应窗口」按钮：**真点一次**（clicked 会塞 checked=False 进来）----
        # 回归（2026-10-08 用户报「使用窗口，图片立马变得非常小」）：此前是
        # ``fit_btn.clicked.connect(self.canvas.fit)``，fit(ratio) 收到
        # checked=False ⇒ float(False)=0.0 被夹成下限 0.2，图缩成视口的 1/4。
        canvas.zoom_in()
        canvas.zoom_in()
        zoomed = canvas.transform().m11()
        assert zoomed > expected * 1.05  # 先确认真的偏离了 fit 值，否则下条是假绿
        dialog.fit_btn.click()
        app.processEvents()
        fit_m11 = canvas.transform().m11()
        ok("「适应窗口」按钮：点一下回到 fit 倍率（不再被 clicked 的 False 缩成 1/4）",
           abs(fit_m11 - expected) <= expected * 0.05,
           f"点前 {zoomed:.3f} 点后 {fit_m11:.3f} expected={expected:.3f}")
        ok("「适应窗口」按钮：直接喂一个 bool 也不会缩水（兜底）",
           (canvas.fit(False), app.processEvents())[1] is None
           and abs(canvas.transform().m11() - expected) <= expected * 0.05,
           f"m11={canvas.transform().m11():.3f} expected={expected:.3f}")

        # ---- 采样方式随倍率切换（2026-10-25 用户：「编辑放大后要高清」）----
        # 100% 以上没有更多像素可看，继续平滑只会把像素糊成一团；按像素格
        # 显示（最近邻）才是编辑器该有的"放大也清晰"。
        from PySide6.QtCore import Qt as _Qt

        canvas.set_zoom(0.5)
        ok("编辑画布：缩小显示走平滑采样（大图缩小不出锯齿）",
           canvas._item is not None
           and canvas._item.transformationMode()
           == _Qt.TransformationMode.SmoothTransformation, "")
        canvas.set_zoom(2.0)
        ok("编辑画布：≥100% 走像素级采样（像素不发虚）",
           canvas._item is not None
           and canvas._item.transformationMode()
           == _Qt.TransformationMode.FastTransformation, "")
        canvas.fit()

        # ---- 布局（2026-10-08 重排）：顶部功能选择 + 右侧参数面板 ----
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QAbstractButton

        header_bottom = dialog.undo_btn.y() + dialog.undo_btn.height()
        tools_at = dialog._tool_buttons["crop"].mapTo(dialog, QPoint(0, 0))
        page_at = dialog._option_page.mapTo(dialog, QPoint(0, 0))
        ok("布局：功能选择条在顶部（动作行下方），五个工具都在窗口内",
           tools_at.y() >= header_bottom
           and all(
               dialog._tool_buttons[k].mapTo(dialog, QPoint(0, 0)).x() >= 0
               and dialog._tool_buttons[k].geometry().right()
               <= dialog.width()
               for k in dialog._tool_buttons
           ),
           f"tools@{tools_at} header.bottom={header_bottom}")
        ok("布局：参数面板在画布右侧（不在工具栏那一行里）",
           page_at.x() >= dialog.canvas.geometry().right()
           and page_at.y() >= header_bottom,
           f"page@{page_at} canvas.right={dialog.canvas.geometry().right()}")
        ok("布局：右侧面板有「编辑历史」列表（第 0 格是打开时的状态）",
           dialog.history_list.isVisible()
           and dialog.history_list.count() >= 1
           and dialog.history_list.item(0).text() == "打开"
           and dialog.history_list.currentRow()
           == dialog.history_list.count() - 1,
           f"n={dialog.history_list.count()} "
           f"行={dialog.history_list.currentRow()}")
        banned = {"应用裁剪", "应用变换", "插入文字"}
        leftovers = [b.text() for b in dialog.findChildren(QAbstractButton)
                     if b.text() in banned]
        ok("布局：三个单步确认按钮已全部删除（编辑改为实时生效）",
           not leftovers, f"残留={leftovers}")
        # 回归（2026-09-30 用户截图）：__init__ 里 _set_tool 被调两次，
        # 被遗弃的旧选项页以默认几何 (0,0,100,30) 悬在左上角盖住撤销按钮
        # （deleteLater 在构造期不生效）。所有可见直儿子都不许落在 (0,0)。
        from PySide6.QtWidgets import QWidget as _QW

        strays = [
            c for c in dialog.findChildren(_QW)
            if c.parent() is dialog and c.isVisible()
            and c.x() == 0 and c.y() == 0
        ]
        ok("工具栏：没有游离控件压在左上角（旧选项页不会盖住撤销按钮）",
           not strays,
           f"strays={[f'{type(c).__name__}@{c.geometry().getRect()}' for c in strays]}")
        app.processEvents()

        # 选区门槛：< 4px 视为没有
        dialog.canvas.set_tool("crop")
        dialog.canvas._rect = QRectF(10, 10, 3, 60)
        ok("选区：小于 4px 的选区视为没有", dialog.canvas.selection() is None, "")
        dialog.canvas._rect = QRectF(10, 10, 3, 3)
        ok("选区：小于 4px 的方块也视为没有",
           dialog.canvas.selection() is None, "")

        # 裁剪 + 撤销 + 重做 + 还原
        dialog._reset_all()          # 前面的用例已把图裁成 140×90，先回 200×120
        dialog.canvas._rect = QRectF(0, 0, 100, 120)
        dialog._preview_crop()
        ok("裁剪：松手只记下待定裁剪、像素一个都没动",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120
           and dialog._pending_crop is not None, "")
        dialog._commit_crop()
        ok("裁剪：落定后画布尺寸 = 选区尺寸",
           canvas_img(dialog.canvas).width() == 100
           and canvas_img(dialog.canvas).height() == 120, "")
        ok("裁剪：落定（换图）后裁剪区重新默认全选新图",
           dialog.canvas.selection() == dialog.canvas.image_rect(),
           f"sel={dialog.canvas.selection()}")
        dialog._undo_now()
        ok("撤销：裁剪被完整回退",
           canvas_img(dialog.canvas).width() == 200
           and canvas_img(dialog.canvas).height() == 120, "")
        dialog._redo_now()
        ok("重做：裁剪被重新应用", canvas_img(dialog.canvas).width() == 100, "")
        dialog._reset_all()
        ok("还原：回到打开时的图", canvas_img(dialog.canvas).width() == 200, "")
        dialog._undo_now()
        ok("还原本身可撤销：回到还原前的裁剪结果",
           canvas_img(dialog.canvas).width() == 100, "")

        # 栈深上限
        for _ in range(20):
            dialog._push_undo()
        ok("撤销栈：深度被夹在 12 以内", len(dialog._undo) <= 12,
           f"depth={len(dialog._undo)}")
        ok("撤销栈：步骤名与快照一一对齐（截断后序号也不漂移）",
           len(dialog._labels) == len(dialog._undo) + len(dialog._redo)
           and dialog._origin_label != "打开",
           f"labels={len(dialog._labels)} undo={len(dialog._undo)} "
           f"redo={len(dialog._redo)} origin={dialog._origin_label!r}")

    finally:
        dialog.deleteLater()

    # ---- 7/8. 预览弹窗接线 ----
    from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

    zoom = ImageZoomDialog(None)
    try:
        ok("预览弹窗：工具条上有「编辑」按钮",
           getattr(zoom, "edit_btn", None) is not None, "")
        # 期望 1360 宽（一行摆得下缩放/朝向/翻页/打印/下载/编辑），但落地尺寸
        # 会先被夹进屏幕可用区域——按同一个公式算期望值，别写死 1280。
        from desktop.components.viewers.image_zoom_dialog import ZOOM_DIALOG_SIZE
        from desktop.ui.window_size import (
            FRAME_ALLOWANCE, FIT_RATIO, available_area,
        )

        zoom_area = available_area(zoom)
        assert zoom_area is not None  # 离屏环境下可用区域总能取到
        zoom_w = min(ZOOM_DIALOG_SIZE.width(),
                     int((zoom_area.width() - FRAME_ALLOWANCE.width()) * FIT_RATIO))
        ok("预览弹窗：宽度取满（理想 1360，超出屏幕时夹进可用区域）",
           zoom.width() == zoom_w and zoom.width() <= zoom_area.width(),
           f"width={zoom.width()} 期望={zoom_w} 可用区={zoom_area.width()}")
        ok("预览弹窗：无图时编辑按钮禁用", not zoom.edit_btn.isEnabled(), "")
        zoom.canvas.set_image(make_image(64, 48))
        zoom._sync_controls()
        ok("预览弹窗：有图时编辑按钮可用", zoom.edit_btn.isEnabled(), "")
        source = zoom.canvas.export_image()
        assert source is not None  # 刚 set 过图，导出必有
        editor = zoom._open_editor(source)
        ok("预览弹窗：_open_editor 拿到画布整图",
           editor is not None
           and editor.canvas.image is not None
           and editor.canvas.image.width() == source.width()
           and editor.canvas.image.height() == source.height(), "")
        assert editor is not None  # 上一条 ok 已断言编辑器打开成功
        ok("预览弹窗：编辑器以弹窗为父（生命周期跟随）",
           editor.parent() is zoom, "")
        editor.deleteLater()

        # 编辑结果写回：set_image 通道替换画布图（_edit_image 内同款调用）
        edited = make_image(30, 20)
        zoom.canvas.set_image(edited)
        _written_back = zoom.canvas.export_image()
        assert _written_back is not None  # 刚 set 过图，导出必有
        ok("预览弹窗：编辑结果写回后画布就是新图",
           _written_back.width() == 30, "")
        zoom._sync_controls()
    finally:
        zoom.deleteLater()
        zoom.shutdown_workers()
    app.processEvents()

    # ---- 崩溃守卫（2026-10-02）：后台线程的异常/取消/收尾 ----
    # 这几条守的都是用户报过的"程序崩溃 / 点了没反应"，且都**实测复现过**。
    from desktop.components.viewers.image_editor import (
        ImageEditorDialog as _Ed, _BakeWorker, run_with_progress)

    def _drain(w):
        from PySide6.QtWidgets import QApplication as _QA
        while not w.wait(20):
            _QA.processEvents()

    # 1. worker 里抛的异常必须被**捕获**（原来它逃出 QThread.run，
    #    result 停在 None、cancelled 是 False，被上层当成"用户取消"）
    def _boom(_params, _progress):
        raise MemoryError("模拟大图内存不足")

    w = _BakeWorker(_boom, {})
    w.start()
    _drain(w)
    ok("崩溃守卫：worker 捕获工作函数异常（不是让它逃出 QThread.run）",
       isinstance(w.error, MemoryError),
       f"→ error={type(w.error).__name__ if w.error else None}")
    ok("崩溃守卫：异常时线程正常结束（不留孤儿）", w.isFinished(), "")

    # 2. run_with_progress 必须**重抛**，让上层能区分"失败"与"用户取消"
    host = _Ed()
    try:
        run_with_progress(host, "t", "l", _boom, {})
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", False, "没有抛")
    except MemoryError:
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", True, "")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：失败时重抛异常（上层弹提示+退撤销点）", False,
           f"抛了别的 {type(exc).__name__}")

    # 3. 正常完成仍要拿到结果（别被收尾的 cancel() 误标成"取消"）
    ok("崩溃守卫：正常完成返回结果（收尾 cancel 不污染语义）",
       run_with_progress(host, "t", "l",
                         lambda p, pr: (pr(1, 2), "结果图")[1], {}) == "结果图", "")

    # 4. progress 的取消信号：工作函数要能看见
    wc = _BakeWorker(lambda p, pr: None, {})
    a1 = wc.progress(1, 10)
    wc.cancelled = True
    a2 = wc.progress(2, 10)
    wc.cancelled = False
    ok("崩溃守卫：progress 取消信号（未取消 True / 取消 False）",
       a1 is True and a2 is False, f"→ {a1}, {a2}")

    # 5. closeEvent 存在且关窗不炸（缺它 ⇒ 线程在飞时析构 ⇒
    #    QThread: Destroyed while thread is still running ⇒ abort）
    ok("崩溃守卫：编辑器有 closeEvent（关窗时收尾在飞线程）",
       hasattr(_Ed, "closeEvent"), "")
    try:
        host.close()
        ok("崩溃守卫：关窗正常（不 abort）", True, "")
    except Exception as exc:                # noqa: BLE001
        ok("崩溃守卫：关窗正常（不 abort）", False, repr(exc))

    # 6. 「完成」整体防重入（三个 busy 标志只挡同名方法，挡不住整体重入）
    ed2 = _Ed()
    calls = []
    for name in ("_commit_transform", "_commit_text_blocks"):
        # ⚠️ *a, **k：_commit_transform 现在带 force 关键字（「完成」收尾用），
        #    桩只管记账，别绑死签名。
        setattr(ed2, name,
                (lambda n: lambda *a, **k: calls.append(n))(name))
    ed2._finish()
    first = list(calls)
    ed2._finishing = True            # 模拟烘焙中 processEvents 派发第二次点击
    ed2._finish()
    ok("崩溃守卫：双击「完成」不重入（_finishing 挡住）",
       calls == first, f"→ 实际 {len(calls)} 次调用")
    ed2._finishing = False
    ed2.deleteLater()

    host.deleteLater()
    app.processEvents()