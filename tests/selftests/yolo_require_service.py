# -*- coding: utf-8 -*-
"""``GUJI_YOLO_REQUIRE_SERVICE`` 自测：GUI 主进程**禁止**加载 YOLO 模型。

背景（用户 2026-10-20 第二个问题 + AGENTS.md 分层守卫）
    常驻 YOLO 服务没走成时，``detect_page_content_by_path`` 原先会**回落**到
    本进程加载 torch（约 350MB）。GUI 主进程不该付这份代价，所以 ``desktop.py``
    的 GUI 分支置 ``GUJI_YOLO_REQUIRE_SERVICE=1``：此时宁可报错，也不把重依赖
    拽进界面进程。

钉住三条：
1. 服务关掉 + require 打开 ⇒ 抛 ``RuntimeError``，**不**在本进程加载模型；
2. 服务可达 + require 打开 ⇒ 正常走服务（``backend == "service"``）；
3. 两者都不置（CLI 口径）⇒ 行为与改造前一致（回落 in-process）。
"""

from __future__ import annotations

import os

NAME = "yolo_require_service"
DEPENDS: list[str] = ["yolo_service"]
TITLE = "GUI 主进程禁加载模型（GUJI_YOLO_REQUIRE_SERVICE）"

_ENV_KEYS = ("GUJI_YOLO_SERVICE", "GUJI_YOLO_REQUIRE_SERVICE")


def _reset_client_state(ys) -> None:
    """清掉客户端的止损标记与线程连接（同 `yolo_service` 用例的白盒操作）。"""
    ys._given_up = False
    ys._local.client = None


def _expect_runtime_error(fn) -> str:
    """调 ``fn``，必须抛 RuntimeError；返回异常文本（给断言看细节）。"""
    try:
        fn()
    except RuntimeError as exc:
        return str(exc)
    return ""


def run(ctx) -> None:
    import tempfile
    from pathlib import Path

    from PySide6.QtGui import QImage

    from functions import yolo_service as ys
    from functions.detect import detect_page_content_by_path, warm_up_detect_model
    from tests.selftests._context import ok

    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    tmp = Path(tempfile.mkdtemp(prefix="guji_require_"))
    try:
        img = tmp / "probe.png"
        canvas = QImage(80, 120, QImage.Format.Format_RGB32)
        canvas.fill(0xFFFFFFFF)
        canvas.save(str(img))

        # ---- 0. 开关本身的真假解析 ----
        os.environ.pop("GUJI_YOLO_REQUIRE_SERVICE", None)
        ok("不设 GUJI_YOLO_REQUIRE_SERVICE 时默认不要求服务",
           ys.require_service() is False)
        os.environ["GUJI_YOLO_REQUIRE_SERVICE"] = "0"
        ok("'0' 视为不要求", ys.require_service() is False)
        os.environ["GUJI_YOLO_REQUIRE_SERVICE"] = "1"
        ok("'1' 视为要求", ys.require_service() is True)

        # ---- 1. 服务关掉 + require ⇒ 报错，不加载模型 ----
        os.environ["GUJI_YOLO_SERVICE"] = "0"
        _reset_client_state(ys)
        msg = _expect_runtime_error(lambda: detect_page_content_by_path(img))
        ok("服务不可用且 require ⇒ 抛 RuntimeError（不回落加载 torch）",
           bool(msg) and "GUJI_YOLO_REQUIRE_SERVICE" in msg, msg or "没有抛错")
        msg = _expect_runtime_error(warm_up_detect_model)
        ok("warm_up_detect_model 同样拒绝在本进程加载", bool(msg), msg or "没有抛错")

        # ---- 2. 服务可达 + require ⇒ 正常走服务 ----
        os.environ["GUJI_YOLO_SERVICE"] = "1"
        _reset_client_state(ys)
        line, seconds = warm_up_detect_model()
        ok("require + 服务可达 ⇒ 预热走常驻服务",
           "常驻" in line, line)
        ok("预热报出加载用时（≥0）", seconds >= 0.0, f"seconds={seconds}")
        page = detect_page_content_by_path(img)
        from functions.detect import last_detect_report

        ok("检测走服务后端", last_detect_report().backend == "service",
           last_detect_report().backend)
        ok("返回了检测结果对象", page is not None, str(page))

        # ---- 3. 都不置（CLI 口径）⇒ 回落 in-process ----
        ys.shutdown_service()
        _reset_client_state(ys)
        os.environ.pop("GUJI_YOLO_REQUIRE_SERVICE", None)
        os.environ["GUJI_YOLO_SERVICE"] = "0"
        line, _ = warm_up_detect_model()
        ok("CLI 口径下预热回落本进程（行为不变）",
           "本进程内" in line, line)
        ok("CLI 口径下检测仍可用", detect_page_content_by_path(img) is not None)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        ys.shutdown_service()
        _reset_client_state(ys)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
