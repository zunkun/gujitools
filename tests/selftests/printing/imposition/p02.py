# -*- coding: utf-8 -*-
"""1b. 页面效果缩略图**实体**（用户 2026-10-09） / 2. 落盘与清理 / 2a-2. 白底导出（2026-10-13 用户：singletask 导出不要透明底） / 2a-3. 去底色导出目录衔接（2026-10-13 用户） / 2a-4. 空态引导层行为（离屏真控件）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import GREEN, RED, _mk, _names, _px_near, ROOT
    from PIL import Image
    from desktop.components.imposition.view import ImpositionViewWidget
    from pathlib import Path
    from desktop.services import imposition as S
    from PIL import Image as _I2
    from PIL import Image as _PILImage
    from desktop.services import rembg_export as _RX
    import os as _os
    from desktop.components.imposition.page_thumb import (
        compose_page_thumb_from_files,
        load_page_index,
        page_signature,
        thumb_file_name,
        write_page_index,
    )
    from tests.selftests._context import make_pdf, ok, pump
    import os as _os

    from desktop.components.imposition.page_thumb import (
        compose_page_thumb_from_files,
        load_page_index,
        page_signature,
        thumb_file_name,
        write_page_index,
    )

    _pt = compose_page_thumb_from_files(st.made, edge=128)
    ok(
        "页面效果缩略图：能从源图文件合成出来（非空、横向对开）",
        _pt is not None and not _pt.isNull() and _pt.width() > _pt.height(),
        f"{None if _pt is None else (_pt.width(), _pt.height())}",
    )
    ok(
        "页面效果缩略图：左半是左槽图、右半是右槽图（像素级）",
        _pt is not None
        and _px_near(_pt, _pt.width() // 4, _pt.height() // 2, GREEN)
        and _px_near(_pt, _pt.width() * 3 // 4, _pt.height() // 2, RED),
        "左半应 GREEN / 右半应 RED",
    )
    ok(
        "页面效果缩略图：坏页返回 None",
        compose_page_thumb_from_files({"items": []}) is None,
    )

    # 内容签名（文件指纹口径）：版面/源图文件任一变了都得变
    _sig0 = page_signature(st.made)
    ok(
        "内容签名：同一页 ⇒ 签名稳定",
        _sig0 is not None and _sig0 == page_signature(st.made),
    )
    _moved_page = S.normalize_page(st.made)
    assert _moved_page is not None
    _moved_page["items"][0]["rect"][0] += 7.0
    ok(
        "内容签名：版面动了 ⇒ 签名变（拖图后缩略图要跟上）",
        page_signature(_moved_page) != _sig0,
    )
    _st_b = st.b.stat()
    _os.utime(st.b, ns=(_st_b.st_atime_ns, _st_b.st_mtime_ns + 1_000_000))
    ok(
        "内容签名：源图文件被覆盖（mtime 变）⇒ 签名变（编辑覆盖后要重生成）",
        page_signature(st.made) != _sig0,
    )
    _os.utime(st.b, ns=(_st_b.st_atime_ns, _st_b.st_mtime_ns))
    ok("内容签名：源图复原 ⇒ 签名复原", page_signature(st.made) == _sig0)
    ok("内容签名：空页返回 None", page_signature({"items": []}) is None)

    # 映射数据：pageN 命名 + index.json 往返（用户要求"做好映射数据"）
    _idx_dir = st.tmp / "page_thumbs_probe"
    ok(
        "映射数据：页号（0 基）→ page1.jpg 从第一页起数",
        thumb_file_name(0) == "page1.jpg" and thumb_file_name(9) == "page10.jpg",
    )
    ok(
        "映射数据：写入成功（index.json 落盘）",
        write_page_index(_idx_dir, {0: _sig0, 1: "abc"}, 256)
        and (_idx_dir / "index.json").is_file(),
    )
    ok(
        "映射数据：读回一致（页号 ↔ 签名）",
        load_page_index(_idx_dir, 256) == {0: _sig0, 1: "abc"},
    )
    ok(
        "映射数据：边长不符 ⇒ 当空表（整批重生成）",
        load_page_index(_idx_dir, 512) == {},
    )
    (_idx_dir / "index.json").write_text("垃圾", encoding="utf-8")
    ok("映射数据：坏档 ⇒ 当空表（不抛异常）", load_page_index(_idx_dir, 256) == {})
    out = st.tmp / "sweep"
    out.mkdir()
    _mk(out / "0009.png", (0, 0, 0), (8, 8))  # 上一轮多出来的页
    written = S.compose_doc({"pages": [st.made, st.made]}, out)
    ok(
        "落盘按页码命名 0001/0002",
        _names(written) == ["0001.png", "0002.png"],
        str(_names(written)),
    )
    ok("上一轮多出来的 0009.png 被清掉", not (out / "0009.png").exists())
    S.compose_doc({"pages": []}, out)
    ok("清空拼版后产物目录也清空", list(out.glob("*.png")) == [])
    white_out = st.tmp / "sweep_white"
    S.compose_doc({"pages": [st._diag_page]}, white_out, background=S.WHITE_BACKGROUND)
    _wpath = white_out / "0001.png"
    with Image.open(_wpath) as _wim:
        _wim.load()
        _wrgba = _wim.convert("RGBA")
    ok(
        "compose_doc 白底导出：产物角落不透明白、内容照旧",
        _wrgba.getpixel((2, 2)) == (255, 255, 255, 255)
        and _wrgba.getpixel((400, 360))[:3] == GREEN,
        f"corner={_wrgba.getpixel((2, 2))} content={_wrgba.getpixel((400, 360))}",
    )
    # 手改整页盖回（flatten_onto_background）：透明 PNG 压到白底
    _flat_src = st.tmp / "flat-src.png"
    _PILImage.new("RGBA", (40, 30), (0, 0, 0, 0)).save(_flat_src)
    _flat_dst = st.tmp / "flat-dst.png"
    S.flatten_onto_background(_flat_src, _flat_dst, S.WHITE_BACKGROUND)
    with Image.open(_flat_dst) as _fim:
        _fim.load()
        _fmode, _fpx = _fim.mode, _fim.convert("RGBA").getpixel((5, 5))
        _ftrns = "transparency" in _fim.info
    ok(
        "手改整页压白：透明源 → 不透明白底 PNG",
        # ⚠️ 不钉死 ``"RGB"``（2026-11-15）：成品落盘改走**紧凑编码**，
        #    纯黑白页会写成调色板（P）。要钉的是**语义**——没有 alpha 通道、
        #    角落是白；"用哪种 PNG 色彩类型"是实现细节（见
        #    ``services.imposition._save_page_atomic``）。
        _fmode in ("RGB", "P") and not _ftrns
        and _fpx == (255, 255, 255, 255),
        f"mode={_fmode} pixel={_fpx} transparency={_ftrns}",
    )
    from desktop.services import rembg_export as _RX

    _rembg_out = st.tmp / "rembg_export_dir"
    _rembg_out.mkdir()
    # 白底图上画一块红：转透明后白底 α=0、红块必须逐位不变
    from PIL import Image as _I2

    _white_page = _rembg_out / "page1.png"
    _img = _I2.new("RGB", (60, 40), (255, 255, 255))
    _img.paste((200, 30, 30), (10, 10, 30, 30))
    _img.save(_white_page)
    _other_dir = st.tmp / "plain_dir"
    _other_dir.mkdir()
    _plain_page = _mk(_other_dir / "page2.png", (255, 255, 255), (60, 40))

    ok("没写标记的目录 is_marked=False", not _RX.is_marked(_rembg_out))
    _RX.write_marker(_rembg_out)
    ok("write_marker 后 is_marked=True（标记文件是 json 非图片）",
       _RX.is_marked(_rembg_out)
       and _RX.marker_path(_rembg_out).suffix == ".json")
    _p, _m = _RX.split_marked([_white_page, _plain_page, _other_dir / "x.png"])
    ok("split_marked：带标记目录的图进 marked、其余原样 plain",
       _m == [_white_page] and _p == [_plain_page, _other_dir / "x.png"],
       f"marked={_m} plain={_p}")

    _copy = _RX.transparent_copy_path(_white_page)
    ok("副本路径在 singletask 缓存区且带指纹后缀",
       "rembg_transparent" in str(_copy)
       and _copy.stem.startswith("page1-") and _copy.suffix == ".png",
       str(_copy))
    ok("同一源指纹 → 同一副本路径；源变化 → 新路径",
       _copy == _RX.transparent_copy_path(_white_page)
       and _copy != _RX.transparent_copy_path(_plain_page))

    _before = _white_page.read_bytes()
    # ⚠️ 副本内容验证写到 **tmp**，不碰真实 singletask 缓存区（
    # transparent_copy_path 只算路径，上一条断言已经覆盖命名规则）
    _copy_real = _copy
    _copy = st.tmp / "copy-probe.png"
    _RX.make_transparent_copy(_white_page, _copy)
    with Image.open(_copy) as _cim:
        _cim.load()
        _crgba = _cim.convert("RGBA")
    ok("副本：白底 α=0（RGB 保持 255）、红块逐位不变",
       _crgba.getpixel((2, 2))[3] == 0
       and _crgba.getpixel((2, 2))[:3] == (255, 255, 255)
       and _crgba.getpixel((15, 15))[:3] == (200, 30, 30)
       and _crgba.getpixel((15, 15))[3] == 255,
       f"bg={_crgba.getpixel((2, 2))} red={_crgba.getpixel((15, 15))}")
    ok("**原图绝不被改动**（字节级对比）",
       _white_page.read_bytes() == _before)
    ok("worker 用的正是同一个指纹路径口径（真实缓存路径未被测试写入）",
       not _copy_real.exists())

    # 接线护栏：去底色页导出成功必须落标记；拼图页选源必须走预备流程
    _rembg_page_src = (ROOT
                       / "desktop/modules/rembg/page.py").read_text(encoding="utf-8")
    _impo_page_src = (ROOT
                      / "desktop/modules/imposition/page.py").read_text(encoding="utf-8")
    ok("去底色页 on_result 落标记（write_marker）",
       "write_marker" in _rembg_page_src)
    ok("拼图页选源走 _prepare_sources（split_marked + RembgTransparentWorker）",
       "_prepare_sources" in _impo_page_src
       and "split_marked" in _impo_page_src
       and "RembgTransparentWorker" in _impo_page_src)
    ok("副本预备有可见进度（progress_row.start + toast 提示等待）",
       "progress_row.start" in _impo_page_src
       and "正在准备透明副本" in _impo_page_src
       and 'toast(\n            "info", "检测到去底色导出目录"' in _impo_page_src)
    _view_src = (ROOT
                 / "desktop/components/imposition/view.py").read_text(encoding="utf-8")
    ok("空态引导层存在且鼠标穿透（红框不能挡住按钮点击）",
       "_EmptyGuideOverlay" in _view_src
       and "WA_TransparentForMouseEvents" in _view_src)
    from desktop.components.imposition.view import ImpositionViewWidget

    _view = ImpositionViewWidget()
    _view.resize(900, 620)
    _view.show()
    pump(st.ctx.app)
    ok("没有拼版页 → 引导层显示（置顶）",
       _view.empty_guide.isVisible()
       and _view.empty_guide.geometry() == _view.rect())
    # 强制走一次 paintEvent：红框/箭头/文字的几何映射不能炸
    _shot = _view.grab()
    ok("空态引导层可绘制（grab 强制 paint 不抛异常）",
       not _shot.isNull())
    ok("有页之后引导层收起",
       (_view.set_pages([st._diag_page], current=0), True)[1]
       and not _view.empty_guide.isVisible())
    # ⚠️ 独立页首轮自动拼版传 current=-1（页已存在但还没选中）——
    #    引导层显隐只看"有没有页"，这一刻也必须收起
    _view.set_current(-1)
    ok("页存在但未选中（current=-1）→ 引导层同样收起",
       not _view.empty_guide.isVisible())
    _view.set_pages([], current=-1)
    ok("删光页回到空态 → 引导层再次出现",
       _view.empty_guide.isVisible())
    _view.hide()
    _view.deleteLater()

    # 清理基准是**页数**而不是"写成功的文件数"：中间某页合成失败会留下编号
    # 空洞（0001/0003），按写成功数去清会把 0003 这页好内容误删。
    gap = st.tmp / "sweep_gap"
    gap.mkdir()
    for name in ("0001.png", "0003.png", "0004.png"):
        _mk(gap / name, (0, 0, 0), (8, 8))
    S._sweep_stale(gap, 3)
    ok(
        "编号空洞里的页不会被误删（只清超出页数的）",
        sorted(p.name for p in gap.glob("*.png")) == ["0001.png", "0003.png"],
        str(sorted(p.name for p in gap.glob("*.png"))),
    )

