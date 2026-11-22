# -*- coding: utf-8 -*-
"""候选卡片网格的收敛与缩略图分批填充（``_FillMixin``）。

Mixin 只在运行期与 ``ImpositionPickerDialog`` 组合；宿主面见 :mod:`._host`，
本模块**不 import** 主类 ``dialog``，避免循环导入。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.components.imposition.picker._qt import QPixmap, QTimer
from desktop.components.imposition.picker.cards import _SourceCard
from desktop.components.imposition.picker.constants import THUMB_BATCH, THUMB_GAP_MS
from desktop.components.imposition.picker.thumb import _source_thumb_pixmap

if TYPE_CHECKING:
    from desktop.components.imposition.picker._host import PickerHost as _Host
else:
    _Host = object


class _FillMixin(_Host):
    """列表内容生成、网格收敛与缩略图分批解码。"""

    # ------------------------------------------------------------------ 填充
    def _source_candidate_paths(self) -> list[Path]:
        """宿主给的候选（不含本次上传的；自动拼版序列用它）。"""
        return list(self._files)

    def _candidate_entries(self) -> list[tuple[str, Path, bool]]:
        """列表内容：``[(键, 路径, 是否本次上传)]``，宿主候选在前、上传的在后。"""
        entries: list[tuple[str, Path, bool]] = [
            (str(path), path, False) for path in self._source_candidate_paths()
        ]
        entries.extend((key, path, True) for key, path in self._uploads)
        return entries

    def _sync_grid(self, grid, store: dict, entries: list) -> list:
        """把网格收敛到 ``entries`` 这批卡片：多退少补、顺序重排。

        ⚠️ 卡片**不跨网格复用**（删/加时旧卡销毁、新卡重建，只把解码好的
        QPixmap 转移过去）。跨网格搬 widget 实例要在布局间摘了又挂，这条路径
        在 Qt 里脆弱（实测能段错误）；缩略图与卡片分离后，销毁重建只是几个
        空壳控件的事。
        """
        want = {key for key, _path, _up in entries}
        for key in [k for k in store if k not in want]:
            store.pop(key).deleteLater()
        cards = []
        for key, path, uploaded in entries:
            card = store.get(key)
            if card is None:
                card = _SourceCard(path, grid, key=key, uploaded=uploaded)
                card.clicked.connect(self._on_card_clicked)
                card.set_pixmap(self._pixmaps.get(key, QPixmap()))
                store[key] = card
            cards.append(card)
        grid.detach_cards()
        grid.adopt_cards(cards)
        return cards

    def _sync_grids(self) -> None:
        """按当前候选重建网格（一个列表，没有页签）。"""
        self.cards = self._sync_grid(
            self.body, self._cand_cards, self._candidate_entries()
        )

    def _populate(self) -> None:
        self._sync_grids()
        self._update_status()
        # 缩略图分批解码：一次全解上百张大图会把弹窗卡住几秒
        QTimer.singleShot(0, self._fill_thumbs)

    def _thumb_pixmap_for(self, card: _SourceCard) -> QPixmap:
        """一张候选的缩略图：**优先用宿主给的预生成小图**，拿不到才整幅解码。

        用户 2026-10-17：弹窗此前对每张候选图**整幅解码**源图再缩——几千像素的
        扫描件一张就要几十 MB 内存、几十毫秒。而这两种候选图**本来就有**
        预生成的 256px 小图：

        - 上游是「图片去底色」的**提交成品** ⇒ ``thumbnails/print[~<节点>]``；
        - 这一步是**流程第一个节点**（候选=入口图片）⇒ ``thumbnails/input/``。

        本次上传的图没有预生成小图（刚选进来），直接整幅解码——它们通常只有
        几张，可以接受。

        ⚠️ **回落路径必须保留**：去底色成品是「1bit 调色板 + tRNS」的透明 PNG，
        缩放读取会给出异常尺寸，只能整幅解码——这条坑见 :func:`_source_thumb_pixmap`。
        """
        if card.uploaded:
            return _source_thumb_pixmap(card.path)
        provided = None
        if self._thumb_provider is not None:
            try:
                provided = self._thumb_provider(str(card.path))
            except Exception:  # noqa: BLE001 - provider 坏掉不该让弹窗整片空白
                provided = None
        if provided:
            pixmap = _source_thumb_pixmap(provided)
            if not pixmap.isNull():
                return pixmap
        return _source_thumb_pixmap(card.path)

    def _fill_thumbs(self) -> None:
        """给还没有缩略图的卡片分批解码。

        ⚠️ 批次之间走 :data:`THUMB_GAP_MS` **有间隔**，不是 ``singleShot(0)``
        ——零间隔会让这一串重解码无缝连着跑满 CPU（用户 2026-10-03 报
        「程序容易跑崩溃，cpu 跑满」）。间隔期间事件循环能真正空出来，
        界面滚动/勾选/关闭都还有响应。
        """
        try:
            self.body.columns()  # noqa: B018 - 真访问 C++：弹窗已销毁就退出
        except RuntimeError:
            return  # 弹窗已被销毁（延迟队列里的 singleShot 才轮到）
        todo = [card for card in self.cards if card.cand_key not in self._pixmaps]
        for card in todo[:THUMB_BATCH]:
            pixmap = self._thumb_pixmap_for(card)
            self._pixmaps[card.cand_key] = pixmap
            card.set_pixmap(pixmap)
        if len(todo) > THUMB_BATCH:
            QTimer.singleShot(THUMB_GAP_MS, self._fill_thumbs)
