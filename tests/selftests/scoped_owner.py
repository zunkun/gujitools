# -*- coding: utf-8 -*-
"""按节点隔离的数据文件**归属标记**（``*.json.owner``）自测。

背景（用户 2026-10-23）：``boxes.json`` / ``pages.json`` / ``print.json`` /
``sizes.json`` / ``drafts/*.json`` 的「主节点用原名、副本带 ``~<节点>``」只是一条
**隐式**规则——主节点是谁由 ``flow.bpmn`` 的节点声明顺序推导，文件名本身不带
节点 id。删掉主节点后，接替的节点会变成新主节点、接管旧主名的文件，把已删
节点的数据误认为自己的。

这里钉住 owner 标记的三条语义：

1. 写入方（带 ``node_id``）落盘时同步写标记；无节点上下文的旧调用方不写；
2. 读取时标记**不一致** ⇒ 退回本节点自己的 ``~<节点>`` 文件，不继承；
3. 没有标记（旧任务）⇒ 信任主名文件（零迁移）。
"""

NAME = "scoped_owner"
DEPENDS: list[str] = []
TITLE = "按节点存的数据文件带 owner 标记"


def run(ctx) -> None:
    from pathlib import Path

    from tests.selftests._context import ok
    from tests.tmpdir import temp_dir

    from desktop.store.annotations import AnnotationMixin
    from desktop.store.drafts import DraftMixin
    from desktop.store.json_io import owner_path, read_owner
    from desktop.store.pages import PageManifestMixin

    tmp = temp_dir("owner_")

    class _Diagram:
        """最小流程图替身：只需要 ``node_ids_of``（主节点 = 第一个）。"""

        def __init__(self, ids):
            self.ids = ids

        def node_ids_of(self, stage):
            return tuple(self.ids.get(stage, ()))

    class _Store(AnnotationMixin, PageManifestMixin, DraftMixin):
        """最小宿主：task_dir + 可变的流程图（模拟"删掉主节点"）。"""

        def __init__(self):
            self.ids: dict[str, tuple[str, ...]] = {
                "detect": ("A", "B"), "print": ("P1", "P2"),
            }

        def task_dir(self, _tid):
            return Path(tmp)

        def task_diagram(self, _tid):
            return _Diagram(self.ids)

        def node_stage_of(self, _nid):
            return "detect"

    store = _Store()
    tid = "t1"
    boxes = Path(tmp) / "boxes.json"
    boxes_b = Path(tmp) / "boxes~B.json"

    # ---- 1. 写入方写 owner 标记 ----
    store.save_detect_boxes(
        tid, "0001", [[1, 2, 3, 4], None], origin="manual",
        node_id="A", primary_id="A",
    )
    store.save_detect_boxes(
        tid, "0002", [[5, 6, 7, 8], None], origin="manual",
        node_id="B", primary_id="A",
    )
    ok("主节点数据文件带 owner=主节点 id",
       read_owner(boxes) == "A", str(read_owner(boxes)))
    ok("副本数据文件带 owner=副本节点 id",
       read_owner(boxes_b) == "B", str(read_owner(boxes_b)))
    entry_a = store.detect_boxes_entry(tid, "0001")
    entry_b = store.detect_boxes_entry(tid, "0002", "B", "A")
    ok("主/副本各写各的文件（互不覆盖）",
       entry_a is not None and entry_a[0] == [[1, 2, 3, 4], None]
       and entry_b is not None and entry_b[0] == [[5, 6, 7, 8], None],
       f"{entry_a} / {entry_b}")

    # ---- 2. 主节点被删：接替节点不能继承旧主名文件 ----
    store.ids["detect"] = ("B",)  # 只剩 B → 按旧规则 B 会变成主节点
    ok("接替节点读到的是自己的 boxes~B.json（不是旧主人的 boxes.json）",
       store.boxes_path(tid, "B") == boxes_b,
       str(store.boxes_path(tid, "B")))
    ok("旧主人的页不会被误认为接替节点的（不继承数据）",
       store.detect_boxes_entry(tid, "0001", node_id="B") is None,
       str(store.detect_boxes_entry(tid, "0001", node_id="B")))
    entry_own = store.detect_boxes_entry(tid, "0002", node_id="B")
    ok("接替节点自己那份照常读得到",
       entry_own is not None and entry_own[0] == [[5, 6, 7, 8], None],
       str(entry_own))

    # ---- 3. 页清单 / 暂存同样按 owner 退回 ----
    store.ids["detect"] = ("A", "B")
    store.save_pages(tid, [{"file": "a.png"}], node_id="A", primary_id="A")
    store.save_pages(tid, [{"file": "b.png"}], node_id="B", primary_id="A")
    ok("pages.json 带 owner=主节点",
       read_owner(Path(tmp) / "pages.json") == "A")
    store.ids["detect"] = ("B",)
    ok("页清单同样退回自己的 pages~B.json",
       store.pages_path(tid, "B", "B") == Path(tmp) / "pages~B.json",
       str(store.pages_path(tid, "B", "B")))
    ok("读回的是自己的页（不是旧主人的）",
       store.load_pages(tid, "B", "B") == [{"file": "b.png"}],
       str(store.load_pages(tid, "B", "B")))

    store.ids["detect"] = ("A", "B")
    store.save_draft(tid, "detect", {"threshold": 3},
                     node_id="A", primary_id="A")
    store.save_draft(tid, "detect", {"threshold": 9},
                     node_id="B", primary_id="A")
    store.ids["detect"] = ("B",)
    ok("参数暂存同样退回自己的 detect~B.json",
       store.draft_path(tid, "detect", "B", "B")
       == Path(tmp) / "drafts" / "detect~B.json",
       str(store.draft_path(tid, "detect", "B", "B")))
    ok("暂存读回的是自己的参数",
       store.load_draft(tid, "detect", "B", "B") == {"threshold": 9},
       str(store.load_draft(tid, "detect", "B", "B")))

    # ---- 4. 旧任务（无标记）继续信任主名文件（零迁移）----
    owner_path(boxes).unlink()
    ok("没有 owner 标记的旧任务仍用主名文件（零迁移）",
       store.boxes_path(tid, "B") == boxes,
       str(store.boxes_path(tid, "B")))
    ok("无标记时不会凭空造 ~ 文件",
       not (Path(tmp) / "boxes~B~B.json").exists())

    # ---- 5. 无节点上下文的旧调用方不写标记（行为与改造前一致）----
    from tests.tmpdir import temp_dir as _temp_dir

    tmp2 = _temp_dir("owner_legacy_")

    class _LegacyStore(_Store):
        def task_dir(self, _tid):
            return Path(tmp2)

    legacy_store = _LegacyStore()
    legacy_store.save_detect_boxes(tid, "0003", [[1, 1, 2, 2]], origin="manual")
    ok("无 node_id 的旧调用方不产生 owner 标记",
       (Path(tmp2) / "boxes.json").exists()
       and not owner_path(Path(tmp2) / "boxes.json").exists(),
       "旧调用方写出了标记")
