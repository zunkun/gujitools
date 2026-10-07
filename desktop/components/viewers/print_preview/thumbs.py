# -*- coding: utf-8 -*-
"""print 预览 Mixin：**缩略图与排序**。

缩略图路径/批量加载/条目排序缓存同步。（从 ``print_preview.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from pathlib import Path
from typing import cast
from PySide6.QtCore import Qt
from desktop.workers import ImageListWorker
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import PrintPreviewHost
else:
    PrintPreviewHost = object


class PrintThumbsMixin(PrintPreviewHost):
    """缩略图路径/批量加载/条目排序缓存同步。"""

    def _thumb_path_for(self, entry: dict) -> Path:
        """条目缩略图来源：条目自带 thumb → provider → 条目图片本身。"""
        spec = entry.get("thumb")
        if isinstance(spec, dict) and spec.get("path"):
            return Path(spec["path"])
        if spec:
            # thumb 合法形态是 dict（已处理）或路径类（str/Path）
            return Path(cast("str | Path", spec))
        file_text = str(entry["file"])
        if self._thumb_provider is not None:
            try:
                provided = self._thumb_provider(file_text)
            except Exception:
                provided = None
            if isinstance(provided, dict) and provided.get("path"):
                return Path(provided["path"])
            if provided:
                return Path(cast("str | Path", provided))
        return Path(file_text)


    def _load_page_thumbs(self) -> None:
        """加载左侧缩略图（缩放解码 = 现算小图，不落盘）。

        名字带 page 是为了与 ThumbsMixin 的 ``_load_thumbs(strip, paths)``
        区分——后者签名不同，两者互不覆盖。

        ⚠️ 走基类 ``_load_thumbs_chunked`` 分批：页面多时一次性解码会把
        一个核打满（风扇起转），分批后首批立刻可见、其余按间隙补齐。

        ⚠️ 分批派发的是**条目身份令牌**而不是下标：批次跑完之前用户可能已经
        删除/拖动过条目，行号会变（详见 :meth:`_apply_page_thumb`）。
        """
        entries = self._entries_cache
        if not entries:
            return
        pending = [
            (key, self._thumb_path_for(entry))
            for key, entry in zip(self._entry_keys, entries)
        ]
        keys = [key for key, _ in pending]
        edge = self._decode_edge(self.THUMB_EDGE)
        self._load_thumbs_chunked(
            len(pending),
            make_worker=lambda start, end: ImageListWorker(
                [path for _, path in pending[start:end]], edge=edge
            ),
            sink=lambda index, image, _path, keys=keys: (
                self._apply_page_thumb(keys[index], image)
                if 0 <= index < len(keys) else None
            ),
        )


    def _apply_page_thumb(self, key, image) -> None:
        """某条目的缩略图就绪：**按身份**找回它当前所在的行再落值。

        ⚠️ 这里绝不能用"派发时的下标"。缩略图是分批异步装的（首批 10 张，
        之后每批 12 张、首轮还要等 2s），一本几百页的书尾部要好几秒才补齐；
        这期间用户删掉/拖动了条目，行号就整体前移了——按旧下标写会把
        「别的页的图 + 别的页的标签 + 别的页的路径」一并刷到这一行上。后果
        不只是看着乱：用户照着缩略图删页，删掉的是**数据层那一条**，跟屏幕
        上看到的页不是同一张（2026-09-23 用户报「缩略图跟真实图片映射乱了，
        我就删除了某些页」）。条目已被删除（令牌找不到）时直接丢弃。
        """
        try:
            row = self._entry_keys.index(key)
        except ValueError:
            return
        entry = self._entries_cache[row]
        label = entry.get("label") or Path(str(entry["file"])).stem
        self.strip.set_item_icon(row, image, str(entry["file"]), str(label))


    def _on_strip_order_changed(self) -> None:
        self._sync_cache_order()
        self._emit_order_changed()


    def _sync_cache_order(self) -> None:
        """按当前视觉顺序重排富条目缓存，并重分配条目索引。"""
        order = []
        for row in range(self.strip.count()):
            index = self.strip.item(row).data(Qt.ItemDataRole.UserRole + 1)
            if index is not None and 0 <= index < len(self._entries_cache):
                order.append(int(index))
        # 删除后 order 会短于缓存——这正是"去掉被删条目"的效果，不能拦
        keys = self._entry_keys
        if len(keys) != len(self._entries_cache):
            # 正常不会走到（两个表只在 set_entries / 本方法里成对重建）；
            # 真错位也只重建令牌，绝不让 IndexError 把同步链路打断
            keys = [object() for _ in self._entries_cache]
        self._entries_cache = [self._entries_cache[i] for i in order]
        # 身份令牌必须与条目**同步换序**：_apply_page_thumb 靠它找回条目
        # 当前所在的行号，两者一旦错位就会把缩略图写到别的页上
        self._entry_keys = [keys[i] for i in order]
        for row in range(self.strip.count()):
            self.strip.item(row).setData(Qt.ItemDataRole.UserRole + 1, row)


    def _emit_order_changed(self) -> None:
        if self._entries_cache:
            self.order_changed.emit()
