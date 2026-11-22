# -*- coding: utf-8 -*-
"""PDF排版「管理图片」弹窗只读**预生成小图**，不现解码原图。

用户 2026-11-02：「这个弹窗打开的时候，显示慢」——弹窗构造时会逐条同步
解码 85 张原图。改为：

1. 进入本步/刷新列表时后台把待打印图渲进 ``thumbnails/print_manage/``；
2. 弹窗只读这份缓存；缓存还没好时**留空图标**（不再回落原图）；
3. 后台生成好一张，弹窗就按**源图路径**就地换掉那一格。

本模块守三点：无缓存时 provider 不给原图、弹窗不落原图；预热后 provider
指向 ``print_manage`` 缓存；弹窗能读到小图。
"""

NAME = "print_manage_thumbs"
DEPENDS: list[str] = ["tasklist"]
TITLE = "PDF排版管理图片缩略图缓存"


def run(ctx) -> None:
    from pathlib import Path

    from PIL import Image
    from PySide6.QtCore import QSize

    from desktop.components.print_manage_dialog import (
        CELL_LABEL_H,
        PrintManagePanel,
        SHOWN_SIZE_ROLE,
        _typical_thumb_height,
    )
    from desktop.utils.files import book_key
    from desktop.workers.thumb_cache_worker import thumb_cache_file
    from tests.selftests._context import ok, pump, wait_until

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    assert tid is not None, "tasklist 模块应已创建主任务"
    d.set_task(tid)

    # 一张「外部插入图」：不在 stages/rembg 下，也不在入口目录，
    # 只能走本轮的 print_manage 缓存分支。
    # 故意用**横版**：竖向框（96×128）会对它留出大段空白，正好验证网格会
    # 按本书真实长宽比收紧。
    root = Path(ctx.tmp) / "print_manage_src"
    root.mkdir(parents=True, exist_ok=True)
    src = root / "外部插图.png"
    Image.new("RGB", (1600, 1200), (200, 80, 60)).save(src)

    cache_dir = repo.print_manage_thumbnails_dir(tid)
    target = thumb_cache_file(cache_dir, src)

    ok("（前置）这是一张还没缓存的大图",
       src.stat().st_size > 0 and not target.exists(), str(target))
    ok("无缓存时 provider 不回落原图（返回 None）",
       d._print_thumb_provider(str(src)) is None,
       str(d._print_thumb_provider(str(src))))

    # 弹窗此时必须留空图标：allow_original=False 的入口就是 provider 返回
    # 假值——它不会去解码 1200x1600 的原图。
    cold = PrintManagePanel(
        entries=[{"file": str(src)}],
        thumb_for=d._print_thumb_provider,
    )
    cold_item = cold.list.item(0)
    ok("无缓存时管理弹窗不落原图（图标空、显示尺寸空）",
       cold_item.icon().isNull() and cold_item.data(SHOWN_SIZE_ROLE) == QSize(),
       f"icon_null={cold_item.icon().isNull()} "
       f"shown={cold_item.data(SHOWN_SIZE_ROLE)}")
    cold.deleteLater()

    d._warm_print_thumbs([str(src)])
    got = wait_until(
        app, lambda: d._print_thumb_provider(str(src)) is not None, timeout=30,
    )
    ok("后台预热后 provider 指向 print_manage 缓存",
       got and Path(d._print_thumb_provider(str(src))) == target,
       f"{d._print_thumb_provider(str(src))} vs {target}")
    ok("缓存文件名按图键命名（不按序号，避免张冠李戴）",
       target.name == f"{book_key(src)}.jpg", target.name)
    ok("缓存确实是缩略图（不等于源图路径）",
       str(target) != str(src))

    hot = PrintManagePanel(
        entries=[{"file": str(src)}],
        thumb_for=d._print_thumb_provider,
    )
    hot_item = hot.list.item(0)
    shown = hot_item.data(SHOWN_SIZE_ROLE)
    ok("有缓存时管理弹窗读到小图（图标非空、尺寸受缩略图框约束）",
       not hot_item.icon().isNull()
       and isinstance(shown, QSize)
       and shown.width() <= PrintManagePanel.THUMB_SIZE.width()
       and shown.height() <= PrintManagePanel.THUMB_SIZE.height(),
       f"shown={shown}")
    # 横版书：网格行高应等于「典型缩略图高度 + 名称区」，而不是固定 128+38
    ok("网格行高按本书图片长宽比收紧（文字下方不再空一大段）",
       hot.list.gridSize().height() == shown.height() + CELL_LABEL_H
       and hot.list.gridSize().height() < PrintManagePanel.CELL_SIZE.height()
       and hot._delegate.thumb_box.height() == shown.height(),
       f"grid={hot.list.gridSize()} shown={shown} "
       f"default={PrintManagePanel.CELL_SIZE}")
    # 一条特别高/特别矮的扉页/插图页不能把整本书的行高带偏
    ok("典型高度忽略特别高或特别矮的离群页",
       _typical_thumb_height([72] * 20 + [128, 30]) == 72,
       str(_typical_thumb_height([72] * 20 + [128, 30])))
    ok("全部同高时典型高度就是该值",
       _typical_thumb_height([96] * 5) == 96,
       str(_typical_thumb_height([96] * 5)))
    hot.deleteLater()
    # 预热线程要等它自己收尾（否则 QThread 在解释器退出时仍活着会让 Qt abort）
    pump(app, 4)
    d.shutdown_workers()
