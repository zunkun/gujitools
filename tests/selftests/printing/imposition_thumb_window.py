# -*- coding: utf-8 -*-
"""拼版左列缩略图**按可见窗口生成**自测（2026-11-21）。

用户报障：生产环境里进「图片拼版」要**等 5 分钟**才看到左列缩略图，"像卡死"。
根因不是合成慢，而是**一次性把整本 81 页排进后台**，还要和整本拼版成品合成
（每页 ~0.5s、PIL 编码期间攥着 GIL）抢同一个进程——实测被拖到 4~7 秒/页。

改法（与本用例一一对应）：

1. ``PageThumbManager`` 支持"可见窗口"：``flush`` **只交窗口里的页**，窗口外
   的留在队列里等用户滚到那儿（同导入预览"只预渲染首屏"的口径）；
2. 滚动/翻页后 ``refresh_window`` 把新进窗口的页补上；
3. 可见页缩略图在生成时，**整本成品合成让路**（不抢 GIL），让完再合成；
4. 没设窗口的宿主（旧调用/自测）保持原行为：排队多少交多少。
"""

from __future__ import annotations

import time
import types

NAME = "imposition_thumb_window"
DEPENDS: list[str] = []
TITLE = "拼版缩略图按可见窗口生成（首屏不等整本）"


