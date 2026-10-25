# -*- coding: utf-8 -*-
"""检测文本框「提交」的**回溯占位**规则（用户 2026-10-23）。

背景：检测只出框，空白页 / 漏检一侧在提交时会被跳过——下游少页、拼版按
``-l``/``-r`` 后缀配对时错配。这里钉住提交条目派生（``print_plan``）的补图
规则：

1. 左右双栏书：缺一侧 → 缺失侧按页中线镜像已有那一侧、截同尺寸的原图区域；
   整页空白 → 截左右两张（尺寸取全书左右框平均，落点取本半页中心）；
2. 单栏书（半幅单宽框）：空白页 → 截一张（半幅平均尺寸、页面居中）；
3. 整幅书：空白页 → 截一张（整幅平均尺寸、页面居中）；
4. 混排书：空白页完全跟随前一页形态；首页空白向前找最近的有框页。

⚠️ 占位图**不是纯白**：一律从该页原图截对应位置/尺寸的区域。
另外钉住 0009 的回归：零面积框（1px 宽）不算框，否则单栏页会被当成双栏页。

纯规则层，不需要 YOLO（``plan_detect_submit_entries`` 不碰 Qt / 模型）。
"""

from pathlib import Path

NAME = "submit_placeholders"
DEPENDS: list[str] = []
TITLE = "检测提交的占位（双栏/单栏/整幅/混排，截原图内容）"

W = 1000
H = 1400
DOUBLE = [[0, 100, 450, 1300], [520, 100, 1000, 1300]]   # 真双栏（两框）
LEFT_ONLY = [[0, 100, 450, 1300], None]                   # 只检出左框
RIGHT_ONLY = [None, [520, 100, 1000, 1300]]               # 只检出右框
WIDE = [[75, 100, 925, 1300], None]                       # 单宽框（85% 页宽）
FULL = [[100, 100, 900, 1300]]                            # 整幅（单槽）
EMPTY: list = []

#: 右框 [520,100,1000,1300] 以 W=1000 中线镜像后的左占位框
MIRRORED_LEFT = [0, 100, 480, 1300]


def _entries(boxes_map: dict, pages: list[str], sizes: dict | None = None):
    """按页名清单 + ``{页名: 槽位}`` 派生提交条目。

    默认每页 1000×1400；``sizes`` 可给个别页指定尺寸（窄页＝单页扫描用例）。
    """
    from desktop.services.print_plan import plan_detect_submit_entries

    size_map = dict(sizes or {})
    paths = [Path(name) for name in pages]
    return plan_detect_submit_entries(
        manifest_paths=paths,
        boxes_for=lambda text: boxes_map.get(Path(text).stem, []),
        page_width_for=lambda text: size_map.get(Path(text).stem, (W, H))[0],
        page_size_for=lambda text: size_map.get(Path(text).stem, (W, H)),
    )


def _by_label(entries) -> dict:
    return {e["label"]: e for e in entries}


def _near_gray(color, expected: int = 128, tolerance: int = 4) -> bool:
    """JPEG 有损：深灰实心块写出再读回会有几级漂移，按容差判断。"""
    return all(
        abs(value - expected) <= tolerance
        for value in (color.red(), color.green(), color.blue())
    )


