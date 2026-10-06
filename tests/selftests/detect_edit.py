# -*- coding: utf-8 -*-
"""第二步人工干预自测：**框的类型是框自己的属性**，不随"还剩几个框"变化。

用户 2026-09-29 给的 6 条规则，逐条守：

1. 删掉其中一个框，**不改变其他框的类型**（类型按槽位存，不是按元素个数推的）；
2. 自己画的框按**中心位置**判左/右，移动后动态重算（拖过中线即换边）；
3. 用户显式选了「整幅」后，无论怎么移动/缩放都还是整幅；
4. 整幅**只能有一个框**：想再设一个 → 弹提示（对话框里可直接删除其他框）；
5. 整幅与左右半幅**互斥**：设整幅时若还有其他框 → 同一条提示；
6. 点类型按钮＝切换选中框的类型；没选中框时＝选中该类型的框。

全部是纯规则断言：不需要 YOLO，也不需要 worker 子进程（可在无界面环境跑）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from desktop.pages.taskdetail.detect import DetectMixin

NAME = "detect_edit"
DEPENDS: list[str] = []
TITLE = "第二步人工干预（框类型）"


class _StoreStub:
    """最小 boxes.json：只保留宿主用到的几个方法。"""

    def __init__(self):
        self.data: dict = {}

    def save_detect_boxes(self, task_id, image_key, boxes, origin="auto"):
        self.data[image_key] = {
            "boxes": [list(b) if b else None for b in boxes], "origin": origin,
        }

    def detect_boxes_entry(self, task_id, image_key):
        entry = self.data.get(image_key)
        return (entry["boxes"], entry["origin"]) if entry else None

    def detect_boxes_all(self, task_id):
        return {
            key: (entry["boxes"], entry["origin"])
            for key, entry in self.data.items()
        }


class _LabelStub:
    def __init__(self):
        self._text = ""

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class _StripStub:
    """缩略图条的最小替身：统计明细点页码时宿主只用到 count/setCurrentRow。"""

    def __init__(self, rows: int = 4):
        self._rows = rows
        self.row = -1

    def count(self):
        return self._rows

    def setCurrentRow(self, row):  # noqa: N802 - Qt 命名
        self.row = int(row)


class _ViewerStub(QObject):
    """只实现宿主用到的方法，内部用**真实的 ImageView**（规则同源）。

    与真实 `ImageViewerWidget` 一样把 `selection_changed` 转发出来，
    这样"选中态变化 → 宿主回填面板"这条链在自测里也是真的走了一遍。
    """

    selection_changed = Signal(int)

    def __init__(self):
        super().__init__()
        from desktop.components.viewers.image_view import ImageView

        self.view = ImageView()
        self.view.selection_changed.connect(self.selection_changed.emit)
        self.info_label = _LabelStub()
        self.path = ""
        self.reference = None
        self.strip = _StripStub()

    def apply_boxes(self, boxes, size, info_text="", full=False, selected=-1):
        self.view.set_boxes(boxes, size, full=full, selected=selected)
        self.info_label.setText(info_text)

    def set_reference_boxes(self, boxes):
        self.reference = boxes

    def current_path(self):
        return self.path

    def box_full_mode(self):
        return self.view.full_mode

    def box_kinds(self):
        return self.view.box_kinds()

    def selected_index(self):
        return self.view.selected_index()

    def select_box(self, index):
        self.view.select_box(index)


class _PanelStub:
    def __init__(self):
        self.selection = None

    def set_box_selection(self, index, kind):
        self.selection = (index, kind)


class _StackStub:
    def __init__(self, panel):
        self._panel = panel

    def widget(self, _index):
        return self._panel


class _Host(DetectMixin):
    """把 DetectMixin 挂到一个最小宿主上（真实页面里这些由 page.py 提供）。"""

    def __init__(self, path: str, size: tuple[int, int], pages: int = 4):
        from desktop.components.detect_stats import DetectStatsWidget

        self.task_id = "t1"
        self.store = _StoreStub()
        self.detect_cache: dict = {}
        self.detect_viewer = _ViewerStub()
        self.detect_viewer.path = path
        self.detect_viewer.strip = _StripStub(pages)
        # 与 view.py 的 _wire_detect_panel 同款接线：选中态变化回填面板
        self.detect_viewer.selection_changed.connect(self._on_box_selection_changed)
        self.control_stack = _StackStub(_PanelStub())
        self._panel = self.control_stack.widget(0)
        self.detect_stats = DetectStatsWidget()
        self._pages = [Path(f"/t/{i:04d}.png") for i in range(1, pages + 1)]
        self._size = size
        self.toasts: list = []

    # ---- 宿主回调/属性（真实页面里各自另有一份实现）----
    def panel_host_of_step(self, step: str):
        """取"某一步的面板"（真实页面在 ``page.py``；DetectMixin 只认这个入口）。

        ⚠️ DetectMixin 里**不再**出现 ``control_stack.widget(1|2)``：那是静态
        步骤表的下标，自定义流程下会读错面板、还会在流程里没有那一步时把
        面板构造出来。这个替身保留一个恒定返回的面板即可。
        """
        return getattr(self, "_panel", None)

    def _current_area(self):
        return 1

    def _image_size_for(self, _path_text):
        return self._size

    def _manifest_paths(self):
        return list(self._pages)

    def _toast(self, kind, title, content):
        self.toasts.append((kind, title, content))

    def _refresh_reference_boxes(self):
        pass

    def window(self):
        return None

    def entry(self, key: str = "0001"):
        got = self.store.detect_boxes_entry("t1", key)
        return got[0] if got else None


def _dialog_stub(calls: dict):
    """替掉 qfluentwidgets.Dialog：记录标题/正文，按 calls["answer"] 返回。"""

    class _Btn:
        def setText(self, _text):
            pass

    class _Dialog:
        def __init__(self, title, text, parent=None):
            calls["title"] = title
            calls["text"] = text
            self.yesButton = _Btn()
            self.cancelButton = _Btn()

        def exec(self):
            return bool(calls.get("answer", False))

    return _Dialog


def _press(widget, point=(5, 5)) -> None:
    """在控件某点按下左键：落在框外 = 手绘新框，落在框内 = 选中。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QPixmap

    widget._boxes_editable = True
    widget._pixmap = QPixmap(2, 2)
    event = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(*point),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    widget.mousePressEvent(event)


