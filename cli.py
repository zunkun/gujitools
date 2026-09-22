"""

gujitools 命令行入口（CLI entry）。

古籍处理命令行工具（gujitools），提供 PDF 提取、文本区域检测/裁剪、去底色等功能。

入口职责:
- 注册 SIGINT (Ctrl+C) 信号处理，实现优雅中断；
- 调用 CLI 层的 `cli_main()` 进行命令解析与功能分发。

启动方式:
    python cli.py <command> [options]
    或 `python -m cli <command> [options]`（走 cli/__main__.py，同一份实现）
    或打包后: guji <command> [options]

命名说明：顶层入口与 GUI 侧对齐——`cli.py` / `desktop.py` 是**两个平行的可执行
入口**，CLI 的实现体在 `cli/` 包里（`cli/__main__.py`），桌面端在 `desktop/` 包里。
不叫 `main.py` 是因为本程序有 cli 与 desktop 两个入口，"main" 说不清是哪一个。
"""

import os
import signal
import sys

# ⚠️ CLI **不使用**常驻 YOLO 服务（原则：cli 与 desktop 是两套系统，内存不互通）。
# CLI 的每次执行都是一次性任务：模型在本进程内加载、进程退出即释放，不占常驻内存。
# 常驻服务只属于 desktop（见 desktop.py，它会把 GUJI_YOLO_SERVICE 置 1 并传给
# 自己的 worker 子进程）。这里显式置 0，防止任何函数层代码误把 CLI 的检测交给
# 常驻服务。
os.environ["GUJI_YOLO_SERVICE"] = "0"

# Windows 上 stdout/stderr 默认编码为 cp936(GBK)，IDE 集成终端按 UTF-8 解码
# 会导致中文乱码。启动时强制重配置为 UTF-8。
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

from cli.__main__ import main as cli_main


def main() -> None:
    """程序主入口：注册信号处理并委托给 CLI 层。"""

    # 捕获 Ctrl+C，避免打印 traceback
    def _handle_sigint(signum, frame):
        print("\n中断：已收到退出信号，正在终止...")
        sys.exit(130)

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception:
        # 某些平台（如部分 Windows 控制台）不支持 signal 注册
        pass

    # 委托给 CLI 层执行命令解析与功能分发，并将其退出码透传给进程
    sys.exit(cli_main())


if __name__ == "__main__":
    main()
