# -*- coding: utf-8 -*-
"""单页实时去底色的后台 worker（任务详情第三步「改参数/翻页」专用）。

只负责**计算 + 落临时目录**供查看器显示；正式产物（``stages/rembg``）仍由
「执行去底色」的 worker 子进程独占写入，实时预览不碰它。

结果通过 token 回传，宿主据此丢弃"已经过期的"结果（用户连拖两次滑块时，
慢的那次回来得晚，不能覆盖新的）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class RembgLiveWorker(QObject):
    """一次性 worker：单页去底色 → 临时预览目录。"""

    #: (token, 结果图片路径)——空路径表示该单已被取消
    finished = Signal(object, str)
    #: (token, 错误信息)
    failed = Signal(object, str)

    def __init__(self, image_path: str, args: dict, out_dir: str,
                 token: object) -> None:
        super().__init__()
        self._image_path = image_path
        self._args = dict(args)
        self._out_dir = out_dir
        self._token = token
        self._cancelled = False

    def cancel(self) -> None:
        """请求放弃计算。token 守卫只丢结果，这里额外让线程尽早返回，省算力。"""
        self._cancelled = True

    def run(self) -> None:
        """线程入口：算完发 finished，异常发 failed（不抛到线程外）。

        ⚠️ 取消路径也必须发终态信号，否则线程事件循环永不退出。
        ⚠️ ``QThread.run()`` 必须 try/except：异常逃出线程＝"点了没反应"。
        """
        if self._cancelled:
            self.finished.emit(self._token, "")
            return
        try:
            from desktop.services.rembg_live import render_page

            out_path = render_page(self._image_path, self._args, self._out_dir)
        except Exception as exc:  # noqa: BLE001 — 子线程异常必须回传主线程
            self.failed.emit(self._token, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self._token, out_path)
