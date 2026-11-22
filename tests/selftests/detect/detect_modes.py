# -*- coding: utf-8 -*-
"""「识别文本框」两种方式（自动识别 / 人工标注）的自测（用户 2026-11-16）。

用户原话：

> 二. 改成「识别文本框」：自动识别 / 人工标注 两种模式
> 1. 自动识别：底部显示「检测文本框」按钮……自动识别是是否通过调用 yolo 来自动
>    识别文本框
> 2. 人工标注模式的时候不显示「检测文本框」按钮，只显示「提交本次任务」按钮；
>    需要用户自己在每一页画框
> 3. 人工标注模式的时候……「自动使用上一个文本框标注」默认勾选，勾选后切换一个
>    新的页面的时候，默认将上一个页面所画的标注带到新的页面（只有在上一页有标注，
>    同时新页面没有任何标注数据的时候生效），不影响已经标注过的页面
> 4. 点击「提交本次任务」的时候检查哪些页面没有进行标注……弹窗二次确认，确认按钮
>    有「继续标注」「执行任务」

本模块同时钉住**「保留框外空白」已整体移除**（面板参数、store 方法、utils 判据）。

⚠️ 全部用替身 + 纯函数：不弹模态（离屏环境弹不出来）、不跑 YOLO、不写真任务。
"""

from __future__ import annotations

from pathlib import Path

from desktop.pages.taskdetail.detect import DetectMixin

NAME = "detect_modes"
DEPENDS: list[str] = []
TITLE = "识别文本框：自动识别 / 人工标注"

#: 造数据用的页尺寸（只参与"页面大小"这类纯几何，不进本模块的断言）
W, H = 1000, 1400

LEFT = [60, 100, 460, 1300]
RIGHT = [520, 100, 940, 1300]

#: 面板默认参数（两处断言共用，免得文案漂移后只改一处）
DEFAULTS_ARGS = {"mode": "auto", "reuse_prev": True}


