# -*- coding: utf-8 -*-
"""BPM 界面的**真界面截图**（离屏，中文字体已注册）。

把"代码里做的东西"变成"眼睛能看到的证据"：

    bpm-1-任务列表-创建任务入口.png        列表页右上角的「创建任务」按钮
    bpm-2-创建任务弹窗-未勾选-显示默认流程.png
                                           用户要求：不勾自定义也要看到当前流程
    bpm-3-创建任务弹窗-勾选-显示自定义流程.png
    bpm-4-流程编辑器-工具栏与选中.png        工具栏 + 选中节点后的状态行
    bpm-5-流程编辑器-连线模式.png            点「连线」后点起点→点终点
    bpm-6-详情页-查看编辑流程弹窗.png        详情页入口进来的样子

⚠️ **离屏截图绝不真弹模态 ``exec()``**（会挂住整个进程）。这里把面板内容挂进
一个普通 ``QWidget`` 窗口来拍——同一个控件实例、同一套布局，视觉与真弹窗一致。

用法::

    QT_QPA_PLATFORM=offscreen python tests/bpm_shot.py [输出目录]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 测试临时文件统一落点：tests/tmp/（见 tests/tmpdir.py）。
from tests.tmpdir import install as _install_tmpdir  # noqa: E402

_install_tmpdir()

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_bpm_shots")
OUT.mkdir(parents=True, exist_ok=True)


def register_cjk_font() -> None:
    """把系统中文字体注册进 QFontDatabase。

    offscreen 平台插件拿不到系统字体库，不注册的话截图里全是豆腐块——
    看图的人会误以为布局有问题。
    """
    for name in ("msyh.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc"):
        path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
            return


def pump(app: QApplication, times: int = 12) -> None:
    for _ in range(times):
        app.processEvents()
        time.sleep(0.02)


def shoot(app: QApplication, widget: QWidget, name: str, size=(1180, 780)) -> str:
    """把控件铺到固定尺寸的窗口里拍一张。"""
    host = QWidget()
    host.setWindowTitle(name)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    widget.setParent(host)
    layout.addWidget(widget)
    host.resize(*size)
    host.show()
    pump(app, 18)
    path = OUT / f"{name}.png"
    host.grab().save(str(path))
    print(f"  ✓ {path.name}  ({host.width()}x{host.height()})")
    host.deleteLater()
    pump(app, 4)
    return str(path)


def main() -> int:
    app = QApplication(sys.argv[:1])
    register_cjk_font()

    # ---- ① 任务列表页：右上角的「创建任务」入口 --------------------------
    print("拍 ① 任务列表（创建任务入口）")
    from desktop.store import TaskStore
    from desktop.pages.tasklist.page import TaskListPage

    store = TaskStore(Path(tempfile.mkdtemp(prefix="bpm_shot_")) / "data")
    list_page = TaskListPage(store)
    shoot(app, list_page, "bpm-1-任务列表-创建任务入口")

    # ---- ② 创建任务弹窗：**未勾选**也必须显示默认流程 --------------------
    print("拍 ② 创建任务弹窗（未勾选 → 显示默认流程）")
    from desktop.components.create_task_dialog import CreateTaskPanel

    panel_default = CreateTaskPanel()
    shoot(app, panel_default, "bpm-2-创建任务弹窗-未勾选-显示默认流程",
          size=(980, 760))

    # ---- ③ 创建任务弹窗：勾选后显示自定义流程 ---------------------------
    print("拍 ③ 创建任务弹窗（勾选 → 显示自定义流程）")
    panel_custom = CreateTaskPanel()
    panel_custom.set_custom_mode(True)
    pump(app, 8)
    shoot(app, panel_custom, "bpm-3-创建任务弹窗-勾选-显示自定义流程",
          size=(980, 760))

    # ---- ④⑤ 流程编辑器：工具栏 + 选中 + 连线模式 ------------------------
    from desktop.components.flow_dialog import FlowPanel
    from desktop.components.create_task_dialog import load_custom_init

    diagram = load_custom_init()

    print("拍 ④ 流程编辑器（工具栏与选中）")
    editor_panel = FlowPanel(diagram)
    shoot(app, editor_panel, "bpm-4-流程编辑器-工具栏与选中", size=(1060, 780))
    board = editor_panel.editor_panel
    canvas = board.editor()
    if canvas is not None and canvas.diagram().nodes:
        # 选中第一个任务节点：状态行与「重命名/删除」按钮会跟着变化
        task = next((n for n in canvas.diagram().nodes
                     if n.kind == "task"), canvas.diagram().nodes[0])
        canvas.set_selected(task.id)
        board._sync_status()
        pump(app, 6)
        shoot(app, editor_panel, "bpm-4b-流程编辑器-选中节点", size=(1060, 780))

    print("拍 ⑤ 流程编辑器（连线模式：点起点 → 点终点）")
    editor_link = FlowPanel(load_custom_init())
    shoot(app, editor_link, "bpm-5-流程编辑器-初始", size=(1060, 780))
    board2 = editor_link.editor_panel
    canvas2 = board2.editor()
    if canvas2 is not None:
        board2.link_button.click()          # 进连线模式
        pump(app, 6)
        tasks = [n for n in canvas2.diagram().nodes if n.kind == "task"]
        if len(tasks) >= 2:
            canvas2._on_press(_press_event(canvas2, tasks[0].id))
            canvas2._on_press(_press_event(canvas2, tasks[1].id))
        board2._sync_status()
        pump(app, 6)
        shoot(app, editor_link, "bpm-5-流程编辑器-连线模式", size=(1060, 780))

    # ---- ⑥ 详情页入口进来的样子（同一控件，另一份图）--------------------
    print("拍 ⑥ 详情页「查看/编辑流程」弹窗")
    store2 = TaskStore(Path(tempfile.mkdtemp(prefix="bpm_shot2_")) / "data")
    pdf = Path(tempfile.mkdtemp(prefix="bpm_pdf_")) / "样例.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    tid = store2.create_task(pdf, "h", "样例任务", diagram=diagram)
    detail_panel = FlowPanel(store2.task_diagram(tid))
    shoot(app, detail_panel, "bpm-6-详情页-查看编辑流程弹窗", size=(1060, 780))

    print(f"\n全部截图在：{OUT}")
    return 0


def _press_event(canvas, node_id):
    """造一个落在节点中心的左键按下事件（离屏下直调，别用 QTest）。"""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    center = canvas.rect_of(node_id).center()
    pos = QPointF(center.x(), center.y())
    return QMouseEvent(QEvent.Type.MouseButtonPress, pos,
                       canvas.mapToGlobal(pos.toPoint()),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


if __name__ == "__main__":
    raise SystemExit(main())
