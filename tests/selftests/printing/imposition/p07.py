# -*- coding: utf-8 -*-
"""候选池：上游剩余图 + 这个任务上传过的图（用户 2026-11-16） / 多选配对：勾 4 张 →「开始拼版」两两成页（用户 2026-09-30） / 左列右键「上移 / 下移」与「向前 / 向后插入拼版」（用户 2026-11-16） / 自动拼版接线：勾 1 张 + 「从这张图片开始自动拼版」→ 规则引擎接管 / 左列缩略图实体（用户 2026-10-09：生成落地、pageN 命名、映射数据） / 单步操作（拖动/复位落盘）后几秒内更新**单页**缩略图（2026-10-09） / ⚠️ 回填**不许**整列重灌（用户 2026-10-06 报\"拼版阶段程序卡死\"）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import BLUE, RED, YELLOW, _mk, _names, _px_near
    from pathlib import Path
    from desktop.utils.files import THUMBNAIL_EDGE as _EDGE
    from PySide6.QtGui import QPixmap as _QPixmap
    import desktop.components.imposition.picker as _ipick
    import time as _time
    from desktop.components.imposition.page_thumb import (
        compose_page_thumb_from_files,
        load_page_index,
        page_signature,
        thumb_file_name,
        write_page_index,
    )
    from tests.selftests._context import make_pdf, ok, pump
    from desktop.services.imposition_insert import upload_dir
    from desktop.services.imposition_insert import upload_dir

    insert_dir = upload_dir(st.page.store.task_dir(st.page.task_id))
    insert_dir.mkdir(parents=True, exist_ok=True)
    mine = insert_dir / "my-scan.png"
    _mk(mine, RED)
    pool = st.page._imposition_candidate_pool(st.page._imposition_doc())
    ok(
        "候选池 = 上游剩余图 + 上传过的图（上传的排在后面、只出现一次）",
        _names(pool)[-1] == "my-scan.png"
        and _names(pool).count("my-scan.png") == 1,
        str(_names(pool)),
    )

    class _FakeUploadedDialog(st._FakeDialog):
        """替身弹窗：只勾那张上传的图。"""

        def picked_files(self):
            return [f for f in self.files if Path(f).name == "my-scan.png"]

    _ipick.ImpositionPickerDialog = _FakeUploadedDialog
    try:
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
        upload_pages = st.page._imposition_pages()
        ok(
            "上传的图能直接拼成一页（已在任务目录里，不再复制第二份）",
            len(upload_pages) == 1
            and Path(upload_pages[0]["items"][0]["file"]) == mine,
            str([[Path(i["file"]).name for i in p["items"]] for p in upload_pages]),
        )
        ok(
            "上传的图不落进上一步的产物目录（上一步页面清单不会多一条）",
            str(mine) not in {str(p) for p in st.page.imposition_source_files()}
            and Path(mine).parent != st.rembg_dir,
            f"{mine.parent} vs {st.rembg_dir}",
        )
        ok(
            "上传的图不落进上一步的产物目录（上一步页面清单不会多一条）",
            str(mine) not in {str(p) for p in st.page.imposition_source_files()}
            and Path(mine).parent != st.rembg_dir,
            f"{mine.parent} vs {st.rembg_dir}",
        )
        ok(
            "被页引用后它不再出现在候选池里",
            "my-scan.png"
            not in _names(st.page._imposition_candidate_pool(st.page._imposition_doc())),
        )
        st.page._on_imposition_release_page(0)
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
        ok(
            "删掉拼版页后，上传的图回到候选池（不再永久消失）",
            "my-scan.png"
            in _names(st.page._imposition_candidate_pool(st.page._imposition_doc())),
            str(_names(st.page._imposition_candidate_pool(st.page._imposition_doc()))),
        )
        # 只勾一张（上游图）→ 单图单独一页（用户 2026-09-30：单张允许拼版）
        _ipick.ImpositionPickerDialog = st._FakeOneDialog
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
        one_pages = st.page._imposition_pages()
        ok(
            "只勾一张 → 单图单独一页（1 项、原图 1-r）",
            len(one_pages) == 1
            and len(one_pages[0]["items"]) == 1
            and Path(one_pages[0]["items"][0]["file"]).name == "1-r.png",
            str([[Path(i["file"]).name for i in p["items"]] for p in one_pages]),
        )
        # 清空，接原有「手动两张」流程
        st.page._save_imposition_pages([])
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog
        try:
            mine.unlink()
        except OSError:
            pass
    _ipick.ImpositionPickerDialog = st._FakeManyDialog
    try:
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
        pages = st.page._imposition_pages()
        ok(
            "多选 4 张：开始拼版两两成页（共 2 页）",
            len(pages) == 2
            and all(len(p["items"]) == 2 for p in pages)
            and Path(pages[0]["items"][0]["file"]).name == "1-r.png"
            and Path(pages[1]["items"][0]["file"]).name == "2-r.png",
            str([[Path(i["file"]).name for i in p["items"]] for p in pages]),
        )
        ok(
            "多选拼版后左列两页、停在第一页",
            len(st.page.imposition_view.page_list.entries()) == 2
            and st.page.imposition_view.current_index() == 0,
            str(st.page.imposition_view.current_index()),
        )
        # 清空，接原有「手动两张」流程
        st.page._save_imposition_pages([])
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog
    class _FakeInsertDialog(st._FakeOneDialog):
        """替身弹窗：只勾 1 张，落点取调用方传进来的 ``position``。"""

        def position(self):
            return self.position_default

    def _page_names():
        return [
            [Path(i["file"]).name for i in _p["items"]]
            for _p in st.page._imposition_pages()
        ]

    _ipick.ImpositionPickerDialog = st._FakeOneDialog
    try:
        st.page._on_imposition_add_requested()   # 第 1 页 = 1-r
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
        st.page._on_imposition_add_requested()   # 第 2 页 = 1-l
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog
    ok(
        "前置：两次「选择拼版」各造一页单图",
        _page_names() == [["1-r.png"], ["1-l.png"]],
        str(_page_names()),
    )
    st.page._on_imposition_page_move(0, +1)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    ok(
        "右键「下移」：第 1 页挪到第 2 位（只换顺序，图片引用不动）",
        _page_names() == [["1-l.png"], ["1-r.png"]]
        and st.page.imposition_view.current_index() == 1,
        f"{_page_names()} current={st.page.imposition_view.current_index()}",
    )
    st.page._on_imposition_page_move(0, -1)
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    ok(
        "首行「上移」越界：顺序不变（不会把页弄丢）",
        _page_names() == [["1-l.png"], ["1-r.png"]],
        str(_page_names()),
    )
    _ipick.ImpositionPickerDialog = _FakeInsertDialog
    try:
        st.page._on_imposition_page_insert(1, "before")
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog
    ok(
        "「向前插入拼版」：新页落在目标页**之前**，视图停在它上面",
        _page_names() == [["1-l.png"], ["2-r.png"], ["1-r.png"]]
        and st.page.imposition_view.current_index() == 1,
        f"{_page_names()} current={st.page.imposition_view.current_index()}",
    )
    _ipick.ImpositionPickerDialog = _FakeInsertDialog
    try:
        st.page._on_imposition_page_insert(1, "after")
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog
    ok(
        "「向后插入拼版」：新页落在目标页**之后**，左列页数同步",
        _page_names()
        == [["1-l.png"], ["2-r.png"], ["2-l.png"], ["1-r.png"]]
        and len(st.page.imposition_view.page_list.entries()) == 4,
        f"{_page_names()} entries="
        f"{len(st.page.imposition_view.page_list.entries())}",
    )
    # 清空，接后续用例（它们从"没有页"开始重建）
    st.page._save_imposition_pages([])
    st.page._imposition_timer.stop()
    pump(st.ctx.app, times=4)
    class _FakeAutoDialog(st._FakeDialog):
        """替身弹窗：只勾第一张 + 自动拼版（UI 行为已在真实弹窗测过）。"""

        def picked_files(self):
            return self.files[:1]

        def auto_mode_file(self):
            return self.files[0]

        def auto_sequence(self):
            return list(self.files)

    _ipick.ImpositionPickerDialog = _FakeAutoDialog
    try:
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
        auto_pages = st.page._imposition_pages()
        ok(
            "自动拼版落盘：首位 1-r 单独一页、(1-l,2-r) 配对、末尾 2-l 单独",
            len(auto_pages) == 3
            and [
                tuple(Path(i["file"]).name for i in p["items"]) for p in auto_pages
            ]
            == [("1-r.png",), ("1-l.png", "2-r.png"), ("2-l.png",)],
            str([[Path(i["file"]).name for i in p["items"]] for p in auto_pages]),
        )
        ok(
            "自动拼版后左列 3 页、停在第一页",
            len(st.page.imposition_view.page_list.entries()) == 3
            and st.page.imposition_view.current_index() == 0,
            str(st.page.imposition_view.current_index()),
        )
        # 清空，接原有「手动两张」流程
        st.page._save_imposition_pages([])
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=4)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog

    _ipick.ImpositionPickerDialog = st._FakeDialog
    try:
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
        pages = st.page._imposition_pages()
        ok(
            "「选择拼版」→ 追加一页并要求两张",
            len(pages) == 1 and len(pages[0]["items"]) == 2,
            str(pages),
        )
        ok(
            "落盘后左列同步成 1 页并停在该页",
            len(st.page.imposition_view.page_list.entries()) == 1
            and st.page.imposition_view.current_index() == 0,
            str(st.page.imposition_view.current_index()),
        )
        ok(
            "加页后自动启用（否则第四步根本用不到它）",
            st.page._load_imposition_enabled(),
        )
        ok(
            "跳过已用过的图：第二页拿到的是剩下那两张",
            [Path(i["file"]).name for i in pages[0]["items"]]
            == ["1-r.png", "1-l.png"],
            str([Path(i["file"]).name for i in pages[0]["items"]]),
        )
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        pump(st.ctx.app, times=6)
        pages = st.page._imposition_pages()
        ok(
            "再加一页 → 共两页，左列两条 + 虚线格",
            len(pages) == 2 and len(st.page.imposition_view.page_list.entries()) == 2,
        )
        # 四张都用完了：再点只能提示，不许造出半页
        st.page._on_imposition_add_requested()
        st.page._imposition_timer.stop()
        ok("没有剩余图片时不会造出残页", len(st.page._imposition_pages()) == 2)
    finally:
        _ipick.ImpositionPickerDialog = st.real_dialog
    import time as _time

    from desktop.components.imposition.page_thumb import load_page_index
    from desktop.utils.files import THUMBNAIL_EDGE as _EDGE

    _pthumb_dir = st.page.store.imposition_page_thumbs_dir(st.page.task_id)
    for _ in range(240):  # 后台 worker 逐页生成：轮询到实体落盘或超时
        if (_pthumb_dir / "page1.jpg").is_file() and (
            _pthumb_dir / "page2.jpg"
        ).is_file():
            break
        st.ctx.app.processEvents()
        _time.sleep(0.05)
    ok(
        "左列缩略图实体：page1.jpg / page2.jpg 落地（页面效果、页号命名）",
        (_pthumb_dir / "page1.jpg").is_file()
        and (_pthumb_dir / "page2.jpg").is_file(),
        f"{_pthumb_dir} -> " f"{sorted(x.name for x in _pthumb_dir.glob('*.jpg'))}",
    )
    _pmap = load_page_index(_pthumb_dir, _EDGE)
    ok(
        "映射数据：index.json 记好 页号 ↔ 文件 ↔ 签名",
        sorted(_pmap) == [0, 1] and all(_pmap.values()),
        str(_pmap),
    )
    st._entries = st.page.imposition_view.page_list.entries()
    ok(
        "左列缩略图：贴到条目上（pixmap 非空，不再是占位）",
        len(st._entries) == 2 and all(not e.thumb.pixmap().isNull() for e in st._entries),
        str([e.thumb.pixmap().isNull() for e in st._entries]),
    )
    for _ in range(100):  # 等左列贴上**整页**实体
        _p2 = st._entries[1].thumb.pixmap()
        if not _p2.isNull() and _p2.toImage().width() > 1:
            break
        st.ctx.app.processEvents()
        _time.sleep(0.05)
    _p2img = st._entries[1].thumb.pixmap().toImage()
    ok(
        "左列缩略图 = 页面效果：两图页两半各显示一张（非单张）",
        _px_near(_p2img, _p2img.width() // 4, _p2img.height() // 2, YELLOW)
        and _px_near(_p2img, _p2img.width() * 3 // 4, _p2img.height() // 2, BLUE),
        f"size={(_p2img.width(), _p2img.height())} "
        f"左半={_p2img.pixelColor(_p2img.width() // 4, _p2img.height() // 2).getRgb()[:3]} "
        f"右半={_p2img.pixelColor(_p2img.width() * 3 // 4, _p2img.height() // 2).getRgb()[:3]}",
    )
    _key_before = st._entries[1]._thumb_key
    _pages_now = st.page._imposition_pages()
    _moved_items = [dict(it) for it in _pages_now[1]["items"]]
    _moved_items[1] = {
        **_moved_items[1],
        "rect": [
            900.0,
            0.0,
            float(_moved_items[1]["rect"][2]),
            float(_moved_items[1]["rect"][3]),
        ],
    }
    st.page._on_imposition_items_changed(1, _moved_items)
    ok(
        "版面落盘后：攒页号等防抖（不立刻重灌、更不整列）",
        st.page._imposition_thumb_dirty == {1}
        and st.page._imposition_thumb_timer.isActive()
        and st._entries[1]._thumb_key == _key_before,
        f"dirty={st.page._imposition_thumb_dirty}",
    )
    st.page._imposition_thumb_timer.stop()
    st.page._refresh_imposition_dirty_page_thumbs()  # 防抖到期（手动触发）
    for _ in range(240):  # 等后台把这一页的实体重生成并贴回
        if st._entries[1]._thumb_key != _key_before:
            break
        st.ctx.app.processEvents()
        _time.sleep(0.05)
    ok(
        "版面落盘后：防抖到期**单页**重生成实体（缩略图跟上版面）",
        st._entries[1]._thumb_key != _key_before,
    )
    st.page._imposition_timer.stop()
    st.page._imposition_dirty = False
    # 还原版面（后续用例还要用这两页）
    st.page._on_imposition_items_changed(
        1, [dict(it) for it in _pages_now[1]["items"]]
    )
    st.page._imposition_thumb_timer.stop()
    st.page._refresh_imposition_dirty_page_thumbs()
    for _ in range(240):  # 版面改回去了：memo 命中/重生成后应回到原来的图
        if st._entries[1]._thumb_key == _key_before:
            break
        st.ctx.app.processEvents()
        _time.sleep(0.05)
    ok("（恢复）版面还原后缩略图跟着复原", st._entries[1]._thumb_key == _key_before)
    _entries_objs = st.page.imposition_view.page_list.entries()
    _sink: list = []
    _docs: list = []
    _real_doc = st.page.store.load_imposition_doc

    def _counting_doc(task_id):
        _docs.append(task_id)
        return _real_doc(task_id)

    # ⚠️ **必须先把原方法抓在手里再包一层**（MEMORY 记过的坑）：否则
    #    无限递归把整轮自测带崩。
    _orig_set_thumb = [_e.set_thumb for _e in _entries_objs]

    def _make_counter(original):
        def _counted(image):
            _sink.append(1)
            return original(image)

        return _counted

    from PySide6.QtGui import QPixmap as _QPixmap

    try:
        for _e, _fn in zip(_entries_objs, _orig_set_thumb):
            _e.set_thumb = _make_counter(_fn)
        st.page.store.load_imposition_doc = _counting_doc
        for _i in range(len(_entries_objs)):
            st.page._on_imposition_page_thumb_ready(_i, _QPixmap(8, 8))
    finally:
        st.page.store.load_imposition_doc = _real_doc
        for _e, _fn in zip(_entries_objs, _orig_set_thumb):
            _e.set_thumb = _fn
    ok(
        "缩略图回填：每张到达只贴**那一条**，不整列重灌（反 O(N²)）",
        len(_sink) <= len(_entries_objs),
        f"set_thumb 被调 {len(_sink)} 次 / {len(_entries_objs)} 条",
    )
    ok(
        "缩略图回填：不重读 imposition.json（反 380×97KB 读盘）",
        not _docs,
        f"load_imposition_doc 被调 {len(_docs)} 次",
    )
    ok(
        "左列版面：缩略图在上、文字在下（勾选框贴左上角）",
        all(e.checkbox.y() < e.thumb.y() < e.title_label.y() for e in st._entries)
        and all(e.checkbox.x() < e.width() // 2 for e in st._entries),
    )
    # 实体归属边界（2026-10-04 目录各归各 + 2026-10-09 pageN 命名）
    _cache_dir = st.page.store.imposition_page_thumbs_dir(st.page.task_id)
    _cached = sorted(x.name for x in _cache_dir.glob("*.jpg"))
    ok(
        "左列缩略图实体写在任务目录 thumbnails/imposition_pages/（pageN 命名）",
        _cache_dir.is_dir() and _cached == ["page1.jpg", "page2.jpg"],
        f"{_cache_dir} -> {_cached}",
    )

