# -*- coding: utf-8 -*-
"""执行内核：把「输入路径 + 输出路径 + 参数」跑成一个后台任务。

用户口径（2026-10-02）：

> 公共组件定义好 API 就行，比如入口文件目录，输出文件目录等；
> 新的功能可以批量处理也可以处理一张图片。

所以这里的 API 只有三样东西——**源（文件或目录）、输出目录、参数**：

    kernel = StepKernel(command_job("rembg"))
    kernel.progress.connect(on_progress)
    kernel.finished.connect(on_finished)   # 参数 = 输出目录
    kernel.failed.connect(on_failed)
    kernel.run(StepRequest(source=src, dest=dst, args=panel.get_args()))

- **单张 / 批量**不是两套代码：源是文件就是单张、是目录就是批量，判断在
  功能层（``FunctionBase.is_file``）里，本内核只负责把路径递下去；
- **与流程无关**：内核不知道自己是第几步、上游是谁——任务管理的那套顺序
  编排留在 ``desktop/pages/taskdetail``，本层只做"跑一步"；
- **不卡界面**：任务跑在 QThread 里，进度/结果经 Qt 信号排队回主线程。

⚠️ 这里跑的是**进程内**线程（与任务流程的子进程隔离不同）。模块页要的是
"点一下就开始、看得见进度"，进程内更轻；崩溃隔离由任务流程那条
``desktop.steps.process.StageProcess`` 负责——两条路各取所需，共用同一份
:class:`StepSpec` 与参数面板。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from core.reporter import EVENT_PROGRESS
from desktop.workers.worker_host import stop_thread


@dataclass
class StepRequest:
    """一次处理请求：**入口 + 出口 + 参数**（内核唯一认识的输入形状）。

    - ``source``：源文件或源目录；``None`` 表示这一步不需要源（罕见）；
    - ``dest``：输出目录（或输出文件）；``None`` 表示由功能层自行推导；
    - ``args``：参数面板 ``get_args()`` 的结果（不含 input/output）。
    """

    source: Path | None = None
    dest: Path | None = None
    args: dict[str, Any] = field(default_factory=dict)


#: 进度回调签名：``(event_name, payload)``（与 ``core.reporter.CallbackReporter`` 同形）
Report = Callable[[str, dict], None]


class StepJob:
    """一次处理任务：给定请求与进度回调，跑完返回输出路径。

    子类只需实现 :meth:`__call__`；抛出的任何异常都会被内核转成 ``failed``
    信号（调用方不必自己 try）。
    """

    def __call__(self, request: StepRequest, report: Report) -> str | None:
        raise NotImplementedError


class CommandJob(StepJob):
    """把 ``functions.get_function(command)`` 包成一个 job。

    ⚠️ 输出目录**精确生效**：显式把 ``function.outpath`` 设成 ``request.dest``。
    不设的话，rembg / cropremove 这类命令会在用户给的目录后再追加一层自己的
    子目录（``resolve_final_output_dir`` 的规则），产物落到 ``dest/rembg/``，
    调用方按 ``dest/<name>.png`` 找结果就永远找不到（模块页改版前的实测坑）。
    显式覆盖后，"输出目录"就真的等于用户选的那个目录——这正是本层对外的承诺。

    仍然有命令会**无视**这个覆盖（自己在 ``dest`` 下面再建目录），extract 就是
    一个：它的布局由 ``utils.pdf_extract.run_on_input_directory`` 决定，是
    ``<dest>/<PDF名>/<子目录>/``。这类"命令自己的目录习惯"由 ``after`` 钩子
    （见 :func:`extract_job`）擦屁股，而不是让每个调用方各自去认路。

    还有一类相反的情况：``artifact_is_file=True`` 的命令（``print``）**不能**被
    覆盖——它的 ``--output`` 是目录、``outpath`` 是目录下的**文件**
    （``<输出>/output.pdf``），覆盖成目录会拿目录当文件路径写。这种命令由它自己
    算 outpath，内核只负责把真正的产物路径回传。
    """

    def __init__(self, command: str,
                 after: Callable[[StepRequest], None] | None = None,
                 artifact_is_file: bool = False):
        self.command = command
        #: 跑完之后的收尾钩子（拿 ``StepRequest``，比如把产物挪到该在的地方）。
        #: ⚠️ 只在 ``execute()`` 正常返回后调；抛异常就当作步骤失败（内核会把
        #: 它变成 ``failed`` 信号）——收尾没做成 = 产物不在约定位置 = 失败。
        self._after = after
        #: 产物是单个文件（见类 docstring）；由 ``StepSpec.artifact_is_file`` 传入。
        self.artifact_is_file = artifact_is_file

    def __call__(self, request: StepRequest, report: Report) -> str | None:
        from core.args import CommandArgs
        from core.reporter import CallbackReporter
        from functions import get_function

        args = dict(request.args or {})
        if request.source is not None:
            args["input"] = str(request.source)
        if request.dest is not None:
            args["output"] = str(request.dest)
        command_args = CommandArgs(command=self.command, **args)
        command_args.validate()  # 与 CLI 同一套校验：非法参数在开跑前就报错
        function = get_function(
            self.command, command_args, reporter=CallbackReporter(report)
        )
        if function is None:
            raise ValueError(f"未知命令：{self.command}")
        if request.dest is not None and not self.artifact_is_file:
            function.outpath = Path(request.dest)
        function.execute()
        if self._after is not None:
            self._after(request)
        # 产物是文件时回传**真正的产物路径**（调用方要靠它显示/打开结果）；
        # 否则回传输出目录（本层对外的承诺就是"输出目录精确生效"）。
        if self.artifact_is_file and function.outpath is not None:
            return str(function.outpath)
        return str(request.dest) if request.dest is not None else None


class CallableJob(StepJob):
    """把任意纯函数包成一个 job（拼版走这条路：``compose_doc`` 不是 CLI 命令）。

    ``fn(request, report) -> str | None``：与 :meth:`StepJob.__call__` 同形。
    """

    def __init__(self, fn: Callable[[StepRequest, Report], str | None]):
        self._fn = fn

    def __call__(self, request: StepRequest, report: Report) -> str | None:
        return self._fn(request, report)


def command_job(command: str) -> CommandJob:
    """按命令名造一个 :class:`CommandJob`（最常用的入口）。"""
    return CommandJob(command)


def extract_job() -> CommandJob:
    """图片提取的 job：跑 ``extract``，**单 PDF 时把产物平铺到输出目录**。

    ⚠️ 为什么需要它（2026-10-02 实测）：``functions.extract`` 按
    ``<输出>/<PDF名>/images/`` 铺图（``run_on_input_directory``，与 CLI 同源）。

    - 源是**目录**（一次多个 PDF）时这是对的做法：每个 PDF 各自一个文件夹，
      否则大家的 ``1.jpg`` 会互相覆盖；
    - 源是**单个 PDF**时这层嵌套纯属多余，而且**违背本层"输出目录精确生效"的
      承诺**：用户选的是 ``样书_提取``，图片却在 ``样书_提取/样书/images/``。
      更糟的是下一步——把输出目录直接拖给「去底色」，功能层只扫顶层，报
      "未找到图片文件"（实测：提取 → 去底色连不上）。

    所以单 PDF 时把 ``<输出>/<PDF名>/**`` 搬平到 ``<输出>/`` 再删空壳；有同名
    文件时**整个不动**（宁可留着嵌套，也不能覆盖或丢文件）。
    """
    return CommandJob("extract", after=_flatten_single_pdf_output)


def _flatten_single_pdf_output(request: StepRequest) -> None:
    """把"单个 PDF"的嵌套产物搬到输出目录根下（见 :func:`extract_job`）。"""
    import os
    import shutil

    source, dest = request.source, request.dest
    if source is None or dest is None:
        return
    if not Path(source).is_file():
        return  # 目录源 = 批量，保持每个 PDF 一个子目录
    nested = Path(dest) / Path(source).stem
    if not nested.is_dir():
        return  # 命令没按预期布局（将来改了规则），什么都不做
    skip = False
    for path in sorted(nested.rglob("*")):
        if not path.is_file():
            continue
        target = Path(dest) / path.name
        if target.exists():
            skip = True
            continue
        os.replace(path, target)
    # ⚠️ 有没搬走的（同名冲突）就**保留整棵嵌套树**：直接 rmtree 会把那些
    #    仍在嵌套里的文件一起删掉——那是用户的产物，宁可多留一层。
    if not skip:
        shutil.rmtree(nested, ignore_errors=True)


def job_for(spec) -> StepJob | None:
    """按 :class:`~desktop.steps.spec.StepSpec` 造执行 job（**唯一入口**）。

    调用方（模块页 / 将来的批处理界面）不要自己拼 ``command_job``：哪一步需要
    额外的收尾（如 extract 的平铺）只有这里知道，散出去就一定会漏。
    没有命令的步骤（拼版）返回 ``None``——那种步骤由调用方给 ``CallableJob``。
    """
    if spec.command is None:
        return None
    # 按 spec.command 装配，而不是写死 extract：将来别的步骤也想要平铺时
    # 只改 ``flat_output=True``，不用记得回来改这里（漏改就跑错命令）。
    return CommandJob(
        spec.command,
        after=_flatten_single_pdf_output if spec.flat_output else None,
        artifact_is_file=spec.artifact_is_file,
    )


def callable_job(fn: Callable[[StepRequest, Report], str | None]) -> CallableJob:
    """按纯函数造一个 :class:`CallableJob`。"""
    return CallableJob(fn)


class _JobWorker(QObject):
    """跑在 worker 线程里的壳：把 job 的返回值/异常翻成信号。"""

    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(str)
    failed = Signal(str)
    #: 步骤**私有**的结构化事件：``(事件名, 负载)``。
    #: ``progress`` / ``log`` 已有专用信号（也最常用），这里只走其余事件——
    #: 典型是 ``page_boxes``（detect 报的每页框坐标）。内核不认识这些事件名，
    #: 只负责原样透传；认不认识由上层（模块页 / 详情页）自己决定。
    event = Signal(str, object)

    def __init__(self, job: StepJob, request: StepRequest):
        super().__init__()
        self._job = job
        self._request = request
        self._cancelled = False

    def cancel(self) -> None:
        """请求中止。⚠️ 只置标记——真正能被打断的只有按页循环的功能层，
        内核不替它们做承诺（与模块页原实现一致）。"""
        self._cancelled = True

    def run(self) -> None:
        """执行 job；任何异常都变成 ``failed`` 信号，绝不抛回 Qt 事件循环。"""
        try:
            output = self._job(self._request, self._report)
        except Exception as exc:  # noqa: BLE001 - 边界：失败必须变成信号
            self.failed.emit(str(exc))
            return
        self.finished.emit("" if output is None else str(output))

    def _report(self, name: str, payload: dict) -> None:
        """reporter 回调（跑在 worker 线程）：进度与日志走专用信号，其余原样透传。

        ⚠️ 「其余」必须透传，不能只认 progress/log——检测这一步**不写文件**，
        框坐标只经 ``page_boxes`` 事件回来（``functions.detect`` 的
        ``_report_boxes``）；内核把它们丢掉的话，独立「检测文本框」模块页就
        永远显示不出框（改造前就是这个症状）。
        """
        if name == EVENT_PROGRESS:
            self.progress.emit(
                int(payload.get("done", 0)), int(payload.get("total", 0))
            )
        elif name == "log":
            message = payload.get("message")
            if message:
                self.log.emit(str(message))
        else:
            self.event.emit(name, payload or {})


class StepKernel(QObject):
    """一个步骤的执行内核：跑一次 :class:`StepJob`，信号回报进度与结果。

    生命周期：``run()`` → ``started`` → 若干 ``progress``/``log`` →
    ``finished`` 或 ``failed``。同一时刻只允许一次运行（``busy()`` 为真时
    ``run()`` 直接返回 False，调用方据此提示"上一次还没结束"）。
    """

    started = Signal()
    progress = Signal(int, int)   # (done, total)；total=0 表示未知
    log = Signal(str)
    finished = Signal(str)        # 输出目录（或输出文件）
    failed = Signal(str)          # 失败原因
    #: 步骤私有的结构化事件 ``(事件名, 负载)``；见 ``_JobWorker.event``。
    event = Signal(str, object)

    def __init__(self, job: StepJob | None, parent=None):
        super().__init__(parent)
        self._job = job
        self._thread: QThread | None = None
        self._worker: _JobWorker | None = None

    # ------------------------------------------------------------------ 运行
    def run(self, request: StepRequest) -> bool:
        """起后台线程跑一次；已在跑则返回 False（调用方应提示并放弃本次）。"""
        if self._job is None or self.busy():
            return False
        thread = QThread(self)
        worker = _JobWorker(self._job, request)
        worker.moveToThread(thread)
        # ⚠️ 必须连到**本对象（主线程）的绑定方法**，别直接 signal.connect(signal)：
        #    worker 在子线程 emit，绑定方法属于主线程对象 → Qt 自动排队回主线程，
        #    下游槽（碰控件）才不会在子线程里跑（同 desktop.workers 的规矩）。
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._on_log)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.event.connect(self._on_event)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        self.started.emit()
        thread.start()
        return True

    def cancel(self) -> None:
        """请求中止（尽力而为；能否立刻停下取决于功能层是否检查标记）。"""
        if self._worker is not None:
            cancel = getattr(self._worker, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:  # noqa: BLE001 - 收尾尽力而为
                    pass

    def busy(self) -> bool:
        """是否正在运行（线程还在跑）。"""
        return self._thread is not None and self._thread.isRunning()

    def shutdown(self, timeout_ms: int = 1500) -> None:
        """收尾：请求中止并等待线程结束（页面关闭/退出时必须调）。"""
        self.cancel()
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is not None:
            stop_thread(thread, timeout_ms, "步骤执行线程")

    # ------------------------------------------------------------------ 转发
    def _on_progress(self, done: int, total: int) -> None:
        self.progress.emit(done, total)

    def _on_log(self, message: str) -> None:
        self.log.emit(message)

    def _on_finished(self, output: str) -> None:
        self.finished.emit(output)

    def _on_failed(self, message: str) -> None:
        self.failed.emit(message)

    def _on_event(self, name: str, payload) -> None:
        """透传步骤私有事件（已在主线程，因为连的是本对象的绑定方法）。"""
        self.event.emit(name, payload)

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None


__all__ = [
    "CallableJob",
    "CommandJob",
    "StepJob",
    "StepKernel",
    "StepRequest",
    "callable_job",
    "command_job",
    "extract_job",
    "job_for",
]
