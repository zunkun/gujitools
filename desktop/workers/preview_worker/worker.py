# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""``PreviewWorker``：整页大图 / 页缩略图（带磁盘缓存）的后台渲染 worker。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QImage, QImageReader

from desktop.utils.image_rotate import rotate_image
from desktop.utils.image_scaling import smooth_downscale
from desktop.utils.files import THUMBNAIL_EDGE, task_extract_pages_dir
from utils.file_utils import is_source_document, write_bytes_atomic

from .compose import compose_outputs_horizontal, compose_region_output
from .constants import THUMB_YIELD_RATIO
from .print_page import compose_print_page


class PreviewWorker(QObject):
    """渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。"""

    finished = Signal(int, QImage, str)
    metadata = Signal(int, str)
    thumbnail_ready = Signal(int, QImage)
    completed = Signal()
    failed = Signal(int, str)
    #: 请求在真正渲染前被判定为过期（用户已点了别的页），什么都没渲染。
    #: 宿主据此结束线程即可，不要当错误处理。
    skipped = Signal()

    def __init__(
        self,
        path: Path | str,
        page: int = 0,
        longest_edge: int | None = 1200,
        thumbnails: bool = False,
        cache_dir: Path | None = None,
        effect: dict | None = None,
        print_spec: dict | None = None,
        render_missing: bool = True,
        pages: list[int] | None = None,
    ):
        """构造预览渲染 worker。

        PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
        thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
        effect 为去底色合成参数 {boxes, border}，仅对单图生效。
        print_spec 为第四步「打印效果」参数
        {"args": print 参数, "index": 0-based 页序, "total": 总页数, "name": 文件名}，
        非空时把图片按 utils.page_layout 的几何排进一张纸（仅内存，不落盘）；
        另可给 "target_edge"：按该边长反推像素密度**重新排版**（标题/页码是
        重新绘制的，放到 4000px 依然锐利）。⚠️ 这个密度应当**高于屏幕需求**
        （超采样）——Qt 一次大比例缩小的质量明显差于分两档温和缩放，实测
        「合成 3000px」的锐度接近理论理想，而「合成 = 显示尺寸」反而最糊。
        密度的上限由 compose_print_page 夹住（不超过源图原生密度）。
        ⚠️ 给了 target_edge 时，longest_edge 应传 0（画布已按该密度合成，
        再缩一次纯粹白扔细节）。

        `render_missing=False`：**只读缓存，不渲染缺页**。给「另一个生产者
        正在填这个缓存目录」的场景用（导入后台任务在逐页写缩略图）——两边
        各跑一遍全量渲染等于把工作量翻倍，而且两个 PyMuPDF 循环会互相抢
        GIL，界面直接冻住（2026-09-25 实测）。
        `pages`：只处理这些页（None = 全部）；配合 render_missing=False 就是
        「只把我还没有的那几页从缓存里读出来」。
        """
        super().__init__()
        # ⚠️ 收成 Path：``run()`` 里要读 ``self.path.suffix`` 判定走 PDF 渲染
        # 还是图片解码，传字符串会在**子线程里**抛 AttributeError，只经 failed
        # 信号显示成「加载失败：'str' object has no attribute 'suffix'」
        # （用户 2026-10-03 报）。在这里收口，调用点传谁都安全。
        self.path = Path(path)
        self.page = page
        self.longest_edge = longest_edge
        self.thumbnail_edge = THUMBNAIL_EDGE
        self.thumbnails = thumbnails
        self.cache_dir = Path(cache_dir) if cache_dir else None
        # 去底色效果合成参数：{"boxes": [[x1,y1,x2,y2],...], "border": str|None}
        self.effect = effect
        self.print_spec = print_spec
        self.render_missing = render_missing
        self.pages = list(pages) if pages is not None else None
        #: 最近一次 PDF 单页渲染的 JPEG 字节（供宿主做页间缓存，见 _render_pdf_page）
        self.last_jpeg: bytes | None = None
        #: 宿主提供的"这条请求是否已过期"回调（如：用户已经点了别的页）。
        #: 过期的请求在拿到渲染锁后直接跳过、发 skipped——不渲染、不白烧
        #: 105ms 的 GIL。批量缩略图模式不用它。
        self.is_stale: Callable[[], bool] | None = None
        #: 收尾时置位：批量缩略图在**页边界**退出（见 cancel 与 _render_all_thumbnails）
        self._cancelled = False

    def cancel(self) -> None:
        """请求中止。

        批量缩略图（整本几百上千页）会在**下一页开头**退出——已经渲好的页都已
        落盘，重进会命中缓存，不会白干。单页渲染不可中断（一次 get_pixmap
        只有 ~160ms，等它一下比打断安全）。
        """
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        """按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。"""
        try:
            # PDF 与 DjVu 都按「按页渲染」处理（渲染服务内部分派到
            # PyMuPDF / djvu-rs）；图片文件仍旧直接解码。
            source_is_document = is_source_document(self.path)
            if source_is_document and self.thumbnails:
                self._render_all_thumbnails()
                return
            if source_is_document:
                image = self._render_pdf_page()
                if image is None:
                    return  # 过期请求：skipped 已发出
            else:
                image = self._load_image()
            self.finished.emit(self.page, image, str(self.path))
        except Exception as exc:
            self.failed.emit(self.page, str(exc))
            if self.thumbnails:
                self.completed.emit()

    def _render_pdf_page(self) -> QImage | None:
        """渲染单页大图；请求过期时发 skipped 并返回 None。

        ⚠️ **真正的渲染在子进程里做**（``pdf_render_service``）：``get_pixmap``
        整段持 GIL，扫描古籍常见内嵌格式是 JPX（JPEG2000，一页 4000×6000），
        渲一页要 ~850ms 且这 850ms 里 GUI 线程拿不到一次时间片——用户点缩略图
        那一下的"卡"就是它。出进程之后本线程只是在等 IPC，GUI 照常响应；
        进程内兜底那条路由服务内部持 ``single_flight`` 单飞锁（语义同旧实现）。

        ⚠️ ``longest_edge=0`` 的语义是「不缩放（要原始分辨率）」，服务侧同样
        按 0 处理——别在这里换算成 1.0，那会变成"渲成原始尺寸再缩"。
        """
        if self.is_stale is not None and self.is_stale():
            self.skipped.emit()
            return None
        from desktop.workers import pdf_render_service as svc

        jpeg = svc.render_jpeg(self.path, self.page, self.longest_edge, 80)
        self.metadata.emit(svc.page_count(self.path), str(self.path))
        if not jpeg:
            raise ValueError("渲染结果为空")
        # ⚠️ 顺手留一份 JPEG 字节：宿主（如 PDF 查看器）拿它做**页间缓存**，
        # 命中时只要 QImage.fromData（实测 25ms）而不是重渲。
        self.last_jpeg = jpeg
        return QImage.fromData(jpeg)

    def _render_all_thumbnails(self) -> None:
        """逐页取缩略图：**命中缓存就直接用**，缺页按 ``render_missing`` 决定渲不渲。

        ⚠️ 缺页的渲染同样**出进程**（``pdf_render_service``），而且**成批并行**
        提交：一页 JPX 缩略图要 ~700ms，逐页渲染时首屏十几张就是十几秒、期间
        界面还被 GIL 冻住。成批（每批 ``workers()*2`` 页）让 3 个子进程真并行，
        每批回来就立刻发信号，用户看到的是"缩略图一段一段地出现"。

        1. **别人正在填这个缓存目录时（render_missing=False）一页都不要渲**——
           原先两边各跑一遍全量渲染，工作量翻倍；
        2. 进程内兜底时按单页耗时成比例让出 GIL（出进程时一秒都不睡）。
        """
        import time

        from desktop.workers import pdf_render_service as svc

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(
                self.cache_dir / ".meta", str(self.thumbnail_edge).encode("utf-8")
            )
        page_count = svc.page_count(self.path)
        self.metadata.emit(page_count, str(self.path))
        order = list(self.pages) if self.pages is not None else list(range(page_count))

        # ---- 第一趟：命中缓存的直接发（不付渲染钱），缺页攒起来 ----
        pending: list[tuple[int, Path | None]] = []
        for page_number in order:
            if self._cancelled:
                # ⚠️ 没有这句时，整本缩略图渲染在收尾时只能"等它跑完"：
                # 几百上千页 × ~160ms/页，`shutdown_workers` 的 800ms 必然
                # 超时，线程被摘出父对象后还在后台干活（2026-09-26 审计）。
                # 在页边界退出即可——已经渲好的页都落盘了，重进会命中缓存。
                self.completed.emit()
                return
            if not (0 <= page_number < page_count):
                continue
            # 命名与导入缩略图一致：1 起始、四位补零（0001.jpg），自然排序
            cache_file = (
                self.cache_dir / f"{page_number + 1:04d}.jpg"
                if self.cache_dir
                else None
            )
            image = None
            if cache_file and cache_file.exists():
                image = QImage(str(cache_file))
            if image is not None and not image.isNull():
                self.thumbnail_ready.emit(page_number, image)
                continue
            if not self.render_missing:
                continue  # 只读通道：缺页交给正在填缓存的那个生产者
            pending.append((page_number, cache_file))

        # ---- 第二趟：缺页成批并行渲，**每张一落地就发信号**（不等整批）----
        chunk = max(1, svc.workers() * 3)
        for start in range(0, len(pending), chunk):
            if self._cancelled:
                break
            part = pending[start:start + chunk]
            targets = dict(part)
            started = time.perf_counter()

            def deliver(page_number: int, data: bytes) -> None:
                if not data:
                    return  # 这页没渲出来：跳过（与原实现一致）
                image = QImage.fromData(data)
                if image.isNull():
                    return
                cache_file = targets.get(page_number)
                if cache_file:
                    # 原子写：截断的缩略图会被 mtime 判据永久当成有效缓存
                    write_bytes_atomic(cache_file, data)
                self.thumbnail_ready.emit(page_number, image)

            svc.render_stream(
                self.path, [page for page, _f in part], self.thumbnail_edge, 70,
                on_page=deliver,
                # 已提取的页从产物 jpg 缩（21ms），不再解 JPX（~850ms）
                pages_dir=task_extract_pages_dir(self.path),
            )
            if not svc.offloaded():
                # 让出量与刚花掉的耗时成比例：GUI 拿到约 1/3 的时间片
                spent_ms = (time.perf_counter() - started) * 1000 / len(part)
                time.sleep(min(0.06, max(0.003, spent_ms * THUMB_YIELD_RATIO / 1000)))
        self.completed.emit()

    def _read_source_image(self) -> tuple[QImage, bool]:
        """读源图；纯展示（无 effect/print_spec）时**按目标边长直接解码**。

        返回 ``(图, 是否已缩到位)``：后者只表示"纯展示路径已经按
        ``longest_edge`` 解码过"，调用方据此跳过最后的 ``scaled()``——合成
        路径（effect / print_spec）的产物尺寸由几何决定，**仍然要**按
        ``longest_edge`` 缩放（打印预览在放大弹窗里就靠这一次放大）。

        ⚠️ ``QImage(str(path))`` 会先整张解码（实测 23MP 扫描件 ~240~250ms），
        再 ``scaled()`` 缩到预览尺寸；而目标边长最多 3000px，解码出来的像素
        九成以上立刻被扔掉——用户点缩略图后的等待主要就在这里。
        ``QImageReader.setScaledSize`` 让 JPEG 按 1/2、1/4、1/8 的尺度解码，
        实测快 2~3 倍。

        ⚠️ 有 ``effect``（检测框是**原始像素坐标**）或 ``print_spec``（几何按
        原图尺寸排版）时**不能缩**：合成必须按原分辨率做。
        """
        if not self.longest_edge or self.effect or self.print_spec:
            image = QImage(str(self.path))
            if image.isNull():
                raise ValueError("无法读取图片")
            return image, False
        reader = QImageReader(str(self.path))
        size = reader.size()
        pre_scaled = False
        if size.isValid() and max(size.width(), size.height()) > self.longest_edge:
            target = size.scaled(
                self.longest_edge,
                self.longest_edge,
                Qt.AspectRatioMode.KeepAspectRatio,
            )
            reader.setScaledSize(target)
            pre_scaled = True
        image = reader.read()
        if image.isNull():
            raise ValueError("无法读取图片")
        return image, pre_scaled

    def _load_image(self) -> QImage:
        image, pre_scaled = self._read_source_image()
        if self.effect:
            outputs = compose_region_output(
                image,
                self.effect.get("boxes", []),
                self.effect.get("border"),
                dpi=int(self.effect.get("dpi", 300)),
            )
            image = compose_outputs_horizontal(outputs)
        if self.print_spec:
            # 打印效果：几何由 utils.page_layout 计算（PDF 生成也是同一份）
            from utils.page_layout import (
                fit_rotated_rect, normalize_page_rotation, plan_print_page,
                rotated_bbox_size,
            )

            # 逐图旋转（度，顺时针为正）：先在位图上按外接框转好，再按**旋转
            # 后**的外接框尺寸排版，并把旋转后的图等比放进同一个用户框——与
            # PDF 侧「PIL 旋转 + page_rotations」同一口径，预览与成品才不会
            # 一个横一个竖、也不会被拉伸变形。
            angle = normalize_page_rotation(self.print_spec.get("rotate"))
            source_size = (image.width(), image.height())
            size = source_size
            image_rect = self.print_spec.get("rect")
            if angle:
                image = rotate_image(image, angle)
                size = rotated_bbox_size(source_size[0], source_size[1], angle)
                if image_rect is not None:
                    image_rect = fit_rotated_rect(image_rect, source_size, angle)
            plan = plan_print_page(
                size,
                self.print_spec.get("args") or {},
                int(self.print_spec.get("index", 0)),
                int(self.print_spec.get("total", 1)),
                image_name=self.print_spec.get("name"),
                image_rect=image_rect,
                # 节点由 GUI 侧按完整条目清单解析好（print_spec["nodes"]）：
                # 这里拿不到清单，走 plan 内部兜底的话节点永远匹配不上
                # （「添加动态节点预览不生效」的根因，2026-09-29）。
                sorted_nodes=self.print_spec.get("nodes"),
            )
            # target_edge（放大弹窗用）：按目标边长**反推像素密度**重新排版。
            # ⚠️ 不能只把 compose_print_page 的产物放大了事——它内部固定按
            # preview_px_per_mm（目标 1600px 长边）合成，放大只会糊；按密度
            # 重排则标题/页码是**重新绘制**的，放到 4000px 依然锐利。
            density = None
            target_edge = self.print_spec.get("target_edge")
            if target_edge:
                longest_mm = max(plan.page_w_mm, plan.page_h_mm)
                if longest_mm > 0:
                    density = float(target_edge) / longest_mm
            image = compose_print_page(image, plan, density)
        if not self.longest_edge:
            return image  # 不缩放：调用方需要原始分辨率
        if pre_scaled:
            return image  # 上面已按目标边长解码到位，再缩一次纯属白算
        if max(image.width(), image.height()) > self.longest_edge:
            # 合成路径（effect/print_spec）的产物是原始像素：分档降采样，
            # 一次缩到显示尺寸会跳采样（细笔画发虚）。
            return smooth_downscale(image, self.longest_edge)
        # 比请求边长还小：沿用原语义（放大到请求边长），只有一次平滑放大
        return image.scaled(
            self.longest_edge,
            self.longest_edge,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
