# -*- coding: utf-8 -*-
"""「离开就释放」自测：切走步骤/切走页面时释放预览位图，回来能重装。

用户 2026-11-21：

> 離開拼版頁面就釋放，其他步驟也一樣，離開邊釋放
> 檢查所有步驟會不會在切換頁面或者操作的時候內存越來越大

背景：预览区的 QPixmap 是"解码一次就存着"的——大图一张几十 MB、左列
每页一张缩略图。步骤与模块页都是**常驻实例**（切走不销毁），这些位图
此前会一直留在内存里，一本古书翻几遍就是几百 MB。

契约（两侧对称，缺一边就是"回来一片空白"）：

1. ``ThumbStrip.release_icons`` 换回共享占位图，**不动条目高度/当前行**；
2. ``ImageView.clear_image`` 连降采样底图 ``_scaled_base`` 一起丢；
3. 各预览控件 ``release_buffers`` 后大图与条目图标归零、清单与当前页保留；
4. ``restore_buffers``（或 ``set_images`` 的释放标记）能把它们装回来；
5. 拼版：「离开」清画布 + 左列缩略图 + 管理者 ``_pix``；回来画布与左列都回来；
6. 任务详情页：``_select_stage`` **切走时**调 ``release_stage_buffers(旧步骤)``，
   ``_refresh_preview`` 进入时调 ``restore_buffers``（能力探测到哪一个）；
7. 模块页：``release_buffers`` 置标记，``showEvent`` 只在标记为真时才重装
   （首次显示不做无谓刷新）。
"""

from __future__ import annotations

from pathlib import Path

NAME = "memory_release"
DEPENDS: list[str] = []
TITLE = "离开步骤/页面释放预览位图（回来能重装）"


def _png(path: Path, color: str, size=(400, 600)) -> Path:
    from PySide6.QtGui import QColor, QImage

    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path)), f"存图失败：{path}"
    return path


def _icons_not_placeholder(strip) -> int:
    """条目里**不是**占位图的图标数（按 cacheKey 判，QIcon 不能 is 比较）。"""
    key = strip._placeholder.cacheKey()
    return sum(
        1 for row in range(strip.count())
        if strip.item(row).icon().cacheKey() != key
    )


def run(ctx) -> None:
    from tests.selftests._context import ok, pump

    app = ctx.app
    work = Path(ctx.tmp) / "memory_release"
    work.mkdir(parents=True, exist_ok=True)
    a = _png(work / "a.png", "#ffffff")
    b = _png(work / "b.png", "#202020")

    _check_strip(app, ok, pump, a, b)
    _check_image_view(app, ok, pump, a)
    _check_viewer_roundtrip(app, ok, pump, a, b)
    _check_rembg_roundtrip(app, ok, pump, a, b)
    _check_imposition_view(app, ok, pump, work, a, b)
    _check_thumb_manager(ok)
    _check_detail_page_dispatch(ctx, ok)
    _check_module_page(app, ok, pump, a, b)


