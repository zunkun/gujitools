# -*- coding: utf-8 -*-
"""检测框文件的定位与整本缓存（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop.pages.taskdetail.detect._host import DetectHost
else:
    DetectHost = object


class DetectBoxCacheMixin(DetectHost):
    """本步/消费方要读的 ``boxes`` 文件，以及逐页/整本取框缓存。"""
    # ------------------------------------------------- 检测框的节点作用域（B 方案）
    def _boxes_write_path(self) -> Path | None:
        """**本步要写**的检测框文件：当前「检测文本框」节点那一份。

        主节点 ⇒ ``boxes.json``（零迁移），副本 ⇒ ``boxes~<节点>.json``。
        """
        if not self.task_id:
            return None
        return self.store.boxes_path(
            self.task_id, **self._node_scope(self.node_of_stage("detect"))
        )

    def _boxes_read_path(self) -> Path | None:
        """**消费方要读**的检测框文件：由连线喂给**当前节点**的那个产出方。

        「图片去底色」/「提交」读的框不该是"本阶段的 boxes"，而是**图上喂它的
        那个检测节点**的 boxes（B 方案：同一步骤可以有多个「检测文本框」，
        第二个节点喂第二条去底色链）。解析不到上游时回落到主节点的
        ``boxes.json``——流程里没有检测节点时行为与改造前一致。
        """
        if not self.task_id:
            return None
        node = self.current_node()
        if node:
            path = self.store.node_input(
                self.task_id, node, "boxes", self.imposition_effective()
            )
            if path is not None:
                return path
        step = "detect"
        return self.store.boxes_path(
            self.task_id, **self._node_scope(self.node_of_stage(step))
        )
    def _detect_boxes_for(self, path_text: str) -> list:
        """某页的检测框（内存缓存优先，其次 boxes.json）。

        ⚠️ 消费方读取（B 方案）：存档框取**连线上喂给当前节点**的那个检测
        节点的文件（``_boxes_read_path``）——两个「检测文本框」节点各有各的框，
        按阶段读会让去底色用错节点的框裁图。

        ⚠️ 走 :meth:`_boxes_map_cached`（整本一次读齐 + 失效缓存）：
        查看器构建条目会**逐页**回调本方法，逐页解析流程图 + 读整份
        ``boxes.json`` 就是 O(n²)。
        """
        boxes = self.detect_cache.get(str(path_text))
        if boxes is not None:
            return boxes or []
        return self._boxes_map_cached().get(Path(path_text).stem, []) or []

    def _boxes_map_cached(self) -> dict:
        """整本 ``{页名: 原始槽位}``，带缓存（``_detect_boxes_for`` 的整本版）。

        ⚠️ 为什么要有缓存：查看器重建条目时会**逐页**回调 ``boxes_provider``
        （110 页 = 110 次），每次走一遍"解析流程图 → 找上游连接线 → 读
        boxes.json"就是 O(n²)——真实 GUI 实测这一步占 0.27~0.58s，是进详情/
        首帧卡顿的主要残留。这里把整本读成一张表，只在下列任一项变化时重算：

        - ``detect_cache.version``（用户改框，``VersionedBoxCache`` 自增）；
        - 框文件指纹（mtime_ns + size，外部落盘如批量检测写回）；
        - 页清单（``_manifest_paths``，内建签名缓存，命中很便宜）；
        - 当前步骤格序（换了节点 ⇒ 上游框可能来自另一份文件）。

        ⚠️ 不能改成"调用方传一张一次性快照"：查看器的 provider 是长期持有的，
        之后改框 / 单页检测落盘都会再次重建条目，快照会把用户刚改的框吃掉。
        """
        paths = self._manifest_paths()
        version = getattr(self.detect_cache, "version", 0)
        bar = getattr(getattr(self, "step_bar", None), "_current", -1)
        file_key = tuple(str(path) for path in paths)
        cache = self.__dict__.get("_boxes_map_cache")
        read_path = cache.get("path") if cache else None
        key = (self.task_id, bar, version, file_key, str(read_path),
               self._file_fingerprint(read_path))
        if cache is not None and cache.get("key") == key:
            return cache["map"]
        # 未命中才现算（见 _boxes_map_all）
        mapping = self._boxes_map_all()
        read_path = self._boxes_read_path() if self.task_id else None
        self._boxes_map_cache = {
            "key": (self.task_id, bar, version, file_key,
                    str(read_path) if read_path else None,
                    self._file_fingerprint(read_path)),
            "map": mapping,
            "path": read_path,
        }
        return mapping

    @staticmethod
    def _file_fingerprint(path) -> tuple[int, int] | None:
        """文件指纹（``mtime_ns`` + ``size``）；文件不存在返回 None。"""
        if path is None:
            return None
        try:
            stat = Path(path).stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _boxes_map_all(self) -> dict:
        """整本：``{页名: 原始槽位}``，**一次读盘**（语义与 ``_detect_boxes_for`` 对齐）。

        ⚠️ 逐页调 ``_detect_boxes_for`` 会对每页重读整份 ``boxes.json``（O(n²)）；
        提交裁图前要整书判据（单栏书结论），必须一次读齐。

        口径与 :meth:`_detect_boxes_for` 逐条一致：内存缓存（用户刚改过的）优先，
        其次连线上游那个节点的 ``boxes`` 文件。
        """
        paths = self._manifest_paths()
        if not paths:
            return {}
        stored = (
            self.store.boxes_all_at(self._boxes_read_path())
            if self.task_id else {}
        )
        boxes: dict = {}
        for p in paths:
            cached = self.detect_cache.get(str(p))
            if cached is not None:
                boxes[Path(p).stem] = list(cached)
                continue
            entry = stored.get(Path(p).stem)
            boxes[Path(p).stem] = list(entry[0]) if entry else []
        return boxes
