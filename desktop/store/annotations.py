# -*- coding: utf-8 -*-
"""页面标注数据：boxes.json（检测框）与 sizes.json（页面图片原始尺寸）。

坐标均为原始图片像素坐标 [x1, y1, x2, y2]，按阅读顺序存 [左框, 右框]。
image_key 取页面文件名去后缀（stem）——检测/去底直接以 extract 目录为
输入，不再物化副本，故同一 stem 恒指向同一页。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.store.json_io import read_json, write_json


class AnnotationMixin:
    """boxes.json / sizes.json 读写。"""

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        artifact: Callable[..., Path]
        task_dir: Callable[[str], Path]
        task_diagram: Callable[[str], Any]

    def _load_json(self, path: Path) -> dict:
        data = read_json(path, {})
        return data if isinstance(data, dict) else {}

    def _save_json(self, path: Path, data: dict) -> None:
        if not path.parent.exists():
            return
        write_json(path, data)

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
        entry = self._load_json(path).get(image_key)
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
        data = self._load_json(path)
        return {
            key: (entry.get("boxes", []), entry.get("origin", "auto"))
            for key, entry in data.items() if isinstance(entry, dict)
        }

    def save_detect_boxes(
        self, task_id: str, image_key: str, boxes: list, origin: str = "auto",
        node_id: str | None = None, primary_id: str | None = None,
    ) -> None:
        """写入某页的检测框及其来源标记（auto=自动检测，manual=人工编辑）。

        ⚠️ **保留**该页已有的 ``side``（用户在半框页上指定的左右，见
        :meth:`set_box_side_override`）：拖框/缩放走的是这条路径，
        顺手把用户刚指定的左右清掉，等于"一拖就丢设定"。
        """
        path = self.boxes_path(task_id, node_id, primary_id)
        data = self._load_json(path)
        previous = data.get(image_key) or {}
        entry = {
            "boxes": boxes,
            "origin": origin,
            "updated_at": time.time(),
        }
        if previous.get("side"):
            entry["side"] = previous["side"]
        data[image_key] = entry
        self._save_json(path, data)

    # ---------- 半框页的人工左右指定 ----------
    def box_side_at(self, path: Path | None, image_key: str) -> str | None:
        """读**指定文件**里某页的人工左右指定（``"left"``/``"right"``/None）。

        ⚠️ 这是**用户显式声明**，不是按位置算出来的左右（那由
        ``box_geometry.half_sides`` 现算）。只有「半框」页需要它：那种框横跨
        整页、中心压在中线上，位置判定没有意义。
        """
        if path is None:
            return None
        entry = self._load_json(path).get(image_key)
        if not isinstance(entry, dict):
            return None
        side = entry.get("side")
        return side if side in ("left", "right") else None

    def box_sides_all_at(self, path: Path | None) -> dict[str, str]:
        """整份文件的 ``image_key → side``（一次读盘，只含有显式指定的页）。"""
        if path is None:
            return {}
        out: dict[str, str] = {}
        for key, entry in self._load_json(path).items():
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
        """写入/清除某页的人工左右指定（``None``＝清除，退回"半框"）。

        ⚠️ 独立成一个方法而不是给 ``save_detect_boxes`` 加参数：那条路是
        "拖框/缩放"的高频路径，**不该**顺带改这个语义位。只有用户明确点了
        「左框/右框」才动它。
        """
        path = self.boxes_path(task_id, node_id, primary_id)
        data = self._load_json(path)
        entry = data.get(image_key)
        if not isinstance(entry, dict):
            return  # 没有框就没有"这页是什么侧"可言
        if side in ("left", "right"):
            entry["side"] = side
        else:
            entry.pop("side", None)
        entry["updated_at"] = time.time()
        data[image_key] = entry
        self._save_json(path, data)

    def save_detect_boxes_batch(self, task_id: str, entries: dict[str, list],
                                node_id: str | None = None,
                                primary_id: str | None = None) -> None:
        """批量写入某阶段的检测框（origin=auto）：**一次读改写**。

        ⚠️ 为什么必须攒批：detect 跑 320 页时逐页 `save_detect_boxes` 是
        「读整个 boxes.json + 改写」× 页数，实测 320 页累计 **1.8 秒**主线程
        阻塞（2400 页的书记忆里是 47.5s，见
        ``.workbuddy/perf/2026-09-23-sqlite-vs-json.md``）；攒批后一次落盘
        ~0.02s。人工框（origin=manual）在这里跳过，不被自动结果覆盖——
        与单条版同一条规矩，但只读一次文件。
        """
        if not entries:
            return
        path = self.boxes_path(task_id, node_id, primary_id)
        data = self._load_json(path)
        updated = time.time()
        for image_key, boxes in entries.items():
            if not boxes or not any(boxes):
                continue
            if (data.get(image_key) or {}).get("origin") == "manual":
                continue  # 人工框优先
            data[image_key] = {
                "boxes": boxes,
                "origin": "auto",
                "updated_at": updated,
            }
        self._save_json(path, data)

    def save_image_sizes_batch(
        self, task_id: str, entries: dict[str, tuple[int, int]],
        node_id: str | None = None, primary_id: str | None = None,
    ) -> None:
        """批量写入页面原始尺寸：一次读改写（理由同 save_detect_boxes_batch）。"""
        if not entries:
            return
        path = self.sizes_path(task_id, node_id, primary_id)
        data = self._load_json(path)
        for image_key, size in entries.items():
            data[image_key] = [int(size[0]), int(size[1])]
        self._save_json(path, data)

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
        data = self._load_json(path)
        data[image_key] = [int(width), int(height)]
        self._save_json(path, data)

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
        data = self._load_json(scoped)
        entry = data.get(image_key)
        if not entry and node_id and primary_id and node_id != primary_id:
            data = self._load_json(self.sizes_path(task_id))
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
        data = self._load_json(self.sizes_path(task_id, node_id, primary_id))
        out: dict[str, tuple[int, int]] = {}
        for key, entry in data.items():
            try:
                out[key] = (int(entry[0]), int(entry[1]))
            except (TypeError, ValueError, IndexError):
                continue  # 畸形条目跳过，别让一条坏记录毁掉整本尺寸
        return out
