# -*- coding: utf-8 -*-
"""对外入口：批次调度、单页提取与目录遍历（CLI / GUI 共用）。"""

import os
import shutil
import threading
import time
from pathlib import Path
from typing import List, Optional

from utils.file_utils import is_source_document
from utils.pdf_extract.constants import DEFAULT_RENDER_DPI
from utils.pdf_extract.djvu import (
    _render_djvu_batch_in_worker,
    djvu_page_count,
)
from utils.pdf_extract.pages import (
    is_djvu_path,
    parse_pages,
    render_zoom,
    validate_page_range,
)
from utils.pdf_extract.pdf_batch import _render_batch_in_worker
from utils.pdf_extract.render import _report_batch
from utils.sort_utils import natural_sort_key


def _render_batch_dispatch(payload: tuple) -> dict:
    """按源文件后缀分派到 PDF / DjVu 的批次执行体（两者返回结构一致）。"""
    if is_djvu_path(payload[0]):
        return _render_djvu_batch_in_worker(payload)
    return _render_batch_in_worker(payload)


def document_page_count(path) -> int:
    """源文件（PDF / DjVu）总页数。"""
    if is_djvu_path(path):
        return djvu_page_count(path)
    import pymupdf as fitz

    document = fitz.open(str(path))
    try:
        return int(document.page_count)
    finally:
        document.close()


def extract_single_page(
    pdf_path: str,
    page_idx: int,
    out_dir: str,
    zoom: float = 1,
    ext: str = "jpg",
    quick: bool = True,
    dpi: float = DEFAULT_RENDER_DPI,
) -> dict:
    """提取**单页**落盘，返回结构化结果（GUI「翻到哪页就提取哪页」用）。

    复用批量提取的 ``_render_batch_dispatch``（quick 自适应 / DPI 下限 /
    原子写全部同一条实现；PDF 与 DjVu 按后缀分派）——单页提取的产物与批量
    提取**逐位一致**，浏览过的页再跑批量提取也只是幂等覆盖。本函数**不 print、
    不汇报**：调用方（GUI worker 线程）自己负责界面反馈，别把批量那条进度
    刷屏带进来。

    返回::

        {"ok": bool, "path": str | None, "w": int, "h": int, "err": str | None}
    """
    try:
        # ⚠️ 与批量路径的 extract_pdf_optimized 对齐：先保证输出目录在。
        # （批量里由 extract_pdf_optimized 建；这里单独建，否则 PIL 落盘
        #   直接 FileNotFoundError。）
        os.makedirs(out_dir, exist_ok=True)
        result = _render_batch_dispatch(
            (str(pdf_path), [int(page_idx)], str(out_dir), zoom, ext, quick, dpi)
        )
    except Exception as e:  # noqa: BLE001 - 兜底：调用方只认结构化结果
        return {"ok": False, "path": None, "w": 0, "h": 0,
                "err": f"{type(e).__name__}: {e}"}
    pages = result.get("pages") or []
    page = pages[0] if pages else {}
    ok = bool(page.get("ok"))
    return {
        "ok": ok,
        "path": str(page.get("path")) if ok and page.get("path") else None,
        "w": int(page.get("w") or 0),
        "h": int(page.get("h") or 0),
        "err": None if ok else str(page.get("err") or "提取失败"),
    }