def _press_image(widget, ix: float, iy: float) -> None:
    """按控件**当前**的图片↔控件映射，点在图片坐标 (ix, iy) 上。"""
    _press(
        widget,
        (ix * widget._scale_x + widget._offset_x,
         iy * widget._scale_y + widget._offset_y),
    )


def run(ctx) -> None:  # noqa: ARG001 - 本模块自带夹具，不用共享 ctx
    from PySide6.QtCore import QSize

    from tests.selftests._context import ok

    from desktop.components.viewers.image_view import ImageView, box_styles
    from utils.box_geometry import half_sides, half_slots

    W, H = 1000, 800
    LEFT = [40, 100, 460, 700]
    RIGHT = [540, 100, 960, 700]
    FULL = [20, 40, 980, 760]
    SIZE = (W, H)

    # ---- 规则 2：半幅的左右由**中心位置**决定（与大小无关） ----
    ok("单框在左半 → 左框", half_sides([LEFT], SIZE) == ["left"])
    ok("单框在右半 → 右框", half_sides([RIGHT], SIZE) == ["right"])
    ok("单框横跨整幅仍按**中心**判（不看框宽）",
       half_sides([[0, 0, 999, 10]], SIZE) == ["left"])
    ok("两个框按中心排序：靠左的归左、另一个归右",
       half_sides([RIGHT, LEFT], SIZE) == ["right", "left"])

    # ---- 槽位：半幅**恒 2 槽**（形态与"还剩几个框"无关）----
    ok("半幅漏检一侧仍写回 2 槽（右侧）",
       half_slots([RIGHT], SIZE) == [None, RIGHT], str(half_slots([RIGHT], SIZE)))
    ok("半幅两框 → [左, 右]，顺序被整理",
       half_slots([RIGHT, LEFT], SIZE) == [LEFT, RIGHT])

    # ---- 规则 3：整幅是显式类型，不受位置/大小影响 ----
    names, colors = box_styles([FULL], SIZE, full=True)
    ok("整幅页的框命名「整幅」", names == ["整幅"], str(names))
    ok("整幅页的框用专用色（靛蓝 #4F46E5）",
       colors[0].name().lower() == "#4f46e5", colors[0].name())
    ok("整幅不按中心判左右（哪怕框只在左半）",
       box_styles([LEFT], SIZE, full=True)[0] == ["整幅"])

    # ---- 规则 2（控件侧）：拖过中线**立刻**换边 ----
    view = ImageView()
    view.set_boxes([LEFT], QSize(W, H), full=False)
    ok("框在左半 → 「左框」", view.box_kinds() == ["left"])
    view._boxes[0] = list(RIGHT)  # 等价于把它拖到右半
    ok("拖过中线后立刻变成「右框」（不必等宿主回写）",
       view.box_kinds() == ["right"], str(view.box_kinds()))

    # ---- 规则 4：整幅页只允许一个框，手绘第二个会被拒绝并提示 ----
    full_view = ImageView()
    full_view.set_boxes([FULL], QSize(W, H), full=True)
    rejected: list = []
    full_view.edit_rejected.connect(rejected.append)
    ok("整幅页的框数上限为 1", full_view.max_boxes == 1, str(full_view.max_boxes))
    _press(full_view)
    ok("整幅页里手绘第二个框被拒绝，且提示怎么改",
       rejected and "整幅" in rejected[0] and "左框" in rejected[0], str(rejected))
    half_view = ImageView()
    half_view.set_boxes([LEFT, RIGHT], QSize(W, H), full=False)
    rejected2: list = []
    half_view.edit_rejected.connect(rejected2.append)
    ok("半幅页的框数上限为 2", half_view.max_boxes == 2)
    _press(half_view)
    ok("半幅页画第三个框被拒绝并提示",
       rejected2 and "最多" in rejected2[0], str(rejected2))
    _press_image(half_view, 100, 200)  # 落在左框内 → 只是选中，不算新增
    ok("点在已有框上不算新增（不会误报上限）", len(rejected2) == 1, str(rejected2))
    ok("点在已有框上会选中它", half_view.selected_index() == 0,
       str(half_view.selected_index()))

    # ================= 宿主侧：入库形态与类型切换 =================
    host = _Host("/t/0001.png", SIZE)
    KEY = host.detect_viewer.path

    # 规则 1：删掉一个框，另一个框的类型不变
    host._store_slots(KEY, [LEFT, RIGHT], "manual")
    host.detect_viewer.select_box(0)
    host._delete_selected_box()
    ok("规则1：删掉左框后仍是半幅 2 槽，剩下的还是「右框」",
       host.entry() == [None, RIGHT]
       and host.detect_viewer.box_kinds() == ["right"], str(host.entry()))
    ok("规则1：删除不会把页面形态变成整幅",
       host.detect_viewer.box_full_mode() is False)

    # 规则 1/3：删光后重画 —— 按中心定左右，**不是**整幅（用户报的 bug）
    host._save_manual_boxes(KEY, [])
    host._save_manual_boxes(KEY, [LEFT])
    ok("删光后重画的第一个框是「左框」而不是「整幅」",
       host.entry() == [LEFT, None]
       and host.detect_viewer.box_kinds() == ["left"], str(host.entry()))
    host._save_manual_boxes(KEY, [RIGHT])
    ok("画在右半 → 「右框」", host.entry() == [None, RIGHT], str(host.entry()))

    # 规则 3：显式选「整幅」之后，移动/缩放都还是整幅
    host._save_manual_boxes(KEY, [FULL])
    host.detect_viewer.select_box(0)
    host._set_selected_box_kind("full")
    ok("单框页切「整幅」→ 1 槽 + 视图进入整幅模式",
       host.entry() == [FULL] and host.detect_viewer.box_full_mode() is True,
       str(host.entry()))
    moved = [[FULL[0] + 12, FULL[1] + 8, FULL[2] - 12, FULL[3] - 8]]
    host._save_manual_boxes(KEY, moved)
    ok("规则3：整幅框移动/缩放后仍然是「整幅」",
       host.entry() == moved and host.detect_viewer.box_kinds() == ["full"],
       str(host.entry()))

    # 规则 4/5：设整幅时若还有其他框 → 弹提示、可删除；取消则原样不动
    # 先切回半幅：整幅页在界面上根本画不出第二个框（max_boxes=1，见规则 4）
    host.detect_viewer.select_box(0)
    host._set_selected_box_kind("left")
    host._save_manual_boxes(KEY, [LEFT, RIGHT])
    ok("准备：半幅两框（整幅页画不出第二个框，只能从半幅切入）",
       host.entry() == [LEFT, RIGHT], str(host.entry()))
    host.detect_viewer.select_box(0)
    import qfluentwidgets

    calls: dict = {}
    original = qfluentwidgets.Dialog
    qfluentwidgets.Dialog = _dialog_stub(calls)
    try:
        calls["answer"] = False
        host._set_selected_box_kind("full")
        ok("规则5：还有别的框时设整幅 → 弹提示并写清其他框的类型",
           "整幅" in calls.get("title", "") and "「右框」" in calls.get("text", ""),
           str(calls))
        ok("规则5：用户取消 → 框原样不动（不静默删框）",
           host.entry() == [LEFT, RIGHT], str(host.entry()))
        calls["answer"] = True
        host.detect_viewer.select_box(0)
        host._set_selected_box_kind("full")
        ok("规则4/5：确认后只留当前框并设为整幅",
           host.entry() == [LEFT] and host.detect_viewer.box_full_mode() is True,
           str(host.entry()))
    finally:
        qfluentwidgets.Dialog = original

    # 规则 6：没选中框时点类型 = 选中该类型的框（并回填面板高亮）
    host._save_manual_boxes(KEY, [LEFT, RIGHT])
    host.detect_viewer.select_box(-1)
    host._set_selected_box_kind("right")
    ok("规则6：没选中框时点「右框」→ 选中右侧那个框",
       host.detect_viewer.selected_index() == 1,
       str(host.detect_viewer.selected_index()))
    ok("规则6：面板回填选中框的类型",
       host.control_stack.widget(1).selection == (1, "right"),
       str(host.control_stack.widget(1).selection))

    # 规则 6：页内没有该类型 → 只提示，不动任何框
    host._save_manual_boxes(KEY, [LEFT])
    host.detect_viewer.select_box(-1)
    host.toasts.clear()
    before = host.entry()
    host._set_selected_box_kind("full")
    ok("规则6：页内没有「整幅」框时点击 → 只提示、不改数据",
       host.toasts and host.entry() == before, f"{host.toasts} / {host.entry()}")

    # 规则 6：点当前已经是的类型 → 幂等（不弹互斥框）
    host._save_manual_boxes(KEY, [LEFT, RIGHT])
    host.detect_viewer.select_box(0)
    host.toasts.clear()
    host._set_selected_box_kind("left")
    ok("规则6：点当前已是的类型 → 无变化、无提示",
       host.entry() == [LEFT, RIGHT] and not host.toasts, f"{host.toasts}")

    # 规则 2/6：半幅里点**另一侧** → 说清"左右由框的位置决定"，不悄悄改坐标
    host.toasts.clear()
    host._set_selected_box_kind("right")
    ok("规则6：半幅里点另一侧 → 提示「由框的位置决定」",
       host.toasts and "位置" in host.toasts[-1][2], str(host.toasts))
    ok("规则6：这条提示不修改框坐标", host.entry() == [LEFT, RIGHT], str(host.entry()))

    # 规则 6：整幅 → 半幅（切回来）
    host._save_manual_boxes(KEY, [LEFT])
    host.detect_viewer.select_box(0)
    host._set_selected_box_kind("full")     # 单框 → 直接切成整幅
    ok("准备：单框已切为整幅", host.detect_viewer.box_full_mode() is True)
    host._set_selected_box_kind("left")     # 整幅 → 半幅
    ok("规则6：从整幅切回半幅 → 2 槽、不再按整幅输出",
       host.entry() == [LEFT, None] and host.detect_viewer.box_full_mode() is False,
       str(host.entry()))

    # ---- 整页模式（area=4）里也要按槽数认形态，不能把"手动半幅"当整幅 ----
    host._save_manual_boxes(KEY, [LEFT])                       # 半幅单侧 → 2 槽
    shown, origin = host._whole_page_entry(KEY)
    ok("整页模式下沿用**手动框**且保留 2 槽形态",
       origin == "manual" and len(shown) == 2, f"{origin} {shown}")
    host._apply_boxes(KEY, shown, origin)
    ok("整页模式下列不会把手动半幅误判成整幅",
       host.detect_viewer.box_full_mode() is False, str(shown))
