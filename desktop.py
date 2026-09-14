"""gujitools 桌面端与 worker 统一入口。

- 启动 GUI：            python desktop.py   （或 hupper -m desktop 热重载开发）
- 子进程执行单个子任务： python desktop.py --worker --config <json>
"""

import os
import sys

# Windows + Anaconda 环境常见 OpenMP 运行时重复，默认兜底放行
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def main() -> int:
    """桌面端统一入口：按参数路由到 GUI 或 worker 子进程。

    若命令行含 --worker 则作为 GUI 子进程执行 desktop.worker.main()，
    否则启动 GUI（desktop.app.main()）。返回值为进程退出码。
    """
    if "--worker" in sys.argv:
        from desktop.worker import main as worker_main

        return worker_main()

    from desktop.app import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