def process_page_batch(
    pdf_path: str,
    page_indices: List[int],
    out_dir: str,
    zoom: float,
    ext: str,
    # 默认值必须与 core/command_spec.py 里 extract 的规格一致（zoom=1 /
    # quick=True）：以前这里写的是 zoom=2 / quick=False，于是「直接调库」与
    # 「走 CLI/GUI」是两套行为，默认值等于有了第二个来源（2026-09-26 审计）。
    quick: bool = True,
    progress: Optional[dict] = None,
    reporter=None,
    dpi: float = DEFAULT_RENDER_DPI,
) -> List[bool]:
    """处理一批源文件页面（PDF / DjVu），返回每页的成功状态。

    参数:
        pdf_path: 源文件路径（PDF 或 DjVu）。
        page_indices: 0-based 页码列表。
        out_dir: 输出目录。
        zoom: 缩放因子。
        ext: 输出格式（jpg/png）。
        quick: True=优先取内嵌图（不满足条件会自动降级整页渲染，见
              `_embedded_page_image`），False=始终整页渲染。
        progress: 共享进度字典（含 lock, done, total），用于线程安全打印进度；
              额外用 reasons/fallback 记录 quick 降级原因（不逐页刷屏）。
        reporter: 结构化汇报通道（进度 + 页尺寸）。None → 只 print，CLI 不受影响。
        dpi: 整页渲染的 DPI 下限（见 `render_zoom`）。**只影响渲染路径**，
              取内嵌图时按原图字节落盘，不做任何重采样。

    返回:
        每页成功/失败的 bool 列表。
    """
    try:
        result = _render_batch_dispatch(
            (pdf_path, list(page_indices), out_dir, zoom, ext, quick, dpi)
        )
    except Exception as e:  # noqa: BLE001 - 兜底：批处理本身失败
        print(f"❌ 处理批次失败: {e}")
        return [False] * len(page_indices)
    _report_batch(result, progress, reporter)
    return [bool(p.get("ok")) for p in result["pages"]]