class _Log:
    """``log_view`` 替身：只要 ``append``。"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, text: str) -> None:
        self.lines.append(str(text))


class _DetectHost:
    """``DetectMixin`` 的最小宿主替身（按名字借实现、按需补协议）。

    ⚠️ 不继承 ``DetectMixin``：它只在 ``TYPE_CHECKING`` 期声明宿主成员，继承
    会把一整套与本模块无关的方法带进来、让人误以为它们也被测过。这里只借四个
    真实现，宿主协议显式补齐——缺哪个会立刻 AttributeError。
    """

    _inherit_boxes_from_prev = DetectMixin._inherit_boxes_from_prev
    _raw_boxes_for = DetectMixin._raw_boxes_for
    _unlabeled_pages = DetectMixin._unlabeled_pages
    _boxes_map_all = DetectMixin._boxes_map_all
    _valid_boxes = staticmethod(DetectMixin._valid_boxes)

    def __init__(self, store, task_id: str, pages: list[Path],
                 *, manual: bool = True, reuse: bool = True) -> None:
        self.store = store
        self.task_id = task_id
        self.detect_cache: dict = {}
        self.log_view = _Log()
        self._pages = list(pages)
        self._manual = manual
        self._reuse = reuse
        #: ``(页名, 槽位, origin)``：走 ``_store_slots`` 的记录（含落库）
        self.committed: list[tuple[str, list, str]] = []

    # ---- 宿主协议替身 ----
    def _manifest_paths(self) -> list[Path]:
        return list(self._pages)

    def _boxes_write_path(self):
        return self.store.boxes_path(self.task_id)

    def _boxes_read_path(self):
        return self._boxes_write_path()

    def _detect_manual(self) -> bool:
        return self._manual

    def _reuse_prev_on(self) -> bool:
        return self._reuse

    def _store_slots(self, path_text, raw, origin, select_box=None) -> None:
        """落库 + 进缓存（真实现还要上屏/刷统计，这里只留数据那一半）。"""
        self.committed.append((Path(path_text).stem, list(raw), origin))
        self.detect_cache[str(path_text)] = list(raw)
        self.store.save_detect_boxes(
            self.task_id, Path(path_text).stem, list(raw), origin=origin
        )


def _make_store(tmp, task_id: str = "0001"):
    """临时 TaskStore + 一个空任务目录（只为让 boxes.json 有地方落）。"""
    from desktop.store import TaskStore

    store = TaskStore(root=tmp)
    store.task_dir(task_id).mkdir(parents=True, exist_ok=True)
    return store


def _pages_of(store, count: int = 3, task_id: str = "0001") -> list[Path]:
    """造 count 个"页路径"（不真落图：本模块不读像素）。"""
    base = store.task_dir(task_id) / "stages" / "input"
    return [base / f"{i:04d}.png" for i in range(1, count + 1)]


def run(ctx) -> None:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFormLayout
    from qfluentwidgets import PrimaryPushButton

    from tests.selftests._context import ok
    from tests.common.tmpdir import temp_dir

    from desktop.components.panels.detect_panel import REUSE_ROW_HEIGHT, DetectPanel
    from desktop.components.panels.params_spec import DEFAULTS
    from desktop.pages.taskdetail import submit as submit_mod
    from desktop.pages.taskdetail.submit import SubmitMixin
    from desktop.pages.taskdetail.view import DetailViewMixin
    from desktop.ui import theme as T
    from desktop.ui.widgets import Divider, SectionTitle

    assert ctx is not None  # 共享夹具（QApplication）由运行器准备好

    # ============================================================ 1. 面板参数
    panel = DetectPanel()
    try:
        ok("面板参数是识别方式两个键，默认自动识别 + 沿用上一页",
           panel.get_args() == DEFAULTS_ARGS, str(panel.get_args()))
        ok("默认表与 get_args 同源（默认值不写两处）",
           DEFAULTS["detect"] == DEFAULTS_ARGS, str(DEFAULTS["detect"]))
        ok("「保留框外空白」的控件已整体删除",
           not hasattr(panel, "keep_blank")
           and not hasattr(panel, "keep_blank_hint"))

        # 表单在 ScrollArea 里：panel.layout() -> [标题行, scroll] -> widget -> form
        form = panel.findChild(QFormLayout)
        ok("能拿到参数表单（行/行高都靠它量）",
           isinstance(form, QFormLayout), str(type(form)))

        def row_visible(widget) -> bool:
            return bool(form.isRowVisible(widget))

        # 用户 2026-11-16：两段之间那条 2px 深灰横线"太深了或者太宽了"⇒ 只留空白
        ok("两段之间不再画分隔线（改留白）",
           not panel.findChildren(Divider), str(panel.findChildren(Divider)))
        ok("两段之间是实打实的空白（≥ SPACE_MD，不是 0）",
           panel.section_gap.minimumHeight() >= T.SPACE_MD,
           str(panel.section_gap.minimumHeight()))

        # 用户 2026-11-16 第 1 条：「检测本页」这个功能整个去掉（只留底部主按钮）
        ok("面板上不再有「检测本页」按钮 / 也不再发那个信号",
           not hasattr(panel, "detect_page_button")
           and not hasattr(panel, "detect_page_requested"))

        # 用户 2026-11-16 第 2 条：「删除选中框」用红色按钮，样式参考拼版的
        # 「删除选中图片」——两边都取 `theme.danger_button_qss`（唯一一份）
        ok("「删除选中框」用共享的危险按钮样式（与「删除选中图片」同款）",
           panel.delete_box.styleSheet()
           == T.danger_button_qss(padding="6px 12px 7px 12px"),
           panel.delete_box.styleSheet()[:80])

        # 用户 2026-11-16 第 4 条：没选中框也能看到分组标题「识别文本框模式」
        titles = [w.text() for w in panel.findChildren(SectionTitle)]
        ok("分组标题改叫「识别文本框模式」",
           "识别文本框模式" in titles, str(titles))

        #: 两种方式下表单总高必须一模一样（固定行高的壳给隐藏的那行留了空白）
        auto_height = form.sizeHint().height()
        ok("自动识别：勾选框藏起来（行高留着，见下一个断言）",
           panel.reuse_prev.isHidden(), "沿用开关仍可见")
        ok("自动识别也留着「自动使用上一个文本框标注」那一行的高度",
           panel.reuse_prev_slot.minimumHeight() == REUSE_ROW_HEIGHT
           and row_visible(panel.reuse_prev_slot),
           f"slot={panel.reuse_prev_slot.minimumHeight()}")

        seen: list[str] = []
        reuse_seen: list[bool] = []
        panel.mode_changed.connect(seen.append)
        panel.reuse_prev_changed.connect(reuse_seen.append)
        # 点分段的右半 = 「人工标注」
        QTest.mouseClick(
            panel.mode, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(panel.mode.width() - 8, panel.mode.height() // 2),
        )
        ok("点「人工标注」→ 参数变 manual，并通知宿主",
           panel.get_args()["mode"] == "manual" and seen == ["manual"],
           f"{panel.get_args()} / {seen}")
        ok("人工标注：「自动使用上一个文本框标注」出现在下面",
           not panel.reuse_prev.isHidden(), "沿用开关不可见")
        ok("人工标注：说明行也换口径",
           "不调 YOLO" in panel.mode_hint.text(), panel.mode_hint.text())
        ok("切换识别方式时两段的距离不变（整张表单等高，不会坍塌）",
           form.sizeHint().height() == auto_height
           and row_visible(panel.section_gap),
           f"auto={auto_height} manual={form.sizeHint().height()}")

        panel.reuse_prev.setChecked(False)
        panel.reuse_prev.setChecked(True)
        ok("沿用开关的勾选变化会通知宿主（两个方向都要）",
           reuse_seen == [False, True], str(reuse_seen))

        # 点左半 = 「自动识别」
        QTest.mouseClick(
            panel.mode, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(8, panel.mode.height() // 2),
        )
        ok("点回「自动识别」→ 勾选框藏起、表单高度不变",
           panel.get_args()["mode"] == "auto"
           and panel.reuse_prev.isHidden()
           and form.sizeHint().height() == auto_height,
           str(panel.get_args()))

        # 程序化回填（换任务 / 历史回填）也要通知宿主，否则按钮显隐停在上一个口径
        seen.clear()
        panel.apply_args({"mode": "manual", "reuse_prev": False})
        ok("程序化回填 manual 会补发 mode_changed",
           seen == ["manual"] and panel.get_args()["reuse_prev"] is False,
           f"{seen} / {panel.get_args()}")
        panel.apply_args({})
        ok("恢复默认回到自动识别 + 沿用上一页",
           panel.get_args() == DEFAULTS_ARGS, str(panel.get_args()))
        ok("回填非法值按自动识别处理（别让脏数据把面板卡成空选）",
           (panel.apply_args({"mode": "half"}) or True)
           and panel.get_args()["mode"] == "auto",
           str(panel.get_args()))
    finally:
        panel.deleteLater()

    # ==================================================== 2. 底部主按钮显隐
    class _ViewHost:
        """``_sync_detect_mode_ui`` 的最小宿主（它只碰这四个成员）。"""

        def __init__(self, *, stage: str = "detect", manual: bool = False,
                     task_id: str | None = "0001") -> None:
            self.run_button = PrimaryPushButton("检测文本框")
            self.task_id = task_id
            self._stage = stage
            self._manual = manual

        def current_stage(self) -> str:
            return self._stage

        def _detect_manual(self) -> bool:
            return self._manual

    manual_host = _ViewHost(manual=True)
    DetailViewMixin._sync_detect_mode_ui(manual_host)
    ok("人工标注：底部「检测文本框」不显示（只剩「提交本次任务」）",
       manual_host.run_button.isHidden(), "主按钮仍然可见")

    auto_host = _ViewHost(manual=False)
    DetailViewMixin._sync_detect_mode_ui(auto_host)
    ok("自动识别：底部「检测文本框」照常显示",
       not auto_host.run_button.isHidden(), "主按钮被误藏")

    other = _ViewHost(stage="rembg", manual=True)
    DetailViewMixin._sync_detect_mode_ui(other)
    ok("别的步骤一律恢复主按钮（人工标注也不能藏掉第三步的执行按钮）",
       not other.run_button.isHidden(), "主按钮在非第二步仍是隐藏")

    empty_host = _ViewHost(stage="detect", manual=True, task_id=None)
    DetailViewMixin._sync_detect_mode_ui(empty_host)
    ok("没有任务时不按人工标注藏按钮（构造期 / 空壳任务）",
       not empty_host.run_button.isHidden(), "空任务把按钮藏了")

    # =============================================== 3. 沿用上一页的框（第 3 条）
    store = _make_store(temp_dir("guji_modes_"))
    pages = _pages_of(store)
    prev, cur = str(pages[0]), str(pages[1])

    host = _DetectHost(store, "0001", pages)
    store.save_detect_boxes("0001", "0001", [LEFT, RIGHT], origin="manual")
    ok("准备：上一页有标注、本页没有任何标注",
       not host._valid_boxes(host._raw_boxes_for(cur)))

    inherited = host._inherit_boxes_from_prev(cur, prev)
    saved = store.boxes_entry_at(store.boxes_path("0001"), "0002")
    ok("人工标注 + 勾选：切到空白页时把上一页的框带过来",
       inherited and saved is not None and list(saved[0]) == [LEFT, RIGHT],
       f"inherited={inherited} saved={saved}")
    ok("带过来的框记成 manual（是用户画的，不该被自动重检当成自动结果）",
       saved is not None and saved[1] == "manual", str(saved))
    ok("带框会打一行日志（用户能看出这不是自己画的）",
       any("沿用上一页" in line for line in host.log_view.lines),
       str(host.log_view.lines))

    before = len(host.committed)
    ok("同一页不会带第二次（用户删光框后翻回来不该又长出来）",
       not host._inherit_boxes_from_prev(cur, prev)
       and len(host.committed) == before,
       str(host.committed))

    # 已经标注过的页：整页跳过
    host2 = _DetectHost(store, "0001", pages)
    store.save_detect_boxes("0001", "0002", [LEFT, None], origin="manual")
    ok("本页已有一条框 → 整页跳过（不影响已经标注过的页面）",
       not host2._inherit_boxes_from_prev(cur, prev) and not host2.committed,
       str(host2.committed))

    # 开关关掉 / 自动识别 / 上一页空 / 第一页：都不带
    off = _DetectHost(store, "0001", pages, reuse=False)
    ok("取消勾选沿用选项 → 不带",
       not off._inherit_boxes_from_prev(str(pages[2]), prev), "仍带框")

    auto = _DetectHost(store, "0001", pages, manual=False)
    ok("自动识别方式下不带（这个选项只属于人工标注）",
       not auto._inherit_boxes_from_prev(str(pages[2]), prev), "自动方式也带了框")

    # ⚠️ 用一个**框都是空**的独立 store：上面几个用例已经把 0002 写进框了，
    #    复用同一份数据会让"上一页没有标注"这条永远测不到（它确实有标注）。
    store_empty = _make_store(temp_dir("guji_modes_empty_"))
    pages_empty = _pages_of(store_empty)
    empty_prev = _DetectHost(store_empty, "0001", pages_empty)
    ok("上一页没有标注 → 没有可带的，什么都不做",
       not empty_prev._inherit_boxes_from_prev(
           str(pages_empty[2]), str(pages_empty[1])
       ) and not empty_prev.committed,
       str(empty_prev.committed))

    no_prev = _DetectHost(store, "0001", pages)
    ok("第一页（没有上一页）→ 什么都不做",
       not no_prev._inherit_boxes_from_prev(prev, None), str(no_prev.committed))

    # ========================================= 4. 提交前查漏 + 二次确认（第 4 条）
    store2 = _make_store(temp_dir("guji_modes_submit_"))
    pages2 = _pages_of(store2)
    store2.save_detect_boxes("0001", "0001", [LEFT], origin="manual")
    store2.save_detect_boxes("0001", "0003", [RIGHT], origin="manual")
    checker = _DetectHost(store2, "0001", pages2)
    missing = checker._unlabeled_pages()
    ok("「哪些页没标注」只报空的那一页（一次读盘，按页序）",
       [p.stem for p in missing] == ["0002"], str([p.stem for p in missing]))

    class _SubmitHost:
        """``_confirm_missing_labels`` 的最小宿主。"""

        _confirm_missing_labels = SubmitMixin._confirm_missing_labels
        _page_label_of = SubmitMixin._page_label_of

        def __init__(self, pages: list[Path]) -> None:
            self.log_view = _Log()
            self._missing = list(pages)

        def _unlabeled_pages(self) -> list[Path]:
            return list(self._missing)

        def _page_label(self, path) -> str:
            stem = Path(path).stem
            return str(int(stem)) if stem.isdigit() else stem

        def window(self):
            return None

    # 弹窗本体：按钮文案与两个出口（替身，不真弹）
    recorded: list[dict] = []
    answer = {"value": False}

    class _DialogStub:
        def __init__(self, title, content, parent=None, **kwargs) -> None:
            recorded.append({"title": title, "content": content, **kwargs})

        def exec(self) -> bool:
            return bool(answer["value"])

    import desktop.ui.confirm_dialog as confirm_mod

    real_cls = confirm_mod.ConfirmDialog
    try:
        confirm_mod.ConfirmDialog = _DialogStub  # type: ignore[assignment]
        answer["value"] = False
        went = submit_mod.confirm_missing_labels(None, ["2", "7"])
        answer["value"] = True
        go = submit_mod.confirm_missing_labels(None, ["2", "7"])
    finally:
        confirm_mod.ConfirmDialog = real_cls  # type: ignore[assignment]

    ok("弹窗两个按钮就是「继续标注 / 执行任务」",
       bool(recorded) and recorded[0].get("cancel_text") == "继续标注"
       and recorded[0].get("yes_text") == "执行任务", str(recorded[:1]))
    ok("「继续标注」= 不做任何事（返回 False）", went is False, str(went))
    ok("「执行任务」= 真去执行（返回 True）", go is True, str(go))

    text = submit_mod.missing_labels_message(["2", "7"])
    ok("弹窗正文点明页数与具体页码", "2 页" in text and "7" in text, text)
    many = submit_mod.missing_labels_message([str(i) for i in range(1, 21)])
    ok("页数很多时才折成「等 N 页」（不是一上来就省略）",
       "等 20 页" in many and many.count("、") == 11, many)

    host_ok = _SubmitHost([])
    ok("没有漏标注的页 → 直接放行，不打扰用户",
       host_ok._confirm_missing_labels() is True, "不该弹窗")

    calls: list[list] = []
    real_confirm = submit_mod.confirm_missing_labels
    try:
        submit_mod.confirm_missing_labels = (
            lambda parent, labels: calls.append(list(labels)) or False
        )
        stopped = _SubmitHost(pages2[:1])._confirm_missing_labels()
    finally:
        submit_mod.confirm_missing_labels = real_confirm
    ok("有漏标注的页 → 弹窗，且交进去的是页码（不是文件名）",
       calls == [["1"]] and stopped is False, f"{calls} / {stopped}")

    # ========================================== 5. 「保留框外空白」已整体移除
    import utils.book_layout as book_layout
    import utils.box_geometry as box_geometry

    ok("utils 层不再有保留空白的判据",
       not hasattr(box_geometry, "keep_blank_regions")
       and not hasattr(book_layout, "keep_blank_slots")
       and not hasattr(book_layout, "keep_blank_page_form"))
    ok("store 不再有扩展框的读写方法",
       not hasattr(store, "save_blank_regions")
       and not hasattr(store, "blank_regions_at")
       and not hasattr(store, "blank_regions_all_at"))
    ok("store 的界面状态换成识别方式两个键",
       hasattr(store, "load_detect_mode")
       and hasattr(store, "save_detect_reuse_prev")
       and not hasattr(store, "load_detect_keep_blank"))
    ok("print_plan 的提交条目不再收保留空白参数", _submit_plan_has_no_blank())

    ok("提交版本判定不再比 keep_blank",
       SubmitMixin.DETECT_SUBMIT_PARAM_KEYS == ()
       and "keep_blank" not in SubmitMixin.DETECT_PREVIEW_PARAM_KEYS,
       str(SubmitMixin.DETECT_SUBMIT_PARAM_KEYS))
    ok("识别方式从参数里读得出来（未知按键按自动识别）",
       SubmitMixin._is_manual_detect({"mode": "manual"})
       and not SubmitMixin._is_manual_detect({"mode": "auto"})
       and not SubmitMixin._is_manual_detect({}))

    # ---- 任务级落盘：ui.json 两个键，任务之间互不影响 ----
    store.save_detect_mode("0001", "manual")
    store.save_detect_reuse_prev("0001", False)
    ok("识别方式按任务记住（ui.json），读回来一致",
       store.load_detect_mode("0001") == "manual"
       and store.load_detect_reuse_prev("0001") is False,
       f"{store.load_detect_mode('0001')} / "
       f"{store.load_detect_reuse_prev('0001')}")
    ok("别的任务没设过 → None（不跟着串味）",
       store.load_detect_mode("0002") is None
       and store.load_detect_reuse_prev("0002") is None)
    ok("非法识别方式直接拒绝（别把错值写进磁盘）",
       _raises_value_error(store.save_detect_mode, "0001", "half"))


def _submit_plan_has_no_blank() -> bool:
    """``plan_detect_submit_entries`` 的签名里不再有 keep_blank/blank_for。"""
    import inspect

    from desktop.services.print_plan import plan_detect_submit_entries

    params = inspect.signature(plan_detect_submit_entries).parameters
    return "keep_blank" not in params and "blank_for" not in params


def _raises_value_error(func, *args) -> bool:
    """``func(*args)`` 是否抛 ValueError（写盘前校验用）。"""
    try:
        func(*args)
    except ValueError:
        return True
    return False
