# -*- coding: utf-8 -*-
"""提取预览控件：左侧**一份** PDF 页缩略图，右侧按页显示提取结果。

用户 2026-10-09 定稿（替换任务详情页旧的「PDF 预览 | 提取结果」双标签——
两个标签各带一套缩略图条，同一本书在界面上出现两份清单）：

- 左侧**只有一份**缩略图：PDF 的每一页（缓存于 ``thumbnails/source``，
  与导入后台任务共用同一条生产链，见 :class:`PdfViewerWidget.set_pdf`）；
- 切到第 N 页时：``stages/extract/N.<ext>`` **已存在** → 直接显示提取结果；
  **不存在** → 后台把这一页**真的提取落盘**（与批量提取同一条渲染实现，
  :func:`utils.pdf_extract.extract_single_page`），完成后上屏提取结果——
  「预览即产物」，不再有"预览渲的和提取存的不是同一张图"的两套口径；
- 批量提取照旧落同一目录：浏览过的页已提好，批量跑只是幂等覆盖（原子写）。

参数（zoom/ext/quick/dpi）由宿主经 :meth:`set_params_provider` 注入——读
「图片提取」面板当前的表单值，保证单页提取与点「执行本子任务」的批量提取
产物一致。表单填到一半 ``get_args()`` 抛 ``ValueError`` 时按默认参数兜底。

编辑链：产物是磁盘上的真实文件，放大弹窗/右键对**已提取**的页给
``edit_path``（右键「编辑图片」覆盖回写）；未提取的页仍是矢量页，只有
「预览图片」。回写后经 :attr:`image_saved` 通知宿主（登记 sizes.json、
重生成页缩略图、同步各查看器）——与旧 ``ImageViewerWidget`` 的信号同形，
宿主侧接线不变。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImageReader

from desktop.components.viewers.pdf_viewer import PdfViewerWidget
from desktop.components.viewers.image_zoom_dialog import ZoomTarget
from desktop.workers import PreviewWorker, connect_queued
from utils.pdf_extract import DEFAULT_RENDER_DPI, extract_single_page


class _SingleExtractWorker(QObject):
    """单页提取 worker：跑在 QThread 里，只认结构化结果（不 print）。"""

    done = Signal(int, dict)
    failed = Signal(int, str)

    def __init__(self, pdf_path: Path, page_idx: int, out_dir: Path,
                 params: dict):
        super().__init__()
        self._pdf = Path(pdf_path)
        self.page_idx = int(page_idx)
        self._out_dir = Path(out_dir)
        self._params = dict(params or {})

    def run(self) -> None:
        """调 :func:`utils.pdf_extract.extract_single_page`（单页不可中断）。"""
        try:
            result = extract_single_page(
                str(self._pdf), self.page_idx, str(self._out_dir),
                zoom=self._params.get("zoom", 1),
                ext=self._params.get("ext", "jpg"),
                quick=self._params.get("quick", True),
                dpi=self._params.get("dpi") or DEFAULT_RENDER_DPI,
            )
        except Exception as exc:  # noqa: BLE001 - QThread.run 异常不许逃出
            self.failed.emit(self.page_idx, f"{type(exc).__name__}: {exc}")
            return
        if result.get("ok"):
            self.done.emit(self.page_idx, result)
        else:
            self.failed.emit(self.page_idx, str(result.get("err") or "提取失败"))

    def cancel(self) -> None:
        """单页提取不可中断（一次渲染 ≤几百 ms，等它跑完比打断安全）。"""


class ExtractPreviewWidget(PdfViewerWidget):
    """「图片提取」步骤的预览：PDF 页缩略图 + 按页按需提取的产物大图。"""

    #: 单页提取落盘完成（绝对路径）。宿主据此登记尺寸 / 重建页面清单。
    extract_saved = Signal(str)
    #: 编辑器/弹窗覆盖了某个真实文件（与 ImageViewerWidget.image_saved 同形，
    #: 宿主接线照旧）。目前只有「已提取页」的右键编辑会走到这里。
    image_saved = Signal(str, object)

    def __init__(self, placeholder: str = "暂无 PDF", parent=None):
        super().__init__(placeholder, parent)
        self._extract_dir: Path | None = None
        self._params_provider: Callable[[], dict] | None = None
        #: 提取/加载请求的代际号：换文档即失效，迟到的结果不许上屏
        self._extract_seq = 0
        #: 文档代际号：set_pdf 递增，worker 回调按它丢弃跨任务的迟到结果
        self._doc_gen = 0
        #: 正在后台提取的页号（0-based）：同一页不重复发起
        self._extracting: set[int] = set()
        #: 当前大图显示的是第几页的**提取结果**（None = 显示的是 PDF 渲染页）
        self._shown_extract_page: int | None = None

    # ------------------------------------------------------------ 宿主注入
    def set_extract_dir(self, extract_dir: Path | None) -> None:
        """记录/刷新产物目录；当前页已有产物就**立即**切换显示。

        批量提取的轮询（``runner._poll_extract_results``）与每次进本步骤的
        ``_refresh_preview`` 都走这里：文件一出现，大图马上从"等提取"换成
        提取结果。还没有产物的页**不打断**当前显示——提取只由「切页」触发，
        刷新不该替用户发起提取。
        """
        self._extract_dir = Path(extract_dir) if extract_dir else None
        self._refresh_current_extract()

    def set_params_provider(self, provider: Callable[[], dict] | None) -> None:
        """注入提取参数来源（宿主读「图片提取」面板表单）。"""
        self._params_provider = provider

    # ------------------------------------------------------------ 产物路径
    def _extract_params(self) -> dict:
        provider = self._params_provider
        if provider is None:
            return {}
        try:
            return dict(provider() or {})
        except Exception:  # noqa: BLE001 - 表单填一半 get_args 会抛 ValueError
            return {}

    def _extract_ext(self) -> str:
        """产物后缀：跟面板当前的 ext 参数走（与批量提取同名同位）。"""
        ext = str(self._extract_params().get("ext") or "jpg")
        return ext.lower().lstrip(".") or "jpg"

    def extract_path_for(self, page: int) -> Path | None:
        """第 page 页（0-based）的产物路径；没有产物目录时为 None。"""
        if self._extract_dir is None:
            return None
        return self._extract_dir / f"{page + 1}.{self._extract_ext()}"

    # ------------------------------------------------------------ 换文档
    def set_pdf(self, path, placeholder=None, cache_dir=None) -> None:
        """换 PDF：提取态全部作废（在飞的提取结果按代际丢弃）。"""
        self._doc_gen += 1
        self._extract_seq += 1
        self._extracting.clear()
        self._shown_extract_page = None
        super().set_pdf(path, placeholder=placeholder, cache_dir=cache_dir)

    # ------------------------------------------------------------ 切页主逻辑
    def _select_page(self, page: int, _path: str = "") -> None:
        """切到第 page 页：有产物显示产物，没产物现场提取，都没有才纯预览。

        ⚠️ 完全取代父类的「渲 PDF 大图」分支——本控件的语义就是"看提取
        结果"；只有 ``set_extract_dir`` 还没被调过（宿主尚未接好产物目录，
        理论上只在构造早期出现）才退回父类的纯预览。
        """
        if not self._pdf_path:
            return
        target = self.extract_path_for(page)
        if target is None:
            self._shown_extract_page = None
            super()._select_page(page, _path)
            return
        if target.exists():
            self._display_extract_file(page, target)
            return
        self._extract_and_display(page, target)

    def _display_extract_file(self, page: int, target: Path) -> None:
        """异步解码产物文件并上屏（大图解码与 PDF 渲染同一条 PreviewWorker 路）。"""
        pdf = self._pdf_path
        gen = self._doc_gen
        self._shown_extract_page = page
        # 作废在飞的 PDF 页渲染/预取/旧加载：只有最新一次请求能上屏
        self._page_req_seq += 1
        self._extract_seq += 1
        seq = self._extract_seq
        edge = self.view.preview_edge()
        self.view.clear_image(f"正在加载第 {page + 1} 页提取结果...")
        self.run_worker(
            lambda: PreviewWorker(target, longest_edge=edge),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished,
                    lambda _p, image, _s, q=seq, g=gen, w=pdf:
                        self._on_extract_image_ready(q, g, w, image),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda _p, msg, q=seq, g=gen:
                        self._on_extract_load_failed(q, g, msg),
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_extract_image_ready(self, seq: int, gen: int, pdf, image) -> None:
        if seq != self._extract_seq or gen != self._doc_gen:
            return  # 迟到的结果：用户已经切了页/换了文档
        if self._pdf_path is None or Path(self._pdf_path) != Path(pdf):
            return
        self.view.set_image(image)

    def _on_extract_load_failed(self, seq: int, gen: int, msg: str) -> None:
        if seq != self._extract_seq or gen != self._doc_gen:
            return
        self.view.clear_image(f"加载失败：{msg}")

    def _extract_and_display(self, page: int, target: Path) -> None:
        """这一页还没有产物：后台提取落盘，完成后上屏。"""
        if page in self._extracting:
            # 已经在提了：保持"正在提取"提示，完成后 _on_extract_done 上屏。
            # ⚠️ 作废在飞的渲染/旧加载，别让它们的结果盖掉提示。
            self._shown_extract_page = None
            self._page_req_seq += 1
            self._extract_seq += 1
            self.view.clear_image(f"正在提取第 {page + 1} 页...")
            return
        pdf = self._pdf_path
        if pdf is None or self._extract_dir is None:
            return
        pdf = Path(pdf)
        out_dir = self._extract_dir
        params = self._extract_params()
        gen = self._doc_gen
        self._extracting.add(page)
        self._shown_extract_page = None
        self._page_req_seq += 1
        self._extract_seq += 1
        self.view.clear_image(f"正在提取第 {page + 1} 页...")
        self.run_worker(
            lambda: _SingleExtractWorker(pdf, page, out_dir, params),
            lambda worker, thread: (
                connect_queued(
                    self, worker.done,
                    lambda p, result, t=target, g=gen, w=pdf:
                        self._on_extract_done(p, result, t, g, w),
                    thread,
                ),
                connect_queued(
                    self, worker.failed,
                    lambda p, msg, g=gen: self._on_extract_failed(p, msg, g),
                    thread,
                ),
                worker.done.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_extract_done(self, page: int, result: dict, target: Path,
                         gen: int, pdf: Path) -> None:
        """提取完成：通知宿主登记尺寸/清单；用户还停在这页才上屏。"""
        self._extracting.discard(page)
        if gen != self._doc_gen:
            return  # 换了文档：文件已落盘，但界面是另一本书的
        self.extract_saved.emit(str(target))
        if max(self.strip.currentRow(), 0) != page:
            return  # 用户已翻走：产物在盘上，切回来时走"有产物"分支
        self._display_extract_file(page, target)

    def _on_extract_failed(self, page: int, msg: str, gen: int) -> None:
        self._extracting.discard(page)
        if gen != self._doc_gen:
            return
        if max(self.strip.currentRow(), 0) == page:
            self.view.clear_image(f"第 {page + 1} 页提取失败：{msg}")

    def _refresh_current_extract(self) -> None:
        """宿主刷新：当前页的产物**新出现**时切换显示（不发起提取）。"""
        if not self._pdf_path or not self.strip.count():
            return
        page = max(self.strip.currentRow(), 0)
        if page in self._extracting or self._shown_extract_page == page:
            return  # 在提了 / 已经显示的就是这页产物：不用动
        target = self.extract_path_for(page)
        if target is None or not target.exists():
            return
        self._display_extract_file(page, target)

    # ------------------------------------------------------------ 编辑生效链
    def refresh_page(self, path_text: str) -> None:
        """某页产物文件被覆盖（编辑器完成/缩略图重生成）：重载当前页大图。

        ``show_edited_image`` 在本控件上没有 ``apply_edited_image``，会退到
        这里；按路径匹配**当前页的产物**才动，其余页不打扰。
        """
        if self._shown_extract_page is None or not self._pdf_path:
            return
        page = self._shown_extract_page
        target = self.extract_path_for(page)
        if target is None or str(target) != str(path_text):
            return
        self._display_extract_file(page, target)

    def _zoom_target(self, index: int) -> ZoomTarget | None:
        """放大弹窗目标：**已提取**的页给真实文件（可编辑回写），否则矢量页。"""
        target = self.extract_path_for(index)
        if target is not None and target.exists():
            reader = QImageReader(str(target))
            size = reader.size()
            original = size if size.isValid() else None
            cap = max(original.width(), original.height()) if original else None
            return ZoomTarget(
                render=lambda edge: PreviewWorker(target, longest_edge=edge),
                note=f"第 {index + 1} 页 · {target.name}",
                stem=target.stem,
                count=max(self.strip.count(), 1),
                original=original,
                cap=cap,
                # 大图显示的像素就是这个文件的全部像素：编辑回写它才安全
                save_path=target,
                edit_path=target,
            )
        return super()._zoom_target(index)

    def _on_zoom_image_saved(self, path_text: str, image=None) -> None:
        """弹窗里覆盖了产物文件：转发宿主 + 当前大图即时换上编辑结果。"""
        self.image_saved.emit(path_text, image)
        page = self._shown_extract_page
        if page is None:
            return
        target = self.extract_path_for(page)
        if target is None or str(target) != str(path_text):
            return
        if image is not None and not getattr(image, "isNull", lambda: True)():
            self.view.set_image(image)
