# -*- coding: utf-8 -*-
"""1. 版面规则（纯逻辑，无 Qt） / 1a. 编辑覆盖源图后 rect 刷新（用户 2026-10-10） / 1b. 裁剪移动留下的透明边距（用户 2026-10-14）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import BLUE, GREEN, RED, YELLOW, _mk
    from PIL import Image
    from pathlib import Path
    from desktop.services import imposition as S
    from PIL import Image as _PILImage
    from tests.selftests._context import make_pdf, ok, pump
    st.src = st.tmp / "src"
    st.a = _mk(st.src / "1-r.png", RED)
    st.b = _mk(st.src / "1-l.png", GREEN)
    st.c = _mk(st.src / "2-r.png", BLUE)
    st.d = _mk(st.src / "2-l.png", YELLOW)

    st.made = S.make_page([st.a, st.b])
    ok("make_page 能造出一页拼版", st.made is not None)
    assert st.made is not None  # ⚠️ 上一行已判过；这里只为类型检查器收窄
    right, left = st.made["items"]
    ok(
        "序号在前的图片落在**右侧**槽位",
        Path(right["file"]).name == "1-r.png"
        and Path(left["file"]).name == "1-l.png",
    )
    ok(
        "右侧槽位的 x 大于左侧（版面左右就位）",
        right["rect"][0] > left["rect"][0],
        f"{right['rect']} vs {left['rect']}",
    )
    ok("页面里**没有纸张**（sheet 键已删除）", "sheet" not in st.made, str(list(st.made)))
    ok(
        "默认版面按**原始像素**摆放（不改动用户的图）",
        right["rect"][2:] == [400.0, 600.0] and left["rect"][2:] == [400.0, 600.0],
        f"{right['rect']} / {left['rect']}",
    )
    ok("只给一张图造不出一页拼版", S.make_page([st.a]) is None)

    composed = S.compose_page(st.made)
    ok(
        "产出图 = 两张图外接框的紧裁（无纸张：图上多大就多大）",
        composed.size == (800, 600),
        str(composed.size),
    )
    ok(
        "合成后：左侧是 1-l、右侧是 1-r（像素级）",
        composed.getpixel((700, 300))[:3] == RED
        and composed.getpixel((100, 300))[:3] == GREEN,
        f"{composed.getpixel((700, 300))} / {composed.getpixel((100, 300))}",
    )
    # ⚠️ 2026-10-10 用户修订：拼版结果**不再铺白底**（白底会烙进成品页图，
    # 编辑器里统一变换/裁剪全带着白底走）。默认版面两图相邻没有留白，
    # 用 30° 旋转的外接框（内容距画布角有 300px 空白）验证：角落透明、
    # 内容照旧。
    from PIL import Image as _PILImage

    _diag = _PILImage.new("RGB", (400, 600), GREEN)
    _diag_path = st.tmp / "diag-probe.png"
    _diag.save(_diag_path)
    st._diag_page = S.normalize_page(
        {
            "items": [
                {
                    "file": str(_diag_path),
                    "rect": [0.0, 0.0, 400.0, 600.0],
                    "rotation": 30.0,
                }
            ],
        }
    )
    assert st._diag_page is not None  # 结构合法，normalize 必过
    _diag_shot = S.compose_page(st._diag_page)
    ok(
        "合成后留白处透明（30° 外接框角落不铺白，返回 RGBA）",
        _diag_shot.mode == "RGBA"
        and _diag_shot.getpixel((2, 2))[3] == 0
        and _diag_shot.getpixel((400, 360))[:3] == GREEN,
        f"mode={_diag_shot.mode} corner={_diag_shot.getpixel((2, 2))}",
    )

    # ⚠️ 2026-10-13 用户：**白底导出**——独立拼图页「导出成品」显式传
    # WHITE_BACKGROUND，任务流程默认仍是透明底（上一条断言钉住）。
    _diag_white = S.compose_page(st._diag_page, S.WHITE_BACKGROUND)
    ok(
        "白底导出：留白处铺白（α=255、RGB=255）、内容逐位不变",
        _diag_white.mode == "RGBA"
        and _diag_white.getpixel((2, 2)) == (255, 255, 255, 255)
        and _diag_white.getpixel((400, 360))[:3] == GREEN,
        f"corner={_diag_white.getpixel((2, 2))} content={_diag_white.getpixel((400, 360))}",
    )

    # 旋转是**顺时针**口径：PIL 侧取负，两边必须一致。
    # ⚠️ 判据必须用**非均匀**图案，否则 ±90° 的中心像素一样，注入翻转方向
    # 也测不出来（第一版就是这么假绿的）。用「左半蓝 / 右半绿」的图：
    # 顺时针 90° 后左半应转到**上边**、右半转到下边。
    from PIL import Image

    striped = Image.new("RGB", (400, 600), GREEN)
    striped.paste(BLUE, (0, 0, 200, 600))
    striped_path = st.tmp / "rotate-probe.png"
    striped.save(striped_path)
    rotated_page = S.normalize_page(
        {
            "items": [
                {
                    "file": str(striped_path),
                    "rect": [0.0, 0.0, 400.0, 600.0],
                    "rotation": 90.0,
                }
            ],
        }
    )
    assert rotated_page is not None  # ⚠️ 上面这一项结构合法，normalize 必过
    shot = S.compose_page(rotated_page)
    # 无纸张：产出图 = 旋转后的外接框（400×600 转 90° → 600×400）
    ok("旋转后的产出图按外接框紧裁", shot.size == (600, 400), str(shot.size))
    ok(
        "旋转 90° 是**顺时针**（左半转到上边、右半转到下边）",
        shot.getpixel((300, 80))[:3] == BLUE
        and shot.getpixel((300, 320))[:3] == GREEN,
        f"上={shot.getpixel((300, 80))} 下={shot.getpixel((300, 320))}",
    )
    st.probe = st.tmp / "edited-probe.png"
    _mk(st.probe, RED)  # 覆盖前：400×600 竖图
    page_stale = S.normalize_page(
        {
            "items": [
                {
                    "file": str(st.probe),
                    "rect": [100.0, 50.0, 400.0, 600.0],
                    "rotation": 0.0,
                }
            ],
        }
    )
    assert page_stale is not None  # ⚠️ 结构合法，normalize 必过
    wide = Image.new("RGB", (600, 400), BLUE)
    wide.paste(RED, (0, 0, 300, 400))  # "转了 90°"：600×400，左红右蓝
    wide.save(st.probe)
    doc_probe = {"pages": [page_stale]}
    ok(
        "编辑覆盖源图后 rect 刷新（返回 True）",
        S.refresh_rects_for_edited_source(doc_probe, str(st.probe)) is True,
    )
    new_rect = [
        round(float(v), 3) for v in doc_probe["pages"][0]["items"][0]["rect"]
    ]
    # 旧 rect 中心 = (300, 350)；新 600×400 绕中心 ⇒ [0, 150, 600, 400]
    ok(
        "rect 宽高 = 新图尺寸、中心保持不动",
        new_rect == [0.0, 150.0, 600.0, 400.0],
        str(new_rect),
    )
    ok(
        "尺寸没变时刷新是 no-op（返回 False）",
        S.refresh_rects_for_edited_source(doc_probe, str(st.probe)) is False,
    )
    ok(
        "尺寸缓存随覆盖失效（重读到新尺寸）",
        S.image_size(st.probe) == (600, 400),
        str(S.image_size(st.probe)),
    )
    # 合成不再压扁：600×400 按原始像素落位（旧 rect 会把它压成 400×600）
    fixed = S.compose_page(doc_probe["pages"][0])
    ok(
        "刷新后合成不压扁（新图原样落位：左半红、右半蓝）",
        fixed.size == (600, 400)
        and fixed.getpixel((150, 200))[:3] == RED
        and fixed.getpixel((450, 200))[:3] == BLUE,
        f"size={fixed.size} {fixed.getpixel((150, 200))} / "
        f"{fixed.getpixel((450, 200))}",
    )
    pad_probe = st.tmp / "padded-probe.png"
    # ⚠️ 内容块必须**完整落在** 240×130 画布内（paste 会被画布边缘裁掉），
    #    所以挪的是 -20 而不是 +30；这里要验的是"四周留白不占版面"。
    padded = Image.new("RGBA", (240, 130), (0, 0, 0, 0))
    padded.paste(RED, (20, 20, 220, 120))        # 内容 200×100，四周留白
    padded.save(pad_probe)
    ok(
        "透明留白图：内容框读到 200×100（不是整张 240×130）",
        S.image_content_bounds(pad_probe) == (20, 20, 200, 100),
        str(S.image_content_bounds(pad_probe)),
    )
    doc_pad = {"pages": [S.normalize_page({
        "items": [{"file": str(pad_probe),
                   "rect": [0.0, 0.0, 200.0, 100.0], "rotation": 0.0}]
    })]}
    ok(
        "裁剪移动后 rect 按**可见内容**刷（不吃透明留白）",
        S.refresh_rects_for_edited_source(doc_pad, str(pad_probe)) is True,
    )
    pad_rect = [
        round(float(v), 3)
        for v in doc_pad["pages"][0]["items"][0]["rect"]
    ]
    ok(
        "rect 宽高 = 可见内容 200×100（旧版是 240×130，框比图大一圈）",
        pad_rect[2] == 200.0 and pad_rect[3] == 100.0,
        str(pad_rect),
    )
    # ⚠️ 合成侧必须同步裁掉留白，否则整张图（含留白）被塞进 200×100 的
    #    框里 ⇒ 内容压扁（把"框偏大"换成"图变形"，一样是错位）。
    pad_out = S.compose_page(doc_pad["pages"][0])
    ok(
        "合成不压扁（留白先裁掉，内容按 200×100 原比例落位）",
        pad_out.size == (200, 100)
        and pad_out.getpixel((100, 50))[:3] == RED,
        f"size={pad_out.size} px={pad_out.getpixel((100, 50))}",
    )
    # 不透明扫描件完全不受影响：内容＝整张，走旧口径
    ok(
        "不透明图内容框 = None（整幅不透明，不裁不改）",
        S.image_content_bounds(st.probe) is None,
        str(S.image_content_bounds(st.probe)),
    )

    ok(
        "坏页被过滤（项为空 / 无文件 / 非字典）",
        all(
            S.normalize_page(bad) is None
            for bad in (
                {"items": []},
                {"items": [{"file": "", "rect": [0, 0, 9, 9]}]},
                "垃圾",
            )
        ),
    )
    # 老任务存过 "sheet"：读进来要**忽略**它，不能因此判成坏页
    legacy = S.normalize_page(
        {"sheet": [800, 600], "items": [{"file": "x.png", "rect": [0, 0, 9, 9]}]}
    )
    ok(
        "老文档里的 sheet 被忽略（老任务照样能读）",
        legacy is not None and "sheet" not in legacy,
        str(legacy),
    )
    ok(
        "中文页码标签",
        [S.cn_page_label(i) for i in (0, 1, 9, 10, 19)]
        == ["第一页", "第二页", "第十页", "第十一页", "第二十页"],
    )

