# -*- coding: utf-8 -*-
"""任务索引（tasks.json）与任务目录布局。"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from desktop.steps import ports
from desktop.steps.flow import (
    FlowDefinition,
    FlowLayout,
    StageSlot,
    default_flow_path,
)
from desktop.steps.spec import FLOW_STAGES, OPTIONAL_STEPS, spec_by_key
from desktop.store.json_io import read_json, write_json
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
#: （多带一个 ``rembg_submit``：它不是独立步骤，却是真实的运行阶段，worker
#: 会跑它、进度与日志都要有名字）。别在这里另写一句中文——BPMN 流程图上的
#: 节点名走的是同一个函数，两边不一致就会出现"图上两个『图片去底色』"。
STAGE_LABELS = {key: ports.stage_label(key) for key in STAGES}
STAGE_LABELS["rembg_submit"] = ports.stage_label("rembg_submit")

# 列表里的阶段短名（步骤条/表格空间有限，用 2~3 字表达）
STAGE_SHORT = {key: spec_by_key(key).short_name() for key in STAGES}

# ------------------------------------------------------------ 流程条的可选节点
#: 「图片拼版」**伪步骤**：流程条上的虚线可选节点，位于第三步（图片去底色）
#: 与第四步（生成 PDF）之间，仅当第三步「区域模式」为 1（左右分开）时出现。
#: 用户可以选择它（启用）也可以不选择；节点详情当前为占位（不参与任何执行
#: 链路，STAGES/runs.json/阶段面板等机制一律不感知它）。
#:
#: ⚠️ 它**有自己的独立模块页**（``desktop/modules/imposition``）——"进不进流程"
#: 和"有没有独立功能"是两件事，这也是 ``StepSpec.role`` 要分
#: ``stage`` / ``optional`` 的原因。
IMPOSITION_STAGE = OPTIONAL_STEPS[0]
IMPOSITION_LABEL = spec_by_key(IMPOSITION_STAGE).stage_name()
#: 伪步骤在流程条上的下标：跟在四个真实步骤之后（控制栈/预览栈里同样占
#: 第 5 位——占位详情面板与占位预览）。
IMPOSITION_INDEX = len(STAGES)

# 「图片拼版」**不是 STAGES 里的一步**（它是可选节点），但任务列表的「子任务
# 状态」胶囊会按任务详情里的启用情况把它插进去，所以上面两张文案表都得有它。
# ⚠️ 取值仍走 ``stage_name()`` / ``short_name()``，不另写一份中文。
STAGE_LABELS[IMPOSITION_STAGE] = IMPOSITION_LABEL
STAGE_SHORT[IMPOSITION_STAGE] = spec_by_key(IMPOSITION_STAGE).short_name()

#: 运行阶段 → 它归属的**界面步骤**（值取 STAGES 里的一项）。
#:
#: ⚠️ 「提交本次任务」（rembg_submit）不是独立步骤，而是第三步 rembg 面板上的
#: 动作：它的进度必须显示在第三步。有了这张表，界面才谈得上"只有当前这一步的
#: 进度才上屏"（详见 desktop/pages/taskdetail/runner.py::_progress_belongs_here）。
STAGE_STEP = {
    "extract": "extract",
    "detect": "detect",
    "rembg": "rembg",
    "rembg_submit": "rembg",
    "print": "print",
}


class TaskMixin:
    """任务索引读写与任务目录/阶段输出目录的路径推导。"""

    root: Path

    # ---------- tasks.json ----------
    def _tasks_path(self) -> Path:
        return self.root / "tasks.json"

    def _load_tasks_index(self) -> list[dict]:
        data = read_json(self._tasks_path(), [])
        return data if isinstance(data, list) else []

    def _save_tasks_index(self, tasks: list[dict]) -> None:
        self._tasks_path().parent.mkdir(parents=True, exist_ok=True)
        write_json(self._tasks_path(), tasks)

    # ---------- 任务 CRUD ----------
    def next_task_no(self) -> str:
        """下一个任务号（**预测值**）：当前最大号 + 1，参考索引与磁盘目录。

        给界面做**占位提示**用（如创建页的默认任务名「任务#0007」）。

        ⚠️ 它只是预测：``create_task`` 真正占号是原子的（``mkdir
        exist_ok=False``，被抢就顺延），所以并发/历史残留时**实际拿到的号
        可能比这里大**。因此：
        - 界面拿它显示"将要用的名字"可以（占位文字而已）；
        - **落库时不要信它**——默认名一律由 :meth:`create_task` 用**实际
          分配到的** ``task_id`` 现算（见 :meth:`default_task_name`），
          否则名字里的序号会和任务号对不上（用户会以为"任务#0008"就是
          0008 号任务，结果落在 0009 上）。
        """
        return self._next_task_no()

    def default_task_name(self) -> str:
        """默认任务名「任务#XXXX」（XXXX = 预测的下一个任务号）。

        只给界面做 **placeholder / 提示**用；真正落库时
        :meth:`create_task` 会用实际号重算一遍（见该方法的同名参数说明）。
        """
        return f"任务#{self._next_task_no()}"

    def _next_task_no(self) -> str:
        """下一个任务号：当前最大任务号 + 1（同时参考索引与磁盘目录）。"""
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
    ) -> str:
        """
        新建任务并返回任务号（四位零填充）。

        任务号取当前最大号 +1，同时参考索引与磁盘目录；若两者不一致导致号被
        占用则继续顺延。创建时会预建 stages/runs/thumbnails/source
        子目录，但不复制源文件（由 copy_source_to_task 负责）。

        ``flow`` / ``flow_layout`` 是**自定义流程**（创建任务弹窗传进来，
        见 ``docs/tasks/bpm.md`` 的 M3）：给了就把本任务自己的 ``flow.bpmn``
        写成这份、坐标落进 BPMN DI 段；不给就是默认流程（从 ports 派生）。

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
                    fallback = load_default_diagram()
                    if fallback.nodes:
                        fallback.save(default_flow_path(task_dir))
                    else:
                        chosen = (flow if flow is not None
                                  else FlowDefinition.default())
                        chosen.save(default_flow_path(task_dir), flow_layout)
        except OSError:
            pass

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
        """
        task_dir = self.task_dir(task_id)
        if task_dir.exists() and not self._rmtree_with_retry(task_dir):
            return False
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
        """步骤三最终图片目录（「提交本次任务」产出，print 阶段从此取图）。"""
        return self.artifact(task_id, "rembg_submit", "pages")

    def rembg_preview_output_dir(self, task_id: str) -> Path:
        """「生成预览」产出的整页去底预览图目录（中间产物，不参与 print）。"""
        return self.artifact(task_id, "rembg", "pages")

    def imposition_output_dir(self, task_id: str) -> Path:
        """「图片拼版」产出的成品拼版页图目录（列表顺序即页序）。

        拼版节点**生效**时（选择态为真且有拼版页），第四步「生成 PDF」与它的
        待打印列表一律从这里取图；否则仍从 ``rembg_output_dir`` 取。
        """
        return self.artifact(task_id, "imposition", "pages")

    def print_output_pdf(self, task_id: str) -> Path:
        """print 阶段产物 print.pdf 的完整路径。"""
        return self.artifact(task_id, "print", "pdf")

    def task_flow(self, task_id: str) -> FlowDefinition:
        """本任务的**流程定义**（BPM 驱动的运行时载体）。

        优先读 ``tasks/<任务号>/flow.bpmn``（建任务时由默认流程生成，可被
        自定义流程替换）；文件缺失、被手编坏（非法 XML / 未知阶段）一律
        **回落默认流程**——任务必须保持可用，坏文件不能拖死整个页面。
        按 mtime 做小缓存：外部编辑器改完文件下一次进来就能生效。
        """
        path = default_flow_path(self.task_dir(task_id))
        cache = getattr(self, "_flow_cache", None)
        if cache is None:
            cache = self._flow_cache = {}
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            return FlowDefinition.default()
        cached = cache.get((task_id, stamp))
        if cached is not None:
            return cached
        try:
            loaded = FlowDefinition.load(path)
        except (ValueError, OSError):
            loaded = FlowDefinition.default()
        cache[(task_id, stamp)] = loaded
        return loaded

    def task_diagram(self, task_id: str):
        """本任务的**流程图**（``FlowDiagram``：节点类型 + 坐标 + 折点）。

        ⚠️ 与 :meth:`task_flow` 的区别：那个给**运行语义**（阶段序列 + 端口
        边表，``FlowDefinition``），这个给**图形**（页面渲染用）。两者读的
        是同一个 ``flow.bpmn``——文件是唯一真源。

        读不到 / 文件坏一律**回落默认模板**：界面宁可显示默认流程，也不能
        整个详情页打不开。

        ⚠️ **"解析得动但一个可执行步骤都认不出"也算坏**：那种图会让
        :meth:`stage_supplier` 的"在流程里"集合变成空集，于是**每个端口都
        解析成 None**（现象是"每一步都说找不到输入"，而流程看起来是有节点的，
        极难查）。所以这里判的是"有没有能跑的步骤"，不是"有没有节点"。
        """
        from desktop.steps.bpmn_diagram import FlowDiagram
        from desktop.steps.scheduler import load_default_diagram

        path = default_flow_path(self.task_dir(task_id))
        if path.is_file():
            try:
                diagram = FlowDiagram.load(path)
                if diagram.stage_order():
                    return diagram
            except (ValueError, OSError):
                pass
        fallback = load_default_diagram()
        if fallback.nodes:
            return fallback
        return FlowDiagram()

    def save_task_diagram(self, task_id: str, diagram) -> None:
        """把流程图写回 ``tasks/<任务号>/flow.bpmn``（原子写）。

        写完**必须清掉 ``task_flow`` 的 mtime 缓存**：它按 ``(task_id, mtime)``
        缓存，不清的话本次会话里再读拿到的还是旧流程——用户改完流程却看到老
        步骤条（"改了没反应"）。

        ⚠️ 只改**流程定义**，不碰任何产物。改完流程后已有产物是否还有效，是
        **界面该提示的事**，由调用方判断——store 只管存。
        """
        diagram.save(default_flow_path(self.task_dir(task_id)))
        cache = getattr(self, "_flow_cache", None)
        if cache is not None:
            for key in [k for k in cache if k[0] == task_id]:
                cache.pop(key, None)

    def task_flow_layout(self, task_id: str) -> FlowLayout | None:
        """本任务流程的**节点坐标**（读``flow.bpmn`` 的 BPMN DI 段）。

        读不到 / 文件坏 / 没有 DI 段时返回 ``None``——调用方（弹窗）据此
        回落自动排布。坐标是"锦上添花"，缺了不该让流程读不出来。
        """
        path = default_flow_path(self.task_dir(task_id))
        if not path.is_file():
            return None
        layout = FlowDefinition.load_layout(path)
        # `load_layout` 读不到时回空布局（boxes 为空）⇒ 对调用方等于"没有坐标"
        return layout if layout.boxes else None

    def save_task_flow(self, task_id: str, flow: FlowDefinition,
                       flow_layout: FlowLayout | None = None) -> None:
        """把新流程写回 ``tasks/<任务号>/flow.bpmn``（详情页改流程用）。

        写完**必须清掉 mtime 缓存**：``task_flow`` 按 ``(task_id, mtime)`` 缓存，
        不清的话本次会话里再读拿到的还是旧流程——用户改完流程却看到老步骤条
        （"改了没反应"）。

        ⚠️ 只改**流程定义与节点坐标**，不碰任何产物。改流程后已有产物是否还
        有效，是**界面该提示的事**（如"新流程不含已完成的去底色"），由调用方
        判断——store 只管存。
        """
        chosen = flow if flow is not None else FlowDefinition.default()
        chosen.save(default_flow_path(self.task_dir(task_id)), flow_layout)
        cache = getattr(self, "_flow_cache", None)
        if cache is not None:
            for key in [k for k in cache if k[0] == task_id]:
                cache.pop(key, None)

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

    def stage_supplier(self, task_id: str, stage: str, port: str,
                       imposition_active: bool = False) -> str | None:
        """本任务里 ``(stage, port)`` 的**实际供给方**（运行时按图求解）。

        ⚠️ **这一步是"运行时跟着图走"的关键**：以前直接查代码里的端口级边表
        （``ports.SUPPLIERS``），一旦用户把流程改成不含某一步（例如去掉
        「图片去底色」），边表给的供给方就不在流程里了——按它取路径会指向
        **永远不会产生的文件**（现象是"生成 PDF 找不到输入"，而不是流程报错，
        极难查）。

        规则（先声明、后回退）：
        1. 取 ``ports`` 声明的供给方（``print/pages`` 走拼版开关那条特例）；
        2. 它**在本流程里**⇒ 就用它；
        3. 不在 ⇒ 沿图往前找**最近的、产出该端口的在流程阶段**
           （:meth:`FlowDiagram.nearest_producer`）。

        ⚠️ **"在流程里"要按"界面格子"判，不能按节点判**：
        ``rembg_submit``（提交去底色结果）是第三步内的**第二个动作**，用户画图
        时通常不会给它单独开一个节点（界面槽位也把它折回「图片去底色」那一格）。
        若按"图里有没有这个节点"判，就会认为它不在流程里，于是 ``print.pages``
        回退到 ``rembg`` ——而 ``rembg`` 指向的是**去底色的实时预览目录**，
        不是用户「提交」过的成品目录，**打印出来的是没提交的图**。
        所以判据是"它所属的**界面格**在不在流程里"（:data:`ports.STAGE_STEPS`
        给出 stage→step 的折叠关系）。
        """
        from desktop.steps.scheduler import Scheduler

        diagram = self.task_diagram(task_id)
        flags = {"imposition": bool(imposition_active)}
        active = set(Scheduler.from_diagram(diagram, flags).stages)
        # 本流程里"活着"的**界面格**（例如 rembg_submit 与 rembg 同属一格）
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
        if declared is None or declared == ports.SUPPLY_TASK_SOURCE:
            return declared
        if in_flow(declared):
            return declared
        return diagram.nearest_producer(stage, port, active)

    def task_scheduler(self, task_id: str, imposition_active: bool = False):
        """本任务的**状态机**（``Scheduler``）——"下一步跑谁 / 能不能跑 / 跳谁"
        的唯一入口。

        ⚠️ 这是"后端按图驱动"的查询面：调用方不该再自己拼
        ``STAGES`` / ``SUPPLIERS`` 的静态知识去推断顺序或可运行性，一律问它。
        顺序来自本任务流程图（拓扑序），跳过看 :data:`CONDITIONS`
        （目前只有"拼版"受开关控制）。

        与 :meth:`stage_input` 的分工：那个回答**"去哪个目录取产物"**，
        这个回答**"什么时候该跑、还差什么"**。
        """
        from desktop.steps.scheduler import Scheduler

        return Scheduler.from_diagram(
            self.task_diagram(task_id),
            {"imposition": bool(imposition_active)},
        )

    def stage_output_dir(self, task_id: str, stage: str) -> Path:
        """返回某阶段（GUI）应写入的输出目录。

        注意 rembg 阶段返回 rembgpreview 预览目录，rembg_submit 才指向
        rembg 最终目录；print 返回 print.pdf 所在目录。
        """
        # detect 只检测不落盘，它的产物是坐标文件；若有参考缩略图放
        # thumbnails/detect（那是界面缓存，不是端口产物，故不在 ports 表里）。
        if stage == "detect":
            return self.task_dir(task_id) / "thumbnails" / "detect"
        return self.stage_dir(task_id, stage)

    def workset_dir(self, task_id: str) -> Path:
        """已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。

        仅为清理历史遗留目录保留（老版本任务目录下可能仍有 workset/）。
        """
        return self.task_dir(task_id) / "workset"

    def runs_config_dir(self, task_id: str) -> Path:
        """子进程执行配置（run-*.json / detect-config.json）。"""
        return self.task_dir(task_id) / "runs"

    def source_thumbnails_dir(self, task_id: str) -> Path:
        """源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。"""
        return self.task_dir(task_id) / "thumbnails" / "source"

    def rembg_thumbnails_dir(self, task_id: str) -> Path:
        """第四步缩略图缓存：提交阶段（rembg_submit）随最终图片一并生成，
        缩略条直接复用，不必每次现解码 6000px 的原图。"""
        return self.task_dir(task_id) / "thumbnails" / "print"

    def imposition_thumbnails_dir(self, task_id: str) -> Path:
        """拼版页左列缩略图缓存（每页取第一张源图，``book_key`` 命名）。

        ⚠️ 与独立拼图页的 ``singletask/imposition/`` **各归各**（用户
        2026-10-04 明确「singletask 和 taskdetail 不是一回事」）：任务缓存
        随任务目录走，``delete_task`` 整体清理时一并清掉；两边只共用组件与
        ``ImageThumbCacheWorker``，**不共用缓存根**。
        """
        return self.task_dir(task_id) / "thumbnails" / "imposition"

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
