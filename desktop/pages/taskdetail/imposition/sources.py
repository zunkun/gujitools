# -*- coding: utf-8 -*-
"""拼版共享基元的**源图与生效**分片：候选源图、产物角色、第四步取图来源。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.utils.files import list_stage_images
from utils.sort_utils import natural_sort_key

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition._host import ImpositionBaseHost
else:
    ImpositionBaseHost = object


class SourcesMixin(ImpositionBaseHost):
    """拼版源图清单、产物角色映射、生效判据与第四步取图目录。"""

    # ------------------------------------------------------------- 源图与生效
    def imposition_source_files(self) -> list[Path]:
        """可挑选的源图：**拼版这一步的 pages 端口**指向的目录。

        ⚠️ 此前这里写死 ``store.rembg_output_dir()``（＝``stages/rembg``）——
        那是**问输入却写成写死**：自定义流程把连线改了（或者压根没有去底色
        那一格）时，它会去读一个永远不会被产出的目录，于是「＋选择拼版」弹
        "没有可拼版的图片，请先提交本次任务"——而那一步压根不在流程里。
        现在与 :meth:`print_source_dir` 同构，走 ``store.stage_input``。

        ⚠️ ``imposition_active`` 必须传 **True**（不是 ``imposition_effective()``）：
        这里问的是"**如果**拼版要跑，它的输入来自谁"，与开关无关。开关没勾时
        状态机把 ``imposition`` 剔出 active 集合，节点粒度的回溯连起点都不认
        （``_node_producers`` 直接返回空），于是退回静态声明 ``rembg``——那是
        默认流程里拼版的**下游**。用户 2026-11-03 自定义流程实测：选图弹窗的
        候选跟着开关变（勾了是上一步、没勾是下一步去底色结果）。
        """
        if not self.task_id:
            return []
        # ⚠️ **按节点取图**（B 方案）：拼版这一步的源图跟着**当前拼版节点**的
        #    连线走——同一步骤多个节点时，按阶段取会读到主节点的上游（用户给
        #    第二个拼版节点连了另一批图，界面却列第一批）。
        node = self.node_of_stage("imposition")
        # ⚠️ 只看目录不够：上游（通常是「图片去底色」）的产出动作没执行成功时，
        #    目录里可能只有实时预览提前写下的图，不该拿来拼版（用户 2026-11-03）。
        ready = (
            self.store.node_input_effective(self.task_id, node, "pages", True)
            if node
            else self.store.stage_input_effective(
                self.task_id, "imposition", "pages", True
            )
        )
        if not ready:
            return []
        source = (
            self.store.node_input(
                self.task_id, node, "pages", imposition_active=True
            )
            if node
            else self.store.stage_input(
                self.task_id,
                "imposition",
                "pages",
                imposition_active=True,
            )
        ) or self.store.rembg_output_dir(self.task_id)
        files = list_stage_images(source)
        return sorted(files, key=lambda p: natural_sort_key(p.name))

    # ------------------------------------------------- 提交计划（产物角色）
    def _upstream_detect_node(self) -> str | None:
        """沿流程**往前**找喂给拼版的「检测文本框」节点。

        拼版的输入链是 ``imposition ← rembg ← detect_submit（同一节点的第二个
        动作）``；``node_supplier`` 把 ``detect_submit`` 折回 ``detect`` 节点。
        ⚠️ 不能按"阶段主节点"取：同一步骤可能有多个检测节点，读错一份就是
        "另一批图的名字套到我们这批图上"。

        ⚠️ **拼版在检测之前时永远返回 None**：这里只走 ``pages`` 的**供给方**
        （严格向前回溯），下游的检测节点不在链上。这是刻意的——那种流程里
        拼版吃的是入口/提取的**整页原图**，``boxes.json`` 描述的是另一批产物，
        拿它按页号套身份会把整页图错当半幅配对（用户 2026-10-23）。
        """
        node = self.node_of_stage("imposition")
        seen: set[str] = set()
        while node and node not in seen:
            seen.add(node)
            diagram = self.store.task_diagram(self.task_id) if self.task_id else None
            item = diagram.node(node) if diagram is not None else None
            if item is not None and getattr(item, "stage", None) == "detect":
                return node
            # ⚠️ 传 ``True`` 而不是 ``imposition_effective()``：这里问的是
            #    "**如果**拼版要跑，它的输入来自谁"——用户还没勾「启用拼版」时
            #    状态机把 imposition 排除在外，供给方会退化成**阶段 key**
            #    （如 ``"rembg"``），往下就再也走不到检测节点，角色表整份为空
            #    （任务 0004 实测：开关没勾时无后缀图全按整幅拆开）。
            ref = self.store.node_supplier(
                self.task_id, node, "pages", True
            ) if self.task_id else None
            if not ref or str(ref).startswith("<"):
                return None
            node = str(ref)
            if diagram is not None and diagram.node(node) is None:
                # 静态声明给的就可能是阶段 key：折成该阶段的主节点继续往前
                node = self._stage_primary.get(node) or ""
        return None

    def imposition_role_map(self) -> dict[str, str]:
        """``{产物 label: role}``（来自上游检测节点的提交计划，拼版配对用）。

        读不到（旧任务没有计划 / 没有检测节点）就返回空字典——调用方据此保持
        纯文件名行为，不会因为缺计划把整幅图错配对。

        ⚠️ 返回值**额外带同一页的文件名别名**（见
        :func:`desktop.services.imposition.expand_role_aliases`）：计划按产物
        label 记身份，而下游文件名可能跨版本不一致（计划无后缀、旧产物还带
        ``-l``/``-r``，或反之）——不补别名就查不到角色，只能回落成整幅、两张
        拆开（任务 0004）。
        """
        from desktop.services.imposition import expand_role_aliases

        task_id = self.task_id
        detect_node = self._upstream_detect_node() if task_id else None
        if not task_id or not detect_node:
            return {}
        try:
            path = self.store.boxes_path(task_id, detect_node)
            plans = self.store.detect_plans_all_at(path)
        except Exception:  # noqa: BLE001 - 计划是可选参考，读不到就回落文件名
            return {}
        roles: dict[str, str] = {}
        for plan in plans.values():
            for output in (plan or {}).get("outputs") or []:
                label = output.get("label")
                role = output.get("role")
                if label and role:
                    roles[str(label)] = str(role)
        return expand_role_aliases(roles)

    def imposition_active(self) -> bool:
        """拼版**是否已启用**（用户勾了「在流程中启用图片拼版」就是启用）。

        ⚠️ **只看勾没勾，不看有没有拼版页**（用户 2026-10-03 口径："如果启用了
        拼版，则最后一步生成 pdf 的数据来源就是拼版"）。早先这里额外要求
        "至少有一页"，于是勾了开关却还没拼页时——取图仍走去底色、流程条仍是
        灰虚线 + 绕行线，用户看到的就是"启用了却不生效"。「有没有拼版页」是
        另一件事（能不能真出东西），走 :meth:`imposition_has_pages`。

        ⚠️ 这是**流程级**的判据（决定第四步取图来源），开关只有一份、存在主节点
        那份 ``drafts/imposition.json`` 里（见 :meth:`_imposition_flag_scope`）。
        ⚠️ **流程条上每个拼版节点的"已选择/绿勾"不看它**（2026-10-18）：那一格
        表达"这一步处理到哪了"，判据是该节点自己有没有拼版页
        （见 :meth:`_sync_imposition_nodes`）。
        """
        task_id = getattr(self, "task_id", None)
        if not task_id:
            return False
        return self.store.step_enabled(task_id, "imposition")

    def imposition_has_pages(self) -> bool:
        """拼版文档里**至少有一页**版面（能不能真的合成出图）。

        与 :meth:`imposition_active` 分开：启用是**用户意图**（决定取图来源），
        有页是**当前进度**（决定要不要提示"还没拼版，PDF排版没有输入"）。
        """
        if not getattr(self, "task_id", None):
            return False
        return bool(self._imposition_doc().get("pages"))

    def print_source_dir(self) -> Path:
        """第四步的取图目录：拼版生效 → stages/imposition，否则 stages/rembg。

        ⚠️ 走的是 :mod:`desktop.steps.ports` 的**条件连线**（"print 的 pages
        端口由谁供给"），不是在这里 if/else 挑目录——BPM 换上游时只改连线表，
        这一行不用动。
        """
        task_id = self.task_id
        assert task_id is not None, "取图来源只在任务态被读取"
        # ⚠️ **按节点取图**（B 方案）：两个「PDF排版」节点各有自己的上游
        #    （可以一个吃去底色成品、另一个吃拼版成品），按阶段取会让两个节点
        #    都读同一个来源——面板说 A、执行做 B。
        node = self.node_of_stage("print")
        source = (
            self.store.node_input(
                task_id, node, "pages", imposition_active=self.imposition_effective()
            )
            if node
            else self.store.stage_input(
                task_id,
                "print",
                "pages",
                # ⚠️ 传"能不能真跑"而不是"勾没勾"：图里没这一格时不该取拼版
                #    产物——历史脏数据（先勾了、后来把节点删了）会让第四步去读
                #    一个根本不该用的目录。
                imposition_active=self.imposition_effective(),
            )
        )
        # 连线表永远给得出路径（rembg 是 print 的静态上游），
        # 但仍留一道兜底：将来若有人把静态上游摘掉，这里不该抛 AttributeError。
        return source or self.store.rembg_output_dir(task_id)
