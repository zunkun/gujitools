# -*- coding: utf-8 -*-
"""页面标注数据：boxes.json（检测框）与 sizes.json（页面图片原始尺寸）。

坐标均为原始图片像素坐标 [x1, y1, x2, y2]，按阅读顺序存 [左框, 右框]。
image_key 取页面文件名去后缀（stem）——检测/去底直接以 extract 目录为
输入，不再物化副本，故同一 stem 恒指向同一页。

## 唯一写者：``_DocCache``

本模块所有 boxes/sizes 的读**与写**都必须经过 :func:`_doc_for` 取到的那个
:class:`_DocCache`（进程内按路径共享一份）。理由有两条：

1. **写更少**：以前每次攒批落盘都是"整份读 + 解析 + 序列化 + 写"；1000+ 页时
   单次就是几十毫秒的主线程阻塞。改成内存持有后，落盘只剩"序列化 + 写"。
2. **不互相覆盖**：单页写（拖框/缩放，``save_detect_boxes``）与批量写
   （``save_detect_boxes_batch``）以前各读各的一份快照，交错时后写的那次会把
   前一次的结果悄悄抹掉。同一条路径只有一个内存文档、一个写者，这个问题就不
   存在了。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.store.json_io import read_json, write_json
from utils.box_geometry import box_iou

#: 人工「整幅」记录被自动检测**刷新槽形**所需的同框阈值（IoU）。
#:
#: 用户 2026-10-23（任务 0004）：旧模型把半幅页存成 1 槽（整幅）人工记录，
#: 人工框优先让新检测结果永远写不进去，那 37 页就永远显示成「整幅」。这里
#: 只在**人工框与本次自动框几乎完全重合**（IoU ≥ 0.90）时才动手，且**只改
#: 槽形、保留人工坐标**——坐标仍是用户拍板的那份，改的只是它的形态归类。
MANUAL_FORM_REFRESH_IOU = 0.90


def _manual_half_refresh(previous: dict, boxes: list) -> dict | None:
    """人工「整幅」（1 槽）遇上同框的自动「半幅」（2 槽单框）→ 只刷新槽形。

    返回刷新后的条目（未命中返回 ``None``）；``boxes`` 仍是人工坐标，按自动
    结果里的槽位摆放（左槽/右槽），形态因此变成半幅 2 槽。

    ⚠️ 顺手丢掉旧的 ``plan``：提交计划描述的是**已落盘**的产物，形态从整幅
    改成半幅后那份计划已经过期（下次「提交本次任务」会整份重写）。
    """
    prev_boxes = list(previous.get("boxes") or [])
    new_boxes = list(boxes or [])
    if len(prev_boxes) != 1 or len(new_boxes) != 2:
        return None
    prev_box = prev_boxes[0]
    present = [b for b in new_boxes if b]
    if not prev_box or len(present) != 1:
        return None
    if box_iou(prev_box, present[0]) < MANUAL_FORM_REFRESH_IOU:
        return None
    slot = 0 if new_boxes[0] else 1
    merged: list = [None, None]
    merged[slot] = list(prev_box)
    entry = {k: v for k, v in previous.items() if k != "plan"}
    entry["boxes"] = merged
    return entry


class _DocCache:
    """一份 JSON 文档在**本进程内**的内存持有者与唯一写者。

    ``_reload_if_stale`` 用 ``stat`` 比对上次读/写时的 ``(mtime_ns, size)``：
    我们自己写入后戳会同步更新，所以只有"外部改过文件"才会重读（例如用户手工
    编辑过 boxes.json，或另一个进程写过）——保证不会拿内存里的旧快照覆盖别人的
    改动。
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._doc: dict | None = None
        self._stamp: tuple[int, int] | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ 读
    def doc(self) -> dict:
        """取内存里的文档（首次访问惰性读盘；文件被外部改过则重读）。

        ⚠️ 返回值**就是**内存里那份 dict，调用方直接原地改，再调 :meth:`flush`。
        """
        with self._lock:
            if self._doc is None:
                self._load()
            else:
                self._reload_if_stale()
            assert self._doc is not None
            return self._doc

    def _load(self) -> None:
        data = read_json(self.path, {})
        self._doc = data if isinstance(data, dict) else {}
        self._stamp = self._stat_stamp()

    def _reload_if_stale(self) -> None:
        """外部改过文件就重读（保持 ``_stamp`` 自洽）。"""
        if self._stat_stamp() != self._stamp:
            self._load()

    def _stat_stamp(self) -> tuple[int, int] | None:
        """``(mtime_ns, size)``；文件不存在/读不到给 None。"""
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    # ------------------------------------------------------------------ 写
    def flush(self) -> None:
        """把内存文档**原子写**回磁盘并更新 ``_stamp``（幂等）。

        ⚠️ 保留原 ``_save_json`` 的守卫：任务目录不存在就不写（空壳任务）。
        """
        with self._lock:
            if self._doc is None:
                return
            if not self.path.parent.exists():
                return
            write_json(self.path, self._doc)
            self._stamp = self._stat_stamp()


