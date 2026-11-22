# -*- coding: utf-8 -*-
"""任务索引（tasks.json）读写、任务号水位与任务增删改查。

从 ``desktop/store/tasks.py`` 拆出（2026-11-22）：只管**记录**，不推导路径
落点（见 ``paths.py``）也不解析流程图（见 ``diagram.py``）。
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from desktop.steps.flow import FlowDefinition, FlowLayout, default_flow_path
from desktop.store.json_io import read_json, write_json
from desktop.store.tasks.base import TaskMixinBase
from desktop.utils.files import copy_file_atomic


class TaskRecordMixin(TaskMixinBase):
    """任务索引读写与任务 CRUD（含聚合任务）。"""

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        task_dir: Callable[[str], Path]
        #: 任务号形状校验（``paths.TaskLayoutMixin`` 上的类属性）
        _TASK_ID_RE: Any
        _log_flow_write_error: Callable[[str, OSError], None]

    # ---------- tasks.json ----------
    def _tasks_path(self) -> Path:
        return self.root / "tasks.json"

    def _load_tasks_index(self) -> list[dict]:
        data = read_json(self._tasks_path(), [])
        return data if isinstance(data, list) else []

    def _save_tasks_index(self, tasks: list[dict]) -> None:
        self._tasks_path().parent.mkdir(parents=True, exist_ok=True)
        write_json(self._tasks_path(), tasks)

    # ---------- 任务号水位（删除不回收号） ----------
    def _task_no_path(self) -> Path:
        """「已分配过的最大任务号」的落点：``<数据根>/task_no.json``。

        ⚠️ 与 ``tasks.json`` **并列**放在数据根，而不是塞进 ``tasks/`` 目录里：
        ``tasks/`` 下全是任务号目录，往里放一个非任务文件容易被将来的"清理孤儿
        目录"逻辑误删。放根目录与 ``tasks.json`` 同族，语义上就是"索引级元数据"。
        """
        return self.root / "task_no.json"

    def _read_max_allocated(self) -> int:
        """读水位（坏文件/没文件都当 0——不因为它而建不出任务）。"""
        data = read_json(self._task_no_path(), {})
        try:
            return max(0, int((data or {}).get("max_allocated") or 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    def _bump_max_allocated(self, number: int) -> None:
        """把水位抬到至少 ``number``（**只增不减**）。

        用户 2026-10-16：「任务删除，任务序号保留占用」——删掉 0020 之后新建的
        必须是 0021，00**20 不许再被用**。只靠"索引里的最大号"做不到：删除会把
        记录从索引里抹掉、目录也删了，最大号就退回到 0019 ⇒ 下一个又是 0020。
        所以要有这个**只涨不跌**的水位。

        ⚠️ 写失败**不抛**（只让本次"号不回收"的保证失效，不该连建任务/删任务
        一起拖死）；水位本身也会在下一次创建/删除时再被抬一次。
        """
        if number <= self._read_max_allocated():
            return
        try:
            write_json(self._task_no_path(), {"max_allocated": int(number)})
        except OSError:
            pass

    # ---------- 任务 CRUD ----------
    def next_task_no(self) -> str:
        """下一个任务号（**预测值**）：当前最大号 + 1，参考索引、磁盘目录与水位。

        给界面做**占位提示**用（如创建页的默认任务名「任务#0007」）。

        ⚠️ 它只是预测：``create_task`` 真正占号是原子的（``mkdir
        exist_ok=False``，被抢就顺延），所以并发/历史残留时**实际拿到的号
        可能比这里大**。因此：
        - 界面拿它显示"将要用的名字"可以（占位文字而已）；
        - **落库时不要信它**——默认名一律由 :meth:`create_task` 用**实际
          分配到的** ``task_id`` 现算（见 :meth:`default_task_name`），
          否则名字里的序号会和任务号对不上（用户会以为"任务#0008"就是
          0008 号任务，结果落在 0009 上）。

        ⚠️ 它**不回收**已删除的号（见 :meth:`_bump_max_allocated`）：删掉 0020
        之后这里给的是 0021，不是 0020。
        """
        return self._next_task_no()

    def default_task_name(self) -> str:
        """默认任务名「任务#XXXX」（XXXX = 预测的下一个任务号）。

        只给界面做 **placeholder / 提示**用；真正落库时
        :meth:`create_task` 会用实际号重算一遍（见该方法的同名参数说明）。
        """
        return f"任务#{self._next_task_no()}"

    def _next_task_no(self) -> str:
        """下一个任务号：``max(索引里的号, 磁盘上的目录名, 水位) + 1``。

        三个来源都要看，少一个都会**回收号**：

        - 索引 ``tasks.json``：绝大多数情况；
        - 磁盘 ``tasks/`` 下的目录名：索引丢了/写坏了但目录还在时兜底；
        - **水位** ``task_no.json``：任务被**删掉**之后，前两个来源都已经不含
          那个号了，只有水位记得它被用过（用户 2026-10-16 的要求）。
        """
        numbers = []
        for task in self._load_tasks_index():
            tid = str(task.get("id", ""))
            if tid.isdigit():
                numbers.append(int(tid))
        tasks_root = self.root / "tasks"
        if tasks_root.exists():
            for entry in tasks_root.iterdir():
                if entry.is_dir() and entry.name.isdigit():
                    numbers.append(int(entry.name))
        numbers.append(self._read_max_allocated())
        return f"{max(numbers, default=0) + 1:04d}"

    def find_tasks(self, source_hash: str) -> list[dict]:
        """按源文件指纹查重，返回全部命中的任务记录（可能多条）。"""
        return [
            t for t in self._load_tasks_index() if t.get("source_hash") == source_hash
        ]

    def list_tasks(self) -> list[dict]:
        """全部任务，按 updated_at 倒序（最近改动的排在前面）。"""
        return sorted(
            self._load_tasks_index(), key=lambda t: t.get("updated_at", 0), reverse=True
        )

    def get_task(self, task_id: str) -> dict | None:
        """按任务号取任务记录；不存在返回 None。"""
        for task in self._load_tasks_index():
            if task.get("id") == task_id:
                return task
        return None

    def _allocate_task_dir(self) -> tuple[str, Path]:
        """原子占号：分配一个空闲任务号并**建出任务目录**。

        ⚠️ **取号靠"目录创建的原子性"，不靠"先查后建"**（2026-09-26 审计）：
        单例守卫是**按构建目录**判定的，开发版与安装版会同时运行、共用同一个
        数据目录（`desktop/single_instance.py` 明说了）。两个进程会算出同一个
        `_next_task_no()`、同时通过"号没被占用"的检查 → 拿到同一个任务号、
        写同一个目录、索引里互相覆盖（一个任务凭空消失）。
        `mkdir(exist_ok=False)` 在文件系统层是原子的：抢不到就顺延取号。

        返回 ``(task_id, task_dir)``；占住号的同时抬水位
        （:meth:`_bump_max_allocated`：此后哪怕任务马上被删，号也不回收）。
        """
        base_no = int(self._next_task_no())
        task_dir: Path | None = None
        task_id = ""
        for offset in range(400):
            task_id = f"{base_no + offset:04d}"
            candidate = self.task_dir(task_id)
            try:
                # 原子占号：目录已存在说明别人（或旧数据）占了 → 顺延
                candidate.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                continue
            task_dir = candidate
            break
        if task_dir is None:
            raise RuntimeError("无法分配到空闲的任务号（连续 400 个都被占用）")
        self._bump_max_allocated(int(task_id))
        return task_id, task_dir

    def create_task(
        self,
        source_path: Path | str | None,
        source_hash: str,
        name: str = "",
        duplicate_confirmed: bool = False,
        flow: FlowDefinition | None = None,
        flow_layout: FlowLayout | None = None,
        diagram=None,
        template_flow=None,
    ) -> str:
        """
        新建任务并返回任务号（四位零填充）。

        任务号取当前最大号 +1，同时参考索引与磁盘目录；若两者不一致导致号被
        占用则继续顺延。创建时会预建 stages/runs/thumbnails/source
        子目录，但不复制源文件（由 copy_source_to_task 负责）。

        ``diagram`` 是**自定义流程图**（创建任务页传进来，见 ``docs/tasks/bpm.md``）：
        给了就把本任务自己的 ``flow.bpmn`` 写成这张图（节点类型 + 坐标 + 折点）。
        不给就**字节拷贝**默认模板 ``task_default.bpmn``——默认流程的真源是那个
        文件，不是代码（见 bpm.md「铁律」）。

        ⚠️ ``flow`` / ``flow_layout`` 是**旧模型**（``FlowDefinition``）的入口，
        只为兼容旧调用方保留；**新的调用方一律走 ``diagram``**。给 ``flow`` 时
        会经 ``template_flow`` 落盘（那条路会丢掉 ``guji:port``，别用）。

        ⚠️ **取号靠"目录创建的原子性"，不靠"先查后建"**（2026-09-26 审计）：
        单例守卫是**按构建目录**判定的，开发版与安装版会同时运行、共用同一个
        数据目录（`desktop/single_instance.py` 明说了）。两个进程会算出同一个
        `_next_task_no()`、同时通过"号没被占用"的检查 → 拿到同一个任务号、
        写同一个目录、索引里互相覆盖（一个任务凭空消失）。
        `mkdir(exist_ok=False)` 在文件系统层是原子的：抢不到就顺延取号。

        **源文件与任务名都可以不给**（用户 2026-10-06：「PDF 输入不是必须的」
        ＋「任务名称可以有默认的」）：

        - ``source_path`` 传 ``None``/空 ⇒ 索引里的 ``source_path`` 存空串。
          详情页据此显示「尚未选择 PDF」并给出补选入口，而不是弹「PDF 缺失」
          的错误框——那是「文件丢了」，与「还没选」完全是两回事。
        - ``name`` 传空 ⇒ 用 :meth:`default_task_name` 的格式，序号取**这里
          实际分配到的** ``task_id``（不是 ``next_task_no()`` 的预测值：占号
          可能顺延，用预测值会让「任务#0008」落在 0009 号任务上）。
        """
        now = time.time()
        task_id, task_dir = self._allocate_task_dir()

        for sub in ("stages", "runs", "thumbnails/source"):
            (task_dir / sub).mkdir(parents=True, exist_ok=True)

        # 把**本任务自己的流程图**落成 flow.bpmn（BPM 驱动的载体）。
        #
        # ⚠️ 2026-10-05 第二轮：**bpmn 文件是真源**，所以优先写调用方给的
        # ``diagram``（整张图：节点类型 + 坐标 + 折点）。只有没给图时才回落到
        # "从 ports 派生一份默认流程"的老路径（供 CLI 等旧调用方使用）。
        # 写失败不拖死建任务——读取端对缺失/坏文件回落默认模板。
        try:
            if diagram is not None:
                diagram.save(default_flow_path(task_dir))
            elif template_flow is not None:
                template_flow.save(default_flow_path(task_dir))
            elif flow is not None:
                # 旧调用方兼容：FlowDefinition 自己能序列化，只是会丢
                # ``guji:port``（新调用方请走 diagram / 模板字节拷贝）。
                flow.save(default_flow_path(task_dir), flow_layout)
            else:
                # ⚠️ 没给图就**原样拷贝默认模板文件**（不是重新序列化）：
                # 模板才是真源，而 `FlowDiagram` 不建模连线上的端口标记
                # （``guji:port``）——过一次它的 to_xml 会把端口信息抹掉，
                # 运行时按端口取产物就全成了默认端口。**字节拷贝**保真。
                from desktop.steps.scheduler import default_template_path

                template = default_template_path()
                if template.is_file():
                    copy_file_atomic(template, default_flow_path(task_dir))
                else:
                    # 🗑 模板文件也缺 ⇒ **不写** flow.bpmn。此前这里会拿
                    # `FlowDefinition.default()`（从 ports 边表**派生**的第三份
                    # 默认流程）序列化一份——那正是"代码设计默认流程"，与
                    # 「默认流程 = task_default.bpmn」的铁律冲突。留空文件时
                    # 读取端会回落 `load_default_diagram()`（同样是空图）并
                    # 走降级告警，比悄悄换一份流程更诚实。
                    pass
        except OSError as exc:
            # ⚠️ 别再静默 ``pass``：写盘失败意味着这个任务**永远没有**自己的
            #    流程图，之后每次读都回落默认流程——用户看到的是"我编的流程
            #    莫名其妙变回默认的"，而且没有任何线索。至少留一条日志。
            self._log_flow_write_error(task_id, exc)

        tasks = self._load_tasks_index()
        # ⚠️ 源文件可缺省（用户 2026-10-06「PDF 输入不是必须的」）：存空串，
        #    **不要**存 "." 或 "None" —— 那些是假路径，详情页会拿它去
        #    exists() 判断，白忙一场还给出误导性的提示文案。
        source_text = ""
        if source_path is not None:
            text = str(source_path).strip()
            #⚠️ Path("") 是 "."（当前目录），必须显式挡掉，否则"没给文件"
            #    会被记成"源文件是当前目录"。
            if text and text != ".":
                source_text = text
        # ⚠️ 名字可缺省：留空 ⇒ 「任务#<实际号>」。序号必须用**这里**的
        #    task_id，不能用 next_task_no() 的预测值（占号可能顺延）。
        clean_name = str(name or "").strip()
        if not clean_name:
            clean_name = f"任务#{task_id}"
        tasks.append(
            {
                "id": task_id,
                "name": clean_name,
                "source_path": source_text,
                "source_hash": source_hash,
                "status": "draft",
                "created_at": now,
                "updated_at": now,
                "duplicate_confirmed": int(bool(duplicate_confirmed)),
            }
        )
        self._save_tasks_index(tasks)
        return task_id

    def create_aggregate_task(
        self,
        members: list[str],
        member_stage: str = "",
        name: str = "",
        diagram=None,
        member_stages: list[str] | None = None,
    ) -> str:
        """新建**聚合任务**并返回任务号（四位零填充）。

        聚合任务（用户 2026-11-17）：选几个**已有任务**在各自节点上的产物
        作输入（顺序有意义，决定合并页序）。与 :meth:`create_task` 的差别：

        - **不吃源文件**：索引里 ``source_path`` 存空串（详情页按"尚未选择
          PDF"处理）。运行期的输入是成员任务的产物——创建之后由
          :mod:`desktop.services.aggregate_ingest` 在后台按成员顺序汇集进来
          （输入落到入口目录、产出落到同一步骤的产物目录，起点记为已完成）；
        - 索引多四个字段：``kind="aggregate"``（列表加标记、弹窗选择器
          排除聚合任务嵌套聚合）、``members``（成员任务号，**按用户排序**）、
          ``member_stages``（与 members 对齐的节点 key 清单；界面 2026-11-17
          本轮改回**全体共用一个起始节点**，所以创建页传来的值都相同，
          字段形状保持不变——老任务里仍可能逐成员不同）、``member_stage``
          （成员节点里**拓扑序最早**的那个——派生流程从它开始，"前面的丢弃，
          后面的接上"）；
        - ``flow.bpmn`` **永远不是**默认模板的字节拷贝：给了 ``diagram``
          （用户在创建面板里编辑过的派生图）就落它；没给就落
          :func:`desktop.steps.aggregate.derive_aggregate_diagram` 派生的图
          ——模板里有 extract，对聚合任务语义不对。

        ``members`` 里出现不存在的任务号时抛 ``ValueError``（聚合任务指向
        一个不存在的任务等于埋雷，宁可当场炸在创建时）。``member_stages``
        不给（旧口径）⇒ 全体成员都用 ``member_stage``；给了 ⇒ 按清单逐个
        校验（长度必须与成员数一致、每个都在允许清单里），``member_stage``
        由清单**重新推导**（取最早），传什么都以推导为准。
        """
        from desktop.steps.aggregate import (
            AGGREGATE_START_STAGES,
            derive_aggregate_diagram,
            earliest_aggregate_stage,
        )

        clean_members = [str(m).strip() for m in (members or []) if str(m).strip()]
        if not clean_members:
            raise ValueError("聚合任务至少要选一个成员任务")
        unknown = [m for m in clean_members if self.get_task(m) is None]
        if unknown:
            raise ValueError(f"成员任务不存在：{'、'.join(unknown)}")
        if member_stages is None:
            if member_stage not in AGGREGATE_START_STAGES:
                raise ValueError(f"非法的聚合起始节点：{member_stage}")
            clean_stages = [member_stage] * len(clean_members)
        else:
            clean_stages = [str(s).strip() for s in member_stages]
            if len(clean_stages) != len(clean_members):
                raise ValueError(
                    f"成员节点数（{len(clean_stages)}）与成员数"
                    f"（{len(clean_members)}）不一致"
                )
            bad = sorted({s for s in clean_stages if s not in AGGREGATE_START_STAGES})
            if bad:
                raise ValueError(f"非法的成员起始节点：{'、'.join(bad)}")
            # 单一事实：落库的 member_stage 恒等于成员节点里最早的
            member_stage = earliest_aggregate_stage(clean_stages)

        now = time.time()
        task_id, task_dir = self._allocate_task_dir()

        for sub in ("stages", "runs", "thumbnails/source"):
            (task_dir / sub).mkdir(parents=True, exist_ok=True)

        # 聚合任务没有源 PDF，thumbnails/source 是空目录占位（与空壳任务
        # 同一待遇）；flow.bpmn 落派生图/用户编辑过的图（不走字节拷贝）。
        flow = diagram if diagram is not None else derive_aggregate_diagram(member_stage)
        if flow is not None and flow.nodes:
            try:
                flow.save(default_flow_path(task_dir))
            except OSError as exc:
                # 同 create_task：写失败不拖死建任务，但至少留一条日志
                self._log_flow_write_error(task_id, exc)

        tasks = self._load_tasks_index()
        clean_name = str(name or "").strip()
        if not clean_name:
            clean_name = f"任务#{task_id}"
        tasks.append(
            {
                "id": task_id,
                "name": clean_name,
                "source_path": "",
                "source_hash": "",
                "status": "draft",
                "created_at": now,
                "updated_at": now,
                "kind": "aggregate",
                "members": clean_members,
                "member_stage": member_stage,
                "member_stages": clean_stages,
            }
        )
        self._save_tasks_index(tasks)
        return task_id

    def set_aggregate_start(self, task_id: str, stage: str) -> bool:
        """改**已建好的**聚合任务的起始节点（用户 2026-11-18）。

        用户原话：「起始节点可以切换变更，如果变更了保存流程的时候，提示起始
        节点丢失，聚合任务之前历史处理数据都丢失」。所以这里只管改 record
        里的 ``member_stage`` / ``member_stages``（全体成员同一口径，与创建时
        一致）；**作废旧数据、按新起点重新汇集**由调用方（流程页 → 详情页
        ``restart_aggregate_ingest``）负责——store 不碰磁盘产物。

        ⚠️ ``member_stage`` 是汇集器唯一认的起点（``aggregate_ingest.plan_ingest``
        读它），改完必须与**新流程图**对得上：调用方要同时保存按新起点派生的
        流程，否则详情页的起点节点找不到。

        任务不存在/不是聚合任务/节点不合法 ⇒ 返回 ``False``。
        """
        from desktop.steps.aggregate import AGGREGATE_START_STAGES

        key = str(stage or "").strip()
        if key not in AGGREGATE_START_STAGES:
            return False
        tasks = self._load_tasks_index()
        for record in tasks:
            if str(record.get("id") or "") != str(task_id):
                continue
            if record.get("kind") != "aggregate":
                return False
            members = [str(m) for m in (record.get("members") or [])]
            record["member_stage"] = key
            # 界面 2026-11-17 起全体共用一个起点，形状保持不变（逐成员节点）
            record["member_stages"] = [key] * len(members)
            record["updated_at"] = time.time()
            self._save_tasks_index(tasks)
            return True
        return False

    def set_task_source(self, task_id: str, source_path: Path | str,
                        source_hash: str | None = None) -> bool:
        """给**已建好但还没有 PDF** 的任务补上源文件（用户 2026-10-06）。

        创建任务时 PDF 非必需，所以会出现"空壳任务"；补选入口（详情页页头
        的 PDF 按钮）走这里：改索引里的 ``source_path``/``source_hash``
        并把文件复制进任务目录。**只改索引不复制**不行——详情页与各阶段
        一律读任务目录里的副本（见 :meth:`source_copy_path`）。

        ``source_hash`` 给了才写指纹（调用方在后台算好了；store 不引哈希
        实现，详见类文档的分工）。⚠️ **指纹必须写进去**：它是"这个 PDF 是不是
        已经导入过"的唯一判据（``find_tasks``），不写的话换过一次源之后
        判重立刻失效。

        返回是否真的改了（任务不存在/路径没给/文件不在/复制失败返回 ``False``）。
        """
        record = self.get_task(task_id)
        if record is None:
            return False
        text = str(source_path or "").strip()
        if not text or text == ".":
            return False
        source = Path(text)
        if not source.is_file():
            return False
        # 复制失败就别改索引：否则索引指向一个任务目录里并不存在的文件，
        # 详情页会一直报"PDF 缺失"，而用户明明选得到文件。
        try:
            self.copy_source_to_task(task_id, source)
        except OSError:
            return False
        tasks = self._load_tasks_index()
        for task in tasks:
            if task.get("id") == task_id:
                task["source_path"] = str(source)
                if source_hash is not None:
                    task["source_hash"] = str(source_hash)
                task["updated_at"] = time.time()
                break
        self._save_tasks_index(tasks)
        return True

    def rename_task(self, task_id: str, name: str) -> bool:
        """改任务名称（用户 2026-10-06："任务名非必需，可随时修改"）。

        返回是否真的改了（名称没变/任务不存在返回 ``False``，调用方据此
        决定要不要提示/刷新）。空名字的回落是**两级**（用户 2026-10-06
        「没填写可以用上传的 pdf 名称」＋「名称可以有默认」）：

        1. 源文件名（``source_path`` 的 stem）——有 PDF 时用它的名字；
        2. 都没有 ⇒ ``任务#<任务号>``，与 :meth:`create_task` 的默认口径
           一致，不留空名字在列表里（空名会让列表那一格空白，扫不出来）。

        ⚠️ 走 :meth:`_save_tasks_index`（临时文件 + ``os.replace``），别直接
        写 ``tasks.json``：那是列表页每次刷新都要读的索引，中途被读会拿到
        半截内容。
        """
        clean = str(name or "").strip()
        record = self.get_task(task_id)
        if record is None:
            return False
        if not clean:
            # ⚠️ source_path 可能为空串（PDF 非必需）——``Path("")`` 是"."，
            #    它的 stem 是空串，正好落到下一级回落，不会写出"."当名字。
            clean = (Path(str(record.get("source_path") or "")).stem
                     or f"任务#{task_id}")
        if record.get("name") == clean:
            return False
        tasks = self._load_tasks_index()
        for task in tasks:
            if task.get("id") == task_id:
                task["name"] = clean
                task["updated_at"] = time.time()
                break
        self._save_tasks_index(tasks)
        return True

    def update_task(self, task_id: str, status: str) -> None:
        """更新任务状态与 updated_at；任务号不存在时静默忽略。"""
        tasks = self._load_tasks_index()
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = status
                task["updated_at"] = time.time()
                break
        self._save_tasks_index(tasks)

    def delete_task(self, task_id: str) -> bool:
        """删除任务及其中间产物，返回是否真的删掉。

        ⚠️ 顺序是「**先删目录、成功才删索引**」：反过来的话目录一旦被占用
        没删掉、索引却先没了，任务目录就变成没人认领的孤儿，用户还看不见。

        ⚠️ Windows 上 PDF 被后台渲染线程打开时 ``rmtree`` 抛 PermissionError，
        原先 ``ignore_errors=True`` 会让它**静默残留**——列表里显示已删除，
        磁盘上目录还在。这里重试若干次再判定失败，失败时保留任务让用户重试。

        ⚠️ 删除**不回收任务号**（用户 2026-10-16：「任务序号保留占用」）：删掉
        0020 之后下一个新建的是 0021。所以这里在抹掉记录之前先把水位抬到该号
        （见 :meth:`_bump_max_allocated`）——**光靠索引与目录做不到**，删除正是
        把这两个来源同时抹掉的那个动作。
        """
        task_dir = self.task_dir(task_id)
        if task_dir.exists() and not self._rmtree_with_retry(task_dir):
            return False
        # ⚠️ 放在成功判定之后：删不掉时任务还在索引里，号本来就还占着，
        #    不必（也不该）在失败分支上动水位。
        if self._TASK_ID_RE.match(str(task_id)):
            self._bump_max_allocated(int(task_id))
        tasks = [t for t in self._load_tasks_index() if t.get("id") != task_id]
        self._save_tasks_index(tasks)
        return True

    @staticmethod
    def _rmtree_with_retry(path: Path, tries: int = 8, delay: float = 0.06) -> bool:
        """反复尝试删除目录；文件被短暂占用（后台渲染）时等一会儿再试。"""
        for attempt in range(tries):
            try:
                shutil.rmtree(path)
                return True
            except OSError:
                if attempt == tries - 1:
                    return False
                time.sleep(delay)
        return False
