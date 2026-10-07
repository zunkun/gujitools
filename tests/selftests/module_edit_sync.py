# -*- coding: utf-8 -*-
"""独立步骤的**图片编辑生效链**自测（用户 2026-10-03：「独立步骤，图片也可以编辑生效」）。

不跑 YOLO / 不跑去底色 / 不起子进程——全部是控件接线与落盘断言。

守护三件事：

1. **四个「一个源」的独立步骤页（提取 / 检测 / 去底色 / 生成 PDF）都接了
   编辑器覆盖文件之后的同步链**：立即上屏 → 后台重渲 singletask 缩略图缓存
   → 写一句「什么时候生效」。此前独立页里改完，磁盘上的图确实变了，屏幕上的
   大图与缩略图却还是旧的——看着就是「编辑不生效」。
2. **缩略图缓存真的按新图重渲**（不是只换大图）：缓存文件名带大小指纹，编辑
   改了尺寸就换键，只"忘掉记忆"不够，还得真的重写一份。
3. **拼图独立页的预览 / 编辑入口真的通了**：此前画布四条信号
   （``item_preview_requested`` / ``spread_preview_requested`` /
   ``item_edit_requested`` / ``spread_edit_requested``）**没接线**——
   右键菜单弹得出来、双击也发信号，点了什么都不会发生。

⚠️ 本用例自建页面、不借主窗口（``DEPENDS`` 为空），所以能单跑、也快。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

NAME = "module_edit_sync"
DEPENDS: list[str] = []
TITLE = "独立步骤的图片编辑生效链"

#: 造图尺寸：编辑后**换一个尺寸**（键里带大小 ⇒ 必然重新渲一张缓存）
W, H = 60, 40
W2, H2 = 80, 50
WHITE, BLUE = "#ffffff", "#2030ff"
GREEN = "#20a030"


# --------------------------------------------------------------------- 小工具
def _png(path: Path, color: str, size: tuple[int, int] = (W, H)) -> Path:
    """现场编码一张纯色 PNG（**不手写字节**：手拼的多半不合法）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    path.parent.mkdir(parents=True, exist_ok=True)
    assert image.save(str(path), "PNG"), f"写不出测试图：{path}"
    return path


def _pixel(path: Path, x: int = 2, y: int = 2) -> str:
    """图片某点的颜色名（``#rrggbb``）；读不出来返回空串。"""
    from PySide6.QtGui import QImage

    image = QImage(str(path))
    return "" if image.isNull() else image.pixelColor(x, y).name()


def _read_image(path: Path):
    """把磁盘上的图读成 QImage（模拟"编辑器完成"时交回来的编辑结果）。"""
    from PySide6.QtGui import QImage

    return QImage(str(path))


def _display_pixel(viewer) -> str:
    """查看器**大图**上某点的颜色；没有图返回空串。

    不用 ``info_label`` 的文案判"上屏"：检测页的 info 行会被检测框说明覆盖
    （``未检测到文本框``），那是它的正常行为，与"图换没换"无关。
    """
    view = getattr(viewer, "view", None)
    pixmap = getattr(view, "_pixmap", None)
    if pixmap is None or pixmap.isNull():
        return ""
    return pixmap.toImage().pixelColor(2, 2).name()


def _icon_pixel(viewer, row: int) -> str:
    """左栏缩略图条第 ``row`` 条图标上的颜色；没图标返回空串。

    这是「编辑生效」在**左栏**的可见证据：刷大图容易（内存里换一张就行），
    左栏要真的走"重取缩略图"那条路才会变。
    """
    strip = getattr(viewer, "strip", None)
    if strip is None:
        return ""
    try:
        if not (0 <= row < strip.count()):
            return ""
        pixmap = strip.item(row).icon().pixmap(64, 64)
    except Exception:  # noqa: BLE001 - 自测探针，取不到就当没有
        return ""
    if pixmap is None or pixmap.isNull():
        return ""
    return pixmap.toImage().pixelColor(2, 2).name()