#: 进程内按路径共享的文档表（**唯一写者**的落点）。键是 ``Path``：同一路径
#: 每次拼出来的 Path 对象不同，但相等/哈希按字符串，故恒指向同一个缓存。
_DOCS: dict[Path, _DocCache] = {}
_DOCS_LOCK = threading.Lock()


def _doc_for(path: Path) -> _DocCache:
    """取某个路径的共享文档缓存（没有就建一个）。"""
    with _DOCS_LOCK:
        cache = _DOCS.get(path)
        if cache is None:
            cache = _DocCache(path)
            _DOCS[path] = cache
        return cache


class AnnotationMixin:
    """boxes.json / sizes.json 读写。"""

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        artifact: Callable[..., Path]
        task_dir: Callable[[str], Path]
        task_diagram: Callable[[str], Any]

    def _doc(self, path: Path) -> _DocCache:
        """取某路径在本进程内的**唯一**文档（读写都走它，见模块 docstring）。"""
        return _doc_for(path)

    # ---------- 检测框 boxes.json ----------
    def boxes_path(self, task_id: str, node_id: str | None = None,
                   primary_id: str | None = None) -> Path:
        """检测框存储文件（主节点：任务目录下的 ``boxes.json``）。

        ⚠️ 走 ``artifact("detect", "boxes")``，不写死文件名：落点的唯一真源是
        :data:`desktop.steps.ports.STAGE_LOCATIONS`。此前这里是**第二份真源**
        （``task_dir / "boxes.json"``），两处碰巧一致，改表不会同步、也永远
        不会报错——这类"双真源"是下一次数据事故的标准配方。

        ⚠️ **按节点隔离**（B 方案，2026-10-17）：同一步骤可以有多个节点，
        副本节点的检测框落在 ``boxes~<节点>.json``。不隔离两个后果都很硬：
        ①第二个「检测文本框」节点的框会**覆盖**第一个的（同页名直接串味）；
        ②消费者（「图片去底色」）永远只读得到主节点那份，副本节点等于白跑。
        """
        from desktop.steps import ports

        if node_id:
            items = self.task_diagram(task_id).node_ids_of("detect")
            primary_id = primary_id or (items[0] if items else None)
        path = ports.artifact_path(
            self.task_dir(task_id), "detect", "boxes", node_id, primary_id
        )
        if path is None:
            raise KeyError("detect 阶段没有登记 boxes 落点")
        return path

    def detect_boxes_entry(self, task_id: str, image_key: str,
                           node_id: str | None = None,
                           primary_id: str | None = None
                           ) -> tuple[list, str] | None:
        """返回 (boxes, origin)；无记录时返回 None。origin: 'auto' | 'manual'。"""
        return self.boxes_entry_at(
            self.boxes_path(task_id, node_id, primary_id), image_key
        )

    def boxes_entry_at(self, path: Path | None, image_key: str
                       ) -> tuple[list, str] | None:
        """读**指定文件**里某页的 ``(boxes, origin)``；文件为空/无该页返回 None。

        ⚠️ 为什么需要"按路径读"这一版（B 方案）：消费方的框来自**图上喂它的
        那个节点**（``store.node_input(node, "boxes")`` 解析出的路径），而不是
        "本阶段的 boxes"——同一步骤多个节点时这两者不是同一个文件。
        """
        if path is None:
            return None
        entry = self._doc(path).doc().get(image_key)
        if not entry:
            return None
        return entry.get("boxes", []), entry.get("origin", "auto")

    def detect_boxes_all(self, task_id: str, node_id: str | None = None,
                         primary_id: str | None = None
                         ) -> dict[str, tuple[list, str]]:
        """整份 boxes.json：``image_key → (boxes, origin)``，**一次读盘**。

        逐页统计（第二步右侧的检测结果统计）要遍历全部页面，若逐页调
        `detect_boxes_entry` 就是「读整个文件」× 页数；这里一次读完。
        """
        return self.boxes_all_at(self.boxes_path(task_id, node_id, primary_id))

    def boxes_all_at(self, path: Path | None) -> dict[str, tuple[list, str]]:
        """读**指定文件**的全部 ``image_key → (boxes, origin)``（一次读盘）。

        与 :meth:`boxes_entry_at` 同一理由：消费方要读的是"上游那个节点"的
        框文件，路径由连线解析而来。
        """
        if path is None:
            return {}
        data = self._doc(path).doc()
        return {
            key: (entry.get("boxes", []), entry.get("origin", "auto"))
            for key, entry in data.items() if isinstance(entry, dict)
        }

    def boxes_raw_at(self, path: Path | None) -> dict:
        """读**指定文件**的**原始条目表** ``{image_key: entry}``（不裁剪字段）。

        ⚠️ 与 :meth:`boxes_all_at` 的分工：那个只出 ``(boxes, origin)`` 两字段，
        供界面消费；复用判据要读条目里的 ``src`` / ``det`` 指纹（见
        ``desktop.services.detect_reuse``），那两个字段在这里必须原样带出。

        返回值**就是内存里那份 dict**：调用方只读，别原地改（要写走
        :meth:`save_detect_boxes_batch` 等）。
        """
        if path is None:
            return {}
        return self._doc(path).doc()

    def save_detect_boxes(
        self, task_id: str, image_key: str, boxes: list, origin: str = "auto",
        node_id: str | None = None, primary_id: str | None = None,
    ) -> None:
        """写入某页的检测框及其来源标记（auto=自动检测，manual=人工编辑）。

        ⚠️ **保留**该页已有的 ``side``（用户在半幅页上指定的左右，见
        :meth:`set_box_side_override`）：拖框/缩放走的是这条路径，
        顺手把用户刚指定的左右清掉，等于"一拖就丢设定"。
        """
        path = self.boxes_path(task_id, node_id, primary_id)
        doc = self._doc(path)
        data = doc.doc()
        previous = data.get(image_key) or {}
        entry = {
            "boxes": boxes,
            "origin": origin,
            "updated_at": time.time(),
        }
        if previous.get("side"):
            entry["side"] = previous["side"]
        # ⚠️ 提交计划描述的是**已经落盘的提交产物**（逐框裁图后的身份），
        #    拖框/缩放不改变那些文件。顺手清掉会让拼版失去"无后缀半幅"的
        #    身份，所以与 `side` 一样原样保留；下次提交会整份重写。
        if isinstance(previous.get("plan"), dict):
            entry["plan"] = previous["plan"]
        data[image_key] = entry
        doc.flush()

    # ---------- 半幅页的人工左右指定 ----------
    def box_side_at(self, path: Path | None, image_key: str) -> str | None:
        """读**指定文件**里某页的人工左右指定（``"left"``/``"right"``/None）。

        ⚠️ 这是**用户显式声明**，不是按位置算出来的左右（那由
        ``box_geometry.half_sides`` 现算）。只有「半幅」页需要它：那种框横跨
        整页、中心压在中线上，位置判定没有意义。
        """
        if path is None:
            return None
        entry = self._doc(path).doc().get(image_key)
        if not isinstance(entry, dict):
            return None
        side = entry.get("side")
        return side if side in ("left", "right") else None

    def box_sides_all_at(self, path: Path | None) -> dict[str, str]:
        """整份文件的 ``image_key → side``（一次读盘，只含有显式指定的页）。"""
        if path is None:
            return {}
        out: dict[str, str] = {}
        for key, entry in self._doc(path).doc().items():
            if not isinstance(entry, dict):
                continue
            side = entry.get("side")
            if side in ("left", "right"):
                out[key] = side
        return out

    def set_box_side_override(
        self, task_id: str, image_key: str, side: str | None,
        node_id: str | None = None, primary_id: str | None = None,
    ) -> None:
        """写入/清除某页的人工左右指定（``None``＝清除，退回"半幅"）。

        ⚠️ 独立成一个方法而不是给 ``save_detect_boxes`` 加参数：那条路是
        "拖框/缩放"的高频路径，**不该**顺带改这个语义位。只有用户明确点了
        「左框/右框」才动它。
        """
        path = self.boxes_path(task_id, node_id, primary_id)
        doc = self._doc(path)
        data = doc.doc()
        entry = data.get(image_key)
        if not isinstance(entry, dict):
            return  # 没有框就没有"这页是什么侧"可言
        if side in ("left", "right"):
            entry["side"] = side
        else:
            entry.pop("side", None)
        entry["updated_at"] = time.time()
        data[image_key] = entry
        doc.flush()

    # ---------- 提交计划（产物角色，供拼版读取） ----------
    def detect_plans_all_at(self, path: Path | None) -> dict[str, dict]:
        """整份文件的 ``image_key → plan``（一次读盘，只含有提交计划的页）。

        ``plan`` 由「提交本次任务」写入，描述**归一化之后每张产物**的身份::

            {"page_class": "harfcontent-left",   # 归一化**前**的检测形态
             "outputs": [{"label": "0007",       # 产物名（无扩展名）
                          "role": "half-unsided",
                          "placeholder": false}]}

        ⚠️ 拼版按 ``outputs[].role`` 认图：``half-unsided`` 的产物名没有
        ``-l``/``-r``，只看文件名会把它误当整幅。没有计划的页（旧任务 /
        「检测文本框」还没提交过）不出现，调用方自然回落到文件名规则。
        """
        if path is None:
            return {}
        out: dict[str, dict] = {}
        for key, entry in self._doc(path).doc().items():
            if not isinstance(entry, dict):
                continue
            plan = entry.get("plan")
            if isinstance(plan, dict):
                out[key] = plan
        return out

    def save_detect_plans(self, task_id: str, plans: dict[str, dict],
                          node_id: str | None = None,
                          primary_id: str | None = None) -> None:
        """批量写入提交计划（**一次读改写**，与检测框同一位写者）。

        只挂在**已有条目**上：没有框记录、也没被检测过的页不凭空造一条
        ``boxes=[]``（那会让统计把"没检测过"当成"检测为空页"）。
        """
        if not plans:
            return
        path = self.boxes_path(task_id, node_id, primary_id)
        doc = self._doc(path)
        data = doc.doc()
        for image_key, plan in plans.items():
            entry = data.get(image_key)
            if not isinstance(entry, dict):
                continue
            entry["plan"] = plan
        doc.flush()

    def save_detect_boxes_batch(self, task_id: str, entries: dict[str, list],
                                node_id: str | None = None,
                                primary_id: str | None = None,
                                extra: dict[str, dict] | None = None) -> None:
        """批量写入某阶段的检测框（origin=auto）：**一次读改写**。

        ⚠️ 为什么必须攒批：detect 跑 320 页时逐页 `save_detect_boxes` 是
        「读整个 boxes.json + 改写」× 页数，实测 320 页累计 **1.8 秒**主线程
        阻塞（2400 页的书记忆里是 47.5s，见
        ``.workbuddy/perf/2026-09-23-sqlite-vs-json.md``）；攒批后一次落盘
        ~0.02s。人工框（origin=manual）在这里跳过，不被自动结果覆盖——
        与单条版同一条规矩，但只读一次文件。

        ``extra``（可选）：``{image_key: {额外字段}}``，合并进对应条目——用于
        记录"这份结果来自哪个源文件、按什么检测指纹算的"（见
        ``desktop.services.detect_reuse``）。⚠️ 默认 ``None`` 时行为与改造前
        逐字一致；带了 extra 的**空框条目也会写**——复用判据要求"无框页也留痕"，
        否则空结果页下次只能重跑。
        """
        if not entries:
            return
        path = self.boxes_path(task_id, node_id, primary_id)
        doc = self._doc(path)
        data = doc.doc()
        updated = time.time()
        for image_key, boxes in entries.items():
            fields = (extra or {}).get(image_key) or {}
            if (not boxes or not any(boxes)) and not fields:
                continue
            previous = data.get(image_key) or {}
            if previous.get("origin") == "manual":
                refreshed = _manual_half_refresh(previous, boxes)
                if refreshed is None:
                    continue  # 人工框优先
                refreshed["updated_at"] = updated
                refreshed.update(fields)
                data[image_key] = refreshed
                continue
            entry: dict = {
                "boxes": boxes,
                "origin": "auto",
                "updated_at": updated,
            }
            # 提交计划描述已落盘的产物，重跑检测不改变那批文件（下次提交才重写）。
            if "plan" not in fields and isinstance(previous.get("plan"), dict):
                entry["plan"] = previous["plan"]
            entry.update(fields)
            data[image_key] = entry
        doc.flush()

    def save_image_sizes_batch(
        self, task_id: str, entries: dict[str, tuple[int, int]],
        node_id: str | None = None, primary_id: str | None = None,
    ) -> None:
        """批量写入页面原始尺寸：一次读改写（理由同 save_detect_boxes_batch）。"""
        if not entries:
            return
        path = self.sizes_path(task_id, node_id, primary_id)
        doc = self._doc(path)
        data = doc.doc()
        for image_key, size in entries.items():
            data[image_key] = [int(size[0]), int(size[1])]
        doc.flush()

    # ---------- 页面尺寸 sizes.json ----------
    def sizes_path(self, task_id: str, node_id: str | None = None,
                   primary_id: str | None = None) -> Path:
        """页面原始尺寸文件：主节点是 ``sizes.json``，副本是 ``sizes~<节点>.json``。

        ⚠️ 尺寸是**框坐标与预览映射的坐标系基准**（``boxes.json`` 里的像素
        坐标按它缩放）。同一步骤多个节点若产出的页图尺寸不同（例如两个
        「图片提取」节点用了不同 zoom/dpi），共用一份基准就会把副本节点的框
        按主节点的比例缩放——框画错位。所以副本节点另存一份。
        """
        from desktop.steps import ports

        name = ports.scoped_name("sizes.json", node_id, primary_id)
        return self.task_dir(task_id) / name

    def save_image_size(self, task_id: str, image_key: str, width: int, height: int,
                        node_id: str | None = None,
                        primary_id: str | None = None) -> None:
        """记录某页图片的原始像素尺寸，作为框坐标与预览映射的坐标系基准。"""
        path = self.sizes_path(task_id, node_id, primary_id)
        doc = self._doc(path)
        data = doc.doc()
        data[image_key] = [int(width), int(height)]
        doc.flush()

    def image_size(self, task_id: str, image_key: str,
                   node_id: str | None = None,
                   primary_id: str | None = None) -> tuple[int, int] | None:
        """返回某页原始像素尺寸 (width, height)；无记录时返回 None。

        ⚠️ 副本节点的记录**缺失时回落共享那份** ``sizes.json``：老任务、以及
        "两个提取节点其实是同一份 PDF 同一套参数"这种常见情形，那边本来就有
        正确记录，回落比"读不到尺寸 ⇒ 框不缩放"更接近用户预期。

        ⚠️ **逐页调用会整份读盘**。要遍历全部页面时改用
        :meth:`image_sizes_all`（一次读盘），否则 320 页就是 320 次全量解析。
        """
        scoped = self.sizes_path(task_id, node_id, primary_id)
        data = self._doc(scoped).doc()
        entry = data.get(image_key)
        if not entry and node_id and primary_id and node_id != primary_id:
            data = self._doc(self.sizes_path(task_id)).doc()
            entry = data.get(image_key)
        if not entry:
            return None
        return int(entry[0]), int(entry[1])

    def image_sizes_all(self, task_id: str, node_id: str | None = None,
                        primary_id: str | None = None
                        ) -> dict[str, tuple[int, int]]:
        """整份 ``sizes.json``：``image_key → (width, height)``，**一次读盘**。

        遍历全部页面时用它，别逐页调 :meth:`image_size`——那个每次都会把整份
        文件读一遍，页数一多就是 O(n²) 重复解析（与 ``save_detect_boxes_batch``
        的批量理由是同一个）。

        ⚠️ 与 :meth:`image_size` 同样**不回落**副本节点到主节点那份：那属于
        单页语义的兜底，批量场景下由调用方自己按需合并，免得把两套坐标系
        悄悄混在一起。
        """
        data = self._doc(self.sizes_path(task_id, node_id, primary_id)).doc()
        out: dict[str, tuple[int, int]] = {}
        for key, entry in data.items():
            try:
                out[key] = (int(entry[0]), int(entry[1]))
            except (TypeError, ValueError, IndexError):
                continue  # 畸形条目跳过，别让一条坏记录毁掉整本尺寸
        return out
