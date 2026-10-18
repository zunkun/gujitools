# -*- coding: utf-8 -*-
"""「定位图片资源」在各步骤的正确性（用户 2026-10-17，2026-10-18 修订）。

报障：任务 0016 第二个「图片拼版」节点里右键图片，「定位到图片资源」不对；
2026-10-18 用户进一步明确：拼版这一步的"图片资源"是**拼版后的图片**
（``stages/imposition[~<节点>]`` —— 实时重合成产出新图），不是画布上那张
输入源图（如 ``stages/input``）。顺带按「检查每一步图片需要定位」把所有定位
入口对了一遍，钉住三件事：

1. **定位＝右键的那一张**：拼版画布命中按旋转后的矩形算、选中项优先，
   两图并排时不能错一格（错一格就是"定位错了"）；
2. **定位与编辑解耦**：拼版的图按现行口径不给单图编辑（编辑统一作用于整页），
   但它背后有真实文件（成品），仍必须能定位（``ZoomTarget.locate_path``
   独立于 ``edit_path``；拼版画布另有 ``set_locate_resolver``）；
3. **定位失败不许静默**：文件被删/目录不在时要说明（静默什么都不发生，
   用户只会以为定位到了错误的资源）。

各步骤的定位来源（本用例覆盖前两处，后三处由既有用例覆盖）：

| 步骤 | 定位到什么 |
| --- | --- |
| 图片提取 | 页面图文件本身（``edit_path``） |
| 检测文本框 | 页面图文件本身 |
| 图片去底色 | 显示的是原图→原图；显示正式结果→结果图（临时合成→不给） |
| 图片拼版 | **本页拼版成品页**（``stages/imposition[~<节点>]``）；没合成→成品目录 |
| PDF 排版 | 待打印的那张图（第三步提交产物／拼版成品） |
"""

NAME = "locate_resource"
DEPENDS: list[str] = []
TITLE = "定位图片资源（各步骤）"


