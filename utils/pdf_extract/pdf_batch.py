# -*- coding: utf-8 -*-
"""PDF 批次的子进程执行体（必须是模块级函数，供 ProcessPoolExecutor pickle）。"""

import math
import os
import time
from typing import List

from utils.pdf_extract.jpx import _jpx_page_source, _render_jpx_page
from utils.pdf_extract.pages import calculate_zoom, render_zoom
from utils.pdf_extract.quick import _embedded_page_image, _save_embedded_image
from utils.pdf_extract.render import (
    _fail_all_pages,
    _page_fail,
    _page_ok,
    _render_page,
    _shrink_mupdf_store,
)


def _render_batch_in_worker(payload: tuple) -> dict:
    """子进程执行体：渲染一批 PDF 页并返回结构化结果（纯数据，不落任何 IO 通道）。

    ⚠️ 必须是**模块级函数**（否则无法 pickle 进进程池），且**不 print、不碰
    ``reporter``/``progress``**（原因见 ``_report_batch``）。返回的 ``pages``
    顺序与传入的 ``page_indices`` 一致，父进程据此按序上报。

    payload = (pdf_path, page_indices, out_dir, zoom, ext, quick, dpi)

    返回::

        {
          "pages": [{"idx": int, "ok": bool, "path": str, "w": int, "h": int,
                     "elapsed": float, "err": str | None}, ...],
          "reasons": {降级原因: 次数},   # 只有 quick 模式会产生
          "fallback": int,               # quick 降级的总页数
        }
    """
    pdf_path, page_indices, out_dir, zoom, ext, quick, dpi = payload
    reasons: dict = {}
    fallback = 0

    def _fail_all(msg: str) -> dict:
        """整批失败（依赖缺失 / PDF 打不开）。"""
        return _fail_all_pages(page_indices, msg)

    try:
        import pymupdf as fitz
    except ImportError as e:
        return _fail_all(f"依赖缺失: PyMuPDF 未安装。请运行: pip install PyMuPDF（{e}）")
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:
        return _fail_all(f"依赖缺失: Pillow 未安装。请运行: pip install Pillow（{e}）")

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:  # noqa: BLE001 - 打不开就是整批失败
        return _fail_all(f"打开 PDF 失败: {e}")

    pages: List[dict] = []
    jpx_fast = 0
    quick_direct = 0
    try:
        for page_idx in page_indices:
            page_start = time.time()
            used_mupdf = False
            try:
                page = doc.load_page(page_idx)
                page_rect = page.rect
                original_width = page_rect.width
                # 两条路径的 zoom 各算各的：
                # - quick_zoom：用户 zoom 的原语义，供内嵌图「覆盖度」判定与
                #   落盘决策（内嵌图永远是原图字节，不按 DPI 重采样）；
                # - actual_zoom：整页渲染用，兜一个 DPI 下限，避免矢量 PDF
                #   在 zoom=1 时只渲染出 72 DPI（见 DEFAULT_RENDER_DPI）。
                quick_zoom = calculate_zoom(original_width, zoom)
                actual_zoom = render_zoom(original_width, zoom, dpi)

                # 自动模式只在 zoom=1 时考虑直取：zoom≠1 需要重采样，直拷
                # 既拿不到零解码的好处，又容易和整页渲染的尺寸口径不一致。
                auto_quick = bool(quick) and math.isclose(
                    float(zoom), 1.0, rel_tol=0.0, abs_tol=1e-9
                )

                if auto_quick:
                    # 自适应 quick：只有"纯扫描页"才直取；有文字/矢量/注释/
                    # 旋转/裁切等任何可见内容，一律回退整页渲染（原因见
                    # _page_scan_block_reason）。
                    info, why = _embedded_page_image(
                        doc, page, page_rect, ext, quick_zoom
                    )
                    if info is None:
                        # JPX 快通道：整页就是一张 JPX 时按**目标分辨率**解码，
                        # 跳过 MuPDF 的整帧解码。目标尺寸必须与整页渲染完全一致
                        # （zoom / DPI 下限 / 6000px 封顶都要生效）。
                        target_wh = (
                            max(1, int(math.ceil(page_rect.width * actual_zoom))),
                            max(1, int(math.ceil(page_rect.height * actual_zoom))),
                        )
                        jpx_info, jpx_why = _jpx_page_source(doc, page)
                        fast = (
                            _render_jpx_page(
                                jpx_info, out_dir, page_idx, ext, target_wh
                            )
                            if jpx_info is not None
                            else None
                        )
                        if fast is not None:
                            img_path, iw, ih = fast
                            jpx_fast += 1
                        else:
                            # 用更具体的那个原因做日志（例如"页面有可见文字"
                            # 比"内嵌格式 .jpx"更能说明为什么没走快通道）
                            why = jpx_why or why or "JPX 解码失败"
                            img_path, iw, ih = _render_page(
                                page, out_dir, page_idx, ext, actual_zoom
                            )
                            used_mupdf = True
                            reasons[why] = reasons.get(why, 0) + 1
                            fallback += 1
                    else:
                        img_path, iw, ih = _save_embedded_image(
                            info, out_dir, page_idx, ext, quick_zoom
                        )
                        quick_direct += 1
                else:
                    # 标准模式（quick=False，或 zoom≠1）：渲染整页为高质量图片
                    img_path, iw, ih = _render_page(
                        page, out_dir, page_idx, ext, actual_zoom
                    )
                    used_mupdf = True

                if used_mupdf:
                    # MuPDF 会把解出来的整页原图留在 store 里；及时回收，
                    # 否则一个进程按 ~70~90MB/页涨（见 _shrink_mupdf_store）
                    _shrink_mupdf_store(fitz)

                pages.append(_page_ok(page_idx, img_path, iw, ih, page_start))
            except Exception as e:  # noqa: BLE001 - 单页失败不拖垮整批
                pages.append(_page_fail(page_idx, e, page_start))
    finally:
        # ⚠️ 异常路径也要还句柄（审计 P2）：Windows 上文档没关，
        # 任务目录会一直被占用删不掉
        try:
            doc.close()
        except Exception:  # noqa: BLE001
            pass
    return {
        "pages": pages,
        "reasons": reasons,
        "fallback": fallback,
        "jpx_fast": jpx_fast,
        "quick_direct": quick_direct,
    }
