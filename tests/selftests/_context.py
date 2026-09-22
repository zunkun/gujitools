# -*- coding: utf-8 -*-
"""自测共享设施：断言计数、样例文件、夹具构建、单模块看门狗。

原先 gui_selftest 是 800+ 行单文件，每次都要整体读取、整体执行；现按
功能拆到本包的一组小模块。模块之间不直接互相引用，只通过 ``Context``
取共享夹具（QApplication/主窗口/任务仓库/样例 PDF）与传递跨模块状态
（主任务 id、插入图路径、注入的检测框等）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    """断言并计数：失败抛 AssertionError（携带细节），成功打印 PASS。"""
    global PASS
    if not condition:
        raise AssertionError(f"[FAIL] {name} {detail}")
    PASS += 1
    print(f"  [PASS] {name}")


def make_pdf(path: Path, pages: int, text_prefix: str = "第") -> Path:
    """生成 pages 页的极简 PDF（每页一行占位文字）。"""
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text_prefix} {i + 1} 页 测试内容")
    doc.save(str(path))
    doc.close()
    return path


def wait_worker(page, app, timeout: float = 180.0) -> int:
    """等待阶段子进程退出，返回退出码。

    注意：只看 QProcess 状态——进程退出时最后一条 finished 事件（才带
    最终 done 值）可能还排在事件队列里，调用方需要按目标值继续轮询。
    """
    deadline = time.time() + timeout
    while page.process and page.process.state() != 0 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    return page.process.exitCode() if page.process else 0


def pump(app, times: int = 6, interval: float = 0.05) -> None:
    """驱动事件循环一小段时间（等信号/异步加载落地）。"""
    for _ in range(times):
        app.processEvents()
        time.sleep(interval)


def wait_until(app, condition, timeout: float = 5.0, interval: float = 0.02) -> bool:
    """驱动事件循环直到 ``condition()`` 成立或超时，返回最终是否成立。

    列表刷新这类**后台线程读盘**的流程是异步的，断言前必须等它回来；
    固定 pump 若干次在慢机器上会偶发失败。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(interval)
    return condition()


class Context:
    """跨模块共享的夹具与状态。

    prepare() 在第一个模块执行前调用一次；各模块产生的跨模块状态直接
    挂在实例属性上（见各属性注释）。
    """

    def __init__(self) -> None:
        self.app = None
        self.w = None            # MainWindow
        self.d = None            # 任务详情页（w.detail_page 别名）
        self.repo = None         # 重定向到临时目录的 TaskStore
        self.tmp: Path | None = None
        self.pdf: Path | None = None      # 6 页样例 PDF
        self.big_pdf: Path | None = None  # 80 页样例 PDF
        # —— 模块间传递的状态 ——
        self.tid: str | None = None             # tasklist 创建的主任务
        self.tid_dup: str | None = None         # 同指纹重复任务（task_delete 删）
        self.tid_big: str | None = None         # resume 创建的大部头任务
        self.inserted_img: Path | None = None   # pages 插入清单的外部图
        self.injected_boxes = None              # rembg 注入的确定性检测框
        self.preview_dir = None                 # rembg 预览目录（print 断言用）

    def prepare(self) -> None:
        """构建 QApplication + 主窗口，并把数据目录重定向到临时目录。"""
        import tempfile

        from PySide6.QtWidgets import QApplication

        from desktop.app import MainWindow
        from desktop.store import TaskStore

        self.tmp = Path(tempfile.mkdtemp(prefix="guji_selftest_"))
        print(f"工作目录：{self.tmp}")
        self.pdf = make_pdf(self.tmp / "古籍样例.pdf", 6)
        self.big_pdf = make_pdf(self.tmp / "大部头.pdf", 80)

        self.app = QApplication([])
        self.w = MainWindow()
        self.w.close()  # 重定向数据目录到临时目录
        self.repo = TaskStore(self.tmp)
        self.w.store = self.repo
        self.w.list_page.store = self.repo
        self.w.detail_page.store = self.repo
        self.d = self.w.detail_page


def show_detail(ctx, stage: int = 0, size: tuple[int, int] = (1080, 720)):
    """真正把详情页显示出来并切到指定阶段，返回该阶段的控制面板。

    必须这样做才能测布局：QStackedWidget 里没被选中的页面从未参与布局，
    其中的 qfluentwidgets ScrollArea 是懒构建的——未显示时 layout() 为
    None、viewport/inner 全是 480x640 之类的脏默认值，据此断言的「有没
    有滚动条」结论都是假的。真显示后 inner=302、viewport=81、vbarMax=221。
    """
    from PySide6.QtWidgets import QStackedWidget

    app, w, d = ctx.app, ctx.w, ctx.d
    pages = w.findChild(QStackedWidget, "pageRoot")
    if pages is not None:
        pages.setCurrentWidget(d)
    w.resize(*size)
    w.show()
    pump(app, times=12)
    d._select_stage(stage)
    pump(app, times=12)
    return d.control_stack.widget(stage)


def install_module_watchdog(app, state: dict, limit: float):
    """按模块计时的看门狗，返回 arm(module_name) 函数。

    QTimer 在任何事件循环（包括模态 exec）里都会触发，因此模块内若有
    控件卡进模态/死循环，超时后打印模块名并 os._exit(3)，避免整条测试
    无声挂起（真实发生过：整条测试卡在续跑段 20+ 分钟无输出）。
    """
    from PySide6.QtCore import QTimer

    def _fire() -> None:
        print(
            f"\n[看门狗] 模块 {state.get('module')} 超过 {limit:.0f}s 未完成，"
            "疑似卡死，强制退出（可用 --module-timeout 调整）"
        )
        os._exit(3)

    timer = QTimer(app)
    timer.setSingleShot(True)
    timer.timeout.connect(_fire)
    state["timer"] = timer

    def arm(module: str) -> None:
        state["module"] = module
        timer.start(int(limit * 1000))

    return arm