def run(ctx) -> None:
    import os
    from pathlib import Path

    from tests.selftests._context import ok
    from tests.tmpdir import temp_dir

    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    import desktop.utils.files as files_mod
    import desktop.components.imposition.canvas as canvas_mod
    from desktop.components.imposition.canvas import ImpositionCanvas
    from desktop.components.viewers.image_zoom_dialog.canvas import ZoomTarget

    # ---- 1. ZoomTarget：定位与编辑解耦 ----
    src = Path(temp_dir("locate_")) / "0007.png"
    src.write_bytes(b"x")

    t_both = ZoomTarget(render=lambda _e: None, stem="a",
                        edit_path=src, locate_path=src)
    ok("同时给 edit_path/locate_path：两者各自成立",
       t_both.edit_path == src and t_both.locate_path == src)

    t_edit_only = ZoomTarget(render=lambda _e: None, stem="b", edit_path=src)
    ok("只给 edit_path 时定位回落它（不传的调用方行为不变）",
       t_edit_only.locate_path == src, str(t_edit_only.locate_path))

    t_locate_only = ZoomTarget(render=lambda _e: None, stem="c", locate_path=src)
    ok("只给 locate_path：能定位但**不可编辑**（edit_path 为 None）",
       t_locate_only.locate_path == src and t_locate_only.edit_path is None,
       f"locate={t_locate_only.locate_path} edit={t_locate_only.edit_path}")

    # ---- 2. 右键菜单：只要定位路径在就给「定位图片资源」 ----
    from desktop.components.viewers.image_zoom_dialog.popup import ZoomPopupMixin

    class _Host(ZoomPopupMixin):
        """最小宿主：直接给一个 target，只看菜单该有哪些项。"""

        def __init__(self, target):
            self._zoom_dialog = None
            self._zoom_editable = True
            self._target = target

        def _zoom_index(self):
            return 0

        def _zoom_target(self, _index):
            return self._target

    labels_edit = [it[0] for it in _Host(t_both)._zoom_menu_items(t_both)]
    ok("有可编辑文件时：预览 / 编辑 / 定位 三项齐全",
       labels_edit == ["预览图片", "编辑图片", "定位图片资源"], str(labels_edit))

    labels_locate = [
        it[0] for it in _Host(t_locate_only)._zoom_menu_items(t_locate_only)
    ]
    ok("只有定位路径时：给「定位图片资源」、**不给**编辑",
       labels_locate == ["预览图片", "定位图片资源"], str(labels_locate))

    labels_none = [
        it[0] for it in _Host(ZoomTarget(render=lambda _e: None, stem="d"))
        ._zoom_menu_items(ZoomTarget(render=lambda _e: None, stem="d"))
    ]
    ok("两者都没有时：只有预览（不弹死按钮）",
       labels_none == ["预览图片"], str(labels_none))

    # ---- 3. 拼版画布：右键哪一张就定位哪一张 ----
    picked: list[str] = []
    original_reveal = files_mod.reveal_in_explorer
    # 让替身按"文件真在不在"回答：不存在就继续试下一个候选（与真
    # reveal_in_explorer 一致——它不存在就返回 False，调用方才有退路）
    files_mod.reveal_in_explorer = (
        lambda p: picked.append(str(p)) or Path(p).exists()
    )
    try:
        a = Path(temp_dir("locate_a_")) / "0001-r.png"
        b = Path(temp_dir("locate_b_")) / "0001-l.png"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        canvas = ImpositionCanvas()
        canvas.resize(900, 700)
        canvas.set_page([
            {"file": str(a), "rect": [0, 0, 400, 600], "rotation": 0.0},
            {"file": str(b), "rect": [400, 0, 400, 600], "rotation": 0.0},
        ])
        # 取每一项在控件上的中心点 → 命中 → 定位
        for expect_index in (0, 1):
            rect = canvas._rect_px(expect_index)
            hit = canvas._item_at(QPointF(rect.center()))
            canvas._selected = -1  # 别让"选中项优先"顶掉命中结果
            canvas._locate_item_file(hit)
        ok("没给解析器时：定位的就是被右键的那一张（两图并排不错格）",
           [Path(p).name for p in picked] == ["0001-r.png", "0001-l.png"],
           str(picked))

        # 选中的图优先：重叠时点重叠区定位的是选中那张（与画面上"最上面"一致）
        canvas.set_page([
            {"file": str(a), "rect": [0, 0, 400, 600], "rotation": 0.0},
            {"file": str(b), "rect": [100, 0, 400, 600], "rotation": 0.0},
        ])
        canvas._selected = 1
        overlap = QPointF(canvas._rect_px(1).center())
        ok("重叠区命中选中的那张（定位与画面分层一致）",
           canvas._item_at(overlap) == 1, str(canvas._item_at(overlap)))
        canvas.deleteLater()

        # ⚠️ 拼版这一步：宿主给**成品**解析器后，定位的是**拼版后的图片**
        #    （用户 2026-10-18），不再是画布上那张输入源图。
        prod_dir = temp_dir("locate_prod_")
        prod = prod_dir / "0001.png"
        prod.write_bytes(b"y")
        canvas_prod = ImpositionCanvas()
        canvas_prod.resize(900, 700)
        canvas_prod.set_page([
            {"file": str(a), "rect": [0, 0, 400, 600], "rotation": 0.0},
        ])
        canvas_prod.set_locate_resolver(
            lambda _i, d=prod_dir, f=prod: [f, d]
        )
        picked.clear()
        canvas_prod._locate_item_file(0)
        ok("拼版给了解析器 → 定位的是成品页，而不是输入源图",
           picked[-1] == str(prod) and str(a) not in picked, str(picked))
        canvas_prod.deleteLater()

        # 成品页还没合成出来 → 退到**成品目录**（至少到这一批产物跟前），
        # 且**不回退**到输入源图（用户明确说那不是拼版的图片资源）
        canvas_pending = ImpositionCanvas()
        canvas_pending.resize(900, 700)
        canvas_pending.set_page([
            {"file": str(a), "rect": [0, 0, 400, 600], "rotation": 0.0},
        ])
        canvas_pending.set_locate_resolver(
            lambda _i, d=prod_dir: [d / "0009.png", d]
        )
        picked.clear()
        canvas_pending._locate_item_file(0)
        ok("成品页还没合成 → 退到成品目录（不回退到输入源图）",
           picked[-1] == str(prod_dir) and str(a) not in picked, str(picked))
        canvas_pending.deleteLater()
    finally:
        files_mod.reveal_in_explorer = original_reveal

    # ---- 4. 定位失败不许静默 ----
    failures: list[str] = []
    files_mod.reveal_in_explorer = lambda _p: False  # 模拟文件已不存在
    try:
        canvas2 = ImpositionCanvas()
        canvas2.resize(900, 700)
        gone = Path(temp_dir("locate_gone_")) / "0001-r.png"  # 不创建
        canvas2.set_page([
            {"file": str(gone), "rect": [0, 0, 400, 600], "rotation": 0.0},
        ])
        canvas2.locate_failed.connect(failures.append)
        canvas2._locate_item_file(0)
        ok("源文件缺失时给出说明（不静默装死）",
           bool(failures) and "不存在" in failures[-1], str(failures))
        canvas2.deleteLater()

        # 目录也不在：仍要有话说，而不是什么都不发生
        failures.clear()
        canvas3 = ImpositionCanvas()
        canvas3.resize(900, 700)
        nowhere = Path(temp_dir("locate_nodir_")) / "no" / "such" / "x.png"
        canvas3.set_page([
            {"file": str(nowhere), "rect": [0, 0, 400, 600], "rotation": 0.0},
        ])
        canvas3.locate_failed.connect(failures.append)
        canvas3._locate_item_file(0)
        ok("连目录都不在时同样给出说明",
           bool(failures) and "找不到文件" in failures[-1], str(failures))
        canvas3.deleteLater()
    finally:
        files_mod.reveal_in_explorer = original_reveal

    # ---- 5. 各步骤的定位来源（源码级守卫：不许把定位绑死在 edit_path 上） ----
    import inspect

    from desktop.pages.taskdetail import imposition_layout

    # ⚠️ 拼版这一步的"图片资源"是**拼版成品**（`stages/imposition[~<节点>]`，
    #    会实时重合成产出新图），不是画布上那张输入源图（用户 2026-10-18）。
    locate_src = inspect.getsource(
        imposition_layout.ImpositionLayoutMixin._imposition_locate_targets
    )
    ok("任务流程·拼版定位：落点走**成品**（成品页 → 成品目录）",
       "product_path(" in locate_src
       and "_imposition_output_dir()" in locate_src
       and "targets.append(output)" in locate_src,
       "拼版没把定位指向成品")

    spread_src = inspect.getsource(
        imposition_layout.ImpositionLayoutMixin._imposition_spread_target
    )
    ok("任务流程·拼版整页组合：成品在就定位成品、否则退到源图目录",
       "locate_path=locate_path" in spread_src
       and "first.parent.is_dir()" in spread_src,
       "整页组合没有定位回退")

    from desktop.modules.imposition import page as module_imposition

    # 独立页的方法名以实际为准，这里只查文件文本，避免把断言绑死在方法名上
    module_text = Path(module_imposition.__file__).read_text(encoding="utf-8")
    ok("独立拼版页：单张原图与整页组合都带 locate_path",
       module_text.count("locate_path=path") >= 1
       and "locate_path=locate_path" in module_text,
       "独立页的定位入口不全")

    # ⚠️ 任务流程的拼版画布必须**挂上成品解析器**（不挂就退到源图，用户报过）
    view_src = (
        Path(imposition_layout.__file__).parent / "view.py"
    ).read_text(encoding="utf-8")
    ok("任务流程·拼版画布挂了「定位成品」解析器",
       "set_locate_resolver" in view_src
       and "_imposition_locate_targets" in view_src,
       "画布没挂成品解析器")

    # ---- 6. 失败信号贯通到宿主（页面上真能看见）----
    from desktop.components.imposition.view import ImpositionViewWidget

    ok("画布 → 视图 有 locate_failed 信号",
       hasattr(ImpositionCanvas, "locate_failed")
       and hasattr(ImpositionViewWidget, "locate_failed"), "信号没贯通")
