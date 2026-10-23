# -*- coding: utf-8 -*-
"""页面清单（pages.json）：当前任务参与处理的页集合。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from desktop.utils.files import IMAGE_SUFFIXES
from desktop.store.json_io import (
    read_json, resolve_scoped_path, write_json, write_owner,
)
from utils.sort_utils import natural_sort_key


class PageManifestMixin:
    """pages.json 的读写与按阶段输出目录重建。"""

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        task_dir: Callable[[str], Path]
        #: 节点 → 运行阶段（``pages.<阶段>.json`` 的命名要用它）
        node_stage_of: Callable[[str], str | None]

    def pages_path(self, task_id: str, node_id: str | None = None,
                   primary_id: str | None = None) -> Path:
        """页面清单文件：主节点是任务目录下的 ``pages.json``，副本是
        ``pages~<节点>.json``（B 方案，2026-10-17）。

        ⚠️ **仍是"每任务一份"**（不是每步一份），理由：
        - 清单是"**这个任务参与处理哪几页**"的用户意图（删页/插页/重排）；
          按步骤分文件会让"在第二步删掉的页"在第三/四步**复活**——那些步骤
          会把目录里的文件重新列出来（用户会以为删除没生效）；
        - 第四步的 ``print.json``、拼版的版面文档本来就各自独立，清单只服务
          「提取 / 检测 / 去底色」这几步的页条。

        步骤之间"清单跟着输入走"由 ``manifest._sync_manifest_to_input`` 负责：
        上游产物换了（拼版刚出成品、换节点）就按**本步的输入目录**重建。

        副本节点（同一步骤的第二个及之后节点）仍然各存一份——那是**同一屏**
        的两个节点，共用一份会互相覆盖。
        """
        from desktop.steps import ports

        name = ports.scoped_name("pages.json", node_id, primary_id)
        return resolve_scoped_path(self.task_dir(task_id) / name, node_id)

    def load_pages(self, task_id: str, node_id: str | None = None,
                   primary_id: str | None = None) -> list[dict]:
        """读取页面清单；文件缺失或格式异常时返回空列表。"""
        data = read_json(self.pages_path(task_id, node_id, primary_id), [])
        return data if isinstance(data, list) else []

    def save_pages(self, task_id: str, pages: list[dict],
                   node_id: str | None = None,
                   primary_id: str | None = None) -> None:
        """写回页面清单；任务目录已删除时跳过（不重建目录）。"""
        if not self.task_dir(task_id).exists():
            return
        path = self.pages_path(task_id, node_id, primary_id)
        write_json(path, pages)
        write_owner(path, node_id or primary_id)

    def refresh_pages_from_dir(self, task_id: str, directory: Path,
                               node_id: str | None = None,
                               primary_id: str | None = None) -> list[dict]:
        """用某阶段输出目录重建页面清单（大任务当前的页集合）。"""
        pages = []
        if directory.exists():
            files = sorted(
                (f for f in directory.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES),
                key=lambda f: natural_sort_key(f.name),
            )
            pages = [{"file": str(f), "label": f.stem} for f in files]
        self.save_pages(task_id, pages, node_id, primary_id)
        return pages

    # ---------- print 页面列表 print.json ----------
    # 文档格式：{"pages": [{file,label,box}]}
    # box 为该条目的效果区域（原始像素坐标）；None 表示整页透传。
    # ⚠️ 2026-10-22 起没有 area/border：旧版写下的这两个键读进内存后不再被
    #    任何逻辑消费，保存时也不再补回。

    def print_pages_path(self, task_id: str, node_id: str | None = None,
                         primary_id: str | None = None) -> Path:
        """待打印列表文件：主节点是 ``print.json``，副本是 ``print~<节点>.json``。

        ⚠️ **清单按节点分**（B 方案）：``print.json`` 存的是"待打印图 + 页序 +
        逐页版面 rect"，是**这一步的用户意图**。两个「PDF排版」节点共用一份，
        切到第二个节点会看到第一个节点的页序与版面——而且在 B 上"生成 PDF"
        会用 A 的排版出图。
        """
        from desktop.steps import ports

        name = ports.scoped_name("print.json", node_id, primary_id)
        return resolve_scoped_path(self.task_dir(task_id) / name, node_id)

    def load_print_doc(self, task_id: str, node_id: str | None = None,
                       primary_id: str | None = None) -> dict | None:
        """读取 print.json 全文（含 pages）；缺失或非字典时返回 None。"""
        data = read_json(self.print_pages_path(task_id, node_id, primary_id), None)
        return data if isinstance(data, dict) and "pages" in data else None

    def save_print_doc(self, task_id: str, doc: dict,
                       node_id: str | None = None,
                       primary_id: str | None = None) -> None:
        """写回 print.json；任务目录已被删除时静默跳过（不重建目录）。"""
        if not self.task_dir(task_id).exists():
            return
        path = self.print_pages_path(task_id, node_id, primary_id)
        write_json(path, doc)
        write_owner(path, node_id or primary_id)

    def load_print_pages(self, task_id: str, node_id: str | None = None,
                         primary_id: str | None = None) -> list[dict]:
        """只取 print.json 的 pages 列表；无文档时返回空列表。"""
        doc = self.load_print_doc(task_id, node_id, primary_id)
        return doc.get("pages", []) if doc else []

    def save_print_pages(self, task_id: str, entries: list[dict],
                         node_id: str | None = None,
                         primary_id: str | None = None) -> None:
        """只替换 print.json 的 pages 字段，保留其它配置。"""
        doc = self.load_print_doc(task_id, node_id, primary_id) or {
            "pages": []
        }
        doc["pages"] = entries
        self.save_print_doc(task_id, doc, node_id, primary_id)
