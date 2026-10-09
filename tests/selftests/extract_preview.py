# -*- coding: utf-8 -*-
"""extract 单缩略图预览自测：翻到哪页就提取哪页，产物落 extract 目录。

背景（用户 2026-10-09）：详情页旧的「PDF 预览 | 提取结果」双标签合并成
:class:`ExtractPreviewWidget` 单控件——左栏一份 PDF 页缩略图；切到某页时
``stages/extract/N.<ext>`` 已存在就显示产物，没有就**真的提取落盘**后显示
（与批量提取同一条渲染实现 ``utils.pdf_extract.extract_single_page``）。
"""

NAME = "extract_preview"
DEPENDS: list[str] = []
TITLE = "extract 单缩略图预览（按页按需提取）"


def run(ctx) -> None:
    from tests.selftests._context import ok, pump, wait_until

    app = ctx.app
    from desktop.components.viewers import ExtractPreviewWidget
    from utils.pdf_extract import extract_single_page

    assert ctx.tmp is not None
    from tests.selftests._context import make_pdf

    pdf = make_pdf(ctx.tmp / "提取预览样例.pdf", 3)
    # ⚠️ utils 层与控件层用**不同**产物目录：控件层要测的是"没有产物 →
    # 现场提取"，共用目录会让第 1 页提前存在、走"已有产物"分支。
    utils_out = ctx.tmp / "extract_utils_out"
    out_dir = ctx.tmp / "extract_preview_out"
    thumb_dir = ctx.tmp / "extract_preview_thumbs"

    # ---- utils 层：单页提取与批量同一条实现 ----
    result = extract_single_page(str(pdf), 0, str(utils_out), ext="jpg")
    ok("extract_single_page 成功", result["ok"], str(result))
    ok("产物落在指定目录且按页号命名",
       result["path"] is not None
       and (utils_out / "1.jpg").is_file(), str(result))
    ok("返回了页面尺寸", result["w"] > 0 and result["h"] > 0, str(result))
    ok("失败页给出 err（页号越界）",
       not extract_single_page(str(pdf), 99, str(out_dir))["ok"])

    # ---- 控件层：切页即提取、有产物显示产物 ----
    viewer = ExtractPreviewWidget()
    saved: list[str] = []
    viewer.extract_saved.connect(saved.append)
    viewer.set_params_provider(lambda: {"ext": "jpg", "zoom": 1,
                                        "quick": True, "dpi": 200})
    viewer.set_extract_dir(out_dir)
    viewer.set_pdf(pdf, cache_dir=thumb_dir)
    # 缩略图 pass 异步：metadata 到达后条目建好并自动选中第 1 页
    ok("等缩略图条目建好",
       wait_until(app, lambda: viewer.strip.count() == 3, timeout=15))
    pump(app, times=6)
    # 自动选中第 0 行 → 立即触发单页提取（此前这是"纯预览渲染，不落盘"）
    ok("翻到第 1 页即提取落盘",
       wait_until(app, lambda: (out_dir / "1.jpg").is_file(), timeout=15))
    ok("extract_saved 信号发出（宿主登记尺寸/清单的钩子）",
       wait_until(app, lambda: len(saved) >= 1, timeout=10), str(saved))
    ok("大图显示的是第 1 页的提取结果",
       wait_until(app, lambda: viewer._shown_extract_page == 0
                  and viewer.view.has_image, timeout=15),
       f"shown={viewer._shown_extract_page}")
    ok("第 2 页还没有产物（没有一次全提）", not (out_dir / "2.jpg").exists())

    # 切到第 3 页 → 现场提取第 3 页
    viewer.strip.setCurrentRow(2)
    ok("切页触发第 3 页提取",
       wait_until(app, lambda: (out_dir / "3.jpg").is_file(), timeout=15))
    ok("大图切到第 3 页产物",
       wait_until(app, lambda: viewer._shown_extract_page == 2, timeout=15))
    ok("第 2 页仍未提取（只提看过的页）", not (out_dir / "2.jpg").exists())

    # 宿主刷新路径：产物已存在的页直接显示，不重复提取、不发起提取
    viewer.set_extract_dir(out_dir)
    pump(app, times=4)
    ok("宿主刷新后仍显示当前页产物", viewer._shown_extract_page == 2
       and viewer.view.has_image)

    # ---- 换文档：提取态作废（代际号守卫） ----
    viewer.set_pdf(None)
    pump(app, times=4)
    ok("释放 PDF 后提取态清空",
       viewer._pdf_path is None and not viewer._extracting
       and viewer._shown_extract_page is None)

    viewer.shutdown_workers()
    viewer.deleteLater()
    pump(app, times=4)
