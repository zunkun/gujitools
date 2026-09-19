# -*- coding: utf-8 -*-
"""worker 信号的**线程归属**自测：跨线程槽必须排队回主线程。

背景（真实 bug）：PySide6 里 ``signal.connect(lambda ...)`` 是**直接连接**
——lambda 没有接收者 QObject，Qt 无从判断它属于哪个线程，于是槽就在
emit 的那个（worker）线程里执行。缩略图加载的
``worker.thumbnail_ready.connect(lambda ...: strip.set_item_icon(...))``
正是这种写法：每张缩略图都在子线程里动 QListWidget，Qt 内部随之在子线程
启动定时器，控制台刷屏
``QBasicTimer::start: Timers cannot be started from another thread``。

本模块守住三条不变量：

1. ``connect_queued`` 存在且导出（跨线程连接的唯一入口）；
2. **运行时实证**：真起一个 worker 线程，经 ``connect_queued`` 的槽必须
   跑在主线程；而 ``connect(lambda)`` 的槽确实跑在子线程（坑存在的证明）；
3. **端到端**：``ThumbsMixin._load_thumbs`` 真跑一遍，``set_item_icon``
   必须在主线程被调用，且全程不出现 QBasicTimer 警告。
"""

NAME = "worker_thread_affinity"
DEPENDS: list[str] = []
TITLE = "worker 信号线程归属（跨线程必须排队）"

#: 各类 worker 的信号名（静态扫描用）
WORKER_SIGNALS = {
    "thumbnail_ready", "finished", "failed", "completed", "metadata",
}


def run(ctx) -> None:
    import tempfile
    import time
    from pathlib import Path

    from PySide6.QtCore import QThread, qInstallMessageHandler
    from PySide6.QtGui import QImage, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from tests.selftests._context import ok

    app = QApplication.instance()
    main_thread = app.thread()

    def on_main() -> bool:
        return QThread.currentThread() is main_thread

    # ---- 1. connect_queued 是唯一入口且已导出 ----
    from desktop.workers import connect_queued
    from desktop.workers.worker_host import connect_queued as cq2

    ok("connect_queued 从 desktop.workers 导出", connect_queued is cq2)
    ok("connect_queued 签名是 (owner, signal, slot, thread=None)",
       list(connect_queued.__code__.co_varnames[:4])
       == ["owner", "signal", "slot", "thread"],
       str(connect_queued.__code__.co_varnames[:4]))

    # ---- 2. 运行时实证：排队 vs 直接 ----
    from desktop.workers import ImageListWorker, WorkerHost

    tmp = Path(tempfile.mkdtemp(prefix="guji_affinity_"))
    try:
        paths = []
        for index, (w, h) in enumerate([(120, 90), (90, 120), (100, 100)]):
            img = QImage(w, h, QImage.Format.Format_RGB32)
            img.fill(0xFF334455)
            path = tmp / f"p{index}.png"
            img.save(str(path))
            paths.append(path)

        class _Host(QWidget, WorkerHost):
            def __init__(self):
                super().__init__()
                self._init_worker_host()

        host = _Host()
        try:
            seen_queued: list[bool] = []
            seen_direct: list[bool] = []
            host.run_worker(
                lambda: ImageListWorker(paths, edge=64),
                lambda worker, thread: (
                    # 排队写法：槽必须回到主线程
                    connect_queued(
                        host,
                        worker.thumbnail_ready,
                        lambda _i, _img, _p: seen_queued.append(on_main()),
                        thread,
                    ),
                    # 故意保留的"错误写法"：证明它确实跑在子线程
                    worker.thumbnail_ready.connect(
                        lambda *_a: seen_direct.append(on_main())
                    ),
                    worker.completed.connect(thread.quit),
                    worker.failed.connect(thread.quit),
                ),
            )
            deadline = time.time() + 15
            while time.time() < deadline and (
                len(seen_queued) < len(paths)
                or len(seen_direct) < len(paths)
            ):
                app.processEvents()
                time.sleep(0.02)
            ok("connect_queued：槽全部跑在主线程",
               len(seen_queued) == len(paths) and all(seen_queued),
               f"{seen_queued}")
            ok("反例成立：connect(lambda) 的槽跑在子线程（坑确实存在）",
               len(seen_direct) == len(paths) and not any(seen_direct),
               f"{seen_direct}")
        finally:
            host.shutdown_workers()
            host.deleteLater()

        # ---- 3. 端到端：_load_thumbs 期间 set_item_icon 必须在主线程 ----
        from desktop.components.viewers.image_viewer import ImageViewerWidget
        from desktop.components.viewers.thumb_strip import ThumbStrip

        warnings: list[str] = []

        def _handler(mode, context, message):
            if "QBasicTimer" in message or "Timers cannot" in message:
                warnings.append(message)

        qInstallMessageHandler(_handler)
        widget = ImageViewerWidget()
        original = ThumbStrip.set_item_icon
        observed: list[bool] = []

        def _spy(self, index, image, path, label):
            observed.append(on_main())
            original(self, index, image, path, label)

        ThumbStrip.set_item_icon = _spy
        try:
            widget._load_thumbs(widget.strip, paths)
            deadline = time.time() + 15
            while time.time() < deadline and len(observed) < len(paths):
                app.processEvents()
                time.sleep(0.02)
            ok("端到端：缩略图回调 set_item_icon 全在主线程",
               len(observed) == len(paths) and all(observed),
               f"{observed}")
            ok("端到端：全程无 QBasicTimer 跨线程警告",
               not warnings, "; ".join(warnings[:3]))
        finally:
            ThumbStrip.set_item_icon = original
            widget.shutdown_workers()
            widget.deleteLater()
            qInstallMessageHandler(None)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 4. 静态扫描：worker 信号不得再直连 lambda ----
    import re
    from pathlib import Path as _P

    offenders = []
    root = _P(__file__).resolve().parents[2] / "desktop"
    for file in root.rglob("*.py"):
        if "__pycache__" in str(file):
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(
            r"\.(\w+)\.connect\(\s*lambda", text
        ):
            if match.group(1) in WORKER_SIGNALS:
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{file.relative_to(root)}:{line}")
    ok("静态扫描：worker 信号无直连 lambda（须用 connect_queued）",
       not offenders, "; ".join(offenders[:5]))
