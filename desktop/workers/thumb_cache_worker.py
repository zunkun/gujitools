# -*- coding: utf-8 -*-
"""**独立任务左栏缩略图的统一缓存层**（``~/Documents/guji/singletask/<子任务>/``）。

用户 2026-10-03 的要求之一是「**所有独立任务左侧显示的都是缩略图**」。此前
只有图片提取页有 PDF 页缩略图（走 ``PdfViewerWidget`` 自己的缩略图通道），
其余四页左栏塞的是**原图**或各自的专用预览控件——同一件「看一批图」的事在五个
页面有五种实现，缓存也无处安放。

本模块管**非 PDF 源**（一批图片）这一半：把每张图渲成
``singletask/<子任务>/thumbs/<边长>/<键>.jpg``（路径规则见
:func:`desktop.utils.files.image_thumb_cache_path`）。

PDF 源**不在这里**——它已有了一份成熟实现（``PreviewWorker`` 的缩略图通道：
单飞锁、按耗时让出 GIL、原子写、命中缓存直接读、页边界可取消），再写一份必然
漂移，而且那份代码里每条注释都在解释踩过的坑。PDF 侧由
:class:`~desktop.components.viewers.pdf_page_source.PdfPageSource` 直接驱动
那个通道。

⚠️ 本模块只写**缓存**，不碰产物：模块页的输出目录仍由
:meth:`desktop.steps.spec.StepSpec.default_output` 决定（用户明确要求「生成
目录按照原先的」）。

⚠️ **透明 = 白底**（用户 2026-10-04「拼板左列缩略图全是黑的」）：去底色
（rembg）产物是**调色板 PNG、白底被标记为透明**（``tRNS``）。Qt 解码为
``ARGB32_Premultiplied``（透明像素 RGB=0），而缓存是 **JPEG——没有 alpha
通道**：直接编码时"透明 = 黑"会被**固化**成纯黑图（用户看到的黑块就是它）。
所以本模块产出前一律过 :func:`flatten_on_white`（白纸黑字，与打印/合成
效果一致）；修复前写坏的历史全黑缓存由 :func:`is_all_black` 兜底重渲自愈。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter

from desktop.utils.files import THUMBNAIL_EDGE, book_key
from utils.file_utils import write_bytes_atomic

#: 缓存缩略图的**最小合理体积**（字节）。低于它必然是写坏/截断的历史遗留：
#: 正常一张 256px JPEG 有几千字节到几十 KB。判据加上体积，坏缓存才能自愈。
#: 与 ``source_thumbnails_worker.MIN_THUMB_BYTES`` 同值、两处各留一份：那边的
#: 目录命名与产出流程与这里不同，不共用一个常量免得互相牵动。
MIN_THUMB_BYTES = 512


def thumb_cache_file(out_dir: Path | str, image: Path | str) -> Path:
    """一张源图在 ``out_dir`` 下的缓存文件名（去后缀 + 大小 + 路径指纹）。

    ⚠️ 键**必须逐图算**、不能按序号：图片源的条目名五花八门（``1.jpg`` /
    ``右-01.png``…），按序号命名一旦清单顺序变了就会张冠李戴——拿到的是
    **别张图的缓存**。这与 PDF 侧「按页号命名 ⇒ 必须按书分目录」是同一个坑。
    """
    return Path(out_dir) / f"{book_key(image)}.jpg"


def stat_mtime(path) -> float:
    """文件 mtime；取不到返回 0（拿不到就当"缓存都是新的"→ 不重渲）。"""
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def cache_usable(target: Path, source_mtime: float) -> bool:
    """缓存缩略图能不能用：不比源图旧，且体积不像截断。"""
    try:
        stat = Path(target).stat()
    except OSError:
        return False
    return stat.st_mtime >= source_mtime and stat.st_size >= MIN_THUMB_BYTES


def is_all_black(image: QImage) -> bool:
    """整张图是否**纯黑**（历史坏缓存的"体检"，见 :func:`flatten_on_white`）。

    修复透明压黑之前写下的缓存是全黑 JPEG，而 :func:`cache_usable` 只看
    mtime/体积——这些坏缓存 mtime 比源图新（写完之后源图没再动过），会被
    **永久命中**。读缓存时做一次纯黑体检，命中就删掉重渲，坏缓存自愈。

    ⚠️ 判据是**精确纯黑**：整张 JPEG 的 DCT 系数全为 0 时解码回来精确为
    (0,0,0)，实测成立；有内容的图绝不会落入此判据。极端的"源图本就是一
    张全黑页"会被每次重渲一遍（毫秒级），代价可忽略、换来的是坏缓存绝不
    会永久钉在界面上。
    """
    if image.isNull():
        return False
    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    width, height = rgb.width(), rgb.height()
    if width <= 0 or height <= 0:
        return False
    data = bytes(rgb.constBits())
    # RGB32：每像素 [B,G,R,A] 四字节，A 恒为 0xFF（RGB32 的定义），且
    # bytesPerLine == width*4（无行填充，实测）。全黑 ⇒ 非零字节数恰为像素数。
    return len(data) - data.count(0) == width * height


def decode_sized(path: Path, edge: int) -> QImage:
    """按最长边 ``edge`` 缩放解码一张图（尽量不把整张原图读进内存）。

    与 :class:`~desktop.workers.image_list_worker.ImageListWorker` 同一套做法：
    ``QImageReader.setScaledSize`` 让解码器直接出目标尺寸；少数格式/异常文件
    缩放解码会失败，回退到整图解码后内存缩放。
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        reader.setScaledSize(
            size.scaled(QSize(edge, edge), Qt.AspectRatioMode.KeepAspectRatio)
        )
    image = reader.read()
    if image.isNull():
        image = QImage(str(path))
    if not image.isNull() and (image.width() > edge or image.height() > edge):
        image = image.scaled(
            edge, edge,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
    return image


def flatten_on_white(image: QImage) -> QImage:
    """把**带 alpha 的图**合成到白底；无 alpha（或空图）原样返回。

    ⚠️ 为什么必须有这一步（用户 2026-10-04「拼板左列全是黑的」实锤往
    事）：去底色产物是"**白底被标记为透明**"的调色板 PNG。Qt 解码成
    ``ARGB32_Premultiplied``——透明像素的 RGB 是 0；而缓存的 JPEG 没有
    alpha 通道，**直接编码 = 把透明固化成黑色**，于是整张缩略图纯黑
    （实测：一张 256px 的坏缓存只有 1331 字节、全图 (0,0,0)）。

    这类图"透明"的语义就是**纸色（白）**，合成到白底是唯一正确读法：
    白纸黑字，与打印/合成后的效果一致。不给 alpha 的图（照片、扫描图）
    原样直通，零改动成本。
    """
    if image.isNull() or not image.hasAlphaChannel():
        return image
    flattened = QImage(image.size(), QImage.Format.Format_RGB32)
    flattened.fill(QColor(255, 255, 255))
    painter = QPainter(flattened)
    painter.drawImage(0, 0, image)
    painter.end()
    return flattened


def encode_jpeg(image: QImage, quality: int = 80) -> bytes:
    """QImage → JPEG 字节。

    ⚠️ ``QImage.save`` 只能写**文件**，这里借 ``QBuffer`` 拿字节——因为落盘
    必须走 :func:`utils.file_utils.write_bytes_atomic`（非原子写留下的截断
    JPEG，mtime 也是新的，会被上面的 :func:`cache_usable` 永久当成有效缓存
    且没有任何自愈路径）。
    """
    array = QByteArray()
    buffer = QBuffer(array)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", quality)
    buffer.close()
    return bytes(array)


class ImageThumbCacheWorker(QObject):
    """把一批**源图片**的缩略图渲进 singletask 缓存，逐张就绪即发一次。

    信号口径与既有的 ``ImageListWorker`` 一致（``thumbnail_ready(int, QImage,
    str)`` / ``completed`` / ``failed``），所以各查看器的分批装载
    (:class:`~desktop.components.viewers.thumbs_loader.ThumbsMixin`) 能原样复用
    ——只是这里第三参数是**缓存文件路径**而不是源图路径（缓存写完前它可能是
    空串：那一张仍然会显示，只是不承诺下次命中）。
    """

    thumbnail_ready = Signal(int, QImage, str)  # index, 缩略图, 缓存文件路径
    completed = Signal()
    failed = Signal(str)

    def __init__(
        self,
        paths: list[Path | str],
        out_dir: Path | str,
        edge: int = THUMBNAIL_EDGE,
        names: list[str | None] | None = None,
    ):
        """``paths`` 为源图清单；``out_dir`` 是这一批共用的缓存目录
        （``singletask/<子任务>/thumbs/<边长>/``）；``edge`` 为缩略图最长边。

        ``names``（可选，与 ``paths`` 等长）：每张图**显式指定的缓存文件名**。
        给了就用它，为 ``None`` 的项回落到 :func:`thumb_cache_file` 的图键命名。

        ⚠️ 什么时候需要它（用户 2026-10-04「只保留一份、按序号处理」）：extract
        的缓存文件名是**序号**（``0001.jpg``），与源图文件名无关——同一页的缩略图
        在「未提取」阶段是 PDF 渲染、「提取后」是产物重渲，两次都写**同一个文件**。
        这时目标名只能由调用方按序号给出，不能从路径反推。
        """
        super().__init__()
        self.paths = [Path(p) for p in paths]
        self.out_dir = Path(out_dir)
        self.edge = int(edge)
        #: 显式缓存文件名（可能含 ``None`` 洞位，与 paths 等长）
        self.names = list(names) if names is not None else None
        self._cancelled = False

    def cancel(self) -> None:
        """请求中止：在**下一张**之前退出（已写好的都在盘上，重进直接命中）。"""
        self._cancelled = True

    def cache_path(self, index: int) -> Path:
        """第 index 张图的缓存路径（宿主拿去当 ``thumb_provider`` 的答案）。"""
        if self.names is not None and index < len(self.names):
            name = self.names[index]
            if name:
                return self.out_dir / name
        return thumb_cache_file(self.out_dir, self.paths[index])

    @Slot()
    def run(self) -> None:
        """逐张：命中缓存直接读，否则渲一张并原子写盘。"""
        try:
            for index, path in enumerate(self.paths):
                if self._cancelled:
                    break
                target = self.cache_path(index)
                if cache_usable(target, stat_mtime(path)):
                    image = QImage(str(target))
                    if image.isNull() or is_all_black(image):
                        # 读不出来（损坏但 mtime 看着还新）、或纯黑（修复
                        # flatten_on_white 之前写下的"透明被压黑"历史缓存
                        # ——mtime 比源图新，不体检就会被永久命中）：
                        # 删掉重渲一次
                        _unlink(target)
                        image = flatten_on_white(decode_sized(path, self.edge))
                        if image.isNull():
                            continue
                        _write_jpeg(image, target)
                else:
                    image = flatten_on_white(decode_sized(path, self.edge))
                    if image.isNull():
                        continue  # 读不出来的图跳过，不让整批停摆
                    # 写不下去（权限/磁盘满）时仍然把图发出去：界面照常显示，
                    # 只是这一张下次没有缓存可命中。
                    if not _write_jpeg(image, target):
                        self.thumbnail_ready.emit(index, image, "")
                        continue
                self.thumbnail_ready.emit(index, image, str(target))
            self.completed.emit()
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(str(exc))


def _write_jpeg(image: QImage, target: Path) -> bool:
    """原子写一张 JPEG 缩略图；失败返回 False（不抛，调用点决定要不要仍显示）。"""
    data = encode_jpeg(image)
    if not data:
        return False
    try:
        write_bytes_atomic(target, data)
    except OSError:
        return False
    return True


def _unlink(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


__all__ = [
    "ImageThumbCacheWorker",
    "MIN_THUMB_BYTES",
    "cache_usable",
    "decode_sized",
    "encode_jpeg",
    "flatten_on_white",
    "is_all_black",
    "stat_mtime",
    "thumb_cache_file",
]
