# -*- coding: utf-8 -*-
"""第三步（去底色）预览的**显示源解析**自测——不依赖 extract/rembg 管道。

为什么要单独一个模块：管道级断言在 ``rembg.py``，但它 ``DEPENDS=["detect"]``
→ 一路依赖到 ``extract`` 的真实子进程，**跑不了管道的环境里整条都跳过**。
于是第三步的"显示哪张图"这段逻辑长期没有可执行的护栏——2026-09-24 把区域
规则抽成 ``_resolve_source()`` 时漏改一处 ``result_img``，``_load_display``
直接 ``NameError``（预览永远停在"正在加载…"），全部护栏照样绿。

本模块用**临时图片 + 注入的 provider** 直接驱动 `_load_display`，不碰管道。
⚠️ provider 必须经 ``set_images(...)`` 传进去：``set_images`` 会把三个
provider 一律赋成入参（默认 None），先在控件上设、再调 set_images 会被清掉。

断言线：
1. 无去底色结果 + 「去底色结果」形态 → 回落原图，说明文案点明"尚未生成"；
2. 有去底色结果 → 取结果图；
3. 切到「原图」形态 → 即使有结果也显示原图；
4. area=1 单框 → 区域参数是「该框 + border」；
5. area=2 双框 → 区域参数带**全部**框（不是并集单框）；
6. 区域参数抛异常 → 提示「区域计算失败」，且**不抛**出去；
7. 图片不存在 → 提示「暂无图片」，且**不抛**出去；
8. 放大弹窗与主预览**同源**：源不存在时 `_zoom_target` 也返回 None；
9. 反复切换形态/重载/刷新都不得抛异常（本次回归的形态）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

NAME = "rembg_preview"
DEPENDS: list[str] = []
TITLE = "第三步预览显示源"

BOX_L = [10, 20, 300, 700]
BOX_R = [320, 20, 590, 700]


def run(ctx) -> None:
    from PySide6.QtGui import QColor, QImage

    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget
    from tests.selftests._context import ok, pump

    app = ctx.app
    tmp = Path(tempfile.mkdtemp(prefix="guji_rembg_preview_"))

    src = tmp / "src" / "1.png"
    src.parent.mkdir()
    image = QImage(600, 800, QImage.Format_RGB32)
    image.fill(QColor("#ffffff"))
    image.save(str(src))

    result_dir = tmp / "rembg"
    result_dir.mkdir()
    result = result_dir / "1.png"          # 与源同名 → 会被认成"该页的结果"
    result_image = QImage(600, 800, QImage.Format_RGB32)
    result_image.fill(QColor("#f0e8d8"))
    result_image.save(str(result))
    no_result_dir = tmp / "no_such_dir"    # 目录不存在 = 还没有结果

    def providers(area=1, border=None, boxes=(BOX_L, BOX_R)):
        """provider 与控件一起给（set_images 会把它们原样装到控件上）。"""
        return (lambda _p: list(boxes), lambda: (area, border))

    def load(rembg_dir, pair=(None, None), paths=(src,)):
        """装清单 + 驱动一次显示；异常必须冒出来，才能被本模块抓住。"""
        widget = RembgPreviewWidget()
        widget.set_images(
            list(paths), rembg_dir,
            boxes_provider=pair[0], region_params_provider=pair[1],
        )
        widget._load_display()  # 显式再来一次：这是出过 NameError 的那个入口
        pump(app, times=4)
        return widget

    # ---- 1. 没有去底色结果：回落原图 + 明确文案 ----
    widget = load(no_result_dir, providers())
    ok("没有结果时回落到原图并加载成功", widget.view.has_image, widget.view.text())
    ok("没有结果时说明文案点明「尚未生成」",
       "尚未生成去底色结果" in widget.toggle_caption.text(),
       widget.toggle_caption.text())
    ok("没有结果时放大弹窗仍可取源（显示原图）",
       widget._zoom_target(0) is not None, "")
    widget.deleteLater()

    # ---- 2. 有结果：取结果图 ----
    widget = load(result_dir, providers())
    ok("有结果时加载成功", widget.view.has_image, "")
    ok("有结果时说明文案是「去底色结果」",
       widget.toggle_caption.text().startswith("去底色结果"),
       widget.toggle_caption.text())
    target = widget._zoom_target(0)
    ok("有结果时放大弹窗取到同一条目",
       target is not None and target.stem == "1", "")

    # ---- 3. 切到「原图」形态：有结果也显示原图 ----
    widget._set_mode("original")
    pump(app, times=4)
    ok("切到原图形态后加载成功且文案是「原图」",
       widget.view.has_image and widget.toggle_caption.text().startswith("原图"),
       widget.toggle_caption.text())
    widget.deleteLater()

    # ---- 4/5. 区域参数：area=1 单框 vs area=2 双框 ----
    widget = load(result_dir, providers(area=1, border="5"))
    entry = widget._entries[0]
    source, effect, has_result, _error = widget._resolve_source(entry)
    ok("area=1 单框条目：区域参数=该框 + border",
       effect == {"boxes": [entry["box"]], "area": 1, "border": "5"},
       f"{effect} / entry.box={entry['box']}")
    ok("area=1 能取到结果图（结果优先）", has_result and source == result,
       str(source))
    widget.deleteLater()

    widget = load(result_dir, providers(area=2, border=None))
    _source, effect, _has, _err = widget._resolve_source(widget._entries[0])
    ok("area=2 双框：区域参数带全部框（不是并集单框）",
       effect["area"] == 2 and len(effect["boxes"]) == 2, str(effect))
    widget.deleteLater()

    # ---- 6. 区域参数抛异常：提示而非崩溃 ----
    def boom():
        raise ValueError("参数填了一半")

    widget = load(result_dir, (lambda _p: [BOX_L, BOX_R], boom))
    ok("区域参数异常时给出提示且不抛异常",
       "区域计算失败" in widget.view.text(), widget.view.text())
    ok("区域参数异常时放大弹窗不给源（与主预览一致）",
       widget._zoom_target(0) is None, "")
    widget.deleteLater()

    # ---- 7. 图片不存在：提示而非崩溃 ----
    widget = load(result_dir, providers(), paths=(tmp / "missing.png",))
    ok("源图不存在时给出提示且不抛异常",
       "暂无图片" in widget.view.text(), widget.view.text())
    ok("源图不存在时放大弹窗不给源", widget._zoom_target(0) is None, "")
    widget.deleteLater()

    # ---- 9. 回归形态：反复切换形态/重载/刷新不得抛异常 ----
    widget = load(result_dir, providers())
    crashed = None
    try:
        for mode in ("original", "result", "original"):
            widget._set_mode(mode)
            pump(app, times=3)
        widget.set_images([src], result_dir)   # 清单未变 → 走"只重载"分支
        pump(app, times=3)
        widget.refresh_display()               # 区域参数变化后的刷新入口
        pump(app, times=3)
    except Exception as exc:  # noqa: BLE001
        crashed = f"{type(exc).__name__}: {exc}"
    ok("反复切换形态/重载/刷新都不抛异常（NameError 形态的回归）",
       crashed is None, crashed or "")
    widget.deleteLater()
