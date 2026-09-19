# -*- coding: utf-8 -*-
"""缺中文字体时的启动引导：体检 → 一键从软件源安装 → 失败给手装命令。

为什么必须是"阻塞式引导"而不是一句 warning：缺中文字体时 PDF 里的标题、
页码会静默退回 Helvetica，检测框标注退回 ASCII 的 ``L``/``R``/``U``——
**产物已经错了，而流程一路绿灯**。与其让用户加工到第四步才发现汉字是方块，
不如在进门前把话说清楚。

分工严格遵守分层：

- 「有没有字体、该装哪个包、失败算网络还是权限」全部在
  ``utils.font_setup``（纯标准库，可自测、可命令行复用）；
- 本模块只管 **Qt 外壳**：体检结果要不要弹窗、按钮状态、流式日志、用户勾选
  "以后不提示"。判断逻辑一行都不在这里。

线程：安装要跑 apt/dnf 并可能弹系统的 pkexec 授权框，必须进子线程，
否则界面卡死；日志与结果都通过 **绑到本对话框方法**的信号回到主线程
（跨线程自动排队，不需要 connect_queued 中继——接收者是主线程的 QObject）。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget,
)
from qfluentwidgets import CheckBox, PrimaryPushButton, PushButton, SubtitleLabel

from desktop.ui import theme as T
from desktop.ui.fonts import ui_font
from utils.font_setup import (
    InstallResult, check_cjk_font, install_cjk_fonts, install_plan,
    manual_install_text,
)

#: 跳过体检的环境变量（打包冒烟、GUI 自测用）
SKIP_ENV = "GUJI_SKIP_FONT_CHECK"

#: 「不再提示」记在 QSettings（组织名 gujitools / 应用名 gui）
_SETTINGS_KEY = "fontCheck/skip"

_MONO_FONT = "Consolas, 'Courier New', monospace"


class FontInstallWorker(QThread):
    """子线程里跑 `install_cjk_fonts`，把输出逐行抛回主线程。

    单独一个类的原因：`utils.font_setup.install_cjk_fonts` 里会有 pkexec
    授权框阻塞十几秒到几分钟（`fonts-noto-cjk` 有上百 MB），放进主线程会
    直接把窗口画成"未响应"。
    """

    line = Signal(str)
    result_ready = Signal(object)

    def __init__(self, packages=None, parent=None):
        super().__init__(parent)
        self._packages = packages

    def run(self) -> None:  # pragma: no cover - 线程体，自测不真跑安装
        try:
            result = install_cjk_fonts(
                packages=self._packages, on_line=self.line.emit,
            )
        except Exception as exc:  # 安装脚本崩了也要给结论，不能静默
            result = InstallResult("failed", f"安装过程异常：{exc}")
        self.result_ready.emit(result)


class FontFixDialog(QDialog):
    """缺字体引导框：自动安装 / 复制手装命令 / 暂时跳过。"""

    def __init__(self, plan, parent=None):
        """plan 是 `utils.font_setup.install_plan()` 的候选（可能为空 = 无法自动装）。"""
        super().__init__(parent)
        self._plan = tuple(plan)
        self._worker: FontInstallWorker | None = None
        self._installed = False

        self.setWindowTitle("缺少中文字体")
        self.setModal(True)
        self.resize(760, 620)
        self.setStyleSheet(f"QDialog {{ background: {T.CANVAS}; }}")

        box = QVBoxLayout(self)
        box.setContentsMargins(T.SPACE_XL, T.SPACE_LG, T.SPACE_XL, T.SPACE_LG)
        box.setSpacing(T.SPACE_MD)

        title = SubtitleLabel("这台机器上没有检测到中文字体")
        box.addWidget(title)

        body = QLabel(
            "缺中文字体时，程序不会报错，但产出的 PDF 会静默降级：\n"
            "· 竖排标题与页码退回英文字体，中文变成方块或整段丢失；\n"
            "· 检测框上的标注文字退回 L / R / U 这类缩写。\n"
            "建议在这里装一个，古籍重排的竖排标题最需要的是仿宋。",
            self,
        )
        body.setWordWrap(True)
        body.setFont(ui_font(T.SIZE_BODY))
        body.setStyleSheet(f"color: {T.INK_SOFT};")
        box.addWidget(body)

        self._plan_label = QLabel(self._plan_text(), self)
        self._plan_label.setWordWrap(True)
        self._plan_label.setFont(ui_font(T.SIZE_BODY))
        self._plan_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        box.addWidget(self._plan_label)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setFont(ui_font(T.SIZE_BODY))
        self._status.hide()
        box.addWidget(self._status)

        self._log = QTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._log.setFont(ui_font(T.SIZE_CAPTION))
        self._log.setStyleSheet(
            f"background: {T.SURFACE_SOFT}; color: {T.INK_SOFT};"
            f" border: 1px solid {T.BORDER}; border-radius: {T.RADIUS_SM}px;"
            f" font-family: {_MONO_FONT};"
        )
        self._log.setFixedHeight(160)
        self._log.hide()
        box.addWidget(self._log)

        self._manual = QTextEdit(self)
        self._manual.setReadOnly(True)
        self._manual.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._manual.setFont(ui_font(T.SIZE_CAPTION))
        self._manual.setStyleSheet(
            f"background: {T.SURFACE_SOFT}; color: {T.INK};"
            f" border: 1px solid {T.BORDER}; border-radius: {T.RADIUS_SM}px;"
            f" font-family: {_MONO_FONT};"
        )
        self._manual.setPlainText(manual_install_text(self._plan))
        self._manual.hide()
        box.addWidget(self._manual)

        box.addStretch(1)

        self._skip_check = CheckBox("装不好也不再提示（我已知道后果）", self)
        self._skip_check.setFont(ui_font(T.SIZE_BODY))
        self._skip_check.toggled.connect(self._on_suppress_toggled)
        box.addWidget(self._skip_check)

        row = QHBoxLayout()
        row.setSpacing(T.SPACE_SM)
        row.addStretch(1)
        self._copy_btn = PushButton("复制手动安装命令")
        self._copy_btn.clicked.connect(self._copy_manual)
        row.addWidget(self._copy_btn)
        self._manual_btn = PushButton("查看手动安装步骤")
        self._manual_btn.clicked.connect(self._toggle_manual)
        row.addWidget(self._manual_btn)
        self._install_btn = PrimaryPushButton("自动安装")
        self._install_btn.setVisible(bool(self._plan))
        self._install_btn.clicked.connect(self._start_install)
        row.addWidget(self._install_btn)
        self._close_btn = PushButton("暂时跳过")
        self._close_btn.clicked.connect(self.accept)
        row.addWidget(self._close_btn)
        container = QWidget(self)
        container.setLayout(row)
        box.addWidget(container)

    # ---------------------------------------------------------------- 文案
    def _plan_text(self) -> str:
        """候选包清单的富文本；一个候选都没有时给出人话解释。"""
        if not self._plan:
            return (
                "没有找到可用的包管理器（apt / dnf / yum / pacman / zypper），"
                "无法自动安装 —— 请照下面的「手动安装步骤」处理。"
            )
        lines = ["将从软件源里挑一个装上（按顺序尝试，仿宋优先）："]
        lines += [f"  {i}. {item.name} —— {item.label}" for i, item in
                  enumerate(self._plan, 1)]
        lines.append(
            "点击「自动安装」后会请求管理员权限"
            "（Linux 上是图形授权框），字体包通常有几十到上百 MB。"
        )
        return "\n".join(lines)

    # ---------------------------------------------------------------- 交互
    def _toggle_manual(self) -> None:
        """展开 / 收起手动安装步骤。"""
        visible = not self._manual.isVisibleTo(self)
        self._manual.setVisible(visible)
        self._manual_btn.setText(
            "收起手动安装步骤" if visible else "查看手动安装步骤"
        )

    def _copy_manual(self) -> None:
        """把手动安装步骤复制到剪贴板。"""
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(manual_install_text(self._plan))
        self._say("已复制到剪贴板。", T.INK_SOFT)

    def _on_suppress_toggled(self, checked: bool) -> None:
        """勾上就在 QSettings 里记一笔，下次启动不再体检。"""
        QSettings("gujitools", "gui").setValue(_SETTINGS_KEY, bool(checked))

    # ---------------------------------------------------------------- 安装
    def _start_install(self) -> None:
        self._install_btn.setEnabled(False)
        self._install_btn.setText("正在安装…")
        self._log.show()
        self._log.clear()
        self._say("正在从软件源下载并安装，可能需要一两分钟…", T.INK_SOFT)
        self._worker = FontInstallWorker(self._packages(), self)
        self._worker.line.connect(self._append_line)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _packages(self):
        """候选包名的元组；为空时交给 install_cjk_fonts 自己按计划推导。"""
        return tuple(item.name for item in self._plan) or None

    def _append_line(self, text: str) -> None:
        self._log.append(text)

    def _on_result(self, result: InstallResult) -> None:
        self._install_btn.setText("自动安装")
        self._install_btn.setEnabled(True)
        self._installed = result.ok
        if result.ok:
            self._close_btn.setText("完成")
            self._say(
                f"{result.message}。已能识别到中文字体，可以正常使用了。",
                T.SUCCESS,
            )
            return
        hints = {
            "network": "连不上软件源（离线环境常见）。",
            "permission": "授权没通过，或者这台机器没有提权手段。",
            "unsupported": "这个平台没法自动装字体。",
        }
        prefix = hints.get(result.status, "安装失败。")
        self._say(f"{prefix} {result.message} 下面是手动安装的办法：", T.DANGER)
        if result.output.strip():
            self._log.append("")
            self._log.append(result.output.strip())
        self._log.show()
        if not self._manual.isVisibleTo(self):
            self._toggle_manual()

    def _say(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")
        self._status.show()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """关窗前先停掉还在跑的安装线程，避免子进程变成孤儿。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.terminate()
            worker.wait(2000)
        super().closeEvent(event)

    @property
    def installed(self) -> bool:
        """本次会话里是否真的装上了中文字体。"""
        return self._installed


def font_check_suppressed() -> bool:
    """用户是否勾过「不再提示」。"""
    try:
        return bool(QSettings("gujitools", "gui").value(_SETTINGS_KEY, False))
    except Exception:
        return False


def reset_font_check() -> None:
    """清掉「不再提示」，下次启动重新体检（自测 / 排错用）。"""
    QSettings("gujitools", "gui").remove(_SETTINGS_KEY)


def ensure_cjk_fonts(parent=None) -> bool:
    """启动体检：没有中文字体就弹引导框。

    正常情况（Windows、装了中文字体的 Linux）会**立刻静默返回 True**；
    ``GUJI_SKIP_FONT_CHECK=1`` 可整体跳过（打包冒烟与 GUI 自测）。
    """
    if os.environ.get(SKIP_ENV):
        return True
    if font_check_suppressed():
        return True
    if check_cjk_font().found:
        return True

    dialog = FontFixDialog(install_plan(), parent)
    dialog.exec()
    return True
