# -*- coding: utf-8 -*-
"""界面状态（``ui.json``）：与"用户上次看到哪"有关的小状态，分两层记。

**任务级**——``tasks/<任务号>/ui.json``（删除任务即清掉）：

    {"last_stage": "rembg"}      # 上次在这个任务里停留的步骤 key

**为什么记 key 而不是下标**：流程里的步骤会增减（「图片拼版」虚线节点就是
条件出现的可选步骤），下标一旦错位就会把用户送到**另一个**步骤去；key 是按
语义匹配的，步骤没了自然"匹配不上"，调用方据此回落第一步。

key 取自 ``desktop.store.tasks``：``STAGES`` 里的一项，或伪步骤
``IMPOSITION_STAGE``（"imposition"）。

**全局**——数据根目录下的 ``ui.json``（跨任务共享，只一项）：

    {"last_task": "0012", "source_hash": "…"}

记录「上次进入的任务」。⚠️ **当前不作为启动入口**（用户 2026-10-06 改口径：
启动一律停在任务列表页，不再自动跳回上次任务详情）。仍然照写，是给"一键回到
上次任务"这类显式入口留的底子——真要加回入口不必重造记录。``source_hash``
是防撞号的：任务号**顺序复用**（删掉 0012 再新建，新任务也叫 0012），指纹
对不上说明这个号已经是别的任务。

⚠️ 只做「读—写」，不碰 Qt。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.store.json_io import read_json, write_json

__all__ = ["UIStateMixin"]


class UIStateMixin:
    """``ui.json`` 的读写（任务级 + 全局）。"""

    root: Path

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：Mixin 本体不持有，只做类型声明，
        # 运行时零副作用（与 taskdetail 侧 Mixin 同一套路）。
        task_dir: Callable[[str], Path]
        get_task: Callable[[str], Any]

    # ---------- 全局：上次停留的任务（记录；不再当启动入口） ----------
    def app_ui_path(self) -> Path:
        """全局界面状态文件：数据根目录下的 ``ui.json``（跨任务共享）。"""
        return self.root / "ui.json"

    def load_last_task(self) -> dict | None:
        """上次停留的任务记录 ``{"id":…, "source_hash":…}``；没有/写坏返回 None。

        ⚠️ **启动已不再自动跳回上次任务**（用户 2026-10-06），本方法只服务于
        「一键回到上次任务」这类**显式**入口。将来加那个入口时，用它拿到记录
        后**必须**用 ``get_task`` + 指纹比对确认"这个号还是当初那个任务"
        （见模块注释的防撞号说明），不能只看 id 就往里跳。
        """
        data = read_json(self.app_ui_path(), None)
        if not isinstance(data, dict):
            return None
        task_id = data.get("last_task")
        if not isinstance(task_id, str) or not task_id:
            return None
        source_hash = data.get("source_hash")
        return {
            "id": task_id,
            "source_hash": source_hash if isinstance(source_hash, str) else "",
        }

    def save_last_task(self, task_id: str) -> bool:
        """记录「上次停留的任务」（供将来的显式"回到上次任务"入口用）。

        只在任务真实存在时写（不给不存在的任务留指针）；指纹一并入库，
        见 :meth:`load_last_task`。
        """
        if not task_id:
            return False
        task = self.get_task(task_id)
        if not task:
            return False
        write_json(
            self.app_ui_path(),
            {
                "last_task": str(task_id),
                "source_hash": str(task.get("source_hash") or ""),
            },
        )
        return True

    # ---------- 任务级：上次停留的步骤 ----------
    def ui_state_path(self, task_id: str) -> Path:
        """任务界面状态文件：``tasks/<任务号>/ui.json``。"""
        return self.task_dir(task_id) / "ui.json"

    def load_last_stage(self, task_id: str) -> str | None:
        """上次停留的步骤 key；没有记录/格式不对返回 None。"""
        data = read_json(self.ui_state_path(task_id), None)
        if not isinstance(data, dict):
            return None
        value = data.get("last_stage")
        return value if isinstance(value, str) and value else None

    def save_last_stage(self, task_id: str, stage: str) -> bool:
        """记录上次停留的步骤 key，返回是否真的写了。

        任务目录已删除时跳过（与 ``save_pages``/``save_imposition_doc``
        同一条规矩：不把已删任务重新创建出来）。文件里只覆盖 ``last_stage``
        一项，将来加别的界面状态互不影响。
        """
        if not task_id or not stage:
            return False
        if not self.task_dir(task_id).exists():
            return False
        path = self.ui_state_path(task_id)
        data = read_json(path, None)
        doc = dict(data) if isinstance(data, dict) else {}
        doc["last_stage"] = str(stage)
        write_json(path, doc)
        return True
