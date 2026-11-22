# -*- coding: utf-8 -*-
"""单页渲染落盘与批量结果上报（父进程侧）。"""

import os
import time
from pathlib import Path
from typing import Optional


def report_image_size(img_path, width: int, height: int, reporter=None) -> None:
    """汇报一页输出图片的尺寸。

    结构化通道 `page_size` 供 GUI 子进程入库（sizes.json 是框坐标的坐标系基准）；
    `[imgsize]` 文本行仅为**兼容保留**。

    reporter 缺省为 None —— CLI 不注入，行为与原先「只 print 一行」完全一致。
    """
    if reporter is not None:
        reporter.event(
            "page_size", image=Path(img_path).stem,
            width=int(width), height=int(height),
        )
    print(f"[imgsize] {Path(img_path).stem} {int(width)},{int(height)}")


def _save_pil(img, img_path: str, ext: str):
    """按目标格式保存 PIL 图。参数与整页渲染路径保持一致（避免两种模式质量不同）。"""
    if ext.lower() == "jpg":
        # JPG 不支持透明通道
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(img_path, "JPEG", quality=95, subsampling=0)
    else:
        img.save(img_path, ext.upper())
    return img


def _render_page(page, out_dir: str, page_idx: int, ext: str, actual_zoom: float):
    """整页渲染落盘，返回 (路径, 宽, 高)。quick 降级与非 quick 都走这里。"""
    import pymupdf as fitz
    from PIL import Image

    mat = fitz.Matrix(actual_zoom, actual_zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    # ⚠️ size 必须给**元组**：PIL 的注解是 tuple[int, int]，给 list 会被
    # 类型检查判错（运行时两者都收，但别依赖这点）。
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img_path = os.path.join(out_dir, f"{page_idx + 1}.{ext}")
    _save_pil(img, img_path, ext)
    return img_path, pix.width, pix.height


def _shrink_mupdf_store(fitz) -> None:
    """把 MuPDF 的解码图像缓存还回去（**内存**优化的关键一步）。

    实测（JPX 4278×6931 连渲 4 页）：RSS 40MB → 81 → 159 → 231 → 307MB，
    因为解出来的整页原图留在 MuPDF 的 store 里；``store_shrink(100)`` 之后
    307MB → 63MB，只花 0.018s。批量提取是多进程 × 每批多页，不回收的话
    峰值内存会是"每页 ~70~90MB × 页数 × 进程数"。
    """
    try:
        fitz.TOOLS.store_shrink(100)
    except Exception:  # noqa: BLE001 - 老版本/异常环境没有就算了
        pass


def _page_ok(page_idx: int, img_path: str, width, height,
             page_start: float) -> dict:
    """单页成功的结构化结果（PDF / DjVu 两个执行体共用同一形状）。"""
    return {
        "idx": int(page_idx), "ok": True, "path": img_path,
        "w": int(width), "h": int(height),
        "elapsed": time.time() - page_start, "err": None,
    }


def _page_fail(page_idx: int, err, page_start: float) -> dict:
    """单页失败的结构化结果（单页失败不拖垮整批）。"""
    return {
        "idx": int(page_idx), "ok": False, "err": str(err),
        "elapsed": time.time() - page_start,
    }


def _fail_all_pages(page_indices, msg: str) -> dict:
    """整批失败的结果形状（依赖缺失 / 文件打不开）：每页都记一条失败原因。"""
    return {
        "pages": [
            {"idx": int(i), "ok": False, "err": msg, "elapsed": 0.0}
            for i in page_indices
        ],
        "reasons": {},
        "fallback": 0,
        "jpx_fast": 0,
        "quick_direct": 0,
    }


def _report_batch(result: dict, progress: Optional[dict], reporter) -> None:
    """父进程侧：把一批渲染结果落到进度 / 日志 / 结构化通道。

    ⚠️ 子进程只返回数据（见 ``_render_batch_in_worker``），所有 ``print`` 与
    ``reporter`` 调用都收敛到这里，原因有二：

    1. 子进程的 ``print`` 会绕过父进程装好的 ``ProgressStream`` 直写 fd 1 ——
       日志格式不统一、顺序也会和进度条对不上；
    2. ``reporter``（JsonLinesReporter）与 ``progress``（内含 ``threading.Lock``）
       **本来就无法跨进程 pickle**，只能靠返回值把数据带回父进程再上报。
    """
    pages = result.get("pages") or []
    batch_reasons = result.get("reasons") or {}
    batch_fallback = int(result.get("fallback") or 0)
    if progress is not None:
        with progress["lock"]:
            reasons = progress.setdefault("reasons", {})
            for k, v in batch_reasons.items():
                reasons[k] = reasons.get(k, 0) + v
            if batch_fallback:
                progress["fallback"] = progress.get("fallback", 0) + batch_fallback
            progress["jpx_fast"] = (
                progress.get("jpx_fast", 0) + int(result.get("jpx_fast") or 0)
            )
            progress["quick_direct"] = (
                progress.get("quick_direct", 0)
                + int(result.get("quick_direct") or 0)
            )
    for p in pages:
        idx = int(p.get("idx", 0))
        if not p.get("ok"):
            print(f"❌ 第 {idx+1} 页失败: {p.get('err')}")
            # ⚠️ 失败页**不计入 done**——这是改造前的既有可观察行为（部分失败时
            #    进度条停在 <100%），并发后端换代时不要顺手改掉它。
            continue
        report_image_size(p["path"], p["w"], p["h"], reporter)
        if progress is not None:
            with progress["lock"]:
                progress["done"] += 1
                done = progress["done"]
                total = progress["total"]
            # 结构化进度在锁外发：多次汇报是幂等/单调的，不必占着锁做 IO
            if reporter is not None:
                reporter.progress(done, total)
            print(
                f"进度: {done}/{total} 页 - 第 {idx+1} 页 "
                f"用时: {p.get('elapsed', 0.0):.2f}s"
            )
