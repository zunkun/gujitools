# -*- coding: utf-8 -*-
"""图片拼版文档（``drafts/imposition.json``）：选择态 + 逐页拼版版面。

为什么放在 ``drafts/`` 而不是任务根目录：这个文件从「图片拼版」占位节点
时代就在那里（当时只有 ``{"enabled": bool}``），换位置会让老任务的选择态
凭空丢失。现在扩成一句话能读完的形状：

    {
      "enabled": true,                      # 是否把拼版接进流程（第四步取图开关）
      "pages": [                            # 拼版清单，列表顺序即产出页序
        {
          "items": [                        # 恒 2 项：0=右槽（序号在前），1=左槽
            {"file": "...", "rect": [x, y, w, h], "rotation": 0.0},
            {"file": "...", "rect": [x, y, w, h], "rotation": 0.0}
          ]
        }
      ]
    }

``rect`` 的单位是**源图像素**（左上原点、x 向右、y 向下）。``rotation`` 是
**顺时针角度**（与 Qt ``QPainter.rotate`` 同向；PIL 侧取负）。

⚠️ **没有 ``sheet``**（用户 2026-09-30：「拼版不需要设置纸张，只需要背景是
白色的就行，后续提交的时候根据图片的四个区域合并出一张图片」）：早期版本存过
``"sheet": [w, h]``，现在读进来**直接忽略**——版面完全以两张图为准，产出图按
所有图的外接框紧裁（``services.imposition.page_bounds``）。

形状校验与合成规则都在 ``desktop.services.imposition``（**唯一实现处**）——
这里只负责「按任务目录读写这份 JSON」，读出来的东西一律过一遍
``normalize_doc``，调用点不用判空、不用自己验字段。

⚠️ 只做「读—写」，不碰 Qt。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from desktop.services.imposition import ITEMS_PER_PAGE, normalize_doc
from desktop.store.json_io import (
    read_json, resolve_scoped_path, write_json, write_owner,
)

__all__ = ["ITEMS_PER_PAGE", "ImpositionMixin", "normalize_doc"]


class ImpositionMixin:
    """``drafts/imposition.json`` 的读写。"""

    root: Path

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        task_dir: Callable[[str], Path]
        drafts_dir: Callable[[str], Path]
        step_enabled: Callable[..., bool]

    def imposition_doc_path(self, task_id: str, node_id: str | None = None,
                            primary_id: str | None = None) -> Path:
        """拼版文档：主节点是 ``drafts/imposition.json``，副本是
        ``drafts/imposition~<节点>.json``（B 方案，2026-10-17）。

        ⚠️ **版面按节点分**：文档里存的是"哪两张图拼成一页、各自什么位置"，
        是**这一步的用户意图**。两个「图片拼版」节点共用一份，改一个的版面
        另一个跟着变——而且会拿 A 的版面去合成 B 的成品页。

        ⚠️ ``enabled``（"在流程中启用图片拼版"）**仍读共享那份**
        （见 :meth:`step_enabled`）：它是**流程级**条件（状态机的 ``imposition``
        标志没有节点上下文），不是某个节点自己的开关。
        """
        from desktop.steps import ports

        name = ports.scoped_name("imposition.json", node_id, primary_id)
        return resolve_scoped_path(self.drafts_dir(task_id) / name, node_id)

    def load_imposition_doc(self, task_id: str, node_id: str | None = None,
                            primary_id: str | None = None) -> dict:
        """读拼版文档（缺失/损坏一律回落成空文档，调用点不用判空）。"""
        return normalize_doc(
            read_json(self.imposition_doc_path(task_id, node_id, primary_id), None)
        )

    def imposition_enabled(self, task_id: str) -> bool:
        """这个任务**是否启用了拼版**（只有 ``enabled``，不看有没有拼版页）。

        给**任务列表**用：列表要回答"这条任务有几个子任务"，而拼版是个可选
        节点——详情页勾了「在流程中启用图片拼版」才把它算进流程（用户 2026-10-03
        口径："子任务到底有几个需要根据详情决定"）。所以判据是**勾没勾**，
        不是"生不生效"（生效还要至少一页，那是 ``imposition_active`` 的口径）。

        ⚠️ 这里**只读 enabled 一个键**，不走 ``load_imposition_doc``：那份文档
        逐页带 rect/rotation，200 页的书能有几百 KB，列表页每个任务都要读一次，
        没必要把整份版面都反序列化。缺文件/坏文件一律当"没启用"。
        ⚠️ 实现走通用的 :meth:`step_enabled`（同一文件、同一键）——拼版开关
        只是"可选步骤开关"的第一个实例，别再为第二个起一份读法。
        """
        return self.step_enabled(task_id, "imposition")

    def save_imposition_doc(self, task_id: str, doc: dict,
                            node_id: str | None = None,
                            primary_id: str | None = None) -> bool:
        """写拼版文档，返回是否真的写了。

        任务目录已删除时跳过（与 ``save_pages`` 同规矩：不把已删任务重新
        创建出来）。
        """
        if not task_id:
            return False
        if not self.task_dir(task_id).exists():
            return False
        self.drafts_dir(task_id).mkdir(parents=True, exist_ok=True)
        path = self.imposition_doc_path(task_id, node_id, primary_id)
        write_json(path, normalize_doc(doc))
        write_owner(path, node_id or primary_id)
        return True
