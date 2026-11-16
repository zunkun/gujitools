# -*- coding: utf-8 -*-
"""「提交本次任务」的裁图条目：**只裁标注过的文本框**（用户 2026-11-16）。

用户原话：

> 执行本次任务的时候，现在会补全某一页没有标注，比如只有单栏会按照镜像补全
> 另一个文本框，没有文本框页面现在也按照平均文本框尺寸补全文本框，删除这条
> 规则，没有文本框的不再进行补全，只裁剪出标注过的文本框。

于是 2026-10-23 那套「回溯占位」（镜像缺失侧 / 按全书平均尺寸造框 / 空白页
跟随前一页 / 窄页整页一张）**整体删除**。本模块钉住删干净后的规则：

1. **双框页** → 两条（``-r`` / ``-l``）；**单框页** → **一条**（半幅仍保住
   ``-l``/``-r`` 身份，产物名不能退化成页名）；
2. **一个框都没有的页 → 零条目**（这一步不出图，绝不造框）；
3. 全书归一化（单栏单宽框 / 窄页 / 「整幅其实像半幅」）只决定**这条叫什么
   名字、算不算可配对半幅**，**不补框**；
4. 旧任务的提交计划里可能还带 ``placeholder``，读侧保留容错、写侧不再产生。

⚠️ 全部是纯逻辑（不弹窗、不跑 YOLO）；最后一段才真跑一次提交阶段验落盘。
"""

from __future__ import annotations

from pathlib import Path

NAME = "submit_entries"
DEPENDS: list[str] = []
TITLE = "提交本次任务：只裁标注过的文本框"

W, H = 1000, 1400
DOUBLE = [[60, 100, 460, 1300], [520, 100, 940, 1300]]   # 左右双框
LEFT_ONLY = [[60, 100, 460, 1300], None]                  # 只检出/只画了左框
RIGHT_ONLY = [None, [520, 100, 940, 1300]]                # 只有右框
WIDE = [[75, 100, 925, 1300], None]                       # 单宽框（85% 页宽）
FULL = [[100, 100, 900, 1300]]                            # 整幅（单槽）
EMPTY: list = []


def _entries(boxes_map: dict, pages: list[str], sizes: dict | None = None):
    """按页名清单 + ``{页名: 槽位}`` 派生「提交本次任务」条目。"""
    from desktop.services.print_plan import plan_detect_submit_entries

    size_map = dict(sizes or {})
    return plan_detect_submit_entries(
        manifest_paths=[Path(name) for name in pages],
        boxes_for=lambda text: boxes_map.get(Path(text).stem, []),
        page_width_for=lambda text: size_map.get(Path(text).stem, (W, H))[0],
    )


def _by_label(entries) -> dict:
    return {e["label"]: e for e in entries}


