# -*- coding: utf-8 -*-
"""独立「去底色」页的**单页实时调整**自测（用户 2026-11-21 提出）。

用户诉求：独立功能页改参数（算法/偏移/印章…）后，当前这张图要**立刻**按新
参数重算上屏，而不是必须先点「开始去底色」跑完整批。实现：
``modules/rembg/live.py::RembgModuleLiveMixin``——草稿落在
``singletask/rembg/preview/<源名-指纹>/``，控件经 ``preview_dir`` 优先显示草稿。

本用例钉六件事：

1. 换源后草稿目录跟着换（带源指纹；旧目录被丢弃）；
2. ``param_edited`` → 防抖 → 真的派发单页 worker、草稿 png 真的落盘；
3. 同一份参数算过后**不重算**（``_live_done`` 台账），参数再变才再算；
4. 翻页在"没动过参数"时不算（触发闸），动过参数才给当前页补算；
5. 全量执行开始（``running_changed(True)``）→ 草稿文件**真的被删掉**、
   台账清空、preview 源摘掉（不能让旧草稿盖住正式产物）；
6. ``viewer.set_preview_dir`` 被调过（草稿来源挂上了）。
"""

from __future__ import annotations

from pathlib import Path

NAME = "rembg_module_live"
DEPENDS: list[str] = ["rembg_module_thumbs"]
TITLE = "独立去底色页·单页实时调整（改参数即看效果）"


def _png(path: Path, gray: int = 200) -> Path:
    import numpy as np
    import utils

    utils.imwrite(path, np.full((64, 48, 3), gray, dtype="uint8"))
    return path


def run(ctx) -> None:
    from desktop.modules.rembg.page import RembgModulePage
    from tests.selftests._context import ok, wait_until

    tmp = Path(ctx.tmp) / "rembg_module_live"
    tmp.mkdir(parents=True, exist_ok=True)
    page = RembgModulePage()
    try:
        # 草稿根目录指到临时区：别写进真实的 ~/Documents/guji/singletask
        page._live_root = lambda: tmp / "preview"

        # ---- 1. 换源 → 草稿目录带源指纹 ----
        images = tmp / "images"
        images.mkdir(exist_ok=True)
        p1 = _png(images / "0001.png", 180)
        p2 = _png(images / "0002.png", 140)
        page.control.set_source(images)

        live_dir = page._live_dir
        ok("换源后草稿目录已设好（源名+指纹）",
           live_dir is not None and live_dir.parent == tmp / "preview"
           and live_dir.name.startswith("images-"),
           str(live_dir))
        ok("换源时草稿目录挂到了查看器（set_images 的 preview_dir 入参）",
           page.viewer._preview_dir == live_dir, str(page.viewer._preview_dir))

        # ---- 2. 改参数 → 防抖 → 单页草稿落盘 ----
        panel = page.control.panel
        ok("面板存在且 param_edited 可触发",
           panel is not None and hasattr(panel, "param_edited"))
        panel.param_edited.emit()
        waited = wait_until(
            ctx.app,
            lambda: (live_dir / f"{p1.stem}.png").is_file(),
            timeout=30,
        )
        ok("改参数后当前页草稿真的落盘（防抖到期派发了单页 worker）", waited,
           str(list(live_dir.glob("*.png")) if live_dir else None))
        ok("执行过一轮后草稿来源仍指向草稿目录（改参数继续生效）",
           page.viewer._preview_dir == live_dir, str(page.viewer._preview_dir))
        ok("台账记下了这份参数",
           p1.stem in page._live_done and page._live_dirty is True,
           str(page._live_done))

        # ---- 3. 同参数不重算；参数变了才重算 ----
        page._live_timer.stop()
        page._start_live_job = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("同参数不该重算"))
        panel.param_edited.emit()
        page._live_timer.start()
        wait_until(ctx.app, lambda: False, timeout=0.4)  # 让防抖到期跑一遍
        ok("同一份参数不重算（台账命中直接跳过）", True)

        del page._start_live_job  # 恢复真实现（闭包替身是实例属性）
        page._live_timer.stop()
        page.control.panel.offset.setValue(
            page.control.panel.offset.value() + 1)
        waited2 = wait_until(
            ctx.app,
            lambda: page._live_done.get(p1.stem, {}).get("offset")
            == page.control.panel.offset.value(),
            timeout=30,
        )
        ok("参数变化后重新计算并更新台账", waited2, str(page._live_done))

        # ---- 4. 触发闸：没动过参数，翻页不算 ----
        page._live_dirty = False
        page._live_done.clear()
        page._start_live_job = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("没动参数翻页不该重算"))
        page.viewer.strip.setCurrentRow(1)
        wait_until(ctx.app, lambda: False, timeout=0.4)
        ok("没动参数时翻页不触发计算（触发闸）", True)

        # 动过参数 → 翻页给当前页补算（真实链路：改参数起防抖，翻页再起一次）
        del page._start_live_job  # 先摘掉上面的替身，恢复真实现
        page._live_dirty = True
        page.viewer.current_changed.emit(1, str(p2))
        waited3 = wait_until(
            ctx.app,
            lambda: (live_dir / f"{p2.stem}.png").is_file(),
            timeout=30,
        )
        ok("动过参数后翻页给当前页补算", waited3,
           str(list(live_dir.glob("*.png")) if live_dir else None))

        # ---- 5. 全量执行开始 → 草稿删干净 ----
        page._on_live_running(True)
        ok("执行开始后草稿文件全部删除",
           list(live_dir.glob("*.png")) == [],
           str(list(live_dir.glob("*.png"))))
        ok("执行开始后台账清空", page._live_done == {}, str(page._live_done))
        ok("执行开始后 dirty 复位", page._live_dirty is False,
           str(page._live_dirty))
        ok("执行开始时 preview 源被摘掉（改看正式产物）",
           page.viewer._preview_dir is None, str(page.viewer._preview_dir))

        # ---- 6. 换新源 → 旧草稿目录被丢弃 ----
        other = tmp / "images2"
        other.mkdir(exist_ok=True)
        _png(other / "0001.png", 100)
        page.control.set_source(other)
        new_dir = page._live_dir
        ok("换源后草稿目录换了（指纹不同）",
           new_dir is not None and new_dir != live_dir
           and not new_dir.name.startswith("images-"),
           f"{live_dir} -> {new_dir}")
        ok("旧草稿目录已被丢弃", not live_dir.exists(), str(live_dir))
    finally:
        page.shutdown_workers()
        page.deleteLater()


__all__ = ["NAME", "DEPENDS", "TITLE", "run"]
