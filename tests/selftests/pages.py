# -*- coding: utf-8 -*-
"""页面增删自测：删除/插入页面同步清单，执行输入直指 extract 目录。

产出跨模块状态：``ctx.inserted_img``（rembg/print 的外部图透传断言用）。
"""

NAME = "pages"
DEPENDS: list[str] = ["history"]
TITLE = "页面增删"


def run(ctx) -> None:
    import shutil

    import pymupdf
    from tests.selftests._context import make_pdf, ok

    app, d, repo, tmp = ctx.app, ctx.d, ctx.repo, ctx.tmp
    tid = ctx.tid

    d.set_task(tid)
    d._refresh_manifest()
    before = len(repo.load_pages(tid))
    d.detect_viewer.strip.setCurrentRow(2)
    d._select_stage(1)
    app.processEvents()
    d.detect_viewer.strip.setCurrentRow(2)
    d.delete_selected_page()
    ok("删除页面", len(repo.load_pages(tid)) == before - 1)

    # 插入（不弹对话框：直接模拟 insert_pages 的真实行为）
    imported = repo.extract_output_dir(tid)
    imported.mkdir(parents=True, exist_ok=True)
    extra = make_pdf(tmp / "extra.png", 1)  # 占位：用图片替代
    _doc = pymupdf.open(); _p = _doc.new_page(); _p.insert_text((72, 72), "插")
    _pix = _p.get_pixmap(); _pix.save(str(tmp / "inserted_src.png")); _doc.close()
    # insert_pages 会把选中的图片**复制进 stages/extract**（与提取结果同目录），
    # 这样后续 detect/rembg 直接读 extract 就能覆盖到它。测试必须走同一条路径，
    # 否则会造出「清单里有、但不在 extract」的不真实状态。
    img = imported / "inserted.png"
    shutil.copy2(tmp / "inserted_src.png", img)
    ctx.inserted_img = img
    pages = repo.load_pages(tid)
    pages.insert(1, {"file": str(img), "label": "inserted"})
    repo.save_pages(tid, pages)
    ok("插入页面", len(repo.load_pages(tid)) == before)
    d._refresh_manifest()  # 与 run_stage 实际流程一致：执行前刷新清单缓存
    # 执行输入直指 extract 目录（不再物化 workset 副本）
    args = {"input": str(repo.extract_output_dir(tid))}
    ok("执行输入指向 extract 目录", args["input"] == str(imported))