def run(ctx) -> None:
    from tests.selftests._context import ok

    # ---------------------------------------------------- 1. 双框 / 单框 / 无框
    got = _by_label(_entries({"0001": DOUBLE}, ["0001.png"]))
    ok("双框页派生两条（-r / -l），各带自己的框",
       sorted(got) == ["0001-l", "0001-r"]
       and got["0001-l"]["boxes"] == [DOUBLE[0]]
       and got["0001-r"]["boxes"] == [DOUBLE[1]],
       str(got))

    got = _by_label(_entries({"0001": LEFT_ONLY}, ["0001.png"]))
    ok("半幅只画了一侧 → **只有一条**，不再镜像补另一栏",
       sorted(got) == ["0001-l"], str(sorted(got)))
    ok("那一条仍保住 -l 身份（拼版要靠它认左右）",
       got["0001-l"]["role"] == "half-left"
       and got["0001-l"]["boxes"] == [LEFT_ONLY[0]],
       str(got.get("0001-l")))

    got = _by_label(_entries({"0001": EMPTY}, ["0001.png"]))
    ok("一个框都没有的页 → **零条目**（不出图，不造平均尺寸的框）",
       got == {}, str(got))

    got = _by_label(_entries({"0001": FULL}, ["0001.png"]))
    ok("整幅页 → 一条，用页名（不拆左右）",
       sorted(got) == ["0001"] and got["0001"]["full"] is True, str(sorted(got)))

    # 混排：有框的页出条目、没框的页一条都不出
    pages = [f"{i:04d}.png" for i in range(1, 6)]
    boxes = {
        "0001": DOUBLE, "0002": EMPTY, "0003": LEFT_ONLY,
        "0004": EMPTY, "0005": FULL,
    }
    entries = _entries(boxes, pages)
    ok("没有框的页整页缺席（不是「出一条空框」）",
       not any(e["label"].startswith(("0002", "0004")) for e in entries),
       str([e["label"] for e in entries]))
    ok("条目按页序 → 同页 r 先 l 后（拼版依赖这个顺序）",
       [e["label"] for e in entries]
       == ["0001-r", "0001-l", "0003-l", "0005"],
       str([e["label"] for e in entries]))

    # 零面积框（1px 宽）不算框：不产生条目，也不让这页被当成双框
    # ⚠️ 槽位是保留的（`[零宽框, 真框]` → `[None, 真框]`），所以那个真框落在
    #    右槽 ⇒ 名字是 ``-r``。这正是"半幅恒 2 槽"约定的应有表现。
    got = _by_label(_entries({"0001": [[0, 0, 0, 0], RIGHT_ONLY[1]]}, ["0001.png"]))
    ok("零面积框先被剔掉（不裁一张 0 宽的图），真框仍按槽位命名",
       sorted(got) == ["0001-r"] and got["0001-r"]["boxes"] == [RIGHT_ONLY[1]],
       str(sorted(got)))

    # ------------------------------------------- 2. 归一化只改名字，不补框
    got = _by_label(_entries({"0001": WIDE}, ["0001.png"]))
    ok("单宽框页（单栏书）→ 一条、用页名、记成可配对半幅",
       sorted(got) == ["0001"] and got["0001"]["role"] == "half-unsided",
       str(got.get("0001")))

    got = _by_label(_entries(
        {"0001": LEFT_ONLY, "0002": LEFT_ONLY}, ["0001.png", "0002.png"],
        sizes={"0002": (600, 1400)},
    ))
    ok("窄页（单页扫描）+ 单框 → 一条、名字不带 -l/-r",
       sorted(k for k in got if k.startswith("0002")) == ["0002"],
       str(sorted(got)))
    ok("正常宽度的单框页不受窄页规则影响（仍是 -l）",
       "0001-l" in got and "0001-r" not in got, str(sorted(got)))

    # 整本书一个框都没有 → 一条都没有（旧实现会造一整本"平均尺寸"的裁图）
    got = _by_label(_entries({}, [f"{i:04d}.png" for i in range(1, 9)]))
    ok("整本无框 → 零条目（不给空白书凭空造 8 张图）", got == {}, str(got))

    # ------------------------------------- 3. 旧占位机制已从代码里删干净
    import desktop.services.print_plan as pp

    for name in ("_placeholder_entries", "_average_size", "_center_box",
                 "_mirror_box", "_fit_box"):
        ok(f"print_plan 不再有 {name}（补框机制的组成部分）",
           not hasattr(pp, name))

    import inspect

    params = inspect.signature(pp.plan_detect_submit_entries).parameters
    ok("检测提交派生不再收 page_size_for（页高只用于造占位框）",
       "page_size_for" not in params, str(sorted(params)))
    params = inspect.signature(pp.plan_rembg_submit_entries).parameters
    ok("共用派生不再收 placeholder_for（占位条目已无生产者）",
       "placeholder_for" not in params, str(sorted(params)))

    spec = pp.entry_to_effect_spec(
        {"file": "0001.png", "label": "0001", "boxes": [LEFT_ONLY[0]]}, "0"
    )
    job = pp.plan_submit_job(spec, (W, H))
    ok("效果规格/作业里不再有 placeholder 标记",
       "placeholder" not in spec and "placeholder" not in job,
       f"{spec} / {job}")
    ok("作业名仍是 <标签>.jpg、单框照常合拍",
       job["names"] == ["0001.jpg"] and job["compose"] is True, str(job))

    # --------------------------------- 4. 真实提交阶段：只落标注过的那几张
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from desktop.stages import detect_stage

    src = Path(ctx.tmp) / "submit_entries_src.png"
    seed = QImage(W, H, QImage.Format.Format_RGB32)
    seed.fill(Qt.GlobalColor.darkGray)
    ok("（前置）源页已写出", seed.save(str(src)), str(src))

    out = Path(ctx.tmp) / "submit_entries_stage"
    one = {"file": str(src), "label": "0002-l",
           "boxes": [LEFT_ONLY[0]], "full": False}
    rc = detect_stage.run_detect_submit_stage({
        "task_id": "selftest", "stage": "detect_submit", "run_id": "entries",
        "args": {
            "_effects": [pp.entry_to_effect_spec(one, "0")],
            "output": str(out), "clean": True,
        },
    })
    ok("提交阶段 exit=0", rc == 0, f"rc={rc}")
    ok("只写出那一张（0002-l.jpg）",
       sorted(p.name for p in out.glob("*")) == ["0002-l.jpg"],
       str(sorted(p.name for p in out.glob("*"))))

    image = QImage(str(out / "0002-l.jpg"))
    box = LEFT_ONLY[0]
    ok("产物尺寸 = 那个框的尺寸（400×1200，没被放大成整页）",
       not image.isNull()
       and (image.width(), image.height())
       == (box[2] - box[0], box[3] - box[1]),
       f"{image.width()}x{image.height()}")
    ok("提交 JPEG 画质仍是 95", detect_stage.SUBMIT_JPEG_QUALITY == 95,
       str(detect_stage.SUBMIT_JPEG_QUALITY))
