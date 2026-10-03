# -*- coding: utf-8 -*-
"""执行进度：细进度条 + 计数文案（**独立功能页共用的那一条**）。

为什么要有这个组件（2026-10-03）：

- 任务流程页早就有进度条（``desktop/pages/taskdetail/view.py`` 的
  ``stage_progress``），但**独立功能页一条都没有**——点「开始提取 / 去底色 /
  生成 PDF」之后，右栏只有一行"正在处理…"的文字，几十秒的活儿看不出跑到
  哪儿了；
- 数字必须和条**放在一起**：页头状态行与右栏底部隔着一屏，对不上号；所以
  计数（``12/48　25%``）直接跟在条右边，同一行读完。

四个状态方法（:meth:`start` / :meth:`update` / :meth:`succeed` / :meth:`fail`）
**谁在执行不重要**——``StepControl``（四个步骤页）与拼版页都用它，视觉与
口径只有一份。

⚠️ **总量未知**是常态而不是例外（print 的合成阶段、拼版合成、detect 出框
之前都报不出 total），此时 :class:`~desktop.ui.widgets.ProgressLine` 走
"来回滑动"的未知态，计数文案相应地不写 ``x/y``。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from desktop.ui import theme as T
from desktop.ui.widgets import ProgressLine, apply_to


class ProgressRow(QWidget):
    """一行执行进度：左侧细进度条（伸展）+ 右侧计数/状态文案。

    对外只认上面那四个状态方法加 :meth:`reset`。**不要**直接去摸
    ``self.bar.setRange/setValue``——计数文案、颜色、未知态滑块都得跟着一起
    变，绕过方法就会漏掉其中一样。
    """

    #: 计数文案右对齐的最小宽度（避免文案长短变化把进度条顶得忽宽忽窄）
    COUNT_MIN_WIDTH = 96

    def __init__(self, parent=None, noun: str = ""):
        """``noun`` 是这一步的计量单位（"页"/"张"），只影响完成文案。"""
        super().__init__(parent)
        self._noun = noun

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(T.SPACE_SM)

        self.bar = ProgressLine()
        self.bar.setVisible(False)
        row.addWidget(self.bar, 1)

        self.count = QLabel("")
        apply_to(self.count, T.SIZE_CAPTION, color=T.INK_FAINT)
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.count.setMinimumWidth(self.COUNT_MIN_WIDTH)
        self.count.setVisible(False)
        row.addWidget(self.count, 0)

    # ------------------------------------------------------------------ 状态
    def start(self, text: str = "正在处理…") -> None:
        """开始执行：条先摆出来（未知态滑块），计数位置显示提示文案。

        ⚠️ **先显示、后知总量**：多数命令第一步是"数一遍文件"，那之前 total
        拿不到；此时若把控件藏起来，用户会以为点了没反应。
        """
        self._set_text(text, T.INK_SOFT)
        self._show_bar()

    def update(self, done: int, total: int) -> None:  # noqa: A002 - 与信号同形
        """一次进度汇报：有 total 就定量显示 ``done/total  百分比``。"""
        self._show_bar()
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        if total:
            percent = int(round(self.bar.ratio * 100))
            self._set_text(f"{done}/{total}　{percent}%", T.INK_SOFT)
        elif done:
            self._set_text(f"已处理 {done}{self.unit()}", T.INK_SOFT)
        else:
            self._set_text("正在处理…", T.INK_SOFT)

    def succeed(self, text: str = "") -> None:
        """成功：条走到头，文案写最终计数（不给文案就只写"完成"）。"""
        if self.bar.is_unknown():
            # ⚠️ 没拿到过 total 就没法"走到头"：藏条、只留完成文案，
            #    别留一根滑块在那儿装忙。
            self.bar.setVisible(False)
        else:
            self._show_bar()
            self.bar.finish()
        self._set_text(text or f"完成{self.unit()}", T.SUCCESS)

    def fail(self, text: str = "执行失败") -> None:
        """失败：条**停住**（不清零——停在出错那一刻才看得出跑到哪儿），文案转红。"""
        if self.bar.is_unknown():
            self.bar.setVisible(False)
        self._set_text(text, T.DANGER)

    def reset(self) -> None:
        """收工复位：条与文案都藏起来（下次 :meth:`start` 再点亮）。"""
        self.bar.setRange(0, 0)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        self.count.setText("")
        self.count.setVisible(False)

    # ------------------------------------------------------------------ 内部
    def _show_bar(self) -> None:
        """点亮进度条并**重新评估动画**。

        ⚠️ 必须显式刷一次动画：``ProgressLine`` 只在**自己**被隐藏过再显示时
        才重入 ``showEvent``，而这里是"上次跑完就藏起来、这次再点亮"，
        父容器整块显隐也不保证触发它——漏掉这一句，未知态的滑块就停在原地，
        看着像卡死。
        """
        if not self.bar.isVisible():
            self.bar.setVisible(True)
        self.bar.refresh_animation()

    def _set_text(self, text: str, color: str) -> None:
        self.count.setText(text)
        apply_to(self.count, T.SIZE_CAPTION, color=color)
        if not self.count.isVisible():
            self.count.setVisible(True)

    def unit(self) -> str:
        """计量单位后缀（"页"/"张"；没给单位就是空串）。**公开**访问器。"""
        return f" {self._noun}" if self._noun else ""

    def done_text(self) -> str:
        """按"最后一次已知上限"拼收尾文案（``完成 12/12 页``）。

        给宿主（``StepControl``）在成功时用：有些命令最后一页不补发 progress
        （print 只在 %10 与末页发，rembg 的失败张不计入 done），靠"最近一次
        进度"会停在 90%。总量未知时只说"已完成"——别写"完成 0 页"。
        """
        if self.bar.is_unknown():
            return "已完成"
        return f"完成 {self.bar.maximum()}/{self.bar.maximum()}{self.unit()}"


__all__ = ["ProgressRow"]
