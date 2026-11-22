# -*- coding: utf-8 -*-
"""完成双图编辑：新画布原点/尺寸要回写为页面版面 rect / 带透明留白的源图：入口版面对齐 + 移动后尺寸不回缩"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import _make_image
    from desktop.components.viewers.image_editor import ImageEditorDialog
    from desktop.pages.taskdetail.imposition_layout import ImpositionLayoutMixin
    from desktop.modules.imposition.page import ImpositionModulePage
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtGui import QColor, QPainter, QPen
    from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
    from types import SimpleNamespace
    from desktop.services.imposition import apply_editor_layout
    from tests.selftests._context import ok
    from tests.common.tmpdir import temp_dir
    from tests.common.tmpdir import temp_dir

    output_dir = temp_dir("guji_editor_layout_")
    left6 = _make_image(200, 100, "#ffffff")
    right6 = _make_image(150, 80, "#dddddd")
    left_path = output_dir / "left.png"
    right_path = output_dir / "right.png"
    assert left6.save(str(left_path)) and right6.save(str(right_path))
    dialog6 = ImageEditorDialog(None, left6, save_back=True)
    dialog6.configure_multiple_images([
        {"image": left6, "file": str(left_path), "rect": (0, 0, 200, 100)},
        {"image": right6, "file": str(right_path),
         "rect": (250, 10, 150, 80)},
    ])
    layout_updates = []
    dialog6.multi_layout_saved.connect(layout_updates.append)
    dialog6._activate_layer(1)
    dialog6._pending_crop = QRectF(20, 5, 120, 60)
    dialog6._commit_crop()
    ok("双图编辑保存：裁剪后的画布位置和尺寸回传页面",
       dialog6._save_multiple_images()
       and layout_updates == [[{
           "index": 1,
           "file": str(right_path),
           # ⚠️ 2026-10-15：位移口径 ＝ **内容框在新画布里的偏移** ＋
           #    **画布原点平移 origin**（两者之和）。**纯裁剪**内容框偏移为 0，
           #    但新画布从被裁掉的 ``box``(20,5) 起 ⇒ 剩下的内容在页面上整体
           #    右/下移一个 ``box`` ⇒ 版面框 = 250+20 / 10+5。只取内容框偏移
           #    会让位置不回写（页面没动、弹窗里却挪了）。
           "rect": [270.0, 15.0, 120.0, 60.0],
       }]],
       f"updates={layout_updates}")
    from desktop.services.imposition import apply_editor_layout

    page_items = [
        {"file": str(left_path), "rect": [0, 0, 200, 100]},
        {"file": str(right_path), "rect": [250, 10, 150, 80]},
    ]
    changed_layout_files = apply_editor_layout(page_items, layout_updates[0])
    ok("拼版页面应用双图编辑布局：左右图间距/重叠按弹窗结果更新",
       changed_layout_files == {str(right_path)}
       and page_items[1]["rect"] == [270.0, 15.0, 120.0, 60.0],
       f"items={page_items}")
    from types import SimpleNamespace

    from desktop.modules.imposition.page import ImpositionModulePage

    module_items = [
        {"file": str(left_path), "rect": [0, 0, 200, 100]},
        {"file": str(right_path), "rect": [250, 10, 150, 80]},
    ]
    module_refreshes = []
    module_invalidations = []
    module_probe = SimpleNamespace(
        _doc={"pages": [{"items": module_items}]},
        _refresh_view=lambda: module_refreshes.append(True),
        _invalidate_page_thumbs_for=module_invalidations.append,
    )
    ImpositionModulePage._after_spread_layout_edited(
        module_probe, 0, layout_updates[0]
    )
    ok("独立拼版页：双图布局更新后重绘画布并失效缩略图",
       module_items[1]["rect"] == [270.0, 15.0, 120.0, 60.0]
       and module_refreshes == [True]
       and module_invalidations == [str(right_path)],
       f"rect={module_items[1]['rect']}, "
       f"refreshes={module_refreshes}, invalidations={module_invalidations}")

    from desktop.pages.taskdetail.imposition_layout import ImpositionLayoutMixin

    task_items = [
        {"file": str(left_path), "rect": [0, 0, 200, 100]},
        {"file": str(right_path), "rect": [250, 10, 150, 80]},
    ]
    persisted_pages = []
    task_probe = SimpleNamespace(
        _imposition_pages=lambda: [{"items": task_items}],
        _save_imposition_pages=persisted_pages.append,
    )
    ImpositionLayoutMixin._on_imposition_spread_layout_saved(
        task_probe, 0, layout_updates[0]
    )
    ok("任务详情页：双图布局更新写回并保存拼版文档",
       task_items[1]["rect"] == [270.0, 15.0, 120.0, 60.0]
       and len(persisted_pages) == 1
       and persisted_pages[0][0]["items"][1]["rect"]
       == [270.0, 15.0, 120.0, 60.0],
       f"rect={task_items[1]['rect']}, saves={len(persisted_pages)}")
    dialog6.close()
    dialog6.release_buffers()
    from PySide6.QtGui import QColor, QImage, QPainter

    pad_dir = temp_dir("guji_editor_pad_")
    pad_left_path = pad_dir / "pad_left.png"
    pad_right_path = pad_dir / "pad_right.png"

    def _write_padded(path: str) -> None:
        """240×180 里只有 (40,40,160,100) 是不透明内容，其余透明。"""
        image = QImage(240, 180, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.fillRect(QRectF(40, 40, 160, 100), QColor("#ffffff"))
        painter.end()
        assert image.save(path)

    def _write_solid(path: str) -> None:
        """整张不透明（无留白）——左右两图留白不同是报障现场的关键变量。"""
        image = QImage(240, 180, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        assert image.save(path)

    _write_padded(str(pad_left_path))
    _write_solid(str(pad_right_path))
    # 入口按真实链路传 ``QImage(路径)``（整张含留白），rect 用页码面的
    # "整尺寸" 版面（``default_items`` 是整图尺寸口径）——两处都是报障现场。
    # 左右两图页面 rect 一样大（240×180）⇒ 拼版页上两图**看起来一样大**；
    # 弹窗里也必须一样大（见下面的显示尺寸断言）。
    dialog_pad = ImageEditorDialog(None, QImage(str(pad_left_path)),
                                   save_back=True)
    dialog_pad.configure_multiple_images([
        {"image": QImage(str(pad_left_path)), "file": str(pad_left_path),
         "rect": (0, 0, 240, 180)},
        {"image": QImage(str(pad_right_path)), "file": str(pad_right_path),
         "rect": (240, 0, 240, 180)},
    ])
    pad_canvas = dialog_pad.canvas
    pad_layer0 = dialog_pad._multi_layers[0]
    ok("含留白源图：入口比例按**可见内容**算（rect/内容，不是 rect/整图）",
       pad_layer0["scale"] == (1.5, 1.8)
       and dialog_pad._multi_layers[1]["scale"] == (1.0, 1.0)
       and pad_layer0["origin"] == (0.0, 0.0),
       f"scale0={pad_layer0['scale']} "
       f"scale1={dialog_pad._multi_layers[1]['scale']} "
       f"origin={pad_layer0['origin']}")
    # ⚠️ 用户 2026-10-15 报障核心：拼版页上两图一样大，弹窗里左图却明显偏小
    #    （右/左宽比 ≈ 1.18，而页面 ≈ 1.00）。判据＝**两图在弹窗里的显示尺寸
    #    之比必须等于页面 rect 之比**：页面两 rect 都是 240×180 ⇒ 弹窗里
    #    左图（内容 160×100，1:1 显示）与右图（内容 240×180，按 s₁/s₀ 缩）
    #    必须都是 160×100。旧版按整图算比例（s₀=(1,1)）⇒ 右图显示成 240×180，
    #    左图偏小——正是截图里的现象。
    ok("含留白源图：弹窗里两图显示尺寸之比 == 拼版页 rect 之比",
       abs(pad_canvas._context_scale_x * 240 - 160) < 1e-6
       and abs(pad_canvas._context_scale_y * 180 - 100) < 1e-6,
       f"context_scale=({pad_canvas._context_scale_x}, "
       f"{pad_canvas._context_scale_y})")
    # 页面 delta=240、活动比例 1.5 ⇒ 弹窗里两图间距 240/1.5=160（旧版按整图
    # 算比例=1、且 origin 重复计留白 ⇒ 间距被放大到 200，与拼版页对不上）。
    ok("含留白源图：弹窗入口两图相对位置与拼版页一致",
       pad_canvas._context_offset == QPointF(160, 0),
       f"offset={pad_canvas._context_offset}")

    # 弹窗里把活动图整体移动 (30,30)（选区随图一起走 ⇒ 内容尺寸不变）。
    dialog_pad._pending_crop = QRectF(30, 30, 160, 100)
    dialog_pad._pending_crop_offset = (30.0, 30.0)
    dialog_pad._commit_crop()
    pad_updates = []
    dialog_pad.multi_layout_saved.connect(pad_updates.append)
    ok("含留白源图：移动后回写版面尺寸＝入口 rect 尺寸（高度不压缩）",
       dialog_pad._save_multiple_images()
       and pad_updates == [[{
           "index": 0,
           "file": str(pad_left_path),
           # 位移 = 内容偏移 + 画布原点，再乘**内容比例**：(30×1.5, 30×1.8)；
           # 尺寸 = 内容尺寸 × 比例 = 入口 rect（240×180）。旧版按整图算比例
           # (1,1)，尺寸会回成 (160,100)——拼版页据此摆框，高度就短了一截。
           "rect": [45.0, 54.0, 240.0, 180.0],
       }]],
       f"updates={pad_updates}")
    dialog_pad.close()
    dialog_pad.release_buffers()

    st.dialog.close()
    st.dialog.release_buffers()
    ok("释放：双图各层整图缓冲一并放掉",
       all(layer["state"]["_image"] is None for layer in st.dialog._multi_layers),
       "")