# ---------------------------------------------------------------- 1. 缩略图条
def _check_strip(app, ok, pump, a: Path, b: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from desktop.components.viewers.thumb_strip import ThumbStrip
    from desktop.workers import PreviewWorker

    strip = ThumbStrip()
    strip.resize(160, 600)
    strip.show()
    strip.add_page_item("第 1 页", str(a))
    strip.add_page_item("第 2 页", str(b))
    for index, path in enumerate((a, b)):
        worker = PreviewWorker(path, longest_edge=96)
        images: list = []
        worker.finished.connect(lambda _p, image, _s, box=images: box.append(image))
        worker.run()
        strip.set_item_icon(index, images[0], str(path), f"第 {index + 1} 页")
    pump(app, 20)

    ok("缩略图条：装好后两条都是真图", _icons_not_placeholder(strip) == 2)
    heights = [strip.item(r).sizeHint().height() for r in range(strip.count())]
    strip.setCurrentRow(1)
    strip.release_icons()
    ok("缩略图条：release_icons 后全部退回占位图",
       _icons_not_placeholder(strip) == 0,
       f"残留={_icons_not_placeholder(strip)}")
    ok("缩略图条：释放不动条目高度（回来不会整列重新长高）",
       [strip.item(r).sizeHint().height() for r in range(strip.count())] == heights)
    ok("缩略图条：释放不动当前行", strip.currentRow() == 1)
    del QApplication


# ------------------------------------------------------------ 2. 大图缩放缓存
def _check_image_view(app, ok, pump, a: Path) -> None:
    from PySide6.QtGui import QImage

    from desktop.components.viewers.image_view import ImageView

    view = ImageView("无预览")
    view.resize(600, 500)
    view.show()
    image = QImage(str(a))
    view.set_image(image)
    pump(app, 5)
    ok("大图画布：set_image 后缓存的降采样底图已在",
       view._scaled_base is not None, "没建底图（控件没布局？）")
    view.clear_image("")
    ok("大图画布：clear_image 连降采样底图一起丢",
       view._pixmap is None and view._scaled_base is None)


# ------------------------------------------------------- 3/4. 两个预览控件往返
def _check_viewer_roundtrip(app, ok, pump, a: Path, b: Path) -> None:
    from desktop.components.viewers import ImageViewerWidget

    viewer = ImageViewerWidget()
    viewer.resize(900, 700)
    viewer.show()
    viewer.set_images([a, b])
    pump(app, 40)
    ok("图片预览：装好有大图 + 两条真图标",
       viewer.view.has_image and _icons_not_placeholder(viewer.strip) == 2)

    paths_before = list(viewer.paths)
    row_before = viewer.strip.currentRow()
    viewer.release_buffers()
    pump(app, 5)
    ok("图片预览：release 后大图与图标全清",
       not viewer.view.has_image and _icons_not_placeholder(viewer.strip) == 0)
    ok("图片预览：release 不动清单与当前行",
       list(viewer.paths) == paths_before and viewer.strip.currentRow() == row_before)

    viewer.restore_buffers()
    pump(app, 40)
    ok("图片预览：restore 后大图与图标都回来",
       viewer.view.has_image and _icons_not_placeholder(viewer.strip) == 2)

    # set_images 路径也要认释放标记：清单没变也得重装（不然宿主走这条路就空白）
    viewer.release_buffers()
    viewer.set_images([a, b])
    pump(app, 40)
    ok("图片预览：释放后 set_images（清单未变）也会重装",
       viewer.view.has_image and _icons_not_placeholder(viewer.strip) == 2)
    viewer.close()


def _check_rembg_roundtrip(app, ok, pump, a: Path, b: Path) -> None:
    from desktop.components.viewers import RembgPreviewWidget

    rembg = RembgPreviewWidget(image_editable=False)
    rembg.resize(900, 700)
    rembg.show()
    rembg.set_images([a, b], None)
    pump(app, 40)
    ok("去底色预览：装好有大图 + 两条真图标",
       rembg.view.has_image and _icons_not_placeholder(rembg.strip) == 2)
    rembg.release_buffers()
    pump(app, 5)
    ok("去底色预览：release 后大图与图标全清",
       not rembg.view.has_image and _icons_not_placeholder(rembg.strip) == 0)
    rembg.restore_buffers()
    pump(app, 40)
    ok("去底色预览：restore 后大图与图标都回来",
       rembg.view.has_image and _icons_not_placeholder(rembg.strip) == 2)
    rembg.close()


# ------------------------------------------------------------------ 5. 拼版
def _check_imposition_view(app, ok, pump, work: Path, a: Path, b: Path) -> None:
    from PySide6.QtGui import QImage

    from desktop.components.imposition import ImpositionViewWidget
    from desktop.services.imposition import make_single_page

    view = ImpositionViewWidget()
    view.resize(1000, 700)
    view.show()
    pages = [dict(make_single_page(a)), dict(make_single_page(b))]
    view.set_pages(pages, current=0)
    pump(app, 10)
    thumbs = [
        QImage(str(_png(work / f"thumb{index}.png", "#888888", size=(120, 90))))
        for index in range(len(pages))
    ]
    view.set_page_thumbs(thumbs)
    pump(app, 10)

    def shown_thumbs() -> int:
        return sum(
            1 for entry in view.page_list.entries()
            if entry.thumb.pixmap() is not None and not entry.thumb.pixmap().isNull()
        )

    ok("拼版视图：装好后画布有版面、左列有图",
       len(view.canvas.items()) > 0 and shown_thumbs() > 0,
       f"画布={len(view.canvas.items())} 左列={shown_thumbs()}")
    view.release_buffers()
    pump(app, 5)
    ok("拼版视图：release 后画布清空、左列缩略图全清",
       len(view.canvas.items()) == 0 and shown_thumbs() == 0)
    ok("拼版视图：release 不动页清单", len(view.pages()) == len(pages))

    view.set_pages(pages, current=0)
    view.set_page_thumbs(thumbs)
    pump(app, 10)
    ok("拼版视图：回来重灌后画布与左列都回来",
       len(view.canvas.items()) > 0 and shown_thumbs() > 0)
    view.close()


def _check_thumb_manager(ok) -> None:
    from PySide6.QtGui import QPixmap

    from desktop.components.imposition.page_thumb import PageThumbManager

    manager = PageThumbManager(Path("."), 96, lambda *_a, **_k: None)
    manager._mapping = {0: "sig-0", 1: "sig-1"}
    manager._pix = {"sig-0": QPixmap(10, 10), "sig-1": QPixmap(10, 10)}
    manager.release_pixmaps()
    ok("缩略图管理者：release_pixmaps 只清位图，映射与排队保持",
       not manager._pix and manager._mapping == {0: "sig-0", 1: "sig-1"})


# ------------------------------------------------------------ 6. 详情页分发
def _check_detail_page_dispatch(ctx, ok) -> None:
    from desktop.pages.taskdetail.page import TaskDetailPage

    page = TaskDetailPage(ctx.repo)
    calls: list[str] = []

    class _Stub:
        def __init__(self, name: str) -> None:
            self._name = name

        def release_buffers(self) -> None:
            calls.append(self._name)

        def restore_buffers(self) -> None:
            calls.append("restore:" + self._name)

    page.detect_viewer = _Stub("detect")          # type: ignore[assignment]
    page.rembg_viewer = _Stub("rembg")            # type: ignore[assignment]
    page.print_preview = _Stub("print")           # type: ignore[assignment]
    page.extract_result_viewer = _Stub("extract")  # type: ignore[assignment]
    page.imposition_view = _Stub("imposition")    # type: ignore[assignment]

    page.release_stage_buffers("detect")
    ok("详情页：按步骤释放只动那一步",
       calls == ["detect"], f"实际={calls}")
    calls.clear()
    page.release_stage_buffers()
    ok("详情页：不传参释放全部五个预览区",
       sorted(calls) == sorted(["extract", "detect", "rembg", "print", "imposition"]),
       f"实际={calls}")
    calls.clear()
    page._restore_stage_buffers("rembg")
    ok("详情页：进入某步时按 stage 找到它并调 restore",
       calls == ["restore:rembg"], f"实际={calls}")


# -------------------------------------------------------------- 7. 模块页
def _check_module_page(app, ok, pump, a: Path, b: Path) -> None:
    from desktop.modules.imposition.page import ImpositionModulePage
    from desktop.services.imposition import make_single_page

    page = ImpositionModulePage()
    page.resize(1100, 780)
    page.show()
    page._set_sources([a, b])
    page._doc["pages"] = [dict(make_single_page(a)), dict(make_single_page(b))]
    page._refresh_view()
    page.view.set_current(0)
    pump(app, 40)

    def shown() -> tuple[int, int]:
        thumbs = sum(
            1 for entry in page.view.page_list.entries()
            if entry.thumb.pixmap() is not None
            and not entry.thumb.pixmap().isNull()
        )
        manager = getattr(page, "_page_thumb_mgr", None)
        return thumbs, len(getattr(manager, "_pix", {}) or {})

    thumbs_before, pix_before = shown()
    ok("模块页：装好后左列有图、管理者也有位图",
       thumbs_before > 0 and pix_before > 0, f"左列={thumbs_before} pix={pix_before}")
    ok("模块页：刚构造/首次显示不算'已释放'", page._buffers_released is False)

    page.release_buffers()
    pump(app, 5)
    thumbs_after, pix_after = shown()
    ok("模块页：release 后左列与管理者位图全清、标记置真",
       thumbs_after == 0 and pix_after == 0 and page._buffers_released is True,
       f"左列={thumbs_after} pix={pix_after} 标记={page._buffers_released}")

    page.restore_buffers()
    pump(app, 40)
    thumbs_back, pix_back = shown()
    ok("模块页：restore 后左列与管理者位图都回来",
       thumbs_back > 0 and pix_back > 0 and len(page.view.canvas.items()) > 0,
       f"左列={thumbs_back} pix={pix_back}")
    page.close()
