# -*- coding: utf-8 -*-
"""**全书级**页形态判据（单栏书 / 整幅书里的可疑半幅）+ 命名落地。

用户 2026-10-17 定的两个极端，判据都是**跨页**的，因此不能落在只看单页的
``utils.box_geometry`` 里（它分不出「一个横跨整页的半幅框」和「真双栏」）：

1. **单栏书**：整本书基本只有一栏（每个框都是单个、且 ≥80% 页宽），页里永远不会
   并排左页+右页 ⇒ 这时 ``7-l.png`` 是**假身份**，必须直接按页码命名 ``7.png``；
2. **整幅书**：基本全是整幅却冒出半幅 ⇒ 结果可疑，**只警告、不自动改**。

本模块钉住三件事：

- 判据本体（``utils.book_layout``）的边界：80% 阈值、2 槽要求、无页宽时保守回落；
- 落地（``print_plan``）：单栏书的单宽框页退化成单槽后，命名/镜像/拼版三条
  下游语义**一起**变对——这是本改动最容易只改一半、留下拼版仍错配的地方；
- 警告方向：整幅书里的半幅**必须仍按半幅处理**（不许顺手"纠正"）。

纯规则层，不需要 YOLO、不需要 Qt。
"""

NAME = "book_layout"
DEPENDS: list[str] = []
TITLE = "全书级页形态（单栏书 / 整幅书可疑半幅）"