def render_pages_parallel(
    pdf_path: str,
    page_indices: List[int],
    out_dir: str,
    zoom: float,
    ext: str,
    # 默认值必须与 core/command_spec.py 里 extract 的规格一致（zoom=1 /
    # quick=True）：以前这里写的是 zoom=2 / quick=False，于是「直接调库」与
    # 「走 CLI/GUI」是两套行为，默认值等于有了第二个来源（2026-09-26 审计）。
    quick: bool = True,
    workers: int = 4,
    batch_size: int = 4,
    progress: Optional[dict] = None,
    reporter=None,
    dpi: float = DEFAULT_RENDER_DPI,
) -> List[bool]:
    """多**进程**提取指定页（PDF / DjVu），返回每页成功状态。

    CLI（`extract_pdf_optimized`）与 GUI（`run_extract_stage`）共用这一份并发
    实现——GUI 曾经直接调 `process_page_batch` 串行跑全部页，是提取慢的主因。

    ⚠️ 2026-09-28：并发后端从 `ThreadPoolExecutor` 换成 `ProcessPoolExecutor`。
    起因是「第一步 extract 变慢 + 界面卡」，实测（本机 6 物理核，102 页 jpx
    扫描件，见 .workbuddy/memory/2026-09-28.md）：

    - **线程对 PyMuPDF 渲染完全无效**：`get_pixmap` 期间持有 GIL，纯渲染
      1→4→6 线程只有 1.15×（1085/942/972 ms/页）；端到端 4 线程与单线程持平，
      6 线程占满物理核还把 GUI 拖卡（**这是"页面卡"的直接原因**）；
    - 同一份活交给 4 个**进程**：**1.79 页/秒 vs 0.96（1.86×）**——GIL 不再共享。

    代价与约束：
    - 每个子进程要各自 `fitz.open`（Document 不可 pickle），结果再 pickle 回父进程，
      因此**只有批次多于 1 批**才开池：单批（≤ batch_size 页）开池会被 ~0.8s 的
      进程启动开销吃回去；
    - 所有 `print` / `reporter` / `progress` 都由**父进程**做（见 `_report_batch`），
      子进程只返回数据；
    - ⚠️ 本函数会 spawn 子进程，因此**调用方入口必须有 `if __name__ == "__main__"`
      保护**，打包环境还须先调 `multiprocessing.freeze_support()`（PyInstaller 的
      硬要求，否则子进程会重新拉起整个 exe）。

    reporter 为结构化汇报通道（进度 + 页尺寸）；None → 保持纯 print 行为。
    """
    if not page_indices:
        return []
    if progress is None:
        progress = {"lock": threading.Lock(), "done": 0, "total": len(page_indices)}
    progress.setdefault("reasons", {})
    progress.setdefault("fallback", 0)
    progress.setdefault("jpx_fast", 0)
    progress.setdefault("quick_direct", 0)

    page_indices = [int(i) for i in page_indices]
    # 子进程执行体：按源文件后缀分派（PDF → PyMuPDF，DjVu → djvu-rs）
    worker = _render_batch_dispatch
    batches = [
        page_indices[i : i + batch_size]
        for i in range(0, len(page_indices), batch_size)
    ]
    workers = max(1, int(workers or 1))

    # 子进程返回的每页状态按 idx 收拢，最后按入参顺序还原（池崩溃串行补跑时，
    # 完成顺序会乱，靠 idx 对齐才不会错位）
    results_by_idx: dict = {}

    def _consume(result: dict) -> None:
        _report_batch(result, progress, reporter)
        for p in result.get("pages") or []:
            results_by_idx[int(p.get("idx", 0))] = bool(p.get("ok"))

    def _payload(batch: List[int]) -> tuple:
        return (pdf_path, batch, out_dir, zoom, ext, quick, dpi)

    done_batches = 0
    if workers > 1 and len(batches) > 1:
        from concurrent.futures import ProcessPoolExecutor

        try:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                # map 按 batches 顺序 yield，done_batches 于是能准确表示
                # 「已消费的批次数」，异常时据此决定补跑哪一段
                for result in executor.map(
                    worker, [_payload(b) for b in batches]
                ):
                    _consume(result)
                    done_batches += 1
        except Exception as exc:  # noqa: BLE001 - 进程池崩溃不能拖垮整个任务
            # 子进程被 OOM 杀掉 / 段错误 → BrokenProcessPool。已消费的批次不重跑，
            # 剩下的在父进程里串行补完（落盘是原子写，重复渲染也是幂等的）。
            print(
                f"⚠️ 多进程渲染中断（{type(exc).__name__}: {exc}），"
                f"剩余 {len(batches) - done_batches} 批改用串行补跑"
            )

    # workers==1 时这是主路径；进程池崩溃时这是兜底
    for batch in batches[done_batches:]:
        _consume(worker(_payload(batch)))

    # quick 是 PDF 专属概念（内嵌图直拷 / JPX 通道）；DjVu 每页都真解码，
    # 打这些统计只会误导（"0 页直取内嵌图"并不代表有问题）。
    if quick and not is_djvu_path(pdf_path):
        jpx_fast = int(progress.get("jpx_fast") or 0)
        quick_direct = int(progress.get("quick_direct") or 0)
        if jpx_fast:
            print(
                f"ℹ️  quick：{jpx_fast}/{len(page_indices)} 页直接解 JPX 码流"
                "（跳过整页渲染）"
            )
        reasons: dict = progress.get("reasons") or {}
        fallback = progress.get("fallback", 0)
        if fallback:
            detail = "；".join(
                f"{k} ×{v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])
            )
            print(f"ℹ️  quick：{fallback}/{len(page_indices)} 页降级整页渲染（{detail}）")
        elif quick_direct + jpx_fast == len(page_indices):
            print(f"ℹ️  quick：全部 {len(page_indices)} 页直接取内嵌图")
        elif not quick_direct and not jpx_fast:
            # 一页都没直取、也没有降级原因：说明 zoom≠1，自动模式没参与判断
            print(f"ℹ️  quick：zoom={zoom}≠1，全部页按整页渲染")
    return [results_by_idx.get(i, False) for i in page_indices]


