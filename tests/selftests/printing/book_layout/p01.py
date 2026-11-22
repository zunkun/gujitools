# -*- coding: utf-8 -*-
"""1. 单宽框判据的三条边界 / 2. 全书级：单栏书 / 3. 全书级：整幅书 + 可疑半幅（只警告，不改） / 4. 命名落地：单栏书按页码命名，不拆 -l/-r / 4b. 方向2：整幅框几何像半幅 → 按半幅落地（用户 2026-10-25） / 5. 界面接线：提示必须在统计面板上真的看得见 / 9. 第二步标注：整宽单框标「半幅」，不是左/右框 / 「点框就切换」：画出来的段边界必须就是可点的段边界"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import DOUBLE, FULL, NARROW, W, WIDE
    from desktop.components.panels.detect_panel import BOX_KIND_ITEMS
    from desktop.components.box_kinds import BoxKindEditor
    from desktop.pages.taskdetail.detect import DetectMixin
    from desktop.components.detect_stats import DetectStatsWidget
    from desktop.components.viewers.image_view.styles import (
        HALF_BOX_NAME, box_styles, is_half_page,
    )
    from desktop.components.viewers.image_view import ImageView
    from pathlib import Path
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtCore import QSize
    from PySide6.QtTest import QTest
    from utils.book_layout import (
        SINGLE_COLUMN_BOOK_RATIO, SINGLE_COLUMN_WIDTH_RATIO,
        is_single_wide_half, profile_book, single_column_summary,
        suspicious_summary,
    )
    from desktop.ui.segmented_toggle import SegmentedToggle
    import inspect as _inspect
    from utils.book_layout import demoted_full_summary
    from utils.book_layout import is_single_wide_box
    from tests.selftests._context import ok
    from desktop.services.print_plan import plan_detect_submit_entries
    from desktop.services.print_plan import plan_rembg_submit_entries
    ok("60% 是单宽框的宽度下限（阈值唯一且可查）",
       abs(SINGLE_COLUMN_WIDTH_RATIO - 0.60) < 1e-9, str(SINGLE_COLUMN_WIDTH_RATIO))
    ok("宽 85% 的单框 → 单宽框", is_single_wide_half(WIDE, W))
    ok("恰好 60% 也算（判据是 ≥ 而非 >）",
       is_single_wide_half([[200, 0, 800, 500], None], W))
    ok("宽 59% 不算单宽框（阈值之下不放行）",
       not is_single_wide_half([[205, 0, 795, 500], None], W))
    ok("宽 45% 的单框不算（那是真半栏）",
       not is_single_wide_half(NARROW, W))
    # 用户 2026-10-23：任务 0012（单页扫描，文本块占 70~78% 页宽）必须认成半幅。
    # 旧阈值 80% 时它整本判不出单栏书，每页都被按中心拆错左右。
    SINGLE_SCAN = [[126, 1047, 1588, 3124], None]  # 0012 第 7 页实框，宽 74%
    ok("宽 74% 的单页扫描框 → 半幅（0012 这类书的回归）",
       is_single_wide_half(SINGLE_SCAN, 1973))
    ok("双框不算（真双栏书本来就该拆 -l/-r）",
       not is_single_wide_half(DOUBLE, W))
    ok("1 槽不算（已是整幅语义，不该被这里改写）",
       not is_single_wide_half([FULL[0]], W))
    ok("页宽未知 → 保守判否（没证据不改身份）",
       not is_single_wide_half(WIDE, None) and not is_single_wide_half(WIDE, 0))
    ok("无框不算", not is_single_wide_half([], W))
    st.single_book = profile_book(
        [(f"{i}", WIDE, W) for i in range(1, 10)]
        + [("10", DOUBLE, W), ("cover", [], W), ("blank", [], W)]
    )
    ok("单栏书被认定（9/10 有框页是单宽框，恰好 90%）",
       st.single_book.single_column_book is True, str(st.single_book.single_column_book))
    ok("单栏书不是整幅书", st.single_book.full_book is False)
    ok("单栏书的无框页不计入分母（有框页 = 10，不是 12）",
       st.single_book.boxed_pages == 10 and st.single_book.total_pages == 12,
       f"boxed={st.single_book.boxed_pages} total={st.single_book.total_pages}")
    ok("单栏书里那些单宽框页**不算**可疑（模型没判错，是形态解释）",
       st.single_book.suspicious_half_pages == (),
       str(st.single_book.suspicious_half_pages))
    ok("单栏书给出一行人读结论（提到不再拆 -l/-r）",
       "不再拆 -l/-r" in single_column_summary(st.single_book),
       single_column_summary(st.single_book))

    # 差一档就不成立：8/10 = 80% < 90%
    not_single = profile_book(
        [(f"{i}", WIDE, W) for i in range(1, 9)]
        + [("9", DOUBLE, W), ("10", DOUBLE, W), ("cover", [], W)]
    )
    ok("80% 不够 → 不认定单栏书（宁可漏判，不误判）",
       not_single.single_column_book is False, str(not_single.single_column_book))

    # 真·双栏书：一页双框，绝不能被当成单栏书
    double_book = profile_book([(f"{i}", DOUBLE, W) for i in range(1, 21)])
    ok("整本双栏书不会被误判成单栏书",
       double_book.single_column_book is False and double_book.full_book is False)
    full_book = profile_book(
        [(f"{i}", FULL, W) for i in range(1, 20)]
        + [("20", DOUBLE, W), ("21", NARROW, W)]
    )
    ok("整幅书被认定（18/20）", full_book.full_book is True)
    ok("整幅书不是单栏书", full_book.single_column_book is False)
    ok("整幅书里的半幅页被列为可疑（双栏页 + 窄单框页都在内）",
       set(full_book.suspicious_half_pages) == {"20", "21"},
       str(full_book.suspicious_half_pages))
    ok("可疑提示点明「可疑」与「未自动改动」",
       "可疑" in suspicious_summary(full_book)
       and "未自动改动" in suspicious_summary(full_book),
       suspicious_summary(full_book))
    ok("单栏结论在整幅书上不出现", single_column_summary(full_book) == "")

    clean_full = profile_book([(f"{i}", FULL, W) for i in range(1, 21)])
    ok("纯整幅书没有可疑页，也不出提示",
       clean_full.suspicious_half_pages == ()
       and suspicious_summary(clean_full) == "",
       str(clean_full.suspicious_half_pages))

    # 混合排版：一半单栏页一半整幅页 → 两个极端都不成立，**不做任何改写**
    mixed = profile_book(
        [(f"a{i}", WIDE, W) for i in range(5)]
        + [(f"b{i}", FULL, W) for i in range(5)]
    )
    ok("混合排版不认定任何一个极端（保守：形态交还原有判据）",
       mixed.single_column_book is False and mixed.full_book is False,
       f"single={mixed.single_column_book} full={mixed.full_book}")
    from desktop.services.print_plan import plan_rembg_submit_entries

    def _entries(pages_boxes, width=W):
        return plan_rembg_submit_entries(
            manifest_paths=[Path(f"{i:04d}.png") for i in range(1, len(pages_boxes) + 1)],
            result_path_for=lambda stem: Path(f"{stem}.png"),
            boxes_for=lambda _p: pages_boxes[_p],
            page_width_for=lambda _p: width,
        )
    st._entries = _entries

    st.nine = {f"000{i}.png": WIDE for i in range(1, 10)}
    st.nine["0010.png"] = DOUBLE

    # 单宽框页 → label 就是页名（7.png），不是 0007-l
    got = {e["label"]: e for e in st._entries(st.nine)}
    ok("单宽框页 label 是页名（按页码命名，不带 -l/-r）",
       "0007" in got and "0007-l" not in got and "0007-r" not in got,
       str(sorted(got)))
    ok("单宽框页按整幅语义（full=True）",
       got["0007"]["full"] is True, str(got["0007"]))
    ok("提交计划记下归一化前的 harfcontent 形态",
       got["0007"].get("page_class") == "harfcontent-left",
       str(got["0007"].get("page_class")))
    ok("无后缀产物仍记成可配对半幅（role=half-unsided）",
       got["0007"].get("role") == "half-unsided",
       str(got["0007"]))
    ok("真双栏页仍照常拆 -r/-l（不误伤双栏书里的那一页）",
       {e["label"] for e in st._entries(st.nine) if e["label"].startswith("0010")}
       == {"0010-r", "0010-l"},
       str([e["label"] for e in st._entries(st.nine) if e["label"].startswith("0010")]))
    ok("单宽框页产出的标签仍无后缀（拼版改看提交计划认身份）",
       all(not e["label"].endswith(("-l", "-r"))
           for e in st._entries(st.nine) if e["label"] != "0010"
           and e["label"] not in ("0010-l", "0010-r")))

    # 用户 2026-10-23（任务 0004）：判据是**页级**的——混合书（不是单栏书）里
    # 单个宽框页同样按半幅归一化，不能按中心硬拆 -l/-r。
    mixed_pages = {f"000{i}.png": WIDE for i in range(1, 6)}
    mixed_pages["0006.png"] = FULL
    mixed_pages["0007.png"] = DOUBLE
    mixed_got = {e["label"]: e for e in st._entries(mixed_pages)}
    ok("混合书里的单宽框页也按半幅归一化（页级判据，不要求全书单栏）",
       "0001" in mixed_got and "0001-l" not in mixed_got
       and "0001-r" not in mixed_got, str(sorted(mixed_got)))
    ok("混合书里的单宽框页 full=True + role=half-unsided",
       mixed_got["0001"]["full"] is True
       and mixed_got["0001"]["role"] == "half-unsided", str(mixed_got["0001"]))
    ok("混合书里的整幅页不受影响（仍叫页名、role=full）",
       mixed_got["0006"]["full"] is True
       and mixed_got["0006"]["role"] == "full", str(mixed_got["0006"]))
    ok("混合书里的真双栏页仍拆 -l/-r",
       {"0007-r", "0007-l"} <= set(mixed_got), str(sorted(mixed_got)))

    # 整幅书里的可疑半幅：**不得**被悄悄改写成整幅
    fullmix = {f"{i:04d}.png": FULL for i in range(1, 20)}
    fullmix["0020.png"] = DOUBLE
    fullmix["0021.png"] = NARROW
    kept = {e["label"]: e for e in st._entries(fullmix)}
    ok("整幅书里的可疑半幅页：仍拆 -l/-r、full=False（只警告不改数据）",
       kept["0021-l"]["full"] is False
       and {"0020-l", "0020-r"} <= set(kept),
       str(sorted(k for k in kept if k.startswith("002"))))
    ok("可疑半幅页不会被单栏判据顺手接管（不因单框就当整幅）",
       kept["0021-l"]["full"] is False, str(kept["0021-l"]))
    from desktop.services.print_plan import plan_detect_submit_entries
    from utils.book_layout import demoted_full_summary

    # 5 页单宽半幅（框宽 85%、宽<高）作基线；3 页同几何的「整幅」应改回半幅
    HALF_LIKE_FULL = [list(WIDE[0])]          # 1 槽，框与半幅完全同几何
    LANDSCAPE_FULL = [[25, 100, 975, 500]]    # 1 槽，宽>高（真整幅形态）
    demo_boxes = {f"{i:04d}.png": WIDE for i in range(1, 6)}
    demo_boxes.update({f"{i:04d}.png": HALF_LIKE_FULL for i in range(6, 9)})
    demo_boxes["0009.png"] = LANDSCAPE_FULL
    demo_sampled = [
        (Path(name).stem, boxes, W) for name, boxes in demo_boxes.items()
    ]
    demo_profile = profile_book(demo_sampled)
    ok("几何像半幅的整幅页被识别（3 页）",
       set(demo_profile.demoted_full_pages) == {"0006", "0007", "0008"},
       str(demo_profile.demoted_full_pages))
    ok("横向整幅页不被改写", "0009" not in demo_profile.demoted_full_pages)
    ok("半幅宽度基线取 2 槽页中位",
       demo_profile.half_width_median is not None
       and abs(demo_profile.half_width_median - 0.85) < 1e-9,
       str(demo_profile.half_width_median))
    ok("提示文案说明按半幅处理",
       "按半幅处理" in demoted_full_summary(demo_profile),
       demoted_full_summary(demo_profile))

    demo_entries = plan_detect_submit_entries(
        manifest_paths=[Path(name) for name in demo_boxes],
        boxes_for=lambda text: demo_boxes[Path(text).name],
        page_width_for=lambda _t: W,
    )
    demo_got = {e["label"]: e for e in demo_entries}
    ok("被修正的整幅页：产物名无后缀、role=half-unsided",
       "0006" in demo_got and demo_got["0006"]["role"] == "half-unsided",
       str(demo_got.get("0006")))
    ok("被修正页 full=True（单宽框归一化成整幅语义）",
       demo_got["0006"]["full"] is True, str(demo_got["0006"]))
    ok("真横向整幅页仍 role=full",
       demo_got["0009"]["role"] == "full", str(demo_got["0009"]))

    # 半幅样本不足（<3）→ 不改写（基线可能本身就是异常值）
    few = profile_book(
        [("a", WIDE, W), ("b", WIDE, W), ("c", HALF_LIKE_FULL, W)]
    )
    ok("半幅样本不足 3 → 不做改写（没证据不猜）",
       few.half_width_median is None and few.demoted_full_pages == (),
       f"{few.half_width_median} {few.demoted_full_pages}")

    # 页宽不可得时不得改写（保守回落，与判据一致）
    no_w = {e["label"]: e for e in st._entries(st.nine, width=0)}
    ok("页宽取不到 → 不改写身份（保守回落成半幅）",
       "0007-l" in no_w or "0007-r" in no_w, str(sorted(no_w)))
    ok("page_width_for 缺省（None）时同样不改写",
       any(
           e["label"].endswith(("-l", "-r"))
           for e in plan_rembg_submit_entries(
               manifest_paths=[Path("0007.png")],
               result_path_for=lambda s: Path(f"{s}.png"),
               boxes_for=lambda _p: WIDE,
           )
       ))
    from desktop.components.detect_stats import DetectStatsWidget

    widget = DetectStatsWidget()
    try:
        # 无结论 → 提示隐藏，标题保持原样（不能悄悄换文案，否则像 bug）
        widget.set_results(10, {}, book_note="")
        ok("无全书结论时提示隐藏、标题保持原样",
           widget.book_note.isHidden()
           and widget.title.text() == "检测结果统计",
           f"hidden={widget.book_note.isHidden()} title={widget.title.text()}")
        # 有结论 → 常驻显示（不是 Toast），标题点明「全书判读」
        note = single_column_summary(st.single_book)
        widget.set_results(10, {}, book_note=note)
        ok("单栏书结论在统计面板上常驻显示",
           not widget.book_note.isHidden() and widget.book_note.text() == note,
           f"hidden={widget.book_note.isHidden()} text={widget.book_note.text()[:40]}")
        ok("有全书结论时标题点明是全书的判读",
           "全书判读" in widget.title.text(), widget.title.text())
        # 可疑警告优先：两条都有时警告排前面（前者要人动手，后者只是告知）
        from desktop.pages.taskdetail.detect import DetectMixin

        mixed_note = DetectMixin._book_note(
            [(f"{i}", FULL, W) for i in range(1, 20)]
            + [("20", DOUBLE, W), ("21", NARROW, W)]
        )
        ok("统计面板里可疑警告排在单栏结论之前（要人动手的在前）",
           mixed_note.index("可疑") < mixed_note.index("单栏")
           if "单栏" in mixed_note else "可疑" in mixed_note,
           mixed_note[:60])
        ok("整幅书只出可疑警告，不出单栏结论",
           "可疑" in mixed_note and "已按单栏处理" not in mixed_note,
           mixed_note[:80])
        ok("单栏书只出结论，不出可疑警告",
           "已按单栏处理" in DetectMixin._book_note(
               [(f"{i}", WIDE, W) for i in range(1, 11)])
           and "可疑" not in DetectMixin._book_note(
               [(f"{i}", WIDE, W) for i in range(1, 11)]))
    finally:
        widget.deleteLater()
    import inspect as _inspect

    from desktop.components.box_kinds import BoxKindEditor
    from desktop.components.viewers.image_view.styles import (
        HALF_BOX_NAME, box_styles, is_half_page,
    )
    from utils.book_layout import is_single_wide_box

    st.wide = [list(WIDE[0])]
    narrow_box = [list(NARROW[0])]
    names_half, _c = box_styles(st.wide, (W, 1400), full=False)
    ok("整宽单框 → 标注「半幅」（不是左框/右框）",
       names_half == [HALF_BOX_NAME] == ["半幅"], str(names_half))
    # ⚠️ 用户 2026-10-23（任务 0004）：判据是**页级**的，不再看整本书是不是
    #    单栏书。混合书里的单个宽框页同样得标半幅，否则按中心硬拆左右。
    names_mixed, _c = box_styles(
        st.wide, (W, 1400), full=False, single_column=False)
    ok("不传单栏书结论时同一个框也标半幅（页级判据）",
       names_mixed == ["半幅"], str(names_mixed))
    # 真双栏页：两个框，不因单宽判据被改写
    names_two, _c = box_styles(
        [list(DOUBLE[0]), list(DOUBLE[1])], (W, 1400), full=False,
        single_column=True)
    ok("真双栏页的两个框不会被改成半幅",
       sorted(names_two) == ["右框", "左框"], str(names_two))
    # 窄单框（不足 60%）仍按位置标左框——它确实是半栏
    names_narrow, _c = box_styles(
        narrow_box, (W, 1400), full=False, single_column=True)
    ok("不足 60% 页宽的单个框仍标「左框」（那是真半栏）",
       names_narrow == ["左框"], str(names_narrow))
    # 整幅优先于半幅（整幅是显式类型）
    names_full, _c = box_styles(
        [list(FULL[0])], (W, 1400), full=True, single_column=True)
    ok("整幅页不会被标成半幅（整幅是显式类型，优先级更高）",
       names_full == ["整幅"], str(names_full))
    ok("半幅判据与 book_layout 同源（不自己算 60%）",
       is_half_page(st.wide, (W, 1400), False, True)
       and is_single_wide_box(st.wide[0], W),
       "标注层的半幅判据与 utils 不一致")
    ok("半幅判据是页级的：不传单栏书结论也认",
       is_half_page(st.wide, (W, 1400), False, False))
    ok("页宽未知时不当半幅（保守回落成左/右）",
       not is_half_page(st.wide, None, False, False))

    # 面板高亮用的 box_kinds 必须与标签同一口径（否则画面标半幅、面板亮左框）
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication, QPushButton

    st._app = QApplication.instance() or QApplication([])
    from desktop.components.viewers.image_view import ImageView

    iv = ImageView()
    try:
        # 整宽单框（84% 页宽）：页级判据，不看书级结论就是「半幅」
        wide_left = [[60, 100, 900, 1300]]
        iv.set_boxes(wide_left, QSize(W, 1400), full=False)
        ok("整宽单框 box_kinds 报 half（不依赖书级单栏结论）",
           iv.box_kinds() == ["half"], str(iv.box_kinds()))
        iv.set_single_column(True)
        ok("再传单栏书结论仍报 half（面板与画面同一「半幅」）",
           iv.box_kinds() == ["half"], str(iv.box_kinds()))
        iv.set_single_column(False)
        ok("退回非单栏结论：box_kinds 仍是 half（页级判据不随书变）",
           iv.box_kinds() == ["half"], str(iv.box_kinds()))
        # 窄单框（39% 页宽）：没有半幅证据，按位置给 left
        iv.set_boxes([[60, 100, 450, 1300]], QSize(W, 1400), full=False)
        ok("窄单框仍按位置报 left（不足 60% 不给半幅）",
           iv.box_kinds() == ["left"], str(iv.box_kinds()))
    finally:
        iv.deleteLater()

    # 面板按钮里必须有「半幅」这一段（否则用户无从「指定/查看」当前框类型）
    from desktop.components.panels.detect_panel import BOX_KIND_ITEMS

    ok("右侧「选中框类型」含「半幅」一段",
       ("half", "半幅") in BOX_KIND_ITEMS, str(BOX_KIND_ITEMS))
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from desktop.ui.segmented_toggle import SegmentedToggle

    seg = SegmentedToggle(BOX_KIND_ITEMS)
    seg.set_current("")
    seg.resize(seg.sizeHint())
    seg.show()
    _fired: list = []
    seg.current_changed.connect(_fired.append)

    def _click_at(x: int) -> list:
        _fired.clear()
        seg.set_current("")  # 每次都从"未选中"开始，确保点哪段都能发信号
        QTest.mouseClick(seg, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(x, 15))
        return list(_fired)

    ok("默认尺寸下各段仍从 2px 起、逐段等宽（观感与旧版一致）",
       [round(start) for start, _end in seg._spans()] == [2, 82, 162, 242],
       str(seg._spans()))
    ok("点段内任意位置都切换（不是只有戳到文字才算）",
       _click_at(2 + 8) == ["left"] and _click_at(2 + 72) == ["left"],
       f"{_click_at(2 + 8)} / {_click_at(2 + 72)}")
    ok("点轨道最左/最右 1px 也切换（边缘不是死区）",
       _click_at(0) == ["left"] and _click_at(seg.width() - 1) == ["full"],
       f"{_click_at(0)} / {_click_at(seg.width() - 1)}")
    seg.resize(200, SegmentedToggle.HEIGHT)  # 面板被拖窄 → 控件被压缩
    st._app.processEvents()
    ok("控件被压缩时段宽铺满（画出来的框＝能点的框）",
       abs(seg._spans()[-1][1] - 198) < 0.6, str(seg._spans()))
    ok("压缩后末段仍点得到（旧实现会被画到控件外、点不到）",
       _click_at(seg.width() - 1) == ["full"], str(_click_at(seg.width() - 1)))
    seg.resize(600, SegmentedToggle.HEIGHT)
    st._app.processEvents()
    ok("控件被拉伸时同样铺满（右侧不留不可点的空白）",
       abs(seg._spans()[-1][1] - 598) < 0.6, str(seg._spans()))
    ok("拉伸后右端 1px 仍命中末段", _click_at(598) == ["full"],
       str(_click_at(598)))
    # 每段盖一个**命中层**：真机上报"必须戳到文字才算"，根因就是命中只看
    # 自绘坐标。命中层铺满整段后，点段内任何像素都算。
    ok("每段都有铺满的命中层（段内任意像素可点）",
       len(seg._hits) == len(BOX_KIND_ITEMS)
       and all(hit.width() > 0 and hit.height() == SegmentedToggle.HEIGHT
               for hit in seg._hits),
       str([hit.geometry() for hit in seg._hits]))
    ok("命中层不引入按钮（旧守卫：切换行里不能有 QPushButton）",
       not seg.findChildren(QPushButton),
       f"{len(seg.findChildren(QPushButton))} 个按钮")
    # 快速点两下＝一次选中：Qt 不把第二下当 press 派发，不补就会"点两次才切"
    _fired.clear()
    seg.set_current("")
    QTest.mouseDClick(seg._hits[1], Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, QPoint(4, 4))
    ok("双击某段＝一次选中（快速点两下不会丢第二下）",
       _fired == ["right"], str(_fired))
    seg.close()
    seg.deleteLater()

    ok("点「半幅」只清指定、不弹提示（规则见 clear_side）",
       "box_toast" not in _inspect.getsource(BoxKindEditor.clear_side),
       "clear_side 仍在弹提示")

