# -*- coding: utf-8 -*-
"""第二步「保留框外空白」（**本任务**参数）自测：只改划线，不改检测结果。

用户 2026-11-11 / 2026-11-12 口径：

1. 参数对本任务**所有页面**生效，但**不是系统级**——任务 A 的设置不影响任务 B，
   默认「不保留」，并且任务要记住它（关掉重开、切走再回来都还在）；
2. 保留时：左右双框以两框相邻边界的中点为界、单框以框的**内侧边**为界，
   上下到图片边缘、外侧到图片边缘；整幅/单栏整页一张；无框页不处理；
3. ⚠️ **是划线，不是丢原始数据**：``boxes.json`` 一个字节都不动，切回去
   立刻按原框重画（用户明确点出的第二处"有误"）。

全部是纯规则断言：不需要 YOLO，也不需要 worker 子进程（可在无界面环境跑）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, Signal

from desktop.pages.taskdetail.detect import DetectMixin

NAME = "detect_keep_blank"
DEPENDS: list[str] = []
TITLE = "第二步「保留框外空白」"


class _StoreStub:
    """最小 boxes.json（只保留宿主用到的方法）。"""

    def __init__(self):
        self.data: dict = {}
        #: 手工调整过的扩展框 ``{image_key: [rect, ...]}``（真实 store 存
        #: boxes.json 的 ``blank`` 字段）
        self.blanks: dict = {}

    def boxes_path(self, task_id, **_kw):
        return Path(f"/t/{task_id}/boxes.json")

    def save_detect_boxes(self, task_id, image_key, boxes, origin="auto", **_kw):
        self.data[image_key] = {
            "boxes": [list(b) if b else None for b in boxes], "origin": origin,
        }

    def boxes_entry_at(self, path, image_key):
        entry = self.data.get(image_key)
        return (entry["boxes"], entry["origin"]) if entry else None

    def boxes_all_at(self, path):
        return {
            key: (entry["boxes"], entry["origin"])
            for key, entry in self.data.items()
        }

    def box_side_at(self, path, image_key):
        return None

    def blank_regions_at(self, path, image_key):
        regions = self.blanks.get(image_key)
        return [list(r) for r in regions] if regions else None

    def save_blank_regions(self, task_id, image_key, regions, **_kw):
        clean = [list(r) for r in (regions or [])]
        if clean:
            self.blanks[image_key] = clean
            # 真实 store 在没有检测结果时会补一条 ``boxes: []`` 的条目
            self.data.setdefault(
                image_key, {"boxes": [], "origin": "manual"}
            )
        else:
            self.blanks.pop(image_key, None)


class _LabelStub:
    def __init__(self):
        self._text = ""

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class _StripStub:
    def __init__(self, rows: int = 4):
        self._rows = rows
        self.row = -1

    def count(self):
        return self._rows

    def setCurrentRow(self, row):  # noqa: N802 - Qt 命名
        self.row = int(row)


class _ViewerStub(QObject):
    """只实现宿主用到的方法，内部用**真实的 ImageView**（规则同源）。"""

    selection_changed = Signal(int)

    def __init__(self):
        super().__init__()
        from desktop.components.viewers.image_view import ImageView

        self.view = ImageView()
        self.view.selection_changed.connect(self.selection_changed.emit)
        self.info_label = _LabelStub()
        self.path = ""
        self.strip = _StripStub()
        self.show_boxes = True
        self.reference: list = []

    def apply_boxes(self, boxes, size, info_text="", full=False, selected=-1):
        self.view.set_boxes(boxes, size, full=full, selected=selected)
        self.info_label.setText(info_text)

    def set_reference_boxes(self, boxes):
        """记录参考框（＝要裁的整页区域，画成橙色虚线）。"""
        self.reference = [list(b) for b in (boxes or [])]

    def current_path(self):
        return self.path

    def box_full_mode(self):
        return self.view.full_mode

    def box_kinds(self):
        return self.view.box_kinds()

    def set_side_override(self, side, rerender=True):
        self.view.set_side_override(side, rerender=rerender)

    def single_column(self):
        return self.view.single_column()

    def selected_index(self):
        return self.view.selected_index()

    def select_box(self, index):
        self.view.select_box(index)


class _PanelStub:
    """只提供宿主用到的东西：``get_args``（「保留框外空白」现值）。"""

    def __init__(self):
        self.keep_blank = False

    def get_args(self):
        return {"keep_blank": self.keep_blank}


class _Host(DetectMixin):
    """把 DetectMixin 挂到一个最小宿主上（真实页面里这些由 page.py 提供）。"""

    def __init__(self, path: str, size: tuple[int, int], pages: int = 4):
        self.task_id = "t1"
        setattr(self, "store", _StoreStub())
        self.detect_cache: dict = {}
        setattr(self, "detect_viewer", _ViewerStub())
        setattr(self.detect_viewer, "path", path)
        setattr(self.detect_viewer, "strip", _StripStub(pages))
        self.detect_viewer.selection_changed.connect(self._on_box_selection_changed)
        self._panel = _PanelStub()
        self._pages = [Path(f"/t/{i:04d}.png") for i in range(1, pages + 1)]
        self._size = size
        self.toasts: list = []
        #: 全书统计（真实宿主由 ``_refresh_detect_stats`` 写入）：无框页补框用。
        #: 默认「没有统计」＝整本无框，因此无框页不补（旧行为）。
        self._blank_has_stats = False
        self._blank_expects_two = False
        self._blank_typical_width = 0
        self._blank_half_width = None
        self._narrow_stems: set = set()
        #: 日志区替身（``_set_blank_region_kind`` 会 append 一行人读日志）
        self.log_view = type("_Log", (), {"append": lambda _self, _t: None})()

    # ---- 宿主回调/属性（真实页面里各自另有一份实现）----
    def panel_host_of_step(self, _step: str):
        return self._panel

    def current_node(self):
        return None

    def node_of_stage(self, _stage):
        return None

    def _node_scope(self, _node_id=None):
        return {"node_id": None, "primary_id": None}

    def _size_node_for(self, _path_text):
        return None

    def _image_size_for(self, _path_text):
        return self._size

    def _manifest_paths(self):
        return list(self._pages)

    def _toast(self, kind, title, content):
        self.toasts.append((kind, title, content))

    def current_stage(self):
        """真实页面在 detect 阶段；这里固定返回它（``_refresh_reference_boxes``
        结尾那段 rembg 刷新据此跳过）。"""
        return "detect"

    def _refresh_stats_now(self):
        pass

    def window(self):
        return None

    # ---- 断言辅助 ----
    def shown(self) -> list:
        return [list(b) for b in self.detect_viewer.view._boxes]

    def regions(self) -> list:
        return [list(b) for b in self.detect_viewer.reference]

    def editable(self) -> bool:
        return bool(self.detect_viewer.view._boxes_editable)


def run(ctx) -> None:  # noqa: ARG001 - 本模块自带夹具，不用共享 ctx
    from tests.selftests._context import ok

    from utils.box_geometry import keep_blank_regions

    W, H = 1000, 1400
    LEFT = [40, 100, 450, 1300]
    RIGHT = [520, 100, 960, 1300]
    FULL = [20, 40, 980, 1360]
    SIZE = (W, H)

    # ================= 纯规则：keep_blank_regions =================
    got = keep_blank_regions([LEFT, RIGHT], SIZE)
    ok("双框：以两框相邻边界中点 (450+520)/2=485 分界",
       [b for b, _s in got] == [[0, 0, 485, H], [485, 0, W, H]], str(got))
    ok("双框：左右两条各带侧别", [s for _b, s in got] == ["left", "right"], str(got))

    got = keep_blank_regions([LEFT, None], SIZE)
    ok("单左框：以框右侧边 450 分界，右侧留白整页高",
       [b for b, _s in got] == [[0, 0, 450, H], [450, 0, W, H]], str(got))

    got = keep_blank_regions([None, RIGHT], SIZE)
    ok("单右框：以框左侧边 520 分界，左侧留白整页高",
       [b for b, _s in got] == [[0, 0, 520, H], [520, 0, W, H]], str(got))

    got = keep_blank_regions([FULL], SIZE)
    ok("整幅：不切分，整页一张（侧别 None）",
       got == [([0, 0, W, H], None)], str(got))

    ok("无框页：不处理（返回空表）",
       keep_blank_regions([None, None], SIZE) == []
       and keep_blank_regions([], SIZE) == [], str(keep_blank_regions([], SIZE)))
    ok("页尺寸未知：返回空表（交回原有紧裁）",
       keep_blank_regions([LEFT, RIGHT], None) == [])

    # ================= 宿主侧：保留时画「扩展框」，不保留时画检测框 =========
    host = _Host("/t/0001.png", SIZE)
    KEY = cast(Any, host.detect_viewer).path
    host._store_slots(KEY, [LEFT, RIGHT], "auto")
    raw_before = host.store.data["0001"]["boxes"]

    ok("默认（不保留）：画的就是检测框本身",
       host.shown() == [LEFT, RIGHT], str(host.shown()))
    ok("默认（不保留）：框可编辑", host.editable() is True)

    host._panel.keep_blank = True
    host._on_keep_blank_changed(True)
    ok("保留：画的是**扩展框**（整页左右两半），不再画检测框",
       host.shown() == [[0, 0, 485, H], [485, 0, W, H]], str(host.shown()))
    ok("保留：扩展框仍标成左框/右框（颜色按类型走）",
       host.detect_viewer.box_kinds() == ["left", "right"],
       str(host.detect_viewer.box_kinds()))
    ok("保留：信息条说明这是要裁的整页区域、可拖动",
       "保留框外空白" in host.detect_viewer.info_label.text()
       and "拖动" in host.detect_viewer.info_label.text(),
       host.detect_viewer.info_label.text())
    ok("保留：扩展框**可以拖动调整**（能改分界与大小）",
       host.editable() is True)
    ok("保留：不再画橙色参考框（扩展框已经是实线）",
       host.regions() == [], str(host.regions()))
    ok("保留：**原始检测框一个字节都不动**",
       host.store.data["0001"]["boxes"] == raw_before,
       str(host.store.data["0001"]["boxes"]))

    # ---- 拖扩展框：写进 blank，不动检测框 ----
    dragged = [[0, 0, 520, H], [520, 0, W, H]]
    host._save_manual_boxes(KEY, dragged)
    ok("拖扩展框后落库到 blank（不是检测框）",
       host.store.blanks.get("0001") == dragged
       and host.store.data["0001"]["boxes"] == raw_before,
       f"{host.store.blanks.get('0001')} / {host.store.data['0001']['boxes']}")
    ok("拖完立刻按新区域上屏（保持左/右标签）",
       host.shown() == dragged
       and host.detect_viewer.box_kinds() == ["left", "right"],
       f"{host.shown()} / {host.detect_viewer.box_kinds()}")

    # 手工值优先于自动推导（翻页回来也还是手工值）
    host._on_keep_blank_changed(True)
    ok("切换开关不会抹掉手工调整（blank 优先于自动推导）",
       host.shown() == dragged, str(host.shown()))

    # ---- 删掉一侧：剩下的仍按几何标左框/右框，**绝不蜕变整幅** ----
    host.detect_viewer.select_box(0)
    host._delete_selected_box()
    ok("删掉左半后只剩右半，标签仍是「右框」（不蜕变成整幅）",
       host.shown() == [[520, 0, W, H]]
       and host.detect_viewer.box_kinds() == ["right"]
       and host.detect_viewer.box_full_mode() is False,
       f"{host.shown()} / {host.detect_viewer.box_kinds()} / "
       f"full={host.detect_viewer.box_full_mode()}")
    ok("删一侧后仍可再画回来（框数上限仍是 2）",
       host.detect_viewer.view.max_boxes == 2,
       str(host.detect_viewer.view.max_boxes))

    # 剩一个时再删 → **允许**（用户 2026-11-12 报的 bug："最后一个框无法删除"）
    host.detect_viewer.select_box(0)
    host.toasts.clear()
    host._delete_selected_box()
    ok("最后一个扩展框**也能删**，删完这页退回整页一张",
       host.shown() == [[0, 0, W, H]]
       and host.detect_viewer.box_kinds() == ["full"],
       f"{host.shown()} / {host.detect_viewer.box_kinds()}")
    ok("删最后一个时会说明「已改成整页一张」", bool(host.toasts), str(host.toasts))

    # 画布上按 Delete 删光（走 _boxes_edited → _save_manual_boxes 这条另一条路）
    host._save_manual_boxes(KEY, [])
    ok("画布上删光也只是退回整页一张（不会留空导致整本书少一页）",
       host.shown() == [[0, 0, W, H]] and host.store.blanks.get("0001") == [[0, 0, W, H]],
       f"{host.shown()} / {host.store.blanks.get('0001')}")

    # ---- 类型按钮对扩展框生效（整幅 / 左右） ----
    host._set_selected_box_kind("full")
    ok("点「整幅」→ 并成整页一张",
       host.shown() == [[0, 0, W, H]]
       and host.detect_viewer.box_kinds() == ["full"],
       f"{host.shown()} / {host.detect_viewer.box_kinds()}")
    host._set_selected_box_kind("left")
    ok("点「左框」→ 按页中线拆回左右两半",
       host.shown() == [[0, 0, W // 2, H], [W // 2, 0, W, H]]
       and host.detect_viewer.box_kinds() == ["left", "right"],
       f"{host.shown()} / {host.detect_viewer.box_kinds()}")
    host.toasts.clear()
    host._set_selected_box_kind("half")
    ok("「半幅」对扩展框没有意义 → 只提示、不改区域",
       bool(host.toasts) and host.shown() == [[0, 0, W // 2, H], [W // 2, 0, W, H]],
       f"{host.toasts} / {host.shown()}")

    # ---- 没有检测结果的页面也能手动画框 ----
    host.store.blanks.clear()
    EMPTY_KEY = "/t/0003.png"
    setattr(host.detect_viewer, "path", EMPTY_KEY)
    host._store_slots(EMPTY_KEY, [], "auto")
    ok("准备：空白页没有检测框、也没有扩展框", host.shown() == [], str(host.shown()))
    host._save_manual_boxes(EMPTY_KEY, [[0, 0, 500, H]])
    ok("空白页手画一个框 → 落进 blank 并在屏上显示",
       host.store.blanks.get("0003") == [[0, 0, 500, H]]
       and host.shown() == [[0, 0, 500, H]],
       f"{host.store.blanks.get('0003')} / {host.shown()}")
    ok("空白页的手画区域也判成「左框」（按几何）",
       host.detect_viewer.box_kinds() == ["left"],
       str(host.detect_viewer.box_kinds()))
    setattr(host.detect_viewer, "path", KEY)

    # 翻到别的页：没有手工值 → 按检测框现算
    host.store.blanks.clear()
    host._store_slots(KEY, [LEFT, RIGHT], "auto")
    setattr(host.detect_viewer, "path", "/t/0002.png")
    host._store_slots("/t/0002.png", [None, RIGHT], "auto")
    ok("保留：另一页（单右框）按检测框现算扩展框",
       host.shown() == [[0, 0, 520, H], [520, 0, W, H]], str(host.shown()))
    setattr(host.detect_viewer, "path", KEY)

    # 切回去：显示检测框（扩展框不再显示）
    host._panel.keep_blank = False
    host._on_keep_blank_changed(False)
    ok("切回「不保留」：立刻回到底层检测框",
       host.shown() == [LEFT, RIGHT], str(host.shown()))
    ok("开关来回切换后检测框依然一致",
       host.store.data["0001"]["boxes"] == raw_before,
       str(host.store.data["0001"]["boxes"]))

    # 单栏页（单个宽框 → 整页归一化）：保留时整页一张
    host._panel.keep_blank = True
    WIDE = [60, 80, 940, 1340]
    host.store.blanks.clear()
    host._store_slots(KEY, [WIDE, None], "auto")
    ok("保留：单栏宽框页整页一张（标「整幅」，与提交产物同一口径）",
       host.shown() == [[0, 0, W, H]]
       and host.detect_viewer.box_full_mode() is True,
       f"{host.shown()} / full={host.detect_viewer.box_full_mode()}")

    # 无框页：**没有统计依据**（整本书一个框都没有）时保持旧行为，不凭空造区域
    host._store_slots(KEY, [], "auto")
    ok("保留：无框页但全书无统计依据 ⇒ 不画区域（skip）",
       host.shown() == [], str(host.shown()))

    # ---- 无框页补框（用户 2026-11-12 第 1 条）----
    # 双栏书 + 本页装得下两个（典型框宽 0.45×1000＝450，两个 900 < 1000）
    host._blank_has_stats = True
    host._blank_expects_two = True
    host._blank_typical_width = W
    host._blank_half_width = 0.45
    host._store_slots(KEY, [], "auto")
    ok("保留：双栏书无框页 ⇒ 按页中线拆左右两半",
       host.shown() == [[0, 0, W // 2, H], [W // 2, 0, W, H]], str(host.shown()))
    ok("保留：补出来的两半标成左框 / 右框",
       host.detect_viewer.box_kinds() == ["left", "right"],
       str(host.detect_viewer.box_kinds()))
    ok("保留：补出来的框**不写进检测结果、也不写进手工区域**（只是显示/裁图口径）",
       host.store.data.get("0001", {}).get("boxes") == []
       and not host.store.blanks.get("0001"),
       f"{host.store.data.get('0001')} / {host.store.blanks.get('0001')}")

    # 同一条规则的反面：典型框宽大到本页装不下两个 ⇒ 只出一个（整页一张）
    host._blank_half_width = 0.60  # 2×600×1.02＝1224 > 1000
    host._store_slots(KEY, [], "auto")
    ok("保留：本页只能容纳一个文本框 ⇒ 整页一张（不拆两半）",
       host.shown() == [[0, 0, W, H]], str(host.shown()))
    ok("保留：只容纳一个时标「整幅」", host.detect_viewer.box_full_mode() is True)

    # 用户 2026-11-12 第 2 条：只检出一个框、统计上该有两个、且**装得下**两个
    # ⇒ 分割线落在检出框的**内侧边**（左框取右边界 485）
    host._blank_half_width = 0.45
    host._store_slots(KEY, [LEFT, None], "auto")
    ok("保留：单框 + 装得下两个 ⇒ 分界线在检出框的内侧边（450）",
       host.shown() == [[0, 0, 450, H], [450, 0, W, H]], str(host.shown()))

    # 同样只检出一个框，但本页**装不下**两个 ⇒ 整页一张（不硬切）
    host._blank_half_width = 0.60
    host._store_slots(KEY, [LEFT, None], "auto")
    ok("保留：单框 + 装不下两个 ⇒ 整页一张（不硬切）",
       host.shown() == [[0, 0, W, H]], str(host.shown()))

    # 收尾：把统计关掉，别把"补框"状态带给后面的整幅页断言
    host._blank_has_stats = False
    host._blank_expects_two = False
    host._blank_half_width = None

    # 从没检出过的空白页**没有 boxes.json 条目**：预览同样要画补出来的框
    # （否则"提交产物里有这页的图、画布上却是空的"，用户 2026-11-12 会当场发现）
    host._blank_has_stats = True
    host._blank_expects_two = True
    host._blank_typical_width = W
    host._blank_half_width = 0.45
    FRESH = "/t/0003.png"
    host.detect_cache.pop(FRESH, None)
    host._detect_image_selected(2, FRESH)
    ok("保留：从没检出过的空白页（无 boxes.json 条目）也画出补框",
       host.shown() == [[0, 0, W // 2, H], [W // 2, 0, W, H]], str(host.shown()))
    host.detect_cache.pop(FRESH, None)
    host._blank_has_stats = False
    host._blank_expects_two = False
    host._blank_half_width = None
    # 整幅页：整页一张
    host._store_slots(KEY, [FULL], "auto")
    ok("保留：整幅页整页一张、标「整幅」",
       host.shown() == [[0, 0, W, H]] and host.detect_viewer.box_kinds() == ["full"],
       f"{host.shown()} / {host.detect_viewer.box_kinds()}")

    # ---- 提交侧：参数进了「提交产物」的版本判定（改它必须重新提交）----
    from desktop.pages.taskdetail.submit import SubmitMixin

    ok("「保留空白」被列进提交产物参数键（改了要重新提交）",
       "keep_blank" in getattr(SubmitMixin, "DETECT_SUBMIT_PARAM_KEYS", ()),
       str(getattr(SubmitMixin, "DETECT_SUBMIT_PARAM_KEYS", ())))
    ok("「保留空白」不进「检测结果」参数键（它不影响检测）",
       "keep_blank" not in getattr(SubmitMixin, "DETECT_PREVIEW_PARAM_KEYS", ()),
       str(getattr(SubmitMixin, "DETECT_PREVIEW_PARAM_KEYS", ())))

    # ---- 面板：分「全局参数 / 本页参数」两段，中间一条看得见的分割线 ----
    from PySide6.QtWidgets import QApplication, QFormLayout

    from desktop.components.panels.detect_panel import DetectPanel
    from desktop.ui import theme as T
    from desktop.ui.widgets import Divider, SectionTitle

    app = QApplication.instance() or QApplication([])
    panel = DetectPanel()
    form = panel.findChild(QFormLayout)
    ok("表单里有两个分组标题（本任务参数 / 本页参数，与「检测结果统计」同款）",
       [t.text() for t in panel.findChildren(SectionTitle)]
       == ["本任务参数", "本页参数"],
       str([t.text() for t in panel.findChildren(SectionTitle)]))

    def _row_of(widget) -> int:
        return form.indexOf(widget) if form is not None else -1

    dividers = panel.findChildren(Divider)
    ok("两段之间有一条 2px 的分割线（浅灰面板上要看得见）",
       len(dividers) == 1 and dividers[0].height() == 2, str(len(dividers)))
    sep = dividers[0]
    ok("分割线用的是专用色 SEPARATOR（不是最淡的分隔色）",
       sep._color == T.SEPARATOR and T.SEPARATOR != T.BORDER_SOFT, str(sep._color))
    ok("顺序＝本任务参数 → 分割线 → 本页参数（分段清楚、与检测本页拉开距离）",
       _row_of(panel.keep_blank) > 0
       and _row_of(sep) > _row_of(panel.keep_blank)
       and _row_of(panel.delete_box) > _row_of(sep)
       and form.itemAt(0, QFormLayout.ItemRole.FieldRole).widget().__class__
       is SectionTitle,
       f"keep={_row_of(panel.keep_blank)} sep={_row_of(sep)} "
       f"del={_row_of(panel.delete_box)}")
    ok("参数名独占一行（不再挤在标签列里）、开关铺满整行",
       form.itemAt(_row_of(panel.keep_blank), QFormLayout.ItemRole.LabelRole)
       is None
       and panel.keep_blank.sizePolicy().horizontalPolicy()
       == panel.keep_blank.sizePolicy().Policy.Expanding,
       str(panel.keep_blank.sizePolicy().horizontalPolicy()))
    ok("面板默认「不保留」，且**默认态也有文字说明**（用户 2026-11-12）",
       panel.get_args() == {"keep_blank": False}
       and bool(panel.keep_blank_hint.text().strip())
       and "只裁框本身" in panel.keep_blank_hint.text(),
       f"{panel.get_args()} / {panel.keep_blank_hint.text()}")
    seen: list = []
    panel.keep_blank_changed.connect(seen.append)
    panel.resize(360, 320)
    panel.show()
    app.processEvents()

    def _click_blank_side(x: int) -> None:
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        QTest.mouseClick(
            panel.keep_blank, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier, QPoint(x, panel.keep_blank.height() // 2),
        )
        app.processEvents()

    # 真点一下（不是直调槽）：左段＝保留、右段＝不保留
    _click_blank_side(6)
    ok("点「保留」段真的切过去（走 Qt 的命中路径，不是只发给自己看）",
       seen == [True] and panel.get_args() == {"keep_blank": True},
       f"{seen} / {panel.get_args()}")
    ok("「保留」的说明行讲清裁什么、而且框可以拖",
       bool(panel.keep_blank_hint.text().strip())
       and "拖动" in panel.keep_blank_hint.text(),
       panel.keep_blank_hint.text())
    ok("「保留」时面板的类型/删框照旧可用（现在改的是扩展框）",
       panel.box_kind.is_item_enabled("left")
       and panel.box_kind.is_item_enabled("full"),
       f"{panel.box_kind.is_item_enabled('left')} / "
       f"{panel.box_kind.is_item_enabled('full')}")
    _click_blank_side(panel.keep_blank.width() - 6)
    ok("点「不保留」段切回去，说明行换成「只裁框本身」",
       seen == [True, False] and panel.get_args() == {"keep_blank": False}
       and "只裁框本身" in panel.keep_blank_hint.text(),
       f"{seen} / {panel.get_args()} / {panel.keep_blank_hint.text()}")
    panel.apply_args({"keep_blank": False})
    ok("程序化回填不再发信号（否则会自我递归）",
       seen == [True, False], str(seen))
    app.processEvents()

    # ========= 任务级：A 的设置不影响 B，关掉重开还记得（用户 2026-11-12）=========
    #
    # 「保留框外空白」是**任务级**参数，不是系统级：它随本任务的参数暂存
    # （``tasks/<任务号>/drafts/<阶段>~<节点>.json``）落盘，任务之间互不影响。
    # 这里用**真实详情页 + 真实 store**（临时目录）跑，替身测不出这条。
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.store.store import TaskStore
    from desktop.ui.widgets import SectionTitle
    from tests.selftests._context import silence_source_prompt
    from tests.tmpdir import temp_dir

    task_store = TaskStore(root=temp_dir("guji_keep_blank_tasks_"))
    tid_a = task_store.create_task(None, "", name="任务A")
    tid_b = task_store.create_task(None, "", name="任务B")
    page = TaskDetailPage(task_store)
    page.resize(1280, 820)
    page.show()
    silence_source_prompt(page)
    app.processEvents()

    def _open_detect(target_page):
        """切到第二步并返回 detect 面板（面板惰性：这一步才建出来）。"""
        target_page._select_stage(1)
        app.processEvents()
        return target_page.control_stack.widget(1).panel

    def _click_keep(target_panel, x_ratio: float) -> None:
        """按比例点分段开关（0.25＝左段「保留」，0.75＝右段「不保留」）。"""
        toggle = target_panel.keep_blank
        QTest.mouseClick(
            toggle, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
            QPoint(int(toggle.width() * x_ratio), toggle.height() // 2),
        )
        app.processEvents()

    page.set_task(tid_a)
    app.processEvents()
    panel_a = _open_detect(page)
    ok("新任务默认「不保留」（任务级默认值，不继承任何别的任务）",
       panel_a.get_args() == {"keep_blank": False}, str(panel_a.get_args()))

    _click_keep(panel_a, 0.25)  # 左段＝保留
    page._flush_param_drafts()
    ok("任务A 点「保留」→ 面板与宿主同一口径（都读到 True）",
       panel_a.get_args() == {"keep_blank": True}
       and page._keep_blank_on() is True,
       f"{panel_a.get_args()} / {page._keep_blank_on()}")
    draft_a = task_store.load_draft(tid_a, "detect", page.node_of_stage("detect"))
    ok("任务A 的选择落在**任务级 ui.json**（不是按节点分的 drafts）",
       task_store.load_detect_keep_blank(tid_a) is True
       and (draft_a or {}).get("keep_blank") is None,
       f"ui={task_store.load_detect_keep_blank(tid_a)} draft={draft_a}")

    page.set_task(tid_b)
    app.processEvents()
    panel_b = _open_detect(page)
    ok("切到任务B：仍是「不保留」（任务A 的设置不影响任务B）",
       panel_b.get_args() == {"keep_blank": False}, str(panel_b.get_args()))
    ok("任务B 的任务级状态里没有这一项（参数没跨任务串味）",
       task_store.load_detect_keep_blank(tid_b) is None,
       str(task_store.load_detect_keep_blank(tid_b)))

    page.set_task(tid_a)
    app.processEvents()
    panel_a2 = _open_detect(page)
    ok("切回任务A：还是「保留」（本任务记住了自己那份）",
       panel_a2.get_args() == {"keep_blank": True}, str(panel_a2.get_args()))

    # 关掉详情页再开一个＝关程序重开：参数得从磁盘回填，不能只在内存里
    page.close()
    reopened = TaskDetailPage(task_store)
    reopened.resize(1280, 820)
    reopened.show()
    silence_source_prompt(reopened)
    reopened.set_task(tid_a)
    app.processEvents()
    panel_a3 = _open_detect(reopened)
    ok("关掉重开再进任务A：参数仍然记着（真的落盘了）",
       panel_a3.get_args() == {"keep_blank": True}, str(panel_a3.get_args()))
    ok("分组标题写的是「本任务参数」，不再出现「全局参数」",
       any(isinstance(w, SectionTitle) and w.text() == "本任务参数"
           for w in panel_a3.findChildren(SectionTitle))
       and all("全局" not in w.text()
               for w in panel_a3.findChildren(SectionTitle)),
       str([w.text() for w in panel_a3.findChildren(SectionTitle)]))
    reopened.close()
    app.processEvents()
