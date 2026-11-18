# -*- coding: utf-8 -*-
"""**聚合任务**的成员产物汇集：把成员任务在**起始节点**上的「输入 + 产出」
按成员顺序复制进聚合任务自己的任务目录。

## 用户口径（2026-11-18 晚，统一模型）

> 比如选择子任务节点 x，那么默认 x 的输入做了聚合开始节点的输入，x 的输出
> 作为聚合开始节点的输出。

起始节点 X 是对成员在 X 这一步「做过的活」的**整体回放**：

1. **X 的输入**（成员侧该节点的上游产物）→ 复制进聚合任务 X 节点的输入目录
   （``stages/input/``）——页清单指向它，起点页面上显示的就是这些图；
2. **X 的产出**（成员在这一步生成的结果）→ 复制进聚合任务 X 节点的产出目录，
   起点视为**已完成**（写一条合成的 runs 记录），下游能直接跑。

一个聚合任务在创建之后立刻拥有三样东西：

1. **起点节点的输入与产出**（``stages/input`` + ``stages/extract`` /
   ``stages/detect`` / ``stages/rembg`` / ``stages/imposition``）；
2. **配套的派生数据**：``pages.json``（页集合，指向**起点输入**——
   ``extract`` / ``imposition`` 例外，见下）、``sizes.json``（逐页像素尺寸）、
   ``boxes.json``（检测框，起点是检测时）、``drafts/imposition.json``
   （拼版版面，起点是拼版时）；
3. **两个例外**：
   - ``extract``：它的输入是成员的**源 PDF**——PDF 不搬（"输入源没有 PDF"），
     只搬产出；页面只读显示汇集来的图（不能现场提取）；
   - ``print``：它的**输出是聚合任务自己生成的 PDF**，不是成员的输出
     （"输出的话是聚合任务的输出，不是子任务的输出"）——创建时**不合并**
     成员 PDF、起点**不记已完成**；汇集只搬成员的印刷取图（拼版生效取
     拼版成品、否则取去底色成品）当输入，用户在聚合任务里点「PDF排版」
     现场生成 ``print.pdf``。

## 页名与顺序：``001_1.jpg``

成员各自的页名都是 ``1.jpg`` / ``10-l.jpg`` 这种**本任务内唯一**的名字，
拼到一起必然撞名。所以汇集后的页名统一是 ``<成员序号3位>_<原页名>``：

- ``natural_sort_key`` 下 ``001_* < 002_*``（成员顺序被保住），
  同一成员内部 ``001_2 < 001_10``（页序被保住）；
- 拼版那种"版面 + 源图"的情形，两者用同一个前缀 ⇒ 版面的 ``001_1.jpg``
  与 ``stages/imposition/001_1.png`` 共享 stem，按页名天然对齐。

## 边界

- **只做一次、幂等**：重复调只会覆盖同名文件、补齐缺的，不会删用户的图；
  ``NNN_`` 前缀的**陈旧**文件（成员变了/页少了）会被清掉，其余不动。
- 成员缺这一步的产物/输入 ⇒ 记一条 note 跳过（不抛异常：聚合是"尽力而为"，
  一个成员没跑完不该让整次汇集失败），调用方把 note 展示给用户。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from desktop.steps import ports
from desktop.steps.aggregate import AGGREGATE_START_STAGES
from desktop.utils.files import IMAGE_SUFFIXES, copy_file_atomic
from utils.sort_utils import natural_sort_key

#: 汇集后页名的成员前缀宽度（``001_1.jpg``，字典序与数字序一致）。
MEMBER_PREFIX_WIDTH = 3

#: 汇集器生成的文件名前缀（``001_``）：只有这些才会被"清陈旧"阶段删除。
_GENERATED_RE = re.compile(r"^\d{%d}_" % MEMBER_PREFIX_WIDTH)

#: 「成员产物正在汇集」的在场标记（任务目录下）。
#:
#: 为什么需要：汇集是后台跑几十秒的活，而用户建完任务立刻就被带进详情页。
#: 没有这个标记时，详情页只能说"这一步的输入还没就位 / 先把上游跑完"——
#: 而聚合任务压根没有上游，用户会去反复点执行。有了它，界面能说真话
#: （"正在汇集，请稍候"），也挡住"半成品被当成输入跑起来"。
AGGREGATE_PENDING_MARKER = ".aggregate-pending"

#: 起点阶段里要把成员该节点的**输入**也一起搬进 ``stages/input`` 的那些
#: （2026-11-18 晚口径："x 的输入做了聚合开始节点的输入"）。
#:
#: ``extract`` **不在内**：它的输入是成员的源 PDF，PDF 不搬（起点页面只读
#: 显示汇集来的产出图）。其余起点（检测/去底色/拼版/PDF排版）的输入都要搬
#: ——页清单与起点页面显示的就是这批图；拼版额外有一层原因：版面文档里的
#: ``items[].file`` 指向"被拼的那批图"，不搬过来版面就打不开。
INPUT_COPY_STAGES = frozenset({"detect", "rembg", "imposition", "print"})


def set_pending_marker(task_dir, on: bool) -> None:
    """写/删「正在汇集」标记（**永不抛**：它只是协作信号）。"""
    target = Path(task_dir)
    marker = target / AGGREGATE_PENDING_MARKER
    try:
        if on:
            target.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(b"1")
        elif marker.exists():
            marker.unlink()
    except OSError:
        pass


def is_pending(task_dir) -> bool:
    """这个任务的成员产物是不是**还在汇集**。"""
    try:
        return (Path(task_dir) / AGGREGATE_PENDING_MARKER).exists()
    except OSError:
        return False


def member_prefix(index: int) -> str:
    """成员序号（1 起）→ 三段零填充前缀（``1 -> "001"``）。"""
    return f"{int(index):0{MEMBER_PREFIX_WIDTH}d}"


def aggregate_page_name(index: int, name: str) -> str:
    """成员页名 → 聚合任务里的页名（``1.jpg`` -> ``001_1.jpg``）。"""
    return f"{member_prefix(index)}_{name}"


def is_generated_name(name: str) -> bool:
    """这个名字是不是汇集器生成的（只看 ``NNN_`` 前缀）。"""
    return bool(_GENERATED_RE.match(str(name)))


@dataclass(frozen=True)
class IngestCopy:
    """一次复制：``source`` → ``target``。"""

    source: Path
    target: Path


@dataclass
class IngestPlan:
    """汇集计划（纯数据，可断言；:func:`run_ingest` 负责落盘）。"""

    task_id: str
    start_stage: str
    #: 起点节点 id（图上那个节点；写 runs 记录要用）
    node_id: str
    #: 起点节点的输入目录（``stages/input``；:data:`INPUT_COPY_STAGES`
    #: 里的起点会把成员该节点的上游图复制到这里）
    entry_dir: Path
    #: 起点节点的产出目录（``print`` 时是 ``stages/print``——2026-11-18 晚
    #: 口径下那本 PDF 由用户现场执行生成，汇集只建目录不写内容）
    output_dir: Path
    #: 起点**输入图**的复制对（按成员顺序、逐成员按页序）。
    #: ⚠️ ``extract`` 起点（无输入）与成员没跑过上游时为空集
    input_copies: tuple[IngestCopy, ...] = ()
    #: 起点**产出**的复制对（同上）；``print`` 起点恒空（输出由用户现场生成）
    output_copies: tuple[IngestCopy, ...] = ()
    #: 汇集后的页面清单（``pages.json`` 的形状：``{file, label}``）。
    #: ⚠️ 指向**起点输入**（``detect``/``rembg``/``print``）；
    #: ``extract``/``imposition`` 指向产出（提取没有输入、拼版清单是成品图）
    pages: tuple[dict, ...] = ()
    #: 汇集后的逐页尺寸（``sizes.json``：stem → (w, h)）
    sizes: dict[str, tuple[int, int]] = field(default_factory=dict)
    #: 汇集后的检测框（``boxes.json``：stem → entry）；起点不是检测时为空
    boxes: dict[str, dict] = field(default_factory=dict)
    #: 汇集后的拼版版面（``drafts/imposition.json``）；起点不是拼版时为空
    imposition: dict | None = None
    #: 汇集后的待打印文档（``print.json``：成员第四步的页序/删页/旋转/rect
    #: 按文件名映射到聚合输入图）；起点不是排版时为空。用户 2026-11-18 原则：
    #: 子任务该节点显示什么，聚合起点就显示什么——手工拖过的顺序要原样重现
    print_doc: dict | None = None
    #: 跳过/降级的原因（展示给用户，不抛异常）
    notes: tuple[str, ...] = ()

    @property
    def total_files(self) -> int:
        return len(self.input_copies) + len(self.output_copies)


@dataclass
class IngestResult:
    """汇集结果（给调用方做提示/日志）。"""

    task_id: str
    start_stage: str
    entry_dir: Path
    output_dir: Path
    pages: int = 0
    copied: int = 0
    #: 跳过/降级的原因（成员没产物、PDF 缺页等），调用方按需展示
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------- 计划
def _stage_node(diagram, stage: str) -> str | None:
    """图上**该阶段的第一个节点** id（拓扑序；起点节点就是它）。"""
    for node_id, item_stage in diagram.node_order():
        if item_stage == stage:
            return node_id
    return None


def _member_imposition_active(store, task_id: str) -> bool:
    """成员任务的「拼版是否生效」（成员侧取图来源要用它）。

    判据与详情页 ``imposition_effective`` 同源：**流程里有这一步**（开关
    打开）**且**已经有拼版页。读不到一律 False。
    """
    try:
        if not store.step_enabled(task_id, "imposition"):
            return False
        return bool(store.load_imposition_doc(task_id).get("pages"))
    except Exception:  # noqa: BLE001 - 成员数据坏了按"没启用"降级
        return False


def _member_input_dir(store, task_id: str, stage: str) -> Path | None:
    """成员任务在起点节点上的 ``pages`` 输入目录。"""
    active = _member_imposition_active(store, task_id) if stage == "print" else False
    try:
        path = store.stage_input(task_id, stage, "pages", active)
    except Exception:  # noqa: BLE001 - 成员图坏了不拖死汇集
        return None
    return path if path is not None and path.is_dir() else None


def _member_output_dir(store, task_id: str, stage: str) -> Path:
    """成员任务在起点节点上的 ``pages`` 产出目录（``print`` 除外）。"""
    folded = ports.fold_forward(stage, "pages")
    try:
        return store.node_or_stage_output(task_id, None, folded, "pages")
    except Exception:  # noqa: BLE001
        return store.scoped_stage_dir(task_id, None, stage)


def _images(directory: Path | None) -> list[Path]:
    """目录里的图片（页序自然排序，唯一排序键 ``natural_sort_key``）。"""
    if directory is None or not directory.is_dir():
        return []
    return sorted(
        (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda f: natural_sort_key(f.name),
    )


def plan_ingest(store, task_id: str) -> IngestPlan | None:
    """算出「怎么把成员产物拼进聚合任务」；不是聚合任务/数据不全返回 ``None``。

    纯读：不建目录、不写文件（可以放心在界面线程调来预览页数）。
    """
    record = store.get_task(task_id)
    if not record or record.get("kind") != "aggregate":
        return None
    members = [str(m).strip() for m in (record.get("members") or []) if str(m).strip()]
    if not members:
        return None
    stage = str(record.get("member_stage") or "")
    if stage not in AGGREGATE_START_STAGES:
        return None
    diagram = store.task_diagram(task_id)
    node_id = _stage_node(diagram, stage)
    if node_id is None:
        # 用户改过流程图、把落库的那个起始节点删了/换了 ⇒ **以图为准**：
        # 取拓扑序里第一个可运行节点当起点（图上没有的阶段交不出货）。
        for candidate_id, candidate_stage in diagram.node_order():
            if candidate_stage in AGGREGATE_START_STAGES:
                node_id, stage = candidate_id, candidate_stage
                break
    if node_id is None:
        return None

    entry_dir = store.node_input(task_id, node_id, "pages")
    if entry_dir is None:
        entry_dir = store.task_input_dir(task_id)
    if stage == "print":
        # 产物是一个 PDF 文件，放在这一步自己的目录里（``stages/print``）
        output_dir = store.scoped_stage_dir(task_id, node_id, "print")
    else:
        output_dir = store.node_or_stage_output(
            task_id, node_id, ports.fold_forward(stage, "pages"), "pages"
        )

    plan = IngestPlan(
        task_id=task_id,
        start_stage=stage,
        node_id=node_id,
        entry_dir=Path(entry_dir),
        output_dir=Path(output_dir),
    )
    notes: list[str] = []
    pages: list[dict] = []
    sizes: dict[str, tuple[int, int]] = {}
    boxes: dict[str, dict] = {}
    imposition_pages: list[dict] = []
    print_doc_entries: dict[str, list[dict]] = {"pages": [], "deleted_pages": []}
    #: 全体成员的「输入图 → 聚合入口路径」映射（⚠️ 跨成员累积：
    #: ``input_name_map`` 是成员循环内的局部变量，只有最后一个成员的）
    input_targets: list[str] = []
    seq = 0

    for index, member in enumerate(members, start=1):
        prefix = member_prefix(index)
        member_sizes = {}
        try:
            member_sizes = store.image_sizes_all(member)
        except Exception:  # noqa: BLE001 - 尺寸读不到就让下游回退读图头
            member_sizes = {}

        # ---- 起点输入（2026-11-18 晚口径："x 的输入做了聚合开始节点的输入"）
        # ---- 成员该节点的上游图复制进 ``stages/input``；``extract`` 例外
        # ---- （它的输入是源 PDF，不搬——见 INPUT_COPY_STAGES）。
        input_name_map: dict[str, str] = {}
        input_sources: list[Path] = []
        if stage in INPUT_COPY_STAGES:
            in_dir = _member_input_dir(store, member, stage)
            input_sources = _images(in_dir)
            for source in input_sources:
                target = plan.entry_dir / aggregate_page_name(index, source.name)
                plan.input_copies += (IngestCopy(source, target),)
                input_name_map[source.name] = str(target)
                input_targets.append(str(target))
                size = member_sizes.get(source.stem)
                if size:
                    sizes[target.stem] = (int(size[0]), int(size[1]))
            if not input_sources:
                notes.append(
                    f"成员 {member} 在「{ports.stage_label(stage)}」没有输入图"
                )

        # ---- 页清单：起点的**输入**就是这一步的页集合（detect/rembg/print）。
        # ---- extract 没有输入、imposition 的清单语义是成品图 ⇒ 那两个从产出取
        if stage in ("detect", "rembg", "print"):
            for source in input_sources:
                seq += 1
                pages.append(
                    {"file": input_name_map[source.name], "label": str(seq)}
                )

        # ---- 起点产出（成员在这一步生成的结果；print 不搬——输出由
        # ---- 聚合任务现场执行生成，见模块头）
        if stage == "print":
            # ---- 成员 print.json 的页序/删页/旋转/rect 一并组合（用户
            # ---- 2026-11-18 原则：子任务该节点显示什么，聚合起点就显示
            # ---- 什么——第四步手工拖过的顺序、删过的页要原样重现）。
            # ---- 文件按名字映射到聚合入口图（同拼版版面的 items 重映射）；
            # ---- 映射不上的是成员手工插入的外部图，聚合里没有对应文件，
            # ---- 跳过。⚠️ 没进过第四步的成员没有 print.json ⇒ 它的输入图
            # ---- 按目录序（=成员顺序）补进列表，不能少页；成员文档里没有
            # ---- 覆盖到的输入图同样兜底补齐。
            try:
                member_doc = store.load_print_doc(member)
            except Exception:  # noqa: BLE001 - 成员文档坏了按没有处理
                member_doc = None
            covered: set[str] = set()
            for key in ("pages", "deleted_pages"):
                for page in (member_doc or {}).get(key) or []:
                    text = str(page.get("file") or "")
                    mapped = input_name_map.get(Path(text).name) if text else None
                    if not mapped:
                        continue
                    covered.add(mapped)
                    entry: dict = {
                        "file": mapped,
                        "label": Path(mapped).stem,
                    }
                    # rect/rect_size 是按**成员那一张图**的像素尺寸量出来的，
                    # 聚合里就是同一张文件（复制），直接带过来仍有效；
                    # 过期由 plan_print_entries 的 rect_fits_image 兜底。
                    for field_name in ("rect", "rect_size"):
                        if page.get(field_name) is not None:
                            entry[field_name] = list(page[field_name])
                    if page.get("rotate"):
                        entry["rotate"] = page["rotate"]
                    print_doc_entries[key].append(entry)
            for source in input_sources:
                mapped = input_name_map.get(source.name)
                if mapped and mapped not in covered:
                    print_doc_entries["pages"].append(
                        {"file": mapped, "label": Path(mapped).stem}
                    )
        else:
            out_dir = _member_output_dir(store, member, stage)
            out_files = _images(out_dir)
            for source in out_files:
                target = plan.output_dir / aggregate_page_name(index, source.name)
                plan.output_copies += (IngestCopy(source, target),)
                if stage in ("extract", "imposition"):
                    seq += 1
                    pages.append({"file": str(target), "label": str(seq)})
                size = member_sizes.get(source.stem)
                if size:
                    sizes[target.stem] = (int(size[0]), int(size[1]))
            if not out_files:
                notes.append(f"成员 {member} 在「{ports.stage_label(stage)}」没有产出")

        # ---- 检测框（起点是检测时才有意义）----
        if stage == "detect":
            try:
                raw = store.boxes_raw_at(store.boxes_path(member))
            except Exception:  # noqa: BLE001
                raw = {}
            for key, entry in raw.items():
                if isinstance(entry, dict):
                    boxes[f"{prefix}_{key}"] = dict(entry)

        # ---- 拼版版面（起点是拼版时才有意义）----
        if stage == "imposition":
            try:
                doc = store.load_imposition_doc(member)
            except Exception:  # noqa: BLE001
                doc = {"pages": []}
            for page in doc.get("pages") or []:
                items = []
                for item in page.get("items") or []:
                    text = str(item.get("file") or "")
                    mapped = input_name_map.get(Path(text).name) if text else None
                    if not mapped:
                        items = []
                        break
                    items.append({**item, "file": mapped})
                if len(items) == 2:
                    imposition_pages.append({"items": items})
                else:
                    notes.append(f"成员 {member} 的拼版版面引用了汇集输入之外的图，已跳过一页")

    plan.pages = tuple(pages)
    plan.sizes = sizes
    plan.boxes = boxes
    plan.imposition = (
        {"enabled": True, "pages": imposition_pages, "removed": []}
        if stage == "imposition"
        else None
    )
    plan.print_doc = (
        {
            # 快照＝聚合入口图全集：plan_print_entries 靠它判断"产物没变、
            # 沿用用户保存的顺序"——集合对上，成员的页序才会被沿用。
            "rembg_snapshot": sorted(input_targets),
            "pages": print_doc_entries["pages"],
            "deleted_pages": print_doc_entries["deleted_pages"],
        }
        if stage == "print"
        else None
    )
    plan.notes = tuple(notes)
    return plan


# ---------------------------------------------------------------- 落盘
def _prune_generated(directory: Path, keep: set[str]) -> None:
    """删掉目录里**汇集器生成过、这次不再需要**的文件（``NNN_`` 前缀）。

    只碰自己命名的文件：用户插进来的图（``1.jpg`` / 任意名字）一律不动。
    """
    if not directory.is_dir():
        return
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for item in entries:
        if item.name in keep or not item.is_file():
            continue
        if not is_generated_name(item.name):
            continue
        try:
            item.unlink()
        except OSError:
            pass


def _mark_stage_done(
    store, plan: IngestPlan, pages: int, output_path: Path | None
) -> None:
    """把起点节点记成**已完成**（合成一条 runs 记录）。

    为什么必须写：下游的"上游生效了吗"判据是 ``runs.json`` 里的 success
    记录（``store._producer_effective``），光有文件的下游一律当没跑过——
    复制的产出就白复制了（第四步会显示"待打印列表为空"）。

    - ``detect`` 是**两个动作**（检测 + 提交），两条都写，且提交记录带上
      ``_preview_run_id`` 指向检测那条，``detect_submit_fresh`` 才不会判过期；
    - ``imposition`` **不写**：它是合成型阶段（没有 worker），生效与否看
      版面文档，写记录反而会污染"拼版没有执行记录"的既有约定；
    - ``print`` **不写**（2026-11-18 晚口径）：它的输出是聚合任务**现场执行**
      生成的 PDF，不是成员的输出——创建时起点未完成，用户点「PDF排版」跑完
      才会有自己的 runs 记录。
    """
    stage = plan.start_stage
    if stage in ("imposition", "print"):
        return
    common = {"aggregate": True, "members": _members_of(store, plan.task_id)}
    if stage == "detect":
        detect_run = store.create_stage_run(
            plan.task_id, "detect", dict(common), node_id=plan.node_id
        )
        store.finish_stage(
            plan.task_id, detect_run, "success", progress=(pages, pages)
        )
        submit_run = store.create_stage_run(
            plan.task_id,
            "detect_submit",
            {**common, "_preview_run_id": detect_run},
            node_id=plan.node_id,
        )
        store.finish_stage(
            plan.task_id,
            submit_run,
            "success",
            str(output_path) if output_path else None,
            (pages, pages),
        )
        return
    params = dict(common)
    run_id = store.create_stage_run(
        plan.task_id, stage, params, node_id=plan.node_id
    )
    store.finish_stage(
        plan.task_id,
        run_id,
        "success",
        str(output_path) if output_path else None,
        (pages, pages),
    )


def _members_of(store, task_id: str) -> list[str]:
    record = store.get_task(task_id) or {}
    return [str(m) for m in (record.get("members") or [])]


def run_ingest(store, task_id: str, progress=None) -> IngestResult:
    """执行汇集（文件复制 + 派生数据 + 起点置为已完成）。

    ``progress(done, total)`` 可选：每复制一个文件调一次（后台 worker 用它
    报进度；每 20 个报一次，避免信号风暴）。

    不是聚合任务 / 计划为空 ⇒ ``ValueError``（调用方不该静默成功）。
    """
    plan = plan_ingest(store, task_id)
    if plan is None:
        raise ValueError("不是聚合任务或缺少成员/起始节点")

    plan.entry_dir.mkdir(parents=True, exist_ok=True)
    plan.output_dir.mkdir(parents=True, exist_ok=True)

    # ---- 旧的合成 runs 记录先作废 ----
    # 重新汇集/改起点后，旧起点（或旧口径）留下的 aggregate 合成记录描述的
    # 是另一份数据：不清掉，下游"这一步完成了吗"就拿旧记录当真（任务 0026：
    # 起点从去底色改成检测后，旧 rembg 合成记录让去底色假显示已完成——它
    # 其实是要重跑的下游）。普通执行记录（无 aggregate 标记）不受影响。
    try:
        store.clear_synthetic_aggregate_runs(task_id)
    except Exception:  # noqa: BLE001 - 清理失败不拖死汇集本身
        pass

    # ---- 旧起点留在各阶段产物目录里的汇集产物一并清掉 ----
    # 改起点后旧起点的产出目录不再属于本次汇集（rembg→detect 后 stages/
    # rembg 里那批旧成品图），不清会一直躺在盘上冒充旧结果。⚠️ 只动
    # ``NNN_`` 前缀的文件（汇集器自己命名的），用户手工放的图不碰。
    for stage_dir_name in ("extract", "detect", "rembg", "imposition"):
        try:
            directory = Path(store.scoped_stage_dir(task_id, None, stage_dir_name))
        except Exception:  # noqa: BLE001
            continue
        _prune_generated(directory, set())

    input_names = {c.target.name for c in plan.input_copies}
    output_names = {c.target.name for c in plan.output_copies}
    _prune_generated(plan.entry_dir, input_names)
    _prune_generated(plan.output_dir, output_names)

    total = plan.total_files
    done = 0
    copied = 0
    for job in (*plan.input_copies, *plan.output_copies):
        try:
            copy_file_atomic(job.source, job.target)
            copied += 1
        except OSError:
            continue  # 单个文件失败不中断整批（与 CopyFilesWorker 同一口径）
        done += 1
        if progress is not None and (done % 20 == 0 or done == total):
            progress(done, total)

    # ---- 派生数据 ----
    # pages.json 指向**起点输入**（detect/rembg/print；extract/imposition
    # 指向产出，见 plan_ingest）。⚠️ 只在真有页时写：一个成员都没产物时把
    # 老清单抹空，会把还能用的聚合任务变成空壳；但 print 起点的清单**必须**
    # 按现状重写（待打印列表跟着成员产物走），没图时写空清单是正确行为。
    if plan.pages or plan.start_stage == "print":
        store.save_pages(task_id, list(plan.pages))
    if plan.sizes:
        store.save_image_sizes_batch(task_id, plan.sizes)
    if plan.boxes:
        store.save_detect_boxes_batch(
            task_id,
            {key: entry.get("boxes", []) for key, entry in plan.boxes.items()},
            extra={
                key: {
                    "origin": entry.get("origin", "auto"),
                    **({"side": entry["side"]} if entry.get("side") else {}),
                }
                for key, entry in plan.boxes.items()
            },
        )
    if plan.imposition is not None:
        store.save_imposition_doc(task_id, plan.imposition)
    if plan.print_doc is not None:
        store.save_print_doc(task_id, plan.print_doc)

    # ---- 起点置为已完成（print 起点不置——输出由用户现场生成）----
    _mark_stage_done(store, plan, len(plan.pages), plan.output_dir)

    return IngestResult(
        task_id=task_id,
        start_stage=plan.start_stage,
        entry_dir=plan.entry_dir,
        output_dir=plan.output_dir,
        pages=len(plan.pages),
        copied=copied,
        notes=plan.notes,
    )


__all__ = [
    "AGGREGATE_PENDING_MARKER",
    "INPUT_COPY_STAGES",
    "IngestCopy",
    "IngestPlan",
    "IngestResult",
    "MEMBER_PREFIX_WIDTH",
    "aggregate_page_name",
    "is_generated_name",
    "is_pending",
    "member_prefix",
    "plan_ingest",
    "run_ingest",
    "set_pending_marker",
]
