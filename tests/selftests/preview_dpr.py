# -*- coding: utf-8 -*-
"""预览**清晰度**自测：高分屏（dpr>1）下不许出「先降后升」的糊图。

起因是用户反馈「图片预览感觉不清晰」。量化诊断（``.workbuddy/perf/2026-09-24-preview-sharpness.md``）
定位到根因**不是**编码格式，而是两条：

1. ``ImageView._rerender`` 按**逻辑**像素出图后 ``setPixmap``，高分屏下 Qt 再按
   dpr 放大一次 → 图被"先降后升"重采样两轮。150% 缩放下锐度 494 → 修后 3755
   （**7.6 倍**），200% 下 171 → 2831（**16 倍**）；100% 缩放下几乎无差别，
   所以只看普通屏是看不出这个问题的。
2. 四处 ``PreviewWorker`` 调用点都写死 ``longest_edge=1600``。150%/200% 下屏幕
   需要的物理像素已逼近/超出 1600，源图只能被放大 → 再糊一层。

断言线：

1. ``_rerender`` 交给 ``setPixmap`` 的图按**物理**像素出（高 = 控件高 × 0.96 × dpr），
   并把 dpr 写回 pixmap；
2. 关键不变量「没有二次重采样」：``物理宽 / dpr == 图片宽 × _scale_x``；
3. dpr≠1 时居中偏移与框**命中**依然正确（映射必须按逻辑尺寸算）；
4. ``preview_edge()`` 随 dpr 线性增长、有上下限、未布局时取下限；
5. 调用点不再写死 1600，且 ``preview_edge()`` **不得出现在 worker lambda 里**
   （worker 线程碰 QWidget 是越界的，见 worker_thread_affinity）；
6. 缩略图解码边 = ``ThumbStrip.DECODE_EDGE`` × dpr，同样不得写在 worker lambda 里。

⚠️ offscreen 平台下 ``devicePixelRatioF()`` 恒为 1，所以这里**替换实例方法**模拟
高分屏；也正因为 ``QLabel.setPixmap`` 会把 pixmap 归一到控件自身 dpr（实测
617x864@1.5 → 411x576@1.0），断言必须看"交给 setPixmap 的那一刻"（记录入参），
不能看 ``view.pixmap()``。
"""

from __future__ import annotations

from pathlib import Path

NAME = "preview_dpr"
DEPENDS: list[str] = []
TITLE = "预览清晰度（高分屏 dpr）"

#: 必须按显示物理像素给渲染密度的四个调用点（写死 1600 就是回归）
VIEWER_FILES = [
    "desktop/components/viewers/image_viewer.py",
    "desktop/components/viewers/pdf_viewer.py",
    "desktop/components/viewers/rembg_viewer.py",
    "desktop/components/viewers/print_preview.py",
]


def _spy_setpixmap(view) -> dict:
    """记录下一张交给 ``setPixmap`` 的图（绕过 QLabel 的 dpr 归一）。"""
    seen: dict = {}
    original = view.setPixmap

    def capture(pixmap):
        seen["w"], seen["h"] = pixmap.width(), pixmap.height()
        seen["dpr"] = pixmap.devicePixelRatio()
        seen["pm"] = pixmap  # 留着做像素级断言（框线画在哪）
        return original(pixmap)

    view.setPixmap = capture
    return seen


def _green_mask(pixmap):
    """框线（第 0 个框是绿色 #21c178，R=33 G=193）的物理像素布尔掩码。"""
    import numpy as np
    from PySide6.QtGui import QImage

    img = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
    raw = np.frombuffer(bytes(img.constBits()), dtype=np.uint8)
    raw = raw[: img.height() * img.bytesPerLine()]
    arr = raw.reshape(img.height(), img.bytesPerLine())[
        :, : img.width() * 3
    ].reshape(img.height(), img.width(), 3).astype(int)
    return (arr[:, :, 1] > 150) & (arr[:, :, 0] < 110)


def _box_line_extent(pixmap) -> dict:
    """框线在**物理像素**上的范围。

    只看最左列与最下行：框的文字标签画在框**上方**、起点又右移 4px，所以
    这两处不受标签污染，是干净的"框边界"取样点。
    """
    import numpy as np

    rows, cols = np.nonzero(_green_mask(pixmap))
    if cols.size == 0:
        return {"left": -1, "bottom": -1}
    return {"left": int(cols.min()), "bottom": int(rows.max())}


