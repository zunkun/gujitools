# -*- coding: utf-8 -*-
"""共用步骤控制组件：把「选源 → 调参数 → 执行/中断」这条链装成一块控件。

这一块就是三个模块页右栏的**全部内容**：一块**大输入区**（拖文件/拖文件夹/
点选，见 :class:`~desktop.steps.source_zone.SourceZone`）、一个输出目录按钮、
一个参数面板（来自 :class:`StepSpec`）、执行与中断按钮。
三个模块各持**自己的一份实例**（各自的 :class:`StepKernel`、各自的源/输出），
因此**互不影响**——没有共享的可变状态，一个模块在跑不会让另一个模块的按钮变灰。

对外 API 与用户口径一一对应（"入口文件目录，输出文件目录"）：

- :meth:`source` / :meth:`set_source` —— 入口（文件或目录）；
- :meth:`output` / :meth:`set_output` —— 出口目录；
- :meth:`args` —— 参数面板收集到的参数；
- :meth:`run` / :meth:`cancel` / :meth:`busy` / :meth:`shutdown`。

「用户给的路径 → 一个源」的归一化**不在这里**：它住在
:meth:`desktop.steps.spec.StepSpec.resolve_source`（纯逻辑、可单测），
本类只负责把结果画出来并发出 ``source_changed``。

⚠️ 本组件**只发信号、不弹 InfoBar**：提示语由宿主页面（模块页有页头状态行与
日志区）决定怎么呈现。这样同一块控件既能放进模块页，也能放进将来的批处理界面。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, PushButton, PrimaryPushButton

from desktop.steps.kernel import StepKernel, StepRequest, job_for
from desktop.steps.source_zone import SourceZone
from desktop.steps.spec import StepSpec
from desktop.ui import theme as T


class StepControl(QWidget):
    """一个步骤的控制区（无卡片外壳，宿主自己包 :class:`Card`）。

    信号：

    - ``status(text, kind)``：状态文案 + 语义（info/success/warning/error）；
    - ``progress(done, total)``：执行进度（``total=0`` 表示未知）；
    - ``finished(output)``：成功，参数是输出目录；
    - ``failed(message)``：失败原因；
    - ``log(text)``：一行人读日志；
    - ``source_changed(path)``：源变了（宿主可据此更新副标题/预览）；
    - ``running_changed(bool)``：开始/结束执行（宿主可据此禁用别的入口）；
    - ``event(name, payload)``：步骤私有的结构化事件（如 ``page_boxes``），
      给"产物不是文件"的步骤用（detect 报框坐标）。
    """

    status = Signal(str, str)
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)
    log = Signal(str)
    source_changed = Signal(object)
    running_changed = Signal(bool)
    #: 步骤私有的结构化事件 ``(事件名, 负载)``，如 ``page_boxes``。
    #: 模块页据此接住"这一步本身的产物不是文件"的结果（detect 报坐标）。
    event = Signal(str, object)

    def __init__(self, spec: StepSpec, job=None, zone: SourceZone | None = None,
                 parent=None):
        """按 ``spec`` 组装控件；``job`` 省略时按 ``spec.command`` 造命令 job。

        ``zone``：宿主已经建好的**大输入区**。模块页把它横跨整幅放在页头下方
        （用户要的"页面上有一个大的输入框"），这时候传进来，本组件只接线、
        不重复摆放；不传就自己建一个摆在自己顶部（给"整块塞进卡片"的用法）。
        """
        super().__init__(parent)
        self.spec = spec
        self._source: Path | None = None
        #: 显式选定的输出目录（None = 按 spec 规则从源派生）
        self._out: Path | None = None
        #: 输出目录是否被用户**手动**选过。手动选过就不再被"换源自动重推"覆盖，
        #: 否则用户挑好的输出目录会在换一次源之后被悄悄改掉。
        self._out_manual = False

        if job is None:
            # ⚠️ 只走 job_for：哪一步需要收尾（extract 单 PDF 平铺）只有它知道，
            #    在这里再拼一次 command_job 就一定会漏掉（实测断过"提取 → 去底色"）。
            job = job_for(spec)
        self.kernel = StepKernel(job, self)
        self.kernel.progress.connect(self._on_progress)
        self.kernel.log.connect(self.log)
        self.kernel.finished.connect(self._on_finished)
        self.kernel.failed.connect(self._on_failed)
        self.kernel.event.connect(self.event)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(T.SPACE_SM)

        # ---- 大输入区（外部给的就只接线，不重复摆）----
        self.zone = zone if zone is not None else SourceZone(spec)
        self.zone.paths_chosen.connect(self._on_paths)
        self.zone.cleared.connect(self._on_zone_cleared)
        self.zone.rejected.connect(
            lambda message: self.status.emit(message, "warning")
        )
        if zone is None:
            layout.addWidget(self.zone)

        # ---- 参数面板（复用阶段面板，与任务流程同一份默认值）----
        panel_class = spec.panel_class()
        self.panel = panel_class() if panel_class is not None else None
        if self.panel is not None:
            layout.addWidget(self.panel)

        # ---- 输出目录 ----
        self.out_button = PushButton(FIF.SAVE, "输出目录")
        self.out_button.setFixedHeight(34)
        self.out_button.setToolTip("默认与源同级；点这里可以改到别处")
        self.out_button.clicked.connect(self._pick_output)
        layout.addWidget(self.out_button)

        # ---- 执行 / 中断 ----
        run_row = QHBoxLayout()
        run_row.setContentsMargins(0, 0, 0, 0)
        run_row.setSpacing(T.SPACE_SM)
        self.run_button = PrimaryPushButton(FIF.PLAY, spec.run_text())
        self.run_button.setFixedHeight(36)
        self.run_button.clicked.connect(self.run)
        run_row.addWidget(self.run_button, 1)

        self.cancel_button = PushButton(FIF.CANCEL, "中断")
        self.cancel_button.setFixedHeight(36)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        run_row.addWidget(self.cancel_button, 0)
        layout.addLayout(run_row)

    # ------------------------------------------------------------------ 源/输出
    def source(self) -> Path | None:
        """当前源（文件或目录）；未选为 ``None``。"""
        return self._source

    def set_source(self, path: Path | str | None) -> None:
        """设置源；未手动选过输出时，按 :meth:`StepSpec.default_output` 重推输出。

        同时把源画进大输入区（已选态）——宿主（模块页 / 拼版页）也走这里，
        保证"输入的显示"与"真正的源"永远一致，只有一份事实。
        """
        self._source = Path(path) if path else None
        if self._source is not None and not self._out_manual:
            self._out = self.spec.default_output(self._source)
        self.zone.set_source(self._source, self._zone_detail(self._source))
        self.source_changed.emit(self._source)

    def output(self) -> Path | None:
        """当前输出目录；未定则为 ``None``（执行时按默认规则补）。"""
        return self._out or self.spec.default_output(self._source)

    def set_output(self, path: Path | str | None) -> None:
        """显式设置输出目录（会被记为"手动选择"，不再自动覆盖）。"""
        self._out = Path(path) if path else None
        self._out_manual = path is not None

    def args(self) -> dict:
        """参数面板收集到的参数（面板为 ``None`` 时是空字典）。"""
        if self.panel is None:
            return {}
        return self.panel.get_args()

    def zone_detail(self, source: Path | None = None) -> str:
        """大输入区第二行的说明文案（宿主想知道"显示里写了什么"时用）。"""
        return self._zone_detail(self._source if source is None else source)

    # ------------------------------------------------------------------ 执行
    def run(self) -> None:
        """校验前置条件并起后台执行。校验不通过只发 ``status``，不弹窗。"""
        if self._source is None:
            self.status.emit(f"请先拖入或{self.spec.pick_label}", "warning")
            return
        if self.kernel.busy():
            self.status.emit("上一次还没结束，请稍候", "warning")
            return
        try:
            args = self.args()
        except Exception as exc:  # noqa: BLE001 - 参数填错要给用户看得懂的话
            self.status.emit(f"参数有误：{exc}", "error")
            return
        dest = self.output()
        if dest is None:
            self.status.emit("无法确定输出目录，请手动选择", "warning")
            return
        request = StepRequest(source=self._source, dest=dest, args=args)
        self._set_running(True)
        self.status.emit("正在处理…", "info")
        self.log.emit(f"开始{self.spec.title}：{self._source} → {dest}")
        if not self.kernel.run(request):
            self._set_running(False)
            self.status.emit("上一次还没结束，请稍候", "warning")

    def cancel(self) -> None:
        """请求中止当前执行。"""
        self.kernel.cancel()
        self.status.emit("正在中断…", "warning")

    def busy(self) -> bool:
        """是否正在执行。"""
        return self.kernel.busy()

    def shutdown(self, timeout_ms: int = 1500) -> None:
        """收尾执行线程（页面关闭时必须调）。"""
        self.kernel.shutdown(timeout_ms)

    # ------------------------------------------------------------------ 内部
    def _zone_detail(self, source: Path | None) -> str:
        """大输入区第二行：目录给"路径 · N 个可用文件"，文件给所在目录。"""
        if source is None:
            return ""
        if source.is_dir():
            count = len(self.spec.listing(source))
            tail = f"{count} 个可用文件" if count else "（这里没有可用的输入文件）"
            return f"{source} · {tail}"
        return str(source.parent)

    def _on_paths(self, paths: list) -> None:
        """大输入区给了路径：按 spec 归一化成一个源，再落到 :meth:`set_source`。"""
        source, note = self.spec.resolve_source(paths)
        if source is None:
            self.status.emit(note or "这些文件用不了", "warning")
            return
        self.set_source(source)
        if note:
            self.log.emit(note)
        self.status.emit(f"已选择：{source}", "info")

    def _on_zone_cleared(self) -> None:
        """用户清了输入：源与手动输出一起复位（不然输出还停在旧源旁边）。"""
        self._source = None
        self._out = None
        self._out_manual = False
        self.source_changed.emit(None)
        self.status.emit("已清空输入", "info")

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.out_button.setEnabled(not running)
        self.zone.busy_lock(running)
        self.running_changed.emit(running)

    def _pick_output(self) -> None:
        """改输出目录。"""
        current = self.output()
        directory = QFileDialog.getExistingDirectory(
            self, "选择输出目录", str(current) if current else ""
        )
        if directory:
            self.set_output(directory)
            self.status.emit(f"输出目录：{directory}", "info")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.emit(done, total)
        if total:
            self.status.emit(f"正在处理… {done}/{total}", "info")

    def _on_finished(self, output: str) -> None:
        self._set_running(False)
        self.status.emit(f"处理完成：{output}", "success")
        self.log.emit(f"处理完成，输出目录：{output}")
        self.finished.emit(output)

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self.status.emit("处理失败", "error")
        self.log.emit(f"处理失败：{message}")
        self.failed.emit(message)


__all__ = ["StepControl"]
