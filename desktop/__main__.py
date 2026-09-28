# -*- coding: utf-8 -*-
"""支持 python -m desktop 与 hupper -m desktop 热重载开发。"""

import sys

from desktop.app import main

if __name__ == "__main__":
    # ⚠️ extract 渲染是多进程（见 utils/pdf_extract.render_pages_parallel）：
    #    spawn 子进程时本模块会以 __mp_main__ 被重新导入，靠此保护不会重跑 main()；
    #    打包环境还需要 freeze_support()（此处保留，两种入口行为一致）。
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
