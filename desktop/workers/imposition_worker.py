# -*- coding: utf-8 -*-
"""后台把图片拼版文档合成为成品页图（写 ``stages/imposition``）。

为什么要后台：版面拖动/删除会频繁触发重合成，而一页拼版要打开两张原图、
缩放、旋转、alpha 合成再编 PNG——几十页叠起来在主线程做就是明显卡顿。
合成只用 PIL，不碰 Qt，也没有共享可变状态，天然适合放线程里。

⚠️ 入参 ``doc`` 是**构造时的快照**（调用方先落盘再把文档交进来），worker 期间
用户又改版面不会写坏文件——最多是这一批略旧，下一批（防抖到期后再跑一轮）
会覆盖成最新。
"""

from __future__ import annotations

# ⚠️ QImage 在 QtGui 不在 QtCore——放错的话模块一被 import 就
# ImportError（护栏 2026-09-30 抓到过：双击空白预览一触发即崩）。
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage


class ImpositionComposeWorker(QObject):
    """把整份拼版文档落成一页一张的成品图（后台线程里跑）。"""

    #: (输出目录, 写出的页数)
    finished = Signal(str, int)
    failed = Signal(str)

    def __init__(self, doc: dict, out_dir):
        """doc 为拼版文档；out_dir 为目标目录（stages/imposition）。"""
        super().__init__()
        self.doc = doc
        self.out_dir = out_dir

    @Slot()
    def run(self) -> None:
        """合成全部拼版页；失败只报 failed，由宿主提示并落日志。"""
        try:
            from desktop.services.imposition import compose_doc

            written = compose_doc(self.doc, self.out_dir)
            self.finished.emit(str(self.out_dir), len(written))
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(str(exc))


class ImpositionPagePreviewWorker(QObject):
    """把**一页拼版**合成内存预览图（后台线程里跑，不落盘）。

    给画布双击空白处的「左右组合预览」弹窗用：``page`` 是构造时的**快照**，
    弹窗开着的时候用户继续拖版面不影响已经打开的这一张。信号口径与
    ``PreviewWorker`` 一致（``finished(int, QImage, str)`` / ``failed(int, str)``），
    ``ImageZoomDialog`` 的接线原样可用。
    """

    finished = Signal(int, QImage, str)
    failed = Signal(int, str)

    def __init__(self, page: dict, longest_edge: int = 1600):
        """``longest_edge`` 是预览密度上限；**传 0 = 不缩**（全分辨率，
        右键空白处「编辑图片」用：编辑器要的是与落盘成品同一分辨率的图）。
        """
        super().__init__()
        self.page = page
        self.longest_edge = int(longest_edge) or 0

    @Slot()
    def run(self) -> None:
        """PIL 合成（services.imposition.compose_page）→ QImage → 缩到边长。"""
        try:
            image = _compose_to_qimage(self.page, self.longest_edge)
            self.finished.emit(0, image, "imposition-preview")
        except Exception as exc:  # noqa: BLE001 - 兜底：别让线程静默死掉
            self.failed.emit(0, str(exc))


def _compose_to_qimage(page: dict, longest_edge: int) -> QImage:
    """一页拼版 → PIL 合成 → 按最长边缩 → QImage（深拷贝脱离源缓冲）。"""
    from PIL import Image

    from desktop.services.imposition import compose_page

    pil_image = compose_page(page).convert("RGBA")
    if longest_edge:
        pil_image.thumbnail((longest_edge, longest_edge), Image.Resampling.LANCZOS)
    raw = pil_image.tobytes("raw", "RGBA")
    image = QImage(
        raw, pil_image.width, pil_image.height,
        pil_image.width * 4, QImage.Format.Format_RGBA8888,
    )
    # tobytes 的缓冲随局部变量回收，必须 copy 一份 QImage 自己持有的
    return image.copy()
