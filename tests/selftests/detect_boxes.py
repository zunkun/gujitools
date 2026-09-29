# -*- coding: utf-8 -*-
"""检测框自测：手动触发当前页 YOLO 检测、手动框入库不产生新文件。

依赖位置说明：本模块会向页面写入 manual 检测框，若排在 rembg/print
之前会改掉它们的合成断言结果，因此声明依赖 print（保持与原单文件
一致的先后次序）。
"""

NAME = "detect_boxes"
DEPENDS: list[str] = ["print"]
TITLE = "detect 检测框"


def run(ctx) -> None:
    import time
    from pathlib import Path

    from tests.selftests._context import ok

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d.set_task(tid)
    d._select_stage(1)
    app.processEvents()
    ok("切换到 detect 不自动执行检测", d.detect_process is None)
    d._detect_current_page()  # 手动触发当前页检测
    deadline = time.time() + 240
    while d.detect_process and d.detect_process.state() != 0 and time.time() < deadline:
        app.processEvents(); time.sleep(0.1)
    time.sleep(0.3); app.processEvents()
    ok("检测子进程返回结果", len(d.detect_cache) >= 1)
    info = d.detect_viewer.info_label.text()
    ok("检测信息展示", len(info) > 0, info)

    # ---- 手动框入库（不生成新文件） ----
    manual_path = repo.load_pages(tid)[0]["file"]

    def _snapshot():
        # 只比对产物文件；*.json 是数据存储（boxes.json 等），不算生成的产物
        return sorted(
            str(p) for p in repo.task_dir(tid).rglob("*")
            if p.is_file() and p.suffix != ".json"
        )

    before_files = _snapshot()
    d._save_manual_boxes(manual_path, [[10, 20, 300, 400]])
    entry = repo.detect_boxes_entry(tid, Path(manual_path).stem)
    ok("手动框写入数据库", entry is not None and entry[1] == "manual", str(entry))
    # ⚠️ 半幅页**恒 2 槽**（缺失侧 null）：不能因为只剩一个框就退化成 1 槽，
    #    否则会被当成「整幅」（用户 2026-09-29 报的"删掉一个框，另一个变整幅"）。
    stored = entry[0] if entry else None
    ok("手动框按半幅 2 槽入库（形态不退化）",
       isinstance(stored, list) and len(stored) == 2
       and [b for b in stored if b] == [[10, 20, 300, 400]], str(stored))
    ok("detect_cache 同步为同一份槽位表示",
       d.detect_cache.get(manual_path) == stored, str(d.detect_cache.get(manual_path)))
    after_files = _snapshot()
    ok("手动调整不生成新文件", before_files == after_files)
    # 再切回该页：直接命中 detect_cache，不触发重新检测
    d.detect_cache[manual_path] = stored
    d._detect_image_selected(0, manual_path)
    info = d.detect_viewer.info_label.text()
    ok("回看页面直接应用框", "300,400" in info and "px" not in info, repr(info))
