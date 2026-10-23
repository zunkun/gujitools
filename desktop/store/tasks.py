# -*- coding: utf-8 -*-
"""任务索引（tasks.json）与任务目录布局。"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, cast

from desktop.steps import ports
from desktop.steps.flow import (
    FlowDefinition,
    FlowLayout,
    StageSlot,
    default_flow_path,
)
from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS, StepSpec, spec_by_key
from desktop.store.json_io import (
    owner_path, read_json, resolve_scoped_path, write_json, write_owner,
)
from desktop.utils.files import copy_file_atomic

#: 默认流程的四个步骤（顺序即执行顺序）。
#:
#: ⚠️ **这里不再是独立的一份清单**：它是 ``desktop.steps.spec.SPECS`` 里
#: ``role == "stage"`` 的派生结果。加/删一步只需改 spec，本文件自动跟着变。
#: （以前这里是第二份硬编码清单，加一步要改两处，还容易漏。）
STAGES = FLOW_STAGES

# ⚠️ 这些是**界面文案**（步骤条/面板标题/toast/日志共用一份）：有中文就不再附
# 英文键名 —— 用户口径「四个步骤有中文，英文就不要出现」。
#: ⚠️ **真源是 :func:`desktop.steps.ports.stage_label`**，本表只是它的派生
#: （多带 ``detect_submit``：它不是独立步骤，却是真实的运行阶段，worker 会跑
#: 它、进度与日志都要有名字）。别在这里另写一句中文
#: ——BPMN 流程图上的节点名走的是同一个函数，两边不一致就会出现"图上两个
#: 『检测文本框』"。
STAGE_LABELS = {key: ports.stage_label(key) for key in STAGES}
STAGE_LABELS["detect_submit"] = ports.stage_label("detect_submit")

# 列表里的阶段短名（步骤条/表格空间有限，用 2~3 字表达）
STAGE_SHORT = {key: cast(StepSpec, spec_by_key(key)).short_name() for key in STAGES}

# ------------------------------------------------------------ 流程条的可选节点
#: 「图片拼版」**伪步骤**：流程条上的虚线可选节点，位于第三步（图片去底色）
#: 与第四步（PDF排版）之间，图上画了就会出现。
#: 用户可以选择它（启用）也可以不选择；节点详情当前为占位（不参与任何执行
#: 链路，STAGES/runs.json/阶段面板等机制一律不感知它）。
#:
#: ⚠️ 它**有自己的独立模块页**（``desktop/modules/imposition``）——"进不进流程"
#: 和"有没有独立功能"是两件事，这也是 ``StepSpec.role`` 要分
#: ``stage`` / ``optional`` 的原因。
IMPOSITION_STAGE = OPTIONAL_STEPS[0]
IMPOSITION_LABEL = cast(StepSpec, spec_by_key(IMPOSITION_STAGE)).stage_name()
#: 🗑 **已删**：``IMPOSITION_INDEX``（= ``len(STAGES)``，即"拼版占第 5 位"）。
#:
#: 它是 BPM 改造**之前**的固定顺序口径：BPM 化后拼版插在哪一格由流程图决定
#: （``FlowDiagram.optional_after`` / 槽位表的 ``bar_index``），这个常量既没人
#: 用（``page.py`` 只 import 它、没有任何实际引用）又和真源矛盾——留在那儿
#: 就是给下一个人留一个"看起来能用"的默认流程假设。查格序一律走
#: ``TaskDetailPage.bar_index_of_step(IMPOSITION_STAGE)``。

# 「图片拼版」**不是 STAGES 里的一步**（它是可选节点），但任务列表的「子任务
# 状态」胶囊会按任务详情里的启用情况把它插进去，所以上面两张文案表都得有它。
# ⚠️ 取值仍走 ``stage_name()`` / ``short_name()``，不另写一份中文。
STAGE_LABELS[IMPOSITION_STAGE] = IMPOSITION_LABEL
STAGE_SHORT[IMPOSITION_STAGE] = cast(StepSpec, spec_by_key(IMPOSITION_STAGE)).short_name()

#: 运行阶段 → 它归属的**界面步骤**（值取 STAGES 里的一项）。
#:
#: ⚠️ 「提交本次任务」（detect_submit）不是独立步骤，而是第二步 detect 面板上的
#: 动作：它的进度必须显示在第二步。有了这张表，界面才谈得上"只有当前这一步的
#: 进度才上屏"（详见 desktop/pages/taskdetail/runner.py::_progress_belongs_here）。
STAGE_STEP = ports.STAGE_STEPS
"""运行阶段 → 界面步骤（**别名** ``ports.STAGE_STEPS``，不是第二份）。

