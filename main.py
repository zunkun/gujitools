"""

gujitools 程序主入口。

古籍处理命令行工具（gujitools），提供 PDF 提取、文本区域检测/裁剪、去底色等功能。

入口职责:
- 注册 SIGINT (Ctrl+C) 信号处理，实现优雅中断；
- 调用 CLI 层的 `cli_main()` 进行命令解析与功能分发。

启动方式:
    python main.py <command> [options]
    或打包后: guji <command> [options]
"""

import signal
import sys
from typing import TextIO

# Windows 上 stdout/stderr 默认编码为 cp936(GBK)，IDE 集成终端按 UTF-8 解码
# 会导致中文乱码。启动时强制重配置为 UTF-8。
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        # if not isinstance(_stream, TextIO):
        #     continue

        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

from cli.cli import main as cli_main


def main() -> None:
    """程序主入口：注册信号处理并委托给 CLI 层。"""

    # 捕获 Ctrl+C，避免打印 traceback
    def _handle_sigint(signum, frame):
        print("\n中断：已收到退出信号，正在终止...")
        sys.exit(1)

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception:
        # 某些平台（如部分 Windows 控制台）不支持 signal 注册
        pass

    # 委托给 CLI 层执行命令解析与功能分发
    cli_main()


if __name__ == "__main__":
    main()