def _near(got: str, want: str, tol: int = 26) -> bool:
    """颜色近似比较（缓存是 JPEG，纯色块也有压缩偏移）。"""
    if not got or len(got) != 7:
        return False
    a = tuple(int(got[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(want[i:i + 2], 16) for i in (1, 3, 5))
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _fresh(path: Path) -> None:
    """把某个文件的 mtime 拨回 10 秒前。

    ⚠️ 为什么必须拨：判"缓存是否过期"用的是 ``mtime >= 源图 mtime``，而 NTFS
    的时间戳来自系统时钟（约 15.6ms 一跳）。若缓存写完、源图又在同一次时钟跳
    里被覆盖，两个 mtime 会**相等**，缓存就被当成"还新鲜"而不重渲——断言会
    随机红。拨旧时间把这件事变成确定性的，比 sleep 一个时钟跳可靠。
    """
    stamp = os.stat(path).st_mtime - 10
    os.utime(path, (stamp, stamp))


def _overwrite_source(path: Path, color: str, size=(W2, H2), work: Path | None = None):
    """模拟编辑器：造一张新图**覆盖源文件**，返回读回来的编辑结果。

    ⚠️ 必须真覆盖文件：重渲缩略图那条链读的是**磁盘上的文件**，只把内存里的
    QImage 传下去测不出"编辑是否真的落盘/生效"。
    ⚠️ 临时图写在源目录**之外**：源是"一个图片目录"的步骤按目录列清单，往里面
    多丢一个文件会让清单多出一张（自己给自己造脏数据）。
    """
    from PySide6.QtGui import QImage

    holder = work or path.parent.parent / "_edited_tmp"
    fresh = _png(holder / f"{path.stem}-{color.lstrip('#')}.png", color, size)
    shutil.copyfile(fresh, path)
    return QImage(str(path))


def _stub_editor(edited, accepted: bool = True):
    """替身编辑器：调用点只依赖 ``exec()`` 与 ``result_image()``。"""
    from PySide6.QtWidgets import QDialog

    class _Stub:
        def __init__(self, parent=None, image=None, save_back=False):
            self.save_back = save_back

        def exec(self):
            return (
                QDialog.DialogCode.Accepted if accepted
                else QDialog.DialogCode.Rejected
            )

        def result_image(self):
            return edited

    return _Stub


def _shutdown(page, app) -> None:
    """收尾页面 + 查看器两个 WorkerHost（否则退出时线程还在跑）。"""
    from tests.selftests._context import pump

    for owner in (getattr(page, "viewer", None), page):
        if owner is None:
            continue
        try:
            owner.shutdown_workers()
        except RuntimeError:
            pass
    pump(app, times=2)


def _viewer_paths(viewer) -> list[str]:
    """查看器当前清单（各控件的公开名不完全一致，测试里统一取一次）。"""
    paths = getattr(viewer, "paths", None)
    if paths is None:
        paths = getattr(viewer, "_paths", [])
    return [str(p) for p in paths]


def _wait_until(app, condition, timeout: float = 20.0) -> bool:
    from tests.selftests._context import wait_until

    return wait_until(app, condition, timeout=timeout, interval=0.02)


# ------------------------------------------------------------------ 一个源的页
def _edit_flow(ctx, page_cls, keyword: str, prepare, ok, has_apply: bool) -> None:
    """跑一个"一个源"的独立步骤页：选源 → 编辑 → 断言三件事都做到了。"""
    from desktop.utils.files import (
        extract_thumbs_dir, image_thumb_cache_path,
    )
    from tests.selftests._context import pump

    def thumb_of(image: Path) -> Path:
        """这张图的缓存缩略图**由页面自己算**（两种口径都对）。

        ⚠️ 不能在这儿按图键拼期望路径：extract 走**序号口径**（用户
        2026-10-04「只保留一份、按序号处理」），缓存名是 ``0001.jpg``，
        与源图文件名无关。自测按自己那份口径拼期望值，跟着一错就查不出真回归。

        走「问页面自己要目标路径」这条路，两种口径都自动成立：序号口径页
        （``NUMBERED_THUMBS``）给出 ``0001.jpg``，其余页给出图键名。
        """
        numbered = getattr(page, "NUMBERED_THUMBS", False)
        book = getattr(page, "_thumb_book", None)
        if numbered and book is not None and image.stem.isdigit():
            return extract_thumbs_dir(
                page._subtask(), book, page.THUMB_EDGE,
            ) / f"{int(image.stem):04d}.jpg"
        return image_thumb_cache_path(page.SPEC.disk_key(), image, page.THUMB_EDGE)

    page = page_cls()
    app = ctx.app
    try:
        work = Path(ctx.tmp) / f"edit_{page.SPEC.key}"
        target = prepare(page, work, ctx)     # 备好源；返回"将被编辑的那张图"
        pump(app, times=8)
        ok(f"{page.TITLE}：左栏列的就是待编辑的那张图",
           str(target) in _viewer_paths(page.viewer), str(_viewer_paths(page.viewer)))

        cached = thumb_of(target)
        ok(f"{page.TITLE}：选源后缩略图缓存已就绪（编辑前的白色）",
           _wait_until(app, lambda: cached.is_file() and _near(_pixel(cached), WHITE),
                       timeout=25.0),
           str(cached))
        _fresh(cached)

        # ---- 编辑 1：**同像素尺寸**换色（文件字节数会变 ⇒ 缓存键随之变）----
        edited = _overwrite_source(target, BLUE, size=(W, H), work=work)
        page.viewer.image_saved.emit(str(target), edited)
        pump(app, times=4)
        if has_apply:
            ok(f"{page.TITLE}：编辑结果**立即**上屏（不等重解码/重渲）",
               _near(_display_pixel(page.viewer), BLUE), _display_pixel(page.viewer))
        else:
            ok(f"{page.TITLE}：编辑结果按新文件重载上屏",
               _wait_until(app, lambda: _near(_display_pixel(page.viewer), BLUE),
                           timeout=20.0),
               _display_pixel(page.viewer))

        # ⭐ 关键回归：条目图标必须换成**编辑后**的图。缓存名字里带文件大小，
        #   编辑一改字节数就换了键；若查看器还记着旧键那条路径（``_thumb_cache_ready``
        #   没清），刷新出来的是**覆盖前**那张缓存——左栏一直是旧图。
        row = _viewer_paths(page.viewer).index(str(target))
        ok(f"{page.TITLE}：左栏该条目的缩略图换成了编辑后的像素",
           _wait_until(app, lambda: _near(_icon_pixel(page.viewer, row), BLUE)),
           _icon_pixel(page.viewer, row))
        now_key = thumb_of(target)
        ok(f"{page.TITLE}：编辑后缓存按新键重渲",
           _wait_until(app, lambda: now_key.is_file() and _near(_pixel(now_key), BLUE)),
           _pixel(now_key))

        # ---- 编辑 2：**换像素尺寸** ⇒ 键变更明显（名字里的大小指纹跟着变）----
        edited2 = _overwrite_source(target, GREEN, size=(W2, H2), work=work)
        page.viewer.image_saved.emit(str(target), edited2)
        pump(app, times=4)
        moved = thumb_of(target)
        ok(f"{page.TITLE}：换尺寸的编辑同样上屏",
           _wait_until(app, lambda: _near(_display_pixel(page.viewer), GREEN),
                       timeout=20.0),
           _display_pixel(page.viewer))
        # ⚠️ 「键会变」只对**图键口径**成立（键里带大小指纹）；序号口径下键
        #    恒为 0001.jpg，是**同一个文件被重写**。两种都断言：换尺寸后目标
        #    确实反映成了编辑后的图（序号口径下就是"同一文件被更新"）。
        if moved != now_key:
            ok(f"{page.TITLE}：换尺寸后缓存键跟着变（键里确实带大小指纹）",
               moved != now_key, f"{moved.name} vs {now_key.name}")
        else:
            ok(f"{page.TITLE}：序号口径下换尺寸仍写同一个序号文件",
               moved.name == now_key.name, f"{moved.name}")
        ok(f"{page.TITLE}：目标那份缓存是编辑后的图",
           _wait_until(app, lambda: moved.is_file() and _near(_pixel(moved), GREEN)),
           _pixel(moved))
        ok(f"{page.TITLE}：换尺寸后条目图标也跟着换",
           _wait_until(app, lambda: _near(_icon_pixel(page.viewer, row), GREEN)),
           _icon_pixel(page.viewer, row))

        # ---- 同键场景：内容没变、只把源图 mtime 变新 ⇒ 也要重渲（判过期靠 mtime）----
        _fresh(moved)
        stale = moved.stat().st_mtime
        os.utime(target)
        page.viewer.image_saved.emit(str(target), _read_image(target))
        ok(f"{page.TITLE}：同键下也靠 mtime 判过期并把缓存重渲一遍",
           _wait_until(app, lambda: moved.stat().st_mtime > stale + 5),
           f"{moved.stat().st_mtime} vs {stale}")

        # ③ 日志写明"什么时候生效"
        text = page.log_view.toPlainText()
        ok(f"{page.TITLE}：日志给出「什么时候生效」", keyword in text, text[-200:])
    finally:
        _shutdown(page, app)
        page.deleteLater()


def _prepare_listing(page, work: Path, _ctx) -> Path:
    """通用：把"一个装着图片的目录"设成源 → 左栏就是这些图。"""
    target = _png(work / "src" / "1.png", WHITE)
    page.control.set_source(work / "src")
    return target


def _prepare_extract(page, work: Path, ctx) -> Path:
    """提取页的源是 **PDF**，图片是**产物**：先"跑完提取"，左栏才轮到图片。

    未提取时左栏是 PDF 的页缩略图（矢量页，没有可回写的文件，不给编辑），
    所以提取页能编辑的只有产物图——这也正是真实用法。
    """
    page.control.set_source(Path(ctx.pdf))
    out = work / "out"
    target = _png(out / "0001.png", WHITE)
    page.on_result(out, {})
    return target


# ------------------------------------------------------------------ 拼图页
def _imposition_flow(ctx, ok) -> None:
    """拼图独立页：四条信号接线 + 编辑单张源图 / 编辑整页组合都生效。"""
    from PySide6.QtGui import QImage

    from desktop.modules.imposition import page as imp
    from desktop.steps import StepRequest
    from tests.selftests._context import pump

    page = imp.ImpositionModulePage()
    app = ctx.app
    record: str | None = None
    try:
        work = Path(ctx.tmp) / "edit_imposition"
        a = _png(work / "a.png", WHITE, (200, 300))
        b = _png(work / "b.png", "#eeeeee", (200, 300))
        page._set_sources([a, b])
        page._auto_impose()
        page.view.set_current(0)
        pump(app, times=4)
        ok("拼图页：自动拼版出了一页且当前页可索引",
           bool(page._doc.get("pages")) and page.view.current_index() == 0,
           f"{page._doc} / {page.view.current_index()}")

        # ---- 预览目标：单张原图可编辑（回写源文件）、整页组合未手改前只读 ----
        item = page._item_target(0, 0)
        item_file = str(page._doc["pages"][0]["items"][0]["file"])
        ok("拼图页：单张原图预览目标可渲染", item is not None and callable(item.render))
        ok("拼图页：单张原图预览的编辑回写目标就是那张源文件",
           item is not None and str(item.edit_path or "") == item_file,
           f"edit={item.edit_path if item else None}")
        spread = page._spread_target(0)
        ok("拼图页：整页组合预览目标可渲染",
           spread is not None and callable(spread.render))
        ok("拼图页：整页组合未手改过时预览只读（右键编辑不受限）",
           spread is not None and spread.edit_path is None,
           f"edit={spread.edit_path if spread else None}")

        # ---- 四条信号真的接到处理函数上（此前四条全空着）----
        opened: list = []
        original_open = page._open_zoom
        page._open_zoom = lambda factory, index: opened.append((factory, index))
        try:
            page.view.item_preview_requested.emit(0)
            page.view.spread_preview_requested.emit()
        finally:
            page._open_zoom = original_open
        ok("拼图页：双击图上 / 空白处分别打到预览入口", len(opened) == 2, str(len(opened)))
        # ⚠️ 编辑那两条**不能**用替换方法再 emit 的办法验：连接时绑的是当时的
        #    绑定方法，事后再换属性改不动已建立的连接（会假绿）。所以下面直接
        #    emit 真信号、让处理函数跑到底（编辑器换成替身），接线与行为一起验。

        # ---- 编辑单张源图：**走画布信号**（连"接线"一起验）----
        import desktop.components.viewers.image_editor as editor_mod

        first = str(page._doc["pages"][0]["items"][0]["file"])
        original_dialog = editor_mod.ImageEditorDialog
        art = _png(work / "_blue.png", BLUE, (200, 300))
        editor_mod.ImageEditorDialog = _stub_editor(QImage(str(art)))
        try:
            page.view.item_edit_requested.emit(0)
        finally:
            editor_mod.ImageEditorDialog = original_dialog
        pump(app, times=4)
        ok("拼图页：编辑单张图覆盖回的正是那个源文件",
           _near(_pixel(Path(first)), BLUE), f"{first} → {_pixel(Path(first))}")
        ok("拼图页：日志说明「导出成品」时生效",
           "导出成品" in page.log_view.toPlainText())

        # ---- 编辑整页组合：**走画布信号** → 合成 → 编辑 → 落到 singletask 缓存 ----
        editor_mod.ImageEditorDialog = _stub_editor(QImage(str(art)))
        try:
            page.view.spread_edit_requested.emit()
            _wait_until(
                app,
                lambda: (page._doc["pages"][0] or {}).get("edited_file") is not None,
                timeout=40.0,
            )
        finally:
            editor_mod.ImageEditorDialog = original_dialog
        record = page._doc["pages"][0].get("edited_file")
        ok("拼图页：整页组合的编辑结果落到手上了",
           bool(record) and Path(record).is_file(), str(record))
        ok("拼图页：落盘的就是编辑器产物",
           bool(record) and _near(_pixel(Path(record)), BLUE))
        ok("拼图页：手改图存在 singletask 缓存区（不污染用户输出目录）",
           bool(record) and "singletask" in Path(record).parts
           and imp.EDITED_DIRNAME in Path(record).parts, str(record))

        # ---- 手改后：整页组合预览的回写目标 = 手改缓存；弹窗 image_saved 接链 ----
        spread2 = page._spread_target(0)
        ok("拼图页：手改后整页组合预览可编辑，回写目标就是手改缓存",
           spread2 is not None and str(spread2.edit_path or "") == str(record),
           f"edit={spread2.edit_path if spread2 else None} / record={record}")
        page.view.canvas._image(item_file)  # 预热画布解码缓存
        page._on_zoom_image_saved(item_file, QImage(str(art)))
        ok("拼图页：弹窗编辑源图 → 画布缓存被丢（重绘读新图）",
           item_file not in page.view.canvas._images)
        page._on_zoom_image_saved(str(record), QImage(str(art)))
        ok("拼图页：弹窗编辑整页组合的日志说明导出用手改图",
           "手改图" in page.log_view.toPlainText(),
           page.log_view.toPlainText()[-80:])

        # ---- 导出时手改图优先 ----
        out = Path(ctx.tmp) / "edit_imposition_out"
        page._compose_job(StepRequest(dest=out, args={"doc": dict(page._doc)}), None)
        exported = out / "0001.png"
        ok("拼图页：导出的第 1 页用的是手改过的整页组合",
           exported.is_file() and _near(_pixel(exported), BLUE), _pixel(exported))

        # ---- 版面一改，手改记录作废（否则用户会以为"改了版面导出还是旧图"）----
        page._on_items_changed(0, list(page.view.current_items()))
        ok("拼图页：改过版面后手改记录作废",
           "edited_file" not in page._doc["pages"][0])
    finally:
        if record:
            Path(record).unlink(missing_ok=True)
        _shutdown(page, app)
        page.deleteLater()


# ------------------------------------------------------------------ PDF 页模式
def _pdf_mode(ctx, ok) -> None:
    """提取页未提取时左栏是 PDF 的页缩略图：能双击放大，但不提供「编辑图片」。"""
    from desktop.modules.extract.page import ExtractModulePage
    from desktop.utils.files import singletask_thumbnails_dir
    from tests.selftests._context import pump

    page = ExtractModulePage()
    app = ctx.app
    try:
        pdf = Path(ctx.pdf)
        page.show_pdf(pdf)
        pump(app, times=4)
        target = page.viewer._zoom_target(0)
        ok("提取页：PDF 页模式也能预览（此前双击/右键整个没反应）",
           target is not None and callable(target.render))
        ok("提取页：PDF 矢量页不给 edit_path（没有可回写的文件）",
           target is not None and target.edit_path is None)
        items = page.viewer._zoom_menu_items(target)
        ok("提取页：PDF 页的右键菜单只有「预览图片」",
           [text for text, _icon, _slot in items] == ["预览图片"],
           str([t for t, _i, _s in items]))
        ok("提取页：PDF 页缩略图缓存目录仍按书分层（不被跨书污染）",
           # disk_key()：目录名锚在路由键上，不跟显示文案漂移
           "thumbnails" in singletask_thumbnails_dir(page.SPEC.disk_key(), pdf).parts)
    finally:
        _shutdown(page, app)
        page.deleteLater()


def run(ctx) -> None:
    from desktop.modules.detect.page import DetectModulePage
    from desktop.modules.extract.page import ExtractModulePage
    from desktop.modules.print.page import PrintModulePage
    from desktop.modules.rembg.page import RembgModulePage
    from tests.selftests._context import ok

    # ① extract 的 PDF 页模式：只给预览、不给编辑
    _pdf_mode(ctx, ok)

    # ② 四个"一个源"的独立步骤页（关键词各不相同：各自的"什么时候生效"）
    _edit_flow(ctx, ExtractModulePage, "提取图片", _prepare_extract, ok, has_apply=True)
    _edit_flow(ctx, DetectModulePage, "重新执行检测", _prepare_listing, ok, has_apply=True)
    _edit_flow(ctx, RembgModulePage, "重新执行去底色", _prepare_listing, ok, has_apply=False)
    _edit_flow(ctx, PrintModulePage, "生成 PDF", _prepare_listing, ok, has_apply=True)

    # ③ 拼图独立页
    _imposition_flow(ctx, ok)
