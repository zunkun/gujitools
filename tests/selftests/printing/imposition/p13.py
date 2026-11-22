# -*- coding: utf-8 -*-
"""8. 双击图片编辑整页；双击空白预览组合 / 画布层：命中分流（图上 → item，图外空白 → spread） / 视图层：信号 → 信号直连转发 + 提示语带双击说明 / worker 层：合成结果 = page_bounds 紧裁（即灰色虚线框那块） / 控制器层：_open_imposition_spread_preview 开弹窗（替身）"""

from typing import Any


def run(st: Any) -> None:
    from desktop.components.imposition.canvas import ImpositionCanvas
    from desktop.components.imposition.view import ImpositionViewWidget
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, QSize, Qt
    from desktop.services import imposition as S
    from desktop.components.viewers import image_zoom_dialog as _izd
    from typing import cast
    from tests.selftests._context import make_pdf, ok, pump
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent

    def _dbl(cv, x, y):
        return QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(float(x), float(y)),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    st._dbl = _dbl
    canvas3 = ImpositionCanvas()
    canvas3.resize(600, 600)
    canvas3.set_page(S.default_items([str(st.a), str(st.b)]))
    canvas3.show()
    st.ctx.app.processEvents()

    def _blank_pt(cv):
        """画布上的空白点：场景顶边（=所有图外接框上沿）再往上 6px。"""
        r = cv._rect_px(0)
        return (r.center().x(), max(2.0, cv._off_y - 6.0))
    st._blank_pt = _blank_pt

    def _item_pt(cv, index=0):
        """某张图 rect 里的点（取中心；默认版面两图不重叠）。"""
        c = cv._rect_px(index).center()
        return (c.x(), c.y())
    st._item_pt = _item_pt

    spread_hits: list[int] = []
    edit_hits: list[int] = []
    canvas3.spread_double_clicked.connect(lambda: spread_hits.append(1))
    canvas3.item_edit_requested.connect(edit_hits.append)
    bx, by = st._blank_pt(canvas3)
    canvas3.mouseDoubleClickEvent(st._dbl(canvas3, bx, by))
    ok(
        "双击图片之外的空白 → 发 spread_double_clicked（预览组合）",
        spread_hits == [1] and edit_hits == [],
        f"spread={spread_hits} edit={edit_hits}",
    )
    ok(
        "双击空白不把手势带起来（处理了就 accept，无编辑模式残留）",
        canvas3._mode is None and not canvas3._pressed,
        f"mode={canvas3._mode} pressed={canvas3._pressed}",
    )
    # 右槽图中心（x∈[400,800] 图坐标 → 约 [300,582] 控件像素）
    ix, iy = st._item_pt(canvas3, 0)
    canvas3.mouseDoubleClickEvent(st._dbl(canvas3, ix, iy))
    ok(
        "双击某张图 → 发 item_edit_requested 且是命中的槽位",
        edit_hits == [0] and spread_hits == [1],
        f"edit={edit_hits} spread={spread_hits}",
    )
    spread_hits.clear()
    edit_hits.clear()
    canvas3.clear_page()
    canvas3.mouseDoubleClickEvent(st._dbl(canvas3, 300, 40))
    ok(
        "空画布双击不发预览或编辑信号",
        spread_hits == [] and edit_hits == [],
        f"spread={spread_hits} edit={edit_hits}",
    )
    canvas3.deleteLater()
    view2 = ImpositionViewWidget()
    view2.resize(900, 600)
    view2.show()
    st.ctx.app.processEvents()
    view2.set_pages([{"items": S.default_items([str(st.a), str(st.b)])}], current=0)
    view_forward: list[str] = []
    view2.spread_preview_requested.connect(lambda: view_forward.append("spread"))
    view2.item_preview_requested.connect(lambda i: view_forward.append(f"item:{i}"))
    view2.item_edit_requested.connect(lambda i: view_forward.append(f"edit:{i}"))
    vb = st._blank_pt(view2.canvas)
    vi = st._item_pt(view2.canvas, 0)
    view2.canvas.mouseDoubleClickEvent(st._dbl(view2.canvas, *vb))
    view2.canvas.mouseDoubleClickEvent(st._dbl(view2.canvas, *vi))
    ok(
        "双击空白预览整页，双击图片编辑整页",
        view_forward == ["spread", "edit:0"],
        str(view_forward),
    )
    ok(
        "底部提示语写明双击编辑与空白预览",
        "双击" in view2.hint.text()
        and "编辑整页" in view2.hint.text()
        and "成品组合" in view2.hint.text(),
        view2.hint.text(),
    )
    view2.deleteLater()
    page_items = st.page._imposition_pages()[0]["items"]
    # ⚠️ 该方法的返回标注是 ``object | None``（宿主侧没写具体类型），
    #    这里按"就是 ZoomTarget"定死；None 的判据留给下一条 ok。
    target = cast("ZoomTarget", st.page._imposition_spread_target(0))
    ok(
        "弹窗来源目标：整页左右组合（count=1，非单张原图）",
        target is not None and target.count == 1 and "左右组合" in target.note,
        str(target and target.note),
    )
    assert target is not None  # ⚠️ 上一行已判过
    ok(
        "拼版预览编辑目标默认隐藏文字工具",
        not target.show_text_tool,
        str(target.show_text_tool),
    )
    # 用户 2026-10-18：「预览图片」/「定位图片资源」要作用于**拼版后的图片**
    # （成品组合/成品页），不是画布上那张输入源图。这里钉住定位落点。
    locate_targets = st.page._imposition_locate_targets(0)
    _out_dir = st.page._imposition_output_dir()
    ok(
        "右键「定位图片资源」落点 = 本页拼版成品页 → 本节点成品目录",
        locate_targets
        and locate_targets[0].parent == _out_dir
        and locate_targets[-1] == _out_dir,
        str(locate_targets),
    )
    bounds = S.page_bounds({"items": [dict(i) for i in page_items]})
    _worker = target.render(1600)
    _got: dict = {}
    _worker.finished.connect(lambda _i, img, _s: _got.update(img=img))
    _worker.run()
    img = _got.get("img")
    ok(
        "组合预览 worker 产出非空 QImage",
        img is not None and not img.isNull(),
        str(type(img)),
    )
    if img is not None and not img.isNull():
        ratio_got = img.width() / img.height()
        ratio_bounds = (bounds[2] - bounds[0]) / (bounds[3] - bounds[1])
        ok(
            "预览图宽高比 = 灰色虚线框（page_bounds）的宽高比",
            abs(ratio_got - ratio_bounds) < 0.01,
            f"图 {img.width()}x{img.height()} vs 界 {bounds}",
        )
    from desktop.components.viewers import image_zoom_dialog as _izd

    _seen_zoom: dict = {}

    class _FakeZoom:
        def __init__(self, *a, **k):
            _seen_zoom["factory"] = k.get("factory")
            _seen_zoom["shown"] = 0
            _seen_zoom["show_for"] = []

            # 控制器会把弹窗编辑的 image_saved 接到生效链上（鸭子类型即可）
            class _Sig:
                def connect(self, _slot):
                    pass

            self.image_saved = _Sig()

        def show(self):
            _seen_zoom["shown"] += 1

        def raise_(self):
            pass

        def activateWindow(self):
            pass

        def show_for(self, factory=None, index=0):
            _seen_zoom["show_for"].append((factory is not None, index))

        def close(self):
            pass

    _real_zoom_cls = _izd.ImageZoomDialog
    _izd.ImageZoomDialog = _FakeZoom
    try:
        st.page._open_imposition_spread_preview()
        ok(
            "双击空白 → 控制器 show + show_for 打开预览弹窗",
            _seen_zoom.get("shown") == 1
            and _seen_zoom.get("show_for") == [(True, 0)],
            str(_seen_zoom),
        )
        zoom_target = (_seen_zoom.get("factory") or (lambda _i: None))(0)
        ok(
            "弹窗内容来源 = 左右组合目标（不是单张原图）",
            zoom_target is not None
            and zoom_target.count == 1
            and "左右组合" in zoom_target.note,
            str(zoom_target and zoom_target.note),
        )
    finally:
        _izd.ImageZoomDialog = _real_zoom_cls
        # ⚠️ 弹窗已关掉，宿主把持有者置回 None（源码侧标注成非 Optional）
        st.page._imposition_zoom_dialog = None  # type: ignore[reportAttributeAccessIssue]

