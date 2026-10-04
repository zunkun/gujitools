# -*- coding: utf-8 -*-
"""独立任务页左栏的**缩略图源**：把「当前源的缩略图」统一喂给查看器。

用户 2026-10-03 的要求：「**所有独立任务左侧显示的都是缩略图**」。此前五个
独立任务页各写各的：图片提取页自己拿 ``PdfViewerWidget`` 渲 PDF 页缩略图，
detect/rembg/print 直接把**原图**塞进查看器（缩略图条每次现解码），
拼图页压根没有缩略图条。

本模块把这件事收成**一个混入**，各页只回答两个问题：

1. **源是什么** → :meth:`ThumbSourceMixin.show_pdf` 或 :meth:`show_images`；
2. **源换了/结果出来了** → 再调一次即可（同一个查看器，不重建控件）。

⚠️ **只管缩略图，不管右侧大图**：大图仍是各查看器自己的事（extract 未提取时
要从 PDF 按需渲高清页，见 :class:`~desktop.components.viewers.ImageViewerWidget`
的 ``page_renderer``）。这一层刻意不做「一个万能预览控件」——检测框编辑、
去底色对比、拼版画布三类左栏差异极大，硬合并只会得到一个谁都不合身的控件。

⚠️ **只写缓存，不碰产物**：输出目录仍由
:meth:`desktop.steps.spec.StepSpec.default_output` 决定。
"""

from __future__ import annotations

from pathlib import Path

from desktop.components.viewers.edit_sync import (
    apply_single_thumb,
    show_edited_image,
)
from desktop.utils.files import (
    THUMBNAIL_EDGE,
    extract_thumb_path,
    extract_thumbs_dir,
    image_thumb_cache_path,
    image_thumbs_dir,
    singletask_thumbnails_dir,
    thumb_map_path,
)