def _box_edge_thickness(pixmap, left: int, top: int, right: int,
                        bottom: int) -> dict:
    """同一个框**四条边各自的物理厚度**（在中点扫一列/一行，取最长连续段）。

    ⚠️ 只有把线宽取整到**设备像素**，四条边才会一样粗。否则 125% 缩放
    （2×1.25 = 2.5 设备像素）光栅化时各边取整不一致，实测出现「上3 下3 左3 右2」
    ——用户看到的就是"框有的线粗、有的线细"。
    """
    mask = _green_mask(pixmap)
    mid_x = max(0, (left + right) // 2)
    mid_y = max(0, (top + bottom) // 2)

    def longest_run(seq) -> int:
        best = cur = 0
        for hit in seq:
            cur = cur + 1 if hit else 0
            best = max(best, cur)
        return best

    lo_x, hi_x = max(0, left - 6), left + 7
    lo_y, hi_y = max(0, top - 6), top + 7
    return {
        "上": longest_run(mask[lo_y:hi_y, mid_x]),
        "下": longest_run(mask[max(0, bottom - 6):bottom + 7, mid_x]),
        "左": longest_run(mask[mid_y, lo_x:hi_x]),
        "右": longest_run(mask[mid_y, max(0, right - 6):right + 7]),
    }


def run(ctx) -> None:
    from PySide6.QtCore import QPointF, QSize
    from PySide6.QtGui import QColor, QImage

    from desktop.components.viewers.image_view import ImageView
    from desktop.components.viewers.thumb_strip import ThumbStrip
    from tests.selftests._context import ok

    root = Path(__file__).resolve().parents[2]

    # ---------------------------------------------------------------- 1~3
    # 控件 800x600，图片 1000x1400（竖开本）→ 按高适配，缩放 = 576/1400
    for dpr in (1.0, 1.25, 1.5, 2.0):
        view = ImageView()
        view.resize(800, 600)
        source = QImage(1000, 1400, QImage.Format_RGB32)
        source.fill(QColor("#ffffff"))
        view.set_image(source, boxes=[[100, 200, 400, 700]],
                       image_size=QSize(1000, 1400))
        view.devicePixelRatioF = lambda d=dpr: d
        seen = _spy_setpixmap(view)
        view._rerender()

        expect_h = round(600 * 0.96 * dpr)
        ok(f"dpr={dpr}：出图按物理像素（高 = 控件高×0.96×dpr）",
           seen["h"] == expect_h and abs(seen["w"] - expect_h * 1000 / 1400) <= 1,
           f"{seen['w']}x{seen['h']} 期望高 {expect_h}")
        ok(f"dpr={dpr}：dpr 已写回 pixmap",
           abs(seen["dpr"] - dpr) < 1e-9, f"{seen['dpr']} ≠ {dpr}")
        # 没有二次重采样：映射按逻辑尺寸（物理/dpr）算
        ok(f"dpr={dpr}：物理宽/dpr == 图片宽 × _scale_x（无二次重采样）",
           abs(seen["w"] / seen["dpr"] - 1000 * view._scale_x) < 1.0,
           f"{seen['w'] / seen['dpr']:.2f} vs {1000 * view._scale_x:.2f}")
        ok(f"dpr={dpr}：按高适配的缩放比正确",
           abs(view._scale_x - 576 / 1400) < 5e-4,
           f"{view._scale_x:.5f}")
        # 图片中心（500,700）必须落在控件中心（400,300）
        cx = 500 * view._scale_x + view._offset_x
        cy = 700 * view._scale_y + view._offset_y
        ok(f"dpr={dpr}：居中偏移正确（映射按逻辑尺寸算）",
           abs(cx - 400) < 1.0 and abs(cy - 300) < 1.0, f"({cx:.1f},{cy:.1f})")
        ok(f"dpr={dpr}：框命中不受 dpr 影响",
           view._hit_box(250, 450) == 0 and view._hit_box(950, 1350) is None,
           str(view._hit_box(250, 450)))
        # 正反换算自洽（编辑框坐标依赖它）
        ix, iy = view._to_image_coords(QPointF(cx, cy))
        ok(f"dpr={dpr}：控件↔图片坐标正反换算自洽",
           abs(ix - 500) < 1.0 and abs(iy - 700) < 1.0, f"({ix:.1f},{iy:.1f})")
        # ⚠️ 叠加层必须画在**逻辑**坐标上：Qt 在带 dpr 的 pixmap 上作画时，
        # painter 的坐标**已经是逻辑坐标**（dpr 在设备层生效，不体现在
        # transform() 里）。再手动 `painter.scale(dpr, dpr)` 就会放大两次——
        # 底图是对的、框却整体放大偏移，看上去就是"框和图片比例对不上"。
        # 这里必须用**像素**断言：只测尺寸与映射抓不到它（真实发生过，
        # 且离屏自测 dpr 恒为 1、当时全绿）。
        extent = _box_line_extent(seen["pm"])
        left_expected = 100 * view._scale_x * dpr
        bottom_expected = 700 * view._scale_y * dpr
        ok(f"dpr={dpr}：框线落在期望的物理位置（没被 dpr 二次放大）",
           abs(extent["left"] - left_expected) <= 3
           and abs(extent["bottom"] - bottom_expected) <= 3,
           f"左边缘={extent['left']} 期望 {left_expected:.1f}；"
           f"下边缘={extent['bottom']} 期望 {bottom_expected:.1f}")
        # ⚠️ 同一个框四条边必须**一样粗**：线宽不取整到设备像素时，125% 缩放
        # （2×1.25=2.5）会出现「上3 下3 左3 右2」——用户报的"有的线粗有的线细"。
        # 选中态（线更粗）也要四边一致。
        drawn = {
            "left": round(round(100 * view._scale_x) * dpr),
            "top": round(round(200 * view._scale_y) * dpr),
            "right": round(round(400 * view._scale_x) * dpr),
            "bottom": round(round(700 * view._scale_y) * dpr),
        }
        measured: dict = {}
        for state, label in ((None, "未选中"), (0, "选中")):
            view._selected = state
            view._rerender()
            thickness = _box_edge_thickness(
                seen["pm"], drawn["left"], drawn["top"],
                drawn["right"], drawn["bottom"],
            )
            measured[label] = thickness
            ok(f"dpr={dpr}：{label}框的四条边一样粗",
               len(set(thickness.values())) == 1, str(thickness))
        ok(f"dpr={dpr}：选中框比未选中更粗（这是设计意图，不是 bug）",
           max(measured["选中"].values()) > max(measured["未选中"].values()),
           f"选中={measured['选中']} 未选中={measured['未选中']}")
        view._selected = None
        view._rerender()
        view.deleteLater()

    # ---------------------------------------------------------------- 4
    view = ImageView()
    view.resize(1400, 900)
    view.devicePixelRatioF = lambda: 1.0
    ok("preview_edge：100% 缩放下取控件的长边（1400）",
       view.preview_edge() == 1400, str(view.preview_edge()))
    for dpr in (1.0, 1.25, 1.5, 2.0):
        view.devicePixelRatioF = lambda d=dpr: d
        want = min(ImageView.MAX_PREVIEW_EDGE, int(round(1400 * dpr)))
        ok(f"preview_edge：dpr={dpr} → {want}（长边 × dpr）",
           view.preview_edge() == want, str(view.preview_edge()))
    view.devicePixelRatioF = lambda: 4.0
    ok("preview_edge：有上限（不会为一页预览分配巨图）",
       view.preview_edge() == ImageView.MAX_PREVIEW_EDGE,
       str(view.preview_edge()))

    # 小控件不得把预览渲染得过小：下限兜底（也是"尚未布局"时的保护）
    view.resize(940, 700)
    view.devicePixelRatioF = lambda: 1.0
    ok("preview_edge：控件长边小于下限时取下限",
       view.preview_edge() == ImageView.MIN_PREVIEW_EDGE,
       str(view.preview_edge()))
    view.resize(0, 0)
    ok("preview_edge：控件未布局（0x0）时同样取下限",
       view.preview_edge() == ImageView.MIN_PREVIEW_EDGE,
       str(view.preview_edge()))
    view.deleteLater()

    # ---------------------------------------------------------------- 5~6
    for rel in VIEWER_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        ok(f"{rel}：不再写死 longest_edge=1600",
           "longest_edge=1600" not in text, "")
        ok(f"{rel}：渲染密度由 preview_edge() 给出",
           "longest_edge=edge" in text, "")
        # ⚠️ preview_edge() 读控件尺寸/dpr，绝不能在 worker lambda 里调用
        offenders = [
            line.strip() for line in text.splitlines()
            if "preview_edge()" in line and "lambda" in line
        ]
        ok(f"{rel}：preview_edge() 不在 worker lambda 里（线程越界）",
           not offenders, str(offenders))

    for rel in [
        "desktop/components/viewers/image_viewer.py",
        "desktop/components/viewers/rembg_viewer.py",
        "desktop/components/viewers/print_preview.py",
        "desktop/components/viewers/thumbs_loader.py",
    ]:
        text = (root / rel).read_text(encoding="utf-8")
        offenders = [
            line.strip() for line in text.splitlines()
            if "_decode_edge(" in line and "lambda" in line
        ]
        ok(f"{rel}：_decode_edge() 不在批次工厂 lambda 里（线程越界）",
           not offenders, str(offenders))

    # ---------------------------------------------------------------- 6
    ok("ThumbStrip.DECODE_EDGE 仍是图标框的长边（基准不变）",
       ThumbStrip.DECODE_EDGE
       == max(ThumbStrip.ICON_SIZE.width(), ThumbStrip.ICON_SIZE.height()),
       str(ThumbStrip.DECODE_EDGE))
    for dpr in (1.0, 1.25, 1.5, 2.0):
        want = int(round(ThumbStrip.DECODE_EDGE * dpr))
        ok(f"decode_edge：dpr={dpr} → 基准边 × dpr = {want}",
           ThumbStrip.decode_edge(dpr) == want,
           str(ThumbStrip.decode_edge(dpr)))
    ok("decode_edge：可换基准边（第四步用 THUMB_EDGE）",
       ThumbStrip.decode_edge(2.0, 100) == 200,
       str(ThumbStrip.decode_edge(2.0, 100)))
