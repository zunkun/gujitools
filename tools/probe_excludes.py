# -*- coding: utf-8 -*-
"""在开发环境模拟 PyInstaller 的 excludes，快速判定哪些模块不能排。

打包一轮要 20 分钟，靠反复重建去试 excludes 太慢。这里用 sys.meta_path 装一个
导入阻塞器，让指定的模块名抛 ModuleNotFoundError，效果和 PyInstaller 排除后
运行时找不到模块基本一致，然后跑**两条真实链路**验证：

  CLI 链：import torch → torchvision → ultralytics → YOLO 推理
  GUI 链：import qfluentwidgets → qframelesswindow → win32_utils（win32api！）

⚠️ **两条链都必须跑**。曾经只跑 CLI 链，把 pywin32（win32api）判成"可安全排除"
写进 guji.spec，结果 GUI 启动即崩 ModuleNotFoundError: No module named 'win32api'
——因为 qframelesswindow/utils/win32_utils.py 第 9 行顶层 `import win32api`，
而 torch 那边的 pywin32 只是函数内导入、确实不触发。

关键：每个候选项都在**独立子进程**里测。同一个进程里第二次 `import torch`
会命中 sys.modules 缓存，导致后续测试形同虚设。

用法：
    python tools/probe_excludes.py                     # 测 guji.spec 里的排除项
    python tools/probe_excludes.py torch.onnx,torch.ao # 测指定项
    python tools/probe_excludes.py --one torch.onnx    # 单次（子进程内部用）
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEFAULT_CANDIDATES = [
    "torch.testing",
    "torch._inductor",
    "torch.distributed",
    "torch._dynamo",
    "torch.onnx",
    "torch._export",
    "torch._functorch",
    "torch.profiler",
    "torch.distributions",
    "torch._higher_order_ops",
    "torch._prims",
    "torch._refs",
]


class Blocker:
    """让指定前缀的模块无法导入。"""

    def __init__(self, names):
        self.names = tuple(names)

    def find_spec(self, fullname, path=None, target=None):
        for n in self.names:
            if fullname == n or fullname.startswith(n + "."):
                raise ModuleNotFoundError(f"No module named {fullname!r} (blocked)")
        return None


def _import_gui_chain() -> None:
    """GUI 导入链：qfluentwidgets 会经 qframelesswindow 顶层 import win32api。

    这是 GUI 启动的必经之路，任何排除项都必须能过这一关。
    用 offscreen 平台，避免子进程真的弹窗。
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # 组件树：button → menu → qframelesswindow → win32_utils（win32api 在这里）
    import qfluentwidgets  # noqa: F401
    from qfluentwidgets import (  # noqa: F401
        FluentWindow, PushButton, ComboBox, LineEdit, SpinBox, TableWidget,
        CardWidget, MessageBox, InfoBar, SubtitleLabel, BodyLabel,
    )
    from PySide6.QtWidgets import QApplication  # noqa: F401

    app = QApplication.instance() or QApplication([])
    # 真造一个窗口，触发 TitleBar / 无边框窗口的 win32 初始化分支
    win = FluentWindow()
    win.destroy(True, True)


def run_chain() -> tuple[bool, str]:
    """跑 CLI 链 + GUI 链，返回（是否成功, 说明）。两条都必须过。"""
    try:
        import numpy as np
        import torch  # noqa: F401
        import torchvision  # noqa: F401
        from ultralytics import YOLO

        weights = Path("weights/detect.pt")
        if weights.is_file():
            model = YOLO(str(weights))
            model.predict(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False)
    except ModuleNotFoundError as exc:
        return False, f"[CLI 链] ModuleNotFoundError: {exc}"
    except Exception as exc:  # noqa: BLE001
        # 只关心「模块找不到」；其它异常（如模型结构问题）与 excludes 无关
        pass

    try:
        _import_gui_chain()
    except ModuleNotFoundError as exc:
        return False, f"[GUI 链] ModuleNotFoundError: {exc}"
    except Exception as exc:  # noqa: BLE001
        return True, f"[GUI 链] 非 ImportError（{type(exc).__name__}: {exc}）"

    return True, ""


def run_one(blocked: list[str]) -> tuple[bool, str]:
    """在独立子进程里测一组排除项。"""
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", ",".join(blocked)]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "").strip()
    return proc.returncode == 0, out


def main() -> int:
    args = sys.argv[1:]

    if args and args[0] == "--one":
        blocked = [x for x in (args[1] if len(args) > 1 else "").split(",") if x]
        sys.meta_path.insert(0, Blocker(blocked))
        ok, detail = run_chain()
        print(detail)
        return 0 if ok else 1

    candidates = ([x.strip() for x in args[0].split(",") if x.strip()]
                  if args else list(DEFAULT_CANDIDATES))

    print(f"待测排除项（{len(candidates)} 个），每项独立子进程：")
    print(f"  {', '.join(candidates)}\n")

    print("[1] 全部一起排除：")
    ok_all, detail_all = run_one(candidates)
    print(f"    {'✅ 通过' if ok_all else '❌ 失败'}" + (f"  {detail_all}" if detail_all else ""))

    print("\n[2] 逐项独立排除：")
    bad = []
    for name in candidates:
        ok_i, detail_i = run_one([name])
        if ok_i:
            print(f"    ✅ 可排除  {name}")
        else:
            print(f"    ❌ 不可排  {name}  ←  {detail_i}")
            bad.append(name)

    print()
    if ok_all:
        print("✅ 全部排除可用，无需调整 guji.spec")
        return 0
    if bad:
        print(f"⚠️ 必须从 excludes 移除（会导致运行时 ImportError）：")
        for b in bad:
            print(f"    - {b}")
        return 1
    print("⚠️ 单项都可排、组合失败：属于组合效应，需要缩小范围再测")
    return 1


if __name__ == "__main__":
    sys.exit(main())
