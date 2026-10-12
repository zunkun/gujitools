# -*- coding: utf-8 -*-
"""独立「PDF排版」模块页自测（补 2026-10-12 测试审计指出的 singletask 缺口）。

之前本页只有共享层兜底（``module_progress`` 四页循环），第四步任务流程侧覆盖
极厚、独立页**零页级断言**。本模块不起子进程，守护五件事：

1. **内核契约**：``spec_by_key("print").artifact_is_file`` 必须为 True——
   执行内核靠它决定「不把 outpath 覆盖成目录、把真 PDF 路径回传 on_result」，
   这个标志丢了 = 拿目录当文件路径写（回归锁）；
2. **页序契约**：独立页**不提供手动排序**，页序 = 文件名自然序
   （1,2,10 而非字典序 1,10,2）——与 CLI 直跑同口径（用户 2026-10-02 的选择）;
3. **选完源能翻看**：左栏条目按待打印图片建好，副标题带张数；
4. **生成完成左栏切换**：``on_result(真PDF)`` 把左栏从待打印图切成产物 PDF
   的页缩略图，副标题带大小；
5. **产物缺失不崩**：``on_result`` 收到不存在的 PDF 走 warning，清单不动。

⚠️ 缩略图缓存（待打印图 + 产物 PDF 页）全部重定向到临时区，不写进真实的
``~/Documents/guji/singletask``。
"""

from __future__ import annotations

from pathlib import Path

NAME = "print_module_page"
DEPENDS: list[str] = ["modules_shell"]
TITLE = "独立PDF排版页（内核契约 / 页序 / 左栏切换）"


def _jpg(path: Path, gray: int = 200) -> Path:
    import numpy as np
    import utils

    utils.imwrite(path, np.full((64, 48, 3), gray, dtype="uint8"))
    return path


def _redirect_caches(page, tmp: Path) -> dict:
    """待打印图缩略图与产物 PDF 页缩略图都落到临时区；原函数收工还原。"""
    import desktop.modules.thumb_source as ts_mod

    real = {
        "singletask_thumbnails_dir": ts_mod.singletask_thumbnails_dir,
    }
    ts_mod.singletask_thumbnails_dir = (
        lambda subtask, book=None, *a, **k: tmp / "thumbs_pdf" / "book"
    )
    page._thumb_cache_dir = lambda: tmp / "thumbs_images"  # type: ignore[method-assign]
    return real


def _restore(real: dict) -> None:
    import desktop.modules.thumb_source as ts_mod

    ts_mod.singletask_thumbnails_dir = real["singletask_thumbnails_dir"]


def run(ctx) -> None:
    from desktop.modules.print.page import PrintModulePage
    from desktop.steps import spec_by_key
    from tests.selftests._context import make_pdf, ok, wait_until

    # ---- 1. 内核契约：print 的产物是单个 PDF 文件 ----
    spec = spec_by_key("print")
    ok("spec_by_key('print').artifact_is_file 为 True（内核不覆盖 outpath）",
       spec.artifact_is_file is True, str(spec.artifact_is_file))

    tmp = Path(ctx.tmp) / "print_module"
    tmp.mkdir(parents=True, exist_ok=True)

    # 待打印图：故意用 1/2/10 钉自然序
    images = tmp / "images"
    images.mkdir()
    _jpg(images / "1.jpg", 150)
    _jpg(images / "2.jpg", 160)
    _jpg(images / "10.jpg", 170)

    page = PrintModulePage()
    real = _redirect_caches(page, tmp)
    try:
        # ---- 2/3. 页序 + 选完源能翻看 ----
        page.control.set_source(images)
        ok("页序 = 文件名自然序（1,2,10，独立页不提供手动排序）",
           [p.name for p in page.source_images()] == ["1.jpg", "2.jpg", "10.jpg"],
           str([p.name for p in page.source_images()]))
        built = wait_until(ctx.app, lambda: page.viewer.strip.count() == 3,
                           timeout=30)
        ok("选完源左栏按待打印图建条目（3 张）",
           built and page.viewer.strip.count() == 3,
           str(page.viewer.strip.count()))
        summary = page.source_summary(page.control.source())
        ok("副标题带待合成张数", "3 张图片" in summary, summary)

        # ---- 5. 产物缺失：warning 不崩、清单不动 ----
        page.on_result(tmp / "不存在.pdf", {})
        ok("on_result 收到不存在的 PDF：不崩、清单保持待打印图",
           page.viewer.strip.count() == 3, str(page.viewer.strip.count()))

        # ---- 4. 生成完成：左栏切成产物 PDF 页缩略图 ----
        pdf = make_pdf(tmp / "成品.pdf", 2)
        page.on_result(pdf, {})
        switched = wait_until(ctx.app, lambda: page.viewer.strip.count() == 2,
                              timeout=30)
        ok("生成完成后左栏切成产物 PDF 的页缩略图（2 页）",
           switched and page.viewer.strip.count() == 2,
           str(page.viewer.strip.count()))
        ok("副标题带产物路径与大小",
           "成品.pdf" in page.header.subtitle_label.text()
           and "KB" in page.header.subtitle_label.text(),
           page.header.subtitle_label.text())
    finally:
        _restore(real)
        page.shutdown_workers()
        page.deleteLater()


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
