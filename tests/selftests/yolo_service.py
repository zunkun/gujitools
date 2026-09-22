# -*- coding: utf-8 -*-
"""常驻 YOLO 服务自测：模型全局只加载一次、跨调用复用、失败必回落。

守的是这个特性的**承诺**与**底线**：

1. 首次预热真的把模型加载起来，且**如实报出用时**（不能报 0，否则客户端会
   误以为模型早就在内存里，日志里那句"加载 YOLO 模型完成: 用时 X s"再也不出现
   ——这就是开发时踩过的坑）；
2. 之后再用**不再加载**（backend 仍为 service、耗时为 0、同一个服务 pid）；
3. 端口发现文件与指纹一致，且**陈旧文件**（指向已死进程）不会把客户端卡死；
4. `GUJI_YOLO_SERVICE=0` 能一键关掉服务，且检测照样跑得通（回落本进程内）
   ——**服务不可用绝不能让检测不可用**；
5. 空闲超过 TTL 服务自行退出、把内存还掉。

⚠️ 本用例会真的拉起服务、真的加载 torch（数秒），并把 TTL 调小以便验证自退；
收尾必须把服务和环境变量都还原，否则会污染后续用例。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

NAME = "yolo_service"
DEPENDS: list[str] = []
TITLE = "常驻 YOLO 服务（模型全局只加载一次）"

#: 验证 TTL 自退用的服务空闲上限（服务 TTL 设为 TTL_PROBE，睡过它再查一次）
TTL_PROBE = 6.0


def _reset_client_state(ys) -> None:
    """清掉客户端模块级缓存，让下一步从零开始发现/拉起服务。

    ⚠️ 白盒操作：`_given_up` 是"本进程内已确认服务不可用"的止损标记，
    `_local.client` 是按线程缓存的连接。测完回落路径必须清，否则后续断言
    会一直被那个标记挡住。
    """
    ys._given_up = False
    ys._local.client = None


def run(ctx) -> None:
    import tempfile

    from PySide6.QtGui import QImage

    from functions import yolo_service as ys
    from functions.detect import detect_page_boxes_by_path
    from tests.selftests._context import ok

    tmp = Path(tempfile.mkdtemp(prefix="guji_yolosvc_"))
    saved_env = {
        key: os.environ.get(key)
        for key in ("GUJI_YOLO_SERVICE", "GUJI_YOLO_TTL")
    }
    # 本用例验的就是服务本身，显式打开开关（默认进程两个入口都不属于，
    # 归属由 cli.py=0 / desktop.py=1 在入口层决定）。
    os.environ["GUJI_YOLO_SERVICE"] = "1"
    try:
        # 造一张真实图片：服务是**按路径**读图的，所以必须落盘
        img_path = tmp / "probe.png"
        canvas = QImage(80, 120, QImage.Format.Format_RGB32)
        canvas.fill(0xFFFFFFFF)
        canvas.save(str(img_path))

        # ---- 清场：先把上一轮可能残留的服务收掉 ----
        ys.shutdown_service()
        time.sleep(1.5)
        _reset_client_state(ys)
        ok("清场后没有可用服务", ys.service_status() is None)

        # ---- 1. 首次预热：真的加载、且如实报用时 ----
        backend, seconds = ys.warm_up()
        ok("首次预热走常驻服务", backend == "service", str(backend))
        ok("首次预热如实报出加载用时（>0）", seconds > 0.1, f"seconds={seconds}")

        status = ys.service_status()
        ok("服务可用且模型已就绪", bool(status) and status.get("model_loaded"),
           str(status))
        first_pid = (status or {}).get("service_pid")

        found = ys._read_service_file(ys._fingerprint())
        ok("发现文件写入且指纹与本进程一致",
           found is not None and found[1] == ys._fingerprint(), str(found))

        # ---- 2. 真正做一次检测：服务代劳，served 递增 ----
        before = ys.service_status().get("served", 0)
        boxes = ys.detect_boxes_via_service(img_path)
        ok("服务可用时检测走服务（不是 None）", boxes is not None, str(boxes))
        after = ys.service_status().get("served", 0)
        ok("服务侧计数递增（确实由服务完成）", after > before,
           f"{before} → {after}")

        # ---- 3. 再预热一次：不再加载，同一个 pid ----
        backend2, seconds2 = ys.warm_up()
        ok("再次预热仍是服务后端", backend2 == "service", str(backend2))
        ok("再次预热不再加载模型（应得 0）", seconds2 == 0.0, f"seconds={seconds2}")
        ok("复用同一个服务进程",
           ys.service_status().get("service_pid") == first_pid,
           f"{first_pid} → {ys.service_status().get('service_pid')}")

        # ---- 4. 陈旧发现文件不得把客户端卡死 ----
        fp = ys._fingerprint()
        real_file = ys.service_file(fp)
        saved = real_file.read_text(encoding="utf-8")
        try:
            # 指向一个几乎不可能有人监听的端口
            real_file.write_text(
                json.dumps({"port": 9, "fp": ys._fingerprint(), "pid": 0}),
                encoding="utf-8",
            )
            ok("陈旧发现文件被识别为连不上", ys._try_connect(9, ys._fingerprint()) is None)
        finally:
            real_file.write_text(saved, encoding="utf-8")

        # ---- 5. 关掉服务也必须能检测（回落本进程内）----
        os.environ["GUJI_YOLO_SERVICE"] = "0"
        _reset_client_state(ys)
        ok("关掉服务后不再走服务", ys.detect_boxes_via_service(img_path) is None)
        fallback = detect_page_boxes_by_path(img_path)   # 本进程内加载
        ok("回落路径照样能返回检测结果（服务不可用 ≠ 检测不可用）",
           fallback is not None and len(fallback) == 2, str(fallback))
        os.environ.pop("GUJI_YOLO_SERVICE", None)
        _reset_client_state(ys)

        # ---- 6. TTL：空闲超时自行退出，把内存还掉 ----
        ys.shutdown_service()
        time.sleep(1.5)
        _reset_client_state(ys)
        os.environ["GUJI_YOLO_TTL"] = str(int(TTL_PROBE))
        backend3, _ = ys.warm_up()
        ok("短 TTL 下服务仍能拉起", backend3 == "service", str(backend3))
        ok("服务在跑", ys.service_status() is not None)

        # ⚠️ 这里**不能轮询**：任何一次请求（包括 status 查询）都会在服务侧
        #    `touch()` 空闲计时，观测行为本身就会让它永远不空闲——用例会假红。
        #    睡够 TTL + 余量之后查一次即可。
        time.sleep(TTL_PROBE + 5.0)
        ok(f"空闲超过 {TTL_PROBE:.0f}s 后服务自行退出（释放常驻内存）",
           ys.service_status() is None,
           "服务仍在运行 —— TTL 失效会导致 torch 运行时长期占着内存")
    finally:
        # 收尾：还原环境变量、收掉服务，别把状态留给后续用例
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        ys.shutdown_service()
        _reset_client_state(ys)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