W = 1000
#: 单宽框：2 槽、单框、宽 85%
WIDE = [[75, 100, 925, 1300], None]
#: 窄单框：2 槽、单框、宽仅 45%（单栏书里的漏网之鱼）
NARROW = [[80, 100, 530, 1300], None]
#: 真双栏
DOUBLE = [[0, 100, 450, 1300], [520, 100, 1000, 1300]]
#: 整幅：1 槽
FULL = [[100, 100, 900, 1300]]


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok

    from utils.book_layout import (
        SINGLE_COLUMN_BOOK_RATIO, SINGLE_COLUMN_WIDTH_RATIO,
        is_single_wide_half, profile_book, single_column_summary,
        suspicious_summary,
    )

    # ---- 1. 单宽框判据的三条边界 ----
    ok("80% 是单宽框的宽度下限（阈值唯一且可查）",
       abs(SINGLE_COLUMN_WIDTH_RATIO - 0.80) < 1e-9, str(SINGLE_COLUMN_WIDTH_RATIO))
    ok("宽 85% 的单框 → 单宽框", is_single_wide_half(WIDE, W))
    ok("恰好 80% 也算（判据是 ≥ 而非 >）",
       is_single_wide_half([[100, 0, 900, 500], None], W))
    ok("宽 79% 不算单宽框（阈值之下不放行）",
       not is_single_wide_half([[105, 0, 895, 500], None], W))
    ok("宽 45% 的单框不算（那是真半栏）",
       not is_single_wide_half(NARROW, W))
    ok("双框不算（真双栏书本来就该拆 -l/-r）",
       not is_single_wide_half(DOUBLE, W))
    ok("1 槽不算（已是整幅语义，不该被这里改写）",
       not is_single_wide_half([FULL[0]], W))
    ok("页宽未知 → 保守判否（没证据不改身份）",
       not is_single_wide_half(WIDE, None) and not is_single_wide_half(WIDE, 0))
    ok("无框不算", not is_single_wide_half([], W))

    # ---- 2. 全书级：单栏书 ----
    # 9 页单宽框 + 1 页真双栏 = 90% 达标；封面/空白页不进分母
    single_book = profile_book(
        [(f"{i}", WIDE, W) for i in range(1, 10)]
        + [("10", DOUBLE, W), ("cover", [], W), ("blank", [], W)]
    )
    ok("单栏书被认定（9/10 有框页是单宽框，恰好 90%）",
       single_book.single_column_book is True, str(single_book.single_column_book))
    ok("单栏书不是整幅书", single_book.full_book is False)
    ok("单栏书的无框页不计入分母（有框页 = 10，不是 12）",
       single_book.boxed_pages == 10 and single_book.total_pages == 12,
       f"boxed={single_book.boxed_pages} total={single_book.total_pages}")
    ok("单栏书里那些单宽框页**不算**可疑（模型没判错，是形态解释）",
       single_book.suspicious_half_pages == (),
       str(single_book.suspicious_half_pages))
    ok("单栏书给出一行人读结论（提到不再拆 -l/-r）",
       "不再拆 -l/-r" in single_column_summary(single_book),
       single_column_summary(single_book))

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

    # ---- 3. 全书级：整幅书 + 可疑半幅（只警告，不改） ----
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

    # ---- 4. 命名落地：单栏书按页码命名，不拆 -l/-r ----
    from desktop.services.print_plan import plan_rembg_submit_entries

    def _entries(pages_boxes, single: bool, width=W):
        return plan_rembg_submit_entries(
            manifest_paths=[Path(f"{i:04d}.png") for i in range(1, len(pages_boxes) + 1)],
            result_path_for=lambda stem: Path(f"{stem}.png"),
            boxes_for=lambda _p: pages_boxes[_p],
            single_column_book=single,
            page_width_for=lambda _p: width,
        )

    nine = {f"000{i}.png": WIDE for i in range(1, 10)}
    nine["0010.png"] = DOUBLE

    # 单栏书的单宽框页 → label 就是页名（7.png），不是 0007-l
    got = {e["label"]: e for e in _entries(nine, True)}
    ok("单栏书：单宽框页 label 是页名（按页码命名，不带 -l/-r）",
       "0007" in got and "0007-l" not in got and "0007-r" not in got,
       str(sorted(got)))
    ok("单栏书：单宽框页按整幅语义（full=True）",
       got["0007"]["full"] is True, str(got["0007"]))
    ok("单栏书：真双栏页仍照常拆 -r/-l（不误伤双栏书里的那一页）",
       {e["label"] for e in _entries(nine, True) if e["label"].startswith("0010")}
       == {"0010-r", "0010-l"},
       str([e["label"] for e in _entries(nine, True) if e["label"].startswith("0010")]))
    ok("单栏书产出的标签无后缀 → 拼版按后缀判左右时不会错配成对",
       all(not e["label"].endswith(("-l", "-r"))
           for e in _entries(nine, True) if e["label"] != "0010"
           and e["label"] not in ("0010-l", "0010-r")))

    # 关掉开关 → 行为与改造前**逐字段一致**（这是向后兼容的底线）
    off = {e["label"]: e for e in _entries(nine, False)}
    ok("未认定单栏书时：单宽框页仍带 -l/-r（旧行为不变）",
       "0007-l" in off or "0007-r" in off, str(sorted(off)))
    ok("未认定单栏书时：单宽框页 full=False",
       (off.get("0007-l") or off.get("0007-r"))["full"] is False,
       str(off.get("0007-l") or off.get("0007-r")))

    # 整幅书里的可疑半幅：**不得**被悄悄改写成整幅
    fullmix = {f"{i:04d}.png": FULL for i in range(1, 20)}
    fullmix["0020.png"] = DOUBLE
    fullmix["0021.png"] = NARROW
    kept = {e["label"]: e for e in _entries(fullmix, False)}
    ok("整幅书里的可疑半幅页：仍拆 -l/-r、full=False（只警告不改数据）",
       kept["0021-l"]["full"] is False
       and {"0020-l", "0020-r"} <= set(kept),
       str(sorted(k for k in kept if k.startswith("002"))))
    ok("可疑半幅页不会被单栏判据顺手接管（不因单框就当整幅）",
       kept["0021-l"]["full"] is False, str(kept["0021-l"]))

    # 页宽不可得时不得改写（保守回落，与判据一致）
    no_w = {e["label"]: e for e in _entries(nine, True, width=0)}
    ok("页宽取不到 → 不改写身份（保守回落成半幅）",
       "0007-l" in no_w or "0007-r" in no_w, str(sorted(no_w)))
    ok("page_width_for 缺省（None）时同样不改写",
       any(
           e["label"].endswith(("-l", "-r"))
           for e in plan_rembg_submit_entries(
               manifest_paths=[Path("0007.png")],
               result_path_for=lambda s: Path(f"{s}.png"),
               boxes_for=lambda _p: WIDE,
               single_column_book=True,
           )
       ))

    # ---- 5. 界面接线：提示必须在统计面板上真的看得见 ----
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
        note = single_column_summary(single_book)
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

    # ---- 9. 第二步标注：单栏书里的整宽框标「半框」，不是左/右框 ----
    import inspect as _inspect

    from desktop.components.box_kinds import BoxKindEditor
    from desktop.components.viewers.image_view.styles import (
        HALF_BOX_NAME, box_styles, is_half_page,
    )
    from utils.book_layout import is_single_wide_box

    wide = [list(WIDE[0])]
    narrow_box = [list(NARROW[0])]
    names_half, _c = box_styles(wide, (W, 1400), full=False, single_column=True)
    ok("单栏书 + 整宽单框 → 标注「半框」（不是左框/右框）",
       names_half == [HALF_BOX_NAME] == ["半框"], str(names_half))
    # 关掉整本书判定 → 回到左/右框（旧行为，没证据不改形态）。
    # ⚠️ WIDE 的中心恰在中线上（cx==500），按 half_sides 规则归「右框」，
    #    所以这里只断言"是某一侧、且不是半框"——不把具体的左右钉死，
    #    免得测试反而去管位置规则的细节。
    names_off, _c = box_styles(wide, (W, 1400), full=False, single_column=False)
    ok("非单栏书时同一个框仍标左/右框（不是半框，旧行为不变）",
       names_off in (["左框"], ["右框"]), str(names_off))
    # 真双栏页：两个框，不因单栏书判定被改写
    names_two, _c = box_styles(
        [list(DOUBLE[0]), list(DOUBLE[1])], (W, 1400), full=False,
        single_column=True)
    ok("单栏书判定不会把真双栏页的两个框改成半框",
       sorted(names_two) == ["右框", "左框"], str(names_two))
    # 窄单框（不足 80%）仍按位置标左框——它确实是半栏
    names_narrow, _c = box_styles(
        narrow_box, (W, 1400), full=False, single_column=True)
    ok("不足 80% 页宽的单个框仍标「左框」（那是真半栏）",
       names_narrow == ["左框"], str(names_narrow))
    # 整幅优先于半框（整幅是显式类型）
    names_full, _c = box_styles(
        [list(FULL[0])], (W, 1400), full=True, single_column=True)
    ok("整幅页不会被标成半框（整幅是显式类型，优先级更高）",
       names_full == ["整幅"], str(names_full))
    ok("半框判据与 book_layout 同源（不自己算 80%）",
       is_half_page(wide, (W, 1400), False, True)
       and is_single_wide_box(wide[0], W),
       "标注层的半框判据与 utils 不一致")
    ok("页宽未知时不当半框（保守回落成左/右）",
       not is_half_page(wide, None, False, True))

    # 面板高亮用的 box_kinds 必须与标签同一口径（否则画面标半框、面板亮左框）
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication, QPushButton

    _app = QApplication.instance() or QApplication([])
    from desktop.components.viewers.image_view import ImageView

    iv = ImageView()
    try:
        # 用中心明确偏左的整宽框，让"左/右"的期望值有确定含义
        # （WIDE 的中心恰在中线上，按规则归右，不适合当 left 的样本）
        wide_left = [[60, 100, 900, 1300]]
        iv.set_boxes(wide_left, QSize(W, 1400), full=False)
        ok("非单栏书：整宽单框 box_kinds 报 left（按位置）",
           iv.box_kinds() == ["left"], str(iv.box_kinds()))
        iv.set_single_column(True)
        ok("单栏书：box_kinds 报 half（面板高亮与画面同为「半框」）",
           iv.box_kinds() == ["half"], str(iv.box_kinds()))
        iv.set_single_column(False)
        ok("退回非单栏：box_kinds 立刻恢复 left（不留上一本书的结论）",
           iv.box_kinds() == ["left"], str(iv.box_kinds()))
    finally:
        iv.deleteLater()

    # 面板按钮里必须有「半框」这一段（否则用户无从「指定/查看」当前框类型）
    from desktop.components.panels.detect_panel import BOX_KIND_ITEMS

    ok("右侧「选中框类型」含「半框」一段",
       ("half", "半框") in BOX_KIND_ITEMS, str(BOX_KIND_ITEMS))

    # ---- 「点框就切换」：画出来的段边界必须就是可点的段边界 ----
    # 用户 2026-10-17 报「要点到文字才能切换」。旧实现绘制与命中都直接用段宽
    # 的**绝对像素**：控件一旦被布局压缩，右几段被画到控件外（看得见一截、
    # 点不到）。现在两者共用 ``_spans()``，且永远铺满控件。
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
    _app.processEvents()
    ok("控件被压缩时段宽铺满（画出来的框＝能点的框）",
       abs(seg._spans()[-1][1] - 198) < 0.6, str(seg._spans()))
    ok("压缩后末段仍点得到（旧实现会被画到控件外、点不到）",
       _click_at(seg.width() - 1) == ["full"], str(_click_at(seg.width() - 1)))
    seg.resize(600, SegmentedToggle.HEIGHT)
    _app.processEvents()
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

    ok("点「半框」只清指定、不弹提示（规则见 clear_side）",
       "box_toast" not in _inspect.getsource(BoxKindEditor.clear_side),
       "clear_side 仍在弹提示")
    # ⚠️ 用户 2026-10-17：左右**按框的个数**分两种情况 + **指定都不弹提示**——
    #   ① 双框页（一页真有左右两页）→ 位置决定，点另一侧不写东西；
    #   ② **单框页**（古籍最常见的"只检出一侧"）→ 用户可指定左/右，指定要落库。
    #      ⚠️ 门槛**不是**"整本书是单栏书"：那个门槛让普通页点左/右毫无反应
    #      （用户第三/四轮连着报"点了没反应、要点两次"）。
    #      这一段**不查源码文本**——门槛改回去时行为断言先红，比字符串匹配可信。

    # ---- 用替身宿主**真跑一遍**：指定三类都不许弹提示（不是看源码文本）----
    class _FakeViewer:
        def __init__(self, kinds):
            self._kinds = list(kinds)
            self.selected = 0

        def box_kinds(self):
            return list(self._kinds)

        def selected_index(self):
            return self.selected

        def select_box(self, index):
            self.selected = index

    class _FakeHost:
        """最小宿主：记录 toast 与 commit，供断言"指定=静默"。"""

        def __init__(self, slots, kind, half_candidate):
            self.slots = list(slots)
            self.kind = kind
            self.half_candidate = bool(half_candidate)
            self.toasts = []
            self.commits = []
            self.resyncs = []
            self.viewer = _FakeViewer([kind])

        # BoxKindHost 协议
        def box_viewer(self):
            return self.viewer

        def box_toast(self, kind, title, content):
            self.toasts.append((kind, title, content))

        def box_raw_slots(self, _p):
            return list(self.slots)

        def box_page_is_full(self, _p):
            return self.kind == "full"

        def box_page_half_candidate(self, _p):
            return self.half_candidate

        def box_image_size(self, _p):
            return (W, 1400)

        def box_commit(self, _p, slots, select_box=None, side="keep"):
            self.commits.append({"slots": list(slots), "side": side})

        def box_confirm(self, *a, **k):
            return True

        def box_resync_kind(self, index):
            self.resyncs.append(index)

        def box_current_path_text(self):
            return "0007.png"

    # ① 普通半幅页（两个框，位置决定）：点另一侧 → 不写、不提示
    host_plain = _FakeHost([list(DOUBLE[0]), list(DOUBLE[1])], "left", False)
    BoxKindEditor(host_plain).set_kind("0007.png", 0, "right")
    ok("普通半幅页点另一侧 → 不弹提示（用户 2026-10-17）",
       host_plain.toasts == [], str(host_plain.toasts))
    ok("普通半幅页点另一侧 → 不改数据（左右由位置决定）",
       host_plain.commits == [], str(host_plain.commits))
    # ⚠️ 分段控件在**按下那一刻**就把滑块移到被点的段。这类"无操作"的点击
    #    若不回填，滑块会停在假位置（看着切了、其实没切），用户再点同一段
    #    就因为"已是当前项"而毫无反应（用户 2026-10-17 报「切换有问题」）。
    ok("普通页点另一侧 → 回填面板，滑块回到真实类型（不假停）",
       bool(host_plain.resyncs) and set(host_plain.resyncs) == {0},
       str(host_plain.resyncs))

    # ② 半框页：指定左 → 写 side=left、摆到左槽、**静默**
    host_half = _FakeHost([[60, 100, 900, 1300], None], "half", True)
    BoxKindEditor(host_half).set_kind("0007.png", 0, "left")
    ok("半框页指定左 → 落库 side=left（真生效）",
       host_half.commits and host_half.commits[-1]["side"] == "left",
       str(host_half.commits))
    ok("半框页指定左 → 槽位摆到左槽",
       host_half.commits[-1]["slots"] == [[60, 100, 900, 1300], None],
       str(host_half.commits[-1]["slots"]))
    ok("半框页指定左 → **不弹提示**（指定是即时操作）",
       host_half.toasts == [], str(host_half.toasts))

    # ③ 半框页：点「半框」→ 清掉指定（side=None）、**静默**
    host_clear = _FakeHost([[60, 100, 900, 1300], None], "left", True)
    BoxKindEditor(host_clear).set_kind("0007.png", 0, "half")
    ok("半框页点「半框」→ 清除指定（side=None）",
       host_clear.commits and host_clear.commits[-1]["side"] is None,
       str(host_clear.commits))
    ok("半框页点「半框」→ **不弹提示**",
       host_clear.toasts == [], str(host_clear.toasts))

    # ④ 普通半幅页：点「半框」没有可清除的东西 → 静默无操作
    host_noop = _FakeHost([list(DOUBLE[0]), list(DOUBLE[1])], "left", False)
    BoxKindEditor(host_noop).set_kind("0007.png", 0, "half")
    ok("普通页点「半框」→ 静默无操作（没有可清除的指定）",
       host_noop.commits == [] and host_noop.toasts == [],
       f"{host_noop.commits} {host_noop.toasts}")
    ok("普通页点「半框」→ 也回填（滑块拨回真实类型，不停在「半框」）",
       bool(host_noop.resyncs) and set(host_noop.resyncs) == {0},
       str(host_noop.resyncs))

    # ⑤ **单框页**（只检出一侧，古籍最常见）：不论整本书是不是单栏书，
    #    点左/右都必须真的换过去。
    #    ⚠️ 门槛从"整本书单栏"放成"这页只有一个框"——用户 2026-10-17 连报
    #    两次"点了没反应/要点两次"，根因就是这个门槛让普通单框页点了空转。
    host_single = _FakeHost([[60, 100, 900, 1300], None], "left", False)
    BoxKindEditor(host_single).set_kind("0007.png", 0, "right")
    ok("普通单框页点「右框」→ 真的写入指定（不再要求整本书是单栏）",
       bool(host_single.commits) and host_single.commits[-1]["side"] == "right",
       str(host_single.commits))
    ok("普通单框页点「右框」→ 槽位摆到右槽（下游命名跟着变）",
       bool(host_single.commits)
       and host_single.commits[-1]["slots"] == [None, [60, 100, 900, 1300]],
       str(host_single.commits[-1]["slots"] if host_single.commits else None))
    host_single_left = _FakeHost([None, [540, 100, 940, 1300]], "right", False)
    BoxKindEditor(host_single_left).set_kind("0007.png", 0, "left")
    ok("反向也一样：单框页点「左框」→ 摆到左槽并记 side=left",
       bool(host_single_left.commits)
       and host_single_left.commits[-1]["side"] == "left"
       and host_single_left.commits[-1]["slots"] == [[540, 100, 940, 1300], None],
       str(host_single_left.commits))

    # ⑥ **整幅页点「半框」不能是空操作**（用户 2026-10-17 报：「当前是整幅，
    #    直接点半框没有效果」）。整幅是 **1 槽**，旧实现只清 ``side`` 不动槽数
    #    ⇒ 形态仍是整幅，面板回填后又跳回「整幅」。必须摊成半幅 **2 槽**。
    #    ⚠️ 样本用**中心恰在中线上**的整页框：按位置落槽恒为右槽，正好证明
    #    "半框"这一下真的动了槽数（不是把同一个 1 槽原样写回）。
    host_full_half = _FakeHost([list(FULL[0])], "full", False)
    BoxKindEditor(host_full_half).set_kind("0007.png", 0, "half")
    ok("整幅页点「半框」→ 真的摊成 2 槽（不再停在整幅）",
       bool(host_full_half.commits)
       and host_full_half.commits[-1]["slots"] == [None, [100, 100, 900, 1300]],
       str(host_full_half.commits))
    ok("整幅页点「半框」→ 同时清除人工指定（side=None）",
       bool(host_full_half.commits)
       and host_full_half.commits[-1]["side"] is None,
       str(host_full_half.commits))

    # ⑦ **整幅页点「左框/右框」必须一步到位**（用户 2026-10-17 报：「整幅」点
    #    「左框」，会先切到「半框」，再点一次才是左框）。旧实现走 make_half 的
    #    "整幅→半幅"分支、按**中心位置**落槽，而整页框中心恰在中线上 ⇒ 恒落右槽。
    host_full_left = _FakeHost([list(FULL[0])], "full", False)
    BoxKindEditor(host_full_left).set_kind("0007.png", 0, "left")
    ok("整幅页点「左框」→ 直接摆到左槽 + side=left（一步到位，不先变半框）",
       bool(host_full_left.commits)
       and host_full_left.commits[-1]["slots"] == [[100, 100, 900, 1300], None]
       and host_full_left.commits[-1]["side"] == "left",
       str(host_full_left.commits))
    host_full_right = _FakeHost([list(FULL[0])], "full", False)
    BoxKindEditor(host_full_right).set_kind("0007.png", 0, "right")
    ok("整幅页点「右框」→ 直接摆到右槽 + side=right（一步到位）",
       bool(host_full_right.commits)
       and host_full_right.commits[-1]["slots"] == [None, [100, 100, 900, 1300]]
       and host_full_right.commits[-1]["side"] == "right",
       str(host_full_right.commits))
    ok("整幅页点「左框」→ 也回填面板（滑块不会停在半框）",
       bool(host_full_left.resyncs) and set(host_full_left.resyncs) == {0},
       str(host_full_left.resyncs))

    # 纯函数层：set_box_side 不听位置，只听调用方
    from utils.box_geometry import set_box_side

    centered = [[100, 100, 900, 1300]]  # 中心恰在中线
    ok("set_box_side 强制左：槽位 [框, None]",
       set_box_side(centered, 0, "left") == [centered[0], None],
       str(set_box_side(centered, 0, "left")))
    ok("set_box_side 强制右：槽位 [None, 框]（与位置判定无关）",
       set_box_side(centered, 0, "right") == [None, centered[0]],
       str(set_box_side(centered, 0, "right")))
    ok("set_box_side 不认的 side 原样返回（不猜）",
       set_box_side(centered, 0, "middle") == centered,
       str(set_box_side(centered, 0, "middle")))

    # 指定左右优先于「半框」判定：画面/面板都要显示成指定的那一侧
    side_names, _c = box_styles(
        wide, (W, 1400), full=False, single_column=True, side_override="left")
    ok("指定左后标「左框」，不再标「半框」（用户声明优先）",
       side_names == ["左框"], str(side_names))
    iv2 = ImageView()
    try:
        iv2.set_boxes(wide, QSize(W, 1400), full=False)
        iv2.set_single_column(True)
        ok("未指定时 box_kinds 报 half", iv2.box_kinds() == ["half"],
           str(iv2.box_kinds()))
        iv2.set_side_override("right")
        ok("指定右后 box_kinds 报 right（面板高亮跟着走）",
           iv2.box_kinds() == ["right"], str(iv2.box_kinds()))
        iv2.set_side_override(None)
        ok("清除指定后退回 half（可回头）",
           iv2.box_kinds() == ["half"], str(iv2.box_kinds()))
    finally:
        iv2.deleteLater()

    # 导出标注图（与界面同一批框）：draw_slots 走的是 slot_names_colors，
    # 它同样要认出「半框」，否则导出图上写着左框、屏幕上是半框。
    from utils.box_draw import BOX_NAME_HALF, slot_names_colors

    names_export, _c = slot_names_colors(
        [[60, 100, 900, 1300], None], W, single_column=True)
    ok("导出标注图也认「半框」（与界面同一批框、同一叫法）",
       set(names_export) == {BOX_NAME_HALF} == {"半框"}, str(names_export))
    names_export_off, _c = slot_names_colors(
        [[60, 100, 900, 1300], None], W, single_column=False)
    ok("不给单栏结论时导出仍按槽位给左/右（旧行为不变）",
       names_export_off == ["左框", "右框"], str(names_export_off))
    ok("导出侧页宽缺失时不当半框（不猜）",
       set(slot_names_colors([[60, 100, 900, 1300], None], None,
                             single_column=True)[0]) == {"左框", "右框"})

    # ---- 10. 切换类型的开销守卫（用户 2026-10-17 报「切换左/右/半框/整幅卡顿」）----
    stats_src = _inspect.getsource(DetectMixin._refresh_detect_stats)
    ok("全书判据每次刷新只算一次（以前算了两次）",
       stats_src.count("profile_book(") == 1, str(stats_src.count("profile_book(")))
    ref_src = _inspect.getsource(DetectMixin._refresh_reference_boxes)
    ok("检测编辑不再顺带重算第三步预览（解码+合成整页大图＝卡顿主因）",
       'current_stage() == "rembg"' in ref_src, "refresh_display 又变成无条件调用")
    apply_src = _inspect.getsource(DetectMixin._apply_boxes)
    ok("上屏只画一次（set_side_override 传 rerender=False）",
       "setter(side, False)" in apply_src, "切换类型会重绘两遍")
    side_src = _inspect.getsource(DetectMixin._side_override_of)
    ok("只有「半幅单框」的页才去读 side（其余页不读盘）",
       "len(slots) != 2" in side_src and "len(present) != 1" in side_src,
       "每个页都在整份读 boxes.json")

    # 面板顺序：左 → 右 → **半框** → 整幅（用户 2026-10-17：「半框要在整幅前面」）
    from utils.box_draw import BOX_KIND_INDEX as _KIND_INDEX

    kind_keys = list(_KIND_INDEX)
    ok("面板顺序＝左/右/半框/整幅（半框挨着左右、排在整幅前）",
       kind_keys == ["left", "right", "half", "full"], str(kind_keys))

    # ---- 11. 判据只有一处 ----
    from desktop.services import print_plan as _pp

    src = _inspect.getsource(_pp.plan_rembg_submit_entries)
    ok("print_plan 只调判据函数，不自己算 0.80（阈值唯一）",
       "single_column_slots(" in src
       and "0.8" not in src and "SINGLE_COLUMN_WIDTH_RATIO" not in src,
       "print_plan 里抄了宽度阈值")
    ok("单栏书归一化发生在**分支之前**（一处生效，命名/镜像/拼版全跟着变）",
       src.index("single_column_slots(") < src.index("full = is_full_content("),
       "归一化写在了分支之后")

    root = Path(__file__).resolve().parents[2]
    dup = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if not ({"dist", "build", "__pycache__", "tests"} & set(p.parts))
        and p.name != "book_layout.py"
        and "SINGLE_COLUMN_WIDTH_RATIO" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    ok("单宽框阈值只有一处定义（utils/book_layout.py）",
       dup == ["desktop/services/print_plan.py"] or dup == [],
       f"重复定义: {dup}")

    # 判定比例常量也不许被抄
    dup2 = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if not ({"dist", "build", "__pycache__", "tests"} & set(p.parts))
        and p.name != "book_layout.py"
        and "SINGLE_COLUMN_BOOK_RATIO" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    ok("单栏书比例阈值只有一处定义",
       all(p.endswith("selftests/book_layout.py") for p in dup2), f"重复: {dup2}")

    # ---- 7. 页宽必须批量读（逐页读＝O(n²) 全量解析，320 页会明显卡） ----
    from desktop.pages.taskdetail.detect import DetectMixin
    from desktop.pages.taskdetail.submit import SubmitMixin

    stats_src = _inspect.getsource(DetectMixin._refresh_detect_stats)
    ok("统计刷新用批量尺寸（image_sizes_all），不逐页 image_size",
       "image_sizes_all" in stats_src and "image_size(" not in stats_src,
       "仍是逐页读 sizes.json")
    ok("宽度取数在**循环外**读一次（循环里只查字典）",
       stats_src.index("image_sizes_all") < stats_src.index("for row, path"),
       "读盘写在了逐页循环里")
    width_src = _inspect.getsource(SubmitMixin._book_page_widths)
    ok("提交侧页宽同样批量读（一次读盘算完整本）",
       "image_sizes_all" in width_src, "提交侧还在逐页读")
    ok("派生回调只查预读好的字典，不回调里读盘",
       "widths.get(Path(text).stem, 0)" in _inspect.getsource(
           SubmitMixin._submit_entries),
       "回调里还在读盘")

    # ---- 8. 第三步预览与提交派生必须同源（否则预览 0007-l、成品 0007.png） ----
    from desktop.components.viewers.rembg_viewer.entries import EntriesMixin

    viewer_src = _inspect.getsource(EntriesMixin._book_slots)
    ok("预览侧的归一化同样调 utils.book_layout（不自己算）",
       "single_column_slots(" in viewer_src
       and "0.8" not in viewer_src and "is_single_wide_half" not in viewer_src,
       "预览侧自写了一套判据")
    entries_src = _inspect.getsource(EntriesMixin._build_entries)
    resolve_src = _inspect.getsource(EntriesMixin._resolve_source)
    ok("预览条目取框走归一化入口（主条目）",
       "_book_slots(" in entries_src, "主条目绕开了归一化")
    ok("实时合成/放大直接用条目已归一化的框（不再二次推导）",
       'entry.get("box")' in resolve_src and "_book_slots(" not in resolve_src,
       "实时合成绕开了条目")

    # 行为上验证：同一个单栏书页，预览与派生给出**同名**（都不带 -l/-r）
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication([])
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget

    viewer = RembgPreviewWidget()
    try:
        page = Path("0007.png")
        viewer.set_images(
            [page], None,
            boxes_provider=lambda _t: list(WIDE),
            border_provider=lambda: "0",
            single_column_book=True,
            page_width_provider=lambda _t: W,
        )
        labels = [e["label"] for e in viewer._entries]
        ok("单栏书第三步预览的标签＝页名（与成品同名，不带后缀）",
           labels == ["0007"], str(labels))
        # 关掉判据（非单栏书）→ 预览恢复 -l/-r，与旧行为一致
        viewer.set_images(
            [page], None,
            boxes_provider=lambda _t: list(WIDE),
            border_provider=lambda: "0",
            single_column_book=False,
            page_width_provider=lambda _t: W,
        )
        labels_off = [e["label"] for e in viewer._entries]
        ok("非单栏书时预览仍带 -l（旧行为不变）",
           labels_off == ["0007-l"], str(labels_off))
    finally:
        viewer.deleteLater()

    # ---- 11. 指定左右要真的改产物命名（不是只改标注）----
    # 用户 2026-10-17：半框页指定左/右后，这一页就不再按单栏归一化，
    # 命名/拼版都按 -l/-r 走——否则"指定"等于一句空话。
    def _with_side(side):
        return plan_rembg_submit_entries(
            manifest_paths=[Path("0007.png")],
            result_path_for=lambda s: Path(f"{s}.png"),
            boxes_for=lambda _p: [[60, 100, 900, 1300], None],
            single_column_book=True,
            page_width_for=lambda _t: W,
            side_for=lambda _t: side,
        )

    ok("半框页未指定 → 按页码命名 0007（单栏书默认）",
       [e["label"] for e in _with_side(None)] == ["0007"],
       str([e["label"] for e in _with_side(None)]))
    ok("半框页指定左 → 产物叫 0007-l（指定真的生效）",
       [e["label"] for e in _with_side("left")] == ["0007-l"],
       str([e["label"] for e in _with_side("left")]))
    ok("指定后 full=False（不再当整幅，不会漏掉镜像/命名语义）",
       [e["full"] for e in _with_side("left")] == [False],
       str([e["full"] for e in _with_side("left")]))

    # 第三步预览必须同步（否则预览 0007、成品 0007-l）
    viewer2 = RembgPreviewWidget()
    try:
        viewer2.set_images(
            [Path("0007.png")], None,
            boxes_provider=lambda _t: [[60, 100, 900, 1300], None],
            border_provider=lambda: "0",
            single_column_book=True,
            page_width_provider=lambda _t: W,
            side_for=lambda _t: "left",
        )
        ok("指定左后第三步预览也叫 0007-l（与成品同名）",
           [e["label"] for e in viewer2._entries] == ["0007-l"],
           str([e["label"] for e in viewer2._entries]))
    finally:
        viewer2.deleteLater()

    # ---- 12. 指定要能落盘并重开还在（否则等于一次性）----
    from tests.tmpdir import temp_dir as _temp_dir

    from desktop.store.annotations import AnnotationMixin

    class _Store(AnnotationMixin):
        """最小宿主：只提供 boxes_path 依赖的 task_dir / artifact 协议。"""

        def task_dir(self, _tid):
            return Path(_tmp)

        def task_diagram(self, _tid):
            raise AssertionError("主节点路径不该用到流程图")

    _tmp = _temp_dir("side_")   # ⚠️ 临时数据只落 tests/tmp/（见 tests/tmpdir.py）
    store = _Store()
    store.save_detect_boxes("t1", "0007", [[60, 100, 900, 1300], None], origin="manual")
    ok("新存档默认没有 side（不猜）", store.box_side_at(store.boxes_path("t1"), "0007") is None)
    store.set_box_side_override("t1", "0007", "left")
    ok("指定左被写进 boxes.json",
       store.box_side_at(store.boxes_path("t1"), "0007") == "left",
       str(store.box_side_at(store.boxes_path("t1"), "0007")))
    ok("批量取也读得到（一次读盘）",
       store.box_sides_all_at(store.boxes_path("t1")) == {"0007": "left"},
       str(store.box_sides_all_at(store.boxes_path("t1"))))
    # ⚠️ 拖框/缩放走 save_detect_boxes —— 不能把用户刚指定的左右顺手清掉
    store.save_detect_boxes("t1", "0007", [[70, 100, 900, 1300], None], origin="manual")
    ok("拖框后指定仍在（拖动不等于撤销指定）",
       store.box_side_at(store.boxes_path("t1"), "0007") == "left",
       "拖框把 side 清掉了")
    store.set_box_side_override("t1", "0007", None)
    ok("清除指定后读回 None（可回头）",
       store.box_side_at(store.boxes_path("t1"), "0007") is None,
       str(store.box_side_at(store.boxes_path("t1"), "0007")))