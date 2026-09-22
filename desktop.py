"""gujitools 桌面端与 worker 统一入口。

- 启动 GUI：            python desktop.py   （或 hupper -m desktop 热重载开发）
- 子进程执行单个子任务： python desktop.py --worker --config <json>
"""

import os
import sys

# Windows + Anaconda 环境常见 OpenMP 运行时重复，默认兜底放行
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def _prepare_gui_startup() -> None:
    """GUI 启动前的降本处理——必须在 ``import qfluentwidgets`` 之前跑。

    目前只做一件事：用轻量 stub 顶掉 ``darkdetect``。

    qfluentwidgets 顶层会 ``import darkdetect``，而它在 Windows 上首次导入要
    初始化 Windows Runtime 去读系统主题，**实测 294ms**（第二次导入只要 1.3ms）。
    本项目的主题是写死的（``desktop.app.main()`` 里 ``setTheme(Theme.LIGHT)``），
    探测结果根本不会被采纳，这笔钱是白花的。

    stub 覆盖 qfluentwidgets 实际用到的四个入口：

    - ``theme()`` → 恒为 ``"Light"``。注意 ``qconfig.theme`` 的 setter 会拿它
      去 ``Theme(t)``，所以必须是 "Light"/"Dark" 这种字面量，不能返回 None；
    - ``isDark()`` / ``isLight()``；
    - ``listener(cb)`` → 空实现（``SystemThemeListener.run()`` 在 win32 分支会
      调它并阻塞，而我们不需要跟随系统主题变化）。

    ⚠️ 写进 ``sys.modules`` 后会**永久屏蔽**真实的 darkdetect（之后的 import
    不再执行模块体），所以只在 GUI 分支调用，worker 子进程不受影响。
    """
    import types

    if "darkdetect" in sys.modules:
        return
    stub = types.ModuleType("darkdetect")
    stub.theme = lambda: "Light"
    stub.isDark = lambda: False
    stub.isLight = lambda: True
    stub.listener = lambda callback=None: None
    sys.modules["darkdetect"] = stub


def main() -> int:
    """桌面端统一入口：按参数路由到 GUI 或 worker 子进程。

    若命令行含 --worker 则作为 GUI 子进程执行 desktop.worker.main()，
    否则启动 GUI（desktop.app.main()）。返回值为进程退出码。
    """
    # 常驻 YOLO 服务**只属于 desktop 侧**（原则：cli 与 desktop 是两套系统、内存
    # 不互通；CLI 在自己的入口 cli.py 里显式置 0，一次性任务用完即释放）。
    # 在这里 setdefault，GUI 进程与它派生的所有 worker 子进程都会带上这个标记，
    # 检测于是交给常驻服务、模型全局只加载一次。用 setdefault 而非直接赋值：
    # 外部显式设 0 仍可整体关掉（排障用）。
    os.environ.setdefault("GUJI_YOLO_SERVICE", "1")

    if "--yolo-service" in sys.argv:
        # 常驻 YOLO 服务进程：desktop 侧的检测按需把它拉起来，之后 desktop 的
        # 多次执行共用这一份模型（见 functions/yolo_service.py）。放在这里早分支，
        # 服务进程不必付 GUI/worker 那套导入。
        from functions.yolo_service import serve

        return serve()

    if "--worker" in sys.argv:
        from desktop.worker import main as worker_main

        return worker_main()

    _prepare_gui_startup()

    from desktop.app import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
