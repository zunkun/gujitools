# -*- coding: utf-8 -*-
"""缩略图磁盘缓存自测：首次加载生成、再次打开复用（mtime 不变）。"""

NAME = "thumb_cache"
DEPENDS: list[str] = ["tasklist"]
TITLE = "缩略图缓存"


def run(ctx) -> None:
    import time

    from tests.selftests._context import ok

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    for _ in range(30):
        app.processEvents(); time.sleep(0.1)
    cache_dir = repo.source_thumbnails_dir(tid)
    thumbs = list(cache_dir.glob("*.jpg"))
    ok("首次加载生成缓存", len(thumbs) == 6, str(cache_dir))
    mtimes = {f.name: f.stat().st_mtime_ns for f in thumbs}
    d.set_task(tid)
    for _ in range(20):
        app.processEvents(); time.sleep(0.1)
    mtimes2 = {f.name: f.stat().st_mtime_ns for f in cache_dir.glob("*.jpg")}
    ok("再次打开复用缓存", mtimes == mtimes2)
