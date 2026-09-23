# -*- coding: utf-8 -*-
"""第四步待打印列表：缩略图必须落在**它自己那一页**上（删除/拖动途中也一样）。

起因（用户报）：进第四步后「生成 PDF」，发现缩略图跟真实图片的映射乱了，
于是照着缩略图删了某些页。

根因：左侧缩略图是**分批异步**装的（首批 10 张，之后每批 12 张、首轮还要等
2 秒、批间 150ms；几百页的书尾部要好几秒才补齐），而落值只认"派发时的行号"。
用户在装载途中删除/拖动条目后行号整体前移，在飞的批次就把
「别的页的图 + 别的页的标签 + 别的页的路径」一并刷到这一行上——列表看着错位、
重复，尾部条目还会因为下标越界被静默丢弃（永远停在灰色占位图）。

断言线：

1. **装载途中删一行 → 剩下的每一行仍然是它自己那页**（图 / 文字 / 路径三者一致）；
2. **装载途中拖动重排 → 同上**；
3. **不重复、不丢弃**：每页的图恰好出现在一行上，且没有行停留在占位图；
4. **已删条目的图到达时被丢弃**，不会写到任何一行上；
5. **Delete/Backspace 真的发删除请求**（第四步工具条写着「Delete 删除选中」，
   原先没有任何地方响应这个键），且前三步默认关着；
6. **删掉的那条仍然只删一条**（本轮不改选择模式：列表沿用单选，选中几条就删
   几条的语义保持原样——多选删除是另一个待用户拍板的改动）。

⚠️ 用真实 ``PrintPreviewWidget`` + 真实 ``ImageListWorker``（图很小，解码很快），
只把分批参数调小让用例跑得快；判据是**每行图的实际颜色**，直接对着"缩略图与
真实图片映射"这件事断言，而不是只看某个内部计数器。
"""

from __future__ import annotations

import time
from pathlib import Path

NAME = "print_thumbs_identity"
DEPENDS: list[str] = []
TITLE = "第四步缩略图不错位"


def _make_pages(root: Path, count: int):
    """造 count 张**每张一个专属纯色**的小图，返回 [(path, rgb)]。"""
    from PySide6.QtGui import QColor, QImage

    out = []
    for index in range(count):
        rgb = ((index * 7 + 20) % 256, (index * 13 + 40) % 256, (index * 29 + 60) % 256)
        img = QImage(40, 56, QImage.Format.Format_RGB32)
        img.fill(QColor(*rgb))
        path = root / f"p{index + 1:03d}.png"
        img.save(str(path))
        out.append((path, rgb))
    return out


def _shown_rgb(widget, row: int):
    """读回第 row 行缩略图中心像素的颜色（None = 还是占位图/没加载）。"""
    from PySide6.QtCore import QSize

    item = widget.strip.item(row)
    if item is None:
        return None
    pm = item.icon().pixmap(QSize(40, 56))
    if pm.isNull():
        return None
    image = pm.toImage()
    if image.isNull() or image.width() < 4 or image.height() < 4:
        return None
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    # 占位图是浅灰底 #e8ecf1，与测试用色不会撞
    if (color.red(), color.green(), color.blue()) == (0xE8, 0xEC, 0xF1):
        return None
    return (color.red(), color.green(), color.blue())


def _near(a, b, tol: int = 24) -> bool:
    """颜色比对放宽一点：缩放/平滑处理会让边缘混色，中心像素基本不变。"""
    return a is not None and b is not None and all(
        abs(x - y) <= tol for x, y in zip(a, b)
    )


