# -*- coding: utf-8 -*-
"""独立「PDF排版」页的**单页打印效果**自测（用户 2026-11-21 提出）。

用户诉求：独立功能页调纸张/边距/标题/页码后，左栏**当前这张图**要立刻按新
参数重排成"打印效果"，不必先点「生成PDF」。实现：
``ImageViewerWidget.set_preview_spec_provider`` ＋
``modules/print/page.py::_preview_spec``（合成走
``PreviewWorker(print_spec=...)``，与任务流程第四步同一条链）。

本用例钉五件事：

1. 页面构造时 provider 已挂上；``_preview_spec_for`` 能要回字典；
2. ``_preview_spec`` 给出完整的四件套（args/index/total/name）＋ ``nodes``
   按**列表位置**解析（worker 拿不到条目清单，交给 plan 内部兜底匹配不上——
   任务流程 2026-09-29 踩过同一个坑）；
3. 面板参数填了一半（``get_args`` 抛异常）→ 返回 ``None``（显示原图），
   不阻断预览；
4. ``params_changed`` → 防抖到期 → ``viewer.refresh_current`` 被调；
5. ``PreviewWorker(print_spec=...)`` 对一张真图真的渲染出"排在纸面上"的
   效果图（尺寸是纸面比例，不是原图尺寸）。
"""

from __future__ import annotations

from pathlib import Path

NAME = "print_module_live"
DEPENDS: list[str] = ["print_module_page"]
TITLE = "独立PDF排版页·单页打印效果（改参数即看效果）"


def _png(path: Path, w: int = 480, h: int = 360, gray: int = 200) -> Path:
    import numpy as np
    import utils

    utils.imwrite(path, np.full((h, w, 3), gray, dtype="uint8"))
    return path


def run(ctx) -> None:
    from desktop.modules.print.page import PrintModulePage
    from tests.selftests._context import ok, wait_until

    tmp = Path(ctx.tmp) / "print_module_live"
    tmp.mkdir(parents=True, exist_ok=True)
    page = PrintModulePage()
    try:
        # ---- 1. provider 已挂上 ----
        ok("页面构造后大图挂了合成参数提供者",
           page.viewer._preview_spec_provider is not None)

        images = tmp / "images"
        images.mkdir(exist_ok=True)
        p1 = _png(images / "0001.png")
        p2 = _png(images / "0002.png", 600, 400, 120)
        page.control.set_source(images)
        ok("给源后左栏条目建好", page.viewer.strip.count() == 2,
           str(page.viewer.strip.count()))

        # ---- 2. _preview_spec 四件套 + nodes 按列表位置解析 ----
        spec = page._preview_spec(str(p1), 0, 2)
        ok("当前页的合成参数四件套齐全",
           spec is not None and spec.get("index") == 0
           and spec.get("total") == 2 and spec.get("name") == "0001"
           and isinstance(spec.get("args"), dict),
           str({k: spec.get(k) for k in ("index", "total", "name")}
               if spec else None))
        ok("参数里带了人能看懂的说明文案（note）",
           bool(str(spec.get("note") or "").strip()) if spec else False)
        # 标题切换节点（第 2 页起换标题）→ nodes 必须在宿主侧按列表位置解析好，
        # 不能是空。add_row 会发 changed→params_changed，顺手也验证了第 4 节的链路
        panel = page.control.panel
        ok("面板有标题节点容器", hasattr(panel, "nodes_list"))
        page._live_timer.stop()
        page.control.panel.nodes_list.add_row(page=2, title="卷二")
        page._live_timer.stop()
        spec2 = page._preview_spec(str(p2), 1, 2)
        ok("标题节点按列表位置解析进 spec（第2页起换标题）",
           spec2 is not None and spec2.get("nodes"),
           str(spec2.get("nodes") if spec2 else None))
        ok("viewer 能向宿主要回这一页的 spec",
           page.viewer._preview_spec_for(str(p1), 0) is not None)

        # ---- 3. 参数填了一半 → 返回 None，不阻断 ----
        # ⚠️ provider 是构造时绑定的方法，替身要打在它内部真正调用的
        # ``panel.get_args`` 上（项目纪律：替身补丁打在"使用方"的命名上）
        original_get_args = panel.get_args

        def broken_get_args():
            raise ValueError("半截参数")

        panel.get_args = broken_get_args  # type: ignore[method-assign]
        ok("参数填了一半 → 这一帧退回原图（spec 为 None，不阻断）",
           page.viewer._preview_spec_for(str(p1), 0) is None)
        panel.get_args = original_get_args  # type: ignore[method-assign]

        # ---- 4. params_changed → 防抖 → refresh_current ----
        refreshes: list[int] = []
        original_refresh = page.viewer.refresh_current

        def spy_refresh() -> None:
            refreshes.append(1)
            original_refresh()

        page.viewer.refresh_current = spy_refresh  # type: ignore[method-assign]
        panel.params_changed.emit()
        refreshed = wait_until(ctx.app, lambda: len(refreshes) >= 1, timeout=5)
        ok("参数变化（防抖到期）触发了当前页重排", refreshed,
           str(len(refreshes)))

        # ---- 5. 真渲染：print_spec 出来的是"纸面效果" ----
        from desktop.workers import PreviewWorker

        args = panel.get_args()
        worker = PreviewWorker(
            p1,
            longest_edge=0,
            print_spec={**spec, "args": args, "nodes": spec2.get("nodes", [])
                        if spec2 else []},
        )
        results: list[QImage] = []
        failures: list[str] = []
        worker.finished.connect(lambda _p, image, _s: results.append(image))
        worker.failed.connect(lambda _p, msg: failures.append(msg))
        worker.run()  # 直接调 run（离屏同步跑，不起线程）
        ok("print_spec 渲染成功（无失败）", not failures and results,
           str(failures))
        if results:
            img = results[0]
            # 纸面比例：按参数里的纸张方向算（横版 ≈ 1.414 / 竖版 ≈ 0.707），
            # 绝不等于原图的 480/360 ≈ 1.333
            orientation = str(args.get("orientation") or "landscape")
            expected = 1.4142 if "land" in orientation.lower() else 0.7071
            ratio = img.width() / img.height()
            ok("渲染出的是纸面比例（按参数方向），不是原图比例",
               abs(ratio - expected) < 0.05,
               f"{img.width()}x{img.height()} ratio={ratio:.3f} "
               f"expected={expected:.3f} ({orientation})")
            ok("页面上真的画了内容（非全白）",
               img.pixelColor(img.width() // 2, img.height() // 2).alpha() > 0)
    finally:
        page.shutdown_workers()
        page.deleteLater()


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