⚠️ 此前这里是一份手写字典，与 :data:`desktop.steps.ports.STAGE_STEPS` 同源却
不同步：漏了 ``imposition``、少了一个键就静默靠 ``.get(s, s)`` 兜底。今天两份
逐值相同只是巧合——`ports` 那份是真源（``bpmn_diagram`` / ``flow`` / ``tasks``
都用它），store 属于下层却反向持有一份，属于层次倒挂。现在直接别名，加/改一步
只改 :data:`desktop.steps.spec.SPECS` 一处。
"""


class TaskMixin:
    """任务索引读写与任务目录/阶段输出目录的路径推导。"""

    root: Path

    if TYPE_CHECKING:
        # 宿主 TaskStore（或同级 Mixin）提供：只做类型声明，运行时零副作用。
        drafts_dir: Callable[[str], Path]
        # 仅类型检查期导入：流程图模块在热路径上是惰性导入的（见 task_diagram）
        from desktop.steps.bpmn_diagram import FlowDiagram

    #: ``任务号 → 流程降级原因``（见 :meth:`task_diagram` / :meth:`flow_degraded_reason`）。
    #:
    #: ⚠️ **必须是每实例一份**，不能放类属性当默认值：键是任务号，而自测里
    #: 一堆临时 store 都用 ``0001`` 这类同名任务 ⇒ 类属性会让 A 任务降级的
    #: 原因"传染"给 B 任务。惰性建在实例上（见 :meth:`_degraded_map`）。
    _flow_degraded: dict[str, str] | None = None

    #: ``任务号 → ((mtime_ns, size), FlowDiagram)``：``flow.bpmn`` 的解析缓存。
    #:
    #: ⚠️ **必须有**：详情页一次刷新会调 :meth:`task_diagram` 上千次（阶段
    #: 槽位、按节点寻址、端口供给、逐页取框都会来问），每次都完整解析 XML
    #: 就是用户实测的「进详情要等 3~5 秒」。键带 **mtime_ns + size**，任何
    #: 落盘（:meth:`save_task_diagram` 会显式作废）都会让旧条目自然失效。
    #: 同样必须**每实例一份**（理由同上一条：自测里同名任务号会串味）。
    _diagram_cache: dict[str, "tuple[tuple[int, int], FlowDiagram]"] | None = None

    #: ``(任务号, 步骤) → ((mtime_ns, size), 开关值)``：``step_enabled`` 的读盘缓存。
    #:
    #: ⚠️ 为什么值得缓存：``imposition_effective()`` 会经 ``_boxes_read_path``
    #: 被**每页**问一次（第三步刷新条目 110 页 = 110 次），而它最终落到
    #: ``step_enabled`` 的一次 JSON 读盘。开关文件只在用户拨开关时才变，
    #: 键带文件指纹即可保证"拨了立刻生效"；同样是**每实例一份**。
    _step_flags_cache: dict[tuple[str, str], tuple[tuple[int, int], bool]] | None = None

    def _degraded_map(self) -> dict[str, str]:
        """本实例的降级原因表（惰性建，避免覆盖类属性默认值）。"""
        if self._flow_degraded is None:
            self._flow_degraded = {}
        return self._flow_degraded

    def _step_flags_map(self) -> dict[tuple[str, str], tuple[tuple[int, int], bool]]:
        """本实例的可选步骤开关读盘缓存（惰性建）。"""
        if self._step_flags_cache is None:
            self._step_flags_cache = {}
        return self._step_flags_cache

    def _diagram_map(self) -> dict[str, "tuple[tuple[int, int], FlowDiagram]"]:
        """本实例的流程图解析缓存（惰性建，避免覆盖类属性默认值）。"""
        if self._diagram_cache is None:
            self._diagram_cache = {}
        return self._diagram_cache

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
        # 号已占住（目录建成了）⇒ 立刻抬水位：此后**哪怕这个任务马上被删**，
        # 这个号也不会被回收（用户 2026-10-16，见 _bump_max_allocated）。
        self._bump_max_allocated(int(task_id))

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

    # ---------- 任务目录布局 ----------
    #: 合法任务号的形状：四位以上纯数字（由 `_next_task_no` 生成，如 0007）。
    _TASK_ID_RE = re.compile(r"^[0-9]{4,}$")

    def task_dir(self, task_id: str) -> Path:
        """任务根目录：tasks/<任务号>。

        ⚠️ **必须校验形状**（2026-09-26 审计）：`task_id` 会被直接拼进路径，而
        `delete_task` 对它做 `rmtree`。`tasks.json` 就在用户的文档目录下、可被
        外部编辑或别的工具写坏，一旦出现 `"id": "..\\..\\somewhere"` 就会
        **越界删除任务目录之外的东西**。这里只认 `create_task` 生成的形状。
        """
        if not isinstance(task_id, str) or not self._TASK_ID_RE.match(task_id):
            raise ValueError(
                f"任务号形状非法：{task_id!r}（应为四位以上数字，如 0007）"
            )
        return self.root / "tasks" / task_id

    def stage_dir(self, task_id: str, stage: str) -> Path:
        """某阶段的输出目录：tasks/<任务号>/stages/<阶段>。"""
        return self.task_dir(task_id) / "stages" / stage

    # ---------- 产物落点（由 desktop.steps.ports 派生）----------
    def artifact(self, task_id: str, stage: str, port: str = "pages") -> Path:
        """某阶段某端口的产物绝对路径（**落点的唯一入口**）。

        ⚠️ 这四个 ``*_output_dir`` 方法以前各自写死了路径，是"加一步要改四处"
        的根源；现在它们都转调到这里，而落点表
        （:data:`desktop.steps.ports.STAGE_LOCATIONS`）是唯一事实来源。
        加一步 = 加一行表，不用动 store。
        """
        path = ports.artifact_path(self.task_dir(task_id), stage, port)
        if path is None:
            raise KeyError(f"阶段 {stage!r} 没有登记端口 {port!r} 的落点")
        return path

    def extract_output_dir(self, task_id: str) -> Path:
        """提取图片直接位于 stages/extract（无 PDF 名/嵌套子目录）。"""
        return self.artifact(task_id, "extract", "pages")

    def rembg_output_dir(self, task_id: str) -> Path:
        """步骤三成品图片目录（「执行去底色」产出，print 阶段从此取图）。"""
        return self.artifact(task_id, "rembg", "pages")

    def rembg_offsets_path(self, task_id: str, node_id: str | None = None,
                           primary_id: str | None = None) -> Path:
        """**逐张图片**阈值偏移的存储文件（黑名单法，只记非 0 的图片）。

        主节点沿用 ``rembg_offsets.json``；同一步骤的副本节点落
        ``rembg_offsets~<节点>.json``（与 ``boxes`` / ``pages`` 同一套命名）。
        """
        from desktop.steps import ports

        if node_id:
            items = self.task_diagram(task_id).node_ids_of("rembg")
            primary_id = primary_id or (items[0] if items else None)
        name = ports.scoped_name("rembg_offsets.json", node_id, primary_id)
        return resolve_scoped_path(self.task_dir(task_id) / name, node_id)

    def load_rembg_offsets(self, task_id: str, node_id: str | None = None,
                           primary_id: str | None = None) -> dict[str, int]:
        """读逐张偏移表 ``{页名: offset}``（只含非 0 项；坏文件当空表）。"""
        path = self.rembg_offsets_path(task_id, node_id, primary_id)
        data = read_json(path, {})
        if not isinstance(data, dict):
            return {}
        out: dict[str, int] = {}
        for key, value in data.items():
            try:
                offset = int(value)
            except (TypeError, ValueError):
                continue
            if offset:
                out[str(key)] = offset
        return out

    def rembg_offset(self, task_id: str, image_key: str,
                     node_id: str | None = None,
                     primary_id: str | None = None) -> int:
        """某张图片的阈值偏移（没记录过 = 0）。"""
        return int(self.load_rembg_offsets(
            task_id, node_id, primary_id
        ).get(str(image_key), 0))

    def save_rembg_offset(self, task_id: str, image_key: str, offset: int,
                          node_id: str | None = None,
                          primary_id: str | None = None) -> None:
        """记录某张图片的阈值偏移；**offset=0 就删掉这一项**（黑名单法）。

        ⚠️ 只在用户**确实改过**这张图时调用；整表很小，读改写即可，不要为它
        再造缓存。
        """
        path = self.rembg_offsets_path(task_id, node_id, primary_id)
        data = self.load_rembg_offsets(task_id, node_id, primary_id)
        image_key = str(image_key)
        value = int(offset)
        if value:
            data[image_key] = value
        else:
            data.pop(image_key, None)
        if not data:
            try:
                path.unlink(missing_ok=True)
                owner_path(path).unlink(missing_ok=True)
            except OSError:
                pass
            return
        if self.task_dir(task_id).exists():
            write_json(path, data)
            write_owner(path, node_id or primary_id)

    def imposition_output_dir(self, task_id: str) -> Path:
        """「图片拼版」产出的成品拼版页图目录（列表顺序即页序）。

        拼版节点**生效**时（选择态为真且有拼版页），第四步「PDF排版」与它的
        待打印列表一律从这里取图；否则仍从 ``rembg_output_dir`` 取。
        """
        return self.artifact(task_id, "imposition", "pages")

    def print_output_pdf(self, task_id: str) -> Path:
        """print 阶段产物 print.pdf 的完整路径。"""
        return self.artifact(task_id, "print", "pdf")

    def task_diagram(self, task_id: str):
        """本任务的**流程图**（``FlowDiagram``：节点类型 + 坐标 + 折点）。

        ⚠️ 与 :mod:`desktop.steps.flow`（``FlowDefinition``）的区别：那个是**旧模型**
        （阶段序列 + 端口边表），已不再被 store 暴露给界面——页面渲染、运行
        顺序、供给方、就绪判据全部走这张图。两者读的
        是同一个 ``flow.bpmn``——文件是唯一真源。

        读不到 / 文件坏一律**回落默认模板**：界面宁可显示默认流程，也不能
        整个详情页打不开。⚠️ 但**回落必须是可见的**——见
        :meth:`flow_degraded_reason`。

        ⚠️ **"解析得动但一个可执行步骤都认不出"也算坏**：那种图会让
        :meth:`stage_supplier` 的"在流程里"集合变成空集，于是**每个端口都
        解析成 None**（现象是"每一步都说找不到输入"，而流程看起来是有节点的，
        极难查）。所以这里判的是"有没有能跑的步骤"，不是"有没有节点"。

        ⚠️ 第三条最隐蔽：用户在 bpmn.io 里把「图片去底色」改名成「AI 抠图」
        ——一次完全合法的编辑——所有 ``task`` 节点的名字都认不出来，
        ``stage_order()`` 就是空，整张自定义图被**静默**判成"坏"并换回默认
        流程。所以回落一定要配一条提示，见 ``flow_degraded_reason``。
        """
        from desktop.steps.bpmn_diagram import FlowDiagram
        from desktop.steps.scheduler import load_default_diagram

        path = default_flow_path(self.task_dir(task_id))
        # ⚠️ 缓存键必须带 **mtime_ns + size**：这个方法是详情页最热的调用
        #    （一次进页面 2000+ 次），但流程文件随时可能被编辑器重写。只按
        #    任务号缓存会让"改了流程没反应"；带上文件指纹则任何落盘都自然
        #    失效，不必依赖每个写入点记得来作废。
        key: tuple[int, int] | None
        try:
            stat = path.stat()
            key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            key = None
        cache = self._diagram_map()
        if key is not None:
            cached = cache.get(task_id)
            if cached is not None and cached[0] == key:
                self._degraded_map().pop(task_id, None)
                return cached[1]
        reason = ""
        if path.is_file():
            try:
                diagram = FlowDiagram.load(path)
                if diagram.stage_order():
                    self._degraded_map().pop(task_id, None)
                    if key is not None:
                        cache[task_id] = (key, diagram)
                    return diagram
                reason = (
                    f"{path.name} 里的步骤一个都认不出来"
                    "（节点名对不上任何已有步骤——阶段是按**节点名**接回的，"
                    "改名后要改回「提取图片 / 检测文本框 / 图片去底色 / "
                    "图片拼版 / PDF排版」这类名字）"
                )
            except (ValueError, OSError) as exc:
                reason = f"{path.name} 解析失败：{exc}"
        else:
            reason = f"本任务目录下没有 {path.name}"
        # 降级路径**不进缓存**：坏文件被修好后 mtime 会变，但这里没有可信的
        # 键；默认模板本身很小，且只在真的降级时才解析。
        cache.pop(task_id, None)
        self._degraded_map()[task_id] = reason
        fallback = load_default_diagram()
        if fallback.nodes:
            return fallback
        return FlowDiagram()

    def flow_degraded_reason(self, task_id: str) -> str:
        """本任务的流程图是不是**降级**了（读的是默认模板而非自己的图）。

        空串 = 正常。⚠️ 这是"自定义流程莫名其妙变回默认"这类报障**唯一**的
        线索来源：``task_diagram`` 的回落必须配一条提示，否则用户看到的现象
        与"我没改过它"完全一样（用户 2026-10-06）。
        """
        return (self._flow_degraded or {}).get(task_id, "")

    @staticmethod
    def _log_flow_write_error(task_id: str, exc: OSError) -> None:
        """建任务时写 ``flow.bpmn`` 失败：留一条可见痕迹。

        ⚠️ 此前是 ``except OSError: pass``——任务照样建成，之后**每一次**读
        流程都回落默认模板。用户报"我编的流程变回默认了"时，没有任何线索。
        """
        import sys

        print(
            f"[store] 任务 {task_id} 写入 flow.bpmn 失败：{exc}。"
            "该任务将按默认流程显示，请检查目录权限。",
            file=sys.stderr,
        )

    def save_task_diagram(self, task_id: str, diagram) -> None:
        """把流程图写回 ``tasks/<任务号>/flow.bpmn``（原子写）。

        ⚠️ 只改**流程定义**，不碰任何产物。改完流程后已有产物是否还有效，是
        **界面该提示的事**，由调用方判断——store 只管存。

        ⚠️ 落盘后**只作废**解析缓存，不能拿传进来的这张图回填：调用方给的往往是
        编辑器手里的**在制品**（节点 ``stage`` 等派生字段可能是 None），而
        ``FlowDiagram.load`` 会按节点名把 ``stage`` 补出来——``stage_slots()``
        正是吃这个字段。回填未归一化的对象会让步骤条退化成"每格都是空步骤"
        （自测 last_stage 6b 当场红）。代价只是保存后多解析一次文件，保存本来
        就是低频操作。
        """
        path = default_flow_path(self.task_dir(task_id))
        diagram.save(path)
        self._diagram_map().pop(task_id, None)

    def task_slots(self, task_id: str) -> tuple[StageSlot, ...]:
        """本任务流程投影出的**界面槽位**（步骤条格子 + 两个栈的页号）。

        界面的步骤条与阶段寻址都走这里（``docs/tasks/bpm.md`` 的 M2），
        不再按``STAGES`` 四步硬索引——自定义流程换了顺序/增删了节点，
        步骤条与寻址一起跟着变。折叠规则见
        :meth:`desktop.steps.flow.FlowDefinition.stage_slots`。
        """
        # ⚠️ **走图模型，不走 FlowDefinition**：后者读不了 bpmn.io 的网关/
        # 自定义 id，解析失败会**静默回落默认流程**——那正是"无论选不选
        # 自定义，详情页永远显示 task_default.bpmn"的根因。
        return self.task_diagram(task_id).stage_slots()

    def task_stage_of(self, task_id: str, bar_index: int) -> str | None:
        """步骤条格序 → **运行阶段**（点节点后反查该跑/该显示什么）。

        返回 ``None`` 说明这一格在本流程里不存在（自定义流程删掉了它），
        调用方必须挡住而不是当成第一步。
        """
        diagram = self.task_diagram(task_id)
        step = diagram.step_at(bar_index)
        if step is None:
            return None
        slot = diagram.slot_of(step)
        return None if slot is None else slot.stage

    def stage_input(self, task_id: str, stage: str, port: str = "pages",
                    imposition_active: bool = False) -> Path | None:
        """按**本任务的流程定义**解析某阶段某端口的输入绝对路径。

        ⚠️ 这是 BPM 化的关键入口：调用方不再问"第三步的图片在哪"，而是问
        "这一步的 ``pages`` 输入在哪"——连线由任务的 ``flow.bpmn`` 决定
        （没有就用默认流程，与 :data:`desktop.steps.ports.SUPPLIERS` 逐边
        相等）。``imposition_active`` 对应那条唯一的**条件连线**（拼版生效
        时换上游），以条件名 ``"imposition"`` 传入解析上下文。

        ⚠️ **沿图回溯不出上游时回落到入口图片目录**（用户 2026-10-06：
        「如果某个节点作为第一个节点，一定要可以有输入可用」）。落点是
        :func:`desktop.steps.ports.task_input_dir`（``stages/input/``），
        界面的「插入图片」也写进那里（见 ``manifest.insert_pages``）。
        回落由 :func:`~desktop.steps.ports.resolve_input_with_entry` 统一做，
        **只对 ``pages`` 生效**——``boxes``/``pdf`` 没得回落。
        """
        supplier = self.stage_supplier(task_id, stage, port, imposition_active)
        return ports.resolve_input_with_entry(
            self.task_dir(task_id), stage, port, supplier
        )

    def task_input_dir(self, task_id: str) -> Path:
        """**流程入口图片**目录（``stages/input/``）。

        供"没有上游的步骤"当输入：用户往这里放图/从界面插图，第一个节点
        （例如自定义流程里的「检测文本框」）就拿它当pages 输入。落点由
        :data:`desktop.steps.ports.TASK_INPUT_LOCATION` 唯一声明。
        """
        return ports.task_input_dir(self.task_dir(task_id))

    def required_stage_inputs(self, task_id: str, stage: str,
                              imposition_active: bool = False) -> tuple[str, ...]:
        """本流程里这一步**真正要等就位**的输入端口。

        规则只在 :func:`desktop.steps.ports.stage_blocking_inputs` 一份（那里
        解释了为什么"声明的端口"不能直接当就绪判据：``pdf`` 由任务供给、
        ``boxes`` 在没有「检测文本框」的流程里压根没人产出）。

        :param imposition_active: 拼版开关的运行态（调用方传 effective）。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = self.scheduler_flags(task_id, imposition_active)
        active = Scheduler.from_diagram(diagram, flags).stages
        return ports.stage_blocking_inputs(diagram, stage, set(active))

    def stage_supplier(self, task_id: str, stage: str, port: str,
                       imposition_active: bool = False) -> str | None:
        """本任务里 ``(stage, port)`` 的**实际供给方**（运行时按图求解）。

        ⚠️ **这一步是"运行时跟着图走"的关键**：以前直接查代码里的端口级边表
        （``ports.SUPPLIERS``），一旦用户把流程改成不含某一步（例如去掉
        「图片去底色」），边表给的供给方就不在流程里了——按它取路径会指向
        **永远不会产生的文件**（现象是"PDF排版找不到输入"，而不是流程报错，
        极难查）。

        规则（先声明、后回退）：
        1. 取 ``ports`` 声明的供给方（``print/pages`` 走拼版开关那条特例）；
        2. 它**在本流程里**⇒ 就用它；
        3. 不在 ⇒ 沿图往前找**最近的、产出该端口的在流程阶段**
           （:meth:`FlowDiagram.nearest_producer`）。

        ⚠️ **"在流程里"要按"界面格子"判，不能按节点判**：
        ``detect_submit``（提交检测结果）是第二步内的**第二个动作**，用户画图
        时通常不会给它单独开一个节点（界面槽位也把它折回「检测文本框」那一格）。
        若按"图里有没有这个节点"判，就会认为它不在流程里，于是 ``rembg.pages``
        回退到 ``detect`` ——而 ``detect`` 只出坐标、没有裁好的图。
        所以判据是"它所属的**界面格**在不在流程里"（:data:`ports.STAGE_STEPS`
        给出 stage→step 的折叠关系）。
        ⚠️⚠️ **图优先，静态表兜底**（2026-10-06 掉头）。原先的规则是**反的**
        （"先静态声明、后沿图回退"），后果是 ``ports.SUPPLIERS``——一份**写死在
        代码里的默认流程连线**——在它给的供给方还留在流程里时**压过用户画的
        连线**。实测两条节点集合相同、连线不同的流程（默认的
        ``extract→detect→rembg→print`` 与用户自己连的 ``extract→print``），
        ``print`` 的取图目录**完全一样**——用户明确要求的连线被静默丢弃。
        这就是"自定义流程里总是冒出默认流程逻辑"的**病根**：BPM 化只覆盖了
        **顺序**，没覆盖**语义**。

        现在的规则：

        1. **图能给出唯一答案**（沿图可达的产出方恰好一个）⇒ **图说了算**；
        2. 图给不出、或给出**多个**（默认流程的「是否拼版」网关就是这种：沿图
           回溯 ``print`` 会同时看到「图片拼版」与「图片去底色」）⇒ 退回静态
           声明 + 条件开关（``ports.print_pages_supplier`` 建模的那一条）；
        3. 静态声明是**任务源**哨兵（``extract`` 的 ``pdf``）⇒ 直接返回，它
           本来就没有上游。

        ⚠️ 第2 条是**确定性**的要求，不是将就：网关分支要用"拼版开关"这个
        运行态来选，两条边在图上都是实线，靠遍历顺序选是随机的。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = self.scheduler_flags(task_id, imposition_active)
        active = set(Scheduler.from_diagram(diagram, flags).stages)
        # 本流程里"活着"的**界面格**（例如 detect_submit 与 detect 同属一格）
        live_steps = {ports.STAGE_STEPS.get(s, s) for s in active}

        def in_flow(name: str) -> bool:
            """该阶段（或它所属的那一格）在不在本流程里。"""
            if name in active:
                return True
            return ports.STAGE_STEPS.get(name, name) in live_steps

        declared = ports.supplier_of(stage, port)
        if stage == "print" and port == "pages":
            # 拼版生效时换上游（这是 ports 里唯一一条条件连线）
            declared = ports.print_pages_supplier(bool(imposition_active))
        if declared == ports.SUPPLY_TASK_SOURCE:
            return declared
        # ⚠️⚠️ **这一步压根不声明这个端口 ⇒ 没有这个输入**（返回 ``None``）。
        #    这一条必须在"图说了算"**之前**：``producers_of`` 只问"图上谁能产出
        #    它"，不问"这一步吃不吃它"——于是 ``print`` 明明不吃 ``boxes``，
        #    沿图回溯却能撞上 ``detect`` 并给出 ``boxes.json``（自测抓到）。
        #    端口声明（``ports.stage_inputs``）才是"这一步吃什么"的唯一真源。
        if port not in ports.stage_inputs(stage):
            return declared

        # ---- 1. 图说了算（图能给出唯一产出方时）----
        producers = diagram.producers_of(stage, port, active)
        if len(producers) == 1:
            return producers[0]

        # ---- 2. 图说不清 ⇒ 退回静态声明 + 条件 ----
        if declared is not None and in_flow(declared):
            return declared
        # 静态声明不可用时，最后才沿图随便取一个（老行为，保底）
        return producers[0] if producers else diagram.nearest_producer(
            stage, port, active
        )

    # ---------- 节点实例（B 方案：同阶段可以有多个节点）----------
    @staticmethod
    def _stage_live(stage: str, active: set[str]) -> bool:
        """某运行阶段（或它所属的**界面格**）在不在本流程里（`detect_submit`
        跟着 `detect` 那一格一起活着，见 ``ports.STAGE_STEPS``）。"""
        if stage in active:
            return True
        return ports.STAGE_STEPS.get(stage, stage) in {
            ports.STAGE_STEPS.get(s, s) for s in active
        }

    @staticmethod
    def _primary_of_stage(diagram, stage: str) -> str | None:
        """运行阶段 → 它的**主节点** id（`detect_submit` 映射到 `detect` 节点）。"""
        step_key = ports.STAGE_STEPS.get(stage, stage)
        return diagram.primary_of(step_key)

    def _node_ref_path(self, task_id: str, ref: str | None, port: str,
                       diagram) -> Path | None:
        """把"产出方引用"解析成产物绝对路径。

        ``ref`` 可以是**节点 id**、**阶段名**（静态声明兜底/旧调用方）或任务
        哨兵（:data:`ports.SUPPLY_TASK_SOURCE` / :data:`ports.SUPPLY_TASK_INPUT`）。
        """
        if ref is None:
            return None
        task_dir = self.task_dir(task_id)
        if ref == ports.SUPPLY_TASK_SOURCE:
            return None
        if ref == ports.SUPPLY_TASK_INPUT:
            return ports.task_input_dir(task_dir)
        item = diagram.node(ref)
        if item is not None and item.stage:
            effective = ports.fold_forward(item.stage, port)
            return ports.artifact_path(
                task_dir, effective, port, ref, diagram.primary_of(item.stage)
            )
        # 阶段名兜底：映射到该阶段的主节点（没有主节点则用旧落点）
        step_key = ports.STAGE_STEPS.get(ref, ref)
        primary = diagram.primary_of(step_key)
        effective = ports.fold_forward(step_key, port)
        return ports.artifact_path(task_dir, effective, port, primary, primary)

    def node_supplier(self, task_id: str, node_id: str, port: str,
                      imposition_active: bool = False) -> str | None:
        """本任务里某**节点实例**某端口的实际供给方（返回**节点 id** 或哨兵）。

        与 :meth:`stage_supplier` 同一套规则（图优先、静态兜底），区别是把
        "图说的产出方"落到**节点粒度**：同阶段有多个节点时，喂给 ``node_id``
        的是图上那个**具体节点**，而不是"整阶段的主节点"。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        item = diagram.node(node_id)
        if item is None or not item.stage:
            return None
        stage = item.stage
        flags = self.scheduler_flags(task_id, imposition_active)
        active = set(Scheduler.from_diagram(diagram, flags).stages)
        # ⚠️ **不在这里判"消费方在不在流程里"**（与 :meth:`stage_supplier` 保持
        #    一致）：那一步该由 runner 的状态机守卫去说，而这里要能回答
        #    "**如果**要跑这一步，它的输入在哪"。
        #    反例（2026-10-17 自测抓到"弹窗里删除的图片没落盘"）：拼版开关没勾时
        #    ``imposition`` 不在 ``active`` 里，早退会让 ``node_input`` 拿不到
        #    上游、回落成入口图片目录（``stages/input``，空的）——拼版详情页于是
        #    "一张候选都没有"，连「删除图片」都无从落盘。``stage_supplier`` 靠
        #    **静态声明兜底**（下面第 2 步）照样给出 ``stages/rembg``，这里也一样。

        declared = ports.supplier_of(stage, port)
        if stage == "print" and port == "pages":
            declared = ports.print_pages_supplier(bool(imposition_active))
        if declared == ports.SUPPLY_TASK_SOURCE:
            return declared
        if port not in ports.stage_inputs(stage):
            return declared
        # ⚠️ **图上的入口节点（一条入边都没有）就是不接上游**，别退回静态声明
        #    （B 方案，2026-10-17 用户报障）：用户画的"图片拼版 → 检测文本框 →…"
        #    里第一个「图片拼版」没有任何上游，本该回落到入口图片目录
        #    （``stages/input/``）；按静态声明兜底会给出 ``stages/rembg``
        #    ——那是**下游**才有的目录，结果第一步"看着有输入、跑起来找不到图"。
        if not diagram.incoming(node_id):
            return None

        # 1. 图说了算（图上恰好一个产出方）
        producers = diagram.producer_nodes_of(node_id, port, active)
        if len(producers) == 1:
            return producers[0]
        # 2. 图说不清 ⇒ 退回静态声明 + 条件（把声明的阶段映射成它的主节点）
        if declared is not None and self._stage_live(declared, active):
            return declared
        if producers:
            return producers[0]
        return diagram.nearest_producer_node(node_id, port, active)

    def node_supplier_stage(self, task_id: str, node_id: str, port: str,
                            imposition_active: bool = False) -> str | None:
        """节点粒度的供给方，但结果折成**阶段 key**（不是节点 id）。

        :meth:`node_supplier` 回答的是"喂你的是哪个**节点**"（B 方案寻址要用
        节点 id）；而"记进 runs 历史、供旧数据判定比对"的那个字段
        （``args["source_stage"]`` ← :func:`desktop.services.stale_chain.print_source_switched`）
        历来是**阶段 key**（``detect_submit`` / ``imposition``）。两者不是一回事，
        所以这里折一道：节点 → 它的运行阶段 →（同格多动作再折）该端口成品的
        产出阶段。哨兵值原样透传。
        """
        ref = self.node_supplier(task_id, node_id, port, imposition_active)
        if ref is None or ref.startswith("<"):
            return ref
        stage = self.node_stage_of(task_id, ref)
        if stage is None:
            return ref if ref in ports.STAGE_STEPS else None
        return ports.fold_forward(stage, port)

    def node_input(self, task_id: str, node_id: str, port: str = "pages",
                   imposition_active: bool = False) -> Path | None:
        """某**节点实例**某端口输入的绝对路径（带**入口回落**）。

        与 :meth:`stage_input` 同构，只是把消费方定位到**节点**：没有上游而该
        节点确实吃 ``pages`` 时，回落到入口图片目录（``stages/input/``）。
        """
        diagram = self.task_diagram(task_id)
        ref = self.node_supplier(task_id, node_id, port, imposition_active)
        if ref is None and port == "pages":
            item = diagram.node(node_id)
            if item is not None and item.stage and "pages" in ports.stage_inputs(
                item.stage
            ):
                return self.task_input_dir(task_id)
        return self._node_ref_path(task_id, ref, port, diagram)

    def node_output(self, task_id: str, node_id: str, port: str = "pages",
                    stage: str | None = None) -> Path:
        """某**节点实例**某端口产物的绝对路径（**落点的唯一入口**）。

        ``stage`` 缺省取节点自身的阶段；显式给时表示"同一步骤的第二个动作"
        （如 ``detect`` 节点的 ``detect_submit`` 裁图落点）。主节点沿用旧落点，
        副本落到 ``~<node_id>`` 后缀的副本落点。
        """
        diagram = self.task_diagram(task_id)
        item = diagram.node(node_id)
        if item is None or not item.stage:
            raise KeyError(f"节点 {node_id!r} 没有对应的运行阶段")
        effective = stage or item.stage
        path = ports.artifact_path(
            self.task_dir(task_id), effective, port, node_id,
            diagram.primary_of(item.stage),
        )
        if path is None:
            raise KeyError(f"阶段 {effective!r} 没有登记端口 {port!r} 的落点")
        return path

    def required_node_inputs(self, task_id: str, node_id: str,
                             imposition_active: bool = False) -> tuple[str, ...]:
        """某**节点实例**真正要等就位的输入端口（节点粒度的就绪判据）。"""
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = self.scheduler_flags(task_id, imposition_active)
        active = Scheduler.from_diagram(diagram, flags).stages
        return ports.node_blocking_inputs(diagram, node_id, set(active))

    def node_ids(self, task_id: str) -> tuple[str, ...]:
        """本任务流程图里**全部可运行节点**的 id（拓扑序）——界面按它建页。"""
        return tuple(nid for nid, _stage in self.task_diagram(task_id).node_order())

    def node_or_stage_output(self, task_id: str, node_id: str | None,
                             stage: str, port: str = "pages") -> Path:
        """**落点的统一入口**：有节点按节点取，没节点/没登记回落该阶段的旧落点。

        主节点与"没有节点信息"（程序化调用、旧测试探针）都拿到 ``stages/<阶段>``
        ——与改造前逐字节相同。副本节点拿到 ``stages/<阶段>~<节点>``。

        调用方（执行端、取图、缩略图）一律走它，别自己 ``if node:`` 分叉：
        分叉处漏一处，就是"副本节点跑完产物写到主节点去了"。
        """
        if node_id:
            try:
                return self.node_output(task_id, node_id, port, stage)
            except KeyError:
                pass
        return self.artifact(task_id, stage, port)

    def scoped_stage_dir(self, task_id: str, node_id: str | None,
                         name: str) -> Path:
        """``stages/<name>`` 的**节点作用域**版本。

        主节点/无节点 ⇒ ``stages/<name>``（零迁移）；副本 ⇒
        ``stages/<name>~<节点>``。用于**没有登记在 STAGE_LOCATIONS 里**的
        辅助目录（如 detect 的标注图目录）。
        """
        scope = self.scoped_file_scope(task_id, node_id)
        return (
            self.task_dir(task_id)
            / "stages"
            / ports.scoped_name(name, scope["node_id"], scope["primary_id"])
        )

    def node_stage_of(self, task_id: str, node_id: str) -> str | None:
        """节点实例 → 它的**运行阶段**（不是界面步骤 key）；认不出返回 ``None``。"""
        try:
            item = self.task_diagram(task_id).node(node_id)
        except Exception:  # noqa: BLE001 - 图坏了不该拖垮寻址
            return None
        return item.stage if item is not None else None

    def node_primary_of(self, task_id: str, node_id: str) -> str | None:
        """节点实例 → 它所属阶段的**主节点** id（"沿用旧路径"的那一个）。"""
        stage = self.node_stage_of(task_id, node_id)
        if not stage:
            return None
        try:
            return self.task_diagram(task_id).primary_of(stage)
        except Exception:  # noqa: BLE001
            return None

    def scoped_file_scope(self, task_id: str, node_id: str | None
                          ) -> dict[str, str | None]:
        """给 ``load_pages``/``save_draft``/``boxes_path`` 这类按节点隔离的读写
        用的**作用域参数**：``{"node_id": …, "primary_id": …}``。

        统一在这里算，调用方不必各自去查"谁是主节点"——那是**只有图知道**的
        事实（见 :meth:`~desktop.steps.bpmn_diagram.FlowDiagram.primary_of`），
        散在各处迟早漂移。``node_id`` 为空时给 ``{"node_id": None,
        "primary_id": None}``，所有读写都落回**旧路径**（零迁移）。
        """
        if not node_id:
            return {"node_id": None, "primary_id": None}
        return {
            "node_id": node_id,
            "primary_id": self.node_primary_of(task_id, node_id),
        }

    def step_enabled(self, task_id: str, step: str) -> bool:
        """某个**可选步骤**的用户开关（``drafts/<步骤>.json`` 的 ``enabled``）。
        ⚠️ 这是"条件开关"的**通用读法**：以前只有拼版有开关（读
        ``drafts/imposition.json`` 的 ``enabled``），`store.imposition_enabled`
        与详情页的 ``imposition_active()`` 各读各的。再加一个可选步骤就要
        第三份读法——现在统一走这里（同一文件、同一键，行为一字不变，
        见 :meth:`scheduler_flags`）。

        ⚠️ 开关查询**永不抛错**：任务号非法/目录没了/文件坏了，一律当"没开"。
        调用方（列表后台线程、状态机）不能因为一个开关读不出来就崩。

        ⚠️ 命中缓存的条件是**文件指纹没变**（mtime_ns + size）：这个方法在
        第三步刷新时会被**每页**问一次（``imposition_effective`` 在里面），
        每次都完整读 JSON 纯属白花；拨开关会重写该文件，指纹一变立刻失效。
        文件不存在时**不缓存**（否则它后来被建出来会被旧结论挡住）。
        """
        cache = self._step_flags_map()
        cache_key = (task_id, step)
        try:
            path = self.drafts_dir(task_id) / f"{step}.json"
            stat = path.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size)
        except (OSError, ValueError):
            # ⚠️ 任务号非法时 ``drafts_dir`` 抛 ValueError：也归到"没开"这一档，
            #    与本方法"永不抛错"的契约一致（调用方有列表后台线程）。
            cache.pop(cache_key, None)
            return False
        cached = cache.get(cache_key)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        try:
            data = read_json(path, None)
        except (OSError, ValueError):
            cache.pop(cache_key, None)
            return False
        enabled = bool(data.get("enabled")) if isinstance(data, dict) else False
        cache[cache_key] = (fingerprint, enabled)
        return enabled

    def scheduler_flags(self, task_id: str,
                        imposition_active: bool = False) -> dict[str, bool]:
        """本任务传给状态机的条件开关表（key = 可选步骤 key）。

        ⚠️ 键集合从 ``role == "optional"`` 派生（与
        :data:`desktop.steps.scheduler.CONDITIONS` 同源），**不是手写表**：
        以后加第二个可选步骤，这里的键自动多一个，调用方不用改。

        ⚠️ ``imposition`` 这一键**用调用方传进来的值覆盖**，不用
        :meth:`step_enabled` 的读数——调用方传的是 ``imposition_effective()``
        （= 在流程里 ＋ 开关两道闸），而 ``step_enabled`` 只读开关。
        图里没有这一格时，拼版产物根本不存在，必须让状态机跳过它、
        下游退回走去底色——只传开关会把流程指去一个空目录。
        """
        from desktop.steps.spec import OPTIONAL_STEPS

        flags = {step: self.step_enabled(task_id, step)
                 for step in OPTIONAL_STEPS}
        if "imposition" in flags:
            flags["imposition"] = bool(imposition_active)
        return flags

    def task_scheduler(self, task_id: str, imposition_active: bool = False):
        """本任务的**状态机**（``Scheduler``）——"下一步跑谁 / 能不能跑 / 跳谁"
        的唯一入口。

        ⚠️ 这是"后端按图驱动"的查询面：调用方不该再自己拼
        ``STAGES`` / ``SUPPLIERS`` 的静态知识去推断顺序或可运行性，一律问它。
        顺序来自本任务流程图（**节点**拓扑序，B 方案后同阶段可有多个节点各占
        一个状态单元，见 :meth:`~desktop.steps.scheduler.Scheduler.nodes`），跳过看
        :meth:`scheduler_flags`（可选步骤的开关表，键从 spec 派生）。

        与 :meth:`stage_input` 的分工：那个回答**"去哪个目录取产物"**，
        这个回答**"什么时候该跑、还差什么"**。
        """
        from desktop.steps.scheduler import Scheduler

        return Scheduler.from_diagram(
            self.task_diagram(task_id),
            self.scheduler_flags(task_id, imposition_active),
        )

    def stage_output_dir(self, task_id: str, stage: str,
                         node_id: str | None = None) -> Path:
        """返回某阶段（GUI）应写入的输出目录。

        rembg 返回成品图目录、print 返回 print.pdf 所在目录。
        """
        # detect 只检测不落盘，它的产物是坐标文件；若有参考缩略图放
        # thumbnails/detect（那是界面缓存，不是端口产物，故不在 ports 表里）。
        # ⚠️ 按**节点**取（B 方案）：同一步骤的多个「检测文本框」节点各自一份
        #    标注图目录，互不覆盖（用户 2026-10-17：缩略图目录也按节点隔离）。
        if stage == "detect":
            return self.thumbnails_dir(task_id, "detect", node_id)
        return self.stage_dir(task_id, stage)

    def workset_dir(self, task_id: str) -> Path:
        """已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。

        仅为清理历史遗留目录保留（老版本任务目录下可能仍有 workset/）。
        """
        return self.task_dir(task_id) / "workset"

    def runs_config_dir(self, task_id: str) -> Path:
        """子进程执行配置（run-*.json / detect-config.json）。"""
        return self.task_dir(task_id) / "runs"

    def thumbnails_dir(self, task_id: str, name: str,
                       node_id: str | None = None) -> Path:
        """按**节点作用域**取一个缩略图缓存目录：``thumbnails/<名>[~<节点>]``。

        主节点/无节点 ⇒ ``thumbnails/<名>``（旧路径，**零迁移**）；副本节点 ⇒
        ``thumbnails/<名>~<节点>``。规则由 :func:`desktop.steps.ports.scoped_name`
        唯一给出，与产物落点（``stages/<阶段>~<节点>``）同一套——同一步骤有多个
        节点时各自的缩略图缓存互不覆盖（用户 2026-10-17：「缩略图目录也要
        按节点这样处理」）。
        """
        scope = self.scoped_file_scope(task_id, node_id)
        return (
            self.task_dir(task_id)
            / "thumbnails"
            / ports.scoped_name(name, scope["node_id"], scope["primary_id"])
        )

    def input_thumbnails_dir(self, task_id: str) -> Path:
        """**入口图片**的缩略图缓存：``thumbnails/input/``。

        用户 2026-10-17：流程第一个节点是「检测文本框 / 图片去底色 / 图片拼版 /
        PDF排版」时，它的输入是用户直接放进 ``stages/input/`` 的那批图——此前
        左栏只能现解码原图（几千像素的扫描图）。现在**导入即按图键生成**到这份
        缓存里，左栏直接读小图。

        ⚠️ **不按节点分**：入口图片目录（``stages/input/``）是**整个任务共用**
        的（所有无上游的节点都回落到它），所以缓存也与它同作用域（任务级）。
        """
        return self.task_dir(task_id) / "thumbnails" / "input"

    def entry_thumb_path(self, task_id: str, image: Path | str) -> Path | None:
        """一张入口图片在 :meth:`input_thumbnails_dir` 里的缓存缩略图路径。

        没有缓存、或缓存比源图旧/体积像截断，一律返回 ``None``（调用方回落到
        真图解码）。按**图键**命名（``book_key``：文件名+大小+路径指纹）——入口
        图片名字五花八门，按序号会张冠李戴（与 ``thumb_cache_worker`` 同一规则）。
        """
        from desktop.utils.files import book_key
        from desktop.workers.thumb_cache_worker import cache_usable, stat_mtime

        target = self.input_thumbnails_dir(task_id) / f"{book_key(image)}.jpg"
        if not cache_usable(target, stat_mtime(image)):
            return None
        return target

    def source_thumbnails_dir(self, task_id: str) -> Path:
        """源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。

        ⚠️ **不按节点分**：它来自**源 PDF**（一本书一份），同一步骤的多个提取
        节点产出的页图同名同页号，共用这份按页号命名的缓存是正确且省事的。
        """
        return self.task_dir(task_id) / "thumbnails" / "source"

    def rembg_thumbnails_dir(self, task_id: str,
                             node_id: str | None = None) -> Path:
        """第四步缩略图缓存：去底色阶段随成品图一并生成，
        缩略条直接复用，不必每次现解码 6000px 的原图。

        ⚠️ 按**节点**取（B 方案）：两个「图片去底色」节点各有各的成品产物
        （``stages/rembg[~<节点>]``），缩略图缓存也跟着分（裸名 ``print`` /
        ``print~<节点>``），否则副本节点会命中主节点的缩略图（张冠李戴）。
        """
        return self.thumbnails_dir(task_id, "print", node_id)

    def imposition_thumbnails_dir(self, task_id: str,
                                  node_id: str | None = None) -> Path:
        """拼版页左列缩略图缓存（每页取第一张源图，``book_key`` 命名）。

        ⚠️ 与独立拼图页的 ``singletask/imposition/`` **各归各**（用户
        2026-10-04 明确「singletask 和 taskdetail 不是一回事」）：任务缓存
        随任务目录走，``delete_task`` 整体清理时一并清掉；两边只共用组件与
        ``ImageThumbCacheWorker``，**不共用缓存根**。
        """
        return self.thumbnails_dir(task_id, "imposition", node_id)

    def imposition_page_thumbs_dir(self, task_id: str,
                                   node_id: str | None = None) -> Path:
        """拼版**页面效果缩略图实体**目录：``tasks/<id>/thumbnails/imposition_pages/``。

        与 :meth:`imposition_thumbnails_dir`（页内**单张源图**的缩略图）
        不是一层：这里放按版面合成的**整页**实体，``page1.jpg`` 从第一页
        起数，映射数据（页号 ↔ 文件 ↔ 内容签名）在同目录 ``index.json``
        （用户 2026-10-09：「缩略图实体其实没有生成落地……组合成拼版图片
        应该另外放在一个目录中，直接按照 page1 page2 命名，注意做好映射
        数据」）。随任务目录走，``delete_task`` 一并清掉。

        ⚠️ 按**节点**取（B 方案）：两个「图片拼版」节点各有各的版面文档与
        合成产物，缩略图实体也跟着分（``imposition_pages[~<节点>]``）。
        """
        return self.thumbnails_dir(task_id, "imposition_pages", node_id)

    def copy_source_to_task(self, task_id: str, source_path: Path) -> Path:
        """导入时在任务目录下保留一份源文件副本（原子落地）。

        ⚠️ 复制本身可能是在**后台线程**里做的（见
        ``desktop/workers/serial_jobs.py``），而详情页/预览随时会来读这份
        副本，所以走 ``copy_file_atomic``：写 ``.part`` 再 ``os.replace``，
        别人不会读到半截 PDF。
        """
        target = self.task_dir(task_id) / source_path.name
        return copy_file_atomic(source_path, target)

    def source_copy_path(self, task_id: str) -> Path | None:
        """任务目录里的 PDF 备份路径；没有备份返回 None。

        ⚠️ 后续所有操作（详情页预览、extract 入参…）**都必须用它**，不能用
        ``task['source_path']``：源文件在用户磁盘上，会被移动/改名/删除，
        一走就「渲染失败」。备份随任务走，任务才是自包含的。
        """
        task_dir = self.task_dir(task_id)
        task = self.get_task(task_id)
        if task:
            candidate = task_dir / Path(str(task.get("source_path") or "")).name
            if candidate.is_file():
                return candidate
        # 兜底：源被改名过（文件名对不上）时，任务目录下唯一的 PDF 就是备份
        pdfs = sorted(task_dir.glob("*.pdf")) if task_dir.exists() else []
        return pdfs[0] if pdfs else None

    def ensure_source_copy(self, task_id: str) -> Path | None:
        """保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。

        老任务（导入时复制失败）或备份被误删时靠它自愈；源也一起没了就
        返回 None，调用方负责提示。
        """
        existing = self.source_copy_path(task_id)
        if existing:
            return existing
        task = self.get_task(task_id)
        if not task:
            return None
        source = Path(str(task.get("source_path") or ""))
        if not source.is_file():
            return None
        try:
            return self.copy_source_to_task(task_id, source)
        except OSError:
            return None
