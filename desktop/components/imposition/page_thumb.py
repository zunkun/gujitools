# -*- coding: utf-8 -*-
"""拼版页的**"页面效果"缩略图实体**——按版面合成整页、落盘、带映射数据。

为什么是"实体"而不是内存合成（用户 2026-10-09 两轮报障的合流）：

1. 第一轮：一页拼版是两张图合成的页面（``3-l`` + ``4-r``），旧口径"每页取
   第一张源图当代表"让缩略图只显示半幅——缩略图必须按**页面效果**显示；
2. 第二轮（0002 任务实测）：内存合成依赖"页内每张源图的缩略图都已在内存"，
   任何一张没到就出**半张**；而且回填反查表只登记每页第一张，第二张到了
   也不重贴。用户拍板：**缩略图实体要生成落地**——组合成拼版图片另放一个
   目录，直接按 ``page1 page2`` 命名，做好映射数据。

本模块给两层东西：

- **纯函数**：:func:`page_signature`（这一页的内容签名：版面 + 每张源图的
  文件指纹——大小/mtime，编辑覆盖后指纹变 ⇒ 签名变 ⇒ 重生成）、
  :func:`compose_page_thumb_from_files`（从**全尺寸源图**直接合成整页
  缩略图，等比缩放解码、白底压平、rect 比例映射、绕中心顺时针旋转）、
  :func:`thumb_file_name` / :func:`load_page_index` / :func:`write_page_index`
  （``pageN.jpg`` 命名与 ``index.json`` 映射的读写）；
- **宿主侧管理者** :class:`PageThumbManager`：签名命中贴**落盘实体**、
  未命中排队交后台 worker（:class:`~desktop.workers.\
imposition_page_thumb_worker.ImpositionPageThumbWorker`）生成落盘——UI 永远
  只认实体文件，重进任务零生成。

两处宿主（任务流程的拼版详情页与独立拼图页）目录各归各（用户 2026-10-04
明确「singletask 和 taskdetail 不是一回事」）：任务写
``tasks/<id>/thumbnails/imposition_pages/``，独立区写
``singletask/<子任务>/page_thumbs/``。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (
    QObject, QRectF, QSize, Qt, Signal, Slot,
)
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap

from desktop.services.imposition import normalize_page, page_bounds
from desktop.workers.thumb_cache_worker import flatten_on_white
from utils.file_utils import write_bytes_atomic

#: 映射文件名（与实体文件同目录）
INDEX_NAME = "index.json"
#: 映射结构版本：改字段口径时 +1，旧文件整体作废（全部重生成）
INDEX_VERSION = 1


# --------------------------------------------------------------------- 签名
def _file_fingerprint(path_text: str) -> str:
    """一张源图的**文件指纹**（大小 + mtime 纳秒）；取不到当 ``missing``。

    ⚠️ 不读内容：签名在每次刷新时对**每一页**都要算一遍（380 页 × 2 文件
    = 760 次 stat，微秒级），读内容就成灾难了。编辑覆盖后大小或 mtime 必变
    ⇒ 指纹变 ⇒ 签名变 ⇒ 含它的页重生成（2026-10-08"编辑完左列还是老图"
    的实体版防复发）。
    """
    try:
        stat = Path(path_text).stat()
    except OSError:
        return "missing"
    return f"{stat.st_size}-{stat.st_mtime_ns}"


def page_signature(page: dict) -> str | None:
    """一页拼版缩略图实体的**内容签名**；空页/不可修复页返回 ``None``。

    签名覆盖：页内**有哪些文件**（含文件指纹）、版面（rect/rotation）。
    任何一件变了签名就变——管理者的"命中/重生成"判据就这一个。
    """
    normalized = normalize_page(page)
    if normalized is None:
        return None
    parts = []
    for item in normalized["items"]:
        x, y, w, h = item["rect"]
        parts.append(
            f"{item['file']}\x1f{_file_fingerprint(item['file'])}"
            f"\x1f{x:.1f},{y:.1f},{w:.1f},{h:.1f}"
            f"\x1f{float(item.get('rotation') or 0.0):.2f}"
        )
    raw = "\x1e".join(parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


# --------------------------------------------------------------------- 合成
def _decode_scaled(path_text: str, width: int, height: int) -> QImage | None:
    """把一张源图按**目标矩形尺寸**缩放解码（不把整张原图读进内存）。

    ``rect`` 存的就是源图像素坐标，比例映射后目标像素尺寸 = rect 尺寸 ×
    缩放系数——直接让解码器出这个尺寸（``QImageReader.setScaledSize``），
    2000×3000 的源图缩到 256px 只解一小块。少数文件缩放解码失败时回退
    整图解码后内存缩放。rembg 产物"白底被标成透明"，一律过
    :func:`flatten_on_white`（透明 = 纸色，与打印效果一致）。
    """
    reader = QImageReader(path_text)
    reader.setAutoTransform(True)
    reader.setScaledSize(QSize(max(1, width), max(1, height)))
    image = flatten_on_white(reader.read())
    if image.isNull():
        image = QImage(path_text)
        if image.isNull():
            return None
        image = flatten_on_white(image.scaled(
            max(1, width), max(1, height),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
    return image


def compose_page_thumb_from_files(
    page: dict, edge: int = 256
) -> QImage | None:
    """一页拼版 → **页面效果**缩略图实体（白底 QImage，从全尺寸源图合成）。

    与成品 :func:`services.imposition.compose_page` 同一条版面规则：白底 +
    各图按 ``rect`` 相对 :func:`page_bounds` 外接框的比例摆放 + 外框紧裁，
    只是像素密度低（最长边 ``edge``）；有 ``rotation`` 绕该项中心顺时针转
    （与操作画布 ``canvas.py`` 同口径）。页内某张源图读不出来就**留白**
    （半张也比空框诚实；文件真丢了签名里的指纹是 ``missing``，不会反复
    重生成）。只有整页非法（没有有效项 / 外框退化）才返回 ``None``。
    """
    normalized = normalize_page(page)
    if normalized is None:
        return None
    left, top, right, bottom = page_bounds(normalized)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None
    scale = float(edge) / max(width, height)
    target_w = max(1, int(round(width * scale)))
    target_h = max(1, int(round(height * scale)))
    image = QImage(target_w, target_h, QImage.Format.Format_RGB32)
    image.fill(QColor(255, 255, 255))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for item in normalized["items"]:
        x, y, w, h = item["rect"]
        tw = max(1, int(round(w * scale)))
        th = max(1, int(round(h * scale)))
        content = _decode_scaled(item["file"], tw, th)
        if content is None:
            continue
        tx = (x - left) * scale
        ty = (y - top) * scale
        rotation = float(item.get("rotation") or 0.0)
        painter.save()
        if rotation:
            center_x, center_y = tx + tw / 2.0, ty + th / 2.0
            painter.translate(center_x, center_y)
            painter.rotate(rotation)  # Qt y 向下坐标系里的"视觉顺时针"
            painter.translate(-center_x, -center_y)
        painter.drawImage(QRectF(tx, ty, tw, th), content)
        painter.restore()
    painter.end()
    return image


# --------------------------------------------------------------------- 映射
def thumb_file_name(page_index: int) -> str:
    """页号（0 基）→ 实体文件名：``page1.jpg`` 从第一页起数（用户口径）。"""
    return f"page{page_index + 1}.jpg"


def load_page_index(out_dir: Path, edge: int) -> dict[int, str]:
    """读映射数据：``{页号(0基): 签名}``；没有/坏档/边长不符给空表。

    ``index.json`` 形如
    ``{"version": 1, "edge": 256, "pages": [{"page": 1, "thumb":
    "page1.jpg", "signature": "..."}]}``——页号从 1 起存（人看的口径），
    0 基换算只在内存里做。
    """
    try:
        data = json.loads(
            (Path(out_dir) / INDEX_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != INDEX_VERSION:
        return {}
    if int(data.get("edge") or 0) != int(edge):
        return {}  # 边长变了＝整批实体尺寸不对口，全部重生成
    mapping: dict[int, str] = {}
    for entry in data.get("pages") or []:
        if not isinstance(entry, dict):
            continue
        try:
            mapping[int(entry["page"]) - 1] = str(entry["signature"])
        except (KeyError, TypeError, ValueError):
            continue
    return mapping


def write_page_index(
    out_dir: Path, mapping: dict[int, str], edge: int
) -> bool:
    """把映射数据原子落盘；失败返回 False（实体文件还在，下次重写即可）。"""
    payload = {
        "version": INDEX_VERSION,
        "edge": int(edge),
        "pages": [
            {"page": index + 1, "thumb": thumb_file_name(index),
             "signature": signature}
            for index, signature in sorted(mapping.items())
        ],
    }
    data = json.dumps(payload, ensure_ascii=False, indent=1)
    try:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(Path(out_dir) / INDEX_NAME, data.encode("utf-8"))
    except OSError:
        return False
    return True


def _snapshot_page(page: dict) -> dict:
    """页字典的一份**独立快照**（防抖期间用户还在改版面，别拿活引用）。"""
    items = page.get("items") or []
    return {
        "items": [dict(item) for item in items if isinstance(item, dict)]
    }


# ------------------------------------------------------------------- 管理者
class PageThumbManager(QObject):
    """页面缩略图**实体**的管理者：命中贴实体、未命中排队后台生成落盘。

    宿主只做三件事：刷新时对每页调 :meth:`pixmap_for`（命中回 QPixmap、
    未命中回 ``None`` 占位并自动排队）→ :meth:`flush`（把排队页交后台
    worker）→ 连 :attr:`page_ready` 把生成好的那条贴回左列。版面/源图
    变了调 :meth:`invalidate`（宿主的防抖计时器到点后）。
    """

    #: 一页的实体缩略图生成完：(0 基页号, QPixmap)
    page_ready = Signal(int, QPixmap)

    def __init__(
        self,
        out_dir: Path | str,
        edge: int,
        submit: Callable,
        parent: QObject | None = None,
    ):
        """``out_dir`` 实体目录；``edge`` 最长边；``submit``＝宿主的
        ``run_worker(factory, wire)``（线程的创建与回收归宿主管）。"""
        super().__init__(parent)
        self._edge = int(edge)
        self._submit = submit
        self._dir = Path(out_dir)
        self._mapping: dict[int, str] = {}
        self._pix: dict[str, QPixmap] = {}
        self._pending: dict[int, dict] = {}
        self._inflight = False
        self.reload()

    @property
    def directory(self) -> Path:
        return self._dir

    # ------------------------------------------------------------- 生命周期
    def bind(self, out_dir: Path | str) -> None:
        """换目录（换任务/换子任务）：状态全清、重读那份映射。"""
        self._dir = Path(out_dir)
        self.reset()
        self.reload()

    def reset(self) -> None:
        """清空内存态（映射/位图缓存/排队）；盘上实体不动。"""
        self._mapping.clear()
        self._pix.clear()
        self._pending.clear()

    def reload(self) -> None:
        """从盘上重读映射数据。"""
        self._mapping = load_page_index(self._dir, self._edge)

    # ------------------------------------------------------------- 宿主接口
    def retain(self, count: int) -> None:
        """页清单缩到 ``count`` 后：多出来的映射删掉、孤儿实体清掉。"""
        stale = [index for index in self._mapping if index >= count]
        for index in stale:
            del self._mapping[index]
        for index in [i for i in self._pending if i >= count]:
            del self._pending[index]
        if stale:
            self._cleanup_orphans()
            self._save_index()

    def pixmap_for(self, index: int, page: dict) -> QPixmap | None:
        """这一页的缩略图：实体命中回 QPixmap；未命中排队并回 ``None``。

        "命中"＝映射里这一页的签名与当前签名一致**且**实体文件读得出来。
        未命中（没有实体/版面或源图变了/实体损坏）自动排队，:meth:`flush`
        时交给后台 worker。
        """
        signature = page_signature(page)
        if signature is None:
            return None
        pixmap = None
        if self._mapping.get(index) == signature:
            pixmap = self._pix.get(signature)
            if pixmap is None:
                image = QImage(str(self._dir / thumb_file_name(index)))
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image)
                    self._pix[signature] = pixmap
        if pixmap is None:
            # 版面"改过去又改回来"时 memo 里可能还有这一版（内容寻址）：
            # 直接复用，不必等重生成
            pixmap = self._pix.get(signature)
        if pixmap is None:
            self._pending[index] = {
                "page": _snapshot_page(page), "signature": signature,
            }
            return None
        return pixmap

    def flush(self) -> None:
        """把排队的页整批交给后台 worker（一批一个；在跑就等它收尾续批）。"""
        if self._inflight or not self._pending:
            return
        from desktop.workers.imposition_page_thumb_worker import (
            ImpositionPageThumbWorker,
        )
        from desktop.workers.worker_host import connect_queued

        jobs = []
        for index in sorted(self._pending):
            job = self._pending[index]
            jobs.append({
                "index": index,
                "name": thumb_file_name(index),
                "signature": job["signature"],
                "page": job["page"],
            })
        self._inflight = True
        import sys as _sys; print(f"[dbg] mgr{id(self):x} flush jobs={len(jobs)} dir={self._dir}", file=_sys.stderr)
        self._submit(
            lambda: ImpositionPageThumbWorker(jobs, self._dir, self._edge),
            lambda worker, thread: (
                connect_queued(
                    self, worker.page_ready, self._on_page_ready, thread),
                connect_queued(self, worker.completed, self._on_done, thread),
                worker.failed.connect(lambda m: print(f"[dbg] worker failed: {m}")),
                worker.failed.connect(thread.quit),
            ),
        )

    def invalidate(self, indexes, pages: list) -> None:
        """版面/源图变了：把这几页排进重生成批次（签名不匹配自然排队）。"""
        for index in indexes:
            if 0 <= index < len(pages):
                self.pixmap_for(index, pages[index])
        self.flush()

    # -------------------------------------------------------------- 后台回调
    @Slot(int, QImage, str, str)
    def _on_page_ready(self, index: int, image, _path: str, sig: str) -> None:
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            return
        import sys as _s
        print(f"[dbg-m] mgr{id(self):x} page_ready index={index}", file=_s.stderr)
        import sys as _s
        print(f"[dbg-m] mgr{id(self):x} page_ready index={index}", file=_s.stderr)
        self._mapping[index] = sig
        self._pix[sig] = pixmap
        self._pending.pop(index, None)
        self.page_ready.emit(index, pixmap)

    @Slot()
    def _on_done(self) -> None:
        import sys as _s
        print(f"[dbg-m] mgr{id(self):x} on_done mapping={self._mapping} pending={sorted(self._pending)}", file=_s.stderr)
        self._inflight = False
        self._save_index()
        self._cleanup_orphans()
        if self._pending:
            self.flush()  # 批次跑的时候又排进了新页（防抖/编辑回写）

    # -------------------------------------------------------------- 内部
    def _save_index(self) -> None:
        write_page_index(self._dir, self._mapping, self._edge)

    def _cleanup_orphans(self) -> None:
        """删掉映射里已经没有的 ``pageN.jpg``（删页后留下的孤儿实体）。"""
        keep = {thumb_file_name(index) for index in self._mapping}
        import sys as _s
        print(f"[dbg-m] cleanup keep={keep}", file=_s.stderr)
        try:
            entries = list(self._dir.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name == INDEX_NAME or entry.suffix.lower() != ".jpg":
                continue
            if entry.name not in keep:
                import sys as _s
                print(f"[dbg-m] mgr{id(self):x} orphan deleted: {entry.name}", file=_s.stderr)
                try:
                    entry.unlink()
                except OSError:
                    pass
