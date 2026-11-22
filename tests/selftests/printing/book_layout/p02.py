# -*- coding: utf-8 -*-
"""用替身宿主**真跑一遍**：指定三类都不许弹提示（不是看源码文本） / 10. 切换类型的开销守卫（用户 2026-10-17 报「切换左/右/半幅/整幅卡顿」） / 11. 判据只有一处 / 7. 页宽必须批量读（逐页读＝O(n²) 全量解析，320 页会明显卡） / 8. 第三步预览与提交派生必须同源（否则预览 0007-l、成品 0007.png） / 11. 指定左右要真的改产物命名（不是只改标注） / 12. 指定要能落盘并重开还在（否则等于一次性）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import DOUBLE, FULL, NARROW, W, WIDE, ROOT
    from desktop.store.annotations import AnnotationMixin
    from utils.box_draw import BOX_NAME_HALF, slot_names_colors
    from desktop.components.box_kinds import BoxKindEditor
    from desktop.pages.taskdetail.detect import DetectMixin
    from desktop.components.viewers.rembg_viewer.entries import EntriesMixin
    from desktop.components.viewers.image_view import ImageView
    from pathlib import Path
    from PySide6.QtWidgets import QApplication, QPushButton
    from PySide6.QtCore import QSize
    from desktop.components.viewers.rembg_viewer import RembgPreviewWidget
    from desktop.pages.taskdetail.submit import SubmitMixin
    from utils.box_draw import BOX_KIND_INDEX as _KIND_INDEX
    import inspect as _inspect
    from desktop.services import print_plan as _pp
    from tests.common.tmpdir import temp_dir as _temp_dir
    from desktop.components.viewers.image_view.styles import (
        HALF_BOX_NAME, box_styles, is_half_page,
    )
    from tests.selftests._context import ok
    from desktop.services.print_plan import plan_rembg_submit_entries
    from utils.box_geometry import set_box_side
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

    # ② 半幅页：指定左 → 写 side=left、摆到左槽、**静默**
    host_half = _FakeHost([[60, 100, 900, 1300], None], "half", True)
    BoxKindEditor(host_half).set_kind("0007.png", 0, "left")
    ok("半幅页指定左 → 落库 side=left（真生效）",
       host_half.commits and host_half.commits[-1]["side"] == "left",
       str(host_half.commits))
    ok("半幅页指定左 → 槽位摆到左槽",
       host_half.commits[-1]["slots"] == [[60, 100, 900, 1300], None],
       str(host_half.commits[-1]["slots"]))
    ok("半幅页指定左 → **不弹提示**（指定是即时操作）",
       host_half.toasts == [], str(host_half.toasts))

    # ③ 半幅页：点「半幅」→ 清掉指定（side=None）、**静默**
    host_clear = _FakeHost([[60, 100, 900, 1300], None], "left", True)
    BoxKindEditor(host_clear).set_kind("0007.png", 0, "half")
    ok("半幅页点「半幅」→ 清除指定（side=None）",
       host_clear.commits and host_clear.commits[-1]["side"] is None,
       str(host_clear.commits))
    ok("半幅页点「半幅」→ **不弹提示**",
       host_clear.toasts == [], str(host_clear.toasts))

    # ④ 普通半幅页：点「半幅」没有可清除的东西 → 静默无操作
    host_noop = _FakeHost([list(DOUBLE[0]), list(DOUBLE[1])], "left", False)
    BoxKindEditor(host_noop).set_kind("0007.png", 0, "half")
    ok("普通页点「半幅」→ 静默无操作（没有可清除的指定）",
       host_noop.commits == [] and host_noop.toasts == [],
       f"{host_noop.commits} {host_noop.toasts}")
    ok("普通页点「半幅」→ 也回填（滑块拨回真实类型，不停在「半幅」）",
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

    # ⑥ **整幅页点「半幅」不能是空操作**（用户 2026-10-17 报：「当前是整幅，
    #    直接点半幅没有效果」）。整幅是 **1 槽**，旧实现只清 ``side`` 不动槽数
    #    ⇒ 形态仍是整幅，面板回填后又跳回「整幅」。必须摊成半幅 **2 槽**。
    #    ⚠️ 样本用**中心恰在中线上**的整页框：按位置落槽恒为右槽，正好证明
    #    "半幅"这一下真的动了槽数（不是把同一个 1 槽原样写回）。
    host_full_half = _FakeHost([list(FULL[0])], "full", False)
    BoxKindEditor(host_full_half).set_kind("0007.png", 0, "half")
    ok("整幅页点「半幅」→ 真的摊成 2 槽（不再停在整幅）",
       bool(host_full_half.commits)
       and host_full_half.commits[-1]["slots"] == [None, [100, 100, 900, 1300]],
       str(host_full_half.commits))
    ok("整幅页点「半幅」→ 同时清除人工指定（side=None）",
       bool(host_full_half.commits)
       and host_full_half.commits[-1]["side"] is None,
       str(host_full_half.commits))

    # ⑦ **整幅页点「左框/右框」必须一步到位**（用户 2026-10-17 报：「整幅」点
    #    「左框」，会先切到「半幅」，再点一次才是左框）。旧实现走 make_half 的
    #    "整幅→半幅"分支、按**中心位置**落槽，而整页框中心恰在中线上 ⇒ 恒落右槽。
    host_full_left = _FakeHost([list(FULL[0])], "full", False)
    BoxKindEditor(host_full_left).set_kind("0007.png", 0, "left")
    ok("整幅页点「左框」→ 直接摆到左槽 + side=left（一步到位，不先变半幅）",
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
    ok("整幅页点「左框」→ 也回填面板（滑块不会停在半幅）",
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

    # 指定左右优先于「半幅」判定：画面/面板都要显示成指定的那一侧
    side_names, _c = box_styles(
        st.wide, (W, 1400), full=False, single_column=True, side_override="left")
    ok("指定左后标「左框」，不再标「半幅」（用户声明优先）",
       side_names == ["左框"], str(side_names))
    iv2 = ImageView()
    try:
        iv2.set_boxes(st.wide, QSize(W, 1400), full=False)
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
    # 它同样要认出「半幅」，否则导出图上写着左框、屏幕上是半幅。
    from utils.box_draw import BOX_NAME_HALF, slot_names_colors

    names_export, _c = slot_names_colors(
        [[60, 100, 900, 1300], None], W, single_column=True)
    ok("导出标注图也认「半幅」（与界面同一批框、同一叫法）",
       set(names_export) == {BOX_NAME_HALF} == {"半幅"}, str(names_export))
    names_export_off, _c = slot_names_colors(
        [[60, 100, 900, 1300], None], W, single_column=False)
    ok("导出侧同样是页级判据：不传单栏结论也认半幅",
       set(names_export_off) == {"半幅"}, str(names_export_off))
    ok("导出侧页宽缺失时不当半幅（不猜）",
       set(slot_names_colors([[60, 100, 900, 1300], None], None,
                             single_column=True)[0]) == {"左框", "右框"})
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

    # 面板顺序：左 → 右 → **半幅** → 整幅（用户 2026-10-17：「半幅要在整幅前面」）
    from utils.box_draw import BOX_KIND_INDEX as _KIND_INDEX

    kind_keys = list(_KIND_INDEX)
    ok("面板顺序＝左/右/半幅/整幅（半幅挨着左右、排在整幅前）",
       kind_keys == ["left", "right", "half", "full"], str(kind_keys))
    from desktop.services import print_plan as _pp

    src = _inspect.getsource(_pp.plan_rembg_submit_entries)
    ok("print_plan 只调判据函数，不自己算 0.80（阈值唯一）",
       "page_single_wide_slots(" in src
       and "0.8" not in src and "SINGLE_COLUMN_WIDTH_RATIO" not in src,
       "print_plan 里抄了宽度阈值")
    ok("页级归一化发生在**分支之前**（一处生效，命名/镜像/拼版全跟着变）",
       src.index("page_single_wide_slots(") < src.index("full = is_full_content("),
       "归一化写在了分支之后")

    root = ROOT
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
       all(p.endswith("selftests/printing/book_layout/") for p in dup2), f"重复: {dup2}")
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
    from desktop.components.viewers.rembg_viewer.entries import EntriesMixin

    viewer_src = _inspect.getsource(EntriesMixin._book_slots)
    ok("预览侧的归一化同样调 utils.book_layout（不自己算）",
       "page_single_wide_slots(" in viewer_src
       and "0.8" not in viewer_src and "is_single_wide_half" not in viewer_src,
       "预览侧自写了一套判据")
    entries_src = _inspect.getsource(EntriesMixin._build_entries)
    resolve_src = _inspect.getsource(EntriesMixin._resolve_source)
    ok("预览条目取框走归一化入口（主条目）",
       "_book_slots(" in entries_src, "主条目绕开了归一化")
    ok("实时合成/放大直接用条目已归一化的框（不再二次推导）",
       'entry.get("box")' in resolve_src and "_book_slots(" not in resolve_src,
       "实时合成绕开了条目")

    # 行为上验证：同一个整宽单框页，预览与派生给出**同名**（都不带 -l/-r）
    from PySide6.QtWidgets import QApplication

    st._app = QApplication.instance() or QApplication([])
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
        ok("第三步预览的标签＝页名（与成品同名，不带后缀）",
           labels == ["0007"], str(labels))
        # 不传书级结论（混合书/0004 那种）：页级判据照样给出同样的名字
        viewer.set_images(
            [page], None,
            boxes_provider=lambda _t: list(WIDE),
            border_provider=lambda: "0",
            single_column_book=False,
            page_width_provider=lambda _t: W,
        )
        labels_off = [e["label"] for e in viewer._entries]
        ok("不传单栏书结论时预览同样是 0007（页级判据）",
           labels_off == ["0007"], str(labels_off))
        # 窄单框（不足 60%）仍带 -l：没有半幅证据，旧行为不变
        viewer.set_images(
            [page], None,
            boxes_provider=lambda _t: list(NARROW),
            border_provider=lambda: "0",
            single_column_book=True,
            page_width_provider=lambda _t: W,
        )
        labels_narrow = [e["label"] for e in viewer._entries]
        ok("窄单框预览仍带 -l（不足 60% 不改写身份）",
           labels_narrow == ["0007-l"], str(labels_narrow))
    finally:
        viewer.deleteLater()
    def _with_side(side):
        return plan_rembg_submit_entries(
            manifest_paths=[Path("0007.png")],
            result_path_for=lambda s: Path(f"{s}.png"),
            boxes_for=lambda _p: [[60, 100, 900, 1300], None],
            page_width_for=lambda _t: W,
            side_for=lambda _t: side,
        )

    ok("半幅页未指定 → 按页码命名 0007（页级归一化默认）",
       [e["label"] for e in _with_side(None)] == ["0007"],
       str([e["label"] for e in _with_side(None)]))
    ok("半幅页指定左 → 产物叫 0007-l（指定真的生效）",
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
    from tests.common.tmpdir import temp_dir as _temp_dir

    from desktop.store.annotations import AnnotationMixin

    class _Store(AnnotationMixin):
        """最小宿主：只提供 boxes_path 依赖的 task_dir / artifact 协议。"""

        def task_dir(self, _tid):
            return Path(_tmp)

        def task_diagram(self, _tid):
            raise AssertionError("主节点路径不该用到流程图")

    _tmp = _temp_dir("side_")   # ⚠️ 临时数据只落 tests/tmp/（见 tests/common/tmpdir.py）
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

