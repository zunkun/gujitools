# -*- coding: utf-8 -*-
"""10 / 11 / 12"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import HOST_FILES, rgb_array, sharpness
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from desktop.components.viewers.pdf_viewer import PdfViewerWidget
    from desktop.workers.preview_worker import PreviewWorker
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from PySide6.QtGui import QColor, QImage
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget
    from typing import cast
    import fitz
    from tests.selftests._context import module_source_text
    import numpy as np
    from tests.selftests._context import ok, pump
    import numpy as np

    from desktop.workers.preview_worker import PreviewWorker

    # 源图用**有纹理**的（模拟扫描件的网点/纸纹）：纯色图的差异只出现在标题
    # 那一小块，全局 RMSE 会被大片相同的白底稀释掉，测不出真实差别。
    rng = np.random.default_rng(20260924)
    base = np.full((1754, 1240, 3), 235, dtype=np.uint8)
    noise = rng.integers(-28, 29, (1754, 1240, 3), dtype=np.int16)
    textured = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    src_path = st.tmp / "page.png"
    QImage(textured.data, 1240, 1754, 1240 * 3,
           QImage.Format.Format_RGB888).copy().save(str(src_path))
    st.base_spec = {
        "args": {"title_printing": True, "title_text": "古籍重製",
                 "title_font_size": 12},
        "index": 0, "total": 1, "name": "page",
    }

    def compose(edge: int, extra: dict):
        captured: dict = {}
        worker = PreviewWorker(
            src_path, longest_edge=edge, print_spec={**st.base_spec, **extra}
        )
        worker.finished.connect(
            lambda _p, image, _s: captured.update(image=image)
        )
        worker.run()
        # ⚠️ cast 而非收窄：下面几处断言里仍保留 ``is not None`` 的判据，
        #    这里先按「worker 跑完必然出图」把类型定死，失败照样由 ok() 报。
        return cast("QImage", captured.get("image"))

    # 两者输出边长相同，差别只在"排版密度"：不指定 target_edge 时是
    # 「按 1600px 密度合成 → 再缩放到请求边长」，指定时才是按请求边长重排。
    upscaled = compose(3000, {})
    big = compose(3000, {"target_edge": 3000})
    ok("不指定 target_edge 时输出边长仍由 longest_edge 决定",
       max(upscaled.width(), upscaled.height()) == 3000,
       f"{upscaled.width()}x{upscaled.height()}")
    ok("指定 target_edge 后长边就是该值",
       max(big.width(), big.height()) == 3000,
       f"{big.width()}x{big.height()}")

    a, b = rgb_array(big), rgb_array(upscaled)
    rows = min(a.shape[0], b.shape[0])  # 两种密度取整会差一行，裁到公共区
    cols = min(a.shape[1], b.shape[1])
    rmse = float(((a[:rows, :cols] - b[:rows, :cols]) ** 2).mean() ** 0.5)
    ok("是「按目标边长重新排版」而不是「把 1600px 合成图放大」",
       rmse > 5.0, f"RMSE={rmse:.2f}")
    ok("重排出来的确实更锐（不是放大的糊图）",
       sharpness(big) > sharpness(upscaled) * 1.2,
       f"重排={sharpness(big):.0f} 放大={sharpness(upscaled):.0f}")
    def compose_src(path, longest, spec):
        captured: dict = {}
        worker = PreviewWorker(path, longest_edge=longest, print_spec=spec)
        worker.finished.connect(
            lambda _p, image, _s: captured.update(image=image)
        )
        worker.run()
        # ⚠️ 同上：cast 定死类型，"没出图"的判据留给调用点的 ok()
        return cast("QImage", captured.get("image"))

    small_path = st.tmp / "small.png"
    QImage(800, 1131, QImage.Format.Format_RGB888).copy().save(str(small_path))
    # 夹住的是**图片区域**的密度，不是画布（画布还要放标题/纸面留白）。
    # 所以这里不比画布尺寸，而是比"要更大的边长能不能拿到更多像素"——
    # 上限一旦存在，4000 与 8000 必然得到同一张画布。
    ask_4000 = compose_src(small_path, 0, {**st.base_spec, "target_edge": 4000})
    ask_8000 = compose_src(small_path, 0, {**st.base_spec, "target_edge": 8000})
    ok("密度有上限：不放大源图（要 4000 与要 8000 得到同一张画布）",
       ask_4000 is not None and ask_4000.size() == ask_8000.size(),
       f"{ask_4000.size()} vs {ask_8000.size()}")
    ok("…而且确实被夹住（没有真按请求边长合成）",
       max(ask_4000.width(), ask_4000.height()) < 4000,
       f"{ask_4000.width()}x{ask_4000.height()}（源图 800x1131）")

    import fitz

    pdf_path = st.tmp / "one.pdf"
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    pg.insert_text((72, 72), "x")
    doc.save(str(pdf_path))
    doc.close()
    pdf_img = compose_src(pdf_path, 0, None)
    ok("longest_edge=0 在 PDF 分支返回原始尺寸（不再得到空图）",
       pdf_img is not None and not pdf_img.isNull() and pdf_img.width() >= 590,
       f"{pdf_img.width()}x{pdf_img.height()}")

    # 2026-10-07 起 print_preview 是**子包**：把包内所有源文件合起来看。
    _pp_pkg = st.root / "desktop/components/viewers/print_preview"
    host_text = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(_pp_pkg.rglob("*.py"))
    )
    ok("第四步主预览：打印效果按 target_edge 重排（密度不写死 1600）",
       "target_edge" in host_text and "MAX_PREVIEW_EDGE" in host_text, "")
    ok("第四步主预览：给了 target_edge 就不再做 longest_edge 缩放",
       "longest_edge=0" in host_text, "")
    from tests.selftests._context import module_source_text

    for rel in HOST_FILES:
        text = module_source_text(st.root, rel)
        # 2026-10-09 起调用形态多了 editable 参数（image_editable 接口），
        # 守卫只认"self.view 接上了弹窗"这件事本身，不锁死参数列表
        ok(f"{rel}：接上了弹窗", "_init_zoom_popup(self.view" in text, "")
        ok(f"{rel}：实现了 _zoom_target", "def _zoom_target(" in text, "")

    # 混入 ZoomPopupMixin 不能和既有的 ThumbsMixin/WorkerHost 抢方法：
    # _init_zoom_popup 之前也要能安全调 close_zoom_popup / shutdown_workers
    from desktop.components.viewers.image_viewer import ImageViewerWidget
    from desktop.components.viewers.pdf_viewer import PdfViewerWidget
    from desktop.components.viewers.print_preview import PrintPreviewWidget
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget

    for cls in (ImageViewerWidget, PdfViewerWidget, RembgPreviewWidget,
                PrintPreviewWidget):
        host = cls()
        mro_ok = True
        try:
            host.close_zoom_popup()   # 还没开过弹窗：必须是无动作而非 AttributeError
            host.shutdown_workers()   # MRO 必须仍落到 WorkerHost 那一版
        except Exception as exc:  # noqa: BLE001
            mro_ok = False
            detail = f"{type(exc).__name__}: {exc}"
        ok(f"{cls.__name__}：混入弹窗后收尾路径仍正常（MRO 无冲突）",
           mro_ok, "" if mro_ok else detail)
        ok(f"{cls.__name__}：双击入口已接上",
           hasattr(host, "_open_zoom_popup") and hasattr(host, "_zoom_target"), "")
        host.deleteLater()

    # 2026-10-07 起 image_zoom_dialog 是**子包**：把包内所有源文件合起来看。
    _zdlg_pkg = st.root / "desktop/components/viewers/image_zoom_dialog"
    text = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(_zdlg_pkg.rglob("*.py"))
    )
    ok("弹窗不自己拼图片路径（渲染口径交给宿主）",
       "PreviewWorker" not in text, "")