def run(ctx) -> None:
    from tests.selftests._context import ok

    from utils.book_layout import profile_book
    from utils.box_geometry import box_has_area

    # ---- 0. 全书形态判据：双栏书的认定 ----
    double_book = profile_book([(f"{i}", DOUBLE, W) for i in range(1, 21)])
    ok("整本双栏（每页左右两框）→ double_column_book",
       double_book.double_column_book is True, str(double_book))
    ok("双栏书不是单栏书、也不是整幅书",
       double_book.single_column_book is False and double_book.full_book is False)

    # ---- 0b. 0009 回归：零面积框不算框（它会把单栏页错判成双栏） ----
    z = [[0, 400, 0, 437], [75, 152, 1896, 2749]]
    ok("零宽框不算框（任务 0009 的 1-l 就是 1×37 的残渣）",
       not box_has_area([0, 400, 0, 437]))
    pages9 = [f"{i:04d}.png" for i in range(1, 6)]
    boxes9 = {f"{i:04d}": WIDE for i in range(1, 6)}
    boxes9["0002"] = EMPTY
    boxes9["0001"] = z
    got9 = _by_label(_entries(boxes9, pages9))
    ok("单栏书里「零宽框 + 宽框」页 → 只出 0001 一张（不多裁占位）",
       "0001" in got9 and "0001-l" not in got9 and "0001-r" not in got9,
       str(sorted(k for k in got9 if k.startswith("0001"))))
    ok("该页的 0002 空白页 → 只补一张占位（不是左右两张）",
       "0002" in got9 and "0002-l" not in got9 and "0002-r" not in got9,
       str(sorted(k for k in got9 if k.startswith("0002"))))
    ok("全书条目数 == 页数（页码不再整体错位）",
       len(got9) == len(pages9), str(sorted(got9)))

    # ---- 1. 双栏书：缺一侧镜像截取、整页空白截左右两张 ----
    pages = [f"{i:04d}.png" for i in range(1, 13)]
    boxes = {f"{i:04d}": DOUBLE for i in range(1, 13)}
    boxes["0005"] = RIGHT_ONLY
    boxes["0006"] = EMPTY
    entries = _entries(boxes, pages)
    got = _by_label(entries)

    ok("双栏书缺左框 → 右框照常出图，并补一张 0005-l",
       "0005-r" in got and "0005-l" in got,
       str(sorted(k for k in got if k.startswith("0005"))))
    ok("补的左框是占位条目：源图仍是本页、带 placeholder 标记",
       got["0005-l"].get("placeholder") is True
       and got["0005-l"]["file"] == "0005.png", str(got["0005-l"]))
    ok("占位截取位置 = 右框以页中线镜像、尺寸相同（480×1200）",
       got["0005-l"]["boxes"] == [MIRRORED_LEFT], str(got["0005-l"]["boxes"]))

    ok("整页空白 → 截左右两张占位",
       "0006-l" in got and "0006-r" in got
       and got["0006-l"].get("placeholder") and got["0006-r"].get("placeholder"),
       str(sorted(k for k in got if k.startswith("0006"))))
    ok("空白页左占位 = 左框平均尺寸、取左半页中心",
       got["0006-l"]["boxes"] == [[25, 100, 475, 1300]],
       str(got["0006-l"]["boxes"]))
    ok("空白页右占位 = 右框平均尺寸、取右半页中心",
       got["0006-r"]["boxes"] == [[510, 100, 990, 1300]],
       str(got["0006-r"]["boxes"]))
    ok("空白页不再透传整页原图（只留占位条目）",
       "0006" not in got, str(sorted(k for k in got if k.startswith("0006"))))
    ok("双栏书仍按 r 先 l 后排序",
       [e["label"] for e in entries if e["label"].startswith("0006")]
       == ["0006-r", "0006-l"],
       str([e["label"] for e in entries if e["label"].startswith("0006")]))

    # ---- 1b. 窄页（单页扫描）：放不下第二栏 → 不补两张、不补另一侧 ----
    from utils.book_layout import (
        is_narrow_page, narrow_page_slots, typical_page_width,
    )

    ok("全书典型页宽 = 中位数（不被个别窄页拉低）",
       typical_page_width([1000, 1383, 1000, 600, 2400]) == 1000,
       str(typical_page_width([1000, 1383, 1000, 600, 2400])))
    ok("600 宽 vs 典型 1000 → 窄页（0.6 < 0.70）", is_narrow_page(600, 1000))
    ok("800 宽 vs 典型 1000 → 不算窄页（0.8 ≥ 0.70）",
       not is_narrow_page(800, 1000))
    ok("窄页单框 → 退化成单槽（不拆左右）",
       narrow_page_slots([[25, 67, 295, 1339], None], True)
       == [[25, 67, 295, 1339]])
    ok("窄页双框 → 原样不动（真双栏页不误伤）",
       narrow_page_slots(DOUBLE, True) == DOUBLE)

    pages = [f"{i:04d}.png" for i in range(1, 23)]
    boxes = {f"{i:04d}": DOUBLE for i in range(1, 23)}
    narrow_left = [[25, 67, 295, 1339], None]
    boxes["0005"] = EMPTY          # 窄页 + 无框 → 只补一张
    boxes["0006"] = narrow_left    # 窄页 + 单框 → 不补另一侧
    boxes["0007"] = RIGHT_ONLY     # 正常宽度 + 单框 → 仍按双栏补左
    sizes = {"0005": (600, 1400), "0006": (600, 1400)}
    got = _by_label(_entries(boxes, pages, sizes))

    ok("窄页无框 → 只补一张 0005（不是 0005-l/0005-r）",
       "0005" in got and got["0005"].get("placeholder") is True
       and "0005-l" not in got and "0005-r" not in got,
       str(sorted(k for k in got if k.startswith("0005"))))
    ok("窄页单框 → 只出一条 0006（不补另一栏、命名不带 -l/-r）",
       "0006" in got and "0006-l" not in got and "0006-r" not in got
       and not got["0006"].get("placeholder"),
       str(sorted(k for k in got if k.startswith("0006"))))
    ok("正常宽度的单框页仍按双栏补缺失侧（窄页规则不误伤）",
       "0007-r" in got and "0007-l" in got
       and got["0007-l"].get("placeholder") is True,
       str(sorted(k for k in got if k.startswith("0007"))))

    # ---- 2. 单栏书（半幅单宽框）：空白页截一张 ----
    pages = [f"{i:04d}.png" for i in range(1, 12)]
    boxes = {f"{i:04d}": WIDE for i in range(1, 12)}
    boxes["0004"] = EMPTY
    got = _by_label(_entries(boxes, pages))
    ok("单栏书空白页 → 只补 0004 一张占位（不拆 -l/-r）",
       "0004" in got and "0004-l" not in got and "0004-r" not in got,
       str(sorted(k for k in got if k.startswith("0004"))))
    ok("单栏书占位 = 半幅平均尺寸、页面居中（850×1200）",
       got["0004"]["boxes"] == [[75, 100, 925, 1300]],
       str(got["0004"].get("boxes")))
    ok("单栏书普通页按页码命名（不带 -l/-r）",
       "0003" in got and all(not k.endswith(("-l", "-r")) for k in got),
       str(sorted(got)))

    # ---- 3. 整幅书：空白页截一张，取整幅平均矩形 ----
    pages = [f"{i:04d}.png" for i in range(1, 12)]
    boxes = {f"{i:04d}": FULL for i in range(1, 12)}
    boxes["0007"] = EMPTY
    got = _by_label(_entries(boxes, pages))
    ok("整幅书空白页 → 截 0007 一张占位",
       "0007" in got and got["0007"].get("placeholder") is not None,
       str(sorted(k for k in got if k.startswith("0007"))))
    ok("整幅书占位 = 整幅平均尺寸、页面居中（800×1200）",
       got["0007"]["boxes"] == [[100, 100, 900, 1300]],
       str(got["0007"].get("boxes")))

    # ---- 4. 混排书：空白页完全跟随前一页 ----
    # 一半整幅 + 一半双栏 → 两个极端都不成立 = 混排。
    pages = [f"{i:04d}.png" for i in range(1, 9)]
    boxes = {
        "0001": FULL, "0002": DOUBLE, "0003": DOUBLE,
        "0004": EMPTY,          # 前页 0003 是双栏 → 截左右两张
        "0005": FULL, "0006": EMPTY,   # 前页 0005 是整幅 → 截一张（整幅平均）
        "0007": LEFT_ONLY, "0008": EMPTY,  # 前页只出左框 → 补 0008-l
    }
    got = _by_label(_entries(boxes, pages))
    ok("混排书：前页双栏 → 空白页截左右两张",
       "0004-l" in got and "0004-r" in got
       and got["0004-l"].get("placeholder") and got["0004-r"].get("placeholder"),
       str(sorted(k for k in got if k.startswith("0004"))))
    ok("混排书：左右占位各取本半页中心、尺寸分别取左右平均",
       got["0004-l"]["boxes"] == [[25, 100, 475, 1300]]
       and got["0004-r"]["boxes"] == [[510, 100, 990, 1300]],
       f"{got['0004-l']['boxes']} / {got['0004-r']['boxes']}")
    ok("混排书：前页整幅 → 空白页截一张（整幅平均尺寸、页面居中）",
       "0006" in got and got["0006"].get("placeholder") is not None
       and got["0006"]["boxes"] == [[100, 100, 900, 1300]]
       and "0006-l" not in got,
       str(sorted(k for k in got if k.startswith("0006"))))
    ok("混排书：前页只出左框 → 空白页补 0008-l（同侧、页面居中）",
       "0008-l" in got and "0008-r" not in got
       and got["0008-l"]["boxes"] == [[275, 100, 725, 1300]],
       str(sorted(k for k in got if k.startswith("0008"))))

    # 首页空白：向前没有前一页 → 向后找最近的有框页
    boxes["0001"] = EMPTY
    boxes["0002"] = DOUBLE
    got = _by_label(_entries(boxes, pages))
    ok("混排书首页空白 → 跟随后一张有框页（双栏 → 截两张）",
       "0001-l" in got and "0001-r" in got,
       str(sorted(k for k in got if k.startswith("0001"))))

    # ---- 5. 占位条目 → 执行作业（沿用真框的裁剪路径） ----
    from desktop.services.print_plan import entry_to_effect_spec, plan_submit_job

    spec = entry_to_effect_spec(got["0001-l"], "0")
    ok("占位条目转效果规格：file=源页、effect=占位框、带 placeholder 标记",
       spec["file"] == "0001.png" and spec["placeholder"] is True
       and spec["effect"] == {"boxes": [[25, 100, 475, 1300]], "border": "0"},
       str(spec))
    job = plan_submit_job(spec, (W, H))
    ok("占位作业：输出名 = 标签.jpg、按单框合成、保留占位标记",
       job["names"] == ["0001-l.jpg"] and job["compose"] is True
       and job["placeholder"] is True
       and job["boxes"] == [[25, 100, 475, 1300]], str(job))

    # 预览侧不传 placeholder_for → 条目与改造前一致（不凭空多占位）
    ok("不传占位描述时条目不变（预览侧零影响）",
       all("placeholder" not in e for e in _entries({"0001": EMPTY}, ["0001.png"])),
       str(_entries({"0001": EMPTY}, ["0001.png"])))

    # ---- 6. 真实提交阶段：占位落成**原图内容**（不是纯白） ----
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from desktop.stages import detect_stage

    src = Path(ctx.tmp) / "submit_placeholders_src.png"
    seed = QImage(W, 1400, QImage.Format.Format_RGB32)
    seed.fill(Qt.GlobalColor.darkGray)
    ok("（前置）占位源页已写出", seed.save(str(src)), str(src))
    # 左半区画一块明显的内容，验证截的是这块，而不是纯白
    out = Path(ctx.tmp) / "submit_placeholders_stage"
    entry = {
        "file": str(src), "label": "0002", "box": [75, 100, 925, 1300],
        "boxes": [[75, 100, 925, 1300]], "full": False, "placeholder": True,
    }
    rc = detect_stage.run_detect_submit_stage({
        "task_id": "selftest", "stage": "detect_submit", "run_id": "placeholder",
        "args": {
            "_effects": [entry_to_effect_spec(entry, "0")],
            "output": str(out), "clean": True,
        },
    })
    ok("占位提交阶段 exit=0", rc == 0, f"rc={rc}")
    written = sorted(p.name for p in out.glob("*.jpg"))
    ok("占位提交阶段写出 0002.jpg", written == ["0002.jpg"], str(written))
    from PIL import Image as _PILImage

    with _PILImage.open(out / "0002.jpg") as saved_image:
        ok("提交产物是 JPEG（不再是 PNG）",
           saved_image.format == "JPEG", str(saved_image.format))
    ok("提交 JPEG 画质为 95",
       detect_stage.SUBMIT_JPEG_QUALITY == 95,
       str(detect_stage.SUBMIT_JPEG_QUALITY))
    image = QImage(str(out / "0002.jpg"))
    ok("占位产物尺寸 = 占位框尺寸（850×1200）",
       not image.isNull() and (image.width(), image.height()) == (850, 1200),
       f"{image.width()}x{image.height()}")
    ok("占位产物截的是原图内容（深灰），不是纯白",
       not image.isNull()
       and _near_gray(image.pixelColor(0, 0))
       and _near_gray(image.pixelColor(image.width() // 2, image.height() // 2)),
       image.pixelColor(0, 0).name())
