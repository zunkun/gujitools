# -*- coding: utf-8 -*-
"""单页实时去底色的后台 worker（第三步「改参数实时预览」专用）。

与 ``PreviewWorker`` 的分工：那个只负责**显示**（读图 / 按区域裁剪 / 缩放），
本 worker 负责**计算**（真正的去底色）。二者接力：本 worker 先把结果落到
临时目录，预览区再按 ``live_dir`` 找到它并走原有的显示管线。

去底色对整页图（数千像素）要百毫秒级 CPU，放主线程会卡住界面，因此一律
丢到 QThread 里跑。结果通过 token 回传，宿主据此丢弃"已经过期的"结果
（用户连拖两次滑块时，慢的那次回来得晚，不能覆盖新的）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class RembgLiveWorker(QObject):
    """一次性 worker：单页去底色 → 写临时文件。"""

    #: (token, 结果图片路径)
    finished = Signal(object, str)
    #: (token, 错误信息)
    failed = Signal(object, str)

    def __init__(self, image_path: str, args: dict, out_dir: str, token: object) -> None:
        """参数:
        image_path: 待去底色的源图（extract 产物）。
        args: rembg 面板收集的参数（offset/type/seal/…）。
        out_dir: 实时暂存目录（``services.rembg_live.live_dir``）。
        token: 本次请求的标识，供宿主判断结果是否已过期。
        """
        super().__init__()
        self._image_path = image_path
        self._args = dict(args)
        self._out_dir = out_dir
        self._token = token

    def run(self) -> None:
        """线程入口：算完发 finished，异常发 failed（不抛到线程外）。"""
        try:
            from desktop.services.rembg_live import render_page

            out_path = render_page(self._image_path, self._args, self._out_dir)
        except Exception as exc:  # noqa: BLE001 — 子线程异常必须回传主线程
            self.failed.emit(self._token, f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self._token, out_path)
