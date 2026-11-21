# -*- coding: utf-8 -*-
"""把 Qt 自己的消息（warning/fatal/debug）接进崩溃日志。

为什么要它：Qt 崩溃前几乎总会先骂几句——``QPainter::begin: Paint device
returned engine == 0``、``QWidget::paintEngine: Should no longer be called``、
``QBackingStore::endPaint() called with active painter`` 之类。GUI 是 windowed
程序没有控制台，这些话平时全被丢掉；接进 ``crash.log`` 之后，崩之前的上下文
就能和栈一起看（2026-11-21 排查 ``QScreen::geometry`` 崩溃时加的）。

⚠️ 处理器里**只写文件**，不做任何可能重入 Qt 的事；写不进去就静默丢弃。
"""

from __future__ import annotations

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

from utils.crash_log import log

_LEVELS = {
    QtMsgType.QtDebugMsg: "debug",
    QtMsgType.QtInfoMsg: "info",
    QtMsgType.QtWarningMsg: "warn",
    QtMsgType.QtCriticalMsg: "critical",
    QtMsgType.QtFatalMsg: "fatal",
}


def _handler(mode, context, message) -> None:  # noqa: ANN001 - Qt 签名
    try:
        level = _LEVELS.get(mode, str(mode))
        where = ""
        if context is not None and getattr(context, "file", ""):
            where = f" ({context.file}:{context.line})"
        log(f"[qt:{level}] {message}{where}")
    except Exception:  # noqa: BLE001 - Qt 回调里不能再抛
        pass


def install() -> None:
    """装上处理器（幂等：Qt 侧本来就只留一个）。"""
    qInstallMessageHandler(_handler)