def _make_source(path, color, size=(240, 320)):
    """造一张纯色源图（拼版页缩略图的输入）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(*color))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return path


def _page(path, size=(240, 320)) -> dict:
    return {
        "items": [{
            "file": str(path),
            "rect": [0.0, 0.0, float(size[0]), float(size[1])],
            "rotation": 0.0,
        }]
    }


def _sync_submit(calls: list):
    """替身 ``run_worker``：**同步**跑完这一批（信号走直连中继，当场落盘）。"""

    def submit(factory, wire):
        worker = factory()
        calls.append(worker.jobs)
        wire(worker, _fake_thread())
        worker.run()

    return submit


def _fake_thread():
    """替身线程对象：装配只用到 ``quit`` 与 ``finished`` 两个成员。"""
    from PySide6.QtCore import QObject, Signal

    class _FakeThread(QObject):
        finished = Signal()

        def quit(self) -> None:
            pass

    return _FakeThread()


def _indexes(batch) -> list:
    """这批活要生成的页号（``jobs`` 是字典列表，断言只看页号）。"""
    return [int(job["index"]) for job in (batch or [])]


def _record_submit(calls: list):
    """替身 ``run_worker``：只记下这批活，不执行（用来看 ``busy``）。"""

    def submit(factory, wire):
        calls.append(factory().jobs)

    return submit


def run(ctx) -> None:
    from PySide6.QtWidgets import QApplication

    from desktop.components.imposition.page_list import ImpositionPageList
    from desktop.components.imposition.page_thumb import PageThumbManager
    from desktop.pages.taskdetail.imposition_layout import (
        COMPOSE_YIELD_MAX_MS, COMPOSE_YIELD_MIN_PAGES,
        COMPOSE_YIELD_TO_THUMBS_MS, ImpositionLayoutMixin,
    )
    from tests.selftests._context import ok

    tmp = ctx.tmp / "imposition_thumb_window"
    tmp.mkdir(parents=True, exist_ok=True)
    pages = [
        _page(_make_source(tmp / f"src{i}.png", (30 * i % 255, 90, 160)))
        for i in range(6)
    ]

    # ---------------- 1. 设了窗口：只生成窗口里的页 ----------------
    out = tmp / "thumbs"
    calls: list = []
    window = {"range": (0, 1)}
    manager = PageThumbManager(
        out, 128, _sync_submit(calls), window_provider=lambda: window["range"],
    )
    queued = [manager.pixmap_for(i, page) for i, page in enumerate(pages)]
    ok("首刷：6 页都没有实体 → 先给占位（None）", all(p is None for p in queued),
       str([p is None for p in queued]))
    manager.flush()
    ok("只把**窗口内**的两页交给后台（不是整列 6 页）",
       calls and _indexes(calls[0]) == [0, 1], str(calls[:1])[:80])
    ok("窗口内的实体落盘（page1.jpg / page2.jpg）",
       (out / "page1.jpg").is_file() and (out / "page2.jpg").is_file(),
       str(sorted(x.name for x in out.glob('*.jpg'))))
    ok("窗口外的页**没有被生成**（page3.jpg 不存在，禁整本预渲染）",
       not (out / "page3.jpg").exists(),
       str(sorted(x.name for x in out.glob('*.jpg'))))
    ok("窗口外的页仍留在队列里（不是丢掉，滚动时会补）",
       manager.pending_count == 4, str(manager.pending_count))

    # ---------------- 2. 滚到新位置：按新窗口补 ----------------
    window["range"] = (4, 5)
    manager.refresh_window()
    ok("滚动后：新窗口的两页被补上（page5.jpg / page6.jpg）",
       (out / "page5.jpg").is_file() and (out / "page6.jpg").is_file(),
       str(sorted(x.name for x in out.glob('*.jpg'))))
    ok("滚动后：中间那两页（窗口没覆盖到）仍不生成",
       not (out / "page3.jpg").exists() and not (out / "page4.jpg").exists(),
       str(sorted(x.name for x in out.glob('*.jpg'))))
    ok("队列跟着清空（窗口内都做完了）",
       manager.pending_count == 2, str(manager.pending_count))

    # ---------------- 3. 同一页不重复排（签名命中就不生成） ----------------
    calls.clear()
    window["range"] = (0, 5)
    again = [manager.pixmap_for(i, page) for i, page in enumerate(pages)]
    ok("签名命中：已生成的两页直接回位图（不必再生成）",
       again[0] is not None and again[1] is not None, str([p is None for p in again]))
    manager.flush()
    ok("再刷时只补缺的两页（第 3、4 页）",
       calls and _indexes(calls[0]) == [2, 3], str(calls[:1])[:80])

    # ---------------- 4. 不设窗口：保持旧行为（排队多少交多少） ----------------
    legacy_calls: list = []
    legacy = PageThumbManager(tmp / "legacy", 128, _record_submit(legacy_calls))
    for index, page in enumerate(pages):
        legacy.pixmap_for(index, page)
    legacy.flush()
    ok("没设窗口的宿主（旧调用）：整批交出去，行为不变",
       legacy_calls and _indexes(legacy_calls[0]) == [0, 1, 2, 3, 4, 5],
       str(legacy_calls[:1]))

    # ---------------- 5. busy＝只认"可见页在生成" ----------------
    busy_calls: list = []
    busy_mgr = PageThumbManager(
        tmp / "busy", 128, _record_submit(busy_calls),
        window_provider=lambda: (0, 1),
    )
    for index, page in enumerate(pages):
        busy_mgr.pixmap_for(index, page)
    ok("还没交活：窗口批次为 0（合成不必让路）",
       busy_mgr.window_batch_size == 0, str(busy_mgr.window_batch_size))
    busy_mgr.flush()
    ok("可见页在飞：窗口批次＝2（合成据此判断要不要让路）",
       busy_mgr.window_batch_size == 2, str(busy_mgr.window_batch_size))
    busy_mgr._on_failed("磁盘满")  # 整批失败：必须解开在飞标记
    ok("一批失败后解开在飞标记（否则整列缩略图永远不再生成）",
       busy_mgr.window_batch_size == 0, str(busy_mgr.window_batch_size))

    # ---------------- 6. 合成让路：可见页缩略图没出完就先不合成 ----------------
    host = ImpositionLayoutMixin()
    host._imposition_dirty = False
    host._imposition_compose_deferred_at = None
    timer = types.SimpleNamespace(active=False, started=[])

    def _start(ms: int = 0) -> None:
        timer.active = True
        timer.started.append(ms)

    timer.start = _start  # type: ignore[method-assign]
    host._imposition_timer = timer
    host._page_thumb_mgr = types.SimpleNamespace(window_batch_size=8)
    ok("批量出首屏（8 页）在生成 → 本轮合成**让路**（返回 True）",
       host._defer_compose_for_thumbs() is True)
    ok("让路期间改动仍挂着（dirty 不被清）", host._imposition_dirty is True)
    ok("让路后按短间隔复查（不是就此不管）",
       timer.active and timer.started[-1] == COMPOSE_YIELD_TO_THUMBS_MS,
       str(timer.started))

    host._page_thumb_mgr = types.SimpleNamespace(window_batch_size=0)
    ok("缩略图这一批做完了 → 合成照常开始（不再让）",
       host._defer_compose_for_thumbs() is False)

    host._page_thumb_mgr = types.SimpleNamespace(window_batch_size=1)
    ok("单页重生成**不让路**（保住「松手 1 秒内看到成品更新」）",
       host._defer_compose_for_thumbs() is False)
    ok("让路门槛是「批量」而不是「任意一批」",
       COMPOSE_YIELD_MIN_PAGES >= 2, str(COMPOSE_YIELD_MIN_PAGES))

    host._page_thumb_mgr = types.SimpleNamespace(window_batch_size=8)
    host._imposition_compose_deferred_at = time.monotonic() - (
        COMPOSE_YIELD_MAX_MS / 1000.0 + 1
    )
    ok("让够了（超过上限）→ 强制合成，不能把下游饿死",
       host._defer_compose_for_thumbs() is False)
    ok("让路上限是个有限值（别写成无限让路）",
       0 < COMPOSE_YIELD_MAX_MS <= 60000, str(COMPOSE_YIELD_MAX_MS))

    # ---------------- 7. 左列"可见范围"是**有界**的 ----------------
    page_list = ImpositionPageList()
    page_list.resize(160, 420)
    page_list.set_pages([f"第{i + 1}页" for i in range(40)])
    page_list.show()
    QApplication.processEvents()
    rng = page_list.visible_index_range(margin=2)
    ok("40 页的清单：可见范围取得到", rng is not None, str(rng))
    if rng is not None:
        first, last = rng
        ok("可见范围是有界的（不是整列 40 页）",
           0 <= first <= last < 40 and (last - first + 1) <= 20,
           f"{first}..{last}")
        ok("可见范围从第一屏开始（不是从末尾）", first <= 3, str(rng))
    page_list.close()
    page_list.deleteLater()

    # ---------------- 8. 接线（静态契约）----------------
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    view_src = (
        root / "desktop/pages/taskdetail/view/previews.py"
    ).read_text(encoding="utf-8")
    pages_src = (
        root / "desktop/pages/taskdetail/imposition_pages/thumbnails.py"
    ).read_text(encoding="utf-8")
    layout_src = (
        root / "desktop/pages/taskdetail/imposition_layout/compose.py"
    ).read_text(encoding="utf-8")
    ok("任务详情页：把左列可见范围变化接到了控制器",
       "viewport_changed.connect" in view_src)
    ok("控制器：给缩略图管理者装了窗口取用方式",
       "window_provider=self._imposition_thumb_window" in pages_src)
    ok("合成入口：走「先让路，再合成」",
       "if not force_full and self._defer_compose_for_thumbs():" in layout_src)