class ThumbSourceMixin:
    """让一个「持有 :class:`ImageViewerWidget` 的宿主」按源类型接上缩略图缓存。

    使用前提：宿主自身是 :class:`~desktop.workers.WorkerHost`（所有模块页都是，
    ``ModulePage`` 已 ``_init_worker_host()``），且有 ``self.SPEC`` 与
    ``self.viewer``。

    用法::

        class MyPage(StepModulePage, ThumbSourceMixin): ...
        # _on_source_changed 里：
        self.show_source(source)          # PDF 给路径，图片/目录给清单
        # 跑完之后：
        self.show_images(collect_result_images(out))
    """

    #: 缩略图最长边。取 :data:`desktop.utils.files.THUMBNAIL_EDGE`（256px），
    #: 与 PDF 页缩略图、任务导入缩略图**同一个值**——三套缓存同源同尺寸，
    #: 缩略图条的显示上限（``ThumbStrip.ICON_SIZE`` 长边 156）也就一致。
    THUMB_EDGE = THUMBNAIL_EDGE

    #: 当前 PDF 源的代际号。换书时递增，旧书那个还在跑的 worker 迟到信号按
    #: 代际丢弃——否则**旧书的页会画进新书的缩略图条**，metadata 还会用旧书
    #: 页数重建条目（与 ``PdfViewerWidget._thumb_gen`` 同一个坑）。
    _pdf_gen = 0

    #: 最近一次 ``show_pdf(numbered=True)`` 的书（extract 用）。提取完成后
    #: :meth:`show_numbered_images` 据此把产物缩略图写回**同一批文件**。
    _thumb_book: Path | None = None

    #: 本步骤是否用「序号口径」的缩略图。extract 置 True（产物序号 = 页号，
    #: 全步骤只留一份）；其余步骤置 False（源是一批图片，缩略图按图键命名）。
    NUMBERED_THUMBS = False

    # ------------------------------------------------------------------ 入口
    def show_source(self, source, paths=None) -> None:
        """按源的类型接上左栏缩略图。

        ``source`` 是这一步归一化后的源（``Path`` 或 ``None``）；``paths``
        给了就按图片清单处理（detect/rembg/print/拼图这类「源是一批图」的步骤
        直接把清单传进来，省得各页再各自判断一遍）。

        - 源是 **PDF** → 渲页缩略图到 ``singletask/<子任务>/thumbnails/<书>/``，
          条目标签「第 N 页」，大图由查看器按需渲高清页；
        - 源是**图片或目录** → 用 ``spec.listing`` 取清单，每张渲一张缓存小图，
          条目标签是文件名。
        """
        if source is None:
            self.viewer.set_images([])
            self._thumb_book = None
            return
        candidate = Path(source)
        if paths is None and candidate.suffix.lower() == ".pdf":
            self.show_pdf(candidate, numbered=self.NUMBERED_THUMBS)
            return
        images = list(paths) if paths is not None else self._listing(candidate)
        # ⚠️ 换成**非 PDF** 源（图片/目录）时清掉 ``_thumb_book``：否则上一次
        # 那本书的序号口径会继续生效，把这批图的缩略图写进别的书的目录。
        if paths is not None or not candidate.is_file():
            self._thumb_book = None
        self.show_images(images)

    def show_pdf(self, pdf: Path | str, numbered: bool = False) -> None:
        """源是 PDF：渲页缩略图并交给查看器（大图按需渲高清页）。

        ⚠️ 缓存目录**必须带书**（:func:`singletask_thumbnails_dir` 的第二个
        参数）：缩略图文件名是页号（``0001.jpg``…），共用目录会让 A 书第 1 页
        被当成 B 书第 1 页的命中缓存 ⇒ 翻出别本书的内容。

        ``numbered=True``（**extract 专用**，用户 2026-10-04「只保留一份、
        按序号处理」）：落到 ``thumbnails/<书>/<边长>/NNNN.jpg``——多一层
        ``<边长>/``，让**提取后按产物重渲写的是同一批文件**，从而全步骤只有
        一份缩略图。print 页渲的是它自己的产物 PDF，与提取序号无关，仍走
        旧路径（``numbered=False``）。
        """
        pdf = Path(pdf)
        self._pdf_gen += 1
        gen = self._pdf_gen
        cache_dir = (
            extract_thumbs_dir(self._subtask(), pdf, self.THUMB_EDGE)
            if numbered
            else singletask_thumbnails_dir(self._subtask(), pdf)
        )
        #: extract 记住「这本书」，提取后按序号重渲要写回同一个目录
        self._thumb_book = pdf if numbered else None
        self.viewer.set_pdf_source(pdf, cache_dir=cache_dir, gen=gen)
        self._watch_pdf_thumbs(pdf, cache_dir, gen)

    def show_images(self, images) -> None:
        """源是一批图片：清单进查看器，缩略图走 singletask 缓存。

        清单**仍然是真实图片路径**（不是缓存路径）：右侧大图、检测框按
        ``Path(path).stem`` 取键、放大弹窗的编辑回写，全都指着真实文件。
        缓存只喂左侧缩略图条（查看器的 ``thumb_provider``）。

        ⚠️ ``NUMBERED_THUMBS`` 的步骤（extract）走**序号口径**：缓存名是
        ``0001.jpg`` 而非图键，于是「未提取时的 PDF 页渲染」与「提取后的产物
        重渲」落在**同一批文件**上——全步骤只有一份缩略图（用户 2026-10-04）。
        序号取自产物文件名的数字部分（``pdf_extract`` 落盘名恒为
        ``f"{page_idx+1}.{ext}"``，见 ``utils/pdf_extract.py:254/317``），
        取不到就退回落回图键命名，绝不猜。
        """
        images = [Path(p) for p in images]
        if not images:
            self.viewer.set_images([])
            return
        book = self._thumb_book
        if self.NUMBERED_THUMBS and book is not None:
            names = [self._seq_of(p) for p in images]
            self.viewer.set_thumb_source(
                images,
                extract_thumbs_dir(self._subtask(), book, self.THUMB_EDGE),
                edge=self.THUMB_EDGE,
                names=names,
            )
            return
        self.viewer.set_thumb_source(
            images, self._thumb_cache_dir(), edge=self.THUMB_EDGE
        )

    def _seq_of(self, image: Path) -> str | None:
        """产物文件名里的序号 → 缓存文件名（``1.jpg`` → ``0001.jpg``）。

        ⚠️ **只认纯数字文件名**（``^\\d+$``）：``0003.png`` 可以，``cover.jpg``
        返回 None（交给调用方回落到图键命名）。宁可退回去多存一份，也不能把
        一个名字对错的图挂到别人的缩略图上（那正是本书各处反复踩的"张冠李戴"）。
        """
        stem = Path(image).stem
        if stem.isdigit():
            return f"{int(stem):04d}.jpg"
        return None

    # ------------------------------------------------- 编辑器覆盖图文件后的同步
    #
    # 用户 2026-10-03：「**独立步骤，图片也可以编辑生效**」。
    #
    # 独立任务页的查看器与任务流程共用一套编辑入口（放大弹窗 / 右键「编辑图片」
    # → ``ImageEditorDialog`` → 覆盖真实文件），但「覆盖之后界面怎么办」此前只有
    # 任务详情页做了（``TaskDetailPage._on_page_image_saved``）：独立页里改完，
    # 磁盘上的图确实变了，屏幕上的大图与缩略图却还是旧的——看着就是「编辑不生效」。
    #
    # 这里把那一半补齐，且**只补独立页该做的三件事**：立即上屏、重生成缩略图
    # 缓存、写一句「什么时候生效」。任务流程那套 sizes.json / 检测框基准同步
    # 属于任务语义，独立页没有，不在这里假装有。

    def _wire_source_edit(self) -> None:
        """把查看器的 ``image_saved`` 接到本页的「编辑生效」链上。

        由 :meth:`desktop.modules.base.StepModulePage.__init__` 在构造末尾调
        （那时 ``_build_preview`` 已跑过，``self.viewer`` 存在）。查看器只在
        编辑器「完成」且**真的覆盖了文件**之后发这个信号。
        """
        viewer = getattr(self, "viewer", None)
        signal = getattr(viewer, "image_saved", None)
        if signal is not None:
            signal.connect(self._on_source_image_saved)

    def _on_source_image_saved(self, path_text: str, image=None) -> None:
        """编辑器覆盖了某个图文件：立即上屏 → 重渲缩略图 → 记一句生效提示。"""
        path = Path(path_text)
        self._show_edited_image(path_text, image)
        self._reload_edited_thumb(path)
        note = self.edit_effect_note(path)
        if note:
            self.log(note)

    def _show_edited_image(self, path_text: str, image=None) -> None:
        """编辑结果**立刻**上屏（实现收在 :mod:`desktop.components.viewers.edit_sync`）。"""
        viewer = getattr(self, "viewer", None)
        if viewer is not None:
            show_edited_image(viewer, path_text, image)

    def edit_effect_note(self, path: Path) -> str:
        """编辑后日志里那句「**什么时候生效**」；各步骤按自己的下游覆盖。

        默认按"本步骤的源图被改了"写——重新执行本步骤就会读新图。产物形态
        不同的步骤（提取的结果图、去底色的结果文件）各自覆盖成准确的说法。
        """
        return f"已更新「{path.name}」，重新执行本步骤即用上这次修改。"

    def _reload_edited_thumb(self, path: Path) -> None:
        """后台按**新文件**重渲这张图的缓存缩略图，渲好只刷那一条。

        ⚠️ 不能省这一步：缓存文件名的键里带**大小**（``files.book_key``），
        编辑改了像素尺寸就换了文件名，而查看器记忆里那条旧路径指向的是
        **覆盖前**的缓存文件；只"立即上屏"不改缓存，翻页回来还是旧图
        （这正是用户报「独立步骤里编辑不生效」的现象）。

        ⚠️ 重渲交给 ``ImageThumbCacheWorker``：它自己会判「缓存比源图旧就重渲」，
        而源图刚被覆盖、mtime 必定更新，所以这里天然会重渲一次；它同时负责
        原子写盘与逐图算键，不另写一份。

        ⚠️ **必须与首次装载用同一个目标文件**，否则编辑后重渲会写到别处
        （序号口径下就是 ``0007.jpg`` 与 ``7-…-hash.jpg`` 分道扬镳，缩略图
        不更新）。所以这里复用 :meth:`_seq_of` / ``_thumb_cache_dir`` 同一份
        规则，而不是各算一遍——用户 2026-10-04 明确要求「后期编辑后能够同步
        缩略图」。
        """
        viewer = getattr(self, "viewer", None)
        if viewer is None:
            return
        from desktop.workers import ImageThumbCacheWorker, connect_queued

        text = str(path)
        edge = self.THUMB_EDGE
        cache_dir = self._edited_thumb_dir()
        names = self._edited_thumb_names([path])
        self.run_worker(
            lambda: ImageThumbCacheWorker(
                [path], cache_dir, edge=edge, names=names,
            ),
            lambda worker, thread: (
                connect_queued(
                    self, worker.thumbnail_ready,
                    lambda _index, image, cached, t=text: self._on_edited_thumb(
                        t, image, cached
                    ),
                    thread,
                ),
                worker.completed.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _edited_thumb_dir(self) -> Path:
        """编辑重渲的目标目录：与首次装载**同一个**（见 :meth:`show_images`）。"""
        book = self._thumb_book
        if self.NUMBERED_THUMBS and book is not None:
            return extract_thumbs_dir(self._subtask(), book, self.THUMB_EDGE)
        return self._thumb_cache_dir()

    def _edited_thumb_names(self, paths: list[Path]) -> list[str | None] | None:
        """编辑重渲的目标文件名：与首次装载同一份规则；无序号口径返回 None。"""
        book = self._thumb_book
        if not (self.NUMBERED_THUMBS and book is not None):
            return None
        return [self._seq_of(p) for p in paths]

    def _on_edited_thumb(self, path_text: str, image, cached: str) -> None:
        """重渲好的缩略图到位：把这一条换成新缓存小图（其余条目不动）。"""
        viewer = getattr(self, "viewer", None)
        if viewer is not None:
            apply_single_thumb(viewer, path_text, cached)

    # -------------------------------------------------------------- 内部实现
    def _listing(self, source: Path) -> list[Path]:
        """源是目录时取本步骤认的顶层图片（源是单张图片就是它自己）。"""
        spec = getattr(self, "SPEC", None)
        if spec is None:
            return []
        if source.is_file():
            return [source] if spec.accepts_path(source) else []
        return list(spec.listing(source))

    def _subtask(self) -> str:
        """缓存目录的「子任务」名：取 ``spec.disk_key()``（步骤路由键）。

        ⚠️ 刻意**不用** ``title`` / ``nav_title``：那是会改的显示文案，而这里
        是磁盘上已经存在的目录名（``singletask/<子任务>/``）。改标题会让用户
        攒下的缩略图缓存与手改件全部失联。
        """
        spec = getattr(self, "SPEC", None)
        return spec.disk_key() if spec else "singletask"

    def _thumb_cache_dir(self) -> Path:
        """一批图片的缩略图缓存**目录**（单图文件名由 worker 逐图算键）。

        目录只按「子任务 + 边长」分层，**不含单图键**——单图的文件名带大小与
        路径指纹（:func:`desktop.utils.files.image_thumb_cache_path`），拿它
        当目录名既会很长，也会让「同图改名」直接换目录、旧缓存全丢。

        规则本体在 :func:`desktop.utils.files.image_thumbs_dir`（拼图页、
        编辑回写后的重渲都取同一份），这里只是把它接到本步骤的子任务名上。
        """
        return image_thumbs_dir(self._subtask(), self.THUMB_EDGE)

    def _watch_pdf_thumbs(self, pdf: Path, cache_dir: Path, gen: int) -> None:
        """起一个 PDF 缩略图 pass（命中即复用，缺页现渲）。

        复用 ``PreviewWorker`` 的缩略图通道而不是另写一份 PyMuPDF 循环——
        那份实现里的单飞锁、按耗时让出 GIL、原子写、页边界可取消，每一条都是
        为「不让界面冻住」踩出来的（见其源码注释）。
        """
        from desktop.workers import PreviewWorker

        self.run_worker(
            lambda: PreviewWorker(
                pdf, thumbnails=True, cache_dir=cache_dir, render_missing=True,
            ),
            lambda worker, thread: (
                self._wire_pdf_thumbs(worker, thread, gen),
            ),
        )

    def _wire_pdf_thumbs(self, worker, thread, gen: int) -> None:
        """接住 PDF 缩略图 worker 的信号（**全部**经 ``connect_queued``）。"""
        from desktop.workers import connect_queued

        connect_queued(
            self, worker.metadata,
            lambda count, path: self._on_pdf_metadata(gen, count, path), thread,
        )
        connect_queued(
            self, worker.thumbnail_ready,
            lambda index, image: self.viewer.set_pdf_thumb(gen, index, image),
            thread,
        )
        connect_queued(
            self, worker.failed,
            lambda _page, message: self._on_pdf_thumb_failed(gen, message), thread,
        )
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)

    def _on_pdf_metadata(self, gen: int, count: int, path: str) -> None:
        """拿到页数：建缩略图条目（标签「第 N 页」）。"""
        if gen != self._pdf_gen:
            return  # 旧书的迟到 metadata：绝不能用它的页数重建新书的条目
        self.viewer.begin_pdf_pages(count, str(path))

    def _on_pdf_thumb_failed(self, gen: int, message: str) -> None:
        """PDF 缩略图 pass 失败：只写日志，不弹窗（PDF 本身可能仍能预览）。"""
        if gen != self._pdf_gen:
            return
        log = getattr(self, "log", None)
        if callable(log):
            log(f"PDF 缩略图生成失败：{message}")


__all__ = [
    "ThumbSourceMixin",
    "extract_thumb_path",
    "extract_thumbs_dir",
    "image_thumb_cache_path",
    "image_thumbs_dir",
    "thumb_map_path",
]
