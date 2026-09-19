# -*- coding: utf-8 -*-
"""第四步「翻页」必须刷新右侧预览（版面编辑器）。

背景（用户实测反馈）：第四步预览「时好时坏，尤其是翻页；切换原图模式再切回来
就恢复正常」。根因不在画布、也不在排版，而在**通知链**：

    ThumbStrip 只在 ``itemClicked`` 时发 ``current_path_changed``

键盘方向键翻页、以及任何程序化 ``setCurrentRow`` 只改 ``currentRow`` 却不产生
点击 —— 宿主收不到通知，画布一直停在上一页的图上。切视图模式之所以能"修好"，
是因为 ``_set_mode`` 会调 ``_load_display()``，而它读的是 ``currentRow``（对的）。

这里守的是"当前行一变，预览就得跟着变"，且刻意**不用**鼠标点击来翻页，
正是为了钉住这条漏掉的信号路径。
"""

NAME = "print_page_flip"
DEPENDS: list[str] = []
TITLE = "第四步翻页刷新预览"

SIZES = [(1200, 1800), (800, 2000), (1600, 1200)]


def _tmp_png(path, w: int, h: int):
    from PySide6.QtGui import QColor, QImage, QPainter

    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#f2f2f2"))
    painter = QPainter(img)
    painter.setPen(QColor("#333333"))
    painter.drawRect(10, 10, w - 20, h - 20)
    painter.end()
    img.save(str(path))
    return path


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok, pump

    from desktop.components.viewers.print_preview import PrintPreviewWidget

    tmp = Path(ctx.tmp) / "print_page_flip"
    tmp.mkdir(parents=True, exist_ok=True)
    app = ctx.app

    full = {
        "paper_size": "A4",
        "orientation": "landscape",
        "page_margins": [20, 20, 20, 20],
        "left_page_margins": [20, 20, 20, 20],
        "right_page_margins": [20, 20, 20, 20],
        "title_printing": False,
        "page_number": False,
    }
    files = [
        _tmp_png(tmp / f"{i + 1:04d}.png", w, h)
        for i, (w, h) in enumerate(SIZES)
    ]

    widget = PrintPreviewWidget(params_provider=lambda: dict(full))
    widget.resize(1000, 700)
    widget.canvas.resize(600, 500)
    widget.show()
    pump(app, 6)
    widget.set_entries(
        [{"file": str(f), "label": f.stem} for f in files]
    )
    pump(app, 8)

    def shown() -> tuple[int, int] | None:
        img = widget.canvas._image
        return None if img is None else (img.width(), img.height())

    ok("默认停在版面编辑模式", widget._mode == "layout", widget._mode)
    ok("首屏显示第 1 页的图",
       shown() == SIZES[0], f"{shown()} 期望 {SIZES[0]}")
    ok("说明行标出第 1 页", "第 1/3 页" in widget.caption.text(),
       widget.caption.text())

    # ---- 核心：非鼠标点击的翻页（键盘/程序化改当前行）也必须刷新 ----
    for i in (1, 2):
        widget.strip.setCurrentRow(i)
        pump(app, 8)
        ok(f"翻到第 {i + 1} 页：画布换成该页的图",
           shown() == SIZES[i], f"{shown()} 期望 {SIZES[i]}")
        ok(f"翻到第 {i + 1} 页：说明行同步",
           f"第 {i + 1}/3 页" in widget.caption.text(),
           widget.caption.text())
        ok(f"翻到第 {i + 1} 页：编辑下标同步",
           widget._canvas_index == i, str(widget._canvas_index))

    # ---- 缩略图条必须真的在「当前行变化」时通知，而不只是点击时 ----
    fired: list[int] = []
    widget.strip.current_path_changed.connect(lambda row, _p: fired.append(row))
    widget.strip.setCurrentRow(0)
    pump(app, 4)
    ok("当前行变化会发出 current_path_changed（不只点击才发）",
       0 in fired, str(fired))

    # ---- 切到原图再切回版面编辑，仍停在正确的那一页 ----
    widget.strip.setCurrentRow(2)
    pump(app, 6)
    widget._set_mode("original")
    pump(app, 6)
    widget._set_mode("layout")
    pump(app, 8)
    ok("切原图再切回版面编辑，仍是第 3 页",
       shown() == SIZES[2] and widget._canvas_index == 2,
       f"{shown()} idx={widget._canvas_index}")

    widget.close()