def extract_pdf_optimized(
    pdf_path: str,
    out_dir: str,
    zoom: float = 1,
    ext: str = "jpg",
    workers: int = 4,
    # 默认值必须与 core/command_spec.py 里 extract 的规格一致（zoom=1 /
    # quick=True）：以前这里写的是 zoom=2 / quick=False，于是「直接调库」与
    # 「走 CLI/GUI」是两套行为，默认值等于有了第二个来源（2026-09-26 审计）。
    quick: bool = True,
    pages: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    batch_size: int = 4,
    clean: bool = False,
    reporter=None,
    dpi: float = DEFAULT_RENDER_DPI,
) -> bool:
    """提取 PDF / DjVu 页面为图片，支持多进程批次处理。

    参数:
        pdf_path: 源文件路径（PDF 或 DjVu）。
        out_dir: 输出目录（此目录将存放该源文件的所有页面图片）。
        zoom: 缩放因子（整数，如 2 表示 2 倍分辨率）。
        dpi: 整页渲染的 DPI 下限（见 `render_zoom`），不影响内嵌图路径；
             **对 DjVu 不生效**（DjVu 按原生分辨率渲染）。
        ext: 输出格式 jpg/png/tiff。
        workers: 进程数。
        quick: True=快速模式（优先提取 PDF 内嵌图片）；对 DjVu 无效。
        pages: 页码字符串（如 "1,3-5,7"），优先级高于 start/end。
        start: 起始页（1-based）。
        end: 结束页（1-based）。
        batch_size: 每批次处理的页数。
        clean: True=清空输出目录后重新提取。
        reporter: 结构化汇报通道；None → 只 print（CLI 默认）。

    返回:
        True=处理完成（部分页面可能失败，查看日志），False=整体失败。
    """
    try:
        start_time = time.time()
        if not os.path.exists(pdf_path):
            print(f"❌ 错误: 源文件不存在: {pdf_path}")
            return False

        is_djvu = is_djvu_path(pdf_path)
        actual_zoom = float(zoom)
        if is_djvu:
            try:
                import djvu_rs  # noqa: F401 - 缺依赖时给一句能照做的提示
            except ImportError:
                print("❌ 依赖缺失: djvu-rs 未安装。请运行: pip install djvu-rs")
                return False
            try:
                total_pages = djvu_page_count(pdf_path)
            except Exception as e:  # noqa: BLE001 - 坏文件/坏目录统一给出人话
                print(f"❌ 打开 DjVu 失败: {e}")
                return False
        else:
            try:
                import pymupdf as fitz
            except ImportError:
                return False
            doc = fitz.open(pdf_path)
            try:
                total_pages = len(doc)
                # 用首页宽度计算实际缩放因子（空文档会在这里抛，保持原有失败语义）
                page_width = doc.load_page(0).rect.width
            finally:
                doc.close()
            actual_zoom = render_zoom(page_width, zoom, dpi)

        if clean and os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir, exist_ok=True)

        # 确定要处理的页码列表
        if pages is not None:
            try:
                page_indices = parse_pages(pages, total_pages)
            except ValueError as e:
                print(f"❌ 页面参数错误: {e}")
                return False
        elif start is not None or end is not None:
            try:
                page_indices = validate_page_range(start, end, total_pages)
            except ValueError as e:
                print(f"❌ 页面范围错误: {e}")
                return False
        else:
            page_indices = list(range(total_pages))

        total_selected = len(page_indices)
        print(f"\n📄 开始处理: {os.path.basename(pdf_path)}")
        print(f"📂 输出目录: {out_dir}")
        print(f"📏 总页数: {total_pages}")
        print(f"📄 处理页数: {total_selected}")
        if is_djvu:
            print(f"🔧 渲染: DjVu 按原生分辨率 × zoom={zoom}（不套用 PDF 的 DPI 下限）")
        else:
            print(f"🔧 实际 zoom: {actual_zoom}（内嵌图路径按原图，不受 DPI 下限影响）")

        # 线程安全的进度计数器
        progress = {"total": total_selected, "done": 0, "lock": threading.Lock()}

        # 多线程处理各批次（与 GUI 的 run_extract_stage 共用同一份实现）
        all_results = render_pages_parallel(
            pdf_path, page_indices, out_dir, zoom, ext,
            quick=quick, workers=workers, batch_size=batch_size, progress=progress,
            reporter=reporter, dpi=dpi,
        )

        success_count = sum(all_results)
        elapsed_time = time.time() - start_time
        time_note = f" 用时: {elapsed_time:.2f} 秒"
        if total_selected > 0 and success_count == 0:
            # ⚠️ 一页都没成，绝不能报成功（2026-09-26 审计实测：原实现无论成功几页
            #    都 `return True`，于是 PDF 损坏/输出目录不可写时命令以退出码 0
            #    结束、没有任何产物，调用方（run_on_input_directory → CLI 退出码、
            #    脚本、流水线）全都发现不了——和 print 那个「空输入静默成功」同类）。
            print(f"\n❌ 提取失败：{total_selected} 页全部失败（成功 0 页）{time_note}")
            return False
        print(f"\n🎉 处理完成！ 成功: {success_count}/{total_selected} 页{time_note}")
        return True
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def run_on_input_directory(
    input_path: str,
    out_root: str,
    zoom: float = 1,
    ext: str = "jpg",
    workers: int = 4,
    # 默认值必须与 core/command_spec.py 里 extract 的规格一致（zoom=1 /
    # quick=True）：以前这里写的是 zoom=2 / quick=False，于是「直接调库」与
    # 「走 CLI/GUI」是两套行为，默认值等于有了第二个来源（2026-09-26 审计）。
    quick: bool = True,
    pages: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    batch_size: int = 4,
    clean: bool = False,
    subdir_name: str = "images",  # 新增参数，默认保持兼容
    reporter=None,
    dpi: float = DEFAULT_RENDER_DPI,
):
    """
    处理输入路径（文件或目录），对每个 PDF/DjVu 在 out_root 下创建以其文件名命名的
    子目录，并在该子目录下创建 subdir_name 目录存放图片。

    参数:
        input_path: 输入路径（单个 PDF/DjVu 文件或包含它们的目录）。
        out_root: 输出根目录（所有源文件的子目录将创建在此目录下）。
        zoom, ext, workers, quick, pages, start, end, batch_size, clean, dpi:
            透传给 extract_pdf_optimized 的参数。
        subdir_name: 每个源文件子目录下存放图片的子目录名。
        reporter: 结构化汇报通道；None → 只 print（CLI 默认）。
    """
    if not os.path.exists(input_path):
        raise ValueError(f"路径不存在: {input_path}")

    if os.path.isfile(input_path):
        if not is_source_document(input_path):
            raise ValueError(
                f"不支持的源文件类型: {input_path}（仅支持 PDF/DjVu）"
            )
        documents = [input_path]
    else:
        documents = [
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if is_source_document(f)
        ]

    if not documents:
        raise ValueError(f"目录中没有 PDF/DjVu 文件: {input_path}")

    # 确保输出根目录存在
    os.makedirs(out_root, exist_ok=True)

    # 单个文件失败不打断批量处理，但必须让调用方最终知道"有失败"，
    # 否则脚本/子进程会把失败当成功（退出码 0）
    # ⚠️ 排序用**自然序**（全仓唯一排序键 utils.sort_utils）：字典序会让
    #    「书2.pdf」排在「书10.pdf」后面，批量处理的先后与输出子目录的
    #    创建顺序都和用户对页序的直觉相反（2026-10-12 排序统一审计）。
    failures: list[str] = []
    for pdf in sorted(documents, key=lambda p: natural_sort_key(Path(p).name)):
        try:
            fname = os.path.basename(pdf)
            folder_name = os.path.splitext(fname)[0]
            # 使用 subdir_name 拼接最终输出目录
            out_dir = os.path.join(out_root, folder_name, subdir_name)
            ok = extract_pdf_optimized(
                pdf,
                out_dir,
                zoom,
                ext,
                workers,
                quick,
                pages,
                start,
                end,
                batch_size,
                clean=clean,
                reporter=reporter,
                dpi=dpi,
            )
            if ok is False:
                failures.append(fname)
        except KeyboardInterrupt:
            print("\n⚠️  用户中断")
            raise
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            failures.append(os.path.basename(pdf))

    if failures:
        raise RuntimeError("以下文件提取失败：" + "、".join(failures))
