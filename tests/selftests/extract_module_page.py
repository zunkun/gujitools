# -*- coding: utf-8 -*-
"""独立「图片提取」模块页自测（补 2026-10-12 测试审计指出的 singletask 缺口）。

之前本页只有"共享层循环"式兜底（``module_progress`` / ``module_edit_sync`` 的
四页循环），没有**页级**断言。本模块不起子进程、不跑真提取，守护四件事：

1. **产物收集口径**（``collect_result_images``）：同名只留一份、**顶层优先**
   （用户 2026-10-03 报的"每页出现两次"bug 的回归锁）、自然排序；
2. **选完 PDF 能翻页**：左栏按 PDF 页数建条目（extract 专属的序号口径缓存
   不写进真实 ``~/Documents/guji/singletask``——测试里重定向到临时区）；
3. **提取完成后左栏切换成产物**：``on_result`` 把清单换成输出目录图片、
   ``map.json`` 序号映射落盘（同名嵌套残留被顶层口径压掉，不重复显示）；
4. **没有产出时不崩**：输出目录没有图片走 warning 提示，清单保持原样。

⚠️ 沙箱 QProcess 起不来没关系——本页执行链走 ``StepKernel``，这里只测结果
回填，不起任何子进程（真执行链已由 ``extract`` L3 用例覆盖）。
"""

from __future__ import annotations

from pathlib import Path

NAME = "extract_module_page"
DEPENDS: list[str] = ["modules_shell"]
TITLE = "独立图片提取页（产物口径 / 左栏切换 / 序号映射）"


def _jpg(path: Path, gray: int = 200) -> Path:
    import numpy as np
    import utils

    utils.imwrite(path, np.full((64, 48, 3), gray, dtype="uint8"))
    return path


def _redirect_caches(page, tmp: Path) -> dict:
    """把本页会用到的 singletask 缓存目录全部重定向到临时区。

    ⚠️ 缩略图缓存与 map.json 的规则函数是**模块级导入**进
    ``thumb_source`` / ``extract.page`` 的，覆盖 ``files.py`` 本体没用，
    要按命名空间逐个替换；原函数收工还原。
    """
    import desktop.modules.extract.page as page_mod
    import desktop.modules.thumb_source as ts_mod

    real = {
        "ts_extract_thumbs_dir": ts_mod.extract_thumbs_dir,
        "ts_singletask_thumbnails_dir": ts_mod.singletask_thumbnails_dir,
        "page_thumb_map_path": page_mod.thumb_map_path,
    }
    ts_mod.extract_thumbs_dir = (
        lambda subtask, book, edge, *a, **k: tmp / "thumbs_extract" / "edge"
    )
    ts_mod.singletask_thumbnails_dir = (
        lambda subtask, book=None, *a, **k: tmp / "thumbs_pdf" / "book"
    )
    page_mod.thumb_map_path = (
        lambda subtask, book, *a, **k: tmp / "map.json"
    )
    page._thumb_cache_dir = lambda: tmp / "thumbs_images"  # type: ignore[method-assign]
    return real


def _restore(real: dict) -> None:
    import desktop.modules.extract.page as page_mod
    import desktop.modules.thumb_source as ts_mod

    ts_mod.extract_thumbs_dir = real["ts_extract_thumbs_dir"]
    ts_mod.singletask_thumbnails_dir = real["ts_singletask_thumbnails_dir"]
    page_mod.thumb_map_path = real["page_thumb_map_path"]


def _check_collect(ok) -> None:
    """collect_result_images：同名去重顶层优先 + 自然排序（2026-10-03 回归锁）。"""
    from desktop.modules.extract.page import collect_result_images

    tmp = Path(__import__("tempfile").gettempdir()) / "collect_probe"
    tmp.mkdir(parents=True, exist_ok=True)
    # 顶层 1.jpg 是"应该在那儿"的产物；嵌套里同名 1.jpg 是命令布局残留
    nested = tmp / "书名" / "images"
    nested.mkdir(parents=True, exist_ok=True)
    top = _jpg(tmp / "1.jpg", 100)
    _jpg(nested / "1.jpg", 220)
    _jpg(tmp / "10.jpg", 120)
    _jpg(tmp / "2.jpg", 140)

    found = collect_result_images(tmp)
    names = [p.name for p in found]
    ok("同名去重：每页只出现一次", len(found) == 3, str(names))
    ok("同名冲突取顶层（不是嵌套残留）",
       found and found[0] == top, str(found[:1]))
    ok("自然排序（1,2,10 而非字典序 1,10,2）",
       names == ["1.jpg", "2.jpg", "10.jpg"], str(names))


def run(ctx) -> None:
    from desktop.modules.extract.page import ExtractModulePage
    from tests.selftests._context import make_pdf, ok, wait_until

    _check_collect(ok)

    tmp = Path(ctx.tmp) / "extract_module"
    tmp.mkdir(parents=True, exist_ok=True)
    pdf = make_pdf(tmp / "样例.pdf", 3)

    page = ExtractModulePage()
    real = _redirect_caches(page, tmp)
    try:
        # ---- 选完 PDF：左栏立刻按页建条目（未提取形态）----
        page.control.set_source(pdf)
        built = wait_until(ctx.app, lambda: page.viewer.strip.count() == 3,
                           timeout=30)
        ok("选完 PDF 左栏按页数建条目（3 页）", built and page.viewer.strip.count() == 3,
           str(page.viewer.strip.count()))
        ok("记住当前书（提取后重渲写回同一批序号缓存）",
           page._thumb_book == pdf, str(page._thumb_book))

        # ---- 提取完成：on_result 把左栏换成产物清单 ----
        out_dir = tmp / "样例_out"
        out_dir.mkdir()
        _jpg(out_dir / "1.jpg", 150)
        _jpg(out_dir / "2.jpg", 160)
        # 命令自己的嵌套布局残留：同名 1.jpg，不许让它把条目撑成重复
        nested = out_dir / "样例" / "images"
        nested.mkdir(parents=True)
        _jpg(nested / "1.jpg", 90)

        page.on_result(out_dir, {})
        ok("提取完成后左栏切换成产物（2 张，不是 3 条+重复）",
           page.viewer.strip.count() == 2, str(page.viewer.strip.count()))

        map_json = tmp / "map.json"
        ok("序号 ↔ 产物映射 map.json 落盘", map_json.is_file(),
           f"缺 {map_json}")
        if map_json.is_file():
            import json

            payload = json.loads(map_json.read_text(encoding="utf-8"))
            entries = payload.get("entries", [])
            ok("映射记录真实产出的序号与文件名",
               [e["seq"] for e in entries] == [1, 2]
               and entries[0]["name"] == "1.jpg",
               str(payload)[:200])

        # ---- 没有产出：warning 提示，不崩、清单不被清空 ----
        empty = tmp / "empty_out"
        empty.mkdir()
        page.on_result(empty, {})
        ok("输出目录没有图片时清单保持原样（不崩不清空）",
           page.viewer.strip.count() == 2, str(page.viewer.strip.count()))
    finally:
        _restore(real)
        page.shutdown_workers()
        page.deleteLater()


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