def _wait_all_thumbs(widget, app, expect_calls: int, timeout: float = 30.0) -> None:
    """等所有批次跑完并静置，确保在飞回调都已落到主线程。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if (widget._thumb_next >= widget._thumb_total
                and widget._thumb_next > 0
                and getattr(widget, "_thumb_probe_calls", 0) >= expect_calls):
            break
        time.sleep(0.02)
    settle = time.time() + 0.6
    while time.time() < settle:
        app.processEvents()
        time.sleep(0.02)


def _audit(widget, label: str, ok, expect: list) -> None:
    """逐行核对：缩略图颜色 / 文字 / 路径 都必须属于该行自己的那一页。"""
    bad_color, bad_text, bad_path, blank = [], [], [], []
    for row in range(widget.strip.count()):
        entry = widget._entries_cache[row]
        want_rgb = expect[str(entry["file"])]
        item = widget.strip.item(row)
        got = _shown_rgb(widget, row)
        if got is None:
            blank.append(row)
        elif not _near(got, want_rgb):
            bad_color.append((row, Path(entry["file"]).stem, got, want_rgb))
        if item.text() != entry["label"]:
            bad_text.append((row, item.text(), entry["label"]))
        if str(item.data(0x0100)) != str(entry["file"]):  # Qt.UserRole
            bad_path.append((row, Path(str(item.data(0x0100))).stem,
                             Path(entry["file"]).stem))
    ok(f"{label}：每一行的缩略图都是它自己那页（图不错位）",
       not bad_color, f"错位 {len(bad_color)} 行，前 3：{bad_color[:3]}")
    ok(f"{label}：条目文字与数据层一致", not bad_text, str(bad_text[:3]))
    ok(f"{label}：条目路径与数据层一致", not bad_path, str(bad_path[:3]))
    ok(f"{label}：没有行停在灰色占位图（图没被下标越界丢掉）",
       not blank, f"空白行 {blank[:6]}")


def run(ctx) -> None:
    import shutil
    import tempfile

    from tests.selftests._context import ok

    from desktop.components.viewers import print_preview as pp
    from desktop.components.viewers import thumbs_loader
    from desktop.components.viewers.thumb_strip import ThumbStrip

    app = ctx.app
    mixin = thumbs_loader.ThumbsMixin
    saved_cfg = (
        mixin.FIRST_BATCH, mixin.SUCCESSIVE_BATCH,
        mixin.BATCH_DELAY_MS, mixin.BATCH_GAP_MS,
    )
    real_apply = pp.PrintPreviewWidget._apply_page_thumb
    tmp = Path(tempfile.mkdtemp(prefix="guji_thumb_identity_"))
    widgets: list = []

    def _new_widget():
        widget = pp.PrintPreviewWidget(
            params_provider=lambda: {"paper_size": "A4", "orientation": "landscape"}
        )
        widgets.append(widget)
        # 统计到达次数（判"批次真的跑完了"），不改行为
        widget._thumb_probe_calls = 0

        def _counted(self, key, image):
            if self is widget:
                self._thumb_probe_calls += 1
            return real_apply(self, key, image)

        pp.PrintPreviewWidget._apply_page_thumb = _counted
        return widget

    try:
        # 缩短分批节奏（策略不变，只是别让用例等好几秒）
        mixin.FIRST_BATCH = 4
        mixin.SUCCESSIVE_BATCH = 5
        mixin.BATCH_DELAY_MS = 500
        mixin.BATCH_GAP_MS = 30

        pages = _make_pages(tmp, 26)
        expect = {str(p): rgb for p, rgb in pages}
        entries = [{"file": str(p), "label": p.stem} for p, _ in pages]

        # ---------- 1. 装载途中删除中间一条 ----------
        widget = _new_widget()
        widget.set_entries(list(entries))
        app.processEvents()
        # 立刻就删（首批 4 张之外的都在排队，正是出错窗口）
        # ⚠️ 先 clearSelection：QListWidget.setCurrentRow 在扩展选择模式下
        # 会把当前行一起选中，不清理就会连当前行一起删掉
        widget.strip.clearSelection()
        widget.strip.item(3).setSelected(True)
        widget.remove_selected()
        ok("装载途中删除后条目数正确",
           widget.strip.count() == len(pages) - 1
           and widget.count() == len(pages) - 1,
           f"strip={widget.strip.count()} cache={widget.count()}")
        expect_after = {str(e["file"]): expect[str(e["file"])]
                        for e in widget._entries_cache}
        _wait_all_thumbs(widget, app, len(widget._entries_cache))
        _audit(widget, "装载途中删除", ok, expect_after)
        # 每页的图恰好出现一行（不重复、不丢失）
        seen = [str(widget._entries_cache[r]["file"]) for r in range(widget.count())]
        ok("装载途中删除：条目集合恰好是被删后的那批（不重复不丢失）",
           len(set(seen)) == len(seen) == len(pages) - 1, f"{len(seen)} 条")

        # ---------- 2. 装载途中拖动重排 ----------
        widget2 = _new_widget()
        widget2.set_entries(list(entries))
        app.processEvents()
        moved = widget2.strip.takeItem(2)
        widget2.strip.insertItem(20, moved)
        widget2._on_strip_order_changed()
        expect2 = {str(e["file"]): expect[str(e["file"])]
                   for e in widget2._entries_cache}
        _wait_all_thumbs(widget2, app, len(widget2._entries_cache))
        _audit(widget2, "装载途中拖动重排", ok, expect2)
        ok("装载途中拖动重排：条目集合仍是全部页",
           len({str(e["file"]) for e in widget2._entries_cache}) == len(pages),
           str(len(widget2._entries_cache)))

        # ---------- 3. 已删条目的图到达 → 丢弃，不写到别行 ----------
        widget3 = _new_widget()
        widget3.set_entries(list(entries))
        app.processEvents()
        ghost_key = object()          # 不在 _entry_keys 里的令牌
        before = [
            (widget3.strip.item(r).text(),
             str(widget3.strip.item(r).data(0x0100)))
            for r in range(widget3.strip.count())
        ]
        from PySide6.QtGui import QImage as _QImage
        _img = _QImage(20, 28, _QImage.Format.Format_RGB32)
        _img.fill(0x00FF00)
        real_apply(widget3, ghost_key, _img)
        after = [
            (widget3.strip.item(r).text(),
             str(widget3.strip.item(r).data(0x0100)))
            for r in range(widget3.strip.count())
        ]
        ok("身份已失效的缩略图被丢弃，一行都没被改写",
           before == after, "有行被改写了")

        # ---------- 4. Delete 键 → 删除请求 ----------
        widget4 = _new_widget()
        widget4.set_entries(list(entries))
        _wait_all_thumbs(widget4, app, len(entries))
        widget4.strip.clearSelection()
        widget4.strip.item(1).setSelected(True)
        widget4.remove_selected()
        ok("「删除选中」只删掉选中的那一条（选择语义未改动）",
           widget4.strip.count() == len(pages) - 1
           and widget4.count() == len(pages) - 1,
           f"strip={widget4.strip.count()} cache={widget4.count()}")
        expect4 = {str(e["file"]): expect[str(e["file"])]
                   for e in widget4._entries_cache}
        _audit(widget4, "删除后", ok, expect4)

        # Delete 键：真的发出删除请求 → 宿主删掉选中条目
        widget4.strip.clearSelection()
        widget4.strip.item(0).setSelected(True)
        widget4.strip.setFocus()
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        before_count = widget4.count()
        QApplication.sendEvent(
            widget4.strip,
            QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete,
                      Qt.KeyboardModifier.NoModifier),
        )
        app.processEvents()
        ok("Delete 键会请求删除选中条目（提示文案不是空头支票）",
           widget4.count() == before_count - 1,
           f"{before_count} → {widget4.count()}")

        # Backspace 同理
        widget4.strip.clearSelection()
        widget4.strip.item(0).setSelected(True)
        QApplication.sendEvent(
            widget4.strip,
            QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backspace,
                      Qt.KeyboardModifier.NoModifier),
        )
        app.processEvents()
        ok("Backspace 也能删除选中条目",
           widget4.count() == before_count - 2,
           str(widget4.count()))

        # 前三步（不可删除）时按键不产生任何删除请求
        plain = ThumbStrip()
        fired: list[int] = []
        plain.delete_requested.connect(lambda: fired.append(1))
        QApplication.sendEvent(
            plain,
            QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete,
                      Qt.KeyboardModifier.NoModifier),
        )
        ok("未打开可删除时，Delete 不产生删除请求（前三步安全）",
           fired == [], str(fired))
        plain.deleteLater()
    finally:
        pp.PrintPreviewWidget._apply_page_thumb = real_apply
        (
            mixin.FIRST_BATCH, mixin.SUCCESSIVE_BATCH,
            mixin.BATCH_DELAY_MS, mixin.BATCH_GAP_MS,
        ) = saved_cfg
        for widget in widgets:
            try:
                widget.shutdown_workers()
            except Exception:
                pass
            widget.deleteLater()
        shutil.rmtree(tmp, ignore_errors=True)
